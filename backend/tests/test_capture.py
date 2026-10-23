"""Action capture: one combat action is one event, all or nothing, undone by merge."""

import pytest
from fastapi.testclient import TestClient

from app.game.server import server
from tests.conftest import FixedDice
from tests.test_effects_game import effects, setup, statuses
from tests.test_game import WS, join, recv
from tests.test_hp_game import apply, pc, place
from tests.test_journal import create_character


def hp(cid: str) -> int:
    return server.characters[cid].sheet["hp"]["current"]


def test_damage_to_a_pc_with_two_tokens_is_one_event(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(20))
        place(gm, page, "t1", "hero")
        place(gm, page, "t2", "hero")
        before = server.seq
        apply(gm, ["t1"], 25)  # unconscious and prone too
        assert server.seq == before + 1
        assert hp("hero") == 0
        assert {"unconscious", "prone"} <= set(server.objects["t2"].props["statuses"])

        gm.send_json({"type": "undo"})
        assert recv(gm, "notice")["detail"].startswith("Undone")
        assert hp("hero") == 20
        assert server.objects["t1"].props["bar1"]["value"] == 20
        assert server.objects["t2"].props["bar1"]["value"] == 20
        assert not (
            {"unconscious", "prone"} & set(server.objects["t2"].props.get("statuses") or [])
        )

        gm.send_json({"type": "redo"})
        recv(gm, "notice")
        assert hp("hero") == 0


def test_undo_after_healing_takes_the_damage_back(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(30))
        place(gm, page, "t1", "hero")
        apply(gm, ["t1"], 10)  # 20/30
        hit = server.seq
        apply(gm, ["t1"], 5, kind="healing")  # 25/30
        gm.send_json({"type": "combat.undo", "seq": hit})
        recv(gm, "notice")
        # 25 + 10, capped at the maximum.
        assert hp("hero") == 30


def test_undo_brings_back_effects_lost_with_concentration(
    client: TestClient, dice: FixedDice
) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        setup(gm, page)
        gm.send_json(
            {"type": "effect.apply", "token_ids": ["a"], "preset": "bless", "source_id": "c"}
        )
        recv(gm, "chat")
        dice.face = 2  # fails the concentration save
        gm.send_json({"type": "combat.apply", "token_ids": ["c"], "amount": 6})
        recv(gm, "chat")
        assert effects("a") == [] and "concentrating" not in statuses("c")

        gm.send_json({"type": "undo"})
        recv(gm, "notice")
        assert effects("a") == ["Bless"]
        assert "concentrating" in statuses("c")
        assert server.objects["c"].props["concentrating"] == {"name": "Bless"}
        assert hp("cleric") == 20


def test_a_failing_action_changes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client.websocket_connect(WS) as gm:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        create_character(gm, "hero", sheet=pc(20))
        place(gm, page, "t1", "hero")
        seq = server.seq

        async def boom(*args, **kwargs):
            raise RuntimeError("boom")

        # Fails after the hit points were already changed in memory.
        monkeypatch.setattr(type(server), "_concentration_save", boom)
        gm.send_json({"type": "combat.apply", "token_ids": ["t1"], "amount": 7})
        assert recv(gm, "error")["detail"] == "internal server error"
        assert server.seq == seq
        assert hp("hero") == 20
        assert server.objects["t1"].props["bar1"]["value"] == 20


def test_players_undo_only_their_own_actions(client: TestClient) -> None:
    with client.websocket_connect(WS) as gm, client.websocket_connect(WS) as pl:
        page = join(gm, "gm", "Master", gm=True)["page_id"]
        join(pl, "p1", "Aria")
        create_character(gm, "hero", sheet=pc(20))
        place(gm, page, "t1", "hero", controlled_by=["p1"])
        apply(gm, ["t1"], 5)
        gm_hit = server.seq
        pl.send_json({"type": "combat.undo", "seq": gm_hit})
        assert recv(pl, "error")["detail"] == "you can only undo your own last actions"

        pl.send_json({"type": "combat.apply", "token_ids": ["t1"], "amount": 3})
        recv(pl, "chat")
        assert hp("hero") == 12
        # The GM can undo anyone's action.
        gm.send_json({"type": "combat.undo", "seq": server.seq})
        recv(gm, "notice")
        assert hp("hero") == 15
