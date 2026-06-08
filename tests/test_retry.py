from __future__ import annotations

import unittest

from app.retry import retry_call


class RetryTests(unittest.TestCase):
    def test_retry_call_retries_until_success(self) -> None:
        calls = {"count": 0}

        def flaky() -> str:
            calls["count"] += 1
            if calls["count"] < 3:
                raise RuntimeError("not yet")
            return "ok"

        with self.assertLogs("app.retry", level="WARNING"):
            self.assertEqual(retry_call("test", flaky, attempts=3, base_delay_seconds=0), "ok")
        self.assertEqual(calls["count"], 3)

    def test_retry_call_raises_last_error(self) -> None:
        def broken() -> str:
            raise RuntimeError("still broken")

        with self.assertLogs("app.retry", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "still broken"):
                retry_call("test", broken, attempts=2, base_delay_seconds=0)


if __name__ == "__main__":
    unittest.main()
