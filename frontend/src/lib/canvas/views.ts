import { Assets, Container, Graphics, Sprite, Text, Texture } from 'pixi.js'
import type { Bar, MapObject, Page } from '../net/protocol'
import { initials } from '../util/ids'
import { BARS, canvasColors, DEFAULT_DRAW_COLOR, DEFAULT_TOKEN_COLOR } from '../theme'
import { STATUS_ICON } from '../util/statuses'

// Text is rasterised once; a higher resolution keeps it crisp when zooming in.
const TEXT_RESOLUTION = 3

const LABEL_STYLE = {
  fill: canvasColors.label,
  fontSize: 13,
  fontFamily: 'Inter, system-ui, sans-serif',
  fontWeight: '600' as const,
  stroke: { color: canvasColors.outline, width: 3 },
}

/** Largest texture the GPU takes (set by the engine); bigger pictures are cut into tiles. */
let maxTextureSize = 4096

export function setMaxTextureSize(size: number): void {
  maxTextureSize = size
}

/** Tile textures of the pictures too big for the GPU, by URL: cut once, reused by every view. */
const tileCache = new Map<string, { width: number; height: number; tiles: { x: number; y: number; tex: Texture }[] }>()

/** Cut a picture larger than the GPU limit into tiles; null if it fits as it is. */
function tilesOf(url: string, tex: Texture) {
  const { width, height } = tex.source
  if (width <= maxTextureSize && height <= maxTextureSize) return null
  const cached = tileCache.get(url)
  if (cached) return cached
  const image = tex.source.resource as CanvasImageSource
  const tiles = []
  for (let y = 0; y < height; y += maxTextureSize) {
    for (let x = 0; x < width; x += maxTextureSize) {
      const w = Math.min(maxTextureSize, width - x)
      const h = Math.min(maxTextureSize, height - y)
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      canvas.getContext('2d')!.drawImage(image, x, y, w, h, 0, 0, w, h)
      tiles.push({ x, y, tex: Texture.from(canvas) })
    }
  }
  const entry = { width, height, tiles }
  tileCache.set(url, entry)
  return entry
}

/** Map pins, in screen pixels: radius of the head and height of its centre above the tip. */
export const PIN_RADIUS = 15
export const PIN_HEAD_Y = 30

/** One renderable map object. Rebuilds itself from the MapObject on update. */
/** Stacking key: spell areas always sit below tokens and other objects of their layer. */
export function stackZ(obj: MapObject): number {
  return obj.kind === 'template' ? obj.z - 1e9 : obj.z
}

export class ObjectView {
  readonly root = new Container()
  /** Rotates/scales with the object (image, shape). */
  private readonly body = new Container()
  /** Stays upright above the object (name, bars, statuses). */
  private readonly hud = new Container()
  private readonly selectionBox = new Graphics()
  private readonly turnRing = new Graphics()
  private sprite: Sprite | null = null
  private imageUrl: string | null = null
  obj: MapObject

  constructor(obj: MapObject, page: Page) {
    this.obj = obj
    // Skipped by the renderer when off screen.
    this.root.cullable = true
    this.root.addChild(this.turnRing, this.body, this.selectionBox, this.hud)
    this.root.label = obj.id
    this.update(obj, page)
  }

  /** Pins keep the same size on screen: the engine sets 1 / zoom. */
  private screenScale = 1

  setScreenScale(scale: number): void {
    this.screenScale = scale
    if (this.obj.kind === 'pin') this.root.scale.set(scale)
  }

  update(obj: MapObject, page: Page): void {
    this.obj = obj
    this.root.position.set(obj.x, obj.y)
    this.root.scale.set(obj.kind === 'pin' ? this.screenScale : 1)
    this.root.zIndex = stackZ(obj)
    this.body.rotation = (obj.rotation * Math.PI) / 180
    this.root.alpha = obj.layer === 'gm' ? 0.55 : 1
    this.drawBody(obj)
    this.drawHud(obj)
  }

