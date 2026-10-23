# Frolls characters: sheet, creation, levelling and inventory (final spec)

This is the final spec for council area B. It merges member 1's gameplay proposal (`council-B1.md`) with the UX and architecture review, and it is aligned with the final combat spec (`council-A-final.md`).

**Ownership:**
- **Combat owns** the action bar, target mode, `combat.act`, cards, undo, prompts, per-token monster state (`token.props.npc`), and the combat fields on `Attack` and `Spell`.
- **This area owns:**
  - the sheet data model, `normalize()` and `derive()`;
  - inventory, class and origin data, the importer v2;
  - the play/edit sheet, the NPC stat block view, the creation wizard, level-up and homebrew lite.

Code references are to the current repo.

---

## 1. Summary

**Store choices, compute the rest.** The sheet stores what the player decided:
- the build record (class, subclass, background, species, lineage, base scores, choices, HP rolls);
- inventory and currency;
- current state (HP, used slots and uses, spells known and prepared, notes).

Two pure server functions compute everything else:
- **`normalize(sheet)`** writes the "materialized" fields that existing server code already reads as stored values: `level`, `abilities`, `hp.max`, `ac`, `speed`, slot maximums, resource maximums, save proficiencies, auto features, `extra_attack`, `crit_range`. It runs on every sheet write. `combat.py`, `sheets.py` and `damage.py` keep working unchanged.
- **`derive(sheet)`** produces the read-only view: bonuses, effective attacks (weapons + custom), and a single ordered **`derived.actions`** list. The sheet's Actions tab, the NPC stat block and the combat action bar all render from that one list.

