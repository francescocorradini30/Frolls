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
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.dice import DiceError, RollResult, is_dice_expression, roll

MAX_MESSAGE_LENGTH = 4000
INLINE_RE = re.compile(r"\[\[(.+?)\]\]")


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


def roll_to_dict(result: RollResult) -> dict[str, Any]:
    return {
        "expression": result.expression,
        "total": result.total,
        "breakdown": result.breakdown,
        "terms": [
            {
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


def _roll(expr: str) -> dict[str, Any]:
    try:
        return roll_to_dict(roll(expr))
    except DiceError as e:
        raise ChatError(f"Tiro non valido: {e}") from e


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


def _inline_rolls(text: str) -> tuple[str, list[dict[str, Any]]]:
    rolls: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        rolls.append(_roll(match.group(1)))
        return f"[[#{len(rolls) - 1}]]"

    return INLINE_RE.sub(replace, text), rolls


def _parse_whisper_target(rest: str) -> tuple[str, str]:
    rest = rest.strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end == -1:
            raise ChatError("Virgolette non chiuse nel destinatario")
        return rest[1:end], rest[end + 1 :].strip()
    target, _, msg = rest.partition(" ")
    return target, msg.strip()


def parse(text: str, is_gm: bool) -> ChatDraft:
    text = text.strip()
    if not text:
        raise ChatError("Messaggio vuoto")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ChatError("Messaggio troppo lungo")

    if not text.startswith("/"):
        if is_dice_expression(text):
            return ChatDraft(kind="roll", roll=_roll(text))
        content, inline = _inline_rolls(text)
        return ChatDraft(kind="text", content=content, inline=inline)

    command, _, rest = text[1:].partition(" ")
    command = command.lower()
    rest = rest.strip()

    if command in ("r", "roll", "gr", "gmroll"):
        if not rest:
            raise ChatError("Manca l'espressione del tiro")
        expr, label = _split_roll_label(rest)
        return ChatDraft(
            kind="roll", roll=_roll(expr), content=label, gm_only=command in ("gr", "gmroll")
        )

    if command in ("w", "whisper"):
        target, msg = _parse_whisper_target(rest)
        if not target or not msg:
            raise ChatError("Uso: /w NOME messaggio")
        if is_dice_expression(msg):
            return ChatDraft(kind="whisper", roll=_roll(msg), whisper_to=target)
        content, inline = _inline_rolls(msg)
        return ChatDraft(kind="whisper", content=content, inline=inline, whisper_to=target)

    if command in ("em", "me", "emote"):
        if not rest:
            raise ChatError("Uso: /em azione")
        content, inline = _inline_rolls(rest)
        return ChatDraft(kind="emote", content=content, inline=inline)

    if command == "ooc":
        if not rest:
            raise ChatError("Uso: /ooc messaggio")
        content, inline = _inline_rolls(rest)
        return ChatDraft(kind="ooc", content=content, inline=inline)

    if command == "desc":
        if not is_gm:
            raise ChatError("Solo il GM può usare /desc")
        if not rest:
            raise ChatError("Uso: /desc testo")
        content, inline = _inline_rolls(rest)
        return ChatDraft(kind="desc", content=content, inline=inline)

    raise ChatError(f"Comando sconosciuto: /{command}")
