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
