"""Database models.

Design notes:
- One persistent game for now (id=1); every row still carries game_id so
  multi-campaign support is a matter of adding auth, not a migration.
- Map objects (tokens, drawings, text, ...) share one table: common geometry
  is in columns for fast filtering, type-specific fields live in `props` JSONB.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DEFAULT_GAME_ID = 1


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # Page where players are, unless overridden per player.
    player_page_id: Mapped[str | None] = mapped_column(String(36))
    # {player_id: page_id}
    player_page_overrides: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    # Initiative tracker: [{id, object_id?, name, initiative, custom?}]
    turn_order: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(9))
    is_gm: Mapped[bool] = mapped_column(Boolean, default=False)
    # Personal preferences (wheel, chat timestamps...), sent only to the player itself.
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[float] = mapped_column(Float, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    # Size in grid cells.
    width: Mapped[int] = mapped_column(Integer, default=25)
    height: Mapped[int] = mapped_column(Integer, default=25)
    # Pixels per cell at 100% zoom.
    grid_size: Mapped[int] = mapped_column(Integer, default=70)
    grid_type: Mapped[str] = mapped_column(String(12), default="square")
    grid_color: Mapped[str] = mapped_column(String(9), default="#c0c0c0")
    grid_opacity: Mapped[float] = mapped_column(Float, default=0.5)
    snap: Mapped[bool] = mapped_column(Boolean, default=True)
    # Overridden by the game measurement system when a page is created (see units.py).
    scale_number: Mapped[float] = mapped_column(Float, default=1.5)
    scale_unit: Mapped[str] = mapped_column(String(12), default="m")
    # "5e" (every diagonal = 1 cell), "pf" (alternating 1/2), "euclid", "manhattan"
    diagonal_rule: Mapped[str] = mapped_column(String(12), default="5e")
    background_color: Mapped[str] = mapped_column(String(9), default="#ffffff")
    # Manual fog of war (app/game/fog.py): {"enabled": bool, "ops": [...]}.
    fog: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {"enabled": False, "ops": []},
        server_default='{"enabled": false, "ops": []}',
    )


class MapObject(Base):
    __tablename__ = "map_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    # token | image | path | text | template
    kind: Mapped[str] = mapped_column(String(16))
    # map | objects | gm
    layer: Mapped[str] = mapped_column(String(12), default="objects")
    # Centre position and size in page pixels (grid_size units).
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float, default=70)
    height: Mapped[float] = mapped_column(Float, default=70)
    rotation: Mapped[float] = mapped_column(Float, default=0)
    z: Mapped[float] = mapped_column(Float, default=0)
    owner_id: Mapped[str | None] = mapped_column(String(36))
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JournalFolder(Base):
    """Journal folder; folders nest without limit through `parent_id`. GM only."""

    __tablename__ = "journal_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[str | None] = mapped_column(String(36))


class Character(Base):
    """Journal entry for a character (PC or NPC). Tokens link to it with `props.represents`."""

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    avatar: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str] = mapped_column(Text, default="")
    # Hidden from players.
    gm_notes: Mapped[str] = mapped_column(Text, default="")
    # [{name, current, max}]
    attributes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Macros of the character: [{name, action, token_action}]. `%{Name|ability}` runs one;
    # token actions show as buttons when a token representing it is selected.
    abilities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # 5e sheet (app/rules5e/sheet.py); None = a plain journal entry.
    sheet: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    folder_id: Mapped[str | None] = mapped_column(String(36))
    # Player who plays this character: sees it, edits it, and speaks with its name in chat.
    player_id: Mapped[str | None] = mapped_column(String(36))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Macro(Base):
    """A player's macro: chat text run with a click or with `#Name`."""

    __tablename__ = "macros"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(Text, default="")
    # Shown in the quick bar under the map.
    in_bar: Mapped[bool] = mapped_column(Boolean, default=False)


class RollableTable(Base):
    """A rollable table: `1t[name]` draws an item by weight."""

    __tablename__ = "rollable_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    # [{id, name, weight, image}]
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Hidden tables are listed and rollable only by the GM.
    show_players: Mapped[bool] = mapped_column(Boolean, default=True)


class Deck(Base):
    """A deck of cards. A card is in the pile, in a hand, or on the table as a token with
    `props.card`; any other card is in the discard pile. Deriving the discard pile means
    deleting, undoing or copying card tokens can never make the lists disagree."""

    __tablename__ = "decks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    # Card back image, shared by all the cards.
    back: Mapped[str | None] = mapped_column(String(500))
    # [{id, name, image}]
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Card ids; the top of the pile is the last one.
    pile: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # player id -> card ids
    hands: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict)
    # {show_players, players_draw}
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Asset(Base):
    """An image in a player's art library."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(500))
    thumb: Mapped[str | None] = mapped_column(String(500))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    folder: Mapped[str] = mapped_column(String(120), default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    """Event log: one row per committed change, numbered per game.

    `seq` is stamped on every message the server sends, so a reconnecting client can
    ask only for what changed since. Map-object events keep the state before and after
    (`data.objects`), which is what undo and redo apply.
    """

    __tablename__ = "events"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    player_id: Mapped[str | None] = mapped_column(String(36))
    # The client message type (obj.update, page.create, ...) or undo / redo / revert.
    kind: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(200), default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Event that undid this one, if any.
    reverted_by: Mapped[int | None] = mapped_column(BigInteger)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    player_id: Mapped[str | None] = mapped_column(String(36))
    speaker: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(9), default="#888888")
    # text | roll | emote | ooc | whisper | system | desc
    kind: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text, default="")
    roll: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Whisper recipients (player ids). NULL = visible to everyone.
    recipients: Mapped[list[str] | None] = mapped_column(JSONB)
    # GM-only rolls (/gr) are visible to GMs and the sender.
    gm_only: Mapped[bool] = mapped_column(Boolean, default=False)
