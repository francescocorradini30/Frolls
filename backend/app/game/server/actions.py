"""GameServer handlers: combat actions (`combat.act`) and their chat cards.

One intent of a player = one `combat.act` = one resolution (rules5e/resolve.py) applied
through the usual helpers inside an action capture = one event = one card = one undo step.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from app.db import session_scope
from app.dice import DiceError
from app.dice import roll as dice_roll
from app.game import chat, permissions
from app.game import protocol as p
from app.game.server.base import Connection, GameError, ServerBase
from app.game.server.capture import captured
from app.models import ChatMessage, Event, MapObject, Player
from app.rules5e import damage as damage5e
from app.rules5e import geometry, resolve
from app.rules5e import rolls as rolls5e
from app.rules5e import sheet as sheet5e
from app.rules5e.sheet import Attack, Sheet

# Conditions that keep a creature from threatening or flanking anyone.
INCAPACITATED = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious", "dead"}


def _roll(formula: str) -> dict[str, Any]:
    try:
        return chat.roll_to_dict(dice_roll(formula))
    except DiceError as e:
        raise GameError(f"invalid formula {formula}: {e}") from e


class ActionsMixin(ServerBase):
    # --- Snapshots -------------------------------------------------------------

    def _box(self, obj: MapObject) -> geometry.Box:
        return geometry.Box(obj.x, obj.y, obj.width, obj.height)

    def _cell(self, obj: MapObject) -> float:
        page = self.pages.get(obj.page_id)
        return float(page.grid_size if page else 70)

    def _combatant(self, obj: MapObject) -> resolve.Combatant:
        return resolve.Combatant(
            obj.id,
            obj.props.get("name") or "Token",
            self._sheet_for_token(obj),
            self._effects(obj),
            frozenset(obj.props.get("statuses") or []),
            self._box(obj),
        )

    def disposition(self, obj: MapObject) -> str:
        """party / neutral / hostile: set on the token, else player tokens are the party."""
        set_ = obj.props.get("disposition")
        if set_ in ("party", "neutral", "hostile"):
            return set_
        return "party" if obj.props.get("controlled_by") or self._linked_pc(obj) else "hostile"

    def _active(self, obj: MapObject) -> bool:
        return obj.kind == "token" and not (set(obj.props.get("statuses") or []) & INCAPACITATED)

    def _allies_and_threats(self, actor: MapObject) -> tuple[list[geometry.Box], bool]:
        """Boxes of the actor's allies on its page that can flank, and whether a hostile
        creature that can act is next to it."""
        mine = self.disposition(actor)
        cell = self._cell(actor)
        allies: list[geometry.Box] = []
        threatened = False
        for o in self.objects.values():
            if o.id == actor.id or o.page_id != actor.page_id or not self._active(o):
                continue
            if o.layer == "gm" and actor.layer != "gm":
                continue
            other = self.disposition(o)
            if other == mine:
                allies.append(self._box(o))
            elif (
                "neutral" not in (mine, other)
                and geometry.gap(self._box(o), self._box(actor), cell) == 0
            ):
                threatened = True
        return allies, threatened

    # --- combat.act ------------------------------------------------------------

    def _acting_token(self, player: Player, token_id: str) -> tuple[MapObject, Sheet]:
        actor = self._get_object(token_id)
        if actor.kind != "token" or not permissions.controls(player, actor):
            raise GameError("act with a token you control")
        sheet = self._sheet_for_token(actor)
        if sheet is None:
            raise GameError("this token has no 5e sheet: link it to a character")
        return actor, sheet

    def _targets(self, player: Player, msg: p.CombatAct) -> list[tuple[MapObject, int]]:
        out = []
        for t in msg.targets:
            obj = self.objects.get(t.id)
            if obj is None or obj.kind != "token" or not self._can_see(player, obj):
                raise GameError("target not found")
            out.append((obj, t.cover))
        return out

    @captured("combat.act", "attack", undoable=True)
    async def on_combat_act(self, conn: Connection, msg: p.CombatAct) -> None:
        player = conn.player
        assert player is not None
        actor, sheet = self._acting_token(player, msg.actor_id)
        if msg.hidden and not player.is_gm:
            raise GameError("only the GM can act in secret")
        if msg.action.kind == "attack":
            attack = next((a for a in sheet.attacks if a.id == msg.action.id), None)
            if attack is None:
                raise GameError("this attack is not on the sheet")
            await self._act_attack(player, actor, sheet, attack, msg)
        else:
            raise GameError(f"{msg.action.kind} actions are not supported yet")

    async def _act_attack(
        self, player: Player, actor: MapObject, sheet: Sheet, attack: Attack, msg: p.CombatAct
    ) -> None:
        assert self.capture is not None
        name = actor.props.get("name") or "Token"
        self.capture.summary = f"{name}: {attack.name}"
        targets = self._targets(player, msg)
        allies, threatened = self._allies_and_threats(actor)
        inline: list[dict[str, Any]] = []

        def roll(formula: str) -> dict[str, Any]:
            result = _roll(formula)
            inline.append(result)
            return result

        rows: list[dict[str, Any]] = []
        reasons: list[str] = []
        warnings: list[str] = []
        self.capture.fold = []
        apply_now = True  # auto_apply "confirm" / "manual" come with the GM controls step
        for target, cover in targets or [(None, 0)]:
            if target is None:
                # No target: the roll and the damage, to apply by hand.
                rows.append(self._untargeted_row(sheet, attack, roll))
                continue
            ctx = resolve.Context(
                roll,
                self._cell(actor),
                msg.mode,
                cover,
                self.option_or("crit_rule", "double"),
                self.option_or("flanking", "off"),
                allies,
                threatened,
            )
            result = resolve.attack(self._combatant(actor), attack, self._combatant(target), ctx)
            reasons += [r for r in result.reasons if r not in reasons]
            warnings += [w for w in result.warnings if w not in warnings]
            row = self._attack_row(target, result, inline)
            if result.damage and result.outcome != "rolled" and apply_now:
                await self._hurt(
                    target, row, [(d.total, d.type) for d in result.damage], False, result.critical
                )
            rows.append(row)
        await self._spend(actor, "reaction" if msg.reaction else attack.cost, sheet)
        card = self._new_card(player, actor, "attack", attack.name, rows, msg.hidden)
        card["reasons"], card["warnings"] = reasons, warnings
        card["notes"] = self.capture.fold
        self.capture.fold = None
        if attack.notes:
            card["text"] = attack.notes
        await self._post_card(player, name, card, inline, msg.hidden)

    def option_or(self, key: str, default: Any) -> Any:
        """An option that may still be in the planned list (then its default)."""
        try:
            return self.option(key)
        except KeyError:
            return default

    # --- Applying ----------------------------------------------------------------

    async def _hurt(
        self,
        target: MapObject,
        row: dict[str, Any],
        parts: list[tuple[int, str]],
        half: bool,
        critical: bool,
    ) -> None:
        """Damage parts to a target, with its defenses, concentration and death; fills the
        card row."""
        health, defenses = self._health(target)
        out = damage5e.apply_parts(health, parts, defenses, half, critical)
        name = target.props.get("name") or "Token"
        await self._write_health(target, out, f'damage to "{name}"')
        row["taken"] = (row.get("taken") or 0) + out.taken
        row["notes"] = [
            *row.get("notes", []),
            *(n for n in out.notes if n not in row.get("notes", [])),
        ]
        row["added"] = sorted(set(row.get("added", [])) | out.added)
        self._row_health(target, row)
        was = bool(target.props.get("concentrating"))
        await self._concentration_save(self.objects[target.id], out.taken)
        if was:
            row["conc"] = "kept" if self.objects[target.id].props.get("concentrating") else "lost"

    def _row_health(self, target: MapObject, row: dict[str, Any]) -> None:
        health, _ = self._health(self.objects[target.id])
        row["hp"] = {"current": health.current, "max": health.max, "temp": health.temp}
        row["state"] = damage5e.bloodied_state(health.current, health.max)

    async def _spend(self, actor: MapObject, cost: str, sheet: Sheet) -> None:
        """Mark the action, bonus action or reaction of the actor as used, if it is in the
        tracker during combat. The first attack of the Attack action spends the action, the
        others (Extra Attack) are free; spending twice is recorded, never refused."""
        assert self.game is not None
        if cost == "legendary" or self.game.settings.get("round", 0) < 1:
            return
        order = [dict(e) for e in self.game.turn_order]
        entry = next((e for e in order if e.get("object_id") == actor.id), None)
        if entry is None:
            return
        used = dict(entry.get("used") or {})
        if cost == "action":
            attacks = int(entry.get("attacks") or 0) + 1
            entry["attacks"] = attacks
            if attacks > 1 and attacks <= sheet.extra_attack and used.get("action"):
                pass
            elif used.get("action"):
                used["action_extra"] = int(used.get("action_extra") or 0) + 1
            used["action"] = True
        else:
            key = "bonus_action" if cost == "bonus" else cost
            if used.get(key):
                used[f"{key}_extra"] = int(used.get(f"{key}_extra") or 0) + 1
            used[key] = True
        entry["used"] = used
        await self._save_turns("turn.use", "", order)

    # --- Cards -------------------------------------------------------------------

    def _attack_row(
        self, target: MapObject, result: resolve.AttackResult, inline: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "token_id": target.id,
            "name": target.props.get("name") or "Token",
            "monster": self._is_monster(target),
            "outcome": result.outcome,
            "d20": _index(inline, result.roll),
            "total": result.total,
            "natural": result.natural,
            "ac": result.ac,
            "damage": [
                {
                    "roll": _index(inline, d.roll),
                    "formula": d.formula,
                    "type": d.type,
                    "total": d.total,
                }
                for d in result.damage
            ],
            "distance": result.distance_ft,
        }

    def _untargeted_row(self, sheet: Sheet, attack: Attack, roll: resolve.Roller) -> dict[str, Any]:
        test = rolls5e.d20_test("attack")
        bonus = sheet5e.attack_bonus(sheet, attack) + rolls5e.exhaustion_penalty(sheet.exhaustion)
        d20 = roll(test.formula(bonus))
        natural = rolls5e.natural(d20)
        crit = natural is not None and natural >= sheet.crit_range
        damage = resolve.roll_parts(
            sheet5e.damage_parts(sheet, attack), crit, self.option_or("crit_rule", "double"), roll
        )
        return {
            "token_id": None,
            "name": "",
            "monster": False,
            "outcome": "critical hit" if crit else "critical miss" if natural == 1 else "rolled",
            "d20": None,
            "total": int(d20["total"]),
            "natural": natural,
            "damage": [{"formula": d.formula, "type": d.type, "total": d.total} for d in damage],
        }

    def _new_card(
        self,
        player: Player,
        actor: MapObject,
        kind: str,
        action: str,
        rows: list[dict[str, Any]],
        hidden: bool,
    ) -> dict[str, Any]:
        assert self.game is not None
        order = self.game.turn_order
        round_ = self.game.settings.get("round", 0)
        return {
            "v": 1,
            "kind": kind,
            "author_id": player.id,
            "actor_id": actor.id,
            "actor_name": actor.props.get("name") or "Token",
            "actor_monster": self._is_monster(actor),
            "action": action,
            "hidden": hidden,
            "seqs": [],
            "undone_seqs": [],
            "turn": {"round": round_, "entry": order[0]["id"]} if round_ and order else None,
            "rows": rows,
        }

    async def _post_card(
        self,
        player: Player,
        speaker: str,
        card: dict[str, Any],
        inline: list[dict[str, Any]],
        hidden: bool,
    ) -> None:
        # Index of every roll in `inline`, for the rows that point at them.
        await self._post_chat(
            player, speaker, "", {"main": None, "inline": inline, "card": card}, gm_only=hidden
        )

    async def _load_card(self, card_id: int) -> ChatMessage:
        async with session_scope() as s:
            row = await s.get(ChatMessage, card_id)
        if row is None or row.game_id != self.game_id or not (row.roll or {}).get("card"):
            raise GameError("card not found")
        return row

    async def _save_card(self, row: ChatMessage, roll: dict[str, Any]) -> None:
        """Change a card and send it again to everyone who sees it (`chat.update`)."""
        async with session_scope() as s:
            await s.execute(
                update(ChatMessage)
                .where(ChatMessage.id == row.id)
                .values(roll=roll, updated_seq=self.seq)
            )
        row.roll = roll
        self._send_chat(row, "chat.update")

    def _may_change_card(self, player: Player, card: dict[str, Any]) -> bool:
        """The GM always; the author while the turn of the card is still going on."""
        if player.is_gm:
            return True
        if card.get("author_id") != player.id:
            return False
        turn = card.get("turn")
        if not turn or self.game is None:
            return True
        order = self.game.turn_order
        return (
            self.game.settings.get("round", 0) == turn["round"]
            and bool(order)
            and order[0]["id"] == turn["entry"]
        )

    async def _mark_cards(self, data: dict[str, Any], seq: int, undone_by: str | None) -> None:
        """An action event was undone (or redone): its cards show it."""
        for card_id in data.get("card_ids", []):
            try:
                row = await self._load_card(card_id)
            except GameError:
                continue
            roll = dict(row.roll or {})
            card = dict(roll["card"])
            undone = [s for s in card.get("undone_seqs", []) if s != seq]
            if undone_by is not None:
                undone.append(seq)
            card["undone_seqs"] = undone
            seqs = card.get("seqs", [])
            card["undone_by"] = undone_by if seqs and seqs[0] in undone else None
            roll["card"] = card
            await self._save_card(row, roll)

    async def on_combat_redo(self, conn: Connection, msg: p.CombatRedo) -> None:
        player = conn.player
        assert player is not None
        row = await self._load_card(msg.card_id)
        card = row.roll["card"]
        if not self._may_change_card(player, card):
            raise GameError("only the GM or the author can redo this action")
        seqs = [s for s in card.get("seqs", []) if s in card.get("undone_seqs", [])]
        if not seqs:
            raise GameError("nothing to redo")
        await self._replay(seqs, "before", f"redid: {card['action']}", None)

    async def _replay(self, seqs: list[int], frm: str, summary: str, undone_by: str | None) -> None:
        """Undo (frm="after", newest first) or redo (frm="before", oldest first) events of
        actions as one new event."""
        async with session_scope() as s:
            events = list(
                await s.scalars(
                    select(Event).where(Event.game_id == self.game_id, Event.seq.in_(seqs))
                )
            )
        events.sort(key=lambda e: e.seq, reverse=frm == "after")
        steps = [e for e in events if "action" in e.data]
        if not steps:
            raise GameError("this action cannot be undone")
        async with self._action("combat.undo" if frm == "after" else "combat.redo", summary):
            for e in steps:
                await self._merge_action(e.data["action"], frm)
        new_seq = self.seq
        for e in steps:
            await self._mark_reverted(e.seq, new_seq if frm == "after" else None)
            await self._mark_cards(e.data["action"], e.seq, undone_by)
        for stacks in (self.undo, self.redo):
            for pid, st in stacks.items():
                if any(step["seq"] in seqs for step in st):
                    st[:] = [step for step in st if step["seq"] not in seqs]
                    self._send_undo_state(pid)

    async def _undo_card(self, player: Player, card_id: int) -> None:
        row = await self._load_card(card_id)
        card = row.roll["card"]
        if not self._may_change_card(player, card):
            raise GameError("only the GM, or the author during that turn, can undo this action")
        seqs = [s for s in card.get("seqs", []) if s not in card.get("undone_seqs", [])]
        if not seqs:
            raise GameError("this action was already undone")
        await self._replay(seqs, "after", f"undid: {card['action']}", player.name)

    # --- Extra damage ------------------------------------------------------------

    async def on_combat_add_damage(self, conn: Connection, msg: p.CombatAddDamage) -> None:
        player = conn.player
        assert player is not None
        row = await self._load_card(msg.card_id)
        roll = dict(row.roll or {})
        card = dict(roll["card"])
        if not self._may_change_card(player, card):
            raise GameError("only the GM or the author can add damage to this card")
        rows = [dict(r) for r in card["rows"]]
        target_row = next((r for r in rows if r.get("token_id") == msg.target_id), None)
        target = self.objects.get(msg.target_id)
        if target_row is None or target is None:
            raise GameError("this target is not on the card")
        if target_row.get("outcome") not in ("hit", "critical hit"):
            raise GameError("extra damage goes on a hit")
        crit = target_row["outcome"] == "critical hit"
        rule = self.option_or("crit_rule", "double")
        formula = rolls5e.critical(msg.formula, rule) if crit else msg.formula
        result = _roll(formula)
        inline = [*(roll.get("inline") or []), result]
        damage_type = (msg.damage_type or "").lower()
        summary = f"{card['actor_name']}: +{formula} on {target_row['name']}"
        async with self._action("combat.add_damage", summary, undoable=True) as cap:
            cap.card_ids.append(row.id)
            cap.fold = []
            await self._hurt(target, target_row, [(int(result["total"]), damage_type)], False, crit)
            notes, cap.fold = cap.fold, None
            seq = self.seq + 1
        target_row["damage"] = [
            *target_row.get("damage", []),
            {
                "roll": len(inline) - 1,
                "formula": formula,
                "type": damage_type,
                "total": int(result["total"]),
                "extra": True,
                "seq": seq,
            },
        ]
        card["notes"] = [*card.get("notes", []), *notes]
        card["rows"] = rows
        if self.seq == seq:
            card["seqs"] = [*card.get("seqs", []), seq]
        roll["inline"], roll["card"] = inline, card
        await self._save_card(row, roll)


def _index(inline: list[dict[str, Any]], roll: dict[str, Any]) -> int | None:
    for i, r in enumerate(inline):
        if r is roll:
            return i
    return None
