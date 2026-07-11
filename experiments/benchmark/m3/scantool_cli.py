"""M3 CLI for the scantool tools. All output is logged per episode.

Arms (M3_ARM env var, required):
  A — baseline: the connectivity tail is suppressed (one-line difference)
  B — connectivity: production behaviour. The corpus is warmed SYNCHRONOUSLY
      before scanfile: connectivity_tail serves the last computed state and a
      fresh CLI process has none, while the long-lived MCP server is already
      warm — synchronous warm mirrors the server's steady state, not an
      artificial advantage. Protocol note: the tail rides only the plain
      scanfile path; focusread (focus=) never carries it (server.py:597-600).

Usage:
  M3_ARM=A|B uv run python .../m3/scantool_cli.py LOG preview DIR
  ... scandir DIR [GLOB] / scanfile PATH [BUDGET] / search DIR REGEX /
      searchname DIR REGEX / focusread PATH NODE
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from scantool import connectivity, server
from scantool.git_signals import repo_root

ARM = os.environ["M3_ARM"].upper()
if ARM == "A":
    server._connectivity_note = lambda file_path: ""

log_path, command, *args = sys.argv[1:]
if ARM == "B" and command == "scanfile":
    root = repo_root(args[0])
    if root:
        connectivity.warm(root)

if command == "preview":
    out = server.preview_directory.fn(args[0], depth="deep")[0].text
elif command == "scandir":
    out = server.scan_directory.fn(args[0], pattern=args[1] if len(args) > 1 else "**/*",
                                   delta=False)[0].text
elif command == "scanfile":
    budget = int(args[1]) if len(args) > 1 else None
    out = server.scan_file.fn(args[0], budget=budget, delta=False)[0].text
elif command == "search":
    out = server.search_structures.fn(args[0], content_pattern=args[1])[0].text
elif command == "searchname":
    out = server.search_structures.fn(args[0], name_pattern=args[1])[0].text
elif command == "focusread":
    out = server.scan_file.fn(args[0], focus=" ".join(args[1:]))[0].text
else:
    out = f"unknown command: {command} — see docstring"
with open(log_path, "a") as f:
    f.write(f"=== CALL: scantool[{ARM}] {command} {' '.join(args)} ===\n{out}\n")
print(out)
