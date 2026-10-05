"""Unit tests for src/analyzer/claude_client.py (no network: the API client is faked)."""
from types import SimpleNamespace

import pytest

from analyzer.claude_client import ClaudeAnalyzer, Verdict, build_prompt, code_context
from scanner.finding import load_rules
from scanner.python_scanner import scan_source

SOURCE = 'def report(avg):\n    return "Average: %d units" % avg\n'
FINDING = next(f for f in scan_source(SOURCE, "reports.py") if f.rule_id == "PY001")
RULE = load_rules("python")["PY001"]
DIFF = '-    return "Average: %d units" % avg\n+    return f"Average: {avg:d} units"\n'


class FakeMessages:
    def __init__(self, verdict=None, stop_reason="end_turn"):
        self.verdict, self.stop_reason, self.calls = verdict, stop_reason, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=self.verdict)


def online_analyzer(tmp_path, monkeypatch, fake):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    analyzer = ClaudeAnalyzer(mode="claude", cache_dir=tmp_path)
    analyzer.client = SimpleNamespace(messages=fake)
    return analyzer


def test_claude_verdict_is_returned_and_cached(tmp_path, monkeypatch):
    verdict = Verdict(safe_to_autofix=False, risk_level="medium",
                      explanation="avg is a float; {avg:d} raises.", suggested_fix='f"{int(avg)}"')
    fake = FakeMessages(verdict)
    analyzer = online_analyzer(tmp_path, monkeypatch, fake)

    result = analyzer.analyze(FINDING, RULE, code_context(SOURCE, FINDING), DIFF)
    assert result["source"] == "claude"
    assert result["safe_to_autofix"] is False and result["risk_level"] == "medium"
    assert fake.calls[0]["output_format"] is Verdict          # structured output requested
    assert "Average: %d units" in fake.calls[0]["messages"][0]["content"]

    # Same question again -> answered from the cache, no second API call.
    again = analyzer.analyze(FINDING, RULE, code_context(SOURCE, FINDING), DIFF)
    assert again["source"] == "cache" and len(fake.calls) == 1


def test_offline_mode_replays_cache_without_a_key(tmp_path, monkeypatch):
    verdict = Verdict(safe_to_autofix=True, risk_level="low", explanation="ok", suggested_fix="x")
    online_analyzer(tmp_path, monkeypatch, FakeMessages(verdict)).analyze(FINDING, RULE, "ctx", DIFF)

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    offline = ClaudeAnalyzer(mode="offline", cache_dir=tmp_path)
    assert offline.client is None
    assert offline.analyze(FINDING, RULE, "ctx", DIFF)["source"] == "cache"


def test_refusal_falls_back_to_rule_default(tmp_path, monkeypatch):
    analyzer = online_analyzer(tmp_path, monkeypatch, FakeMessages(None, stop_reason="refusal"))
    result = analyzer.analyze(FINDING, RULE, "ctx", DIFF)
    assert result["source"] == "fallback"
    assert result["risk_level"] == RULE["default_risk"]
    assert not list(tmp_path.iterdir())  # nothing cached


def test_fallback_never_approves_without_a_rewrite(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    analyzer = ClaudeAnalyzer(mode="auto", cache_dir=tmp_path)
    assert analyzer.analyze(FINDING, RULE, "ctx", None)["safe_to_autofix"] is False
    assert analyzer.analyze(FINDING, RULE, "ctx", DIFF)["safe_to_autofix"] is True  # PY001 default is low


def test_claude_mode_requires_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeAnalyzer(mode="claude")


def test_prompt_contains_rule_context_and_diff():
    prompt = build_prompt(FINDING, RULE, code_context(SOURCE, FINDING), DIFF, "")
    assert "Rule PY001" in prompt and "reports.py" in prompt
    assert ">>    2 |" in prompt                 # flagged line is marked
    assert "```diff" in prompt


def test_prompt_without_rewrite_explains_why():
    prompt = build_prompt(FINDING, RULE, "ctx", None, "Fixer declined: x")
    assert "No automated rewrite is available" in prompt and "Fixer declined: x" in prompt
