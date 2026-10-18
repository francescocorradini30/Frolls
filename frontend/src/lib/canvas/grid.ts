import { Graphics } from 'pixi.js'
import type { Page } from '../net/protocol'

const SQRT3 = Math.sqrt(3)

export interface Point {
  x: number
  y: number
}

export function pagePixelSize(page: Page): { w: number; h: number } {
  return { w: page.width * page.grid_size, h: page.height * page.grid_size }
}

/** Draw the page background and grid lines. */
export function drawGrid(g: Graphics, page: Page): void {
  const { w, h } = pagePixelSize(page)
  const s = page.grid_size
  g.clear()
  g.rect(0, 0, w, h).fill(page.background_color)
  if (page.grid_type === 'none') return

  if (page.grid_type === 'square') {
    for (let x = 0; x <= w; x += s) g.moveTo(x, 0).lineTo(x, h)
    for (let y = 0; y <= h; y += s) g.moveTo(0, y).lineTo(w, y)
  } else {
    const r = s / SQRT3
    if (page.grid_type === 'hex_h') {
      // Pointy-top hexes in offset rows.
      const rowH = 1.5 * r
      for (let row = 0; row * rowH <= h + r; row++) {
        for (let col = -1; col * s <= w + s; col++) {
          const cx = col * s + (row % 2 ? s / 2 : 0)
          const cy = row * rowH
          hexPath(g, cx, cy, r, 30)
        }
      }
    } else {
      // Flat-top hexes in offset columns.
      const colW = 1.5 * r
      for (let col = 0; col * colW <= w + r; col++) {
        for (let row = -1; row * s <= h + s; row++) {
          const cx = col * colW
          const cy = row * s + (col % 2 ? s / 2 : 0)
          hexPath(g, cx, cy, r, 0)
        }
      }
    }
  }
  g.stroke({ width: 1, color: page.grid_color, alpha: page.grid_opacity, pixelLine: true })
}

function hexPath(g: Graphics, cx: number, cy: number, r: number, startDeg: number): void {
  for (let i = 0; i <= 6; i++) {
    const a = ((startDeg + i * 60) * Math.PI) / 180
    const x = cx + r * Math.cos(a)
    const y = cy + r * Math.sin(a)
    if (i === 0) g.moveTo(x, y)
    else g.lineTo(x, y)
  }
}

/**
 * Snap an object centre to the grid. Objects with an even number of cells
 * snap to grid intersections, odd ones to cell centres (as on a real mat).
 */
export function snapCenter(page: Page, p: Point, width: number, height: number): Point {
  const s = page.grid_size
  if (page.grid_type === 'none') return p
  if (page.grid_type === 'square') {
    return { x: snapAxis(p.x, s, width), y: snapAxis(p.y, s, height) }
  }
  return hexCenter(page, p)
}

function snapAxis(v: number, s: number, size: number): number {
  const cells = Math.max(1, Math.round(size / s))
  const offset = cells % 2 ? s / 2 : 0
  return Math.round((v - offset) / s) * s + offset
}

/** Snap a size to whole cells (min one cell). */
export function snapSize(page: Page, size: number): number {
  const s = page.grid_size
  return Math.max(1, Math.round(size / s)) * s
}

export function snapPoint(page: Page, p: Point): Point {
  if (page.grid_type === 'none') return p
  if (page.grid_type === 'square') {
    const s = page.grid_size
    return { x: Math.round(p.x / s) * s, y: Math.round(p.y / s) * s }
  }
  return hexCenter(page, p)
}

// --- Hex math (axial coordinates) ---------------------------------------------

interface Axial {
  q: number
  r: number
}

function hexRadius(page: Page): number {
  return page.grid_size / SQRT3
}

/** Offset-grid hex nearest to a point, as axial coords. */
export function pixelToHex(page: Page, p: Point): Axial {
  const size = hexRadius(page)
  if (page.grid_type === 'hex_h') {
    // Rows are offset by half a hex: convert via the odd-r layout.
    const row = Math.round(p.y / (1.5 * size))
    const col = Math.round((p.x - (row % 2 ? page.grid_size / 2 : 0)) / page.grid_size)
    return refineHex(page, p, offsetToAxial(page, col, row))
  }
  const col = Math.round(p.x / (1.5 * size))
  const row = Math.round((p.y - (col % 2 ? page.grid_size / 2 : 0)) / page.grid_size)
  return refineHex(page, p, offsetToAxial(page, col, row))
}

function offsetToAxial(page: Page, col: number, row: number): Axial {
  if (page.grid_type === 'hex_h') return { q: col - (row - (row & 1)) / 2, r: row }
  return { q: col, r: row - (col - (col & 1)) / 2 }
}

function hexToPixel(page: Page, h: Axial): Point {
  const size = hexRadius(page)
  if (page.grid_type === 'hex_h') {
    return { x: size * SQRT3 * (h.q + h.r / 2), y: size * 1.5 * h.r }
  }
  return { x: size * 1.5 * h.q, y: size * SQRT3 * (h.r + h.q / 2) }
}

/** The offset estimate can be off by one near edges: pick the closest neighbour. */
function refineHex(page: Page, p: Point, guess: Axial): Axial {
  let best = guess
  let bestD = Infinity
  for (const [dq, dr] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, -1], [-1, 1]]) {
    const cand = { q: guess.q + dq, r: guess.r + dr }
    const c = hexToPixel(page, cand)
    const d = (c.x - p.x) ** 2 + (c.y - p.y) ** 2
    if (d < bestD) {
      bestD = d
      best = cand
    }
  }
  return best
}

function hexCenter(page: Page, p: Point): Point {
  return hexToPixel(page, pixelToHex(page, p))
}

export function hexDistance(page: Page, a: Point, b: Point): number {
  const ha = pixelToHex(page, a)
  const hb = pixelToHex(page, b)
  const dq = ha.q - hb.q
  const dr = ha.r - hb.r
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2
}
