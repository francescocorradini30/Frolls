"""Effects with a duration: spells, conditions, features (SRD 5.2).

An effect lives on the token it affects (`props.effects`). It can change rolls (bonus dice,
advantage, disadvantage, AC), give a condition, end at the start or end of a given
creature's turn after some rounds, allow a repeated saving throw at the end of the
target's turns, and depend on someone's concentration.
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

RollKind = Literal["attack", "check", "save"]
Ability = Literal["str", "dex", "con", "int", "wis", "cha"]


class Ending(BaseModel):
    """Ends at the start or end of `of`'s turn, after `rounds` such turns."""

    when: Literal["start", "end"] = "start"
    of: Annotated[str, Field(max_length=36)]
    rounds: Annotated[int, Field(ge=1, le=1000)] = 10


class RepeatSave(BaseModel):
    """The target repeats this saving throw at the end of each of its turns; success ends it."""

    ability: Ability
    dc: Annotated[int, Field(ge=1, le=40)]


class Effect(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=36)] = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    name: Annotated[str, Field(min_length=1, max_length=60)]
    # Token that concentrates on it: if its concentration ends, so does the effect.
    concentration_of: Annotated[str, Field(max_length=36)] | None = None
    ending: Ending | None = None
    # Shown to players: "1 minute", "until the end of your next turn"…
    duration: Annotated[str, Field(max_length=60)] = ""
    # Extra dice on the target's own rolls (Bless "1d4", Bane "-1d4").
    dice: dict[RollKind, Annotated[str, Field(max_length=10)]] = {}
    # Flat bonus to the target's rolls.
    bonus: dict[RollKind, Annotated[int, Field(ge=-20, le=20)]] = {}
    ac: Annotated[int, Field(ge=-10, le=10)] = 0
    advantage: list[RollKind] = []
    disadvantage: list[RollKind] = []
    # Advantage / disadvantage only on Dexterity saves (Haste, Dodge).
    dex_save_advantage: bool = False
    # Attack rolls against the target.
    attacked_with: Literal["advantage", "disadvantage"] | None = None
    # A condition it gives (status icon + its rules).
    condition: Annotated[str, Field(max_length=20)] | None = None
    repeat_save: RepeatSave | None = None


# Preset effects of common SRD 5.2 spells and actions. `rounds` = 1 minute = 10 rounds.
PRESETS: dict[str, dict[str, Any]] = {
    "bless": {"name": "Bless", "duration": "1 minute", "conc": True, "rounds": 10,
              "dice": {"attack": "1d4", "save": "1d4"}},
    "bane": {"name": "Bane", "duration": "1 minute", "conc": True, "rounds": 10,
             "dice": {"attack": "-1d4", "save": "-1d4"}},
    "guidance": {"name": "Guidance", "duration": "1 minute", "conc": True, "rounds": 10,
                 "dice": {"check": "1d4"}},
    "resistance": {"name": "Resistance", "duration": "1 minute", "conc": True, "rounds": 10,
                   "dice": {"save": "1d4"}},
    "shield_of_faith": {"name": "Shield of Faith", "duration": "10 minutes", "conc": True,
                        "rounds": 100, "ac": 2},
    "haste": {"name": "Haste", "duration": "1 minute", "conc": True, "rounds": 10, "ac": 2,
              "dex_save_advantage": True},
    "slow": {"name": "Slow", "duration": "1 minute", "conc": True, "rounds": 10, "ac": -2,
             "bonus": {"save": -2}, "repeat_save": "wis"},
    "hold_person": {"name": "Hold Person", "duration": "1 minute", "conc": True, "rounds": 10,
                    "condition": "paralyzed", "repeat_save": "wis"},
    "faerie_fire": {"name": "Faerie Fire", "duration": "1 minute", "conc": True, "rounds": 10,
                    "attacked_with": "advantage"},
    "invisibility": {"name": "Invisibility", "duration": "1 hour", "conc": True, "rounds": 600,
                     "condition": "invisible"},
    "shield": {"name": "Shield", "duration": "until the start of your next turn", "rounds": 1,
               "when": "start", "ac": 5},
    "dodge": {"name": "Dodge", "duration": "until the start of your next turn", "rounds": 1,
              "when": "start", "attacked_with": "disadvantage", "dex_save_advantage": True},
    "help": {"name": "Helped", "duration": "until the start of the helper's next turn",
             "rounds": 1, "when": "start", "advantage": ["attack", "check"]},
    "frightened": {"name": "Frightened", "duration": "1 minute", "rounds": 10,
                   "condition": "frightened", "repeat_save": "wis"},
}  # fmt: skip


