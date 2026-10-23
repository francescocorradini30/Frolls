"""combat.act through the game server: card, application, redaction, undo, extra damage."""

from fastapi.testclient import TestClient

from app.game.server import server
from tests.conftest import FixedDice
from tests.test_game import WS, join, recv, token
from tests.test_hp_game import monster, pc
from tests.test_journal import create_character


def fighter() -> dict:
    sheet = pc(20)
    sheet["abilities"] = {**sheet["abilities"], "str": 16}
    sheet["attacks"] = [
        {"id": "sword", "name": "Longsword", "damage": "1d8", "damage_type": "slashing"}
    ]
    return sheet


def goblin() -> dict:
    sheet = monster(12, ac=13)
    sheet["attacks"] = [
        {
            "id": "scim",
            "name": "Scimitar",
            "ability": "none",
            "to_hit": 4,
            "damage": "1d6+2",
            "damage_type": "slashing",
            "add_modifier": False,
            "range": "reach 5 ft",
        }
    ]
    return sheet


def setup(gm, page: str, controller: str | None = None) -> None:
    create_character(gm, "hero", name="Aria", sheet=fighter())
    create_character(gm, "gob", name="Goblin", sheet=goblin())
    hero = token(page, "h", represents="hero", name="Aria")
    if controller:
        hero["props"]["controlled_by"] = [controller]
    gm.send_json(
        {
            "type": "obj.create",
            "objects": [
                {**hero, "x": 35},
                {**token(page, "g", represents="gob", name="Goblin 1"), "x": 105},
            ],
        }
    )
    recv(gm, "obj.upsert")


def act(ws, actor: str, attack: str, *targets: str, **extra) -> dict:
    ws.send_json(
        {
            "type": "combat.act",
            "actor_id": actor,
            "action": {"kind": "attack", "id": attack},
            "targets": [{"id": t} for t in targets],
            **extra,
        }
    )
    return next_card(ws)


def next_card(ws, kind: str = "chat") -> dict:
    for _ in range(30):
        msg = recv(ws, kind)["message"]
        if (msg.get("roll") or {}).get("card"):
            return msg
    raise AssertionError("no card")


def gob_hp() -> int:
    return server.objects["g"].props["bar1"]["value"]


def test_attack_hits_applies_damage_and_is_one_event(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        dice.face = 10  # 10 + 5 = 15 vs AC 13; damage 8 + 3
        before = server.seq
        msg = act(gm, "h", "sword", "g")
        card = msg["roll"]["card"]
        assert server.seq == before + 1 and card["seqs"] == [server.seq]
        row = card["rows"][0]
        assert row["outcome"] == "hit" and row["taken"] == 11 and row["ac"] == 13
        assert gob_hp() == 1
        assert card["action"] == "Longsword" and card["actor_name"] == "Aria"


def test_miss_changes_nothing_but_posts_the_card(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        dice.face = 2
        before = server.seq
        card = act(gm, "h", "sword", "g")["roll"]["card"]
        assert card["rows"][0]["outcome"] == "miss" and card["seqs"] == []
        assert server.seq == before and gob_hp() == 12


def test_players_see_monster_cards_redacted(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        setup(gm, page, controller="p1")
        dice.face = 10
        mine = act(pl, "h", "sword", "g")["roll"]["card"]["rows"][0]
        # Monster AC and hit points stay hidden; the bloodied state shows.
        assert "ac" not in mine and "hp" not in mine and mine["state"] == "Near death"
        assert mine["total"] == 15
        gm_view = next_card(gm)["roll"]["card"]["rows"][0]
        assert gm_view["ac"] == 13 and gm_view["hp"]["current"] == 1

        theirs = act(gm, "g", "scim", "h")
        seen = next_card(pl)
        assert theirs["roll"]["card"]["rows"][0]["total"] == 14
        # Monster dice are hidden from players.
        assert "total" not in seen["roll"]["card"]["rows"][0]
        assert seen["roll"]["inline"][0] is None


def test_card_undo_and_redo(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        dice.face = 10
        card_id = act(gm, "h", "sword", "g")["id"]
        assert gob_hp() == 1
        gm.send_json({"type": "combat.undo", "card_id": card_id})
        updated = next_card(gm, "chat.update")
        assert updated["id"] == card_id and updated["roll"]["card"]["undone_by"] == "Master"
        assert gob_hp() == 12
        gm.send_json({"type": "combat.redo", "card_id": card_id})
        updated = next_card(gm, "chat.update")
        assert updated["roll"]["card"]["undone_by"] is None
        assert gob_hp() == 1


def test_extra_damage_on_a_hit_is_undone_with_the_card(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", name="Aria", sheet=fighter())
        tough = goblin()
        tough["hp"] = {"current": 40, "max": 40, "temp": 0}
        create_character(gm, "gob", name="Goblin", sheet=tough)
        gm.send_json(
            {
                "type": "obj.create",
                "objects": [
                    {**token(page, "h", represents="hero", name="Aria"), "x": 35},
                    {**token(page, "g", represents="gob", name="Goblin 1"), "x": 105},
                ],
            }
        )
        recv(gm, "obj.upsert")
        dice.face = 10
        card_id = act(gm, "h", "sword", "g")["id"]
        assert gob_hp() == 29
        gm.send_json(
            {
                "type": "combat.add_damage",
                "card_id": card_id,
                "target_id": "g",
                "formula": "2d6",
                "damage_type": "piercing",
            }
        )
        row = next_card(gm, "chat.update")["roll"]["card"]["rows"][0]
        assert row["taken"] == 23 and row["damage"][-1]["extra"] is True
        assert gob_hp() == 17
        gm.send_json({"type": "combat.undo", "card_id": card_id})
        next_card(gm, "chat.update")
        assert gob_hp() == 40


def test_attacking_spends_the_action_in_combat(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json({"type": "combat.initiative", "token_ids": ["h", "g"]})
        recv(gm, "chat")
        order = server.game.turn_order
        actor = order[0]["object_id"]
        target = "g" if actor == "h" else "h"
        attack = "sword" if actor == "h" else "scim"
        act(gm, actor, attack, target)
        entry = server.game.turn_order[0]
        assert entry["used"]["action"] is True and entry["attacks"] == 1
        act(gm, actor, attack, target)
        assert server.game.turn_order[0]["used"]["action_extra"] == 1
