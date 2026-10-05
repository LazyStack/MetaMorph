"""Python wrapper around the Node.js React scanner and fixer.

The React tooling (jscodeshift) lives in JavaScript; the pipeline is Python.
This module runs the JS scripts as subprocesses and exchanges JSON with them,
so the pipeline can treat both languages through the same two functions:

    scan_path(root)            -> (files, findings)
    apply_fix(source, finding) -> new source  (raises FixNotSupported)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from fixer.python_fixer import FixNotSupported
from scanner.finding import Finding

SRC = Path(__file__).resolve().parent
SCANNER_JS = SRC / "scanner" / "react_scanner.js"
FIXER_JS = SRC / "fixer" / "react_fixer.js"


def node_available() -> bool:
    return shutil.which("node") is not None and (SRC.parent / "node_modules" / "jscodeshift").exists()


def _run_node(script: Path, args: list[str], stdin: str | None = None) -> dict:
    proc = subprocess.run(
        ["node", str(script), *args], input=stdin, capture_output=True,
        text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{script.name} failed: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


def scan_path(root: Path) -> tuple[list[str], list[Finding]]:
    data = _run_node(SCANNER_JS, [str(root)])
    return data["files"], [Finding(**f) for f in data["findings"]]


def apply_fix(source: str, finding: Finding) -> str:
    request = {"source": source, "finding": {k: v for k, v in finding.to_dict().items() if k != "verdict"}}
    result = _run_node(FIXER_JS, [], stdin=json.dumps(request))
    if not result["ok"]:
        raise FixNotSupported(result["reason"])
    return result["source"]
