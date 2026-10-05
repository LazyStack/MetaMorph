"""Python legacy-pattern scanner.

Parses each .py file into a libcst Concrete Syntax Tree and walks it with a
visitor. Each `visit_<NodeType>` method checks one kind of node against the
curated rules in rules/python_rules.json. Detection is purely rule-based and
deterministic: the same input always yields the same findings.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from scanner.finding import Finding

# typing alias -> builtin replacement (None = needs the `|` operator instead)
TYPING_ALIASES = {
    "List": "list",
    "Dict": "dict",
    "Tuple": "tuple",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Type": "type",
    "Optional": None,
    "Union": None,
}

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "build", "dist"}
MAX_SNIPPET_LINES = 8


def is_test_file(path: Path) -> bool:
    """Test files are the safety net for validating fixes, so we never rewrite them."""
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def is_py2_except(node: cst.ExceptHandler) -> bool:
    """libcst is lenient and parses Python 2's `except ValueError, e:` as catching
    an unparenthesized tuple `(ValueError, e)`. Real Python 3 rejects that line."""
    t = node.type
    return (
        node.name is None
        and isinstance(t, cst.Tuple)
        and not t.lpar                      # no parentheses written in the source
        and len(t.elements) == 2
        and isinstance(t.elements[1].value, cst.Name)
    )


class LegacyPatternVisitor(cst.CSTVisitor):
    # Ask libcst to compute line/column positions for every node.
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, rel_path: str, source_lines: list[str]) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.source_lines = source_lines
        self.findings: list[Finding] = []

    def _add(self, rule_id: str, node: cst.CSTNode, message: str, header_only: bool = False) -> None:
        """Record a finding for `node`. header_only keeps just the first line
        (for classes, functions and except blocks whose bodies aren't the issue)."""
        pos = self.get_metadata(PositionProvider, node)
        start, end = pos.start.line, pos.end.line
        last = start if header_only else min(end, start + MAX_SNIPPET_LINES - 1)
        snippet = "\n".join(self.source_lines[start - 1 : last])
        self.findings.append(
            Finding(
                rule_id=rule_id,
                language="python",
                file=self.rel_path,
                line=start,
                column=pos.start.column,
                end_line=end,
                snippet=snippet,
                message=message,
            )
        )

    # PY001: "Hello %s" % name
    def visit_BinaryOperation(self, node: cst.BinaryOperation) -> None:
        left = node.left
        if (
            isinstance(node.operator, cst.Modulo)
            and isinstance(left, cst.SimpleString)
            and "b" not in left.prefix.lower()  # bytes % formatting has no f-string equivalent
        ):
            self._add("PY001", node, "String is formatted with the % operator.")

    # PY002: d.has_key(k)      PY005: super(Foo, self)
    def visit_Call(self, node: cst.Call) -> None:
        func = node.func
        if isinstance(func, cst.Attribute) and func.attr.value == "has_key" and len(node.args) == 1:
            self._add("PY002", node, "Uses .has_key(), which Python 3 dicts do not have.")
        if isinstance(func, cst.Name) and func.value == "super" and len(node.args) == 2:
            self._add("PY005", node, "Uses the two-argument form of super().")

    # PY003: except:      PY008: except ValueError, e:
    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> None:
        if node.type is None:
            self._add("PY003", node, "Bare `except:` also catches SystemExit and KeyboardInterrupt.", header_only=True)
        elif is_py2_except(node):
            self._add("PY008", node, "Uses Python 2 `except X, e:` syntax.", header_only=True)

    # PY004: class Foo(object):
    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        for base in node.bases:
            if base.keyword is None and isinstance(base.value, cst.Name) and base.value.value == "object":
                self._add("PY004", node, f"Class `{node.name.value}` explicitly inherits from object.", header_only=True)
                break

    # PY006: from typing import List, Optional
    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if not (isinstance(node.module, cst.Name) and node.module.value == "typing"):
            return
        if isinstance(node.names, cst.ImportStar):
            return
        legacy = [
            alias.name.value
            for alias in node.names
            if isinstance(alias.name, cst.Name) and alias.asname is None and alias.name.value in TYPING_ALIASES
        ]
        if legacy:
            self._add("PY006", node, f"Imports deprecated typing aliases: {', '.join(legacy)}.")

    # PY007: def foo(a, b):   (no annotations)
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        p = node.params
        params = [*p.posonly_params, *p.params, *p.kwonly_params]
        if isinstance(p.star_arg, cst.Param):
            params.append(p.star_arg)
        if p.star_kwarg is not None:
            params.append(p.star_kwarg)
        if params and params[0].name.value in ("self", "cls"):
            params = params[1:]

        missing = [param.name.value for param in params if param.annotation is None]
        missing_return = node.returns is None and node.name.value != "__init__"
        if missing or missing_return:
            parts = []
            if missing:
                parts.append(f"parameters without hints: {', '.join(missing)}")
            if missing_return:
                parts.append("no return type")
            self._add("PY007", node, f"Function `{node.name.value}` has {'; '.join(parts)}.", header_only=True)


def _unparseable(source: str, rel_path: str, line: int, column: int, reason: str) -> Finding:
    lines = source.splitlines()
    return Finding(
        rule_id="PY000",
        language="python",
        file=rel_path,
        line=line,
        column=column,
        end_line=line,
        snippet=lines[line - 1] if 0 < line <= len(lines) else "",
        message=f"File is not valid Python 3: {reason}",
    )


def scan_source(source: str, rel_path: str) -> list[Finding]:
    """Scan one file's source text and return its findings, in source order."""
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as err:
        # libcst can't read it at all - report it rather than crash; a human must look.
        return [_unparseable(source, rel_path, err.raw_line or 1, err.raw_column, err.message)]

    visitor = LegacyPatternVisitor(rel_path, source.splitlines())
    MetadataWrapper(module).visit(visitor)
    findings = visitor.findings

    # Second opinion from Python's own parser. libcst accepts a few things Python 3
    # rejects; if the error isn't one a rule already explains (PY008), flag the file.
    try:
        ast.parse(source)
    except SyntaxError as err:
        explained = {f.line for f in findings if f.rule_id == "PY008"}
        if err.lineno not in explained:
            findings.append(_unparseable(source, rel_path, err.lineno or 1, err.offset or 0, err.msg))

    return sorted(findings, key=lambda f: (f.line, f.column))


def find_python_files(root: Path) -> list[Path]:
    """All non-test .py files under root, skipping virtualenvs, caches, etc."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.endswith(".py") and not is_test_file(path):
                files.append(path)
    return files


def scan_path(root: Path) -> tuple[list[Path], list[Finding]]:
    """Scan every Python file under root. Returns (files scanned, findings)."""
    root = Path(root)
    files = find_python_files(root)
    findings: list[Finding] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        findings.extend(scan_source(path.read_text(encoding="utf-8"), rel))
    return files, findings
