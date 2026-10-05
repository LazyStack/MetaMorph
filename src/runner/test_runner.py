"""Runs the target repo's own test suites (pytest / jest).

The tests are the safety net: a fix is kept only if the suite that was green
before the fix is still green after it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

TIMEOUT_SECONDS = 300


@dataclass
class TestResult:
    suite: str          # "pytest" or "jest"
    passed: bool
    summary: str        # e.g. "12 passed in 0.31s"
    duration: float
    output_tail: str    # last lines of output, for the report when something fails

    def to_dict(self) -> dict:
        return asdict(self)


def detect_suites(repo: Path) -> dict[str, list[str]]:
    """Work out which test commands apply to this repo."""
    suites: dict[str, list[str]] = {}
    has_pytests = any(
        p.name.startswith("test_") or p.name.endswith("_test.py")
        for p in repo.rglob("*.py")
        if "node_modules" not in p.parts
    )
    if has_pytests:
        suites["pytest"] = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(repo)]

    jest_config = repo / "jest.config.js"
    npx = shutil.which("npx")
    if jest_config.exists() and npx:
        suites["jest"] = [npx, "jest", "--config", str(jest_config), "--silent"]
    return suites


def run_suite(name: str, command: list[str], cwd: Path) -> TestResult:
    # Python reuses a cached .pyc when a source file's size and mtime (in whole
    # seconds) are unchanged. A fix + rollback + another same-length fix within
    # one second would then run STALE bytecode. So: never write bytecode.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT_SECONDS,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, passed = f"Timed out after {TIMEOUT_SECONDS}s", False
    duration = time.perf_counter() - start
    return TestResult(
        suite=name,
        passed=passed,
        summary=_summarize(name, output, passed),
        duration=round(duration, 2),
        output_tail="\n".join(output.strip().splitlines()[-25:]),
    )


def _summarize(name: str, output: str, passed: bool) -> str:
    if name == "pytest":
        # last line looks like "3 failed, 9 passed in 0.42s"
        m = re.search(r"(\d+ (?:passed|failed|error)[^\n]*?in [\d.]+s)", output)
    else:
        m = re.search(r"Tests:\s+([^\n]+)", output)
    if m:
        return m.group(1).strip()
    return "passed" if passed else "failed (see output)"
