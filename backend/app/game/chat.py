"""Chat command parsing.

Turns raw chat input into a ChatDraft. Rules:
- If the whole message is a dice expression (`d20`, `2d6+3`), it's a roll.
- `/r` or `/roll EXPR [label]`     roll
- `/gr` or `/gmroll EXPR`          roll visible to GMs and the sender
- `/w NAME msg`, `/w "Full Name" msg`, `/w gm msg`   whisper
- `/em msg` or `/me msg`           emote
- `/ooc msg`                       out of character
- `/desc msg`                      GM narration (GM only)
- `[[EXPR]]` anywhere in a message is rolled inline.
- `1t[name]` draws from a rollable table, anywhere a roll is allowed.
- `&{template:default} {{name=Title}} {{Key=Value}}` shows a card; values may hold
  inline rolls. `&{noerror}` is dropped.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.dice import DiceError, RollResult, TableItem, TableTermResult, is_dice_expression, roll

# Lowercase table name -> items: the tables the sender may roll.
Tables = Mapping[str, Sequence[TableItem]]

MAX_MESSAGE_LENGTH = 4000
# A table draw `t[name]` may sit inside: `[[1t[loot]]]`.
INLINE_RE = re.compile(r"\[\[((?:t\[[^\]]*\]|[^\]])+?)\]\]", re.IGNORECASE)
TEMPLATE_RE = re.compile(r"&\{template:([\w-]+)\}")
FIELD_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


class ChatError(ValueError):
    pass


@dataclass
class ChatDraft:
    kind: str
    content: str = ""
    roll: dict[str, Any] | None = None
    whisper_to: str | None = None  # player name or "gm", resolved by the server
    gm_only: bool = False
    inline: list[dict[str, Any]] = field(default_factory=list)
    # Roll template card: {"name": "default", "title": str, "fields": [[key, value], ...]}
    template: dict[str, Any] | None = None


def roll_to_dict(result: RollResult) -> dict[str, Any]:
    return {
        "expression": result.expression,
        "total": result.total,
        "breakdown": result.breakdown,
        "text": result.text,
        "terms": [
            {
                "notation": t.notation,
                "sides": "T",
                "total": t.total,
                "success_mode": False,
                "dice": [],
                "table": t.table,
                "items": [{"name": i.name, "image": i.image} for i in t.items],
            }
            if isinstance(t, TableTermResult)
            else {
                "notation": t.notation,
                "sides": t.sides,
                "total": t.total,
                "success_mode": t.success_mode,
                "dice": [
                    {
                        "value": d.value,
                        "kept": d.kept,
                        "exploded": d.exploded,
                        "rerolled": d.rerolled,
                        "success": d.success,
                        "failure": d.failure,
                    }
                    for d in t.dice
                ],
            }
            for t in result.terms
        ],
    }


def _roll(expr: str, tables: Tables | None = None) -> dict[str, Any]:
    try:
        return roll_to_dict(roll(expr, tables))
    except DiceError as e:
        raise ChatError(f"Invalid roll: {e}") from e


def _split_roll_label(rest: str) -> tuple[str, str]:
    """`/r 1d20+5 Attacco` -> ("1d20+5", "Attacco"). Longest valid prefix wins."""
    words = rest.split()
    for i in range(len(words), 0, -1):
        expr = " ".join(words[:i])
        if is_dice_expression(expr) or _is_number_expr(expr):
            return expr, " ".join(words[i:])
    return rest, ""


def _is_number_expr(expr: str) -> bool:
    try:
        roll(expr)
    except DiceError:
        return False
    return True


def _inline_rolls(
    text: str, rolls: list[dict[str, Any]] | None = None, tables: Tables | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Roll every [[EXPR]], replaced by a [[#n]] marker; `rolls` collects them."""
    rolls = [] if rolls is None else rolls

    def replace(match: re.Match[str]) -> str:
        rolls.append(_roll(match.group(1), tables))
        return f"[[#{len(rolls) - 1}]]"

    return INLINE_RE.sub(replace, text), rolls


def _body(
    text: str, tables: Tables | None = None
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
    """Content, inline rolls and roll template of a message body."""
    text = text.replace("&{noerror}", "").strip()
    match = TEMPLATE_RE.search(text)
    if match is None:
        content, inline = _inline_rolls(text, tables=tables)
        return content, inline, None
    rolls: list[dict[str, Any]] = []
    title = ""
    fields: list[list[str]] = []
    for raw in FIELD_RE.findall(text):
        key, _, value = raw.partition("=")
        value, _ = _inline_rolls(value.strip(), rolls, tables)
        if key.strip().lower() == "name":
            title = value
        else:
            fields.append([key.strip(), value])
    return "", rolls, {"name": match.group(1), "title": title, "fields": fields}


def _parse_whisper_target(rest: str) -> tuple[str, str]:
    rest = rest.strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            raise ChatError("Unclosed quotes in recipient")
        return rest[1:end], rest[end + 1 :].strip()
    target, _, msg = rest.partition(" ")
    return target, msg.strip()


def parse(text: str, is_gm: bool, tables: Tables | None = None) -> ChatDraft:
    text = text.strip()
    if not text:
        raise ChatError("Empty message")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ChatError("Message too long")

    if not text.startswith("/"):
        if is_dice_expression(text):
            return ChatDraft(kind="roll", roll=_roll(text, tables))
        content, inline, template = _body(text, tables)
        return ChatDraft(kind="text", content=content, inline=inline, template=template)

    command, _, rest = text[1:].partition(" ")
    command = command.lower()
    rest = rest.strip()

    if command in ("r", "roll", "gr", "gmroll"):
        if not rest:
            raise ChatError("Missing roll expression")
        expr, label = _split_roll_label(rest)
        return ChatDraft(
            kind="roll",
            roll=_roll(expr, tables),
            content=label,
            gm_only=command in ("gr", "gmroll"),
        )

    if command in ("w", "whisper"):
        target, msg = _parse_whisper_target(rest)
        if not target or not msg:
            raise ChatError("Usage: /w NAME message")
        if is_dice_expression(msg):
            return ChatDraft(kind="whisper", roll=_roll(msg, tables), whisper_to=target)
        content, inline, template = _body(msg, tables)
        return ChatDraft(
            kind="whisper", content=content, inline=inline, whisper_to=target, template=template
        )

    if command in ("em", "me", "emote"):
        if not rest:
            raise ChatError("Usage: /em action")
        content, inline = _inline_rolls(rest, tables=tables)
        return ChatDraft(kind="emote", content=content, inline=inline)

    if command == "ooc":
        if not rest:
            raise ChatError("Usage: /ooc message")
        content, inline = _inline_rolls(rest, tables=tables)
        return ChatDraft(kind="ooc", content=content, inline=inline)

    if command == "desc":
        if not is_gm:
            raise ChatError("Only the GM can use /desc")
        if not rest:
            raise ChatError("Usage: /desc text")
        content, inline, template = _body(rest, tables)
        return ChatDraft(kind="desc", content=content, inline=inline, template=template)

    raise ChatError(f"Unknown command: /{command}")
