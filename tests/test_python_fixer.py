"""Unit tests for src/fixer/python_fixer.py."""
import pytest

from fixer.python_fixer import FixNotSupported, apply_fix
from scanner.python_scanner import scan_source


def fix(source: str, rule_id: str) -> str:
    """Apply the first finding of `rule_id` in `source`."""
    finding = next(f for f in scan_source(source, "t.py") if f.rule_id == rule_id)
    return apply_fix(source, finding)


@pytest.mark.parametrize(
    "before, after",
    [
        ('x = "Hello %s" % name\n', 'x = f"Hello {name}"\n'),
        ('x = "%s is %d" % (a, b)\n', 'x = f"{a} is {b:d}"\n'),
        ("x = '%.2f%%' % pct\n", "x = f'{pct:.2f}%'\n"),
        ('x = "%-8s|%05d" % (a, n)\n', 'x = f"{a!s:<8}|{n:05d}"\n'),
        ('x = "%r" % obj\n', 'x = f"{obj!r}"\n'),
        ('x = "{k}: %s" % v\n', 'x = f"{{k}}: {v}"\n'),
    ],
)
def test_percent_format_to_fstring(before, after):
    assert fix(before, "PY001") == after


@pytest.mark.parametrize(
    "source, reason",
    [
        ('x = "%(name)s" % data\n', "Mapping keys"),
        ('x = "%s %s" % pair\n', "not a literal tuple"),
        ("x = '%s' % d['k']\n", "same quote"),
        ('x = "%s %s" % (a,)\n', "2 placeholders but 1"),
    ],
)
def test_percent_format_refusals(source, reason):
    with pytest.raises(FixNotSupported, match=reason):
        fix(source, "PY001")


def test_has_key():
    assert fix("ok = d.has_key(k)\n", "PY002") == "ok = k in d\n"
    assert fix("ok = d.has_key(a or b)\n", "PY002") == "ok = (a or b) in d\n"
    # must not turn into the chained comparison `k in d == True`
    assert fix("ok = d.has_key(k) == True\n", "PY002") == "ok = (k in d) == True\n"


def test_bare_except_keeps_comment():
    before = "try:\n    run()\nexcept:  # keep me\n    pass\n"
    assert fix(before, "PY003") == "try:\n    run()\nexcept Exception:  # keep me\n    pass\n"


def test_object_base():
    assert fix("class A(object):\n    pass\n", "PY004") == "class A:\n    pass\n"
    assert fix("class A(Base, object):\n    pass\n", "PY004") == "class A(Base):\n    pass\n"


def test_super():
    before = "class A(B):\n    def f(self):\n        super(A, self).f()\n"
    assert fix(before, "PY005") == "class A(B):\n    def f(self):\n        super().f()\n"


def test_super_with_different_class_is_refused():
    with pytest.raises(FixNotSupported, match="does not match"):
        fix("class A(B):\n    def f(self):\n        super(B, self).f()\n", "PY005")


def test_super_inside_lambda_is_refused():
    with pytest.raises(FixNotSupported, match="not called directly inside a method"):
        fix("class A(B):\n    def f(self):\n        g = lambda: super(A, self).f()\n", "PY005")


def test_typing_aliases():
    before = (
        "from typing import Any, List, Optional, Union\n\n"
        "def f(xs: List[int], y: Optional[str], z: Union[int, float]) -> Any:\n"
        "    List = 3  # unrelated local name\n"
        "    return xs\n"
    )
    after = (
        "from typing import Any\n\n"
        "def f(xs: list[int], y: str | None, z: int | float) -> Any:\n"
        "    List = 3  # unrelated local name\n"
        "    return xs\n"
    )
    assert fix(before, "PY006") == after


def test_typing_import_removed_when_empty():
    assert fix("from typing import Dict\nx: Dict[str, int] = {}\n", "PY006") == "x: dict[str, int] = {}\n"


def test_typing_in_string_annotation_is_refused():
    with pytest.raises(FixNotSupported, match="string annotation"):
        fix("from typing import List\nx: 'List[int]' = []\n", "PY006")


def test_py2_except():
    before = "try:\n    run()\nexcept ValueError, e:\n    log(e)\n"
    assert fix(before, "PY008") == "try:\n    run()\nexcept ValueError as e:\n    log(e)\n"


def test_fix_in_file_with_other_py2_syntax_is_still_allowed():
    # The file can't pass ast.parse until PY008 is fixed too; PY001 alone must still work.
    before = 'try:\n    pass\nexcept IOError, e:\n    print("err %s" % e)\n'
    assert 'print(f"err {e}")' in fix(before, "PY001")


def test_review_only_rule_is_refused():
    with pytest.raises(FixNotSupported):
        fix("def f(a):\n    return a\n", "PY007")
