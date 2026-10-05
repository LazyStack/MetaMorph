"""The Finding record shared by every stage of the pipeline.

A Finding is one occurrence of one legacy pattern in one file. Scanners create
them; the analyzer (Claude) attaches a verdict; the fixer and the report read them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


@dataclass
class Finding:
    rule_id: str          # e.g. "PY001"
    language: str         # "python" or "react"
    file: str             # path relative to the scanned repo root, with forward slashes
    line: int             # 1-based start line of the offending code
    column: int           # 0-based start column
    end_line: int
    snippet: str          # the offending source code (trimmed to a few lines)
    message: str          # human-readable description of what was found
    # Filled in by later stages:
    verdict: dict | None = None   # Claude's judgment (see analyzer/claude_client.py)
    status: str = "found"         # found -> auto_fixed | needs_review | rolled_back | ...
    status_detail: str = ""       # one-line reason for the status
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Stable identifier, e.g. 'app/utils.py:12:4:PY001'."""
        return f"{self.file}:{self.line}:{self.column}:{self.rule_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(**data)


def load_rules(language: str) -> dict[str, dict]:
    """Return the rule catalogue for a language, keyed by rule id."""
    name = "python_rules.json" if language == "python" else "react_rules.json"
    data = json.loads((RULES_DIR / name).read_text(encoding="utf-8"))
    return {rule["id"]: rule for rule in data["rules"]}