  setPosition(x: number, y: number, rotation?: number): void {
    this.root.position.set(x, y)
    if (rotation !== undefined) this.body.rotation = (rotation * Math.PI) / 180
  }

  setSelected(selected: boolean, color: string): void {
    const g = this.selectionBox
    g.clear()
    if (!selected) return
    if (this.obj.kind === 'pin') {
      g.circle(0, -PIN_HEAD_Y, PIN_RADIUS + 5).stroke({ width: 2, color, alpha: 0.95 })
      return
    }
    const { w, h } = this.bounds()
    g.rect(-w / 2 - 3, -h / 2 - 3, w + 6, h + 6).stroke({ width: 2, color, alpha: 0.95 })
  }

  /** Ring under the token whose turn it is. */
  setTurn(current: boolean): void {
    const g = this.turnRing
    g.clear()
    if (!current) return
    const { w, h } = this.bounds()
    const r = Math.max(w, h) / 2 + 8
    g.circle(0, 0, r + 8).fill({ color: canvasColors.turn, alpha: 0.22 })
    g.circle(0, 0, r).stroke({ width: 6, color: canvasColors.turn, alpha: 0.95 })
  }

  /** Local-space bounds used for selection and hit testing. */
  bounds(): { w: number; h: number } {
    const o = this.obj
    if (o.kind === 'template') {
      const size = o.props.size ?? 0
      return { w: size * 2, h: size * 2 }
    }
    return { w: o.width, h: o.height }
  }

  destroy(): void {
    this.root.destroy({ children: true })
  }

  // --- Body -------------------------------------------------------------------

  private drawBody(o: MapObject): void {
    switch (o.kind) {
      case 'token':
      case 'image':
        return this.drawImageLike(o)
      case 'path':
        return this.drawPath(o)
      case 'text':
        return this.drawText(o)
      case 'template':
        return this.drawTemplate(o)
      case 'pin':
        return this.drawPin(o)
    }
  }

  /** A map pin: a drop with its icon, the tip on the pinned point. Screen pixels (see setScreenScale). */
  private drawPin(o: MapObject): void {
    this.clearBody()
    const color = o.props.color ?? canvasColors.accent
    const r = PIN_RADIUS
    const cy = -PIN_HEAD_Y
    const shadow = new Graphics().ellipse(0, 0, r * 0.55, r * 0.22).fill({ color: canvasColors.outline, alpha: 0.35 })
    const drop = new Graphics()
      .moveTo(0, 0)
      .lineTo(-r * 0.72, cy + r * 0.7)
      .arc(0, cy, r, Math.PI * 0.75, Math.PI * 0.25)
      .closePath()
      .fill(color)
      .stroke({ width: 2, color: canvasColors.tokenBorder, alpha: 0.9 })
    const icon = new Text({ text: o.props.icon || '📍', style: { fontSize: r * 1.05 }, resolution: TEXT_RESOLUTION })
    icon.anchor.set(0.5)
    icon.position.set(0, cy)
    this.body.addChild(shadow, drop, icon)
  }

  private clearBody(): void {
    for (const child of this.body.removeChildren()) {
      if (child !== this.sprite) child.destroy()
    }
  }

