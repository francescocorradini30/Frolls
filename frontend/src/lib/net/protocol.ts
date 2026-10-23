// Mirrors backend/app/game/protocol.py and serialize.py. Keep in sync.

export type Layer = 'map' | 'objects' | 'gm'
export type ObjectKind = 'token' | 'image' | 'path' | 'text' | 'template' | 'pin'
export type GridType = 'square' | 'hex_v' | 'hex_h' | 'none'
export type DiagonalRule = '5e' | 'pf' | 'euclid' | 'manhattan'
export type Measurement = 'metric' | 'imperial'

/** Personal preferences, only ever sent to the player itself. */
export interface PlayerSettings {
  wheel?: 'zoom' | 'pan'
  chat_timestamps?: boolean
}

export interface Player {
  id: string
  name: string
  color: string
  is_gm: boolean
  online: boolean
  settings?: PlayerSettings
}

export interface Page {
  id: string
  name: string
  sort_order: number
  archived: boolean
  width: number
  height: number
  grid_size: number
  grid_type: GridType
  grid_color: string
  grid_opacity: number
  snap: boolean
  scale_number: number
  scale_unit: string
  diagonal_rule: DiagonalRule
  background_color: string
  /** Manual fog of war: areas revealed or hidden, in order (the last one wins). */
  fog?: { enabled: boolean; ops: FogArea[] } | null
}

export interface FogArea {
  mode: 'reveal' | 'hide'
  shape: 'rect' | 'poly'
  /** Rectangle: two corners; polygon: its points. Page pixels, flattened. */
  points: number[]
}

export interface Bar {
  value: number | null
  max: number | null
  /** Monsters with hit points shown as a state only: "Bloodied"… (value/max are quarters). */
  state?: string
}

export type NpcHp = 'hidden' | 'status' | 'full'

/** Token stamp settings, see frontend/src/lib/util/stamp.ts (StoredStamp). */
export interface TokenStampProps {
  source: string
  border: 'none' | 'thin' | 'solid' | 'double' | 'bevel'
  borderColor: string
  background: string | null
  x: number
  y: number
  zoom: number
  rotation: number
}

export interface TokenProps {
  name?: string
  image?: string
  color?: string
  show_name?: boolean
  bar1?: Bar
  bar2?: Bar
  statuses?: string[]
  stamp?: TokenStampProps
  controlled_by?: string[]
  gm_notes?: string
  /** Journal character this token stands for (GM only). */
  represents?: string
}

export interface PathProps {
  shape: 'free' | 'rect' | 'ellipse' | 'polygon' | 'line'
  // Points relative to the object centre, flattened [x0, y0, x1, y1, ...]
  points?: number[]
  stroke: string
  stroke_width: number
  fill?: string | null
}

export interface TextProps {
  text: string
  color: string
  font_size: number
}

export interface TemplateProps {
  shape: 'circle' | 'cone' | 'line' | 'square'
  // Length/radius in page pixels; angle in degrees for cones.
  size: number
  angle?: number
  color: string
}

export interface MapObject {
  id: string
  page_id: string
  kind: ObjectKind
  layer: Layer
  x: number
  y: number
  width: number
  height: number
  rotation: number
  z: number
  owner_id: string | null
  props: Record<string, any>
}

export type TurnAction = 'action' | 'bonus_action' | 'reaction'

export interface TurnEntry {
  id: string
  object_id: string | null
  name: string
  value: string
  /** This turn: what was already used, and feet moved. */
  used?: Partial<Record<TurnAction, boolean>> | null
  moved?: number | null
}

/** A game option the GM can change (catalog: backend/app/game/options.py). */
export interface GameOption {
  key: string
  section: string
  label: string
  help: string
  default: OptionValue
  kind: 'bool' | 'choice' | 'int'
  choices: [string, string][]
  min: number
  max: number
}
export type OptionValue = boolean | number | string

export interface GameState {
  name: string
  player_page_id: string | null
  player_page_overrides: Record<string, string>
  turn_order: TurnEntry[]
  settings: { round?: number; measurement?: Measurement; npc_hp?: NpcHp; [k: string]: unknown }
}

export interface Die {
  value: number
  kept: boolean
  exploded: boolean
  rerolled: boolean
  success: boolean
  failure: boolean
}

