"""Python auto-fixer.

`apply_fix(source, finding)` rewrites exactly ONE finding and returns the new
source text. It never touches the disk - the pipeline decides when to write,
test and roll back.

How a fix works:
  1. Parse the source into a libcst tree (comments/formatting are preserved).
  2. Walk it with a CSTTransformer. The `leave_<NodeType>` methods get each
     node and may return a replacement; we only replace the node that sits at
     the finding's exact (line, column) position.
  3. Turn the tree back into text and double-check it with Python's own parser.

When a rewrite could change behaviour in a way we can't reason about
mechanically, the fixer raises FixNotSupported and the finding is routed to
human review instead.
"""

from __future__ import annotations

import ast
import re

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider, ScopeProvider

from scanner.finding import Finding
from scanner.python_scanner import TYPING_ALIASES, is_py2_except


class FixNotSupported(Exception):
    """The fixer can't safely rewrite this occurrence. The message says why."""


# Expressions that bind more loosely than `in` and need (...) around them.
_LOOSER_THAN_IN = (cst.BooleanOperation, cst.UnaryOperation, cst.Comparison, cst.IfExp, cst.Lambda, cst.NamedExpr)


def _parenthesize(expr: cst.BaseExpression) -> cst.BaseExpression:
    return expr.with_changes(lpar=[cst.LeftParen()], rpar=[cst.RightParen()])


def apply_fix(source: str, finding: Finding) -> str:
    """Return `source` with `finding` fixed, or raise FixNotSupported."""
    wrapper = MetadataWrapper(cst.parse_module(source))
    transformer = _FixTransformer(finding, wrapper)
    new_source = wrapper.visit(transformer).code

    if not transformer.applied:
        raise FixNotSupported("The flagged code was not found at the recorded position.")
    # Never write broken code. Only checked when the input was valid Python 3:
    # a file that still has other legacy syntax (e.g. PY008) can't pass yet.
    if _is_valid_python(source) and not _is_valid_python(new_source):
        raise FixNotSupported("Rewrite produced invalid Python.")
    return new_source


def _is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