  private drawImageLike(o: MapObject): void {
    const url: string | undefined = o.props.image
    this.clearBody()
    if (url) {
      if (!this.sprite) this.sprite = new Sprite(Texture.EMPTY)
      const sprite = this.sprite
      sprite.anchor.set(0.5)
      sprite.width = o.width
      sprite.height = o.height
      this.body.addChild(sprite)
      if (url !== this.imageUrl) {
        this.imageUrl = url
        sprite.visible = true
        Assets.load<Texture>(url)
          .then((tex) => {
            if (this.imageUrl !== url || sprite.destroyed) return
            const tiled = tilesOf(url, tex)
            if (tiled) return this.showTiles(tiled)
            sprite.texture = tex
            sprite.width = this.obj.width
            sprite.height = this.obj.height
          })
          .catch(() => {})
      } else if (tileCache.has(url)) {
        this.showTiles(tileCache.get(url)!)
      }
      return
    }
    this.sprite?.destroy()
    this.sprite = null
    this.imageUrl = null
    if (o.props.shape === 'card') return this.drawPlainCard(o)
    const r = Math.min(o.width, o.height) / 2
    const disc = new Graphics()
      .ellipse(0, 0, o.width / 2, o.height / 2)
      .fill(o.props.color ?? DEFAULT_TOKEN_COLOR)
      .stroke({ width: Math.max(2, r * 0.08), color: canvasColors.tokenBorder, alpha: 0.9 })
    const label = new Text({
      text: initials(o.props.name),
      style: { ...LABEL_STYLE, fontSize: Math.max(10, r * 0.7), stroke: undefined },
      resolution: TEXT_RESOLUTION,
    })
    label.anchor.set(0.5)
    this.body.addChild(disc, label)
  }

  /** A picture too big for the GPU, drawn as tiles scaled to the object's size. */
  private showTiles(t: { width: number; height: number; tiles: { x: number; y: number; tex: Texture }[] }): void {
    if (this.sprite) this.sprite.visible = false
    const o = this.obj
    const group = new Container({ label: 'tiles' })
    for (const tile of t.tiles) {
      const s = new Sprite(tile.tex)
      s.position.set(tile.x, tile.y)
      group.addChild(s)
    }
    group.scale.set(o.width / t.width, o.height / t.height)
    group.position.set(-o.width / 2, -o.height / 2)
    this.body.addChild(group)
  }

  /** A card without a picture: its name on a light card, or a plain back when face down. */
  private drawPlainCard(o: MapObject): void {
    const faceDown = o.props.side === 1 || !o.props.name
    const radius = Math.min(o.width, o.height) * 0.08
    const card = new Graphics()
      .roundRect(-o.width / 2, -o.height / 2, o.width, o.height, radius)
      .fill(faceDown ? canvasColors.cardBack : canvasColors.cardFace)
      .stroke({ width: Math.max(1.5, o.width * 0.03), color: canvasColors.tokenBorder, alpha: 0.9 })
    this.body.addChild(card)
    if (faceDown) return
    const label = new Text({
      text: o.props.name,
      style: {
        ...LABEL_STYLE,
        fill: canvasColors.cardInk,
        stroke: undefined,
        fontSize: Math.max(8, o.width * 0.16),
        wordWrap: true,
        wordWrapWidth: o.width * 0.85,
        align: 'center',
      },
      resolution: TEXT_RESOLUTION,
    })
    label.anchor.set(0.5)
    this.body.addChild(label)
  }

