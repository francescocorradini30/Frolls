"""GameServer handlers: chat, live measurement, ping."""

from __future__ import annotations

import json
from typing import Any

from app.db import session_scope
from app.game import chat, macros, permissions
from app.game import protocol as p
from app.game.serialize import (
    chat_dict,
)
from app.game.server.base import (
    Connection,
    GameError,
    ServerBase,
)
from app.game.server.journal import MacroResolver
from app.models import (
    ChatMessage,
    Player,
)


class MessagingMixin(ServerBase):
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
            game_id=self.game_id,
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
