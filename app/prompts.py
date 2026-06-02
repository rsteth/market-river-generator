from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEMPLATE_VERSION = "river_city_v0.1"
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "river_city_v0.1.txt"
NEGATIVE_PROMPT = "text, numbers, logos, stock charts, candlesticks, tickers, people in foreground"


@dataclass(frozen=True)
class PromptResult:
    template_version: str
    positive_prompt: str
    negative_prompt: str


def compose_prompt(state: dict[str, Any], template_path: Path = DEFAULT_TEMPLATE_PATH) -> PromptResult:
    template = template_path.read_text(encoding="utf-8")
    river = state["river"]
    city = state["city"]
    positive = template.format(
        river_speed=river["speed"],
        river_depth=river["depth"],
        river_surface=river["surface"],
        river_color=river["color"],
        city_lighting=city["lighting"],
        city_mood=city["mood"],
    ).strip()
    return PromptResult(
        template_version=TEMPLATE_VERSION,
        positive_prompt=positive,
        negative_prompt=NEGATIVE_PROMPT,
    )

