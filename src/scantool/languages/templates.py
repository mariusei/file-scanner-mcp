"""Template preprocessing for HTML files with embedded template syntax.

Handles Jinja2/Django/Twig/Nunjucks/Liquid, Svelte, ERB/EJS, and Blade
template syntax by:
1. Extracting structural template nodes (blocks, conditionals, loops)
2. Neutralizing template syntax with same-length whitespace
3. Preserving all original line numbers exactly

The neutralized HTML can then be parsed by tree-sitter, and the template
nodes merged back into the final structure tree.
"""

import re
from dataclasses import dataclass
from typing import Optional

from .models import StructureNode


# ═══════════════════════════════════════════════════════════════════════
# Template dialect detection and tag patterns
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TemplateTag:
    """A single parsed template tag with position info."""
    kind: str         # "open", "close", "mid", "value", "comment", "meta"
    construct: str    # "if", "for", "block", "extends", "include", etc.
    expression: str   # The condition/variable/argument
    start: int        # Byte offset in source
    end: int          # Byte offset end
    line: int         # 1-based line number


# Dialect: Jinja2 / Django / Twig / Nunjucks / Liquid
# Syntax: {% tag %}, {{ expr }}, {# comment #}
_JINJA_BLOCK_TAG = re.compile(
    r'\{%-?\s*'
    r'(if|elif|else|endif|'
    r'for|empty|endfor|'
    r'block|endblock|'
    r'macro|endmacro|'
    r'call|endcall|'
    r'filter|endfilter|'
    r'with|endwith|'
    r'autoescape|endautoescape|'
    r'spaceless|endspaceless|'
    r'verbatim|endverbatim|'
    r'raw|endraw|'
    r'cache|endcache|'
    r'set|extends|include|import|from|load|url|static|trans|blocktrans|endblocktrans)'
    r'(?:\s+(.*?))?'
    r'\s*-?%\}',
    re.DOTALL,
)
_JINJA_VALUE = re.compile(r'\{\{-?\s*(.*?)\s*-?\}\}', re.DOTALL)
_JINJA_COMMENT = re.compile(r'\{#.*?#\}', re.DOTALL)

# Dialect: Svelte
# Syntax: {#if expr}, {:else}, {/if}, {#each expr}, {/each}
_SVELTE_BLOCK = re.compile(
    r'\{([#:/])'
    r'(if|else|each|await|then|catch|key|snippet)'
    r'(?:\s+(.*?))?'
    r'\}',
    re.DOTALL,
)

# Dialect: ERB / EJS / ASP
# Syntax: <% code %>, <%= expr %>, <%# comment %>
_ERB_TAG = re.compile(r'<%[=#-]?\s*(.*?)\s*-?%>', re.DOTALL)

# Dialect: Blade (Laravel)
# Syntax: @if(expr), @foreach(expr), @endif, @endforeach, etc.
_BLADE_BLOCK = re.compile(
    r'@(if|elseif|else|endif|'
    r'foreach|endforeach|'
    r'for|endfor|'
    r'while|endwhile|'
    r'forelse|empty|endforelse|'
    r'switch|case|break|default|endswitch|'
    r'unless|endunless|'
    r'isset|endisset|'
    r'section|endsection|show|'
    r'extends|include|yield|component|endcomponent|slot|endslot)'
    r'(?:\s*\((.*?)\))?',
    re.DOTALL,
)
_BLADE_VALUE = re.compile(r'\{\{\s*(.*?)\s*\}\}', re.DOTALL)
_BLADE_RAW_VALUE = re.compile(r'\{!!\s*(.*?)\s*!!\}', re.DOTALL)


# ═══════════════════════════════════════════════════════════════════════
# Construct classification tables
# ═══════════════════════════════════════════════════════════════════════

