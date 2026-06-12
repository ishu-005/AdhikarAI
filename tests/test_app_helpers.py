import json
import unittest

from backend.core.sse import cached_stream_events, sse


class AppHelperTests(unittest.TestCase):
    def test_cached_stream_events_emit_meta_replace_done(self):
        cached = {
            "answer": "Cached answer",
            "citations": [{"id": 1}],
            "live_sources": [],
            "context_notice": "cached notice",
            "context_sources": ["database"],
        }

        events = list(cached_stream_events("abc", "rti", "en", cached))

        self.assertEqual(len(events), 3)
        self.assertTrue(events[0].startswith("event: meta"))
        self.assertTrue(events[1].startswith("event: replace"))
        self.assertTrue(events[2].startswith("event: done"))
        done_payload = json.loads(events[2].split("data:", 1)[1])
        self.assertEqual(done_payload["answer"], "Cached answer")
        self.assertEqual(done_payload["citations"], [{"id": 1}])

    def test_sse_preserves_unicode(self):
        frame = sse("token", {"value": "हिंदी"})
        self.assertIn("हिंदी", frame)


if __name__ == "__main__":
    unittest.main()
