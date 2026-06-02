from __future__ import annotations

from typing import Any


SLOT_ORDER = {"open": 0, "midday": 1, "close": 2}


def update_latest_manifest(
    existing: dict[str, Any] | None,
    item: dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    items = []
    if existing and isinstance(existing.get("items"), list):
        items = [old for old in existing["items"] if _item_key(old) != _item_key(item)]
    items.append(item)
    items.sort(key=lambda value: (value.get("date", ""), SLOT_ORDER.get(value.get("slot", ""), 99)))
    return {"updated_at": updated_at, "items": items}


def _item_key(item: dict[str, Any]) -> tuple[str | None, str | None]:
    return item.get("date"), item.get("slot")

