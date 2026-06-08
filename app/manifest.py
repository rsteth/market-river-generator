from __future__ import annotations

from typing import Any

from app.contracts import ManifestItem


SLOT_ORDER = {"open": 0, "midday": 1, "close": 2}
WEATHER_ORDER = {"sunny": 0, "cloudy": 1, "rainy": 2}


def update_latest_manifest(
    existing: dict[str, Any] | None,
    item: ManifestItem | dict[str, Any],
    updated_at: str,
) -> dict[str, Any]:
    return update_latest_manifest_items(existing, [item], updated_at=updated_at)


def update_latest_manifest_items(
    existing: dict[str, Any] | None,
    new_items: list[ManifestItem | dict[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    item_payloads = [item.to_dict() if isinstance(item, ManifestItem) else item for item in new_items]
    items = []
    if existing and isinstance(existing.get("items"), list):
        items = [
            old
            for old in existing["items"]
            if not any(_same_manifest_slot(old, item_payload) for item_payload in item_payloads)
        ]
    items.extend(item_payloads)
    items.sort(
        key=lambda value: (
            value.get("date", ""),
            SLOT_ORDER.get(value.get("slot", ""), 99),
            WEATHER_ORDER.get(value.get("weather", ""), 99),
        )
    )
    return {"updated_at": updated_at, "items": items}


def _same_manifest_slot(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if old.get("date") != new.get("date") or old.get("slot") != new.get("slot"):
        return False
    new_weather = new.get("weather")
    old_weather = old.get("weather")
    if new_weather:
        return old_weather in {None, new_weather}
    return old_weather == new_weather
