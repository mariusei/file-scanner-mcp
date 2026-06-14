"""Data models for the unified language system.

This module contains all data structures used by both scanners (structure extraction)
and analyzers (semantic analysis). Combining them here ensures consistency and
allows languages to share common structures.
"""

from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# Structure models (from scanners)
# ===========================================================================


@dataclass
class StructureNode:
    """Represents a node in the file structure with rich metadata.

    Used by scan() to represent classes, functions, methods, and other
    structural elements in source code.
    """

    type: str  # e.g., "class", "function", "method", "heading"
    name: str
    start_line: int
    end_line: int
    children: list["StructureNode"] = field(default_factory=list)

    # Enhanced metadata (optional)
    signature: Optional[str] = None  # Function signature with types
    decorators: list[str] = field(default_factory=list)  # @decorators
    docstring: Optional[str] = None  # First line of docstring
    complexity: Optional[dict] = None  # {"lines": int, "depth": int, "branches": int}
    modifiers: list[str] = field(default_factory=list)  # async, static, public, etc.
    file_metadata: Optional[dict] = None  # File-level metadata: size, timestamps

    # Entropy-based saliency (set by FileScanner._annotate_salient_code)
    code_excerpt: Optional[list[str]] = None  # Verbatim source lines for salient nodes
    code_skeleton: Optional[list[str]] = None  # Condensed method skeleton (preferred display)
    saliency: Optional[float] = None  # Normalized saliency score for selected nodes
    recent_edits: Optional[int] = None  # Distinct commits behind this node's lines (90d window)
    delta_status: Optional[str] = None  # "new"/"changed" vs previous scan (delta mode)

    def __repr__(self):
        return f"{self.type}: {self.name} ({self.start_line}-{self.end_line})"


# ===========================================================================
# Analysis models (from analyzers)
# ===========================================================================


@dataclass
class ImportInfo:
    """Information about an import statement."""

    source_file: str  # File doing the import
    target_module: str  # Module being imported
    line: int  # Line number of import
    import_type: str  # "from_import", "import", "relative", "absolute"
    imported_names: list[str] = field(default_factory=list)  # Specific names imported


@dataclass
class EntryPointInfo:
    """Information about an entry point in the codebase."""

    file: str  # File containing entry point
    type: str  # "main_function", "if_main", "app_instance", "export"
    name: Optional[str] = None  # Function/variable name if applicable
    line: int = 0  # Line number
    framework: Optional[str] = None  # "Flask", "FastAPI", etc.


@dataclass
class DefinitionInfo:
    """Information about a function/class/method definition."""

    file: str  # File containing definition
    type: str  # "function", "class", "method"
    name: str  # Name of function/class
    line: int  # Starting line number
    signature: Optional[str] = None  # Full signature
    parent: Optional[str] = None  # Parent class if method
    # Reachability facts the call graph cannot see (carried from StructureNode so
    # dead-detection can read them language-agnostically). Each language already
    # emits these: visibility in modifiers (Go cap->"public", Rust "pub", TS
    # "export", Java/C# "public"), framework registration in decorators.
    modifiers: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class CallInfo:
    """Information about a function call."""

    caller_file: str  # File where call is made
    caller_name: Optional[str]  # Function/method making the call
    callee_name: str  # Function/method being called
    line: int  # Line number of call
    is_cross_file: bool = False  # True if calling function in another file


# ===========================================================================
# Graph models (for code map analysis)
# ===========================================================================


@dataclass
class CallGraphNode:
    """Node in the call graph."""

    name: str  # Fully qualified name
    file: str  # File containing this definition
    type: str  # "function", "class", "method"
    callers: list[str] = field(default_factory=list)  # Who calls this
    callees: list[str] = field(default_factory=list)  # Who this calls
    # Weighted in/out degree. For an unambiguous name these equal the distinct
    # caller/callee counts (weight 1). When a call resolves to k candidates the
    # edge credit is split 1/k across them, so an arbitrary tie-break can no
    # longer crown one node — see experiments/bucket_entropy/.
    in_weight: float = 0.0
    out_weight: float = 0.0
    centrality_score: float = 0.0  # Centrality metric


@dataclass
class DivergenceFinding:
    """A site that breaks a call-co-occurrence pattern its siblings follow.

    Mined by consensus.find_divergences(): among the callers of `anchor`, a
    strong majority also call `missing`, but `site` does not. This is a review
    signal ("look here"), NOT a defect claim — peers may legitimately differ.
    """

    site: str  # "file:caller" that diverges (the outlier)
    anchor: str  # shared callee X that defines the cohort (callers of X)
    missing: str  # coupled callee Y that the peers call and `site` does not
    peer_count: int  # n: how many callers of X there are
    conform_count: int  # k: how many of them also call Y
    surprise: float  # S = -log10 binomial-tail; scale-free consensus strength
    peers_sample: list[str] = field(default_factory=list)  # a few conforming peers


@dataclass
class FileNode:
    """Node representing a file in the import graph."""

    path: str  # Relative file path
    imports: list[str] = field(default_factory=list)  # Files this imports
    imported_by: list[str] = field(default_factory=list)  # Files importing this
    centrality_score: float = 0.0  # Centrality metric
    cluster: str = "other"  # Architectural cluster

    # Temporal metadata (for relevance scoring)
    mtime: float = 0.0  # Modification timestamp
    size: int = 0  # File size in bytes
    age_days: float = 0.0  # Days since last modified


@dataclass
class CodeMapResult:
    """Aggregated result of code map analysis."""

    # Layer 1: File-level analysis
    files: list[FileNode] = field(default_factory=list)
    entry_points: list[EntryPointInfo] = field(default_factory=list)
    import_graph: dict[str, FileNode] = field(default_factory=dict)
    clusters: dict[str, list[str]] = field(default_factory=dict)

    # Layer 2: Structure-level analysis
    definitions: list[DefinitionInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    call_graph: dict[str, CallGraphNode] = field(default_factory=dict)
    hot_functions: list[CallGraphNode] = field(default_factory=list)

    # Metadata
    total_files: int = 0
    analysis_time: float = 0.0
    layers_analyzed: list[str] = field(default_factory=list)
