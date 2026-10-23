"""Three-way merge used to undo combat actions after the game went on."""

from app.game.merge import diff_props, revert


def test_untouched_value_goes_back() -> None:
    assert revert(20, 11, 11) == (20, [])
    assert revert("a", "b", "b") == ("a", [])


def test_numbers_move_back_by_the_difference() -> None:
    # Hit for 9 (20 -> 11), healed 4 since (15): undo gives 24 (the caller clamps it).
    assert revert(20, 11, 15) == (24, [])
    assert revert(
        {"current": 20, "max": 30}, {"current": 11, "max": 30}, {"current": 15, "max": 30}
    ) == (
        {"current": 24, "max": 30},
        [],
    )


def test_effects_by_id() -> None:
    bless = {"id": "e1", "name": "Bless"}
    hex_ = {"id": "e2", "name": "Hex"}
    prone = {"id": "e3", "name": "Prone"}
    # The action added Hex and removed Bless (concentration); Prone arrived later.
    value, conflicts = revert([bless], [hex_], [hex_, prone])
    assert value == [prone, bless] and conflicts == []


def test_statuses_as_sets() -> None:
    value, _ = revert(["poisoned"], ["poisoned", "prone"], ["poisoned", "prone", "blinded"])
    assert value == ["poisoned", "blinded"]
    value, _ = revert(["concentrating"], [], ["prone"])
    assert value == ["prone", "concentrating"]


def test_keys_created_by_the_action_go_away() -> None:
    assert revert(None, ["prone"], ["prone"]) == (None, [])
    value, _ = revert(None, ["prone"], ["prone", "blinded"])
    assert value == ["blinded"]
    assert revert(None, {"name": "Bless"}, {"name": "Bless"}) == (None, [])


def test_changed_scalars_are_conflicts() -> None:
    value, conflicts = revert({"name": "Bless"}, None, {"name": "Hex"}, "concentrating")
    assert value == {"name": "Hex"} and conflicts == ["concentrating.name"]
    assert revert(True, False, None) == (None, ["value"])


def test_redo_is_the_swapped_merge() -> None:
    # Undo of 20 -> 11 gave 20; redo applies the hit again on whatever is there.
    assert revert(11, 20, 18) == (9, [])


def test_props_diff_keeps_only_changed_keys() -> None:
    before = {"name": "Goblin", "bar1": {"value": 7}, "statuses": ["prone"]}
    after = {"name": "Goblin", "bar1": {"value": 2}}
    assert diff_props(before, after) == (
        {"bar1": {"value": 7}, "statuses": ["prone"]},
        {"bar1": {"value": 2}, "statuses": None},
    )
