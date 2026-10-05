# Metamorph – Architecture

## Pipeline

```
                    ┌──────────────────────────────┐
  [Repository] ───▶ │ 0. Copy to --out (optional)  │   source repo is never modified
                    └──────────────┬───────────────┘
                                   ▼
        ┌───────────────────────────────────────────────────────┐
        │ 1. SCAN  (deterministic, rule-based)                  │
        │   python_scanner.py  ── libcst syntax tree + ast check │
        │   react_scanner.js   ── jscodeshift (Babel) tree       │
        │   rules: src/rules/python_rules.json, react_rules.json │
        └──────────────────────────┬────────────────────────────┘
                                   ▼  Finding list (rule, file, line, snippet)
        ┌───────────────────────────────────────────────────────┐
        │ 2. BASELINE TESTS   pytest / jest (must be green)     │
        └──────────────────────────┬────────────────────────────┘
                                   ▼
        ┌───────────────────────────────────────────────────────┐
        │ 3. ANALYZE  (Claude, one call per finding)            │
        │   input : rule + code context + exact proposed diff   │
        │   output: {safe_to_autofix, risk_level, explanation,  │
        │            suggested_fix}  (structured JSON output)   │
        │   cache : .metamorph_cache/  →  --mode offline replay │
        │   no key: conservative rule default (default_risk)    │
        └──────────────────────────┬────────────────────────────┘
                                   ▼
             approved = rewrite exists AND safe AND risk <= --max-risk
                                   ▼
        ┌───────────────────────────────────────────────────────┐
        │ 4. MIGRATE + VALIDATE  (per fix, bottom-up per file)  │
        │   python_fixer.py / react_fixer.js rewrites ONE node  │
        │   run the language's test suite                       │
        │   red → restore the file (rollback)                   │
        └──────────────────────────┬────────────────────────────┘
                                   ▼
        ┌───────────────────────────────────────────────────────┐
        │ 5. REPORT   metamorph_report.md + .json               │
        │   auto-fixed / rolled back / needs review, test       │
        │   results before & after, Claude's reasoning, diffs   │
        └───────────────────────────────────────────────────────┘
```

## Design decisions

**Deterministic detection, AI judgment.** Claude never decides *what* to look for – the scanners
do, from a fixed rule catalogue, so the same repo always yields the same findings. Claude decides
*what to do* about each finding, given its real context and the exact diff the fixer would
apply. A plain linter can't see that `cfg.has_key(k)` is called on a custom class rather than a
dict; blind AI rewriting can't be reproduced or audited. Metamorph sits between the two.

**Four independent gates before code changes.** A fix is kept only if (1) a deterministic rewrite
exists, (2) Claude judges it safe, (3) its risk is within `--max-risk`, and (4) the existing tests
stay green after it is applied. Any gate failing routes the finding to human review, with a reason.

**Syntax trees, not regex or text generation.** `libcst` (Python) and `jscodeshift`/recast (JS)
rewrite only the targeted node and reprint the rest of the file byte-for-byte, keeping comments
and formatting. Every Python rewrite is re-parsed with `ast`; every JS rewrite is re-parsed with
Babel. A rewrite that would produce invalid code is refused.

**Fixers refuse rather than guess.** Each rewrite has explicit preconditions, e.g.:
- `%`-format → f-string: refuses dict-style `%(name)s`, non-literal argument tuples, quotes inside
  arguments; emits `{x:d}` for `%d` so a float fails loudly instead of printing `3.7` for `3`.
- `super(A, self)` → `super()`: only directly inside a method of class `A`.
- `typing.List` → `list`: uses libcst's scope analysis, so unrelated names called `List` are untouched.
- `defaultProps` → default parameters: refuses if props aren't destructured, if a `...rest` would
  change, or if `Comp.defaultProps` is read elsewhere.
- class → function component: only for render-only, non-Pure classes that use `this` only for `this.props`.

**One fix at a time, bottom-up.** Fixes are applied in reverse source order, so a fix never shifts
the line/column of a finding that is still pending, and each test run tests exactly one change –
a failure is attributable and the rollback is precise.

**Test files are never rewritten.** They are the oracle that validates every change.

**Safe offline operation.** Live Claude verdicts are cached keyed by a hash of model + prompt.
`--mode offline` replays them without a key. Without a cache entry the tool falls back to the
rule's `default_risk`, which only ever auto-applies `low`-risk rules.

**Stale-bytecode guard.** Test subprocesses run with `PYTHONDONTWRITEBYTECODE=1`. Python validates
cached `.pyc` files by source size + mtime (whole seconds), so fix → rollback → another
same-length fix within one second could otherwise execute outdated bytecode. Found during testing.

## Components

| Path | Language | Responsibility |
|---|---|---|
| `src/metamorph.py` | Python | CLI + orchestration of the five stages |
| `src/rules/*.json` | JSON | Curated rule catalogue (id, description, auto-fixable, default risk) |
| `src/scanner/finding.py` | Python | `Finding` record passed between all stages |
| `src/scanner/python_scanner.py` | Python | libcst visitor detecting PY000–PY008 |
| `src/scanner/react_scanner.js` | Node | jscodeshift scanner detecting RX000–RX005 |
| `src/react_bridge.py` | Python | Runs the Node scanner/fixer as subprocesses, JSON in/out |
| `src/analyzer/claude_client.py` | Python | Prompt building, Claude structured output, cache, fallback |
| `src/fixer/python_fixer.py` | Python | libcst transformer applying one fix |
| `src/fixer/react_fixer.js` | Node | jscodeshift transform applying one fix |
| `src/runner/test_runner.py` | Python | Detects and runs pytest / jest |
| `src/report/report_generator.py` | Python | Markdown + JSON report |

## Rule catalogue

| Rule | Pattern | Auto-fix | Default risk |
|---|---|---|---|
| PY000 | File is not valid Python 3 | – | high |
| PY001 | `"%s" % x` → f-string | yes | low |
| PY002 | `d.has_key(k)` → `k in d` | yes | medium |
| PY003 | bare `except:` → `except Exception:` | yes | medium |
| PY004 | `class A(object)` → `class A` | yes | low |
| PY005 | `super(A, self)` → `super()` | yes | low |
| PY006 | `typing.List/Dict/Optional/Union` → builtins / `X \| None` | yes | low |
| PY007 | missing type hints | review only | medium |
| PY008 | `except E, e:` → `except E as e:` | yes | low |
| RX000 | File can't be parsed | – | high |
| RX001 | class component → function component | simple cases | medium |
| RX002 | `componentDidMount/DidUpdate/WillUnmount` → `useEffect` | review only | medium |
| RX003 | `componentWillMount/WillReceiveProps/WillUpdate` | review only | high |
| RX004 | `Comp.defaultProps` → default parameters | yes | low |
| RX005 | PropTypes → TypeScript types | review only | low |

## Security

- The Claude API key is read from the `ANTHROPIC_API_KEY` environment variable by the Anthropic
  SDK. It is never hard-coded, logged, or written to the cache or report.
- Only code snippets and surrounding context from the scanned repo are sent to the API.
- The source repository is copied before migration (`--out`); the original is never modified.

## Future work

- GitHub API integration: open a pull request with the migrated copy and the report as description.
- AI-assisted detection "layer 2": let Claude propose new candidate patterns, reviewed and promoted
  into the deterministic rule catalogue.
- More rewrites (lifecycle → `useEffect` for common shapes, PropTypes → TypeScript interfaces).