_JINJA_OPEN_CLOSE = {
    "if": "endif",
    "for": "endfor",
    "block": "endblock",
    "macro": "endmacro",
    "call": "endcall",
    "filter": "endfilter",
    "with": "endwith",
    "autoescape": "endautoescape",
    "spaceless": "endspaceless",
    "verbatim": "endverbatim",
    "raw": "endraw",
    "cache": "endcache",
    "blocktrans": "endblocktrans",
}
_JINJA_CLOSE_TO_OPEN = {v: k for k, v in _JINJA_OPEN_CLOSE.items()}
_JINJA_MID = {"elif", "else", "empty"}
_JINJA_META = {"extends", "include", "import", "from", "load", "url", "static",
               "trans", "set"}

_BLADE_OPEN_CLOSE = {
    "if": "endif",
    "foreach": "endforeach",
    "for": "endfor",
    "while": "endwhile",
    "forelse": "endforelse",
    "unless": "endunless",
    "isset": "endisset",
    "switch": "endswitch",
    "section": "endsection",
    "component": "endcomponent",
    "slot": "endslot",
}
_BLADE_CLOSE_TO_OPEN = {v: k for k, v in _BLADE_OPEN_CLOSE.items()}
_BLADE_MID = {"elseif", "else", "empty", "case", "default", "break"}
_BLADE_META = {"extends", "include", "yield", "show"}


class Dialect:
    JINJA = "jinja"
    SVELTE = "svelte"
    ERB = "erb"
    BLADE = "blade"
    NONE = "none"


def detect_dialect(source: str) -> str:
    """Detect which template dialect is present in the source."""
    sample = source[:4000]
    jinja_score = (
        len(re.findall(r'\{%', sample)) * 2
        + len(re.findall(r'\{\{', sample))
        + len(re.findall(r'\{#', sample))
    )
    svelte_score = len(re.findall(r'\{[#:/](?:if|each|await|key|snippet)', sample)) * 2
    erb_score = len(re.findall(r'<%', sample)) * 2
    blade_score = (
        len(re.findall(r'@(?:if|foreach|for|section|extends|include|yield)\b', sample)) * 2
        + len(re.findall(r'\{!!', sample))
    )

    # {{ }} alone is ambiguous (could be Handlebars, Blade, etc.)
    # Require at least score 2 to avoid false positives on JS objects
    scores = [
        (jinja_score, Dialect.JINJA),
        (svelte_score, Dialect.SVELTE),
        (erb_score, Dialect.ERB),
        (blade_score, Dialect.BLADE),
    ]
    best_score, best_dialect = max(scores, key=lambda x: x[0])
    if best_score < 2:
        return Dialect.NONE
    return best_dialect


# ═══════════════════════════════════════════════════════════════════════
# Tag extraction per dialect
# ═══════════════════════════════════════════════════════════════════════

def _line_at(source: str, offset: int) -> int:
    """1-based line number at byte offset."""
    return source[:offset].count("\n") + 1


def _extract_jinja_tags(source: str) -> list[TemplateTag]:
    """Extract all Jinja/Django/Twig template tags."""
    tags = []

    for m in _JINJA_BLOCK_TAG.finditer(source):
        keyword = m.group(1)
        expr = (m.group(2) or "").strip()
        line = _line_at(source, m.start())

        if keyword in _JINJA_OPEN_CLOSE:
            tags.append(TemplateTag("open", keyword, expr, m.start(), m.end(), line))
        elif keyword in _JINJA_CLOSE_TO_OPEN:
            tags.append(TemplateTag("close", _JINJA_CLOSE_TO_OPEN[keyword], expr,
                                    m.start(), m.end(), line))
        elif keyword in _JINJA_MID:
            tags.append(TemplateTag("mid", keyword, expr, m.start(), m.end(), line))
        elif keyword in _JINJA_META:
            tags.append(TemplateTag("meta", keyword, expr, m.start(), m.end(), line))

    for m in _JINJA_COMMENT.finditer(source):
        tags.append(TemplateTag("comment", "comment", "",
                                m.start(), m.end(), _line_at(source, m.start())))

    for m in _JINJA_VALUE.finditer(source):
        tags.append(TemplateTag("value", "expression", m.group(1).strip(),
                                m.start(), m.end(), _line_at(source, m.start())))

    tags.sort(key=lambda t: t.start)
    return tags


