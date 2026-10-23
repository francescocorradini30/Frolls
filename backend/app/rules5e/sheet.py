"""5e character sheet: stored base values (validated here) and derived values.

Only base values are stored. Modifiers, proficiency, save and skill bonuses, spell DC and
attack bonuses are always computed by `derive`, so they can never go out of sync.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.rules5e.data import (
    ABILITIES,
    CR_XP,
    SKILLS,
    modifier,
    proficiency_for_cr,
    proficiency_for_level,
)

Ability = Literal["str", "dex", "con", "int", "wis", "cha"]
Score = Annotated[int, Field(ge=1, le=30)]
Text = Annotated[str, Field(max_length=120)]
Formula = Annotated[str, Field(max_length=80)]
Small = Annotated[int, Field(ge=-99, le=99)]


class Abilities(BaseModel):
    str: Score = 10
    dex: Score = 10
    con: Score = 10
    int: Score = 10
    wis: Score = 10
    cha: Score = 10


class HitPoints(BaseModel):
    current: Annotated[int, Field(ge=0, le=9999)] = 10
    max: Annotated[int, Field(ge=0, le=9999)] = 10
    temp: Annotated[int, Field(ge=0, le=9999)] = 0


class HitDice(BaseModel):
    die: Literal[6, 8, 10, 12] = 8
    spent: Annotated[int, Field(ge=0, le=20)] = 0


class DeathSaves(BaseModel):
    successes: Annotated[int, Field(ge=0, le=3)] = 0
    failures: Annotated[int, Field(ge=0, le=3)] = 0


Feet = Annotated[int, Field(ge=0, le=5000)]


class DamagePart(BaseModel):
    """An extra damage part of an attack ("plus 4 (1d8) Acid damage")."""

    formula: Formula
    type: Text = ""


class Area(BaseModel):
    shape: Literal["sphere", "cylinder", "emanation", "cone", "cube", "line"]
    size_ft: Annotated[int, Field(ge=5, le=500)]


class Uses(BaseModel):
    max: Annotated[int, Field(ge=1, le=9)] = 1
    reset: Literal["day", "short", "long"] = "day"


class MultiattackStep(BaseModel):
    attack_id: Annotated[str, Field(min_length=1, max_length=36)]
    count: Annotated[int, Field(ge=1, le=6)] = 1


RANGE_RE = re.compile(r"range\s+(\d+)(?:\s*/\s*(\d+))?")
REACH_RE = re.compile(r"reach\s+(\d+)")


class Attack(BaseModel):
    """A weapon attack, an NPC action, or an effect that forces a saving throw."""

    id: Annotated[str, Field(min_length=1, max_length=36)]
    name: Text = "Attack"
    # Attack roll, or a saving throw the target makes (`save`).
    kind: Literal["attack", "save"] = "attack"
    ability: Ability | Literal["spell", "none"] = "str"
    proficient: bool = True
    # Extra bonus to hit (magic weapons…).
    bonus: Small = 0
    # Fixed bonus to hit, as written in a monster stat block; overrides the computed one.
    to_hit: Small | None = None
    damage: Formula = "1d6"
    damage_type: Text = "slashing"
    # Add the ability modifier to the damage.
    add_modifier: bool = True
    save: Ability | None = None
    # Fixed save DC from a stat block; otherwise 8 + proficiency + modifier.
    dc: Annotated[int, Field(ge=1, le=40)] | None = None
    half_on_save: bool = True
    # Free text, as written in a stat block ("reach 10 ft · range 80/320 ft").
    range: Text = ""
    notes: Annotated[str, Field(max_length=2000)] = ""
    # Numbers the automation uses (feet). Melee: reach; ranged: normal / long range.
    reach: Feet | None = None
    range_normal: Feet | None = None
    range_long: Feet | None = None
    extra_damage: Annotated[list[DamagePart], Field(max_length=4)] = []
    # What it costs on the turn; legendary actions cost 1-3 uses.
    cost: Literal["action", "bonus", "reaction", "legendary"] = "action"
    legendary_cost: Annotated[int, Field(ge=1, le=3)] = 1
    # Recharge 5-6 = 5: rolled on a d6 at the start of the creature's turn.
    recharge: Annotated[int, Field(ge=2, le=6)] | None = None
    uses: Uses | None = None
    area: Area | None = None
    # Weapon mastery property (stored for later automation).
    mastery: Annotated[str, Field(max_length=20)] | None = None

    @model_validator(mode="before")
    @classmethod
    def _numbers_from_range_text(cls, data: Any) -> Any:
        """Older sheets only have the range text: read reach and range from it."""
        if (
            isinstance(data, dict)
            and data.get("range")
            and not any(data.get(k) is not None for k in ("reach", "range_normal", "range_long"))
        ):
            text = str(data["range"]).lower()
            data = dict(data)
            if m := REACH_RE.search(text):
                data["reach"] = int(m.group(1))
            if m := RANGE_RE.search(text):
                data["range_normal"] = int(m.group(1))
                data["range_long"] = int(m.group(2)) if m.group(2) else None
        return data

    @property
    def melee(self) -> bool:
        return self.range_normal is None or self.reach is not None


class Slot(BaseModel):
    max: Annotated[int, Field(ge=0, le=9)] = 0
    used: Annotated[int, Field(ge=0, le=9)] = 0


class Spell(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=36)]
    name: Text = "Spell"
    level: Annotated[int, Field(ge=0, le=9)] = 0
    prepared: bool = True
    concentration: bool = False
    ritual: bool = False
    # How it hits: a spell attack roll, a saving throw, or neither.
    attack: bool = False
    save: Ability | None = None
    half_on_save: bool = True
    damage: Formula = ""
    damage_type: Text = ""
    # Damage dice added per slot level above the spell's level, e.g. "1d6".
    upcast: Formula = ""
    duration: Text = ""
    description: Annotated[str, Field(max_length=4000)] = ""
    # Effect it puts on its targets (a preset of app/rules5e/effects.py), on a failed save if
    # it has one.
    effect: Annotated[str, Field(max_length=30)] | None = None
    # The dice heal (Cure Wounds) or give temporary hit points (False Life) instead of damage.
    heal: Literal["", "healing", "temp"] = ""
    # Add the spellcasting modifier to the dice ("2d8 plus your spellcasting ability modifier").
    add_modifier: bool = False
    casting_time: Literal["action", "bonus", "reaction", "long"] = "action"
    # Feet; 0 = self, 5 = touch.
    range_ft: Feet | None = None
    area: Area | None = None
    extra_damage: Annotated[list[DamagePart], Field(max_length=4)] = []


class Resource(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=36)]
    name: Text = "Resource"
    max: Annotated[int, Field(ge=0, le=99)] = 1
    used: Annotated[int, Field(ge=0, le=99)] = 0
    reset: Literal["short", "long", "none"] = "long"


class Spellcasting(BaseModel):
    ability: Ability | None = None
    # Slot level ("1".."9") -> slots.
    slots: dict[Literal["1", "2", "3", "4", "5", "6", "7", "8", "9"], Slot] = {}


class Sheet(BaseModel):
    kind: Literal["pc", "npc"] = "pc"
    # Compendium entry it was made from (e.g. "srd-2024_goblin-warrior"), if any.
    source: Text = ""
    # Character
    level: Annotated[int, Field(ge=1, le=20)] = 1
    classes: Text = ""
    species: Text = ""
    background: Text = ""
    # Monster
    cr: Literal[tuple(CR_XP)] = "1"  # type: ignore[valid-type]
    creature_type: Text = ""
    size: Literal["tiny", "small", "medium", "large", "huge", "gargantuan"] = "medium"

    abilities: Abilities = Abilities()
    save_proficiencies: Annotated[list[Ability], Field(max_length=6)] = []
    # Skill -> 1 proficient, 2 expertise.
    skills: dict[Literal[tuple(SKILLS)], Literal[1, 2]] = {}  # type: ignore[valid-type]
    ac: Annotated[int, Field(ge=0, le=40)] = 10
    # Feet, as in the rules; the interface converts to metres.
    speed: Annotated[int, Field(ge=0, le=500)] = 30
    initiative_bonus: Small = 0
    hp: HitPoints = HitPoints()
    hit_dice: HitDice = HitDice()
    death_saves: DeathSaves = DeathSaves()
    exhaustion: Annotated[int, Field(ge=0, le=6)] = 0
    attacks: Annotated[list[Attack], Field(max_length=50)] = []
    # Attacks per Attack action (Extra Attack), lowest d20 that is a critical hit.
    extra_attack: Annotated[int, Field(ge=1, le=4)] = 1
    crit_range: Annotated[int, Field(ge=18, le=20)] = 20
    multiattack: Annotated[list[MultiattackStep], Field(max_length=6)] = []
    multiattack_note: Text = ""
    legendary_uses: Annotated[int, Field(ge=0, le=5)] = 0
    legendary_resistance: Annotated[int, Field(ge=0, le=5)] = 0
    spellcasting: Spellcasting = Spellcasting()
    spells: Annotated[list[Spell], Field(max_length=200)] = []
    resources: Annotated[list[Resource], Field(max_length=50)] = []
    resistances: Annotated[list[Text], Field(max_length=20)] = []
    immunities: Annotated[list[Text], Field(max_length=20)] = []
    vulnerabilities: Annotated[list[Text], Field(max_length=20)] = []
    condition_immunities: Annotated[list[Text], Field(max_length=20)] = []
    features: Annotated[str, Field(max_length=20_000)] = ""


def new_sheet(kind: Literal["pc", "npc"]) -> dict[str, Any]:
    return Sheet(kind=kind).model_dump()


def proficiency(sheet: Sheet) -> int:
    return (
        proficiency_for_level(sheet.level) if sheet.kind == "pc" else proficiency_for_cr(sheet.cr)
    )


def ability_mod(sheet: Sheet, ability: str) -> int:
    if ability == "spell":
        ability = sheet.spellcasting.ability or ""
    return modifier(getattr(sheet.abilities, ability)) if ability in ABILITIES else 0


def save_bonus(sheet: Sheet, ability: str) -> int:
    prof = proficiency(sheet) if ability in sheet.save_proficiencies else 0
    return ability_mod(sheet, ability) + prof


def skill_bonus(sheet: Sheet, skill: str) -> int:
    return ability_mod(sheet, SKILLS[skill]) + proficiency(sheet) * sheet.skills.get(skill, 0)


def attack_bonus(sheet: Sheet, attack: Attack) -> int:
    if attack.to_hit is not None:
        return attack.to_hit
    prof = proficiency(sheet) if attack.proficient else 0
    return ability_mod(sheet, attack.ability) + prof + attack.bonus


def save_dc(sheet: Sheet, attack: Attack) -> int:
    if attack.dc is not None:
        return attack.dc
    return 8 + proficiency(sheet) + ability_mod(sheet, attack.ability)


def damage_parts(sheet: Sheet, attack: Attack) -> list[tuple[str, str]]:
    """(formula, type) of every damage part; the modifier goes on the first one."""
    first = damage_formula(sheet, attack)
    parts = [(first, attack.damage_type)] if first else []
    return parts + [(p.formula, p.type) for p in attack.extra_damage if p.formula.strip()]


def damage_formula(sheet: Sheet, attack: Attack) -> str:
    mod = ability_mod(sheet, attack.ability) if attack.add_modifier else 0
    if not attack.damage.strip():
        return ""
    return f"{attack.damage}{mod:+d}" if mod else attack.damage


def spell_dc(sheet: Sheet) -> int | None:
    if sheet.spellcasting.ability is None:
        return None
    return 8 + proficiency(sheet) + ability_mod(sheet, "spell")


def spell_attack(sheet: Sheet) -> int | None:
    if sheet.spellcasting.ability is None:
        return None
    return proficiency(sheet) + ability_mod(sheet, "spell")


def initiative(sheet: Sheet) -> int:
    return ability_mod(sheet, "dex") + sheet.initiative_bonus


def derive(raw: dict[str, Any]) -> dict[str, Any]:
    """Every computed value the sheet shows, from the stored base values."""
    sheet = Sheet.model_validate(raw)
    return {
        "proficiency": proficiency(sheet),
        "modifiers": {a: ability_mod(sheet, a) for a in ABILITIES},
        "saves": {a: save_bonus(sheet, a) for a in ABILITIES},
        "skills": {s: skill_bonus(sheet, s) for s in SKILLS},
        "passive_perception": 10 + skill_bonus(sheet, "perception"),
        "initiative": initiative(sheet),
        "spell_dc": spell_dc(sheet),
        "spell_attack": spell_attack(sheet),
        "xp": CR_XP[sheet.cr] if sheet.kind == "npc" else None,
        "attacks": {
            a.id: {
                "to_hit": attack_bonus(sheet, a) if a.kind == "attack" else None,
                "dc": save_dc(sheet, a) if a.kind == "save" else None,
                "damage": damage_formula(sheet, a),
                "parts": [list(p) for p in damage_parts(sheet, a)],
            }
            for a in sheet.attacks
        },
        "hit_dice_total": sheet.level if sheet.kind == "pc" else 0,
    }
