"""GameServer handlers: 5e sheet rolls, hit points."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import update

from app.dice import DiceError
from app.dice import roll as dice_roll
from app.game import chat, permissions
from app.game import protocol as p
from app.game.server.base import (
    SKILL_LABELS,
    Connection,
    GameError,
    ServerBase,
    _apply_buttons,
    _copy,
    _mode_label,
)
from app.models import (
    Character,
    MapObject,
    Player,
)
from app.rules5e import damage as damage5e
from app.rules5e import effects as effects5e
from app.rules5e import rolls as rolls5e
from app.rules5e import sheet as sheet5e
from app.rules5e.data import ABILITIES, ABILITY_NAMES, SIZES, SKILLS
from app.rules5e.sheet import Sheet


class SheetsMixin(ServerBase):
    # --- 5e sheet rolls -------------------------------------------------------

    def _sheet_of(self, player: Player, character_id: str) -> tuple[Character, Sheet]:
        """Character and its 5e sheet, if `player` may roll for it (GM, or who plays it)."""
        character = self._get_character(character_id)
        if not player.is_gm and character.player_id != player.id:
            raise GameError("you can only roll for your own character")
        if character.sheet is None:
            raise GameError(f"{character.name} has no 5e sheet")
        return character, Sheet.model_validate(character.sheet)

    def _token_for_roll(self, player: Player, token_id: str | None) -> MapObject | None:
        obj = self.objects.get(token_id or "")
        if obj is None or obj.kind != "token" or not self._can_see(player, obj):
            return None
        return obj

    def _sheet_for_token(self, obj: MapObject | None) -> Sheet | None:
        character = self.characters.get(obj.props.get("represents") or "") if obj else None
        return Sheet.model_validate(character.sheet) if character and character.sheet else None

    def _within_5ft(self, a: MapObject, b: MapObject) -> bool:
        """Adjacent footprints (or overlapping): the gap between the two tokens is under a cell."""
        page = self.pages.get(a.page_id)
        cell = page.grid_size if page else 70
        gap_x = abs(a.x - b.x) - (a.width + b.width) / 2
        gap_y = abs(a.y - b.y) - (a.height + b.height) / 2
        return max(gap_x, gap_y) < cell / 2

    async def on_sheet_roll(self, conn: Connection, msg: p.SheetRoll) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        actor = self._token_for_roll(player, msg.token_id)
        target = self._token_for_roll(player, msg.target_id)
        actor_conditions = frozenset(actor.props.get("statuses") or []) if actor else frozenset()
        target_conditions = frozenset(target.props.get("statuses") or []) if target else frozenset()
        penalty = rolls5e.exhaustion_penalty(sheet.exhaustion)

        rolls: list[dict[str, Any]] = []

        def inline(formula: str) -> tuple[str, dict[str, Any]]:
            try:
                result = chat.roll_to_dict(dice_roll(formula))
            except DiceError as e:
                raise GameError(f"invalid formula {formula}: {e}") from e
            rolls.append(result)
            return f"[[#{len(rolls) - 1}]]", result

        fields: list[list[str]] = []
        key = msg.key or ""
        label: str

        if msg.roll == "death_save":
            label = "Death save"
            fields = await self._death_save(player, character, sheet)
        elif msg.roll in ("check", "save", "skill", "initiative"):
            if msg.roll == "skill":
                if key not in SKILLS:
                    raise GameError("unknown skill")
                label, bonus, ability = SKILL_LABELS[key], sheet5e.skill_bonus(sheet, key), None
                kind: rolls5e.TestKind = "check"
            elif msg.roll == "initiative":
                label, bonus, ability, kind = (
                    "Initiative",
                    sheet5e.initiative(sheet),
                    None,
                    "initiative",
                )
            else:
                if key not in ABILITIES:
                    raise GameError("unknown ability")
                ability = key
                if msg.roll == "save":
                    label = f"{ABILITY_NAMES[key]} save"
                    bonus, kind = sheet5e.save_bonus(sheet, key), "save"
                else:
                    label = f"{ABILITY_NAMES[key]} check"
                    bonus, kind = sheet5e.ability_mod(sheet, key), "check"
            effect_kind = "save" if kind == "save" else "check"
            adv, dis, dice, flat = effects5e.roll_changes(
                self._effects(actor),
                effect_kind,
                ability or ("dex" if kind == "initiative" else None),
            )
            test = rolls5e.d20_test(
                kind, msg.mode, ability, actor_conditions, extra_adv=adv, extra_dis=dis
            )
            if test.auto_fail:
                fields.append(["Result", test.auto_fail])
            else:
                marker, result = inline(test.formula(bonus + penalty + flat, dice))
                fields.append([_mode_label(test.mode), marker])
                nat = rolls5e.natural(result)
                if nat in (1, 20):
                    fields.append(["Natural", str(nat)])
                if msg.roll == "initiative" and actor:
                    await self._set_initiative(actor, int(result["total"]))
            if test.reasons:
                fields.append(["Why", "; ".join(test.reasons)])
            if penalty:
                fields.append(["Exhaustion", str(penalty)])
        else:
            attack = next((a for a in sheet.attacks if a.id == key), None)
            if attack is None:
                raise GameError("this attack is not on the sheet")
            target_sheet = self._sheet_for_token(target)
            target_name = (target.props.get("name") or "the target") if target else None
            damage = sheet5e.damage_formula(sheet, attack)
            if msg.roll == "attack" and attack.kind == "attack":
                label = attack.name
                near = self._within_5ft(actor, target) if actor and target else True
                adv, dis, dice, flat = effects5e.roll_changes(self._effects(actor), "attack", None)
                t_adv, t_dis = effects5e.attacked_with(self._effects(target))
                test = rolls5e.d20_test(
                    "attack",
                    msg.mode,
                    None,
                    actor_conditions,
                    target_conditions,
                    near,
                    adv + t_adv,
                    dis + t_dis,
                )
                bonus = sheet5e.attack_bonus(sheet, attack) + penalty + flat
                marker, result = inline(test.formula(bonus, dice))
                fields.append([f"Attack {_mode_label(test.mode).lower()}", marker])
                ac = (
                    target_sheet.ac + effects5e.ac_bonus(self._effects(target))
                    if target_sheet
                    else None
                )
                auto_crit = near and bool(target_conditions & set(rolls5e.AUTO_CRIT))
                outcome = rolls5e.attack_outcome(
                    rolls5e.natural(result), int(result["total"]), ac, auto_crit
                )
                if target_name:
                    vs = f" vs AC {ac}" if ac is not None else ""
                    fields.append(["Target", f"{target_name}{vs}"])
                if outcome:
                    fields.append(["Result", outcome.capitalize()])
                if test.reasons:
                    fields.append(["Why", "; ".join(test.reasons)])
                if damage and outcome != "miss" and outcome != "critical miss":
                    crit = outcome == "critical hit"
                    fields.append(["Damage", self._damage_button(character, attack.id, crit, msg)])
            elif msg.roll == "attack":
                # An effect that forces a saving throw: the card shows the DC.
                label = attack.name
                save = ABILITY_NAMES.get(attack.save or "", "")
                fields.append(["Save", f"DC {sheet5e.save_dc(sheet, attack)} {save}".strip()])
                if damage:
                    half = " (half on a success)" if attack.half_on_save else ""
                    button = self._damage_button(character, attack.id, False, msg)
                    fields.append(["Damage", f"{button}{half}"])
            else:
                label = f"{attack.name} damage" + (" (critical)" if msg.crit else "")
                if not damage:
                    raise GameError(f"{attack.name} has no damage")
                formula = rolls5e.critical(damage) if msg.crit else damage
                marker, result = inline(formula)
                fields.append([attack.damage_type.capitalize() or "Damage", marker])
                fields.append(
                    [
                        "Apply",
                        _apply_buttons(int(result["total"]), attack.damage_type, msg.target_id),
                    ]
                )
            if attack.notes:
                fields.append(["Notes", attack.notes])

        template = {"name": "default", "title": f"{character.name}: {label}", "fields": fields}
        await self._post_chat(
            player,
            character.name,
            content="",
            roll={"main": None, "inline": rolls, "template": template},
            gm_only=msg.gm_only,
        )

    def _damage_button(
        self, character: Character, attack_id: str, crit: bool, msg: p.SheetRoll
    ) -> str:
        """Chat button that rolls this attack's damage (see `runButton` in the client)."""
        args = [
            character.id,
            attack_id,
            "1" if crit else "0",
            msg.token_id or "-",
            msg.target_id or "-",
        ]
        return f"[{'Roll critical damage' if crit else 'Roll damage'}](!damage {' '.join(args)})"

    def _hp_from_sheet(self, obj: MapObject) -> None:
        """A new token of a sheet character: the PC's own hit points, or a monster's maximum."""
        character = self._represented(obj) if obj.kind == "token" else None
        if character is None or character.sheet is None:
            return
        hp = character.sheet["hp"]
        if character.sheet["kind"] == "pc":
            obj.props = {**obj.props, **self._bars(hp["current"], hp["max"], hp["temp"])}
        elif "bar1" not in obj.props:
            obj.props = {**obj.props, "bar1": {"value": hp["max"], "max": hp["max"]}}

    async def _after_token_change(self, changes: list[dict[str, Any]]) -> None:
        """A newly linked token takes the sheet's hit points; editing its bars changes the sheet.

        `changes`: the {id, before, after} of an object event.
        """
        to_sheet = []
        for ch in changes:
            obj = self.objects.get(ch["id"])
            before, after = ch["before"] or {}, ch["after"] or {}
            if obj and "props" in after:
                await self._check_concentration(obj)
            pc = self._linked_pc(obj) if obj and "props" in after else None
            if obj is None or pc is None:
                continue
            old_link = (before.get("props") or {}).get("represents")
            if old_link != after["props"].get("represents"):
                await self._sync_tokens(pc)
            elif any(
                (before.get("props") or {}).get(k) != after["props"].get(k)
                for k in ("bar1", "bar2")
            ):
                to_sheet.append(obj)
        await self._tokens_to_sheets(to_sheet)

    async def _set_initiative(self, token: MapObject, value: int) -> None:
        """Put the rolled initiative in the turn tracker, adding the token if needed."""
        assert self.game is not None
        order = [dict(e) for e in self.game.turn_order]
        entry = next((e for e in order if e.get("object_id") == token.id), None)
        if entry is None:
            name = token.props.get("name") or "Token"
            order.append({"id": str(uuid.uuid4()), "object_id": token.id, "name": name})
            entry = order[-1]
        entry["value"] = str(value)
        await self._save_turns("turn.update", f'rolled initiative for "{entry["name"]}"', order)

    # --- Hit points: token <-> sheet, damage, healing, death -------------------

    @property
    def npc_hp(self) -> str:
        """What players see of monsters' hit points: hidden, status or full."""
        return self.option("npc_hp")

    def _represented(self, obj: MapObject) -> Character | None:
        character = self.characters.get(obj.props.get("represents") or "")
        return character if character and character.sheet else None

    def _linked_pc(self, obj: MapObject) -> Character | None:
        """Player character whose sheet holds this token's hit points (shared by its tokens)."""
        character = self._represented(obj)
        return (
            character if character and character.sheet and character.sheet["kind"] == "pc" else None
        )

    def _tokens_of(self, character: Character) -> list[MapObject]:
        return [
            o
            for o in self.objects.values()
            if o.kind == "token" and o.props.get("represents") == character.id
        ]

    def _health(self, obj: MapObject) -> tuple[damage5e.Health, damage5e.Defenses]:
        conditions = frozenset(obj.props.get("statuses") or [])
        character = self._represented(obj)
        sheet = character.sheet if character else None
        defenses = damage5e.Defenses()
        if sheet:
            defenses = damage5e.Defenses(
                frozenset(sheet["resistances"]),
                frozenset(sheet["immunities"]),
                frozenset(sheet["vulnerabilities"]),
            )
        pc = self._linked_pc(obj)
        if pc and pc.sheet:
            hp, saves = pc.sheet["hp"], pc.sheet["death_saves"]
            health = damage5e.Health(
                hp["current"],
                hp["max"],
                hp["temp"],
                True,
                saves["successes"],
                saves["failures"],
                conditions,
            )
        else:
            bar1, bar2 = obj.props.get("bar1") or {}, obj.props.get("bar2") or {}
            current = int(bar1.get("value") or 0)
            maximum = int(bar1.get("max") or current)
            health = damage5e.Health(
                current, maximum, int(bar2.get("value") or 0), False, 0, 0, conditions
            )
        return health, defenses

    @staticmethod
    def _bars(current: int, maximum: int, temp: int) -> dict[str, Any]:
        return {
            "bar1": {"value": current, "max": maximum},
            "bar2": {"value": temp or None, "max": None},
        }

    async def _set_props(self, changes: dict[str, dict[str, Any]], kind: str, summary: str) -> None:
        """Merge props into tokens (null removes a key), save and broadcast. Not undoable."""
        planned: list[tuple[MapObject, dict[str, Any]]] = []
        for obj_id, patch in changes.items():
            obj = self.objects.get(obj_id)
            if obj is None:
                continue
            merged = {**obj.props, **patch}
            props = {k: v for k, v in merged.items() if v is not None}
            if props != obj.props:
                planned.append((obj, props))
        if not planned:
            return
        async with self._commit(kind, summary, None, [o.id for o, _ in planned]) as s:
            for obj, props in planned:
                await s.execute(update(MapObject).where(MapObject.id == obj.id).values(props=props))
        for obj, props in planned:
            obj.props = props
        self._publish_objects([o for o, _ in planned], [], {})

    async def _set_sheet(self, character: Character, sheet: dict[str, Any], summary: str) -> None:
        if sheet == character.sheet:
            return
        async with self._commit("char.update", summary) as s:
            await s.execute(
                update(Character).where(Character.id == character.id).values(sheet=sheet)
            )
        character.sheet = sheet
        self._broadcast_character(character, character.player_id)

    async def _sync_tokens(self, character: Character) -> None:
        """A player character's hit points shown on every token that represents it."""
        if not character.sheet or character.sheet["kind"] != "pc":
            return
        hp = character.sheet["hp"]
        bars = self._bars(hp["current"], hp["max"], hp["temp"])
        await self._set_props(
            {o.id: bars for o in self._tokens_of(character)},
            "token.sync",
            f'hit points of "{character.name}"',
        )

    async def _tokens_to_sheets(self, objs: list[MapObject]) -> None:
        """Hit points typed on a linked token go to the sheet, then to its other tokens."""
        for obj in objs:
            pc = self._linked_pc(obj)
            if pc is None or pc.sheet is None:
                continue
            bar1, bar2 = obj.props.get("bar1") or {}, obj.props.get("bar2") or {}
            sheet = _copy(pc.sheet)
            hp = sheet["hp"]
            hp["max"] = max(0, min(9999, int(bar1.get("max") or hp["max"])))
            hp["current"] = max(0, min(hp["max"], int(bar1.get("value") or 0)))
            hp["temp"] = max(0, min(9999, int(bar2.get("value") or 0)))
            await self._set_sheet(pc, sheet, f'hit points of "{pc.name}"')
            await self._sync_tokens(pc)

    async def _fit_tokens(self, character: Character) -> None:
        """Tokens of a character take the space of its size (Large = 2×2 cells…)."""
        if not character.sheet:
            return
        cells = SIZES[character.sheet["size"]]
        planned = []
        for o in self._tokens_of(character):
            page = self.pages.get(o.page_id)
            side = cells * (page.grid_size if page else 70)
            if (o.width, o.height) != (side, side):
                planned.append((o, side))
        if not planned:
            return
        async with self._commit(
            "token.sync", f'size of "{character.name}"', None, [o.id for o, _ in planned]
        ) as s:
            for o, side in planned:
                await s.execute(
                    update(MapObject).where(MapObject.id == o.id).values(width=side, height=side)
                )
        for o, side in planned:
            o.width = o.height = side
        self._publish_objects([o for o, _ in planned], [], {})

    async def _write_health(self, obj: MapObject, out: damage5e.Outcome, summary: str) -> None:
        """Store the new hit points (sheet or token) and the conditions that came with them."""
        h = out.health
        pc = self._linked_pc(obj)
        targets = self._tokens_of(pc) if pc else [obj]
        changes: dict[str, dict[str, Any]] = {}
        for t in targets:
            statuses = (set(t.props.get("statuses") or []) | out.added) - out.removed
            patch: dict[str, Any] = {"statuses": sorted(statuses) or None}
            if pc is None:
                patch.update(self._bars(h.current, h.max, h.temp))
            changes[t.id] = patch
        if pc and pc.sheet:
            sheet = _copy(pc.sheet)
            sheet["hp"].update(current=h.current, max=h.max, temp=h.temp)
            sheet["death_saves"] = {"successes": h.successes, "failures": h.failures}
            await self._set_sheet(pc, sheet, summary)
            await self._sync_tokens(pc)
        await self._set_props(changes, "combat.apply", summary)
        for t in targets:
            await self._check_concentration(self.objects[t.id])

    def _is_monster(self, obj: MapObject) -> bool:
        """A token no player controls and that is not a player character."""
        return (
            obj.kind == "token" and not obj.props.get("controlled_by") and not self._linked_pc(obj)
        )

    def _shows_hp(self, obj: MapObject) -> bool:
        """Whether everyone may see this token's hit point numbers."""
        return not self._is_monster(obj) or self.npc_hp == "full"

    async def on_combat_apply(self, conn: Connection, msg: p.CombatApply) -> None:
        player = conn.player
        assert player is not None
        tokens = [self._get_object(i) for i in msg.token_ids]
        for t in tokens:
            if t.kind != "token" or not permissions.controls(player, t):
                raise GameError("you can only change the hit points of tokens you control")
        rows: list[list[str]] = []
        verb = {"damage": "takes", "healing": "heals", "temp": "gains"}[msg.kind]
        for t in tokens:
            health, defenses = self._health(t)
            out = damage5e.apply(
                health, msg.kind, msg.amount, msg.damage_type, defenses, msg.half, msg.critical
            )
            name = t.props.get("name") or "Token"
            what = {
                "damage": f"{out.taken} {msg.damage_type or ''} damage".replace("  ", " "),
                "healing": f"{msg.amount} hit points",
                "temp": f"{msg.amount} temporary hit points",
            }[msg.kind]
            text = f"{verb} {what}"
            if self._shows_hp(t):
                text += f" → {out.health.current}/{out.health.max} HP"
                if out.health.temp:
                    text += f" (+{out.health.temp})"
            if out.notes:
                text += f" · {'; '.join(out.notes)}"
            rows.append([name, text])
            await self._write_health(t, out, f'{verb} {what}: "{name}"')
            if msg.kind == "damage":
                await self._concentration_save(self.objects[t.id], out.taken)
        title = {"damage": "Damage", "healing": "Healing", "temp": "Temporary hit points"}[msg.kind]
        template = {"name": "default", "title": title, "fields": rows}
        await self._post_chat(
            player, player.name, "", {"main": None, "inline": [], "template": template}
        )

    async def _death_save(
        self, player: Player, character: Character, sheet: Sheet
    ) -> list[list[str]]:
        """Roll a death save for a player character at 0 HP and record it."""
        if sheet.hp.current > 0:
            raise GameError(f"{character.name} is not at 0 hit points")
        result = chat.roll_to_dict(dice_roll("1d20"))
        nat = rolls5e.natural(result) or 0
        tokens = self._tokens_of(character)
        health = damage5e.Health(
            0,
            sheet.hp.max,
            sheet.hp.temp,
            True,
            sheet.death_saves.successes,
            sheet.death_saves.failures,
        )
        out = damage5e.death_save(health, nat)
        if tokens:
            await self._write_health(tokens[0], out, f'death save of "{character.name}"')
        else:
            data = _copy(character.sheet)
            data["hp"]["current"] = out.health.current
            data["death_saves"] = {
                "successes": out.health.successes,
                "failures": out.health.failures,
            }
            await self._set_sheet(character, data, f'death save of "{character.name}"')
        h = out.health
        return [
            ["Roll", str(nat)],
            ["Result", "; ".join(out.notes)],
            ["Death saves", f"{h.successes} successes, {h.failures} failures"],
        ]

    async def on_sheet_rest(self, conn: Connection, msg: p.SheetRest) -> None:
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        data = sheet.model_dump()
        fields: list[list[str]] = []
        rolls: list[dict[str, Any]] = []
        if msg.kind == "hit_die":
            total = sheet.level if sheet.kind == "pc" else 0
            if data["hit_dice"]["spent"] >= total:
                raise GameError("no hit point dice left")
            con = sheet5e.ability_mod(sheet, "con")
            result = chat.roll_to_dict(
                dice_roll(f"1d{sheet.hit_dice.die}{con:+d}" if con else f"1d{sheet.hit_dice.die}")
            )
            rolls.append(result)
            gained = max(1, int(result["total"]))
            data["hit_dice"]["spent"] += 1
            data["hp"]["current"] = min(data["hp"]["max"], data["hp"]["current"] + gained)
            fields = [
                ["Hit point die", "[[#0]]"],
                ["Hit points", f"{data['hp']['current']}/{data['hp']['max']}"],
            ]
            label = "Hit point die"
        elif msg.kind == "short":
            for r in data["resources"]:
                if r["reset"] == "short":
                    r["used"] = 0
            fields = [["Restored", "resources that recharge on a short rest"]]
            label = "Short rest"
        else:
            data["hp"]["current"], data["hp"]["temp"] = data["hp"]["max"], 0
            data["hit_dice"]["spent"] = 0
            data["death_saves"] = {"successes": 0, "failures": 0}
            data["exhaustion"] = max(0, data["exhaustion"] - 1)
            for slot in data["spellcasting"]["slots"].values():
                slot["used"] = 0
            for r in data["resources"]:
                if r["reset"] in ("short", "long"):
                    r["used"] = 0
            fields = [
                ["Restored", "hit points, hit point dice, spell slots and resources; exhaustion −1"]
            ]
            label = "Long rest"
        await self._set_sheet(character, data, f'{label.lower()} of "{character.name}"')
        await self._sync_tokens(character)
        if msg.kind == "long":
            await self._set_props(
                {
                    o.id: {
                        "statuses": sorted(set(o.props.get("statuses") or []) - {"unconscious"})
                        or None
                    }
                    for o in self._tokens_of(character)
                },
                "combat.apply",
                f'long rest of "{character.name}"',
            )
        template = {"name": "default", "title": f"{character.name}: {label}", "fields": fields}
        await self._post_chat(
            player, character.name, "", {"main": None, "inline": rolls, "template": template}
        )