export interface RollTerm {
  notation: string
  /** 'T': items drawn from a rollable table (`table`, `items`), no dice. */
  sides: number | 'F' | 'T'
  total: number
  success_mode: boolean
  dice: Die[]
  table?: string
  items?: { name: string; image: string | null }[]
}

export interface Roll {
  expression: string
  total: number
  breakdown: string
  terms: RollTerm[]
  /** Names drawn from a table, shown instead of the total when they aren't numbers. */
  text?: string | null
}

export type ChatKind = 'text' | 'roll' | 'emote' | 'ooc' | 'whisper' | 'system' | 'desc'

export interface ChatMessage {
  id: number
  created_at: string
  player_id: string | null
  speaker: string
  color: string
  kind: ChatKind
  content: string
  roll: { main: Roll | null; inline: Roll[]; template?: RollTemplate | null } | null
  recipients: string[] | null
  gm_only: boolean
}

export type ObjectPatch = { id: string } & Partial<Omit<MapObject, 'id' | 'owner_id' | 'kind'>>

export type PreviewItem = { id: string; x: number; y: number; rotation?: number }

/** A live measurement (ruler or token drag), in page pixels. */
export interface Segment {
  x1: number
  y1: number
  x2: number
  y2: number
  /** Waypoints between the two ends: flat [x, y, ...]. */
  via?: number[]
}

/** Macro of a character: `%{Name|ability}` runs it; token actions are buttons on the map. */
export interface Ability {
  name: string
  action: string
  token_action: boolean
}

/** My own macro, run with a click or with `#Name` in chat. */
export interface Macro {
  id: string
  name: string
  action: string
  in_bar: boolean
}

/** A rollable table: `1t[name]` in chat draws an item by weight. */
export interface RollableTable {
  id: string
  name: string
  items: TableItem[]
  /** Hidden tables are listed and rollable only by the GM. */
  show_players: boolean
}

export interface TableItem {
  id: string
  name: string
  weight: number
  image: string | null
}

export interface Card {
  id: string
  name: string
  image: string | null
}

export interface DeckSettings {
  show_players: boolean
  players_draw: boolean
}

/** What I know of a deck: everything for the GM; for a player, counts and my own hand. */
export interface Deck {
  id: string
  name: string
  back: string | null
  settings: DeckSettings
  size: number
  pile_count: number
  discard_count: number
  table_count: number
  /** player id -> number of cards in hand */
  hand_counts: Record<string, number>
  hand: Card[]
  /** GM only */
  cards?: Card[]
  hands?: Record<string, string[]>
  discard?: string[]
}

export type DeckActionKind = 'shuffle' | 'recall' | 'draw' | 'play' | 'discard' | 'take'

/** An image in my art library. */
export interface Asset {
  id: string
  name: string
  url: string
  thumb: string | null
  width: number
  height: number
  folder: string
  tags: string[]
}

/** A roll query the server asks before sending a message. */
export interface Query {
  prompt: string
  default: string
  /** [label, value]; two or more = a drop-down. */
  options: [string, string][]
}

export interface RollTemplate {
  name: string
  title: string
  fields: [string, string][]
}

// --- 5e sheet (mirror of backend/app/rules5e/sheet.py) -----------------------------

export type AbilityKey = 'str' | 'dex' | 'con' | 'int' | 'wis' | 'cha'
export type RollMode = 'normal' | 'advantage' | 'disadvantage'

export interface SheetAttack {
  id: string
  name: string
  kind: 'attack' | 'save'
  ability: AbilityKey | 'spell' | 'none'
  proficient: boolean
  bonus: number
  to_hit: number | null
  damage: string
  damage_type: string
  add_modifier: boolean
  save: AbilityKey | null
  dc: number | null
  half_on_save: boolean
  range: string
  notes: string
}

export interface SheetSpell {
  id: string
  name: string
  level: number
  prepared: boolean
  concentration: boolean
  ritual: boolean
  attack: boolean
  save: AbilityKey | null
  half_on_save: boolean
  damage: string
  damage_type: string
  upcast: string
  duration: string
  description: string
  /** Effect preset it puts on its targets (on a failed save, if it has one). */
  effect?: string | null
}

