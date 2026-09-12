"""
FIL: languages/yaml.py

PROBLEM:
  YAML files (.yaml, .yml) were handled by ConfigLanguage, whose scan()
  returns an empty list by design (see config.py). That leaves GitHub
  Actions workflows, Kubernetes manifests, docker-compose files and every
  other YAML document with no visible structure: no jobs, no steps, no
  keys, no line numbers.

SOLUTION:
  A dedicated tree-sitter-backed handler (grammar from
  tree_sitter_language_pack, already a dependency) that turns the YAML
  parse tree into StructureNode trees:
    - top-level keys become nodes, nested mappings become their children
    - sequences become a node whose signature carries the item count (and
      a compact scalar preview when every item is a short scalar)
    - sequence items that are themselves mappings (e.g. a workflow's
      `steps:` list) become child nodes named after their own "name" key,
      so `steps[].name` shows up without a special case for "steps"
    - scalars (plain, quoted, block `|`/`>`) become leaf nodes with a
      truncated, single-line signature
    - anchors and aliases are shown as modifiers/signature (`anchor:foo`,
      `*foo`) — never resolved
    - a multi-document file (`---`) becomes one synthetic "document N"
      node per document, wrapping that document's top-level keys
    - full-line comments are structure too (in a config file they carry
      the explanation): a single comment line directly above a key is that
      key's docstring; every other block of consecutive comment lines (or a
      lone line of at least COMMENT_BLOCK_MIN_CHARS) becomes a `comment`
      node placed right before the key that follows it — a file header
      separated from the first key by a blank line is therefore a `comment`
      node, and focus= prints it verbatim. Placement is by the following
      key, not by indentation. A comment trailing a key on the same line
      is left alone (it is neither a block nor a docstring), and comments
      inside flow collections (`[...]`, `{...}`) are ignored. The rule and
      the node shape live in base.CommentBlocks, shared with TOML.
  Every node's synthetic flag is computed the same way the golden/synthetic
  test checks it: true unless the node's name literally appears on its own
  start_line.

  The import/entry-point logic ConfigLanguage used to run for .yaml/.yml
  (docker-compose env_file/dockerfile/volume references, the generic
  relative-path scan, and the docker-compose project/services entry
  points) moves here unchanged so behaviour for those files is identical
  to before.

SCOPE:
  - Real structure for arbitrary YAML (mappings, sequences, scalars,
    anchors/aliases, block scalars, multi-document streams)
  - docker-compose imports/entry points (moved from config.py)
  - Not in scope: schema validation, resolving anchors/aliases/merge keys
  - Not in scope: YAML 1.2 core-schema tag resolution (tags shown verbatim)
"""

import re
from pathlib import Path

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_language as get_packed_grammar

from .base import BaseLanguage, CommentBlocks
from .models import (
    CallInfo,
    DefinitionInfo,
    EntryPointInfo,
    ImportInfo,
    StructureNode,
)

# Container/value node types produced by the tree-sitter-yaml grammar.
_WRAPPER_TYPES = ("block_node", "flow_node")
_MAPPING_TYPES = ("block_mapping", "flow_mapping")
_SEQUENCE_TYPES = ("block_sequence", "flow_sequence")
_PAIR_TYPES = ("block_mapping_pair", "flow_pair")

# Signature/preview truncation length, shared by scalars and sequence previews.
_PREVIEW_LIMIT = 60


class _Src:
    """Source bytes, their decoded lines and the file's comment blocks,
    computed once per scan()."""

    __slots__ = ("bytes", "lines", "comments")

    def __init__(self, source_code: bytes, comments: CommentBlocks):
        self.bytes = source_code
        self.lines = source_code.decode("utf-8", errors="replace").split("\n")
        self.comments = comments


