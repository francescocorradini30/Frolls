from typing import Any

from app.models import ChatMessage, Game, MapObject, Page, Player

PAGE_FIELDS = (
    "id",
    "name",
    "sort_order",
    "archived",
    "width",
    "height",
    "grid_size",
    "grid_type",
    "grid_color",
    "grid_opacity",
    "snap",
    "scale_number",
    "scale_unit",
    "diagonal_rule",
    "background_color",
)
OBJECT_FIELDS = (
    "id",
    "page_id",
    "kind",
    "layer",
    "x",
    "y",
    "width",
    "height",
    "rotation",
    "z",
    "owner_id",
    "props",
)


def page_dict(page: Page) -> dict[str, Any]:
    return {f: getattr(page, f) for f in PAGE_FIELDS}


def object_dict(obj: MapObject) -> dict[str, Any]:
    return {f: getattr(obj, f) for f in OBJECT_FIELDS}


def player_dict(player: Player, online: bool, private: bool = False) -> dict[str, Any]:
    data = {
        "id": player.id,
        "name": player.name,
        "color": player.color,
        "is_gm": player.is_gm,
        "online": online,
    }
    if private:
        data["settings"] = player.settings or {}
    return data


def game_dict(game: Game) -> dict[str, Any]:
    return {
        "name": game.name,
        "player_page_id": game.player_page_id,
        "player_page_overrides": game.player_page_overrides,
        "turn_order": game.turn_order,
        "settings": game.settings,
    }


def chat_dict(msg: ChatMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "created_at": msg.created_at.isoformat(),
        "player_id": msg.player_id,
        "speaker": msg.speaker,
        "color": msg.color,
        "kind": msg.kind,
        "content": msg.content,
        "roll": msg.roll,
        "recipients": msg.recipients,
        "gm_only": msg.gm_only,
    }
