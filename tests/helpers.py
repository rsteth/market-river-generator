from __future__ import annotations

from pathlib import Path

from app.config import Settings


def make_settings(output_dir: Path, **overrides: object) -> Settings:
    values = {
        "app_name": "market-river-generator",
        "aws_region": "us-east-1",
        "s3_bucket": None,
        "public_base_url": None,
        "image_provider": "mock",
        "fal_model": "fal-ai/flux/schnell",
        "fal_image_size": "square_hd",
        "fal_output_format": "jpeg",
        "fal_num_inference_steps": 4,
        "fal_acceleration": "none",
        "fal_enable_safety_checker": True,
        "replicate_model": "black-forest-labs/flux-2-pro",
        "replicate_aspect_ratio": "1:1",
        "replicate_resolution": "1 MP",
        "replicate_output_format": "webp",
        "replicate_output_quality": 88,
        "replicate_safety_tolerance": 2,
        "replicate_seed": None,
        "prompt_active_key": "prompts/river_city/active.json",
        "allow_bundled_prompt_fallback": False,
        "market_data_max_age_hours": 120,
        "output_dir": output_dir,
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)