/** Mirror of Effect in backend/app/rules5e/effects.py; lives in a token's `props.effects`. */
export interface Effect {
  id: string
  name: string
  concentration_of: string | null
  ending: { when: 'start' | 'end'; of: string; rounds: number } | null
  duration: string
  dice: Partial<Record<'attack' | 'check' | 'save', string>>
  bonus: Partial<Record<'attack' | 'check' | 'save', number>>
  ac: number
  advantage: ('attack' | 'check' | 'save')[]
  disadvantage: ('attack' | 'check' | 'save')[]
  dex_save_advantage: boolean
  attacked_with: 'advantage' | 'disadvantage' | null
  condition: string | null
  repeat_save: { ability: AbilityKey; dc: number } | null
}

export interface SheetResource {
  id: string
  name: string
  max: number
  used: number
  reset: 'short' | 'long' | 'none'
}

export interface Sheet {
  kind: 'pc' | 'npc'
  level: number
  classes: string
  species: string
  background: string
  cr: string
  creature_type: string
  size: 'tiny' | 'small' | 'medium' | 'large' | 'huge' | 'gargantuan'
  abilities: Record<AbilityKey, number>
  save_proficiencies: AbilityKey[]
  /** Skill -> 1 proficient, 2 expertise. */
  skills: Record<string, 1 | 2>
  ac: number
  /** Feet. */
  speed: number
  initiative_bonus: number
  hp: { current: number; max: number; temp: number }
  hit_dice: { die: 6 | 8 | 10 | 12; spent: number }
  death_saves: { successes: number; failures: number }
  exhaustion: number
  attacks: SheetAttack[]
  spellcasting: { ability: AbilityKey | null; slots: Record<string, { max: number; used: number }> }
  spells: SheetSpell[]
  resources: SheetResource[]
  resistances: string[]
  immunities: string[]
  vulnerabilities: string[]
  condition_immunities: string[]
  features: string
}

/** Values computed by the server from the sheet: never stored. */
export interface SheetDerived {
  proficiency: number
  modifiers: Record<AbilityKey, number>
  saves: Record<AbilityKey, number>
  skills: Record<string, number>
  passive_perception: number
  initiative: number
  spell_dc: number | null
  spell_attack: number | null
  xp: number | null
  attacks: Record<string, { to_hit: number | null; dc: number | null; damage: string }>
  hit_dice_total: number
}

export type CompendiumKind = 'monster' | 'spell'

/** A compendium search result. */
export interface CompendiumItem {
  key: string
  name: string
  cr?: string
  type?: string
  size?: string
  level?: number
  school?: string
}

/** A whole compendium entry: a monster's NPC sheet, or a spell for a sheet. */
export interface CompendiumEntry extends CompendiumItem {
  sheet?: Sheet
  spell?: SheetSpell
  classes?: string[]
}

export interface CharacterAttribute {
  name: string
  current: string
  max: string
}

/** Journal character. Players receive only the ones they play, without `gm_notes`. */
export interface Character {
  id: string
  name: string
  avatar: string | null
  bio: string
  gm_notes?: string
  attributes: CharacterAttribute[]
  abilities: Ability[]
  sheet: Sheet | null
  derived: SheetDerived | null
  folder_id: string | null
  /** Player who plays it: sees it, edits it, speaks with its name. */
  player_id: string | null
  archived: boolean
}

export interface JournalFolder {
  id: string
  name: string
  parent_id: string | null
}

export type CharacterPatch = Partial<Omit<Character, 'id' | 'derived'>>

/** One entry of the event log, as the GM history shows it. */
export interface HistoryEvent {
  seq: number
  player_id: string | null
  kind: string
  summary: string
  /** Map-object change: the GM can revert it. */
  revertible: boolean
  reverted: boolean
  created_at: string
}

/** Sent on reconnect when the page is still loaded: the server sends back only what changed. */
export interface Resume {
  seq: number
  page_id: string
  chat_id?: number
}

