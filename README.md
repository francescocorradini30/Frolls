# Frolls

**Roll the dice, not the connection.**

Frolls is a virtual tabletop for playing fantasy roleplaying games online, 5e compatible. Map, tokens, chat and dice in real time in the browser, with nothing to install: fast, lightweight, designed to keep the table playing instead of waiting.

> Project under active development (version 0.1.0). Features and interface may change.

## What's already there

- **Shared map** with multiple pages, square, hex or no grid, configurable scale and distance rules.
- **Layers** for map, objects and GM: whatever is on the GM layer is never seen by players.
- **Tokens** with images, bars and status markers, draggable with grid snapping.
- **Drawing** freehand and shapes, text, ruler and areas (circle, cone, line, cube).
- **Ping** to point out a spot to everyone, and GM pull of the whole group's view.
- **Chat** with whispers, emotes, narration and dice rolls right inside the message.
- **Full dice engine**: advantage and disadvantage, exploding dice, rerolls, success counting, Fate dice.
- **Initiative tracker** with sorting, turns and rounds.

## How to play

| Action | How |
|---|---|
| Roll dice | type in chat `d20`, `2d6+3`, `2d20kh1` (advantage), `4d6dl1`, `8d6!`, `5d10>8` |
| Roll inside text | `I hit for [[1d8+3]] damage` |
| Whisper | `/w Name message`, `/w gm message` |
| Roll hidden to the GM | `/gr 1d20` |
| Emote / out of character / narration | `/em`, `/ooc`, `/desc` (GM) |
| Ping | press and hold on an empty spot (GM + Shift: brings everyone's view there) |
| Move the map | middle or right mouse button, or Space + drag |
| Zoom | mouse wheel |
| Tools | `V` select, `R` ruler, `D` pencil, `T` text |
| Journal | 📖 tab: characters with avatar, bio (`[Name]` links), attributes and folders. The GM sets who plays each character; drag a character onto the map to place its linked token, or link a token from its settings. Players speak in chat with their character's name; the GM picks "As …" under the chat box |
| Macros | ⚡ tab: your macros, run with a click, from the quick bar or with `#Name`. In any message: `@{selected\|hp}`, `@{target\|hp}` (then click the target), `%{Character\|Ability}`, `?{Bonus\|0}` (asked in one dialog), `&{template:default} {{name=Title}} {{Hit=[[1d20+5]]}}`, chat buttons `[Label](#Macro)`. Character abilities marked "token action" appear in the quick bar when one of its tokens is selected |
| Undo / redo | `Ctrl+Z` / `Ctrl+Y` (or `Ctrl+Shift+Z`) on your own map changes, or the ↶ ↷ buttons; the GM can revert anyone's change from the 🕘 History tab |
| Token | double-click = settings, right-click = menu, `Del` deletes, arrows move, `Ctrl+C/V/D` copy/paste/duplicate, `Alt` while dragging disables snapping |

## Coming soon

Handouts and journal permissions, 5e sheets for characters and NPCs with effects, durations and damage, SRD compendium, manual fog of war, rollable tables and card decks, accounts and multiple games.

## Legal notes

Frolls is an independent product compatible with the fifth edition. It uses exclusively content from the System Reference Document 5.2, released under the [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) license. It is not affiliated with or endorsed by Wizards of the Coast.

This work includes material from the System Reference Document 5.2 ("SRD 5.2") by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode. The compendium data was structured by [Open5e](https://open5e.com) (`backend/scripts/import_srd.py`).
