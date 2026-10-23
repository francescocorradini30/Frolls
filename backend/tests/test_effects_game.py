"""Effects, concentration and spells through the game server."""

from fastapi.testclient import TestClient

from app.game.server import server
from tests.conftest import FixedDice
from tests.test_game import WS, join, recv, token
from tests.test_hp_game import monster, pc
from tests.test_journal import create_character


def caster_sheet() -> dict:
    sheet = pc(20)
    sheet.update(
        level=5,
        abilities={**sheet["abilities"], "wis": 16, "con": 14},
        save_proficiencies=["con"],
        spellcasting={
            "ability": "wis",
            "slots": {"1": {"max": 2, "used": 0}, "3": {"max": 1, "used": 0}},
        },
        spells=[
            {"id": "bless", "name": "Bless", "level": 1, "concentration": True, "effect": "bless"},
            {
                "id": "fb",
                "name": "Fire Bolt",
                "level": 0,
                "attack": True,
                "damage": "1d10",
                "damage_type": "fire",
            },
            {
                "id": "ball",
                "name": "Fireball",
                "level": 3,
                "save": "dex",
                "damage": "8d6",
                "damage_type": "fire",
                "upcast": "1d6",
            },
            {
                "id": "hold",
                "name": "Hold Person",
                "level": 2,
                "save": "wis",
                "concentration": True,
                "effect": "hold_person",
            },
        ],
    )
    return sheet


def setup(gm, page: str) -> None:
    create_character(gm, "cleric", name="Cleric", sheet=caster_sheet())
    create_character(gm, "ally", name="Ally", sheet=pc(20))
    create_character(gm, "ogre", name="Ogre", sheet=monster(100, ac=11))
    gm.send_json(
        {
            "type": "obj.create",
            "objects": [
                {**token(page, "c", represents="cleric", name="Cleric"), "x": 35},
                {**token(page, "a", represents="ally", name="Ally"), "x": 105},
                {**token(page, "o", represents="ogre", name="Ogre"), "x": 175},
            ],
        }
    )
    recv(gm, "obj.upsert")


def card(gm) -> dict:
    msg = recv(gm, "chat")["message"]
    return {
        "title": msg["roll"]["template"]["title"],
        **dict(msg["roll"]["template"]["fields"]),
        "_msg": msg,
    }


def card_titled(gm, title: str) -> dict:
    """The next chat card with this title (other cards may come first)."""
    for _ in range(20):
        found = card(gm)
        if found["title"] == title:
            return found
    raise AssertionError(f"no card {title}")


def effects(oid: str) -> list[str]:
    return [e["name"] for e in server.objects[oid].props.get("effects") or []]


def statuses(oid: str) -> list[str]:
    return server.objects[oid].props.get("statuses") or []