export type ClientMessage = { rid?: string } & (
  | { type: 'hello'; player: Omit<Player, 'online' | 'settings'>; resume?: Resume }
  | { type: 'player.update'; name?: string; color?: string; settings?: PlayerSettings }
  | { type: 'game.settings'; measurement?: Measurement; npc_hp?: NpcHp }
  | { type: 'game.options'; patch: Record<string, OptionValue> }
  | { type: 'page.view'; page_id: string }
  | { type: 'page.create'; page?: Partial<Page> }
  | { type: 'page.update'; id: string; patch: Partial<Page> }
  | { type: 'page.delete'; id: string }
  | { type: 'page.duplicate'; id: string }
  | { type: 'game.player_page'; page_id: string; player_id?: string | null }
  | { type: 'obj.create'; objects: Omit<MapObject, 'owner_id' | 'z'>[] }
  /** via: waypoints of a move per object id, flat [x, y, ...]; combat movement follows them. */
  | { type: 'obj.update'; patches: ObjectPatch[]; via?: Record<string, number[]> }
  | { type: 'obj.preview'; items: PreviewItem[] }
  | { type: 'measure'; page_id: string; segment: Segment | null; object_id?: string }
  | { type: 'obj.delete'; ids: string[] }
  | { type: 'obj.order'; ids: string[]; to: 'front' | 'back' }
  | {
      type: 'chat.send'
      text: string
      as_character?: string | null
      selected_id?: string | null
      target_id?: string | null
      answers?: string[]
    }
  | { type: 'ping'; page_id: string; x: number; y: number; pull?: boolean }
  | { type: 'turn.set'; order: TurnEntry[]; round?: number }
  | { type: 'turn.add'; entry: TurnEntry }
  | { type: 'turn.update'; id: string; value?: string; name?: string }
  | { type: 'turn.remove'; id: string }
  | { type: 'turn.next' }
  | { type: 'turn.sort'; descending?: boolean }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'history.get' }
  | { type: 'event.revert'; seq: number }
  | { type: 'char.create'; id: string; character: CharacterPatch }
  | { type: 'char.update'; id: string; patch: CharacterPatch }
  | { type: 'char.delete'; id: string }
  | { type: 'folder.create'; id: string; name: string; parent_id?: string | null }
  | { type: 'folder.update'; id: string; name?: string; parent_id?: string | null }
  | { type: 'folder.delete'; id: string }
  | { type: 'macro.create'; id: string; name: string; action: string; in_bar: boolean }
  | { type: 'macro.update'; id: string; name?: string; action?: string; in_bar?: boolean }
  | { type: 'macro.delete'; id: string }
  | { type: 'table.create'; id: string; name: string }
  | { type: 'table.update'; id: string; name?: string; show_players?: boolean; items?: TableItem[] }
  | { type: 'table.delete'; id: string }
  /** side: index, or null for a random one */
  | { type: 'token.side'; ids: string[]; side: number | null }
  | { type: 'deck.create'; id: string; name: string }
  | {
      type: 'deck.update'
      id: string
      name?: string
      back?: string | null
      cards?: Card[]
      settings?: Partial<DeckSettings>
    }
  | { type: 'deck.delete'; id: string }
  | {
      type: 'deck.action'
      deck_id: string
      action: DeckActionKind
      count?: number
      player_id?: string | null
      card_ids?: string[]
      object_ids?: string[]
      page_id?: string | null
      x?: number
      y?: number
      face_down?: boolean
    }
  | {
      type: 'asset.create'
      id: string
      name: string
      url: string
      thumb: string | null
      width: number
      height: number
      folder?: string
      tags?: string[]
    }
  | { type: 'asset.update'; id: string; name?: string; folder?: string; tags?: string[] }
  | { type: 'asset.delete'; ids: string[] }
  | {
      type: 'sheet.roll'
      character_id: string
      roll: SheetRollKind
      key?: string | null
      mode?: RollMode
      crit?: boolean
      token_id?: string | null
      target_id?: string | null
      gm_only?: boolean
    }
  | { type: 'sheet.rest'; character_id: string; kind: 'short' | 'long' | 'hit_die' }
  | { type: 'combat.initiative'; token_ids: string[]; group?: boolean }
  | { type: 'turn.use'; id: string; what: TurnAction; used: boolean }
  | {
      type: 'effect.apply'
      token_ids: string[]
      preset?: string | null
      effect?: Partial<Effect> & { name: string }
      source_id?: string | null
      concentrate?: boolean
      dc?: number | null
    }
  | { type: 'effect.remove'; token_id: string; effect_id: string }
  | { type: 'effect.end_concentration'; token_id: string }
  | {
      type: 'sheet.cast'
      character_id: string
      spell_id: string
      slot?: number | null
      ritual?: boolean
      token_id?: string | null
      target_ids?: string[]
    }
  | { type: 'fog.set'; page_id: string; enabled: boolean }
  | ({ type: 'fog.op'; page_id: string } & FogArea)
  | { type: 'fog.reset'; page_id: string; mode: 'reveal' | 'hide' }
  | { type: 'compendium.search'; kind: CompendiumKind; query?: string; cr?: string | null; level?: number | null; limit?: number }
  | { type: 'compendium.get'; kind: CompendiumKind; key: string }
  | { type: 'compendium.add_monster'; key: string }
  | { type: 'compendium.place'; key: string; page_id: string; x: number; y: number; layer?: 'objects' | 'gm' }
  | { type: 'compendium.add_spell'; key: string; character_id: string }
  | {
      type: 'spell.saves'
      character_id: string
      spell_id: string
      slot: number
      token_id?: string | null
      target_ids: string[]
    }
  | {
      type: 'combat.apply'
      token_ids: string[]
      kind: HpChange
      amount: number
      damage_type?: string | null
      half?: boolean
      critical?: boolean
    }
)

