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
  private sprite: Sprite | null = null
  private imageUrl: string | null = null
  obj: MapObject

  constructor(obj: MapObject, page: Page) {
    this.obj = obj
    this.root.addChild(this.body, this.selectionBox, this.hud)
    this.root.label = obj.id
    this.update(obj, page)
  }

  update(obj: MapObject, page: Page): void {
    this.obj = obj
    this.root.position.set(obj.x, obj.y)
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
      this.body.addChild(sprite)
      if (url !== this.imageUrl) {
        this.imageUrl = url
        Assets.load<Texture>(url)
          .then((tex) => {
            if (this.imageUrl !== url || sprite.destroyed) return
            sprite.texture = tex
            sprite.width = this.obj.width
            sprite.height = this.obj.height
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

  // --- HUD --------------------------------------------------------------------

  private drawHud(o: MapObject): void {
    for (const child of this.hud.removeChildren()) child.destroy()
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
