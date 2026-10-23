"""The game server: one class assembled from a mixin per area (see the modules)."""

from app.game.server.base import Connection, GameError, ServerBase
from app.game.server.combat import CombatMixin
from app.game.server.journal import JournalMixin
from app.game.server.messaging import MessagingMixin
from app.game.server.objects import ObjectsMixin
from app.game.server.session import SessionMixin
from app.game.server.sheets import SheetsMixin
from app.game.server.world import WorldMixin


class GameServer(
    SessionMixin, ObjectsMixin, JournalMixin, SheetsMixin, CombatMixin, WorldMixin, MessagingMixin
):
    """Authoritative state of the game and the handler of every client message."""


server = GameServer()

__all__ = ["Connection", "GameError", "GameServer", "ServerBase", "server"]
