"""Event log: sequence numbers, resume after reconnect, undo/redo and the GM history."""

from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.game.server import server
from tests.test_game import WS, join, recv, token


def hello(ws: WebSocketTestSession, pid: str, name: str, gm: bool = False, **extra: Any) -> None:
    ws.send_json(
        {
            "type": "hello",
            "player": {"id": pid, "name": name, "color": "#aa3355", "is_gm": gm},
            **extra,
        }
    )


def move(ws: WebSocketTestSession, oid: str, x: float) -> dict[str, Any]:
    ws.send_json({"type": "obj.update", "patches": [{"id": oid, "x": x}]})
    return recv(ws, "obj.upsert")


def test_every_message_carries_the_last_seq(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        state = join(gm, "gm", "Master", gm=True)
        assert state["welcome"]["seq"] == 0
        gm.send_json({"type": "obj.create", "objects": [token(state["page_id"])]})
        assert recv(gm, "obj.upsert")["seq"] == 1
        assert move(gm, "t1", 105)["seq"] == 2


def test_events_are_saved_with_author_and_summary(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")
        move(gm, "t1", 105)
        gm.send_json({"type": "history.get"})
        events = recv(gm, "history")["events"]
    assert [(e["seq"], e["player_id"], e["summary"]) for e in events] == [
        (1, "gm", 'created token "Goblin"'),
        (2, "gm", 'moved token "Goblin"'),
    ]
    assert all(e["revertible"] and not e["reverted"] for e in events)


def test_seq_survives_a_restart(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")
    server.__init__()
    with client.websocket_connect(WS) as gm:
        assert join(gm, "gm", "Master", gm=True)["welcome"]["seq"] == 1


def test_undo_and_redo_a_move(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")
        move(gm, "t1", 105)
        assert recv(gm, "undo.state") == {
            "type": "undo.state",
            "undo": 'moved token "Goblin"',
            "redo": None,
            "seq": 2,
        }

        gm.send_json({"type": "undo"})
        assert recv(gm, "obj.upsert")["objects"][0]["x"] == 35
        assert recv(gm, "undo.state")["redo"] == 'moved token "Goblin"'
        assert recv(gm, "notice")["detail"] == 'Undone: moved token "Goblin"'

        gm.send_json({"type": "redo"})
        assert recv(gm, "obj.upsert")["objects"][0]["x"] == 105
        assert server.objects["t1"].x == 105


def test_multi_object_change_is_one_step(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page, "a"), token(page, "b")]})
        recv(gm, "obj.upsert")
        gm.send_json(
            {"type": "obj.update", "patches": [{"id": "a", "x": 200}, {"id": "b", "x": 300}]}
        )
        recv(gm, "obj.upsert")
        gm.send_json({"type": "undo"})
        assert recv(gm, "notice")["detail"] == "Undone: moved 2 tokens"
        assert (server.objects["a"].x, server.objects["b"].x) == (35, 35)


def test_undo_delete_restores_the_object(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, hp=7)]})
        recv(pl, "obj.upsert")
        gm.send_json({"type": "obj.delete", "ids": ["t1"]})
        assert recv(pl, "obj.removed")["ids"] == ["t1"]

        gm.send_json({"type": "undo"})
        back = recv(pl, "obj.upsert")["objects"][0]
        assert back["id"] == "t1" and back["props"]["hp"] == 7

        # Undoing the creation removes it again.
        gm.send_json({"type": "undo"})
        assert recv(pl, "obj.removed")["ids"] == ["t1"]
        assert "t1" not in server.objects


def test_undo_skips_objects_changed_by_someone_else(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, controlled_by=["p1"])]})
        recv(pl, "obj.upsert")
        move(pl, "t1", 105)
        move(gm, "t1", 175)

        pl.send_json({"type": "undo"})
        assert (
            recv(pl, "error")["detail"]
            == 'cannot undo: token "Goblin" was changed since, so it was skipped'
        )
        assert server.objects["t1"].x == 175
        # The stale step is gone: the next Ctrl+Z does not hit it again.
        pl.send_json({"type": "undo"})
        assert recv(pl, "error")["detail"] == "nothing to undo"


