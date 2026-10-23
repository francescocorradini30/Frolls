"""Hit points through the game server: token <-> sheet link, damage, death, monsters' HP."""

from fastapi.testclient import TestClient

from app.game.server import server
from app.rules5e.sheet import new_sheet
from tests.conftest import FixedDice
from tests.test_game import WS, join, recv, token
from tests.test_journal import create_character


def until(ws, check) -> dict:
    """The first obj.upsert for which `check(objects)` holds."""
    for _ in range(20):
        objs = {o["id"]: o for o in recv(ws, "obj.upsert")["objects"]}
        if check(objs):
            return objs
    raise AssertionError("no matching obj.upsert")


def pc(hp: int = 20) -> dict:
    sheet = new_sheet("pc")
    sheet["hp"] = {"current": hp, "max": hp, "temp": 0}
    return sheet


def monster(hp: int = 7, **extra) -> dict:
    sheet = new_sheet("npc")
    sheet["hp"] = {"current": hp, "max": hp, "temp": 0}
    sheet.update(extra)
    return sheet


def apply(ws, ids: list[str], amount: int, **extra) -> list[list[str]]:
    ws.send_json({"type": "combat.apply", "token_ids": ids, "amount": amount, **extra})
    return recv(ws, "chat")["message"]["roll"]["template"]["fields"]


def place(ws, page: str, oid: str, character: str, **props) -> dict:
    ws.send_json(
        {"type": "obj.create", "objects": [token(page, oid, represents=character, **props)]}
    )
    return recv(ws, "obj.upsert")["objects"][0]


def test_player_character_hp_lives_on_the_sheet(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", name="Brom", sheet=pc(20))
        assert place(gm, page, "t1", "hero")["props"]["bar1"] == {"value": 20, "max": 20}

        rows = apply(gm, ["t1"], 7, damage_type="slashing")
        assert rows == [["Goblin", "takes 7 slashing damage → 13/20 HP"]]
        assert server.characters["hero"].sheet["hp"]["current"] == 13

        # Typing on the token's HP bubble changes the sheet.
        gm.send_json(
            {
                "type": "obj.update",
                "patches": [{"id": "t1", "props": {"bar1": {"value": 5, "max": 20}}}],
            }
        )
        hero = recv(gm, "journal.upsert")["characters"][0]
        assert hero["sheet"]["hp"]["current"] == 5

        # And changing the sheet changes every token of the character.
        place(gm, page, "t2", "hero")
        sheet = {**server.characters["hero"].sheet, "hp": {"current": 9, "max": 20, "temp": 3}}
        gm.send_json({"type": "char.update", "id": "hero", "patch": {"sheet": sheet}})
        objs = until(gm, lambda o: "t2" in o)
        assert objs["t1"]["props"]["bar1"]["value"] == 9
        assert objs["t2"]["props"]["bar2"]["value"] == 3


def test_monster_defenses_and_death(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "gob", name="Goblin", sheet=monster(7, resistances=["fire"]))
        place(gm, page, "g1", "gob")
        place(gm, page, "g2", "gob")
        rows = apply(gm, ["g1"], 10, damage_type="fire")
        # Monsters' hit points stay out of the public card (game setting "status").
        assert rows[0][1] == "takes 5 fire damage · resistant to fire"
        assert server.objects["g1"].props["bar1"]["value"] == 2
        # Each copy keeps its own hit points.
        assert server.objects["g2"].props["bar1"]["value"] == 7
        apply(gm, ["g1"], 3)
        assert "dead" in server.objects["g1"].props["statuses"]


def test_pc_unconscious_then_death_saves(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(10))
        place(gm, page, "t1", "hero")
        rows = apply(gm, ["t1"], 12)
        assert "falls unconscious" in rows[0][1]
        assert {"unconscious", "prone"} <= set(server.objects["t1"].props["statuses"])

        dice.face = 5
        gm.send_json({"type": "sheet.roll", "character_id": "hero", "roll": "death_save"})
        fields = dict(recv(gm, "chat")["message"]["roll"]["template"]["fields"])
        assert fields["Death saves"] == "0 successes, 1 failures"

        dice.face = 20
        gm.send_json({"type": "sheet.roll", "character_id": "hero", "roll": "death_save"})
        recv(gm, "chat")
        assert server.characters["hero"].sheet["hp"]["current"] == 1
        assert "unconscious" not in server.objects["t1"].props["statuses"]


def test_healing_and_temporary_hit_points(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(20))
        place(gm, page, "t1", "hero")
        apply(gm, ["t1"], 15)
        apply(gm, ["t1"], 4, kind="healing")
        apply(gm, ["t1"], 6, kind="temp")
        rows = apply(gm, ["t1"], 8)
        assert rows[0][1] == "takes 8 damage → 7/20 HP · 6 absorbed by temporary hit points"


def test_players_see_only_how_hurt_monsters_look(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        create_character(gm, "gob", sheet=monster(8))
        place(gm, page, "g1", "gob")
        apply(gm, ["g1"], 4)
        seen = recv(pl, "obj.upsert")["objects"][0]["props"]["bar1"]
        while seen.get("max") != 4 or seen.get("value") != 2:
            seen = recv(pl, "obj.upsert")["objects"][0]["props"]["bar1"]
        assert seen == {"value": 2, "max": 4, "state": "Bloodied"}

        gm.send_json({"type": "game.settings", "npc_hp": "hidden"})
        snapshot = recv(pl, "page.snapshot")
        assert "bar1" not in snapshot["objects"][0]["props"]

        # Nor through macros.
        pl.send_json({"type": "chat.send", "text": "[[@{target|hp}]]", "target_id": "g1"})
        assert recv(pl, "error")["detail"] == "the hit points of that creature are hidden"

        gm.send_json({"type": "game.settings", "npc_hp": "full"})
        assert recv(pl, "page.snapshot")["objects"][0]["props"]["bar1"] == {"value": 4, "max": 8}


def test_players_cannot_damage_tokens_they_do_not_control(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        create_character(gm, "gob", sheet=monster())
        place(gm, page, "g1", "gob")
        pl.send_json({"type": "combat.apply", "token_ids": ["g1"], "amount": 3})
        assert (
            recv(pl, "error")["detail"]
            == "you can only change the hit points of tokens you control"
        )


def test_long_rest_and_size(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(20))
        place(gm, page, "t1", "hero")
        apply(gm, ["t1"], 15)
        gm.send_json({"type": "sheet.rest", "character_id": "hero", "kind": "long"})
        recv(gm, "chat")
        assert server.characters["hero"].sheet["hp"]["current"] == 20
        assert server.objects["t1"].props["bar1"]["value"] == 20

        sheet = {**server.characters["hero"].sheet, "size": "large"}
        gm.send_json({"type": "char.update", "id": "hero", "patch": {"sheet": sheet}})
        objs = until(gm, lambda o: o.get("t1", {}).get("width") == 140)
        assert objs["t1"]["height"] == 140
