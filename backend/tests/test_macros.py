"""Macro expansion, without the game server."""

import pytest

from app.game.macros import MacroError, NeedTarget, expand


class FakeResolver:
    def __init__(self) -> None:
        self.macros = {
            "Attack": "/r 1d20+@{selected|str}",
            "Loop": "#Loop",
            "Twice": "#Attack #Attack",
        }
        self.characters = {
            "c1": {
                "name": "Thorin",
                "attributes": {"str": ("3", "5"), "hp": ("12", "20")},
                "abilities": {"Axe": "/r 1d8+@{str}", "Ask": "?{Bonus|2}"},
            }
        }
        self.selected = "c1"
        self.target: str | None = None

    def _character(self, ref: str) -> str:
        if ref == "selected":
            return self.selected
        if ref == "target":
            if self.target is None:
                raise NeedTarget
            return self.target
        if ref.startswith("\x01"):
            return ref[1:]
        for cid, c in self.characters.items():
            if c["name"] == ref:
                return cid
        raise MacroError(f'no character named "{ref}"')

    def macro(self, name: str) -> str | None:
        return self.macros.get(name)

    def ability(self, ref: str, name: str) -> tuple[str, str]:
        cid = self._character(ref)
        return self.characters[cid]["abilities"][name], cid

    def attribute(self, ref: str, name: str, use_max: bool) -> str:
        current, maximum = self.characters[self._character(ref)]["attributes"][name]
        return maximum if use_max else current


def test_plain_text_is_unchanged() -> None:
    assert expand("hello C# and #nomacro", FakeResolver()).text == "hello C# and #nomacro"


def test_attributes_by_name_selected_and_max() -> None:
    r = FakeResolver()
    assert expand("@{Thorin|hp}/@{selected|hp|max}", r).text == "12/20"


def test_macro_expands_recursively() -> None:
    assert expand("#Twice", FakeResolver()).text == "/r 1d20+3 /r 1d20+3"


def test_ability_binds_bare_attributes_to_its_character() -> None:
    assert expand("%{Thorin|Axe}", FakeResolver()).text == "/r 1d8+3"


def test_bare_attribute_outside_an_ability_is_an_error() -> None:
    with pytest.raises(MacroError, match="needs a character"):
        expand("@{str}", FakeResolver())


def test_infinite_macro_loop_is_stopped() -> None:
    with pytest.raises(MacroError, match="too many times"):
        expand("#Loop", FakeResolver())


def test_queries_are_asked_once_and_then_substituted() -> None:
    r = FakeResolver()
    text = "/r 1d20+?{Bonus|2} and ?{Bonus|2} ?{Mode|Normal,1d20|Advantage,2d20kh1}"
    asked = expand(text, r)
    assert [q.as_dict() for q in asked.queries] == [
        {"prompt": "Bonus", "default": "2", "options": []},
        {
            "prompt": "Mode",
            "default": "1d20",
            "options": [("Normal", "1d20"), ("Advantage", "2d20kh1")],
        },
    ]
    assert expand(text, r, ["4", "2d20kh1"]).text == "/r 1d20+4 and 4 2d20kh1"


def test_queries_inside_abilities_are_found() -> None:
    assert [q.prompt for q in expand("%{selected|Ask}", FakeResolver()).queries] == ["Bonus"]


def test_target_must_be_picked_first() -> None:
    r = FakeResolver()
    with pytest.raises(NeedTarget):
        expand("@{target|hp}", r)
    r.target = "c1"
    assert expand("@{target|hp}", r).text == "12"


def test_buttons_are_not_expanded() -> None:
    text = "[Swing](~Thorin|Axe) [Again](#Attack)"
    assert expand(text, FakeResolver()).text == text
