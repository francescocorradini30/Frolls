"""Effects: presets, roll changes, durations tied to turns, concentration DC."""

from app.rules5e.effects import (
    Effect,
    Ending,
    ac_bonus,
    attacked_with,
    concentration_dc,
    from_preset,
    roll_changes,
    tick,
)


def test_bless_adds_a_d4_to_attacks_and_saves() -> None:
    bless = from_preset("bless", "caster", True, None)
    assert bless.concentration_of == "caster" and bless.ending == Ending(of="caster", rounds=10)
    assert roll_changes([bless], "attack", None) == ([], [], "+1d4", 0)
    assert roll_changes([from_preset("bane", "c", True, None)], "save", "wis")[2] == "-1d4"


def test_haste_and_dodge() -> None:
    haste = from_preset("haste", "c", True, None)
    assert ac_bonus([haste]) == 2
    assert roll_changes([haste], "save", "dex")[0] == ["advantage: Haste"]
    assert roll_changes([haste], "save", "wis")[0] == []
    assert attacked_with([from_preset("dodge", "me", False, None)])[1] == [
        "disadvantage: target has Dodge"
    ]


def test_hold_person_paralyzes_with_a_repeated_save() -> None:
    hold = from_preset("hold_person", "c", True, 14)
    assert hold.condition == "paralyzed" and hold.repeat_save.dc == 14


def test_effects_end_on_the_right_turn() -> None:
    shield = from_preset("shield", "me", False, None)
    other = Effect(name="Other", ending=Ending(when="end", of="someone", rounds=1))
    kept, ended = tick([shield, other], "me", "end")
    assert [e.name for e in kept] == ["Shield", "Other"] and ended == []
    kept, ended = tick(kept, "me", "start")
    assert [e.name for e in ended] == ["Shield"] and [e.name for e in kept] == ["Other"]


def test_one_minute_lasts_ten_turns() -> None:
    effects = [from_preset("bless", "c", True, None)]
    for _ in range(9):
        effects, ended = tick(effects, "c", "start")
        assert not ended
    assert tick(effects, "c", "start")[1][0].name == "Bless"


def test_concentration_dc() -> None:
    assert [concentration_dc(d) for d in (4, 22, 25, 90)] == [10, 11, 12, 30]
