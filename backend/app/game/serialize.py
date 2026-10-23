from typing import Any

from app.models import (
    Asset,
    Character,
    ChatMessage,
    Deck,
    Game,
    JournalFolder,
    Macro,
    MapObject,
    Page,
    Player,
    RollableTable,
)
from app.rules5e.sheet import derive

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
    "fog",
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


CHARACTER_FIELDS = (
    "id",
    "name",
    "avatar",
    "bio",
    "gm_notes",
    "attributes",
    "abilities",
    "sheet",
    "folder_id",
    "player_id",
    "archived",
)


def character_dict(character: Character, gm: bool = True) -> dict[str, Any]:
    data = {f: getattr(character, f) for f in CHARACTER_FIELDS}
    data["derived"] = derive(character.sheet) if character.sheet else None
    if not gm:
        del data["gm_notes"]
    return data


def folder_dict(folder: JournalFolder) -> dict[str, Any]:
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}


def macro_dict(macro: Macro) -> dict[str, Any]:
    return {"id": macro.id, "name": macro.name, "action": macro.action, "in_bar": macro.in_bar}


def table_dict(table: RollableTable) -> dict[str, Any]:
    return {
        "id": table.id,
        "name": table.name,
        "items": table.items,
        "show_players": table.show_players,
    }


def deck_dict(
    deck: Deck, player: Player, on_table: set[str], hand_owner: str | None = None
) -> dict[str, Any]:
    """What `player` knows of the deck: the GM sees every card and hand, a player only the
    cards in their own hand and how many cards the others hold. The pile order is never sent.
    `on_table`: ids of the deck's cards on the map."""
    hands = deck.hands or {}
    held = {cid for ids in hands.values() for cid in ids}
    discard = [
        c
        for c in deck.cards
        if c["id"] not in held and c["id"] not in on_table and c["id"] not in deck.pile
    ]
    own = hands.get(player.id, [])
    by_id = {c["id"]: c for c in deck.cards}
    data: dict[str, Any] = {
        "id": deck.id,
        "name": deck.name,
        "back": deck.back,
        "settings": deck.settings or {},
        "size": len(deck.cards),
        "pile_count": len(deck.pile),
        "discard_count": len(discard),
        "table_count": len(on_table),
        "hand_counts": {pid: len(ids) for pid, ids in hands.items() if ids},
        "hand": [by_id[cid] for cid in own if cid in by_id],
    }
    if player.is_gm:
        data["cards"] = deck.cards
        data["hands"] = hands
        data["discard"] = [c["id"] for c in discard]
    return data


def asset_dict(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "name": asset.name,
        "url": asset.url,
        "thumb": asset.thumb,
        "width": asset.width,
        "height": asset.height,
        "folder": asset.folder,
        "tags": asset.tags,
    }
