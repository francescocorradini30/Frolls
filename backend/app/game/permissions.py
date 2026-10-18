"""Who may see and change what. GMs may do everything."""

from typing import Any

from app.models import MapObject, Player

PLAYER_LAYERS = {"objects"}
DRAWING_KINDS = {"path", "text", "template"}
# Fields a non-GM may never change on an object.
GM_ONLY_FIELDS = {"layer", "owner_id", "page_id", "kind"}
GM_ONLY_PROPS = {"controlled_by", "gm_notes", "represents"}


def controls(player: Player, obj: MapObject) -> bool:
    if player.is_gm:
        return True
    if obj.layer not in PLAYER_LAYERS:
        return False
    controlled_by = obj.props.get("controlled_by") or []
    if "all" in controlled_by or player.id in controlled_by:
        return True
    return obj.kind in DRAWING_KINDS and obj.owner_id == player.id


def can_see(player: Player, obj: MapObject) -> bool:
    return player.is_gm or obj.layer != "gm"


def visible_props(player: Player, obj: MapObject) -> dict[str, Any]:
    if player.is_gm or "gm_notes" not in obj.props:
        return obj.props
    return {k: v for k, v in obj.props.items() if k != "gm_notes"}


def can_create(player: Player, data: dict[str, Any]) -> bool:
    if player.is_gm:
        return True
    return data.get("layer", "objects") in PLAYER_LAYERS and data.get("kind") in DRAWING_KINDS


def check_patch(player: Player, patch: dict[str, Any]) -> str | None:
    """Return an error message if the player may not apply this patch."""
    if player.is_gm:
        return None
    if GM_ONLY_FIELDS & patch.keys():
        return "solo il GM può cambiare livello, pagina o proprietario"
    if GM_ONLY_PROPS & (patch.get("props") or {}).keys():
        return "solo il GM può cambiare permessi e note GM"
    return None
