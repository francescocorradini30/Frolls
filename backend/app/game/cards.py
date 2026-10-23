"""Combat cards: the structured chat card of a combat action, and what each viewer sees.

A card lives in `chat_messages.roll` as `{"main": None, "inline": [rolls], "card": {...}}`:

    {v, kind, author_id, actor_id, actor_name, actor_monster, action, hidden,
     seqs: [event seqs, the first made the card], undone_seqs: [...], undone_by,
     turn: {round, entry} | None,
     rows: [{token_id, name, monster, outcome, d20 (index in inline), total, natural, ac,
             dc, save, damage: [{roll, formula, type, total, seq}], taken, hp, state,
             notes, added, conc}],
     reasons, warnings, notes}

Players don't see monsters' dice (game option), AC (option) or hit points beyond what the
"monsters' hit points" option allows. Pure functions.
"""

from typing import Any


def redact(roll: dict[str, Any], npc_hp: str, show_ac: bool, hide_rolls: bool) -> dict[str, Any]:
    """The card as a player sees it (the GM sees everything)."""
    card = roll.get("card")
    if card is None:
        return roll
    inline = list(roll.get("inline") or [])
    rows = []
    hide_actor_dice = hide_rolls and card.get("actor_monster")
    for row in card.get("rows", []):
        row = dict(row)
        if row.get("monster"):
            if not show_ac:
                row.pop("ac", None)
            if npc_hp != "full":
                row.pop("hp", None)
                if npc_hp == "hidden":
                    row.pop("state", None)
        if hide_actor_dice:
            if isinstance(row.get("d20"), int) and row["d20"] < len(inline):
                inline[row["d20"]] = None
            for key in ("d20", "total", "natural"):
                row.pop(key, None)
        rows.append(row)
    out = {**card, "rows": rows}
    out.pop("pending_gm", None)
    if hide_actor_dice:
        out["reasons"] = []
    return {**roll, "inline": inline, "card": out}
