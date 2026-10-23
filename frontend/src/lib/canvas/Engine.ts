import { Application, Container, CullerPlugin, extensions, Graphics, RenderTexture, Sprite, Text } from 'pixi.js'
import type { Layer, MapObject, ObjectPatch, Page, PreviewItem, Segment } from '../net/protocol'
import type { GameStore, Ping, RemoteMeasure, Tool } from '../state/game.svelte'
import { canvasColors } from '../theme'
import { uid } from '../util/ids'
import { anchorCell, cellCenter, drawBackground, drawGrid, pagePixelSize, snapCenter, snapSize, type Point } from './grid'
import { formatDistance, measure } from './measure'
import { ObjectView, PIN_HEAD_Y, PIN_RADIUS, setMaxTextureSize, stackZ } from './views'

// Objects off screen are not drawn (each view is cullable).
extensions.add(CullerPlugin)

const PREVIEW_INTERVAL_MS = 33
const LONG_PRESS_MS = 550
const CLICK_SLOP_PX = 4
const MIN_ZOOM = 0.1
const MAX_ZOOM = 6
const HANDLE_PX = 9
const ROTATE_OFFSET_PX = 26
// Eraser reach around the pointer, in screen pixels.
const ERASER_PX = 10

export interface EngineCallbacks {
  /** Double click on an object. */
  onEdit: (id: string) => void
  /** Right click; id is null on empty space. Coordinates are client (screen) pixels. */
  onContext: (id: string | null, clientX: number, clientY: number) => void
  /** Text tool click: ask the UI for a string, then create the object. */
  onTextRequest: (world: Point, clientX: number, clientY: number) => void
  /** Zoom level changed (for the zoom indicator). */
  onZoom: (zoom: number) => void
  /** Click on a map pin: show its notes. Client (screen) pixels. */
  onPin: (id: string, clientX: number, clientY: number) => void
}

type Gesture =
  | { kind: 'none' }
  | { kind: 'pan'; startX: number; startY: number; camX: number; camY: number; moved: boolean; button: number }
  | {
      kind: 'drag'
      start: Point
      origins: Map<string, Point>
      moved: boolean
      lastSent: number
      // Alt held on the last move: free placement, no grid snapping.
      noSnap?: boolean
      // Positions of the lead object where Space was pressed (Roll20-style waypoints).
      waypoints: Point[]
    }
  | { kind: 'marquee'; start: Point; additive: boolean; timer: number; startClient: Point }
  | { kind: 'resize'; id: string; handle: ResizeHandle; start: MapObject }
  | { kind: 'rotate'; id: string; deg: number | null }
  | { kind: 'ruler'; start: Point; end?: Point; waypoints: Point[] }
  | { kind: 'draw'; tool: Tool; start: Point; points: number[] }
  | { kind: 'template'; start: Point; snapped: boolean }
  | { kind: 'fog'; mode: 'reveal' | 'hide'; start: Point }
  | { kind: 'erase'; ids: Set<string> }

// Bottom to top.
const LAYERS: Layer[] = ['map', 'objects', 'gm']

const LABEL_STYLE = {
  fill: canvasColors.label,
  fontSize: 15,
  fontWeight: '700',
  fontFamily: 'Inter, system-ui, sans-serif',
  stroke: { color: canvasColors.outline, width: 4 },
} as const

/** Another player's live ruler, drawn on its own so it never clashes with mine. */
interface RemoteRuler {
  segment: Segment
  color: string
  root: Container
  g: Graphics
  label: Text
}

/** What I am measuring right now, shared with the other viewers. */
interface Measured {
  segment: Segment
  objectId?: string
}

export class Engine {
  private readonly app = new Application()
  private readonly world = new Container()
  private readonly background = new Graphics({ label: 'background' })
  private readonly grid = new Graphics({ label: 'grid' })
  private readonly layers = new Map<Layer, Container>()
  private readonly overlay = new Graphics()
  private readonly overlayLabel = new Text({ text: '', style: LABEL_STYLE })
  private readonly remoteLayer = new Container()
  private readonly remoteRulers = new Map<string, RemoteRuler>()
  private readonly pings = new Container()
  private readonly fogSprite = new Sprite()
  private fogTexture: RenderTexture | null = null
  private readonly views = new Map<string, ObjectView>()
  private page: Page | null = null
  private gesture: Gesture = { kind: 'none' }
  private polygon: number[] | null = null
  private clipboard: MapObject[] = []
  private spaceHeld = false
  private readonly unsubscribe: (() => void)[] = []
  private readonly store: GameStore
  private readonly cb: EngineCallbacks
  private mounted = false
  // Sharing my measurement: throttled like drag previews, the latest one always goes out.
  private sharing = false
  private measureSentAt = 0
  private measureTimer = 0
  private measurePending: Measured | null = null
  // A pin I just placed: its editor opens when the server confirms it.
  private editOnArrival: string | null = null

  constructor(store: GameStore, callbacks: EngineCallbacks) {
    this.store = store
    this.cb = callbacks
  }

  // --- Lifecycle ----------------------------------------------------------------

  async mount(host: HTMLElement): Promise<void> {
    await this.app.init({
      resizeTo: host,
      background: canvasColors.background,
      antialias: true,
      resolution: window.devicePixelRatio,
      autoDensity: true,
    })
    host.appendChild(this.app.canvas)
    this.mounted = true
    const gl = (this.app.renderer as unknown as { gl?: WebGL2RenderingContext }).gl
    if (gl) this.limitTextureSize(gl.getParameter(gl.MAX_TEXTURE_SIZE))

    this.world.addChild(this.background)
    for (const layer of LAYERS) {
      const c = new Container({ sortableChildren: true, label: `layer:${layer}` })
      this.layers.set(layer, c)
      this.world.addChild(c)
      // Grid lines go right above the map layer: over the maps, under the tokens.
      if (layer === 'map') this.world.addChild(this.grid)
    }
    this.overlayLabel.anchor.set(0.5, 1.2)
    // Fog above every layer, below rulers, pings and what I'm drawing.
    this.world.addChild(this.fogSprite)
    this.world.addChild(this.remoteLayer, this.overlay, this.overlayLabel, this.pings)
    this.app.stage.addChild(this.world)

    const canvas = this.app.canvas
    canvas.addEventListener('pointerdown', this.onPointerDown)
    canvas.addEventListener('pointermove', this.onPointerMove)
    canvas.addEventListener('pointerup', this.onPointerUp)
    canvas.addEventListener('pointercancel', this.onPointerUp)
    canvas.addEventListener('wheel', this.onWheel, { passive: false })
    canvas.addEventListener('dblclick', this.onDoubleClick)
    canvas.addEventListener('contextmenu', (e) => e.preventDefault())
    canvas.addEventListener('dragover', (e) => e.preventDefault())
    window.addEventListener('keydown', this.onKeyDown)
    window.addEventListener('keyup', this.onKeyUp)

    const s = this.store
    this.unsubscribe.push(
      s.on('page', (page, objects) => this.loadPage(page, objects)),
      s.on('pageUpdated', (page) => this.updatePage(page)),
      s.on('upsert', (objs) => this.upsert(objs)),
      s.on('removed', (ids) => this.remove(ids)),
      s.on('preview', (items) => this.applyPreview(items)),
      s.on('selection', () => this.refreshSelection()),
      s.on('turn', () => this.refreshTurn()),
      s.on('ping', (p) => this.showPing(p)),
      s.on('measure', (m) => this.showRemoteMeasure(m)),
      s.on('focus', (x, y) => this.centerOn(x, y)),
    )
    if (s.page) this.loadPage(s.page, [...s.objects.values()])
  }

