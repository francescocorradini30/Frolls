# Roll20: functional specification for Frolls

> **Clean-room** specification document. It describes only Roll20 **behavior** observable from public sources (community wiki, Help Center, blog, forums, reviews). No Roll20 code was read or copied. Each section states what the feature does, how it behaves for the user, who can use it (GM or player), what data is needed, edge cases, and the known complaints Frolls must solve.
>
> Research dated 2026-10-18. The Roll20 wiki and Help Center block automated access, so wiki pages were read from Wayback Machine copies (2022-2025 revisions). Roll20 released the new "Jumpgate" engine in January 2025: where the new behavior differs from the legacy one, I point it out.
>
> **Excluded by user decision** (final list only): voice/video, audio/jukebox, fog of war, dynamic lighting, vision/line of sight.

## Legend

- **GM**: Game Master. Roll20 has three roles: **Creator** (only one, owns the game, their subscriptions unlock features), **GM** (promoted by the Creator, there can be more than one), **Player**.
- **"Controlled by"**: list of players (or "All players") with control permission over a token or character.
- **[Frolls+]**: recommended improvement over Roll20, motivated by a documented complaint.
- **[Frolls decision]**: point where Roll20 does not define the behavior, or defines it poorly, and Frolls has to choose.

---

## 1. Accounts, games and roles

### What it does
An account creates games ("Game"/"Campaign"). Each game has a **Game Details** page outside the virtual tabletop (VTT), with players, settings, chat archive, private forum and a "Launch Game" button.

