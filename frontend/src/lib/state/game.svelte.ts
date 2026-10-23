import type {
  Asset,
  Card,
  Character,
  Deck,
  DeckActionKind,
  RollableTable,
  TableItem,
  CompendiumEntry,
  CompendiumItem,
  CompendiumKind,
  CharacterPatch,
  ChatMessage,
  ClientMessage,
  GameOption,
  GameState,
  OptionValue,
  HistoryEvent,
  HpChange,
  JournalFolder,
  Macro,
  Layer,
  MapObject,
  Measurement,
  ObjectPatch,
  Page,
  Player,
  PlayerSettings,
  PreviewItem,
  Query,
  RollMode,
  Segment,
  ServerMessage,
  TurnAction,
  SheetRollKind,
  TurnEntry,
  ActAction,
} from '../net/protocol'
import { GameSocket, type ConnectionStatus } from '../net/socket'
import { DEFAULT_DRAW_COLOR } from '../theme'
import { saveIdentity, type Identity } from './identity'

/** A chat message waiting for a target token or for answers to its queries. */
export interface PendingChat {
  text: string
  selectedId: string | null
  targetId: string | null
  queries: Query[]
}

export type Tool =
  | 'select'
  | 'ruler'
  | 'draw-free'
  | 'draw-line'
  | 'draw-rect'
  | 'draw-ellipse'
  | 'draw-polygon'
  | 'text'
  | 'template-circle'
  | 'fog-reveal'
  | 'fog-hide'
  | 'fog-reveal-poly'
  | 'fog-hide-poly'
  | 'eraser'
  | 'pin'

/** Target mode: an action waits for its targets to be clicked on the map. */
export interface Targeting {
  actorId: string
  action: ActAction
  label: string
  /** Several targets: Shift-click to pick, Enter to confirm. Single: a click resolves. */
  multi: boolean
  mode: RollMode
  targets: string[]
  cover: Record<string, 0 | 2 | 5>
  /** Feet. Melee: reach; ranged: normal / long range. */
  range: { reach: number | null; normal: number | null; long: number | null }
  /** Spells are cast through the sheet path (character, spell, slot level). */
  spell?: { characterId: string; spellId: string; slot: number | null }
  /** Enter with nothing picked still acts (spells with no target, self). */
  allowNone?: boolean
}

/** Another player's live measurement; segment null = they stopped measuring. */
export interface RemoteMeasure {
  player_id: string
  color?: string
  segment: Segment | null
}

export interface Ping {
  x: number
  y: number
  color: string
  pull: boolean
}

/** Events the canvas engine listens to (kept outside Svelte reactivity for speed). */
export interface EngineEvents {
  page: (page: Page, objects: MapObject[]) => void
  pageUpdated: (page: Page) => void
  upsert: (objects: MapObject[]) => void
  removed: (ids: string[]) => void
  preview: (items: PreviewItem[]) => void
  /** The turn order changed: whose turn it is may have changed. */
  turn: () => void
  ping: (ping: Ping) => void
  measure: (m: RemoteMeasure) => void
  selection: (ids: string[]) => void
  focus: (x: number, y: number) => void
  /** Target mode started, changed or ended. */
  targeting: () => void
}

type Listeners = { [K in keyof EngineEvents]: Set<EngineEvents[K]> }

export interface Toast {
  id: number
  text: string
}

export interface DrawStyle {
  stroke: string
  fill: string | null
  strokeWidth: number
  fontSize: number
}

