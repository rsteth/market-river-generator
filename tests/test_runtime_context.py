from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.runtime_context import load_runtime_log_context


class RuntimeContextTests(unittest.TestCase):
    def test_load_runtime_log_context_uses_env_and_task_input(self) -> None:
        env = {
            "APP_NAME": "market-river-generator",
            "AWS_REGION": "us-east-1",
            "SCHEDULE_NAME": "market-river-generator-open",
            "SCHEDULE_SLOT": "open",
            "TASK_INPUT_JSON": '{"slot":"open","schedule_name":"market-river-generator-open"}',
        }

        with patch.dict(os.environ, env, clear=True):
            context = load_runtime_log_context()

        self.assertEqual(context["app_name"], "market-river-generator")
        self.assertEqual(context["schedule_name"], "market-river-generator-open")
        self.assertEqual(context["scheduler_slot"], "open")
        self.assertEqual(context["scheduler_name"], "market-river-generator-open")


if __name__ == "__main__":
    unittest.main()
