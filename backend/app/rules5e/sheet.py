"""5e character sheet: stored base values (validated here) and derived values.

Only base values are stored. Modifiers, proficiency, save and skill bonuses, spell DC and
attack bonuses are always computed by `derive`, so they can never go out of sync.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

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
    range: Text = ""
    notes: Annotated[str, Field(max_length=2000)] = ""


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
            }
            for a in sheet.attacks
        },
        "hit_dice_total": sheet.level if sheet.kind == "pc" else 0,
    }