export class GameStore {
  status = $state<ConnectionStatus>('connecting')
  me = $state<Player | null>(null)
  game = $state<GameState | null>(null)
  players = $state<Player[]>([])
  pages = $state<Page[]>([])
  page = $state<Page | null>(null)
  chat = $state<ChatMessage[]>([])
  selection = $state<string[]>([])
  tool = $state<Tool>('select')
  layer = $state<Layer>('objects')
  toasts = $state<Toast[]>([])
  drawStyle = $state<DrawStyle>({ stroke: DEFAULT_DRAW_COLOR, fill: null, strokeWidth: 4, fontSize: 28 })
  /** Bumped on every object change so UI deriveds can re-read `objects`. */
  objectsVersion = $state(0)
  /** What Ctrl+Z / Ctrl+Y would do (server summary), null = nothing. */
  undoLabel = $state<string | null>(null)
  redoLabel = $state<string | null>(null)
  /** GM history, oldest first; null until requested. */
  history = $state<HistoryEvent[] | null>(null)
  /** Journal: all characters for the GM, only the ones I play for a player. */
  characters = $state<Character[]>([])
  folders = $state<JournalFolder[]>([])
  /** Character sheet open in the journal window, if any. */
  openCharacterId = $state<string | null>(null)
  /** GM: journal character whose name the chat uses; null = my own name. */
  speakingAs = $state<string | null>(null)
  macros = $state<Macro[]>([])
  tables = $state<RollableTable[]>([])
  decks = $state<Deck[]>([])
  /** My art library. */
  assets = $state<Asset[]>([])
  /** Message waiting for my click on a target token (`@{target|…}`). */
  targetPick = $state<PendingChat | null>(null)
  /** Message waiting for my answers to its roll queries. */
  queryPrompt = $state<PendingChat | null>(null)
  /** 5e sheet rolls: mode, whisper to the GM, target token for attacks. */
  sheetMode = $state<RollMode>('normal')
  sheetGmOnly = $state(false)
  sheetTarget = $state<string | null>(null)
  /** Waiting for a click on the map to choose `sheetTarget`. */
  pickingSheetTarget = $state(false)
  /** Tokens the effect window is open for. */
  effectTargets = $state<string[] | null>(null)
  /** Compendium: last results and the entry being read. */
  compendiumResults = $state<CompendiumItem[]>([])
  compendiumEntry = $state<CompendiumEntry | null>(null)

  /** Action waiting for its targets on the map. */
  targeting = $state<Targeting | null>(null)
  /** Last targets of each actor token: Enter in target mode reuses them. */
  private lastTargets = new Map<string, string[]>()

  /** Catalog of game options (from the server); values are in `game.settings`. */
  options = $state<GameOption[]>([])

  /** Objects of the viewed page. Plain Map: the engine reads it every frame. */
  readonly objects = new Map<string, MapObject>()

  private socket: GameSocket | null = null
  private identity: Identity | null = null
  /** Last event seq seen, and whether the loaded page is complete: then a reconnect resumes. */
  private lastSeq = 0
  private pageSynced = false
  private toastSeq = 0
  private chatSeq = 0
  /** Sent chat messages by request id, until the server takes them or asks for more. */
  private pendingChats = new Map<string, PendingChat>()
  private readonly listeners: Listeners = {
    page: new Set(),
    pageUpdated: new Set(),
    upsert: new Set(),
    removed: new Set(),
    preview: new Set(),
    turn: new Set(),
    ping: new Set(),
    measure: new Set(),
    selection: new Set(),
    focus: new Set(),
    targeting: new Set(),
  }

  get isGm(): boolean {
    return this.me?.is_gm ?? false
  }

  /** Value of a game option, with its default. */
  option<T extends OptionValue = OptionValue>(key: string): T {
    const value = this.game?.settings[key]
    const def = this.options.find((o) => o.key === key)?.default
    return (value ?? def) as T
  }

  setOption(key: string, value: OptionValue): void {
    this.send({ type: 'game.options', patch: { [key]: value } })
  }

  /** My personal settings, with defaults. */
  get settings(): Required<PlayerSettings> {
    return { wheel: 'zoom', chat_timestamps: true, ...this.me?.settings }
  }

  /** The character I play: players speak in chat with its name. */
  get myCharacter(): Character | null {
    const me = this.me
    if (!me || me.is_gm) return null
    const mine = this.characters.filter((c) => c.player_id === me.id && !c.archived)
    return mine.sort((a, b) => a.name.localeCompare(b.name))[0] ?? null
  }

  character(id: string | null | undefined): Character | undefined {
    return id ? this.characters.find((c) => c.id === id) : undefined
  }

  /** Mirror of PLAYER_CHARACTER_FIELDS on the server: the GM edits everything. */
  canEditCharacter(c: Character): boolean {
    return this.isGm || (!!this.me && c.player_id === this.me.id)
  }

  get measurement(): Measurement {
    return this.game?.settings.measurement ?? 'metric'
  }

  updateSettings(patch: PlayerSettings): void {
    if (!this.me) return
    this.me = { ...this.me, settings: { ...this.me.settings, ...patch } }
    this.send({ type: 'player.update', settings: patch })
  }

  updateProfile(patch: { name?: string; color?: string }): void {
    if (!this.identity) return
    // Keep the tab identity in sync, or a reconnect would send the old name back.
    this.identity = { ...this.identity, ...patch }
    saveIdentity(this.identity)
    this.send({ type: 'player.update', ...patch })
  }

