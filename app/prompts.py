from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEMPLATE_VERSION = "river_city_v0.1"
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "river_city_v0.1.txt"
NEGATIVE_PROMPT = "text, numbers, logos, stock charts, candlesticks, tickers, people in foreground"
DEFAULT_WEATHER_CONDITION = "sunny"
WEATHER_SNIPPETS = {
    "sunny": (
        "Clear sunny weather localized only over the floating city-disc, with crisp visibility and warm directional "
        "sunlight falling on the mountain, rooftops, riverbanks, and waterfall. Highlights stay attached to the "
        "architecture, terrain, trees, and water. The surrounding white space remains empty and unaffected, with no sky "
        "gradient, horizon, or light spill."
    ),
    "cloudy": (
        "Overcast cloudy weather contained around the floating city-disc, with compact cloud layers wrapping parts of "
        "the mountain and upper city without extending beyond the world. Broad diffused light creates soft shadows and "
        "muted reflections on glass, stone, and water. This is dry cloud cover only: no rain, no drizzle, no falling "
        "water from the clouds, no wet streets, and no rain streaks. The surrounding white space remains pure, empty, "
        "and unclouded."
    ),
    "rainy": (
        "Rainy weather contained within the floating city-disc, with localized gray clouds, visible rainfall over the "
        "city and mountain, wet rooftops, darkened streets, and glossy reflections across stone, glass, and river "
        "surfaces. Mist gathers only around the mountain and waterfall, fading before it reaches the white background. "
        "The city layout remains readable and centered."
    ),
}
MARKET_CONDITION_SNIPPETS = {
    "strong_risk_on": (
        "Within this contained world, the river and city feel forceful and expansive. The river is full, fast, and "
        "high-volume, with bright rapids, churning whitewater, small whirlpools, and broken gold reflections where it "
        "cuts through the city. The waterfall is broad and energetic as it leaves the disc. The mountain slopes and "
        "riverbanks feel warm and green, with lush trees, active terraces, and a few tiny birds contained over the "
        "city, never outside the disc silhouette. City lighting is bright and confident, with warm highlights on glass, "
        "stone, and water."
    ),
    "risk_on": (
        "Within this contained world, the river and city feel constructive and open. The river is full and clear, moving "
        "briskly with mild rapids, steady current, and warm reflections along the riverbanks. The waterfall is full and "
        "continuous as it leaves the disc. Mountain slopes and terraces feel green and warm-toned, while city lighting is "
        "broad, warm, and confident without becoming exaggerated."
    ),
    "flat": (
        "Within this contained world, the river and city feel balanced and still. The river is steady, moderate, and "
        "quiet, with a smooth surface, long muted reflections, and a consistent waterline along the banks. The waterfall "
        "leaves the disc in a clean, even sheet. City lighting is even and calm, with soft contrast, orderly "
        "architecture, and a stable, observant mood."
    ),
    "risk_off": (
        "Within this contained world, the river and city feel cautious but still functional. The river is low, dark, and "
        "uneven, with small rapids, exposed stone banks, and broken reflections, but the water remains open and "
        "unfrozen. A light dusting of snow sits on rooftops, terraces, bridge edges, and the upper mountain, avoiding "
        "the river surface. The waterfall is narrower but continuous as it leaves the disc. City lighting is cool, "
        "restrained, and directional, with sharper shadows and fewer warm highlights."
    ),
    "strong_risk_off": (
        "Within this contained world, the river and city feel strained and defensive. The river is shallow, turbulent, "
        "and visibly obstructed by jagged ice plates, with dark water forcing through narrow channels, harsh rapids, "
        "exposed stone banks, and shattered reflections. Snow gathers heavily on rooftops, bridges, terraces, river "
        "edges, and the upper mountain, making the city feel winterized and austere. The waterfall is fragmented and "
        "partly icy as it spills over the edge of the disc. City lighting is sparse, cold, and directional, with sharp "
        "shadows and a tense mood."
    ),
}


@dataclass(frozen=True)
class PromptResult:
    template_version: str
    positive_prompt: str
    negative_prompt: str


def compose_prompt(state: dict[str, Any], template_path: Path = DEFAULT_TEMPLATE_PATH) -> PromptResult:
    template = template_path.read_text(encoding="utf-8")
    weather = WEATHER_SNIPPETS[_weather_condition(state)]
    market_condition = MARKET_CONDITION_SNIPPETS[_market_condition(state)]
    positive = template.format(
        weather=weather,
        market_condition=market_condition,
    ).strip()
    return PromptResult(
        template_version=TEMPLATE_VERSION,
        positive_prompt=positive,
        negative_prompt=NEGATIVE_PROMPT,
    )


def _weather_condition(state: dict[str, Any]) -> str:
    weather = state.get("weather")
    raw = weather.get("condition") if isinstance(weather, dict) else weather
    if raw is None:
        raw = state.get("weather_condition", DEFAULT_WEATHER_CONDITION)
    condition = str(raw).strip().lower()
    if condition not in WEATHER_SNIPPETS:
        valid = ", ".join(sorted(WEATHER_SNIPPETS))
        raise ValueError(f"weather condition must be one of: {valid}")
    return condition


def _market_condition(state: dict[str, Any]) -> str:
    mood = str(state.get("market_mood", "")).strip().lower()
    if mood not in MARKET_CONDITION_SNIPPETS:
        valid = ", ".join(sorted(MARKET_CONDITION_SNIPPETS))
        raise ValueError(f"market mood must be one of: {valid}")
    return mood