  destroy(): void {
    for (const off of this.unsubscribe) off()
    window.removeEventListener('keydown', this.onKeyDown)
    window.removeEventListener('keyup', this.onKeyUp)
    clearTimeout(this.measureTimer)
    if (this.mounted) this.app.destroy(true, { children: true })
    this.views.clear()
  }

  // --- Camera -------------------------------------------------------------------

  get zoom(): number {
    return this.world.scale.x
  }

  private setZoom(zoom: number, anchor: Point): void {
    const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom))
    const before = this.toWorld(anchor)
    this.world.scale.set(z)
    this.world.position.set(anchor.x - before.x * z, anchor.y - before.y * z)
    this.cb.onZoom(z)
    this.redrawRemoteRulers()
    this.rescalePins()
  }

  /** Pins keep the same size on screen whatever the zoom. */
  private rescalePins(): void {
    for (const v of this.views.values()) if (v.obj.kind === 'pin') v.setScreenScale(1 / this.zoom)
  }

  zoomBy(factor: number): void {
    const { width, height } = this.app.screen
    this.setZoom(this.zoom * factor, { x: width / 2, y: height / 2 })
  }

  fitPage(): void {
    if (!this.page) return
    const { w, h } = pagePixelSize(this.page)
    const { width, height } = this.app.screen
    const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(width / w, height / h) * 0.92))
    this.world.scale.set(z)
    this.world.position.set((width - w * z) / 2, (height - h * z) / 2)
    this.cb.onZoom(z)
    this.redrawRemoteRulers()
    this.rescalePins()
  }

  centerOn(x: number, y: number): void {
    const { width, height } = this.app.screen
    const z = this.zoom
    this.world.position.set(width / 2 - x * z, height / 2 - y * z)
  }

  private toWorld(screen: Point): Point {
    const z = this.zoom
    return { x: (screen.x - this.world.x) / z, y: (screen.y - this.world.y) / z }
  }

  private local(e: PointerEvent | WheelEvent | MouseEvent): Point {
    const rect = this.app.canvas.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  /** World coordinates of a client-space point (used for drag & drop from the UI). */
  clientToWorld(clientX: number, clientY: number): Point {
    const rect = this.app.canvas.getBoundingClientRect()
    return this.toWorld({ x: clientX - rect.left, y: clientY - rect.top })
  }

  // --- Page & objects -----------------------------------------------------------

  private loadPage(page: Page, objects: MapObject[]): void {
    const samePage = this.page?.id === page.id
    for (const v of this.views.values()) v.destroy()
    this.views.clear()
    this.page = page
    this.drawPage(page)
    for (const o of objects) this.upsertOne(o)
    this.refreshTurn()
    if (!samePage) {
      for (const r of this.remoteRulers.values()) r.root.destroy({ children: true })
      this.remoteRulers.clear()
      this.fitPage()
    }
  }

  private updatePage(page: Page): void {
    this.page = page
    this.drawPage(page)
    for (const v of this.views.values()) v.update(v.obj, page)
    this.redrawRemoteRulers()
  }

  /** The fog as one texture: the page dark, revealed areas cut out, hidden ones dark again. */
  private drawFog(page: Page): void {
    const fog = page.fog
    if (!fog?.enabled) {
      this.fogSprite.visible = false
      return
    }
    const { w, h } = pagePixelSize(page)
    // Huge pages: a coarser fog texture keeps under the GPU size limit.
    const resolution = Math.min(1, 4096 / Math.max(w, h))
    if (!this.fogTexture || this.fogTexture.width !== w || this.fogTexture.height !== h) {
      this.fogTexture?.destroy(true)
      this.fogTexture = RenderTexture.create({ width: w, height: h, resolution })
    }
    const scene = new Container()
    scene.addChild(new Graphics().rect(0, 0, w, h).fill(canvasColors.fog))
    for (const area of fog.ops) {
      const g = new Graphics()
      const p = area.points
      if (area.shape === 'rect') g.rect(Math.min(p[0], p[2]), Math.min(p[1], p[3]), Math.abs(p[2] - p[0]), Math.abs(p[3] - p[1]))
      else g.poly(p)
      g.fill(canvasColors.fog)
      if (area.mode === 'reveal') g.blendMode = 'erase'
      scene.addChild(g)
    }
    this.app.renderer.render({ container: scene, target: this.fogTexture, clear: true })
    scene.destroy({ children: true })
    this.fogSprite.texture = this.fogTexture
    // The GM sees through it.
    this.fogSprite.alpha = this.store.isGm ? 0.45 : 1
    this.fogSprite.visible = true
  }

  private drawPage(page: Page): void {
    this.drawFog(page)
    drawBackground(this.background, page)
    drawGrid(this.grid, page)
  }

  private upsert(objs: MapObject[]): void {
    for (const o of objs) this.upsertOne(o)
    this.refreshSelection()
    this.refreshTurn()
  }

  private upsertOne(o: MapObject): void {
    if (!this.page || o.page_id !== this.page.id) return
    const dragging = this.gesture.kind === 'drag' && this.gesture.origins.has(o.id)
    let view = this.views.get(o.id)
    if (view) {
      const parent = this.layers.get(o.layer)!
      if (view.root.parent !== parent) parent.addChild(view.root)
      const { x, y } = view.root
      view.update(o, this.page)
      // Don't let a late server echo yank a token the user is dragging.
      if (dragging) view.setPosition(x, y)
    } else {
      view = new ObjectView(o, this.page)
      if (o.kind === 'pin') view.setScreenScale(1 / this.zoom)
      this.views.set(o.id, view)
      this.layers.get(o.layer)!.addChild(view.root)
    }
    if (o.id === this.editOnArrival) {
      this.editOnArrival = null
      this.cb.onEdit(o.id)
    }
  }

  private remove(ids: string[]): void {
    for (const id of ids) {
      this.views.get(id)?.destroy()
      this.views.delete(id)
    }
  }

  private applyPreview(items: PreviewItem[]): void {
    for (const item of items) this.views.get(item.id)?.setPosition(item.x, item.y, item.rotation)
  }

  /** Mark the token whose turn it is (when combat is running). */
  private refreshTurn(): void {
    const game = this.store.game
    const current = game && (game.settings.round ?? 0) > 0 ? game.turn_order[0]?.object_id : null
    for (const [id, v] of this.views) v.setTurn(id === current)
  }

  private refreshSelection(): void {
    const selected = new Set(this.store.selection)
    const color = this.store.me?.color ?? canvasColors.accent
    for (const [id, v] of this.views) v.setSelected(selected.has(id), color)
    this.drawOverlay()
  }

  // --- Hit testing ----------------------------------------------------------------

  private activeLayer(): Layer {
    return this.store.isGm ? this.store.layer : 'objects'
  }

  private hitTest(p: Point): ObjectView | null {
    const layer = this.activeLayer()
    let best: ObjectView | null = null
    for (const v of this.views.values()) {
      const o = v.obj
      if (o.layer !== layer || !this.store.controls(o)) continue
      if (!contains(v, p, this.zoom)) continue
      if (!best || stackZ(o) > stackZ(best.obj)) best = v
    }
    return best
  }

  /** Topmost pin at a point among those I can see (players click them to read the notes). */
  private pinAt(p: Point): ObjectView | null {
    let best: ObjectView | null = null
    for (const v of this.views.values()) {
      if (v.obj.kind !== 'pin' || !contains(v, p, this.zoom)) continue
      if (!best || stackZ(v.obj) > stackZ(best.obj)) best = v
    }
    return best
  }

  /** Topmost visible token at a point, on any layer I can see, controlled or not. */
  private tokenAt(p: Point): ObjectView | null {
    let best: ObjectView | null = null
    for (const v of this.views.values()) {
      if (v.obj.kind !== 'token' || !contains(v, p, this.zoom)) continue
      if (!best || stackZ(v.obj) > stackZ(best.obj)) best = v
    }
    return best
  }

  private singleSelected(): ObjectView | null {
    if (this.store.selection.length !== 1) return null
    const v = this.views.get(this.store.selection[0])
    return v && this.store.controls(v.obj) && v.obj.kind !== 'path' ? v : null
  }

  private handleAt(p: Point): ResizeHandle | 'rotate' | null {
    const v = this.singleSelected()
    if (!v || v.obj.kind === 'template' || v.obj.kind === 'text' || v.obj.kind === 'pin') return null
    // Locked: no resizing or rotating either.
    if (v.obj.props.locked) return null
    const o = v.obj
    const tol = HANDLE_PX / this.zoom
    const local = toLocal(o, p)
    const { w, h } = v.bounds()
    const rotY = -h / 2 - ROTATE_OFFSET_PX / this.zoom
    if (Math.hypot(local.x, local.y - rotY) <= tol * 1.2) return 'rotate'
    for (const handle of resizeHandles(w * this.zoom, h * this.zoom)) {
      if (Math.abs(local.x - (handle.sx * w) / 2) <= tol && Math.abs(local.y - (handle.sy * h) / 2) <= tol) {
        return handle
      }
    }
    return null
  }

  // --- Pointer input ----------------------------------------------------------------

  private onPointerDown = (e: PointerEvent): void => {
    if (!this.page) return
    this.app.canvas.setPointerCapture(e.pointerId)
    const screen = this.local(e)
    const p = this.toWorld(screen)
    const tool = this.store.tool

    if (e.button === 1 || e.button === 2 || this.spaceHeld) {
      this.gesture = {
        kind: 'pan',
        startX: screen.x,
        startY: screen.y,
        camX: this.world.x,
        camY: this.world.y,
        moved: false,
        button: e.button,
      }
      return
    }
    if (e.button !== 0) return

    // A chat message waits for its @{target|…}: the click picks a token, nothing else.
    if (this.store.targetPick || this.store.pickingSheetTarget) {
      const target = this.tokenAt(p)
      if (target) this.store.pickTarget(target.obj.id)
      return
    }

    if (tool === 'select') {
      const handle = this.handleAt(p)
      if (handle) {
        const v = this.singleSelected()!
        this.gesture =
          handle === 'rotate'
            ? { kind: 'rotate', id: v.obj.id, deg: null }
            : { kind: 'resize', id: v.obj.id, handle, start: v.obj }
        return
      }
      const hit = this.hitTest(p)
      if (hit) {
        const id = hit.obj.id
        const sel = this.store.selection
        if (e.shiftKey) {
          this.store.setSelection(sel.includes(id) ? sel.filter((s) => s !== id) : [...sel, id])
        } else if (!sel.includes(id)) {
          this.store.setSelection([id])
        }
        const origins = new Map<string, Point>()
        for (const sid of this.store.selection) {
          const o = this.store.objects.get(sid)
          if (o && this.store.controls(o) && !o.props.locked) origins.set(sid, { x: o.x, y: o.y })
        }
        this.gesture = { kind: 'drag', start: p, origins, moved: false, lastSent: 0, waypoints: [] }
        if (!origins.size && hit.obj.kind === 'pin') this.cb.onPin(id, e.clientX, e.clientY)
        return
      }
      // Pins I don't control (players): a click shows their notes.
      const pin = this.pinAt(p)
      if (pin) {
        this.cb.onPin(pin.obj.id, e.clientX, e.clientY)
        return
      }
      const startClient = { x: e.clientX, y: e.clientY }
      const timer = window.setTimeout(() => {
        if (this.gesture.kind === 'marquee') {
          this.gesture = { kind: 'none' }
          this.drawOverlay()
          this.store.ping(p.x, p.y, e.shiftKey && this.store.isGm)
        }
      }, LONG_PRESS_MS)
      this.gesture = { kind: 'marquee', start: p, additive: e.shiftKey, timer, startClient }
      if (!e.shiftKey) this.store.setSelection([])
      return
    }

    if (tool === 'ruler') {
      this.gesture = { kind: 'ruler', start: this.maybeSnapPoint(p, e), waypoints: [] }
      return
    }

    if (tool === 'eraser') {
      const g: Gesture = { kind: 'erase', ids: new Set() }
      this.gesture = g
      this.eraseAt(p, g)
      return
    }

    if (tool === 'pin' && this.store.isGm) {
      this.placePin(p)
      return
    }

    if (tool === 'text') {
      this.cb.onTextRequest(p, e.clientX, e.clientY)
      return
    }

    if (tool === 'draw-polygon' || tool === 'fog-reveal-poly' || tool === 'fog-hide-poly') {
      this.addPolygonPoint(p, e.detail >= 2)
      return
    }

    if (tool === 'fog-reveal' || tool === 'fog-hide') {
      this.gesture = { kind: 'fog', mode: tool === 'fog-reveal' ? 'reveal' : 'hide', start: p }
      return
    }

    if (tool.startsWith('draw-')) {
      this.gesture = { kind: 'draw', tool, start: p, points: [p.x, p.y] }
      return
    }

    if (tool === 'template-circle') {
      // Areas start at a cell centre; the circle then covers whole cells (see areaRadius).
      const snapped = this.page.snap && !e.altKey && this.page.grid_type !== 'none'
      this.gesture = { kind: 'template', start: this.maybeSnapPoint(p, e), snapped }
    }
  }

  private onPointerMove = (e: PointerEvent): void => {
    const screen = this.local(e)
    const p = this.toWorld(screen)
    const g = this.gesture

    switch (g.kind) {
      case 'none':
        if (this.store.tool === 'select') {
          const handle = this.handleAt(p)
          this.app.canvas.style.cursor =
            handle === 'rotate'
              ? 'grab'
              : handle
                ? resizeCursor(handle, this.singleSelected()!.obj.rotation)
                : this.hitTest(p)?.obj.props.locked
                  ? 'not-allowed'
                  : this.hitTest(p) || this.pinAt(p)
                    ? 'pointer'
                    : 'default'
        } else if (this.store.tool === 'draw-polygon' && this.polygon) {
          this.drawOverlay(p)
        } else if (this.store.tool === 'eraser') {
          this.drawOverlay(p)
        }
        return
      case 'erase':
        this.eraseAt(p, g)
        this.drawOverlay(p)
        return
      case 'pan': {
        const dx = screen.x - g.startX
        const dy = screen.y - g.startY
        if (Math.hypot(dx, dy) > CLICK_SLOP_PX) g.moved = true
        this.world.position.set(g.camX + dx, g.camY + dy)
        return
      }
      case 'drag': {
        const dx = p.x - g.start.x
        const dy = p.y - g.start.y
        if (!g.moved && Math.hypot(dx, dy) * this.zoom < CLICK_SLOP_PX) return
        g.moved = true
        g.noSnap = e.altKey
        const items: PreviewItem[] = []
        for (const [id, origin] of g.origins) {
          const v = this.views.get(id)
          if (!v) continue
          // Tokens hop from cell to cell while dragged, so they never sit off the grid.
          const { x, y } = this.snapObject(v.obj, { x: origin.x + dx, y: origin.y + dy }, e.altKey)
          v.setPosition(x, y)
          items.push({ id, x, y })
        }
        this.sendPreview(g, items)
        this.drawOverlay()
        return
      }
      case 'marquee': {
        if (Math.hypot(e.clientX - g.startClient.x, e.clientY - g.startClient.y) > CLICK_SLOP_PX) {
          clearTimeout(g.timer)
        }
        this.drawOverlay(p)
        return
      }
      case 'resize': {
        const v = this.views.get(g.id)
        if (!v || !this.page) return
        v.update(resizeFrom(this.page, g.start, g.handle, p, e), this.page)
        this.drawOverlay()
        return
      }
      case 'rotate': {
        const v = this.views.get(g.id)
        if (!v) return
        let deg = (Math.atan2(p.y - v.obj.y, p.x - v.obj.x) * 180) / Math.PI + 90
        if (!e.altKey) deg = Math.round(deg / 15) * 15
        v.setPosition(v.obj.x, v.obj.y, deg)
        g.deg = deg
        return
      }
      case 'ruler':
        g.end = this.maybeSnapPoint(p, e)
        this.drawOverlay()
        return
      case 'template':
        this.drawOverlay(p)
        return
      case 'draw':
        if (g.tool === 'draw-free') {
          const lx = g.points[g.points.length - 2]
          const ly = g.points[g.points.length - 1]
          if (Math.hypot(p.x - lx, p.y - ly) * this.zoom >= 2) g.points.push(p.x, p.y)
        }
        this.drawOverlay(p)
        return
    }
  }

  private onPointerUp = (e: PointerEvent): void => {
    const screen = this.local(e)
    const p = this.toWorld(screen)
    const g = this.gesture
    this.gesture = { kind: 'none' }

    switch (g.kind) {
      case 'pan':
        if (!g.moved && g.button === 2) {
          const hit = this.hitTest(p)
          if (hit && !this.store.selection.includes(hit.obj.id)) this.store.setSelection([hit.obj.id])
          this.cb.onContext(hit ? hit.obj.id : null, e.clientX, e.clientY)
        }
        break
      case 'drag':
        if (g.moved) this.commitDrag(g, e.altKey)
        else if (g.origins.size === 1) {
          // A click on a pin I can move (GM): show it like everyone else.
          const id = [...g.origins.keys()][0]
          if (this.store.objects.get(id)?.kind === 'pin') this.cb.onPin(id, e.clientX, e.clientY)
        }
        break
      case 'erase':
        this.commitErase(g)
        break
      case 'marquee': {
        clearTimeout(g.timer)
        const ids = this.marqueeHits(g.start, p)
        const base = g.additive ? this.store.selection : []
        this.store.setSelection([...new Set([...base, ...ids])])
        break
      }
      case 'resize': {
        const v = this.views.get(g.id)
        if (v && v.obj !== g.start) {
          const { x, y, width, height } = v.obj
          this.store.updateObjects([{ id: g.id, x, y, width, height }])
        }
        break
      }
      case 'rotate':
        if (g.deg !== null) {
          this.store.updateObjects([{ id: g.id, rotation: ((g.deg % 360) + 360) % 360 }])
        }
        break
      case 'draw':
        this.commitDrawing(g, p)
        break
      case 'template':
        this.commitTemplate(g, p)
        break
      case 'fog':
        if (Math.hypot(p.x - g.start.x, p.y - g.start.y) * this.zoom >= CLICK_SLOP_PX) {
          this.store.fogArea(g.mode, 'rect', [g.start.x, g.start.y, p.x, p.y])
        }
        break
    }
    this.drawOverlay()
  }

  private onWheel = (e: WheelEvent): void => {
    e.preventDefault()
    // "Pan" setting: the wheel scrolls the map, Ctrl+wheel (and trackpad pinch) still zooms.
    if (this.store.settings.wheel === 'pan' && !e.ctrlKey) {
      const dx = e.shiftKey && !e.deltaX ? e.deltaY : e.deltaX
      const dy = e.shiftKey && !e.deltaX ? 0 : e.deltaY
      this.world.position.set(this.world.x - dx, this.world.y - dy)
      return
    }
    const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015))
    this.setZoom(this.zoom * factor, this.local(e))
  }

  private onDoubleClick = (e: MouseEvent): void => {
    if (this.store.tool !== 'select') return
    const hit = this.hitTest(this.toWorld(this.local(e)))
    if (hit) this.cb.onEdit(hit.obj.id)
  }

  // --- Gesture helpers --------------------------------------------------------------

  private maybeSnapPoint(p: Point, e: { altKey: boolean }): Point {
    if (!this.page || !this.page.snap || e.altKey) return p
    // Rulers and templates always start and end at cell centres, never at corners.
    return cellCenter(this.page, p)
  }

  private snapObject(o: MapObject, p: Point, noSnap: boolean): Point {
    const page = this.page
    if (!page || !page.snap || noSnap) return p
    // Spell areas keep their centre on a cell centre, like when they are created.
    if (o.kind === 'template' && o.props.shape === 'circle') return cellCenter(page, p)
    if (o.kind !== 'token' && o.kind !== 'image') return p
    return snapCenter(page, p, o.width, o.height)
  }

  private sendPreview(g: Extract<Gesture, { kind: 'drag' }>, items: PreviewItem[]): void {
    const now = performance.now()
    if (now - g.lastSent >= PREVIEW_INTERVAL_MS) {
      g.lastSent = now
      this.store.preview(items)
    }
  }

  private commitDrag(g: Extract<Gesture, { kind: 'drag' }>, noSnap: boolean): void {
    if (!this.page) return
    const patches: ObjectPatch[] = []
    // Every object followed the lead one: its waypoints, shifted to where each object started.
    const lead = g.origins.values().next().value
    const via: Record<string, number[]> = {}
    for (const [id, origin] of g.origins) {
      const v = this.views.get(id)
      if (!v) continue
      const pos = this.snapObject(v.obj, { x: v.root.x, y: v.root.y }, noSnap)
      v.setPosition(pos.x, pos.y)
      patches.push({ id, x: pos.x, y: pos.y })
      if (lead && g.waypoints.length) {
        via[id] = g.waypoints.flatMap((w) => [w.x - lead.x + origin.x, w.y - lead.y + origin.y])
      }
    }
    if (patches.length) this.store.updateObjects(patches, g.waypoints.length ? via : undefined)
  }

  // --- Eraser and pins ------------------------------------------------

  /** Mark the drawings under the eraser (mine, or any for the GM); they go on release. */
  private eraseAt(p: Point, g: Extract<Gesture, { kind: 'erase' }>): void {
    const layer = this.drawingLayer()
    const reach = ERASER_PX / this.zoom
    for (const v of this.views.values()) {
      const o = v.obj
      if (g.ids.has(o.id) || o.layer !== layer || (o.kind !== 'path' && o.kind !== 'text')) continue
      if (!this.store.canDelete(o) || !touchesDrawing(v, p, reach)) continue
      g.ids.add(o.id)
      v.root.alpha = 0.3
    }
  }

  private commitErase(g: Extract<Gesture, { kind: 'erase' }>): void {
    if (!g.ids.size) return
    this.store.deleteObjects([...g.ids])
    // Anything the server refused to delete comes back.
    window.setTimeout(() => {
      for (const id of g.ids) {
        const v = this.views.get(id)
        if (v && this.page) v.update(v.obj, this.page)
      }
    }, 1500)
  }

  private placePin(p: Point): void {
    if (!this.page) return
    const id = uid()
    this.editOnArrival = id
    this.store.createObjects([
      {
        id,
        page_id: this.page.id,
        kind: 'pin',
        layer: this.store.layer === 'gm' ? 'gm' : 'objects',
        x: p.x,
        y: p.y,
        width: 1,
        height: 1,
        rotation: 0,
        props: { title: '', icon: '📍', notes: '' },
      },
    ])
    this.store.tool = 'select'
  }

  private marqueeHits(a: Point, b: Point): string[] {
    const minX = Math.min(a.x, b.x)
    const maxX = Math.max(a.x, b.x)
    const minY = Math.min(a.y, b.y)
    const maxY = Math.max(a.y, b.y)
    if ((maxX - minX) * this.zoom < CLICK_SLOP_PX && (maxY - minY) * this.zoom < CLICK_SLOP_PX) {
      return []
    }
    const layer = this.activeLayer()
    const ids: string[] = []
    for (const v of this.views.values()) {
      const o = v.obj
      if (o.layer !== layer || !this.store.controls(o)) continue
      if (o.x >= minX && o.x <= maxX && o.y >= minY && o.y <= maxY) ids.push(o.id)
    }
    return ids
  }

  private addPolygonPoint(p: Point, finish: boolean): void {
    if (!this.polygon) this.polygon = []
    const pts = this.polygon
    const closeToStart =
      pts.length >= 6 && Math.hypot(p.x - pts[0], p.y - pts[1]) * this.zoom < HANDLE_PX * 1.5
    if (finish || closeToStart) {
      const tool = this.store.tool
      if (pts.length >= 6 && tool === 'draw-polygon') this.createPath('polygon', pts)
      else if (pts.length >= 6) this.store.fogArea(tool === 'fog-reveal-poly' ? 'reveal' : 'hide', 'poly', pts)
      this.polygon = null
      this.drawOverlay()
      return
    }
    pts.push(p.x, p.y)
    this.drawOverlay(p)
  }

  private commitDrawing(g: Extract<Gesture, { kind: 'draw' }>, end: Point): void {
    const { start } = g
    if (Math.hypot(end.x - start.x, end.y - start.y) * this.zoom < CLICK_SLOP_PX) return
    if (g.tool === 'draw-free') this.createPath('free', [...g.points, end.x, end.y])
    else if (g.tool === 'draw-line') this.createPath('line', [start.x, start.y, end.x, end.y])
    else this.createBox(g.tool === 'draw-rect' ? 'rect' : 'ellipse', start, end)
  }

  private drawingLayer(): Layer {
    return this.activeLayer()
  }

  private createPath(shape: 'free' | 'line' | 'polygon', abs: number[]): void {
    if (!this.page) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (let i = 0; i < abs.length; i += 2) {
      minX = Math.min(minX, abs[i])
      maxX = Math.max(maxX, abs[i])
      minY = Math.min(minY, abs[i + 1])
      maxY = Math.max(maxY, abs[i + 1])
    }
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    const points = abs.map((v, i) => Math.round((i % 2 ? v - cy : v - cx) * 10) / 10)
    const style = this.store.drawStyle
    this.store.createObjects([
      {
        id: uid(),
        page_id: this.page.id,
        kind: 'path',
        layer: this.drawingLayer(),
        x: cx,
        y: cy,
        width: Math.max(1, maxX - minX),
        height: Math.max(1, maxY - minY),
        rotation: 0,
        props: {
          shape,
          points,
          stroke: style.stroke,
          stroke_width: style.strokeWidth,
          fill: shape === 'polygon' ? style.fill : null,
        },
      },
    ])
  }

  private createBox(shape: 'rect' | 'ellipse', a: Point, b: Point): void {
    if (!this.page) return
    const style = this.store.drawStyle
    this.store.createObjects([
      {
        id: uid(),
        page_id: this.page.id,
        kind: 'path',
        layer: this.drawingLayer(),
        x: (a.x + b.x) / 2,
        y: (a.y + b.y) / 2,
        width: Math.max(1, Math.abs(b.x - a.x)),
        height: Math.max(1, Math.abs(b.y - a.y)),
        rotation: 0,
        props: { shape, stroke: style.stroke, stroke_width: style.strokeWidth, fill: style.fill },
      },
    ])
  }

  private commitTemplate(g: Extract<Gesture, { kind: 'template' }>, end: Point): void {
    if (!this.page) return
    // A click, or a drag shorter than one cell, creates nothing.
    const { cells, size } = areaRadius(this.page, g.start, end, g.snapped)
    if (cells < 1) return
    this.store.createObjects([
      {
        id: uid(),
        page_id: this.page.id,
        kind: 'template',
        layer: 'objects',
        x: g.start.x,
        y: g.start.y,
        width: 1,
        height: 1,
        rotation: 0,
        props: {
          shape: 'circle',
          size,
          width: this.page.grid_size,
          color: this.store.me?.color ?? canvasColors.template,
        },
      },
    ])
  }

  createText(world: Point, text: string): void {
    if (!this.page || !text.trim()) return
    const style = this.store.drawStyle
    this.store.createObjects([
      {
        id: uid(),
        page_id: this.page.id,
        kind: 'text',
        layer: this.drawingLayer(),
        x: world.x,
        y: world.y,
        width: 10,
        height: 10,
        rotation: 0,
        props: { text: text.trim(), color: style.stroke, font_size: style.fontSize },
      },
    ])
  }

  // --- Overlay ------------------------------------------------------------------

  private drawOverlay(cursor?: Point): void {
    const g = this.overlay
    const z = this.zoom
    g.clear()
    this.overlayLabel.text = ''
    const accent = this.store.me?.color ?? canvasColors.accent
    const gesture = this.gesture
    let measured: Measured | null = null

    // Handles for the single selected object.
    const v = this.singleSelected()
    if (v && gesture.kind !== 'drag' && v.obj.kind !== 'template' && v.obj.kind !== 'text') {
      const o = v.obj
      const { w, h } = v.bounds()
      const hs = HANDLE_PX / z
      const top = fromLocal(o, { x: 0, y: -h / 2 })
      const rot = fromLocal(o, { x: 0, y: -h / 2 - ROTATE_OFFSET_PX / z })
      for (const handle of resizeHandles(w * z, h * z)) {
        const c = fromLocal(o, { x: (handle.sx * w) / 2, y: (handle.sy * h) / 2 })
        g.rect(c.x - hs / 2, c.y - hs / 2, hs, hs).fill(canvasColors.handle).stroke({ width: 1.5 / z, color: accent })
      }
      g.moveTo(top.x, top.y).lineTo(rot.x, rot.y).stroke({ width: 1.5 / z, color: accent })
      g.circle(rot.x, rot.y, hs / 1.6).fill(canvasColors.handle).stroke({ width: 1.5 / z, color: accent })
    }

    if (gesture.kind === 'drag' && gesture.moved && this.page) {
      // Show how far the lead token travelled, like a ruler.
      const [id, origin] = gesture.origins.entries().next().value ?? []
      const view = id ? this.views.get(id) : undefined
      if (view && origin) {
        let from = origin
        let to = { x: view.root.x, y: view.root.y }
        const snaps = view.obj.kind === 'token' || view.obj.kind === 'image'
        if (snaps && this.page.snap && !gesture.noSnap) {
          // Measure cell centre to cell centre, like the ruler.
          const { width, height } = view.obj
          from = anchorCell(this.page, from, width, height)
          to = anchorCell(this.page, to, width, height)
        }
        const lead = view.obj
        const stops = gesture.waypoints.map((w) =>
          snaps && this.page!.snap && !gesture.noSnap ? anchorCell(this.page!, w, lead.width, lead.height) : w,
        )
        const path = [from, ...stops, to]
        this.rulerPath(g, this.overlayLabel, path, accent)
        measured = { segment: pathSegment(path), objectId: id }
      }
    } else if (gesture.kind === 'ruler' && gesture.end) {
      const path = [gesture.start, ...gesture.waypoints, gesture.end]
      this.rulerPath(g, this.overlayLabel, path, accent)
      measured = { segment: pathSegment(path) }
    }
    this.shareMeasure(measured)

    if (!cursor) return

    if (this.store.tool === 'eraser') {
      g.circle(cursor.x, cursor.y, ERASER_PX / z).stroke({ width: 1.5 / z, color: accent })
    }

    if (gesture.kind === 'marquee') {
      const { start } = gesture
      g.rect(
        Math.min(start.x, cursor.x),
        Math.min(start.y, cursor.y),
        Math.abs(cursor.x - start.x),
        Math.abs(cursor.y - start.y),
      )
        .fill({ color: accent, alpha: 0.1 })
        .stroke({ width: 1 / z, color: accent })
    } else if (gesture.kind === 'draw') {
      const style = this.store.drawStyle
      const { start } = gesture
      if (gesture.tool === 'draw-free') {
        const pts = gesture.points
        g.moveTo(pts[0], pts[1])
        for (let i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1])
      } else if (gesture.tool === 'draw-line') {
        g.moveTo(start.x, start.y).lineTo(cursor.x, cursor.y)
      } else if (gesture.tool === 'draw-rect') {
        g.rect(Math.min(start.x, cursor.x), Math.min(start.y, cursor.y), Math.abs(cursor.x - start.x), Math.abs(cursor.y - start.y))
      } else {
        g.ellipse((start.x + cursor.x) / 2, (start.y + cursor.y) / 2, Math.abs(cursor.x - start.x) / 2, Math.abs(cursor.y - start.y) / 2)
      }
      g.stroke({ width: style.strokeWidth, color: style.stroke, cap: 'round', join: 'round' })
    } else if (gesture.kind === 'template' && this.page) {
      // Radius grows one whole cell at a time; the label is the radius.
      const o = gesture.start
      const { cells, size, end } = areaRadius(this.page, o, cursor, gesture.snapped)
      if (cells < 1) return
      g.circle(o.x, o.y, size).fill({ color: accent, alpha: 0.25 }).stroke({ width: 2 / z, color: accent })
      this.rulerLine(g, this.overlayLabel, o, end, accent)
      this.overlayLabel.text = formatDistance(this.page, cells * this.page.scale_number)
    } else if (gesture.kind === 'fog') {
      const s = gesture.start
      const color = gesture.mode === 'reveal' ? canvasColors.turn : canvasColors.fog
      g.rect(Math.min(s.x, cursor.x), Math.min(s.y, cursor.y), Math.abs(cursor.x - s.x), Math.abs(cursor.y - s.y))
        .fill({ color, alpha: 0.25 })
        .stroke({ width: 2 / z, color: accent })
    } else if (this.polygon && this.store.tool.startsWith('fog-')) {
      const pts = this.polygon
      g.moveTo(pts[0], pts[1])
      for (let i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1])
      g.lineTo(cursor.x, cursor.y)
      g.stroke({ width: 2 / z, color: accent })
    } else if (this.polygon && this.store.tool === 'draw-polygon') {
      const pts = this.polygon
      g.moveTo(pts[0], pts[1])
      for (let i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1])
      g.lineTo(cursor.x, cursor.y)
      g.stroke({ width: this.store.drawStyle.strokeWidth, color: this.store.drawStyle.stroke })
    }
  }

  /** A ruler through waypoints: the label is the total distance along the path. */
  private rulerPath(g: Graphics, label: Text, path: Point[], color: string): void {
    if (!this.page || path.length < 2) return
    if (path.length === 2) return this.rulerLine(g, label, path[0], path[1], color)
    const z = this.zoom
    g.moveTo(path[0].x, path[0].y)
    for (const pt of path.slice(1)) g.lineTo(pt.x, pt.y)
    g.stroke({ width: 4 / z, color: canvasColors.outline, alpha: 0.6 })
    g.moveTo(path[0].x, path[0].y)
    for (const pt of path.slice(1)) g.lineTo(pt.x, pt.y)
    g.stroke({ width: 2 / z, color })
    for (const pt of path) g.circle(pt.x, pt.y, 4 / z).fill(color)
    let total = 0
    for (let i = 1; i < path.length; i++) total += measure(this.page, path[i - 1], path[i])
    const end = path[path.length - 1]
    label.text = formatDistance(this.page, total)
    label.position.set(end.x, end.y)
    label.scale.set(1 / z)
  }

  private rulerLine(g: Graphics, label: Text, a: Point, b: Point, color: string): void {
    if (!this.page) return
    const z = this.zoom
    g.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({ width: 4 / z, color: canvasColors.outline, alpha: 0.6 })
    g.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({ width: 2 / z, color })
    g.circle(a.x, a.y, 4 / z).fill(color)
    g.circle(b.x, b.y, 4 / z).fill(color)
    label.text = formatDistance(this.page, measure(this.page, a, b))
    label.position.set(b.x, b.y)
    label.scale.set(1 / z)
  }

  // --- Shared measurements ------------------------------------------------------

  /** Send my current measurement (null = none) to the other viewers of the page. */
  private shareMeasure(m: Measured | null): void {
    if (!m) {
      this.measurePending = null
      clearTimeout(this.measureTimer)
      this.measureTimer = 0
      if (this.sharing) this.store.shareMeasure(null)
      this.sharing = false
      return
    }
    this.measurePending = m
    if (this.measureTimer) return
    const wait = PREVIEW_INTERVAL_MS - (performance.now() - this.measureSentAt)
    if (wait <= 0) this.flushMeasure()
    else this.measureTimer = window.setTimeout(this.flushMeasure, wait)
  }

  private flushMeasure = (): void => {
    this.measureTimer = 0
    const m = this.measurePending
    if (!m) return
    this.measurePending = null
    this.measureSentAt = performance.now()
    this.sharing = true
    this.store.shareMeasure(m.segment, m.objectId)
  }

  private showRemoteMeasure(m: RemoteMeasure): void {
    let r = this.remoteRulers.get(m.player_id)
    if (!m.segment) {
      r?.root.destroy({ children: true })
      this.remoteRulers.delete(m.player_id)
      return
    }
    if (!r) {
      const root = new Container()
      const g = new Graphics()
      const label = new Text({ text: '', style: LABEL_STYLE })
      label.anchor.set(0.5, 1.2)
      root.addChild(g, label)
      this.remoteLayer.addChild(root)
      r = { segment: m.segment, color: m.color ?? canvasColors.accent, root, g, label }
      this.remoteRulers.set(m.player_id, r)
    }
    r.segment = m.segment
    if (m.color) r.color = m.color
    this.drawRemoteRuler(r)
  }

  private drawRemoteRuler(r: RemoteRuler): void {
    r.g.clear()
    this.rulerPath(r.g, r.label, segmentPath(r.segment), r.color)
  }

  /** Line widths and labels follow the zoom, so redraw them when it changes. */
  private redrawRemoteRulers(): void {
    for (const r of this.remoteRulers.values()) this.drawRemoteRuler(r)
  }

  // --- Pings ----------------------------------------------------------------------

  private showPing(ping: Ping): void {
    if (ping.pull) this.centerOn(ping.x, ping.y)
    const g = new Graphics()
    this.pings.addChild(g)
    const started = performance.now()
    const duration = 1600
    const tick = () => {
      const t = (performance.now() - started) / duration
      if (t >= 1 || g.destroyed) {
        this.app.ticker.remove(tick)
        if (!g.destroyed) g.destroy()
        return
      }
      g.clear()
      const z = this.zoom
      for (let ring = 0; ring < 3; ring++) {
        const rt = (t * 2 + ring / 3) % 1
        g.circle(ping.x, ping.y, (8 + rt * 46) / z).stroke({ width: 3 / z, color: ping.color, alpha: 1 - rt })
      }
      g.circle(ping.x, ping.y, 5 / z).fill({ color: ping.color, alpha: 1 - t })
    }
    this.app.ticker.add(tick)
  }

  // --- Keyboard -------------------------------------------------------------------

  private onKeyDown = (e: KeyboardEvent): void => {
    if (isTyping(e)) return
    const s = this.store
    if (e.code === 'Space') {
      e.preventDefault()
      const g = this.gesture
      // While dragging a token or measuring, Space drops a waypoint instead of panning.
      if (g.kind === 'drag' && g.moved) {
        if (e.repeat) return
        const lead = this.views.get(g.origins.keys().next().value ?? '')
        if (lead) g.waypoints.push({ x: lead.root.x, y: lead.root.y })
        this.drawOverlay()
        return
      }
      if (g.kind === 'ruler' && g.end) {
        if (!e.repeat) g.waypoints.push(g.end)
        this.drawOverlay()
        return
      }
      this.spaceHeld = true
      return
    }
    if (e.key === 'Escape') {
      s.cancelTarget()
      this.polygon = null
      this.gesture = { kind: 'none' }
      s.setSelection([])
      this.drawOverlay()
      return
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && s.selection.length) {
      s.deleteObjects(s.selection)
      e.preventDefault()
      return
    }
    if (e.key.startsWith('Arrow') && s.selection.length && this.page) {
      const step = e.shiftKey ? 1 : this.page.grid_size
      const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0
      const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0
      const patches = s.selection
        .map((id) => s.objects.get(id))
        .filter((o): o is MapObject => !!o && s.controls(o) && !o.props.locked)
        .map((o) => ({ id: o.id, x: o.x + dx, y: o.y + dy }))
      if (patches.length) s.updateObjects(patches)
      e.preventDefault()
      return
    }
    const mod = e.ctrlKey || e.metaKey
    // Ctrl+Z undo; Ctrl+Y or Ctrl+Shift+Z redo (server side, see on_undo).
    if (mod && e.key.toLowerCase() === 'z') {
      if (e.shiftKey) s.redo()
      else s.undo()
      e.preventDefault()
      return
    }
    if (mod && e.key.toLowerCase() === 'y') {
      s.redo()
      e.preventDefault()
      return
    }
    if (mod && e.key.toLowerCase() === 'c') {
      this.clipboard = s.selection.map((id) => s.objects.get(id)).filter((o): o is MapObject => !!o)
      return
    }
    if (mod && e.key.toLowerCase() === 'v' && this.clipboard.length) {
      this.paste(this.clipboard)
      e.preventDefault()
      return
    }
    if (mod && e.key.toLowerCase() === 'd' && s.selection.length) {
      this.duplicateSelection()
      e.preventDefault()
      return
    }
    if (mod && e.key.toLowerCase() === 'a') {
      const layer = this.activeLayer()
      s.setSelection([...s.objects.values()].filter((o) => o.layer === layer && s.controls(o)).map((o) => o.id))
      e.preventDefault()
      return
    }
    if (mod) return
    const shortcuts: Record<string, Tool> = { v: 'select', r: 'ruler', d: 'draw-free', t: 'text', e: 'eraser' }
    const tool = shortcuts[e.key.toLowerCase()]
    if (tool) s.tool = tool
  }

  private onKeyUp = (e: KeyboardEvent): void => {
    if (e.code === 'Space') this.spaceHeld = false
  }

  /** GPU texture limit: pictures larger than this are drawn as tiles (tests lower it). */
  limitTextureSize(size: number): void {
    setMaxTextureSize(size)
  }

  duplicateSelection(): void {
    const s = this.store
    this.paste(s.selection.map((id) => s.objects.get(id)).filter((o): o is MapObject => !!o))
  }

  /** Client-space point of a world coordinate (used by tests and overlays). */
  worldToClient(x: number, y: number): Point {
    const rect = this.app.canvas.getBoundingClientRect()
    return { x: rect.left + this.world.x + x * this.zoom, y: rect.top + this.world.y + y * this.zoom }
  }

  /** World point at the centre of the visible canvas. */
  viewCenter(): Point {
    const { width, height } = this.app.screen
    return this.toWorld({ x: width / 2, y: height / 2 })
  }

  private paste(objs: MapObject[]): void {
    if (!this.page) return
    const offset = this.page.grid_size
    const copies = objs
      .filter((o) => this.store.isGm || ['path', 'text', 'template'].includes(o.kind))
      .map((o) => ({
        id: uid(),
        page_id: this.page!.id,
        kind: o.kind,
        layer: this.store.isGm ? o.layer : ('objects' as Layer),
        x: o.x + offset,
        y: o.y + offset,
        width: o.width,
        height: o.height,
        rotation: o.rotation,
        props: structuredClone(o.props),
      }))
    if (!copies.length) return
    this.store.createObjects(copies)
    this.store.setSelection(copies.map((c) => c.id))
  }
}