  connect(identity: Identity): void {
    this.identity = identity
    this.socket?.close()
    this.socket = new GameSocket({
      onOpen: () => this.identity && this.send({ type: 'hello', player: this.identity, resume: this.resumeInfo() }),
      onStatus: (s) => (this.status = s),
      onMessage: (m) => this.receive(m),
    })
  }

  disconnect(): void {
    this.socket?.close()
    this.socket = null
    this.me = null
    this.pageSynced = false
  }

  /** On reconnect, ask only for what changed since the last message, if the page is complete. */
  private resumeInfo() {
    if (!this.pageSynced || !this.page) return undefined
    return { seq: this.lastSeq, page_id: this.page.id, chat_id: this.chat.at(-1)?.id }
  }

  send(msg: ClientMessage): void {
    this.socket?.send(msg)
  }

  on<K extends keyof EngineEvents>(event: K, fn: EngineEvents[K]): () => void {
    this.listeners[event].add(fn)
    return () => this.listeners[event].delete(fn)
  }

  private emit<K extends keyof EngineEvents>(event: K, ...args: Parameters<EngineEvents[K]>): void {
    for (const fn of this.listeners[event]) (fn as (...a: unknown[]) => void)(...args)
  }

  toast(text: string): void {
    const id = ++this.toastSeq
    this.toasts.push({ id, text })
    setTimeout(() => (this.toasts = this.toasts.filter((t) => t.id !== id)), 4000)
  }

  // --- Incoming ---------------------------------------------------------------

