"""M2b-CLI for scantool-verktøyene. All output logges per episode.

Bruk:
  uv run python /tmp/m2b/scantool_cli.py LOGG preview DIR
  uv run python /tmp/m2b/scantool_cli.py LOGG scandir DIR [GLOB]
  uv run python /tmp/m2b/scantool_cli.py LOGG scanfile STI [BUDSJETT]
  uv run python /tmp/m2b/scantool_cli.py LOGG search DIR REGEX     (innholdssøk)
  uv run python /tmp/m2b/scantool_cli.py LOGG searchname DIR REGEX (navnesøk)
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
else:
    out = f"ukjent kommando: {command} — se docstring"
with open(log_path, "a") as f:
    f.write(f"=== CALL: scantool {command} {' '.join(args)} ===\n{out}\n")
print(out)
