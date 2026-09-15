"""
FILE: ref_diff.py

PROBLEM:
  The structural table (structural_diff.diff_refs) says WHAT changed. A
  reviewer also needs the loose ends a change introduced: a definition
  touched here that now has no caller, a route referenced nowhere, a
  touched function that breaks a call pattern its siblings follow.

SOLUTION:
  A review tail, scoped to the files a diff touched, built once from the
  repository's own call graph (code_map.CodeMap) and shared by both `sct
  diff --review` and the MCP scan_diff tool — the same finding, regardless
  of which one asked. Previously this lived only in the MCP path
  (diff_against_ref); the CLI had no equivalent. Unifying it here is the
  fix for that gap, not a new feature invented for this file.

SCOPE:
  ✓ dead/orphan/divergence candidates restricted to files that changed
  ✗ not a corpus-wide audit (that is find_divergence / preview_directory)
"""


def changed_files_review(top: str, changed_files: set[str]) -> str:
    """Review-mode connectivity on the changed code: the loose ends a
    change introduced. Three subsections, scoped to the changed files:
      - orphan : a route/template you touched that is referenced nowhere
      - dead   : a definition you touched that now has no inbound caller
      - drift  : a touched function that breaks a sibling call-pattern
    The repo is the corpus, the diff is the scope. "Candidates, not
    verdicts." Never raises into the diff — a corpus build failure just
    means no section."""
    if not changed_files:
        return ""
    try:
        from .code_map import CodeMap
        from .connectivity import corpus_dead_orphans
        from .consensus import find_divergences, format_divergences

        result = CodeMap(top).analyze()
        blocks: list[str] = []

        # dead + orphan introduced in the changed files
        dead_all, orphans_all, dyn = corpus_dead_orphans(top, result)
        orphan = [(t, k, p) for loc, t, k, p in orphans_all if loc in changed_files]
        dead = sorted((f, qual) for f, qual in dead_all if f in changed_files)
        if orphan or dead:
            lines = ["── REVIEW: connectivity in changed files (candidates, not verdicts) ──"]
            if orphan:
                lines.append("  orphan (referenced nowhere — candidate dead):")
                for tag, key, pid in orphan[:20]:
                    lines.append(f"    {tag} {key}  ({pid})")
            if dead:
                note = " [dynamic dispatch — down-weighted]" if dyn else ""
                lines.append(f"  candidate-dead (no inbound caller){note}:")
                for f, qual in dead[:20]:
                    lines.append(f"    {qual}  ({f})")
            blocks.append("\n".join(lines))

        # peer divergence on the changed functions (the repo is the peer corpus,
        # the diff is the suspect set — review-mode precision)
        suspects = {(d.file, d.name) for d in result.definitions if d.file in changed_files}
        if suspects:
            file_clusters = {
                f: cluster for cluster, files in result.clusters.items() for f in files
            }
            findings = find_divergences(
                result.definitions,
                result.calls,
                suspects=suspects,
                file_clusters=file_clusters,
            )
            if findings:
                blocks.append(format_divergences(findings))

        return "\n\n".join(blocks)
    except Exception:
        return ""
