"""GameServer handlers: combat, effects, conditions, concentration, spells, turn order."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import update

from app.dice import roll as dice_roll
from app.game import chat, permissions
from app.game import protocol as p
from app.game.server.base import (
    Connection,
    GameError,
    ServerBase,
    _apply_buttons,
    _round_head,
    _turn_value,
)
from app.models import (
    Game,
    MapObject,
    Player,
)
from app.rules5e import damage as damage5e
from app.rules5e import effects as effects5e
from app.rules5e import rolls as rolls5e
from app.rules5e import sheet as sheet5e
from app.rules5e.data import ABILITY_NAMES
from app.rules5e.sheet import Sheet


class CombatMixin(ServerBase):
    # --- Combat: initiative, turns, action economy, movement -------------------

    def _turn_key(self, entry: dict[str, Any]) -> tuple[float, int]:
        """Sort key: initiative, then Dexterity score for ties (the GM can reorder by hand)."""
        obj = self.objects.get(entry.get("object_id") or "")
        sheet = self._sheet_for_token(obj)
        return _turn_value(entry["value"]), sheet.abilities.dex if sheet else 0

    async def on_combat_initiative(self, conn: Connection, msg: p.CombatInitiative) -> None:
        """GM: roll initiative for the given tokens, add them to the tracker and sort it."""
        player = self._require_gm(conn)
        assert self.game is not None
        tokens = [
            o for o in (self.objects.get(i) for i in msg.token_ids) if o and o.kind == "token"
        ]
        if not tokens:
            raise GameError("select some tokens first")
        # Monsters of the same kind can share one roll.
        groups: dict[str, list[MapObject]] = {}
        for t in tokens:
            same = t.props.get("represents") if msg.group and self._is_monster(t) else None
            groups.setdefault(same or t.id, []).append(t)
        rolls: list[dict[str, Any]] = []
        rows: list[list[str]] = []
        order = [dict(e) for e in self.game.turn_order]
        for members in groups.values():
            first = members[0]
            sheet = self._sheet_for_token(first)
            conditions = frozenset(first.props.get("statuses") or [])
            test = rolls5e.d20_test("initiative", "normal", None, conditions)
            bonus = sheet5e.initiative(sheet) if sheet else 0
            result = chat.roll_to_dict(dice_roll(test.formula(bonus)))
            rolls.append(result)
            names = ", ".join(t.props.get("name") or "Token" for t in members)
            rows.append([names, f"[[#{len(rolls) - 1}]]"])
            for t in members:
                entry = next((e for e in order if e.get("object_id") == t.id), None)
                if entry is None:
                    entry = {
                        "id": str(uuid.uuid4()),
                        "object_id": t.id,
                        "name": t.props.get("name") or "Token",
                    }
                    order.append(entry)
                entry["value"] = str(int(result["total"]))
        order.sort(key=self._turn_key, reverse=True)
        first_round = self.game.settings.get("round", 0) == 0
        if first_round and order:
            order[0] = {**order[0], "used": {}, "moved": 0}
        await self._save_turns(
            msg.type, "rolled initiative", order, max(1, self.game.settings.get("round", 0))
        )
        template = {"name": "default", "title": "Initiative", "fields": rows}
        await self._post_chat(
            player,
            player.name,
            "",
            {"main": None, "inline": rolls, "template": template},
            gm_only=True,
        )
        if first_round and order:
            await self._on_turn_start(order[0])

    async def _on_turn_start(self, entry: dict[str, Any]) -> None:
        """Start of a combatant's turn: effects timed on it end; a dying character rolls a
        death save."""
        await self._tick_effects(entry, "start")
        obj = self.objects.get(entry.get("object_id") or "")
        pc = self._linked_pc(obj) if obj else None
        if pc is None or pc.sheet is None:
            return
        hp, saves = pc.sheet["hp"], pc.sheet["death_saves"]
        dead = "dead" in (obj.props.get("statuses") or []) if obj else False
        if hp["current"] == 0 and not dead and saves["successes"] < 3:
            fields = [["Death save", f"[Roll death save](!deathsave {pc.id})"]]
            template = {"name": "default", "title": f"{pc.name} is dying", "fields": fields}
            owner = self.players.get(pc.player_id or "") or next(iter(self.players.values()))
            await self._post_chat(
                owner, pc.name, "", {"main": None, "inline": [], "template": template}
            )

    async def _on_turn_end(self, entry: dict[str, Any]) -> None:
        """End of a combatant's turn: effects timed on it end, repeated saves."""
        await self._tick_effects(entry, "end")

    async def on_turn_use(self, conn: Connection, msg: p.TurnUse) -> None:
        """Mark the action, bonus action or reaction of a combatant as used or available."""
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        entry = dict(self.game.turn_order[i])
        if not self._controls_entry(player, entry):
            raise GameError("you do not control this entry")
        entry["used"] = {**(entry.get("used") or {}), msg.what: msg.used}
        order = list(self.game.turn_order)
        order[i] = entry
        word = "used" if msg.used else "got back"
        await self._save_turns(
            msg.type, f"{entry['name']} {word} the {msg.what.replace('_', ' ')}", order
        )

    async def _track_movement(
        self, changes: list[dict[str, Any]], via: dict[str, list[float]] | None = None
    ) -> None:
        """Feet moved by the combatant whose turn it is, from the token's moves on the map,
        along the waypoints of the move if it had any."""
        assert self.game is not None
        order = self.game.turn_order
        if not order or self.game.settings.get("round", 0) < 1:
            return
        current = order[0]
        for ch in changes:
            if ch["id"] != current.get("object_id"):
                continue
            before, after = ch["before"] or {}, ch["after"] or {}
            if "page_id" in after or not ({"x", "y"} & after.keys()):
                continue
            obj = self.objects.get(ch["id"])
            page = self.pages.get(obj.page_id) if obj else None
            if obj is None or page is None:
                continue
            stops = (via or {}).get(ch["id"], [])
            points = [before.get("x", obj.x), before.get("y", obj.y)]
            points += stops[: len(stops) // 2 * 2]
            points += [after.get("x", obj.x), after.get("y", obj.y)]
            # 5e grid: every square, diagonal or not, is 5 feet.
            steps = range(0, len(points) - 2, 2)
            cells = (
                sum(
                    max(abs(points[i + 2] - points[i]), abs(points[i + 3] - points[i + 1]))
                    for i in steps
                )
                / page.grid_size
            )
            feet = round(cells * 2) / 2 * 5
            if feet <= 0:
                continue
            entry = {**current, "moved": (current.get("moved") or 0) + feet}
            await self._save_turns(
                "turn.move", f"{entry['name']} moved {feet:g} ft", [entry, *order[1:]]
            )
            return

    # --- Effects, conditions, concentration -----------------------------------

    @staticmethod
    def _effects(obj: MapObject | None) -> list[effects5e.Effect]:
        return effects5e.load(obj.props.get("effects")) if obj else []

    def _roll_save(
        self, obj: MapObject, ability: str, dc: int
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """A saving throw of a token: its sheet, conditions and effects. (success, text, roll)."""
        sheet = self._sheet_for_token(obj)
        bonus = sheet5e.save_bonus(sheet, ability) if sheet else 0
        penalty = rolls5e.exhaustion_penalty(sheet.exhaustion) if sheet else 0
        adv, dis, dice, flat = effects5e.roll_changes(self._effects(obj), "save", ability)
        conditions = frozenset(obj.props.get("statuses") or [])
        test = rolls5e.d20_test("save", "normal", ability, conditions, extra_adv=adv, extra_dis=dis)
        if test.auto_fail:
            return False, test.auto_fail, None
        result = chat.roll_to_dict(dice_roll(test.formula(bonus + flat + penalty, dice)))
        total = int(result["total"])
        success = total >= dc
        mode = "" if test.mode == "normal" else f" ({test.mode})"
        return success, f"{total}{mode} {'✓ success' if success else '✗ failure'}", result

    def _with_effects(
        self, obj: MapObject, effects: list[effects5e.Effect], dropped: list[effects5e.Effect]
    ) -> dict[str, Any]:
        """Props patch: the new effects, and the statuses their conditions add or remove."""
        statuses = set(obj.props.get("statuses") or [])
        statuses -= effects5e.conditions(dropped) - effects5e.conditions(effects)
        statuses |= effects5e.conditions(effects)
        return {"effects": effects5e.dump(effects), "statuses": sorted(statuses) or None}

    async def _drop_effects(self, ended: dict[str, list[str]], summary: str) -> None:
        """Remove effects by id from tokens ({token id: [effect ids]})."""
        changes: dict[str, dict[str, Any]] = {}
        for obj_id, ids in ended.items():
            obj = self.objects.get(obj_id)
            if obj is None:
                continue
            effects = self._effects(obj)
            keep = [e for e in effects if e.id not in ids]
            gone = [e for e in effects if e.id in ids]
            if gone:
                changes[obj_id] = self._with_effects(obj, keep, gone)
        await self._set_props(changes, "effect.end", summary)

    async def _start_concentration(self, caster: MapObject, name: str) -> None:
        if caster.props.get("concentrating"):
            await self._end_concentration(caster, f"started concentrating on {name}")
        statuses = sorted(set(caster.props.get("statuses") or []) | {"concentrating"})
        await self._set_props(
            {caster.id: {"concentrating": {"name": name}, "statuses": statuses}},
            "effect.concentration",
            f'"{caster.props.get("name") or "Token"}" concentrates on {name}',
        )

    async def _end_concentration(self, caster: MapObject, why: str) -> None:
        """Concentration ends: every effect that depends on it ends too, on every token."""
        state = caster.props.get("concentrating")
        if not state:
            return
        name = caster.props.get("name") or "Token"
        ended = {
            o.id: [e.id for e in self._effects(o) if e.concentration_of == caster.id]
            for o in self.objects.values()
            if o.props.get("effects")
        }
        await self._drop_effects(
            {k: v for k, v in ended.items() if v}, f'"{name}" lost concentration'
        )
        statuses = sorted(set(caster.props.get("statuses") or []) - {"concentrating"}) or None
        await self._set_props(
            {caster.id: {"concentrating": None, "statuses": statuses}},
            "effect.concentration",
            f'"{name}" lost concentration',
        )
        await self._card(
            caster, f"{name} loses concentration", [["Spell", state["name"]], ["Why", why]]
        )

    async def _check_concentration(self, obj: MapObject) -> None:
        """Incapacitated, unconscious or dead: no more concentration."""
        if obj.props.get("concentrating"):
            breaking = set(obj.props.get("statuses") or []) & effects5e.BREAKS_CONCENTRATION
            if breaking:
                await self._end_concentration(obj, f"{sorted(breaking)[0]}")

    async def _concentration_save(self, obj: MapObject, damage: int) -> None:
        """Damage to a concentrating creature: Constitution save or the concentration ends."""
        if not obj.props.get("concentrating") or damage <= 0:
            return
        dc = effects5e.concentration_dc(damage)
        success, text, result = self._roll_save(obj, "con", dc)
        name = obj.props.get("name") or "Token"
        if success:
            fields = [["Constitution save", f"DC {dc}: {text}"]]
            await self._card(obj, f"{name} keeps concentrating", fields)
        else:
            await self._end_concentration(obj, f"failed the DC {dc} Constitution save ({text})")

    async def _card(
        self, obj: MapObject | None, title: str, fields: list[list[str]], gm_only: bool = False
    ) -> None:
        """A chat card from the game itself, spoken by the token's controller (or the GM)."""
        player = None
        if obj is not None:
            controllers = obj.props.get("controlled_by") or []
            player = next((self.players[i] for i in controllers if i in self.players), None)
        if player is None:
            player = next((p for p in self.players.values() if p.is_gm), None) or next(
                iter(self.players.values())
            )
        template = {"name": "default", "title": title, "fields": fields}
        await self._post_chat(
            player,
            "Frolls",
            "",
            {"main": None, "inline": [], "template": template},
            gm_only=gm_only,
        )

    def _may_affect(self, player: Player, source: MapObject | None) -> bool:
        """GMs, or players acting with a token they control (their character's spell)."""
        return player.is_gm or (source is not None and permissions.controls(player, source))

    async def on_effect_apply(self, conn: Connection, msg: p.EffectApply) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        source = self.objects.get(msg.source_id or "")
        if not self._may_affect(player, source):
            raise GameError("apply effects with a token you control, or as the GM")
        targets = [self._get_object(i) for i in msg.token_ids]
        if msg.preset:
            if msg.preset not in effects5e.PRESETS:
                raise GameError("unknown effect")
            base = effects5e.from_preset(
                msg.preset, source.id if source else None, msg.concentrate, msg.dc
            )
        elif msg.effect:
            base = msg.effect
        else:
            raise GameError("choose an effect")
        await self._add_effect(base, targets, source)

    async def _add_effect(
        self, base: effects5e.Effect, targets: list[MapObject], source: MapObject | None
    ) -> None:
        assert self.game is not None
        ending = base.ending
        # "Until the end of your next turn", cast during your turn: this turn's end doesn't count.
        order = self.game.turn_order
        current = (
            order[0].get("object_id") if order and self.game.settings.get("round", 0) else None
        )
        if ending and ending.when == "end" and ending.of == current:
            ending = ending.model_copy(update={"rounds": ending.rounds + 1})
        if base.concentration_of and source:
            await self._start_concentration(source, base.name)
        changes: dict[str, dict[str, Any]] = {}
        for t in targets:
            effect = base.model_copy(update={"id": str(uuid.uuid4()), "ending": ending})
            effects = [*self._effects(self.objects[t.id]), effect]
            changes[t.id] = self._with_effects(self.objects[t.id], effects, [])
        names = ", ".join(t.props.get("name") or "Token" for t in targets)
        await self._set_props(changes, "effect.apply", f"{base.name} on {names}")
        for t in targets:
            await self._check_concentration(self.objects[t.id])
        rows = [["Targets", names]]
        if base.duration:
            rows.append(["Duration", base.duration])
        if base.concentration_of:
            rows.append(["Concentration", source.props.get("name") or "Token" if source else ""])
        await self._card(source, f"{base.name}", rows)

    async def on_effect_remove(self, conn: Connection, msg: p.EffectRemove) -> None:
        player = conn.player
        assert player is not None
        obj = self._get_object(msg.token_id)
        effect = next((e for e in self._effects(obj) if e.id == msg.effect_id), None)
        if effect is None:
            raise GameError("effect not found")
        source = self.objects.get(effect.concentration_of or "")
        if not (
            player.is_gm
            or permissions.controls(player, obj)
            or (source and permissions.controls(player, source))
        ):
            raise GameError("you cannot remove this effect")
        await self._drop_effects(
            {obj.id: [effect.id]},
            f'{effect.name} removed from "{obj.props.get("name") or "Token"}"',
        )

    async def on_effect_end_concentration(self, conn: Connection, msg: p.EndConcentration) -> None:
        player = conn.player
        assert player is not None
        obj = self._get_object(msg.token_id)
        if not permissions.controls(player, obj):
            raise GameError("you do not control this token")
        await self._end_concentration(obj, "chose to stop")

    async def _tick_effects(self, entry: dict[str, Any], when: str) -> None:
        """Start or end of a combatant's turn: effects timed on it end; at the end of its own
        turn the creature repeats the saving throws that can end its effects."""
        turn_of = entry.get("object_id")
        if not turn_of:
            return
        changes: dict[str, dict[str, Any]] = {}
        notes: list[list[str]] = []
        for o in list(self.objects.values()):
            effects = self._effects(o)
            if not any(
                e.ending and e.ending.of == turn_of and e.ending.when == when for e in effects
            ):
                continue
            kept, gone = effects5e.tick(effects, turn_of, when)
            changes[o.id] = self._with_effects(o, kept, gone)
            notes += [[o.props.get("name") or "Token", f"{e.name} ends"] for e in gone]
        await self._set_props(changes, "effect.tick", "effects count down")
        if when == "end":
            obj = self.objects.get(turn_of)
            for e in self._effects(obj):
                if e.repeat_save is None or obj is None:
                    continue
                success, text, _ = self._roll_save(obj, e.repeat_save.ability, e.repeat_save.dc)
                name = obj.props.get("name") or "Token"
                save = f"{ABILITY_NAMES[e.repeat_save.ability]} DC {e.repeat_save.dc}"
                notes.append(
                    [name, f"{e.name}: {save} save {text}" + (" — it ends" if success else "")]
                )
                if success:
                    await self._drop_effects({obj.id: [e.id]}, f"{e.name} ends")
        if notes:
            await self._card(self.objects.get(turn_of), "Effects", notes)

    # --- Spells ----------------------------------------------------------------

    def _spell_damage(self, sheet: Sheet, spell: Any, slot: int) -> str:
        """Damage of a spell cast with a slot: extra dice per level above the spell's, and
        cantrips growing with the character (×2 at level 5, ×3 at 11, ×4 at 17)."""
        damage = spell.damage.strip()
        if not damage:
            return ""
        if spell.level == 0 and sheet.kind == "pc":
            times = 1 + (sheet.level >= 5) + (sheet.level >= 11) + (sheet.level >= 17)
            damage = rolls5e.DICE_RE.sub(
                lambda m: f"{int(m.group(1) or 1) * times}d{m.group(2)}", damage
            )
        extra = slot - spell.level
        if spell.upcast.strip() and spell.level > 0 and extra > 0:
            damage += "".join(f"+{spell.upcast.strip()}" for _ in range(extra))
        mod = sheet5e.ability_mod(sheet, "spell") if spell.add_modifier else 0
        return f"{damage}{mod:+d}" if mod else damage

    async def on_sheet_cast(self, conn: Connection, msg: p.SheetCast) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        spell = next((s for s in sheet.spells if s.id == msg.spell_id), None)
        if spell is None:
            raise GameError("this spell is not on the sheet")
        slot = spell.level if msg.slot is None else msg.slot
        data = sheet.model_dump()
        if spell.level > 0 and not (msg.ritual and spell.ritual):
            if slot < spell.level:
                raise GameError(f"{spell.name} needs a level {spell.level} slot or higher")
            slots = data["spellcasting"]["slots"].get(str(slot))
            if not slots or slots["used"] >= slots["max"]:
                raise GameError(f"no level {slot} spell slots left")
            slots["used"] += 1
            await self._set_sheet(character, data, f"{character.name} used a level {slot} slot")
        caster = self._token_for_roll(player, msg.token_id)
        targets = [t for t in (self._token_for_roll(player, i) for i in msg.target_ids) if t]

        fields: list[list[str]] = []
        rolls: list[dict[str, Any]] = []
        level = "cantrip" if spell.level == 0 else f"level {slot}"
        damage = self._spell_damage(sheet, spell, slot)
        dc = sheet5e.spell_dc(sheet)
        # A spell with an effect starts concentrating when the effect lands (_add_effect).
        if spell.concentration and caster and not spell.effect:
            await self._start_concentration(caster, spell.name)
        if spell.attack and targets:
            # One spell attack roll per target, against its AC.
            for t in targets:
                target_sheet = self._sheet_for_token(t)
                conditions = (
                    frozenset(caster.props.get("statuses") or []) if caster else frozenset()
                )
                t_conditions = frozenset(t.props.get("statuses") or [])
                adv, dis, dice, flat = effects5e.roll_changes(self._effects(caster), "attack", None)
                t_adv, t_dis = effects5e.attacked_with(self._effects(t))
                near = self._within_5ft(caster, t) if caster else True
                test = rolls5e.d20_test(
                    "attack",
                    "normal",
                    None,
                    conditions,
                    t_conditions,
                    near,
                    adv + t_adv,
                    dis + t_dis,
                )
                bonus = (sheet5e.spell_attack(sheet) or 0) + flat
                result = chat.roll_to_dict(dice_roll(test.formula(bonus, dice)))
                rolls.append(result)
                ac = (
                    target_sheet.ac + effects5e.ac_bonus(self._effects(t)) if target_sheet else None
                )
                outcome = rolls5e.attack_outcome(
                    rolls5e.natural(result), int(result["total"]), ac, False
                )
                name = t.props.get("name") or "Token"
                vs = f" vs AC {ac}" if ac is not None else ""
                fields.append([f"{name}{vs}", f"[[#{len(rolls) - 1}]] {outcome}".strip()])
                if damage and outcome in ("hit", "critical hit"):
                    formula = rolls5e.critical(damage) if outcome == "critical hit" else damage
                    dmg = chat.roll_to_dict(dice_roll(formula))
                    rolls.append(dmg)
                    total = int(dmg["total"])
                    kind = spell.damage_type or "-"
                    fields.append(
                        [
                            f"{spell.damage_type or 'Damage'}",
                            f"[[#{len(rolls) - 1}]] [Apply](!apply damage {total} {kind} {t.id})",
                        ]
                    )
        elif spell.save:
            save = ABILITY_NAMES[spell.save]
            fields.append(["Save", f"DC {dc} {save}" if dc else save])
            if targets:
                ids = ",".join(t.id for t in targets)
                args = f"{character.id} {spell.id} {slot} {caster.id if caster else '-'} {ids}"
                fields.append(["Targets", f"[Roll saves and apply](!saves {args})"])
        elif damage:
            dmg = chat.roll_to_dict(dice_roll(damage))
            rolls.append(dmg)
            kind = spell.heal or "damage"
            label = {"healing": "Healing", "temp": "Temporary hit points"}.get(
                spell.heal, spell.damage_type.capitalize() or "Damage"
            )
            fields.append([label, f"[[#{len(rolls) - 1}]]"])
            target = targets[0].id if len(targets) == 1 else None
            fields.append(
                ["Apply", _apply_buttons(int(dmg["total"]), spell.damage_type, target, kind)]
            )
        if spell.effect and not spell.save and targets:
            preset = effects5e.from_preset(
                spell.effect, caster.id if caster else None, spell.concentration, dc
            )
            await self._add_effect(preset, targets, caster)
        if spell.duration:
            fields.append(
                ["Duration", spell.duration + (" (concentration)" if spell.concentration else "")]
            )
        if spell.description:
            fields.append(["Description", spell.description])
        template = {
            "name": "default",
            "title": f"{character.name} casts {spell.name} ({level})",
            "fields": fields,
        }
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )

    async def on_spell_saves(self, conn: Connection, msg: p.SpellSaves) -> None:
        """Every target rolls its saving throw; damage (half on a success) and the spell's
        effect (on a failure) are applied."""
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        spell = next((s for s in sheet.spells if s.id == msg.spell_id), None)
        if spell is None or spell.save is None:
            raise GameError("this spell has no saving throw")
        caster = self.objects.get(msg.token_id or "")
        dc = sheet5e.spell_dc(sheet) or 10
        damage = self._spell_damage(sheet, spell, msg.slot)
        rolls: list[dict[str, Any]] = []
        total = 0
        if damage:
            dmg = chat.roll_to_dict(dice_roll(damage))
            rolls.append(dmg)
            total = int(dmg["total"])
        fields: list[list[str]] = (
            [["Damage", f"[[#0]] {spell.damage_type}".strip()]] if damage else []
        )
        failed: list[MapObject] = []
        for t in (self.objects.get(i) for i in msg.target_ids):
            if t is None or t.kind != "token":
                continue
            success, text, _ = self._roll_save(t, spell.save, dc)
            name = t.props.get("name") or "Token"
            line = f"{ABILITY_NAMES[spell.save]} DC {dc}: {text}"
            if not success:
                failed.append(t)
            if damage and (not success or spell.half_on_save):
                health, defenses = self._health(t)
                out = damage5e.apply(health, "damage", total, spell.damage_type, defenses, success)
                await self._write_health(t, out, f'{spell.name} on "{name}"')
                await self._concentration_save(t, out.taken)
                line += f" → {out.taken} damage"
                if self._shows_hp(t):
                    line += f" ({out.health.current}/{out.health.max} HP)"
            fields.append([name, line])
        if spell.effect and failed:
            preset = effects5e.from_preset(
                spell.effect, caster.id if caster else None, spell.concentration, dc
            )
            await self._add_effect(preset, failed, caster)
        template = {"name": "default", "title": f"{spell.name}: saving throws", "fields": fields}
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )

    # --- Turn order ----------------------------------------------------------

    async def _save_turns(
        self, kind: str, summary: str, order: list[dict[str, Any]], round_: int | None = None
    ) -> None:
        assert self.game is not None
        game_settings = self.game.settings
        if round_ is not None:
            game_settings = {**game_settings, "round": round_}
        async with self._commit(kind, summary) as s:
            await s.execute(
                update(Game)
                .where(Game.id == self.game.id)
                .values(turn_order=order, settings=game_settings)
            )
        self.game.turn_order, self.game.settings = order, game_settings
        self._broadcast_game()

    def _controls_entry(self, player: Player, entry: dict[str, Any]) -> bool:
        if player.is_gm:
            return True
        obj = self.objects.get(entry.get("object_id") or "")
        return obj is not None and permissions.controls(player, obj)

    def _find_entry(self, entry_id: str) -> int:
        assert self.game is not None
        for i, e in enumerate(self.game.turn_order):
            if e["id"] == entry_id:
                return i
        raise GameError("entry not found in the turn tracker")

    async def on_turn_set(self, conn: Connection, msg: p.TurnSet) -> None:
        self._require_gm(conn)
        await self._save_turns(
            msg.type, "rearranged the turn tracker", [e.model_dump() for e in msg.order], msg.round
        )

    async def on_turn_add(self, conn: Connection, msg: p.TurnAdd) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        entry = msg.entry.model_dump()
        if not player.is_gm:
            if not entry["object_id"] or not self._controls_entry(player, entry):
                raise GameError("you can only add tokens you control")
        if entry["object_id"] and not entry["name"]:
            obj = self.objects.get(entry["object_id"])
            entry["name"] = (obj.props.get("name") if obj else None) or "Token"
        order = [e for e in self.game.turn_order if e["id"] != entry["id"]]
        if entry["object_id"]:
            order = [e for e in order if e.get("object_id") != entry["object_id"]]
        await self._save_turns(
            msg.type, f'added "{entry["name"]}" to the turn tracker', [*order, entry]
        )

    async def on_turn_update(self, conn: Connection, msg: p.TurnUpdate) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        entry = dict(self.game.turn_order[i])
        if not self._controls_entry(player, entry):
            raise GameError("you do not control this entry")
        if msg.value is not None:
            entry["value"] = msg.value
        if msg.name is not None:
            entry["name"] = msg.name
        order = list(self.game.turn_order)
        order[i] = entry
        await self._save_turns(msg.type, f'changed turn of "{entry["name"]}"', order)

    async def on_turn_remove(self, conn: Connection, msg: p.TurnRemove) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        i = self._find_entry(msg.id)
        if not self._controls_entry(player, self.game.turn_order[i]):
            raise GameError("you do not control this entry")
        name = self.game.turn_order[i]["name"]
        await self._save_turns(
            msg.type,
            f'removed "{name}" from the turn tracker',
            [e for e in self.game.turn_order if e["id"] != msg.id],
        )

    async def on_turn_next(self, conn: Connection, msg: p.TurnNext) -> None:
        player = conn.player
        assert player is not None and self.game is not None
        order = self.game.turn_order
        if not order:
            return
        if not self._controls_entry(player, order[0]):
            raise GameError("it is not your turn")
        rotated = [*order[1:], order[0]]
        rotated[0] = {**rotated[0], "used": {}, "moved": 0}
        round_ = self.game.settings.get("round", 0)
        # A new round starts when the first entry of the sorted order comes back on top.
        if rotated[0]["id"] == _round_head(order):
            round_ += 1
        await self._save_turns(msg.type, f'ended the turn of "{order[0]["name"]}"', rotated, round_)
        await self._on_turn_end(order[0])
        await self._on_turn_start(rotated[0])

    async def on_turn_sort(self, conn: Connection, msg: p.TurnSort) -> None:
        self._require_gm(conn)
        assert self.game is not None
        order = sorted(self.game.turn_order, key=self._turn_key, reverse=msg.descending)
        await self._save_turns(msg.type, "sorted the turn tracker", order, 1 if order else 0)

    async def _prune_turn_order(self, object_ids: set[str]) -> None:
        assert self.game is not None
        order = [e for e in self.game.turn_order if e.get("object_id") not in object_ids]
        if len(order) != len(self.game.turn_order):
            await self._save_turns(
                "turn.prune", "removed deleted tokens from the turn tracker", order
            )
