"""Gitignore parsing and path matching utilities.

A scan honours every .gitignore from the scanned directory up to the home
directory, each one matched relative to ITS OWN directory as git does. A
layer that ignores the scanned directory itself (uv writes `.venv/.gitignore`
containing `*`) is set aside when that directory was named explicitly, and
the caller is told which file and pattern were overridden.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path


class GitignoreParser:
    """Parse and match paths against gitignore patterns."""

    def __init__(self, patterns: list[str]):
        """
        Initialize gitignore parser with patterns.

        Args:
            patterns: List of gitignore pattern strings
        """
        self.patterns: list[tuple[re.Pattern, bool, str]] = []
        for pattern in patterns:
            pattern = pattern.strip()
            # Skip empty lines and comments
            if not pattern or pattern.startswith("#"):
                continue
            self.patterns.append(self._compile_pattern(pattern))

    def _compile_pattern(self, pattern: str) -> tuple[re.Pattern, bool, str]:
        """
        Compile a gitignore pattern to regex.

        Returns:
            Tuple of (compiled_regex, is_negation, the pattern as written)
        """
        raw = pattern
        is_negation = pattern.startswith("!")
        if is_negation:
            pattern = pattern[1:]

        # Directory-only pattern: the trailing slash is stripped, but the
        # directory-only restriction itself is not enforced when matching.
        if pattern.endswith("/"):
            pattern = pattern[:-1]

        # Anchored pattern (starts with /)
        if pattern.startswith("/"):
            pattern = pattern[1:]
            anchored = True
        else:
            anchored = False

        # Convert gitignore glob to regex
        regex_parts = []
        i = 0
        while i < len(pattern):
            char = pattern[i]
            if char == "*":
                if i + 1 < len(pattern) and pattern[i + 1] == "*":
                    # ** matches any number of directories
                    regex_parts.append(".*")
                    i += 2
                    # Skip following /
                    if i < len(pattern) and pattern[i] == "/":
                        i += 1
                    continue
                else:
                    # * matches anything except /
                    regex_parts.append("[^/]*")
            elif char == "?":
                regex_parts.append("[^/]")
            elif char == "[":
                # Character class
                j = i + 1
                while j < len(pattern) and pattern[j] != "]":
                    j += 1
                if j < len(pattern):
                    regex_parts.append(pattern[i : j + 1])
                    i = j
                else:
                    regex_parts.append(re.escape(char))
            else:
                regex_parts.append(re.escape(char))
            i += 1

        regex_str = "".join(regex_parts)

        # Build final pattern
        # Pattern should match:
        # 1. The exact name (.venv matches .venv)
        # 2. The name as a directory (.venv matches .venv/)
        # 3. Anything under it (.venv matches .venv/foo/bar.py)

        if anchored:
            # Must match from start
            # Matches: exact name, or name followed by / and anything
            final_pattern = f"^{regex_str}(?:/.*)?$"
        else:
            # Can match anywhere in path
            # Matches at start or after /, then exact name or name/ with anything
            final_pattern = f"(?:^|/){regex_str}(?:/.*)?$"

        return (re.compile(final_pattern), is_negation, raw)

    def matches(self, path: str, is_dir: bool = False) -> bool:
        """
        Check if path matches any pattern.

        Args:
            path: Relative path to check
            is_dir: Whether the path is a directory

        Returns:
            True if path should be ignored
        """
        return self.decide(path, is_dir) is not None

    def decide(self, path: str, is_dir: bool = False) -> str | None:
        """The pattern (as written) that ignores the path, or None. The last
        matching pattern wins, as in git; a negation clears the decision."""
        if path.startswith("./"):
            path = path[2:]
        decision = None
        for regex, is_negation, raw in self.patterns:
            if regex.search(path):
                decision = None if is_negation else raw
        return decision


@dataclass
class IgnoreLayer:
    """One .gitignore file and where the scanned directory sits below it."""

    source: Path  # the .gitignore file
    prefix: str  # scan root relative to the file's directory; "" when it is the root
    parser: GitignoreParser

    def rooted(self, rel_path: str) -> str:
        return f"{self.prefix}/{rel_path}" if self.prefix else rel_path


class GitignoreStack:
    """All .gitignore layers above and at a directory, outermost first, each
    matched relative to its own directory; the last matching pattern wins."""

    PROBE = "__scantool_probe__"  # a name no real pattern spells out

    def __init__(self, layers: list[IgnoreLayer]):
        self.layers = layers

    def decide(self, path: str, is_dir: bool = False) -> str | None:
        """'<gitignore file>: <pattern>' for the pattern that ignores the
        path (relative to the scanned directory), or None."""
        if path.startswith("./"):
            path = path[2:]
        decision = None
        for layer in self.layers:
            rooted = layer.rooted(path)
            for regex, is_negation, raw in layer.parser.patterns:
                if regex.search(rooted):
                    decision = None if is_negation else f"{layer.source}: {raw}"
        return decision

    def matches(self, path: str, is_dir: bool = False) -> bool:
        return self.decide(path, is_dir) is not None

    def set_aside_root_ignores(self) -> list[tuple[Path, str]]:
        """Drop every layer that ignores the scanned directory itself or
        everything in it; return (file, pattern) for each. An explicitly
        named directory is meant to be read."""
        kept: list[IgnoreLayer] = []
        set_aside: list[tuple[Path, str]] = []
        for layer in self.layers:
            pattern = layer.parser.decide(layer.prefix, True) if layer.prefix else None
            pattern = pattern or layer.parser.decide(layer.rooted(self.PROBE), False)
            if pattern:
                set_aside.append((layer.source, pattern))
            else:
                kept.append(layer)
        self.layers = kept
        return set_aside


def load_gitignore(directory: Path) -> GitignoreStack | None:
    """
    Load the .gitignore files from directory and every parent up to the home
    directory (or the filesystem root), outermost first, each one matched
    relative to its own directory as git does.

    Returns:
        GitignoreStack, or None if no .gitignore holds a pattern
    """
    directory = directory.resolve()
    home = Path.home()
    layers: list[IgnoreLayer] = []
    current = directory
    while current != current.parent and current != home:
        gitignore_path = current / ".gitignore"
        if gitignore_path.exists():
            try:
                patterns = gitignore_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                patterns = []
            parser = GitignoreParser(patterns)
            if parser.patterns:
                prefix = os.path.relpath(directory, current).replace(os.sep, "/")
                layers.append(IgnoreLayer(gitignore_path, "" if prefix == "." else prefix, parser))
        current = current.parent
    if not layers:
        return None
    return GitignoreStack(list(reversed(layers)))
