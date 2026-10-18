from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.game.server import server

WS = "/ws/game"


def recv(ws: WebSocketTestSession, type_: str) -> dict[str, Any]:
    """Skip messages until one of the given type arrives."""
    for _ in range(50):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg
    raise AssertionError(f"no {type_} message")


def join(ws: WebSocketTestSession, pid: str, name: str, gm: bool = False) -> dict[str, Any]:
    ws.send_json(
        {"type": "hello", "player": {"id": pid, "name": name, "color": "#aa3355", "is_gm": gm}}
    )
    welcome = recv(ws, "welcome")
    snapshot = recv(ws, "page.snapshot")
    return {"welcome": welcome, "snapshot": snapshot, "page_id": snapshot["page"]["id"]}


def token(page_id: str, oid: str = "t1", layer: str = "objects", **props: Any) -> dict[str, Any]:
    return {
        "id": oid,
        "page_id": page_id,
        "kind": "token",
        "layer": layer,
        "x": 35,
        "y": 35,
        "props": {"name": "Goblin", **props},
    }


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_hello_requires_first(client: TestClient) -> None:
    with client.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat.send", "text": "hi"})
        assert recv(ws, "error")["detail"] == "send hello first"


def test_welcome_creates_default_page(client: TestClient) -> None:
    with client.websocket_connect(WS) as ws:
        state = join(ws, "gm", "Master", gm=True)
        assert len(state["welcome"]["pages"]) == 1
        assert state["snapshot"]["objects"] == []


def test_rejoin_with_same_name_reuses_offline_player(client: TestClient) -> None:
    with client.websocket_connect(WS) as ws:
        join(ws, "a1", "Aria")
    with client.websocket_connect(WS) as ws:
        state = join(ws, "a2", " aria ")
        assert state["welcome"]["you"]["id"] == "a1"
        assert [p["id"] for p in state["welcome"]["players"]] == ["a1"]
        # Same name while the first one is online: a different player.
        with client.websocket_connect(WS) as ws2:
            other = join(ws2, "a3", "Aria")
            assert other["welcome"]["you"]["id"] == "a3"


def test_gm_creates_token_and_player_sees_it(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        got = recv(pl, "obj.upsert")["objects"][0]
        assert got["id"] == "t1" and got["props"]["name"] == "Goblin"


def test_state_persists_across_restart(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")

    # Simulate a server restart: wipe memory, reload from Postgres.
    server.__init__()
    with client.websocket_connect(WS) as gm:
        objs = join(gm, "gm", "Master", gm=True)["snapshot"]["objects"]
        assert [o["id"] for o in objs] == ["t1"]


def test_gm_layer_hidden_from_players(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, "secret", layer="gm")]})
        gm.send_json({"type": "obj.create", "objects": [token(page, "visible")]})
        # Player only ever receives the visible one.
        assert [o["id"] for o in recv(pl, "obj.upsert")["objects"]] == ["visible"]

        gm.send_json({"type": "obj.update", "patches": [{"id": "visible", "layer": "gm"}]})
        assert recv(pl, "obj.removed")["ids"] == ["visible"]


def test_gm_notes_hidden_from_players(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, gm_notes="trappola")]})
        assert "gm_notes" not in recv(pl, "obj.upsert")["objects"][0]["props"]
        assert recv(gm, "obj.upsert")["objects"][0]["props"]["gm_notes"] == "trappola"


def test_player_cannot_move_uncontrolled_token(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(pl, "obj.upsert")
        pl.send_json({"type": "obj.update", "patches": [{"id": "t1", "x": 500}]})
        assert recv(pl, "error")["detail"] == "you do not control this object"


def test_player_moves_controlled_token(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, controlled_by=["p1"])]})
        recv(gm, "obj.upsert")
        recv(pl, "obj.upsert")

        pl.send_json({"type": "obj.preview", "items": [{"id": "t1", "x": 100, "y": 100}]})
        assert recv(gm, "obj.preview")["items"] == [{"id": "t1", "x": 100, "y": 100}]

        pl.send_json({"type": "obj.update", "patches": [{"id": "t1", "x": 105, "y": 175}]})
        moved = recv(gm, "obj.upsert")["objects"][0]
        assert (moved["x"], moved["y"]) == (105, 175)


