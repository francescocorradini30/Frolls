"""Action capture: one combat action = one event = one undo step.

Inside `async with self._action(kind, summary):` the state helpers (`_set_props`,
`_set_sheet`, `_save_turns`, `_fit_tokens`, `_post_chat`) change the in-memory state at
once, so later reads in the same handler see the new values, but they neither write nor
broadcast. They record the state before the first change instead. At the end of the block
everything is written in one `_commit` (one event row with the before/after of every
token, sheet and the turn order) and then broadcast. If the handler raises, the memory is
put back as it was: no half-applied action, ever.

Undo of an action is a three-way merge (`app/game/merge.py`) inside a new capture, so it
works even after the game went on, and is itself one event.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update

from app.db import session_scope
from app.game import merge
from app.game import protocol as p
from app.game.server.base import (
    UNDO_LIMIT,
    Connection,
    GameError,
    ServerBase,
    _copy,
)
from app.models import Character, ChatMessage, Event, Game, MapObject, Player


@dataclass
class Capture:
    kind: str
    summary: str
    # Ctrl+Z step for its author (combat results); turn changes and rests are not.
    undoable: bool
    author: Player | None
    # id -> {column: value before}; "props" is the whole props dict.
    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    # id -> sheet before.
    characters: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    # (turn order, settings) before.
    turn: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
    chat: list[ChatMessage] = field(default_factory=list)
    # While a combat card is being built: lines that game cards (concentration, effects)
    # add to it instead of posting their own message.
    fold: list[str] | None = None
    # Existing cards this action adds to (extra damage): their Undo includes it.
    card_ids: list[int] = field(default_factory=list)


Handler = Callable[[Any, Connection, Any], Awaitable[None]]


def captured(kind: str, summary: str, undoable: bool = False) -> Callable[[Handler], Handler]:
    """Run a message handler inside an action capture. The handler may refine the summary
    with `self.capture.summary = ...`."""

    def wrap(fn: Handler) -> Handler:
        @functools.wraps(fn)
        async def handler(self: Any, conn: Connection, msg: Any) -> None:
            async with self._action(kind, summary, undoable):
                await fn(self, conn, msg)

        return handler

    return wrap


class CaptureMixin(ServerBase):
    @asynccontextmanager
    async def _action(
        self, kind: str, summary: str, undoable: bool = False
    ) -> AsyncIterator[Capture]:
        """Capture every state change of the block into one event (see the module doc).
        Reentrant: an inner `_action` joins the outer one."""
        if self.capture is not None:
            yield self.capture
            return
        cap = Capture(kind, summary, undoable, self.actor)
        self.capture = cap
        try:
            yield cap
        except BaseException:
            self.capture = None
            self._rollback(cap)
            raise
        self.capture = None
        await self._finish(cap)

    # --- Recording ---------------------------------------------------------------

    def _touch_object(self, obj: MapObject, *columns: str) -> None:
        assert self.capture is not None
        before = self.capture.objects.setdefault(obj.id, {})
        for col in columns:
            if col not in before:
                before[col] = _copy(getattr(obj, col))

    def _touch_character(self, character: Character) -> None:
        assert self.capture is not None
        if character.id not in self.capture.characters:
            self.capture.characters[character.id] = _copy(character.sheet)

    def _touch_turns(self) -> None:
        assert self.capture is not None and self.game is not None
        if self.capture.turn is None:
            self.capture.turn = (_copy(self.game.turn_order), _copy(self.game.settings))

    def _rollback(self, cap: Capture) -> None:
        for obj_id, before in cap.objects.items():
            obj = self.objects.get(obj_id)
            if obj is not None:
                for col, value in before.items():
                    setattr(obj, col, value)
        for char_id, sheet in cap.characters.items():
            character = self.characters.get(char_id)
            if character is not None:
                character.sheet = sheet
        if cap.turn is not None and self.game is not None:
            self.game.turn_order, self.game.settings = cap.turn

    # --- Commit ------------------------------------------------------------------

    def _action_data(self, cap: Capture) -> dict[str, Any]:
        """Before/after of everything the action changed (only what changed)."""
        objects = []
        for obj_id, before in cap.objects.items():
            obj = self.objects.get(obj_id)
            if obj is None:
                continue
            b: dict[str, Any] = {}
            a: dict[str, Any] = {}
            for col, old in before.items():
                new = _copy(getattr(obj, col))
                if col == "props":
                    pb, pa = merge.diff_props(old, new)
                    if pb or pa:
                        b["props"], a["props"] = pb, pa
                elif old != new:
                    b[col], a[col] = old, new
            if b or a:
                objects.append({"id": obj_id, "before": b, "after": a})
        characters = []
        for char_id, old_sheet in cap.characters.items():
            character = self.characters.get(char_id)
            if character is not None and character.sheet != old_sheet:
                characters.append(
                    {"id": char_id, "before": old_sheet, "after": _copy(character.sheet)}
                )
        data: dict[str, Any] = {"objects": objects, "characters": characters}
        if cap.turn is not None and self.game is not None:
            old_order, old_settings = cap.turn
            if old_order != self.game.turn_order or old_settings != self.game.settings:
                data["turn"] = {
                    "before": {"order": old_order, "round": old_settings.get("round", 0)},
                    "after": {
                        "order": _copy(self.game.turn_order),
                        "round": self.game.settings.get("round", 0),
                    },
                }
        return data

    async def _finish(self, cap: Capture) -> None:
        assert self.game is not None
        data = self._action_data(cap)
        changed = bool(data["objects"] or data["characters"] or "turn" in data)
        if not changed and not cap.chat:
            return
        touched_objs = [self.objects[o["id"]] for o in data["objects"]]
        touched_chars = [self.characters[c["id"]] for c in data["characters"]]
        if changed:
            # The cards of this action know the event that made them (for their Undo).
            for row in cap.chat:
                card = (row.roll or {}).get("card")
                if card is not None:
                    card["seqs"] = [*card.get("seqs", []), self.seq + 1]
            event = {"action": data}
            async with self._commit(
                cap.kind, cap.summary, event, [o.id for o in touched_objs]
            ) as s:
                for o in data["objects"]:
                    obj = self.objects[o["id"]]
                    values = {col: getattr(obj, col) for col in o["after"]}
                    await s.execute(
                        update(MapObject).where(MapObject.id == obj.id).values(**values)
                    )
                for character in touched_chars:
                    await s.execute(
                        update(Character)
                        .where(Character.id == character.id)
                        .values(sheet=character.sheet)
                    )
                if "turn" in data:
                    await s.execute(
                        update(Game)
                        .where(Game.id == self.game.id)
                        .values(turn_order=self.game.turn_order, settings=self.game.settings)
                    )
                await self._insert_chat(s, cap.chat)
                cards = [r.id for r in cap.chat if (r.roll or {}).get("card") is not None]
                cards += cap.card_ids
                if cards:
                    data["card_ids"] = cards
        else:
            async with session_scope() as s:
                await self._insert_chat(s, cap.chat)
        # Broadcast, synchronously: the new seq is already visible to every message.
        if touched_objs:
            self._publish_objects(touched_objs, [], {})
        for character in touched_chars:
            self._broadcast_character(character, character.player_id)
        if "turn" in data:
            self._broadcast_game()
        for row in cap.chat:
            self._send_chat(row)
        if changed and cap.undoable and cap.author is not None:
            self._push_action_undo(cap.author, cap.summary, data)

    async def _insert_chat(self, s: Any, rows: list[ChatMessage]) -> None:
        if not rows:
            return
        s.add_all(rows)
        await s.flush()
        for row in rows:
            await s.refresh(row, ["created_at"])

    def _push_action_undo(self, player: Player, summary: str, data: dict[str, Any]) -> None:
        stack = self.undo.setdefault(player.id, [])
        stack.append({"seq": self.seq, "summary": summary, "action": data})
        del stack[:-UNDO_LIMIT]
        self.redo.pop(player.id, None)
        self._send_undo_state(player.id)

    # --- Undo by merge -------------------------------------------------------------

    async def _merge_action(self, data: dict[str, Any], frm: str) -> list[str]:
        """Take the action out of the current state (`frm`="after": undo) or put it back
        (`frm`="before": redo), inside the current capture. Returns the conflicts."""
        to = "before" if frm == "after" else "after"
        conflicts: list[str] = []
        for o in data.get("objects", []):
            obj = self.objects.get(o["id"])
            if obj is None:
                conflicts.append(f"{o['id']}: deleted since")
                continue
            name = obj.props.get("name") or obj.kind
            # Undo (frm="after") takes before -> after out of the current state.
            for col, new in o[frm].items():
                old = o[to][col]
                if col == "props":
                    current = {k: obj.props.get(k) for k in new.keys() | old.keys()}
                    value, c = merge.revert(old, new, current)
                    conflicts += [f"{name}: {x}" for x in c]
                    patch = _clamp_props(obj.props, value or {})
                    self._touch_object(obj, "props")
                    merged = {**obj.props, **patch}
                    obj.props = {k: v for k, v in merged.items() if v is not None}
                else:
                    value, c = merge.revert(old, new, getattr(obj, col))
                    conflicts += [f"{name}: {x}" for x in c]
                    self._touch_object(obj, col)
                    setattr(obj, col, value)
        for ch in data.get("characters", []):
            character = self.characters.get(ch["id"])
            if character is None:
                continue
            value, c = merge.revert(ch[to], ch[frm], character.sheet)
            conflicts += [f"{character.name}: {x}" for x in c]
            await self._set_sheet(character, _clamp_sheet(value), "")
            await self._sync_tokens(character)
        if "turn" in data and self.game is not None:
            t = data["turn"]
            order, c = merge.revert(t[to]["order"], t[frm]["order"], self.game.turn_order)
            conflicts += [f"turn order: {x}" for x in c]
            round_, _ = merge.revert(
                t[to]["round"], t[frm]["round"], self.game.settings.get("round", 0)
            )
            await self._save_turns("", "", order, max(0, int(round_)))
        return conflicts

    async def _undo_action(self, step: dict[str, Any], frm: str, kind: str) -> int:
        """Apply an action step as a new event; returns its seq."""
        verb = "undid" if kind == "undo" else "redid"
        async with self._action(kind, f"{verb}: {step['summary']}"):
            conflicts = await self._merge_action(step["action"], frm)
        by = self.actor.name if self.actor else "the GM"
        await self._mark_cards(step["action"], step["seq"], by if frm == "after" else None)
        if conflicts and self.actor is not None:
            for c in self.connections:
                if c.player and c.player.id == self.actor.id:
                    c.send(
                        {
                            "type": "notice",
                            "detail": "Partly undone, changed since: " + "; ".join(conflicts[:4]),
                        }
                    )
        return self.seq

    async def on_combat_undo(self, conn: Connection, msg: p.CombatUndo) -> None:
        """Undo a combat action from its chat card (the author, or the GM for anyone's)."""
        player = conn.player
        assert player is not None
        if msg.card_id is not None:
            await self._undo_card(player, msg.card_id)
            return
        if msg.seq is None:
            raise GameError("which action?")
        stack = self.undo.get(player.id, [])
        step = next((s for s in stack if s["seq"] == msg.seq and "action" in s), None)
        if step is None:
            if not player.is_gm:
                raise GameError("you can only undo your own last actions")
            async with session_scope() as s:
                event = await s.get(Event, (self.game_id, msg.seq))
            if event is None or "action" not in event.data:
                raise GameError("this action cannot be undone")
            if event.reverted_by is not None:
                raise GameError("this action was already undone")
            step = {"seq": event.seq, "summary": event.summary, "action": event.data["action"]}
        seq = await self._undo_action(step, "after", "undo")
        await self._mark_reverted(step["seq"], seq)
        for stacks in (self.undo, self.redo):
            for pid, st in stacks.items():
                if any(s["seq"] == step["seq"] for s in st):
                    st[:] = [s for s in st if s["seq"] != step["seq"]]
                    self._send_undo_state(pid)
        conn.send({"type": "notice", "detail": f"Undone: {step['summary']}"})


def _clamp_props(old: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Bars stay within 0..max after a merge."""
    out = dict(patch)
    for key in ("bar1", "bar2"):
        bar = out.get(key)
        if isinstance(bar, dict) and isinstance(bar.get("value"), int | float):
            top = bar.get("max")
            value = max(0, bar["value"])
            out[key] = {**bar, "value": min(value, top) if isinstance(top, int | float) else value}
    return out


def _clamp_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """Counters stay in their ranges after a merge (HP 0..max, used 0..max...)."""
    sheet = _copy(sheet)
    hp = sheet.get("hp") or {}
    if "max" in hp:
        hp["current"] = max(0, min(int(hp.get("current", 0)), int(hp["max"])))
        hp["temp"] = max(0, int(hp.get("temp", 0)))
    ds = sheet.get("death_saves") or {}
    for k in ("successes", "failures"):
        if k in ds:
            ds[k] = max(0, min(3, int(ds[k])))
    for slot in (sheet.get("spellcasting") or {}).get("slots", {}).values():
        slot["used"] = max(0, min(int(slot.get("used", 0)), int(slot.get("max", 0))))
    for r in sheet.get("resources") or []:
        r["used"] = max(0, min(int(r.get("used", 0)), int(r.get("max", 0))))
    return sheet
