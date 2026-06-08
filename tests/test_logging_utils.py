from __future__ import annotations

import json
import logging
import unittest

from app.logging_utils import JsonFormatter, set_log_context


class LoggingUtilsTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_log_context({})

    def test_json_formatter_includes_global_context_and_record_extra(self) -> None:
        set_log_context({"ecs_task_arn": "task-arn", "schedule_name": "market-open"})
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record._run_id = "run-1"

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["ecs_task_arn"], "task-arn")
        self.assertEqual(payload["schedule_name"], "market-open")
        self.assertEqual(payload["run_id"], "run-1")