def test_player_cannot_change_permissions(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, controlled_by=["p1"])]})
        recv(pl, "obj.upsert")
        pl.send_json(
            {"type": "obj.update", "patches": [{"id": "t1", "props": {"controlled_by": ["all"]}}]}
        )
        assert "permissions" in recv(pl, "error")["detail"]


def test_props_patch_merges_and_null_removes(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page, bar1={"value": 7, "max": 7})]})
        recv(gm, "obj.upsert")
        gm.send_json(
            {"type": "obj.update", "patches": [{"id": "t1", "props": {"bar1": None, "aura": 2}}]}
        )
        props = recv(gm, "obj.upsert")["objects"][0]["props"]
        assert props == {"name": "Goblin", "aura": 2}


def test_player_draws_and_deletes_own_path(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        path = {"id": "d1", "page_id": page, "kind": "path", "x": 0, "y": 0, "props": {}}
        pl.send_json({"type": "obj.create", "objects": [path]})
        recv(gm, "obj.upsert")
        pl.send_json({"type": "obj.delete", "ids": ["d1"]})
        assert recv(gm, "obj.removed")["ids"] == ["d1"]


def test_player_cannot_create_token(client: TestClient) -> None:
    with client.websocket_connect(WS) as pl:
        page = join(pl, "p1", "Aria")["page_id"]
        pl.send_json({"type": "obj.create", "objects": [token(page)]})
        assert recv(pl, "error")["detail"] == "you cannot create this object"


def test_pages_and_moving_players(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        first = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "page.create", "page": {"name": "Dungeon"}})
        new_id = recv(gm, "page.created")["id"]

        gm.send_json({"type": "game.player_page", "page_id": new_id})
        snap = recv(pl, "page.snapshot")
        assert snap["page"]["name"] == "Dungeon"

        # Players cannot peek at other pages.
        pl.send_json({"type": "page.view", "page_id": first})
        assert recv(pl, "error")["detail"] == "you cannot see this page"


def test_move_single_player_to_page(client: TestClient) -> None:
    with (
        client.websocket_connect(WS) as gm,
        client.websocket_connect(WS) as a,
        client.websocket_connect(WS) as b,
    ):
        join(gm, "gm", "Master", gm=True)
        start = join(a, "pa", "Aria")["page_id"]
        join(b, "pb", "Bruno")
        gm.send_json({"type": "page.create", "page": {"name": "Cell"}})
        cell = recv(gm, "page.created")["id"]
        gm.send_json({"type": "game.player_page", "page_id": cell, "player_id": "pb"})
        assert recv(b, "page.snapshot")["page"]["id"] == cell
        a.send_json({"type": "page.view", "page_id": start})
        assert recv(a, "page.snapshot")["page"]["id"] == start


def test_chat_auto_dice(client: TestClient) -> None:
    with client.websocket_connect(WS) as a, client.websocket_connect(WS) as b:
        join(a, "pa", "Aria")
        join(b, "pb", "Bruno")
        a.send_json({"type": "chat.send", "text": "2d6+3"})
        msg = recv(b, "chat")["message"]
        assert msg["kind"] == "roll"
        assert 5 <= msg["roll"]["main"]["total"] <= 15


def test_chat_text_with_inline_roll(client: TestClient) -> None:
    with client.websocket_connect(WS) as a:
        join(a, "pa", "Aria")
        a.send_json({"type": "chat.send", "text": "I hit for [[1d8+2]] damage"})
        msg = recv(a, "chat")["message"]
        assert msg["kind"] == "text"
        assert msg["content"] == "I hit for [[#0]] damage"
        assert 3 <= msg["roll"]["inline"][0]["total"] <= 10


def test_whisper_only_reaches_target(client: TestClient) -> None:
    with (
        client.websocket_connect(WS) as a,
        client.websocket_connect(WS) as b,
        client.websocket_connect(WS) as c,
    ):
        join(a, "pa", "Aria")
        join(b, "pb", "Bruno")
        join(c, "pc", "Carla")
        a.send_json({"type": "chat.send", "text": "/w Bruno segreto"})
        a.send_json({"type": "chat.send", "text": "pubblico"})
        assert recv(b, "chat")["message"]["content"] == "segreto"
        # Carla's first chat message is the public one.
        assert recv(c, "chat")["message"]["content"] == "pubblico"


