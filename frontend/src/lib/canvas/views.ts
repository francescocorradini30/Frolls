import { Assets, Container, Graphics, Sprite, Text, Texture } from 'pixi.js'
import type { Bar, MapObject, Page } from '../net/protocol'
import { initials } from '../util/ids'
import { AURA_COLORS, BAR_COLORS, canvasColors, DEFAULT_DRAW_COLOR, DEFAULT_TOKEN_COLOR } from '../theme'
import { STATUS_ICON } from '../util/statuses'
import { unitsToPx } from './measure'

// Text is rasterised once; a higher resolution keeps it crisp when zooming in.
const TEXT_RESOLUTION = 3

const LABEL_STYLE = {
  fill: canvasColors.label,
  fontSize: 13,
  fontFamily: 'Inter, system-ui, sans-serif',
  fontWeight: '600' as const,
  stroke: { color: canvasColors.outline, width: 3 },
}

/** One renderable map object. Rebuilds itself from the MapObject on update. */
export class ObjectView {
  readonly root = new Container()
  /** Rotates/scales with the object (image, shape). */
  private readonly body = new Container()
  /** Stays upright above the object (name, bars, statuses). */
  private readonly hud = new Container()
  private readonly auras = new Graphics()
  private readonly selectionBox = new Graphics()
  private sprite: Sprite | null = null
  private imageUrl: string | null = null
  obj: MapObject

  constructor(obj: MapObject, page: Page) {
    this.obj = obj
    this.root.addChild(this.auras, this.body, this.selectionBox, this.hud)
    this.root.label = obj.id
    this.update(obj, page)
  }

  update(obj: MapObject, page: Page): void {
    this.obj = obj
    this.root.position.set(obj.x, obj.y)
    this.root.zIndex = obj.z
    this.body.rotation = (obj.rotation * Math.PI) / 180
    this.root.alpha = obj.layer === 'gm' ? 0.55 : 1
    this.drawBody(obj)
    this.drawAuras(obj, page)
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
    const { w, h } = this.bounds()
    g.rect(-w / 2 - 3, -h / 2 - 3, w + 6, h + 6).stroke({ width: 2, color, alpha: 0.95 })
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
    }
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
      sprite.scale.x = Math.abs(sprite.scale.x) * (o.props.flip_h ? -1 : 1)
      sprite.scale.y = Math.abs(sprite.scale.y) * (o.props.flip_v ? -1 : 1)
      this.body.addChild(sprite)
      if (url !== this.imageUrl) {
        this.imageUrl = url
        Assets.load<Texture>(url)
          .then((tex) => {
            if (this.imageUrl !== url || sprite.destroyed) return
            sprite.texture = tex
            sprite.width = this.obj.width
            sprite.height = this.obj.height
            sprite.scale.x = Math.abs(sprite.scale.x) * (this.obj.props.flip_h ? -1 : 1)
            sprite.scale.y = Math.abs(sprite.scale.y) * (this.obj.props.flip_v ? -1 : 1)
          })
          .catch(() => {})
      }
      return
    }
    this.sprite?.destroy()
    this.sprite = null
    this.imageUrl = null
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

  // --- Auras & HUD ------------------------------------------------------------

  private drawAuras(o: MapObject, page: Page): void {
    const g = this.auras
    g.clear()
    if (o.kind !== 'token') return
    for (const key of ['aura1', 'aura2'] as const) {
      const aura = o.props[key]
      if (!aura || !aura.radius) continue
      const r = unitsToPx(page, aura.radius) + Math.max(o.width, o.height) / 2
      if (aura.square) g.rect(-r, -r, r * 2, r * 2)
      else g.circle(0, 0, r)
      g.fill({ color: aura.color ?? AURA_COLORS[0], alpha: 0.18 })
      g.stroke({ width: 1.5, color: aura.color ?? AURA_COLORS[0], alpha: 0.6 })
    }
  }

  private drawHud(o: MapObject): void {
    for (const child of this.hud.removeChildren()) child.destroy()
    if (o.kind !== 'token') return
    const w = o.width
    const h = o.height

    // Bars stacked above the token.
    const bars = [o.props.bar1, o.props.bar2, o.props.bar3] as (Bar | undefined)[]
    let y = -h / 2 - 6
    bars.forEach((bar, i) => {
      if (!bar || bar.max == null || bar.max <= 0) return
      const frac = Math.max(0, Math.min(1, (bar.value ?? 0) / bar.max))
      const g = new Graphics()
        .roundRect(-w / 2, y - 6, w, 6, 3)
        .fill({ color: canvasColors.barTrack, alpha: 0.6 })
        .roundRect(-w / 2, y - 6, w * frac, 6, 3)
        .fill(BAR_COLORS[i])
      this.hud.addChild(g)
      y -= 8
    })

    // Status markers along the top-right edge.
    const statuses: string[] = o.props.statuses ?? []
    statuses.slice(0, 8).forEach((id, i) => {
      const icon = new Text({ text: STATUS_ICON.get(id) ?? '•', style: { fontSize: 14 } })
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