**Other key decisions:**
- **One pipeline.** Using a potion, Second Wind or Rage is a `combat.act` with `action.kind: "item" | "feature"`. That means it is undoable, posts a card, and spends the right economy. There is no separate `item.use` path.
- **Small sheets, because every HP change rebroadcasts the whole character.** SRD text is not copied into sheets: spells, features and items store a `ref`, and the client fetches text on demand (`compendium.texts`). Budget: about 12 KB for a typical PC sheet.
- **Data-driven wizard and level-up.** `build.pending(build)` returns a list of typed choices. Four generic widgets render every choice. The server is the only rules implementation: the client asks for `char.build_preview` (dry run, about 2 ms) and duplicates no rules in TypeScript.
- **Five game switches** (down from member 1's 18), no per-player switch.

---

## 2. Final feature list

### MVP

| # | Feature | What it does |
|---|---|---|
| C1 | Sheet v2 model + migration | Build record, inventory, currency, feature list, refs, NPC text fields. One-time data migration plus a validator that upgrades anything old. |
| C2 | `normalize()` + `derive()` | Class/origin data drive level, HP, saves, slots, resources, features, AC, speed, Extra Attack and crit range. `derive` adds effective attacks, the `actions` list, spell counts, carrying, warnings and pending count. |
| C3 | Importer v2 | Classes, subclasses, species, backgrounds, feats, weapons, armor, gear and magic items, plus curated patches (`class_rules.py`). Monsters and spells are regenerated with the combat fields and a feature list. |
| C4 | Play / Edit sheet | Opens in Play mode with tabs Actions, Spells, Inventory, Features and Bio. A ✎ toggle switches to Edit, which reuses the current `Sheet5e` form per tab. |
| C5 | Inventory | Equip, attune, quantity, charges, currency with relative input, weight, encumbrance (switch). Weapons become attacks and armor sets AC. Consumables and features with a `use` go through `combat.act`. Add from compendium or as a custom item; GM drags an item onto a token; Give to a token. |
| C6 | Class features & resources | Auto-managed resources with rest rules (including "regain one on a short rest"), feature cards grouped by source with uses pips, plus a short list of number-changing hooks (section 6.4). |
| C7 | Spells tab | Attack, DC, "Prepared n/max", "Cantrips n/max" (warning only), Pact slots, add spells from your class list, always-prepared spells. |
| C8 | NPC stat block view | Play-mode stat block in the 2024 layout. Every action is a button that uses combat's action path. Shows the per-token state (recharge, X/Day, legendary pips) when opened from a token. |
| C9 | Creation wizard | Five steps, Quick build, server-rolled 4d6, live summary from the server preview, "skip → pending choices", optional token placement. Also used to **Rebuild** an existing character. |
| C10 | Level-up | A single dialog showing what you gain, HP (average or roll), that level's pending choices, and Confirm. One event, which the GM can revert from History. |
| C11 | Rests extension | Long rest restores item charges ("dawn"), Pact slots refresh on a short rest, and "regain one" resources. Humans regain Heroic Inspiration. |
| C12 | Heroic Inspiration star, XP | A star toggle in the header. `xp` field with a glowing "Level up" chip when the XP threshold is reached. |
| C13 | Homebrew lite | GM "Save to homebrew" on an item, a spell or an NPC. Saved entries appear in search with 🏠, and the GM chooses whether players can see each one. |

### Post-MVP (in this order)

1. Weapon Mastery automation. This is combat's post-MVP step 11. The wizard already records the mastery choices, and weapon rows show them as tags.
2. Heroic Inspiration "Reroll" on your own d20 cards.
3. Multiclass UI. The model already supports `build.classes` with up to 4 entries; `HitDice` becomes a per-die pool.
4. Character JSON export/import.
5. Homebrew classes, species, backgrounds and feats (wizard schema).
6. Wizard spellbook (known versus prepared), Great Weapon Fighting automation, ammunition tracking.
7. "Update from compendium" for NPCs already placed. This is shared with combat.

---

## 3. UI spec

All colours come from `theme.ts` tokens. Panels use `.panel` and `--gradient-surface`, corners are 10–12 px, and focus uses `--glow`. Two new palette tokens are needed:
- **`--roll-attack`** (violet outline chip) for to-hit values;
- **`--roll-damage`** (peach filled chip) for damage values, so damage is visibly different from attack.

### 3.1 Sheet window (`CharacterSheet.svelte` shell, 980 × min(760, 90vh), resizable)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ [avatar] Mira Thorne   Rogue 5 · Halfling · Criminal  ⚠2 pending  ★  ✎  ☾▾  ✕  │
│ [AC 15] [HP 31/38 +5 ▸ −/+ ] [Init +4] [Speed 7.5 m] [PB +3] [Pass. Perc 13]   │
│ chips: Poisoned · Bless ⏳ · Exhaustion 1 (−2) · ⚠ Untrained armor              │
├──────────────────────┬────────────────────────────────────────────────────────┤
│ STR  8 −1   save −1  │ Actions  Spells  Inventory  Features  Bio              │
│ DEX 18 +4   save +7● │ ACTION ─────────────────────────────── Attacks 1 ─── │
│ CON 14 +2   save +2  │  ⚔ Shortsword   (+7)  [1d6+4 piercing]   5 ft   Vex    │
│ INT 13 +1   save +4● │  🏹 Shortbow    (+7)  [1d6+4 piercing]   24/96 m        │
│ WIS 10 +0   save +0  │  ✊ Unarmed     (+2)  [1 bludgeoning]                  │
│ CHA 12 +1   save +1  │  hint: Sneak Attack 3d6 (use ＋ Damage on a hit)        │
│ ── skills ────────── │ BONUS ACTION ──────────────────────────────────────── │
│ ◆ Stealth +10        │  🧪 Potion of Healing ×2   [2d4+2 healing]             │
│ ● Acrobatics +7      │ REACTION ──────────────────────────────────────────── │
│   Arcana +1  …       │  Uncanny Dodge                                         │
│ ── proficiencies ─── │ LIMITED USES ──────────────────────────────────────── │
│ Armor, weapons, lang │  Luck ●●○  (long rest)                                 │
└──────────────────────┴────────────────────────────────────────────────────────┘
```

**Header:**
- **HP box:** click opens an inline input that accepts `-7`, `-7 fire`, `+5`, `+5 temp`. This sends `combat.apply` with `character_id` (alignment request to combat, section 7).
- **☾▾ rest menu:** Short rest, Long rest, Hit die (existing `sheet.rest`).
- **★ Heroic Inspiration:** toggles with one click (the GM or the owner).
- **⚠ n pending:** reopens the wizard on only the pending choices.
- **Death saves** replace the HP box at 0 HP (existing behaviour).

**Left column:** always visible.
- Click an ability, save or skill to roll it (existing `sheet.roll`). Shift-click rolls with advantage, Ctrl-click with disadvantage.
- Markers: ● proficient, ◆ expertise.

**Tabs:**
- **Actions** (default) is `ActionList` grouped by cost.
- **Spells** is hidden if the character has no spellcasting and no spells.
- **Bio** is the existing bio, notes and attributes view, moved into the shell.

**Click behaviour:**
- Clicking any action row calls `startAction(entry)`, which is combat's target mode on the character's token on the current page. With no token, it sends `combat.act` with no targets and the card gets manual Apply buttons (combat spec 4.3).
- The bracketed damage chip on a row shows the formula only. Damage is rolled by the action.

**Play / Edit:**
- **✎** switches the same tabs to Edit mode. While the sheet window has focus, `E` also toggles. The window stops propagation, so the map's Eraser shortcut does not fire.
- The last mode is remembered per character in `localStorage` (wrapped in try/catch). There is no per-player game setting.
- The sheet always opens in Play mode for players who cannot edit.

**Edit mode** in a built sheet:
- Fields that come from the build show a 🔒 with the tooltip "From Rogue 5: change it with Level up or Rebuild".
- Allowed overrides: **AC**, **Speed** and **HP max bonus** (`overrides`).
- Extra buttons: **Level up**, **Rebuild**, **+ Feature**, **+ Attack** (custom), **+ Resource** (custom).

**Opening the sheet:**
- `store.openCharacter(id, tokenId?)`. Opening it from a token (the HUD name, or double-click on a linked token) passes the token, so NPC per-token HP and state show.

### 3.2 Features tab

- Collapsible cards grouped by source: Class, Subclass, Species, Background, Feats, Custom.
- Each card shows the name, a level tag and a uses-pips widget when it has a resource.
- **Use** appears when the feature has a `use`.
- Passive cards are collapsed by default. Expanding fetches the text by `ref` (cached), rendered with `util/minimd.ts`, which handles paragraphs, bold, lists and pipe tables, and escapes HTML.

### 3.3 Spells tab

- **Header line:** `Spell attack +7 · Save DC 15 · Prepared 6/7 · Cantrips 3/3`. A count over its limit turns rose; it warns and never blocks.
- **Slots:** a pips row per level, with Pact slots on their own row labelled "Pact Lv 3".
- **Play mode:** only cantrips and prepared or always-prepared spells, grouped by level.
  - Each row shows a casting-time tag (A / BA / R / 1 min+), ◎ for concentration and ® for ritual.
  - Clicking a row casts it (combat target mode). Expanding shows the text.
- **Edit mode:** prepare checkboxes. **+ Add spell** is an `ItemPicker`-style search over spells filtered to your classes' lists, with an "All spells" toggle.

### 3.4 Inventory tab

```
 [cp 0] [sp 14] [ep 0] [gp 112] [pp 0]        Attuned 1/3     ▰▰▰▱▱ 48/120 lb (only if encumbrance)
 EQUIPPED
  🛡 Studded Leather     12 + Dex          ◉ equipped            13 lb        ⋯
  ⚔ Shortsword +1       ♦ attuned? –       ◉                      2 lb        ⋯
 CARRIED
  🧪 Potion of Healing   ×2  [Use]                                 1 lb        ⋯
  🪄 Wand of Magic Missiles  ●●●●○○○   ♦                           1 lb        ⋯
  🎒 Explorer's Pack …
 [+ Add item]
```

- **Currency pill:** click to edit; accepts `+50` or `-3`.
- **Equip toggle:**
  - equipping armor unequips the other armor;
  - only one shield;
  - two-handed weapon plus shield gives a warning chip, not a block.
- **Row interactions:** clicking the name expands the text. The quantity stepper appears on hover. Clicking a charges pip spends or restores a charge.
- **⋯ menu:**
  - Give… (combat-style target mode: click a token);
  - Edit (inline form, as attack rows are edited today);
  - Delete;
  - Save to homebrew (GM).
- **+ Add item:** `ItemPicker` popover with search over items, magic items and homebrew, a kind filter, and "Custom item" at the bottom. It sends `item.add`.
- **GM drag:** dragging an item from the Compendium panel (new **Items** kind) onto a token or an open sheet sends `item.add`.

### 3.5 NPC stat block (`StatBlock.svelte`, Play mode for `kind: "npc"`)

```
 Goblin Warrior                                   ✎  ✕
 Small Fey (Goblinoid), Chaotic Neutral
 AC 15   Initiative +2 (12)   HP 10/10 (3d6)   Speed 9 m
 ┌ STR 8 −1 −1 │ DEX 15 +2 +2 │ CON 10 +0 +0 │ INT 10 │ WIS 8 │ CHA 8 ┐   (mod, save)
 Skills Stealth +6 · Senses Darkvision 18 m, Passive Perception 9 · Languages Common, Goblin
 CR 1/4 (XP 50; PB +2)
 TRAITS        Nimble Escape …
 ACTIONS       [Scimitar] Melee +4, 5 ft. 5 (1d6+2) slashing.   [Shortbow] …
 BONUS ACTIONS …     REACTIONS …
 LEGENDARY ACTIONS ◆◆◇ (per token)    [Breath Weapon ⚡ Recharge 5–6]  (dim when spent)
```

- Action names are buttons that use the same `startAction`.
- Recharge, X/Day and legendary pips read `token.props.npc` (combat spec M6) when a token was passed. Otherwise they show only the maximums.
- HP shows the token's HP when one was passed.
- Edit mode is the existing form plus the new fields.

### 3.6 Creation wizard (`wizard/CharacterWizard.svelte`, modal 1000 × 680)

**Opened from:**
- the Journal's **+ Character** button (the GM always; players when `player_creation` is on);
- a soft banner "Create your character" for a player who controls no character;
- **Rebuild** and **⚠ pending**.

**Layout:**
- **Left rail:** the steps ①–⑤, each with a check or a "skipped" dot.
- **Centre:** the current step.
- **Right:** `BuildSummary`, a live mini-sheet from `char.build_preview` (AC, HP, saves, skills, attacks, spells, pending count), debounced 150 ms.

**Keys:** `Enter` = Next, `Shift+Enter` = Back, `Esc` = close (the draft is kept in `localStorage`).

**Steps:**
1. **Class and level:**
   - 12 class cards (name, one-line pitch, primary ability; "Simple to play" tag on Fighter, Barbarian and Rogue);
   - level stepper (default `start_level`);
   - **⚡ Quick build** gives recommended choices for everything and jumps to step 5.
2. **Origin:**
   - background card (shows its 3 abilities, feat and skills);
   - ability increase as +2/+1 or +1/+1/+1, with a "Recommended" button;
   - species card, then a lineage or ancestry picker if the species has one.
3. **Ability scores:**
   - tabs for the methods allowed by `ability_scores`:
     - Standard array: click a value, then an ability;
     - Point buy: 27 points, 8–15;
     - Roll: the server rolls and posts to chat, then you assign like the array;
     - Manual;
   - "Auto for my class" assigns by primary-ability priority;
   - totals show base + background (max 20).
4. **Choices.** Every item from `pending()` for levels 1..N except the step 2 ones and equipment, as a checklist of collapsible widgets:
   - skills;
   - expertise;
   - Fighting Style;
   - masteries;
   - subclass (pre-selected when there is only one SRD option);
   - ASI or feat;
   - Epic Boon;
   - cantrips and spells, with a "Suggested" button from the curated starter lists;
   - origin feat sub-choices (Magic Initiate list and spells, Skilled skills);
   - languages.
5. **Equipment and details:**
   - class equipment A/B and background equipment A/B (radio cards listing the items);
   - name; avatar through the existing Token Stamp;
   - **Review**: big AC, HP and attacks;
   - **☐ Place my token** (default on), placed at the centre of my current view;
   - **Create**.

**Every step has "Skip for now".** Skipped choices stay in `pending()` and appear as the header badge.

**Choice widgets (four only):**
- `PickN`: chips or cards with search; used for skills, expertise, masteries, cantrips, spells, languages, feats, lineage, subclass, Fighting Style and Epic Boon;
- `AbilityAssign`;
- `AsiOrFeat`;
- `EquipmentPick`.

### 3.7 Level-up dialog (`LevelUpDialog.svelte`, 640 px)

- **Title:** `Level 6 · Rogue`, from the preview with level + 1.
- **"You gain":** feature cards (names, expandable text), plus derived changes as chips: `PB +3 → +4`, `Sneak Attack 3d6 → 4d6`, `Slots: +1 Lv 3`, `Prepared 6 → 7`.
- **HP:** `[Average +6]` / `[Roll d8+2]`, depending on `hp_on_level`. A roll is made by the server on Confirm and posted to chat.
- **Pending choices for this level:** the same widgets.
- **Confirm** (Enter).

**Access:**
- The player when `player_creation` is on.
- The GM always.
- The play-mode header shows a glowing **Level up** chip when `xp` reaches the next threshold. The button is always present in Edit mode.

---

## 4. Data model and migration

### 4.1 Pydantic (`backend/app/rules5e/sheet.py`), mirrored in `frontend/src/lib/net/protocol.ts`

All new fields have defaults. Combat's fields are listed in combat spec section 5 and are not repeated here: `extra_damage`, `reach`, `range_*`, `cost`, `recharge`, `uses`, `area`, `mastery`, `extra_attack`, `crit_range`, `multiattack`, `legendary_*`, and on `Spell` `casting_time`, `range_ft`, `area`.

```python
SHEET_VERSION = 2
Key = Annotated[str, Field(max_length=80)]          # compendium/homebrew key, "" = none
Cost = Literal["action", "bonus", "reaction", "other"]

class Use(BaseModel):                               # what a consumable or feature does when used
    kind: Literal["heal", "temp", "damage", "save", "effect"]
    formula: Formula = ""                           # "2d4+2", "1d10+@level"
    damage_type: Text = ""
    save: Ability | None = None
    dc: Annotated[int, Field(ge=1, le=40)] | None = None
    effect: Annotated[str, Field(max_length=30)] | None = None   # effects.py preset
    cost: Cost = "action"
    target: Literal["self", "creature"] = "creature"
    consume: bool = True                            # item: qty −1 / feature: resource −1

class WeaponData(BaseModel):
    category: Literal["simple", "martial"] = "simple"
    melee: bool = True
    damage: Formula = "1d6"
    damage_type: Text = "slashing"
    versatile: Formula = ""
    properties: list[Literal["finesse","light","heavy","thrown","two_handed","reach",
                             "ammunition","loading"]] = []
    range_normal: int | None = None; range_long: int | None = None   # feet
    mastery: Text = ""

class ArmorData(BaseModel):
    category: Literal["light", "medium", "heavy", "shield"]
    base: Annotated[int, Field(ge=0, le=30)] = 10   # shield: 2
    dex_cap: int | None = None                       # None = no cap, 0 = no Dex
    str_req: int | None = None
    stealth_dis: bool = False

class Charges(BaseModel):
    max: Annotated[int, Field(ge=1, le=50)]; used: Annotated[int, Field(ge=0, le=50)] = 0
    reset: Literal["dawn", "long", "short", "none"] = "dawn"   # dawn = applied on a long rest
    regain: Formula = ""                                       # "" = all, else "1d6+1"

class Item(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=36)]
    ref: Key = ""                                    # SRD/homebrew key; text comes from it
    name: Text = "Item"
    kind: Literal["weapon","armor","shield","consumable","gear","tool","focus","ammo","wondrous"] = "gear"
    qty: Annotated[int, Field(ge=0, le=9999)] = 1
    weight: Annotated[float, Field(ge=0, le=2000)] = 0   # lb per unit
    equipped: bool = False
    attuned: bool = False
    requires_attunement: bool = False
    proficient: bool | None = None                   # None = from class training
    weapon: WeaponData | None = None
    armor: ArmorData | None = None
    bonus_hit: Small = 0; bonus_dmg: Small = 0; bonus_ac: Small = 0; bonus_save: Small = 0
    charges: Charges | None = None
    use: Use | None = None
    notes: Annotated[str, Field(max_length=2000)] = ""   # custom text only

