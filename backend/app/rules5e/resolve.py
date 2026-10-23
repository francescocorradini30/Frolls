"""Resolution of an attack against one target (SRD 5.2), without touching the game.

The server builds `Combatant` snapshots from tokens and sheets, calls `attack()` and then
writes the outcome (hit points, effects) through its own helpers. Dice come from the
`roll` function passed in, so tests can fix them.

Order: range and cover → advantage/disadvantage (choice, conditions, effects, range, a
hostile next to a ranged attacker, optional flanking) → attack roll against AC + cover +
effects → critical hit on a natural roll in the crit range, or automatically on a hit from
within 5 feet against a Paralyzed or Unconscious target → damage parts (doubled dice on a
critical, or the "max + roll" house rule).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.rules5e import effects as effects5e
from app.rules5e import geometry
from app.rules5e import rolls as rolls5e
from app.rules5e import sheet as sheet5e
from app.rules5e.sheet import Attack, Sheet

Roller = Callable[[str], dict[str, Any]]


@dataclass
class Combatant:
    id: str
    name: str
    sheet: Sheet | None
    effects: list[effects5e.Effect]
    conditions: frozenset[str]
    box: geometry.Box


@dataclass
class Context:
    roll: Roller
    cell: float
    mode: rolls5e.Mode = "normal"
    # AC bonus of the target's cover: 0, 2 (half) or 5 (three-quarters).
    cover: int = 0
    crit_rule: str = "double"
    # "off", "advantage" or "bonus" (+2), with the attacker's allies that could flank.
    flanking: str = "off"
    allies: list[geometry.Box] = field(default_factory=list)
    # A hostile, not incapacitated creature is next to the attacker (ranged disadvantage).
    threatened: bool = False


@dataclass
class DamageRoll:
    formula: str
    type: str
    roll: dict[str, Any]

    @property
    def total(self) -> int:
        return int(self.roll["total"])


@dataclass
class AttackResult:
    target_id: str
    roll: dict[str, Any]
    natural: int | None
    total: int
    ac: int | None
    # "hit", "critical hit", "miss", "critical miss", or "rolled" when the AC is unknown.
    outcome: str
    reasons: list[str]
    warnings: list[str]
    damage: list[DamageRoll]
    distance_ft: int

    @property
    def hit(self) -> bool:
        return self.outcome in ("hit", "critical hit")

    @property
    def critical(self) -> bool:
        return self.outcome == "critical hit"


def target_ac(target: Combatant, cover: int) -> int | None:
    if target.sheet is None:
        return None
    return target.sheet.ac + effects5e.ac_bonus(target.effects) + cover


def attack(
    actor: Combatant, attack_: Attack, target: Combatant, ctx: Context, roll_damage: bool = True
) -> AttackResult:
    sheet = actor.sheet
    assert sheet is not None
    distance = geometry.distance_ft(actor.box, target.box, ctx.cell)
    near = distance <= geometry.FEET_PER_CELL
    warnings: list[str] = []
    extra_adv: list[str] = []
    extra_dis: list[str] = []

    melee = attack_.melee
    if attack_.reach is not None and distance <= attack_.reach:
        melee = True
    if melee:
        reach = attack_.reach or 5
        if distance > reach:
            warnings.append(f"out of reach ({distance} ft, reach {reach} ft)")
    else:
        normal = attack_.range_normal or 0
        long = attack_.range_long or normal
        if distance > long:
            warnings.append(f"beyond long range ({distance} ft)")
        elif distance > normal:
            extra_dis.append("disadvantage: beyond normal range")
        if ctx.threatened:
            extra_dis.append("disadvantage: a hostile creature is next to the attacker")

    flank_bonus = 0
    if melee and ctx.flanking != "off" and near:
        if any(geometry.flanked(actor.box, ally, target.box, ctx.cell) for ally in ctx.allies):
            if ctx.flanking == "advantage":
                extra_adv.append("advantage: flanking")
            else:
                flank_bonus = 2

    adv, dis, dice, flat = effects5e.roll_changes(actor.effects, "attack", None)
    t_adv, t_dis = effects5e.attacked_with(target.effects)
    test = rolls5e.d20_test(
        "attack",
        ctx.mode,
        None,
        actor.conditions,
        target.conditions,
        near,
        adv + t_adv + extra_adv,
        dis + t_dis + extra_dis,
    )
    bonus = (
        sheet5e.attack_bonus(sheet, attack_)
        + rolls5e.exhaustion_penalty(sheet.exhaustion)
        + flat
        + flank_bonus
    )
    reasons = list(test.reasons)
    if flank_bonus:
        reasons.append("+2: flanking")
    if ctx.cover:
        reasons.append(f"+{ctx.cover} AC: {'half' if ctx.cover == 2 else 'three-quarters'} cover")
    d20 = ctx.roll(test.formula(bonus, dice))
    natural = rolls5e.natural(d20)
    total = int(d20["total"])
    ac = target_ac(target, ctx.cover)

    if natural is not None and natural >= sheet.crit_range:
        outcome = "critical hit"
    elif natural == 1:
        outcome = "critical miss"
    elif ac is None:
        outcome = "rolled"
    elif total >= ac:
        auto = near and bool(target.conditions & set(rolls5e.AUTO_CRIT))
        outcome = "critical hit" if auto else "hit"
        if auto:
            reasons.append("critical: the target is paralyzed or unconscious, within 5 ft")
    else:
        outcome = "miss"

    damage: list[DamageRoll] = []
    if roll_damage and outcome in ("hit", "critical hit", "rolled"):
        damage = roll_parts(
            sheet5e.damage_parts(sheet, attack_), outcome == "critical hit", ctx.crit_rule, ctx.roll
        )
    return AttackResult(
        target.id, d20, natural, total, ac, outcome, reasons, warnings, damage, distance
    )


def roll_parts(
    parts: list[tuple[str, str]], critical: bool, rule: str, roll: Roller
) -> list[DamageRoll]:
    out = []
    for formula, damage_type in parts:
        f = rolls5e.critical(formula, rule) if critical else formula
        out.append(DamageRoll(f, damage_type, roll(f)))
    return out