// --- Resizing ---------------------------------------------------------------------

/** A resize handle: which side it moves on each axis (-1 left/top, 0 none, 1 right/bottom). */
interface ResizeHandle {
  sx: -1 | 0 | 1
  sy: -1 | 0 | 1
}

const RESIZE_HANDLES: ResizeHandle[] = [
  { sx: -1, sy: -1 },
  { sx: 0, sy: -1 },
  { sx: 1, sy: -1 },
  { sx: 1, sy: 0 },
  { sx: 1, sy: 1 },
  { sx: 0, sy: 1 },
  { sx: -1, sy: 1 },
  { sx: -1, sy: 0 },
]

/** Side handles only when the object is big enough on screen not to be buried by them. */
function resizeHandles(screenW: number, screenH: number): ResizeHandle[] {
  const roomy = Math.min(screenW, screenH) >= HANDLE_PX * 5
  return roomy ? RESIZE_HANDLES : RESIZE_HANDLES.filter((h) => h.sx && h.sy)
}

const MIN_SIZE_PX = 10

/**
 * Resize `o` by dragging `handle` to `p`, keeping the opposite side (or corner) fixed.
 * Corners keep the proportions of tokens (Shift frees them) and free those of images
 * (Shift locks them). With snap on, sizes are whole cells.
 */
