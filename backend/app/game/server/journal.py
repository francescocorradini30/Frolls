"""GameServer handlers: journal, macros."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, update

from app.game import macros
from app.game import protocol as p
from app.game.serialize import (
    character_dict,
    folder_dict,
    macro_dict,
)
from app.game.server.base import (
    PLAYER_CHARACTER_FIELDS,
    Connection,
    GameError,
    ServerBase,
    _number,
)
from app.models import (
    DEFAULT_GAME_ID,
    Character,
    JournalFolder,
    Macro,
    MapObject,
    Player,
)


class JournalMixin(ServerBase):
    # --- Journal -------------------------------------------------------------

    def _sees_character(self, player: Player, character: Character) -> bool:
        """GMs see every character; a player sees only the ones they play."""
        return player.is_gm or character.player_id == player.id

    def _journal_for(self, player: Player) -> dict[str, Any]:
        return {
            "characters": [
                character_dict(c, player.is_gm)
                for c in self.characters.values()
                if self._sees_character(player, c)
            ],
            # Folders organise the GM's journal; players see their characters flat.
            "folders": [folder_dict(f) for f in self.folders.values()] if player.is_gm else [],
        }

    def _broadcast_character(self, character: Character, old_player: str | None) -> None:
        for c in self.connections:
            if not c.player:
                continue
            if self._sees_character(c.player, character):
                c.send(
                    {
                        "type": "journal.upsert",
                        "characters": [character_dict(character, c.player.is_gm)],
                    }
                )
            elif old_player == c.player.id:
                # Taken away from this player.
                c.send({"type": "journal.removed", "character_ids": [character.id]})

    def _broadcast_folders(self, upsert: list[JournalFolder], removed: list[str]) -> None:
        for c in self.connections:
            if c.player and c.player.is_gm:
                if upsert:
                    c.send({"type": "journal.upsert", "folders": [folder_dict(f) for f in upsert]})
                if removed:
                    c.send({"type": "journal.removed", "folder_ids": removed})

    def _get_character(self, character_id: str) -> Character:
        character = self.characters.get(character_id)
        if character is None:
            raise GameError("character does not exist")
        return character

    def _character_values(self, patch: p.CharacterPatch) -> dict[str, Any]:
        values = patch.model_dump(exclude_unset=True)
        if patch.sheet is not None:
            # The whole sheet with every default filled in, not only the fields sent.
            values["sheet"] = patch.sheet.model_dump()
        for key in ("name", "bio", "gm_notes", "attributes", "archived"):
            if key in values and values[key] is None:
                raise GameError(f"{key} cannot be empty")
        if "name" in values:
            values["name"] = values["name"].strip() or "Unnamed"
        if values.get("folder_id") is not None and values["folder_id"] not in self.folders:
            raise GameError("folder does not exist")
        if values.get("player_id") is not None and values["player_id"] not in self.players:
            raise GameError("player does not exist")
        return values

    async def on_char_create(self, conn: Connection, msg: p.CharacterCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.characters:
            raise GameError(f"id {msg.id} already in use")
        values = self._character_values(msg.character)
        character = Character(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            **{
                "name": "New character",
                "bio": "",
                "gm_notes": "",
                "attributes": [],
                "archived": False,
                **values,
            },
        )
        async with self._commit(msg.type, f'created character "{character.name}"') as s:
            s.add(character)
        self.characters[character.id] = character
        self._broadcast_character(character, None)

    async def on_char_update(self, conn: Connection, msg: p.CharacterUpdate) -> None:
        player = conn.player
        assert player is not None
        character = self._get_character(msg.id)
        values = self._character_values(msg.patch)
        if not player.is_gm:
            if character.player_id != player.id:
                raise GameError("you can only edit your own character")
            if values.keys() - PLAYER_CHARACTER_FIELDS:
                raise GameError("only the GM can change notes, folder, player or archive")
        values = {k: v for k, v in values.items() if getattr(character, k) != v}
        if not values:
            return
        old_player = character.player_id
        async with self._commit(msg.type, f'edited character "{character.name}"') as s:
            await s.execute(update(Character).where(Character.id == character.id).values(**values))
        old_sheet = character.sheet
        for k, v in values.items():
            setattr(character, k, v)
        self._broadcast_character(character, old_player)
        if "sheet" in values:
            await self._sync_tokens(character)
            if (old_sheet or {}).get("size") != (character.sheet or {}).get("size"):
                await self._fit_tokens(character)

    async def on_char_delete(self, conn: Connection, msg: p.CharacterDelete) -> None:
        self._require_gm(conn)
        character = self._get_character(msg.id)
        # Tokens that represented it become plain tokens.
        linked = [o for o in self.objects.values() if o.props.get("represents") == character.id]
        async with self._commit(
            msg.type, f'deleted character "{character.name}"', None, [o.id for o in linked]
        ) as s:
            await s.execute(delete(Character).where(Character.id == character.id))
            for o in linked:
                props = {k: v for k, v in o.props.items() if k != "represents"}
                await s.execute(update(MapObject).where(MapObject.id == o.id).values(props=props))
        for o in linked:
            o.props = {k: v for k, v in o.props.items() if k != "represents"}
        del self.characters[character.id]
        for c in self.connections:
            if c.player and self._sees_character(c.player, character):
                c.send({"type": "journal.removed", "character_ids": [character.id]})
        self._publish_objects(linked, [], {})

    async def on_folder_create(self, conn: Connection, msg: p.FolderCreate) -> None:
        self._require_gm(conn)
        if msg.id in self.folders:
            raise GameError(f"id {msg.id} already in use")
        if msg.parent_id is not None and msg.parent_id not in self.folders:
            raise GameError("folder does not exist")
        folder = JournalFolder(
            id=msg.id, game_id=DEFAULT_GAME_ID, name=msg.name.strip(), parent_id=msg.parent_id
        )
        async with self._commit(msg.type, f'created folder "{folder.name}"') as s:
            s.add(folder)
        self.folders[folder.id] = folder
        self._broadcast_folders([folder], [])

    async def on_folder_update(self, conn: Connection, msg: p.FolderUpdate) -> None:
        self._require_gm(conn)
        folder = self.folders.get(msg.id)
        if folder is None:
            raise GameError("folder does not exist")
        values = msg.model_dump(exclude_unset=True, include={"name", "parent_id"})
        if values.get("name") is None:
            values.pop("name", None)
        if "parent_id" in values:
            parent = values["parent_id"]
            # A folder cannot go inside itself or one of its subfolders.
            while parent is not None:
                if parent == folder.id:
                    raise GameError("a folder cannot go inside itself")
                if parent not in self.folders:
                    raise GameError("folder does not exist")
                parent = self.folders[parent].parent_id
        if not values:
            return
        async with self._commit(msg.type, f'changed folder "{folder.name}"') as s:
            await s.execute(
                update(JournalFolder).where(JournalFolder.id == folder.id).values(**values)
            )
        for k, v in values.items():
            setattr(folder, k, v)
        self._broadcast_folders([folder], [])

    async def on_folder_delete(self, conn: Connection, msg: p.FolderDelete) -> None:
        self._require_gm(conn)
        folder = self.folders.get(msg.id)
        if folder is None:
            raise GameError("folder does not exist")
        children = [f for f in self.folders.values() if f.parent_id == folder.id]
        members = [c for c in self.characters.values() if c.folder_id == folder.id]
        async with self._commit(msg.type, f'deleted folder "{folder.name}"') as s:
            await s.execute(
                update(JournalFolder)
                .where(JournalFolder.parent_id == folder.id)
                .values(parent_id=folder.parent_id)
            )
            await s.execute(
                update(Character)
                .where(Character.folder_id == folder.id)
                .values(folder_id=folder.parent_id)
            )
            await s.execute(delete(JournalFolder).where(JournalFolder.id == folder.id))
        del self.folders[folder.id]
        for f in children:
            f.parent_id = folder.parent_id
        self._broadcast_folders(children, [folder.id])
        for character in members:
            character.folder_id = folder.parent_id
            self._broadcast_character(character, character.player_id)

    def _speaker(self, player: Player, as_character: str | None) -> str:
        """Chat name: a player speaks as their character, the GM as whoever they pick."""
        if player.is_gm:
            if as_character is None:
                return player.name
            return self._get_character(as_character).name
        own = self._own_character(player)
        return own.name if own else player.name

    def _own_character(self, player: Player) -> Character | None:
        mine = [c for c in self.characters.values() if c.player_id == player.id and not c.archived]
        return min(mine, key=lambda c: c.name.casefold()) if mine else None

    # --- Macros --------------------------------------------------------------

    def _macros_of(self, player_id: str) -> list[Macro]:
        return [m for m in self.macros.values() if m.player_id == player_id]

    def _send_macros(self, player_id: str, upsert: list[Macro], removed: list[str]) -> None:
        """Macros are private: only the owner's connections hear about them."""
        for c in self.connections:
            if c.player and c.player.id == player_id:
                if upsert:
                    c.send({"type": "macro.upsert", "macros": [macro_dict(m) for m in upsert]})
                if removed:
                    c.send({"type": "macro.removed", "ids": removed})

    def _own_macro(self, player: Player, macro_id: str) -> Macro:
        macro = self.macros.get(macro_id)
        if macro is None or macro.player_id != player.id:
            raise GameError("macro does not exist")
        return macro

    async def on_macro_create(self, conn: Connection, msg: p.MacroCreate) -> None:
        player = conn.player
        assert player is not None
        if msg.id in self.macros:
            raise GameError(f"id {msg.id} already in use")
        macro = Macro(
            id=msg.id,
            game_id=DEFAULT_GAME_ID,
            player_id=player.id,
            name=_macro_name(msg.name),
            action=msg.action,
            in_bar=msg.in_bar,
        )
        async with self._commit(msg.type, f'created macro "{macro.name}"') as s:
            s.add(macro)
        self.macros[macro.id] = macro
        self._send_macros(player.id, [macro], [])

    async def on_macro_update(self, conn: Connection, msg: p.MacroUpdate) -> None:
        player = conn.player
        assert player is not None
        macro = self._own_macro(player, msg.id)
        values = msg.model_dump(exclude_none=True, include={"name", "action", "in_bar"})
        if "name" in values:
            values["name"] = _macro_name(values["name"])
        values = {k: v for k, v in values.items() if getattr(macro, k) != v}
        if not values:
            return
        async with self._commit(msg.type, f'edited macro "{macro.name}"') as s:
            await s.execute(update(Macro).where(Macro.id == macro.id).values(**values))
        for k, v in values.items():
            setattr(macro, k, v)
        self._send_macros(player.id, [macro], [])

    async def on_macro_delete(self, conn: Connection, msg: p.MacroDelete) -> None:
        player = conn.player
        assert player is not None
        macro = self._own_macro(player, msg.id)
        async with self._commit(msg.type, f'deleted macro "{macro.name}"') as s:
            await s.execute(delete(Macro).where(Macro.id == macro.id))
        del self.macros[macro.id]
        self._send_macros(player.id, [], [macro.id])