class Currency(BaseModel):
    cp: int = 0; sp: int = 0; ep: int = 0; gp: int = 0; pp: int = 0   # each 0..10_000_000

class Feature(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=36)]
    ref: Key = ""
    name: Text = "Feature"
    source: Literal["class","subclass","species","background","feat","custom","monster"] = "custom"
    level: Annotated[int, Field(ge=0, le=20)] = 0
    text: Annotated[str, Field(max_length=4000)] = ""   # custom/monster text; SRD via ref
    cost: Cost | Literal["passive"] = "passive"
    resource_id: str | None = None
    use: Use | None = None
    auto: bool = False                                # managed by normalize(); not user-deletable

class ClassLevel(BaseModel):
    key: Key; subclass: Key = ""; level: Annotated[int, Field(ge=1, le=20)] = 1

class Build(BaseModel):
    classes: Annotated[list[ClassLevel], Field(max_length=4)] = []   # [] = hand-made sheet
    background: Key = ""; species: Key = ""; lineage: Key = ""
    base_scores: Abilities | None = None              # before background and ASIs
    method: Literal["array", "buy", "roll", "manual"] = "manual"
    bg_increase: dict[Ability, Literal[1, 2]] = {}    # sums to 3, keys in the background's 3
    hp_rolls: Annotated[list[Annotated[int, Field(ge=1, le=12)]], Field(max_length=19)] = []
    # choice id -> picked keys. Ids are stable strings made by pending():
    # "<class>:<level>:skills", "<class>:<level>:asi" (["str","dex"] or ["feat:<key>"]),
    # "bg:feat:<key>:spells", "custom:skills", "custom:expertise", ...
    choices: dict[Annotated[str, Field(max_length=80)], Annotated[list[Key], Field(max_length=20)]] = {}

