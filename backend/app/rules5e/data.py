"""Fixed SRD 5.2 tables."""

from fractions import Fraction

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
ABILITY_NAMES = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

SKILLS = {
    "acrobatics": "dex",
    "animal_handling": "wis",
    "arcana": "int",
    "athletics": "str",
    "deception": "cha",
    "history": "int",
    "insight": "wis",
    "intimidation": "cha",
    "investigation": "int",
    "medicine": "wis",
    "nature": "int",
    "perception": "wis",
    "performance": "cha",
    "persuasion": "cha",
    "religion": "int",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    "survival": "wis",
}

DAMAGE_TYPES = (
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "force",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
)

CONDITIONS = (
    "blinded",
    "charmed",
    "deafened",
    "exhaustion",
    "frightened",
    "grappled",
    "incapacitated",
    "invisible",
    "paralyzed",
    "petrified",
    "poisoned",
    "prone",
    "restrained",
    "stunned",
    "unconscious",
)

# Space in grid cells (Tiny = half a cell).
SIZES = {"tiny": 0.5, "small": 1, "medium": 1, "large": 2, "huge": 3, "gargantuan": 4}

# Challenge rating -> experience points.
CR_XP = {
    "0": 10,
    "1/8": 25,
    "1/4": 50,
    "1/2": 100,
    **{
        str(cr): xp
        for cr, xp in zip(
            range(1, 31),
            (
                200,
                450,
                700,
                1100,
                1800,
                2300,
                2900,
                3900,
                5000,
                5900,
                7200,
                8400,
                10000,
                11500,
                13000,
                15000,
                18000,
                20000,
                22000,
                25000,
                33000,
                41000,
                50000,
                62000,
                75000,
                90000,
                105000,
                120000,
                135000,
                155000,
            ),  # fmt: skip
            strict=True,
        )
    },
}


def modifier(score: int) -> int:
    """(score - 10) / 2, rounded down."""
    return (score - 10) // 2


def proficiency_for_level(level: int) -> int:
    """+2 at levels 1-4, +3 at 5-8, … +6 at 17-20."""
    return 2 + (max(1, min(level, 20)) - 1) // 4


def proficiency_for_cr(cr: str) -> int:
    """+2 up to CR 4, then +1 every 4 CR."""
    value = Fraction(cr) if cr in CR_XP else Fraction(0)
    return 2 + max(0, (int(value) - 1) // 4) if value >= 1 else 2
