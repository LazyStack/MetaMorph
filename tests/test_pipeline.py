"""End-to-end test: run the whole pipeline (offline) on the Python half of the demo repo."""
import json
import shutil
from pathlib import Path

import metamorph

DEMO = Path(__file__).resolve().parents[1] / "src" / "demo_repo" / "python"


def test_pipeline_fixes_safe_findings_and_rolls_back_breaking_one(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(metamorph.react_bridge, "node_available", lambda: False)  # Python-only run
    repo = tmp_path / "repo"
    shutil.copytree(DEMO, repo, ignore=shutil.ignore_patterns("__pycache__"))
    report = tmp_path / "report.md"

    exit_code = metamorph.main(
        [str(repo), "--out", str(tmp_path / "out"), "--mode", "offline", "--report", str(report)]
    )

    assert exit_code == 0  # final test run is green
    data = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    status = {(f["file"], f["line"], f["rule_id"]): f["status"] for f in data["findings"]}

    # %d applied to a float breaks a test -> reverted
    assert status[("shop/reports.py", 11, "PY001")] == "rolled_back"
    # safe, low-risk rewrites are applied
    assert status[("shop/inventory.py", 5, "PY004")] == "auto_fixed"
    assert status[("shop/inventory.py", 2, "PY006")] == "auto_fixed"
    # medium-risk and review-only patterns are left for a human
    assert status[("shop/legacy_config.py", 25, "PY002")] == "needs_review"
    assert status[("scripts/old_report.py", 4, "PY000")] == "needs_review"

    migrated = (tmp_path / "out" / "shop" / "reports.py").read_text()
    assert '"Average stock: %d units" % avg' in migrated  # rollback restored the original
    assert 'f"{name!s:<10}|{qty:5d}"' in migrated  # neighbouring fix kept
    # the source repo itself is never modified
    assert (repo / "shop" / "inventory.py").read_text() == (DEMO / "shop" / "inventory.py").read_text()
    assert "Rolled back (1)" in report.read_text(encoding="utf-8")
