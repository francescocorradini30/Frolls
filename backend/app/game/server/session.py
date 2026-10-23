"""GameServer handlers: session, pages."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import session_scope
from app.game import protocol as p
from app.game import units
from app.game.serialize import (
    asset_dict,
    chat_dict,
    macro_dict,
    object_dict,
    page_dict,
    player_dict,
    table_dict,
)
from app.game.server.base import (
    Connection,
    GameError,
    ServerBase,
)
from app.models import (
    DEFAULT_GAME_ID,
    ChatMessage,
    Game,
    MapObject,
    Page,
    Player,
)


class SessionMixin(ServerBase):
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
