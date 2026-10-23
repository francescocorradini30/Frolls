"""Damage, healing, temporary hit points and death (SRD 5.2)."""

from dataclasses import dataclass, field
from typing import Literal

ApplyKind = Literal["damage", "healing", "temp"]


@dataclass
class Health:
    current: int
    max: int
    temp: int = 0
    # Player characters make death saving throws at 0 HP; monsters simply die.
    pc: bool = True
    successes: int = 0
    failures: int = 0
    conditions: frozenset[str] = frozenset()


@dataclass
class Defenses:
    resistances: frozenset[str] = frozenset()
    immunities: frozenset[str] = frozenset()
    vulnerabilities: frozenset[str] = frozenset()


@dataclass
class Outcome:
    health: Health
    # Damage actually taken after halving, resistances and temporary HP, for the chat card.
    taken: int = 0
    notes: list[str] = field(default_factory=list)
    added: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)


def adjust(
    amount: int, damage_type: str | None, defenses: Defenses, half: bool
) -> tuple[int, list[str]]:
    """Damage after a successful save (half) and the target's defenses.

    Halving rounds down. Immunity cancels the damage; resistance halves it and
    vulnerability doubles it (both, if the creature has both).
    """
    notes: list[str] = []
    if half:
        amount //= 2
        notes.append("half on a successful save")
    t = (damage_type or "").lower()
    if t and t in defenses.immunities:
        return 0, [*notes, f"immune to {t}"]
    if t and t in defenses.resistances:
        amount //= 2
        notes.append(f"resistant to {t}")
    if t and t in defenses.vulnerabilities:
        amount *= 2
        notes.append(f"vulnerable to {t}")
    return amount, notes


def apply(
    health: Health,
    kind: ApplyKind,
    amount: int,
    damage_type: str | None = None,
    defenses: Defenses | None = None,
    half: bool = False,
    critical: bool = False,
) -> Outcome:
    """New health after damage, healing or temporary hit points."""
    h = Health(**health.__dict__)
    out = Outcome(h)
    if kind == "temp":
        # Temporary hit points don't add up: keep the higher.
        if amount > h.temp:
            h.temp = amount
        else:
            out.notes.append("kept the higher temporary hit points")
        return out
    if kind == "healing":
        if "dead" in h.conditions:
            out.notes.append("the dead cannot be healed")
            return out
        was_down = h.current == 0
        h.current = min(h.max, h.current + max(0, amount))
        if was_down and h.current > 0:
            h.successes = h.failures = 0
            out.removed |= {"unconscious"}
            out.notes.append("back on their feet")
        return out

    amount, notes = adjust(max(0, amount), damage_type, defenses or Defenses(), half)
    out.notes += notes
    out.taken = amount
    absorbed = min(h.temp, amount)
    h.temp -= absorbed
    rest = amount - absorbed
    if absorbed:
        out.notes.append(f"{absorbed} absorbed by temporary hit points")
    if rest == 0:
        return out

    if h.current == 0:
        # Already at 0 HP: damage is a failed death save, two on a critical hit;
        # damage at least equal to the hit point maximum kills outright.
        if rest >= h.max:
            _die(out, "massive damage")
        elif h.pc:
            h.failures = min(3, h.failures + (2 if critical else 1))
            out.notes.append("death save failure" + ("s" if critical else ""))
            if h.failures >= 3:
                _die(out, "three failed death saves")
        return out

    h.current -= rest
    if h.current > 0:
        return out
    excess = -h.current
    h.current = 0
    if excess >= h.max:
        _die(out, "instant death: the remaining damage equals the hit point maximum")
    elif h.pc:
        h.successes = h.failures = 0
        out.added |= {"unconscious", "prone"}
        out.notes.append("falls unconscious and starts making death saves")
    else:
        _die(out, "drops to 0 hit points")
    return out


def _die(out: Outcome, why: str) -> None:
    out.health.current = 0
    out.added |= {"dead"}
    out.removed |= {"unconscious"}
    out.notes.append(why)


def death_save(health: Health, natural: int) -> Outcome:
    """A death saving throw: 10 or more succeeds; a 20 brings back 1 HP; a 1 counts twice."""
    h = Health(**health.__dict__)
    out = Outcome(h)
    if natural == 20:
        h.current, h.successes, h.failures = 1, 0, 0
        out.removed |= {"unconscious"}
        out.notes.append("natural 20: regains 1 hit point")
    elif natural >= 10:
        h.successes = min(3, h.successes + 1)
        out.notes.append("success")
        if h.successes >= 3:
            out.notes.append("stable")
    else:
        h.failures = min(3, h.failures + (2 if natural == 1 else 1))
        out.notes.append("natural 1: two failures" if natural == 1 else "failure")
        if h.failures >= 3:
            _die(out, "three failed death saves")
    return out


def bloodied_state(current: int, maximum: int) -> str:
    """What players see of a monster's health when the GM shows only its state."""
    if maximum <= 0 or current >= maximum:
        return "Unhurt"
    if current <= 0:
        return "Down"
    ratio = current / maximum
    if ratio > 0.5:
        return "Wounded"
    return "Bloodied" if ratio > 0.25 else "Near death"
