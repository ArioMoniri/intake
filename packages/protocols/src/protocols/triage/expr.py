"""The red-flag ``when`` grammar and its Kleene evaluation (INT-080).

Every accepted construct is one the blueprint itself writes down; anything
else is refused at load with :class:`WhenGrammarError`, never guessed:

- ``&&``, ``||``, ``>=``, ``==``, parentheses and dotted slot atoms —
  files/03 §6 (``when: "hpi.single_hot_swollen_joint && (vitals.temp_c >=
  38 || symptoms.fever)"``); the top-level ``||`` split with quote/paren
  respect already backs files/12 §4 layer 2 in :mod:`protocols.validator`.
- ``!``, ``in {...}``, string and boolean literals — the rule exemplars in
  files/protocols/base.life_threat.yaml (``!(chest_pain.character in
  {"baskı", ...})``); ``set`` is a GuardExpr type (files/13 §9.5).
- The remaining comparison operators (``!=``, ``<``, ``<=``, ``>``) — the
  files/03 §8 "CEL-like sandboxed expression engine", whose comparison set
  is exactly these six, and files/12 §4 layer 3, which derives its canary
  corpus from "every numeric literal ... plus l±ε" at "every comparison
  boundary the authors actually wrote" — both directions of every bound.
- Numbers are :class:`~decimal.Decimal`, never float — files/13 §9.5:
  "no floats anywhere ... exact comparison, because floats are how two
  machines disagree about the same session".
- Three-valued logic — files/12 §1.1 / files/13 §9.5 Kleene: ``F ∧ U = F``,
  ``T ∨ U = T``, everything else touching ``U`` is ``U``; a type-mismatched
  comparison is likewise ``Unknown``, never ``False``, so a data defect can
  suppress a firing only into review, not into false reassurance.

Deliberately absent, refused at parse: function calls, arithmetic,
assignment, signed literals, bare literals as predicates, empty sets —
none appears in any blueprint red-flag rule (GuardExpr's function whitelist
belongs to step gates, files/13 §9.5, not to this grammar).
"""

from __future__ import annotations

import enum
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "Lookup",
    "Truth",
    "WhenGrammarError",
    "WhenNode",
    "evaluate_node",
    "parse_when",
    "referenced_slots",
    "truth_and",
    "truth_not",
    "truth_or",
]


class WhenGrammarError(ValueError):
    """A ``when`` construct the blueprint does not define — refused at load."""


class Truth(enum.Enum):
    """Kleene three-valued truth (files/12 §1.1; files/13 §9.5)."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


def truth_not(value: Truth) -> Truth:
    if value is Truth.TRUE:
        return Truth.FALSE
    if value is Truth.FALSE:
        return Truth.TRUE
    return Truth.UNKNOWN


def truth_and(values: Iterable[Truth]) -> Truth:
    result = Truth.TRUE
    for value in values:
        if value is Truth.FALSE:
            return Truth.FALSE
        if value is Truth.UNKNOWN:
            result = Truth.UNKNOWN
    return result


def truth_or(values: Iterable[Truth]) -> Truth:
    result = Truth.FALSE
    for value in values:
        if value is Truth.TRUE:
            return Truth.TRUE
        if value is Truth.UNKNOWN:
            result = Truth.UNKNOWN
    return result


# ---------------------------------------------------------------------------
# AST — small, closed, frozen.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    """A dotted slot reference (files/03 §6 atoms)."""

    name: str


@dataclass(frozen=True)
class Lit:
    """A literal: bool, Decimal or str (files/13 §9.5 scalar types)."""

    value: bool | Decimal | str


Operand = Ref | Lit


@dataclass(frozen=True)
class BoolRef:
    """A bare boolean slot atom (files/03 §6 ``symptoms.fever``)."""

    ref: Ref


@dataclass(frozen=True)
class Compare:
    """A comparison (files/03 §6; files/03 §8 CEL-like operator set)."""

    left: Operand
    op: str
    right: Operand


@dataclass(frozen=True)
class InSet:
    """Set membership (base.life_threat exemplars; files/13 §9.5 ``set``)."""

    operand: Operand
    elements: tuple[Lit, ...]


@dataclass(frozen=True)
class Not:
    item: WhenNode


@dataclass(frozen=True)
class And:
    items: tuple[WhenNode, ...]


@dataclass(frozen=True)
class Or:
    items: tuple[WhenNode, ...]


WhenNode = BoolRef | Compare | InSet | Not | And | Or


# ---------------------------------------------------------------------------
# Tokenizer.
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<ident>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'[^'\\]*'|"[^"\\]*")
  | (?P<op>\|\||&&|==|!=|<=|>=|[!<>(){},])
    """,
    re.VERBOSE,
)

