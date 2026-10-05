# Metamorph migration report

| | |
|---|---|
| Repository | `src/demo_repo` |
| Migrated copy | `build/migrated` |
| Run at | 2026-10-05 21:08 |
| Files scanned | 6 Python, 5 React/JS |
| Judgment layer | offline (cached Claude verdicts, rule-based fallback when no cache entry) |
| Verdict sources | rule-based fallback: 43 |
| Auto-fix policy | automated rewrite exists AND judged safe AND risk <= `low` AND tests stay green |
| Duration | 35.1 s |

## Summary

| Outcome | Findings |
|---|---:|
| Auto-fixed (tests still pass) | 14 |
| Rolled back (tests failed) | 1 |
| Needs human review | 28 |
| **Total** | **43** |

### By rule

| Rule | Pattern | Found | Auto-fixed | Rolled back | Review |
|---|---|---:|---:|---:|---:|
| PY000 | File could not be parsed | 1 | 0 | 0 | 1 |
| PY001 | Old %-style string formatting | 6 | 5 | 1 | 0 |
| PY002 | dict.has_key() call | 2 | 0 | 0 | 2 |
| PY003 | Bare except clause | 1 | 0 | 0 | 1 |
| PY004 | Explicit `object` base class | 3 | 3 | 0 | 0 |
| PY005 | Old-style super() call | 2 | 2 | 0 | 0 |
| PY006 | Deprecated typing aliases | 1 | 1 | 0 | 0 |
| PY007 | Missing type hints | 17 | 0 | 0 | 17 |
| PY008 | Python 2 except syntax | 1 | 1 | 0 | 0 |
| RX001 | Class component | 3 | 0 | 0 | 3 |
| RX002 | Lifecycle method -> useEffect | 2 | 0 | 0 | 2 |
| RX003 | Unsafe legacy lifecycle | 1 | 0 | 0 | 1 |
| RX004 | defaultProps on a function component | 2 | 2 | 0 | 0 |
| RX005 | PropTypes runtime checking | 1 | 0 | 0 | 1 |

## Test validation

Each automated fix was applied on its own and the language's test suite was re-run; a fix that turned the suite red was reverted immediately.

Test runs during migration: 15

| Suite | Before migration | After migration |
|---|---|---|
| pytest | PASS - 10 passed in 0.05s | PASS - 10 passed in 0.05s |
| jest | PASS - 7 passed, 7 total | PASS - 7 passed, 7 total |

## Auto-fixed (14)

