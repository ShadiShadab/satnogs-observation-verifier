from __future__ import annotations


def markdown(result: dict) -> str:
    rows = [f"## Observation {result['observation']} — verdict: **{result['verdict']}**", ""]
    if result.get("url"):
        rows += [result["url"], ""]
    from collections import Counter
    counts = Counter(c["status"] for c in result["checks"])
    rows += [" · ".join(f"{k}: {v}" for k, v in sorted(counts.items())), ""]
    if counts.get("NOT EVALUATED"):
        rows += ["Some checks were not evaluated; the verdict covers only the evaluated checks.", ""]
    rows += ["| Item | Check | Status | Detail | Evidence |", "|---|---|---|---|---|"]
    for c in result["checks"]:
        detail = c["detail"].replace("|", "\\|")
        rows.append(f"| {c['item']} | {c['name']} | {c['status']} | {detail} | {c['evidence']} |")
    return "\n".join(rows) + "\n"
