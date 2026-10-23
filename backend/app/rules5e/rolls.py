"""d20 tests and damage rolls (SRD 5.2).

Advantage and disadvantage come from the roller's choice and from conditions on the
actor and on the target; if there is at least one of each, they cancel out and the roll
is normal. Exhaustion takes 2 per level off every d20 test.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["normal", "advantage", "disadvantage"]
TestKind = Literal["attack", "check", "save", "initiative"]

D20 = {"normal": "1d20", "advantage": "2d20kh1", "disadvantage": "2d20kl1"}
# A hit from within 5 ft against a creature with one of these is a critical hit.
AUTO_CRIT = ("paralyzed", "unconscious")
# The creature automatically fails Strength and Dexterity saving throws.
AUTO_FAIL_STR_DEX = ("paralyzed", "petrified", "stunned", "unconscious")


@dataclass
class D20Test:
    mode: Mode
    # Why, for the chat card: "advantage: target is prone".
    reasons: list[str] = field(default_factory=list)
    auto_fail: str | None = None

    def formula(self, bonus: int, extra: str = "") -> str:
        return D20[self.mode] + (f"{bonus:+d}" if bonus else "") + extra


def d20_test(
    kind: TestKind,
    requested: Mode = "normal",
    ability: str | None = None,
    actor: frozenset[str] = frozenset(),
    target: frozenset[str] = frozenset(),
    within_5ft: bool = True,
    extra_adv: list[str] | None = None,
    extra_dis: list[str] | None = None,
) -> D20Test:
    """Mode of a d20 test from the request, the conditions of actor and target, and other
    reasons (effects) passed in `extra_adv` / `extra_dis`."""
    adv: list[str] = ["advantage: chosen"] if requested == "advantage" else []
    dis: list[str] = ["disadvantage: chosen"] if requested == "disadvantage" else []
    adv += extra_adv or []
    dis += extra_dis or []
    auto_fail = None

    def on(cond: str, where: list[str], text: str) -> None:
        where.append(text)

    if kind == "attack":
        for c in actor & {"blinded", "frightened", "poisoned", "prone", "restrained"}:
            on(c, dis, f"disadvantage: attacker is {c}")
        if "invisible" in actor:
            on("invisible", adv, "advantage: attacker is invisible")
        for c in target & {
            "blinded",
            "paralyzed",
            "petrified",
            "restrained",
            "stunned",
            "unconscious",
        }:
            on(c, adv, f"advantage: target is {c}")
        if "invisible" in target:
            on("invisible", dis, "disadvantage: target is invisible")
        if "prone" in target:
            if within_5ft:
                on("prone", adv, "advantage: target is prone, within 5 ft")
            else:
                on("prone", dis, "disadvantage: target is prone, beyond 5 ft")
    elif kind == "check":
        for c in actor & {"frightened", "poisoned"}:
            on(c, dis, f"disadvantage: {c}")
    elif kind == "save":
        if ability == "dex" and "restrained" in actor:
            on("restrained", dis, "disadvantage: restrained")
        if ability in ("str", "dex"):
            failing = sorted(actor & set(AUTO_FAIL_STR_DEX))
            if failing:
                auto_fail = f"automatic failure: {failing[0]}"
    elif kind == "initiative":
        if "invisible" in actor:
            on("invisible", adv, "advantage: invisible")
        if "incapacitated" in actor:
            on("incapacitated", dis, "disadvantage: incapacitated")

    if adv and dis:
        mode: Mode = "normal"
        reasons = [*adv, *dis, "advantage and disadvantage cancel out"]
    elif adv:
        mode, reasons = "advantage", adv
    elif dis:
        mode, reasons = "disadvantage", dis
    else:
        mode, reasons = "normal", []
    return D20Test(mode, reasons, auto_fail)


def exhaustion_penalty(level: int) -> int:
    return -2 * level


DICE_RE = re.compile(r"(\d*)d(\d+)")


def critical(formula: str) -> str:
    """Critical hit: twice the dice, the same modifiers. `1d8+3` -> `2d8+3`."""
    return DICE_RE.sub(lambda m: f"{2 * int(m.group(1) or 1)}d{m.group(2)}", formula)


def natural(roll: dict) -> int | None:
    """Natural value of the kept d20 of a roll dict (first term), if it is a d20 roll."""
    for term in roll.get("terms", []):
        if term.get("sides") == 20:
            kept = [d["value"] for d in term["dice"] if d["kept"]]
            return kept[0] if kept else None
    return None


def attack_outcome(nat: int | None, total: int, ac: int | None, auto_crit: bool) -> str:
    """Hit or miss: a natural 20 always hits (critical), a natural 1 always misses."""
    if nat == 20:
        return "critical hit"
    if nat == 1:
        return "critical miss"
    if ac is None:
        return ""
    if total >= ac:
        return "critical hit" if auto_crit else "hit"
    return "miss"
