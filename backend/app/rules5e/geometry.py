"""Positions on the grid, for the rules: distances, reach, flanking (SRD 5.2).

A creature fills the cells under its token. Distances are counted in cells the 5e way
(every diagonal is one cell, 5 feet) between the closest cells of the two creatures, so
two adjacent creatures are 5 feet apart. Pure functions on token boxes, no game imports.
"""

from dataclasses import dataclass

FEET_PER_CELL = 5


@dataclass(frozen=True)
class Box:
    """A token: centre and size in page pixels."""

    x: float
    y: float
    width: float
    height: float

    def bounds(self, cell: float) -> tuple[int, int, int, int]:
        """First and last column and row the token covers (a token smaller than a cell
        still fills the cell it is in)."""
        half_w, half_h = max(self.width, cell * 0.5) / 2, max(self.height, cell * 0.5) / 2
        eps = cell * 0.01
        return (
            int((self.x - half_w + eps) // cell),
            int((self.y - half_h + eps) // cell),
            int((self.x + half_w - eps) // cell),
            int((self.y + half_h - eps) // cell),
        )


def gap(a: Box, b: Box, cell: float) -> int:
    """Empty cells between two creatures (0 = adjacent or overlapping)."""
    ax0, ay0, ax1, ay1 = a.bounds(cell)
    bx0, by0, bx1, by1 = b.bounds(cell)
    dx = max(bx0 - ax1, ax0 - bx1, 0)
    dy = max(by0 - ay1, ay0 - by1, 0)
    return max(dx, dy, 1) - 1


def distance_ft(a: Box, b: Box, cell: float) -> int:
    """Feet between two creatures: 5 when adjacent."""
    return (gap(a, b, cell) + 1) * FEET_PER_CELL


def within(a: Box, b: Box, cell: float, feet: int) -> bool:
    return distance_ft(a, b, cell) <= max(feet, FEET_PER_CELL)


def _side(of: Box, around: Box, cell: float) -> tuple[int, int]:
    """Which side of `around` the creature `of` is on: -1 / 0 / +1 on each axis."""
    ox0, oy0, ox1, oy1 = of.bounds(cell)
    ax0, ay0, ax1, ay1 = around.bounds(cell)
    sx = -1 if ox1 < ax0 else 1 if ox0 > ax1 else 0
    sy = -1 if oy1 < ay0 else 1 if oy0 > ay1 else 0
    return sx, sy


def flanked(attacker: Box, ally: Box, target: Box, cell: float) -> bool:
    """Optional flanking rule: attacker and ally both next to the target, on opposite
    sides or at opposite corners of its space."""
    if gap(attacker, target, cell) or gap(ally, target, cell):
        return False
    a = _side(attacker, target, cell)
    b = _side(ally, target, cell)
    return a != (0, 0) and a == (-b[0], -b[1])


def covered(box: Box, cx: float, cy: float, radius: float, cell: float) -> bool:
    """Whether any cell of the creature is inside a circle area (whole cells, centre of the
    cell inside the circle), as the circle tool draws it."""
    x0, y0, x1, y1 = box.bounds(cell)
    for col in range(x0, x1 + 1):
        for row in range(y0, y1 + 1):
            px, py = (col + 0.5) * cell, (row + 0.5) * cell
            if (px - cx) ** 2 + (py - cy) ** 2 <= radius**2:
                return True
    return False