class YAMLLanguage(BaseLanguage):
    """Unified language handler for YAML files (.yaml, .yml)."""

    # Key used to label a sequence item that is itself a mapping (a GitHub
    # Actions step, a Kubernetes container, ...). When present, its value
    # becomes the item's node name and the key is not repeated as a child.
    _ITEM_LABEL_KEY = "name"

    CONDENSE_STRATEGY = "compact"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = get_packed_grammar("yaml")

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".yaml", ".yml"]

    @classmethod
    def get_language_name(cls) -> str:
        return "YAML"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (identical to config.py's handling of these filenames)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip lock files and minified YAML."""
        filename_lower = filename.lower()
        if filename_lower == "pnpm-lock.yaml":
            return True
        if filename_lower.endswith(".lock"):
            return True
        return ".min." in filename_lower

    def should_analyze(self, file_path: str) -> bool:
        """Skip lock files and minified YAML."""
        filename = Path(file_path).name.lower()
        if filename == "pnpm-lock.yaml":
            return False
        if filename.endswith(".lock"):
            return False
        return ".min." not in filename

    # ===========================================================================
    # Regex fallback for severely malformed files
    # ===========================================================================

    REGEX_FALLBACK_PATTERNS = [
        {"pattern": r"^[ \t]*([A-Za-z0-9_.\-]+):", "type": "key"},
    ]

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Turn a YAML `stream` into StructureNodes.

        A single-document stream contributes its top-level keys directly.
        A multi-document stream (separated by `---`) wraps each document's
        keys in a synthetic "document N" node, since nothing in the source
        names the document itself.
        """
        src = _Src(
            source_code, CommentBlocks(self._full_line_comments(root, source_code), _PREVIEW_LIMIT)
        )
        documents = [c for c in root.children if c.type == "document"]
        if not documents:
            return src.comments.rest()
        if len(documents) == 1:
            return self._document_top_level(documents[0], src) + src.comments.rest()
        nodes = [
            self._make_node(
                "document",
                f"document {i}",
                doc.start_point[0] + 1,
                doc.end_point[0] + 1,
                src,
                children=self._document_top_level(doc, src),
            )
            for i, doc in enumerate(documents, start=1)
        ]
        nodes[-1].children.extend(src.comments.rest())
        return nodes

    def _full_line_comments(self, root: Node, source_code: bytes) -> list[tuple[int, str]]:
        """(line, text) of every comment that has a line to itself, in source
        order. A comment sharing its line with a key (trailing comment) is
        skipped, as is anything inside a flow collection."""
        comments: list[tuple[int, str]] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "comment":
                prev = node.prev_sibling
                on_own_line = prev is None or prev.end_point[0] < node.start_point[0]
                if on_own_line and not (node.parent and node.parent.type.startswith("flow_")):
                    text = self._get_node_text(node, source_code).lstrip("#").strip()
                    comments.append((node.start_point[0] + 1, text))
            else:
                stack.extend(reversed(node.children))
        return comments

    def _document_top_level(self, doc_node: Node, src: "_Src") -> list[StructureNode]:
        content = next((c for c in doc_node.children if c.type in _WRAPPER_TYPES), None)
        if content is None:
            return []
        anchor, tag, inner = self._unwrap_value(content, src)
        if inner is None:
            return []
        if inner.type in _MAPPING_TYPES:
            return self._mapping_children(inner, src)
        # A document whose top level is a bare sequence or scalar (rare):
        # one synthetic node stands in for the whole document.
        return [
            self._value_to_node(
                inner,
                "document",
                content.start_point[0] + 1,
                content.end_point[0] + 1,
                src,
                anchor,
                tag,
            )
        ]

    def _unwrap_value(
        self, node: Node | None, src: "_Src"
    ) -> tuple[str | None, str | None, Node | None]:
        """Peel through block_node/flow_node wrappers to the real value,
        capturing any anchor/tag seen along the way. Anchors and aliases
        are surfaced (in modifiers/signature), never resolved."""
        anchor = None
        tag = None
        while node is not None and node.type in _WRAPPER_TYPES:
            rest = None
            for child in node.children:
                if child.type == "anchor":
                    anchor = self._anchor_or_alias_name(child, src)
                elif child.type == "tag":
                    tag = self._get_node_text(child, src.bytes)
                else:
                    rest = child
            node = rest
        return anchor, tag, node

    def _anchor_or_alias_name(self, node: Node, src: "_Src") -> str:
        for child in node.children:
            if child.type in ("anchor_name", "alias_name"):
                return self._get_node_text(child, src.bytes)
        return self._get_node_text(node, src.bytes).lstrip("&*")

    def _split_pair(self, pair_node: Node) -> tuple[Node | None, Node | None]:
        key_node = None
        value_node = None
        seen_colon = False
        for child in pair_node.children:
            if child.type == ":":
                seen_colon = True
            elif not seen_colon:
                key_node = child
            else:
                value_node = child
        return key_node, value_node

    def _key_text(self, key_node: Node, src: "_Src") -> str | None:
        _, _, inner = self._unwrap_value(key_node, src)
        if inner is None:
            return None
        return self._normalize_signature(self._get_node_text(inner, src.bytes))

    def _scalar_text(self, node: Node | None, src: "_Src") -> str | None:
        if node is None:
            return None
        return self._normalize_signature(self._get_node_text(node, src.bytes))

    def _compact(self, text: str, limit: int = _PREVIEW_LIMIT) -> str:
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text

    def _mapping_children(
        self, mapping_node: Node, src: "_Src", skip_key: str | None = None
    ) -> list[StructureNode]:
        children: list[StructureNode] = []
        for pair in mapping_node.children:
            if pair.type not in _PAIR_TYPES:
                continue
            key_node, value_node = self._split_pair(pair)
            if key_node is None:
                continue
            key_text = self._key_text(key_node, src)
            if not key_text or key_text == skip_key:
                continue
            anchor, tag, inner = (
                self._unwrap_value(value_node, src)
                if value_node is not None
                else (None, None, None)
            )
            leading, docstring = src.comments.before(pair.start_point[0] + 1)
            children.extend(leading)
            node = self._value_to_node(
                inner,
                key_text,
                pair.start_point[0] + 1,
                pair.end_point[0] + 1,
                src,
                anchor,
                tag,
            )
            node.docstring = docstring
            children.append(node)
        return children

    def _value_to_node(
        self,
        inner: Node | None,
        name: str,
        start_line: int,
        end_line: int,
        src: "_Src",
        anchor: str | None = None,
        tag: str | None = None,
    ) -> StructureNode:
        modifiers = []
        if anchor:
            modifiers.append(f"anchor:{anchor}")
        if tag:
            modifiers.append(f"tag:{tag}")

        if inner is None:
            return self._make_node(
                "scalar", name, start_line, end_line, src, signature="null", modifiers=modifiers
            )

        if inner.type in _MAPPING_TYPES:
            children = self._mapping_children(inner, src)
            signature = f"{len(children)} key{'' if len(children) == 1 else 's'}"
            return self._make_node(
                "mapping",
                name,
                start_line,
                end_line,
                src,
                children=children,
                signature=signature,
                modifiers=modifiers,
            )

        if inner.type in _SEQUENCE_TYPES:
            return self._sequence_to_node(inner, name, start_line, end_line, src, modifiers)

        if inner.type == "alias":
            alias_name = self._anchor_or_alias_name(inner, src)
            modifiers.append("alias")
            return self._make_node(
                "scalar",
                name,
                start_line,
                end_line,
                src,
                signature=f"*{alias_name}",
                modifiers=modifiers,
            )

        if inner.type == "block_scalar":
            raw = self._get_node_text(inner, src.bytes)
            modifiers.append("literal" if raw.lstrip().startswith("|") else "folded")
            return self._make_node(
                "scalar",
                name,
                start_line,
                end_line,
                src,
                signature=self._compact(self._scalar_text(inner, src) or ""),
                modifiers=modifiers,
            )

        text = self._compact(self._scalar_text(inner, src) or "")
        return self._make_node(
            "scalar", name, start_line, end_line, src, signature=text, modifiers=modifiers
        )

    def _sequence_to_node(
        self,
        seq_node: Node,
        name: str,
        start_line: int,
        end_line: int,
        src: "_Src",
        modifiers: list[str],
    ) -> StructureNode:
        items = self._sequence_items(seq_node, src)
        children: list[StructureNode] = []
        scalars: list[str] = []
        for item_inner, item_anchor, item_tag, item_start, item_end in items:
            is_mapping = item_inner is not None and item_inner.type in _MAPPING_TYPES
            leading, docstring = src.comments.before(item_start, attachable=is_mapping)
            children.extend(leading)
            if item_inner is not None and is_mapping:
                label = self._item_label(item_inner, src)
                item_modifiers = []
                if item_anchor:
                    item_modifiers.append(f"anchor:{item_anchor}")
                if item_tag:
                    item_modifiers.append(f"tag:{item_tag}")
                item_children = self._mapping_children(
                    item_inner, src, skip_key=self._ITEM_LABEL_KEY if label else None
                )
                children.append(
                    self._make_node(
                        "item",
                        label or f"[{sum(c.type == 'item' for c in children)}]",
                        item_start,
                        item_end,
                        src,
                        children=item_children,
                        modifiers=item_modifiers,
                        docstring=docstring,
                    )
                )
            else:
                text = self._scalar_text(item_inner, src) if item_inner is not None else None
                if text is not None:
                    scalars.append(text)

        n = len(items)
        if any(c.type == "item" for c in children):
            signature = f"{n} item{'' if n == 1 else 's'}"
        else:
            signature = self._sequence_signature(n, scalars)
        return self._make_node(
            "sequence",
            name,
            start_line,
            end_line,
            src,
            children=children,
            signature=signature,
            modifiers=modifiers,
        )

    def _sequence_signature(self, n: int, scalars: list[str]) -> str:
        if n == 0:
            return "0 items"
        if len(scalars) == n and n <= 5:
            preview = self._compact(", ".join(scalars))
            return f"[{n}] {preview}"
        return f"{n} item{'' if n == 1 else 's'}"

    def _sequence_items(
        self, seq_node: Node, src: "_Src"
    ) -> list[tuple[Node | None, str | None, str | None, int, int]]:
        items: list[tuple[Node | None, str | None, str | None, int, int]] = []
        if seq_node.type == "block_sequence":
            for child in seq_node.children:
                if child.type != "block_sequence_item":
                    continue
                value_node = next((gc for gc in child.children if gc.type != "-"), None)
                anchor, tag, inner = (
                    self._unwrap_value(value_node, src)
                    if value_node is not None
                    else (None, None, None)
                )
                items.append((inner, anchor, tag, child.start_point[0] + 1, child.end_point[0] + 1))
        else:  # flow_sequence
            for child in seq_node.children:
                if child.type != "flow_node":
                    continue
                anchor, tag, inner = self._unwrap_value(child, src)
                items.append((inner, anchor, tag, child.start_point[0] + 1, child.end_point[0] + 1))
        return items

    def _item_label(self, item_inner: Node, src: "_Src") -> str | None:
        for pair in item_inner.children:
            if pair.type not in _PAIR_TYPES:
                continue
            key_node, value_node = self._split_pair(pair)
            if key_node is None or value_node is None:
                continue
            if self._key_text(key_node, src) != self._ITEM_LABEL_KEY:
                continue
            _, _, value_inner = self._unwrap_value(value_node, src)
            text = self._scalar_text(value_inner, src) if value_inner is not None else None
            if text:
                return self._compact(text)
        return None

    def _make_node(
        self,
        node_type: str,
        name: str,
        start_line: int,
        end_line: int,
        src: "_Src",
        **kwargs,
    ) -> StructureNode:
        """Build a node, computing `synthetic` the same way the synthetic-flag
        test does: false only when the name literally appears on the line
        that declares it."""
        first_line = src.lines[start_line - 1] if 0 < start_line <= len(src.lines) else ""
        return StructureNode(
            type=node_type,
            name=name,
            start_line=start_line,
            end_line=end_line,
            synthetic=name not in first_line,
            **kwargs,
        )

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # (moved from config.py's ConfigLanguage: behaviour for .yaml/.yml is
    # unchanged — docker-compose references plus the generic relative-path
    # scan that used to run for every config file type)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract file path references from YAML files.

        Handles docker-compose.yml env_file/dockerfile/volume references,
        plus generic relative file path patterns found in any YAML file.
        """
        imports: list[ImportInfo] = []
        filename = Path(file_path).name.lower()

        if "docker-compose" in filename:
            imports.extend(self._extract_docker_compose_imports(file_path, content))

        imports.extend(self._extract_path_patterns(file_path, content))
        return imports

    def _extract_docker_compose_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from docker-compose.yml files."""
        imports: list[ImportInfo] = []

        # env_file: .env.production or env_file: .env
        env_file_pattern = r'env_file:\s*["\']?(\.env[^\s"\']*)["\']?'
        for match in re.finditer(env_file_pattern, content):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="env_file",
                )
            )

        # dockerfile: ./Dockerfile.prod
        dockerfile_pattern = r'dockerfile:\s*["\']?([^\s"\']+Dockerfile[^\s"\']*)["\']?'
        for match in re.finditer(dockerfile_pattern, content, re.IGNORECASE):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="dockerfile",
                )
            )

        # volumes: - ./data:/app/data
        volume_pattern = r'[-\s]+["\']?(\.{1,2}/[^:\s"\']+):[^\s"\']+["\']?'
        for match in re.finditer(volume_pattern, content):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="volume_mount",
                )
            )

        return imports

    def _extract_path_patterns(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract generic relative file path patterns from YAML.

        Conservative patterns: relative paths (./x, ../x), quoted or bare,
        with a file extension. URLs are excluded.
        """
        imports: list[ImportInfo] = []

        quoted_path_pattern = r'["\'](\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+|\.\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+)["\']'
        for match in re.finditer(quoted_path_pattern, content):
            path = match.group(1)
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        # Unquoted relative paths on their own line: "  - ./file.ext" or "key: ./file.ext"
        unquoted_path_pattern = (
            r"(?:^|\s)(\./[^\s:]+\.[a-zA-Z0-9]+|\.\./(?:[^/\s]+/)*[^/\s]+\.[a-zA-Z0-9]+)(?:\s|$)"
        )
        for match in re.finditer(unquoted_path_pattern, content, re.MULTILINE):
            path = match.group(1)
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in YAML files (docker-compose projects/services)."""
        entry_points: list[EntryPointInfo] = []
        filename = Path(file_path).name.lower()

        if "docker-compose" in filename:
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="project_config",
                    name="docker_compose_project",
                    line=1,
                    framework="Docker",
                )
            )

            services_pattern = r"^services:\s*$"
            for match in re.finditer(services_pattern, content, re.MULTILINE):
                line = content[: match.start()].count("\n") + 1
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="services_section",
                        name="services",
                        line=line,
                        framework="Docker",
                    )
                )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """YAML files don't have function/class definitions."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """YAML files don't have function calls."""
        return []

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """All YAML config files go to the config cluster (matches ConfigLanguage)."""
        return "config"

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> str | None:
        """Resolve a YAML file reference to a file path (same rule as ConfigLanguage:
        direct match, then relative to the source file's directory)."""
        if module in all_files:
            return module

        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None
