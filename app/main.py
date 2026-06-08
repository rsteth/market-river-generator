from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from app.config import Settings, VALID_SLOTS, VALID_WEATHER_CONDITIONS, resolve_run_request
from app.logging_utils import configure_logging, get_logger
from app.pipeline import default_dependencies, run_pipeline


logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    try:
        request = resolve_run_request(args.slot, args.weather)
        result = run_pipeline(request, default_dependencies(settings))
        return 0 if result.succeeded else 1

    except Exception as exc:
        logger.exception("failed to start run", extra={"_slot": args.slot or "unknown", "_error": str(exc)})
        return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a symbolic market river image and manifest.")
    parser.add_argument("--slot", choices=sorted(VALID_SLOTS), help="Market day slot to generate.")
    parser.add_argument("--weather", choices=[*sorted(VALID_WEATHER_CONDITIONS), "all"], help="Weather variant to use.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
