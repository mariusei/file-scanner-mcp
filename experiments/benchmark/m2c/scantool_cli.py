"""M2c CLI for the scantool tools. All output is logged per episode.

Usage:
  uv run python .../m2c/scantool_cli.py LOG preview DIR
  uv run python .../m2c/scantool_cli.py LOG scandir DIR [GLOB]
  uv run python .../m2c/scantool_cli.py LOG scanfile PATH [BUDGET]
  uv run python .../m2c/scantool_cli.py LOG search DIR REGEX     (content search)
  uv run python .../m2c/scantool_cli.py LOG searchname DIR REGEX (name search)
  uv run python .../m2c/scantool_cli.py LOG focusread PATH NODE  (one node verbatim)
"""
import sys
sys.path.insert(0, "/Users/dev/Projects/scantool/src")
from scantool import server

log_path, command, *args = sys.argv[1:]
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
    f.write(f"=== CALL: scantool {command} {' '.join(args)} ===\n{out}\n")
print(out)
