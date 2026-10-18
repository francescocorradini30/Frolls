/**
 * Token stamping: frame an uploaded picture into a round token with a border, like a token maker. Pure canvas drawing, shared by the live preview and
 * the final PNG export.
 */

import { palette } from '../theme'

export const STAMP_SIZE = 512

export type StampBorder = 'none' | 'thin' | 'solid' | 'double' | 'bevel'

export interface StampOptions {
  border: StampBorder
  borderColor: string
  /** null = transparent behind the picture. */
  background: string | null
  /** Picture centre offset from the token centre, in output pixels. */
  x: number
  y: number
  /** 1 = the picture just covers the token. */
  zoom: number
  rotation: number
}

/** Border thickness as a fraction of the token size. */
const BORDER_WIDTH: Record<StampBorder, number> = {
  none: 0,
  thin: 0.025,
  solid: 0.055,
  double: 0.07,
  bevel: 0.075,
}

/** Scale at which the picture covers the token at zoom 1. */
export function coverScale(img: HTMLImageElement, size = STAMP_SIZE): number {
  return size / Math.min(img.naturalWidth, img.naturalHeight)
}

/**
 * Draw the token centred in a `ctx` of side `view` (>= size). With `preview`, the
 * part of the picture outside the frame is shown faded so it can be positioned.
 */
export function drawStamp(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  o: StampOptions,
  { size = STAMP_SIZE, view, preview = false }: { size?: number; view?: number; preview?: boolean } = {},
): void {
  view ??= size
  const k = size / STAMP_SIZE
  const c = view / 2
  const bw = BORDER_WIDTH[o.border] * size
  // The picture runs under half of the border, so no gap shows at the edge.
  const inner = size / 2 - bw / 2

  ctx.clearRect(0, 0, view, view)

  const picture = () => {
    const s = coverScale(img, size) * o.zoom
    ctx.save()
    ctx.translate(c + o.x * k, c + o.y * k)
    ctx.rotate((o.rotation * Math.PI) / 180)
    ctx.scale(s, s)
    ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
    ctx.restore()
  }

  if (preview) {
    ctx.globalAlpha = 0.28
    picture()
    ctx.globalAlpha = 1
  }

  ctx.save()
  circle(ctx, c, inner)
  ctx.clip()
  if (o.background) {
    ctx.fillStyle = o.background
    ctx.fillRect(0, 0, view, view)
  } else if (preview) {
    ctx.clearRect(0, 0, view, view)
  }
  picture()
  ctx.restore()

  drawBorder(ctx, o, c, size / 2, bw)
}

function circle(ctx: CanvasRenderingContext2D, c: number, r: number): void {
  ctx.beginPath()
  ctx.arc(c, c, r, 0, Math.PI * 2)
}

function ring(ctx: CanvasRenderingContext2D, c: number, r: number, width: number, style: string | CanvasGradient): void {
  circle(ctx, c, r)
  ctx.lineWidth = width
  ctx.strokeStyle = style
  ctx.stroke()
}

function drawBorder(ctx: CanvasRenderingContext2D, o: StampOptions, c: number, outer: number, bw: number): void {
  if (o.border === 'none' || bw <= 0) return
  const mid = outer - bw / 2
  const dark = mix(o.borderColor, palette.ink950, 0.55)
  const light = mix(o.borderColor, palette.cream, 0.55)

  if (o.border === 'double') {
    const band = bw * 0.36
    ring(ctx, c, outer - band / 2, band, o.borderColor)
    ring(ctx, c, outer - bw + band / 2, band, o.borderColor)
    ring(ctx, c, mid, bw - band * 2, dark)
  } else if (o.border === 'bevel') {
    // Metallic ring: light from the top-left, shade at the bottom-right.
    const g = ctx.createLinearGradient(c - outer, c - outer, c + outer, c + outer)
    g.addColorStop(0, light)
    g.addColorStop(0.45, o.borderColor)
    g.addColorStop(1, dark)
    ring(ctx, c, mid, bw, g)
    ring(ctx, c, mid, bw * 0.3, mix(o.borderColor, palette.cream, 0.2))
  } else {
    ring(ctx, c, mid, bw, o.borderColor)
  }
  // Thin dark edges keep the border readable on any map.
  const edge = Math.max(1, bw * 0.08)
  ring(ctx, c, outer - edge / 2, edge, dark)
  ring(ctx, c, outer - bw + edge / 2, edge, dark)
}

/** Mix two #rrggbb colours; t = 0 gives a, 1 gives b. */
function mix(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1, 7), 16)
  const pb = parseInt(b.slice(1, 7), 16)
  const ch = (p: number, shift: number) => (p >> shift) & 255
  const out = [16, 8, 0].map((s) => Math.round(ch(pa, s) * (1 - t) + ch(pb, s) * t))
  return `rgb(${out.join(' ')})`
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Could not read the image'))
    img.src = src
  })
}

/** Render the final token as a square PNG file. */
export async function exportStamp(img: HTMLImageElement, o: StampOptions, name: string): Promise<File> {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = STAMP_SIZE
  drawStamp(canvas.getContext('2d')!, img, o)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('Could not create the token image')
  return new File([blob], `${name.replace(/\.[^.]+$/, '') || 'token'}.png`, { type: 'image/png' })
}