class _FixTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider, ParentNodeProvider, ScopeProvider)

    def __init__(self, finding: Finding, wrapper: MetadataWrapper) -> None:
        super().__init__()
        self.finding = finding
        self.applied = False
        # Stack of enclosing scopes, e.g. [("class", "Greeter"), ("def", "self")].
        # Needed by PY005 to check that super(Greeter, self) is really inside Greeter.
        self.scopes: list[tuple[str, str]] = []
        # PY006 only: every Name node that refers to the flagged typing import.
        self.typing_refs: dict[int, str] = {}
        self.typing_unions_left: set[int] = set()
        if finding.rule_id == "PY006":
            self._collect_typing_refs(wrapper)

    def _is_target(self, node: cst.CSTNode) -> bool:
        pos = self.get_metadata(PositionProvider, node)
        return (pos.start.line, pos.start.column) == (self.finding.line, self.finding.column)

    def _rule(self, rule_id: str, node: cst.CSTNode) -> bool:
        return self.finding.rule_id == rule_id and not self.applied and self._is_target(node)

    # ---- scope tracking (PY005) --------------------------------------------

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self.scopes.append(("class", node.name.value))

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        params = node.params.posonly_params or node.params.params
        self.scopes.append(("def", params[0].name.value if params else ""))

    def visit_Lambda(self, node: cst.Lambda) -> None:
        self.scopes.append(("lambda", ""))

    def leave_Lambda(self, original_node, updated_node):
        self.scopes.pop()
        return updated_node

    def leave_FunctionDef(self, original_node, updated_node):
        self.scopes.pop()
        return updated_node

    # ---- PY004: class Foo(object): -> class Foo: ---------------------------

    def leave_ClassDef(self, original_node, updated_node):
        self.scopes.pop()
        if not self._rule("PY004", original_node):
            return updated_node
        bases = [
            b for b in updated_node.bases
            if not (b.keyword is None and isinstance(b.value, cst.Name) and b.value.value == "object")
        ]
        self.applied = True
        if not bases and not updated_node.keywords:
            # No bases left: drop the parentheses too.
            return updated_node.with_changes(bases=[], lpar=cst.MaybeSentinel.DEFAULT, rpar=cst.MaybeSentinel.DEFAULT)
        if bases and not updated_node.keywords:
            bases[-1] = bases[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)  # no dangling comma
        return updated_node.with_changes(bases=bases)

    # ---- PY003 / PY008: except clauses -------------------------------------

    def leave_ExceptHandler(self, original_node, updated_node):
        if self._rule("PY003", original_node):
            # except:  ->  except Exception:
            self.applied = True
            return updated_node.with_changes(
                type=cst.Name("Exception"),
                whitespace_after_except=cst.SimpleWhitespace(" "),
            )
        if self._rule("PY008", original_node) and is_py2_except(original_node):
            # except ValueError, e:  ->  except ValueError as e:
            exc_type, var = (el.value for el in updated_node.type.elements)
            self.applied = True
            return updated_node.with_changes(type=exc_type, name=cst.AsName(name=var))
        return updated_node

    # ---- PY002 / PY005: calls ----------------------------------------------

    def leave_Call(self, original_node, updated_node):
        if self._rule("PY002", original_node):
            parent = self.get_metadata(ParentNodeProvider, original_node)
            return self._fix_has_key(updated_node, parent)
        if self._rule("PY005", original_node):
            return self._fix_super(updated_node)
        return updated_node

    def _fix_has_key(self, call: cst.Call, parent: cst.CSTNode) -> cst.BaseExpression:
        # d.has_key(k)  ->  k in d
        receiver = call.func.value
        key = call.args[0].value
        if isinstance(key, _LOOSER_THAN_IN):
            key = _parenthesize(key)               # d.has_key(a or b) -> (a or b) in d
        comparison = cst.Comparison(
            left=key,
            comparisons=[cst.ComparisonTarget(operator=cst.In(), comparator=receiver)],
        )
        # Parenthesize when the surrounding code binds tighter than `in`, e.g.
        # `d.has_key(k) == True` must not become the chained `k in d == True`.
        if isinstance(parent, (cst.Comparison, cst.BinaryOperation, cst.Attribute, cst.Subscript, cst.Await)):
            comparison = _parenthesize(comparison)
        self.applied = True
        return comparison

    def _fix_super(self, call: cst.Call) -> cst.Call:
        # super(Foo, self)  ->  super()   ...only if we're directly inside
        # a method of class Foo whose first parameter is `self`. Zero-argument
        # super() does not work in nested functions or lambdas.
        cls_arg, self_arg = (a.value for a in call.args)
        if not (isinstance(cls_arg, cst.Name) and isinstance(self_arg, cst.Name)):
            raise FixNotSupported("super() arguments are not simple names.")
        if len(self.scopes) < 2 or self.scopes[-1][0] != "def" or self.scopes[-2][0] != "class":
            raise FixNotSupported("super() is not called directly inside a method.")
        if self.scopes[-2][1] != cls_arg.value or self.scopes[-1][1] != self_arg.value:
            raise FixNotSupported(
                f"super({cls_arg.value}, {self_arg.value}) does not match the enclosing class/method "
                "- removing the arguments would change which class is skipped."
            )
        self.applied = True
        return call.with_changes(args=[])

    # ---- PY001: "..." % args  ->  f"..." -----------------------------------

    def leave_BinaryOperation(self, original_node, updated_node):
        if not self._rule("PY001", original_node):
            return updated_node
        fstring = percent_to_fstring(updated_node.left, updated_node.right)
        self.applied = True
        return fstring.with_changes(lpar=updated_node.lpar, rpar=updated_node.rpar)

    # ---- PY006: typing aliases -> builtins ---------------------------------

    def _collect_typing_refs(self, wrapper: MetadataWrapper) -> None:
        """Use libcst's scope analysis to find every place the flagged import's
        names are used. This is precise: a local variable or attribute that
        happens to be called `List` is not touched."""
        target = None
        positions = wrapper.resolve(PositionProvider)
        for node, pos in positions.items():
            if isinstance(node, cst.ImportFrom) and (pos.start.line, pos.start.column) == (
                self.finding.line,
                self.finding.column,
            ):
                target = node
                break
        if target is None or isinstance(target.names, cst.ImportStar):
            return

        global_scope = wrapper.resolve(ScopeProvider)[wrapper.module]
        for alias in target.names:
            name = alias.name.value if isinstance(alias.name, cst.Name) else None
            if name not in TYPING_ALIASES or alias.asname is not None:
                continue
            for assignment in global_scope.assignments[name]:
                if getattr(assignment, "node", None) is not target:
                    continue
                for ref in assignment.references:
                    if not isinstance(ref.node, cst.Name):
                        raise FixNotSupported(f"`{name}` is used inside a string annotation.")
                    self.typing_refs[id(ref.node)] = name
                    if TYPING_ALIASES[name] is None:
                        self.typing_unions_left.add(id(ref.node))

    def leave_Name(self, original_node, updated_node):
        name = self.typing_refs.get(id(original_node))
        if name and TYPING_ALIASES[name]:
            return updated_node.with_changes(value=TYPING_ALIASES[name])  # List -> list
        return updated_node

    def leave_Subscript(self, original_node, updated_node):
        # Optional[X] -> X | None        Union[A, B] -> A | B
        value_id = id(original_node.value)
        if value_id not in self.typing_unions_left:
            return updated_node
        members = []
        for element in updated_node.slice:
            if not isinstance(element.slice, cst.Index):
                raise FixNotSupported("Unexpected slice inside Optional/Union.")
            members.append(element.slice.value)
        if self.typing_refs[value_id] == "Optional":
            members.append(cst.Name("None"))
        union = members[0]
        for member in members[1:]:
            union = cst.BinaryOperation(left=union, operator=cst.BitOr(), right=member)
        self.typing_unions_left.discard(value_id)
        return union

    def leave_Module(self, original_node, updated_node):
        # Runs last, after every usage in the file has been visited.
        if self.finding.rule_id == "PY006" and self.typing_unions_left:
            raise FixNotSupported("Optional/Union is used without [...] somewhere, e.g. at runtime.")
        return updated_node

    def leave_ImportFrom(self, original_node, updated_node):
        if not self._rule("PY006", original_node):
            return updated_node
        keep = [
            a for a in updated_node.names
            if not (isinstance(a.name, cst.Name) and a.asname is None and a.name.value in TYPING_ALIASES)
        ]
        self.applied = True
        if not keep:
            return cst.RemoveFromParent()  # whole `from typing import ...` line goes
        keep[-1] = keep[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
        return updated_node.with_changes(names=keep)


# ---------------------------------------------------------------------------
# %-format -> f-string conversion
# ---------------------------------------------------------------------------

# %[(key)][flags][width][.precision]type
_SPEC = re.compile(r"%(?P<key>\([^)]*\))?(?P<flags>[-+ #0]*)(?P<width>\*|\d+)?(?:\.(?P<prec>\*|\d+))?(?P<type>.)", re.S)
_NUMERIC = set("diouxXeEfFgG")


def percent_to_fstring(left: cst.SimpleString, right: cst.BaseExpression) -> cst.FormattedString:
    prefix = left.prefix.lower()
    if "b" in prefix or "f" in prefix:
        raise FixNotSupported("Bytes or f-string on the left of %.")
    quote = left.quote
    content = left.value[len(left.prefix) + len(quote) : -len(quote)]

    # 1. Split the format string into literal text and %-specifiers.
    pieces: list[str | re.Match] = []
    pos = 0
    for m in _SPEC.finditer(content):
        pieces.append(content[pos : m.start()])
        pieces.append(m)
        pos = m.end()
    pieces.append(content[pos:])
    specs = [p for p in pieces if isinstance(p, re.Match) and p["type"] != "%"]

    # 2. Work out which expression feeds each specifier.
    if isinstance(right, cst.Tuple):
        args = [el.value for el in right.elements]
    elif len(specs) == 1 and not isinstance(right, (cst.Dict, cst.List)):
        args = [right]
    else:
        raise FixNotSupported("Arguments are not a literal tuple, so they can't be matched to placeholders.")
    if len(args) != len(specs):
        raise FixNotSupported(f"{len(specs)} placeholders but {len(args)} arguments.")

    # 3. Rebuild as f-string text.
    out = []
    arg_iter = iter(args)
    for piece in pieces:
        if isinstance(piece, str):
            out.append(piece.replace("{", "{{").replace("}", "}}"))
        elif piece["type"] == "%":
            out.append("%")
        else:
            out.append("{" + _expr_text(next(arg_iter), quote) + _spec_to_format(piece) + "}")

    new_prefix = prefix.replace("u", "") + "f"
    return cst.ensure_type(cst.parse_expression(f"{new_prefix}{quote}{''.join(out)}{quote}"), cst.FormattedString)


def _expr_text(expr: cst.BaseExpression, quote: str) -> str:
    """Source text of an argument, made safe to embed in an f-string (Python 3.11 rules)."""
    if isinstance(expr, (cst.Lambda, cst.NamedExpr, cst.Dict, cst.Set, cst.DictComp, cst.SetComp)):
        expr = expr.with_changes(lpar=[cst.LeftParen()], rpar=[cst.RightParen()])
    text = cst.Module([]).code_for_node(expr)
    if "\\" in text or "\n" in text or "#" in text:
        raise FixNotSupported("Argument contains a backslash, newline or comment (not allowed in f-strings).")
    if quote[0] in text:
        raise FixNotSupported("Argument uses the same quote character as the string.")
    return text


def _spec_to_format(m: re.Match) -> str:
    """Translate one %-specifier into an f-string conversion/format spec."""
    if m["key"]:
        raise FixNotSupported("Mapping keys like %(name)s need a dict argument; not converted automatically.")
    if m["width"] == "*" or m["prec"] == "*":
        raise FixNotSupported("`*` width/precision is not supported.")
    flags, width, prec, kind = m["flags"], m["width"] or "", m["prec"], m["type"]
    if kind in "sra":
        return _text_spec(flags, width, prec, kind)
    if kind in _NUMERIC:
        return _numeric_spec(flags, width, prec, kind)
    raise FixNotSupported(f"%{kind} is not supported by the converter.")


def _text_spec(flags: str, width: str, prec: str | None, kind: str) -> str:
    """%s -> {x}    %r -> {x!r}    %-10s -> {x!s:<10}    %10s -> {x!s:>10}"""
    align = ""
    if "-" in flags:
        align = "<"
    elif width:
        align = ">"   # %-format right-aligns text by default; format() left-aligns it
    spec = align + width + (f".{prec}" if prec else "")
    conversion = "" if kind == "s" and not spec else f"!{kind}"
    return conversion + (f":{spec}" if spec else "")


def _numeric_spec(flags: str, width: str, prec: str | None, kind: str) -> str:
    """%d -> {x:d}    %.2f -> {x:.2f}    %05d -> {x:05d}    %+d -> {x:+d}"""
    # Note: %d becomes {x:d}, which raises for floats where %d truncated.
    # That is deliberate: a loud failure the test suite catches, rather than
    # silently printing "3.7" where "3" used to appear.
    kind = "d" if kind in "iu" else kind
    spec = "<" if "-" in flags else ""
    if "+" in flags:
        spec += "+"
    elif " " in flags:
        spec += " "
    if "#" in flags:
        spec += "#"
    if "0" in flags and "-" not in flags:
        spec += "0"
    return ":" + spec + width + (f".{prec}" if prec is not None else "") + kind
