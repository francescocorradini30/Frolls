"""Authoritative game server.

State lives in memory (fast reads, per-viewer filtering) and every committed
change is written to Postgres before it is broadcast, under a single lock so
the database order and the broadcast order are the same.

Each connection has its own bounded send queue: a slow client never blocks
the others, and a client that falls too far behind is dropped (it reconnects
and receives a fresh snapshot).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import session_scope
from app.game import chat, permissions, units
from app.game import protocol as p
from app.game.serialize import chat_dict, game_dict, object_dict, page_dict, player_dict
from app.models import DEFAULT_GAME_ID, ChatMessage, Game, MapObject, Page, Player

log = logging.getLogger(__name__)

SEND_QUEUE_SIZE = 1000


class GameError(Exception):
    pass


@dataclass(eq=False)
class Connection:
    ws: WebSocket
    player: Player | None = None
    viewing: str | None = None
    # Page where this connection is showing a live measurement to the others.
    measuring: str | None = None
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(SEND_QUEUE_SIZE))

    def send(self, message: dict[str, Any]) -> None:
        self.send_raw(json.dumps(message, separators=(",", ":")))

    def send_raw(self, payload: str) -> None:
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            log.warning("dropping slow client %s", self.player and self.player.id)
            asyncio.get_running_loop().create_task(self.ws.close(code=1013))


class GameServer:
    def __init__(self) -> None:
        self.game: Game | None = None
        self.players: dict[str, Player] = {}
        self.pages: dict[str, Page] = {}
        self.objects: dict[str, MapObject] = {}
        self.connections: set[Connection] = set()
        self.lock = asyncio.Lock()
        self._loaded = False

    # --- Lifecycle -----------------------------------------------------------

    async def load(self) -> None:
        async with session_scope() as s:
            game = await s.get(Game, DEFAULT_GAME_ID)
            if game is None:
                game = Game(
                    id=DEFAULT_GAME_ID,
                    name="Frolls",
                    player_page_overrides={},
                    turn_order=[],
                    settings={"round": 0, "measurement": units.DEFAULT_MEASUREMENT},
                )
                s.add(game)
                await s.flush()
            self.game = game
            self.players = {
                pl.id: pl for pl in await s.scalars(select(Player).where(Player.game_id == game.id))
            }
            self.pages = {
                pg.id: pg for pg in await s.scalars(select(Page).where(Page.game_id == game.id))
            }
            if not self.pages:
                page = self._new_page(name="Starting map", sort_order=0)
                s.add(page)
                self.pages[page.id] = page
            if game.player_page_id not in self.pages:
                game.player_page_id = min(self.pages.values(), key=lambda pg: pg.sort_order).id
            self.objects = {
                o.id: o
                for o in await s.scalars(
                    select(MapObject).where(MapObject.page_id.in_(list(self.pages)))
                )
            }
        self._loaded = True

    @property
    def measurement(self) -> units.Measurement:
        assert self.game is not None
        return self.game.settings.get("measurement", units.DEFAULT_MEASUREMENT)

    def _new_page(self, **fields: Any) -> Page:
        defaults = {
            column.key: column.default.arg
            for column in Page.__table__.columns
            if column.default is not None and not callable(column.default.arg)
        }
        defaults["scale_number"], defaults["scale_unit"] = units.CELL_SCALE[self.measurement]
        return Page(id=str(uuid.uuid4()), game_id=DEFAULT_GAME_ID, **{**defaults, **fields})

    # --- Connections ---------------------------------------------------------

    async def serve(self, ws: WebSocket) -> None:
        if not self._loaded:
            await self.load()
        conn = Connection(ws)
        writer = asyncio.create_task(self._writer(conn))
        self.connections.add(conn)
        try:
            async for raw in ws.iter_text():
                await self.handle(conn, raw)
        finally:
            self.connections.discard(conn)
            writer.cancel()
            self._end_measure(conn)
            if conn.player:
                self._broadcast_players()

    async def _writer(self, conn: Connection) -> None:
        while True:
            payload = await conn.queue.get()
            try:
                await conn.ws.send_text(payload)
            except Exception:
                return

    async def handle(self, conn: Connection, raw: str) -> None:
        try:
            msg = p.client_message.validate_json(raw)
        except ValidationError as e:
            conn.send({"type": "error", "detail": _validation_summary(e)})
            return

        if conn.player is None and not isinstance(msg, p.Hello):
            conn.send({"type": "error", "rid": msg.rid, "detail": "send hello first"})
            return

        handler = getattr(self, "on_" + msg.type.replace(".", "_"))
        try:
            if isinstance(msg, (p.ObjectPreview, p.Measure, p.Ping)):
                await handler(conn, msg)
            else:
                async with self.lock:
                    await handler(conn, msg)
        except GameError as e:
            conn.send({"type": "error", "rid": msg.rid, "detail": str(e)})
        except Exception:
            # Never let one bad message kill the connection.
            log.exception("error handling %s", msg.type)
            conn.send({"type": "error", "rid": msg.rid, "detail": "internal server error"})

    # --- Helpers -------------------------------------------------------------

    @property
    def gm_ids(self) -> set[str]:
        return {pl.id for pl in self.players.values() if pl.is_gm}

    def _online_ids(self) -> set[str]:
        return {c.player.id for c in self.connections if c.player}

    def player_page(self, player: Player) -> str:
        assert self.game is not None
        override = self.game.player_page_overrides.get(player.id)
        if override in self.pages:
            return override
        assert self.game.player_page_id is not None
        return self.game.player_page_id

    def _objects_on(self, page_id: str) -> list[MapObject]:
        return [o for o in self.objects.values() if o.page_id == page_id]

    def _object_for(self, player: Player, obj: MapObject) -> dict[str, Any]:
        data = object_dict(obj)
        data["props"] = permissions.visible_props(player, obj)
        return data

    def _viewers(self, page_id: str) -> list[Connection]:
        return [c for c in self.connections if c.player and c.viewing == page_id]

    def _page_snapshot(self, conn: Connection, page_id: str) -> None:
        assert conn.player is not None
        if conn.measuring != page_id:
            self._end_measure(conn)
        conn.viewing = page_id
        conn.send(
            {
                "type": "page.snapshot",
                "page": page_dict(self.pages[page_id]),
                "objects": [
                    self._object_for(conn.player, o)
                    for o in self._objects_on(page_id)
                    if permissions.can_see(conn.player, o)
                ],
            }
        )

    def _pages_for(self, player: Player) -> list[dict[str, Any]]:
        if player.is_gm:
            return [page_dict(pg) for pg in self.pages.values()]
        return [page_dict(self.pages[self.player_page(player)])]

    def _broadcast_players(self) -> None:
        online = self._online_ids()
        payload = json.dumps(
            {
                "type": "players",
                "players": [player_dict(pl, pl.id in online) for pl in self.players.values()],
            }
        )
        for c in self.connections:
            if c.player:
                c.send_raw(payload)

    def _broadcast_pages(self) -> None:
        for c in self.connections:
            if c.player:
                c.send({"type": "pages", "pages": self._pages_for(c.player)})

    def _broadcast_game(self) -> None:
        for c in self.connections:
            if c.player:
                c.send({"type": "game", "game": self._game_for(c.player)})

    def _game_for(self, player: Player) -> dict[str, Any]:
        assert self.game is not None
        data = game_dict(self.game)
        if not player.is_gm:
            data["turn_order"] = [e for e in self.game.turn_order if self._turn_visible(e)]
            data["player_page_overrides"] = {}
        return data

    def _turn_visible(self, entry: dict[str, Any]) -> bool:
        obj = self.objects.get(entry.get("object_id") or "")
        return obj is None or obj.layer != "gm"

    def _broadcast_objects(
        self, page_id: str, objs: list[MapObject], exclude: Connection | None = None
    ) -> None:
        for c in self._viewers(page_id):
            if c is exclude:
                continue
            assert c.player is not None
            visible = [
                self._object_for(c.player, o) for o in objs if permissions.can_see(c.player, o)
            ]
            hidden = [o.id for o in objs if not permissions.can_see(c.player, o)]
            if visible:
                c.send({"type": "obj.upsert", "objects": visible})
            if hidden:
                # e.g. a token moved to the GM layer disappears for players.
                c.send({"type": "obj.removed", "ids": hidden})

    def _require_gm(self, conn: Connection) -> Player:
        assert conn.player is not None
        if not conn.player.is_gm:
            raise GameError("only the GM can do that")
        return conn.player

    def _get_object(self, obj_id: str) -> MapObject:
        obj = self.objects.get(obj_id)
        if obj is None:
            raise GameError(f"object {obj_id} does not exist")
        return obj

    def _get_page(self, page_id: str) -> Page:
        page = self.pages.get(page_id)
        if page is None:
            raise GameError(f"page {page_id} does not exist")
        return page

    # --- Session -------------------------------------------------------------

    async def on_hello(self, conn: Connection, msg: p.Hello) -> None:
        info = msg.player
        player_id = info.id
        if player_id not in self.players:
            # Joining with the name of an offline player takes that player back,
            # so new tabs don't pile up duplicates. The client adopts the id from `welcome`.
            online = self._online_ids()
            key = info.name.strip().casefold()
            match = next(
                (
                    pl
                    for pl in self.players.values()
                    if pl.id not in online and pl.name.strip().casefold() == key
                ),
                None,
            )
            if match is not None:
                player_id = match.id
        values = {"name": info.name, "color": info.color, "is_gm": info.is_gm}
        async with session_scope() as s:
            # Upsert: safe even if the row exists but this process hasn't seen it yet.
            await s.execute(
                pg_insert(Player)
                .values(id=player_id, game_id=DEFAULT_GAME_ID, **values)
                .on_conflict_do_update(index_elements=[Player.id], set_=values)
            )
            history = list(
                await s.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.game_id == DEFAULT_GAME_ID)
                    .order_by(ChatMessage.id.desc())
                    .limit(settings.chat_history_limit)
                )
            )
        player = self.players.get(player_id)
        if player is None:
            player = Player(id=player_id, game_id=DEFAULT_GAME_ID, **values)
            self.players[player.id] = player
        else:
            player.name, player.color, player.is_gm = info.name, info.color, info.is_gm
        conn.player = player
        online = self._online_ids()
        conn.send(
            {
                "type": "welcome",
                "you": player_dict(player, True, private=True),
                "game": self._game_for(player),
                "players": [player_dict(pl, pl.id in online) for pl in self.players.values()],
                "pages": self._pages_for(player),
                "chat": [chat_dict(m) for m in reversed(history) if self._chat_visible(player, m)],
            }
        )
        self._page_snapshot(conn, self.player_page(player))
        self._broadcast_players()

    async def on_player_update(self, conn: Connection, msg: p.PlayerUpdate) -> None:
        player = conn.player
        assert player is not None
        values = msg.model_dump(exclude_none=True, exclude={"type", "rid", "settings"})
        if msg.settings is not None:
            values["settings"] = {
                **(player.settings or {}),
                **msg.settings.model_dump(exclude_none=True),
            }
        if not values:
            return
        async with session_scope() as s:
            await s.execute(update(Player).where(Player.id == player.id).values(**values))
        for k, v in values.items():
            setattr(player, k, v)
        # Settings are private and already applied by the client: only name/colour are news.
        if values.keys() - {"settings"}:
            self._broadcast_players()

    async def on_game_settings(self, conn: Connection, msg: p.GameSettings) -> None:
        self._require_gm(conn)
        assert self.game is not None
        if msg.measurement is None or msg.measurement == self.measurement:
            return
        # Convert every page scale to the new system: 5 ft <-> 1.5 m.
        conversions = units.CONVERSIONS[msg.measurement]
        pages: list[tuple[Page, str, float]] = [
            (pg, *conversions[pg.scale_unit])
            for pg in self.pages.values()
            if pg.scale_unit in conversions
        ]
        game_settings = {**self.game.settings, "measurement": msg.measurement}
        async with session_scope() as s:
            await s.execute(
                update(Game).where(Game.id == self.game.id).values(settings=game_settings)
            )
            for pg, unit, factor in pages:
                await s.execute(
                    update(Page)
                    .where(Page.id == pg.id)
                    .values(scale_number=units.convert(pg.scale_number, factor), scale_unit=unit)
                )
        self.game.settings = game_settings
        for pg, unit, factor in pages:
            pg.scale_number, pg.scale_unit = units.convert(pg.scale_number, factor), unit
        self._broadcast_game()
        self._broadcast_pages()
        for pg, _, _ in pages:
            for c in self._viewers(pg.id):
                c.send({"type": "page.updated", "page": page_dict(pg)})

    # --- Pages ---------------------------------------------------------------

    async def on_page_view(self, conn: Connection, msg: p.PageView) -> None:
        assert conn.player is not None
        self._get_page(msg.page_id)
        if not conn.player.is_gm and msg.page_id != self.player_page(conn.player):
            raise GameError("you cannot see this page")
        self._page_snapshot(conn, msg.page_id)

    async def on_page_create(self, conn: Connection, msg: p.PageCreate) -> None:
        self._require_gm(conn)
        fields = msg.page.model_dump(exclude_none=True)
        fields.setdefault("name", f"Page {len(self.pages) + 1}")
        fields.setdefault(
            "sort_order", max((pg.sort_order for pg in self.pages.values()), default=0) + 1
        )
        page = self._new_page(**fields)
        async with session_scope() as s:
            s.add(page)
        self.pages[page.id] = page
        self._broadcast_pages()
        conn.send({"type": "page.created", "rid": msg.rid, "id": page.id})

    async def on_page_update(self, conn: Connection, msg: p.PageUpdate) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.id)
        values = msg.patch.model_dump(exclude_none=True)
        if not values:
            return
        async with session_scope() as s:
            await s.execute(update(Page).where(Page.id == page.id).values(**values))
        for k, v in values.items():
            setattr(page, k, v)
        self._broadcast_pages()
        for c in self._viewers(page.id):
            c.send({"type": "page.updated", "page": page_dict(page)})

    async def on_page_delete(self, conn: Connection, msg: p.PageDelete) -> None:
        self._require_gm(conn)
        assert self.game is not None
        page = self._get_page(msg.id)
        if len(self.pages) == 1:
            raise GameError("you cannot delete the last page")
        remaining = sorted(
            (pg for pg in self.pages.values() if pg.id != page.id), key=lambda pg: pg.sort_order
        )
        fallback = remaining[0].id
        overrides = {k: v for k, v in self.game.player_page_overrides.items() if v != page.id}
        player_page = fallback if self.game.player_page_id == page.id else self.game.player_page_id
        async with session_scope() as s:
            await s.execute(
                update(Game)
                .where(Game.id == self.game.id)
                .values(player_page_id=player_page, player_page_overrides=overrides)
            )
            await s.execute(delete(Page).where(Page.id == page.id))
        self.game.player_page_id, self.game.player_page_overrides = player_page, overrides
        del self.pages[page.id]
        self.objects = {k: o for k, o in self.objects.items() if o.page_id != page.id}
        self._broadcast_pages()
        self._broadcast_game()
        for c in self.connections:
            if c.player and c.viewing == page.id:
                self._page_snapshot(
                    c, self.player_page(c.player) if not c.player.is_gm else fallback
                )
            elif c.player and not c.player.is_gm:
                if c.viewing != self.player_page(c.player):
                    self._page_snapshot(c, self.player_page(c.player))

    async def on_page_duplicate(self, conn: Connection, msg: p.PageDuplicate) -> None:
        self._require_gm(conn)
        source = self._get_page(msg.id)
        fields = page_dict(source)
        del fields["id"]
        fields["name"] = f"{source.name} (copy)"
        fields["sort_order"] = max(pg.sort_order for pg in self.pages.values()) + 1
        page = self._new_page(**fields)
        copies = [
            MapObject(
                **{
                    **object_dict(o),
                    "id": str(uuid.uuid4()),
                    "page_id": page.id,
                    "props": json.loads(json.dumps(o.props)),
                }
            )
            for o in self._objects_on(source.id)
        ]
        async with session_scope() as s:
            s.add(page)
            await s.flush()
            s.add_all(copies)
        self.pages[page.id] = page
        for o in copies:
            self.objects[o.id] = o
        self._broadcast_pages()
        conn.send({"type": "page.created", "rid": msg.rid, "id": page.id})

    async def on_game_player_page(self, conn: Connection, msg: p.SetPlayerPage) -> None:
        self._require_gm(conn)
        assert self.game is not None
        self._get_page(msg.page_id)
        if msg.player_id is None:
            player_page, overrides = msg.page_id, {}
        else:
            if msg.player_id not in self.players:
                raise GameError("player does not exist")
            player_page = self.game.player_page_id
            overrides = {**self.game.player_page_overrides, msg.player_id: msg.page_id}
        async with session_scope() as s:
            await s.execute(
                update(Game)
                .where(Game.id == self.game.id)
                .values(player_page_id=player_page, player_page_overrides=overrides)
            )
        self.game.player_page_id, self.game.player_page_overrides = player_page, overrides
        self._broadcast_game()
        for c in self.connections:
            if c.player and not c.player.is_gm:
                target = self.player_page(c.player)
                c.send({"type": "pages", "pages": self._pages_for(c.player)})
                if c.viewing != target:
                    self._page_snapshot(c, target)

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
            created.append(MapObject(**fields, owner_id=player.id))
        async with session_scope() as s:
            s.add_all(created)
        for o in created:
            self.objects[o.id] = o
        by_page: dict[str, list[MapObject]] = {}
        for o in created:
            by_page.setdefault(o.page_id, []).append(o)
        for page_id, objs in by_page.items():
            self._broadcast_objects(page_id, objs)

    def _top_z(self) -> float:
        return max((o.z for o in self.objects.values()), default=0)

    async def on_obj_update(self, conn: Connection, msg: p.ObjectUpdate) -> None:
        player = conn.player
        assert player is not None
        planned: list[tuple[MapObject, dict[str, Any], str]] = []
        for patch in msg.patches:
            obj = self._get_object(patch.id)
            values = patch.model_dump(exclude_unset=True, exclude={"id"})
            if not permissions.controls(player, obj):
                raise GameError("you do not control this object")
            if error := permissions.check_patch(player, values):
                raise GameError(error)
            if "page_id" in values:
                self._get_page(values["page_id"])
            if "props" in values:
                merged = {**obj.props, **values["props"]}
                values["props"] = {k: v for k, v in merged.items() if v is not None}
            planned.append((obj, values, obj.page_id))

        async with session_scope() as s:
            for obj, values, _ in planned:
                if values:
                    await s.execute(
                        update(MapObject).where(MapObject.id == obj.id).values(**values)
                    )

        touched: dict[str, list[MapObject]] = {}
        for obj, values, old_page in planned:
            for k, v in values.items():
                setattr(obj, k, v)
            touched.setdefault(obj.page_id, []).append(obj)
            if obj.page_id != old_page:
                for c in self._viewers(old_page):
                    c.send({"type": "obj.removed", "ids": [obj.id]})
        for page_id, objs in touched.items():
            self._broadcast_objects(page_id, objs)
        # Turn entries of tokens moved to/from the GM layer appear/disappear for players.
        layer_changed = {obj.id for obj, values, _ in planned if "layer" in values}
        assert self.game is not None
        if layer_changed & {e.get("object_id") for e in self.game.turn_order}:
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
            visible = [i for i in items if permissions.can_see(c.player, self.objects[i["id"]])]
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
        async with session_scope() as s:
            await s.execute(delete(MapObject).where(MapObject.id.in_([o.id for o in objs])))
        by_page: dict[str, list[str]] = {}
        for obj in objs:
            del self.objects[obj.id]
            by_page.setdefault(obj.page_id, []).append(obj.id)
        for page_id, ids in by_page.items():
            for c in self._viewers(page_id):
                c.send({"type": "obj.removed", "ids": ids})
        await self._prune_turn_order({o.id for o in objs})

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

    # --- Chat ----------------------------------------------------------------

    def _chat_visible(self, player: Player, msg: ChatMessage) -> bool:
        if msg.player_id == player.id:
            return True
        if msg.gm_only:
            return player.is_gm
        if msg.recipients is None:
            return True
        return player.id in msg.recipients or (player.is_gm and "gm" in msg.recipients)

    def _resolve_whisper(self, target: str) -> list[str]:
        if target.lower() == "gm":
            return ["gm"]
        matches = [pl.id for pl in self.players.values() if pl.name.lower() == target.lower()]
        if not matches:
            raise GameError(f'no player is named "{target}"')
        return matches

    async def on_chat_send(self, conn: Connection, msg: p.ChatSend) -> None:
        player = conn.player
        assert player is not None
        try:
            draft = chat.parse(msg.text, is_gm=player.is_gm)
        except chat.ChatError as e:
            raise GameError(str(e)) from e
        recipients = self._resolve_whisper(draft.whisper_to) if draft.whisper_to else None
        roll: dict[str, Any] | None = None
        if draft.roll or draft.inline:
            roll = {"main": draft.roll, "inline": draft.inline}
        row = ChatMessage(
            game_id=DEFAULT_GAME_ID,
            player_id=player.id,
            speaker=player.name,
            color=player.color,
            kind=draft.kind,
            content=draft.content,
            roll=roll,
            recipients=recipients,
            gm_only=draft.gm_only,
        )
        async with session_scope() as s:
            s.add(row)
            await s.flush()
            await s.refresh(row, ["created_at"])
        payload = json.dumps({"type": "chat", "message": chat_dict(row)})
        for c in self.connections:
            if c.player and self._chat_visible(c.player, row):
                c.send_raw(payload)

    # --- Live measurement ----------------------------------------------------

    async def on_measure(self, conn: Connection, msg: p.Measure) -> None:
        player = conn.player
        assert player is not None
        if msg.segment is None or msg.page_id != conn.viewing:
            self._end_measure(conn)
            return
        obj = self.objects.get(msg.object_id) if msg.object_id else None
        if msg.object_id and (obj is None or not permissions.controls(player, obj)):
            return
        if conn.measuring and conn.measuring != msg.page_id:
            self._end_measure(conn)
        conn.measuring = msg.page_id
        payload = {
            "type": "measure",
            "page_id": msg.page_id,
            "player_id": player.id,
            "color": player.color,
            "segment": msg.segment.model_dump(),
        }
        for c in self._viewers(msg.page_id):
            if c is conn:
                continue
            assert c.player is not None
            if obj is None or permissions.can_see(c.player, obj):
                c.send(payload)

    def _end_measure(self, conn: Connection) -> None:
        """Tell the page's viewers that this connection stopped measuring."""
        page_id = conn.measuring
        if page_id is None or conn.player is None:
            return
        conn.measuring = None
        payload = {"type": "measure", "page_id": page_id, "player_id": conn.player.id, "segment": None}
        for c in self._viewers(page_id):
            if c is not conn:
                c.send(payload)

    # --- Ping ----------------------------------------------------------------

    async def on_ping(self, conn: Connection, msg: p.Ping) -> None:
        player = conn.player
        assert player is not None
        pull = msg.pull and player.is_gm
        payload = {
            "type": "ping",
            "page_id": msg.page_id,
            "x": msg.x,
            "y": msg.y,
            "color": player.color,
            "player_id": player.id,
            "pull": pull,
        }
        for c in self._viewers(msg.page_id):
            c.send(payload)

    # --- Turn order ----------------------------------------------------------

    async def _save_turns(self, order: list[dict[str, Any]], round_: int | None = None) -> None:
        assert self.game is not None
        game_settings = self.game.settings
        if round_ is not None:
            game_settings = {**game_settings, "round": round_}
        async with session_scope() as s:
            await s.execute(
                update(Game)
                .where(Game.id == self.game.id)
                .values(turn_order=order, settings=game_settings)
            )
        self.game.turn_order, self.game.settings = order, game_settings
        self._broadcast_game()

    def _controls_entry(self, player: Player, entry: dict[str, Any]) -> bool:
        if player.is_gm:
            return True
        obj = self.objects.get(entry.get("object_id") or "")
        return obj is not None and permissions.controls(player, obj)

    def _find_entry(self, entry_id: str) -> int:
        assert self.game is not None
        for i, e in enumerate(self.game.turn_order):
            if e["id"] == entry_id:
                return i
        raise GameError("entry not found in the turn tracker")

    async def on_turn_set(self, conn: Connection, msg: p.TurnSet) -> None:
        self._require_gm(conn)
        await self._save_turns([e.model_dump() for e in msg.order], msg.round)

    async def on_turn_add(self, conn: Connection, msg: p.TurnAdd) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        entry = msg.entry.model_dump()
        if not player.is_gm:
            if not entry["object_id"] or not self._controls_entry(player, entry):
                raise GameError("you can only add tokens you control")
        if entry["object_id"] and not entry["name"]:
            obj = self.objects.get(entry["object_id"])
            entry["name"] = (obj.props.get("name") if obj else None) or "Token"
        order = [e for e in self.game.turn_order if e["id"] != entry["id"]]
        if entry["object_id"]:
            order = [e for e in order if e.get("object_id") != entry["object_id"]]
        await self._save_turns([*order, entry])

    async def on_turn_update(self, conn: Connection, msg: p.TurnUpdate) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        entry = dict(self.game.turn_order[i])
        if not self._controls_entry(player, entry):
            raise GameError("you do not control this entry")
        if msg.value is not None:
            entry["value"] = msg.value
        if msg.name is not None:
            entry["name"] = msg.name
        order = list(self.game.turn_order)
        order[i] = entry
        await self._save_turns(order)

    async def on_turn_remove(self, conn: Connection, msg: p.TurnRemove) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        if not self._controls_entry(player, self.game.turn_order[i]):
            raise GameError("you do not control this entry")
        await self._save_turns([e for e in self.game.turn_order if e["id"] != msg.id])

    async def on_turn_next(self, conn: Connection, msg: p.TurnNext) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        order = self.game.turn_order
        if not order:
            return
        if not self._controls_entry(player, order[0]):
            raise GameError("it is not your turn")
        rotated = [*order[1:], order[0]]
        round_ = self.game.settings.get("round", 0)
        # A new round starts when the first entry of the sorted order comes back on top.
        if rotated[0]["id"] == _round_head(order):
            round_ += 1
        await self._save_turns(rotated, round_)

    async def on_turn_sort(self, conn: Connection, msg: p.TurnSort) -> None:
        self._require_gm(conn)
        assert self.game is not None
        order = sorted(
            self.game.turn_order, key=lambda e: _turn_value(e["value"]), reverse=msg.descending
        )
        await self._save_turns(order, 1 if order else 0)

    async def _prune_turn_order(self, object_ids: set[str]) -> None:
        assert self.game is not None
        order = [e for e in self.game.turn_order if e.get("object_id") not in object_ids]
        if len(order) != len(self.game.turn_order):
            await self._save_turns(order)


def _turn_value(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("-inf")


def _round_head(order: list[dict[str, Any]]) -> str:
    """Entry that starts a round: the highest initiative."""
    return max(order, key=lambda e: _turn_value(e["value"]))["id"]


def _validation_summary(e: ValidationError) -> str:
    first = e.errors()[0]
    loc = ".".join(str(x) for x in first["loc"])
    return f"invalid message ({loc}: {first['msg']})"


server = GameServer()
