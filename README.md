# Metamorph – Legacy Code Migration Agent

Metamorph scans a codebase for known legacy patterns in **Python** and **React/JS**, asks
**Claude** whether each finding is safe to auto-fix, applies the safe fixes, re-runs the
project's own tests after every single change (rolling back anything that breaks), and writes
a migration report.

```
Scan (rule-based) → Analyze (Claude) → Migrate (AST rewrite) → Validate (tests, rollback) → Report
```

See [Agent.md](Agent.md) for the idea and value, and [docs/architecture.md](docs/architecture.md)
for the design.

---

## 1. Setup

Requirements: **Python 3.10+** and **Node.js 18+** (with npm).

```bash
cd Arunava_Saha_700160
python -m pip install -r requirements.txt     # libcst, anthropic, pydantic, pytest
npm install                                   # jscodeshift, jest, babel, react (for the React side)
```

### Claude API key (optional but recommended)

Metamorph reads the key from the `ANTHROPIC_API_KEY` environment variable. **Never put the key in
a file in this folder.**

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "<your-api-key>"
```
```bash
# macOS / Linux
export ANTHROPIC_API_KEY="<your-api-key>"
```

Optional: `METAMORPH_MODEL` overrides the Claude model (default `claude-opus-5`).

Without a key Metamorph still runs end to end: it uses each rule's conservative default risk
instead of Claude's judgment (only `low`-risk rewrites are applied), and the report says so.

---

## 2. How to run

```bash
# Full migration of the bundled demo repo into a copy (the original is never modified)
python src/metamorph.py src/demo_repo --out build/migrated --report build/metamorph_report.md