class Overrides(BaseModel):
    ac: Annotated[int, Field(ge=0, le=40)] | None = None
    speed: Annotated[int, Field(ge=0, le=500)] | None = None
    hp_max_bonus: Annotated[int, Field(ge=-999, le=999)] = 0

class PactSlots(BaseModel):
    level: Annotated[int, Field(ge=1, le=5)] = 1
    max: Annotated[int, Field(ge=0, le=4)] = 0
    used: Annotated[int, Field(ge=0, le=4)] = 0

# Additions to existing models
Resource += source: Key = ""                         # class_rules RESOURCES key → auto-managed
            short_regain: Literal["all", "one"] | None = None   # None: from `reset`
Spell    += ref: Key = ""; always_prepared: bool = False; source: Key = ""
            resource_id: str | None = None           # free cast (lineage, Magic Initiate)
            auto: bool = False
Spellcasting += pact: PactSlots | None = None
Sheet    += v: int = SHEET_VERSION
            build: Build = Build()
            overrides: Overrides = Overrides()
            inventory: Annotated[list[Item], Field(max_length=200)] = []
            currency: Currency = Currency()
            features: Annotated[list[Feature], Field(max_length=150)] = []   # was str
            notes: Annotated[str, Field(max_length=20_000)] = ""             # old `features` text
            heroic_inspiration: bool = False
            xp: Annotated[int, Field(ge=0, le=10_000_000)] = 0
            alignment: Text = ""; senses: Text = ""; languages: Text = ""
            proficiencies: Annotated[str, Field(max_length=1000)] = ""   # hand-made sheets only
