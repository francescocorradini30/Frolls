"""Manual fog of war: areas, visibility of tokens for players."""

from fastapi.testclient import TestClient

from app.game.fog import contains, visible
from tests.test_game import WS, join, recv, token


def test_areas_and_order() -> None:
    fog = {
        "enabled": True,
        "ops": [
            {"mode": "reveal", "shape": "rect", "points": [0, 0, 200, 200]},
            {"mode": "hide", "shape": "poly", "points": [100, 100, 200, 100, 200, 200]},
        ],
    }
    assert visible(fog, 50, 50)
    assert not visible(fog, 190, 150)  # hidden again by the triangle, which comes later
    assert not visible(fog, 300, 300)  # never revealed
    assert visible({"enabled": False, "ops": []}, 999, 999)
    assert contains({"shape": "rect", "points": [10, 10, 0, 0]}, 5, 5)


def objects_of(ws) -> set[str]:
    return {o["id"] for o in recv(ws, "page.snapshot")["objects"]}


def test_players_do_not_receive_tokens_under_the_fog(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        gm.send_json(
            {
                "type": "obj.create",
                "objects": [
                    {**token(page, "orc"), "x": 35, "y": 35},
                    {**token(page, "mine", controlled_by=["p1"]), "x": 455, "y": 455},
                ],
            }
        )
        recv(pl, "obj.upsert")

        gm.send_json({"type": "fog.set", "page_id": page, "enabled": True})
        # Under the fog: only the player's own token.
        assert objects_of(pl) == {"mine"}

        gm.send_json(
            {
                "type": "fog.op",
                "page_id": page,
                "mode": "reveal",
                "shape": "rect",
                "points": [0, 0, 140, 140],
            }
        )
        assert objects_of(pl) == {"orc", "mine"}

        # The orc walks back into the dark: it disappears for the player.
        gm.send_json({"type": "obj.update", "patches": [{"id": "orc", "x": 315}]})
        assert recv(pl, "obj.removed")["ids"] == ["orc"]

        gm.send_json({"type": "fog.reset", "page_id": page, "mode": "reveal"})
        assert objects_of(pl) == {"orc", "mine"}

        pl.send_json({"type": "fog.set", "page_id": page, "enabled": False})
        assert recv(pl, "error")["detail"] == "only the GM can do that"
