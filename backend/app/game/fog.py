"""Manual fog of war: a page starts dark; the GM reveals and hides areas, in order.

`fog` on a page: {"enabled": bool, "ops": [{"mode": "reveal"|"hide", "shape": "rect"|"poly",
"points": [x1, y1, x2, y2, …]}]}. For a rectangle the points are two opposite corners.
The last area that contains a point decides whether it is visible.
"""

from typing import Any

MAX_OPS = 1000


def contains(op: dict[str, Any], x: float, y: float) -> bool:
    pts = op["points"]
    if op["shape"] == "rect":
        x1, y1, x2, y2 = pts[:4]
        return min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)
    # Polygon: even-odd ray casting.
    inside = False
    n = len(pts) // 2
    for i in range(n):
        ax, ay = pts[2 * i], pts[2 * i + 1]
        bx, by = pts[2 * ((i + 1) % n)], pts[2 * ((i + 1) % n) + 1]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def visible(fog: dict[str, Any] | None, x: float, y: float) -> bool:
    """Whether a point of the page is out of the fog."""
    if not fog or not fog.get("enabled"):
        return True
    for op in reversed(fog.get("ops") or []):
        if contains(op, x, y):
            return op["mode"] == "reveal"
    return False


def default() -> dict[str, Any]:
    return {"enabled": False, "ops": []}