  private receive(msg: ServerMessage): void {
    if (msg.seq !== undefined) this.lastSeq = msg.seq
    switch (msg.type) {
      case 'welcome':
        // The server may hand back an existing player with the same name.
        if (this.identity && this.identity.id !== msg.you.id) {
          this.identity = { ...this.identity, id: msg.you.id }
          saveIdentity(this.identity)
        }
        this.me = msg.you
        this.options = msg.options
        this.game = msg.game
        this.emit('turn')
        this.players = msg.players
        this.pages = sortPages(msg.pages)
        this.macros = msg.macros
        this.tables = msg.tables
        this.decks = msg.decks
        this.assets = msg.assets
        this.characters = msg.journal.characters
        this.folders = msg.journal.folders
        if (this.speakingAs && !this.character(this.speakingAs)) this.speakingAs = null
        if (msg.chat_mode === 'append') {
          // Missed messages, plus older cards that changed meanwhile: upsert by id.
          for (const m of msg.chat) {
            const i = this.chat.findIndex((c) => c.id === m.id)
            if (i >= 0) this.chat[i] = m
            else this.chat.push(m)
          }
        }
        else this.chat = msg.chat
        if (!msg.you.is_gm) this.layer = 'objects'
        // Until the page arrives the loaded one is not up to date.
        this.pageSynced = false
        if (this.history) this.send({ type: 'history.get' })
        break
      case 'page.snapshot':
        this.page = msg.page
        this.objects.clear()
        for (const o of msg.objects) this.objects.set(o.id, o)
        this.setSelection([])
        this.objectsVersion++
        this.pageSynced = true
        this.emit('page', msg.page, msg.objects)
        break
      case 'page.resume': {
        // Same page as before the disconnection: apply only the differences.
        this.page = msg.page
        for (const id of msg.removed) this.objects.delete(id)
        for (const o of msg.objects) this.objects.set(o.id, o)
        this.setSelection(this.selection.filter((id) => this.objects.has(id)))
        this.objectsVersion++
        this.pageSynced = true
        this.emit('pageUpdated', msg.page)
        this.emit('removed', msg.removed)
        this.emit('upsert', msg.objects)
        break
      }
      case 'page.updated':
        if (this.page?.id === msg.page.id) {
          this.page = msg.page
          this.emit('pageUpdated', msg.page)
        }
        break
      case 'pages':
        this.pages = sortPages(msg.pages)
        break
      case 'page.created':
        break
      case 'game':
        this.game = msg.game
        this.emit('turn')
        break
      case 'players':
        this.players = msg.players
        if (this.me) {
          const me = msg.players.find((p) => p.id === this.me!.id)
          // The public list has no settings: keep mine.
          if (me) this.me = { ...me, settings: this.me.settings }
        }
        break
      case 'obj.upsert': {
        const mine = msg.objects.filter((o) => o.page_id === this.page?.id)
        for (const o of mine) this.objects.set(o.id, o)
        this.objectsVersion++
        this.emit('upsert', mine)
        break
      }
      case 'obj.removed':
        for (const id of msg.ids) this.objects.delete(id)
        this.setSelection(this.selection.filter((id) => !msg.ids.includes(id)))
        this.objectsVersion++
        this.emit('removed', msg.ids)
        break
      case 'obj.preview':
        this.emit('preview', msg.items)
        break
      case 'chat.update': {
        const i = this.chat.findIndex((m) => m.id === msg.message.id)
        if (i >= 0) this.chat[i] = msg.message
        break
      }
      case 'chat':
        this.chat.push(msg.message)
        if (this.chat.length > 500) this.chat.splice(0, this.chat.length - 500)
        break
      case 'measure':
        if (msg.page_id === this.page?.id) this.emit('measure', msg)
        break
      case 'ping':
        if (msg.page_id === this.page?.id) this.emit('ping', msg)
        break
      case 'error':
      case 'notice':
        this.toast(msg.detail)
        break
      case 'undo.state':
        this.undoLabel = msg.undo
        this.redoLabel = msg.redo
        break
      case 'history':
        this.history = msg.events
        break
      case 'history.add':
        if (this.history) {
          this.history.push(msg.event)
          if (this.history.length > 200) this.history.splice(0, this.history.length - 200)
        }
        break
      case 'journal.upsert':
        for (const c of msg.characters ?? []) upsertById(this.characters, c)
        for (const f of msg.folders ?? []) upsertById(this.folders, f)
        break
      case 'compendium.results':
        this.compendiumResults = msg.items
        break
      case 'compendium.entry':
        this.compendiumEntry = msg.entry
        break
      case 'compendium.added':
        this.openCharacterId = msg.character_id
        break
      case 'macro.upsert':
        for (const m of msg.macros) upsertById(this.macros, m)
        break
      case 'table.upsert':
        for (const t of msg.tables) upsertById(this.tables, t)
        break
      case 'table.removed':
        this.tables = this.tables.filter((t) => !msg.ids.includes(t.id))
        break
      case 'deck.upsert':
        for (const d of msg.decks) upsertById(this.decks, d)
        break
      case 'deck.removed':
        this.decks = this.decks.filter((d) => !msg.ids.includes(d.id))
        break
      case 'asset.upsert':
        for (const a of msg.assets) upsertById(this.assets, a)
        break
      case 'asset.removed':
        this.assets = this.assets.filter((a) => !msg.ids.includes(a.id))
        break
      case 'macro.removed':
        this.macros = this.macros.filter((m) => !msg.ids.includes(m.id))
        break
      case 'chat.needs': {
        const pending = msg.rid ? this.pendingChats.get(msg.rid) : undefined
        if (msg.rid) this.pendingChats.delete(msg.rid)
        if (!pending) break
        if (msg.target) {
          this.targetPick = pending
          this.toast('Click the target token (Esc to cancel)')
        } else {
          this.queryPrompt = { ...pending, queries: msg.queries }
        }
        break
      }
      case 'journal.removed': {
        const chars = new Set(msg.character_ids ?? [])
        const folders = new Set(msg.folder_ids ?? [])
        if (chars.size) this.characters = this.characters.filter((c) => !chars.has(c.id))
        if (folders.size) this.folders = this.folders.filter((f) => !folders.has(f.id))
        if (this.openCharacterId && chars.has(this.openCharacterId)) this.openCharacterId = null
        if (this.speakingAs && chars.has(this.speakingAs)) this.speakingAs = null
        break
      }
      case 'history.update': {
        const e = this.history?.find((h) => h.seq === msg.event_seq)
        if (e) e.reverted = msg.reverted
        break
      }
    }
  }

  // --- Selection --------------------------------------------------------------

  setSelection(ids: string[]): void {
    const same = ids.length === this.selection.length && ids.every((id, i) => this.selection[i] === id)
    if (same) return
    this.selection = ids
    this.emit('selection', ids)
  }

  focus(x: number, y: number): void {
    this.emit('focus', x, y)
  }

  // --- Permissions (mirror of backend/app/game/permissions.py) ----------------

  controls(obj: MapObject): boolean {
    const me = this.me
    if (!me) return false
    if (me.is_gm) return true
    if (obj.layer !== 'objects') return false
    const by: string[] = obj.props.controlled_by ?? []
    if (by.includes('all') || by.includes(me.id)) return true
    return ['path', 'text', 'template'].includes(obj.kind) && obj.owner_id === me.id
  }

  canDelete(obj: MapObject): boolean {
    const me = this.me
    if (!me) return false
    return me.is_gm || (['path', 'text', 'template'].includes(obj.kind) && obj.owner_id === me.id)
  }

  // --- Outgoing (optimistic) --------------------------------------------------

