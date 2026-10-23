"""Undo of combat actions by three-way merge.

An action changed a value from `before` to `after`; since then the game went on and the
value is now `current`. Undoing takes the action's change out of `current` instead of
restoring `before`, so an old hit can be undone after later healing:

- numbers move back by the action's difference (HP 20 → 11 by the hit, healed to 15 since:
  undo gives 24, clamped by the caller to the maximum);
- lists of objects with an `id` (effects): the ones the action added go, the ones it
  removed come back;
- lists of strings (statuses): the same, as sets;
- dicts recurse key by key;
- anything else goes back to `before` only if nobody changed it since, otherwise it stays
  and a conflict is reported.

Redo is the same merge with `before` and `after` swapped. Pure functions, no game imports.
"""

from typing import Any


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _id_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) and "id" in x for x in v)


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _empty_like(v: Any) -> Any:
    return {} if isinstance(v, dict) else [] if isinstance(v, list) else None


def revert(before: Any, after: Any, current: Any, path: str = "") -> tuple[Any, list[str]]:
    """`current` without the change `before` → `after`; returns (value, conflicting paths)."""
    if before == after:
        return current, []
    if current == after:
        return before, []
    # A key or list the action created (or removed): compare against an empty one.
    was_none = before is None
    if before is None and isinstance(after, dict | list):
        before = _empty_like(after)
    if after is None and isinstance(before, dict | list):
        after = _empty_like(before)
    if current is None and isinstance(after, dict | list):
        current = _empty_like(after)

    if _is_number(before) and _is_number(after) and _is_number(current):
        value = current - (after - before)
        return (int(value) if isinstance(value, float) and value.is_integer() else value), []
    if isinstance(before, dict) and isinstance(after, dict) and isinstance(current, dict):
        out = dict(current)
        conflicts: list[str] = []
        for key in before.keys() | after.keys():
            value, c = revert(before.get(key), after.get(key), current.get(key), f"{path}.{key}")
            conflicts += c
            if value is None and key not in before:
                out.pop(key, None)
            else:
                out[key] = value
        return (None if was_none and not out else out), conflicts
    if _id_list(before) and _id_list(after) and _id_list(current):
        return _revert_ids(before, after, current, path)
    if _str_list(before) and _str_list(after) and _str_list(current):
        added = set(after) - set(before)
        removed = [x for x in before if x not in after]
        out_list = [x for x in current if x not in added]
        out_list += [x for x in removed if x not in out_list]
        return (None if was_none and not out_list else out_list), []
    return current, [path.lstrip(".") or "value"]


def _revert_ids(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    current: list[dict[str, Any]],
    path: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    b = {x["id"]: x for x in before}
    a = {x["id"]: x for x in after}
    out: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for item in current:
        i = item["id"]
        if i in a and i not in b:
            continue  # added by the action
        if i in a and i in b:
            merged, c = revert(b[i], a[i], item, f"{path}[{i}]")
            conflicts += c
            out.append(merged)
        else:
            out.append(item)
    present = {x["id"] for x in out}
    out += [x for i, x in b.items() if i not in a and i not in present]
    return out, conflicts


def diff_props(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict, dict]:
    """Only the top-level keys that changed; an absent key is null (props patch rules)."""
    keys = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}