def _macro_name(name: str) -> str:
    """Macro names are called as `#Name`: no spaces."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", name.replace(" ", "_"))
    if not cleaned:
        raise GameError("a macro name needs letters or digits")
    return cleaned


# Token fields readable with @{selected|…} and @{target|…}: (prop, key in the bar).
TOKEN_FIELDS = {
    "hp": ("bar1", "value"),
    "bar1": ("bar1", "value"),
    "temp_hp": ("bar2", "value"),
    "bar2": ("bar2", "value"),
}


class MacroResolver:
    """Game data for macro expansion, limited to what `player` may see."""

    def __init__(
        self,
        server: ServerBase,
        player: Player,
        selected_id: str | None,
        target_id: str | None,
    ) -> None:
        self.server = server
        self.player = player
        self.tokens = {"selected": selected_id, "target": target_id}

    def macro(self, name: str) -> str | None:
        own = self.server._macros_of(self.player.id)
        found = next((m for m in own if m.name == name), None) or next(
            (m for m in own if m.name.casefold() == name.casefold()), None
        )
        return found.action if found else None

    def _token(self, ref: str) -> MapObject:
        token_id = self.tokens[ref]
        if token_id is None:
            if ref == "target":
                raise macros.NeedTarget
            raise macros.MacroError("select a token first")
        obj = self.server.objects.get(token_id)
        if obj is None or obj.kind != "token" or not self.server._can_see(self.player, obj):
            raise macros.MacroError(f"the {ref} token does not exist")
        return obj

    def _character(self, ref: str) -> Character:
        if ref in self.tokens:
            obj = self._token(ref)
            character = self.server.characters.get(obj.props.get("represents") or "")
            if character is None:
                raise macros.MacroError(f"the {ref} token does not represent a character")
        elif ref.startswith(macros.BOUND):
            character = self.server.characters.get(ref[1:])
        else:
            key = ref.casefold()
            character = next(
                (
                    c
                    for c in self.server.characters.values()
                    if c.name.casefold() == key and self.server._sees_character(self.player, c)
                ),
                None,
            )
        if character is None or not self.server._sees_character(self.player, character):
            raise macros.MacroError(f'no character named "{ref}"')
        return character

    def ability(self, ref: str, name: str) -> tuple[str, str]:
        character = self._character(ref)
        key = name.casefold()
        found = next((a for a in character.abilities if a["name"].casefold() == key), None)
        if found is None:
            raise macros.MacroError(f'{character.name} has no ability "{name}"')
        return found["action"], character.id

    def attribute(self, ref: str, name: str, use_max: bool) -> str:
        key = name.casefold()
        if ref in self.tokens:
            obj = self._token(ref)
            if key == "token_name":
                return str(obj.props.get("name") or "")
            if key in TOKEN_FIELDS:
                if not self.player.is_gm and not self.server._shows_hp(obj):
                    raise macros.MacroError("the hit points of that creature are hidden")
                prop, _ = TOKEN_FIELDS[key]
                value = (obj.props.get(prop) or {}).get("max" if use_max else "value")
                return "0" if value is None else _number(value)
        character = self._character(ref)
        found = next((a for a in character.attributes if a["name"].casefold() == key), None)
        if found is None:
            raise macros.MacroError(f'{character.name} has no attribute "{name}"')
        return found["max" if use_max else "current"] or "0"
