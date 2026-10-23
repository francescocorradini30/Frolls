"""Macro expansion: what happens to a chat message before it is parsed and rolled.

Order of operations (spec §12.12):
1. Abilities `%{Character|Ability}` (also `%{selected|…}`, `%{target|…}`) and macros
   `#Name`, recursively. Inside an ability, a bare `@{attr}` refers to its character.
2. Attributes `@{Character|attr}`, `@{selected|attr}`, `@{target|attr}`, `…|max`.
3. Roll queries `?{Prompt|default}` or `?{Prompt|Label,value|Label,value}`: all the
   questions of one message are answered at once; the same prompt is asked only once.
Chat buttons `[Label](~Character|Ability)` and `[Label](#Macro)` are left as they are:
they run when someone clicks them.

The data comes from a `Resolver`, so this module knows nothing about the game state.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

MAX_DEPTH = 10
MAX_ANSWER_LENGTH = 500

# `!` buttons run a game action (roll damage, apply damage…), see the client.
BUTTON_RE = re.compile(r"\[([^\]\n]+)\]\(([~#!][^)\n]+)\)")
ABILITY_RE = re.compile(r"%\{([^{}|]+)\|([^{}]+)\}")
# `#Name` not glued to a word: `C#`, `[[#0]]` and colours like `&#35;` stay text.
MACRO_RE = re.compile(r"(?<![\w#&\[])#([A-Za-z0-9_\-]+)")
ATTR_RE = re.compile(r"@\{([^{}]+)\}")
QUERY_RE = re.compile(r"\?\{([^{}]*)\}")
# Internal reference to a character by id, used for bare attributes inside abilities.
BOUND = "\x01"


class MacroError(ValueError):
    pass


class NeedTarget(Exception):  # noqa: N818 - a request, not an error
    """The message uses `target`: the sender must click a token first."""


class Resolver(Protocol):
    def macro(self, name: str) -> str | None:
        """Action of the sender's macro, None if there is no such macro."""

    def ability(self, ref: str, name: str) -> tuple[str, str]:
        """(action, character id) of an ability. `ref`: selected, target, a name or an id."""

    def attribute(self, ref: str, name: str, use_max: bool) -> str:
        """Value of an attribute (or token field for selected/target)."""


@dataclass
class Query:
    prompt: str
    default: str = ""
    # [label, value]; two or more = a drop-down.
    options: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {"prompt": self.prompt, "default": self.default, "options": self.options}


@dataclass
class Expanded:
    text: str
    # Questions still to answer: the client shows them and sends the message again.
    queries: list[Query] = field(default_factory=list)


def expand(text: str, resolver: Resolver, answers: list[str] | None = None) -> Expanded:
    """Expand macros, abilities, attributes and queries. Raises NeedTarget or MacroError."""
    buttons: list[str] = []

    def keep_button(m: re.Match[str]) -> str:
        buttons.append(m.group(0))
        return f"\x00{len(buttons) - 1}\x00"

    text = BUTTON_RE.sub(keep_button, text)
    text = _calls(text, resolver, 0)
    text = _attributes(text, resolver)

    queries = _queries(text)
    if queries:
        if answers is None:
            return Expanded(text, queries)
        if len(answers) != len(queries):
            raise MacroError("the questions changed: send the message again")
        by_prompt = {q.prompt: a[:MAX_ANSWER_LENGTH] for q, a in zip(queries, answers, strict=True)}
        text = QUERY_RE.sub(lambda m: by_prompt[_parse_query(m.group(1)).prompt], text)
    if "?{" in text:
        raise MacroError("a query inside another query is not supported")

    return Expanded(re.sub(r"\x00(\d+)\x00", lambda m: buttons[int(m.group(1))], text))


def _calls(text: str, resolver: Resolver, depth: int) -> str:
    """Abilities and macros, recursively."""
    if depth > MAX_DEPTH:
        raise MacroError("macros and abilities call each other too many times")

    def ability(m: re.Match[str]) -> str:
        action, character_id = resolver.ability(m.group(1).strip(), m.group(2).strip())
        # A bare @{attr} in an ability belongs to its character.
        action = ATTR_RE.sub(
            lambda a: (
                a.group(0) if "|" in a.group(1) else f"@{{{BOUND}{character_id}|{a.group(1)}}}"
            ),
            action,
        )
        return _calls(action, resolver, depth + 1)

    def macro(m: re.Match[str]) -> str:
        action = resolver.macro(m.group(1))
        return m.group(0) if action is None else _calls(action, resolver, depth + 1)

    return MACRO_RE.sub(macro, ABILITY_RE.sub(ability, text))


def _attributes(text: str, resolver: Resolver) -> str:
    """Attribute calls; a value may contain other calls, up to MAX_DEPTH levels."""

    def attribute(m: re.Match[str]) -> str:
        parts = [p.strip() for p in m.group(1).split("|")]
        use_max = len(parts) == 3 and parts[2].lower() == "max"
        if len(parts) == 1:
            raise MacroError(f"@{{{parts[0]}}} needs a character: write @{{selected|{parts[0]}}}")
        if len(parts) > 3 or (len(parts) == 3 and not use_max):
            raise MacroError(f"invalid attribute call @{{{m.group(1)}}}")
        return resolver.attribute(parts[0], parts[1], use_max)

    for _ in range(MAX_DEPTH):
        expanded = ATTR_RE.sub(attribute, text)
        if expanded == text:
            return text
        text = expanded
    raise MacroError("attributes refer to each other too many times")


def _parse_query(inner: str) -> Query:
    prompt, *rest = inner.split("|")
    prompt = prompt.strip() or "Value"
    if len(rest) <= 1:
        return Query(prompt, rest[0].strip() if rest else "")
    options = []
    for option in rest:
        label, sep, value = option.partition(",")
        options.append((label.strip(), value.strip() if sep else label.strip()))
    return Query(prompt, options[0][1], options)


def _queries(text: str) -> list[Query]:
    """Distinct queries in order of appearance (by prompt)."""
    seen: dict[str, Query] = {}
    for m in QUERY_RE.finditer(text):
        q = _parse_query(m.group(1))
        seen.setdefault(q.prompt, q)
    return list(seen.values())