def _extract_svelte_tags(source: str) -> list[TemplateTag]:
    """Extract all Svelte template tags."""
    tags = []

    for m in _SVELTE_BLOCK.finditer(source):
        prefix = m.group(1)   # '#', ':', '/'
        keyword = m.group(2)
        expr = (m.group(3) or "").strip()
        line = _line_at(source, m.start())

        if prefix == "#":
            tags.append(TemplateTag("open", keyword, expr, m.start(), m.end(), line))
        elif prefix == "/":
            tags.append(TemplateTag("close", keyword, expr, m.start(), m.end(), line))
        elif prefix == ":":
            tags.append(TemplateTag("mid", keyword, expr, m.start(), m.end(), line))

    tags.sort(key=lambda t: t.start)
    return tags


def _extract_erb_tags(source: str) -> list[TemplateTag]:
    """Extract ERB/EJS tags. Limited structural info (no block matching)."""
    tags = []
    for m in _ERB_TAG.finditer(source):
        content = m.group(1).strip()
        line = _line_at(source, m.start())

        if re.match(r'(?:if|unless|case|while|for|do)\b', content):
            tags.append(TemplateTag("open", "erb-block", content,
                                    m.start(), m.end(), line))
        elif re.match(r'end\b', content):
            tags.append(TemplateTag("close", "erb-block", content,
                                    m.start(), m.end(), line))
        elif re.match(r'(?:elsif|else|when)\b', content):
            tags.append(TemplateTag("mid", content.split()[0], content,
                                    m.start(), m.end(), line))
        else:
            tags.append(TemplateTag("value", "erb-expr", content,
                                    m.start(), m.end(), line))

    tags.sort(key=lambda t: t.start)
    return tags


def _extract_blade_tags(source: str) -> list[TemplateTag]:
    """Extract Blade template tags."""
    tags = []

    for m in _BLADE_BLOCK.finditer(source):
        keyword = m.group(1)
        expr = (m.group(2) or "").strip()
        line = _line_at(source, m.start())

        if keyword in _BLADE_OPEN_CLOSE:
            tags.append(TemplateTag("open", keyword, expr, m.start(), m.end(), line))
        elif keyword in _BLADE_CLOSE_TO_OPEN:
            tags.append(TemplateTag("close", _BLADE_CLOSE_TO_OPEN[keyword], expr,
                                    m.start(), m.end(), line))
        elif keyword in _BLADE_MID:
            tags.append(TemplateTag("mid", keyword, expr, m.start(), m.end(), line))
        elif keyword in _BLADE_META:
            tags.append(TemplateTag("meta", keyword, expr, m.start(), m.end(), line))

    for m in _BLADE_VALUE.finditer(source):
        tags.append(TemplateTag("value", "expression", m.group(1).strip(),
                                m.start(), m.end(), _line_at(source, m.start())))
    for m in _BLADE_RAW_VALUE.finditer(source):
        tags.append(TemplateTag("value", "raw-expression", m.group(1).strip(),
                                m.start(), m.end(), _line_at(source, m.start())))

    tags.sort(key=lambda t: t.start)
    return tags


# ═══════════════════════════════════════════════════════════════════════
# Stack-based block matching → StructureNode tree
# ═══════════════════════════════════════════════════════════════════════

_TEMPLATE_DISPLAY = {
    "if": "if",
    "elif": "elif",
    "else": "else",
    "for": "for",
    "foreach": "for",
    "each": "each",
    "block": "block",
    "macro": "macro",
    "with": "with",
    "section": "section",
    "component": "component",
    "slot": "slot",
    "unless": "unless",
    "await": "await",
    "key": "key",
    "snippet": "snippet",
    "erb-block": "block",
    "forelse": "for",
    "filter": "filter",
    "switch": "switch",
    "isset": "isset",
    "autoescape": "autoescape",
}


