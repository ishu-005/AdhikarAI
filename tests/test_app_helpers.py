import json
import unittest

from backend.core.cache import OptimizationCache
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


    def test_optimization_cache_is_scoped_by_conversation(self):
        cache = OptimizationCache()

        cache.set("Police refused FIR", "criminal_law", "en", {"answer": "from chat one"}, scope="chat-1")

        self.assertEqual(
            cache.get("Police refused FIR", "criminal_law", "en", scope="chat-1")["answer"],
            "from chat one",
        )
        self.assertIsNone(cache.get("Police refused FIR", "criminal_law", "en", scope="chat-2"))

    def test_optimization_cache_returns_defensive_copies(self):
        cache = OptimizationCache()
        cache.set(
            "Police refused FIR",
            "criminal_law",
            "en",
            {"answer": "original", "citations": [{"id": 1, "section": "A"}]},
            scope="chat-1",
        )

        cached = cache.get("Police refused FIR", "criminal_law", "en", scope="chat-1")
        cached["citations"][0]["section"] = "mutated"

        fresh = cache.get("Police refused FIR", "criminal_law", "en", scope="chat-1")
        self.assertEqual(fresh["citations"][0]["section"], "A")


if __name__ == "__main__":
    unittest.main()
