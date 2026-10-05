"""Metamorph - legacy code migration agent.

    Scan -> Analyze (Claude) -> Migrate -> Validate (tests) -> Report

Usage:
    python src/metamorph.py src/demo_repo --out build/migrated
    python src/metamorph.py src/demo_repo --scan-only
    python src/metamorph.py --help
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Make `scanner`, `fixer`, ... importable however this script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import react_bridge  # noqa: E402
from analyzer.claude_client import DEFAULT_MODEL, ClaudeAnalyzer, code_context  # noqa: E402
from fixer import python_fixer  # noqa: E402
from fixer.python_fixer import FixNotSupported  # noqa: E402
from report.report_generator import write_report  # noqa: E402
from runner.test_runner import detect_suites, run_suite  # noqa: E402
from scanner import python_scanner  # noqa: E402
from scanner.finding import Finding, load_rules  # noqa: E402

RISK_RANK = {"low": 0, "medium": 1, "high": 2}
SUITE_FOR = {"python": "pytest", "react": "jest"}
FIXERS = {"python": python_fixer.apply_fix, "react": react_bridge.apply_fix}
COPY_IGNORE = shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache", ".git")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="metamorph", description="Scan, judge, fix and validate legacy Python/React code.")
    p.add_argument("repo", help="path of the codebase to migrate")
    p.add_argument("--out", help="copy the repo here and migrate the copy (recommended); without it the repo is changed in place")
    p.add_argument("--mode", choices=["auto", "claude", "offline"], default="auto",
                   help="auto: Claude if ANTHROPIC_API_KEY is set; offline: cached verdicts / rule defaults only")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model id (default: {DEFAULT_MODEL})")
    p.add_argument("--max-risk", choices=["low", "medium"], default="low",
                   help="highest risk level that may be auto-applied (default: low)")
    p.add_argument("--report", default="metamorph_report.md", help="where to write the Markdown report")
    p.add_argument("--no-tests", action="store_true", help="skip test validation (not recommended)")
    p.add_argument("--scan-only", action="store_true", help="only list findings; change nothing")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 2

    workdir = prepare_workdir(repo, args.out) if not args.scan_only else repo
    rules = {"python": load_rules("python"), "react": load_rules("react")}

    # 1. SCAN -------------------------------------------------------------
    print(f"[1/5] Scanning {workdir}")
    py_files, findings = python_scanner.scan_path(workdir)
    react_files: list[str] = []
    if react_bridge.node_available():
        react_files, rx_findings = react_bridge.scan_path(workdir)
        findings += rx_findings
    else:
        print("      (node / jscodeshift not installed - React scan skipped; run `npm install`)")
    print(f"      {len(py_files)} Python + {len(react_files)} React files, {len(findings)} findings")

    if args.scan_only:
        for f in findings:
            print(f"      {f.id:55} {f.message}")
        return 0

    originals = {f.file: read_file(workdir / f.file) for f in findings}

    # 2. BASELINE TESTS ---------------------------------------------------
    suites = {} if args.no_tests else detect_suites(workdir)
    print(f"[2/5] Baseline tests: {', '.join(suites) or 'none'}")
    baseline = {name: run_suite(name, cmd, workdir) for name, cmd in suites.items()}
    for r in baseline.values():
        print(f"      {r.suite}: {'PASS' if r.passed else 'FAIL'} - {r.summary}")

    # 3. ANALYZE ----------------------------------------------------------
    analyzer = ClaudeAnalyzer(mode=args.mode, model=args.model)
    print(f"[3/5] Judging {len(findings)} findings with {analyzer.describe()}")
    approved = []
    for f in findings:
        rule = rules[f.language][f.rule_id]
        if judge(f, rule, originals[f.file], analyzer, args.max_risk, baseline):
            approved.append(f)
    print(f"      {len(approved)} approved for auto-fix, {len(findings) - len(approved)} need review")

    # 4. MIGRATE + VALIDATE -----------------------------------------------
    print("[4/5] Applying approved fixes one at a time (bottom-up per file), testing after each")
    test_runs = 0
    for f in sorted(approved, key=lambda f: (f.file, -f.line, -f.column)):
        test_runs += apply_and_validate(f, workdir, suites)

    # 5. FINAL TESTS + REPORT --------------------------------------------
    final = {name: run_suite(name, cmd, workdir) for name, cmd in suites.items()}
    diffs = {}
    for file, before in originals.items():
        after = read_file(workdir / file)
        if after != before:
            diffs[file] = unified_diff(before, after, file)

    run = {
        "repo": display_path(repo),
        "workdir": display_path(workdir),
        "started": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files_scanned": {"python": len(py_files), "react": len(react_files)},
        "analyzer": analyzer.describe(),
        "verdict_sources": analyzer.stats,
        "max_risk": args.max_risk,
        "duration": time.perf_counter() - started,
        "tests": {
            "baseline": {k: v.to_dict() for k, v in baseline.items()},
            "final": {k: v.to_dict() for k, v in final.items()},
            "runs_during_fixing": test_runs,
        },
        "diffs": diffs,
    }
    report_path = Path(args.report).resolve()
    write_report(run, findings, rules, report_path)

    counts = {s: sum(f.status == s for f in findings) for s in ("auto_fixed", "rolled_back", "needs_review")}
    print(f"[5/5] Report: {report_path}")
    print(f"      auto-fixed {counts['auto_fixed']}, rolled back {counts['rolled_back']}, "
          f"needs review {counts['needs_review']}")
    for r in final.values():
        print(f"      final {r.suite}: {'PASS' if r.passed else 'FAIL'} - {r.summary}")
    return 0 if all(r.passed for r in final.values()) else 1


def judge(f: Finding, rule: dict, source: str, analyzer: ClaudeAnalyzer, max_risk: str, baseline: dict) -> bool:
    """Decide one finding. Returns True if it is approved for auto-fixing."""
    proposed, reason = None, "Rule is review-only (no safe mechanical rewrite exists)."
    if rule["autofix_supported"]:
        try:
            proposed = unified_diff(source, FIXERS[f.language](source, f), f.file)
            f.extra["proposed_diff"] = proposed
        except FixNotSupported as err:
            reason = f"Fixer declined: {err}"

    f.verdict = analyzer.analyze(f, rule, code_context(source, f), proposed, reason)
    risk = f.verdict["risk_level"]
    suite = SUITE_FOR[f.language]

    f.status = "needs_review"
    if proposed is None:
        f.status_detail = reason
    elif not f.verdict["safe_to_autofix"]:
        f.status_detail = f"Judged unsafe to auto-apply (risk: {risk})."
    elif RISK_RANK[risk] > RISK_RANK[max_risk]:
        f.status_detail = f"Risk `{risk}` is above the auto-fix threshold `{max_risk}`."
    elif suite in baseline and not baseline[suite].passed:
        f.status_detail = f"The {suite} suite already fails before migration, so the fix can't be validated."
    else:
        f.status = "approved"
        return True
    return False


def apply_and_validate(f: Finding, workdir: Path, suites: dict) -> int:
    """Apply one approved fix, run its test suite, revert on failure. Returns test runs used."""
    path = workdir / f.file
    before = read_file(path)
    try:
        after = FIXERS[f.language](before, f)
    except FixNotSupported as err:
        f.status, f.status_detail = "needs_review", f"Fixer declined at apply time: {err}"
        return 0
    write_file(path, after)

    suite = SUITE_FOR[f.language]
    if suite not in suites:
        f.status, f.status_detail = "auto_fixed", "No test suite for this language; syntax-checked only."
        print(f"      {f.id}: applied (no tests)")
        return 0

    result = run_suite(suite, suites[suite], workdir)
    if result.passed:
        f.status, f.status_detail = "auto_fixed", result.summary
        print(f"      {f.id}: applied, {suite} PASS")
    else:
        write_file(path, before)  # rollback
        f.status, f.status_detail = "rolled_back", result.summary
        f.extra["test_output"] = result.output_tail
        print(f"      {f.id}: {suite} FAIL -> rolled back")
    return 1


def prepare_workdir(repo: Path, out: str | None) -> Path:
    if not out:
        return repo
    workdir = Path(out).resolve()
    if workdir == repo or repo in workdir.parents:
        raise SystemExit("error: --out must not be the repo itself or inside it")
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(repo, workdir, ignore=COPY_IGNORE)
    return workdir


def read_file(path: Path) -> str:
    # newline="" keeps the file's own line endings (no silent LF <-> CRLF changes)
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_file(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def unified_diff(before: str, after: str, name: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True), f"a/{name}", f"b/{name}",
    ))


def display_path(p: Path) -> str:
    try:
        return p.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return p.as_posix()


if __name__ == "__main__":
    sys.exit(main())