```

**Removed:** `Sheet.ac` stays but becomes materialized: `normalize` computes it unless `overrides.ac` is set. `classes`, `species` and `background` stay as display text, written by `normalize` for built sheets.

### 4.2 Upgrading old sheets

`upgrade(raw: dict) -> dict` in `sheet.py` is pure and idempotent. It is called by `Sheet.model_validator(mode="before")` when `raw.get("v", 1) < 2`:

1. If `features` is a `str`, move it to `notes` and set `features = []`. For NPCs from the compendium the importer v2 provides the split list instead (see "Update from compendium", post-MVP).
2. `overrides.ac = raw["ac"]` for PCs. This keeps the typed AC until the player clears the override. NPCs keep a stored `ac` with no armor in inventory, which normalizes to the same value.
3. For each spell whose `id` is a compendium spell key and whose `description` equals the compendium text: set `ref = id` and `description = ""`. This shrinks the sheet; the cast card falls back to the compendium text.
4. `v = 2`.

**Where it runs:**
- **Alembic data migration** `sheet_v2`: Python loop over `characters` that rewrites `sheet = Sheet.model_validate(upgrade(s)).model_dump()`. Down-migration is not supported (documented). The DB is then uniform.
- **The validator** catches anything else: compendium JSON from before regeneration, event `before`/`after` snapshots used by merge-undo, and clients still sending old shapes.

**The `normalize` contract:**
- `normalize(Sheet) -> Sheet` is pure and idempotent; a property test checks `normalize(normalize(s)) == normalize(s)`.
- It is called in `JournalMixin._character_values` (every `char.update` with a sheet), in `char.build`, in `char.level_up`, in the migration, and after merge-undo of a sheet (combat capture).
- **With `build.classes == []`** (hand-made sheets and NPCs), it only does inventory work: AC from equipped armor if any armor is equipped and there is no override, clamps, and `classes` text untouched. **Hand-made sheets therefore keep working exactly as today.**

### 4.3 Materialized fields (built sheets only)

| Field | Rule |
|---|---|
| `level`, `classes`, `species`, `background` | Sum of class levels; display names ("Rogue 5"). |
| `abilities` | `base_scores` + `bg_increase` + ASI choices, each capped at 20. In Edit mode the user edits **base scores**. |
| `save_proficiencies` | First class's saves, from patched data. |
| `skills` | Choices: class, background, species, feat and `custom:skills`. Expertise = 2. |
| `hp.max` | Hit die max at level 1 + Σ `hp_rolls` (the average is stored as the roll value) + Con mod × level + hooks (Dwarven Toughness) + `overrides.hp_max_bonus`. `hp.current` is clamped. Raising Con updates HP retroactively, as the rules say. |
| `hit_dice.die` | First class die. The total stays `level` (existing). |
| `ac` | `overrides.ac`, otherwise the best formula (section 6.2). |
| `speed` | `overrides.speed`, otherwise species speed + class hooks − heavy-armor Strength penalty (−10). Encumbrance is applied here when the switch is on, because the inputs are all in the sheet. |
| `spellcasting.ability`, `slots[*].max`, `pact` | Class caster type and table (full; half rounded up, which gives slots at level 1 in 2024; pact). Existing `used` values are kept and clamped. |
| `resources` | Auto resources (`source` set) are created, updated (`max`, `reset`) or removed per `class_rules.RESOURCES`. Custom resources are untouched. |
| `features` | Auto features (`auto: True`) for every class, subclass, species, background and feat gained, with `ref` and no text. Custom features are untouched. |
| `spells` | Auto spells (always prepared: lineage spells, subclass spells) added or removed. Chosen spells come from `choices` the first time only; afterwards the player manages them in the Spells tab. |
| `extra_attack`, `crit_range` | From class hooks (Fighter 2/3/4 at 5/11/20, other martials 2 at 5; Champion 19, then 18 at 15). |

**Computed in `derive` only, never stored:** armor and weapon training, Alert initiative, Jack of All Trades, Archery bonus.

---

## 5. Importer v2 (`backend/scripts/import_srd.py`)

- **Fetch:**
  - use `document__key__in=srd-2024` everywhere (the plain filter leaks 2014 rows on weapons, items and magic items);
  - `limit=200`;
  - curl with `--ssl-no-revoke` on Windows.
- **Cache:** raw pages go to `backend/scripts/.open5e-cache/` (gitignored) so parsing can be re-run offline.
- **Structure:** parsing is split into pure functions (`parse_class`, `parse_species`, `parse_background`, `parse_item`, `parse_magic_item`, `monster`, `spell`), tested on small fixtures in `backend/tests/fixtures/open5e/`.
- **Output:** compact JSON (`separators=(",",":")`), committed, loaded lazily with `@cache`.

| File | Content | Budget |
|---|---|---|
| `classes.json` | 12 classes: `key, name, hit_die, caster (full/half/pact/none), spell_ability, saves, skill_choice {count, options}, armor, weapons (simple/martial/"martial_finesse_light"), tools, primary, table {column: [20]}, features [{key, name, level, text}], subclasses [{key, name, features[...]}]`. Saves and missing columns are patched from `class_rules.py` **at import**, so the JSON is correct. | ≤ 260 KB |
| `origins.json` | `species [{key, name, sizes, speed, traits [{key, name, text}], lineages [{key, name, traits, spells_by_level}]}]`, `backgrounds [{key, name, abilities[3], feat, skills[2], tool, equipment {A: [[item_key, qty]], B_gp}}]`, `feats [{key, name, category (origin/general/fighting_style/epic_boon), repeatable, prereq_level, text}]` | ≤ 60 KB |
| `items.json` | Mundane and magic items in one list: `key, name, kind, category, rarity|null, cost_gp, weight, requires_attunement, weapon?, armor?, bonus_* parsed, charges? parsed ("has N charges", "regains XdY(+Z) expended charges daily at dawn"), use? (curated map for potions, e.g. Healing 2d4+2, Greater 4d4+4…), text, bases? (magic variants collapsed: "Adamantine Armor" once with `bases: [armor keys]`, chosen when added)`. About 200 mundane + about 400 magic. | ≤ 380 KB |
| `monsters.json` | Regenerated with combat's fields; traits → `features` (source `monster`); `alignment`, `senses`, `languages`; action text kept only in `Attack.notes`, no longer duplicated in a text blob. | ≤ 600 KB |
| `spells.json` | Regenerated with combat's fields; `classes` kept for list filtering. | ≤ 400 KB |

The total of about 1.7 MB is loaded once per process, about 10 MB as Python objects. `test_importer.py` asserts the size budgets.

**Curated code (`backend/app/rules5e/class_rules.py`, about 300 lines, hand-written, unit-tested):**
- `CLASS_PATCHES`: saves for all 12 classes; Wild Shape and Unarmored Movement columns.
- `RESOURCES`: `key → ResourceRule(name, applies(ctx), max(ctx), reset, short_regain, feature_key)`. Covers Rage, Bardic Inspiration (Font at 5 = short), Channel Divinity, Focus Points, Sorcery Points, Second Wind, Action Surge, Indomitable, Lay on Hands pool, Wild Shape, Arcane Recovery, Breath Weapon (PB), Large Form, Adrenaline Rush, Stone's Endurance and lineage free casts. Formulas are Python lambdas over a `ctx` (levels, PB, modifiers), so they are not stored in the sheet and there is no expression language.
- `HOOKS`: Extra Attack levels, crit range, Unarmored Defense formulas, Fighting Styles (Archery, Defense, Two-Weapon Fighting), Alert, Jack of All Trades, Dwarven Toughness, Martial Arts die, Sneak Attack dice, Rage damage, Monk and Barbarian speed.
- `FEATURE_USES`: feature key → `Use`:
  - Second Wind: heal `1d10+@fighter_level`, bonus action, self;
  - Rage: effect `rage`, bonus action, self;
  - Bardic Inspiration: effect `bardic_inspiration`, bonus action;
  - Breath Weapon: save, damage by level, area.
- `STARTING_EQUIPMENT`: class → `{A: [[item_key, qty]], B_gp}`, hand-mapped (12 strings; parsing markdown is not worth it).
- `STARTER_SPELLS`: class → suggested cantrips and level-1 spells (SRD only).
- `RECOMMENDED`: class → ability priority, background, skills and Fighting Style (used by Quick build and "Recommended").
- `XP_TABLE`: 20 thresholds from SRD 5.2.

**Legal guard.** `test_importer.py` fails if any generated name matches a blocklist of non-SRD IP ("Beholder", "Mind Flayer", "Sharpshooter", "Great Weapon Master", …). The wizard offers only keys present in the data or in the game's homebrew.

---

## 6. Server logic

### 6.1 Modules

- `rules5e/sheet.py`: models, `upgrade`, `derive`.
- `rules5e/build.py` (new, pure):
  - `normalize(sheet)`;
  - `pending(sheet_or_build) -> list[Choice]`;
  - `validate_choices(build) -> list[ChoiceError]`;
  - `apply_build(sheet, BuildInput) -> Sheet`;
  - `level_up(sheet, class_key, hp_roll: int | None, choices) -> Sheet`;
  - `quick_build(class_key, level) -> BuildInput`;
  - `diff_gains(before, after)`, used by the level-up preview.
- `rules5e/inventory.py` (new, pure): `armor_class`, `weapon_attacks`, `carrying`, `attuned`, `equip(sheet, item_id)` (unequip rules), `regain_charges(sheet, roll)`.
- `rules5e/class_rules.py`: curated data (section 5).
- `compendium/__init__.py`: `entries(kind)` extended to `item`, `class`, `species`, `background`, `feat` (+ homebrew merge); `texts(refs)`; `catalog()` (wizard summaries, no long text).

**`Choice`:**

```python
Choice = {id, kind: "pick" | "abilities" | "asi_or_feat" | "equipment",
          label, level, count, options: [{key, name, hint}], picked: [...], required: bool}
