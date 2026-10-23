"""Attack resolution and grid geometry (pure rules code)."""

from app.dice import roll as dice_roll
from app.game.chat import roll_to_dict
from app.rules5e import geometry, resolve
from app.rules5e.effects import from_preset
from app.rules5e.sheet import Attack, Sheet
from tests.conftest import FixedDice

CELL = 70.0


def box(col: int, row: int, cells: int = 1) -> geometry.Box:
    side = cells * CELL
    return geometry.Box(col * CELL + side / 2, row * CELL + side / 2, side, side)


def fighter() -> Sheet:
    return Sheet.model_validate({"kind": "pc", "abilities": {"str": 16, "dex": 14}})


SWORD = Attack(id="s", name="Longsword", damage="1d8", damage_type="slashing", reach=5)
BOW = Attack(
    id="b",
    name="Longbow",
    ability="dex",
    damage="1d8",
    damage_type="piercing",
    range="range 150/600 ft",
)


def who(
    name: str, at: geometry.Box, ac: int | None = 13, statuses: tuple[str, ...] = ()
) -> resolve.Combatant:
    sheet = Sheet.model_validate({"kind": "npc", "ac": ac}) if ac is not None else None
    return resolve.Combatant(name, name, sheet, [], frozenset(statuses), at)


def ctx(**kw) -> resolve.Context:
    return resolve.Context(lambda f: roll_to_dict(dice_roll(f)), CELL, **kw)


def actor(at: geometry.Box) -> resolve.Combatant:
    return resolve.Combatant("me", "Aria", fighter(), [], frozenset(), at)


def test_geometry_distances_and_reach() -> None:
    assert geometry.distance_ft(box(0, 0), box(1, 0), CELL) == 5
    assert geometry.distance_ft(box(0, 0), box(1, 1), CELL) == 5
    assert geometry.distance_ft(box(0, 0), box(3, 0), CELL) == 15
    # A Large creature (2x2) is next to anything touching its four cells.
    assert geometry.distance_ft(box(0, 0, 2), box(2, 1), CELL) == 5
    assert geometry.within(box(0, 0), box(2, 0), CELL, 10)


def test_flanking_needs_opposite_sides() -> None:
    target = box(5, 5)
    assert geometry.flanked(box(4, 5), box(6, 5), target, CELL)
    assert geometry.flanked(box(4, 4), box(6, 6), target, CELL)
    assert not geometry.flanked(box(4, 5), box(5, 6), target, CELL)
    # Large target: opposite sides of its 2x2 space.
    assert geometry.flanked(box(4, 5), box(7, 6), box(5, 5, 2), CELL)


def test_hit_and_damage(dice: FixedDice) -> None:
    dice.face = 10  # 10 + 5 = 15 vs AC 13
    r = resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0)), ctx())
    assert r.outcome == "hit" and r.total == 15 and r.ac == 13
    assert [(d.formula, d.total, d.type) for d in r.damage] == [("1d8+3", 11, "slashing")]


def test_misses_and_natural_rolls(dice: FixedDice) -> None:
    dice.face = 5
    assert (
        resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0), ac=18), ctx()).outcome
        == "miss"
    )
    dice.face = 1
    assert (
        resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0), ac=2), ctx()).outcome
        == "critical miss"
    )


def test_critical_damage_rules(dice: FixedDice) -> None:
    dice.face = 20
    r = resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0)), ctx())
    assert r.outcome == "critical hit" and r.damage[0].formula == "2d8+3"
    r = resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0)), ctx(crit_rule="max"))
    assert r.damage[0].formula == "1d8+3+8"


def test_unknown_ac_is_only_rolled(dice: FixedDice) -> None:
    dice.face = 12
    r = resolve.attack(actor(box(0, 0)), SWORD, who("crate", box(1, 0), ac=None), ctx())
    assert r.outcome == "rolled" and r.damage


def test_range_and_reach(dice: FixedDice) -> None:
    dice.face = 10
    far = resolve.attack(actor(box(0, 0)), BOW, who("gob", box(40, 0)), ctx())
    assert "disadvantage: beyond normal range" in far.reasons
    too_far = resolve.attack(actor(box(0, 0)), BOW, who("gob", box(200, 0)), ctx())
    assert too_far.warnings == ["beyond long range (1000 ft)"]
    close = resolve.attack(actor(box(0, 0)), BOW, who("gob", box(1, 0)), ctx(threatened=True))
    assert "disadvantage: a hostile creature is next to the attacker" in close.reasons
    reach = resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(3, 0)), ctx())
    assert reach.warnings == ["out of reach (15 ft, reach 5 ft)"]


def test_flanking_house_rule(dice: FixedDice) -> None:
    dice.face = 10
    c = ctx(flanking="advantage", allies=[box(2, 0)])
    r = resolve.attack(actor(box(0, 0)), SWORD, who("gob", box(1, 0)), c)
    assert "advantage: flanking" in r.reasons
    r = resolve.attack(
        actor(box(0, 0)), SWORD, who("gob", box(1, 0)), ctx(flanking="bonus", allies=[box(2, 0)])
    )
    assert r.total == 17 and "+2: flanking" in r.reasons


def test_cover_and_effects_raise_the_ac(dice: FixedDice) -> None:
    dice.face = 10
    target = who("gob", box(1, 0))
    target.effects = [from_preset("shield_of_faith", None, False, None)]
    r = resolve.attack(actor(box(0, 0)), SWORD, target, ctx(cover=2))
    assert r.ac == 17 and r.outcome == "miss"


def test_paralyzed_target_hit_from_next_to_it_is_a_critical(dice: FixedDice) -> None:
    dice.face = 10
    r = resolve.attack(
        actor(box(0, 0)), SWORD, who("gob", box(1, 0), statuses=("paralyzed",)), ctx()
    )
    assert r.outcome == "critical hit"