def from_preset(key: str, source: str | None, concentrating: bool, dc: int | None) -> Effect:
    """An effect from a preset, cast by `source` (token id)."""
    p = PRESETS[key]
    ending = Ending(when=p.get("when", "start"), of=source, rounds=p["rounds"]) if source else None
    repeat = RepeatSave(ability=p["repeat_save"], dc=dc) if p.get("repeat_save") and dc else None
    return Effect(
        name=p["name"],
        duration=p["duration"],
        concentration_of=source if p.get("conc") and concentrating else None,
        ending=ending,
        dice=p.get("dice", {}),
        bonus=p.get("bonus", {}),
        ac=p.get("ac", 0),
        advantage=p.get("advantage", []),
        disadvantage=p.get("disadvantage", []),
        dex_save_advantage=p.get("dex_save_advantage", False),
        attacked_with=p.get("attacked_with"),
        condition=p.get("condition"),
        repeat_save=repeat,
    )


def load(raw: list[dict[str, Any]] | None) -> list[Effect]:
    return [Effect.model_validate(e) for e in raw or []]


def dump(effects: list[Effect]) -> list[dict[str, Any]] | None:
    return [e.model_dump() for e in effects] or None


def roll_changes(
    effects: list[Effect], kind: RollKind, ability: str | None
) -> tuple[list[str], list[str], str, int]:
    """(advantage reasons, disadvantage reasons, extra dice, flat bonus) for one roll."""
    adv: list[str] = []
    dis: list[str] = []
    dice = ""
    bonus = 0
    for e in effects:
        if kind in e.advantage or (kind == "save" and ability == "dex" and e.dex_save_advantage):
            adv.append(f"advantage: {e.name}")
        if kind in e.disadvantage:
            dis.append(f"disadvantage: {e.name}")
        if kind in e.dice:
            d = e.dice[kind]
            dice += d if d.startswith("-") else f"+{d}"
        bonus += e.bonus.get(kind, 0)
    return adv, dis, dice, bonus


def ac_bonus(effects: list[Effect]) -> int:
    return sum(e.ac for e in effects)


def attacked_with(effects: list[Effect]) -> tuple[list[str], list[str]]:
    """Advantage / disadvantage reasons for attacks against a creature with these effects."""
    adv = [f"advantage: target has {e.name}" for e in effects if e.attacked_with == "advantage"]
    dis = [
        f"disadvantage: target has {e.name}" for e in effects if e.attacked_with == "disadvantage"
    ]
    return adv, dis


def conditions(effects: list[Effect]) -> set[str]:
    return {e.condition for e in effects if e.condition}


def tick(effects: list[Effect], token_id: str, when: str) -> tuple[list[Effect], list[Effect]]:
    """A turn of `token_id` starts or ends: (effects that stay, effects that end now)."""
    kept: list[Effect] = []
    ended: list[Effect] = []
    for e in effects:
        if e.ending and e.ending.of == token_id and e.ending.when == when:
            e = e.model_copy(
                update={"ending": e.ending.model_copy(update={"rounds": e.ending.rounds - 1})}
            )
            if e.ending and e.ending.rounds <= 0:
                ended.append(e)
                continue
        kept.append(e)
    return kept, ended


def concentration_dc(damage: int) -> int:
    """Constitution save to keep concentrating: DC 10 or half the damage, the higher, at most 30."""
    return min(30, max(10, damage // 2))


# Conditions that end concentration (Incapacitated, and those that include it).
BREAKS_CONCENTRATION = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious", "dead"}
