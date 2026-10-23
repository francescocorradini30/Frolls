"""Game options: every switch the GM can turn, in one catalog.

The catalog is the single source of truth: the server validates changes against it, sends
it to the clients (the GM's Game settings panel is drawn from it) and reads the values with
their defaults. A new switch is one `Option` here; the code that uses it reads
`GameServer.option(key)`. Values live in `games.settings`, next to `round` and `measurement`.
"""

from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["bool", "choice", "int"]


@dataclass(frozen=True)
class Option:
    key: str
    section: str
    label: str
    help: str
    default: Any
    kind: Kind = "bool"
    # For "choice": (value, label) pairs.
    choices: tuple[tuple[str, str], ...] = ()
    # For "int".
    min: int = 0
    max: int = 99

    def valid(self, value: Any) -> bool:
        if self.kind == "bool":
            return isinstance(value, bool)
        if self.kind == "choice":
            return value in {c for c, _ in self.choices}
        return (
            isinstance(value, int) and not isinstance(value, bool) and self.min <= value <= self.max
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "section": self.section,
            "label": self.label,
            "help": self.help,
            "default": self.default,
            "kind": self.kind,
            "choices": [list(c) for c in self.choices],
            "min": self.min,
            "max": self.max,
        }


SECTIONS = ("Automation", "Combat", "House rules", "Visibility", "Characters")

CATALOG: tuple[Option, ...] = (
    Option(
        "npc_hp",
        "Visibility",
        "Monsters' hit points, for players",
        'Tokens that no player controls. With "How hurt they look" players see the bar in '
        "quarters, never the numbers.",
        "status",
        "choice",
        (("hidden", "Hidden"), ("status", "How hurt they look"), ("full", "Numbers")),
    ),
)

# Drafted switches, moved into CATALOG as their features are built.
PLANNED: tuple[Option, ...] = (
    # --- Automation ---------------------------------------------------------
    Option(
        "auto_apply",
        "Automation",
        "Apply attack and spell results",
        "Auto: hits, damage, healing and failed saves are applied at once, with an Undo button "
        "on the chat card. Confirm: everything is rolled and computed, the GM clicks Apply. "
        "Manual: only buttons in chat, anyone applies by hand.",
        "auto",
        "choice",
        (
            ("auto", "Automatically, with Undo"),
            ("confirm", "After the GM confirms"),
            ("manual", "By hand"),
        ),
    ),
    Option(
        "auto_monster_saves",
        "Automation",
        "Roll saving throws for monsters",
        "Monsters and other GM creatures roll their own saves against spells and effects.",
        True,
    ),
    Option(
        "auto_player_saves",
        "Automation",
        "Roll saving throws for player characters",
        "Off: each player gets a button to roll their own save, the result applies when they "
        "click. On: their saves are rolled for them like monsters'.",
        False,
    ),
    Option(
        "auto_concentration",
        "Automation",
        "Concentration saves",
        "A concentrating creature that takes damage rolls its Constitution save at once; on a "
        "failure the spell and its effects end.",
        True,
    ),
    Option(
        "auto_death_saves",
        "Automation",
        "Death saves at the start of the turn",
        "A dying player character rolls its death save automatically when its turn starts. "
        "Off: the player gets a button.",
        False,
    ),
    # --- Combat -------------------------------------------------------------
    Option(
        "initiative_mode",
        "Combat",
        "Initiative",
        "Individual: every creature rolls. Same monsters together: identical monsters share "
        "one roll. Sides: one roll for the players' side and one for the GM's, the higher side "
        "acts first.",
        "grouped",
        "choice",
        (("individual", "Individual"), ("grouped", "Same monsters together"), ("sides", "Sides")),
    ),
    Option(
        "initiative_reroll",
        "Combat",
        "Reroll initiative every round",
        "At the start of each round everyone rolls initiative again.",
        False,
    ),
    Option(
        "track_movement",
        "Combat",
        "Track movement",
        "Count the distance moved by the creature whose turn it is and show what is left of its "
        "speed.",
        True,
    ),
    Option(
        "skip_defeated",
        "Combat",
        "Skip defeated creatures",
        "Next turn jumps over monsters at 0 hit points and dead creatures.",
        True,
    ),
    # --- House rules ----------------------------------------------------------
    Option(
        "flanking",
        "House rules",
        "Flanking",
        "Optional rule: a melee attacker and an ally on opposite sides of an enemy flank it.",
        "off",
        "choice",
        (("off", "Off"), ("advantage", "Advantage"), ("bonus", "+2 to hit")),
    ),
    Option(
        "crit_rule",
        "House rules",
        "Critical hit damage",
        "Rules as written: roll the damage dice twice. Max + roll: one set of dice at their "
        "maximum plus one rolled set.",
        "double",
        "choice",
        (("double", "Roll the dice twice (rules)"), ("max", "Max dice + roll")),
    ),
    Option(
        "potion_bonus_action",
        "House rules",
        "Drinking a potion is a Bonus Action",
        "Giving a potion to someone else still takes an action.",
        False,
    ),
    # --- Visibility -----------------------------------------------------------
    Option(
        "show_monster_ac",
        "Visibility",
        "Show monsters' AC on attack cards",
        "Off: players see Hit or Miss but not the number they rolled against.",
        False,
    ),
    Option(
        "hide_monster_rolls",
        "Visibility",
        "Hide monster attack rolls",
        "Players see the result of a monster's attack (hit, miss, damage) but not the dice.",
        False,
    ),
)

BY_KEY = {o.key: o for o in CATALOG}


def value(settings: dict[str, Any], key: str) -> Any:
    option = BY_KEY[key]
    v = settings.get(key, option.default)
    return v if option.valid(v) else option.default


def validate(patch: dict[str, Any]) -> str | None:
    """Why the patch is invalid, if it is."""
    for key, v in patch.items():
        option = BY_KEY.get(key)
        if option is None:
            return f"unknown option {key}"
        if not option.valid(v):
            return f"invalid value for {option.label}"
    return None


def catalog() -> list[dict[str, Any]]:
    return [o.as_dict() for o in CATALOG]
