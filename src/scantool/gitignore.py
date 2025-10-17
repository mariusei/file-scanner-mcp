"""Gitignore parsing and path matching utilities."""

import re
from pathlib import Path
from typing import Optional


class GitignoreParser:
    """Parse and match paths against gitignore patterns."""

    def __init__(self, patterns: list[str]):
        """
        Initialize gitignore parser with patterns.

        Args:
            patterns: List of gitignore pattern strings
        """
        self.patterns = []
        for pattern in patterns:
            pattern = pattern.strip()
            # Skip empty lines and comments
            if not pattern or pattern.startswith('#'):
                continue
            self.patterns.append(self._compile_pattern(pattern))

    def _compile_pattern(self, pattern: str) -> tuple[re.Pattern, bool]:
        """
        Compile a gitignore pattern to regex.

        Returns:
            Tuple of (compiled_regex, is_negation)
        """
        is_negation = pattern.startswith('!')
        if is_negation:
            pattern = pattern[1:]

        # Directory-only pattern
        if pattern.endswith('/'):
            pattern = pattern[:-1]
            is_dir_only = True
        else:
            is_dir_only = False

        # Anchored pattern (starts with /)
        if pattern.startswith('/'):
            pattern = pattern[1:]
            anchored = True
        else:
            anchored = False

        # Convert gitignore glob to regex
        regex_parts = []
        i = 0
        while i < len(pattern):
            char = pattern[i]
            if char == '*':
                if i + 1 < len(pattern) and pattern[i + 1] == '*':
                    # ** matches any number of directories
                    regex_parts.append('.*')
                    i += 2
                    # Skip following /
                    if i < len(pattern) and pattern[i] == '/':
                        i += 1
                    continue
                else:
                    # * matches anything except /
                    regex_parts.append('[^/]*')
            elif char == '?':
                regex_parts.append('[^/]')
            elif char == '[':
                # Character class
                j = i + 1
                while j < len(pattern) and pattern[j] != ']':
                    j += 1
                if j < len(pattern):
                    regex_parts.append(pattern[i:j + 1])
                    i = j
                else:
                    regex_parts.append(re.escape(char))
            else:
                regex_parts.append(re.escape(char))
            i += 1

        regex_str = ''.join(regex_parts)

        # Build final pattern
        # Pattern should match:
        # 1. The exact name (.venv matches .venv)
        # 2. The name as a directory (.venv matches .venv/)
        # 3. Anything under it (.venv matches .venv/foo/bar.py)

        if anchored:
            # Must match from start
            # Matches: exact name, or name followed by / and anything
            final_pattern = f'^{regex_str}(?:/.*)?$'
        else:
            # Can match anywhere in path
            # Matches at start or after /, then exact name or name/ with anything
            final_pattern = f'(?:^|/){regex_str}(?:/.*)?$'

        return (re.compile(final_pattern), is_negation)

    def matches(self, path: str, is_dir: bool = False) -> bool:
        """
        Check if path matches any pattern.

        Args:
            path: Relative path to check
            is_dir: Whether the path is a directory

        Returns:
            True if path should be ignored
        """
        # Normalize path (remove leading ./ if present)
        if path.startswith('./'):
            path = path[2:]

        ignored = False
        for regex, is_negation in self.patterns:
            if regex.search(path):
                ignored = not is_negation

        return ignored


def load_gitignore(directory: Path) -> Optional[GitignoreParser]:
    """
    Load .gitignore file from directory.

    Args:
        directory: Directory to search for .gitignore

    Returns:
        GitignoreParser or None if no .gitignore found
    """
    gitignore_path = directory / '.gitignore'
    if not gitignore_path.exists():
        return None

    try:
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            patterns = f.readlines()
        return GitignoreParser(patterns)
    except Exception:
        return None
