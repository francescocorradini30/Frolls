"""Who may see and change what. GMs may do everything."""

from typing import Any

from app.models import MapObject, Player
from app.rules5e.damage import bloodied_state

PLAYER_LAYERS = {"objects"}
DRAWING_KINDS = {"path", "text", "template"}
# Fields a non-GM may never change on an object.
GM_ONLY_FIELDS = {"layer", "owner_id", "page_id", "kind"}
GM_ONLY_PROPS = {"controlled_by", "gm_notes", "represents", "card"}


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


def visible_props(player: Player, obj: MapObject, hp: str = "full") -> dict[str, Any]:
    """Props a player may see. `hp`: how much of the token's hit points they see
    (full, status or hidden; the server decides it for monsters)."""
    if player.is_gm:
        return obj.props
    props = {k: v for k, v in obj.props.items() if k != "gm_notes"}
    if props.get("card") and props.get("side") == 1 and not controls(player, obj):
        # A face-down card: only its back, so its face can't be read from the page data.
        back = (props.get("sides") or [None, None])[1]
        props = {k: v for k, v in props.items() if k not in ("card", "sides", "name")}
        props["image"] = back
        props["show_name"] = False
    npc_hp = hp
    if npc_hp != "full":
        bar1 = props.pop("bar1", None)
        props.pop("bar2", None)
        if npc_hp == "status" and bar1 and bar1.get("max"):
            # Only how hurt it looks, in quarters: the bar shows it, the numbers stay hidden.
            current, maximum = int(bar1.get("value") or 0), int(bar1["max"])
            quarters = 0 if current <= 0 else max(1, round(4 * current / maximum))
            props["bar1"] = {"value": quarters, "max": 4, "state": bloodied_state(current, maximum)}
    return props


def can_create(player: Player, data: dict[str, Any]) -> bool:
    if player.is_gm:
        return True
    return data.get("layer", "objects") in PLAYER_LAYERS and data.get("kind") in DRAWING_KINDS


# What a lock freezes: where the object is and how big.
LOCKED_FIELDS = {"x", "y", "width", "height", "rotation", "page_id"}


def check_patch(player: Player, patch: dict[str, Any], obj: MapObject | None = None) -> str | None:
    """Return an error message if the player may not apply this patch."""
    if obj is not None and obj.props.get("locked") and LOCKED_FIELDS & patch.keys():
        # Unlocking in the same patch is fine; nobody moves a locked object by accident.
        if (patch.get("props") or {}).get("locked", True) is not None:
            return "it is locked: unlock it first"
    if player.is_gm:
        return None
    if GM_ONLY_FIELDS & patch.keys():
        return "only the GM can change layer, page or owner"
    if GM_ONLY_PROPS & (patch.get("props") or {}).keys():
        return "only the GM can change permissions and GM notes"
    return None
