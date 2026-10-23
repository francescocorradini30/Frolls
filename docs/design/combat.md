# Frolls: combat flow and automation, final spec

Council area A. This merges member 1's gameplay proposal with the UX and architecture review. A developer should be able to build from this document alone. Code references are to the current repo (`backend/app/game/server/*.py`, `backend/app/rules5e/*`, `frontend/src/lib/*`).

## 1. Summary

- **One rule:** one player intent = one `combat.act` = one server resolution = one event row = one chat card = one undo step.
  - The server rolls, compares against AC, applies damage with resistances, adds effects, spends slots and the action, and posts one structured card.
  - The card has **Undo** (actor during their turn, GM always). Ctrl+Z undoes it too.
- **Atomic writes:** a new **action capture** layer makes the existing helpers (`_set_props`, `_set_sheet`, `_save_turns`, `_post_chat`, `_card`) write to memory and record before/after during one handler. Everything is committed in a single `_commit` at the end.
  - Undo is a **3-way merge**: numbers revert by delta, id-lists revert by id. It never refuses, so an old hit can still be undone after later healing.
- **Fewer clicks:**
  - **Player attack:** turn starts and the token is auto-selected → press `1` → click the goblin. Two inputs; damage is applied and the card is posted.
  - **Same target again:** `1` then `Enter`.
  - **Fireball:** `3` → click a point → `Enter`.
  - **Monster turn:** Multiattack slot → click the target.
- **UI pieces:**
  - **Token dock** (the existing SelectionHud plus a new action bar), bottom centre.
  - **Initiative ribbon**, top centre, shown only in combat.
  - **Prompt tray**, right side, for initiative, saves and death saves. It never blocks the table.
  - **Combat card** in chat, collapsed by default.
