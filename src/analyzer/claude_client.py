"""The judgment layer: asks Claude whether one finding is safe to auto-fix.

The scanner has already decided WHAT is legacy. Claude only decides what to DO
about one finding, given the surrounding code and the exact rewrite our
deterministic fixer would apply. Its answer is forced into a fixed JSON shape
(the Verdict model below) using the API's structured-output feature.

Modes
  auto     use Claude if ANTHROPIC_API_KEY is set, otherwise the rule-based fallback
  claude   always call Claude (fails fast if no key)
  offline  never call the network: replay cached Claude answers, else fall back

Every live answer is cached on disk (keyed by a hash of the model + prompt), so a
later --offline run reproduces the exact same verdicts without an API key.

Security: the API key is read by the SDK from the ANTHROPIC_API_KEY environment
variable. It is never hard-coded, logged, or written to the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from scanner.finding import Finding

DEFAULT_MODEL = os.environ.get("METAMORPH_MODEL", "claude-opus-5")
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".metamorph_cache"

SYSTEM_PROMPT = """\
You are a senior engineer reviewing an automated legacy-code migration.

A deterministic scanner has flagged one legacy pattern. You will see the rule, the \
flagged code with surrounding context, and - if one exists - the exact rewrite the \
automated fixer would apply. Decide whether applying that rewrite automatically is \
safe, i.e. it cannot change the program's observable behaviour in this context.

Guidelines:
- Judge the specific rewrite shown, in this specific context - not the rule in general.
- Look for context that breaks the usual assumption: a custom class instead of a \
builtin dict, a float reaching an integer format, exceptions that callers rely on, \
values used at runtime rather than only as type hints, object identity changes, etc.
- If no automated rewrite is offered, set safe_to_autofix to false and put a concrete \
recommended change in suggested_fix for a human to apply.
- risk_level: "low" = behaviour-preserving; "medium" = probably fine but depends on \
things not visible here; "high" = likely to change behaviour or needs real redesign.
- explanation: 1-3 sentences a reviewer can act on. Mention the specific reason.
- suggested_fix: the code you recommend (may equal the automated rewrite). Code only."""


class Verdict(BaseModel):
    """The structured answer Claude must return for each finding."""

    safe_to_autofix: bool = Field(description="True only if the shown automated rewrite is behaviour-preserving here.")
    risk_level: Literal["low", "medium", "high"]
    explanation: str = Field(description="1-3 sentences explaining the judgment.")
    suggested_fix: str = Field(description="Recommended replacement code.")


class ClaudeAnalyzer:
    def __init__(self, mode: str = "auto", model: str = DEFAULT_MODEL, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        if mode not in ("auto", "claude", "offline"):
            raise ValueError(f"unknown analyzer mode: {mode}")
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if mode == "claude" and not has_key:
            raise RuntimeError("--mode claude needs the ANTHROPIC_API_KEY environment variable.")
        self.online = mode == "claude" or (mode == "auto" and has_key)
        self.mode = mode
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.client = anthropic.Anthropic() if self.online else None
        self.stats = {"claude": 0, "cache": 0, "fallback": 0}

    def describe(self) -> str:
        if self.online:
            return f"Claude API ({self.model})"
        return "offline (cached Claude verdicts, rule-based fallback when no cache entry)"

    def analyze(self, finding: Finding, rule: dict, context: str, proposed_fix: str | None, fix_unavailable_reason: str = "") -> dict:
        """Return a verdict dict: the Verdict fields plus `source` = claude | cache | fallback."""
        prompt = build_prompt(finding, rule, context, proposed_fix, fix_unavailable_reason)
        cache_file = self.cache_dir / f"{hashlib.sha256((self.model + prompt).encode()).hexdigest()[:24]}.json"

        if cache_file.exists():
            self.stats["cache"] += 1
            return {**json.loads(cache_file.read_text(encoding="utf-8")), "source": "cache"}

        if self.online:
            try:
                verdict = self._ask_claude(prompt)
            except anthropic.APIError as err:  # network/API trouble: degrade, don't crash
                return self._fallback(rule, proposed_fix, f"Claude call failed ({type(err).__name__}); used rule default.")
            if verdict is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
                self.stats["claude"] += 1
                return {**verdict, "source": "claude"}
            return self._fallback(rule, proposed_fix, "Claude declined to answer; used rule default.")

        return self._fallback(rule, proposed_fix, "No API key; used the rule's default risk.")

    def _ask_claude(self, prompt: str) -> dict | None:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format=Verdict,
        )
        # A refusal or truncated answer has no valid parsed output - treat as "no verdict".
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            return None
        return response.parsed_output.model_dump()

    def _fallback(self, rule: dict, proposed_fix: str | None, note: str) -> dict:
        """Conservative rule-based verdict used when Claude isn't available."""
        self.stats["fallback"] += 1
        safe = proposed_fix is not None and rule["default_risk"] == "low"
        return {
            "safe_to_autofix": safe,
            "risk_level": rule["default_risk"],
            "explanation": f"{rule['description']} ({note})",
            "suggested_fix": proposed_fix or "",
            "source": "fallback",
        }


def build_prompt(finding: Finding, rule: dict, context: str, proposed_fix: str | None, fix_unavailable_reason: str) -> str:
    lang = "python" if finding.language == "python" else "jsx"
    parts = [
        f"Rule {rule['id']}: {rule['title']}",
        f"Rule description: {rule['description']}",
        f"Finding: {finding.message}",
        f"File: {finding.file} (line {finding.line})",
        "",
        "Code context (line numbers on the left, flagged lines marked with >>):",
        f"```{lang}\n{context}\n```",
        "",
    ]
    if proposed_fix is not None:
        parts += ["The automated fixer would apply this change (unified diff):", f"```diff\n{proposed_fix}\n```"]
    else:
        reason = f" Reason: {fix_unavailable_reason}" if fix_unavailable_reason else ""
        parts += [f"No automated rewrite is available for this finding.{reason}"]
    return "\n".join(parts)


def code_context(source: str, finding: Finding, radius: int = 12) -> str:
    """Numbered source lines around the finding, flagged lines marked with >>."""
    lines = source.splitlines()
    start = max(1, finding.line - radius)
    end = min(len(lines), finding.end_line + radius)
    out = []
    for n in range(start, end + 1):
        marker = ">>" if finding.line <= n <= finding.end_line else "  "
        out.append(f"{marker}{n:5} | {lines[n - 1]}")
    return "\n".join(out)
