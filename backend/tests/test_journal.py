"""Journal: characters, folders, the token link and speaking as a character in chat."""

from fastapi.testclient import TestClient

from app.game.server import server
from tests.test_game import WS, join, recv, token


def create_character(ws, cid: str = "c1", **fields) -> dict:
    ws.send_json({"type": "char.create", "id": cid, "character": {"name": "Thorin", **fields}})
    while "characters" not in (msg := recv(ws, "journal.upsert")):
        pass  # folder upserts sent before
    return msg["characters"][0]


def test_gm_creates_a_character_and_it_persists(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        got = create_character(
            gm,
            bio="Dwarf",
            gm_notes="Secretly a prince",
            attributes=[{"name": "hp", "current": "12", "max": "12"}],
        )
        assert got["name"] == "Thorin" and got["gm_notes"] == "Secretly a prince"
    server.__init__()
    with client.websocket_connect(WS) as gm:
        journal = join(gm, "gm", "Master", gm=True)["welcome"]["journal"]
        [thorin] = journal["characters"]
        assert thorin["attributes"] == [{"name": "hp", "current": "12", "max": "12"}]


def test_players_see_only_their_character_without_gm_notes(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        create_character(gm, "villain", name="Strahd")
        gm.send_json({"type": "folder.create", "id": "f1", "name": "NPCs"})
        recv(gm, "journal.upsert")
        create_character(gm, "hero", name="Aria the Ranger", gm_notes="cursed")

        # Assigning it to the player makes it appear for them, without the GM notes.
        gm.send_json({"type": "char.update", "id": "hero", "patch": {"player_id": "p1"}})
        got = recv(pl, "journal.upsert")["characters"]
        assert [c["id"] for c in got] == ["hero"] and "gm_notes" not in got[0]

        gm.send_json({"type": "char.update", "id": "hero", "patch": {"player_id": None}})
        assert recv(pl, "journal.removed")["character_ids"] == ["hero"]

    with client.websocket_connect(WS) as pl:
        journal = join(pl, "p1", "Aria")["welcome"]["journal"]
        assert journal == {"characters": [], "folders": []}


def test_player_edits_only_story_fields_of_own_character(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        create_character(gm, "hero", player_id="p1")
        create_character(gm, "other")
        pl.send_json({"type": "char.update", "id": "hero", "patch": {"bio": "From the north"}})
        assert recv(gm, "journal.upsert")["characters"][0]["bio"] == "From the north"
        pl.send_json({"type": "char.update", "id": "hero", "patch": {"gm_notes": "x"}})
        assert (
            recv(pl, "error")["detail"] == "only the GM can change notes, folder, player or archive"
        )
        pl.send_json({"type": "char.update", "id": "other", "patch": {"bio": "x"}})
        assert recv(pl, "error")["detail"] == "you can only edit your own character"
        pl.send_json({"type": "char.create", "id": "c9", "character": {"name": "Mine"}})
        assert recv(pl, "error")["detail"] == "only the GM can do that"


def test_folders_nest_and_deleting_moves_content_up(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        gm.send_json({"type": "folder.create", "id": "a", "name": "World"})
        gm.send_json({"type": "folder.create", "id": "b", "name": "Town", "parent_id": "a"})
        gm.send_json({"type": "folder.create", "id": "c", "name": "Tavern", "parent_id": "b"})
        create_character(gm, "inn", folder_id="b")

        gm.send_json({"type": "folder.update", "id": "a", "parent_id": "c"})
        assert recv(gm, "error")["detail"] == "a folder cannot go inside itself"

        gm.send_json({"type": "folder.delete", "id": "b"})
        assert recv(gm, "journal.removed")["folder_ids"] == ["b"]
        assert server.folders["c"].parent_id == "a"
        assert server.characters["inn"].folder_id == "a"


def test_token_represents_a_character_and_loses_the_link_on_delete(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        create_character(gm, "hero")
        gm.send_json({"type": "obj.create", "objects": [token(page, represents="hero")]})
        assert recv(pl, "obj.upsert")["objects"][0]["props"]["represents"] == "hero"

        # Only the GM links tokens to characters.
        gm.send_json(
            {"type": "obj.update", "patches": [{"id": "t1", "props": {"controlled_by": ["p1"]}}]}
        )
        recv(pl, "obj.upsert")
        pl.send_json(
            {"type": "obj.update", "patches": [{"id": "t1", "props": {"represents": None}}]}
        )
        assert recv(pl, "error")["detail"] == "only the GM can change permissions and GM notes"

        gm.send_json({"type": "char.delete", "id": "hero"})
        assert "represents" not in recv(pl, "obj.upsert")["objects"][0]["props"]
        assert "represents" not in server.objects["t1"].props


def test_players_speak_as_their_character(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        pl.send_json({"type": "chat.send", "text": "hello"})
        assert recv(pl, "chat")["message"]["speaker"] == "Aria"

        create_character(gm, "hero", name="Aria the Ranger", player_id="p1")
        # A player cannot pick another name.
        pl.send_json({"type": "chat.send", "text": "hi", "as_character": "nobody"})
        assert recv(gm, "chat")["message"]["speaker"] == "Aria the Ranger"


def test_gm_speaks_as_any_character(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        join(gm, "gm", "Master", gm=True)
        create_character(gm, "villain", name="Strahd")
        gm.send_json({"type": "chat.send", "text": "Welcome", "as_character": "villain"})
        assert recv(gm, "chat")["message"]["speaker"] == "Strahd"
        gm.send_json({"type": "chat.send", "text": "OOC", "as_character": None})
        assert recv(gm, "chat")["message"]["speaker"] == "Master"


def test_whisper_to_a_character_reaches_its_player(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        create_character(gm, "hero", name="Ranger", player_id="p1")
        gm.send_json({"type": "chat.send", "text": "/w Ranger you hear a noise"})
        msg = recv(pl, "chat")["message"]
        assert msg["recipients"] == ["p1"] and msg["content"] == "you hear a noise"