def _build_template_tree(tags: list[TemplateTag], total_lines: int = 0) -> list[StructureNode]:
    """Build a tree of StructureNodes from matched template tags.

    Uses a stack to match open/close pairs and nest mid-tags (else/elif)
    as children of their parent block.
    """
    root: list[StructureNode] = []
    stack: list[tuple[TemplateTag, StructureNode]] = []  # (open_tag, node)

    for tag in tags:
        if tag.kind == "open":
            display = _TEMPLATE_DISPLAY.get(tag.construct, tag.construct)
            name = f"{display}: {tag.expression}" if tag.expression else display
            node = StructureNode(
                type=f"template-{display}",
                name=name,
                start_line=tag.line,
                end_line=tag.line,
                modifiers=["template"],
            )
            stack.append((tag, node))

        elif tag.kind == "close":
            # Pop stack until matching open
            if stack and stack[-1][0].construct == tag.construct:
                _, node = stack.pop()
                node.end_line = tag.line
                if stack:
                    stack[-1][1].children.append(node)
                else:
                    root.append(node)
            # Unmatched close — ignore gracefully

        elif tag.kind == "mid":
            # Mid-tags (else, elif, empty) close the previous branch
            # and open a new sibling within the same parent block
            display = _TEMPLATE_DISPLAY.get(tag.construct, tag.construct)
            name = f"{display}: {tag.expression}" if tag.expression else display
            node = StructureNode(
                type=f"template-{display}",
                name=name,
                start_line=tag.line,
                end_line=tag.line,
                modifiers=["template"],
            )
            if stack:
                stack[-1][1].children.append(node)

        elif tag.kind == "meta":
            node = StructureNode(
                type=f"template-{tag.construct}",
                name=f"{tag.construct}: {tag.expression}" if tag.expression else tag.construct,
                start_line=tag.line,
                end_line=tag.line,
                modifiers=["template"],
            )
            if stack:
                stack[-1][1].children.append(node)
            else:
                root.append(node)

    # Flush unclosed blocks — set end_line to end of source
    last_line = max(total_lines, tags[-1].line if tags else 1)
    while stack:
        _, node = stack.pop()
        if node.end_line == node.start_line:
            node.end_line = last_line
        if stack:
            stack[-1][1].children.append(node)
        else:
            root.append(node)

    return _filter_noise(root)


# Structural types — always keep
_KEEP_TYPES = {
    "template-extends", "template-from", "template-import",
    "template-include", "template-block", "template-macro",
    "template-component", "template-slot", "template-section",
}

# Conditional/loop types — keep only if they span multiple lines
_KEEP_IF_MULTILINE = {
    "template-if", "template-for", "template-each",
    "template-unless", "template-await", "template-with",
    "template-filter", "template-switch", "template-forelse",
    "template-isset", "template-key", "template-snippet",
}

# Mid-tags — keep as children of kept parents
_MID_TYPES = {
    "template-elif", "template-else", "template-empty",
}

# Everything else (set, url, static, load, trans, etc.) is noise


def _is_single_line_block(node: StructureNode) -> bool:
    """Check if a node and all its descendants fit on one line."""
    if node.end_line > node.start_line:
        return False
    return all(_is_single_line_block(c) for c in node.children)


def _filter_noise(nodes: list[StructureNode]) -> list[StructureNode]:
    """Remove noise nodes, keeping only structural and navigational ones.

    Rules:
    - Always keep: extends, from, include, block, macro, component, section
    - Keep if multi-line: if, for, each, unless, await, etc.
    - Keep mid-tags (elif, else, empty) only as children of kept parents
    - Drop: set, url, static, load, trans, and other utilities
    - Drop: single-line if/else/endif (inline ternaries)
    """
    result = []
    for node in nodes:
        node.children = _filter_noise(node.children)

        if node.type in _KEEP_TYPES:
            result.append(node)
        elif node.type in _KEEP_IF_MULTILINE:
            if not _is_single_line_block(node) and (node.end_line > node.start_line or node.children):
                result.append(node)
            # Single-line block: drop entirely (don't promote mid-tag orphans)
        elif node.type in _MID_TYPES:
            result.append(node)
        else:
            result.extend(node.children)

    return result


