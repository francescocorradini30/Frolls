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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_scope
from app.game import fog, permissions, units
from app.game import protocol as p
from app.game.serialize import (
    game_dict,
    object_dict,
    page_dict,
    player_dict,
)
from app.models import (
    DEFAULT_GAME_ID,
    Asset,
    Character,
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
from app.rules5e.data import SKILLS

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


class ServerBase:
    """State, connections, filtering helpers and the event log, shared by every mixin."""

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


def _turn_value(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("-inf")


def _round_head(order: list[dict[str, Any]]) -> str:
    """Entry that starts a round: the highest initiative."""
    return max(order, key=lambda e: _turn_value(e["value"]))["id"]


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
