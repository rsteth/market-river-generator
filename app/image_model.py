from __future__ import annotations

import html
import mimetypes
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings
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


class FalImageProvider:
    name = "fal"

    def __init__(self, settings: Settings):
        self.model = settings.fal_model
        self.image_size = settings.fal_image_size
        self.output_format = settings.fal_output_format
        self.num_inference_steps = settings.fal_num_inference_steps
        self.acceleration = settings.fal_acceleration
        self.enable_safety_checker = settings.fal_enable_safety_checker

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        import fal_client

        output_dir.mkdir(parents=True, exist_ok=True)
        result = fal_client.subscribe(
            self.model,
            arguments={
                "prompt": _fal_prompt(prompt_result),
                "image_size": self.image_size,
                "num_inference_steps": self.num_inference_steps,
                "num_images": 1,
                "enable_safety_checker": self.enable_safety_checker,
                "output_format": self.output_format,
                "acceleration": self.acceleration,
            },
        )
        image = _first_fal_image(result)
        url = image["url"]
        content_type = image.get("content_type") or _content_type_for_format(self.output_format)
        image_format = _format_for_content_type(content_type, self.output_format)
        path = output_dir / f"{slot}-{run_id}.{image_format}"
        _download_image(url, path)
        return GeneratedImage(provider=self.name, path=path, content_type=content_type, format=image_format)


class ReplicateImageProvider:
    name = "replicate"

    def __init__(self, settings: Settings):
        self.model = settings.replicate_model
        self.aspect_ratio = settings.replicate_aspect_ratio
        self.resolution = settings.replicate_resolution
        self.output_format = settings.replicate_output_format
        self.output_quality = settings.replicate_output_quality
        self.safety_tolerance = settings.replicate_safety_tolerance
        self.seed = settings.replicate_seed

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        import replicate

        output_dir.mkdir(parents=True, exist_ok=True)
        request_input: dict[str, object] = {
            "prompt": provider_prompt(prompt_result),
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "output_format": self.output_format,
            "output_quality": self.output_quality,
            "safety_tolerance": self.safety_tolerance,
        }
        if self.seed is not None:
            request_input["seed"] = self.seed

        result = replicate.run(self.model, input=request_input)
        content_type = _content_type_for_format(self.output_format)
        image_format = _format_for_content_type(content_type, self.output_format)
        path = output_dir / f"{slot}-{run_id}.{image_format}"
        _write_replicate_output(result, path)
        return GeneratedImage(provider=self.name, path=path, content_type=content_type, format=image_format)


def get_image_provider(settings: Settings) -> ImageProvider:
    name = settings.image_provider
    providers: dict[str, ImageProvider] = {
        "mock": MockImageProvider(),
        "none": NoneImageProvider(),
        "future": FutureImageProvider(),
        "fal": FalImageProvider(settings),
        "replicate": ReplicateImageProvider(settings),
    }
    try:
        return providers[name]
    except KeyError as exc:
        valid = ", ".join(sorted(providers))
        raise ValueError(f"IMAGE_PROVIDER must be one of: {valid}") from exc


def _fal_prompt(prompt_result: PromptResult) -> str:
    return provider_prompt(prompt_result)


def provider_prompt(prompt_result: PromptResult) -> str:
    return (
        f"{prompt_result.positive_prompt}\n\n"
        f"Avoid: {prompt_result.negative_prompt}."
    )


def _first_fal_image(result: object) -> dict[str, str]:
    if not isinstance(result, dict):
        raise ValueError("fal response must be a JSON object")
    images = result.get("images")
    if not isinstance(images, list) or not images:
        raise ValueError("fal response did not include any images")
    image = images[0]
    if not isinstance(image, dict) or not isinstance(image.get("url"), str):
        raise ValueError("fal response image did not include a URL")
    return image


def _download_image(url: str, path: Path) -> None:
    import requests

    with requests.get(url, timeout=120) as response:
        response.raise_for_status()
        path.write_bytes(response.content)


def _write_replicate_output(result: object, path: Path) -> None:
    output = _first_replicate_output(result)
    read = getattr(output, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        path.write_bytes(data)
        return

    url = _replicate_output_url(output)
    if url:
        _download_image(url, path)
        return

    raise ValueError("Replicate response did not include a readable file or URL")


def _first_replicate_output(result: object) -> object:
    if isinstance(result, list | tuple):
        if not result:
            raise ValueError("Replicate response did not include any outputs")
        return result[0]
    return result


def _replicate_output_url(output: object) -> str | None:
    if isinstance(output, str):
        return output
    url_method = getattr(output, "url", None)
    if callable(url_method):
        url = url_method()
        return url if isinstance(url, str) else None
    return None


def _content_type_for_format(output_format: str) -> str:
    if output_format == "webp":
        return "image/webp"
    if output_format == "png":
        return "image/png"
    return "image/jpeg"


def _format_for_content_type(content_type: str, fallback: str) -> str:
    extension = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if extension:
        return extension.lstrip(".").replace("jpe", "jpg")
    if fallback == "webp":
        return "webp"
    if fallback == "png":
        return "png"
    return "jpg"


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
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1200 1200" role="img" aria-label="{html.escape(title)}">
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
  <rect width="1200" height="1200" fill="url(#sky)"/>
  <path d="M0 660 C180 590 300 700 470 640 C650 565 830 625 1200 530 L1200 1200 L0 1200 Z" fill="url(#water)" opacity="0.95"/>
  <path d="M0 745 C200 675 330 805 520 730 C710 650 900 725 1200 610" fill="none" stroke="#f5d27a" stroke-width="12" opacity="0.55"/>
  <path d="M60 420 L140 310 L220 420 Z M205 420 L205 255 L305 255 L305 420 Z M330 420 L395 290 L460 420 Z M480 420 L480 230 L595 230 L595 420 Z M620 420 L700 280 L780 420 Z M795 420 L795 245 L900 245 L900 420 Z M920 420 L990 300 L1060 420 Z" fill="#22313b" opacity="0.9"/>
  <rect x="48" y="54" width="1104" height="270" rx="18" fill="#10202a" opacity="0.72"/>
  <text x="72" y="112" class="title">{html.escape(title)}</text>
  <text x="72" y="154" class="small">Mock image artifact for market-river-generator</text>
  {text_lines}
</svg>
"""
