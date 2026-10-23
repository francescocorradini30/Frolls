"""Damage, healing and death rules."""

from app.rules5e.damage import Defenses, Health, adjust, apply, bloodied_state, death_save


def test_half_then_resistance_round_down() -> None:
    assert adjust(15, "fire", Defenses(resistances=frozenset({"fire"})), half=True) == (
        3,
        ["half on a successful save", "resistant to fire"],
    )


def test_immunity_and_vulnerability() -> None:
    assert adjust(10, "poison", Defenses(immunities=frozenset({"poison"})), False)[0] == 0
    assert adjust(10, "cold", Defenses(vulnerabilities=frozenset({"cold"})), False)[0] == 20


def test_temporary_hit_points_absorb_first_and_do_not_stack() -> None:
    out = apply(Health(10, 10, temp=5), "damage", 7)
    assert (out.health.current, out.health.temp) == (8, 0)
    assert apply(Health(10, 10, temp=8), "temp", 5).health.temp == 8
    assert apply(Health(10, 10, temp=3), "temp", 5).health.temp == 5


def test_pc_falls_unconscious_and_monster_dies() -> None:
    pc = apply(Health(5, 20), "damage", 9)
    assert pc.health.current == 0 and pc.added == {"unconscious", "prone"}
    monster = apply(Health(5, 20, pc=False), "damage", 9)
    assert monster.added == {"dead"}


def test_instant_death_from_massive_damage() -> None:
    out = apply(Health(6, 12), "damage", 18)
    assert "dead" in out.added


def test_damage_at_zero_is_a_death_save_failure() -> None:
    down = Health(0, 20, failures=1)
    assert apply(down, "damage", 3).health.failures == 2
    assert "dead" in apply(down, "damage", 3, critical=True).added
    assert "dead" in apply(Health(0, 20), "damage", 20).added


def test_healing_wakes_up_and_resets_death_saves() -> None:
    out = apply(Health(0, 20, successes=2, failures=1), "healing", 4)
    assert out.health.current == 4 and (out.health.successes, out.health.failures) == (0, 0)
    assert out.removed == {"unconscious"}
    assert apply(Health(18, 20), "healing", 10).health.current == 20


def test_death_saves() -> None:
    assert death_save(Health(0, 20, successes=2), 12).notes == ["success", "stable"]
    assert death_save(Health(0, 20), 1).health.failures == 2
    assert "dead" in death_save(Health(0, 20, failures=2), 5).added
    twenty = death_save(Health(0, 20, failures=2), 20)
    assert twenty.health.current == 1 and twenty.removed == {"unconscious"}


def test_bloodied_states() -> None:
    assert [bloodied_state(c, 20) for c in (20, 15, 10, 4, 0)] == [
        "Unhurt",
        "Wounded",
        "Bloodied",
        "Near death",
        "Down",
    ]