_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    pos: int


def _scan(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise WhenGrammarError(
                f"character {text[pos]!r} at position {pos} is not part of the "
                "when grammar the blueprint defines (files/03 §6; files/13 §9.5) "
                "— refused, never guessed"
            )
        kind = str(match.lastgroup)
        if kind != "ws":
            tokens.append(_Token(kind=kind, text=match.group(), pos=pos))
        pos = match.end()
    return tokens


class _Parser:
    """Recursive descent over the closed grammar above."""

    def __init__(self, text: str) -> None:
        self._tokens = _scan(text)
        self._index = 0

    def parse(self) -> WhenNode:
        node = self._or()
        if self._index != len(self._tokens):
            raise WhenGrammarError(
                f"unexpected {self._tokens[self._index].text!r} after a complete "
                "predicate — trailing constructs are refused"
            )
        return node

    # -- token helpers ------------------------------------------------------

    def _peek(self) -> _Token | None:
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _take(self) -> _Token:
        token = self._peek()
        if token is None:
            raise WhenGrammarError("the predicate ends where the grammar expects more")
        self._index += 1
        return token

    def _take_op(self, text: str) -> None:
        token = self._take()
        if token.kind != "op" or token.text != text:
            raise WhenGrammarError(f"expected {text!r}, found {token.text!r}")

    def _at_op(self, text: str) -> bool:
        token = self._peek()
        return token is not None and token.kind == "op" and token.text == text

    # -- grammar ------------------------------------------------------------

    def _or(self) -> WhenNode:
        items = [self._and()]
        while self._at_op("||"):
            self._take()
            items.append(self._and())
        if len(items) == 1:
            return items[0]
        return Or(items=tuple(items))

    def _and(self) -> WhenNode:
        items = [self._unary()]
        while self._at_op("&&"):
            self._take()
            items.append(self._unary())
        if len(items) == 1:
            return items[0]
        return And(items=tuple(items))

    def _unary(self) -> WhenNode:
        if self._at_op("!"):
            self._take()
            return Not(item=self._unary())
        if self._at_op("("):
            self._take()
            node = self._or()
            self._take_op(")")
            return node
        return self._predicate()

    def _predicate(self) -> WhenNode:
        left = self._operand()
        token = self._peek()
        if token is not None and token.kind == "op" and token.text in _COMPARISONS:
            self._take()
            return Compare(left=left, op=token.text, right=self._operand())
        if token is not None and token.kind == "ident" and token.text == "in":
            self._take()
            return InSet(operand=left, elements=self._set_literal())
        if isinstance(left, Ref):
            return BoolRef(ref=left)
        raise WhenGrammarError(
            "a bare literal is not a predicate — the blueprint's atoms are "
            "slot references (files/03 §6)"
        )

    def _operand(self) -> Operand:
        token = self._take()
        if token.kind == "ident":
            if token.text == "true":
                return Lit(value=True)
            if token.text == "false":
                return Lit(value=False)
            if token.text == "in":
                raise WhenGrammarError("'in' needs a left-hand operand")
            reference = Ref(name=token.text)
            if self._at_op("("):
                raise WhenGrammarError(
                    f"function call {token.text!r}(...) — the red-flag when "
                    "grammar has no functions (files/13 §9.5 whitelists belong "
                    "to step gates, not rules); refused, never guessed"
                )
            return reference
        if token.kind == "number":
            return Lit(value=Decimal(token.text))
        if token.kind == "string":
            return Lit(value=token.text[1:-1])
        raise WhenGrammarError(f"expected a slot reference or literal, found {token.text!r}")

    def _set_literal(self) -> tuple[Lit, ...]:
        self._take_op("{")
        if self._at_op("}"):
            raise WhenGrammarError("an empty set literal is not defined by the blueprint")
        elements = [self._set_element()]
        while self._at_op(","):
            self._take()
            elements.append(self._set_element())
        self._take_op("}")
        return tuple(elements)

    def _set_element(self) -> Lit:
        element = self._operand()
        if isinstance(element, Ref):
            raise WhenGrammarError(
                "a set literal may contain only literals "
                "(files/protocols/base.life_threat.yaml exemplars)"
            )
        return element


def parse_when(text: str) -> WhenNode:
    """Parse a rule's ``when`` predicate, refusing undefined constructs."""
    return _Parser(text).parse()


def referenced_slots(node: WhenNode) -> frozenset[str]:
    """Every dotted slot reference the predicate reads."""
    if isinstance(node, BoolRef):
        return frozenset({node.ref.name})
    if isinstance(node, Compare):
        return _operand_refs(node.left) | _operand_refs(node.right)
    if isinstance(node, InSet):
        return _operand_refs(node.operand)
    if isinstance(node, Not):
        return referenced_slots(node.item)
    refs: frozenset[str] = frozenset()
    for item in node.items:
        refs |= referenced_slots(item)
    return refs


def _operand_refs(operand: Operand) -> frozenset[str]:
    if isinstance(operand, Ref):
        return frozenset({operand.name})
    return frozenset()


# ---------------------------------------------------------------------------
# Evaluation. The lookup returns a canonical scalar (bool | Decimal | str)
# or None for Unknown; canonicalisation of JsonValue lives in context.py.
# ---------------------------------------------------------------------------

Lookup = Callable[[str], bool | Decimal | str | None]


def evaluate_node(node: WhenNode, lookup: Lookup) -> Truth:
    """Kleene evaluation of a parsed predicate (files/12 §1.1)."""
    if isinstance(node, Or):
        return truth_or(evaluate_node(item, lookup) for item in node.items)
    if isinstance(node, And):
        return truth_and(evaluate_node(item, lookup) for item in node.items)
    if isinstance(node, Not):
        return truth_not(evaluate_node(node.item, lookup))
    if isinstance(node, BoolRef):
        value = lookup(node.ref.name)
        if isinstance(value, bool):
            return Truth.TRUE if value else Truth.FALSE
        return Truth.UNKNOWN  # unknown slot or non-boolean atom: never False
    if isinstance(node, Compare):
        left = _operand_value(node.left, lookup)
        right = _operand_value(node.right, lookup)
        return _compare(left, node.op, right)
    left = _operand_value(node.operand, lookup)
    return truth_or(_equal(left, element.value) for element in node.elements)


def _operand_value(operand: Operand, lookup: Lookup) -> bool | Decimal | str | None:
    if isinstance(operand, Lit):
        return operand.value
    return lookup(operand.name)


def _equal(left: bool | Decimal | str | None, right: bool | Decimal | str | None) -> Truth:
    """Typed equality; a cross-type comparison is Unknown, never False."""
    if left is None or right is None:
        return Truth.UNKNOWN
    if isinstance(left, bool) and isinstance(right, bool):
        return Truth.TRUE if left is right else Truth.FALSE
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        return Truth.TRUE if left == right else Truth.FALSE
    if isinstance(left, str) and isinstance(right, str):
        return Truth.TRUE if left == right else Truth.FALSE
    return Truth.UNKNOWN


def _compare(
    left: bool | Decimal | str | None, op: str, right: bool | Decimal | str | None
) -> Truth:
    if op == "==":
        return _equal(left, right)
    if op == "!=":
        return truth_not(_equal(left, right))
    # Ordered comparison is numeric-only: the blueprint orders quantities
    # (files/03 §6 temp_c >= 38), never strings or booleans.
    if not isinstance(left, Decimal) or not isinstance(right, Decimal):
        return Truth.UNKNOWN
    if op == "<":
        return Truth.TRUE if left < right else Truth.FALSE
    if op == "<=":
        return Truth.TRUE if left <= right else Truth.FALSE
    if op == ">":
        return Truth.TRUE if left > right else Truth.FALSE
    return Truth.TRUE if left >= right else Truth.FALSE