function resizeFrom(page: Page, o: MapObject, handle: ResizeHandle, p: Point, e: PointerEvent): MapObject {
  const { sx, sy } = handle
  const local = toLocal(o, p)
  // Fixed side, in the object's local frame (centre = 0,0).
  const ax = (-sx * o.width) / 2
  const ay = (-sy * o.height) / 2
  let w = sx ? Math.max(MIN_SIZE_PX, sx * (local.x - ax)) : o.width
  let h = sy ? Math.max(MIN_SIZE_PX, sy * (local.y - ay)) : o.height

  if (sx && sy && (o.kind === 'token') !== e.shiftKey) {
    const k = Math.max(w / o.width, h / o.height)
    w = o.width * k
    h = o.height * k
  }

  if (page.snap && page.grid_type !== 'none' && !e.altKey && (o.kind === 'token' || o.kind === 'image')) {
    // Always a whole number of cells, never 1.5 or 1.25.
    if (sx) w = snapSize(page, w)
    if (sy) h = snapSize(page, h)
    if (page.grid_type === 'square' && o.rotation % 360 === 0) {
      // The fixed side also settles on the nearest grid line, so the object ends up
      // exactly covering whole cells (e.g. a map dropped off-grid lines up with it).
      const s = page.grid_size
      const fixedX = Math.round((o.x + ax) / s) * s
      const fixedY = Math.round((o.y + ay) / s) * s
      return {
        ...o,
        x: sx ? fixedX + (sx * w) / 2 : o.x,
        y: sy ? fixedY + (sy * h) / 2 : o.y,
        width: w,
        height: h,
      }
    }
  }

  const center = fromLocal(o, { x: sx ? ax + (sx * w) / 2 : 0, y: sy ? ay + (sy * h) / 2 : 0 })
  return { ...o, x: center.x, y: center.y, width: w, height: h }
}