def test_gm_roll_hidden_from_other_players(client: TestClient) -> None:
    with (
        client.websocket_connect(WS) as gm,
        client.websocket_connect(WS) as a,
        client.websocket_connect(WS) as b,
    ):
        join(gm, "gm", "Master", gm=True)
        join(a, "pa", "Aria")
        join(b, "pb", "Bruno")
        a.send_json({"type": "chat.send", "text": "/gr 1d20"})
        a.send_json({"type": "chat.send", "text": "later"})
        assert recv(gm, "chat")["message"]["gm_only"] is True
        assert recv(b, "chat")["message"]["content"] == "later"


def test_chat_history_on_join(client: TestClient) -> None:
    with client.websocket_connect(WS) as a:
        join(a, "pa", "Aria")
        a.send_json({"type": "chat.send", "text": "primo"})
        recv(a, "chat")
    with client.websocket_connect(WS) as b:
        history = join(b, "pb", "Bruno")["welcome"]["chat"]
        assert [m["content"] for m in history] == ["primo"]


def test_bad_command_returns_error(client: TestClient) -> None:
    with client.websocket_connect(WS) as a:
        join(a, "pa", "Aria")
        a.send_json({"type": "chat.send", "text": "/desc narro"})
        assert recv(a, "error")["detail"] == "Only the GM can use /desc"


def test_turn_order_flow(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, "hero", controlled_by=["p1"])]})
        gm.send_json({"type": "obj.create", "objects": [token(page, "orc")]})
        recv(pl, "obj.upsert")

        pl.send_json(
            {"type": "turn.add", "entry": {"id": "e1", "object_id": "hero", "value": "12"}}
        )
        gm.send_json({"type": "turn.add", "entry": {"id": "e2", "object_id": "orc", "value": "18"}})
        gm.send_json({"type": "turn.sort"})
        order = None
        for _ in range(3):
            order = recv(pl, "game")["game"]["turn_order"]
        assert order is not None and [e["id"] for e in order] == ["e2", "e1"]

        # Not Aria's turn yet.
        pl.send_json({"type": "turn.next"})
        assert recv(pl, "error")["detail"] == "it is not your turn"

        gm.send_json({"type": "turn.next"})
        game = recv(pl, "game")["game"]
        assert [e["id"] for e in game["turn_order"]] == ["e1", "e2"]
        pl.send_json({"type": "turn.next"})
        game = recv(pl, "game")["game"]
        assert game["settings"]["round"] == 2


def test_deleting_token_removes_turn_entry(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        gm.send_json({"type": "turn.add", "entry": {"id": "e1", "object_id": "t1", "value": "5"}})
        recv(gm, "game")
        gm.send_json({"type": "obj.delete", "ids": ["t1"]})
        assert recv(gm, "game")["game"]["turn_order"] == []


def test_ping_reaches_page_viewers(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "ping", "page_id": page, "x": 10, "y": 20, "pull": True})
        ping = recv(pl, "ping")
        assert (ping["x"], ping["y"], ping["pull"]) == (10, 20, True)


def test_order_to_front(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page, "a"), token(page, "b")]})
        recv(gm, "obj.upsert")
        gm.send_json({"type": "obj.order", "ids": ["a"], "to": "front"})
        moved = recv(gm, "obj.upsert")["objects"][0]
        assert moved["id"] == "a" and moved["z"] == 3


def test_duplicate_page_copies_objects(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")
        gm.send_json({"type": "page.duplicate", "id": page})
        copy_id = recv(gm, "page.created")["id"]
        gm.send_json({"type": "page.view", "page_id": copy_id})
        objs = recv(gm, "page.snapshot")["objects"]
        assert len(objs) == 1 and objs[0]["id"] != "t1"


def test_delete_page_moves_players(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        first = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "page.create", "page": {"name": "Due"}})
        second = recv(gm, "page.created")["id"]
        gm.send_json({"type": "game.player_page", "page_id": second})
        recv(pl, "page.snapshot")
        gm.send_json({"type": "page.delete", "id": second})
        assert recv(pl, "page.snapshot")["page"]["id"] == first