# ═══════════════════════════════════════════════════════════════════════
# Neutralization: replace template syntax with same-length whitespace
# ═══════════════════════════════════════════════════════════════════════

def _neutralize(source: str, tags: list[TemplateTag]) -> str:
    """Replace all template tags with whitespace of identical length.

    Preserves newlines within multi-line tags so line numbers stay exact.
    """
    chars = list(source)
    for tag in tags:
        for i in range(tag.start, min(tag.end, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


# ═══════════════════════════════════════════════════════════════════════
# Merge: interleave template and HTML structure trees
# ═══════════════════════════════════════════════════════════════════════

def merge_trees(
    template_nodes: list[StructureNode],
    html_nodes: list[StructureNode],
) -> list[StructureNode]:
    """Merge template structure nodes and HTML structure nodes into one tree.

    Uses line spans to determine containment: a template block that spans
    lines 10-50 becomes the parent of HTML elements on lines 15-45.
    """
    if not template_nodes:
        return html_nodes
    if not html_nodes:
        return template_nodes

    all_nodes = []
    for n in template_nodes:
        all_nodes.append(("template", n))
    for n in html_nodes:
        all_nodes.append(("html", n))

    all_nodes.sort(key=lambda x: (x[1].start_line, -x[1].end_line))

    return _nest_by_span(all_nodes)


def _nest_by_span(tagged_nodes: list[tuple[str, StructureNode]]) -> list[StructureNode]:
    """Nest nodes by their line spans using a stack.

    A node whose span is fully contained within another becomes its child.
    """
    result: list[StructureNode] = []
    stack: list[StructureNode] = []

    for origin, node in tagged_nodes:
        # Collect the node's own children to re-merge later
        original_children = node.children
        node.children = []

        # Pop stack until we find a parent that contains this node
        while stack and stack[-1].end_line < node.start_line:
            stack.pop()

        if stack and stack[-1].end_line >= node.end_line:
            stack[-1].children.append(node)
        else:
            result.append(node)

        # Only push container nodes (those that span multiple lines)
        if node.end_line > node.start_line:
            stack.append(node)

        # Re-merge original children into the node
        if original_children:
            sub_tagged = [(origin, c) for c in original_children]
            existing_tagged = [("existing", c) for c in node.children]
            all_children = sub_tagged + existing_tagged
            all_children.sort(key=lambda x: (x[1].start_line, -x[1].end_line))
            node.children = _nest_by_span(all_children)


    return result


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PreprocessResult:
    """Result of template preprocessing."""
    cleaned_source: bytes
    template_nodes: list[StructureNode]
    dialect: str
    tag_count: int


def preprocess(source_code: bytes) -> Optional[PreprocessResult]:
    """Preprocess HTML source with template syntax.

    Returns None if no template syntax detected.
    Returns PreprocessResult with cleaned HTML and extracted template structure.
    """
    try:
        source = source_code.decode("utf-8", errors="replace")
    except Exception:
        return None

    dialect = detect_dialect(source)
    if dialect == Dialect.NONE:
        return None

    if dialect == Dialect.JINJA:
        tags = _extract_jinja_tags(source)
    elif dialect == Dialect.SVELTE:
        tags = _extract_svelte_tags(source)
    elif dialect == Dialect.ERB:
        tags = _extract_erb_tags(source)
    elif dialect == Dialect.BLADE:
        tags = _extract_blade_tags(source)
    else:
        return None

    if not tags:
        return None

    total_lines = source.count("\n") + 1
    template_nodes = _build_template_tree(tags, total_lines)
    cleaned = _neutralize(source, tags)

    return PreprocessResult(
        cleaned_source=cleaned.encode("utf-8"),
        template_nodes=template_nodes,
        dialect=dialect,
        tag_count=len(tags),
    )
