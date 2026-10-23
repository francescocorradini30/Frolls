"""Game options: catalog in the welcome, GM-only changes, validation, defaults."""

from fastapi.testclient import TestClient

from app.game import options
from app.game.server import server
from tests.test_game import WS, join, recv


def test_catalog_values_and_defaults() -> None:
    assert options.value({}, "npc_hp") == "status"
    assert options.value({"npc_hp": "full"}, "npc_hp") == "full"
    # A stored value that is no longer valid falls back to the default.
    assert options.value({"npc_hp": "all"}, "npc_hp") == "status"
    assert options.validate({"npc_hp": "hidden"}) is None
    assert options.validate({"npc_hp": "all"}) is not None
    assert options.validate({"nope": True}) == "unknown option nope"
    assert options.validate({"npc_hp": 1}) is not None


def test_gm_changes_options_and_everyone_sees_them(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        welcome = join(gm, "gm", "Master", gm=True)["welcome"]
        assert {o["key"] for o in welcome["options"]} == set(options.BY_KEY)
        join(pl, "p1", "Aria")

        gm.send_json({"type": "game.options", "patch": {"npc_hp": "full"}})
        assert recv(pl, "game")["game"]["settings"]["npc_hp"] == "full"
        assert server.option("npc_hp") == "full"

        pl.send_json({"type": "game.options", "patch": {"npc_hp": "hidden"}})
        assert recv(pl, "error")["detail"] == "only the GM can do that"

        gm.send_json({"type": "game.options", "patch": {"npc_hp": "all"}})
        assert recv(gm, "error")["detail"].startswith("invalid value for Monsters")
        assert server.option("npc_hp") == "full"