const RESIZE_CURSORS = ['ew-resize', 'nwse-resize', 'ns-resize', 'nesw-resize']

/** Resize cursor matching the handle's on-screen direction, rotation included. */
function resizeCursor(handle: ResizeHandle, rotation: number): string {
  const deg = (Math.atan2(handle.sy, handle.sx) * 180) / Math.PI + rotation
  const octant = Math.round(deg / 45)
  return RESIZE_CURSORS[((octant % 4) + 4) % 4]
}

// --- Geometry helpers -------------------------------------------------------------

function toLocal(o: MapObject, p: Point): Point {
  const a = (-o.rotation * Math.PI) / 180
  const dx = p.x - o.x
  const dy = p.y - o.y
  return { x: dx * Math.cos(a) - dy * Math.sin(a), y: dx * Math.sin(a) + dy * Math.cos(a) }
}

function fromLocal(o: MapObject, p: Point): Point {
  const a = (o.rotation * Math.PI) / 180
  return {
    x: o.x + p.x * Math.cos(a) - p.y * Math.sin(a),
    y: o.y + p.x * Math.sin(a) + p.y * Math.cos(a),
  }
}

function contains(v: ObjectView, p: Point, zoom = 1): boolean {
  const o = v.obj
  if (o.kind === 'pin') {
    // The drop above the tip, in screen pixels.
    const dx = (p.x - o.x) * zoom
    const dy = (p.y - o.y) * zoom
    return Math.abs(dx) <= PIN_RADIUS + 2 && dy <= 2 && dy >= -PIN_HEAD_Y - PIN_RADIUS - 2
  }
  if (o.kind === 'template') {
    return Math.hypot(p.x - o.x, p.y - o.y) <= Math.max(12, o.props.size ?? 0)
  }
  const local = toLocal(o, p)
  const { w, h } = v.bounds()
  const pad = 4
  return Math.abs(local.x) <= w / 2 + pad && Math.abs(local.y) <= h / 2 + pad
}

