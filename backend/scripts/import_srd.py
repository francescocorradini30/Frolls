"""Download the SRD 5.2 monsters and spells and convert them to Frolls sheets.

Source: the Open5e API (document "srd-2024"), which structures the System Reference
Document 5.2 by Wizards of the Coast, licensed CC-BY-4.0. Run it once; the result is saved
in app/compendium/data and committed.

    .venv/Scripts/python scripts/import_srd.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

API = "https://api.open5e.com/v2"
OUT = Path(__file__).resolve().parent.parent / "app" / "compendium" / "data"
ABILITY = {
    "strength": "str",
    "dexterity": "dex",
    "constitution": "con",
    "intelligence": "int",
    "wisdom": "wis",
    "charisma": "cha",
}
# Spells whose effect Frolls applies by itself (presets of app/rules5e/effects.py).
SPELL_EFFECTS = {
    "Bless": "bless",
    "Bane": "bane",
    "Guidance": "guidance",
    "Resistance": "resistance",
    "Shield of Faith": "shield_of_faith",
    "Haste": "haste",
    "Slow": "slow",
    "Hold Person": "hold_person",
    "Faerie Fire": "faerie_fire",
    "Invisibility": "invisibility",
    "Shield": "shield",
}
SAVE_RE = re.compile(
    r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) Saving Throw: DC (\d+)"
)
DAMAGE_RE = re.compile(r"\d+ \((\d+d\d+(?: ?[+−-] ?\d+)?)\) (\w+) damage", re.IGNORECASE)


def fetch_all(path: str) -> list[dict]:
    url = f"{API}/{path}/?document__key=srd-2024&limit=100"
    items: list[dict] = []
    while url:
        # curl: it uses the system certificates, which Python's bundle may lack.
        raw = subprocess.run(["curl", "-sSf", "-m", "60", url], capture_output=True, check=True)
        page = json.loads(raw.stdout)
        items += page["results"]
        url = page.get("next")
        print(f"{path}: {len(items)}/{page['count']}", file=sys.stderr)
    return items


def cr_text(value: float) -> str:
    return {0.125: "1/8", 0.25: "1/4", 0.5: "1/2"}.get(value, str(int(value)))


def proficiency(cr: float) -> int:
    return 2 + max(0, (int(cr) - 1) // 4) if cr >= 1 else 2


def formula(count: int | None, die: str | None, bonus: int | None) -> str:
    if not count or not die:
        return str(bonus or 0)
    text = f"{count}{die.lower()}"
    return f"{text}{bonus:+d}" if bonus else text


def monster(m: dict) -> dict:
    cr = float(m["challenge_rating"])
    prof = proficiency(cr)
    scores = {ABILITY[k]: max(1, v) for k, v in m["ability_scores"].items()}
    mods = {ABILITY[k]: v for k, v in m["modifiers"].items()}
    saves = [
        ABILITY[k] for k, v in (m.get("saving_throws") or {}).items() if v != m["modifiers"][k]
    ]
    skills = {}
    for skill, bonus in (m.get("skill_bonuses") or {}).items():
        ability = {
            "acrobatics": "dex", "animal_handling": "wis", "arcana": "int", "athletics": "str",
            "deception": "cha", "history": "int", "insight": "wis", "intimidation": "cha",
            "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
            "performance": "cha", "persuasion": "cha", "religion": "int", "sleight_of_hand": "dex",
            "stealth": "dex", "survival": "wis",
        }[skill]  # fmt: skip
        skills[skill] = 2 if bonus - mods[ability] >= 2 * prof else 1

    attacks = []
    text: list[str] = []
    for action in sorted(
        m.get("actions") or [], key=lambda a: (a["action_type"], a["order_in_statblock"])
    ):
        kind = action["action_type"].replace("_", " ").title()
        text.append(f"{kind} — {action['name']}. {action['desc']}")
        for i, att in enumerate(action.get("attacks") or []):
            dtype = att.get("damage_type") or att.get("extra_damage_type") or {}
            reach = f"reach {att['reach']} ft" if att.get("reach") else ""
            rng = f"range {att['range']}/{att['long_range']} ft" if att.get("range") else ""
            attacks.append(
                {
                    "id": f"{action['name']}-{i}"[:36],
                    "name": action["name"],
                    "kind": "attack",
                    "ability": "none",
                    "to_hit": att.get("to_hit_mod"),
                    "damage": formula(
                        att.get("damage_die_count"),
                        att.get("damage_die_type"),
                        att.get("damage_bonus"),
                    ),
                    "damage_type": (dtype.get("key") or "")[:120],
                    "add_modifier": False,
                    "range": " · ".join(x for x in (reach, rng) if x),
                    "notes": action["desc"][:2000],
                }
            )
        if not action.get("attacks"):
            save = SAVE_RE.search(action["desc"])
            damage = DAMAGE_RE.search(action["desc"])
            if save and damage:
                attacks.append(
                    {
                        "id": f"{action['name']}-save"[:36],
                        "name": action["name"],
                        "kind": "save",
                        "ability": "none",
                        "save": ABILITY[save.group(1).lower()],
                        "dc": int(save.group(2)),
                        "damage": damage.group(1).replace(" ", "").replace("−", "-"),
                        "damage_type": damage.group(2).lower(),
                        "add_modifier": False,
                        "half_on_save": "Success: Half damage" in action["desc"],
                        "notes": action["desc"][:2000],
                    }
                )
    traits = [f"{t['name']}. {t['desc']}" for t in m.get("traits") or []]
    ri = m.get("resistances_and_immunities") or {}
    keys = lambda items: [i["key"] if isinstance(i, dict) else str(i) for i in items or []][:20]  # noqa: E731
    header = f"{m['size']['name']} {m['type']['name']}, {m.get('alignment') or ''}".strip(", ")
    dice = m.get("hit_dice") or "—"
    armor = m.get("armor_detail") or ""
    hp_line = f"HP {m['hit_points']} ({dice}) · AC {m['armor_class']} {armor}".strip()
    langs = (m.get("languages") or {}).get("as_string") or ""
    lang_line = f"Languages: {langs}" if langs else ""
    features = "\n\n".join(x for x in [header, hp_line, lang_line, *traits, *text] if x)
    sheet = {
        "kind": "npc",
        "source": m["key"],
        "cr": cr_text(cr),
        "creature_type": m["type"]["name"].lower(),
        "size": m["size"]["key"]
        if m["size"]["key"] in ("tiny", "small", "medium", "large", "huge", "gargantuan")
        else "medium",
        "abilities": scores,
        "save_proficiencies": saves,
        "skills": skills,
        "ac": m["armor_class"],
        "speed": int((m.get("speed") or {}).get("walk") or 30),
        "initiative_bonus": (m.get("initiative_bonus") or mods["dex"]) - mods["dex"],
        "hp": {"current": m["hit_points"], "max": m["hit_points"], "temp": 0},
        "attacks": attacks[:50],
        "resistances": keys(ri.get("damage_resistances")),
        "immunities": keys(ri.get("damage_immunities")),
        "vulnerabilities": keys(ri.get("damage_vulnerabilities")),
        "condition_immunities": keys(ri.get("condition_immunities")),
        "features": features[:20000],
    }
    return {
        "key": m["key"],
        "name": m["name"],
        "cr": cr_text(cr),
        "type": m["type"]["name"].lower(),
        "size": m["size"]["key"],
        "sheet": sheet,
    }


def upcast(s: dict) -> str:
    """Dice added per slot level above the spell's, from the next level's damage."""
    base = re.fullmatch(r"(\d+)d(\d+)", (s.get("damage_roll") or "").strip())
    nxt = next(
        (o for o in s.get("casting_options") or [] if o["type"] == f"slot_level_{s['level'] + 1}"),
        None,
    )
    if not base or not nxt or not nxt.get("damage_roll"):
        return ""
    up = re.fullmatch(r"(\d+)d(\d+)", nxt["damage_roll"].strip())
    if not up or up.group(2) != base.group(2) or int(up.group(1)) <= int(base.group(1)):
        return ""
    return f"{int(up.group(1)) - int(base.group(1))}d{base.group(2)}"


def heal_kind(desc: str) -> str:
    if "Temporary Hit Points" in desc and "gain" in desc:
        return "temp"
    return "healing" if "regains" in desc and "Hit Points" in desc else ""


def spell(s: dict) -> dict:
    desc = s["desc"] + (
        f"\n\nAt higher levels: {s['higher_level']}" if s.get("higher_level") else ""
    )
    save = ABILITY.get((s.get("saving_throw_ability") or "").lower())
    data = {
        "id": s["key"][:36],
        "name": s["name"],
        "level": s["level"],
        "prepared": True,
        "concentration": bool(s.get("concentration")),
        "ritual": bool(s.get("ritual")),
        "attack": bool(s.get("attack_roll")),
        "save": save,
        "half_on_save": "half as much damage" in s["desc"],
        "damage": (s.get("damage_roll") or "").replace(" ", "")[:80],
        "damage_type": ((s.get("damage_types") or [""])[0] or "")[:120],
        "upcast": upcast(s),
        "duration": (s.get("duration") or "")[:120],
        "description": desc[:4000],
        "effect": SPELL_EFFECTS.get(s["name"]),
        "heal": heal_kind(s["desc"]),
        "add_modifier": "plus your spellcasting ability modifier" in s["desc"],
    }
    return {
        "key": s["key"],
        "name": s["name"],
        "level": s["level"],
        "school": (s.get("school") or {}).get("name", ""),
        "classes": [c["name"] for c in s.get("classes") or []],
        "spell": data,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    monsters = sorted((monster(m) for m in fetch_all("creatures")), key=lambda x: x["name"])
    spells = sorted((spell(s) for s in fetch_all("spells")), key=lambda x: (x["level"], x["name"]))
    for name, items in (("monsters", monsters), ("spells", spells)):
        path = OUT / f"{name}.json"
        path.write_text(
            json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf8"
        )
        print(f"{path}: {len(items)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
