"""Combat: initiative for tokens, turn start and end, action economy, movement."""

from fastapi.testclient import TestClient

from app.game.server import server
from tests.conftest import FixedDice
from tests.test_game import WS, join, recv, token
from tests.test_hp_game import monster, pc
from tests.test_journal import create_character


def setup(gm, page: str) -> None:
    hero = pc(12)
    hero["abilities"]["dex"] = 16
    create_character(gm, "hero", name="Brom", sheet=hero)
    create_character(gm, "gob", name="Goblin", sheet=monster(7))
    gm.send_json(
        {
            "type": "obj.create",
            "objects": [
                {**token(page, "h", represents="hero", name="Brom"), "x": 35},
                {**token(page, "g1", represents="gob", name="Goblin 1"), "x": 315},
                {**token(page, "g2", represents="gob", name="Goblin 2"), "x": 385},
            ],
        }
    )
    recv(gm, "obj.upsert")


def initiative(gm, ids: list[str]) -> dict:
    gm.send_json({"type": "combat.initiative", "token_ids": ids})
    return recv(gm, "chat")["message"]


def test_initiative_groups_monsters_and_sorts(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        card = initiative(gm, ["h", "g1", "g2"])
        assert card["gm_only"] and [r[0] for r in card["roll"]["template"]["fields"]] == [
            "Brom",
            "Goblin 1, Goblin 2",
        ]
        order = server.game.turn_order
        # Same roll: Brom 10+3, goblins 10+0. Sorted, highest first; round 1.
        assert [(e["object_id"], e["value"]) for e in order] == [
            ("h", "13"),
            ("g1", "10"),
            ("g2", "10"),
        ]
        assert server.game.settings["round"] == 1


def test_turns_reset_the_action_economy(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        setup(gm, page)
        initiative(gm, ["h", "g1"])
        first = server.game.turn_order[0]["id"]
        gm.send_json({"type": "turn.use", "id": first, "what": "action"})
        recv(gm, "game")
        assert server.game.turn_order[0]["used"] == {"action": True}

        pl.send_json({"type": "turn.use", "id": first, "what": "reaction"})
        assert recv(pl, "error")["detail"] == "you do not control this entry"

        gm.send_json({"type": "turn.next"})
        recv(gm, "game")
        gm.send_json({"type": "turn.next"})
        recv(gm, "game")
        assert server.game.turn_order[0]["id"] == first
        assert server.game.turn_order[0]["used"] == {} and server.game.settings["round"] == 2


def test_movement_of_the_current_combatant(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        initiative(gm, ["h", "g1"])
        # Three squares diagonally: 15 feet with the 5e rule.
        gm.send_json({"type": "obj.update", "patches": [{"id": "h", "x": 245, "y": 245}]})
        while recv(gm, "game")["game"]["turn_order"][0].get("moved") != 15:
            pass
        assert server.game.turn_order[0]["moved"] == 15
        # Goblins moving out of turn don't count.
        gm.send_json({"type": "obj.update", "patches": [{"id": "g1", "x": 455}]})
        recv(gm, "obj.upsert")
        assert server.game.turn_order[0]["moved"] == 15


def test_a_dying_character_is_asked_for_a_death_save(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        initiative(gm, ["h", "g1"])
        gm.send_json({"type": "combat.apply", "token_ids": ["h"], "amount": 15})
        recv(gm, "chat")
        gm.send_json({"type": "turn.next"})
        recv(gm, "game")
        gm.send_json({"type": "turn.next"})
        card = recv(gm, "chat")["message"]["roll"]["template"]
        assert card["title"] == "Brom is dying"
        assert card["fields"] == [["Death save", "[Roll death save](!deathsave hero)"]]
