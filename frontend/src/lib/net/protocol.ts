// Mirrors backend/app/game/protocol.py and serialize.py. Keep in sync.

export type Layer = 'map' | 'objects' | 'gm'
export type ObjectKind = 'token' | 'image' | 'path' | 'text' | 'template'
export type GridType = 'square' | 'hex_v' | 'hex_h' | 'none'
export type DiagonalRule = '5e' | 'pf' | 'euclid' | 'manhattan'

export interface Player {
  id: string
  name: string
  color: string
  is_gm: boolean
  online: boolean
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
}

export interface Bar {
  value: number | null
  max: number | null
}

export interface Aura {
  radius: number // in page units (e.g. ft)
  color: string
  square?: boolean
}

export interface TokenProps {
  name?: string
  image?: string
  color?: string
  show_name?: boolean
  bar1?: Bar
  bar2?: Bar
  bar3?: Bar
  aura1?: Aura
  aura2?: Aura
  statuses?: string[]
  controlled_by?: string[]
  gm_notes?: string
  flip_h?: boolean
  flip_v?: boolean
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

export interface TurnEntry {
  id: string
  object_id: string | null
  name: string
  value: string
}

export interface GameState {
  name: string
  player_page_id: string | null
  player_page_overrides: Record<string, string>
  turn_order: TurnEntry[]
  settings: { round?: number; [k: string]: unknown }
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
  sides: number | 'F'
  total: number
  success_mode: boolean
  dice: Die[]
}

export interface Roll {
  expression: string
  total: number
  breakdown: string
  terms: RollTerm[]
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
  roll: { main: Roll | null; inline: Roll[] } | null
  recipients: string[] | null
  gm_only: boolean
}

export type ObjectPatch = { id: string } & Partial<Omit<MapObject, 'id' | 'owner_id' | 'kind'>>

export type PreviewItem = { id: string; x: number; y: number; rotation?: number }

export type ClientMessage = { rid?: string } & (
  | { type: 'hello'; player: Omit<Player, 'online'> }
  | { type: 'player.update'; name?: string; color?: string }
  | { type: 'page.view'; page_id: string }
  | { type: 'page.create'; page?: Partial<Page> }
  | { type: 'page.update'; id: string; patch: Partial<Page> }
  | { type: 'page.delete'; id: string }
  | { type: 'page.duplicate'; id: string }
  | { type: 'game.player_page'; page_id: string; player_id?: string | null }
  | { type: 'obj.create'; objects: Omit<MapObject, 'owner_id' | 'z'>[] }
  | { type: 'obj.update'; patches: ObjectPatch[] }
  | { type: 'obj.preview'; items: PreviewItem[] }
  | { type: 'obj.delete'; ids: string[] }
  | { type: 'obj.order'; ids: string[]; to: 'front' | 'back' }
  | { type: 'chat.send'; text: string }
  | { type: 'ping'; page_id: string; x: number; y: number; pull?: boolean }
  | { type: 'turn.set'; order: TurnEntry[]; round?: number }
  | { type: 'turn.add'; entry: TurnEntry }
  | { type: 'turn.update'; id: string; value?: string; name?: string }
  | { type: 'turn.remove'; id: string }
  | { type: 'turn.next' }
  | { type: 'turn.sort'; descending?: boolean }
)

export type ServerMessage =
  | {
      type: 'welcome'
      you: Player
      game: GameState
      players: Player[]
      pages: Page[]
      chat: ChatMessage[]
    }
  | { type: 'page.snapshot'; page: Page; objects: MapObject[] }
  | { type: 'page.updated'; page: Page }
  | { type: 'page.created'; rid?: string; id: string }
  | { type: 'pages'; pages: Page[] }
  | { type: 'game'; game: GameState }
  | { type: 'players'; players: Player[] }
  | { type: 'obj.upsert'; objects: MapObject[] }
  | { type: 'obj.removed'; ids: string[] }
  | { type: 'obj.preview'; items: PreviewItem[] }
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
