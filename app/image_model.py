from __future__ import annotations

import html
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.prompts import PromptResult


@dataclass(frozen=True)
class GeneratedImage:
    provider: str
    path: Path | None
    content_type: str | None
    format: str | None


class ImageProvider(Protocol):
    name: str

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        ...


class MockImageProvider:
    name = "mock"

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{slot}-{run_id}.svg"
        excerpt = _wrap(prompt_result.positive_prompt, width=76, max_lines=5)
        svg = _placeholder_svg(slot, market_mood, volatility_mood, excerpt)
        path.write_text(svg, encoding="utf-8")
        return GeneratedImage(provider=self.name, path=path, content_type="image/svg+xml", format="svg")


class NoneImageProvider:
    name = "none"

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        return GeneratedImage(provider=self.name, path=None, content_type=None, format=None)


class FutureImageProvider:
    name = "future"

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        raise NotImplementedError(
            "TODO: implement a real image provider such as OpenAI, Replicate, or Bedrock. "
            "Keep this method returning GeneratedImage so publish.py does not need to change."
        )


def get_image_provider(name: str) -> ImageProvider:
    providers: dict[str, ImageProvider] = {
        "mock": MockImageProvider(),
        "none": NoneImageProvider(),
        "future": FutureImageProvider(),
    }
    try:
        return providers[name]
    except KeyError as exc:
        valid = ", ".join(sorted(providers))
        raise ValueError(f"IMAGE_PROVIDER must be one of: {valid}") from exc


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(" ".join(text.split()), width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = f"{lines[-1].rstrip()}..."
    return lines


def _placeholder_svg(slot: str, market_mood: str, volatility_mood: str, excerpt: list[str]) -> str:
    title = f"{slot.upper()} / {market_mood} / volatility {volatility_mood}"
    text_lines = "\n".join(
        f'<text x="72" y="{260 + index * 28}" class="body">{html.escape(line)}</text>'
        for index, line in enumerate(excerpt)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800" role="img" aria-label="{html.escape(title)}">
  <defs>
    <linearGradient id="sky" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#20324a"/>
      <stop offset="58%" stop-color="#6c8791"/>
      <stop offset="100%" stop-color="#d7b36a"/>
    </linearGradient>
    <linearGradient id="water" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0%" stop-color="#0c4f5f"/>
      <stop offset="55%" stop-color="#1e7d80"/>
      <stop offset="100%" stop-color="#d9a83d"/>
    </linearGradient>
    <style>
      .title {{ font: 700 34px Arial, sans-serif; fill: #f7f1df; }}
      .body {{ font: 22px Arial, sans-serif; fill: #f7f1df; opacity: 0.92; }}
      .small {{ font: 18px Arial, sans-serif; fill: #d8e4e5; opacity: 0.86; }}
    </style>
  </defs>
  <rect width="1200" height="800" fill="url(#sky)"/>
  <path d="M0 490 C180 430 300 520 470 470 C650 415 830 465 1200 390 L1200 800 L0 800 Z" fill="url(#water)" opacity="0.95"/>
  <path d="M0 560 C200 505 330 610 520 548 C710 485 900 540 1200 455" fill="none" stroke="#f5d27a" stroke-width="10" opacity="0.55"/>
  <path d="M60 420 L140 310 L220 420 Z M205 420 L205 255 L305 255 L305 420 Z M330 420 L395 290 L460 420 Z M480 420 L480 230 L595 230 L595 420 Z M620 420 L700 280 L780 420 Z M795 420 L795 245 L900 245 L900 420 Z M920 420 L990 300 L1060 420 Z" fill="#22313b" opacity="0.9"/>
  <rect x="48" y="54" width="1104" height="270" rx="18" fill="#10202a" opacity="0.72"/>
  <text x="72" y="112" class="title">{html.escape(title)}</text>
  <text x="72" y="154" class="small">Mock image artifact for market-river-generator</text>
  {text_lines}
</svg>
"""

