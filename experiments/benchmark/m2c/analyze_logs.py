"""M2c log analysis: call categories and tokens per episode.

MEASUREMENTS (actual data only, no interpretation). Categories:
  read  = cat/head/tail/sed via tool.sh + focusread (the read step, P2)
  nav   = preview/scandir/scanfile/search/searchname (navigation)
Outcome unknown — the script reports raw numbers identically for all arms.
"""
import re
from pathlib import Path

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")
LOGS = Path(__file__).parent / "logs"

READ_CMDS = {"cat", "head", "tail", "sed", "focusread"}


def segments(text: str):
    parts = re.split(r"^=== CALL: (.+?) ===$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        yield parts[i].strip(), parts[i + 1]


def classify(call: str) -> tuple[str, str]:
    words = call.split()
    cmd = words[1] if words and words[0] == "scantool" else words[0].split("/")[-1]
    return cmd, ("read" if cmd in READ_CMDS else "nav")


def main():
    rows = []
    for log in sorted(LOGS.glob("m2c-*.log")):
        calls, focusreads = 0, 0
        tokens = {"read": 0, "nav": 0}
        for call, output in segments(log.read_text(errors="replace")):
            cmd, cat = classify(call)
            calls += 1
            focusreads += cmd == "focusread"
            tokens[cat] += len(ENC.encode(output))
        rows.append((log.stem, calls, focusreads, tokens["read"], tokens["nav"]))

    print(f"{'episode':34s} {'calls':>5s} {'focusread':>9s} {'read-tok':>8s} {'nav-tok':>8s} {'sum':>8s}")
    for name, calls, fr, rt, nt in rows:
        print(f"{name:34s} {calls:5d} {fr:9d} {rt:8d} {nt:8d} {rt + nt:8d}")

    print()
    for arm in ("a", "b", "b2"):
        sub = [r for r in rows if f"-{arm}-" in r[0]]
        n = len(sub)
        print(f"ARM {arm.upper()}: episodes={n} calls={sum(r[1] for r in sub)} "
              f"focusread-calls={sum(r[2] for r in sub)} "
              f"episodes-with-focusread={sum(1 for r in sub if r[2])} "
              f"read-tok={sum(r[3] for r in sub)} nav-tok={sum(r[4] for r in sub)} "
              f"sum-tok={sum(r[3] + r[4] for r in sub)}")


if __name__ == "__main__":
    main()
