// Grid distances for the rules, mirror of backend/app/rules5e/geometry.py: a creature fills
// the cells under its token; distances are counted 5e-style (every diagonal one cell, 5 ft)
// between the closest cells, so adjacent creatures are 5 ft apart. Keep the two in sync.
import type { MapObject } from '../net/protocol'

export const FEET_PER_CELL = 5

type Box = Pick<MapObject, 'x' | 'y' | 'width' | 'height'>

function bounds(b: Box, cell: number): [number, number, number, number] {
  const hw = Math.max(b.width, cell * 0.5) / 2
  const hh = Math.max(b.height, cell * 0.5) / 2
  const eps = cell * 0.01
  return [
    Math.floor((b.x - hw + eps) / cell),
    Math.floor((b.y - hh + eps) / cell),
    Math.floor((b.x + hw - eps) / cell),
    Math.floor((b.y + hh - eps) / cell),
  ]
}

/** Empty cells between two creatures (0 = adjacent or overlapping). */
export function gap(a: Box, b: Box, cell: number): number {
  const [ax0, ay0, ax1, ay1] = bounds(a, cell)
  const [bx0, by0, bx1, by1] = bounds(b, cell)
  const dx = Math.max(bx0 - ax1, ax0 - bx1, 0)
  const dy = Math.max(by0 - ay1, ay0 - by1, 0)
  return Math.max(dx, dy, 1) - 1
}

/** Feet between two creatures: 5 when adjacent. */
export function distanceFt(a: Box, b: Box, cell: number): number {
  return (gap(a, b, cell) + 1) * FEET_PER_CELL
}

/** Feet in the game's units: 5 ft = 1.5 m. */
export function feetLabel(feet: number, metric: boolean): string {
  return metric ? `${Number((feet * 0.3).toFixed(1))} m` : `${feet} ft`
}
