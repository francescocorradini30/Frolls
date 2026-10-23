"""Macros, abilities, attribute calls, roll queries and roll templates through the game server."""

from fastapi.testclient import TestClient

from tests.test_game import WS, join, recv, token
from tests.test_journal import create_character


def say(ws, text: str, **extra) -> dict:
    ws.send_json({"type": "chat.send", "text": text, **extra})
    return recv(ws, "chat")["message"]


def test_macros_are_private_and_run_with_hash(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        welcome = join(pl, "p1", "Aria")["welcome"]
        assert welcome["macros"] == []
        pl.send_json(
            {
                "type": "macro.create",
                "id": "m1",
                "name": "Big hit",
                "action": "/r 2d6+3",
                "in_bar": True,
            }
        )
        got = recv(pl, "macro.upsert")["macros"][0]
        assert got == {"id": "m1", "name": "Big_hit", "action": "/r 2d6+3", "in_bar": True}

        assert say(pl, "#Big_hit")["roll"]["main"]["expression"] == "2d6+3"
        recv(gm, "chat")  # the GM sees the player's roll too
        # The GM has no such macro: the text stays text.
        assert say(gm, "#Big_hit")["content"] == "#Big_hit"
        gm.send_json({"type": "macro.delete", "id": "m1"})
        assert recv(gm, "error")["detail"] == "macro does not exist"


def test_selected_token_bars_and_character_attributes(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(
            gm,
            "hero",
            attributes=[{"name": "str", "current": "3", "max": ""}],
            abilities=[{"name": "Axe", "action": "/r 1d8+@{str}", "token_action": True}],
        )
        hp = {"value": 12, "max": 20}
        gm.send_json({"type": "obj.create", "objects": [token(page, represents="hero", bar1=hp)]})
        recv(gm, "obj.upsert")

        msg = say(gm, "HP [[@{selected|hp}]] of [[@{selected|hp|max}]]", selected_id="t1")
        assert [r["total"] for r in msg["roll"]["inline"]] == [12, 20]
        axe = say(gm, "%{selected|Axe}", selected_id="t1")["roll"]["main"]
        assert axe["expression"] == "1d8+3"

        gm.send_json({"type": "chat.send", "text": "@{selected|hp}"})
        assert recv(gm, "error")["detail"] == "select a token first"


def test_queries_round_trip(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        text = "/r 1d20+?{Bonus|2}"
        gm.send_json({"type": "chat.send", "text": text, "rid": "q1"})
        needs = recv(gm, "chat.needs")
        assert needs["rid"] == "q1" and needs["queries"][0]["prompt"] == "Bonus"
        assert say(gm, text, answers=["5"])["roll"]["main"]["expression"] == "1d20+5"


def test_target_round_trip(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page, bar1={"value": 7, "max": 7})]})
        recv(gm, "obj.upsert")
        gm.send_json({"type": "chat.send", "text": "[[@{target|hp}]]"})
        assert recv(gm, "chat.needs")["target"] is True
        assert say(gm, "[[@{target|hp}]]", target_id="t1")["roll"]["inline"][0]["total"] == 7


def test_players_cannot_read_characters_they_do_not_play(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        create_character(
            gm, "villain", name="Strahd", attributes=[{"name": "ac", "current": "16", "max": ""}]
        )
        gm.send_json({"type": "obj.create", "objects": [token(page, represents="villain")]})
        recv(pl, "obj.upsert")
        pl.send_json({"type": "chat.send", "text": "@{Strahd|ac}"})
        assert recv(pl, "error")["detail"] == 'no character named "Strahd"'
        pl.send_json({"type": "chat.send", "text": "@{target|ac}", "target_id": "t1"})
        assert recv(pl, "error")["detail"] == 'no character named "target"'
        # Token fields everyone sees are fine.
        assert say(pl, "@{target|token_name}", target_id="t1")["content"] == "Goblin"


def test_roll_template_and_buttons(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        msg = say(
            gm,
            "&{template:default} {{name=Longsword}} {{Attack=[[1d20+5]]}} "
            "{{Damage=[[1d8+3]] [Again](~Thorin|Axe)}}",
        )
        template = msg["roll"]["template"]
        assert template["title"] == "Longsword"
        assert template["fields"] == [
            ["Attack", "[[#0]]"],
            ["Damage", "[[#1]] [Again](~Thorin|Axe)"],
        ]
        assert len(msg["roll"]["inline"]) == 2 and msg["content"] == ""