  private drawPath(o: MapObject): void {
    this.clearBody()
    const p = o.props
    const g = new Graphics()
    const w = o.width
    const h = o.height
    switch (p.shape) {
      case 'rect':
        g.rect(-w / 2, -h / 2, w, h)
        break
      case 'ellipse':
        g.ellipse(0, 0, w / 2, h / 2)
        break
      default: {
        const pts: number[] = p.points ?? []
        if (pts.length >= 2) {
          g.moveTo(pts[0], pts[1])
          for (let i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1])
          if (p.shape === 'polygon') g.closePath()
        }
      }
    }
    if (p.fill) g.fill({ color: p.fill, alpha: 0.5 })
    g.stroke({ width: p.stroke_width ?? 3, color: p.stroke ?? DEFAULT_DRAW_COLOR, cap: 'round', join: 'round' })
    this.body.addChild(g)
  }

  private drawText(o: MapObject): void {
    this.clearBody()
    const t = new Text({
      text: o.props.text ?? '',
      style: {
        fill: o.props.color ?? DEFAULT_DRAW_COLOR,
        fontSize: o.props.font_size ?? 24,
        fontFamily: 'Inter, system-ui, sans-serif',
        fontWeight: '600',
        wordWrap: false,
      },
      resolution: TEXT_RESOLUTION,
    })
    t.anchor.set(0.5)
    this.body.addChild(t)
    // Keep geometry in sync with the rendered text for selection.
    this.obj = { ...o, width: Math.max(10, t.width), height: Math.max(10, t.height) }
  }

  private drawTemplate(o: MapObject): void {
    this.clearBody()
    const p = o.props
    const size: number = p.size ?? 0
    const color: string = p.color ?? canvasColors.template
    const g = new Graphics()
    switch (p.shape) {
      case 'circle':
        g.circle(0, 0, size)
        break
      case 'square':
        g.rect(-size, -size, size * 2, size * 2)
        break
      case 'line': {
        const half = (p.width ?? 70) / 2
        g.rect(0, -half, size, half * 2)
        break
      }
      case 'cone': {
        // 5e cone: width at distance d equals d (53.13° total angle).
        const half = ((p.angle ?? 53.13) / 2) * (Math.PI / 180)
        g.moveTo(0, 0)
        g.lineTo(size * Math.cos(-half), size * Math.sin(-half))
        g.arc(0, 0, size, -half, half)
        g.closePath()
        break
      }
    }
    g.fill({ color, alpha: 0.28 }).stroke({ width: 2, color, alpha: 0.9 })
    this.body.addChild(g)
  }

  // --- HUD --------------------------------------------------------------------

  private drawHud(o: MapObject): void {
    for (const child of this.hud.removeChildren()) child.destroy()
    if (o.kind === 'pin') {
      if (o.props.title && o.props.show_title !== false) {
        const label = new Text({ text: o.props.title, style: LABEL_STYLE, resolution: TEXT_RESOLUTION })
        label.anchor.set(0.5, 0)
        label.position.set(0, 4)
        this.hud.addChild(label)
      }
      return
    }
    if (o.kind !== 'token') return
    const w = o.width
    const h = o.height

    // Thin bars inside the bottom of the token box, HP lowest, the next one above it.
    const thick = Math.max(2, Math.min(w, h) * 0.035)
    const barW = w * 0.56
    let y = h / 2 - thick - Math.max(3, h * 0.05)
    BARS.forEach(({ key, color }) => {
      const bar = o.props[key] as Bar | undefined
      if (!bar || bar.max == null || bar.max <= 0) return
      const frac = Math.max(0, Math.min(1, (bar.value ?? 0) / bar.max))
      const g = new Graphics()
        .roundRect(-barW / 2, y, barW, thick, thick / 2)
        .fill({ color: canvasColors.barTrack, alpha: 0.7 })
      if (frac > 0) g.roundRect(-barW / 2, y, barW * frac, thick, thick / 2).fill(color)
      this.hud.addChild(g)
      y -= thick + 2
    })

    // Status markers along the top-right edge.
    const statuses = ((o.props.statuses ?? []) as string[]).filter((id) => STATUS_ICON.has(id))
    statuses.slice(0, 8).forEach((id, i) => {
      const icon = new Text({ text: STATUS_ICON.get(id)!, style: { fontSize: 14 } })
      icon.anchor.set(0.5)
      icon.position.set(w / 2 - 8 - (i % 4) * 15, -h / 2 + 8 + Math.floor(i / 4) * 15)
      this.hud.addChild(icon)
    })

    // Name plate.
    if (o.props.name && o.props.show_name !== false) {
      const label = new Text({ text: o.props.name, style: LABEL_STYLE, resolution: TEXT_RESOLUTION })
      label.anchor.set(0.5, 0)
      label.position.set(0, h / 2 + 3)
      this.hud.addChild(label)
    }
  }
}
