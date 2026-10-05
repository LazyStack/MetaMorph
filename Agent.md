# Agent Name: Metamorph

## 1. Problem Statement

Enterprise codebases accumulate legacy patterns – old React class components and lifecycle
methods, outdated Python syntax such as `%`-formatting, `has_key()`, Python 2 exception syntax and
pre-3.9 typing aliases. Migrating them by hand is slow, repetitive and risky: each change looks
trivial, but some silently change behaviour (a `%d` that truncated a float, a `has_key()` on a
custom class that isn't a dict). Linters can find these patterns but can't tell which fixes are
safe in context; letting an AI rewrite whole files is fast but not reproducible or auditable.

## 2. Proposed Agent

Metamorph scans a codebase for a curated set of known legacy patterns, uses Claude to judge –
per finding, in context – whether the exact automated fix is safe to apply or needs a human,
applies the safe fixes one at a time, validates each one against the project's existing test
suite (rolling back any fix that breaks a test), and produces a migration report.

## 3. Key Capabilities

- **Rule-based detection** for Python (9 rules, `libcst`) and React/JS (6 rules, `jscodeshift`) –
  deterministic and reproducible.
- **AI-assisted risk judgment per finding:** Claude sees the code context and the exact diff the
  fixer would apply, and returns structured JSON (`safe_to_autofix`, `risk_level`, `explanation`,
  `suggested_fix`).
- **Automated safe-fix application** via syntax-tree rewriting that preserves comments and
  formatting, with explicit preconditions – the fixer refuses rather than guesses.
- **Test-validated migration:** baseline tests, one fix at a time, re-test after each, automatic
  rollback on failure.
- **Human-readable report:** auto-fixed vs. rolled back vs. needs review, Claude's reasoning,
  suggested changes for reviewers, test results before/after and full diffs.
- **Runs without an API key** (conservative rule defaults) and **offline replay** of cached
  Claude verdicts.

## 4. Target Users

Development teams maintaining legacy Python and React codebases who want to modernize
incrementally – without a manual audit of every occurrence and without trusting an unreviewed
bulk rewrite. Also useful for tech leads planning migrations: `--scan-only` sizes the work.

## 5. How It Works

1. **Scan** – Python and React scanners walk each file's syntax tree and match a fixed rule
   catalogue (`src/rules/*.json`), producing findings (rule, file, line, snippet).
2. **Analyze** – for each finding the fixer computes the exact rewrite (as a diff, without writing
   it); Claude judges safety and risk in context and explains why.
3. **Migrate** – approved fixes (rewrite exists + judged safe + risk ≤ threshold) are applied one
   at a time, bottom-up within each file.
4. **Validate** – after each fix the language's test suite (pytest / jest) runs; a red suite
   reverts that fix immediately.
5. **Report** – a Markdown + JSON report lists every finding, its outcome and reason, Claude's
   explanation and suggested fix, test results before/after, and the diff of applied changes.

## 6. Technology / Framework

Python 3.11 · `libcst` (Python syntax trees) · Node.js · `jscodeshift` / Babel / recast (JS/JSX
syntax trees) · Anthropic Python SDK with structured outputs (Pydantic) · pytest · Jest.

## 7. Tools / Integrations

- **Claude API (Anthropic)** – judgment layer (`src/analyzer/claude_client.py`).
- **pytest / Jest** – the target repository's own test suites as the validation oracle.
- *Future:* GitHub API to open a pull request with the migrated code and the report as its
  description (not built).

## 8. Expected Business Value

- **Less manual migration effort:** on the demo repo, 14 of 43 findings were fixed and validated
  automatically in about 30 seconds; the remaining 29 come with a reason and, with Claude enabled,
  a suggested change.
- **Lower risk:** nothing is kept unless the existing tests still pass; risky patterns are routed
  to humans with an explanation instead of being rewritten blindly. In the demo, a
  harmless-looking fix that would have changed output was caught and rolled back automatically.
- **Faster tech-debt reduction:** can run repeatedly (e.g. in CI) as a migration backlog shrinks;
  the report doubles as a reviewable change summary.

## 9. Innovation / Differentiator

**Two-layer design: deterministic detection + AI judgment + test-validated execution.**
Metamorph is neither a plain linter (which can't judge context) nor blind AI rewriting (which
can't be reproduced or trusted). Detection and rewriting are deterministic, so results are
reproducible and auditable; Claude adds judgment exactly where rules can't – deciding whether
*this* occurrence is safe – and is shown the precise diff it is approving. Every applied change is
then proven against the project's own tests and individually rolled back if it fails.

## 10. Architecture / Flow Diagram

See [docs/architecture.md](docs/architecture.md).

## 11. Effort Spent in Hrs

_<fill in>_

## 12. Expected Output

A migration report (`metamorph_report.md` + `.json`) listing the patterns found, which were
auto-fixed, rolled back or need review (with reasons and suggested fixes), test pass/fail status
before and after migration, and diffs of all applied changes – plus the migrated copy of the code.
Example: [tests/sample_report.md](tests/sample_report.md).

> The sample report was generated without an API key, so its verdicts come from the rule-based
> fallback (conservative default risk per rule); the Claude path is covered by unit tests with a
> mocked API client. Setting `ANTHROPIC_API_KEY` and re-running the same command produces a report
> with Claude's per-finding reasoning and suggested fixes (see README.md).

## 13. Data / Security Considerations

- Only the bundled demo repository was processed; no production code or secrets were used.
- The Claude API key is read from the `ANTHROPIC_API_KEY` environment variable – never
  hard-coded, committed, logged, or written to cache or reports (documented in README.md).
- Only code snippets with surrounding context are sent to the API, not whole repositories.
- The source repository is never modified when `--out` is used; all changes go to a copy.
