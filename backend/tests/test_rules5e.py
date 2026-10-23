"""5e rules: derived values, advantage/disadvantage from conditions, critical damage."""

import pytest

from app.rules5e.data import modifier, proficiency_for_cr, proficiency_for_level
from app.rules5e.rolls import attack_outcome, critical, d20_test, natural
from app.rules5e.sheet import derive, new_sheet


@pytest.mark.parametrize(
    ("score", "mod"), [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (15, 2), (30, 10)]
)
def test_modifier_rounds_down(score: int, mod: int) -> None:
    assert modifier(score) == mod


@pytest.mark.parametrize(
    ("level", "prof"), [(1, 2), (4, 2), (5, 3), (9, 4), (13, 5), (17, 6), (20, 6)]
)
def test_proficiency_by_level(level: int, prof: int) -> None:
    assert proficiency_for_level(level) == prof


@pytest.mark.parametrize(
    ("cr", "prof"), [("0", 2), ("1/4", 2), ("4", 2), ("5", 3), ("9", 4), ("17", 6), ("30", 9)]
)
def test_proficiency_by_cr(cr: str, prof: int) -> None:
    assert proficiency_for_cr(cr) == prof


def fighter() -> dict:
    sheet = new_sheet("pc")
    sheet.update(
        level=5,
        abilities={"str": 16, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10},
        save_proficiencies=["str", "con"],
        skills={"athletics": 1, "perception": 2},
        attacks=[
            {
                "id": "a",
                "name": "Longsword",
                "ability": "str",
                "damage": "1d8",
                "damage_type": "slashing",
            },
            {"id": "b", "name": "Ogre club", "to_hit": 6, "damage": "2d8+4", "add_modifier": False},
            {
                "id": "c",
                "name": "Breath",
                "kind": "save",
                "ability": "con",
                "save": "dex",
                "damage": "4d6",
            },
        ],
        spellcasting={"ability": "wis", "slots": {}},
    )
    return sheet


def test_derived_values() -> None:
    d = derive(fighter())
    assert d["proficiency"] == 3
    assert d["modifiers"]["str"] == 3 and d["modifiers"]["int"] == -1
    assert d["saves"] == {"str": 6, "dex": 2, "con": 5, "int": -1, "wis": 1, "cha": 0}
    assert d["skills"]["athletics"] == 6 and d["skills"]["perception"] == 7  # expertise
    assert d["passive_perception"] == 17
    assert d["initiative"] == 2
    assert (d["spell_dc"], d["spell_attack"]) == (12, 4)
    assert d["attacks"]["a"] == {"to_hit": 6, "dc": None, "damage": "1d8+3"}
    assert d["attacks"]["b"]["to_hit"] == 6 and d["attacks"]["b"]["damage"] == "2d8+4"
    assert d["attacks"]["c"]["dc"] == 13


def test_npc_uses_cr_for_proficiency_and_xp() -> None:
    sheet = new_sheet("npc")
    sheet["cr"] = "1/4"
    d = derive(sheet)
    assert d["proficiency"] == 2 and d["xp"] == 50


def test_advantage_and_disadvantage_cancel() -> None:
    t = d20_test("attack", "advantage", actor=frozenset({"poisoned"}))
    assert t.mode == "normal" and "advantage and disadvantage cancel out" in t.reasons


def test_prone_target_depends_on_distance() -> None:
    assert d20_test("attack", target=frozenset({"prone"})).mode == "advantage"
    assert d20_test("attack", target=frozenset({"prone"}), within_5ft=False).mode == "disadvantage"


def test_conditions_on_checks_and_saves() -> None:
    assert d20_test("check", actor=frozenset({"frightened"})).mode == "disadvantage"
    assert d20_test("save", ability="dex", actor=frozenset({"restrained"})).mode == "disadvantage"
    stunned = d20_test("save", ability="str", actor=frozenset({"stunned"}))
    assert stunned.auto_fail == "automatic failure: stunned"
    assert d20_test("save", ability="wis", actor=frozenset({"stunned"})).auto_fail is None


def test_formula_includes_bonus_and_extra_dice() -> None:
    assert d20_test("attack", "disadvantage").formula(5, "+1d4") == "2d20kl1+5+1d4"
    assert d20_test("check").formula(0) == "1d20"


def test_critical_doubles_dice_not_modifiers() -> None:
    assert critical("1d8+3") == "2d8+3"
    assert critical("2d6+1d4+2") == "4d6+2d4+2"


def test_attack_outcome() -> None:
    assert attack_outcome(20, 5, 30, False) == "critical hit"
    assert attack_outcome(1, 30, 10, False) == "critical miss"
    assert attack_outcome(12, 15, 15, False) == "hit"
    assert attack_outcome(12, 14, 15, False) == "miss"
    assert attack_outcome(12, 15, 15, True) == "critical hit"


def test_natural_reads_the_kept_die() -> None:
    roll = {
        "terms": [{"sides": 20, "dice": [{"value": 3, "kept": False}, {"value": 17, "kept": True}]}]
    }
    assert natural(roll) == 17