def test_invalid_message(client: TestClient) -> None:
    with client.websocket_connect(WS) as a:
        a.send_json({"type": "nope"})
        assert recv(a, "error")["detail"].startswith("invalid message")


def test_upload_rejects_non_image(client: TestClient) -> None:
    r = client.post("/api/assets", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 415


def test_upload_image(client: TestClient) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    r = client.post("/api/assets", files={"file": ("a.png", png, "image/png")})
    assert r.status_code == 200
    assert client.get(r.json()["url"]).content == png


def test_turn_entry_hidden_when_token_moves_to_gm_layer(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        gm.send_json({"type": "turn.add", "entry": {"id": "e1", "object_id": "t1", "value": "5"}})
        assert len(recv(pl, "game")["game"]["turn_order"]) == 1
        gm.send_json({"type": "obj.update", "patches": [{"id": "t1", "layer": "gm"}]})
        assert recv(pl, "game")["game"]["turn_order"] == []


def test_hello_survives_player_row_unknown_to_memory(client: TestClient) -> None:
    """Another process (or a restart race) may have inserted the player already."""
    with client.websocket_connect(WS) as a:
        join(a, "pa", "Aria")
    server.players.clear()
    with client.websocket_connect(WS) as a:
        assert join(a, "pa", "Aria Due")["welcome"]["you"]["name"] == "Aria Due"


def test_player_settings_are_private_and_persist(client: TestClient) -> None:
    with client.websocket_connect(WS) as a, client.websocket_connect(WS) as b:
        join(a, "pa", "Aria")
        join(b, "pb", "Bruno")
        a.send_json({"type": "player.update", "settings": {"wheel": "pan"}})
        a.send_json({"type": "player.update", "settings": {"chat_timestamps": False}})
        # Name changes are news for everyone, settings are not.
        a.send_json({"type": "player.update", "name": "Aria the Ranger"})
        for _ in range(5):
            players = recv(b, "players")["players"]
            assert all("settings" not in p for p in players)
            if any(p["name"] == "Aria the Ranger" for p in players):
                break
        else:
            raise AssertionError("rename not broadcast")
    with client.websocket_connect(WS) as a:
        you = join(a, "pa", "Aria the Ranger")["welcome"]["you"]
        assert you["settings"] == {"wheel": "pan", "chat_timestamps": False}


def test_metric_is_the_default_measurement(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        state = join(gm, "gm", "Master", gm=True)
        assert state["welcome"]["game"]["settings"]["measurement"] == "metric"
        page = state["snapshot"]["page"]
        assert (page["scale_number"], page["scale_unit"]) == (1.5, "m")


def test_measurement_switch_converts_pages_and_auras(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page_id = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        aura = {"radius": 3, "color": "#ffdb7a"}
        gm.send_json({"type": "obj.create", "objects": [token(page_id, aura1=aura)]})
        recv(gm, "obj.upsert")

        pl.send_json({"type": "game.settings", "measurement": "imperial"})
        assert recv(pl, "error")["detail"] == "only the GM can do that"

        gm.send_json({"type": "game.settings", "measurement": "imperial"})
        assert recv(pl, "game")["game"]["settings"]["measurement"] == "imperial"
        page = recv(pl, "page.updated")["page"]
        assert (page["scale_number"], page["scale_unit"]) == (5, "ft")
        obj = recv(pl, "obj.upsert")["objects"][0]
        assert obj["props"]["aura1"]["radius"] == 10

        # New pages follow the system; switching back restores the metric values.
        gm.send_json({"type": "page.create", "page": {"name": "Dungeon"}})
        new_id = recv(gm, "page.created")["id"]
        assert server.pages[new_id].scale_unit == "ft"
        gm.send_json({"type": "game.settings", "measurement": "metric"})
        recv(gm, "game")
        assert (server.pages[page_id].scale_number, server.pages[page_id].scale_unit) == (1.5, "m")
        assert server.objects["t1"].props["aura1"]["radius"] == 3