  createObjects(objects: Omit<MapObject, 'owner_id' | 'z'>[]): void {
    this.send({ type: 'obj.create', objects })
  }

  updateObjects(patches: ObjectPatch[], via?: Record<string, number[]>): void {
    if (!patches.length) return
    const changed: MapObject[] = []
    for (const patch of patches) {
      const obj = this.objects.get(patch.id)
      if (!obj) continue
      const { props, ...rest } = patch
      const next: MapObject = { ...obj, ...rest }
      if (props) {
        const merged: Record<string, unknown> = { ...obj.props, ...props }
        for (const k of Object.keys(merged)) if (merged[k] === null) delete merged[k]
        next.props = merged
      }
      this.objects.set(next.id, next)
      changed.push(next)
    }
    this.objectsVersion++
    this.emit('upsert', changed)
    this.send({ type: 'obj.update', patches, ...(via && { via }) })
  }

  updateProps(id: string, props: Record<string, unknown>): void {
    this.updateObjects([{ id, props }])
  }

  deleteObjects(ids: string[]): void {
    const allowed = ids.filter((id) => {
      const o = this.objects.get(id)
      return o && this.canDelete(o)
    })
    if (allowed.length) this.send({ type: 'obj.delete', ids: allowed })
  }

  preview(items: PreviewItem[]): void {
    // Dragging only locked objects moves nothing: nothing to send.
    if (items.length) this.send({ type: 'obj.preview', items })
  }

  /** Show my ruler / drag distance to the other viewers; null hides it. */
  shareMeasure(segment: Segment | null, objectId?: string): void {
    if (this.page) this.send({ type: 'measure', page_id: this.page.id, segment, object_id: objectId })
  }

  /** Middle of the map view in page pixels: set by the map once it is mounted. */
  viewCenter: () => { x: number; y: number } = () => ({ x: 0, y: 0 })

  // --- GM tools -------------------------------------------------------------

  createTable(name: string): void {
    this.send({ type: 'table.create', id: crypto.randomUUID(), name })
  }

  updateTable(id: string, patch: { name?: string; show_players?: boolean; items?: TableItem[] }): void {
    this.send({ type: 'table.update', id, ...patch })
  }

  deleteTable(id: string): void {
    this.send({ type: 'table.delete', id })
  }

  /** Show side `side` of multi-sided tokens; null = a random side, picked by the server. */
  tokenSide(ids: string[], side: number | null): void {
    this.send({ type: 'token.side', ids, side })
  }

  createDeck(name: string): void {
    this.send({ type: 'deck.create', id: crypto.randomUUID(), name })
  }

  updateDeck(
    id: string,
    patch: { name?: string; back?: string | null; cards?: Card[]; settings?: Partial<Deck['settings']> },
  ): void {
    this.send({ type: 'deck.update', id, ...patch })
  }

  deleteDeck(id: string): void {
    this.send({ type: 'deck.delete', id })
  }

  deckAction(
    deckId: string,
    action: DeckActionKind,
    extra: {
      count?: number
      player_id?: string | null
      card_ids?: string[]
      object_ids?: string[]
      x?: number
      y?: number
      face_down?: boolean
    } = {},
  ): void {
    const onPage = action === 'play' ? { page_id: this.page?.id ?? null } : {}
    this.send({ type: 'deck.action', deck_id: deckId, action, ...onPage, ...extra })
  }

  addAsset(asset: Omit<Asset, 'id' | 'folder' | 'tags'> & { folder?: string; tags?: string[] }): void {
    this.send({ type: 'asset.create', id: crypto.randomUUID(), ...asset })
  }

  updateAsset(id: string, patch: { name?: string; folder?: string; tags?: string[] }): void {
    this.send({ type: 'asset.update', id, ...patch })
  }

  deleteAssets(ids: string[]): void {
    if (ids.length) this.send({ type: 'asset.delete', ids })
  }

  /** Send chat text; macros, @{selected|…} and queries are expanded by the server.
   *  `selectedId`: the token for @{selected|…}, by default the only selected one. */
  sendChat(text: string, selectedId: string | null = this.selection.length === 1 ? this.selection[0] : null): void {
    this.sendPending({ text, selectedId, targetId: null, queries: [] })
  }

  private sendPending(p: PendingChat, answers?: string[]): void {
    const rid = `chat-${++this.chatSeq}`
    this.pendingChats.set(rid, p)
    if (this.pendingChats.size > 50) this.pendingChats.delete(this.pendingChats.keys().next().value!)
    this.send({
      type: 'chat.send',
      rid,
      text: p.text,
      as_character: this.isGm ? this.speakingAs : null,
      selected_id: p.selectedId,
      target_id: p.targetId,
      answers,
    })
  }

