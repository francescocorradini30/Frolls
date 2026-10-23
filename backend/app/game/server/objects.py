"""GameServer handlers: objects, undo, redo, history."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update

from app.db import session_scope
from app.game import permissions
from app.game import protocol as p
from app.game.serialize import (
    object_dict,
)
from app.game.server.base import (
    HISTORY_LIMIT,
    UNDO_LIMIT,
    Connection,
    GameError,
    ServerBase,
    _copy,
    _describe,
    _history_entry,
    _name,
    _other,
    _verb,
)
from app.models import (
    Event,
    MapObject,
    Player,
)


class ObjectsMixin(ServerBase):
    # --- Objects -------------------------------------------------------------

    async def on_obj_create(self, conn: Connection, msg: p.ObjectCreate) -> None:
        player = conn.player
        assert player is not None
        created: list[MapObject] = []
        top = self._top_z()
        for data in msg.objects:
            self._get_page(data.page_id)
            if data.id in self.objects:
                raise GameError(f"id {data.id} already in use")
            if not permissions.can_create(player, data.model_dump()):
                raise GameError("you cannot create this object")
            top += 1
            fields = data.model_dump()
            fields["z"] = top if data.z is None else data.z
            obj = MapObject(**fields, owner_id=player.id)
            self._hp_from_sheet(obj)
            created.append(obj)
        changes = [{"id": o.id, "before": None, "after": object_dict(o)} for o in created]
        summary = "created " + _describe(created)
        ids = [o.id for o in created]
        async with self._commit(msg.type, summary, {"objects": changes}, ids) as s:
            s.add_all(created)
        for o in created:
            self.objects[o.id] = o
        self._publish_objects(created, [], {})
        self._push_undo(player, summary, changes)
        await self._after_card_tokens_change(created)

    def _top_z(self) -> float:
        return max((o.z for o in self.objects.values()), default=0)

    async def on_obj_update(self, conn: Connection, msg: p.ObjectUpdate) -> None:
        player = conn.player
        assert player is not None
        planned: list[tuple[MapObject, dict[str, Any]]] = []
        for patch in msg.patches:
            obj = self._get_object(patch.id)
            values = patch.model_dump(exclude_unset=True, exclude={"id"})
            if not permissions.controls(player, obj):
                raise GameError("you do not control this object")
            if error := permissions.check_patch(player, values, obj):
                raise GameError(error)
            if "page_id" in values:
                self._get_page(values["page_id"])
            if "props" in values:
                merged = {**obj.props, **values["props"]}
                values["props"] = {k: v for k, v in merged.items() if v is not None}
            # Only real changes: they are what undo restores.
            values = {k: v for k, v in values.items() if getattr(obj, k) != v}
            if values:
                planned.append((obj, values))
        if not planned:
            return

        changes = [
            {
                "id": obj.id,
                "before": {k: _copy(getattr(obj, k)) for k in values},
                "after": _copy(values),
            }
            for obj, values in planned
        ]
        summary = _verb(changes) + " " + _describe([obj for obj, _ in planned])
        ids = [obj.id for obj, _ in planned]
        async with self._commit(msg.type, summary, {"objects": changes}, ids) as s:
            for obj, values in planned:
                await s.execute(update(MapObject).where(MapObject.id == obj.id).values(**values))
        old_pages = {obj.id: obj.page_id for obj, _ in planned}
        for obj, values in planned:
            for k, v in values.items():
                setattr(obj, k, v)
        self._publish_objects([obj for obj, _ in planned], [], old_pages)
        self._push_undo(player, summary, changes)
        await self._after_token_change(changes)
        await self._track_movement(changes, msg.via)

    def _publish_objects(
        self, changed: list[MapObject], removed: list[MapObject], old_pages: dict[str, str]
    ) -> None:
        """Broadcast changed and removed objects to the viewers of their pages."""
        touched: dict[str, list[MapObject]] = {}
        for obj in changed:
            touched.setdefault(obj.page_id, []).append(obj)
            old_page = old_pages.get(obj.id, obj.page_id)
            if old_page != obj.page_id:
                for c in self._viewers(old_page):
                    c.send({"type": "obj.removed", "ids": [obj.id]})
        for page_id, objs in touched.items():
            self._broadcast_objects(page_id, objs)
        gone: dict[str, list[str]] = {}
        for obj in removed:
            gone.setdefault(obj.page_id, []).append(obj.id)
        for page_id, ids in gone.items():
            for c in self._viewers(page_id):
                c.send({"type": "obj.removed", "ids": ids})
        # Turn entries of tokens moved to/from the GM layer appear/disappear for players.
        assert self.game is not None
        if {o.id for o in changed} & {e.get("object_id") for e in self.game.turn_order}:
            self._broadcast_game()

    async def on_obj_preview(self, conn: Connection, msg: p.ObjectPreview) -> None:
        player = conn.player
        assert player is not None
        items = []
        page_id: str | None = None
        for item in msg.items:
            obj = self.objects.get(item.id)
            if obj is None or not permissions.controls(player, obj):
                continue
            page_id = obj.page_id
            items.append(item.model_dump(exclude_none=True))
        if not items or page_id is None:
            return
        for c in self._viewers(page_id):
            if c is conn:
                continue
            assert c.player is not None
            visible = [i for i in items if self._can_see(c.player, self.objects[i["id"]])]
            if visible:
                c.send({"type": "obj.preview", "items": visible})

    async def on_obj_delete(self, conn: Connection, msg: p.ObjectDelete) -> None:
        player = conn.player
        assert player is not None
        objs = [self._get_object(i) for i in msg.ids]
        for obj in objs:
            gm_or_owner = player.is_gm or (
                obj.owner_id == player.id and obj.kind in permissions.DRAWING_KINDS
            )
            if not gm_or_owner:
                raise GameError("you cannot delete this object")
        changes = [{"id": o.id, "before": object_dict(o), "after": None} for o in objs]
        summary = "deleted " + _describe(objs)
        ids = [o.id for o in objs]
        async with self._commit(msg.type, summary, {"objects": changes}, ids) as s:
            await s.execute(delete(MapObject).where(MapObject.id.in_(ids)))
        for obj in objs:
            del self.objects[obj.id]
        self._publish_objects([], objs, {})
        self._push_undo(player, summary, changes)
        await self._prune_turn_order(set(ids))
        await self._after_card_tokens_change(objs)

    async def on_obj_order(self, conn: Connection, msg: p.ObjectOrder) -> None:
        player = conn.player
        assert player is not None
        objs = [self._get_object(i) for i in msg.ids]
        for obj in objs:
            if not permissions.controls(player, obj):
                raise GameError("you do not control this object")
        objs.sort(key=lambda o: o.z)
        if msg.to == "front":
            base = self._top_z()
            new_z = [base + i + 1 for i in range(len(objs))]
        else:
            base = min(o.z for o in self.objects.values())
            new_z = [base - len(objs) + i for i in range(len(objs))]
        patches = [p.ObjectPatch(id=o.id, z=z) for o, z in zip(objs, new_z, strict=True)]
        await self.on_obj_update(conn, p.ObjectUpdate(type="obj.update", patches=patches))

    # --- Undo, redo, history -------------------------------------------------

    def _push_undo(self, player: Player, summary: str, changes: list[dict[str, Any]]) -> None:
        """A new action of `player`: it becomes undoable and clears what could be redone."""
        stack = self.undo.setdefault(player.id, [])
        stack.append({"seq": self.seq, "summary": summary, "objects": changes})
        del stack[:-UNDO_LIMIT]
        self.redo.pop(player.id, None)
        self._send_undo_state(player.id)

    def _send_undo_state(self, player_id: str) -> None:
        undo, redo = self.undo.get(player_id), self.redo.get(player_id)
        message = {
            "type": "undo.state",
            "undo": undo[-1]["summary"] if undo else None,
            "redo": redo[-1]["summary"] if redo else None,
        }
        for c in self.connections:
            if c.player and c.player.id == player_id:
                c.send(message)

    def _conflict(self, changes: list[dict[str, Any]], side: str) -> str | None:
        """Why the objects are no longer as `side` ("before"/"after") left them, if so."""
        for ch in changes:
            expected = ch[side]
            obj = self.objects.get(ch["id"])
            if expected is None:
                if obj is not None:
                    return f"{_describe([obj])} exists again"
            elif obj is None:
                return f"{_name(expected)} was deleted since"
            elif any(_copy(getattr(obj, k)) != v for k, v in expected.items()):
                return f"{_describe([obj])} was changed since"
            target = ch[_other(side)]
            if target is not None and target.get("page_id", obj and obj.page_id) not in self.pages:
                return "its page no longer exists"
        return None

    async def _apply(self, changes: list[dict[str, Any]], frm: str, kind: str, summary: str) -> int:
        """Bring the objects from state `frm` to the other one, as a new event; returns its seq."""
        if reason := self._conflict(changes, frm):
            raise GameError(f"cannot {kind}: {reason}")
        to = _other(frm)
        applied = [{"id": ch["id"], "before": ch[frm], "after": ch[to]} for ch in changes]
        ids = [ch["id"] for ch in changes]
        async with self._commit(kind, summary, {"objects": applied}, ids) as s:
            for ch in applied:
                if ch["after"] is None:
                    await s.execute(delete(MapObject).where(MapObject.id == ch["id"]))
                elif ch["before"] is None:
                    s.add(MapObject(**_copy(ch["after"])))
                else:
                    await s.execute(
                        update(MapObject).where(MapObject.id == ch["id"]).values(**ch["after"])
                    )
        changed: list[MapObject] = []
        removed: list[MapObject] = []
        old_pages: dict[str, str] = {}
        for ch in applied:
            if ch["after"] is None:
                removed.append(self.objects.pop(ch["id"]))
            elif ch["before"] is None:
                obj = MapObject(**_copy(ch["after"]))
                self.objects[obj.id] = obj
                changed.append(obj)
            else:
                obj = self.objects[ch["id"]]
                old_pages[obj.id] = obj.page_id
                for k, v in _copy(ch["after"]).items():
                    setattr(obj, k, v)
                changed.append(obj)
        seq = self.seq
        self._publish_objects(changed, removed, old_pages)
        await self._after_token_change(applied)
        if removed:
            await self._prune_turn_order({o.id for o in removed})
        await self._after_card_tokens_change(changed + removed)
        return seq

    async def _mark_reverted(self, seq: int, by: int | None) -> None:
        async with session_scope() as s:
            await s.execute(
                update(Event)
                .where(Event.game_id == self.game_id, Event.seq == seq)
                .values(reverted_by=by)
            )
        for c in self.connections:
            if c.player and c.player.is_gm:
                c.send({"type": "history.update", "event_seq": seq, "reverted": by is not None})

    def _skip_if_stale(
        self, player: Player, stack: list[dict[str, Any]], side: str, kind: str
    ) -> None:
        """A step whose objects someone else changed can never apply: drop it, so the
        next Ctrl+Z reaches the step before instead of failing forever."""
        if reason := self._conflict(stack[-1]["objects"], side):
            stack.pop()
            self._send_undo_state(player.id)
            raise GameError(f"cannot {kind}: {reason}, so it was skipped")

    async def on_undo(self, conn: Connection, msg: p.Undo) -> None:
        player = conn.player
        assert player is not None
        stack = self.undo.get(player.id)
        if not stack:
            raise GameError("nothing to undo")
        step = stack[-1]
        self._skip_if_stale(player, stack, "after", "undo")
        undo_seq = await self._apply(step["objects"], "after", "undo", f"undid: {step['summary']}")
        stack.pop()
        self.redo.setdefault(player.id, []).append(step)
        await self._mark_reverted(step["seq"], undo_seq)
        self._send_undo_state(player.id)
        conn.send({"type": "notice", "detail": f"Undone: {step['summary']}"})

    async def on_redo(self, conn: Connection, msg: p.Redo) -> None:
        player = conn.player
        assert player is not None
        stack = self.redo.get(player.id)
        if not stack:
            raise GameError("nothing to redo")
        step = stack[-1]
        self._skip_if_stale(player, stack, "before", "redo")
        await self._apply(step["objects"], "before", "redo", f"redid: {step['summary']}")
        stack.pop()
        self.undo.setdefault(player.id, []).append(step)
        await self._mark_reverted(step["seq"], None)
        self._send_undo_state(player.id)
        conn.send({"type": "notice", "detail": f"Redone: {step['summary']}"})

    async def on_event_revert(self, conn: Connection, msg: p.EventRevert) -> None:
        """GM: undo any map-object change from the history, whoever made it."""
        self._require_gm(conn)
        async with session_scope() as s:
            event = await s.get(Event, (self.game_id, msg.seq))
        if event is None or not event.data.get("objects"):
            raise GameError("this change cannot be reverted")
        if event.reverted_by is not None:
            raise GameError("this change was already reverted")
        revert_seq = await self._apply(
            event.data["objects"], "after", "revert", f"reverted: {event.summary}"
        )
        await self._mark_reverted(event.seq, revert_seq)
        # It no longer is anyone's last action.
        for stacks in (self.undo, self.redo):
            for pid, stack in stacks.items():
                if any(step["seq"] == event.seq for step in stack):
                    stack[:] = [step for step in stack if step["seq"] != event.seq]
                    self._send_undo_state(pid)
        conn.send({"type": "notice", "detail": f"Reverted: {event.summary}"})

    async def on_history_get(self, conn: Connection, msg: p.HistoryGet) -> None:
        self._require_gm(conn)
        async with session_scope() as s:
            events = list(
                await s.scalars(
                    select(Event)
                    .where(Event.game_id == self.game_id)
                    .order_by(Event.seq.desc())
                    .limit(HISTORY_LIMIT)
                )
            )
        conn.send({"type": "history", "events": [_history_entry(e) for e in reversed(events)]})