```

`pending()` walks class levels 1..N (class skills at 1, expertise, Fighting Style, masteries count from the table, subclass at 3, ASI levels, Epic Boon at 19, cantrips and prepared counts versus spells chosen), then origin (lineage, background increase, feat sub-choices, languages), then equipment (only at creation). It returns the choices that are unpicked or invalid.

### 6.2 `derive()` additions (one call per broadcast, reused for every recipient)

```text
ac:            {value, formula: "Studded Leather 12 + Dex 4 + Shield 2", overridden: bool}
attacks:       existing per-attack map, extended to effective attacks
effective_attacks: ids "w:<item_id>", "w:<item_id>:oh" (off-hand), "unarmed", plus custom ids
actions:       ordered list (shared with combat ActionBar):
  {id, kind: attack|spell|item|feature|resource, ref_id, name, icon, cost,
   to_hit?, dc?, save?, parts:[{formula, type}], range_text, reach?, range?,
   uses?:{max, used, reset}, slot_level?, qty?, hint?}
   order = combat 3.1 rule: attacks → prepared leveled spells with effect → cantrips
           → items with use → features with use → other resources
spells:        {prepared, prepared_max, cantrips, cantrips_max}
carrying:      {weight, capacity, encumbered} (weight includes coins at 50/lb when on)
attuned:       {count, limit: 3}
training:      {armor: [...], weapons: [...]}; warnings: ["untrained_armor", "over_prepared", "over_attuned", "two_handed_shield"]
pending:       int (len(pending()))
xp_next:       int | None
sneak_attack:  "3d6" | None  (shown as a hint; prefilled in combat's ＋ Damage input)
```

**AC (`inventory.armor_class`):**
- **Base:** the maximum of:
  - equipped armor `base + min(Dex, cap)`;
  - 10 + Dex;
  - unarmored hooks: Barbarian `10 + Dex + Con` (shield allowed); Monk `10 + Dex + Wis` (no armor, no shield); Draconic Sorcery `10 + Dex + Cha`.
- **Additions:**
  - shield +2 + its `bonus_ac`;
  - armor `bonus_ac`;
  - attuned or unattuned-allowed items' `bonus_ac` (Ring and Cloak of Protection also give `bonus_save`);
  - Defense style +1 while wearing armor.
- **Token effects** (Shield, Shield of Faith) stay token-side in combat (`effects5e.ac_bonus`).

**Weapon attacks** (`inventory.weapon_attacks`, turned into `Attack` objects so `resolve.py` needs no new code):
- **Ability:**
  - melee uses Str and ranged uses Dex;
  - Finesse uses the better of the two;
  - thrown melee keeps Str;
  - Monk weapons and Unarmed can use Dex and the Martial Arts die.
- **Proficiency:** `item.proficient` if set, else class training (simple / martial / Rogue's martial with Finesse or Light). Hand-made sheets with no build default to proficient.
- **Bonuses:** `bonus_hit` and `bonus_dmg` apply only if the item is attuned or needs no attunement. Archery adds +2 to ranged.
- **Versatile:** uses the two-handed die automatically when no shield and no second weapon is equipped.
- **Off-hand:** two equipped Light melee weapons add an off-hand row with cost `bonus`. Its damage has no positive ability modifier unless Two-Weapon Fighting.
- **Unarmed Strike:** always present, damage `1 + Str` bludgeoning.
- **Shape:** each effective attack is a regular `Attack` with combat's numeric `reach` and `range_*` and its `mastery` tag.

**Untrained armor and stealth.** `on_sheet_roll` and `resolve` read `derived.warnings`:
- untrained armor gives disadvantage on Str/Dex d20 tests and blocks casting with a warning;
- `stealth_dis` armor gives disadvantage on Stealth.
These go through the `extra` reasons of `rolls.d20_test`.

### 6.3 Build, level-up, items

- **`char.build`:**
  1. Validate the permission (GM, or the player with `player_creation` on: a new character with `player_id` = sender, or a rebuild of their own).
  2. `validate_choices`, rejecting unknown keys and wrong counts. Skipped choices are allowed and become pending.
  3. `apply_build` → `normalize`.
  4. For a new character: create the character with `sheet.hp.current = max`, the `inventory` from equipment A/B (equipped by rule: best armor, shield, first weapon), and `currency.gp`.
  5. With `place`: create a token (image from the avatar, size from the species, `represents`, `controlled_by` = player) on `place.page_id` at the snapped point.
  6. Everything goes into **one** `_action`/`_commit("char.build")`, so the GM can revert it from History.
  7. For a rebuild, inventory, notes, HP damage taken (as a delta), used resources and slots are kept.
- **`char.build_preview`:** the same steps 2–3 on a copy. Nothing is committed and there is no event. The reply goes only to the sender: `{rid, sheet, derived, pending, errors, gains?}`. It is rate-limited by debounce on the client and capped at 20 per second per connection on the server.
- **`char.level_up`:**
  1. Check permission.
  2. `hp = average` → store `die/2 + 1` in `hp_rolls`; `roll` → the server rolls 1dX (posted to chat as a template card "Mira gains 6 HP").
  3. Apply the choices, `normalize`, then `hp.current += hp.max - old_max`.
  4. One `_action("char.level_up")`. The GM can revert it from History; it is not on the Ctrl+Z stack.
- **`item.add`:** builds an `Item` from `ref` (compendium or homebrew; `base` for collapsed variants) or takes a custom `item`. Permission: the GM, or the owner of the target character. Target: `character_id`, or `token_id` → its `represents`. For NPC tokens without a sheet the server refuses.
- **`item.give`:** moves `qty` of `item_id` from a character the sender owns (or any, for the GM) to the character represented by `to_token_id`. Both sheets change in one `_action`. A partial quantity splits the item with a new id. It posts an emote "Mira gives 2 Potions of Healing to Bren".
- **Using an item or a feature:** this is combat's `combat.act` with `action: {kind: "item" | "feature", id}`.
  - `ActionsMixin` reads the `Use` and resolves `heal`/`temp`/`damage`/`save`/`effect` with the existing resolution code. `target: self` skips target mode.
  - It decrements `qty` (an item reaching 0 is removed, unless it has charges) or spends `resource_id`/`charges`. The cost comes from `Use.cost`, with `potion_action` overriding the cost for potions.
  - It all happens inside the capture, so the card's Undo restores quantity, charges and HP together.
- **Rests (`on_sheet_rest`, extended):**
  - **Short rest:** resources with `reset: short` → all; resources with `short_regain: one` → `used - 1`; Pact slots → 0 used; charges with `reset: short`.
  - **Long rest:** the existing behaviour, plus `charges` `dawn`/`long` regain (rolled with `regain`, one chat line per item), plus `heroic_inspiration = True` for species Human (the Resourceful trait).

### 6.4 Class automation (MVP, only hooks that change a number we already compute)

- **Numbers:** Unarmored Defense (3 formulas); Fighting Styles Archery, Defense and Two-Weapon Fighting; Alert; Jack of All Trades; Expertise; Dwarven Toughness.
- **Class table values:** Extra Attack; Champion crit range; Martial Arts die; Sneak Attack dice (hint plus prefill of ＋ Damage); Rage damage.
- **Effect presets added to `effects.py`:**
  - `rage`: resistance to bludgeoning, piercing and slashing; advantage on Str checks and saves; +rage damage on Str melee attacks;
  - `bardic_inspiration`: one-shot +die on the next d20 test.

  Each needs a small resolver hook in combat.
- **Uses:** Second Wind and Breath Weapon (as `Use`).
- **Everything else is a text card with uses pips.**

### 6.5 Performance

- `derive` and `normalize` each run in under 1 ms (pytest benchmark assertion on a level-20 Wizard with 40 spells and 60 items).
- `_broadcast_character` computes `character_dict` once per call. The welcome snapshot computes `derive` once per character.
- The typical sheet stays at or under 12 KB thanks to refs. If measurements later show broadcast cost, add a `char.patch` delta message (post-MVP, not designed now).

---

## 7. Protocol (`game/protocol.py` ↔ `net/protocol.ts`, changed together)

**Client → server:**

| Message | Fields | Who |
|---|---|---|
| `char.update` (exists) | Whole `sheet`; the server runs `upgrade` and `normalize` | owner / GM |
| `char.build` | `id?` (new uuid) or `character_id?` (rebuild), `name`, `avatar?`, `build: BuildInput {classes:[ClassLevel], background, species, lineage, base_scores, method, bg_increase, choices, equipment: {class: "A"\|"B", background: "A"\|"B"}}`, `place?: {page_id, x, y}` | GM; player if `player_creation` |
| `char.build_preview` | `rid`, `character_id?`, `build: BuildInput` | same |
| `char.roll_abilities` | `rid` → server rolls `4d6dl1` ×6, posts to chat, replies with the values | player in wizard, if `ability_scores` allows rolling |
| `char.level_up` | `character_id`, `class_key`, `hp: "average"\|"roll"`, `choices` | owner if `player_creation`; GM |
| `item.add` | `character_id?` \| `token_id?`, `ref?` \| `item?: Item`, `base?` (variant), `qty=1` | owner / GM |
| `item.give` | `from_character_id`, `item_id`, `qty`, `to_token_id` | owner / GM |
| `compendium.search` (exists) | `kind` += `item`, `feat`, `background`, `species`, `class`; filters `category?`, `rarity?`, `class_list?` (spells) | everyone for items and spells (homebrew only if visible); monsters stay GM-only |
| `compendium.texts` | `refs: list[str]` (≤ 50) | everyone (homebrew visibility checked) |
| `homebrew.save` | `kind: item\|spell\|monster`, `key?` (update), `name`, `data` (validated as `Item` / `Spell` / `Sheet`), `visible: bool` | GM |
| `homebrew.remove` | `key` | GM |
| `combat.act` (combat) | `action.kind` += `"item"`, `"feature"` | combat rules |
| `combat.apply` (combat) | += `character_id?` (PC with no token on the page: sheet HP header input) | owner / GM |

**Server → client:**

| Message | Fields |
|---|---|
| `char.build_preview.result` | `rid, sheet, derived, pending: [Choice], errors: [{choice_id, message}], gains?: {features: [{ref, name}], changes: [[label, before, after]]}` |
| `char.roll_abilities.result` | `rid, values: [6 ints]` |
| `compendium.texts.result` | `texts: {ref: text}` |
| `homebrew.upsert` / `homebrew.removed` | entries (summaries) to the GM, and to players when visible |
| `character` (exists) | unchanged shape; `derived` gains the section 6.2 fields |

**HTTP:** `GET /api/compendium/catalog?v=<hash>` returns wizard summaries:
- classes with feature names and levels, table columns, skill choice;
- species, backgrounds and feats;
- the starter spells and recommendations.

It is about 50 KB (gzip about 12 KB), with `Cache-Control: public, max-age=31536000, immutable`. The hash is sent in `welcome` as `catalog_v`.

**DB:** one Alembic migration `homebrew` (table `homebrew(id, game_id, kind, key unique per game, name, data JSONB, visible, created_by player_id)`) plus the `sheet_v2` data migration. Homebrew writes go through `_commit` (kinds `homebrew.save` / `homebrew.remove`).

---

## 8. Settings (section "Characters" in `backend/app/game/options.py`)

| Key | Kind / options | Default | Label (help) |
|---|---|---|---|
| `player_creation` | bool | `true` | Players create and level up their own characters. Off: only the GM builds and grants levels. |
| `ability_scores` | choice: `standard` Standard array or point buy · `roll` Also 4d6 (rolled in chat) · `any` Also manual entry | `standard` | Ability score methods |
| `start_level` | int 1–20 | `1` | Starting level for new characters |
| `hp_on_level` | choice: `average` Average · `roll` Roll · `choice` Player chooses | `average` | Hit points when levelling up |
| `encumbrance` | bool | `false` | Track carrying capacity: Str × 15 lb, ×2 Large, ½ Tiny; coins 50 per lb; over capacity, Speed drops as the SRD 5.2 rule says (verify the exact text when implementing). |

There are no per-player settings. The Play/Edit mode is remembered per sheet in `localStorage`.

**Owned by combat, not duplicated here:** `potion_action` (with `potion_bonus_action` gone), recharge, legendary and mastery behaviour.

---

## 9. Build order (each step shippable, with `npm test` and `npm run e2e` green)

1. **Sheet v2 model + upgrade + migration.**
   - Work: new models, `upgrade()`, the `sheet_v2` Alembic data migration, `notes`, the `features` list, spell `ref`, `normalize()` skeleton (inventory-free, no build), and protocol.ts types.
   - Coordinate with combat build step 4: one PR adds both field sets to `sheet.py`.
   - Tests: v1 fixtures (a dev sheet and a v1 compendium monster) validate and upgrade; the result is idempotent; size budget.
2. **Importer v2 + compendium extensions.**
   - Work: `__in` filter, cache, `classes.json` / `origins.json` / `items.json`, monsters and spells v2 (with combat parsing), `class_rules.py` data, `compendium.texts`, the catalog endpoint, and `compendium.search` kinds.
   - Tests: fixture parsing, size budgets, blocklist.
3. **Play-mode sheet.**
   - Work: `CharacterSheet` shell, `SheetHeader`, `AbilitiesColumn`, `ActionList` (from a first `derived.actions`, made from custom attacks, spells and resources), `FeaturesTab`, `SpellsTab`, `BioTab`, ✎ Edit that reuses the split `Sheet5e` sections, and `minimd.ts`.
   - e2e: the sheet opens in Play mode, clicking a skill posts a roll, Edit toggles.
4. **Inventory.**
   - Work: `inventory.py` (AC, weapon attacks into `effective_attacks`, carrying, attunement), `InventoryTab`, `ItemPicker`, `item.add` / `item.give`, compendium Items kind with GM drag onto a token, the `encumbrance` switch, charges and the rests extension, and `combat.act` kinds `item`/`feature`.
   - Dependency: combat build step 2. Until then, Use posts the existing template card.
   - Tests: `test_inventory.py` (every AC case, weapon cases, attunement gating, encumbrance), and a game test where potion use lowers quantity and Undo restores it.
5. **NPC stat block.**
   - Work: `StatBlock.svelte`, `openCharacter(id, tokenId)`, per-token state display (after combat step 6, it reads `token.props.npc`), and the new `alignment`/`senses`/`languages` from the importer.
   - e2e: the GM opens a goblin from its token and clicks Scimitar.
6. **Build engine.**
   - Work: `build.py` (`normalize` with class and origin data, `pending`, `validate_choices`, `apply_build`, `level_up`, `quick_build`), resources and hooks, and the `rage` / `bardic_inspiration` presets.
   - Tests: `test_build.py`, parametrized over the 12 classes × levels 1/2/3/5/11/17/20 (PB, HP average, slots full/half/pact, resource maximums, Extra Attack, saves, feature count). `quick_build` leaves zero pending. Validation errors cover non-SRD keys, wrong counts and background skill overlap.
7. **Creation wizard.**
   - Work: `char.build_preview`, `char.build`, `char.roll_abilities`, `CharacterWizard` with `PickN` / `AbilityAssign` / `AsiOrFeat` / `EquipmentPick` / `BuildSummary`, Quick build, place token, `player_creation` / `ability_scores` / `start_level` settings, the pending badge, and Rebuild.
   - Tests: preview writes no event; permissions with the switch on and off.
   - e2e: the player clicks Quick build Fighter, then Create; their token appears in both tabs; Actions shows Longsword with the expected to-hit.
8. **Level-up and XP.**
   - Work: `LevelUpDialog`, `char.level_up`, the `hp_on_level` setting, gains diff, XP chip, History revert.
   - Tests: one event; HP average and roll with seeded dice; revert restores the level-1 sheet.
   - e2e: the player levels to 2 and HP max rises in both tabs.
9. **Homebrew lite.**
   - Work: migration, `homebrew.save` / `remove`, merge into search and texts with 🏠, visibility to players, and "Save to homebrew" in the item ⋯ menu, the spell editor and the NPC header.
   - Then update the living docs (dev log, Frolls vs Roll20), the MVP roadmap artifact and the CLAUDE.md "Manca" list.

---

## 10. Discarded or deferred, with reasons

| Idea (member 1) | Decision | Reason |
|---|---|---|
| Separate `item.use` and `npc.use` messages | Use `combat.act` kinds `item`/`feature`; NPC state belongs to combat | One pipeline gives undo, cards and economy for free; avoids two resolution paths. |
| Formula strings on resources (`"table:rages"`) | Python lambdas in `class_rules.RESOURCES`; sheet stores only `source` | No mini expression language to parse, validate and keep in sync. |
| Copying SRD text into every sheet | `ref` + `compendium.texts` on demand | Sheets are rebroadcast whole on every HP change. A 25-spell sheet with text is about 30 KB; with refs it is about 6 KB. |
| Client-side preview from the same JSON | Server `char.build_preview` only | One rules implementation; no Python/TS drift. 2 ms plus round trip is invisible behind a 150 ms debounce. |
| Settings `enforce_prepared`, `attunement_limit`, `long_rest_hit_dice`, `heroic_inspiration`, `class_automation`, `coin_weight`, `track_ammo`, `multiclass`, `weapon_mastery`, `auto_recharge`, `legendary_reminder`, `players_level_up` | Dropped or merged (5 remain) | Counts are warnings, never blocks. SRD 5.2 rules are fixed (attunement 3, all hit dice on a long rest). Coins fold into `encumbrance`. Level-up merges into `player_creation`. Combat owns recharge and legendary. Mastery is post-MVP. |
| Per-player `sheet_mode_default`, `action_dock` | Dropped | Players who cannot edit always get Play mode; edit mode is remembered per sheet locally. The dock is combat's ActionBar. |
| Weapon Mastery effects in MVP | Post-MVP (combat step 11). Choices are recorded and shown as tags now | Needs 8 behaviours in resolve; Effects + ＋ Damage cover them by hand. |
| Sneak Attack "offer on hit" | Hint + prefilled ＋ Damage (combat M2) | Once-per-turn rider logic is combat's post-MVP "named riders". |
| Great Weapon Fighting automation | Text | Needs a "treat 1–2 as 3" dice operator; not worth a dice-engine change now. |
| Ammunition decrement, variant encumbrance | Deferred / dropped | Bookkeeping with low value; quantity is editable by hand. |
| Heroic Inspiration reroll button | Post-MVP; star toggle now | Rerolling a combat card is undo + re-resolve with a forced die, which is combat-pipeline work. |
| Give via a character list in the journal | Give → click a token (target mode) | Players do not receive other players' characters (journal privacy). A token is the natural target. |
| Multiclass UI, spellbook, spell-swap timing, components and focus checks | Deferred / never | The model is ready. These are rare at our table and slow play. |
| GM "grant level from party view" | Level up in the sheet (GM always allowed) | No party view in this area's MVP; one entry point is enough. |
| D&D Beyond / Roll20 import | Never | Unofficial endpoints, unclear ToS, non-SRD content. |
| Homebrew classes, species, backgrounds and feats; JSON packs | Post-MVP | Heavy wizard schema; homebrew items, spells and monsters cover what groups add most. |
| Shop, merchant, loot splitter | Post-MVP | Give + currency deltas cover sessions. |
| Persisting the wizard draft on the server | `localStorage` (try/catch) | A per-viewer convenience; never authoritative. |
| Automatic "Create your character" modal on join | Soft banner + Journal button | Modals on join block the table; the banner is one click. |