/**
 * Spell area radius in whole cells (0 until the cursor reaches a neighbouring cell), measured from the origin cell's centre like
 * the ruler. When snapped the drawn circle reaches the outer edge of the last cell (half a cell
 * further), so it fills whole cells: radius 1 = the origin cell plus its ring, 3x3 cells.
 * `end` is the radius line's end: the centre of the last cell, towards the cursor.
 */
function areaRadius(page: Page, o: Point, cursor: Point, snapped: boolean): { cells: number; size: number; end: Point } {
  const dist = Math.hypot(cursor.x - o.x, cursor.y - o.y)
  const cells = Math.round(dist / page.grid_size)
  const len = cells * page.grid_size
  const end = dist > 0 ? { x: o.x + ((cursor.x - o.x) / dist) * len, y: o.y + ((cursor.y - o.y) / dist) * len } : { x: o.x + len, y: o.y }
  return { cells, size: (cells + (snapped ? 0.5 : 0)) * page.grid_size, end }
}

/** A path as a shared measurement: its ends, and the waypoints between them. */
function pathSegment(path: Point[]): Segment {
  const a = path[0]
  const b = path[path.length - 1]
  const via = path.slice(1, -1).flatMap((pt) => [pt.x, pt.y])
  return { x1: a.x, y1: a.y, x2: b.x, y2: b.y, ...(via.length && { via }) }
}

