"""Unit tests for src/scanner/python_scanner.py."""
from pathlib import Path

import pytest

from scanner.python_scanner import scan_path, scan_source


def rule_ids(source: str) -> list[str]:
    return [f.rule_id for f in scan_source(source, "example.py")]


@pytest.mark.parametrize(
    "source, expected",
    [
        ('x = "Hello %s" % name\n', "PY001"),
        ("ok = cfg.has_key(k)\n", "PY002"),
        ("try:\n    run()\nexcept:\n    pass\n", "PY003"),
        ("class A(object):\n    pass\n", "PY004"),
        ("class A(B):\n    def f(self) -> None:\n        super(A, self).f()\n", "PY005"),
        ("from typing import List\n", "PY006"),
        ("def f(a, b):\n    return a\n", "PY007"),
        ("try:\n    run()\nexcept ValueError, e:\n    pass\n", "PY008"),
    ],
)
def test_each_rule_is_detected(source, expected):
    assert expected in rule_ids(source)


def test_modern_code_has_no_findings():
    source = (
        "from typing import Any\n\n"
        "class A:\n"
        "    def f(self, x: int) -> str:\n"
        "        try:\n"
        "            return f'{x}'\n"
        "        except ValueError as e:\n"
        "            return str(e)\n"
    )
    assert rule_ids(source) == []


def test_bytes_percent_formatting_is_not_flagged():
    assert "PY001" not in rule_ids('x = b"%s" % data\n')


def test_typing_names_that_are_not_legacy_are_ignored():
    assert rule_ids("from typing import Any, Callable\n") == []


def test_init_without_return_annotation_is_fine():
    assert rule_ids("class A:\n    def __init__(self, x: int):\n        self.x = x\n") == []


def test_python2_print_is_reported_as_unparseable():
    assert rule_ids('print "hi"\n') == ["PY000"]


def test_py2_except_is_not_also_reported_as_unparseable():
    # libcst can read it, ast can't - PY008 explains the syntax error, so no PY000.
    assert rule_ids("try:\n    pass\nexcept IOError, e:\n    pass\n") == ["PY008"]


def test_finding_position_and_snippet():
    [f] = scan_source('a = 1\nb = "%s" % a\n', "m.py")
    assert (f.line, f.column, f.snippet) == (2, 4, 'b = "%s" % a')
    assert f.id == "m.py:2:4:PY001"


def test_scan_path_skips_test_files_and_virtualenvs(tmp_path: Path):
    (tmp_path / "app.py").write_text('x = "%s" % 1\n')
    (tmp_path / "test_app.py").write_text('x = "%s" % 1\n')
    (tmp_path / "conftest.py").write_text('x = "%s" % 1\n')
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").write_text('x = "%s" % 1\n')

    files, findings = scan_path(tmp_path)
    assert [p.name for p in files] == ["app.py"]
    assert [f.file for f in findings] == ["app.py"]
