"""GM tools: rollable tables, multi-sided tokens, card decks, art library."""

import pytest
from fastapi.testclient import TestClient

from app.dice import DiceError, TableItem, roll
from app.game import chat
from tests.test_game import WS, join, recv, token

LOOT = {"loot": [TableItem("Gold", 3), TableItem("Sword", 1), TableItem("Never", 0)]}


def test_table_draws_by_weight_and_never_draws_weight_zero() -> None:
    names = {roll("1t[Loot]", LOOT).text for _ in range(200)}
    assert names == {"Gold", "Sword"}
    assert len(roll("3t[loot]", LOOT).terms[0].items) == 3


def test_numeric_tables_count_in_math() -> None:
    tables = {"bonus": [TableItem("4")]}
    result = roll("1t[bonus]+2", tables)
    assert result.total == 6 and result.text is None
    with pytest.raises(DiceError, match="can't be used in math"):
        roll("1t[loot]+1", LOOT)
    with pytest.raises(DiceError, match="no rollable table"):
        roll("1t[nothing]", LOOT)


def test_tables_in_chat_commands_and_inline() -> None:
    assert chat.parse("1t[loot]", False, LOOT).roll["text"] in ("Gold", "Sword")
    assert chat.parse("/r 2t[loot] treasure", False, LOOT).content == "treasure"
    draft = chat.parse("You find [[1t[loot]]] and [[1d4]] gp", False, LOOT)
    assert draft.content == "You find [[#0]] and [[#1]] gp"
    assert draft.inline[0]["terms"][0]["table"] == "loot"


