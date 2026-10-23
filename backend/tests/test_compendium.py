"""SRD 5.2 compendium: data, search, monsters on the map, spells on sheets."""

from fastapi.testclient import TestClient

from app import compendium
from app.game.server import server
from app.rules5e.sheet import Sheet, Spell
from tests.test_game import WS, join, recv
from tests.test_hp_game import pc
from tests.test_journal import create_character


def test_every_entry_is_a_valid_sheet() -> None:
    monsters = compendium.entries("monster")
    spells = compendium.entries("spell")
    assert len(monsters) > 300 and len(spells) > 300
    for m in monsters.values():
        Sheet.model_validate(m["sheet"])
    for s in spells.values():
        Spell.model_validate(s["spell"])


def test_search_and_filters() -> None:
    names = [r["name"] for r in compendium.search("monster", "goblin")]
    assert "Goblin Warrior" in names
    assert all(r["cr"] == "1/4" for r in compendium.search("monster", "", cr="1/4"))
    fireball = compendium.search("spell", "fireball")[0]
    assert fireball == {
        "key": "srd-2024_fireball",
        "name": "Fireball",
        "level": 3,
        "school": "Evocation",
    }


def test_monster_dropped_on_the_map(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        for x in (35, 105):
            gm.send_json(
                {
                    "type": "compendium.place",
                    "key": "srd-2024_goblin-warrior",
                    "page_id": page,
                    "x": x,
                    "y": 35,
                }
            )
            recv(gm, "obj.upsert")
        goblins = [c for c in server.characters.values() if c.name == "Goblin Warrior"]
        assert len(goblins) == 1 and goblins[0].sheet["cr"] == "1/4"
        assert server.folders[goblins[0].folder_id].name == "SRD monsters"
        tokens = sorted(
            (o for o in server.objects.values() if o.props.get("represents") == goblins[0].id),
            key=lambda o: o.x,
        )
        assert [t.props["name"] for t in tokens] == ["Goblin Warrior 1", "Goblin Warrior 2"]
        assert tokens[0].props["bar1"] == {"value": 10, "max": 10}

        pl.send_json(
            {
                "type": "compendium.place",
                "key": "srd-2024_goblin-warrior",
                "page_id": page,
                "x": 0,
                "y": 0,
            }
        )
        assert recv(pl, "error")["detail"] == "only the GM can do that"


def test_spells_go_to_a_sheet(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        create_character(gm, "hero", sheet=pc(20))
        gm.send_json(
            {"type": "compendium.add_spell", "key": "srd-2024_fireball", "character_id": "hero"}
        )
        assert recv(gm, "notice")["detail"] == "Fireball added to Thorin"
        [fireball] = server.characters["hero"].sheet["spells"]
        assert (fireball["level"], fireball["save"], fireball["damage"], fireball["upcast"]) == (
            3,
            "dex",
            "8d6",
            "1d6",
        )
        gm.send_json(
            {"type": "compendium.add_spell", "key": "srd-2024_fireball", "character_id": "hero"}
        )
        assert recv(gm, "error")["detail"] == "Thorin already has Fireball"


def test_search_through_the_socket(client: TestClient) -> None:
    with client.websocket_connect(WS) as pl:
        join(pl, "p1", "Aria")
        pl.send_json({"type": "compendium.search", "kind": "spell", "query": "cure", "rid": "s1"})
        results = recv(pl, "compendium.results")
        assert results["rid"] == "s1" and "Cure Wounds" in [i["name"] for i in results["items"]]
        pl.send_json({"type": "compendium.get", "kind": "spell", "key": "srd-2024_cure-wounds"})
        entry = recv(pl, "compendium.entry")["entry"]
        assert entry["spell"]["heal"] == "healing" and entry["spell"]["add_modifier"]