  /** The token clicked as target: for the sheet, or to send the waiting message again. */
  pickTarget(id: string): void {
    if (this.pickingSheetTarget) {
      this.pickingSheetTarget = false
      this.sheetTarget = id
      return
    }
    const p = this.targetPick
    this.targetPick = null
    if (p) this.sendPending({ ...p, targetId: id })
  }

  cancelTarget(): void {
    this.targetPick = null
    this.pickingSheetTarget = false
  }

  /** The token acting for a character: the selected one if it represents it, else one on this page. */
  tokenFor(characterId: string): string | null {
    for (const id of this.selection) if (this.objects.get(id)?.props.represents === characterId) return id
    for (const o of this.objects.values()) if (o.kind === 'token' && o.props.represents === characterId) return o.id
    return null
  }

  /** Roll from a 5e sheet; the server computes the formula from the sheet and the conditions. */
  sheetRoll(
    characterId: string,
    roll: SheetRollKind,
    key: string | null = null,
    opts: { crit?: boolean; tokenId?: string | null; targetId?: string | null } = {},
  ): void {
    const targetId = opts.targetId !== undefined ? opts.targetId : this.sheetTarget
    const actor = opts.tokenId !== undefined ? opts.tokenId : this.tokenFor(characterId)
    if (roll === 'attack' && key && actor) {
      // With a token on the map an attack is a combat action: resolved and applied.
      const targets =
        targetId && this.objects.has(targetId)
          ? [targetId]
          : this.selection.filter((id) => id !== actor && this.objects.get(id)?.kind === 'token')
      this.act(actor, { kind: 'attack', id: key }, targets, {
        mode: this.sheetMode,
        hidden: this.sheetGmOnly && this.isGm,
      })
      return
    }
    this.send({
      type: 'sheet.roll',
      character_id: characterId,
      roll,
      key,
      mode: this.sheetMode,
      crit: opts.crit ?? false,
      token_id: opts.tokenId !== undefined ? opts.tokenId : this.tokenFor(characterId),
      target_id: targetId && this.objects.has(targetId) ? targetId : null,
      gm_only: this.sheetGmOnly,
    })
  }

  answerQueries(answers: string[] | null): void {
    const p = this.queryPrompt
    this.queryPrompt = null
    if (p && answers) this.sendPending(p, answers)
  }

  /** Run a chat button: `~Character|Ability`, `#Macro` or a game action `!name args…`. */
  runButton(target: string): void {
    if (target.startsWith('!')) {
      const [name, ...args] = target.slice(1).trim().split(/\s+/)
      const arg = (i: number) => (args[i] && args[i] !== '-' ? args[i] : null)
      if (name === 'damage') {
        this.sheetRoll(args[0], 'damage', args[1], { crit: args[2] === '1', tokenId: arg(3), targetId: arg(4) })
      } else if (name === 'saves') {
        // !saves <character> <spell> <slot> <caster token|-> <target,ids>
        this.send({
          type: 'spell.saves',
          character_id: args[0],
          spell_id: args[1],
          slot: Number(args[2]),
          token_id: arg(3),
          target_ids: (args[4] ?? '').split(',').filter(Boolean),
        })
      } else if (name === 'deathsave') {
        this.sheetRoll(args[0], 'death_save')
      } else if (name === 'apply') {
        // !apply damage <amount> <type|-> <token id|sel> [half]
        const ids = args[3] === 'sel' ? [...this.selection] : [args[3]]
        if (!ids.length) this.toast('Select the tokens first')
        else this.applyHp(ids, args[0] as HpChange, Number(args[1]), arg(2), args[4] === 'half')
      }
      return
    }
    this.sendChat(target.startsWith('~') ? `%{${target.slice(1)}}` : target)
  }

  /** Damage, healing or temporary hit points; the server applies resistances and death rules. */
  applyHp(tokenIds: string[], kind: HpChange, amount: number, damageType: string | null = null, half = false): void {
    if (!Number.isFinite(amount) || amount < 0) return
    this.send({ type: 'combat.apply', token_ids: tokenIds, kind, amount: Math.round(amount), damage_type: damageType, half })
  }

