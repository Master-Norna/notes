"""Integration tests. Use `python run.py --test` to test BOTH pinned sources."""
import os
import unittest

import probe


class TCPRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.revision = os.environ.get("BACKPRESSURE_REVISION")
        if cls.revision not in ("before", "after"):
            raise RuntimeError("Use python run.py --test to select and verify pinned sources")
        cls.loop_choice = os.environ.get("BACKPRESSURE_LOOP", "default")

    def test_already_cancelled_scope(self):
        result = probe.run_async(probe.already_cancelled, self.loop_choice)
        probe.check_cancellation(result, self.revision)

    def test_cancel_pending_receive(self):
        result = probe.run_async(probe.blocked_receive, self.loop_choice)
        self.assertTrue(result["was_blocked_and_reading"])
        probe.check_cancellation(result, self.revision)

    def test_buffer_and_lossless_resume(self):
        result = probe.run_async(probe.backpressure, self.loop_choice)
        probe.check_backpressure(result, self.revision)


if __name__ == "__main__":
    unittest.main()
