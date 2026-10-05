"""Builds the human-readable migration report (Markdown) and a JSON twin."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scanner.finding import Finding

STATUS_LABELS = {
    "auto_fixed": "Auto-fixed (tests still pass)",
    "rolled_back": "Rolled back (tests failed)",
    "needs_review": "Needs human review",
}
SOURCE_LABELS = {"claude": "Claude", "cache": "Claude (cached)", "fallback": "rule-based fallback"}


def write_report(run: dict, findings: list[Finding], rules: dict, md_path: Path) -> None:
    md_path = Path(md_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(run, findings, rules), encoding="utf-8")
    json_path = md_path.with_suffix(".json")
    json_path.write_text(
        json.dumps({"run": run, "findings": [f.to_dict() for f in findings]}, indent=2, default=str),
        encoding="utf-8",
    )


def render_markdown(run: dict, findings: list[Finding], rules: dict) -> str:
    out: list[str] = []
    w = out.append
    counts = Counter(f.status for f in findings)

    w("# Metamorph migration report\n")
    w("| | |\n|---|---|")
    w(f"| Repository | `{run['repo']}` |")
    if run.get("workdir") != run["repo"]:
        w(f"| Migrated copy | `{run['workdir']}` |")
    w(f"| Run at | {run['started']} |")
    w(f"| Files scanned | {run['files_scanned']['python']} Python, {run['files_scanned']['react']} React/JS |")
    w(f"| Judgment layer | {run['analyzer']} |")
    w(f"| Verdict sources | {', '.join(f'{SOURCE_LABELS[k]}: {v}' for k, v in run['verdict_sources'].items() if v) or 'n/a'} |")
    w(f"| Auto-fix policy | automated rewrite exists AND judged safe AND risk <= `{run['max_risk']}` AND tests stay green |")
    w(f"| Duration | {run['duration']:.1f} s |")
    w("")

    # ---- summary ----------------------------------------------------------
    w("## Summary\n")
    w("| Outcome | Findings |\n|---|---:|")
    for status, label in STATUS_LABELS.items():
        w(f"| {label} | {counts.get(status, 0)} |")
    w(f"| **Total** | **{len(findings)}** |")
    w("")
    w("### By rule\n")
    w("| Rule | Pattern | Found | Auto-fixed | Rolled back | Review |\n|---|---|---:|---:|---:|---:|")
    by_rule: dict[str, Counter] = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, Counter())[f.status] += 1
    for rule_id in sorted(by_rule):
        c = by_rule[rule_id]
        title = _rule(rules, rule_id)["title"]
        w(f"| {rule_id} | {title} | {sum(c.values())} | {c['auto_fixed']} | {c['rolled_back']} | {c['needs_review']} |")
    w("")

    # ---- tests ------------------------------------------------------------
    w("## Test validation\n")
    if not run["tests"]["baseline"]:
        w("_No test suites were run._\n")
    else:
        w("Each automated fix was applied on its own and the language's test suite was re-run; "
          "a fix that turned the suite red was reverted immediately.\n")
        w(f"Test runs during migration: {run['tests']['runs_during_fixing']}\n")
        w("| Suite | Before migration | After migration |\n|---|---|---|")
        for name, before in run["tests"]["baseline"].items():
            after = run["tests"]["final"].get(name)
            w(f"| {name} | {_result(before)} | {_result(after) if after else 'not run'} |")
        w("")

    # ---- auto-fixed -------------------------------------------------------
    fixed = [f for f in findings if f.status == "auto_fixed"]
    w(f"## Auto-fixed ({len(fixed)})\n")
    if fixed:
        w("| Location | Rule | Risk | Why it was considered safe |\n|---|---|---|---|")
        for f in fixed:
            v = f.verdict or {}
            w(f"| `{f.file}:{f.line}` | {f.rule_id} | {v.get('risk_level', '')} | {_cell(v.get('explanation', ''))} |")
        w("")
    else:
        w("_None._\n")

    # ---- rolled back ------------------------------------------------------
    rolled = [f for f in findings if f.status == "rolled_back"]
    w(f"## Rolled back ({len(rolled)})\n")
    if rolled:
        w("These fixes were judged safe but broke the test suite, so they were reverted. "
          "This is the safety net working - each needs a human look.\n")
        for f in rolled:
            w(f"### `{f.file}:{f.line}` - {f.rule_id} {_rule(rules, f.rule_id)['title']}\n")
            w(f"**Tests after fix:** {f.status_detail}\n")
            w("Attempted change:\n")
            w(f"```diff\n{f.extra.get('proposed_diff', '').rstrip()}\n```\n")
            if f.extra.get("test_output"):
                w("<details><summary>Test output</summary>\n")
                w(f"```\n{f.extra['test_output']}\n```\n")
                w("</details>\n")
    else:
        w("_None._\n")

    # ---- needs review -----------------------------------------------------
    review = [f for f in findings if f.status == "needs_review"]
    w(f"## Needs human review ({len(review)})\n")
    for f in review:
        v = f.verdict or {}
        lang = "python" if f.language == "python" else "jsx"
        w(f"### `{f.file}:{f.line}` - {f.rule_id} {_rule(rules, f.rule_id)['title']}\n")
        w(f"**Risk:** {v.get('risk_level', '?')} &nbsp;|&nbsp; **Verdict from:** "
          f"{SOURCE_LABELS.get(v.get('source'), '?')} &nbsp;|&nbsp; **Why not auto-fixed:** {f.status_detail}\n")
        w(f"```{lang}\n{f.snippet}\n```\n")
        if v.get("explanation"):
            w(f"{v['explanation']}\n")
        if v.get("suggested_fix") and v.get("source") != "fallback":
            w("Suggested change:\n")
            w(f"```{lang}\n{v['suggested_fix'].rstrip()}\n```\n")
        elif f.extra.get("proposed_diff"):
            w("Available automated rewrite (not applied):\n")
            w(f"```diff\n{f.extra['proposed_diff'].rstrip()}\n```\n")

    # ---- full diff --------------------------------------------------------
    w("## Applied changes\n")
    if run["diffs"]:
        for file, diff in run["diffs"].items():
            w(f"<details><summary><code>{file}</code></summary>\n")
            w(f"```diff\n{diff.rstrip()}\n```\n")
            w("</details>\n")
    else:
        w("_No files were changed._\n")

    return "\n".join(out)


def _rule(rules: dict, rule_id: str) -> dict:
    lang = "python" if rule_id.startswith("PY") else "react"
    return rules[lang][rule_id]


def _result(r: dict) -> str:
    return f"{'PASS' if r['passed'] else 'FAIL'} - {r['summary']}"


def _cell(text: str) -> str:
    """Make free text safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")
