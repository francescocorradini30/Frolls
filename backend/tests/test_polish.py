"""Map polish: locked objects, waypoints, map pins."""

from fastapi.testclient import TestClient

from app.game.server import server
from tests.conftest import FixedDice
from tests.test_combat_game import initiative, setup
from tests.test_game import WS, join, recv, token


def test_locked_objects_do_not_move(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json({"type": "obj.create", "objects": [token(page, controlled_by=["p1"])]})
        recv(pl, "obj.upsert")
        pl.send_json({"type": "obj.update", "patches": [{"id": "t1", "props": {"locked": True}}]})
        recv(pl, "obj.upsert")

        pl.send_json({"type": "obj.update", "patches": [{"id": "t1", "x": 400}]})
        assert recv(pl, "error")["detail"] == "it is locked: unlock it first"
        gm.send_json({"type": "obj.update", "patches": [{"id": "t1", "rotation": 90}]})
        assert recv(gm, "error")["detail"] == "it is locked: unlock it first"
        # Other changes are fine, and so is unlocking while moving.
        pl.send_json({"type": "obj.update", "patches": [{"id": "t1", "props": {"name": "X"}}]})
        assert recv(pl, "obj.upsert")["objects"][0]["props"]["name"] == "X"
        pl.send_json(
            {"type": "obj.update", "patches": [{"id": "t1", "x": 400, "props": {"locked": None}}]}
        )
        assert recv(pl, "obj.upsert")["objects"][0]["x"] == 400


def test_movement_follows_the_waypoints(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        initiative(gm, ["h", "g1"])
        start = server.objects["h"]
        x0, y0 = start.x, start.y
        # Out three squares and back to where it started: 30 feet, not 0.
        gm.send_json(
            {
                "type": "obj.update",
                "patches": [{"id": "h", "x": x0 + 1, "y": y0}],
                "via": {"h": [x0 + 210, y0]},
            }
        )
        moved = None
        while not moved:
            moved = recv(gm, "game")["game"]["turn_order"][0].get("moved")
        assert moved == 30


def test_map_layer_is_seen_by_players_and_pins_are_for_the_gm(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        roof = {**token(page, "roof"), "kind": "image", "layer": "map"}
        pin = {**token(page, "pin", title="Inn", notes="Rooms: 5 sp"), "kind": "pin"}
        secret = {**token(page, "secret", title="Trap"), "kind": "pin", "layer": "gm"}
        gm.send_json({"type": "obj.create", "objects": [roof, pin, secret]})
        seen = {o["id"]: o for o in recv(pl, "obj.upsert")["objects"]}
        assert set(seen) == {"roof", "pin"} and seen["pin"]["props"]["notes"] == "Rooms: 5 sp"

        pl.send_json({"type": "obj.update", "patches": [{"id": "roof", "x": 1}]})
        assert recv(pl, "error")["detail"] == "you do not control this object"
        mine = {**token(page, "mine"), "kind": "pin"}
        pl.send_json({"type": "obj.create", "objects": [mine]})
        assert recv(pl, "error")["detail"] == "you cannot create this object"