  /** One combat action: the server rolls, compares, applies and posts the card. */
  act(
    actorId: string,
    action: ActAction,
    targets: string[],
    opts: { mode?: RollMode; cover?: Record<string, 0 | 2 | 5>; hidden?: boolean; reaction?: boolean; point?: { x: number; y: number } } = {},
  ): void {
    this.send({
      type: 'combat.act',
      actor_id: actorId,
      action,
      targets: targets.map((id) => ({ id, cover: opts.cover?.[id] ?? 0 })),
      point: opts.point ?? null,
      mode: opts.mode ?? 'normal',
      hidden: opts.hidden ?? false,
      reaction: opts.reaction ?? false,
    })
  }

  // --- Target mode ---------------------------------------------------------------

  startTargeting(t: Omit<Targeting, 'mode' | 'targets' | 'cover'> & { mode?: RollMode }): void {
    this.targetPick = null
    this.pickingSheetTarget = false
    this.targeting = { ...t, mode: t.mode ?? 'normal', targets: [], cover: {} }
    this.emit('targeting')
  }

  /** Last targets of an actor that are still on the page. */
  lastTargetsOf(actorId: string): string[] {
    return (this.lastTargets.get(actorId) ?? []).filter((id) => this.objects.has(id))
  }

  clickTarget(id: string, additive: boolean): void {
    const t = this.targeting
    if (!t) return
    if (!t.multi && !additive) {
      t.targets = [id]
      this.confirmTargeting()
      return
    }
    t.targets = t.targets.includes(id) ? t.targets.filter((x) => x !== id) : [...t.targets, id]
    this.emit('targeting')
  }

  setTargetMode(mode: RollMode): void {
    if (!this.targeting) return
    this.targeting.mode = this.targeting.mode === mode ? 'normal' : mode
    this.emit('targeting')
  }

  cycleCover(id: string): void {
    const t = this.targeting
    if (!t) return
    const next = { 0: 2, 2: 5, 5: 0 } as const
    t.cover = { ...t.cover, [id]: next[t.cover[id] ?? 0] }
    this.emit('targeting')
  }

  confirmTargeting(): void {
    const t = this.targeting
    if (!t) return
    const targets = t.targets.length ? t.targets : this.lastTargetsOf(t.actorId)
    if (!targets.length && !t.allowNone) {
      this.toast('Click a target first')
      return
    }
    this.targeting = null
    this.emit('targeting')
    if (targets.length) this.lastTargets.set(t.actorId, targets)
    if (t.spell) this.cast(t.spell.characterId, t.spell.spellId, t.spell.slot, false, targets)
    else this.act(t.actorId, t.action, targets, { mode: t.mode, cover: t.cover })
  }

  cancelTargeting(): void {
    if (!this.targeting) return
    this.targeting = null
    this.emit('targeting')
  }

  undoCard(cardId: number): void {
    this.send({ type: 'combat.undo', card_id: cardId })
  }

  redoCard(cardId: number): void {
    this.send({ type: 'combat.redo', card_id: cardId })
  }

  addDamage(cardId: number, targetId: string, formula: string, damageType: string | null): void {
    this.send({ type: 'combat.add_damage', card_id: cardId, target_id: targetId, formula, damage_type: damageType })
  }

  /** GM: roll initiative for tokens (monsters of the same kind share a roll) and sort the tracker. */
  rollInitiative(tokenIds: string[], group = true): void {
    if (tokenIds.length) this.send({ type: 'combat.initiative', token_ids: tokenIds, group })
  }

  turnUse(entryId: string, what: TurnAction, used: boolean): void {
    this.send({ type: 'turn.use', id: entryId, what, used })
  }

  /** Cast a spell from a sheet; targets: the sheet target, else the selected tokens. */
  cast(characterId: string, spellId: string, slot: number | null, ritual = false, chosen?: string[]): void {
    const caster = this.tokenFor(characterId)
    const targets = chosen
      ? chosen
      : this.sheetTarget && this.objects.has(this.sheetTarget)
        ? [this.sheetTarget]
        : this.selection.filter((id) => id !== caster && this.objects.get(id)?.kind === 'token')
    this.send({ type: 'sheet.cast', character_id: characterId, spell_id: spellId, slot, ritual, token_id: caster, target_ids: targets })
  }

  applyEffect(tokenIds: string[], preset: string, sourceId: string | null, dc: number | null, concentrate = true): void {
    this.send({ type: 'effect.apply', token_ids: tokenIds, preset, source_id: sourceId, dc, concentrate })
  }

  removeEffect(tokenId: string, effectId: string): void {
    this.send({ type: 'effect.remove', token_id: tokenId, effect_id: effectId })
  }

  endConcentration(tokenId: string): void {
    this.send({ type: 'effect.end_concentration', token_id: tokenId })
  }

