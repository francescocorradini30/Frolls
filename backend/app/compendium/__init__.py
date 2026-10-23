"""SRD 5.2 compendium: monsters and spells ready for Frolls sheets.

Data in `data/*.json`, made by scripts/import_srd.py. It includes material from the System
Reference Document 5.2 by Wizards of the Coast LLC, licensed CC-BY-4.0 (see ATTRIBUTION).
"""

import json
from fractions import Fraction
from functools import cache
from pathlib import Path
from typing import Any, Literal

DATA = Path(__file__).parent / "data"
Kind = Literal["monster", "spell"]

ATTRIBUTION = (
    "This work includes material from the System Reference Document 5.2 (“SRD 5.2”) by "
    "Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2 is "
    "licensed under the Creative Commons Attribution 4.0 International License, available at "
    "https://creativecommons.org/licenses/by/4.0/legalcode. Structured data from Open5e."
)


@cache
def entries(kind: Kind) -> dict[str, dict[str, Any]]:
    name = "monsters" if kind == "monster" else "spells"
    items = json.loads((DATA / f"{name}.json").read_text(encoding="utf8"))
    return {item["key"]: item for item in items}


def summary(kind: Kind, item: dict[str, Any]) -> dict[str, Any]:
    """What a result list shows."""
    if kind == "monster":
        return {
            "key": item["key"],
            "name": item["name"],
            "cr": item["cr"],
            "type": item["type"],
            "size": item["size"],
        }
    return {
        "key": item["key"],
        "name": item["name"],
        "level": item["level"],
        "school": item["school"],
    }


def search(
    kind: Kind, query: str = "", limit: int = 60, cr: str | None = None, level: int | None = None
) -> list[dict[str, Any]]:
    q = query.strip().lower()
    found = []
    for item in entries(kind).values():
        if q and q not in item["name"].lower() and q not in item.get("type", "").lower():
            continue
        if kind == "monster" and cr and item["cr"] != cr:
            continue
        if kind == "spell" and level is not None and item["level"] != level:
            continue
        found.append(item)
    if kind == "monster":
        found.sort(key=lambda i: (Fraction(i["cr"]), i["name"]))
    else:
        found.sort(key=lambda i: (i["level"], i["name"]))
    return [summary(kind, i) for i in found[:limit]]


def get(kind: Kind, key: str) -> dict[str, Any] | None:
    return entries(kind).get(key)
