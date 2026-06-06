from __future__ import annotations

from typing import Any


def derive_visual_state(snapshot: dict[str, Any], weather_condition: str = "sunny", slot: str = "open") -> dict[str, Any]:
    summary = snapshot.get("summary", {})
    avg_risk = summary.get("avg_risk_change_pct")
    vix_change = summary.get("vix_change_pct")

    market_mood = _market_mood(avg_risk)
    volatility_mood = _volatility_mood(vix_change)

    river = _river_for_market(market_mood)
    river["surface"] = _surface_for_volatility(volatility_mood, river["surface"])

    city = _city_for_market(market_mood)

    return {
        "market_mood": market_mood,
        "volatility_mood": volatility_mood,
        "weather": {"condition": weather_condition},
        "time_of_day": {"slot": slot},
        "river": river,
        "city": city,
    }


def caption_for_state(state: dict[str, Any]) -> str:
    river = state["river"]
    city = state["city"]
    opening = _caption_opening(state)
    return f"{opening}. a {river['speed']}, {river['depth']} river under {city['lighting']} city light"


def _caption_opening(state: dict[str, Any]) -> str:
    weather = state.get("weather", {}).get("condition", "sunny")
    time_of_day = state.get("time_of_day")
    slot = time_of_day.get("slot") if isinstance(time_of_day, dict) else time_of_day
    normalized_slot = str(slot or "open").strip().lower()
    if normalized_slot == "close":
        weather_label = "clear" if weather == "sunny" else weather
        return f"a {weather_label} evening"
    caption_time = {
        "open": "morning",
        "midday": "midday",
    }.get(normalized_slot, "morning")
    return f"a {weather} {caption_time}"


def _market_mood(avg_risk: float | None) -> str:
    if avg_risk is None:
        return "flat"
    if avg_risk > 1.0:
        return "strong_risk_on"
    if avg_risk > 0.25:
        return "risk_on"
    if avg_risk >= -0.25:
        return "flat"
    if avg_risk >= -1.0:
        return "risk_off"
    return "strong_risk_off"


def _volatility_mood(vix_change: float | None) -> str:
    if vix_change is None:
        return "stable"
    if vix_change > 5:
        return "rising"
    if vix_change < -5:
        return "falling"
    return "stable"


def _river_for_market(mood: str) -> dict[str, str]:
    mapping = {
        "strong_risk_on": {
            "speed": "surging",
            "depth": "deep",
            "surface": "forceful",
            "color": "blue green with strong gold reflections",
        },
        "risk_on": {
            "speed": "fast",
            "depth": "deep",
            "surface": "smooth but forceful",
            "color": "blue green with gold reflections",
        },
        "flat": {
            "speed": "slow",
            "depth": "steady",
            "surface": "quiet",
            "color": "muted blue gray with soft silver reflections",
        },
        "risk_off": {
            "speed": "receding",
            "depth": "shallow",
            "surface": "uneven",
            "color": "dark teal with exposed stone banks",
        },
        "strong_risk_off": {
            "speed": "low and strained",
            "depth": "shallow",
            "surface": "broken",
            "color": "charcoal green with wide exposed banks",
        },
    }
    return dict(mapping[mood])


def _surface_for_volatility(volatility_mood: str, base_surface: str) -> str:
    if volatility_mood == "rising":
        return f"{base_surface}, choppy, with broken reflections and small whirlpools"
    if volatility_mood == "falling":
        return f"{base_surface}, smoother, with long continuous reflections"
    return f"{base_surface}, stable, with measured reflections"


def _city_for_market(mood: str) -> dict[str, str]:
    mapping = {
        "strong_risk_on": {
            "lighting": "brightly illuminated",
            "mood": "confident and expansive",
        },
        "risk_on": {
            "lighting": "broadly illuminated",
            "mood": "confident but calm",
        },
        "flat": {
            "lighting": "muted and even",
            "mood": "still and observant",
        },
        "risk_off": {
            "lighting": "low and directional",
            "mood": "cautious and tense",
        },
        "strong_risk_off": {
            "lighting": "dark and fragmented",
            "mood": "defensive and austere",
        },
    }
    return dict(mapping[mood])