| Location | Rule | Risk | Why it was considered safe |
|---|---|---|---|
| `python/scripts/import_job.py:10` | PY008 | low | `except ValueError, e:` is a syntax error in Python 3; use `except ValueError as e:`. (No API key; used the rule's default risk.) |
| `python/scripts/import_job.py:11` | PY001 | low | `"Hello %s" % name` should become an f-string: `f"Hello {name}"`. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:2` | PY006 | low | `typing.List`, `Dict`, `Tuple`, `Set`, `Optional`, `Union` can be replaced by `list`, `dict`, `tuple`, `set`, `X \| None`, `A \| B` (Python 3.10+). (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:5` | PY004 | low | `class Foo(object):` is redundant in Python 3; use `class Foo:`. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:13` | PY001 | low | `"Hello %s" % name` should become an f-string: `f"Hello {name}"`. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:21` | PY005 | low | `super(Foo, self).method()` can be written `super().method()` in Python 3. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:25` | PY005 | low | `super(Foo, self).method()` can be written `super().method()` in Python 3. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:26` | PY001 | low | `"Hello %s" % name` should become an f-string: `f"Hello {name}"`. (No API key; used the rule's default risk.) |
| `python/shop/inventory.py:29` | PY004 | low | `class Foo(object):` is redundant in Python 3; use `class Foo:`. (No API key; used the rule's default risk.) |
| `python/shop/legacy_config.py:7` | PY004 | low | `class Foo(object):` is redundant in Python 3; use `class Foo:`. (No API key; used the rule's default risk.) |
| `python/shop/reports.py:5` | PY001 | low | `"Hello %s" % name` should become an f-string: `f"Hello {name}"`. (No API key; used the rule's default risk.) |
| `python/shop/reports.py:22` | PY001 | low | `"Hello %s" % name` should become an f-string: `f"Hello {name}"`. (No API key; used the rule's default risk.) |
| `react/components/Badge.jsx:9` | RX004 | low | `Comp.defaultProps = {...}` is deprecated for function components (removed in React 19). Use default values in the destructured props parameter. (No API key; used the rule's default risk.) |
| `react/components/UserCard.jsx:21` | RX004 | low | `Comp.defaultProps = {...}` is deprecated for function components (removed in React 19). Use default values in the destructured props parameter. (No API key; used the rule's default risk.) |

## Rolled back (1)

These fixes were judged safe but broke the test suite, so they were reverted. This is the safety net working - each needs a human look.

### `python/shop/reports.py:11` - PY001 Old %-style string formatting

**Tests after fix:** 1 failed, 9 passed in 0.14s

Attempted change:

```diff
--- a/python/shop/reports.py
+++ b/python/shop/reports.py
@@ -8,7 +8,7 @@
 def average_stock(inventory):
     products = [inventory.find(sku) for sku in inventory.skus()]
     avg = sum(p.qty for p in products) / len(products)
-    return "Average stock: %d units" % avg
+    return f"Average stock: {avg:d} units"
 
 
 def restock_ratio(current, target):
```

<details><summary>Test output</summary>

```
_________________ test_average_stock_truncates_to_whole_units _________________

inventory = <shop.inventory.Inventory object at 0x000002364B001190>

    def test_average_stock_truncates_to_whole_units(inventory):
        # (4 + 11 + 7) / 3 = 7.33 -> the report shows whole units
>       assert average_stock(inventory) == "Average stock: 7 units"
               ^^^^^^^^^^^^^^^^^^^^^^^^

python\tests\test_reports.py:10: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

inventory = <shop.inventory.Inventory object at 0x000002364B001190>

    def average_stock(inventory):
        products = [inventory.find(sku) for sku in inventory.skus()]
        avg = sum(p.qty for p in products) / len(products)
>       return f"Average stock: {avg:d} units"
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       ValueError: Unknown format code 'd' for object of type 'float'

python\shop\reports.py:11: ValueError
=========================== short test summary info ===========================
FAILED python\tests\test_reports.py::test_average_stock_truncates_to_whole_units
1 failed, 9 passed in 0.14s
```

</details>

## Needs human review (28)

### `python/scripts/import_job.py:5` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def read_rows(path):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/scripts/old_report.py:4` - PY000 File could not be parsed

**Risk:** high &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
print "Generating report for", sys.argv[1]
```

The file is not valid Python 3 (often leftover Python 2 syntax such as `except X, e:` or `print x`). It cannot be analysed or rewritten automatically. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:6` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def __init__(self, sku, name, price, qty):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:12` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def label(self):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:15` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def value(self):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:20` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def __init__(self, sku, name, price, qty, days_left):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:24` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def label(self):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:42` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def total_value(self):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/inventory.py:45` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def low_stock(self, threshold):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:8` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def __init__(self, values):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:11` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def has_key(self, key):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:14` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def __getitem__(self, key):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:17` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
    def get(self, key, default=None):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:18` - PY002 dict.has_key() call

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Judged unsafe to auto-apply (risk: medium).

```python
        if self.has_key(key):
```

`d.has_key(k)` was removed from dict in Python 3; use `k in d`. (No API key; used the rule's default risk.)

Available automated rewrite (not applied):

```diff
--- a/python/shop/legacy_config.py
+++ b/python/shop/legacy_config.py
@@ -15,7 +15,7 @@
         return self._values[key]
 
     def get(self, key, default=None):
-        if self.has_key(key):
+        if key in self:
             return self[key]
         return default
```

### `python/shop/legacy_config.py:23` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def load_flags(cfg):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/legacy_config.py:25` - PY002 dict.has_key() call

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Judged unsafe to auto-apply (risk: medium).

```python
    if cfg.has_key("debug"):
```

`d.has_key(k)` was removed from dict in Python 3; use `k in d`. (No API key; used the rule's default risk.)

Available automated rewrite (not applied):

```diff
--- a/python/shop/legacy_config.py
+++ b/python/shop/legacy_config.py
@@ -22,6 +22,6 @@
 
 def load_flags(cfg):
     flags = {"debug": False}
-    if cfg.has_key("debug"):
+    if "debug" in cfg:
         flags["debug"] = bool(cfg["debug"])
     return flags
```

### `python/shop/reports.py:4` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def format_row(name, qty):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/reports.py:8` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def average_stock(inventory):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/reports.py:14` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def restock_ratio(current, target):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `python/shop/reports.py:17` - PY003 Bare except clause

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Judged unsafe to auto-apply (risk: medium).

```python
    except:
```

`except:` also catches SystemExit and KeyboardInterrupt; use `except Exception:`. (No API key; used the rule's default risk.)

Available automated rewrite (not applied):

```diff
--- a/python/shop/reports.py
+++ b/python/shop/reports.py
@@ -14,7 +14,7 @@
 def restock_ratio(current, target):
     try:
         return current / target
-    except:
+    except Exception:
         return 0.0
```

### `python/shop/reports.py:21` - PY007 Missing type hints

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```python
def report_header(title, count):
```

Function parameters or return value have no type annotations. Correct hints need human understanding of the code, so this is never auto-fixed. (No API key; used the rule's default risk.)

### `react/components/Clock.jsx:4` - RX001 Class component

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Fixer declined: Class has more than render(): constructor, componentDidMount, componentWillUnmount - needs hooks designed by hand.

```jsx
export default class Clock extends React.Component {
```

Class components should become function components with hooks. Simple render-only classes are converted automatically; classes with state or lifecycle methods need a human. (No API key; used the rule's default risk.)

### `react/components/Clock.jsx:10` - RX002 Lifecycle method -> useEffect

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```jsx
  componentDidMount() {
```

componentDidMount / componentDidUpdate / componentWillUnmount map to useEffect, but the dependency array and cleanup must be designed by hand. (No API key; used the rule's default risk.)

### `react/components/Clock.jsx:14` - RX002 Lifecycle method -> useEffect

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```jsx
  componentWillUnmount() {
```

componentDidMount / componentDidUpdate / componentWillUnmount map to useEffect, but the dependency array and cleanup must be designed by hand. (No API key; used the rule's default risk.)

### `react/components/Greeting.jsx:4` - RX001 Class component

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Judged unsafe to auto-apply (risk: medium).

```jsx
export default class Greeting extends Component {
```

Class components should become function components with hooks. Simple render-only classes are converted automatically; classes with state or lifecycle methods need a human. (No API key; used the rule's default risk.)

Available automated rewrite (not applied):

```diff
--- a/react/components/Greeting.jsx
+++ b/react/components/Greeting.jsx
@@ -1,14 +1,12 @@
-import React, { Component } from "react";
+import React from "react";
 
 // Render-only class component: a safe candidate for automatic conversion.
-export default class Greeting extends Component {
-  render() {
-    const { name, excited } = this.props;
-    return (
-      <h1 className="greeting">
-        Hello, {name}
-        {excited ? "!" : "."}
-      </h1>
-    );
-  }
+export default function Greeting(props) {
+  const { name, excited } = props;
+  return (
+    <h1 className="greeting">
+      Hello, {name}
+      {excited ? "!" : "."}
+    </h1>
+  );
 }
```

### `react/components/ProductList.jsx:4` - RX001 Class component

**Risk:** medium &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Fixer declined: PureComponent skips re-renders on equal props; the equivalent needs React.memo, which changes the export.

```jsx
export default class ProductList extends PureComponent {
```

Class components should become function components with hooks. Simple render-only classes are converted automatically; classes with state or lifecycle methods need a human. (No API key; used the rule's default risk.)

### `react/components/ProductList.jsx:10` - RX003 Unsafe legacy lifecycle

**Risk:** high &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```jsx
  componentWillReceiveProps(nextProps) {
```

componentWillMount / componentWillReceiveProps / componentWillUpdate (and UNSAFE_ variants) are deprecated and unsafe with concurrent rendering. They usually need a redesign (derived state, effects, or memoisation). (No API key; used the rule's default risk.)

### `react/components/UserCard.jsx:15` - RX005 PropTypes runtime checking

**Risk:** low &nbsp;|&nbsp; **Verdict from:** rule-based fallback &nbsp;|&nbsp; **Why not auto-fixed:** Rule is review-only (no safe mechanical rewrite exists).

```jsx
UserCard.propTypes = {
  user: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }).isRequired,
  tags: PropTypes.arrayOf(PropTypes.string),
  onSelect: PropTypes.func,
};
```

PropTypes are ignored by React 19 and are better expressed as TypeScript types. Migrating to TypeScript is a project-level decision, so this is flagged for review with a suggested interface. (No API key; used the rule's default risk.)

## Applied changes

<details><summary><code>python/scripts/import_job.py</code></summary>

```diff
--- a/python/scripts/import_job.py
+++ b/python/scripts/import_job.py
@@ -7,6 +7,6 @@
     try:
         with open(path) as fh:
             rows = list(csv.DictReader(fh))
-    except IOError, e:
-        print("could not read %s: %s" % (path, e))
+    except IOError as e:
+        print(f"could not read {path}: {e}")
     return rows
```

</details>

<details><summary><code>python/shop/inventory.py</code></summary>

```diff
--- a/python/shop/inventory.py
+++ b/python/shop/inventory.py
@@ -1,8 +1,7 @@
 """Product catalogue and stock levels."""
-from typing import Dict, List, Optional
 
 
-class Product(object):
+class Product:
     def __init__(self, sku, name, price, qty):
         self.sku = sku
         self.name = name
@@ -10,7 +9,7 @@
         self.qty = qty
 
     def label(self):
-        return "%s (%s) - $%.2f" % (self.name, self.sku, self.price)
+        return f"{self.name} ({self.sku}) - ${self.price:.2f}"
 
     def value(self):
         return self.price * self.qty
@@ -18,25 +17,25 @@
 
 class PerishableProduct(Product):
     def __init__(self, sku, name, price, qty, days_left):
-        super(PerishableProduct, self).__init__(sku, name, price, qty)
+        super().__init__(sku, name, price, qty)
         self.days_left = days_left
 
     def label(self):
-        base = super(PerishableProduct, self).label()
-        return "%s [expires in %d days]" % (base, self.days_left)
+        base = super().label()
+        return f"{base} [expires in {self.days_left:d} days]"
 
 
-class Inventory(object):
+class Inventory:
     def __init__(self):
-        self._items: Dict[str, Product] = {}
+        self._items: dict[str, Product] = {}
 
     def add(self, product: Product) -> None:
         self._items[product.sku] = product
 
-    def find(self, sku: str) -> Optional[Product]:
+    def find(self, sku: str) -> Product | None:
         return self._items.get(sku)
 
-    def skus(self) -> List[str]:
+    def skus(self) -> list[str]:
         return sorted(self._items)
 
     def total_value(self):
```

</details>

<details><summary><code>python/shop/legacy_config.py</code></summary>

```diff
--- a/python/shop/legacy_config.py
+++ b/python/shop/legacy_config.py
@@ -4,7 +4,7 @@
 """
 
 
-class LegacyConfig(object):
+class LegacyConfig:
     def __init__(self, values):
         self._values = dict(values)
```

</details>

<details><summary><code>python/shop/reports.py</code></summary>

```diff
--- a/python/shop/reports.py
+++ b/python/shop/reports.py
@@ -2,7 +2,7 @@
 
 
 def format_row(name, qty):
-    return "%-10s|%5d" % (name, qty)
+    return f"{name!s:<10}|{qty:5d}"
 
 
 def average_stock(inventory):
@@ -19,4 +19,4 @@
 
 
 def report_header(title, count):
-    return "== %s (%d items) ==" % (title, count)
+    return f"== {title} ({count:d} items) =="
```

</details>

<details><summary><code>react/components/Badge.jsx</code></summary>

```diff
--- a/react/components/Badge.jsx
+++ b/react/components/Badge.jsx
@@ -1,12 +1,7 @@
 import React from "react";
 
-export function Badge({ label, color, size }) {
+export function Badge({ label, color = "grey", size = "md" }) {
   return (
     <span className={`badge badge-${color} badge-${size}`}>{label}</span>
   );
 }
-
-Badge.defaultProps = {
-  color: "grey",
-  size: "md",
-};
```

</details>

<details><summary><code>react/components/UserCard.jsx</code></summary>

```diff
--- a/react/components/UserCard.jsx
+++ b/react/components/UserCard.jsx
@@ -1,7 +1,7 @@
 import React from "react";
 import PropTypes from "prop-types";
 
-const UserCard = ({ user, tags, onSelect }) => (
+const UserCard = ({ user, tags = [], onSelect = () => {} }) => (
   <div className="user-card" onClick={() => onSelect(user.id)}>
     <strong>{user.name}</strong>
     <ul>
@@ -18,9 +18,4 @@
   onSelect: PropTypes.func,
 };
 
-UserCard.defaultProps = {
-  tags: [],
-  onSelect: () => {},
-};
-
 export default UserCard;
```

</details>
