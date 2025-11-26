"""Data models for code map analysis."""

from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class CallInfo:
    """Information about a function call."""

    caller_file: str  # File where call is made
    caller_name: Optional[str]  # Function/method making the call
    callee_name: str  # Function/method being called
    line: int  # Line number of call
    is_cross_file: bool = False  # True if calling function in another file


@dataclass
class CallGraphNode:
    """Node in the call graph."""

    name: str  # Fully qualified name
    file: str  # File containing this definition
    type: str  # "function", "class", "method"
    callers: list[str] = field(default_factory=list)  # Who calls this
    callees: list[str] = field(default_factory=list)  # Who this calls
    centrality_score: float = 0.0  # Centrality metric


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
