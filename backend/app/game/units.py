"""Measurement systems. The 5e metric convention rounds 5 ft to 1.5 m (one square)."""

from typing import Literal

Measurement = Literal["metric", "imperial"]

DEFAULT_MEASUREMENT: Measurement = "metric"

# Default page scale: one grid cell.
CELL_SCALE: dict[Measurement, tuple[float, str]] = {
    "metric": (1.5, "m"),
    "imperial": (5, "ft"),
}

# Unit -> (unit in the other system, factor). 5 ft = 1.5 m, 1 mi = 1.5 km.
CONVERSIONS: dict[Measurement, dict[str, tuple[str, float]]] = {
    "metric": {"ft": ("m", 0.3), "mi": ("km", 1.5)},
    "imperial": {"m": ("ft", 1 / 0.3), "km": ("mi", 1 / 1.5)},
}


def convert(value: float, factor: float) -> float:
    # Round away float noise (1.5 / 0.3 = 5.000000000000001).
    return round(value * factor, 2)