function segmentPath(s: Segment): Point[] {
  const via: Point[] = []
  for (let i = 0; i + 1 < (s.via?.length ?? 0); i += 2) via.push({ x: s.via![i], y: s.via![i + 1] })
  return [{ x: s.x1, y: s.y1 }, ...via, { x: s.x2, y: s.y2 }]
}

/** The eraser touches a drawing: near its stroke for lines, inside it for shapes and text. */
function touchesDrawing(v: ObjectView, p: Point, reach: number): boolean {
  const o = v.obj
  const pts: number[] | undefined = o.props.points
  if (o.kind === 'path' && pts && pts.length >= 4 && o.props.shape !== 'polygon') {
    const local = toLocal(o, p)
    const tol = reach + (o.props.stroke_width ?? 4) / 2
    for (let i = 0; i + 3 < pts.length; i += 2) {
      if (distToSegment(local, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]) <= tol) return true
    }
    return false
  }
  const local = toLocal(o, p)
  const { w, h } = v.bounds()
  return Math.abs(local.x) <= w / 2 + reach && Math.abs(local.y) <= h / 2 + reach
}

function distToSegment(p: Point, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const len = dx * dx + dy * dy
  const t = len ? Math.max(0, Math.min(1, ((p.x - x1) * dx + (p.y - y1) * dy) / len)) : 0
  return Math.hypot(p.x - (x1 + t * dx), p.y - (y1 + t * dy))
}

function isTyping(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}