- **Settings:** 13 game switches and 1 player switch (down from member 1's 31). Everything else is either always on, never blocking, or one click to override.
- **Prompts never block:** the GM always has "Roll the rest". Nothing waits for everyone: each target resolves as its save arrives.

## 2. Final feature list

### MVP

| # | Feature | What it does |
|---|---|---|
| M1 | Action capture + merge undo | Every combat write is atomic and undoable: HP, sheet, effects, slots, tracker. HUD typing `-12 fire` / `+8` goes through the damage pipeline. |
| M2 | `combat.act` + combat card | Attacks resolve end to end: hit vs AC (+cover, +effects), every damage part, resistances, temp HP, concentration save, 0 HP, effects. Structured card, `chat.update`, Undo, per-viewer redaction. Generic **＋ Damage** on hit rows (Sneak Attack, Hex, Hunter's Mark, Smite dice; doubled or maxed on a crit). |
| M3 | Action bar + target mode | Bottom dock with economy pips, movement and slots 1–9. Spells / Actions / Legendary popovers. Map target mode (range rings, adv/dis, cover, multi-target). Enter = last target. |
| M4 | Sheet data + importer | Multi-part damage, numeric reach/range, cost (action/bonus/reaction/legendary), recharge, X/Day, multiattack, legendary uses and resistance, Extra Attack, crit range, spell casting time/range/area. Re-import of the SRD JSON. |
| M5 | Spells and saves | Attack spells per target, save spells with damage rolled once, per-target resolution. Monster saves always auto. PC saves are prompts (or auto, per switch). Circle area targeting from `spell.area`. Slots and concentration inside the action. |
| M6 | Monster kit | Multiattack (one click = all attacks on that target; Shift-click spreads them), Recharge (d6 at turn start, GM-only note), X/Day pips, Legendary actions (GM prompt after each other creature's turn), Legendary Resistance chip on a failed save. Per-token state in `token.props.npc`. |
| M7 | Combat flow | **⚔ Start combat** → initiative (NPCs auto, PCs prompted) → **Begin** → ribbon, "Your turn" banner, auto-select, chat turn divider, skip defeated, End turn (Ctrl+Enter) → **End combat** (clears the tracker and "until end of combat" effects, summary card with XP). Initiative modes: individual / grouped / sides. Reroll every round. Death save prompts. |
| M8 | Tactics and house rules | Range (beyond normal = disadvantage, beyond long = warning), ranged attack with a hostile within 5 ft = disadvantage, cover `C` (+2/+5), flanking switch, crit rule switch, movement budget (Speed, exhaustion, Grappled/Restrained = 0, Dash), opportunity attack prompts, standard actions (Dash, Disengage, Dodge, Stand up, Drink potion, Grapple, Shove, Other). Token `disposition`. |
| M9 | GM control | GM "⋯" on cards: Edit damage, Flip hit/miss, Flip save. Apply mode `confirm` / `manual`. Hidden action toggle. Visibility of monster AC and rolls. Combat actions revertible from the History tab. |

### Post-MVP (in this order)

1. **Named riders:** presets on the sheet that prefill ＋ Damage, with once-per-turn and cost (Sneak Attack, Divine Smite slot, Hunter's Mark/Hex auto-chip when the target has the mark effect).
2. **Weapon Mastery:** Graze, Sap, Vex, Slow, Topple as automatic effects; Push and Cleave as card buttons; Nick as economy.
3. **Reaction cards:** a "React" chip on hit/save cards for `casting_time: reaction` (Shield re-checks the hit, Uncanny Dodge halves).
4. Cone, line and cube targeting shapes. This is an owner decision, because those tools were removed.
5. Difficult terrain painting.
6. "Previous turn" for the GM.
7. Encounter builder with difficulty.
8. A "combat only" chat filter.

## 3. UI spec

All colours come from `theme.ts` tokens (`--accent` violet, `--success` mint, `--danger` rose, peach and butter from `palette`; add tokens before use). Panels use `.panel` + `--gradient-surface`, soft 10–12px corners and the `--glow` focus ring. Every element below is hidden when it has nothing to show.

### 3.1 Token dock (bottom centre)

The existing `SelectionHud.svelte` `.hud-wrap` stays where it is. Its stack, top to bottom:

1. HP / Temp bubbles (existing). Typing `-12 fire`, `-12`, `+8` or `+5 temp` on a token with a sheet sends `combat.apply` (pipeline, undoable). A plain number still sets the value as today.
2. HUD row (existing): name ✎, Statuses ▾, Effects.
3. **New `ActionBar.svelte`**. It shows when exactly one token is selected that the viewer controls and that `represents` a character with a sheet. A GM sees it for any such token.

Action bar layout, one row, 52px high:

```
[ A ● B ● R ● | ▰▰▰▱▱ 15/30 ft | Atk 1/2 ]  [1 ⚔ Longsword][2 🏹 Shortbow][3 ✦ Fireball ▪▪▫][4 ♥ Cure W.] … [9]  [✦ Spells ▾][⚑ Actions ▾][◆ Legendary ▾]  [👁][End turn ⏎]
```

**Economy cluster** (only while the token is in the tracker and the round is 1 or higher):
- Three pips: **A** action, **B** bonus, **R** reaction. Mint = available, haze = used, rose ring = overspent (spent twice). Clicking a pip toggles it, as `turn.use` does today.
- Movement bar shows moved / budget in the game's units (metric `4.5/9 m`). It turns rose past the budget.
- `Atk n/m` appears only when Extra Attack is above 1.

**Slots 1–9:**
- 44px tiles: number top-left, glyph, name truncated below, slot pips for leveled spells.
- Auto-filled in this order:
  - PCs: attacks, then prepared non-cantrip spells that have damage, heal or effect (lowest level first), then cantrips, then resources with uses.
  - NPCs: Multiattack, then attacks in stat-block order, then recharge/X-day abilities.
- A dim tile means a recharge ability not charged or no slots left. It can still be clicked: it warns, never blocks.
- Hovering a tile for 400ms shows the readable stat card: to-hit or DC, damage parts with types, range, cost, notes. This is the sheet's missing "play mode".
- Pinning or reordering tiles is post-MVP.

**Popovers:**
- **✦ Spells ▾:** a grid by level with slot pips per level. Clicking a spell = cast at its lowest available slot. `+` / `-` in target mode changes the slot level.
- **⚑ Actions ▾:** Dash, Disengage, Dodge, Stand up, Drink potion, Grapple, Shove, Other.
- **◆ Legendary ▾:** NPC only, shows uses left. Its actions are the attacks with `cost: legendary`.

**Right end:**
- 👁 hidden-action toggle (GM only, persists while on). The next card goes to the GM only.
- **End turn ⏎** (Ctrl+Enter), shown only to whoever controls the current entry. A GM sees **Next ▶**.

**Keys** (only when focus is not in an input and a dock token is selected): `1`–`9` start the slot. These digits are unused today; the tool shortcuts `v r d t e` are unchanged.

The QuickBar (macros, token actions) stays bottom-left as is. The HandBar stays bottom-right.

### 3.2 Target mode (Pixi overlay + store state)

`store.targeting = {actorId, action, slot, mode, targets: Map<id, cover>, area?}`. The Engine gets a `targeting` branch that runs before the tool branches in `onPointerDown` / `onPointerMove` / `onKeyDown`. It draws on a new overlay `Graphics` above objects, redrawn only when the hovered cell changes.

**Visuals:**
- Crosshair cursor.
- Dashed line from the actor's centre to the cursor in the player's colour, with a distance label (the existing measure label style).
- Range rings around the actor: reach as a cell outline; normal range as a solid faint ring; long range as a dashed ring.
- Hovered token: glow ring. **Mint** = valid. **Peach** = valid with disadvantage (long range, or a hostile adjacent for a ranged attack). **Rose** = beyond long range or total cover. Rose still allows the click; the card warns.
- Picked targets: pink reticle, numbered for multi-target.
- Cursor badge: `ADV` / `DIS`, cover `½` / `¾` for the hovered token, and the slot level for spells (`Lv 4`).
- A top hint line in the toast area: `Longsword: click a target · Shift multi · A/D adv/dis · C cover · Enter last target · Esc cancel`.

**Input:**
- Click a token: single-target actions resolve immediately.
- Shift-click: toggle the token into the set. `Enter` confirms.
- `Enter` with nothing picked reuses the actor's last target, which gets a faint reticle when target mode opens.
- `A` / `D` toggle advantage / disadvantage (a second press returns to normal). `C` cycles cover on the hovered token.
- `+` / `-` change the spell slot level.
- `Esc` cancels. The mouse wheel keeps zooming; right/middle drag keeps panning.

**Area spells** (`spell.area.shape in sphere|cylinder|emanation`) and save attacks with an area:
- The existing circle template follows the cursor, snapped to a cell centre, with radius `size_ft / 5` cells, using `areaRadius` from `Engine.ts`.
- Emanation is centred on the actor and does not follow the cursor.
- Click places it. Every token with any occupied cell inside the covered cells is pre-picked, the caster included as the rules say. Click toggles picks. `Enter` confirms.
- The client sends the final target list and the point. The server trusts the list, so the GM keeps freedom.
- Instantaneous spells only flash the area for 3 s to everyone on the page (`combat.flash`, transient like `measure`).
- Spells with a duration create a real circle template object inside the action, so Undo removes it.
- Cone, line and cube areas fall back to "Shift-click the targets" with the hint `Cone 15 ft: pick the targets`.

### 3.3 Initiative ribbon (top centre)

`InitiativeRibbon.svelte` appears when `turn_order` is not empty. Toasts move down below it.

```
 Round 3  ◀ [● Aria][Goblin B][Goblin C][Mage ◆◆◇] … ▶   [⋯]  [Next ▶]
```

**Chips:** 40px round avatar (token image, or colour plus initial) with the name under it.
- The current chip is 52px with a butter glow (the same colour as `views.setTurn`). The next one has a small "on deck" tag.
- Monster chips get an HP ring per `npc_hp`: hidden = no ring; status = quarters; full = arc.
- A dying PC shows death-save pips. Legendary NPCs show ◆ pips. A defeated combatant is a dim chip with a strike-through.
- In sides mode, chips are grouped into two capsules ("Party" / "Foes") and the whole active capsule glows.

**Interaction:**
- Clicking a chip focuses the token on the map and selects it if you control it.
- Before round 1, a chip waiting for initiative shows 🎲 (pulse). A GM click on a waiting chip rolls it.
- `⋯` opens the existing `TurnTracker.svelte` window for GM editing: values, drag reorder, custom entries, Clear. Its footer becomes: **⚔ Start combat** (round 0), **Begin round 1** (setup), **End combat** (in combat), plus the existing buttons. In setup a ☐ Surprised toggle shows per row: it re-rolls that row with disadvantage.
- Start combat with no selection = every token on the GM's page, objects layer, that represents a sheet. GM-layer tokens are excluded.
- The ribbon scrolls horizontally past the visible width. Arrow buttons appear only on overflow.

**"Your turn" banner:**
- When the current entry becomes one you control, a centred "Your turn" in the gradient text style fades in at 30% screen height and slides into your ribbon chip in 1.2 s. It has `pointer-events: none`.
- If `turn_autoselect` is on, your token is selected and the camera pans only if the token is off-screen.
- The next combatant's controller gets a quiet "On deck" tag on their chip and a short toast.

**Chat turn divider:** a server message of kind `turn`, rendered as a thin centred line `— Round 3 · Aria —`, posted at each turn start.

### 3.4 Prompt tray (right side, above the HandBar)

`PromptTray.svelte` is a stack of small actionable cards, newest at the bottom. Prompts are **derived from server state** so they survive a reload:

- **Initiative:** the tracker entry has `awaiting: true` and you control it. Card: `Roll initiative · Aria  [Roll ⏎]  A/D`.
- **Saving throw:** a card has a pending row for a token you control. `DEX save DC 15 · Fireball  [Roll ⏎]  A/D`.
- **Death save:** your PC is at 0 HP, it is its turn, and it hasn't rolled this turn.
- **Concentration save** (when `players_roll`): pending row of type `concentration` on a card.
- **Opportunity attack:** transient `combat.prompt` from the server. `Goblin B can hit Aria as she leaves  [Attack] [×]`. Gone after the next move or after 15 s. This is the only prompt not stored.
- **Legendary action** (GM only, derived on the client): after any turn ends that isn't the boss's, if `npc.legendary_used < uses`. `Mage ◆◆◇  [Arcane Burst] [Teleport] [×]`. Clicking an action starts target mode with `cost: legendary`.

Keys work on the bottom-most prompt when focus is free: `Enter` = primary button, `A` / `D` = roll with advantage / disadvantage. They never steal keys while target mode is active.

The GM sees a compact "Waiting: Aria, Bren [Roll the rest]" line instead of each player's prompt.

### 3.5 Combat card (chat)

`CombatCard.svelte` renders `msg.roll.card` (structured). `ChatMessageView.svelte` picks it when `roll.card` is present. Old template cards are unchanged.

**Collapsed (default):**

```
● Aria → Goblin B · Longsword                  [HIT]  ↶  ⋯
  Goblin B    −9 slashing  ½ resist     ◉ Bloodied   +Prone
  [＋ Damage]
```

- **Header:** speaker colour dot, `actor → target(s) · action` (`→ 3 targets` beyond 2), outcome badge, ↶ Undo (actor during their turn, GM always), ⋯ GM menu.
  - Badge colours: HIT mint, CRIT pink glow, MISS haze, `SAVE` ✓/✗ counts for save actions, `PENDING` butter.
- **One row per target:**
  - name, result, damage taken with its type(s), small tags (`½ save`, `½ resist`, `immune`, `×2 vuln`), HP display per visibility (numbers / status word / nothing), condition icons added (existing status icons), `◎ kept` / `◎ lost` for concentration.
  - Pending rows show `⏳ DEX save` plus **[Roll]** for that token's controller.
  - Folded notes (recharge, effects ending, concentration) appear as a muted line under the row.
- Rows beyond 3 collapse into `+5 more ▸`.
- **[＋ Damage]** on HIT rows, for the actor and the GM: a tiny inline input `3d6 piercing`. It rolls and applies to that target inside the same card's undo group. On a crit the dice follow `crit_rule`.
- **Expanded (click the header):**
  - one `RollView` per roll (d20 and damage parts)
  - reasons (`advantage: target is prone; flanking`)
  - modifiers
  - `vs AC 15` / `DC 15` per visibility
  - range and cover notes
  - warnings (`beyond long range`, `no slots left: overspent`, `out of reach`)
- **Undone:** the whole card is dimmed and struck through, with `Undone by Bren` and Redo (↷) for the same person.
- **GM ⋯ menu:**
  - Edit damage (per target, a number). The delta is applied through the HP path with no further resistances.
  - Flip hit/miss.
  - Flip save.
  - Use Legendary Resistance (when it applies; also shown as an inline chip on the failed row to the GM).
  - Apply (in `confirm` mode).
- **Hidden actions:** gm_only card. Players still see the results on the map (HP bubbles and statuses), which is how a GM screen works.

## 4. Architecture and protocol

### 4.1 Action capture (backend, `server/base.py` + new `server/capture.py`)

```python
@dataclass
class Capture:
    kind: str; summary: str
    objects: dict[str, dict]      # id -> {"props": before}, first touch only (+ x/y/width/height if moved/resized)
    created: dict[str, dict]      # id -> object_dict after (templates); before = None
    characters: dict[str, dict]   # id -> sheet before (deep copy)
    turn: tuple[list, dict] | None  # (turn_order, settings) before
    chat: list[ChatMessage]       # new rows, inserted at commit
    chat_updates: list[ChatMessage]  # existing rows whose roll.card changed
    notes: list[list[str]]        # rows from _card() folded into the action card
    card: ChatMessage | None      # the action's card, if any
```

- `ServerBase.capture: Capture | None`. `async with self._action(kind, summary) as cap:` sets it. It is reentrant: an inner `_action` joins the outer one. All handlers already run under `self.lock`.
- **Capture-aware helpers.** When `self.capture` is set:
  - `_set_props`, `_set_sheet`, `_save_turns` record the *before* on first touch, mutate the in-memory state at once (later reads in the same handler see it, as today's code expects), and **do not** commit or broadcast.
  - `_post_chat` appends a row. `_card()` appends to `cap.notes` when a card is being built, otherwise it posts a row.
  - `_fit_tokens` and `obj.create` of templates go into `objects` / `created`.
  - With no capture, every helper behaves exactly as today, so non-combat code is untouched.
- **On exit without error:** one `_commit(kind, summary, data, touched)` that, in the same session:
  - UPDATEs each touched object's changed columns
  - UPDATEs each character's `sheet`
  - UPDATEs `games.turn_order/settings` if touched
  - INSERTs the chat rows (flush for ids)
  - UPDATEs `chat_messages.roll` and `updated_seq` for card updates

  Then, synchronously (no `await` until done, as `_commit` requires): `_publish_objects`, `_broadcast_character` for each, `_broadcast_game` once, chat payloads redacted per viewer, `chat.update` payloads, and the undo push.
- **On exception:** restore every captured before into memory (props, sheet, turn, and delete created objects from `self.objects`), then re-raise. No partial state ever. This also fixes today's multi-commit handlers.
- **Event `data`:**

  ```json
  {"action": {"objects": [{"id","before","after"}],
              "characters": [{"id","before":{"sheet"},"after":{"sheet"}}],
              "turn": {"before": [...], "after": [...]},
              "card": 123}}
  ```

  `before`/`after` keep only the keys that changed (props are diffed by top-level key). `_history_entry.revertible` = `bool(data.get("objects") or data.get("action"))`.
- **Wrap with `_action`:** `on_turn_next` (end/start hooks, ticks, recharge, legendary refill, divider), `on_combat_apply`, `on_sheet_rest`, `on_effect_*`, the death save, and all new `combat.*`.
  - Only `combat.*`, `combat.apply` and HUD damage are **undo steps**. Turn changes and rests are atomic events but not on the Ctrl+Z stack (post-MVP "Previous turn").

### 4.2 Undo by 3-way merge (`backend/app/game/merge.py`, pure)

`revert(before, after, current) -> (value, conflicts)` is applied per touched object's props, per character sheet, and per tracker entry (matched by `id`). Redo is the same function with `before` / `after` swapped.

| Value kind | Rule |
|---|---|
| number (HP, temp, bar values, slot `used`, resource `used`, `moved`, death saves) | `current − (after − before)`, then clamped by the schema (HP 0..max, used 0..max). Undoing round-2 damage after round-3 healing works. |
| list of dicts with `id` (effects) | Remove ids the action added; re-insert ids it removed if absent (concentration-dependent effects come back). |
| list of strings (statuses) | Set ops: remove the added ones, add back the removed ones. |
| dict | Recurse. |
| other scalar / null (`concentrating`, `used.action` bool) | If `current == after` → `before`; else keep current and add a conflict note. |

Rules:
- **Undo never refuses.** Conflicts become a muted card line `partly undone: Goblin B concentration changed since`. Statuses are re-derived with `_with_effects` after the merge.
- After merging a PC sheet, `_sync_tokens` runs inside the same undo capture. The undo is one event (`combat.undo`), the original event gets `reverted_by`, and the card gets `chat.update` (undone).
- A card can span several events (the cast, then PC saves arriving later). `card.seqs` lists them, and Undo reverts all of them newest-first in one capture.
- **Unified Ctrl+Z stack:** steps are `{seq, summary, objects}` (map, existing code) or `{seq, summary, action: true, card}`.
  - `on_undo` dispatches: map steps keep today's strict `_conflict` check, action steps use merge.
  - `combat.undo {card_id}` from the card removes that step from the stack.
  - GM History "Revert" works on action events through the same path.
- **Permission:** the actor may undo their card until the next turn starts. The GM may undo any card at any time.

### 4.3 Resolution pipeline

**`backend/app/rules5e/resolve.py` (pure, no server imports).**

Input:
- `Actor(sheet, effects, conditions, cells, disposition, npc_state)`
- `Target` objects (the same fields plus `health`, `defenses`, `cover`)
- `ActionSpec`
- `Options(crit_rule, flanking)`
- `geometry` facts (distance ft, within reach, flanked)

Output:
- `Resolution(per_target=[TargetResult(d20_roll, outcome, damage_rolls, taken, notes, add_effects, health_after, save)], costs, warnings)`

Order:
1. Range and cover.
2. Adv/dis from `rolls5e.d20_test`, with the new extras: flanking, ranged attack with a hostile within 5 ft, beyond normal range.
3. Attack roll vs AC + cover + `effects5e.ac_bonus`.
4. Crit when nat ≥ `crit_range`, or auto-crit within 5 ft vs paralyzed/unconscious.
5. Damage: every part rolled, `rolls5e.critical(formula, rule)` (`double`: dice ×2; `max`: one set maxed as a flat number + one set rolled).
6. `damage5e.apply` **per part** (resistance per type), temp HP first.
7. Effects.

Save actions roll damage once and resolve each target independently. Dice come from `app.dice.roll`; tests monkeypatch `app.dice.engine._rng` with a seeded `random.Random`.

**`backend/app/rules5e/geometry.py` (pure).** Token cells from x/y/width/height and `grid_size`; distance in feet using the page's diagonal rule; `within(a, b, ft)`; `flanked(attacker, ally, target)` (the line between centres crosses opposite sides or corners of the target's footprint on a square grid; opposite hexes on hex); `left_reach(path, threat, reach)` for opportunity attacks. `_within_5ft` in `sheets.py` moves here.

**`backend/app/game/server/actions.py` (new `ActionsMixin`).** It builds snapshots from tokens and sheets, calls `resolve`, then writes **through the existing helpers** inside `_action`:
- `_write_health`, `_concentration_save`, `_add_effect`, `_set_sheet` for slots and resources
- `_save_turns` for `used` / `attacks` / `moved`
- `_set_props` for `npc` state

Then it builds the card. `on_sheet_cast` becomes a wrapper that calls the same pipeline. `on_sheet_roll` keeps checks, saves and skills. Its `attack` / `damage` branches call `combat.act` with no targets, which gives a card with manual Apply buttons. `!apply`, `!saves` and `!damage` stay for `manual` mode and old cards.

**Pending (two-phase) actions.** A save action with PC targets (`players_roll` on) commits phase 1 (cost, NPC saves resolved and applied, card with `pending` rows) as event 1. Each `combat.roll` resolves one row as a new event appended to `card.seqs`. The pending state lives **in the card JSON** (`card.pending = {action, dc, damage_rolls, rows:[token ids]}`), so it survives a restart. No extra table and no in-memory-only map. `combat.roll_rest` (GM) rolls every pending row of the card at once. Offline controllers' rows are rolled automatically. `confirm` apply mode uses the same mechanism: the resolution is stored in the card, and GM **Apply** commits it.

**Opportunity attacks.** After an `obj.update` move of a token in combat (round ≥ 1), check each hostile token that is not incapacitated, has its reaction unused, and whose reach the mover leaves (`left_reach` along `via` waypoints). Skip if the mover has the Disengage effect. Send `combat.prompt {id, kind: "oa", actor_id, target_id, attack_id}` to its controllers, or to the GMs for monsters. Accepting sends `combat.act` with `reaction: true`, which spends R.

**Card redaction** (`_card_for(player, card)`, also used by the history snapshot in `session.py`). Applied to monster actors and targets:
- d20 and bonus removed if `hide_monster_rolls`
- AC removed unless `show_monster_ac`
- HP per `npc_hp`
- pending payload removed for non-GMs
- GM-only notes (recharge, legendary) removed

The chat payload is serialized once per distinct redaction (GM / everyone else). Card `id` = chat message id.

### 4.4 Protocol (`game/protocol.py` ↔ `net/protocol.ts`, change together)

Client → server:

| Message | Fields | Who |
|---|---|---|
| `combat.act` | `actor_id, action:{kind: attack\|spell\|multiattack\|standard\|legendary, id, slot?}, targets:[{id, cover:0\|2\|5}] (≤50), point?:{x,y}, mode: normal\|advantage\|disadvantage, hidden=false, reaction=false` | controller of actor / GM |
| `combat.apply` (exists) | + runs in a capture; HUD sends it | controller / GM |
| `combat.add_damage` | `card_id, target_id, formula, damage_type` | actor / GM |
| `combat.roll` | `card_id?, token_id, kind: initiative\|save\|death_save\|concentration, mode` | controller |
| `combat.roll_rest` | `card_id?` (none = pending initiative) | GM |
| `combat.undo` / `combat.redo` | `card_id` | actor (own turn) / GM |
| `combat.override` | `card_id, target_id, damage?: int, flip?: hit\|save` | GM |
| `combat.legendary_resistance` | `card_id, target_id` | GM |
| `combat.apply_pending` | `card_id` (confirm mode) | GM |
| `combat.start` | `token_ids` (empty = page default) | GM |
| `combat.begin` | — (auto-rolls still-awaiting entries, round 1, first turn start) | GM |
| `combat.end` | — | GM |
| `combat.initiative` (exists) | kept for "add mid-fight"; honours `initiative_mode` | GM |

Server → client:

| Message | Fields |
|---|---|
| `chat.update` | `message` (redacted for the recipient) |
| `combat.prompt` | `prompt:{id, kind:"oa", actor_id, target_id, attack_id}` (transient) |
| `combat.flash` | `page_id, x, y, size, color` (transient area highlight) |
| `chat` kind `turn` | divider message |

`turn.next` stays, now also allowed in sides mode for any controller of the active side. Flip/override re-resolution reuses the stored d20 and damage rolls from the card and rolls fresh dice only for a branch that never rolled (miss → hit). It runs as merge-undo of the target's row plus a re-apply, in one capture, and updates the same card.

## 5. Data model changes

**Sheet (`rules5e/sheet.py`, pydantic; JSONB, so no DB migration):**
- All new fields have defaults, so old sheets validate unchanged.
- A `model_validator(mode="before")` parses the legacy `Attack.range` text ("reach 10 ft · range 80/320 ft") into the numeric fields when they are missing.

```python
class DamagePart(BaseModel): formula: Formula; type: Text = ""
class Area(BaseModel): shape: Literal["sphere","cylinder","emanation","cone","cube","line"]; size_ft: int (5..500)
class Uses(BaseModel): max: int (1..9); reset: Literal["day","short","long"] = "day"

Attack += extra_damage: list[DamagePart] (≤4)   # primary part stays damage/damage_type: no data migration
          reach: int|None; range_normal: int|None; range_long: int|None   # feet
          cost: Literal["action","bonus","reaction","legendary"] = "action"; legendary_cost: 1..3 = 1
          recharge: int|None (2..6, "5" = 5–6); uses: Uses|None; area: Area|None
          mastery: str|None   # post-MVP, stored now
Sheet  += extra_attack: 1..4 = 1; crit_range: 18..20 = 20
          multiattack: list[{attack_id, count 1..6}] (≤6); multiattack_note: Text
          legendary_uses: 0..5 = 0; legendary_resistance: 0..5 = 0
Spell  += casting_time: Literal["action","bonus","reaction","long"] = "action"
          range_ft: int|None (0 = self, 5 = touch); area: Area|None
          extra_damage: list[DamagePart]
```

`derive()` adds per attack: `parts` (formulas with modifiers), `reach`, `range`.

**Token props (JSONB):**
- `disposition`: `party|neutral|hostile`. Default derived: a linked PC or `controlled_by` = party, else hostile. Set from the context menu (submenu Disposition).
- `npc` (per-token monster state; each Goblin token shares one sheet): `{charged: {attack_id: bool}, uses: {attack_id: used}, legendary_used: int, lr_used: int, lair: bool}`. Stripped by `permissions.visible_props` for non-GM viewers. Mirror the rule in `GameStore.controls` and the frontend side.
- Effects get presets `dodge`, `disengage`, `dashed` (movement +Speed), `grappled_by` (ending tied to the grappler), and `surprised` (initiative only).

**Turn entry (`TurnEntry` in protocol, both sides):** `side: party|hostile|neutral|None`, `awaiting: bool|None` (initiative not rolled), `surprised: bool|None`, `attacks: int|None` (made this turn), `defeated: bool|None` (derived on save for skip). `used` gains no keys: overspend = a second spend while already `true`, recorded as `used.<x>_extra` (int).

**Combat state:** no new flag. `round == 0` with entries = setup; `round ≥ 1` = in combat; `combat.end` → order `[]`, round 0.

**Chat:**
- Card JSON in the existing `chat_messages.roll` JSONB under `card`:

  ```
  {v:1, actor_id, actor_name, action_name, kind, hidden, seqs:[...], undone_by?, rows:[{token_id, name, outcome, d20, ac, dc, save, damage:[{formula,total,type,taken}], tags, effects_added, conc, hp_after}], notes, warnings, pending?}
  ```

- **Alembic migration (the only one):** `chat_messages.updated_seq BigInteger NULL`. Resume (`session.py`) also sends messages with `updated_seq > resume.seq`, and the client upserts by id in append mode.

**Importer (`backend/scripts/import_srd.py`, re-run, then commit the new `data/*.json`):**
- `extra_damage_*` fields → `extra_damage`.
- Reach/range numbers → numeric fields.
- `action_type` BONUS_ACTION / REACTION / LEGENDARY_ACTION → `cost`. "(Costs 2 Actions)" → `legendary_cost`.
- "Recharge 5–6" → `recharge=5`. "(3/Day)" → `uses`.
- The Multiattack description parsed by attack names ("makes three Rend attacks") → `multiattack`. If it can't be parsed: keep the note and leave the list empty.
- "Legendary Action Uses: 3" → `legendary_uses`. "Legendary Resistance (3/Day)" → `legendary_resistance`.
- Save actions: "60-foot Cone" / "20-foot-radius Sphere" → `area`.
- Spells: Open5e `range`, `casting_time`, `shape_type` / `shape_size` → `range_ft`, `casting_time`, `area`; secondary damage types → `extra_damage`.
- Unit tests on stored description fixtures (Adult Black Dragon Rend, a Recharge breath, Mage multiattack).
- NPCs already placed keep their old sheets (they still work). The compendium panel gets "Update from compendium" on an NPC whose `source` matches (GM, one click). Post-MVP if short on time.

## 6. Settings

Values are `Option` entries in `backend/app/game/options.py` (move them from `PLANNED` to `CATALOG` as each one is built). The GM panel is generated from them.

| Key | Section | Kind / options | Default | Label |
|---|---|---|---|---|
| `auto_apply` | Automation | choice: `auto` Automatically, with Undo · `confirm` After the GM confirms · `manual` By hand | `auto` | Apply attack and spell results |
| `players_roll` | Automation | bool | `true` | Players roll their own initiative, saves and death saves (off: rolled for them) |
| `opportunity_prompts` | Automation | bool | `true` | Offer opportunity attacks when a creature leaves reach |
| `initiative_mode` | Combat | choice: `individual` · `grouped` Same monsters together · `sides` Sides | `grouped` | Initiative |
| `initiative_reroll` | Combat | bool | `false` | Reroll initiative every round (rerolls are automatic, no prompts) |
| `track_movement` | Combat | bool | `true` | Track movement and show what is left of the speed |
| `skip_defeated` | Combat | bool | `true` | Skip defeated creatures |
| `flanking` | House rules | choice: `off` · `advantage` · `bonus` +2 to hit | `off` | Flanking |
| `crit_rule` | House rules | choice: `double` Roll the dice twice (rules) · `max` Max dice + roll | `double` | Critical hit damage |
| `potion_action` | House rules | choice: `bonus` Bonus Action (2024 rules) · `action` Action | `bonus` | Drinking a potion. Replaces the planned `potion_bonus_action`. 2024 already makes it a Bonus Action, which meets the owner's house rule. Check the SRD 5.2 Potion of Healing text for administering to others when implementing. |
| `npc_hp` (exists) | Visibility | hidden / status / full | `status` | Monsters' hit points, for players |
| `show_monster_ac` | Visibility | bool | `false` | Show monsters' AC on attack cards |
| `hide_monster_rolls` | Visibility | bool | `true` | Hide monster dice (players see hit, miss and damage) |

Player setting (`players.settings`, ⚙ My settings): `turn_autoselect` bool, `true`, "Select my token when my turn starts".

The owner's requirements map like this:
- auto + undo default → `auto_apply=auto`
- flanking → `flanking`
- max-die crits → `crit_rule=max`
- potion → `potion_action`
- side initiative → `initiative_mode=sides`
- reroll each round → `initiative_reroll`

## 7. Build order

Each step is shippable, with its tests green (`npm test`) and the e2e passing (`npm run e2e`).

**1. Action capture + merge undo.**
- `Capture`, `_action`, capture-aware helpers, rollback on exception, `merge.py`, unified undo stack, revertible action events in History.
- `combat.apply` and HUD `-12 fire` / `+8` in a capture (undo step). `turn.next` and rests wrapped (atomic).
- Tests:
  - `test_merge.py` (every rule)
  - `test_capture.py`: one event row per handler; exception leaves memory unchanged; Ctrl+Z restores PC sheet, tokens and statuses; undo after later healing uses the delta; concentration-dropped effects come back.

**2. Combat card + `combat.act` for attacks.**
- `resolve.py`, `geometry.py` (distance, within), `ActionsMixin`, card JSON, `CombatCard.svelte`, redaction, `chat.update`, `updated_seq` migration plus resume, card Undo/Redo, ＋ Damage.
- The sheet's attack buttons call `combat.act` (still using `store.sheetTarget`).
- Tests: `test_resolve.py` (seeded dice: hit/miss/nat 20/nat 1, auto-crit, resistance per part, temp HP, 0 HP), game-level act → card → undo, redaction per viewer, resume picks up a card update.

**3. Action bar + target mode.**
- `ActionBar.svelte` in the dock, slot auto-fill, keys 1–9, Engine `targeting` branch plus Pixi overlay (line, rings, glow, reticles, badge), A/D/C/Enter/Esc/Shift, last target, economy pips spending `used` / overspend, Atk n/m, End turn ⏎.
- e2e: the player selects a token, presses `1`, clicks the goblin; both tabs show the card; the player clicks Undo and HP comes back in both tabs.

**4. Sheet data + importer.**
- New fields, legacy `range` parsing, `derive` additions, importer parsing plus fixture tests, regenerated `data/*.json`. The Sheet5e editor gets the new fields in compact form (damage parts list, cost, recharge, uses, area).
- Tests: model round-trip of old sheets, importer fixtures.

**5. Spells, saves, areas, prompts.**
- Spells through `combat.act` (attack per target, save with damage rolled once, per-target resolution), slots, concentration in the capture, `sheet.cast` wrapper, pending rows in the card, `combat.roll` / `roll_rest`, `PromptTray.svelte`, circle area targeting plus `combat.flash`, duration spells create a template in the capture.
- Tests: pending survives a server reload (rebuild `GameServer` from the DB); `roll_rest`; half on save; effect on fail.
- e2e: the GM casts a circle spell on 2 goblins plus the PC; the PC answers the save prompt.

**6. Monster kit.**
- Multiattack (click = all, Shift spreads), recharge at turn start (GM note), X/Day pips, `token.props.npc` plus visibility stripping, legendary prompt and Legendary ▾, Legendary Resistance chip.
- Tests: recharge roll on turn start; legendary refill at its own turn; LR flips a failed save inside the same card undo group.

**7. Combat flow.**
- `combat.start/begin/end`, awaiting initiative plus prompts, surprised toggle, `initiative_mode` (individual/grouped/sides with block turns in `_track_movement` and the hooks), `initiative_reroll`, `InitiativeRibbon.svelte`, banner, `turn_autoselect`, turn divider, skip defeated, death save prompt, End combat card (rounds, defeated, XP), "until end of combat" cleanup.
- Tests: sides mode `turn.next` and movement; reroll order; begin auto-rolls the awaiting entries.
- e2e: start → prompt → begin → ribbon highlights → end turn.

**8. Tactics and house rules.**
- Range/long range, ranged-with-adjacent-hostile, cover `C`, `flanking`, `crit_rule=max`, movement budget (Speed, exhaustion, Grappled/Restrained, Dash), `disposition`, standard actions (Dash, Disengage, Dodge, Stand up, Drink potion per `potion_action`, Grapple/Shove as save actions vs DC 8 + Str mod + PB, Other), opportunity attack prompts.
- Tests: geometry flanking cases (square/hex, Large target), crit max formula, OA along waypoints, Disengage suppresses it.

**9. GM control polish.**
- `combat.override` (edit damage, flip hit/save with replayed rolls), `auto_apply` confirm/manual, hidden toggle, `show_monster_ac` / `hide_monster_rolls` wired, settings moved into `CATALOG`. Update the living docs (dev log, Frolls vs Roll20) and the roadmap artifact.

**MVP = steps 1–9.** Post-MVP: 10 named riders, 11 weapon mastery, 12 reaction cards.

## 8. Discarded or deferred, with reasons

| Idea (member 1) | Decision | Reason |
|---|---|---|
| Global `T` pre-target key | Replaced by "Enter = last target" | `t` is the Text tool. "1 → Enter" gives the same one-gesture repeat with no new mode. |
| `H` hidden-roll key in target mode | 👁 toggle on the GM's bar | Discoverable; no extra key to remember. |
| Mouse wheel to change slot level | `+` / `-` in target mode, Spells ▾ | The wheel zooms the map. Reassigning it would surprise users. |
| Start-combat modal dialog | Tracker setup phase (round 0) with ☐ Surprised per row | No modal. Same clicks, and it stays visible while the players roll. |
| Waiting for every save before applying | Each target resolves when its save arrives | Nothing stalls on one slow player. Damage is still rolled once. |
| Lettering identical monsters (Goblin A/B/C) at combat start | Dropped | Placement already numbers tokens. Renaming tokens mid-session confuses players. |
| Persistent template for every area spell | Only spells with a duration | Instantaneous areas would litter the map. A 3 s flash shows the area. |
| Server recomputing area targets | Client sends the confirmed list | The user confirms visually anyway. Avoids keeping two identical geometry implementations in sync; the GM keeps freedom. |
| Switches `npc_saves`, `legendary_resistance`, `legendary_prompt`, `recharge`, `concentration`, `death_saves`, `area_targets`, `range_check`, `action_economy`, `mastery`, `npc_zero_hp`, `crit_scope`, `double_total`, `npc_save_dc`, `players_end_turn`, `pc_initiative`, `turn_follow_camera`, `confirm_targets` | Merged or dropped | Each one either never blocks (warnings, prompts with ×), is one click to override (card ⋯, Undo), or merges into `players_roll` / `auto_apply`. Fewer switches = fewer support questions, which is the Midi-QOL lesson. |
| Undo refusing on "changed since" for combat | Merge with delta | In combat something always changed since. Refusal would make Undo useless after one round. |
| Override as a separate delta event | Override = merge-undo of the row + re-apply, in one capture, same card | One code path (merge), no second bookkeeping system. |
| Rider presets in MVP | Generic ＋ Damage in MVP, presets post-MVP | ＋ Damage covers Sneak Attack, Hex, Hunter's Mark and Smite dice now with one tiny feature. Presets add conditions and once-per-turn logic. |
| Weapon Mastery in MVP | Post-MVP step 11 (fields stored now) | Needs per-character mastery choices and 8 behaviours. Effects plus ＋ Damage cover it by hand meanwhile. |
| Reaction prompts with timeouts | Never | Blocking the table is the top complaint about over-automation. OA is a non-blocking prompt. |
| Cone, line and cube targeting | Shift-click fallback; owner decision later | The owner removed those tools. |
| Help, Hide, Search and other actions automated | "Other" spends the action and posts a line | Low value per complexity. The GM adjudicates. |
| Auto cover from walls, difficult terrain, turn timers, encounter builder, combat-only chat filter | Post-MVP or never | No walls before dynamic lighting. The rest is prep or pressure, not combat flow. |
| A new `combat.active` flag | Use `round` | The existing state already encodes setup and in-combat. |
| A separate pending-actions table or in-memory map | Pending lives in the card JSON | Survives restarts, is visible to everyone, and needs no extra persistence. |