export type SheetRollKind = 'check' | 'save' | 'skill' | 'initiative' | 'attack' | 'damage' | 'death_save'
export type HpChange = 'damage' | 'healing' | 'temp'

/** Every server message carries `seq`: the last committed event when it was sent. */
export type ServerMessage = { seq?: number } & (
  | {
      type: 'welcome'
      you: Player
      game: GameState
      players: Player[]
      pages: Page[]
      journal: { characters: Character[]; folders: JournalFolder[] }
      macros: Macro[]
      tables: RollableTable[]
      decks: Deck[]
      assets: Asset[]
      chat: ChatMessage[]
      /** append: `chat` holds only the messages missed while disconnected. */
      chat_mode: 'replace' | 'append'
      resumed: boolean
      options: GameOption[]
    }
  | { type: 'page.snapshot'; page: Page; objects: MapObject[] }
  /** Answer to a resume: only the objects changed since, and the ids gone. */
  | { type: 'page.resume'; page: Page; objects: MapObject[]; removed: string[] }
  | { type: 'page.updated'; page: Page }
  | { type: 'page.created'; rid?: string; id: string }
  | { type: 'pages'; pages: Page[] }
  | { type: 'game'; game: GameState }
  | { type: 'players'; players: Player[] }
  | { type: 'obj.upsert'; objects: MapObject[] }
  | { type: 'obj.removed'; ids: string[] }
  | { type: 'obj.preview'; items: PreviewItem[] }
  | { type: 'measure'; page_id: string; player_id: string; color?: string; segment: Segment | null }
  | { type: 'chat'; message: ChatMessage }
  | {
      type: 'ping'
      page_id: string
      x: number
      y: number
      color: string
      player_id: string
      pull: boolean
    }
  | { type: 'error'; rid?: string; detail: string }
  | { type: 'notice'; detail: string }
  /** What my Ctrl+Z / Ctrl+Y would do; null = nothing. */
  | { type: 'undo.state'; undo: string | null; redo: string | null }
  | { type: 'history'; events: HistoryEvent[] }
  | { type: 'history.add'; event: HistoryEvent }
  | { type: 'history.update'; event_seq: number; reverted: boolean }
  | { type: 'journal.upsert'; characters?: Character[]; folders?: JournalFolder[] }
  | { type: 'journal.removed'; character_ids?: string[]; folder_ids?: string[] }
  | { type: 'macro.upsert'; macros: Macro[] }
  | { type: 'macro.removed'; ids: string[] }
  | { type: 'table.upsert'; tables: RollableTable[] }
  | { type: 'table.removed'; ids: string[] }
  | { type: 'deck.upsert'; decks: Deck[] }
  | { type: 'deck.removed'; ids: string[] }
  | { type: 'asset.upsert'; assets: Asset[] }
  | { type: 'asset.removed'; ids: string[] }
  | { type: 'compendium.results'; rid?: string; kind: CompendiumKind; items: CompendiumItem[] }
  | { type: 'compendium.entry'; kind: CompendiumKind; entry: CompendiumEntry }
  | { type: 'compendium.added'; rid?: string; character_id: string }
  /** The message needs a target token, or answers to roll queries, before it can go out. */
  | { type: 'chat.needs'; rid?: string; target: boolean; queries: Query[] }
)
