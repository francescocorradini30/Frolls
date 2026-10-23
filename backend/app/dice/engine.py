"""Dice expression parser and roller.

Grammar (case-insensitive, whitespace ignored):

    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/') unary)*
    unary   := '-' unary | primary
    primary := NUMBER | dice | table | '(' expr ')'
    dice    := [NUMBER] 'd' (NUMBER | '%' | 'F') modifier*
    table   := [NUMBER] 't[' NAME ']'     draws from a rollable table

Modifiers, in any order, as in Roll20:

    !  [cmp]     exploding: roll an extra die on match (default: max face)
    !! [cmp]     compounding: add the extra rolls to the same die
    !p [cmp]     penetrating: like exploding, each extra die gets -1
    r  [cmp]     reroll while matching (default: =1)
    ro [cmp]     reroll once
    k / kh N     keep highest N         kl N    keep lowest N
    d / dl N     drop lowest N          dh N    drop highest N
    cmp          success target, e.g. 5d10>8 counts dice >= 8
    f cmp        failures, subtracted from successes
    s / sa / sd  sort results ascending / descending

    cmp := ('>' | '<' | '=')? NUMBER    ('>' means >=, '<' means <=)

Table items are drawn by weight, with replacement. A table result counts in the math
only when the item name is a number; otherwise the roll shows the names (`text`).

Randomness comes from `secrets.SystemRandom`: rolls happen on the server only.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

MAX_DICE = 1000
MAX_SIDES = 10_000
MAX_EXTRA_ROLLS = 100
MAX_EXPRESSION_LENGTH = 200
MAX_TABLE_DRAWS = 100

_rng = secrets.SystemRandom()


class DiceError(ValueError):
    pass


# --- Tokenizer ---------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(?:(?P<num>\d+)|(?P<table>t\[[^\]]+\])|(?P<op>!!|!p|ro|kh|kl|dh|dl|sa|sd|[-+*/()d%f!rks><=]))",
    re.IGNORECASE,
)


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match or match.end() == pos:
            raise DiceError(f"unexpected character at position {pos}: {text[pos]!r}")
        if match.group("table"):
            # Keeps the case: "t[Name" names the table.
            tokens.append(match.group("table")[:-1].strip())
        else:
            tokens.append((match.group("num") or match.group("op")).lower())
        pos = match.end()
    return tokens


# --- Results -----------------------------------------------------------------


@dataclass
class Die:
    value: int
    kept: bool = True
    exploded: bool = False  # this roll triggered an explosion
    rerolled: bool = False  # discarded because of a reroll
    success: bool = False
    failure: bool = False


@dataclass
class DiceTermResult:
    notation: str
    sides: int | Literal["F"]
    dice: list[Die]
    total: int
    success_mode: bool


@dataclass(frozen=True)
class TableItem:
    name: str
    weight: int = 1
    image: str | None = None


@dataclass
class TableTermResult:
    notation: str
    table: str
    items: list[TableItem]
    total: float
    numeric: bool


@dataclass
class RollResult:
    expression: str
    total: float
    terms: list[DiceTermResult | TableTermResult] = field(default_factory=list)
    breakdown: str = ""
    # Names drawn from tables, shown instead of the total when they aren't numbers.
    text: str | None = None

    @property
    def display_total(self) -> str:
        return _fmt_number(self.total)


# --- Comparisons -------------------------------------------------------------


@dataclass(frozen=True)
class Compare:
    op: Literal[">", "<", "="]
    value: int

    def matches(self, n: int) -> bool:
        if self.op == ">":
            return n >= self.value
        if self.op == "<":
            return n <= self.value
        return n == self.value

    def __str__(self) -> str:
        return f"{self.op}{self.value}"


# --- AST ---------------------------------------------------------------------


@dataclass
class DiceSpec:
    count: int
    sides: int | Literal["F"]
    explode: Literal["", "!", "!!", "!p"] = ""
    explode_on: Compare | None = None
    reroll: Compare | None = None
    reroll_once: bool = False
    keep: tuple[Literal["kh", "kl", "dh", "dl"], int] | None = None
    success: Compare | None = None
    failure: Compare | None = None
    sort: Literal["", "sa", "sd"] = ""

    @property
    def faces(self) -> tuple[int, int]:
        return (-1, 1) if self.sides == "F" else (1, self.sides)


@dataclass
class Number:
    value: float


@dataclass
class BinOp:
    op: str
    left: Node
    right: Node


@dataclass
class Neg:
    operand: Node


@dataclass
class Group:
    inner: Node


@dataclass
class TableSpec:
    count: int
    name: str


Node = Number | DiceSpec | TableSpec | BinOp | Neg | Group


# --- Parser ------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.has_dice = False

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        tok = self.peek()
        if tok is None:
            raise DiceError("unexpected end of expression")
        self.pos += 1
        return tok

    def expect_number(self) -> int:
        tok = self.next()
        if not tok.isdigit():
            raise DiceError(f"expected number, got {tok!r}")
        return int(tok)

    def parse(self) -> Node:
        node = self.expr()
        if self.peek() is not None:
            raise DiceError(f"unexpected token {self.peek()!r}")
        return node

    def expr(self) -> Node:
        node = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()
            node = BinOp(op, node, self.term())
        return node

    def term(self) -> Node:
        node = self.unary()
        while self.peek() in ("*", "/"):
            op = self.next()
            node = BinOp(op, node, self.unary())
        return node

    def unary(self) -> Node:
        if self.peek() == "-":
            self.next()
            return Neg(self.unary())
        return self.primary()

    def primary(self) -> Node:
        tok = self.peek()
        if tok == "(":
            self.next()
            inner = self.expr()
            if self.next() != ")":
                raise DiceError("missing ')'")
            return Group(inner)
        if tok == "d":
            return self.dice(1)
        if tok is not None and tok.startswith("t["):
            return self.table(1)
        if tok is not None and tok.isdigit():
            n = int(self.next())
            if self.peek() == "d":
                return self.dice(n)
            if (nxt := self.peek()) is not None and nxt.startswith("t["):
                return self.table(n)
            return Number(n)
        raise DiceError(f"unexpected token {tok!r}")

    def dice(self, count: int) -> DiceSpec:
        self.next()  # 'd'
        tok = self.next()
        sides: int | Literal["F"]
        if tok == "%":
            sides = 100
        elif tok == "f":
            sides = "F"
        elif tok.isdigit():
            sides = int(tok)
        else:
            raise DiceError(f"invalid die type {tok!r}")

        if count < 1 or count > MAX_DICE:
            raise DiceError(f"dice count must be between 1 and {MAX_DICE}")
        if sides != "F" and (sides < 1 or sides > MAX_SIDES):
            raise DiceError(f"die sides must be between 1 and {MAX_SIDES}")

        self.has_dice = True
        spec = DiceSpec(count=count, sides=sides)
        self.modifiers(spec)
        self.validate(spec)
        return spec

    def table(self, count: int) -> TableSpec:
        name = self.next()[2:].strip()
        if not name:
            raise DiceError("missing table name")
        if count < 1 or count > MAX_TABLE_DRAWS:
            raise DiceError(f"table draws must be between 1 and {MAX_TABLE_DRAWS}")
        self.has_dice = True
        return TableSpec(count, name)

    def compare(self, required: bool) -> Compare | None:
        tok = self.peek()
        if tok in (">", "<", "="):
            self.next()
            return Compare(tok, self.expect_number())  # type: ignore[arg-type]
        if tok is not None and tok.isdigit():
            return Compare("=", self.expect_number())
        if required:
            raise DiceError("expected comparison")
        return None

    def modifiers(self, spec: DiceSpec) -> None:
        while (tok := self.peek()) is not None:
            if tok in ("!", "!!", "!p"):
                self.next()
                spec.explode = tok  # type: ignore[assignment]
                spec.explode_on = self.compare(required=False)
            elif tok in ("r", "ro"):
                self.next()
                spec.reroll = self.compare(required=False) or Compare("=", spec.faces[0])
                spec.reroll_once = tok == "ro"
            elif tok in ("k", "kh", "kl", "dh", "dl") or (tok == "d" and self._next_is_number()):
                self.next()
                kind = {"k": "kh", "d": "dl"}.get(tok, tok)
                spec.keep = (kind, self.expect_number())  # type: ignore[assignment]
            elif tok in (">", "<", "="):
                spec.success = self.compare(required=True)
            elif tok == "f":
                self.next()
                spec.failure = self.compare(required=True)
            elif tok in ("s", "sa", "sd"):
                self.next()
                spec.sort = "sd" if tok == "sd" else "sa"
            else:
                break

    def _next_is_number(self) -> bool:
        nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
        return nxt is not None and nxt.isdigit()

    def validate(self, spec: DiceSpec) -> None:
        low, high = spec.faces
        if spec.explode:
            trigger = spec.explode_on or Compare("=", high)
            if all(trigger.matches(v) for v in range(low, high + 1)):
                raise DiceError("explosion would never stop")
        if spec.reroll and not spec.reroll_once:
            if all(spec.reroll.matches(v) for v in range(low, high + 1)):
                raise DiceError("reroll would never stop")
        if spec.failure and not spec.success:
            raise DiceError("failures need a success target too")


# --- Evaluation --------------------------------------------------------------


def _roll_face(spec: DiceSpec) -> int:
    low, high = spec.faces
    return _rng.randint(low, high)


def _roll_one(spec: DiceSpec) -> list[Die]:
    """Roll a single die with rerolls and explosions; returns all rolls made."""
    out: list[Die] = []

    def roll_with_reroll() -> int:
        value = _roll_face(spec)
        if spec.reroll:
            attempts = 0
            while spec.reroll.matches(value) and attempts < MAX_EXTRA_ROLLS:
                out.append(Die(value, kept=False, rerolled=True))
                value = _roll_face(spec)
                attempts += 1
                if spec.reroll_once:
                    break
        return value

    value = roll_with_reroll()
    if not spec.explode:
        out.append(Die(value))
        return out

    trigger = spec.explode_on or Compare("=", spec.faces[1])
    if spec.explode == "!!":
        total, extra = value, 0
        while trigger.matches(value) and extra < MAX_EXTRA_ROLLS:
            value = _roll_face(spec)
            total += value
            extra += 1
        out.append(Die(total, exploded=extra > 0))
        return out

    penalty = 0
    extra = 0
    while True:
        exploded = trigger.matches(value) and extra < MAX_EXTRA_ROLLS
        out.append(Die(value - penalty, exploded=exploded))
        if not exploded:
            return out
        extra += 1
        if spec.explode == "!p":
            penalty = 1
        value = _roll_face(spec)


def _apply_keep(spec: DiceSpec, dice: list[Die]) -> None:
    if not spec.keep:
        return
    kind, n = spec.keep
    live = [d for d in dice if not d.rerolled]
    ordered = sorted(live, key=lambda d: d.value, reverse=kind in ("kh", "dh"))
    if kind in ("kh", "kl"):
        dropped = ordered[n:]
    else:
        dropped = ordered[:n]
    for d in dropped:
        d.kept = False


def _eval_dice(spec: DiceSpec, notation: str) -> DiceTermResult:
    dice: list[Die] = []
    for _ in range(spec.count):
        dice.extend(_roll_one(spec))
    _apply_keep(spec, dice)

    counted = [d for d in dice if d.kept and not d.rerolled]
    if spec.success:
        for d in counted:
            d.success = spec.success.matches(d.value)
            d.failure = bool(spec.failure and spec.failure.matches(d.value))
        total = sum(d.success for d in counted) - sum(d.failure for d in counted)
    else:
        total = sum(d.value for d in counted)

    if spec.sort:
        dice.sort(key=lambda d: d.value, reverse=spec.sort == "sd")

    return DiceTermResult(
        notation=notation,
        sides=spec.sides,
        dice=dice,
        total=total,
        success_mode=spec.success is not None,
    )


def _notation(spec: DiceSpec) -> str:
    out = f"{spec.count}d{spec.sides}"
    if spec.reroll:
        out += ("ro" if spec.reroll_once else "r") + str(spec.reroll)
    if spec.explode:
        out += spec.explode + (str(spec.explode_on) if spec.explode_on else "")
    if spec.keep:
        out += f"{spec.keep[0]}{spec.keep[1]}"
    if spec.success:
        out += str(spec.success)
    if spec.failure:
        out += f"f{spec.failure}"
    if spec.sort:
        out += spec.sort
    return out


def _fmt_number(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _fmt_dice(term: DiceTermResult) -> str:
    parts = []
    for d in term.dice:
        s = str(d.value)
        if d.rerolled or not d.kept:
            s = f"~~{s}~~"
        elif d.success:
            s = f"**{s}**"
        elif d.failure:
            s = f"_{s}_"
        if d.exploded:
            s += "!"
        parts.append(s)
    return "(" + "+".join(parts) + ")"


def _number_name(name: str) -> float | None:
    try:
        return float(name.strip())
    except ValueError:
        return None


def _draw(spec: TableSpec, items: Sequence[TableItem]) -> TableTermResult:
    weighted = [i for i in items if i.weight > 0]
    if not weighted:
        raise DiceError(f"table {spec.name!r} has no items to draw")
    drawn = _rng.choices(weighted, weights=[i.weight for i in weighted], k=spec.count)
    values = [_number_name(i.name) for i in drawn]
    numeric = all(v is not None for v in values)
    total = sum(v for v in values if v is not None) if numeric else 0
    return TableTermResult(
        notation=f"{spec.count}t[{spec.name}]",
        table=spec.name,
        items=drawn,
        total=total,
        numeric=numeric,
    )


class _Evaluator:
    def __init__(self, tables: Mapping[str, Sequence[TableItem]] | None) -> None:
        self.terms: list[DiceTermResult | TableTermResult] = []
        # Lowercase table name -> items.
        self.tables = tables or {}

    def eval(self, node: Node) -> tuple[float, str]:
        if isinstance(node, Number):
            return node.value, _fmt_number(node.value)
        if isinstance(node, DiceSpec):
            term = _eval_dice(node, _notation(node))
            self.terms.append(term)
            return term.total, _fmt_dice(term)
        if isinstance(node, TableSpec):
            items = self.tables.get(node.name.casefold())
            if items is None:
                raise DiceError(f"no rollable table named {node.name!r}")
            table = _draw(node, items)
            self.terms.append(table)
            return table.total, "(" + ", ".join(i.name for i in table.items) + ")"
        if isinstance(node, Neg):
            v, s = self.eval(node.operand)
            return -v, f"-{s}"
        if isinstance(node, Group):
            v, s = self.eval(node.inner)
            return v, f"({s})"
        left, ls = self.eval(node.left)
        right, rs = self.eval(node.right)
        if node.op == "+":
            value = left + right
        elif node.op == "-":
            value = left - right
        elif node.op == "*":
            value = left * right
        else:
            if right == 0:
                raise DiceError("division by zero")
            value = left / right
        return value, f"{ls}{node.op}{rs}"


# --- Public API --------------------------------------------------------------


def _parse(text: str) -> tuple[Node, bool]:
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise DiceError("expression too long")
    tokens = _tokenize(text)
    if not tokens:
        raise DiceError("empty expression")
    parser = _Parser(tokens)
    return parser.parse(), parser.has_dice


def is_dice_expression(text: str) -> bool:
    """True when the whole text is a valid expression containing at least one die."""
    try:
        _, has_dice = _parse(text)
    except DiceError:
        return False
    return has_dice


def roll(text: str, tables: Mapping[str, Sequence[TableItem]] | None = None) -> RollResult:
    """Roll `text`; `tables` maps lowercase table names to their items."""
    node, _ = _parse(text)
    evaluator = _Evaluator(tables)
    total, breakdown = evaluator.eval(node)
    names = [t for t in evaluator.terms if isinstance(t, TableTermResult) and not t.numeric]
    text_result = None
    if names:
        if not isinstance(node, TableSpec):
            raise DiceError("table items that aren't numbers can't be used in math")
        text_result = ", ".join(i.name for i in names[0].items)
    return RollResult(
        expression=text.strip(),
        total=round(total, 2),
        terms=evaluator.terms,
        breakdown=breakdown,
        text=text_result,
    )