### Behavior
- **Game creation**: name, optional choice of sheet template (or "None"), tags. For Frolls the template will always be "5e (SRD)".
- **Invite**: the "Invite Players" button shows a **unique invite link** to copy and allows email invites with a list of pending invites. Anyone with the link can join. Any GM can share it.
- **Kick**: "Kick from game" removes the player **and regenerates the invite link**, so the old link stops working. To let someone back in, the new link is needed.
- **Promotion**: only the Creator can "Promote to GM" or "Demote to player" by hovering over the player's icon. The GM has a blue "GM" label on their avatar.
- **Multiple GMs** can be connected at the same time.
- **Join as player**: a GM can "Rejoin as player" (losing GM tools until "Rejoin as GM") to see what a player sees. There is a dedicated link with `?desiredrole=player`.
- **Leave game**: the only settings option available to players.
- **Game info**: system played, date and time of the next session (converted to the user's time zone; 12-hour clock only, complained about), Markdown description, icon.
- **Copy game** (Creator): chooses what to copy: players and settings (macros included), pages, decks and tables, chat log, journal, playlists, forum. The sheet template resets to "None" and must be chosen again (UX bug).
- **Delete game**: with confirmation, irreversible.
- **Rollback** (Pro only): one snapshot per day between 4 and 6 AM PST, kept for 7 days; you pick the date and restore.
- **Game forum**: discussions with threads and replies; GM and Creator can pin, sink, delete and restore.
- **Looking for Group (LFG)**: public listing of the game in a directory (out of initial scope).

### Data
`User(id, username, display_name, avatar, color)`, `Game(id, name, creator_id, sheet_template, description_md, next_session_at, tags, invite_token, created_at)`, `GameMember(game_id, user_id, role: creator|gm|player, joined_at)`, `Invite(email, status)`.

### Edge cases
- Roles are per game, not per account: the same user is GM in one game and player in another.
- Player names appear in permission menus only **after** they have joined the game at least once.
- The Creator cannot be demoted.

### Complaints and what to do better
- [Frolls+] Session date and time with a 24-hour clock and explicit time zone.
- [Frolls+] Rollback for everyone, not paid, and more granular: Frolls already has a delta event log and can offer per-object history.
- [Frolls+] Copying a game must preserve the sheet template.
- Security: in December 2018 Roll20 suffered a breach of about 4 million accounts (emails, IPs, bcrypt hashes, last 4 card digits) ([HIBP](https://haveibeenpwned.com/Breach/Roll20)). Frolls: minimize personal data, no payment data in-house.

> Note: by user decision, auth and accounts come **last**. Until then there is a single persistent game and the role is chosen on entry.

---

## 2. Interface layout

- **Tabletop** (center): canvas of the current page.
- **Toolbar** (left), from the top: Select/Move (with Pan mode), Layers (GM only), Drawing tools, Text (separated after the redesign), FX effects, Zoom, Measure, Place tool (lights/doors/windows, excluded), Fog of War (excluded), Turn Tracker (GM only), Dice (GUI), Help. After the 2023-2024 redesign the layers sit at the bottom of the toolbar (order: GM, Lighting, Map, plus Foreground since 2025).
- **Page Toolbar** (top, GM only): page list and Player Ribbon.
- **Sidebar** (right, resizable), tabs: Chat, Art Library (GM only), Journal, Compendium, Jukebox (excluded), Collections (macros, decks, tables), My Settings.
- **Player area** (bottom left): avatar of each connected player with name and color. You can drag cards onto them (to hand them over), handouts (to show them) and players onto pages (split party).
- **Macro Quick Bar** (bottom): the individual user's macro buttons.
- **Token Actions bar** (top): appears when a token is selected.
- **Popout**: chat, character sheets and handouts can be opened in a separate window. In popout some sheet features (button drag, repeating sections, Charactermancer) do not work: a known complaint.
- **Dark mode** (since 2022).

[Frolls+] Separate interface for GM and player: it was one of the stated goals of the Roll20 redesign ([wiki](https://wiki.roll20.net/Toolbar_%26_Layers_Redesign)). Usable on tablets too: Owlbear Rodeo is appreciated for this.

---

## 3. Pages (maps)

### What it does
A game contains multiple **pages** (scenes, maps, encounters). One page is viewed at a time. The GM can be on a different page from the players, for example to prepare the next scene.

### Page Toolbar (GM only)
- Horizontal list of thumbnails; scroll with Shift+wheel.
- **Create new page**; **rename** by clicking on the name (Enter to save).
- **Reorder** with drag & drop.
- On hover, **Settings** (gear) and **Duplicate** appear.
- **Duplicate page**: copies settings **and** content. Full copying only exists since December 2020; before that a script was needed.
- **Page folders** (since October 2023, highly requested).
- **Page icon** = the largest image on the page. To change it the trick is a huge image sent to the back: terrible UX. [Frolls+] Thumbnail chosen explicitly or generated automatically from the map.
- **Archive page**: hides it in an "Archived" area on the right, from which it can be restored. Archived pages however **still load at startup** and do not improve performance ([wiki Archiving](https://wiki.roll20.net/Archiving)). [Frolls+] Lazy loading: archived and unviewed pages are not loaded.
- **Delete page**: at the bottom of the settings. You **cannot delete** the page where the Player Ribbon is, nor the one you are looking at.

### Player Ribbon and split party
- The **Player Ribbon** (red bookmark) marks the players' page. The GM **drags** it onto another page and all players are moved there. The GM does **not** move: to go there they must double-click the page.
- **Split the Party**: the GM drags a player's avatar from the player area onto a page. A small player icon appears on that page. Dragging it onto another page moves the player; dragging it **onto the Ribbon** (the same page is not enough) returns the player to the group.
- **Define Party / Place Party** (Jumpgate, August 2025): characters have a "Party member" property, toggled from the context menu or the sheet. "Place Party" brings all party tokens to a spot on a page in two clicks, moves the Ribbon and centers the view ([BoLS](https://www.belloflostsouls.net/2025/08/roll20-unleashes-powerful-new-party-tools-after-recent-jumpgate-upgrades.html), [forum](https://app.roll20.net/forum/post/12465889/gm-time-save-alert-party-tools-are-here)).
- **Moving tokens between pages**: Ctrl+C on the selection, change page, Ctrl+V. The paste point is the last click on the tabletop.
- When a page loads, the view starts from the **top-left corner**: a complaint, the GM has to use the pull ping. [Frolls+] Initial view centered on the player's tokens, or a saved starting point per page.

### Page settings (GM only)
Default values for new pages are set in the Game Settings.
- **Name**.
- **Size**: width and height in 70 px units (or in pixels, converted). Base: **70 px = 1 cell = 1 inch at 100%**. Jumpgate allows panning past the edges.
- **Background color** (picker with hex).
- **Scale**: what one cell is worth (default **5**), unit **ft, m, km, mi** or custom. Without a grid the scale applies every 70 px.
- **Grid**: on or off (turning it off also removes snapping); type **square, horizontal hex, vertical hex** (recent Roll20 versions also have "isometric", to be verified); **cell size** as a multiplier (0.5 = 35 px) or in pixels; line **color** and **opacity** (opacity 0 = invisible lines but snapping active); cell **labels** (hexes only); **diagonal measurement** (see §5).
- **Play on load**: audio track (excluded).
- **Archive** and **Delete**.
- The Fog of War and Dynamic Lighting sections are excluded.

### Data
`Page(id, game_id, name, folder_id, order, width_units, height_units, bg_color, scale_number, scale_unit, grid_type, cell_size, grid_color, grid_opacity, grid_labels, diagonal_rule, archived, thumbnail_asset_id)`, `Game.player_page_id`, `PlayerPageOverride(user_id, page_id)`, `Character.is_party_member`.

### Edge cases
- A player in split party stays on their page even when the Ribbon moves.
- The turn tracker is global across pages (see §10).
- The Ribbon cannot point to an archived page.

---

## 4. Layers

| Layer | Who sees it | Use | Notes |
|---|---|---|---|
| **Map and background** | everyone | maps, static furniture, tokens of defeated enemies | when active, tokens on other layers are grayed out and not selectable |
| **Objects and tokens** | everyone | tokens and objects in play; radial menu, bars and markers exist only here | players are **always** on this layer and cannot change it |
| **GM Info Overlay** | GM only | notes, traps, hidden tokens | objects **always appear gray and semi-transparent** to the GM as a reminder they are hidden; selectable only when the layer is active |
| **Foreground** (June 2025) | everyone | roofs, tree canopies, weather above tokens | requested for years ([wiki](https://wiki.roll20.net/Foreground_Layer)) |
| Dynamic lighting / Walls | GM only | **excluded** | |

### Behavior
- Switch layer from the toolbar or with **Ctrl+M** (map), **Ctrl+O** (objects), **Ctrl+K** (GM).
- To **move the selection** to another layer: right-click, Layer, layer name, or **Ctrl+Shift+M/O/K** (switches active layer and moves the objects).
- A new object is created on the **active layer**.
- Typical use case: enemies prepared on the GM layer and moved to the objects layer for an ambush.
- Drawings and text follow the same layer rules.

### Complaints
- [Frolls+] Reveal a group of GM-layer tokens in one click ("encounters"): today the EncounterHelper script is needed.
- [Frolls+] Lockable layers, so the map isn't moved by mistake.

---

## 5. Grid, scale and measurement

### Snap
- With the grid active, snapping applies to **movement, resizing and rotation**. Holding **Alt** temporarily disables it.
- On a square grid the token snaps to the **corner** (in Roll20 the "bottom right" of the cell), on hex to the **center** of the hex.
- Rotation with snap: steps of **45°** on square grid and **30°** on hex.
- Small tokens (less than one cell) snap to the corner, not the cell center. It is a complaint with **+235 votes** ([forum](https://app.roll20.net/forum/post/2309394/)). [Frolls+] Small tokens centered in the cell, or 4 sub-positions.

### Diagonal rules
**Square grid:**
1. **D&D 5E/4E** (default): each diagonal step counts as 1 cell (5 ft).
2. **Pathfinder/3.5**: diagonals alternate 1 and 2 cells (5, 15, 20, 30 ft...), i.e. 1.5 per diagonal rounded down.
3. **Manhattan**: diagonal = 2 cells.
4. **Euclidean**: diagonal = √2 ≈ 1.414.

**Hex grid:**
1. **Hex path**: +1 for each hex crossed on the shortest path.
2. **Euclidean**.

### Data
On `Page`: `grid_type ∈ {none, square, hex_h, hex_v}`, `diagonal_rule ∈ {dnd5e, pf35, manhattan, euclidean, hexpath}`, `cell_size_px`, `scale_number`, `scale_unit`.

---

## 6. Canvas navigation

- **Zoom**: toolbar menu with 10% steps; +/- slider with percentage (double-click on the slider = 100%); **Alt/Ctrl/Cmd + wheel**; **+ and -** keys (ignored if a context menu such as markers is open). Zoom is **per user**.
- **Wheel behavior** configurable per game and as account default:
  - "Wheel = pan": Alt/Ctrl+wheel zooms, Shift+wheel pans horizontally.
  - "Wheel = zoom": Alt/Ctrl+wheel pans vertically, Alt+Shift+wheel pans horizontally.
- **Pan**: toolbar Pan mode, or **right-button drag** at any time, or scrollbars.
- **Ping**: holding left-click on a spot shows animated radar rings **in the user's color**, visible to everyone on the same page.
- **Pull ping** (GM only): **Shift + hold** centers the view of **all** players on that spot. In legacy Roll20 it only worked on the map and objects layers.
- **Zoom view**: **Z** with an object selected opens an enlarged popup of the image. **Shift+Z** (GM) shows it to all players **on the same page**.
- **Arrows**: move the selected token by one cell; **Alt+arrows** by a few pixels.

### Edge cases
- Should the pull ping also work for those on another page? In Roll20 no, it only applies to those on the page. [Frolls decision] Same page only.
- [Frolls+] Player pings with a modifier too, for example a ping that "calls the GM".

---

## 7. Graphic objects and tokens

### 7.1 Creation
- An image dragged onto the **objects** or **GM** layer becomes a **token**; on the map layer it is a "background" image without token features.
- Sources: Art Library (GM), files from the computer (upload and placement), character from the Journal (its default token, for the GM and whoever controls it), compendium (creates an NPC, see §18), card from a deck, rollable table (multi-sided token).
- **"As drawing"** (Advanced > Is Drawing): removes token features (no bars, bubbles, snapping) and is selectable together with drawings with Alt.

### 7.2 Manipulation (Select tool)
- **Selection**: click. **Rectangle selection**: drag over an empty area. **Shift+click** adds to or removes from the selection. **Alt+rectangle** selects drawings only, **Ctrl+rectangle** tokens only. Selection works only on the active layer. **Ctrl+A** selects the whole layer.
- **Movement**: drag from the inside (not from the edge, which resizes). The selected group moves together.
- **Waypoints**: while dragging a token, **Q** shows a ruler of the distance traveled and each subsequent Q adds a waypoint. On release everyone sees the path.
- **Last move**: **X** with a token selected shows its last move with waypoints, kept **with no expiry** (useful for play-by-post).
- **Resizing** (**GM only**): handles at the corners (proportional) and sides (one axis), from the center, with grid snap (Alt ignores it). "Set dimensions" accepts exact values in pixels or cells. **Players cannot resize their own tokens** ([wiki Player](https://wiki.roll20.net/Player)).
- **Rotation**: protruding handle at the top (the token's "front"). **E+wheel** rotates in 45° or 30° steps, **Alt+E+wheel** by 1°.
- **Flip** horizontal or vertical (Advanced).
- **Group / Ungroup** (Advanced): the group moves as a block; clicking a single member drags it alone.
- **Order (z-order)** (GM only): right-click, "To front" or "To back".
- **Copy/Paste/Delete**: Ctrl+C, Ctrl+V, Del or Backspace.
- **Undo**: Ctrl+Z. It is **a single level** and pressing it again toggles between done and undone: a strong complaint ([forum](https://app.roll20.net/forum/post/3210982/please-review-the-undo-slash-redo-code), [forum](https://app.roll20.net/forum/post/5809236/problem-with-undoing)). Players had no undo ([forum](https://app.roll20.net/forum/post/8760735/player-undo-button-ctrl-plus-z)). [Frolls+] Multi-level undo/redo per user, also for players on their own objects.
- **Token lock** (GM, since March 2022): prevents players **and GM** from moving it until it is unlocked.

### 7.3 Z-order rules (since 2019)
- By default the last token dropped is on top.
- The GM reorders freely.
- **For the player who controls it**, a token "with vision" always appears above those they don't control, even if the GM put it below. Others see the GM's order.
- Controlled tokens **without vision** (e.g. spell templates) are not brought to the front.
- Complaints: inconsistent order between GM and players ([forum](https://app.roll20.net/forum/post/8928459/)); players cannot reorder their own tokens ([forum](https://app.roll20.net/forum/post/7892438/)); request to be able to disable "always on top" ([forum](https://app.roll20.net/forum/post/11577293/)).
- Without vision (excluded), [Frolls decision]: a single, consistent z-order for everyone; per-game option "player tokens always on top"; players can reorder the tokens they control relative to other tokens they control.

### 7.4 Radial menu (selected token)
Visible to the selecting user according to permissions:
1. **Three value bubbles** (green, blue, red) for bars 1, 2 and 3. Click to edit: absolute value (`20`, also text `ABC`) or **relative** (`+5`, `-10`). Colors configurable by the GM.
2. **Nameplate** (if enabled).
3. **Edit/Settings** (GM only; also double-click on the token).
4. **Status markers** (dropdown menu).
5. **Pause animation** (animated tokens).

### 7.5 Token settings (dialog)
Tabs: Details, GM Notes, (Lighting and vision: excluded). Changes apply in real time.

**Details**
- **Name** and **Nameplate** checkbox (shows the name under the token). Name permissions: *See* (players see the nameplate) and *Edit* (the controller can edit it).
- **Represents character**: menu of all characters in alphabetical order, or "None/Generic".
- **Controlled by**: multi-select of players or "All players". If the token represents a character, control **inherits** the character's "Controlled by".
- **Tooltip** (October 2021): text of at most **150 characters** shown **under the token on hover**, with a "Show" checkbox. Spaces and line breaks are stripped (complaint), emoji are supported. It is also meant for screen readers.
- **Bars 1-3**: each has a **value** and **max** (optional; if present, the visual bar shows the value/max fill). If the token represents a character, the bar can be **linked to an attribute**: an edit from the bubble, the dialog, the sheet or a script updates **both**. Per-bar permissions: *See* and *Edit*, plus number visibility: **nobody / controller only / everyone**.
- **4th bar**: recently added as a "Maximum number of bubbles/bars" setting. Requests for more bars existed for years ([forum](https://app.roll20.net/forum/post/1285136/), [forum](https://app.roll20.net/forum/post/11729667/)).
- **Bar options**: **location** (Above [default], Overlapping top, Overlapping bottom, Below) and **style** (Standard or Compact top/bottom/overlapping). The "overlapping bottom" location collides with the nameplate: known bug.
- **Auras 1-2**: semi-transparent circle or **square** ("Square") starting from the **token center**. It has a **radius** in scale units measured **from the token edge** (radius 0 draws the aura on the edge; to remove it you **empty** the field, not set 0), **color** and *See*/*Edit* permissions.
- **Tint**: color overlaid on the image.
- **GM Notes**: GM-private rich text, with journal links.

**Game defaults for tokens**: bar values and max, auras, tint, nameplate and all see/edit permissions (see §23).

### 7.6 Status markers
- Default set: colored dots, a **red X** (covers the whole token, unlike the other markers which are small) and over 40 icons. Multiple markers at once.
- **Number on the marker**: hovering a marker in the menu and pressing **0-9** shows a red digit; 0 removes it.
- Marker **position**: above (default), below, left, right (GM setting).
- **Custom sets** (since 2020): account library (512×512 recommended, png/jpg/gif without animation); names with letters, numbers and hyphens only (space becomes `_`). They are added to the game from the Details page and ordered. The default set can be removed, but **not** the colored dots or the X. Removing a set hides the markers on tokens; re-adding it makes them reappear. Players must reload to see new sets (complaint).
- [Frolls+] Markers with a duration in rounds linked to the turn tracker; 5e SRD conditions preloaded.

### 7.7 Multi-sided tokens (from rollable table)
- From a rollable table with icons you create a token containing all images **at the moment of creation**. Later changes to the table do **not** propagate: complaint.
- It is created as a "drawing" (no snapping or bars) and must be converted by hand.
- Menu: **Multi-Sided > Choose side** (slider) or **Random side** (table weights are **not** used).
- It can represent a character and be its default token (wild shapes, variants).
- [Frolls+] Sides dynamically linked to the table.

### 7.8 Default token and character link
- The character has a **default token**: select a token on the tabletop and press "Use selected token". A full copy is saved (bars, links, permissions, notes).
- Dragging the character's **name** from the Journal onto the tabletop creates a copy of the default token. The GM can do it, or whoever "can edit and control" the character.
- **Only the GM** can change the default token or the avatar ([wiki Player](https://wiki.roll20.net/Player)). [Frolls+] Allow the owning player too.
- **Unique PCs and NPCs**: bars **linked** to attributes, so token and sheet stay in sync.
- **Generic monsters**: **unlinked** bars. Each copy has its own HP but shares the sheet for rolls and stats.
- **Shift+double-click** on the token opens the linked sheet; since 2023 there is also an "Open sheet" entry in the context menu.
- [Frolls+] Automatic numbering of copies ("Goblin 1, 2, 3", today the TokenNameNumber script is needed) and random HP from hit dice on placement (today the MonsterHitDice script is needed).

### 7.9 Token Actions
See §13.4.

### Token data
```
Token(id, page_id, layer, x, y, width, height, rotation, flip_h, flip_v, z,
      image_asset_id, sides[] , current_side, is_drawing, locked,
      name, show_nameplate, name_perm{see,edit},
      represents_character_id, controlled_by[user_id|"all"],
      bars[1..4]{value, max, link_attr_id?, see, edit, numbers_visibility},
      bar_location, bar_style,
      auras[1..2]{radius, color, square, see, edit},
      tint_color, status_markers[{marker_id, number?}],
      tooltip{text<=150, show}, gm_notes_html,
      group_id, last_move{path[]}, created_at)
```

---

## 8. Drawing tools

### Tools
- **Shapes**: rectangle; **Alt** for circle/ellipse; **Shift** for grid snapping.
- **Freehand**: drag as on a whiteboard. Shift gives snapped straight lines.
- **Polygon/Line**: click for each vertex. **Right-click or Esc** closes the shape; a vertex near the first one closes the polygon; right-click after the first segment leaves an open line. **Ctrl+Z** undoes segment by segment while drawing; Shift snaps vertices to the grid.
- **Text**: click and type. Font, size and color apply to **the whole object**, not individual characters ("it's a label maker"). Double-click or right-click > Edit to re-enter; Esc removes focus.
- **Secondary bar**: **stroke** color, **fill** color (transparent too), line **width**.
- **Clear drawings**: deletes **all drawings on the current layer**.
- **Group** drawings (Advanced).

### Permissions
- **Players can always draw**, on any page they are on, on the objects layer. The GM cannot prevent it without a script (DryErase).
- Players can move and delete their own drawings; in 2023 their ability to resize them disappeared ([forum](https://app.roll20.net/forum/post/11501167/)).
- [Frolls+] Game permission "players can draw" (yes/no/only on marked pages) and "clear my drawings".

### Data
`Drawing(id, page_id, layer, kind: rect|ellipse|freehand|polygon|polyline|text, points[], stroke_color, stroke_width, fill_color, text, font_family, font_size, x, y, rotation, z, owner_id, group_id)`

### Edge cases
- Ctrl+F opens the freehand tool **instead of** the browser search: a complaint ([wiki Journal](https://wiki.roll20.net/Journal)). [Frolls+] Don't steal browser shortcuts.
- There is no eraser ([forum](https://app.roll20.net/forum/post/3756/eraser-tool)) and no eyedropper ([forum](https://app.roll20.net/forum/post/1509/)). [Frolls+] Add them.

---

## 9. Measurement and area templates (AoE)

### 9.1 Legacy ruler
- Click and drag measures distance using the page scale and diagonal rule.
- Modes: **snap to corner** (measures in whole cells), **snap to center** (whole cells), **free** (exact distance).
- Visibility: **"Show to others"** (everyone sees it) or **"Hide from others"** (the GM sees it anyway).
- While measuring, **Q** or right-click adds a waypoint; **Shift** leaves it visible until right-click or a new measurement; **X** recalls the last measurement.

### 9.2 Measure tool (since 2023, standard in Jumpgate)
- **Shapes**: **Line**, **Square** (origin: center, edge or corner), **Circle** (origin: center or edge), **Cone**, **Beam** (line with width).
- **Cone angle**: "Width = length" (**53.13°**, the 5e rule), quick presets or custom angle.
- **Snap**: adjustable.
- **Linger**: the measurement stays on the tabletop.
- Each measurement shows the **name and color** of whoever is measuring.
- The interface shows whether the measurement will be broadcast to others or hidden.
- Sources: [Help Center](https://help.roll20.net/hc/en-us/articles/360039674913-Measure-Tool), [blog](https://blog.roll20.net/posts/new-measure-tool-shows-aoe-and-shapes/), [X/Roll20](https://x.com/roll20app/status/1887940210240930057).

### 9.3 Persistent templates
In legacy Roll20, tokens with auras or drawings were used as templates. There is no AoE template as a persistent object with highlighting of affected cells.
- [Frolls+] Persistent **Template** object (cone, sphere, cube, line, cylinder) linkable to the spell, with **affected cells highlighted** according to the 5e rule (cell affected if at least half covered, or configurable rule) and a list of affected tokens. It was a long-standing request ([forum](https://app.roll20.net/forum/post/8270654/advanced-rulers-cone-square-circles-beam)).

### Data
`Measurement(user_id, page_id, shape, origin, points[], angle, width, snap_mode, visibility: all|gm, linger)`. Temporary measurements are realtime only and don't persist; lingering ones become objects.

---

## 10. Turn tracker (initiative order)

### Behavior
- **Only the GM** opens and closes it. When open, **it is visible to everyone**; when closed, it closes for everyone.
- **Not automated** by design: it serves any system.
- **Adding turns**:
  - Right-click on the token > **Add turn** (even multiple turns for the same token), or **Ctrl+U** on the selected ones.
  - Roll with the **`&{tracker}`** flag with a token selected (also from the sheet's Initiative button). If no token is selected the warning *"You wanted to send the result of this roll to the turn tracker, but no valid token was selected!"* appears. With the wrong token selected, the value still goes to that token.
  - **Custom entry** (without token): name plus an optional **round calculation** (`+1` or `-1`) applied every time the entry reaches the top. Used as a round counter or for expiring buffs; only works with more than one entry.
  - **Cards**: "Deal cards to turn order entries" (Savage Worlds), or drag a card onto the value field.
- **Values**: click the number and type, then Enter. GM and players can do it (players on their own). You can drag a roll result from the chat onto the value field. `&{tracker:+}` and `&{tracker:-}` add to or subtract from the current value; if the token is not yet in the tracker the roll **adds** it ignoring the sign. If the token already has a turn, `&{tracker}` updates **all** its turns.
- **Advance**: arrow, the top turn goes to the bottom. **Back**: a "back" button added later.
- **Reorder**: drag & drop; **sort** numerically (ascending or descending), alphabetically or by card suit.
- **Remove**: trash icon on hover; **Clear list**.
- **Multiple pages**: the tracker contains tokens from any page. The GM sees everything, **players see only the entries for their page**.
- **Tokens on the GM layer**: gray name in the tracker and entry **not shown to players**.
- **Macro reference**: `@{tracker|Entry name}` returns the value.

### Main complaints
- **No native round counter**: requested for over 10 years ([forum](https://app.roll20.net/forum/post/494250/), [forum](https://app.roll20.net/forum/post/1242008/), [forum](https://app.roll20.net/forum/post/294139/)). Roll20 said that "the concept of rounds does not exist in the code".
- Having to **select the token** before rolling initiative; old rolls to clean up by hand; controls scattered in a separate panel; no integration with HP and AC ([forum](https://app.roll20.net/forum/post/11481189/fixing-initiative-and-the-turn-tracker), +21).
- No per-entry status and duration ([forum](https://app.roll20.net/forum/post/1170023/), [forum](https://app.roll20.net/forum/post/3478727/)).
- No group initiative (today the GroupInitiative script is needed).

### [Frolls+]
- **Round** counter and **active turn** highlighted on the token, with optional centering.
- Initiative from the sheet goes to the **character's token on the current page** even without selection.
- "**Roll initiative for selected/for all NPCs**" in one click.
- Condition durations that tick down automatically.
- 5e tie-breaker (Dexterity bonus).
- Ask whether to clear the tracker on close.
- GM view with AC, HP and passive perception.

### Data
`TurnOrder(game_id, open: bool, round: int, entries[{id, token_id?, page_id?, custom_name?, value: string, formula?: "+1", hidden: bool}], current_index)`

---

## 11. Chat

### 11.1 Basics
- Type and send with **Enter**. **Shift+Enter** inserts a line break: each line is interpreted **separately**, but the block stays contiguous (it does not interleave with other people's messages).
- **"Speaking as"**: menu under the input with yourself (display name) or one of the characters you **control**. The GM sees all characters.
- **Chat avatars** (personal setting): the user's avatar, or the character's portrait when speaking as a character.
- **Timestamps**: **always saved**, display optional per user (less than 24 hours: time only; older: date and time).
- **Up arrow** in the input recalls the last command or roll of the session, including one from a sheet button: it's the way to see the formula.
- **Background beep**: sound for new messages when not on the chat tab.
- **Popout** of the chat by double-clicking its icon.
- **The GM can hide messages** (since December 2022).
- **Markdown supported**: `*italic*`, `**bold**`, `***both***`, code with double backticks, `[text](url)`. A link ending in .png, .jpg, .jpeg or .gif is shown as an **image**. No headings. Applies to messages, `/w`, `/desc`, `/em` and roll template fields.
- **Backtick escape**: a message starting with `` ` `` is not interpreted (no rolls, attributes or macros) and goes to chat literally. Used to share macros.
- **Clear log** (personal setting): empties only your own view until reload.

### 11.2 Commands

| Command | Who | Effect |
|---|---|---|
| `/roll F` · `/r F` | everyone | public roll of formula F (§12) |
| `/gmroll F` · `/gr F` | everyone | roll visible **only to the GM and the roller** |
| `/w Name text` | everyone | whisper to a player or character; names with spaces in `"quotes"`; **Tab completion**. Whispering to a **character** sends it to everyone in "Controlled by" (trick used for "languages") |
| `/w gm text` | everyone | whisper to all GMs |
| `/em text` · `/me text` | everyone | emote as the "speaking as" identity; centered, bold italic, brown style |
| `/ooc text` · `/o text` | everyone | out of character: **always** appears as the player, never as the character |
| `/desc text` | GM | description without author; centered, bold italic on gray style |
| `/as "Name" text` | GM | speak as any NPC without a character in the journal |
| `/emas "Name" text` | GM | emote as any NPC |
| `/talktomyself [on/off]` | everyone | your following messages reach **nobody**, neither the GM nor the archive. The toggle goes on its own line; with the toggle active API scripts don't fire |
| `/fx type-color sourceId [targetId]` | GM (Pro) | visual effect (§20) |
| `#macroName` | everyone | runs a macro (§13) |
| `%{character|ability}` | everyone | runs an ability |
| `&{template:name} {{k=v}}...` | everyone | message with roll template |
| `!command` | everyone | API command (Pro) |

### 11.3 Chat archive
- History **persists across sessions**. At the top of the chat there is "View all game messages", which opens the archive in another window. "Show on one page" lets you save as HTML or PDF from the browser. The archive has a "Hide whispers" filter.
- **Visibility**: everyone sees only the whispers and GM rolls they took part in. An old wiki note says only whispers to the GM were kept.
- **Clear archive** (Creator, Game Details): permanent, requires typing `CONFIRM`. Also used when the chat "gets corrupted" and stops working: an implicit complaint about reliability.

### Complaints and [Frolls+]
- **Blind rolls**: today there is no roll a player makes without seeing the result. It is the most voted dice request: **+410** ([forum](https://app.roll20.net/forum/post/4922089/)), plus a similar one at +39 ([forum](https://app.roll20.net/forum/post/11459035/)). Current solutions are CSS hacks or scripts ([wiki Hidden Rolls](https://wiki.roll20.net/Hidden_Rolls)). [Frolls+] **`/br`** command (blind roll), the GM can force it on sheet rolls, and the GM can request a blind roll from a player.
- Text search in chat and archive, export to JSON or Markdown, paginated loading (large archives are slow).
- Whisper to multiple recipients (today the DiscreteWhisper script is needed).
- [Frolls decision, already made] A message that is **entirely** a valid dice expression (`d20`, `2d20kh1+5`) is rolled without `/roll`.

### Data
`ChatMessage(id, game_id, sender_user_id, speaking_as{type:user|character|freeform, id?, name}, type: text|roll|emote|ooc|desc|whisper|gmroll|blind|template|system, recipients[]?, content_raw, content_rendered, rolls[] (structured results), template_name?, fields{}, hidden_by_gm, created_at)`

---

## 12. Dice engine (full specification)

> Main sources: [Dice Reference](https://wiki.roll20.net/Dice_Reference) and [Order of Operations](https://wiki.roll20.net/Order_of_Operations). In Frolls rolls are **computed by the server** with a cryptographic RNG and stored in structured form, so the log is verifiable.

### 12.1 Where to roll
- `/roll F`, `/r F`, `/gmroll F`, `/gr F`.
- **Inline roll** `[[F]]` inside any message, emote, whisper or template field.
- Sheet buttons, macros, abilities, token actions, dice GUI.
- [Frolls decision] A message made only of a valid formula is rolled automatically.

### 12.2 Text, labels and escaping
- Free text can follow the formula: `/roll 1d20+5 For initiative`.
- If the text contains numbers or operators (`+ - * / % ( )`), it must be separated with `\`: `/roll 1d20+5 \ +5 For initiative`.
- **Inline label** `[text]` right after a term: `2d10+5[Fire] + 3d6[Ice]`. It appears as a **tooltip** on the dice and in the roll breakdown. It can contain attributes: `@{selected|str}[str]`.

### 12.3 Die types
| Syntax | Meaning | Constraints |
|---|---|---|
| `NdX` | N dice with X sides. `dX` = `1dX` | N ≥ 0, X ≥ 1. Roll20 client limit: **≤ 999 dice** and **≤ 9,999,999 sides**, beyond that it silently rounds ([forum](https://app.roll20.net/forum/post/9164629/)) |
| `NdF` | Fate/Fudge dice: sides −1, −1, 0, 0, +1, +1 | |
| `(expr)dX`, `Nd(expr)` | computed number of dice or sides; the number of dice is **rounded** like `round()` | |
| `NtX[name]`, `1t[table]` | roll on a **rollable table** (§14) | inside an inline roll **only one** result is shown whatever N is |

[Frolls decision] Explicit error, not silent rounding, beyond the limits (proposal: 1000 dice, 10^6 sides). `d%` as alias for `d100` (Roll20 does not document it).

### 12.4 Math
- Operators: `+ - * /`, `%` (modulo; with a < 0 the result is negative), `**` (power; roots with fractional exponents).
- Functions: `floor(x)`, `ceil(x)`, `round(x)` (≥ .5 toward +∞), `abs(x)`.
- Precedence: `( )` > functions > `**` > `* / %` (left to right) > `+ -` (left to right).
- **There are no** `min()` and `max()` ([forum](https://app.roll20.net/forum/post/1146425/)). Worked around with groups: `{a, b}kh1` = max. [Frolls+] Add `min`, `max` and comparison operators.
- Math-only rolls: `/roll 5+3`, `[[5+3]]`.

### 12.5 Compare Point (CP)
Many modifiers compare each die against a **CP**: an optional operator among `=`, `>`, `<` followed by a number.
- **Without an operator it means `=`**.
- **`>` means ≥** and **`<` means ≤**: inclusive, careful.
- Examples: `=3`, `>2` (≥2), `<18` (≤18).

### 12.6 Dice modifiers (B = basic dice, F = Fate)
| Modifier | Syntax | Semantics | Default CP |
|---|---|---|---|
| **Exploding** | `!` · `!CP` | if the die meets the CP **another one** is rolled and added as a separate die, repeating while it meets it | max face |
| **Compounding** | `!!` · `!!CP` | like exploding, but the extra rolls are **added into the same die**: a die can exceed the maximum (Shadowrun, 7th Sea, L5R) | max face. `5d6!!5`: compounds on 5, 6 is a normal roll |
| **Penetrating** | `!p` · `!pCP` | like exploding, but **each** extra roll gets **−1** (always and only −1, even after multiple penetrations; HackMaster) | max face |
| **Reroll** | `r` · `rCP` (repeatable: `r1r3r5`) | if the die meets the CP it is **discarded and rerolled**, until it no longer meets it | `=1` (`8d6r` rerolls 1s) |
| **Reroll once** | `ro` · `roCP` | like `r`, but only once per die, keeping the new result (e.g. 5e Great Weapon Fighting style) | `=1` |
| **Keep highest** | `khN` · `kN` | keep the N highest; the others are shown **in gray** and don't count | `k` = `kh` |
| **Keep lowest** | `klN` | keep the N lowest | |
| **Drop lowest** | `dlN` · `dN` | drop the N lowest | `d` = `dl` |
| **Drop highest** | `dhN` | drop the N highest | |
| **Successes** | `CP` after the dice: `3d6>3`, `10d6<4` | the result becomes the **number of dice** meeting the CP (≥3, ≤4); ties count as success | |
| **Failures** | `fCP` (only if there is already a success CP) | each die that meets it subtracts 1 from the successes: `3d6>3f1`, `10d6<4f>5` | |
| **Critical (visual only)** | `csCP`, `cfCP` (repeatable: `cs20cs10`) | changes **only the highlighting** of crit or fumble, **not** explosions or anything else | cs = max, cf = 1 |
| **Match** | `m[N][CP]` · `mt[N][CP]` | `m` highlights matching dice with a **colored bar** (a different color for each group), without changing the total. `mt` returns the **number of match groups**. N = how many equal dice are needed for a group (default 2); CP = allowed values (`5d6mt3>4`) | N = 2 |
| **Sort** | `s` · `sa` · `sd` | sorts the display ascending (default) or descending | `s` = `sa` |

**Order in which modifiers are applied to a set of dice:**
1. **While the dice are "rolling"**: exploding, compounding, penetrating, reroll (including "once").
2. **Once the dice have settled**: keep/drop, successes, failures, sorting.

Example: to explode on ≥18 **and** show the crit on ≥18 write `1d20!>18cs>18`.

**Edge cases to cover in tests:**
- `{5d6!!}>8`: the braces are needed to say "compound on 6, then count successes ≥8". Without braces `5d6!!>8` would mean "compound on ≥8".
- `{3d6+1}<3`: to add a modifier **to each die** before comparison you must use a group.
- **Infinite reroll or explosion**: `1d1!`, `1d6r<6`, `1d6!>1`. Roll20 does not document a cap. [Frolls decision] Cap of 100 explosions or rerolls per die and a warning in the output; reject a CP covering all faces in `r`.
- `kh` with N greater than the dice: keeps everything. N = 0: keeps nothing (total 0).
- Modifiers can be combined, for example `8d6!r1kh4sd`. [Frolls decision] Accept any textual order and apply the semantic order above.

### 12.7 Grouped rolls `{ }`
- `{expr1, expr2, ...}` with group modifiers after the `}`.
- **A single sub-roll** (no commas): group modifiers act on the **individual dice** of the whole group, even of different types.
  - `{4d6+3d8}k4`: of the 7 dice keeps the 4 highest.
  - `{3d20+5}>21`: adds 5 to **each** d20, then counts those ≥21.
  - `{2d6!}>4`: explodes, then counts those ≥4.
- **Multiple sub-rolls** (comma-separated): each is **summed**, then the modifiers act on the **totals**.
  - `{4d6,3d8}kh1`: keeps the highest total (Savage Worlds: trait die plus wild die).
  - `{4d6+2d8, 3d20+3, 5d10+1}d1`: drops the lowest total.
  - `{...}>40f<10`: counts totals ≥40 and subtracts those ≤10.
- **Group modifiers**: `khN klN dhN dlN`, successes `CP`, failures `fCP`.
- **Type constraint**: all sub-rolls must be of the same type, i.e. all sums or all successes. A lone number is a special type ("M roll"): `[[{1d6, 5}kh1]]` **fails**, while `{1d6, 5+0d0}kh1`, `{1d6, {5}}kh1` and `{[[1d6]], 5}kh1` work. [Frolls decision] Make `{1d6, 5}kh1` work too, as it's the natural way to write `max(1d6, 5)`.
- Groups can be nested.

### 12.8 Inline rolls `[[ ]]`
- Used in any message: `/em hits me for [[2d6+2]] damage`.
- They are evaluated **before** the rest of the line, so they can be used as variables: `/roll [[2d6]]d5`.
- **Nestable**: evaluated from the innermost: `[[ 3d6>[[1+3]] ]]`.
- **Display**: only the **total** in a (yellow) box. **On hover** you see the formula with individual dice and labels.
- **Highlighting**: **green** border if there is a crit, **red** if there is a fumble, **blue** if both. In the breakdown individual dice are highlighted in green or red.
- Auto-calculated sheet attributes must be wrapped in `[[ ]]` to show the value rather than the formula: complaint, the sheet exposes raw formulas.

### 12.9 Reusing rolls (emergent behavior)
- `$[[n]]` is a reference to the n-th inline roll **of the same line** (0-based index in evaluation order, innermost first). It shows the result without rerolling.
- It cannot be used inside another inline roll without breaking it; there is however `$[[n.computed]]`.
- `%NEWLINE%` keeps the same logical "line".
- It started as a bug exploited by the community ([wiki Reusing Rolls](https://wiki.roll20.net/Reusing_Rolls)). [Frolls+] Explicit, documented variables, for example `[[1d20]]=>atk` and then `$atk`, besides compatibility with `$[[n]]`.

### 12.10 Roll queries `?{}`
- `?{Prompt}` shows a free input; `?{Prompt|default}` prefills it.
- **Dropdown**: `?{Prompt|Op1|Op2|Op3}`, or with **label and value**: `?{Prompt|Label 1,value1|Label 2,value2}`.
- **Same question = a single prompt**: queries with identical text in the same command ask once and reuse the value. It can be reused even without options: `?{Deadly Aim}` after `?{Deadly Aim|Yes,1|No,0}`.
- They work everywhere (rolls, macros, abilities, emotes, whispers).
- **Nesting**: `|`, `,` and `}` inside a nested query must be written as HTML entities (`&#124;`, `&#44;`, `&#125;`), with an extra `&amp;` at each level. `@{}`, `%{}` and `#` calls must never be encoded. Macros in the Collections tab **lose their entities** when reopened and saved, and break: a long-standing complaint, which is why the community saves macros as abilities.
- [Frolls+] Parser with real nesting (balanced brackets) and no entities; a **single dialog** for all queries of a command instead of one popup at a time; input types (number, yes/no).

### 12.11 Roll flags `&{...}`
- `&{tracker}`, `&{tracker:+}`, `&{tracker:-}` (§10).
- `&{noerror}`: suppresses errors, for example a nonexistent attribute.
- `&{template:name}`: roll template (§13.6).

### 12.12 Order of operations (essential for macro compatibility)
1. Expansion of **abilities** `%{char|abil}`.
2. Expansion of **macros** `#name`.
3. Resolution of **attributes** `@{...}`.
4. Repeat steps 1-3 up to **99 levels** or until there is nothing left to expand.
5. **Roll queries**, up to 99 levels. After each query HTML entities are decoded **once**.
6. **Inline rolls**, innermost first.
7. Rolling the **dice** of the remaining formula.
8. Math **functions**.
9. Evaluation of the **expression** with math precedence.
10. Custom Roll Parsing (sheet).
11. Decoding of HTML entities (once).
12. Sending to chat (and to API scripts).

Consequence: you cannot build an attribute name with a query (queries come after attributes). This is a known limitation. [Frolls decision] Keep this order for compatibility, but document it in the editor.

### 12.13 Output rendering
- `/roll`: **individual dice** are shown as die shapes colored with the **player's color**; dropped ones in gray; crit and fumble highlighted; total after the `=`.
- **Advanced dice** (setting): dice icons in chat can be dragged to reorder them or onto the tabletop.
- **Dice GUI**: quick roll of up to 5 d4-d20 dice with one click; options GM roll, exploding, compounding, penetrating; advanced roller with type, number and modifier; **last 10 rolls** to repeat, including those made in chat.
- **3D dice** (§20).

### 12.14 Reference grammar (for implementation)
```
expr      := term (('+'|'-') term)*
term      := factor (('*'|'/'|'%') factor)*
factor    := unary ('**' factor)?
unary     := '-' unary | atom label?
atom      := number | dice | group | func '(' expr ')' | '(' expr ')' | inline | table
dice      := count? 'd' (sides | 'F' | '%') dmods*
count     := number | '(' expr ')'
sides     := number | '(' expr ')'
dmods     := explode | compound | penetrate | reroll | rerollonce
           | keep | drop | success | failure | crit | match | sort
explode   := '!' cp?        compound := '!!' cp?      penetrate := '!p' cp?
reroll    := 'r' cp?        rerollonce := 'ro' cp?
keep      := 'k' ('h'|'l')? number     drop := 'd' ('h'|'l')? number
success   := cp             failure := 'f' cp
crit      := ('cs'|'cf') cp match := ('m'|'mt') number? cp?
sort      := 's' ('a'|'d')?
cp        := ('='|'<'|'>')? number
group     := '{' expr (',' expr)* '}' gmods*
gmods     := keep | drop | success | failure
inline    := '[[' expr flags* ']]'
table     := number 't' '[' name ']'
label     := '[' text ']'
func      := 'floor'|'ceil'|'round'|'abs'  (+ Frolls: 'min'|'max')
```
Ambiguities to resolve: `d` as "drop" and `d` as "die" (`2d6d1` = 2d6 drop 1 lowest); `>` as success and `!>` as explosion. The rule is binding to the preceding die.

### 12.15 Roll data
```
RollResult(id, expression_original, expression_expanded, total, type: sum|success|match,
  parts[{kind:dice|number|group|table, label?, sides, dice[{value, dropped, exploded_from?,
         rerolled[], crit:success|fail|null, match_group?}], subtotal}],
  seed_ref, created_at, roller_user_id, visibility)
```

---

## 13. Macros, abilities, references and templates

### 13.1 Macros (Collections)
- Created in the **Collections** tab: **name** and **action** (multiline text, one line per command).
- Options:
  - **Visible to**: players the macro is shared with; the GM can make it visible to everyone.
  - **Show in quick bar**: enabling it also turns on the bar.
  - **Show as token action**.
- Each player can create their own macros; shared GM macros appear to the others.
- **Running**: `#name` in chat, click in Collections, click in the quick bar or among the token actions.
- **Trailing variable**: `#d20` defined as `/roll 1d20+`, typing `#d204` becomes `/roll 1d20+4`.
- **Nesting**: `#other` on its own line. In a query you write `,#macro ` with a space after the name.
- **Autocomplete** in the editor and chat: `#` (macros), `@` (attributes of controlled characters), `%` (abilities, chat only). Matches by substring and is navigated with arrows and Enter. Shows only what you are allowed to see.
- **Shift+click** on a macro button opens the editor.

### 13.2 Abilities (per character)
- Found in the character's "Attributes & Abilities" tab: name, action and "Show as token action".
- `%{Character|ability}` or `%{selected|ability}` / `%{target|...}`. **A keyword is always needed**, even inside the character itself: `%{ability}` alone does not work (complaint).
- Sheet buttons behave like abilities (`%{Name|button_name}`).
- **Shift+click** opens the ability editor.

### 13.3 Attribute references
| Syntax | Meaning |
|---|---|
| `@{attr}` | attribute of the current character (in an ability or sheet) |
| `@{Character|attr}` | attribute of a character by name (**not** case-sensitive) |
| `@{Character|attr|max}` | max value |
| `@{selected|attr}` | from the **selected** token: if it represents a character it reads its attributes |
| `@{selected|bar1}`, `bar1|max` | token bars (unlinked too) |
| `@{selected|token_name}`, `token_id`, `character_name`, `character_id` | identity |
| `@{target|attr}` | asks to **click a target token**, even an uncontrolled one |
| `@{target|Name|attr|max}` | multiple named targets (same name = a single prompt, even across lines) |
| `@{Character|repeating_section_$0_field}` | repeating section by **index** (0-based) |
| `@{...|repeating_section_<rowid>_field}` | repeating section by **row ID** (stable) |
| `@{tracker|Name}` | value in the turn tracker |

Edge cases:
- An auto-calculated attribute returns the **formula** and must be wrapped in `[[ ]]`.
- A nonexistent attribute gives an error (`&{noerror}` suppresses it).
- `selected` without a selection gives an error.
- [Frolls decision] Ambiguity if two characters have the same name: pick the first by ID and show a warning.

### 13.4 Token Actions
- Bar at the top when a token is selected. It contains **all macros** marked as token actions (on any token) and the marked **abilities** of the character the token represents.
- **Alphabetical** ordering by default (tricks: numeric prefixes, symbols, zero-width spaces), or "legacy" in ability order (per-user setting).
- Token actions defined **inside the sheet code** cannot be removed. [Frolls+] The 5e sheet offers predefined token actions (attacks, saving throws, initiative) that can be disabled per character. Today the TokenActionMaker script is needed.

### 13.5 Macro quick bar
- Enabled from settings or by turning on "in bar" on a macro. It sits at the bottom, under the avatars.
- **Drag** to reorder, **drag out** to remove (turns red).
- You can drag **sheet buttons** onto it (doesn't work with popout sheets).
- **Right-click**: **Rename** and background **Color** (text adapts for contrast), for the local user only.

### 13.6 Roll templates
- Form: `&{template:name} {{field=value}} {{...}}`. Values can be text or inline rolls (macros and abilities inside must produce inline rolls, not `/roll`). Used in normal messages and whispers, **not** with `/roll`.
- **Whitespace-sensitive**: `{{ name=x}}` does not work (complaint).
- **`default` template** (in every game): `name` goes in the purple header, every other `{{key=value}}` becomes a row with a bold key and rows alternating white and gray, `=` aligned. Fields with a numeric key (≥0) are sorted **before** the others, in numeric order. Keys can contain rolls.
- Specific templates (5e: `simple`, `atk`, `dmg`, `atkdmg`, `npcatk`, `npcaction`, `spell`, `traits`, `desc`...) belong to the sheet and have conditional logic (for example `rollGreater()`, show/hide sections).

### 13.7 Chat buttons (chat menu)
- `[Label](~Character|ability)`, or `[Label](~ability)` inside the character: clickable **ability button** in chat.
- `[Label](!command)`: API button.
- Used to build **chat menus** as an alternative to nested queries.
- In the journal: link with a URL starting with `` ` `` followed by macro code (**journal command button**). Doesn't work if characters are in popout.

### Complaints and [Frolls+]
- HTML entities and nested queries are the top source of frustration ([wiki Macros](https://wiki.roll20.net/Macros)).
- Macros don't transfer between games (the Transmogrifier doesn't copy them; "macro sheet" trick).
- [Frolls+] **Account macro library** reusable across games; editor with syntax highlighting and preview; sharing macros via a link.

### Data
`Macro(id, game_id, owner_user_id, name, action, visible_to[], in_bar, token_action)`, `UserBarEntry(user_id, game_id, ref_type: macro|ability|sheet_button, ref_id, label_override, color, order)`, `Ability(id, character_id, name, action, token_action, order)`

---

## 14. Rollable Tables

- Found in **Collections**, only the GM creates them. "Add" creates "new-table" with 0 items.
- **Table**: name (no spaces in practice, since it's used in `1t[name]`) and "**Show to players**" (required for players to use it in macros).
- **Item**: name or text (shown in chat when rolled), optional **icon** (the image appears in chat) and **weight**. Weight is expressed as a number of occurrences or as a percentage; as a percentage it's written without `%` and the total must be 100.
- **Use**:
  - **Roll** button in Collections: the result goes to chat and into the GUI's last 10 rolls.
  - `/roll 1t[name]`, `/roll 3t[name]` (multiple draws).
  - Inline `[[1t[name]]]`, with only one result visible even if N > 1 and the others on hover.
- Used for custom dice (numeric items) and for crit or loot tables.
- **Token** from the table: see §7.7.
- Complaints: no nested tables (a result that rolls on another table, today RecursiveTable is needed); inline rolls inside an item's text are not evaluated; no import/export (TableExport is needed).
- [Frolls+] Nested tables, inline rolls in results, CSV import, d100-style ranges ("01-15 = goblin").

### Data
`RollTable(id, game_id, name, show_to_players)`, `RollTableItem(id, table_id, name, weight, icon_asset_id, order)`

---

## 15. Card decks

### What it does
Each game starts with a **standard 54-card deck** (52 plus 2 jokers). Only the GM creates decks.

### Behavior
- **Show/Hide** the deck from Collections: the deck appears on the right side of the tabletop, with a scrollbar if there are many.
- **Draw**: click the card sticking out behind the deck. The drawn card appears face up **on top of the deck**, visible to whoever sees the deck.
- **Play on the tabletop**: drag the face-up card, or the face-down one from behind the deck (without revealing it). It becomes a token. **Shift** while dragging plays it on the opposite side from the default. Right-click on the card: **Flip**.
- **Deal**: drag a card onto a player's name in the player area, or **Deal** from the menu (how many cards, to whom, "All players") or "Deal to turn order entries". The deck icon with the card count appears above the player's avatar.
- **Hand**: the player clicks the icon and sees the cards; reorders them; single view or per deck; dragging one onto the tabletop plays it. **Take card**: right-click on a card on the tabletop.
- **Steal**: open another player's hand (by default only the backs are visible) and pick a card; the victim must **confirm**.
- **Trade**: dragging a card from your hand onto another player's name opens a two-way trade dialog; both add or remove cards and confirm.
- **Recall**: dialog with counts in hand, on the tabletop, undrawn and totals; buttons to recall each group; "Shuffle on recall"; "Recall all".
- **Shuffle**: with confirmation; puts the discard pile back in first.
- **Discards**: collects cards played and then deleted from the tabletop, and those drawn but never played.

### Deck settings
- Name.
- **Show the deck to players?**
- **Can players draw?**
- **Infinite cards?** (never run out). If the deck runs out while dealing the error *"Ran out of cards..."* appears and a shuffle is needed.
- **In other people's hands** (for GM and for players): see **card count** and/or **card faces**. Default: count only.
- **Discard pile**: how to draw from it (only the top or bottom card, or choosing among all face down or face up).
- **Played cards**: face up or face down by default.
- **Card size on the tabletop** (empty = automatic).
- Per-card **tooltip**, enableable per deck.
- **Back** shared by all cards.
- **Cards**: name, image, delete; "**Add multiple**" for bulk upload (since 2020). Fronts and back should have the same dimensions.
- The on-screen size of decks is adjusted with a GM slider.

### Complaints
- No piles or decks on the tabletop ([forum](https://app.roll20.net/forum/permalink/2793233/)).
- "Look at the face-down cards I played" requires a script.
- Selected cards don't come to the front ([forum](https://app.roll20.net/forum/post/2344077/)).

### Data
`Deck(id, game_id, name, back_asset_id, show_to_players, players_can_draw, infinite, hand_visibility{gm:{count,face}, players:{count,face}}, discard_draw_mode, play_face_down, card_size, tooltips_enabled)`, `Card(id, deck_id, name, asset_id, tooltip)`, `CardInstance(card_id, location: deck|discard|hand|table, owner_user_id?, token_id?, order)`

---

## 16. Journal

### 16.1 General
- It is the central archive of **Characters** and **Handouts**, organized in **folders**.
- **Only the GM** creates characters and handouts (+ Add button, or right-click on a folder). A character is created with a random name, a handout with the name "Mysterious Note".
- **Search** and **tags** at the top.
- **Archive** at the bottom, which appears when there is at least one archived item. Archived items **still load** and don't improve performance.
- **Reordering**: ≡ handle left of the name, drag under the folder and then to the right to enter it.
- **Windows**: double-clicking the title bar collapses the window to a draggable bar; you can have multiple windows open, in popout or with content zoom.
- **Links between entries**: `[Entry name]` in square brackets in the text becomes a **link** on save (purple to handouts or characters, blue to compendium and URLs). It respects permissions: those without access cannot open it.
- **Compendium link**: the full URL of the compendium page (without `?` and `#`) opens in the internal compendium.
- **Show to players** (GM): opens the entry on players' screens. If they lack permission it asks whether to give it to everyone, and "Show to all" adds "All players" to the permissions. Since 2023 there's a notification when something is shown.
- **Dragging a handout onto a player's avatar**: gives them permission to view it and opens it for them immediately.
- **External journal** (Plus/Pro): web page outside the VTT with characters (Bio only) and handouts, updated in real time. The trick to search with Ctrl+F is to use the browser there, since in the VTT Ctrl+F is stolen.

### 16.2 Permissions (identical for characters and handouts)
| Field | Effect |
|---|---|
| **In player's journals** | whoever is listed (or "All") **sees** the entry. For a character they see only name, avatar and Bio: **not** the sheet or attributes |
| **Can be edited and controlled by** (characters) / **Can be edited by** (handouts) | for a character: they can pick it in "speaking as", edit name and Bio, **see and edit the sheet and attributes**, control the tokens representing it. For a handout: they see and edit it |
| **GM Notes** | always GM only |

To let a player play a PC the GM must add the player **in both** fields: a complaint, two steps for a common case.

### 16.3 Folders
- Subfolders limited to a few levels (about 4), "because of sidebar space": complaint.
- **Visibility**: a player sees a folder only if it contains at least one item visible to them. They do however see the **folder name** containing a shared handout, for example "Cursed items", and this can spoil things.
- Menu: add subfolder, character or handout; sort A-Z; rename; delete (items return to the root, with confirmation).

### 16.4 Character
- Window with tabs **Bio & Info**, **Character Sheet** (if there is a template) and **Attributes & Abilities**.
- **Edit** (GM only):
  - Name.
  - **Avatar** (drag from computer or Art Library).
  - **Default token**.
  - In player's journals / Can be edited and controlled by.
  - Tags.
  - Bio and GM Notes in rich text, with tables and paste from PDF or Word.
  - Duplicate ("Copy of ..."), Archive, Delete (with confirmation, irreversible).
- **Attributes**: name, current value, optional max. Whoever controls the character adds and edits them. With an active sheet the attributes mirror it, except repeating sections, and editing them by hand can break the sheet.
- **Abilities**: see §13.2. Reordered by dragging.

### 16.5 Handout
- Content: name, **image** (with magnifier and fullscreen if large), **Description & notes** (rich text visible to viewers, editable by editors), **GM Notes**, tags, duplicate, archive, delete.
- Pasting formatted content preserves the style.

### Complaints and [Frolls+]
- Performance collapses with hundreds of complex characters ([wiki Optimizing](https://wiki.roll20.net/Optimizing_Roll20_Performance), [forum](https://app.roll20.net/forum/post/7085783/character-sheets-very-slow-to-open), [forum](https://app.roll20.net/forum/post/12443273/high-level-character-sheets-cause-intense-lag-and-crash)). [Frolls+] Lazy loading of sheets and attributes only on open; lightweight journal index.
- [Frolls+] A single "**Assign to player**" button, which sets see plus control.
- [Frolls+] Full-text search in handout content (today the Search script is needed).
- [Frolls+] Folders with unlimited depth and folder names not visible to players, if chosen.
- [Frolls+] Players can create their own characters (GM setting). Today they can't without an option or a script ([wiki Player](https://wiki.roll20.net/Player)).

### Data
`Folder(id, game_id, parent_id, name, order)`, `Character(id, game_id, folder_id, name, avatar_asset_id, bio_html, gm_notes_html, tags[], in_journals[], controlled_by[], default_token_json, sheet_type: pc|npc, archived, is_party_member)`, `Attribute(id, character_id, name, current, max)` (index on lowercase `character_id+name`), `Handout(id, game_id, folder_id, name, image_asset_id, notes_html, gm_notes_html, tags[], in_journals[], editable_by[], archived)`

---

## 17. 5e character sheet (reference: "D&D 5E by Roll20", formerly 5th Edition OGL)

> Frolls implements a **5e compatible** sheet with **SRD 5.2 only** content (CC-BY-4.0) and its own names, without WotC trademarks. Below is the behavior of the Roll20 sheet, to be replicated in function, not in appearance.

### 17.1 Principles
- Saves automatically on every change.
- **Computed** fields are not editable.
- **Rollable labels** turn red on hover; clicking rolls with a roll template.
- Buttons are **draggable** to the macro bar.
- **Repeating sections** (attacks, inventory, spells, traits, proficiencies, resources): + add button; the **lock** toggles between "add" and "reorder/delete" (≡ drag, trash deletes **without confirmation**: complaint).
- PC sheet pages: **Core**, **Bio**, **Spells**, **Settings** (gear). **NPC** toggle for the monster sheet.

### 17.2 Core page
- **Header**: class (12 classes plus a custom one) and level, up to 4 classes when multiclassing; background, race or species, alignment, XP. The name is synced with the journal name.
- **Ability scores** (STR, DEX, CON, INT, WIS, CHA): score and **modifier = floor((score−10)/2)** (attributes `strength`, `strength_mod`...). Racial bonuses go in the settings.
- **Inspiration** (toggle).
- **Proficiency bonus**: computed from total level. Alternatively "proficiency die" or custom.
- **Saving throws**: proficiency checkboxes, preset from the main class; optional global modifier (e.g. `1d4[Bless]`).
- **Skills**: 18, with ability in parentheses, proficiency, **Expertise**, **Jack of all trades** (half proficiency), flat bonuses; global skill modifier (e.g. `1d4[Guidance]`).
- **AC**: automatic (10 + DEX + equipped armor), custom (up to 2 attributes) or manual; global AC modifiers in an optional repeating section. Multiple equipped armors make a **red warning** appear.
- **Initiative**: computed from DEX plus a bonus; normal, advantage or disadvantage style; optional **DEX tie-breaker** as a decimal (e.g. 2.14). Clicking with the token selected sends it to the tracker.
- **Speed**.
- **HP**: current, max and **temporary**. Damage reduces temporary first.
- **Hit dice**: type from class, number from level, available; clicking asks how many to roll per type.
- **Death saving throws**: roll plus success and failure checkboxes, with modifier.
- **Exhaustion** (optional): shows the effects but **does not apply them**.
- **Attacks & spellcasting** (repeating): name, ability (STR, DEX, spellcasting or none), proficient, bonus, magic bonus, range, **damage 1** and **damage 2** (formula, ability, type), **saving throw** (ability, DC, "half damage" effect), description, **crit range**. Global attack and damage modifiers.
- **Traits, ideals, bonds and flaws**: lockable fields (line breaks are stripped: complaint).
- **Class and other resources** (repeatable): value, max and name; linkable to an item ("use as resource": the quantity is synced). Ammunition taken from the compendium links automatically.
- **Tools and custom skills**: proficiency, expertise or jack of all trades; fixed ability or **asked with a query**.
- **Other proficiencies and languages**: plain text or typed list (Language, Weapon, Armor, Other).
- **Equipment**: "Simple" (text) or "Compendium compatible" (list). Each item has quantity, name, weight, equipped, use as resource, properties and **MODS**. MODS is a comma-separated `Stat: n` string (e.g. `Strength: 21`, `AC +1`, `Animal Handling +3`) and modifies stats **only if the item is equipped**; the modified stat becomes **blue with an asterisk** and the base value shows on hover. Coins: CP, SP, EP, GP, PP. **Encumbrance**: total weight and ENCUMBERED, HEAVILY ENCUMBERED, IMMOBILE states (optional variant).
- **Features & traits** (repeating): name, source, description.

### 17.3 Spells page
- Spellcasting ability (automatic from class), **DC = 8 + proficiency + mod** and **attack bonus = proficiency + mod**, both computed.
- Levels 0 (cantrips) to 9: **total slots** (from caster level, with multiclassing and manual modifiers) and slots remaining.
- Spell (repeating): name, school, ritual, casting time, range, target, V/S/M components and materials, concentration, duration, "Spellcard" or "Attack" output (in that case it adds an entry to Attacks), attack type, damage, saving throw, **at higher levels** (die per slot level), description and class.
- Toggleable R, C, V, S, M icons.

### 17.4 Sheet settings
Hit dice, carrying capacity modifier, manual caster level, DC modifier, halfling Luck (rerolls 1s, i.e. `ro1`), multiclassing, custom class, extra slots, ability score modifiers, initiative, AC, saves and death saves, passive perception. General options:
- **Advantage**: "Always roll 2d20" (Roll20 default: the left one is used if there is no advantage), "Toggle" (Advantage/Normal/Disadvantage buttons at the top of the sheet), "Query", "Never".
- **Whisper rolls to GM**: never, toggle, query, always.
- **Auto damage**: if off, damage is hidden and shown by clicking the attack name in chat.
- **Base die** (default 1d20).
- **Character name in templates**.
- **Automatic calculations on level up**.
- **Ammunition tracking** (with the companion script).
- Show exhaustion.
- Sheet defaults are set in the game; "Apply default settings" extends them to existing sheets.

### 17.5 NPC sheet (monster)
- **NPC options** (collapsible): name, size, type, alignment, AC and AC description, HP and formula, speed, ability scores, saves and skills (**they appear in the block only if filled in**; 0 to show them anyway), vulnerabilities, resistances, immunities, condition immunities, senses, languages, **CR** (**XP is computed** from CR), "NPC spellcaster" (adds the spell list), "has reactions", "legendary actions" (count).
- **Stat block** with everything clickable: Traits, Actions, Bonus actions, Reactions, Legendary actions, Spells. An action can be an attack (roll, damage 1 and 2, crit) or text.
- Own options: whisper to GM (recommended for NPCs), auto damage, NPC name in rolls (off by default, so the monster isn't revealed), initiative tie-breaker.

### 17.6 Sheet roll templates
- **simple**: one roll or a double roll for advantage/disadvantage, with the ability name.
- **atk/dmg/atkdmg**: attack on top, info in the middle, damage at the bottom, crit with extra damage.
- **spell**: spell card in chat.
- **npcatk/npcaction**: NPC actions.
- **traits** and **desc**.
- With "always roll advantage" the two d20s are side by side and the chosen one is highlighted (with the toggle active).

### 17.7 Charactermancer
Guided creation and level-up wizard based on the compendium. Doesn't work in popout.

### Complaints and [Frolls+]
- Performance: hundreds of attributes per sheet and lag with high-level sheets ([forum](https://app.roll20.net/forum/post/12443273/)). [Frolls+] Attributes in JSONB per character, derived calculations client-side and validated server-side.
- No formatting in text fields; line breaks are stripped.
- Deleting an entry from a repeating section happens **without confirmation** and **without undo**. [Frolls+] Undo and trash.
- Exhaustion doesn't apply penalties. [Frolls+] 5e conditions that actually apply advantage and disadvantage where possible.
- [Frolls+] "**Apply damage/healing**" button from the chat template to the selected tokens, with resistances. Today a script is needed (ApplyDamage, ChatSetAttr).
- [Frolls+] Short and long rest in one click (restoring HP, hit dice, slots and resources).

---

## 18. Compendium

- Collection of **indexed rules** like a mini-wiki: rules, classes, races, monsters, spells, items. Consulted **outside** and **inside** the VTT (sidebar tab, visible to GM and players). Entries open in separate windows.
- **Lists** (spells, monsters) with an expandable data block per entry, filters, search and source (book) icon.
- **Dragging**:
  - **Non-monster entry onto the tabletop**: creates a **handout** with text and images (it's also the way to share purchased content).
  - **Monster onto the tabletop**: creates a **complete NPC character** with the sheet filled in and a **linked token** (if available) placed at that spot.
  - **Monster onto an open sheet**: converts it to an NPC and **adds** (doesn't replace) the data.
  - **Item or spell onto the sheet**: "ACCEPTING DROP FROM COMPENDIUM" appears and dropping fills in the right section; weapons also create an attack, items with MODS are applied, ammunition becomes resources.
- **Settings**: compendium given by the sheet template or chosen by hand; **sharing** of purchased compendiums with the game's players; selection of active expansions.
- **The most voted complaint of all those seen: "Custom Compendium" at +1732** ([forum](https://app.roll20.net/forum/post/2940484/)). Today you can neither create nor edit the compendium.
- [Frolls+] **Built-in SRD 5.2 compendium** plus a game or account **custom compendium** (homebrew monsters, items and spells with the same data structure), importable and exportable as JSON.

### Data
`CompendiumEntry(id, source: srd|homebrew, owner_id?, kind: monster|spell|item|rule|class|race|condition, name, data_json, text_md, image_asset_id?)`

---

## 19. Art Library and assets

- **GM only** (players have no Art Library; complaint: they can't upload their own token or avatar).
- **Search**: My Library, Purchases, Pro sets, free assets, premium and "from the web" (old index). Multiple words are **AND**, explicit `OR`, `-word` excludes. Type filters: tokens, maps, tiles, textures, portraits. Small or large thumbnails.
- **Upload**: drag a file onto the tabletop (uploads and places) or from the dialog **up to 10 files at a time**. **Limit per file or batch: 5 MB** free, **10 MB** for subscribers (fails near the limit). Types: **jpg, png, gif, animated gif, mp4, webm, PDF** (you pick the page to convert). `.jpeg` used to be rejected: bug. Animated uploads are slow or time out ([wiki](https://wiki.roll20.net/Art_Library)).
- **Storage quota**: 100 MB free, 3 GB Plus, 8 GB Pro, 50 GB Elite. Exceeding it blocks uploads but deletes nothing. Marketplace content doesn't count.
- **Recent Uploads**: all images in chronological order. Folders are **references**. Deleting from Recent Uploads deletes **permanently**, also from games using it.
- **Folders** (up to 3 levels) with menu: subfolder, sort A-Z, rename, delete (images go back to Recent).
- **Folder view**: multi-select, move, delete, **tags** (the file name becomes a tag; space or Enter confirm the tag).
- **Copy to library**: creates references to premium assets without using quota.
- [Frolls+] Larger uploads; automatic conversion to WebP or AVIF; hash deduplication; generated thumbnails; "this image is used on N pages" warning before deleting it; **players can upload avatars and tokens for their own characters** within a quota.

### Data
`Asset(id, owner_user_id, storage_key, mime, bytes, width, height, sha256, animated, created_at)`, `AssetFolder(id, owner_user_id, parent_id, name)`, `AssetTag(asset_id, tag)`

---

## 20. Visual effects and 3D dice (low priority)

- **FX** (GM, Pro): `/fx type-color sourceId [targetId]`. Types: beam, bomb, breath, bubbling, burn, burst, explode, glow, missile, nova, splatter. Colors: acid, blood, charm, death, fire, frost, holy, magic, slime, smoke, water. Beam and breath are **directional** (source and target); the others are area effects (source only). There are custom effects and an FX tool to place them with the mouse.
- **3D dice**: physics simulation above the tabletop (WebGL). With "Dice Agency" you drag to throw; otherwise the throw is automatic. Player color. The d100 uses two d10s (00-90 and 0-9). You see others' dice if they also have the option enabled. **In case of discrepancy the chat is authoritative**: templates can roll dice that are then hidden. Disabled per user.
- [Frolls decision] 3D dice must be **only an animation** of a result already computed by the server, so there are no discrepancies.

---

## 21. Map Pins (2025)

- The GM drags a **handout** (or a heading or anchor inside a handout) onto the map and creates a **pin** that takes its image, title, text and GM notes.
- The "Place pin" tool and right-click on the map also create unlinked pins.
- "**Blockquote as player text**" option: the first quote goes into the players' tooltip, the rest into the GM notes.
- Pins can be **resized**.
- Sources: [Help Center](https://help.roll20.net/hc/en-us/articles/36271267343639-Map-Pins-Early-Access), [blog](https://blog.roll20.net/posts/map-pins-open-beta/).

### Data
`Pin(id, page_id, x, y, scale, handout_id?, anchor?, title, player_text, gm_text, icon, visible_to_players)`

---

## 22. API / Mod scripts (Pro), summary only

- **JavaScript** scripts run in a server-side sandbox of the game. Installed from a community repository ([roll20-api-scripts](https://github.com/Roll20/roll20-api-scripts)) or written by hand. Reserved for the Pro Creator.
- **Reactive** (`chat:message`, `change:graphic`, `add:...` events) and **proactive** (timers). They can read and modify all objects, create handouts, send chat messages and handle `!command` commands.
- The most used scripts show what's missing from the base product, so they are the **Frolls wish list**:
  - **TokenMod**: edit tokens from chat.
  - **ChatSetAttr**: edit attributes from chat.
  - **GroupInitiative**: group initiative.
  - **TurnMarker**: turn indicator.
  - **CombatMaster / RoundMaster**: conditions with duration.
  - **ApplyDamage**.
  - **TokenNameNumber**.
  - **MonsterHitDice**.
  - **Search**: search in handouts.
  - **DiscreteWhisper**.
  - **Blind roll**.
  - **TableExport / RecursiveTable**.
  - **Teleport**.
  - **MarchingOrder**.
  - **5e Companion**: automatic ammunition, slots, hit dice.
- [Frolls decision] No scripting system in the first phase: the features above become **native features**. In the future, a plugin system with permissions.

---

## 23. Settings

### 23.1 Game settings (web page, Creator)
- Public access (journal and archive visible to visitors).
- Game page background.
- **Allow players to import characters** (from the Character Vault).
- **Page defaults**: all page settings except play-on-load, archive and delete.
- **Token defaults**: bar values, auras, tint, nameplate and see/edit permissions for name, bars and auras.
- Compendium: system, sharing, expansions.
- **Sheet template** and **sheet defaults** (§17.4).
- "**Apply default settings**" (in game, GM) applies page, token and sheet defaults to **all existing content**, with a progress bar, interruptible with Esc and **irreversible**.
- Changes on the settings page require **reloading** an already open game: complaint. [Frolls+] Live settings, inside the VTT.

### 23.2 My Settings (sidebar, per user and per game)
Display name; advanced shortcuts; automatic popouts for characters and handouts; chat beep; advanced dice; 3D dice and auto-roll; chat avatars; timestamps; token actions in alphabetical order; wheel zoom or pan; clear log; exit; rejoin as player.

**GM only**: bar colors, marker position, deck size, apply defaults.

### 23.3 Player color
Chosen with the swatch next to your name in the player area. Used for pings, dice, measurements and the avatar frame.

---

## 24. Other features

- **Character Vault**: personal account archive. **Import** a character from a game (edit permissions required) as a **snapshot** that doesn't update; to update it you delete and reimport. **Export** to another game: requires the GM to allow it and a full Vault (subscription or module); since July 2023 free users can export up to 3 characters per game. Works across games by different creators too. Saves avatar, token, sheet and stats.
- **Transmogrifier** (Pro): copies pages (with tokens), characters, handouts, decks and tables between **your own games** with drag & drop between two lists. Copies, doesn't move. Warns on overwrite (same original ID). **Doesn't copy players or macros**, so "Controlled by" must be redone. Used for the "library campaign" that lightens games.
- **Default keyboard shortcuts**:
  - Layers: Ctrl+M/O/K, Ctrl+Shift+M/O/K.
  - Edit: Ctrl+C/V/Z/A, Del.
  - Tools: Ctrl+S select, Ctrl+F freehand, Ctrl+G text, Ctrl+U add turn.
  - Measurement and movement: Q, Shift, X; Alt to ignore snap; arrows; E+wheel; right-click+drag to pan; Z and Shift+Z.
  - Selection: Alt+rectangle (drawings).
  - Characters and macros: Shift+double-click on the token, Shift+click on macro.
  - GM: Ctrl+T rejoin as player.
- **Advanced shortcuts** (optional): single-key sequences (e.g. `F R` for shapes, `C C` to focus chat), show/hide sidebar, focus journal search.
- **External journal, chat archive and game forum**: see above.
- **Marketplace modules and addons**: ready-made adventures installed into a game, with patches that update only changed items. Out of scope for now; keep the game import and export format in mind.
- **UVTT import** (2026): map with walls, doors and lights from a Universal VTT file. Useful for importing maps even without lights: only the image and the grid are imported.
- **Mobile app**: Roll20 has limited iPad and Android apps. [Frolls+] Responsive interface.

---

## 25. Cross-cutting complaints (summary for priorities)

| Problem | Source | Frolls answer |
|---|---|---|
| Dated interface and steep learning curve | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/), [StoryRoll](https://storyroll.app/blog/best-online-dnd-platforms) | Modern UI, separate for GM and player, consistent shortcuts |
| Performance: low FPS with many tokens or large assets, slow sheets, bloated games | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/), [wiki Optimizing](https://wiki.roll20.net/Optimizing_Roll20_Performance), [forum](https://app.roll20.net/forum/post/4192520/big-campaign-and-slow-performance) | PixiJS, delta sync, lazy loading of pages and sheets |
| Basic features behind a subscription (lighting, API, rollback, quota) | [Subscription](https://wiki.roll20.net/Subscription), [Elite](https://app.roll20.net/forum/post/12542863/) | No paywall on gameplay features |
| Single-level undo | [forum](https://app.roll20.net/forum/post/3210982/) | Multi-level undo/redo per user |
| No blind rolls | [forum +410](https://app.roll20.net/forum/post/4922089/) | Native `/br` |
| No custom compendium | [forum +1732](https://app.roll20.net/forum/post/2940484/) | Homebrew compendium |
| Turn tracker without rounds or automation | [forum](https://app.roll20.net/forum/post/11481189/) | Rounds, conditions, group initiative |
| Fragile macros (HTML entities, nested queries) | [wiki Macros](https://wiki.roll20.net/Macros) | Robust parser, editor with preview |
| Small tokens not centered | [forum +235](https://app.roll20.net/forum/post/2309394/) | Snap to center |
| Players without upload, resizing or z-order | [wiki Player](https://wiki.roll20.net/Player) | Granular permissions decided by the GM |
| Ctrl+F stolen from the browser | [wiki Journal](https://wiki.roll20.net/Journal) | Internal search, no shortcut stealing |
| Criticized customer support and moderation, 2018 breach | [octobergeek](https://octobergeek.wordpress.com/2018/09/30/why-im-staying-with-roll20-for-now/), [HIBP](https://haveibeenpwned.com/Breach/Roll20) | Security by design, full data export |
| Owlbear: 30-second setup, no account for players, mobile-friendly | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/) | Invite link that leads straight to the table; guest entry to be evaluated |
| Foundry: automation and modules | [scriptoriumgm](https://www.scriptoriumgm.com/blog/best-virtual-tabletop-vtt-systems) | Native 5e automation, plugins in the future |

---

## 26. Recommended implementation order (vertical slices)

Each slice is **end-to-end**: Postgres model, API or WebSocket messages, Svelte or Pixi UI and tests. The order takes user decisions into account: auth last, a single persistent game until then, dice in chat without a command.

**Current order (2026-10-20).** Slices 2, 3, 4 (basic chat and dice), 9, 10 (ruler and circle only), 11 and the basic turn tracker are done. Slice 1 is complete since 2026-10-20: event log with sequence numbers, resume after a reconnection with only the missed changes, per-player undo/redo of map changes and a GM history that reverts anyone's change. Slice 6 is in progress: characters, nested folders, search, archive, token link (`represents`) and drag onto the map are done; players speak with their character's name automatically and only the GM has "speaking as". Handouts, journal permissions and bars linked to attributes are in the backlog. Slice 7 is done for the core: server-side expansion of `#macro`, `%{}` abilities, `@{}` attributes (selected, target, max, token bars), roll queries in a single dialog, the default roll template, chat buttons, personal macros with a quick bar and token actions from character abilities (`&{tracker}`, shared macros and other templates later). Then: the rest of 4 (groups, `m`/`mt`, `cs`/`cf`, `/as`, hidden rolls), 12-13 5e sheet and SRD 5.2 compendium (with the effects and durations engine, damage and death, 5e token sizes and monster HP visibility), manual fog of war, 14-16, 17, and 18 accounts together with GDPR, Italian translation, daily backups and measured performance targets. The MVP checklist that tracks this lives outside the repo.

1. **Persistence and shared state**: Postgres (pages, tokens, events), loading a snapshot on join, delta sync, per-user undo/redo (basis of §7.2). *Exit*: tokens persist after restart.
2. **Base canvas**: a page with size, background color, **square and hex grid**, scale and units; zoom, pan, arrows; **ping and pull ping**; upload of a **map image** (S3 or MinIO storage, or local in dev) on the map layer.
3. **Tokens v1**: creation from upload, movement with snap and Alt, resizing (GM), rotation, flip, multiple and rectangle selection, group, z-order, copy/paste/delete, lock, **map, objects and GM layers** with visibility rules, waypoints and last move.
4. **Full dice engine (server)** plus **chat**: grammar §12.14, all modifiers, groups, inline, labels, `/r /gr /w /em /ooc /desc /as /emas /talktomyself`, automatic rolling of expressions, `/br`, rendering of dice and breakdown, persistent archive with pagination. Property tests on the parser.
5. **Tokens v2**: settings dialog, **bars 1-4** (value, max, permissions, location and style), bubbles with relative values, **auras**, **markers** with numbers (SRD condition set), nameplate, tooltip, tint, GM notes, controlled by.
6. **Journal v1**: folders, **characters** (bio, GM notes, avatar, attributes, abilities), **handouts**, see/edit permissions plus "assign to player", show to players, `[Name]` links, archive, search. **Default token**, drag from the journal, **bars linked to attributes**, "speaking as".
7. **Macros and references**: `@{}` (selected, target, max, repeating, tracker), `%{}`, `#`, roll queries with a single dialog, order of operations §12.12, `&{noerror}`, **default roll template**, chat buttons, Collections macros, **quick bar**, **token actions**.
8. **Turn tracker**: add turn, `&{tracker[:+|:-]}`, custom entries with formula, forward and back, sorting, visibility per page and GM layer, **rounds**, highlighted turn, group initiative.
9. **Multiple pages**: page toolbar, folders, duplicate, archive, delete with constraints, **Player Ribbon**, **split party**, Define/Place Party, full page settings with diagonal rules, copying tokens between pages.
10. **Measurement and AoE**: ruler with snap and visibility, waypoints, line, square, circle, cone (53.13°), beam; persistent templates with affected cells and tokens.
11. **Drawing**: shapes, freehand, polygon, text, colors and widths, eraser, clear layer, "players can draw" permission.
12. **5e PC sheet** (SRD): automatic calculations, rolls with simple, atk and spell templates, advantage, whisper, repeating sections with undo, inventory with MODS, spells and slots, resources, rests; then the **NPC sheet** with clickable stat block.
13. **SRD compendium** with drag & drop (monster on the tabletop becomes NPC plus token; item or spell onto the sheet; entry becomes handout), then the **homebrew compendium**.
14. **Rollable tables** (`1t[...]`, inline, weights, nested) and **multi-sided tokens**.
15. **Card decks**: standard deck, draw, play, hand, deal, steal, trade, discards, cards in the tracker.
16. **Full Art Library**: folders, tags, quota, search, bulk upload, PDF to image, animations, player uploads.
17. **Gameplay polish**: map pins, zoom view (Z, Shift+Z), FX, 3D dice as animation only, live personal and game settings, advanced shortcuts, apply defaults.
18. **Accounts and games (last, as decided)**: registration, OAuth (Google and Discord), multiple games, Creator, GM and Player roles, **invite link** regenerated on kick, promotion and demotion, game details, game copy, full game export and import (JSON plus assets), Character Vault.
19. **Future**: plugin system (instead of the API), marketplace, LFG, game forum, UVTT import. Then the deferred features below.

---

## 27. Deferred (out of scope for now)

- **Voice and video**: dropped, not to be developed.
- **Audio / Jukebox** (playlists, page play-on-load, volume).
- **Fog of war, advanced** (the basic manual reveal/hide is in the MVP, after the 5e sheet).
- **Dynamic lighting** (walls, doors, windows, lights, darkness, lighting layer).
- **Vision and line of sight** (sight, darkvision, Ctrl+L, movement restriction).

---

## 28. Sources

**Roll20 wiki (community; read via the Wayback Machine)**
- [Dice Reference](https://wiki.roll20.net/Dice_Reference) · [Order of Operations](https://wiki.roll20.net/Order_of_Operations) · [Inline Rolls](https://wiki.roll20.net/Inline_Rolls) · [Roll Query](https://wiki.roll20.net/Roll_Query) · [Reusing Rolls](https://wiki.roll20.net/Reusing_Rolls) · [Hidden Rolls](https://wiki.roll20.net/Hidden_Rolls) · [Roll Templates](https://wiki.roll20.net/Roll_Templates) · [Default Roll Template](https://wiki.roll20.net/Default_Roll_Template) · [Dice Rolling GUI](https://wiki.roll20.net/Dice_Rolling_GUI) · [3D Dice](https://wiki.roll20.net/3D_Dice)
- [Text Chat](https://wiki.roll20.net/Text_Chat) · [Chat Archive](https://wiki.roll20.net/Chat_Archive) · [Chat Menus](https://wiki.roll20.net/Chat_Menus)
- [Macros](https://wiki.roll20.net/Macros) · [Token Actions](https://wiki.roll20.net/Token_Actions) · [Collections](https://wiki.roll20.net/Collections)
- [Token Features](https://wiki.roll20.net/Token_Features) · [Manipulating Tokens](https://wiki.roll20.net/Manipulating_Tokens) · [Token Markers](https://wiki.roll20.net/Token_Markers) · [Token Tooltip](https://wiki.roll20.net/Token_Tooltip) · [Token Lock](https://wiki.roll20.net/Token_Lock) · [Token Z-Ordering](https://wiki.roll20.net/Token_Z-Ordering) · [Multi-Sided Token](https://wiki.roll20.net/Multi-Sided_Token) · [Linking Tokens to Journals](https://wiki.roll20.net/Linking_Tokens_to_Journals) · [Waypoint](https://wiki.roll20.net/Waypoint)
- [Page Settings](https://wiki.roll20.net/Page_Settings) · [Page Toolbar](https://wiki.roll20.net/Page_Toolbar) · [Layers](https://wiki.roll20.net/Layers) · [Foreground Layer](https://wiki.roll20.net/Foreground_Layer) · [Ruler](https://wiki.roll20.net/Ruler) · [Zoom Tool](https://wiki.roll20.net/Zoom_Tool) · [Ping](https://wiki.roll20.net/Ping) · [Tabletop](https://wiki.roll20.net/Tabletop) · [Select Tool](https://wiki.roll20.net/Select_Tool) · [Drawing Tools](https://wiki.roll20.net/Drawing_Tools) · [Toolbox](https://wiki.roll20.net/Toolbox) · [Toolbar & Layers Redesign](https://wiki.roll20.net/Toolbar_%26_Layers_Redesign) · [Keyboard Shortcuts](https://wiki.roll20.net/Keyboard_Shortcuts) · [Advanced Shortcuts](https://wiki.roll20.net/Advanced_Shortcuts)
- [Turn Tracker](https://wiki.roll20.net/Turn_Tracker) · [Card Decks](https://wiki.roll20.net/Card_Decks) · [Rollable Table](https://wiki.roll20.net/Rollable_Table)
- [Journal](https://wiki.roll20.net/Journal) · [Handouts](https://wiki.roll20.net/Handouts) · [Character Sheet](https://wiki.roll20.net/Character_Sheet) · [D&D 5E by Roll20](https://wiki.roll20.net/D%26D_5E_by_Roll20) · [Compendium](https://wiki.roll20.net/Compendium) · [Art Library](https://wiki.roll20.net/Art_Library) · [Archiving](https://wiki.roll20.net/Archiving)
- [Game Details / Game Management](https://wiki.roll20.net/Game_Management) · [Game Settings](https://wiki.roll20.net/Game_Settings) · [My Settings](https://wiki.roll20.net/My_Settings) · [Player](https://wiki.roll20.net/Player) · [Gamemaster](https://wiki.roll20.net/Gamemaster) · [Character Vault](https://wiki.roll20.net/Character_Vault) · [Transmogrifier](https://wiki.roll20.net/Transmogrifier) · [Fx Tool](https://wiki.roll20.net/Fx_Tool) · [API Introduction](https://wiki.roll20.net/API:Introduction) · [Optimizing Roll20 Performance](https://wiki.roll20.net/Optimizing_Roll20_Performance) · [Subscription](https://wiki.roll20.net/Subscription)

**Roll20 Help Center and blog**
- [Measure Tool](https://help.roll20.net/hc/en-us/articles/360039674913-Measure-Tool) · [Turn Tracker](https://help.roll20.net/hc/en-us/articles/360039178634-Turn-Tracker) · [Token Features](https://help.roll20.net/hc/en-us/articles/360039674573-Token-Features) · [Map Pins](https://help.roll20.net/hc/en-us/articles/36271267343639-Map-Pins-Early-Access) · [2025 Change Log](https://help.roll20.net/hc/en-us/articles/38597501957015-2025-Change-Log)
- [New Measure Tool Shows AoE and Shapes](https://blog.roll20.net/posts/new-measure-tool-shows-aoe-and-shapes/) · [Jumpgate Officially Launches](https://blog.roll20.net/posts/the-future-of-tabletop-gaming-jumpgate-officially-launches/) · [Map Pins open beta](https://blog.roll20.net/posts/map-pins-open-beta/) · [Define and Place Party](https://blog.roll20.net/posts/define-and-place-party/)

**Roll20 forum**
- Suggestions: [Custom Compendium +1732](https://app.roll20.net/forum/post/2940484/) · [GM rolls hidden from the player +410](https://app.roll20.net/forum/post/4922089/) · [Secret rolls](https://app.roll20.net/forum/post/11459035/) · [Centered small tokens +235](https://app.roll20.net/forum/post/2309394/) · [Transmogrifier folders +583](https://app.roll20.net/forum/post/3234668/) · [Fixing Initiative and the Turn Tracker](https://app.roll20.net/forum/post/11481189/fixing-initiative-and-the-turn-tracker) · [Round counter](https://app.roll20.net/forum/post/494250/) · [Turn Tracker Enhancements](https://app.roll20.net/forum/post/1170023/) · [More bars](https://app.roll20.net/forum/post/1285136/) · [4th bar](https://app.roll20.net/forum/post/11729667/) · [Undo for players](https://app.roll20.net/forum/post/8760735/player-undo-button-ctrl-plus-z) · [Undo/Redo](https://app.roll20.net/forum/post/3210982/please-review-the-undo-slash-redo-code) · [Eraser](https://app.roll20.net/forum/post/3756/eraser-tool) · [Advanced decks](https://app.roll20.net/forum/permalink/2793233/) · [Advanced rulers](https://app.roll20.net/forum/post/8270654/advanced-rulers-cone-square-circles-beam)
- Bugs and technical: [Z-order not synced](https://app.roll20.net/forum/post/8928459/) · [Tokens always on top](https://app.roll20.net/forum/post/11577293/) · [Token bar redesign](https://app.roll20.net/forum/post/7396014/token-bar-redesign-bug-thread) · [Slow sheets](https://app.roll20.net/forum/post/7085783/character-sheets-very-slow-to-open) · [High-level sheets and crashes](https://app.roll20.net/forum/post/12443273/high-level-character-sheets-cause-intense-lag-and-crash) · [Big slow campaign](https://app.roll20.net/forum/post/4192520/big-campaign-and-slow-performance) · [Dice limits](https://app.roll20.net/forum/post/9164629/) · [No min/max](https://app.roll20.net/forum/post/1146425/) · [Player drawing resizing](https://app.roll20.net/forum/post/11501167/) · [Release Notes May 23rd 2025](https://app.roll20.net/forum/post/12372218/release-notes-may-23rd-2025) · [Party Tools](https://app.roll20.net/forum/post/12465889/gm-time-save-alert-party-tools-are-here) · [Elite](https://app.roll20.net/forum/post/12542863/introducing-roll20-elite-5x-storage-4x-sharing-and-more)

**Public repositories**
- [Roll20/roll20-character-sheets](https://github.com/Roll20/roll20-character-sheets) · [Roll20/roll20-api-scripts](https://github.com/Roll20/roll20-api-scripts) (cited only as a reference to the ecosystem; no code was read)

**Reviews, comparisons and news**
- [GM Craft Tavern: Foundry vs Roll20 vs Owlbear 2026](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/) · [StoryRoll: Best Online D&D Platforms 2026](https://storyroll.app/blog/best-online-dnd-platforms) · [Scriptorium GM: VTT compared](https://www.scriptoriumgm.com/blog/best-virtual-tabletop-vtt-systems) · [Black Lantern Forge](https://blacklanternforge.com/blogs/news/roll20-vs-foundry-vtt-vs-owlbear-rodeo-which-virtual-tabletop-is-right-for-your-campaign) · [Dice Outpost](https://www.diceoutpost.com/guides/best-vtt-for-beginners/) · [Bell of Lost Souls: Party Tools](https://www.belloflostsouls.net/2025/08/roll20-unleashes-powerful-new-party-tools-after-recent-jumpgate-upgrades.html) · [GamingTrend: Map Pins](https://gamingtrend.com/news/roll20-unveils-new-map-pins-feature/) · [Have I Been Pwned: Roll20](https://haveibeenpwned.com/Breach/Roll20) · [October Geek](https://octobergeek.wordpress.com/2018/09/30/why-im-staying-with-roll20-for-now/) · [Wikipedia: Roll20](https://en.wikipedia.org/wiki/Roll20)

**Research limitations**: Reddit (r/Roll20, r/DnD) blocks automated access, so complaints come from the official forum, the wiki and reviews. The Help Center and wiki return 403 to direct requests, so wiki pages were read from archived copies, which may lag a few months behind on Jumpgate updates.
