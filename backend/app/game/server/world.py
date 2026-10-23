"""GameServer handlers: fog of war, compendium, tables, tokens, card decks, art library."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, update

from app import compendium
from app.dice import TableItem
from app.game import fog, permissions
from app.game import protocol as p
from app.game.serialize import (
    asset_dict,
    deck_dict,
    object_dict,
    page_dict,
    table_dict,
)
from app.game.server.base import (
    CARD_RATIO,
    Connection,
    GameError,
    ServerBase,
    _describe,
    _rng,
    _tags,
)
from app.models import (
    Asset,
    Character,
    Deck,
    JournalFolder,
    MapObject,
    Page,
    Player,
    RollableTable,
)
from app.rules5e.data import SIZES
from app.rules5e.sheet import Sheet


class WorldMixin(ServerBase):
    # --- Fog of war ------------------------------------------------------------

    async def _save_fog(self, page: Page, data: dict[str, Any], summary: str) -> None:
        async with self._commit("fog", summary) as s:
            await s.execute(update(Page).where(Page.id == page.id).values(fog=data))
        page.fog = data
        self._broadcast_pages()
        for c in self._viewers(page.id):
            assert c.player is not None
            if c.player.is_gm:
                c.send({"type": "page.updated", "page": page_dict(page)})
            else:
                # Tokens may have come out of the fog or gone under it.
                self._page_snapshot(c, page.id)

    async def on_fog_set(self, conn: Connection, msg: p.FogSet) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        data = {**(page.fog or fog.default()), "enabled": msg.enabled}
        word = "on" if msg.enabled else "off"
        await self._save_fog(page, data, f'fog {word} on page "{page.name}"')

    async def on_fog_op(self, conn: Connection, msg: p.FogOp) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        if msg.shape == "poly" and len(msg.points) < 6:
            raise GameError("a polygon needs at least three points")
        current = page.fog or fog.default()
        ops = [
            *current.get("ops", []),
            {"mode": msg.mode, "shape": msg.shape, "points": msg.points},
        ]
        if len(ops) > fog.MAX_OPS:
            raise GameError("too many fog areas: hide or reveal the whole page to start again")
        await self._save_fog(
            page, {**current, "enabled": True, "ops": ops}, f"fog: {msg.mode} an area"
        )

    async def on_fog_reset(self, conn: Connection, msg: p.FogReset) -> None:
        self._require_gm(conn)
        page = self._get_page(msg.page_id)
        ops = []
        if msg.mode == "reveal":
            w, h = page.width * page.grid_size, page.height * page.grid_size
            ops = [{"mode": "reveal", "shape": "rect", "points": [0, 0, w, h]}]
        await self._save_fog(page, {"enabled": True, "ops": ops}, f"fog: {msg.mode} the whole page")

    # --- Compendium ------------------------------------------------------------

    async def on_compendium_search(self, conn: Connection, msg: p.CompendiumSearch) -> None:
        results = compendium.search(msg.kind, msg.query, msg.limit, msg.cr, msg.level)
        conn.send(
            {"type": "compendium.results", "rid": msg.rid, "kind": msg.kind, "items": results}
        )

    async def on_compendium_get(self, conn: Connection, msg: p.CompendiumGet) -> None:
        item = compendium.get(msg.kind, msg.key)
        if item is None:
            raise GameError("not in the compendium")
        conn.send({"type": "compendium.entry", "kind": msg.kind, "entry": item})

    async def _monster_character(self, key: str) -> Character:
        """The journal entry of a compendium monster: reused if it exists, else created in the
        "SRD monsters" folder."""
        item = compendium.get("monster", key)
        if item is None:
            raise GameError("not in the compendium")
        for c in self.characters.values():
            if c.sheet and c.sheet.get("source") == key:
                return c
        folder = next(
            (f for f in self.folders.values() if f.name == "SRD monsters" and f.parent_id is None),
            None,
        )
        if folder is None:
            folder = JournalFolder(
                id=str(uuid.uuid4()), game_id=self.game_id, name="SRD monsters", parent_id=None
            )
            async with self._commit("folder.create", 'created folder "SRD monsters"') as s:
                s.add(folder)
            self.folders[folder.id] = folder
            self._broadcast_folders([folder], [])
        sheet = Sheet.model_validate(item["sheet"]).model_dump()
        character = Character(
            id=str(uuid.uuid4()),
            game_id=self.game_id,
            name=item["name"],
            bio="",
            gm_notes="",
            attributes=[],
            abilities=[],
            sheet=sheet,
            folder_id=folder.id,
            archived=False,
        )
        async with self._commit("char.create", f'added "{item["name"]}" from the compendium') as s:
            s.add(character)
        self.characters[character.id] = character
        self._broadcast_character(character, None)
        return character

    async def on_compendium_add_monster(
        self, conn: Connection, msg: p.CompendiumAddMonster
    ) -> None:
        self._require_gm(conn)
        character = await self._monster_character(msg.key)
        conn.send({"type": "compendium.added", "rid": msg.rid, "character_id": character.id})

    async def on_compendium_place(self, conn: Connection, msg: p.CompendiumPlace) -> None:
        """GM: a compendium monster dropped on the map becomes a journal NPC and a token,
        numbered (Goblin 1, Goblin 2…)."""
        player = self._require_gm(conn)
        page = self._get_page(msg.page_id)
        character = await self._monster_character(msg.key)
        assert character.sheet is not None
        side = SIZES[character.sheet["size"]] * page.grid_size
        same = [
            o
            for o in self.objects.values()
            if o.props.get("represents") == character.id and o.page_id == page.id
        ]
        token = p.ObjectData(
            id=str(uuid.uuid4()),
            page_id=page.id,
            kind="token",
            layer=msg.layer,
            x=msg.x,
            y=msg.y,
            width=side,
            height=side,
            props={
                "name": f"{character.name} {len(same) + 1}",
                "show_name": True,
                "represents": character.id,
            },
        )
        await self.on_obj_create(conn, p.ObjectCreate(type="obj.create", objects=[token]))
        del player

    async def on_compendium_add_spell(self, conn: Connection, msg: p.CompendiumAddSpell) -> None:
        """Add a compendium spell to a character's sheet (the GM, or who plays it)."""
        player = conn.player
        assert player is not None
        character, sheet = self._sheet_of(player, msg.character_id)
        item = compendium.get("spell", msg.key)
        if item is None:
            raise GameError("not in the compendium")
        data = sheet.model_dump()
        if any(s["name"] == item["name"] for s in data["spells"]):
            raise GameError(f"{character.name} already has {item['name']}")
        spell = {**item["spell"], "id": str(uuid.uuid4())}
        data["spells"].append(spell)
        data = Sheet.model_validate(data).model_dump()
        await self._set_sheet(character, data, f"{character.name} learned {item['name']}")
        conn.send({"type": "notice", "detail": f"{item['name']} added to {character.name}"})

    # --- Rollable tables -----------------------------------------------------

    def _sees_table(self, player: Player, table: RollableTable) -> bool:
        return player.is_gm or table.show_players

    def _table_lookup(self, player: Player) -> dict[str, list[TableItem]]:
        """The tables `player` may roll, by lowercase name."""
        return {
            t.name.casefold(): [
                TableItem(i["name"], int(i.get("weight", 1)), i.get("image")) for i in t.items
            ]
            for t in self.tables.values()
            if self._sees_table(player, t)
        }

    def _get_table(self, table_id: str) -> RollableTable:
        table = self.tables.get(table_id)
        if table is None:
            raise GameError("table does not exist")
        return table

    def _table_name(self, name: str, table_id: str) -> str:
        name = name.strip()
        if not name:
            raise GameError("a table needs a name")
        if any(
            t.name.casefold() == name.casefold() and t.id != table_id for t in self.tables.values()
        ):
            raise GameError(f'there is already a table named "{name}"')
        return name

    def _send_tables(self, upsert: list[RollableTable], removed: list[str]) -> None:
        for c in self.connections:
            if not c.player:
                continue
            shown = [t for t in upsert if self._sees_table(c.player, t)]
            gone = removed + [t.id for t in upsert if not self._sees_table(c.player, t)]
            if shown:
                c.send({"type": "table.upsert", "tables": [table_dict(t) for t in shown]})
            if gone:
                c.send({"type": "table.removed", "ids": gone})

    async def on_table_create(self, conn: Connection, msg: p.TableCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.tables:
            raise GameError(f"id {msg.id} already in use")
        table = RollableTable(
            id=msg.id,
            game_id=self.game_id,
            name=self._table_name(msg.name, msg.id),
            items=[],
            show_players=True,
        )
        async with self._commit(msg.type, f'created rollable table "{table.name}"') as s:
            s.add(table)
        self.tables[table.id] = table
        self._send_tables([table], [])

    async def on_table_update(self, conn: Connection, msg: p.TableUpdate) -> None:
        self._require_gm(conn)
        table = self._get_table(msg.id)
        values: dict[str, Any] = {}
        if msg.name is not None:
            values["name"] = self._table_name(msg.name, table.id)
        if msg.show_players is not None:
            values["show_players"] = msg.show_players
        if msg.items is not None:
            values["items"] = [i.model_dump() for i in msg.items]
        values = {k: v for k, v in values.items() if getattr(table, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited rollable table "{table.name}"') as s:
            await s.execute(
                update(RollableTable).where(RollableTable.id == table.id).values(**values)
            )
        for k, v in values.items():
            setattr(table, k, v)
        self._send_tables([table], [])

    async def on_table_delete(self, conn: Connection, msg: p.TableDelete) -> None:
        self._require_gm(conn)
        table = self._get_table(msg.id)
        async with self._commit(msg.type, f'deleted rollable table "{table.name}"') as s:
            await s.execute(delete(RollableTable).where(RollableTable.id == table.id))
        del self.tables[table.id]
        self._send_tables([], [table.id])

    # --- Multi-sided tokens -------------------------------------------------

    async def on_token_side(self, conn: Connection, msg: p.TokenSide) -> None:
        """Server-side, so a random side (a coin, a die token) can't be picked by the client."""
        patches = []
        for obj_id in msg.ids:
            obj = self._get_object(obj_id)
            sides = obj.props.get("sides") or []
            if len(sides) < 2:
                continue
            side = _rng.randrange(len(sides)) if msg.side is None else msg.side
            if side >= len(sides):
                raise GameError(f"{_describe([obj])} has only {len(sides)} sides")
            patches.append(p.ObjectPatch(id=obj.id, props={"side": side, "image": sides[side]}))
        if patches:
            await self.on_obj_update(conn, p.ObjectUpdate(type="obj.update", patches=patches))

    # --- Card decks ----------------------------------------------------------

    def _sees_deck(self, player: Player, deck: Deck) -> bool:
        return player.is_gm or bool((deck.settings or {}).get("show_players", True))

    def _cards_on_table(self, deck: Deck) -> dict[str, MapObject]:
        """Card id -> its token on the map."""
        out: dict[str, MapObject] = {}
        for o in self.objects.values():
            card = o.props.get("card")
            if card and card.get("deck_id") == deck.id:
                out[card["card_id"]] = o
        return out

    def _deck_for(self, player: Player, deck: Deck) -> dict[str, Any]:
        return deck_dict(deck, player, set(self._cards_on_table(deck)))

    def _send_decks(self, upsert: list[Deck], removed: list[str]) -> None:
        for c in self.connections:
            if not c.player:
                continue
            shown = [d for d in upsert if self._sees_deck(c.player, d)]
            gone = removed + [d.id for d in upsert if not self._sees_deck(c.player, d)]
            if shown:
                c.send(
                    {"type": "deck.upsert", "decks": [self._deck_for(c.player, d) for d in shown]}
                )
            if gone:
                c.send({"type": "deck.removed", "ids": gone})

    def _get_deck(self, deck_id: str) -> Deck:
        deck = self.decks.get(deck_id)
        if deck is None:
            raise GameError("deck does not exist")
        return deck

    async def _save_deck(self, deck: Deck, values: dict[str, Any], kind: str, summary: str) -> None:
        async with self._commit(kind, summary) as s:
            await s.execute(update(Deck).where(Deck.id == deck.id).values(**values))
        for k, v in values.items():
            setattr(deck, k, v)
        self._send_decks([deck], [])

    async def on_deck_create(self, conn: Connection, msg: p.DeckCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.decks:
            raise GameError(f"id {msg.id} already in use")
        deck = Deck(
            id=msg.id,
            game_id=self.game_id,
            name=msg.name.strip() or "Deck",
            back=None,
            cards=[],
            pile=[],
            hands={},
            settings=p.DeckSettings().model_dump(),
        )
        async with self._commit(msg.type, f'created deck "{deck.name}"') as s:
            s.add(deck)
        self.decks[deck.id] = deck
        self._send_decks([deck], [])

    async def on_deck_update(self, conn: Connection, msg: p.DeckUpdate) -> None:
        self._require_gm(conn)
        deck = self._get_deck(msg.id)
        values = msg.model_dump(exclude_unset=True, include={"name", "back"})
        if msg.settings is not None:
            values["settings"] = {**deck.settings, **msg.settings.model_dump(exclude_unset=True)}
        if msg.cards is not None:
            cards = [c.model_dump() for c in msg.cards]
            ids = [c["id"] for c in cards]
            if len(set(ids)) != len(ids):
                raise GameError("two cards have the same id")
            old = {c["id"] for c in deck.cards}
            kept = set(ids)
            # New cards go to the bottom of the pile; removed ones leave every list.
            values["cards"] = cards
            values["pile"] = [cid for cid in ids if cid not in old] + [
                cid for cid in deck.pile if cid in kept
            ]
            values["hands"] = {
                pid: [cid for cid in hand if cid in kept] for pid, hand in deck.hands.items()
            }
        values = {k: v for k, v in values.items() if getattr(deck, k) != v}
        if values:
            await self._save_deck(deck, values, msg.type, f'edited deck "{deck.name}"')

    async def on_deck_delete(self, conn: Connection, msg: p.DeckDelete) -> None:
        self._require_gm(conn)
        deck = self._get_deck(msg.id)
        tokens = list(self._cards_on_table(deck).values())
        if tokens:
            await self._remove_objects(tokens, msg.type, f'cleared the cards of "{deck.name}"')
        async with self._commit(msg.type, f'deleted deck "{deck.name}"') as s:
            await s.execute(delete(Deck).where(Deck.id == deck.id))
        del self.decks[deck.id]
        self._send_decks([], [deck.id])

    async def _add_objects(self, objs: list[MapObject], kind: str, summary: str) -> None:
        """Create objects for the server's own actions: no permission check, no undo step."""
        changes = [{"id": o.id, "before": None, "after": object_dict(o)} for o in objs]
        async with self._commit(kind, summary, {"objects": changes}, [o.id for o in objs]) as s:
            s.add_all(objs)
        for o in objs:
            self.objects[o.id] = o
        self._publish_objects(objs, [], {})

    async def _remove_objects(self, objs: list[MapObject], kind: str, summary: str) -> None:
        changes = [{"id": o.id, "before": object_dict(o), "after": None} for o in objs]
        ids = [o.id for o in objs]
        async with self._commit(kind, summary, {"objects": changes}, ids) as s:
            await s.execute(delete(MapObject).where(MapObject.id.in_(ids)))
        for o in objs:
            del self.objects[o.id]
        self._publish_objects([], objs, {})
        await self._prune_turn_order(set(ids))

    def _from_hand(self, deck: Deck, player: Player, card_ids: list[str]) -> dict[str, list[str]]:
        """Hands after taking `card_ids` out: the player's own, or any hand for the GM."""
        hands = {pid: list(ids) for pid, ids in deck.hands.items()}
        for cid in card_ids:
            holder = next((pid for pid, ids in hands.items() if cid in ids), None)
            if holder is None or (holder != player.id and not player.is_gm):
                raise GameError("that card is not in your hand")
            hands[holder].remove(cid)
        return {pid: ids for pid, ids in hands.items() if ids}

    async def on_deck_action(self, conn: Connection, msg: p.DeckAction) -> None:
        player = conn.player
        assert player is not None
        deck = self._get_deck(msg.deck_id)
        if not self._sees_deck(player, deck):
            raise GameError("deck does not exist")
        name = f'"{deck.name}"'
        on_table = self._cards_on_table(deck)

        if msg.action in ("shuffle", "recall"):
            self._require_gm(conn)
            if msg.action == "recall":
                if on_table:
                    await self._remove_objects(
                        list(on_table.values()), msg.type, f"recalled {name}"
                    )
                hands: dict[str, list[str]] = {}
                pile = [c["id"] for c in deck.cards]
            else:
                # The discard pile goes back in; hands and the table stay as they are.
                hands = deck.hands
                held = {cid for ids in hands.values() for cid in ids}
                pile = [
                    c["id"] for c in deck.cards if c["id"] not in held and c["id"] not in on_table
                ]
            _rng.shuffle(pile)
            summary = f"{'recalled and ' if msg.action == 'recall' else ''}shuffled {name}"
            await self._save_deck(deck, {"pile": pile, "hands": hands}, msg.type, summary)
            await self._card_chat(player, summary)
            return

        if msg.action == "draw":
            to = msg.player_id or player.id
            if to != player.id:
                self._require_gm(conn)
            elif not player.is_gm and not deck.settings.get("players_draw", True):
                raise GameError("only the GM deals from this deck")
            if to not in self.players:
                raise GameError("player does not exist")
            if len(deck.pile) < msg.count:
                raise GameError(f"{name} has only {len(deck.pile)} cards left")
            drawn = deck.pile[len(deck.pile) - msg.count :][::-1]
            hands = {**deck.hands, to: [*deck.hands.get(to, []), *drawn]}
            who = self.players[to].name
            cards = f"{msg.count} card{'s' if msg.count > 1 else ''}"
            summary = (
                f"drew {cards} from {name}"
                if to == player.id
                else f"dealt {cards} from {name} to {who}"
            )
            await self._save_deck(
                deck,
                {"pile": deck.pile[: len(deck.pile) - msg.count], "hands": hands},
                msg.type,
                summary,
            )
            await self._card_chat(player, summary)
            return

        if msg.action == "play":
            page = self._get_page(msg.page_id or self.player_page(player))
            if not player.is_gm and page.id != self.player_page(player):
                raise GameError("you can only play cards on your page")
            values: dict[str, Any] = {}
            if msg.card_ids:
                values["hands"] = self._from_hand(deck, player, msg.card_ids)
                played = msg.card_ids
            else:
                self._require_gm(conn)
                if len(deck.pile) < msg.count:
                    raise GameError(f"{name} has only {len(deck.pile)} cards left")
                played = deck.pile[len(deck.pile) - msg.count :][::-1]
                values["pile"] = deck.pile[: len(deck.pile) - msg.count]
            holder = {cid: pid for pid, ids in deck.hands.items() for cid in ids}
            by_id = {c["id"]: c for c in deck.cards}
            size = page.grid_size
            top = self._top_z()
            objs = []
            for i, cid in enumerate(played):
                card = by_id[cid]
                side = 1 if msg.face_down else 0
                sides = [card.get("image"), deck.back]
                owner = holder.get(cid)
                objs.append(
                    MapObject(
                        id=str(uuid.uuid4()),
                        page_id=page.id,
                        kind="token",
                        layer="objects",
                        x=msg.x + i * size * 0.3,
                        y=msg.y,
                        width=size,
                        height=size * CARD_RATIO,
                        rotation=0,
                        z=top + i + 1,
                        owner_id=player.id,
                        props={
                            "name": card.get("name") or "Card",
                            "image": sides[side],
                            "sides": sides,
                            "side": side,
                            "show_name": False,
                            # Kept for every viewer: a card without a picture is drawn as one.
                            "shape": "card",
                            "card": {"deck_id": deck.id, "card_id": cid},
                            "controlled_by": [owner] if owner else [],
                        },
                    )
                )
            how = " face down" if msg.face_down else ""
            # A face-down card keeps its name to itself.
            what = (
                f"{len(objs)} card{'s' if len(objs) > 1 else ''}"
                if len(objs) > 1 or msg.face_down
                else f'"{objs[0].props["name"]}"'
            )
            summary = f"played {what}{how} from {name}"
            await self._add_objects(objs, msg.type, summary)
            await self._save_deck(deck, values, msg.type, summary)
            await self._card_chat(player, summary)
            return

        if msg.action == "discard":
            hands = self._from_hand(deck, player, msg.card_ids)
            n = len(msg.card_ids)
            summary = f"discarded {n} card{'s' if n != 1 else ''} from {name}"
            await self._save_deck(deck, {"hands": hands}, msg.type, summary)
            await self._card_chat(player, summary)
            return

        # take: card tokens from the table into the hand.
        tokens = []
        for obj_id in msg.object_ids:
            obj = self._get_object(obj_id)
            card = obj.props.get("card") or {}
            if card.get("deck_id") != deck.id:
                raise GameError("that is not a card of this deck")
            if not permissions.controls(player, obj):
                raise GameError("you do not control that card")
            tokens.append(obj)
        if not tokens:
            return
        summary = (
            f"{player.name} took {len(tokens)} card{'s' if len(tokens) > 1 else ''} into their hand"
        )
        await self._remove_objects(tokens, msg.type, summary)
        taken = [o.props["card"]["card_id"] for o in tokens]
        hands = {**deck.hands, player.id: [*deck.hands.get(player.id, []), *taken]}
        await self._save_deck(deck, {"hands": hands}, msg.type, summary)

    async def _card_chat(self, player: Player, text: str) -> None:
        """Card moves are announced in chat, as at a real table: "Aria drew 1 card from …"."""
        await self._post_chat(player, player.name, content=text + ".", roll=None, kind="emote")

    async def _after_card_tokens_change(self, objs: list[MapObject]) -> None:
        """Counts of the decks whose card tokens were created or deleted elsewhere."""
        decks = {
            o.props["card"].get("deck_id") for o in objs if isinstance(o.props.get("card"), dict)
        }
        changed = [self.decks[d] for d in decks if d in self.decks]
        if changed:
            self._send_decks(changed, [])

    # --- Art library ---------------------------------------------------------

    def _send_assets(self, player_id: str, upsert: list[Asset], removed: list[str]) -> None:
        """A library is private: only its owner's connections hear about it."""
        for c in self.connections:
            if c.player and c.player.id == player_id:
                if upsert:
                    c.send({"type": "asset.upsert", "assets": [asset_dict(a) for a in upsert]})
                if removed:
                    c.send({"type": "asset.removed", "ids": removed})

    def _own_asset(self, player: Player, asset_id: str) -> Asset:
        asset = self.assets.get(asset_id)
        if asset is None or asset.player_id != player.id:
            raise GameError("image does not exist")
        return asset

    async def on_asset_create(self, conn: Connection, msg: p.AssetCreate) -> None:
        player = conn.player
        assert player is not None
        if msg.id in self.assets:
            raise GameError(f"id {msg.id} already in use")
        values = msg.model_dump(exclude={"type", "rid"})
        values["tags"] = _tags(values["tags"])
        values["folder"] = values["folder"].strip()
        asset = Asset(game_id=self.game_id, player_id=player.id, **values)
        async with self._commit(msg.type, f'added "{asset.name}" to the art library') as s:
            s.add(asset)
        self.assets[asset.id] = asset
        self._send_assets(player.id, [asset], [])

    async def on_asset_update(self, conn: Connection, msg: p.AssetUpdate) -> None:
        player = conn.player
        assert player is not None
        asset = self._own_asset(player, msg.id)
        values = msg.model_dump(exclude_none=True, include={"name", "folder", "tags"})
        if "tags" in values:
            values["tags"] = _tags(values["tags"])
        if "folder" in values:
            values["folder"] = values["folder"].strip()
        values = {k: v for k, v in values.items() if getattr(asset, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited "{asset.name}" in the art library') as s:
            await s.execute(update(Asset).where(Asset.id == asset.id).values(**values))
        for k, v in values.items():
            setattr(asset, k, v)
        self._send_assets(player.id, [asset], [])

    async def on_asset_delete(self, conn: Connection, msg: p.AssetDelete) -> None:
        player = conn.player
        assert player is not None
        assets = [self._own_asset(player, i) for i in msg.ids]
        n = len(assets)
        summary = f"removed {n} image{'s' if n > 1 else ''} from the art library"
        async with self._commit(msg.type, summary) as s:
            await s.execute(delete(Asset).where(Asset.id.in_([a.id for a in assets])))
        for a in assets:
            # The files stay: tokens on the map may still show them.
            del self.assets[a.id]
        self._send_assets(player.id, [], [a.id for a in assets])