  searchCompendium(kind: CompendiumKind, query: string, cr: string | null, level: number | null): void {
    this.send({ type: 'compendium.search', kind, query, cr, level, limit: 80 })
  }

  openCompendium(kind: CompendiumKind, key: string): void {
    this.send({ type: 'compendium.get', kind, key })
  }

  /** GM: a compendium monster on the map (journal NPC + numbered token). */
  placeMonster(key: string, x: number, y: number): void {
    if (!this.page) return
    this.send({ type: 'compendium.place', key, page_id: this.page.id, x, y, layer: this.layer === 'gm' ? 'gm' : 'objects' })
  }

  /** GM: reveal or hide an area of the fog on the current page. */
  fogArea(mode: 'reveal' | 'hide', shape: 'rect' | 'poly', points: number[]): void {
    if (this.page) this.send({ type: 'fog.op', page_id: this.page.id, mode, shape, points: points.map((v) => Math.round(v)) })
  }

  setFog(enabled: boolean): void {
    if (this.page) this.send({ type: 'fog.set', page_id: this.page.id, enabled })
  }

  resetFog(mode: 'reveal' | 'hide'): void {
    if (this.page) this.send({ type: 'fog.reset', page_id: this.page.id, mode })
  }

  sheetRest(characterId: string, kind: 'short' | 'long' | 'hit_die'): void {
    this.send({ type: 'sheet.rest', character_id: characterId, kind })
  }

  // --- Macros -----------------------------------------------------------------

  createMacro(fields: Omit<Macro, 'id'>): string {
    const id = crypto.randomUUID()
    this.send({ type: 'macro.create', id, ...fields })
    return id
  }

  updateMacro(id: string, patch: Partial<Omit<Macro, 'id'>>): void {
    this.send({ type: 'macro.update', id, ...patch })
  }

  deleteMacro(id: string): void {
    this.send({ type: 'macro.delete', id })
  }

  // --- Journal ----------------------------------------------------------------

  createCharacter(fields: CharacterPatch = {}): string {
    const id = crypto.randomUUID()
    this.send({ type: 'char.create', id, character: { name: 'New character', ...fields } })
    return id
  }

  updateCharacter(id: string, patch: CharacterPatch): void {
    this.send({ type: 'char.update', id, patch })
  }

  deleteCharacter(id: string): void {
    this.send({ type: 'char.delete', id })
  }

  createFolder(name: string, parentId: string | null = null): void {
    this.send({ type: 'folder.create', id: crypto.randomUUID(), name, parent_id: parentId })
  }

  updateFolder(id: string, patch: { name?: string; parent_id?: string | null }): void {
    this.send({ type: 'folder.update', id, ...patch })
  }

  deleteFolder(id: string): void {
    this.send({ type: 'folder.delete', id })
  }

  ping(x: number, y: number, pull: boolean): void {
    if (this.page) this.send({ type: 'ping', page_id: this.page.id, x, y, pull })
  }

  undo(): void {
    this.send({ type: 'undo' })
  }

  redo(): void {
    this.send({ type: 'redo' })
  }

  /** GM: load the history; it then stays up to date. */
  requestHistory(): void {
    this.send({ type: 'history.get' })
  }

  /** GM: undo one change from the history, whoever made it. */
  revert(seq: number): void {
    this.send({ type: 'event.revert', seq })
  }

  viewPage(pageId: string): void {
    this.send({ type: 'page.view', page_id: pageId })
  }

  // --- Turn order -------------------------------------------------------------

  addToTurnOrder(objectIds: string[]): void {
    const existing = new Set(this.game?.turn_order.map((e) => e.object_id))
    for (const id of objectIds) {
      const obj = this.objects.get(id)
      if (!obj || obj.kind !== 'token' || existing.has(id)) continue
      const entry: TurnEntry = {
        id: crypto.randomUUID(),
        object_id: id,
        name: obj.props.name ?? '',
        value: '0',
      }
      this.send({ type: 'turn.add', entry })
    }
  }

  playerName(id: string): string {
    return this.players.find((p) => p.id === id)?.name ?? '?'
  }

  get identityValue(): Identity | null {
    return this.identity
  }
}

function upsertById<T extends { id: string }>(list: T[], item: T): void {
  const i = list.findIndex((x) => x.id === item.id)
  if (i >= 0) list[i] = item
  else list.push(item)
}

function sortPages(pages: Page[]): Page[] {
  return [...pages].sort((a, b) => a.sort_order - b.sort_order)
}

export const store = new GameStore()