def test_players_undo_only_their_own_changes(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(pl, "obj.upsert")
        pl.send_json({"type": "undo"})
        assert recv(pl, "error")["detail"] == "nothing to undo"
        assert "t1" in server.objects


def test_new_change_clears_redo(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        recv(gm, "obj.upsert")
        move(gm, "t1", 105)
        gm.send_json({"type": "undo"})
        recv(gm, "notice")
        move(gm, "t1", 140)
        gm.send_json({"type": "redo"})
        assert recv(gm, "error")["detail"] == "nothing to redo"


def test_gm_reverts_a_player_change_from_history(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, controlled_by=["p1"])]})
        recv(pl, "obj.upsert")
        move(pl, "t1", 105)
        added = recv(gm, "history.add")
        while added["event"]["player_id"] != "p1":
            added = recv(gm, "history.add")
        seq = added["event"]["seq"]

        # Players cannot open the history.
        pl.send_json({"type": "history.get"})
        assert recv(pl, "error")["detail"] == "only the GM can do that"

        gm.send_json({"type": "event.revert", "seq": seq})
        assert recv(pl, "obj.upsert")["objects"][0]["x"] == 35
        update = recv(gm, "history.update")
        assert (update["event_seq"], update["reverted"]) == (seq, True)
        # The player's step is gone: nothing left for them to undo.
        assert recv(pl, "undo.state")["undo"] is None

        gm.send_json({"type": "event.revert", "seq": seq})
        assert recv(gm, "error")["detail"] == "this change was already reverted"


def test_resume_sends_only_what_changed(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        objs = [token(page, f"t{i}") for i in range(5)]
        gm.send_json({"type": "obj.create", "objects": objs})
        recv(gm, "obj.upsert")
        move(gm, "t0", 70)
        gm.send_json({"type": "chat.send", "text": "before"})
        before = recv(gm, "chat")

        with client.websocket_connect(WS) as pl:
            state = join(pl, "p1", "Aria")
            last_seq = state["snapshot"]["seq"]
            assert len(state["snapshot"]["objects"]) == 5

        # While the player is away.
        move(gm, "t1", 105)
        gm.send_json({"type": "obj.delete", "ids": ["t2"]})
        recv(gm, "obj.removed")
        gm.send_json({"type": "chat.send", "text": "while away"})
        recv(gm, "chat")

        with client.websocket_connect(WS) as pl:
            resume = {"seq": last_seq, "page_id": page, "chat_id": before["message"]["id"]}
            hello(pl, "p1", "Aria", resume=resume)
            welcome = recv(pl, "welcome")
            assert welcome["resumed"] and welcome["chat_mode"] == "append"
            assert [m["content"] for m in welcome["chat"]] == ["while away"]
            delta = pl.receive_json()
            assert delta["type"] == "page.resume"
            # From the last event the client saw, included: it may have lost part of it.
            assert [o["id"] for o in delta["objects"]] == ["t0", "t1"]
            assert delta["removed"] == ["t2"]


def test_resume_falls_back_to_snapshot_after_restart(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        gm.send_json({"type": "obj.create", "objects": [token(page)]})
        seq = recv(gm, "obj.upsert")["seq"]
    server.__init__()
    with client.websocket_connect(WS) as gm:
        hello(gm, "gm", "Master", gm=True, resume={"seq": seq, "page_id": page})
        assert recv(gm, "welcome")["resumed"] is False
        assert gm.receive_json()["type"] == "page.snapshot"


def test_player_cannot_resume_on_a_page_they_cannot_see(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        gm.send_json({"type": "page.create"})
        other = recv(gm, "page.created")["id"]
        seq = server.seq
        with client.websocket_connect(WS) as pl:
            hello(pl, "p1", "Aria", resume={"seq": seq, "page_id": other})
            assert recv(pl, "welcome")["resumed"] is False
            assert pl.receive_json()["page"]["id"] != other