def test_bless_from_a_spell_concentrates_and_adds_a_d4(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json(
            {
                "type": "sheet.cast",
                "character_id": "cleric",
                "spell_id": "bless",
                "token_id": "c",
                "target_ids": ["c", "a"],
            }
        )
        cast = card(gm)
        while not cast["title"].startswith("Cleric casts"):
            cast = card(gm)
        assert effects("a") == ["Bless"] and effects("c") == ["Bless"]
        assert "concentrating" in statuses("c")
        assert server.characters["cleric"].sheet["spellcasting"]["slots"]["1"]["used"] == 1
        # One concentration only: casting doesn't end it right away.
        assert server.objects["c"].props["concentrating"] == {"name": "Bless"}

        gm.send_json(
            {
                "type": "sheet.roll",
                "character_id": "ally",
                "roll": "save",
                "key": "wis",
                "token_id": "a",
            }
        )
        assert card(gm)["_msg"]["roll"]["inline"][0]["expression"] == "1d20+1d4"


def test_damage_breaks_concentration_and_its_effects(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json(
            {"type": "effect.apply", "token_ids": ["a"], "preset": "bless", "source_id": "c"}
        )
        recv(gm, "chat")
        dice.face = 2  # Constitution save 2 + 5 = 7 against DC 10
        gm.send_json({"type": "combat.apply", "token_ids": ["c"], "amount": 6})
        card_titled(gm, "Cleric loses concentration")
        assert effects("a") == [] and "concentrating" not in statuses("c")


def test_incapacitated_ends_concentration(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json(
            {"type": "effect.apply", "token_ids": ["a"], "preset": "bless", "source_id": "c"}
        )
        recv(gm, "chat")
        gm.send_json(
            {
                "type": "obj.update",
                "patches": [{"id": "c", "props": {"statuses": ["concentrating", "stunned"]}}],
            }
        )
        assert card(gm)["Why"] == "stunned" and effects("a") == []


def test_shield_raises_ac_until_the_start_of_the_next_turn(
    client: TestClient, dice: FixedDice
) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json({"type": "combat.initiative", "token_ids": ["a", "o"]})
        recv(gm, "chat")
        gm.send_json(
            {"type": "effect.apply", "token_ids": ["a"], "preset": "shield", "source_id": "a"}
        )
        recv(gm, "chat")
        assert effects("a") == ["Shield"]
        # Ally (initiative 10) then Ogre; Shield ends when the Ally's next turn starts.
        gm.send_json({"type": "turn.next"})
        recv(gm, "game")
        assert effects("a") == ["Shield"]
        gm.send_json({"type": "turn.next"})
        assert card(gm)["Ally"] == "Shield ends"
        assert effects("a") == []


def test_hold_person_on_a_failed_save_then_repeated_saves(
    client: TestClient, dice: FixedDice
) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json({"type": "combat.initiative", "token_ids": ["o", "c"]})
        recv(gm, "chat")
        dice.face = 3
        gm.send_json(
            {
                "type": "spell.saves",
                "character_id": "cleric",
                "spell_id": "hold",
                "slot": 2,
                "token_id": "c",
                "target_ids": ["o"],
            }
        )
        saves = card(gm)
        while saves["title"] != "Hold Person: saving throws":
            saves = card(gm)
        assert saves["Ogre"].startswith("Wisdom DC 14: 3 ✗ failure")
        assert effects("o") == ["Hold Person"] and "paralyzed" in statuses("o")
        # The Ogre's turn ends: it repeats the save and shakes it off.
        dice.face = 20
        order = [e["object_id"] for e in server.game.turn_order]
        if order[0] != "o":
            gm.send_json({"type": "turn.next"})
            recv(gm, "game")
        gm.send_json({"type": "turn.next"})
        repeat = card(gm)
        while repeat["title"] != "Effects":
            repeat = card(gm)
        assert "it ends" in repeat["Ogre"]
        assert effects("o") == [] and "paralyzed" not in statuses("o")


def test_fireball_uses_a_slot_and_halves_on_a_success(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json(
            {
                "type": "sheet.cast",
                "character_id": "cleric",
                "spell_id": "ball",
                "token_id": "c",
                "target_ids": ["o", "a"],
            }
        )
        cast = card(gm)
        assert cast["Save"] == "DC 14 Dexterity" and "!saves cleric ball 3 c o,a" in cast["Targets"]
        gm.send_json(
            {"type": "sheet.cast", "character_id": "cleric", "spell_id": "ball", "token_id": "c"}
        )
        assert recv(gm, "error")["detail"] == "no level 3 spell slots left"

        dice.face = 14  # d6s show 6 (48 damage); saves: 14 + 0 = 14 succeeds
        gm.send_json(
            {
                "type": "spell.saves",
                "character_id": "cleric",
                "spell_id": "ball",
                "slot": 3,
                "token_id": "c",
                "target_ids": ["o"],
            }
        )
        saves = card(gm)
        while saves["title"] != "Fireball: saving throws":
            saves = card(gm)
        assert "success → 24 damage" in saves["Ogre"]
        assert server.objects["o"].props["bar1"]["value"] == 76


def test_cantrips_grow_with_level(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        dice.face = 15
        gm.send_json(
            {
                "type": "sheet.cast",
                "character_id": "cleric",
                "spell_id": "fb",
                "token_id": "c",
                "target_ids": ["o"],
            }
        )
        cast = card(gm)
        # Level 5: two d10; with every die on 10 → 20 fire damage.
        assert cast["_msg"]["roll"]["inline"][1]["expression"] == "2d10"