def test_gm_tables_and_hidden_ones(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        gm.send_json({"type": "table.create", "id": "t1", "name": "Weather"})
        assert recv(pl, "table.upsert")["tables"][0]["name"] == "Weather"
        items = [{"id": "i1", "name": "Rain", "weight": 1, "image": "/uploads/rain.webp"}]
        gm.send_json({"type": "table.update", "id": "t1", "items": items})
        assert recv(pl, "table.upsert")["tables"][0]["items"][0]["name"] == "Rain"

        pl.send_json({"type": "chat.send", "text": "/r 1t[weather]"})
        main = recv(pl, "chat")["message"]["roll"]["main"]
        assert main["text"] == "Rain" and main["terms"][0]["items"][0]["image"].endswith(
            "rain.webp"
        )

        gm.send_json({"type": "table.create", "id": "t2", "name": "weather"})
        assert "already a table" in recv(gm, "error")["detail"]
        pl.send_json({"type": "table.create", "id": "t3", "name": "Mine"})
        assert recv(pl, "error")["detail"] == "only the GM can do that"

        # Hidden: gone from the player's list and no longer rollable by them.
        gm.send_json({"type": "table.update", "id": "t1", "show_players": False})
        assert recv(pl, "table.removed")["ids"] == ["t1"]
        pl.send_json({"type": "chat.send", "text": "1t[weather]"})
        assert "no rollable table" in recv(pl, "error")["detail"]
        gm.send_json({"type": "chat.send", "text": "1t[weather]"})
        assert recv(gm, "chat")["message"]["roll"]["main"]["text"] == "Rain"


def test_multi_sided_token(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        sides = ["/uploads/a.webp", "/uploads/b.webp", "/uploads/c.webp"]
        coin = token(page, "coin", controlled_by=["p1"], sides=sides, side=0, image=sides[0])
        gm.send_json({"type": "obj.create", "objects": [coin]})
        recv(pl, "obj.upsert")

        pl.send_json({"type": "token.side", "ids": ["coin"], "side": 2})
        props = recv(pl, "obj.upsert")["objects"][0]["props"]
        assert props["side"] == 2 and props["image"] == sides[2]
        pl.send_json({"type": "token.side", "ids": ["coin"], "side": 5})
        assert "only 3 sides" in recv(pl, "error")["detail"]
        for _ in range(5):
            gm.send_json({"type": "token.side", "ids": ["coin"]})
        seen = set()
        for _ in range(5):
            props = recv(gm, "obj.upsert")["objects"][0]["props"]
            assert props["image"] == sides[props["side"]]
            seen.add(props["side"])
        assert seen <= {0, 1, 2}


def deck_of(ws, until=lambda deck: True) -> dict:
    """The first update of deck d1 that matches `until`: earlier ones are skipped."""
    while True:
        for deck in recv(ws, "deck.upsert")["decks"]:
            if deck["id"] == "d1" and until(deck):
                return deck


def make_deck(gm, n: int = 5) -> None:
    gm.send_json({"type": "deck.create", "id": "d1", "name": "Tarot"})
    deck_of(gm)
    cards = [{"id": f"c{i}", "name": f"Card {i}", "image": f"/uploads/c{i}.webp"} for i in range(n)]
    gm.send_json({"type": "deck.update", "id": "d1", "back": "/uploads/back.webp", "cards": cards})
    assert deck_of(gm)["pile_count"] == n


def test_cards_draw_play_and_privacy(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        make_deck(gm)
        player_view = deck_of(pl, lambda d: d["size"] == 5)
        assert "cards" not in player_view and player_view["hand"] == []

        pl.send_json({"type": "deck.action", "deck_id": "d1", "action": "draw", "count": 2})
        mine = deck_of(pl)
        assert len(mine["hand"]) == 2 and mine["pile_count"] == 3
        assert recv(pl, "chat")["message"]["content"] == 'drew 2 cards from "Tarot".'
        gm_view = deck_of(gm)
        assert gm_view["hand_counts"] == {"p1": 2} and gm_view["hands"]["p1"] == [
            c["id"] for c in mine["hand"]
        ]

        # Played face down: the GM sees the card, the other players only its back.
        card = mine["hand"][0]
        pl.send_json(
            {
                "type": "deck.action",
                "deck_id": "d1",
                "action": "play",
                "card_ids": [card["id"]],
                "page_id": page,
                "x": 100,
                "y": 100,
                "face_down": True,
            }
        )
        on_gm = recv(gm, "obj.upsert")["objects"][0]
        assert on_gm["props"]["card"]["card_id"] == card["id"]
        assert on_gm["props"]["image"] == "/uploads/back.webp"
        assert on_gm["props"]["controlled_by"] == ["p1"]
        assert deck_of(pl)["table_count"] == 1

        with client.websocket_connect(WS) as other:
            snapshot = join(other, "p2", "Bram")["snapshot"]
            seen = next(o for o in snapshot["objects"] if o["id"] == on_gm["id"])
            assert "card" not in seen["props"] and "sides" not in seen["props"]
            assert "name" not in seen["props"]
            # Turned face up, it shows its face to everyone.
            pl.send_json({"type": "token.side", "ids": [on_gm["id"]], "side": 0})
            seen = recv(other, "obj.upsert")["objects"][0]["props"]
            assert seen["image"] == card["image"] and seen["name"] == card["name"]

        # Back into the hand.
        pl.send_json(
            {"type": "deck.action", "deck_id": "d1", "action": "take", "object_ids": [on_gm["id"]]}
        )
        assert recv(pl, "obj.removed")["ids"] == [on_gm["id"]]
        assert len(deck_of(pl)["hand"]) == 2

        # Discard, then the GM shuffles the discard pile back in.
        pl.send_json(
            {"type": "deck.action", "deck_id": "d1", "action": "discard", "card_ids": [card["id"]]}
        )
        assert deck_of(pl)["discard_count"] == 1
        pl.send_json({"type": "deck.action", "deck_id": "d1", "action": "shuffle"})
        assert recv(pl, "error")["detail"] == "only the GM can do that"
        gm.send_json({"type": "deck.action", "deck_id": "d1", "action": "shuffle"})
        view = deck_of(
            gm,
            lambda d: d["table_count"] == d["discard_count"] == 0 and d["hand_counts"] == {"p1": 1},
        )
        assert (view["pile_count"], view["discard_count"], view["hand_counts"]) == (4, 0, {"p1": 1})


def test_gm_deals_plays_from_pile_and_recalls(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        make_deck(gm, 3)
        gm.send_json({"type": "deck.update", "id": "d1", "settings": {"players_draw": False}})
        deck_of(gm)
        pl.send_json({"type": "deck.action", "deck_id": "d1", "action": "draw"})
        assert recv(pl, "error")["detail"] == "only the GM deals from this deck"

        gm.send_json({"type": "deck.action", "deck_id": "d1", "action": "draw", "player_id": "p1"})
        assert len(deck_of(pl, lambda d: d["hand"])["hand"]) == 1
        gm.send_json(
            {"type": "deck.action", "deck_id": "d1", "action": "play", "page_id": page, "x": 5}
        )
        card_token = recv(pl, "obj.upsert")["objects"][0]
        assert card_token["props"]["side"] == 0 and card_token["props"]["controlled_by"] == []

        # Deleting a card from the map puts it in the discard pile.
        gm.send_json({"type": "obj.delete", "ids": [card_token["id"]]})
        view = deck_of(gm, lambda d: d["discard_count"])
        assert (view["pile_count"], view["table_count"], view["discard_count"]) == (1, 0, 1)

        gm.send_json({"type": "deck.action", "deck_id": "d1", "action": "recall"})
        view = deck_of(gm, lambda d: not d["discard_count"])
        assert (view["pile_count"], view["hand_counts"]) == (3, {})
        assert deck_of(pl, lambda d: d["pile_count"] == 3)["hand"] == []

        gm.send_json({"type": "deck.action", "deck_id": "d1", "action": "draw", "count": 4})
        assert "only 3 cards left" in recv(gm, "error")["detail"]

        # Hidden from players: the deck disappears for them.
        gm.send_json({"type": "deck.update", "id": "d1", "settings": {"show_players": False}})
        assert recv(pl, "deck.removed")["ids"] == ["d1"]
        assert deck_of(gm, lambda d: not d["settings"]["show_players"])["settings"] == {
            "show_players": False,
            "players_draw": False,
        }


def test_art_library_is_private(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        join(gm, "gm", "Master", gm=True)
        join(pl, "p1", "Aria")
        pl.send_json(
            {
                "type": "asset.create",
                "id": "a1",
                "name": "Forest",
                "url": "/uploads/f.webp",
                "thumb": "/uploads/f-t.webp",
                "width": 800,
                "height": 600,
                "folder": " Maps ",
                "tags": ["Outdoor", "outdoor ", "night"],
            }
        )
        asset = recv(pl, "asset.upsert")["assets"][0]
        assert asset["folder"] == "Maps" and asset["tags"] == ["outdoor", "night"]
        pl.send_json({"type": "asset.update", "id": "a1", "name": "Dark forest"})
        assert recv(pl, "asset.upsert")["assets"][0]["name"] == "Dark forest"

        gm.send_json({"type": "asset.delete", "ids": ["a1"]})
        assert recv(gm, "error")["detail"] == "image does not exist"
        pl.send_json(
            {"type": "asset.create", "id": "a2", "name": "x", "url": "https://evil.example/x.png"}
        )
        assert recv(pl, "error")["detail"].startswith("invalid message")

    with client.websocket_connect(WS) as again:
        assert [a["id"] for a in join(again, "p1", "Aria")["welcome"]["assets"]] == ["a1"]
