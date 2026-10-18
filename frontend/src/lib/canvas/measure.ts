import type { Page } from '../net/protocol'
import { hexDistance, type Point } from './grid'

/** Distance between two points in page units (e.g. feet), following the page rules. */
export function measure(page: Page, a: Point, b: Point): number {
  const s = page.grid_size
  if (page.grid_type === 'hex_h' || page.grid_type === 'hex_v') {
    return hexDistance(page, a, b) * page.scale_number
  }
  const dx = Math.abs(b.x - a.x) / s
  const dy = Math.abs(b.y - a.y) / s
  let cells: number
  if (page.grid_type === 'none' || page.diagonal_rule === 'euclid') {
    cells = Math.hypot(dx, dy)
  } else {
    const cx = Math.round(dx)
    const cy = Math.round(dy)
    switch (page.diagonal_rule) {
      case 'pf':
        // Every second diagonal counts double.
        cells = Math.max(cx, cy) + Math.floor(Math.min(cx, cy) / 2)
        break
      case 'manhattan':
        cells = cx + cy
        break
      default:
        cells = Math.max(cx, cy)
    }
  }
  return cells * page.scale_number
}

const distanceFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

export function formatDistance(page: Page, value: number): string {
  return `${distanceFormat.format(value)} ${page.scale_unit}`
}

/** Convert a distance in page units to pixels. */
export function unitsToPx(page: Page, units: number): number {
  return (units / page.scale_number) * page.grid_size
}