# Just list findings, change nothing
python src/metamorph.py src/demo_repo --scan-only
```

| Option | Meaning |
|---|---|
| `repo` | Folder to migrate |
| `--out DIR` | Copy the repo to `DIR` and migrate the copy (recommended). Without it, files are changed in place. |
| `--mode auto\|claude\|offline` | `auto` (default): Claude if a key is set, else rule defaults. `claude`: require Claude. `offline`: never call the API; replay cached Claude verdicts from `.metamorph_cache/`. |
| `--model ID` | Claude model id |
| `--max-risk low\|medium` | Highest risk level that may be auto-applied (default `low`) |
| `--report PATH` | Report location (a `.json` twin is written next to it) |
| `--no-tests` | Skip test validation (not recommended) |
| `--scan-only` | Only print findings |

Test suites are detected automatically: **pytest** if the repo contains `test_*.py` files,
**jest** if it has a `jest.config.js`. Test files themselves are never modified.

---

## 3. Sample input / output

**Input:** [`src/demo_repo/`](src/demo_repo) – a small, deliberately old-fashioned shop app:

| Path | What's in it |
|---|---|
| `python/shop/inventory.py` | `class X(object)`, `super(X, self)`, `%`-formatting, `typing.Dict/List/Optional` |
| `python/shop/reports.py` | `%d` applied to a float (a trap), bare `except:` |
| `python/shop/legacy_config.py` | `.has_key()` on a custom class that is *not* a dict (a trap) |
| `python/scripts/import_job.py` | Python 2 `except IOError, e:` |
| `python/scripts/old_report.py` | Python 2 `print` statement (cannot be parsed) |
| `react/components/*.jsx` | Class components, `componentDidMount`, `componentWillReceiveProps`, `defaultProps`, `propTypes` |
| `python/tests/`, `react/__tests__/` | The demo's own pytest (10) and jest (7) tests |

**Console output:**

```
[1/5] Scanning ...\build\migrated
      6 Python + 5 React files, 43 findings
[2/5] Baseline tests: pytest, jest
      pytest: PASS - 10 passed in 0.13s
      jest: PASS - 7 passed, 7 total
[3/5] Judging 43 findings with offline (cached Claude verdicts, rule-based fallback when no cache entry)
      15 approved for auto-fix, 28 need review
[4/5] Applying approved fixes one at a time (bottom-up per file), testing after each
      python/scripts/import_job.py:11:14:PY001: applied, pytest PASS
      ...
      python/shop/reports.py:11:11:PY001: pytest FAIL -> rolled back
      ...
      react/components/Badge.jsx:9:0:RX004: applied, jest PASS
[5/5] Report: ...\build\metamorph_report.md
      auto-fixed 14, rolled back 1, needs review 28
      final pytest: PASS - 10 passed in 0.04s
      final jest: PASS - 7 passed, 7 total
```

**Example changes applied:**

```diff
-class Product(object):
+class Product:
-        return "%s (%s) - $%.2f" % (self.name, self.sku, self.price)
+        return f"{self.name} ({self.sku}) - ${self.price:.2f}"
-        super(PerishableProduct, self).__init__(sku, name, price, qty)
+        super().__init__(sku, name, price, qty)
```
```diff
-export function Badge({ label, color, size }) {
+export function Badge({ label, color = "grey", size = "md" }) {
 ...
-Badge.defaultProps = {
-  color: "grey",
-  size: "md",
-};
```

**Example rollback:** `"Average stock: %d units" % avg` was rewritten to
`f"Average stock: {avg:d} units"`. `avg` is a float, so the new code raises `ValueError`, the
demo's test failed, and Metamorph restored the original line automatically.

**Full report:** [`tests/sample_report.md`](tests/sample_report.md) (with a JSON twin
`tests/sample_report.json`), produced by actually running the command above.

> Note: `tests/sample_report.md` was generated **without** an API key, so its verdicts come from
> the rule-based fallback (the report header says so). To regenerate it with Claude's judgment:
> set `ANTHROPIC_API_KEY` and run
> `python src/metamorph.py src/demo_repo --out build/migrated --report tests/sample_report.md`.

---

## 4. How to test

```bash
python -m pytest            # 46 tests: Python scanner, Python fixer, Claude client (mocked), end-to-end pipeline
npx jest                    # 17 tests: React scanner and React fixer
```

| Test file | Covers |
|---|---|
| `tests/test_python_scanner.py` | Every Python rule is detected; modern code produces no findings; test files and virtualenvs are skipped; Python 2 files |
| `tests/test_python_fixer.py` | Each rewrite's exact output, and every case where the fixer must refuse |
| `tests/test_claude_client.py` | Structured-output request, caching, offline replay, refusal handling, fallback (API faked, no network) |
| `tests/test_pipeline.py` | Whole pipeline on the demo: safe fixes applied, breaking fix rolled back, source repo untouched |
| `tests/test_react_scanner.js` | Every React rule is detected; React fixer conversions and refusals; line endings preserved |

The demo repo's own suites can also be run directly:
`python -m pytest src/demo_repo` and `npx jest --config src/demo_repo/jest.config.js`.

---

## 5. Project layout

```
Arunava_Saha_700160/
├── Agent.md                     idea, problem, capabilities, value
├── README.md                    this file
├── requirements.txt / package.json
├── src/
│   ├── metamorph.py             CLI + pipeline orchestration
│   ├── rules/                   curated rule catalogue (python_rules.json, react_rules.json)
│   ├── scanner/                 python_scanner.py, react_scanner.js, finding.py
│   ├── analyzer/claude_client.py   Claude judgment layer (key from env var only)
│   ├── fixer/                   python_fixer.py, react_fixer.js
│   ├── runner/test_runner.py    pytest / jest runner
│   ├── report/report_generator.py
│   ├── react_bridge.py          Python ↔ Node bridge for the React tooling
│   └── demo_repo/               deliberately legacy sample code with its own tests
├── tests/                       unit + end-to-end tests, sample_report.md
└── docs/architecture.md
```

## 6. Security & configuration

- No credentials are stored anywhere in this folder. The only secret is `ANTHROPIC_API_KEY`,
  read from the environment by the Anthropic SDK.
- `.metamorph_cache/` stores Claude's verdicts (JSON) – never the key.
- Only the demo repo was processed during development; no production code was sent to the API.
