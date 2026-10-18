import type {
  ChatMessage,
  ClientMessage,
  GameState,
  Layer,
  MapObject,
  ObjectPatch,
  Page,
  Player,
  PreviewItem,
  ServerMessage,
  TurnEntry,
} from '../net/protocol'
import { GameSocket, type ConnectionStatus } from '../net/socket'
import type { Identity } from './identity'

export type Tool =
  | 'select'
  | 'pan'
  | 'ruler'
  | 'draw-free'
  | 'draw-line'
  | 'draw-rect'
  | 'draw-ellipse'
  | 'draw-polygon'
  | 'text'
  | 'template-circle'
  | 'template-cone'
  | 'template-line'
  | 'template-square'

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
  ping: (ping: Ping) => void
  selection: (ids: string[]) => void
  focus: (x: number, y: number) => void
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
  drawStyle = $state<DrawStyle>({ stroke: '#e74c3c', fill: null, strokeWidth: 4, fontSize: 28 })
  /** Bumped on every object change so UI deriveds can re-read `objects`. */
  objectsVersion = $state(0)

  /** Objects of the viewed page. Plain Map: the engine reads it every frame. */
  readonly objects = new Map<string, MapObject>()

  private socket: GameSocket | null = null
  private identity: Identity | null = null
  private toastSeq = 0
  private readonly listeners: Listeners = {
    page: new Set(),
    pageUpdated: new Set(),
    upsert: new Set(),
    removed: new Set(),
    preview: new Set(),
    ping: new Set(),
    selection: new Set(),
    focus: new Set(),
  }

  get isGm(): boolean {
    return this.me?.is_gm ?? false
  }

  connect(identity: Identity): void {
    this.identity = identity
    this.socket?.close()
    this.socket = new GameSocket({
      onOpen: () => this.send({ type: 'hello', player: identity }),
      onStatus: (s) => (this.status = s),
      onMessage: (m) => this.receive(m),
    })
  }

  disconnect(): void {
    this.socket?.close()
    this.socket = null
    this.me = null
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
    switch (msg.type) {
      case 'welcome':
        this.me = msg.you
        this.game = msg.game
        this.players = msg.players
        this.pages = sortPages(msg.pages)
        this.chat = msg.chat
        if (!msg.you.is_gm) this.layer = 'objects'
        break
      case 'page.snapshot':
        this.page = msg.page
        this.objects.clear()
        for (const o of msg.objects) this.objects.set(o.id, o)
        this.setSelection([])
        this.objectsVersion++
        this.emit('page', msg.page, msg.objects)
        break
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
        break
      case 'players':
        this.players = msg.players
        if (this.me) this.me = msg.players.find((p) => p.id === this.me!.id) ?? this.me
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
      case 'chat':
        this.chat.push(msg.message)
        if (this.chat.length > 500) this.chat.splice(0, this.chat.length - 500)
        break
      case 'ping':
        if (msg.page_id === this.page?.id) this.emit('ping', msg)
        break
      case 'error':
        this.toast(msg.detail)
        break
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

  updateObjects(patches: ObjectPatch[]): void {
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
    this.send({ type: 'obj.update', patches })
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
    this.send({ type: 'obj.preview', items })
  }

  sendChat(text: string): void {
    this.send({ type: 'chat.send', text })
  }

  ping(x: number, y: number, pull: boolean): void {
    if (this.page) this.send({ type: 'ping', page_id: this.page.id, x, y, pull })
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

function sortPages(pages: Page[]): Page[] {
  return [...pages].sort((a, b) => a.sort_order - b.sort_order)
}

export const store = new GameStore()
