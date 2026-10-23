"""5e sheets through the game server: derived values, rolls, conditions, targets."""

from fastapi.testclient import TestClient

from app.game.server import server
from app.rules5e.sheet import new_sheet
from tests.conftest import FixedDice
from tests.test_game import WS, join, recv, token
from tests.test_journal import create_character


def fighter() -> dict:
    sheet = new_sheet("pc")
    sheet.update(
        level=5,
        abilities={"str": 16, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10},
        save_proficiencies=["str", "con"],
        attacks=[{"id": "sword", "name": "Longsword", "damage": "1d8", "damage_type": "slashing"}],
    )
    return sheet


def goblin() -> dict:
    sheet = new_sheet("npc")
    sheet.update(cr="1/4", ac=15)
    return sheet


def card(msg: dict) -> dict[str, str]:
    fields = dict(msg["roll"]["template"]["fields"])
    totals = [r["total"] for r in msg["roll"]["inline"]]
    return {**fields, "_title": msg["roll"]["template"]["title"], "_totals": totals}


def roll(ws, **fields) -> dict:
    ws.send_json({"type": "sheet.roll", **fields})
    return card(recv(ws, "chat")["message"])


def test_sheet_is_sent_with_derived_values(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        hero = create_character(gm, "hero", name="Brom", sheet=fighter())
        assert hero["derived"]["saves"]["str"] == 6 and hero["derived"]["proficiency"] == 3
        plain = create_character(gm, "plain", name="Nobody")
        assert plain["sheet"] is None and plain["derived"] is None


def test_player_edits_own_sheet(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        create_character(gm, "hero", sheet=fighter(), player_id="p1")
        sheet = {**fighter(), "level": 9}
        pl.send_json({"type": "char.update", "id": "hero", "patch": {"sheet": sheet}})
        assert recv(gm, "journal.upsert")["characters"][0]["derived"]["proficiency"] == 4
        pl.send_json({"type": "char.update", "id": "hero", "patch": {"sheet": {"level": 99}}})
        assert "invalid message" in recv(pl, "error")["detail"]


def test_save_check_and_skill(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        create_character(gm, "hero", name="Brom", sheet=fighter())
        save = roll(gm, character_id="hero", roll="save", key="str")
        assert save["_title"] == "Brom: Strength save" and save["_totals"] == [16]
        check = roll(gm, character_id="hero", roll="check", key="int", mode="advantage")
        assert "With advantage" in check and check["_totals"] == [9]
        skill = roll(gm, character_id="hero", roll="skill", key="athletics")
        assert skill["_title"] == "Brom: Athletics" and skill["_totals"] == [13]


def test_conditions_on_the_token_change_the_roll(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=fighter())
        statuses = ["stunned", "poisoned"]
        gm.send_json(
            {"type": "obj.create", "objects": [token(page, represents="hero", statuses=statuses)]}
        )
        recv(gm, "obj.upsert")
        dex = roll(gm, character_id="hero", roll="save", key="dex", token_id="t1")
        assert dex["Result"] == "automatic failure: stunned" and dex["_totals"] == []
        check = roll(gm, character_id="hero", roll="check", key="str", token_id="t1")
        assert "With disadvantage" in check and check["Why"] == "disadvantage: poisoned"


def test_attack_against_a_target_and_critical_damage(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=fighter())
        create_character(gm, "gob", name="Goblin", sheet=goblin())
        gm.send_json(
            {
                "type": "obj.create",
                "objects": [
                    token(page, "me", represents="hero"),
                    {**token(page, "foe", represents="gob", statuses=["prone"]), "x": 105},
                ],
            }
        )
        recv(gm, "obj.upsert")
        hit = roll(
            gm, character_id="hero", roll="attack", key="sword", token_id="me", target_id="foe"
        )
        # 10 + 6 = 16 against AC 15, with advantage because the goblin is prone and adjacent.
        assert hit["_totals"] == [16] and hit["Target"] == "Goblin vs AC 15"
        assert hit["Result"] == "Hit" and "advantage: target is prone, within 5 ft" in hit["Why"]
        assert hit["Damage"] == "[Roll damage](!damage hero sword 0 me foe)"

        dice.face = 20
        crit = roll(gm, character_id="hero", roll="attack", key="sword", target_id="foe")
        assert crit["Result"] == "Critical hit" and "!damage hero sword 1" in crit["Damage"]
        dice.face = 5
        damage = roll(gm, character_id="hero", roll="damage", key="sword", crit=True)
        # Dice doubled, modifier once: 2d8+3 with every die on 5.
        assert damage["_totals"] == [13]
        assert damage["_title"] == "Thorin: Longsword damage (critical)"


def test_initiative_goes_into_the_tracker(client: TestClient, dice: FixedDice) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=fighter())
        gm.send_json({"type": "obj.create", "objects": [token(page, represents="hero")]})
        recv(gm, "obj.upsert")
        roll(gm, character_id="hero", roll="initiative", token_id="t1")
        assert [(e["object_id"], e["value"]) for e in server.game.turn_order] == [("t1", "12")]


def test_players_roll_only_for_their_character(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        create_character(gm, "hero", sheet=fighter())
        pl.send_json({"type": "sheet.roll", "character_id": "hero", "roll": "save", "key": "str"})
        assert recv(pl, "error")["detail"] == "you can only roll for your own character"


def test_a_partial_sheet_is_stored_complete(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        create_character(gm, "hero")
        gm.send_json({"type": "char.update", "id": "hero", "patch": {"sheet": {"kind": "npc"}}})
        sheet = recv(gm, "journal.upsert")["characters"][0]["sheet"]
        assert (
            sheet["kind"] == "npc"
            and sheet["save_proficiencies"] == []
            and sheet["hp"]["max"] == 10
        )
