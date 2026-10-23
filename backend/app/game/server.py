"""Authoritative game server.

State lives in memory (fast reads, per-viewer filtering) and every committed
change is written to Postgres before it is broadcast, under a single lock so
the database order and the broadcast order are the same.

Each connection has its own bounded send queue: a slow client never blocks
the others, and a client that falls too far behind is dropped (it reconnects
and receives a fresh snapshot).

Every committed change is also an `Event` with a sequence number (`seq`), written in
the same transaction. Every outgoing message carries the last committed `seq`, so a
client that reconnects asks only for what changed since (`hello.resume`). Map-object
events keep the state before and after: undo, redo and the GM's revert apply them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import compendium
from app.config import settings
from app.db import session_scope
from app.dice import DiceError, TableItem
from app.dice import roll as dice_roll
from app.game import chat, fog, macros, permissions, units
from app.game import protocol as p
from app.game.serialize import (
    asset_dict,
    character_dict,
    chat_dict,
    deck_dict,
    folder_dict,
    game_dict,
    macro_dict,
    object_dict,
    page_dict,
    player_dict,
    table_dict,
)
from app.models import (
    DEFAULT_GAME_ID,
    Asset,
    Character,
    ChatMessage,
    Deck,
    Event,
    Game,
    JournalFolder,
    Macro,
    MapObject,
    Page,
    Player,
    RollableTable,
)
from app.rules5e import damage as damage5e
from app.rules5e import effects as effects5e
from app.rules5e import rolls as rolls5e
from app.rules5e import sheet as sheet5e
from app.rules5e.data import ABILITIES, ABILITY_NAMES, SIZES, SKILLS
from app.rules5e.sheet import Sheet

log = logging.getLogger(__name__)

SEND_QUEUE_SIZE = 1000
# Recent events kept in memory for resuming clients (beyond them: full snapshot).
RECENT_EVENTS = 5000
UNDO_LIMIT = 50
HISTORY_LIMIT = 100
# What a player may change on the character they play.
PLAYER_CHARACTER_FIELDS = {"name", "avatar", "bio", "attributes", "abilities", "sheet"}
SKILL_LABELS = {s: s.replace("_", " ").title() for s in SKILLS}
# Card tokens: one cell wide, in the proportions of a playing card.
CARD_RATIO = 1.4
_rng = secrets.SystemRandom()


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
    # Last committed event seq, stamped on every message.
    seq: Callable[[], int] = lambda: 0

    def send(self, message: dict[str, Any]) -> None:
        self.send_raw(json.dumps({**message, "seq": self.seq()}, separators=(",", ":")))

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
        self.characters: dict[str, Character] = {}
        self.folders: dict[str, JournalFolder] = {}
        self.macros: dict[str, Macro] = {}
        self.tables: dict[str, RollableTable] = {}
        self.decks: dict[str, Deck] = {}
        self.assets: dict[str, Asset] = {}
        self.connections: set[Connection] = set()
        self.lock = asyncio.Lock()
        self._loaded = False
        # Last committed event. Advanced only right before the broadcast of its change,
        # so a message stamped with seq N is never sent before the messages of event N.
        self.seq = 0
        # (seq, ids of the map objects it touched), for resuming clients.
        self.recent: deque[tuple[int, frozenset[str]]] = deque(maxlen=RECENT_EVENTS)
        # Resume works only from a seq above this: older events are no longer in `recent`.
        self.recent_floor = 0
        # Player who sent the message being handled: the author of its events.
        self.actor: Player | None = None
        # Per player: steps {seq, summary, objects} that Ctrl+Z / Ctrl+Y apply.
        self.undo: dict[str, list[dict[str, Any]]] = {}
        self.redo: dict[str, list[dict[str, Any]]] = {}

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
            self.characters = {
                c.id: c
                for c in await s.scalars(select(Character).where(Character.game_id == game.id))
            }
            self.folders = {
                f.id: f
                for f in await s.scalars(
                    select(JournalFolder).where(JournalFolder.game_id == game.id)
                )
            }
            self.macros = {
                m.id: m for m in await s.scalars(select(Macro).where(Macro.game_id == game.id))
            }
            self.tables = {
                t.id: t
                for t in await s.scalars(
                    select(RollableTable).where(RollableTable.game_id == game.id)
                )
            }
            self.decks = {
                d.id: d for d in await s.scalars(select(Deck).where(Deck.game_id == game.id))
            }
            self.assets = {
                a.id: a for a in await s.scalars(select(Asset).where(Asset.game_id == game.id))
            }
            self.seq = (
                await s.scalar(select(func.max(Event.seq)).where(Event.game_id == game.id)) or 0
            )
        self.recent_floor = self.seq
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
        conn = Connection(ws, seq=lambda: self.seq)
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
            if isinstance(
                msg, (p.ObjectPreview, p.Measure, p.Ping, p.CompendiumSearch, p.CompendiumGet)
            ):
                await handler(conn, msg)
            else:
                async with self.lock:
                    self.actor = conn.player
                    try:
                        await handler(conn, msg)
                    finally:
                        self.actor = None
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

    def _can_see(self, player: Player, obj: MapObject) -> bool:
        """Layer rules, plus the fog of war: players don't receive the tokens under it,
        except those they control."""
        if not permissions.can_see(player, obj):
            return False
        if player.is_gm or obj.kind != "token" or permissions.controls(player, obj):
            return True
        page = self.pages.get(obj.page_id)
        return fog.visible(page.fog if page else None, obj.x, obj.y)

    def _object_for(self, player: Player, obj: MapObject) -> dict[str, Any]:
        data = object_dict(obj)
        hp = self.npc_hp if self._is_monster(obj) else "full"
        data["props"] = permissions.visible_props(player, obj, hp)
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
                    if self._can_see(conn.player, o)
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
                "seq": self.seq,
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
            visible = [self._object_for(c.player, o) for o in objs if self._can_see(c.player, o)]
            hidden = [o.id for o in objs if not self._can_see(c.player, o)]
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

    # --- Event log -----------------------------------------------------------

    @asynccontextmanager
    async def _commit(
        self,
        kind: str,
        summary: str,
        data: dict[str, Any] | None = None,
        touched: Iterable[str] = (),
    ) -> AsyncIterator[AsyncSession]:
        """Transaction that also writes the event; on success the event becomes `self.seq`.

        Everything after the block up to the broadcast must stay synchronous: the new
        seq is visible to every message sent from then on.
        """
        seq = self.seq + 1
        author = self.actor.id if self.actor else None
        event = Event(
            game_id=DEFAULT_GAME_ID,
            seq=seq,
            created_at=datetime.now(UTC),
            player_id=author,
            kind=kind,
            summary=summary[:200],
            data=data or {},
        )
        async with session_scope() as s:
            yield s
            s.add(event)
        self.seq = seq
        if len(self.recent) == self.recent.maxlen:
            self.recent_floor = self.recent[0][0]
        self.recent.append((seq, frozenset(touched)))
        for c in self.connections:
            if c.player and c.player.is_gm:
                c.send({"type": "history.add", "event": _history_entry(event)})

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
        player = self.players.get(player_id)
        if player is None:
            player = Player(id=player_id, game_id=DEFAULT_GAME_ID, **values)
        else:
            player.name, player.color, player.is_gm = info.name, info.color, info.is_gm
        resume = msg.resume if msg.resume and self._can_resume(player, msg.resume) else None
        limit = settings.chat_history_limit
        async with session_scope() as s:
            # Upsert: safe even if the row exists but this process hasn't seen it yet.
            await s.execute(
                pg_insert(Player)
                .values(id=player_id, game_id=DEFAULT_GAME_ID, **values)
                .on_conflict_do_update(index_elements=[Player.id], set_=values)
            )
            chat_query = select(ChatMessage).where(ChatMessage.game_id == DEFAULT_GAME_ID)
            new_chat: list[ChatMessage] | None = None
            if resume and resume.chat_id is not None:
                new_chat = list(
                    await s.scalars(
                        chat_query.where(ChatMessage.id > resume.chat_id)
                        .order_by(ChatMessage.id)
                        .limit(limit + 1)
                    )
                )
            if new_chat is None or len(new_chat) > limit:
                # Fresh join, or too much missed: the whole recent history.
                new_chat = None
                history = list(
                    await s.scalars(chat_query.order_by(ChatMessage.id.desc()).limit(limit))
                )[::-1]
            else:
                history = new_chat
        self.players[player.id] = player
        conn.player = player
        online = self._online_ids()
        conn.send(
            {
                "type": "welcome",
                "you": player_dict(player, True, private=True),
                "game": self._game_for(player),
                "players": [player_dict(pl, pl.id in online) for pl in self.players.values()],
                "pages": self._pages_for(player),
                "journal": self._journal_for(player),
                "macros": [macro_dict(m) for m in self._macros_of(player.id)],
                "tables": [
                    table_dict(t) for t in self.tables.values() if self._sees_table(player, t)
                ],
                "decks": [
                    self._deck_for(player, d)
                    for d in self.decks.values()
                    if self._sees_deck(player, d)
                ],
                "assets": [asset_dict(a) for a in self.assets.values() if a.player_id == player.id],
                "chat": [chat_dict(m) for m in history if self._chat_visible(player, m)],
                # append: `chat` holds only the messages missed while disconnected.
                "chat_mode": "replace" if new_chat is None else "append",
                "resumed": resume is not None,
            }
        )
        if resume:
            self._page_resume(conn, resume)
        else:
            self._page_snapshot(conn, self.player_page(player))
        self._send_undo_state(player.id)
        self._broadcast_players()

    def _can_resume(self, player: Player, resume: p.Resume) -> bool:
        """The client's page state is still recoverable from the recent events."""
        if not self.recent_floor < resume.seq <= self.seq or resume.page_id not in self.pages:
            return False
        return player.is_gm or resume.page_id == self.player_page(player)

    def _page_resume(self, conn: Connection, resume: p.Resume) -> None:
        """Send only the objects of the page that changed since `resume.seq`.

        Events from `resume.seq` included: the client may have lost part of its messages.
        """
        assert conn.player is not None
        page_id = resume.page_id
        if conn.measuring != page_id:
            self._end_measure(conn)
        conn.viewing = page_id
        touched: set[str] = set()
        for seq, ids in self.recent:
            if seq >= resume.seq:
                touched |= ids
        objects, removed = [], []
        for oid in sorted(touched):
            obj = self.objects.get(oid)
            if obj and obj.page_id == page_id and self._can_see(conn.player, obj):
                objects.append(self._object_for(conn.player, obj))
            else:
                removed.append(oid)
        conn.send(
            {
                "type": "page.resume",
                "page": page_dict(self.pages[page_id]),
                "objects": objects,
                "removed": removed,
            }
        )

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
        summary = (
            "changed name or colour" if values.keys() - {"settings"} else "changed own settings"
        )
        async with self._commit(msg.type, summary) as s:
            await s.execute(update(Player).where(Player.id == player.id).values(**values))
        for k, v in values.items():
            setattr(player, k, v)
        # Settings are private and already applied by the client: only name/colour are news.
        if values.keys() - {"settings"}:
            self._broadcast_players()

    async def on_game_settings(self, conn: Connection, msg: p.GameSettings) -> None:
        self._require_gm(conn)
        assert self.game is not None
        if msg.npc_hp is not None and msg.npc_hp != self.npc_hp:
            game_settings = {**self.game.settings, "npc_hp": msg.npc_hp}
            async with self._commit(msg.type, f"monster hit points: {msg.npc_hp}") as s:
                await s.execute(
                    update(Game).where(Game.id == self.game.id).values(settings=game_settings)
                )
            self.game.settings = game_settings
            self._broadcast_game()
            # Players' copies of the tokens change: send them their pages again.
            for c in self.connections:
                if c.player and not c.player.is_gm and c.viewing:
                    self._page_snapshot(c, c.viewing)
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
        async with self._commit(msg.type, f"set measurement to {msg.measurement}") as s:
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
        async with self._commit(msg.type, f'created page "{page.name}"') as s:
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
        async with self._commit(msg.type, f'changed page "{page.name}"') as s:
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
        async with self._commit(msg.type, f'deleted page "{page.name}"') as s:
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
        async with self._commit(msg.type, f'duplicated page "{source.name}"') as s:
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
        who = "all players" if msg.player_id is None else self.players[msg.player_id].name
        summary = f'moved {who} to page "{self.pages[msg.page_id].name}"'
        async with self._commit(msg.type, summary) as s:
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
                .where(Event.game_id == DEFAULT_GAME_ID, Event.seq == seq)
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
            event = await s.get(Event, (DEFAULT_GAME_ID, msg.seq))
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
                    .where(Event.game_id == DEFAULT_GAME_ID)
                    .order_by(Event.seq.desc())
                    .limit(HISTORY_LIMIT)
                )
            )
        conn.send({"type": "history", "events": [_history_entry(e) for e in reversed(events)]})

    # --- Journal -------------------------------------------------------------

    def _sees_character(self, player: Player, character: Character) -> bool:
        """GMs see every character; a player sees only the ones they play."""
        return player.is_gm or character.player_id == player.id

    def _journal_for(self, player: Player) -> dict[str, Any]:
        return {
            "characters": [
                character_dict(c, player.is_gm)
                for c in self.characters.values()
                if self._sees_character(player, c)
            ],
            # Folders organise the GM's journal; players see their characters flat.
            "folders": [folder_dict(f) for f in self.folders.values()] if player.is_gm else [],
        }

    def _broadcast_character(self, character: Character, old_player: str | None) -> None:
        for c in self.connections:
            if not c.player:
                continue
            if self._sees_character(c.player, character):
                c.send(
                    {
                        "type": "journal.upsert",
                        "characters": [character_dict(character, c.player.is_gm)],
                    }
                )
            elif old_player == c.player.id:
                # Taken away from this player.
                c.send({"type": "journal.removed", "character_ids": [character.id]})

    def _broadcast_folders(self, upsert: list[JournalFolder], removed: list[str]) -> None:
        for c in self.connections:
            if c.player and c.player.is_gm:
                if upsert:
                    c.send({"type": "journal.upsert", "folders": [folder_dict(f) for f in upsert]})
                if removed:
                    c.send({"type": "journal.removed", "folder_ids": removed})

    def _get_character(self, character_id: str) -> Character:
        character = self.characters.get(character_id)
        if character is None:
            raise GameError("character does not exist")
        return character

    def _character_values(self, patch: p.CharacterPatch) -> dict[str, Any]:
        values = patch.model_dump(exclude_unset=True)
        if patch.sheet is not None:
            # The whole sheet with every default filled in, not only the fields sent.
            values["sheet"] = patch.sheet.model_dump()
        for key in ("name", "bio", "gm_notes", "attributes", "archived"):
            if key in values and values[key] is None:
                raise GameError(f"{key} cannot be empty")
        if "name" in values:
            values["name"] = values["name"].strip() or "Unnamed"
        if values.get("folder_id") is not None and values["folder_id"] not in self.folders:
            raise GameError("folder does not exist")
        if values.get("player_id") is not None and values["player_id"] not in self.players:
            raise GameError("player does not exist")
        return values

    async def on_char_create(self, conn: Connection, msg: p.CharacterCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.characters:
            raise GameError(f"id {msg.id} already in use")
        values = self._character_values(msg.character)
        character = Character(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            **{
                "name": "New character",
                "bio": "",
                "gm_notes": "",
                "attributes": [],
                "archived": False,
                **values,
            },
        )
        async with self._commit(msg.type, f'created character "{character.name}"') as s:
            s.add(character)
        self.characters[character.id] = character
        self._broadcast_character(character, None)

    async def on_char_update(self, conn: Connection, msg: p.CharacterUpdate) -> None:
        player = conn.player
        assert player is not None
        character = self._get_character(msg.id)
        values = self._character_values(msg.patch)
        if not player.is_gm:
            if character.player_id != player.id:
                raise GameError("you can only edit your own character")
            if values.keys() - PLAYER_CHARACTER_FIELDS:
                raise GameError("only the GM can change notes, folder, player or archive")
        values = {k: v for k, v in values.items() if getattr(character, k) != v}
        if not values:
            return
        old_player = character.player_id
        async with self._commit(msg.type, f'edited character "{character.name}"') as s:
            await s.execute(update(Character).where(Character.id == character.id).values(**values))
        old_sheet = character.sheet
        for k, v in values.items():
            setattr(character, k, v)
        self._broadcast_character(character, old_player)
        if "sheet" in values:
            await self._sync_tokens(character)
            if (old_sheet or {}).get("size") != (character.sheet or {}).get("size"):
                await self._fit_tokens(character)

    async def on_char_delete(self, conn: Connection, msg: p.CharacterDelete) -> None:
        self._require_gm(conn)
        character = self._get_character(msg.id)
        # Tokens that represented it become plain tokens.
        linked = [o for o in self.objects.values() if o.props.get("represents") == character.id]
        async with self._commit(
            msg.type, f'deleted character "{character.name}"', None, [o.id for o in linked]
        ) as s:
            await s.execute(delete(Character).where(Character.id == character.id))
            for o in linked:
                props = {k: v for k, v in o.props.items() if k != "represents"}
                await s.execute(update(MapObject).where(MapObject.id == o.id).values(props=props))
        for o in linked:
            o.props = {k: v for k, v in o.props.items() if k != "represents"}
        del self.characters[character.id]
        for c in self.connections:
            if c.player and self._sees_character(c.player, character):
                c.send({"type": "journal.removed", "character_ids": [character.id]})
        self._publish_objects(linked, [], {})

    async def on_folder_create(self, conn: Connection, msg: p.FolderCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.folders:
            raise GameError(f"id {msg.id} already in use")
        if msg.parent_id is not None and msg.parent_id not in self.folders:
            raise GameError("folder does not exist")
        folder = JournalFolder(
            id=msg.id, game_id=DEFAULT_GAME_ID, name=msg.name.strip(), parent_id=msg.parent_id
        )
        async with self._commit(msg.type, f'created folder "{folder.name}"') as s:
            s.add(folder)
        self.folders[folder.id] = folder
        self._broadcast_folders([folder], [])

    async def on_folder_update(self, conn: Connection, msg: p.FolderUpdate) -> None:
        self._require_gm(conn)
        folder = self.folders.get(msg.id)
        if folder is None:
            raise GameError("folder does not exist")
        values = msg.model_dump(exclude_unset=True, include={"name", "parent_id"})
        if values.get("name") is None:
            values.pop("name", None)
        if "parent_id" in values:
            parent = values["parent_id"]
            # A folder cannot go inside itself or one of its subfolders.
            while parent is not None:
                if parent == folder.id:
                    raise GameError("a folder cannot go inside itself")
                if parent not in self.folders:
                    raise GameError("folder does not exist")
                parent = self.folders[parent].parent_id
        if not values:
            return
        async with self._commit(msg.type, f'changed folder "{folder.name}"') as s:
            await s.execute(
                update(JournalFolder).where(JournalFolder.id == folder.id).values(**values)
            )
        for k, v in values.items():
            setattr(folder, k, v)
        self._broadcast_folders([folder], [])

    async def on_folder_delete(self, conn: Connection, msg: p.FolderDelete) -> None:
        self._require_gm(conn)
        folder = self.folders.get(msg.id)
        if folder is None:
            raise GameError("folder does not exist")
        children = [f for f in self.folders.values() if f.parent_id == folder.id]
        members = [c for c in self.characters.values() if c.folder_id == folder.id]
        async with self._commit(msg.type, f'deleted folder "{folder.name}"') as s:
            await s.execute(
                update(JournalFolder)
                .where(JournalFolder.parent_id == folder.id)
                .values(parent_id=folder.parent_id)
            )
            await s.execute(
                update(Character)
                .where(Character.folder_id == folder.id)
                .values(folder_id=folder.parent_id)
            )
            await s.execute(delete(JournalFolder).where(JournalFolder.id == folder.id))
        del self.folders[folder.id]
        for f in children:
            f.parent_id = folder.parent_id
        self._broadcast_folders(children, [folder.id])
        for character in members:
            character.folder_id = folder.parent_id
            self._broadcast_character(character, character.player_id)

    def _speaker(self, player: Player, as_character: str | None) -> str:
        """Chat name: a player speaks as their character, the GM as whoever they pick."""
        if player.is_gm:
            if as_character is None:
                return player.name
            return self._get_character(as_character).name
        own = self._own_character(player)
        return own.name if own else player.name

    def _own_character(self, player: Player) -> Character | None:
        mine = [c for c in self.characters.values() if c.player_id == player.id and not c.archived]
        return min(mine, key=lambda c: c.name.casefold()) if mine else None

    # --- Macros --------------------------------------------------------------

    def _macros_of(self, player_id: str) -> list[Macro]:
        return [m for m in self.macros.values() if m.player_id == player_id]

    def _send_macros(self, player_id: str, upsert: list[Macro], removed: list[str]) -> None:
        """Macros are private: only the owner's connections hear about them."""
        for c in self.connections:
            if c.player and c.player.id == player_id:
                if upsert:
                    c.send({"type": "macro.upsert", "macros": [macro_dict(m) for m in upsert]})
                if removed:
                    c.send({"type": "macro.removed", "ids": removed})

    def _own_macro(self, player: Player, macro_id: str) -> Macro:
        macro = self.macros.get(macro_id)
        if macro is None or macro.player_id != player.id:
            raise GameError("macro does not exist")
        return macro

    async def on_macro_create(self, conn: Connection, msg: p.MacroCreate) -> None:
        player = conn.player
        assert player is not None
        if msg.id in self.macros:
            raise GameError(f"id {msg.id} already in use")
        macro = Macro(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            player_id=player.id,
            name=_macro_name(msg.name),
            action=msg.action,
            in_bar=msg.in_bar,
        )
        async with self._commit(msg.type, f'created macro "{macro.name}"') as s:
            s.add(macro)
        self.macros[macro.id] = macro
        self._send_macros(player.id, [macro], [])

    async def on_macro_update(self, conn: Connection, msg: p.MacroUpdate) -> None:
        player = conn.player
        assert player is not None
        macro = self._own_macro(player, msg.id)
        values = msg.model_dump(exclude_none=True, include={"name", "action", "in_bar"})
        if "name" in values:
            values["name"] = _macro_name(values["name"])
        values = {k: v for k, v in values.items() if getattr(macro, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited macro "{macro.name}"') as s:
            await s.execute(update(Macro).where(Macro.id == macro.id).values(**values))
        for k, v in values.items():
            setattr(macro, k, v)
        self._send_macros(player.id, [macro], [])

    async def on_macro_delete(self, conn: Connection, msg: p.MacroDelete) -> None:
        player = conn.player
        assert player is not None
        macro = self._own_macro(player, msg.id)
        async with self._commit(msg.type, f'deleted macro "{macro.name}"') as s:
            await s.execute(delete(Macro).where(Macro.id == macro.id))
        del self.macros[macro.id]
        self._send_macros(player.id, [], [macro.id])

    # --- 5e sheet rolls -------------------------------------------------------

    def _sheet_of(self, player: Player, character_id: str) -> tuple[Character, Sheet]:
        """Character and its 5e sheet, if `player` may roll for it (GM, or who plays it)."""
        character = self._get_character(character_id)
        if not player.is_gm and character.player_id != player.id:
            raise GameError("you can only roll for your own character")
        if character.sheet is None:
            raise GameError(f"{character.name} has no 5e sheet")
        return character, Sheet.model_validate(character.sheet)

    def _token_for_roll(self, player: Player, token_id: str | None) -> MapObject | None:
        obj = self.objects.get(token_id or "")
        if obj is None or obj.kind != "token" or not self._can_see(player, obj):
            return None
        return obj

    def _sheet_for_token(self, obj: MapObject | None) -> Sheet | None:
        character = self.characters.get(obj.props.get("represents") or "") if obj else None
        return Sheet.model_validate(character.sheet) if character and character.sheet else None

    def _within_5ft(self, a: MapObject, b: MapObject) -> bool:
        """Adjacent footprints (or overlapping): the gap between the two tokens is under a cell."""
        page = self.pages.get(a.page_id)
        cell = page.grid_size if page else 70
        gap_x = abs(a.x - b.x) - (a.width + b.width) / 2
        gap_y = abs(a.y - b.y) - (a.height + b.height) / 2
        return max(gap_x, gap_y) < cell / 2

    async def on_sheet_roll(self, conn: Connection, msg: p.SheetRoll) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        actor = self._token_for_roll(player, msg.token_id)
        target = self._token_for_roll(player, msg.target_id)
        actor_conditions = frozenset(actor.props.get("statuses") or []) if actor else frozenset()
        target_conditions = frozenset(target.props.get("statuses") or []) if target else frozenset()
        penalty = rolls5e.exhaustion_penalty(sheet.exhaustion)

        rolls: list[dict[str, Any]] = []

        def inline(formula: str) -> tuple[str, dict[str, Any]]:
            try:
                result = chat.roll_to_dict(dice_roll(formula))
            except DiceError as e:
                raise GameError(f"invalid formula {formula}: {e}") from e
            rolls.append(result)
            return f"[[#{len(rolls) - 1}]]", result

        fields: list[list[str]] = []
        key = msg.key or ""
        label: str

        if msg.roll == "death_save":
            label = "Death save"
            fields = await self._death_save(player, character, sheet)
        elif msg.roll in ("check", "save", "skill", "initiative"):
            if msg.roll == "skill":
                if key not in SKILLS:
                    raise GameError("unknown skill")
                label, bonus, ability = SKILL_LABELS[key], sheet5e.skill_bonus(sheet, key), None
                kind: rolls5e.TestKind = "check"
            elif msg.roll == "initiative":
                label, bonus, ability, kind = (
                    "Initiative",
                    sheet5e.initiative(sheet),
                    None,
                    "initiative",
                )
            else:
                if key not in ABILITIES:
                    raise GameError("unknown ability")
                ability = key
                if msg.roll == "save":
                    label = f"{ABILITY_NAMES[key]} save"
                    bonus, kind = sheet5e.save_bonus(sheet, key), "save"
                else:
                    label = f"{ABILITY_NAMES[key]} check"
                    bonus, kind = sheet5e.ability_mod(sheet, key), "check"
            effect_kind = "save" if kind == "save" else "check"
            adv, dis, dice, flat = effects5e.roll_changes(
                self._effects(actor),
                effect_kind,
                ability or ("dex" if kind == "initiative" else None),
            )
            test = rolls5e.d20_test(
                kind, msg.mode, ability, actor_conditions, extra_adv=adv, extra_dis=dis
            )
            if test.auto_fail:
                fields.append(["Result", test.auto_fail])
            else:
                marker, result = inline(test.formula(bonus + penalty + flat, dice))
                fields.append([_mode_label(test.mode), marker])
                nat = rolls5e.natural(result)
                if nat in (1, 20):
                    fields.append(["Natural", str(nat)])
                if msg.roll == "initiative" and actor:
                    await self._set_initiative(actor, int(result["total"]))
            if test.reasons:
                fields.append(["Why", "; ".join(test.reasons)])
            if penalty:
                fields.append(["Exhaustion", str(penalty)])
        else:
            attack = next((a for a in sheet.attacks if a.id == key), None)
            if attack is None:
                raise GameError("this attack is not on the sheet")
            target_sheet = self._sheet_for_token(target)
            target_name = (target.props.get("name") or "the target") if target else None
            damage = sheet5e.damage_formula(sheet, attack)
            if msg.roll == "attack" and attack.kind == "attack":
                label = attack.name
                near = self._within_5ft(actor, target) if actor and target else True
                adv, dis, dice, flat = effects5e.roll_changes(self._effects(actor), "attack", None)
                t_adv, t_dis = effects5e.attacked_with(self._effects(target))
                test = rolls5e.d20_test(
                    "attack",
                    msg.mode,
                    None,
                    actor_conditions,
                    target_conditions,
                    near,
                    adv + t_adv,
                    dis + t_dis,
                )
                bonus = sheet5e.attack_bonus(sheet, attack) + penalty + flat
                marker, result = inline(test.formula(bonus, dice))
                fields.append([f"Attack {_mode_label(test.mode).lower()}", marker])
                ac = (
                    target_sheet.ac + effects5e.ac_bonus(self._effects(target))
                    if target_sheet
                    else None
                )
                auto_crit = near and bool(target_conditions & set(rolls5e.AUTO_CRIT))
                outcome = rolls5e.attack_outcome(
                    rolls5e.natural(result), int(result["total"]), ac, auto_crit
                )
                if target_name:
                    vs = f" vs AC {ac}" if ac is not None else ""
                    fields.append(["Target", f"{target_name}{vs}"])
                if outcome:
                    fields.append(["Result", outcome.capitalize()])
                if test.reasons:
                    fields.append(["Why", "; ".join(test.reasons)])
                if damage and outcome != "miss" and outcome != "critical miss":
                    crit = outcome == "critical hit"
                    fields.append(["Damage", self._damage_button(character, attack.id, crit, msg)])
            elif msg.roll == "attack":
                # An effect that forces a saving throw: the card shows the DC.
                label = attack.name
                save = ABILITY_NAMES.get(attack.save or "", "")
                fields.append(["Save", f"DC {sheet5e.save_dc(sheet, attack)} {save}".strip()])
                if damage:
                    half = " (half on a success)" if attack.half_on_save else ""
                    button = self._damage_button(character, attack.id, False, msg)
                    fields.append(["Damage", f"{button}{half}"])
            else:
                label = f"{attack.name} damage" + (" (critical)" if msg.crit else "")
                if not damage:
                    raise GameError(f"{attack.name} has no damage")
                formula = rolls5e.critical(damage) if msg.crit else damage
                marker, result = inline(formula)
                fields.append([attack.damage_type.capitalize() or "Damage", marker])
                fields.append(
                    [
                        "Apply",
                        _apply_buttons(int(result["total"]), attack.damage_type, msg.target_id),
                    ]
                )
            if attack.notes:
                fields.append(["Notes", attack.notes])

        template = {"name": "default", "title": f"{character.name}: {label}", "fields": fields}
        await self._post_chat(
            player,
            character.name,
            content="",
            roll={"main": None, "inline": rolls, "template": template},
            gm_only=msg.gm_only,
        )

    def _damage_button(
        self, character: Character, attack_id: str, crit: bool, msg: p.SheetRoll
    ) -> str:
        """Chat button that rolls this attack's damage (see `runButton` in the client)."""
        args = [
            character.id,
            attack_id,
            "1" if crit else "0",
            msg.token_id or "-",
            msg.target_id or "-",
        ]
        return f"[{'Roll critical damage' if crit else 'Roll damage'}](!damage {' '.join(args)})"

    def _hp_from_sheet(self, obj: MapObject) -> None:
        """A new token of a sheet character: the PC's own hit points, or a monster's maximum."""
        character = self._represented(obj) if obj.kind == "token" else None
        if character is None or character.sheet is None:
            return
        hp = character.sheet["hp"]
        if character.sheet["kind"] == "pc":
            obj.props = {**obj.props, **self._bars(hp["current"], hp["max"], hp["temp"])}
        elif "bar1" not in obj.props:
            obj.props = {**obj.props, "bar1": {"value": hp["max"], "max": hp["max"]}}

    async def _after_token_change(self, changes: list[dict[str, Any]]) -> None:
        """A newly linked token takes the sheet's hit points; editing its bars changes the sheet.

        `changes`: the {id, before, after} of an object event.
        """
        to_sheet = []
        for ch in changes:
            obj = self.objects.get(ch["id"])
            before, after = ch["before"] or {}, ch["after"] or {}
            if obj and "props" in after:
                await self._check_concentration(obj)
            pc = self._linked_pc(obj) if obj and "props" in after else None
            if obj is None or pc is None:
                continue
            old_link = (before.get("props") or {}).get("represents")
            if old_link != after["props"].get("represents"):
                await self._sync_tokens(pc)
            elif any(
                (before.get("props") or {}).get(k) != after["props"].get(k)
                for k in ("bar1", "bar2")
            ):
                to_sheet.append(obj)
        await self._tokens_to_sheets(to_sheet)

    async def _set_initiative(self, token: MapObject, value: int) -> None:
        """Put the rolled initiative in the turn tracker, adding the token if needed."""
        assert self.game is not None
        order = [dict(e) for e in self.game.turn_order]
        entry = next((e for e in order if e.get("object_id") == token.id), None)
        if entry is None:
            name = token.props.get("name") or "Token"
            order.append({"id": str(uuid.uuid4()), "object_id": token.id, "name": name})
            entry = order[-1]
        entry["value"] = str(value)
        await self._save_turns("turn.update", f'rolled initiative for "{entry["name"]}"', order)

    # --- Hit points: token <-> sheet, damage, healing, death -------------------

    @property
    def npc_hp(self) -> str:
        """What players see of monsters' hit points: hidden, status or full."""
        assert self.game is not None
        return self.game.settings.get("npc_hp", "status")

    def _represented(self, obj: MapObject) -> Character | None:
        character = self.characters.get(obj.props.get("represents") or "")
        return character if character and character.sheet else None

    def _linked_pc(self, obj: MapObject) -> Character | None:
        """Player character whose sheet holds this token's hit points (shared by its tokens)."""
        character = self._represented(obj)
        return (
            character if character and character.sheet and character.sheet["kind"] == "pc" else None
        )

    def _tokens_of(self, character: Character) -> list[MapObject]:
        return [
            o
            for o in self.objects.values()
            if o.kind == "token" and o.props.get("represents") == character.id
        ]

    def _health(self, obj: MapObject) -> tuple[damage5e.Health, damage5e.Defenses]:
        conditions = frozenset(obj.props.get("statuses") or [])
        character = self._represented(obj)
        sheet = character.sheet if character else None
        defenses = damage5e.Defenses()
        if sheet:
            defenses = damage5e.Defenses(
                frozenset(sheet["resistances"]),
                frozenset(sheet["immunities"]),
                frozenset(sheet["vulnerabilities"]),
            )
        pc = self._linked_pc(obj)
        if pc and pc.sheet:
            hp, saves = pc.sheet["hp"], pc.sheet["death_saves"]
            health = damage5e.Health(
                hp["current"],
                hp["max"],
                hp["temp"],
                True,
                saves["successes"],
                saves["failures"],
                conditions,
            )
        else:
            bar1, bar2 = obj.props.get("bar1") or {}, obj.props.get("bar2") or {}
            current = int(bar1.get("value") or 0)
            maximum = int(bar1.get("max") or current)
            health = damage5e.Health(
                current, maximum, int(bar2.get("value") or 0), False, 0, 0, conditions
            )
        return health, defenses

    @staticmethod
    def _bars(current: int, maximum: int, temp: int) -> dict[str, Any]:
        return {
            "bar1": {"value": current, "max": maximum},
            "bar2": {"value": temp or None, "max": None},
        }

    async def _set_props(self, changes: dict[str, dict[str, Any]], kind: str, summary: str) -> None:
        """Merge props into tokens (null removes a key), save and broadcast. Not undoable."""
        planned: list[tuple[MapObject, dict[str, Any]]] = []
        for obj_id, patch in changes.items():
            obj = self.objects.get(obj_id)
            if obj is None:
                continue
            merged = {**obj.props, **patch}
            props = {k: v for k, v in merged.items() if v is not None}
            if props != obj.props:
                planned.append((obj, props))
        if not planned:
            return
        async with self._commit(kind, summary, None, [o.id for o, _ in planned]) as s:
            for obj, props in planned:
                await s.execute(update(MapObject).where(MapObject.id == obj.id).values(props=props))
        for obj, props in planned:
            obj.props = props
        self._publish_objects([o for o, _ in planned], [], {})

    async def _set_sheet(self, character: Character, sheet: dict[str, Any], summary: str) -> None:
        if sheet == character.sheet:
            return
        async with self._commit("char.update", summary) as s:
            await s.execute(
                update(Character).where(Character.id == character.id).values(sheet=sheet)
            )
        character.sheet = sheet
        self._broadcast_character(character, character.player_id)

    async def _sync_tokens(self, character: Character) -> None:
        """A player character's hit points shown on every token that represents it."""
        if not character.sheet or character.sheet["kind"] != "pc":
            return
        hp = character.sheet["hp"]
        bars = self._bars(hp["current"], hp["max"], hp["temp"])
        await self._set_props(
            {o.id: bars for o in self._tokens_of(character)},
            "token.sync",
            f'hit points of "{character.name}"',
        )

    async def _tokens_to_sheets(self, objs: list[MapObject]) -> None:
        """Hit points typed on a linked token go to the sheet, then to its other tokens."""
        for obj in objs:
            pc = self._linked_pc(obj)
            if pc is None or pc.sheet is None:
                continue
            bar1, bar2 = obj.props.get("bar1") or {}, obj.props.get("bar2") or {}
            sheet = _copy(pc.sheet)
            hp = sheet["hp"]
            hp["max"] = max(0, min(9999, int(bar1.get("max") or hp["max"])))
            hp["current"] = max(0, min(hp["max"], int(bar1.get("value") or 0)))
            hp["temp"] = max(0, min(9999, int(bar2.get("value") or 0)))
            await self._set_sheet(pc, sheet, f'hit points of "{pc.name}"')
            await self._sync_tokens(pc)

    async def _fit_tokens(self, character: Character) -> None:
        """Tokens of a character take the space of its size (Large = 2×2 cells…)."""
        if not character.sheet:
            return
        cells = SIZES[character.sheet["size"]]
        planned = []
        for o in self._tokens_of(character):
            page = self.pages.get(o.page_id)
            side = cells * (page.grid_size if page else 70)
            if (o.width, o.height) != (side, side):
                planned.append((o, side))
        if not planned:
            return
        async with self._commit(
            "token.sync", f'size of "{character.name}"', None, [o.id for o, _ in planned]
        ) as s:
            for o, side in planned:
                await s.execute(
                    update(MapObject).where(MapObject.id == o.id).values(width=side, height=side)
                )
        for o, side in planned:
            o.width = o.height = side
        self._publish_objects([o for o, _ in planned], [], {})

    async def _write_health(self, obj: MapObject, out: damage5e.Outcome, summary: str) -> None:
        """Store the new hit points (sheet or token) and the conditions that came with them."""
        h = out.health
        pc = self._linked_pc(obj)
        targets = self._tokens_of(pc) if pc else [obj]
        changes: dict[str, dict[str, Any]] = {}
        for t in targets:
            statuses = (set(t.props.get("statuses") or []) | out.added) - out.removed
            patch: dict[str, Any] = {"statuses": sorted(statuses) or None}
            if pc is None:
                patch.update(self._bars(h.current, h.max, h.temp))
            changes[t.id] = patch
        if pc and pc.sheet:
            sheet = _copy(pc.sheet)
            sheet["hp"].update(current=h.current, max=h.max, temp=h.temp)
            sheet["death_saves"] = {"successes": h.successes, "failures": h.failures}
            await self._set_sheet(pc, sheet, summary)
            await self._sync_tokens(pc)
        await self._set_props(changes, "combat.apply", summary)
        for t in targets:
            await self._check_concentration(self.objects[t.id])

    def _is_monster(self, obj: MapObject) -> bool:
        """A token no player controls and that is not a player character."""
        return (
            obj.kind == "token" and not obj.props.get("controlled_by") and not self._linked_pc(obj)
        )

    def _shows_hp(self, obj: MapObject) -> bool:
        """Whether everyone may see this token's hit point numbers."""
        return not self._is_monster(obj) or self.npc_hp == "full"

    async def on_combat_apply(self, conn: Connection, msg: p.CombatApply) -> None:
        player = conn.player
        assert player is not None
        tokens = [self._get_object(i) for i in msg.token_ids]
        for t in tokens:
            if t.kind != "token" or not permissions.controls(player, t):
                raise GameError("you can only change the hit points of tokens you control")
        rows: list[list[str]] = []
        verb = {"damage": "takes", "healing": "heals", "temp": "gains"}[msg.kind]
        for t in tokens:
            health, defenses = self._health(t)
            out = damage5e.apply(
                health, msg.kind, msg.amount, msg.damage_type, defenses, msg.half, msg.critical
            )
            name = t.props.get("name") or "Token"
            what = {
                "damage": f"{out.taken} {msg.damage_type or ''} damage".replace("  ", " "),
                "healing": f"{msg.amount} hit points",
                "temp": f"{msg.amount} temporary hit points",
            }[msg.kind]
            text = f"{verb} {what}"
            if self._shows_hp(t):
                text += f" → {out.health.current}/{out.health.max} HP"
                if out.health.temp:
                    text += f" (+{out.health.temp})"
            if out.notes:
                text += f" · {'; '.join(out.notes)}"
            rows.append([name, text])
            await self._write_health(t, out, f'{verb} {what}: "{name}"')
            if msg.kind == "damage":
                await self._concentration_save(self.objects[t.id], out.taken)
        title = {"damage": "Damage", "healing": "Healing", "temp": "Temporary hit points"}[msg.kind]
        template = {"name": "default", "title": title, "fields": rows}
        await self._post_chat(
            player, player.name, "", {"main": None, "inline": [], "template": template}
        )

    async def _death_save(
        self, player: Player, character: Character, sheet: Sheet
    ) -> list[list[str]]:
        """Roll a death save for a player character at 0 HP and record it."""
        if sheet.hp.current > 0:
            raise GameError(f"{character.name} is not at 0 hit points")
        result = chat.roll_to_dict(dice_roll("1d20"))
        nat = rolls5e.natural(result) or 0
        tokens = self._tokens_of(character)
        health = damage5e.Health(
            0,
            sheet.hp.max,
            sheet.hp.temp,
            True,
            sheet.death_saves.successes,
            sheet.death_saves.failures,
        )
        out = damage5e.death_save(health, nat)
        if tokens:
            await self._write_health(tokens[0], out, f'death save of "{character.name}"')
        else:
            data = _copy(character.sheet)
            data["hp"]["current"] = out.health.current
            data["death_saves"] = {
                "successes": out.health.successes,
                "failures": out.health.failures,
            }
            await self._set_sheet(character, data, f'death save of "{character.name}"')
        h = out.health
        return [
            ["Roll", str(nat)],
            ["Result", "; ".join(out.notes)],
            ["Death saves", f"{h.successes} successes, {h.failures} failures"],
        ]

    async def on_sheet_rest(self, conn: Connection, msg: p.SheetRest) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        data = sheet.model_dump()
        fields: list[list[str]] = []
        rolls: list[dict[str, Any]] = []
        if msg.kind == "hit_die":
            total = sheet.level if sheet.kind == "pc" else 0
            if data["hit_dice"]["spent"] >= total:
                raise GameError("no hit point dice left")
            con = sheet5e.ability_mod(sheet, "con")
            result = chat.roll_to_dict(
                dice_roll(f"1d{sheet.hit_dice.die}{con:+d}" if con else f"1d{sheet.hit_dice.die}")
            )
            rolls.append(result)
            gained = max(1, int(result["total"]))
            data["hit_dice"]["spent"] += 1
            data["hp"]["current"] = min(data["hp"]["max"], data["hp"]["current"] + gained)
            fields = [
                ["Hit point die", "[[#0]]"],
                ["Hit points", f"{data['hp']['current']}/{data['hp']['max']}"],
            ]
            label = "Hit point die"
        elif msg.kind == "short":
            for r in data["resources"]:
                if r["reset"] == "short":
                    r["used"] = 0
            fields = [["Restored", "resources that recharge on a short rest"]]
            label = "Short rest"
        else:
            data["hp"]["current"], data["hp"]["temp"] = data["hp"]["max"], 0
            data["hit_dice"]["spent"] = 0
            data["death_saves"] = {"successes": 0, "failures": 0}
            data["exhaustion"] = max(0, data["exhaustion"] - 1)
            for slot in data["spellcasting"]["slots"].values():
                slot["used"] = 0
            for r in data["resources"]:
                if r["reset"] in ("short", "long"):
                    r["used"] = 0
            fields = [
                ["Restored", "hit points, hit point dice, spell slots and resources; exhaustion −1"]
            ]
            label = "Long rest"
        await self._set_sheet(character, data, f'{label.lower()} of "{character.name}"')
        await self._sync_tokens(character)
        if msg.kind == "long":
            await self._set_props(
                {
                    o.id: {
                        "statuses": sorted(set(o.props.get("statuses") or []) - {"unconscious"})
                        or None
                    }
                    for o in self._tokens_of(character)
                },
                "combat.apply",
                f'long rest of "{character.name}"',
            )
        template = {"name": "default", "title": f"{character.name}: {label}", "fields": fields}
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )

    # --- Combat: initiative, turns, action economy, movement -------------------

    def _turn_key(self, entry: dict[str, Any]) -> tuple[float, int]:
        """Sort key: initiative, then Dexterity score for ties (the GM can reorder by hand)."""
        obj = self.objects.get(entry.get("object_id") or "")
        sheet = self._sheet_for_token(obj)
        return _turn_value(entry["value"]), sheet.abilities.dex if sheet else 0

    async def on_combat_initiative(self, conn: Connection, msg: p.CombatInitiative) -> None:
        """GM: roll initiative for the given tokens, add them to the tracker and sort it."""
        player = self._require_gm(conn)
        assert self.game is not None
        tokens = [
            o for o in (self.objects.get(i) for i in msg.token_ids) if o and o.kind == "token"
        ]
        if not tokens:
            raise GameError("select some tokens first")
        # Monsters of the same kind can share one roll.
        groups: dict[str, list[MapObject]] = {}
        for t in tokens:
            same = t.props.get("represents") if msg.group and self._is_monster(t) else None
            groups.setdefault(same or t.id, []).append(t)
        rolls: list[dict[str, Any]] = []
        rows: list[list[str]] = []
        order = [dict(e) for e in self.game.turn_order]
        for members in groups.values():
            first = members[0]
            sheet = self._sheet_for_token(first)
            conditions = frozenset(first.props.get("statuses") or [])
            test = rolls5e.d20_test("initiative", "normal", None, conditions)
            bonus = sheet5e.initiative(sheet) if sheet else 0
            result = chat.roll_to_dict(dice_roll(test.formula(bonus)))
            rolls.append(result)
            names = ", ".join(t.props.get("name") or "Token" for t in members)
            rows.append([names, f"[[#{len(rolls) - 1}]]"])
            for t in members:
                entry = next((e for e in order if e.get("object_id") == t.id), None)
                if entry is None:
                    entry = {
                        "id": str(uuid.uuid4()),
                        "object_id": t.id,
                        "name": t.props.get("name") or "Token",
                    }
                    order.append(entry)
                entry["value"] = str(int(result["total"]))
        order.sort(key=self._turn_key, reverse=True)
        first_round = self.game.settings.get("round", 0) == 0
        if first_round and order:
            order[0] = {**order[0], "used": {}, "moved": 0}
        await self._save_turns(
            msg.type, "rolled initiative", order, max(1, self.game.settings.get("round", 0))
        )
        template = {"name": "default", "title": "Initiative", "fields": rows}
        await self._post_chat(
            player,
            player.name,
            "",
            {"main": None, "inline": rolls, "template": template},
            gm_only=True,
        )
        if first_round and order:
            await self._on_turn_start(order[0])

    async def _on_turn_start(self, entry: dict[str, Any]) -> None:
        """Start of a combatant's turn: effects timed on it end; a dying character rolls a
        death save."""
        await self._tick_effects(entry, "start")
        obj = self.objects.get(entry.get("object_id") or "")
        pc = self._linked_pc(obj) if obj else None
        if pc is None or pc.sheet is None:
            return
        hp, saves = pc.sheet["hp"], pc.sheet["death_saves"]
        dead = "dead" in (obj.props.get("statuses") or []) if obj else False
        if hp["current"] == 0 and not dead and saves["successes"] < 3:
            fields = [["Death save", f"[Roll death save](!deathsave {pc.id})"]]
            template = {"name": "default", "title": f"{pc.name} is dying", "fields": fields}
            owner = self.players.get(pc.player_id or "") or next(iter(self.players.values()))
            await self._post_chat(
                owner, pc.name, "", {"main": None, "inline": [], "template": template}
            )

    async def _on_turn_end(self, entry: dict[str, Any]) -> None:
        """End of a combatant's turn: effects timed on it end, repeated saves."""
        await self._tick_effects(entry, "end")

    async def on_turn_use(self, conn: Connection, msg: p.TurnUse) -> None:
        """Mark the action, bonus action or reaction of a combatant as used or available."""
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        entry = dict(self.game.turn_order[i])
        if not self._controls_entry(player, entry):
            raise GameError("you do not control this entry")
        entry["used"] = {**(entry.get("used") or {}), msg.what: msg.used}
        order = list(self.game.turn_order)
        order[i] = entry
        word = "used" if msg.used else "got back"
        await self._save_turns(
            msg.type, f"{entry['name']} {word} the {msg.what.replace('_', ' ')}", order
        )

    async def _track_movement(
        self, changes: list[dict[str, Any]], via: dict[str, list[float]] | None = None
    ) -> None:
        """Feet moved by the combatant whose turn it is, from the token's moves on the map,
        along the waypoints of the move if it had any."""
        assert self.game is not None
        order = self.game.turn_order
        if not order or self.game.settings.get("round", 0) < 1:
            return
        current = order[0]
        for ch in changes:
            if ch["id"] != current.get("object_id"):
                continue
            before, after = ch["before"] or {}, ch["after"] or {}
            if "page_id" in after or not ({"x", "y"} & after.keys()):
                continue
            obj = self.objects.get(ch["id"])
            page = self.pages.get(obj.page_id) if obj else None
            if obj is None or page is None:
                continue
            stops = (via or {}).get(ch["id"], [])
            points = [before.get("x", obj.x), before.get("y", obj.y)]
            points += stops[: len(stops) // 2 * 2]
            points += [after.get("x", obj.x), after.get("y", obj.y)]
            # 5e grid: every square, diagonal or not, is 5 feet.
            steps = range(0, len(points) - 2, 2)
            cells = (
                sum(
                    max(abs(points[i + 2] - points[i]), abs(points[i + 3] - points[i + 1]))
                    for i in steps
                )
                / page.grid_size
            )
            feet = round(cells * 2) / 2 * 5
            if feet <= 0:
                continue
            entry = {**current, "moved": (current.get("moved") or 0) + feet}
            await self._save_turns(
                "turn.move", f"{entry['name']} moved {feet:g} ft", [entry, *order[1:]]
            )
            return

    # --- Effects, conditions, concentration -----------------------------------

    @staticmethod
    def _effects(obj: MapObject | None) -> list[effects5e.Effect]:
        return effects5e.load(obj.props.get("effects")) if obj else []

    def _roll_save(
        self, obj: MapObject, ability: str, dc: int
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """A saving throw of a token: its sheet, conditions and effects. (success, text, roll)."""
        sheet = self._sheet_for_token(obj)
        bonus = sheet5e.save_bonus(sheet, ability) if sheet else 0
        penalty = rolls5e.exhaustion_penalty(sheet.exhaustion) if sheet else 0
        adv, dis, dice, flat = effects5e.roll_changes(self._effects(obj), "save", ability)
        conditions = frozenset(obj.props.get("statuses") or [])
        test = rolls5e.d20_test("save", "normal", ability, conditions, extra_adv=adv, extra_dis=dis)
        if test.auto_fail:
            return False, test.auto_fail, None
        result = chat.roll_to_dict(dice_roll(test.formula(bonus + flat + penalty, dice)))
        total = int(result["total"])
        success = total >= dc
        mode = "" if test.mode == "normal" else f" ({test.mode})"
        return success, f"{total}{mode} {'✓ success' if success else '✗ failure'}", result

    def _with_effects(
        self, obj: MapObject, effects: list[effects5e.Effect], dropped: list[effects5e.Effect]
    ) -> dict[str, Any]:
        """Props patch: the new effects, and the statuses their conditions add or remove."""
        statuses = set(obj.props.get("statuses") or [])
        statuses -= effects5e.conditions(dropped) - effects5e.conditions(effects)
        statuses |= effects5e.conditions(effects)
        return {"effects": effects5e.dump(effects), "statuses": sorted(statuses) or None}

    async def _drop_effects(self, ended: dict[str, list[str]], summary: str) -> None:
        """Remove effects by id from tokens ({token id: [effect ids]})."""
        changes: dict[str, dict[str, Any]] = {}
        for obj_id, ids in ended.items():
            obj = self.objects.get(obj_id)
            if obj is None:
                continue
            effects = self._effects(obj)
            keep = [e for e in effects if e.id not in ids]
            gone = [e for e in effects if e.id in ids]
            if gone:
                changes[obj_id] = self._with_effects(obj, keep, gone)
        await self._set_props(changes, "effect.end", summary)

    async def _start_concentration(self, caster: MapObject, name: str) -> None:
        if caster.props.get("concentrating"):
            await self._end_concentration(caster, f"started concentrating on {name}")
        statuses = sorted(set(caster.props.get("statuses") or []) | {"concentrating"})
        await self._set_props(
            {caster.id: {"concentrating": {"name": name}, "statuses": statuses}},
            "effect.concentration",
            f'"{caster.props.get("name") or "Token"}" concentrates on {name}',
        )

    async def _end_concentration(self, caster: MapObject, why: str) -> None:
        """Concentration ends: every effect that depends on it ends too, on every token."""
        state = caster.props.get("concentrating")
        if not state:
            return
        name = caster.props.get("name") or "Token"
        ended = {
            o.id: [e.id for e in self._effects(o) if e.concentration_of == caster.id]
            for o in self.objects.values()
            if o.props.get("effects")
        }
        await self._drop_effects(
            {k: v for k, v in ended.items() if v}, f'"{name}" lost concentration'
        )
        statuses = sorted(set(caster.props.get("statuses") or []) - {"concentrating"}) or None
        await self._set_props(
            {caster.id: {"concentrating": None, "statuses": statuses}},
            "effect.concentration",
            f'"{name}" lost concentration',
        )
        await self._card(
            caster, f"{name} loses concentration", [["Spell", state["name"]], ["Why", why]]
        )

    async def _check_concentration(self, obj: MapObject) -> None:
        """Incapacitated, unconscious or dead: no more concentration."""
        if obj.props.get("concentrating"):
            breaking = set(obj.props.get("statuses") or []) & effects5e.BREAKS_CONCENTRATION
            if breaking:
                await self._end_concentration(obj, f"{sorted(breaking)[0]}")

    async def _concentration_save(self, obj: MapObject, damage: int) -> None:
        """Damage to a concentrating creature: Constitution save or the concentration ends."""
        if not obj.props.get("concentrating") or damage <= 0:
            return
        dc = effects5e.concentration_dc(damage)
        success, text, result = self._roll_save(obj, "con", dc)
        name = obj.props.get("name") or "Token"
        if success:
            fields = [["Constitution save", f"DC {dc}: {text}"]]
            await self._card(obj, f"{name} keeps concentrating", fields)
        else:
            await self._end_concentration(obj, f"failed the DC {dc} Constitution save ({text})")

    async def _card(
        self, obj: MapObject | None, title: str, fields: list[list[str]], gm_only: bool = False
    ) -> None:
        """A chat card from the game itself, spoken by the token's controller (or the GM)."""
        player = None
        if obj is not None:
            controllers = obj.props.get("controlled_by") or []
            player = next((self.players[i] for i in controllers if i in self.players), None)
        if player is None:
            player = next((p for p in self.players.values() if p.is_gm), None) or next(
                iter(self.players.values())
            )
        template = {"name": "default", "title": title, "fields": fields}
        await self._post_chat(
            player,
            "Frolls",
            "",
            {"main": None, "inline": [], "template": template},
            gm_only=gm_only,
        )

    def _may_affect(self, player: Player, source: MapObject | None) -> bool:
        """GMs, or players acting with a token they control (their character's spell)."""
        return player.is_gm or (source is not None and permissions.controls(player, source))

    async def on_effect_apply(self, conn: Connection, msg: p.EffectApply) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        source = self.objects.get(msg.source_id or "")
        if not self._may_affect(player, source):
            raise GameError("apply effects with a token you control, or as the GM")
        targets = [self._get_object(i) for i in msg.token_ids]
        if msg.preset:
            if msg.preset not in effects5e.PRESETS:
                raise GameError("unknown effect")
            base = effects5e.from_preset(
                msg.preset, source.id if source else None, msg.concentrate, msg.dc
            )
        elif msg.effect:
            base = msg.effect
        else:
            raise GameError("choose an effect")
        await self._add_effect(base, targets, source)

    async def _add_effect(
        self, base: effects5e.Effect, targets: list[MapObject], source: MapObject | None
    ) -> None:
        assert self.game is not None
        ending = base.ending
        # "Until the end of your next turn", cast during your turn: this turn's end doesn't count.
        order = self.game.turn_order
        current = (
            order[0].get("object_id") if order and self.game.settings.get("round", 0) else None
        )
        if ending and ending.when == "end" and ending.of == current:
            ending = ending.model_copy(update={"rounds": ending.rounds + 1})
        if base.concentration_of and source:
            await self._start_concentration(source, base.name)
        changes: dict[str, dict[str, Any]] = {}
        for t in targets:
            effect = base.model_copy(update={"id": str(uuid.uuid4()), "ending": ending})
            effects = [*self._effects(self.objects[t.id]), effect]
            changes[t.id] = self._with_effects(self.objects[t.id], effects, [])
        names = ", ".join(t.props.get("name") or "Token" for t in targets)
        await self._set_props(changes, "effect.apply", f"{base.name} on {names}")
        for t in targets:
            await self._check_concentration(self.objects[t.id])
        rows = [["Targets", names]]
        if base.duration:
            rows.append(["Duration", base.duration])
        if base.concentration_of:
            rows.append(["Concentration", source.props.get("name") or "Token" if source else ""])
        await self._card(source, f"{base.name}", rows)

    async def on_effect_remove(self, conn: Connection, msg: p.EffectRemove) -> None:
        player = conn.player
        assert player is not None
        obj = self._get_object(msg.token_id)
        effect = next((e for e in self._effects(obj) if e.id == msg.effect_id), None)
        if effect is None:
            raise GameError("effect not found")
        source = self.objects.get(effect.concentration_of or "")
        if not (
            player.is_gm
            or permissions.controls(player, obj)
            or (source and permissions.controls(player, source))
        ):
            raise GameError("you cannot remove this effect")
        await self._drop_effects(
            {obj.id: [effect.id]},
            f'{effect.name} removed from "{obj.props.get("name") or "Token"}"',
        )

    async def on_effect_end_concentration(self, conn: Connection, msg: p.EndConcentration) -> None:
        player = conn.player
        assert player is not None
        obj = self._get_object(msg.token_id)
        if not permissions.controls(player, obj):
            raise GameError("you do not control this token")
        await self._end_concentration(obj, "chose to stop")

    async def _tick_effects(self, entry: dict[str, Any], when: str) -> None:
        """Start or end of a combatant's turn: effects timed on it end; at the end of its own
        turn the creature repeats the saving throws that can end its effects."""
        turn_of = entry.get("object_id")
        if not turn_of:
            return
        changes: dict[str, dict[str, Any]] = {}
        notes: list[list[str]] = []
        for o in list(self.objects.values()):
            effects = self._effects(o)
            if not any(
                e.ending and e.ending.of == turn_of and e.ending.when == when for e in effects
            ):
                continue
            kept, gone = effects5e.tick(effects, turn_of, when)
            changes[o.id] = self._with_effects(o, kept, gone)
            notes += [[o.props.get("name") or "Token", f"{e.name} ends"] for e in gone]
        await self._set_props(changes, "effect.tick", "effects count down")
        if when == "end":
            obj = self.objects.get(turn_of)
            for e in self._effects(obj):
                if e.repeat_save is None or obj is None:
                    continue
                success, text, _ = self._roll_save(obj, e.repeat_save.ability, e.repeat_save.dc)
                name = obj.props.get("name") or "Token"
                save = f"{ABILITY_NAMES[e.repeat_save.ability]} DC {e.repeat_save.dc}"
                notes.append(
                    [name, f"{e.name}: {save} save {text}" + (" — it ends" if success else "")]
                )
                if success:
                    await self._drop_effects({obj.id: [e.id]}, f"{e.name} ends")
        if notes:
            await self._card(self.objects.get(turn_of), "Effects", notes)

    # --- Spells ----------------------------------------------------------------

    def _spell_damage(self, sheet: Sheet, spell: Any, slot: int) -> str:
        """Damage of a spell cast with a slot: extra dice per level above the spell's, and
        cantrips growing with the character (×2 at level 5, ×3 at 11, ×4 at 17)."""
        damage = spell.damage.strip()
        if not damage:
            return ""
        if spell.level == 0 and sheet.kind == "pc":
            times = 1 + (sheet.level >= 5) + (sheet.level >= 11) + (sheet.level >= 17)
            damage = rolls5e.DICE_RE.sub(
                lambda m: f"{int(m.group(1) or 1) * times}d{m.group(2)}", damage
            )
        extra = slot - spell.level
        if spell.upcast.strip() and spell.level > 0 and extra > 0:
            damage += "".join(f"+{spell.upcast.strip()}" for _ in range(extra))
        mod = sheet5e.ability_mod(sheet, "spell") if spell.add_modifier else 0
        return f"{damage}{mod:+d}" if mod else damage

    async def on_sheet_cast(self, conn: Connection, msg: p.SheetCast) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        spell = next((s for s in sheet.spells if s.id == msg.spell_id), None)
        if spell is None:
            raise GameError("this spell is not on the sheet")
        slot = spell.level if msg.slot is None else msg.slot
        data = sheet.model_dump()
        if spell.level > 0 and not (msg.ritual and spell.ritual):
            if slot < spell.level:
                raise GameError(f"{spell.name} needs a level {spell.level} slot or higher")
            slots = data["spellcasting"]["slots"].get(str(slot))
            if not slots or slots["used"] >= slots["max"]:
                raise GameError(f"no level {slot} spell slots left")
            slots["used"] += 1
            await self._set_sheet(character, data, f"{character.name} used a level {slot} slot")
        caster = self._token_for_roll(player, msg.token_id)
        targets = [t for t in (self._token_for_roll(player, i) for i in msg.target_ids) if t]

        fields: list[list[str]] = []
        rolls: list[dict[str, Any]] = []
        level = "cantrip" if spell.level == 0 else f"level {slot}"
        damage = self._spell_damage(sheet, spell, slot)
        dc = sheet5e.spell_dc(sheet)
        # A spell with an effect starts concentrating when the effect lands (_add_effect).
        if spell.concentration and caster and not spell.effect:
            await self._start_concentration(caster, spell.name)
        if spell.attack and targets:
            # One spell attack roll per target, against its AC.
            for t in targets:
                target_sheet = self._sheet_for_token(t)
                conditions = (
                    frozenset(caster.props.get("statuses") or []) if caster else frozenset()
                )
                t_conditions = frozenset(t.props.get("statuses") or [])
                adv, dis, dice, flat = effects5e.roll_changes(self._effects(caster), "attack", None)
                t_adv, t_dis = effects5e.attacked_with(self._effects(t))
                near = self._within_5ft(caster, t) if caster else True
                test = rolls5e.d20_test(
                    "attack",
                    "normal",
                    None,
                    conditions,
                    t_conditions,
                    near,
                    adv + t_adv,
                    dis + t_dis,
                )
                bonus = (sheet5e.spell_attack(sheet) or 0) + flat
                result = chat.roll_to_dict(dice_roll(test.formula(bonus, dice)))
                rolls.append(result)
                ac = (
                    target_sheet.ac + effects5e.ac_bonus(self._effects(t)) if target_sheet else None
                )
                outcome = rolls5e.attack_outcome(
                    rolls5e.natural(result), int(result["total"]), ac, False
                )
                name = t.props.get("name") or "Token"
                vs = f" vs AC {ac}" if ac is not None else ""
                fields.append([f"{name}{vs}", f"[[#{len(rolls) - 1}]] {outcome}".strip()])
                if damage and outcome in ("hit", "critical hit"):
                    formula = rolls5e.critical(damage) if outcome == "critical hit" else damage
                    dmg = chat.roll_to_dict(dice_roll(formula))
                    rolls.append(dmg)
                    total = int(dmg["total"])
                    kind = spell.damage_type or "-"
                    fields.append(
                        [
                            f"{spell.damage_type or 'Damage'}",
                            f"[[#{len(rolls) - 1}]] [Apply](!apply damage {total} {kind} {t.id})",
                        ]
                    )
        elif spell.save:
            save = ABILITY_NAMES[spell.save]
            fields.append(["Save", f"DC {dc} {save}" if dc else save])
            if targets:
                ids = ",".join(t.id for t in targets)
                args = f"{character.id} {spell.id} {slot} {caster.id if caster else '-'} {ids}"
                fields.append(["Targets", f"[Roll saves and apply](!saves {args})"])
        elif damage:
            dmg = chat.roll_to_dict(dice_roll(damage))
            rolls.append(dmg)
            kind = spell.heal or "damage"
            label = {"healing": "Healing", "temp": "Temporary hit points"}.get(
                spell.heal, spell.damage_type.capitalize() or "Damage"
            )
            fields.append([label, f"[[#{len(rolls) - 1}]]"])
            target = targets[0].id if len(targets) == 1 else None
            fields.append(
                ["Apply", _apply_buttons(int(dmg["total"]), spell.damage_type, target, kind)]
            )
        if spell.effect and not spell.save and targets:
            preset = effects5e.from_preset(
                spell.effect, caster.id if caster else None, spell.concentration, dc
            )
            await self._add_effect(preset, targets, caster)
        if spell.duration:
            fields.append(
                ["Duration", spell.duration + (" (concentration)" if spell.concentration else "")]
            )
        if spell.description:
            fields.append(["Description", spell.description])
        template = {
            "name": "default",
            "title": f"{character.name} casts {spell.name} ({level})",
            "fields": fields,
        }
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )

    async def on_spell_saves(self, conn: Connection, msg: p.SpellSaves) -> None:
        """Every target rolls its saving throw; damage (half on a success) and the spell's
        effect (on a failure) are applied."""
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        spell = next((s for s in sheet.spells if s.id == msg.spell_id), None)
        if spell is None or spell.save is None:
            raise GameError("this spell has no saving throw")
        caster = self.objects.get(msg.token_id or "")
        dc = sheet5e.spell_dc(sheet) or 10
        damage = self._spell_damage(sheet, spell, msg.slot)
        rolls: list[dict[str, Any]] = []
        total = 0
        if damage:
            dmg = chat.roll_to_dict(dice_roll(damage))
            rolls.append(dmg)
            total = int(dmg["total"])
        fields: list[list[str]] = (
            [["Damage", f"[[#0]] {spell.damage_type}".strip()]] if damage else []
        )
        failed: list[MapObject] = []
        for t in (self.objects.get(i) for i in msg.target_ids):
            if t is None or t.kind != "token":
                continue
            success, text, _ = self._roll_save(t, spell.save, dc)
            name = t.props.get("name") or "Token"
            line = f"{ABILITY_NAMES[spell.save]} DC {dc}: {text}"
            if not success:
                failed.append(t)
            if damage and (not success or spell.half_on_save):
                health, defenses = self._health(t)
                out = damage5e.apply(health, "damage", total, spell.damage_type, defenses, success)
                await self._write_health(t, out, f'{spell.name} on "{name}"')
                await self._concentration_save(t, out.taken)
                line += f" → {out.taken} damage"
                if self._shows_hp(t):
                    line += f" ({out.health.current}/{out.health.max} HP)"
            fields.append([name, line])
        if spell.effect and failed:
            preset = effects5e.from_preset(
                spell.effect, caster.id if caster else None, spell.concentration, dc
            )
            await self._add_effect(preset, failed, caster)
        template = {"name": "default", "title": f"{spell.name}: saving throws", "fields": fields}
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )

    # --- Fog of war ------------------------------------------------------------

    async def _save_fog(self, page: Page, data: dict[str, Any], summary: str) -> None:
        async with self._commit("fog", summary) as s:
            await s.execute(update(Page).where(Page.id == page.id).values(fog=data))
        page.fog = data
        self._broadcast_pages()
        for c in self._viewers(page.id):
            assert c.player is not None
            if c.player.is_gm:
                c.send({"type": "page.updated", "page": page_dict(page)})
            else:
                # Tokens may have come out of the fog or gone under it.
                self._page_snapshot(c, page.id)

    async def on_fog_set(self, conn: Connection, msg: p.FogSet) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        data = {**(page.fog or fog.default()), "enabled": msg.enabled}
        word = "on" if msg.enabled else "off"
        await self._save_fog(page, data, f'fog {word} on page "{page.name}"')

    async def on_fog_op(self, conn: Connection, msg: p.FogOp) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        if msg.shape == "poly" and len(msg.points) < 6:
            raise GameError("a polygon needs at least three points")
        current = page.fog or fog.default()
        ops = [
            *current.get("ops", []),
            {"mode": msg.mode, "shape": msg.shape, "points": msg.points},
        ]
        if len(ops) > fog.MAX_OPS:
            raise GameError("too many fog areas: hide or reveal the whole page to start again")
        await self._save_fog(
            page, {**current, "enabled": True, "ops": ops}, f"fog: {msg.mode} an area"
        )

    async def on_fog_reset(self, conn: Connection, msg: p.FogReset) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        ops = []
        if msg.mode == "reveal":
            w, h = page.width * page.grid_size, page.height * page.grid_size
            ops = [{"mode": "reveal", "shape": "rect", "points": [0, 0, w, h]}]
        await self._save_fog(page, {"enabled": True, "ops": ops}, f"fog: {msg.mode} the whole page")

    # --- Compendium ------------------------------------------------------------

    async def on_compendium_search(self, conn: Connection, msg: p.CompendiumSearch) -> None:
        results = compendium.search(msg.kind, msg.query, msg.limit, msg.cr, msg.level)
        conn.send(
            {"type": "compendium.results", "rid": msg.rid, "kind": msg.kind, "items": results}
        )

    async def on_compendium_get(self, conn: Connection, msg: p.CompendiumGet) -> None:
        item = compendium.get(msg.kind, msg.key)
        if item is None:
            raise GameError("not in the compendium")
        conn.send({"type": "compendium.entry", "kind": msg.kind, "entry": item})

    async def _monster_character(self, key: str) -> Character:
        """The journal entry of a compendium monster: reused if it exists, else created in the
        "SRD monsters" folder."""
        item = compendium.get("monster", key)
        if item is None:
            raise GameError("not in the compendium")
        for c in self.characters.values():
            if c.sheet and c.sheet.get("source") == key:
                return c
        folder = next(
            (f for f in self.folders.values() if f.name == "SRD monsters" and f.parent_id is None),
            None,
        )
        if folder is None:
            folder = JournalFolder(
                id=str(uuid.uuid4()), game_id=DEFAULT_GAME_ID, name="SRD monsters", parent_id=None
            )
            async with self._commit("folder.create", 'created folder "SRD monsters"') as s:
                s.add(folder)
            self.folders[folder.id] = folder
            self._broadcast_folders([folder], [])
        sheet = Sheet.model_validate(item["sheet"]).model_dump()
        character = Character(
            id=str(uuid.uuid4()),
            game_id=DEFAULT_GAME_ID,
            name=item["name"],
            bio="",
            gm_notes="",
            attributes=[],
            abilities=[],
            sheet=sheet,
            folder_id=folder.id,
            archived=False,
        )
        async with self._commit("char.create", f'added "{item["name"]}" from the compendium') as s:
            s.add(character)
        self.characters[character.id] = character
        self._broadcast_character(character, None)
        return character

    async def on_compendium_add_monster(
        self, conn: Connection, msg: p.CompendiumAddMonster
    ) -> None:
        self._require_gm(conn)
        character = await self._monster_character(msg.key)
        conn.send({"type": "compendium.added", "rid": msg.rid, "character_id": character.id})

    async def on_compendium_place(self, conn: Connection, msg: p.CompendiumPlace) -> None:
        """GM: a compendium monster dropped on the map becomes a journal NPC and a token,
        numbered (Goblin 1, Goblin 2…)."""
        player = self._require_gm(conn)
        page = self._get_page(msg.page_id)
        character = await self._monster_character(msg.key)
        assert character.sheet is not None
        side = SIZES[character.sheet["size"]] * page.grid_size
        same = [
            o
            for o in self.objects.values()
            if o.props.get("represents") == character.id and o.page_id == page.id
        ]
        token = p.ObjectData(
            id=str(uuid.uuid4()),
            page_id=page.id,
            kind="token",
            layer=msg.layer,
            x=msg.x,
            y=msg.y,
            width=side,
            height=side,
            props={
                "name": f"{character.name} {len(same) + 1}",
                "show_name": True,
                "represents": character.id,
            },
        )
        await self.on_obj_create(conn, p.ObjectCreate(type="obj.create", objects=[token]))
        del player

    async def on_compendium_add_spell(self, conn: Connection, msg: p.CompendiumAddSpell) -> None:
        """Add a compendium spell to a character's sheet (the GM, or who plays it)."""
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        item = compendium.get("spell", msg.key)
        if item is None:
            raise GameError("not in the compendium")
        data = sheet.model_dump()
        if any(s["name"] == item["name"] for s in data["spells"]):
            raise GameError(f"{character.name} already has {item['name']}")
        spell = {**item["spell"], "id": str(uuid.uuid4())}
        data["spells"].append(spell)
        data = Sheet.model_validate(data).model_dump()
        await self._set_sheet(character, data, f"{character.name} learned {item['name']}")
        conn.send({"type": "notice", "detail": f"{item['name']} added to {character.name}"})

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
            # Or the name of the character a player plays.
            matches = list(
                {
                    c.player_id
                    for c in self.characters.values()
                    if c.player_id and c.name.lower() == target.lower()
                }
            )
        if not matches:
            raise GameError(f'no player is named "{target}"')
        return matches

    # --- Rollable tables -----------------------------------------------------

    def _sees_table(self, player: Player, table: RollableTable) -> bool:
        return player.is_gm or table.show_players

    def _table_lookup(self, player: Player) -> dict[str, list[TableItem]]:
        """The tables `player` may roll, by lowercase name."""
        return {
            t.name.casefold(): [
                TableItem(i["name"], int(i.get("weight", 1)), i.get("image")) for i in t.items
            ]
            for t in self.tables.values()
            if self._sees_table(player, t)
        }

    def _get_table(self, table_id: str) -> RollableTable:
        table = self.tables.get(table_id)
        if table is None:
            raise GameError("table does not exist")
        return table

    def _table_name(self, name: str, table_id: str) -> str:
        name = name.strip()
        if not name:
            raise GameError("a table needs a name")
        if any(
            t.name.casefold() == name.casefold() and t.id != table_id for t in self.tables.values()
        ):
            raise GameError(f'there is already a table named "{name}"')
        return name

    def _send_tables(self, upsert: list[RollableTable], removed: list[str]) -> None:
        for c in self.connections:
            if not c.player:
                continue
            shown = [t for t in upsert if self._sees_table(c.player, t)]
            gone = removed + [t.id for t in upsert if not self._sees_table(c.player, t)]
            if shown:
                c.send({"type": "table.upsert", "tables": [table_dict(t) for t in shown]})
            if gone:
                c.send({"type": "table.removed", "ids": gone})

    async def on_table_create(self, conn: Connection, msg: p.TableCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.tables:
            raise GameError(f"id {msg.id} already in use")
        table = RollableTable(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            name=self._table_name(msg.name, msg.id),
            items=[],
            show_players=True,
        )
        async with self._commit(msg.type, f'created rollable table "{table.name}"') as s:
            s.add(table)
        self.tables[table.id] = table
        self._send_tables([table], [])

    async def on_table_update(self, conn: Connection, msg: p.TableUpdate) -> None:
        self._require_gm(conn)
        table = self._get_table(msg.id)
        values: dict[str, Any] = {}
        if msg.name is not None:
            values["name"] = self._table_name(msg.name, table.id)
        if msg.show_players is not None:
            values["show_players"] = msg.show_players
        if msg.items is not None:
            values["items"] = [i.model_dump() for i in msg.items]
        values = {k: v for k, v in values.items() if getattr(table, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited rollable table "{table.name}"') as s:
            await s.execute(
                update(RollableTable).where(RollableTable.id == table.id).values(**values)
            )
        for k, v in values.items():
            setattr(table, k, v)
        self._send_tables([table], [])

    async def on_table_delete(self, conn: Connection, msg: p.TableDelete) -> None:
        self._require_gm(conn)
        table = self._get_table(msg.id)
        async with self._commit(msg.type, f'deleted rollable table "{table.name}"') as s:
            await s.execute(delete(RollableTable).where(RollableTable.id == table.id))
        del self.tables[table.id]
        self._send_tables([], [table.id])

    # --- Multi-sided tokens -------------------------------------------------

    async def on_token_side(self, conn: Connection, msg: p.TokenSide) -> None:
        """Server-side, so a random side (a coin, a die token) can't be picked by the client."""
        patches = []
        for obj_id in msg.ids:
            obj = self._get_object(obj_id)
            sides = obj.props.get("sides") or []
            if len(sides) < 2:
                continue
            side = _rng.randrange(len(sides)) if msg.side is None else msg.side
            if side >= len(sides):
                raise GameError(f"{_describe([obj])} has only {len(sides)} sides")
            patches.append(p.ObjectPatch(id=obj.id, props={"side": side, "image": sides[side]}))
        if patches:
            await self.on_obj_update(conn, p.ObjectUpdate(type="obj.update", patches=patches))

    # --- Card decks ----------------------------------------------------------

    def _sees_deck(self, player: Player, deck: Deck) -> bool:
        return player.is_gm or bool((deck.settings or {}).get("show_players", True))

    def _cards_on_table(self, deck: Deck) -> dict[str, MapObject]:
        """Card id -> its token on the map."""
        out: dict[str, MapObject] = {}
        for o in self.objects.values():
            card = o.props.get("card")
            if card and card.get("deck_id") == deck.id:
                out[card["card_id"]] = o
        return out

    def _deck_for(self, player: Player, deck: Deck) -> dict[str, Any]:
        return deck_dict(deck, player, set(self._cards_on_table(deck)))

    def _send_decks(self, upsert: list[Deck], removed: list[str]) -> None:
        for c in self.connections:
            if not c.player:
                continue
            shown = [d for d in upsert if self._sees_deck(c.player, d)]
            gone = removed + [d.id for d in upsert if not self._sees_deck(c.player, d)]
            if shown:
                c.send(
                    {"type": "deck.upsert", "decks": [self._deck_for(c.player, d) for d in shown]}
                )
            if gone:
                c.send({"type": "deck.removed", "ids": gone})

    def _get_deck(self, deck_id: str) -> Deck:
        deck = self.decks.get(deck_id)
        if deck is None:
            raise GameError("deck does not exist")
        return deck

    async def _save_deck(self, deck: Deck, values: dict[str, Any], kind: str, summary: str) -> None:
        async with self._commit(kind, summary) as s:
            await s.execute(update(Deck).where(Deck.id == deck.id).values(**values))
        for k, v in values.items():
            setattr(deck, k, v)
        self._send_decks([deck], [])

    async def on_deck_create(self, conn: Connection, msg: p.DeckCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.decks:
            raise GameError(f"id {msg.id} already in use")
        deck = Deck(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            name=msg.name.strip() or "Deck",
            back=None,
            cards=[],
            pile=[],
            hands={},
            settings=p.DeckSettings().model_dump(),
        )
        async with self._commit(msg.type, f'created deck "{deck.name}"') as s:
            s.add(deck)
        self.decks[deck.id] = deck
        self._send_decks([deck], [])

    async def on_deck_update(self, conn: Connection, msg: p.DeckUpdate) -> None:
        self._require_gm(conn)
        deck = self._get_deck(msg.id)
        values = msg.model_dump(exclude_unset=True, include={"name", "back"})
        if msg.settings is not None:
            values["settings"] = {**deck.settings, **msg.settings.model_dump(exclude_unset=True)}
        if msg.cards is not None:
            cards = [c.model_dump() for c in msg.cards]
            ids = [c["id"] for c in cards]
            if len(set(ids)) != len(ids):
                raise GameError("two cards have the same id")
            old = {c["id"] for c in deck.cards}
            kept = set(ids)
            # New cards go to the bottom of the pile; removed ones leave every list.
            values["cards"] = cards
            values["pile"] = [cid for cid in ids if cid not in old] + [
                cid for cid in deck.pile if cid in kept
            ]
            values["hands"] = {
                pid: [cid for cid in hand if cid in kept] for pid, hand in deck.hands.items()
            }
        values = {k: v for k, v in values.items() if getattr(deck, k) != v}
        if values:
            await self._save_deck(deck, values, msg.type, f'edited deck "{deck.name}"')

    async def on_deck_delete(self, conn: Connection, msg: p.DeckDelete) -> None:
        self._require_gm(conn)
        deck = self._get_deck(msg.id)
        tokens = list(self._cards_on_table(deck).values())
        if tokens:
            await self._remove_objects(tokens, msg.type, f'cleared the cards of "{deck.name}"')
        async with self._commit(msg.type, f'deleted deck "{deck.name}"') as s:
            await s.execute(delete(Deck).where(Deck.id == deck.id))
        del self.decks[deck.id]
        self._send_decks([], [deck.id])

    async def _add_objects(self, objs: list[MapObject], kind: str, summary: str) -> None:
        """Create objects for the server's own actions: no permission check, no undo step."""
        changes = [{"id": o.id, "before": None, "after": object_dict(o)} for o in objs]
        async with self._commit(kind, summary, {"objects": changes}, [o.id for o in objs]) as s:
            s.add_all(objs)
        for o in objs:
            self.objects[o.id] = o
        self._publish_objects(objs, [], {})

    async def _remove_objects(self, objs: list[MapObject], kind: str, summary: str) -> None:
        changes = [{"id": o.id, "before": object_dict(o), "after": None} for o in objs]
        ids = [o.id for o in objs]
        async with self._commit(kind, summary, {"objects": changes}, ids) as s:
            await s.execute(delete(MapObject).where(MapObject.id.in_(ids)))
        for o in objs:
            del self.objects[o.id]
        self._publish_objects([], objs, {})
        await self._prune_turn_order(set(ids))

    def _from_hand(self, deck: Deck, player: Player, card_ids: list[str]) -> dict[str, list[str]]:
        """Hands after taking `card_ids` out: the player's own, or any hand for the GM."""
        hands = {pid: list(ids) for pid, ids in deck.hands.items()}
        for cid in card_ids:
            holder = next((pid for pid, ids in hands.items() if cid in ids), None)
            if holder is None or (holder != player.id and not player.is_gm):
                raise GameError("that card is not in your hand")
            hands[holder].remove(cid)
        return {pid: ids for pid, ids in hands.items() if ids}

    async def on_deck_action(self, conn: Connection, msg: p.DeckAction) -> None:
        player = conn.player
        assert player is not None
        deck = self._get_deck(msg.deck_id)
        if not self._sees_deck(player, deck):
            raise GameError("deck does not exist")
        name = f'"{deck.name}"'
        on_table = self._cards_on_table(deck)

        if msg.action in ("shuffle", "recall"):
            self._require_gm(conn)
            if msg.action == "recall":
                if on_table:
                    await self._remove_objects(
                        list(on_table.values()), msg.type, f"recalled {name}"
                    )
                hands: dict[str, list[str]] = {}
                pile = [c["id"] for c in deck.cards]
            else:
                # The discard pile goes back in; hands and the table stay as they are.
                hands = deck.hands
                held = {cid for ids in hands.values() for cid in ids}
                pile = [
                    c["id"] for c in deck.cards if c["id"] not in held and c["id"] not in on_table
                ]
            _rng.shuffle(pile)
            summary = f"{'recalled and ' if msg.action == 'recall' else ''}shuffled {name}"
            await self._save_deck(deck, {"pile": pile, "hands": hands}, msg.type, summary)
            await self._card_chat(player, summary)
            return

        if msg.action == "draw":
            to = msg.player_id or player.id
            if to != player.id:
                self._require_gm(conn)
            elif not player.is_gm and not deck.settings.get("players_draw", True):
                raise GameError("only the GM deals from this deck")
            if to not in self.players:
                raise GameError("player does not exist")
            if len(deck.pile) < msg.count:
                raise GameError(f"{name} has only {len(deck.pile)} cards left")
            drawn = deck.pile[len(deck.pile) - msg.count :][::-1]
            hands = {**deck.hands, to: [*deck.hands.get(to, []), *drawn]}
            who = self.players[to].name
            cards = f"{msg.count} card{'s' if msg.count > 1 else ''}"
            summary = (
                f"drew {cards} from {name}"
                if to == player.id
                else f"dealt {cards} from {name} to {who}"
            )
            await self._save_deck(
                deck,
                {"pile": deck.pile[: len(deck.pile) - msg.count], "hands": hands},
                msg.type,
                summary,
            )
            await self._card_chat(player, summary)
            return

        if msg.action == "play":
            page = self._get_page(msg.page_id or self.player_page(player))
            if not player.is_gm and page.id != self.player_page(player):
                raise GameError("you can only play cards on your page")
            values: dict[str, Any] = {}
            if msg.card_ids:
                values["hands"] = self._from_hand(deck, player, msg.card_ids)
                played = msg.card_ids
            else:
                self._require_gm(conn)
                if len(deck.pile) < msg.count:
                    raise GameError(f"{name} has only {len(deck.pile)} cards left")
                played = deck.pile[len(deck.pile) - msg.count :][::-1]
                values["pile"] = deck.pile[: len(deck.pile) - msg.count]
            holder = {cid: pid for pid, ids in deck.hands.items() for cid in ids}
            by_id = {c["id"]: c for c in deck.cards}
            size = page.grid_size
            top = self._top_z()
            objs = []
            for i, cid in enumerate(played):
                card = by_id[cid]
                side = 1 if msg.face_down else 0
                sides = [card.get("image"), deck.back]
                owner = holder.get(cid)
                objs.append(
                    MapObject(
                        id=str(uuid.uuid4()),
                        page_id=page.id,
                        kind="token",
                        layer="objects",
                        x=msg.x + i * size * 0.3,
                        y=msg.y,
                        width=size,
                        height=size * CARD_RATIO,
                        rotation=0,
                        z=top + i + 1,
                        owner_id=player.id,
                        props={
                            "name": card.get("name") or "Card",
                            "image": sides[side],
                            "sides": sides,
                            "side": side,
                            "show_name": False,
                            # Kept for every viewer: a card without a picture is drawn as one.
                            "shape": "card",
                            "card": {"deck_id": deck.id, "card_id": cid},
                            "controlled_by": [owner] if owner else [],
                        },
                    )
                )
            how = " face down" if msg.face_down else ""
            # A face-down card keeps its name to itself.
            what = (
                f"{len(objs)} card{'s' if len(objs) > 1 else ''}"
                if len(objs) > 1 or msg.face_down
                else f'"{objs[0].props["name"]}"'
            )
            summary = f"played {what}{how} from {name}"
            await self._add_objects(objs, msg.type, summary)
            await self._save_deck(deck, values, msg.type, summary)
            await self._card_chat(player, summary)
            return

        if msg.action == "discard":
            hands = self._from_hand(deck, player, msg.card_ids)
            n = len(msg.card_ids)
            summary = f"discarded {n} card{'s' if n != 1 else ''} from {name}"
            await self._save_deck(deck, {"hands": hands}, msg.type, summary)
            await self._card_chat(player, summary)
            return

        # take: card tokens from the table into the hand.
        tokens = []
        for obj_id in msg.object_ids:
            obj = self._get_object(obj_id)
            card = obj.props.get("card") or {}
            if card.get("deck_id") != deck.id:
                raise GameError("that is not a card of this deck")
            if not permissions.controls(player, obj):
                raise GameError("you do not control that card")
            tokens.append(obj)
        if not tokens:
            return
        summary = (
            f"{player.name} took {len(tokens)} card{'s' if len(tokens) > 1 else ''} into their hand"
        )
        await self._remove_objects(tokens, msg.type, summary)
        taken = [o.props["card"]["card_id"] for o in tokens]
        hands = {**deck.hands, player.id: [*deck.hands.get(player.id, []), *taken]}
        await self._save_deck(deck, {"hands": hands}, msg.type, summary)

    async def _card_chat(self, player: Player, text: str) -> None:
        """Card moves are announced in chat, as at a real table: "Aria drew 1 card from …"."""
        await self._post_chat(player, player.name, content=text + ".", roll=None, kind="emote")

    async def _after_card_tokens_change(self, objs: list[MapObject]) -> None:
        """Counts of the decks whose card tokens were created or deleted elsewhere."""
        decks = {
            o.props["card"].get("deck_id") for o in objs if isinstance(o.props.get("card"), dict)
        }
        changed = [self.decks[d] for d in decks if d in self.decks]
        if changed:
            self._send_decks(changed, [])

    # --- Art library ---------------------------------------------------------

    def _send_assets(self, player_id: str, upsert: list[Asset], removed: list[str]) -> None:
        """A library is private: only its owner's connections hear about it."""
        for c in self.connections:
            if c.player and c.player.id == player_id:
                if upsert:
                    c.send({"type": "asset.upsert", "assets": [asset_dict(a) for a in upsert]})
                if removed:
                    c.send({"type": "asset.removed", "ids": removed})

    def _own_asset(self, player: Player, asset_id: str) -> Asset:
        asset = self.assets.get(asset_id)
        if asset is None or asset.player_id != player.id:
            raise GameError("image does not exist")
        return asset

    async def on_asset_create(self, conn: Connection, msg: p.AssetCreate) -> None:
        player = conn.player
        assert player is not None
        if msg.id in self.assets:
            raise GameError(f"id {msg.id} already in use")
        values = msg.model_dump(exclude={"type", "rid"})
        values["tags"] = _tags(values["tags"])
        values["folder"] = values["folder"].strip()
        asset = Asset(game_id=DEFAULT_GAME_ID, player_id=player.id, **values)
        async with self._commit(msg.type, f'added "{asset.name}" to the art library') as s:
            s.add(asset)
        self.assets[asset.id] = asset
        self._send_assets(player.id, [asset], [])

    async def on_asset_update(self, conn: Connection, msg: p.AssetUpdate) -> None:
        player = conn.player
        assert player is not None
        asset = self._own_asset(player, msg.id)
        values = msg.model_dump(exclude_none=True, include={"name", "folder", "tags"})
        if "tags" in values:
            values["tags"] = _tags(values["tags"])
        if "folder" in values:
            values["folder"] = values["folder"].strip()
        values = {k: v for k, v in values.items() if getattr(asset, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited "{asset.name}" in the art library') as s:
            await s.execute(update(Asset).where(Asset.id == asset.id).values(**values))
        for k, v in values.items():
            setattr(asset, k, v)
        self._send_assets(player.id, [asset], [])

    async def on_asset_delete(self, conn: Connection, msg: p.AssetDelete) -> None:
        player = conn.player
        assert player is not None
        assets = [self._own_asset(player, i) for i in msg.ids]
        n = len(assets)
        summary = f"removed {n} image{'s' if n > 1 else ''} from the art library"
        async with self._commit(msg.type, summary) as s:
            await s.execute(delete(Asset).where(Asset.id.in_([a.id for a in assets])))
        for a in assets:
            # The files stay: tokens on the map may still show them.
            del self.assets[a.id]
        self._send_assets(player.id, [], [a.id for a in assets])

    async def on_chat_send(self, conn: Connection, msg: p.ChatSend) -> None:
        player = conn.player
        assert player is not None
        resolver = MacroResolver(self, player, msg.selected_id, msg.target_id)
        try:
            expanded = macros.expand(msg.text, resolver, msg.answers)
        except macros.NeedTarget:
            conn.send({"type": "chat.needs", "rid": msg.rid, "target": True, "queries": []})
            return
        except macros.MacroError as e:
            raise GameError(str(e)) from e
        if expanded.queries:
            # The sender answers all the questions in one dialog and sends again.
            queries = [q.as_dict() for q in expanded.queries]
            conn.send({"type": "chat.needs", "rid": msg.rid, "target": False, "queries": queries})
            return
        try:
            draft = chat.parse(expanded.text, is_gm=player.is_gm, tables=self._table_lookup(player))
        except chat.ChatError as e:
            raise GameError(str(e)) from e
        recipients = self._resolve_whisper(draft.whisper_to) if draft.whisper_to else None
        roll: dict[str, Any] | None = None
        if draft.roll or draft.inline or draft.template:
            roll = {"main": draft.roll, "inline": draft.inline, "template": draft.template}
        await self._post_chat(
            player,
            self._speaker(player, msg.as_character),
            content=draft.content,
            roll=roll,
            kind=draft.kind,
            recipients=recipients,
            gm_only=draft.gm_only,
        )

    async def _post_chat(
        self,
        player: Player,
        speaker: str,
        content: str,
        roll: dict[str, Any] | None,
        kind: str = "text",
        recipients: list[str] | None = None,
        gm_only: bool = False,
    ) -> None:
        """Save a chat message and send it to everyone allowed to see it."""
        row = ChatMessage(
            game_id=DEFAULT_GAME_ID,
            player_id=player.id,
            speaker=speaker,
            color=player.color,
            kind=kind,
            content=content,
            roll=roll,
            recipients=recipients,
            gm_only=gm_only,
        )
        async with session_scope() as s:
            s.add(row)
            await s.flush()
            await s.refresh(row, ["created_at"])
        payload = json.dumps({"type": "chat", "message": chat_dict(row), "seq": self.seq})
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
            "segment": msg.segment.model_dump(exclude={"via"} if not msg.segment.via else None),
        }
        for c in self._viewers(msg.page_id):
            if c is conn:
                continue
            assert c.player is not None
            if obj is None or self._can_see(c.player, obj):
                c.send(payload)

    def _end_measure(self, conn: Connection) -> None:
        """Tell the page's viewers that this connection stopped measuring."""
        page_id = conn.measuring
        if page_id is None or conn.player is None:
            return
        conn.measuring = None
        payload = {
            "type": "measure",
            "page_id": page_id,
            "player_id": conn.player.id,
            "segment": None,
        }
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

    async def _save_turns(
        self, kind: str, summary: str, order: list[dict[str, Any]], round_: int | None = None
    ) -> None:
        assert self.game is not None
        game_settings = self.game.settings
        if round_ is not None:
            game_settings = {**game_settings, "round": round_}
        async with self._commit(kind, summary) as s:
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
        await self._save_turns(
            msg.type, "rearranged the turn tracker", [e.model_dump() for e in msg.order], msg.round
        )

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
        await self._save_turns(
            msg.type, f'added "{entry["name"]}" to the turn tracker', [*order, entry]
        )

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
        await self._save_turns(msg.type, f'changed turn of "{entry["name"]}"', order)

    async def on_turn_remove(self, conn: Connection, msg: p.TurnRemove) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        if not self._controls_entry(player, self.game.turn_order[i]):
            raise GameError("you do not control this entry")
        name = self.game.turn_order[i]["name"]
        await self._save_turns(
            msg.type,
            f'removed "{name}" from the turn tracker',
            [e for e in self.game.turn_order if e["id"] != msg.id],
        )

    async def on_turn_next(self, conn: Connection, msg: p.TurnNext) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        order = self.game.turn_order
        if not order:
            return
        if not self._controls_entry(player, order[0]):
            raise GameError("it is not your turn")
        rotated = [*order[1:], order[0]]
        rotated[0] = {**rotated[0], "used": {}, "moved": 0}
        round_ = self.game.settings.get("round", 0)
        # A new round starts when the first entry of the sorted order comes back on top.
        if rotated[0]["id"] == _round_head(order):
            round_ += 1
        await self._save_turns(msg.type, f'ended the turn of "{order[0]["name"]}"', rotated, round_)
        await self._on_turn_end(order[0])
        await self._on_turn_start(rotated[0])

    async def on_turn_sort(self, conn: Connection, msg: p.TurnSort) -> None:
        self._require_gm(conn)
        assert self.game is not None
        order = sorted(self.game.turn_order, key=self._turn_key, reverse=msg.descending)
        await self._save_turns(msg.type, "sorted the turn tracker", order, 1 if order else 0)

    async def _prune_turn_order(self, object_ids: set[str]) -> None:
        assert self.game is not None
        order = [e for e in self.game.turn_order if e.get("object_id") not in object_ids]
        if len(order) != len(self.game.turn_order):
            await self._save_turns(
                "turn.prune", "removed deleted tokens from the turn tracker", order
            )


def _turn_value(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("-inf")


def _round_head(order: list[dict[str, Any]]) -> str:
    """Entry that starts a round: the highest initiative."""
    return max(order, key=lambda e: _turn_value(e["value"]))["id"]


def _macro_name(name: str) -> str:
    """Macro names are called as `#Name`: no spaces."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", name.replace(" ", "_"))
    if not cleaned:
        raise GameError("a macro name needs letters or digits")
    return cleaned


# Token fields readable with @{selected|…} and @{target|…}: (prop, key in the bar).
TOKEN_FIELDS = {
    "hp": ("bar1", "value"),
    "bar1": ("bar1", "value"),
    "temp_hp": ("bar2", "value"),
    "bar2": ("bar2", "value"),
}


class MacroResolver:
    """Game data for macro expansion, limited to what `player` may see."""

    def __init__(
        self,
        server: GameServer,
        player: Player,
        selected_id: str | None,
        target_id: str | None,
    ) -> None:
        self.server = server
        self.player = player
        self.tokens = {"selected": selected_id, "target": target_id}

    def macro(self, name: str) -> str | None:
        own = self.server._macros_of(self.player.id)
        found = next((m for m in own if m.name == name), None) or next(
            (m for m in own if m.name.casefold() == name.casefold()), None
        )
        return found.action if found else None

    def _token(self, ref: str) -> MapObject:
        token_id = self.tokens[ref]
        if token_id is None:
            if ref == "target":
                raise macros.NeedTarget
            raise macros.MacroError("select a token first")
        obj = self.server.objects.get(token_id)
        if obj is None or obj.kind != "token" or not self.server._can_see(self.player, obj):
            raise macros.MacroError(f"the {ref} token does not exist")
        return obj

    def _character(self, ref: str) -> Character:
        if ref in self.tokens:
            obj = self._token(ref)
            character = self.server.characters.get(obj.props.get("represents") or "")
            if character is None:
                raise macros.MacroError(f"the {ref} token does not represent a character")
        elif ref.startswith(macros.BOUND):
            character = self.server.characters.get(ref[1:])
        else:
            key = ref.casefold()
            character = next(
                (
                    c
                    for c in self.server.characters.values()
                    if c.name.casefold() == key and self.server._sees_character(self.player, c)
                ),
                None,
            )
        if character is None or not self.server._sees_character(self.player, character):
            raise macros.MacroError(f'no character named "{ref}"')
        return character

    def ability(self, ref: str, name: str) -> tuple[str, str]:
        character = self._character(ref)
        key = name.casefold()
        found = next((a for a in character.abilities if a["name"].casefold() == key), None)
        if found is None:
            raise macros.MacroError(f'{character.name} has no ability "{name}"')
        return found["action"], character.id

    def attribute(self, ref: str, name: str, use_max: bool) -> str:
        key = name.casefold()
        if ref in self.tokens:
            obj = self._token(ref)
            if key == "token_name":
                return str(obj.props.get("name") or "")
            if key in TOKEN_FIELDS:
                if not self.player.is_gm and not self.server._shows_hp(obj):
                    raise macros.MacroError("the hit points of that creature are hidden")
                prop, _ = TOKEN_FIELDS[key]
                value = (obj.props.get(prop) or {}).get("max" if use_max else "value")
                return "0" if value is None else _number(value)
        character = self._character(ref)
        found = next((a for a in character.attributes if a["name"].casefold() == key), None)
        if found is None:
            raise macros.MacroError(f'{character.name} has no attribute "{name}"')
        return found["max" if use_max else "current"] or "0"


def _tags(tags: list[str]) -> list[str]:
    """Lowercase, trimmed, without repeats, in their order."""
    out: list[str] = []
    for tag in tags:
        tag = tag.strip().casefold()
        if tag and tag not in out:
            out.append(tag)
    return out


def _number(value: Any) -> str:
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def _apply_buttons(amount: int, damage_type: str, target: str | None, kind: str = "damage") -> str:
    """Chat buttons that apply rolled damage or healing (`!apply` in the client)."""
    dtype = damage_type or "-"
    buttons = []
    if target:
        buttons.append(f"[To target](!apply {kind} {amount} {dtype} {target})")
        if kind == "damage":
            buttons.append(f"[Half to target](!apply damage {amount} {dtype} {target} half)")
    buttons.append(f"[To selected](!apply {kind} {amount} {dtype} sel)")
    if kind == "damage":
        buttons.append(f"[Half to selected](!apply damage {amount} {dtype} sel half)")
    return " ".join(buttons)


def _mode_label(mode: str) -> str:
    return {"advantage": "With advantage", "disadvantage": "With disadvantage"}.get(mode, "Roll")


def _copy(value: Any) -> Any:
    """Deep copy of JSON-like data, so stored event states never alias live objects."""
    return json.loads(json.dumps(value))


def _other(side: str) -> str:
    return "before" if side == "after" else "after"


def _name(data: dict[str, Any]) -> str:
    kind = data.get("kind", "object")
    name = (data.get("props") or {}).get("name")
    if kind == "template":
        return "spell area"
    if kind in ("path", "text"):
        return "drawing" if kind == "path" else "text"
    return f'{kind} "{name}"' if name else kind


def _describe(objs: list[MapObject]) -> str:
    """Short English description for the history: 'token "Goblin"', '3 objects'."""
    if len(objs) == 1:
        return _name(object_dict(objs[0]))
    kinds = {o.kind for o in objs}
    noun = "tokens" if kinds == {"token"} else "objects"
    return f"{len(objs)} {noun}"


def _verb(changes: list[dict[str, Any]]) -> str:
    fields = set().union(*(ch["after"].keys() for ch in changes))
    if fields <= {"x", "y", "page_id"}:
        return "moved"
    if fields == {"z"}:
        return "reordered"
    if fields == {"rotation"}:
        return "rotated"
    if fields <= {"width", "height", "x", "y"}:
        return "resized"
    return "edited"


def _history_entry(event: Event) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "player_id": event.player_id,
        "kind": event.kind,
        "summary": event.summary,
        "revertible": bool(event.data.get("objects")),
        "reverted": event.reverted_by is not None,
        "created_at": event.created_at.isoformat(),
    }


def _validation_summary(e: ValidationError) -> str:
    first = e.errors()[0]
    loc = ".".join(str(x) for x in first["loc"])
    return f"invalid message ({loc}: {first['msg']})"


server = GameServer()
