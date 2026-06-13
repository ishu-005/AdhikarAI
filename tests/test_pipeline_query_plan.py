import unittest
from unittest.mock import patch

from backend.rag.pipeline import answer_query


class PipelineQueryPlanTests(unittest.TestCase):
    def test_smalltalk_skips_retrieval(self):
        with patch("backend.rag.pipeline.retrieve") as retrieve:
            result = answer_query("Tell me about yourself", "general", "en", history=[])

        retrieve.assert_not_called()
        self.assertIn("AdhikarAI", result["answer"])
        self.assertEqual(result["context_source_label"], "no retrieval")
        self.assertFalse(result["diagnostics"]["needs_retrieval"])
        self.assertEqual(result["diagnostics"]["query_type"], "smalltalk")

    def test_greeting_smalltalk_is_conversational(self):
        result = answer_query("Hi", "general", "en", history=[])

        self.assertIn("Hi", result["answer"])
        self.assertIn("legal", result["answer"].lower())
        self.assertNotIn("I will decide whether legal retrieval is needed", result["answer"])

    def test_status_smalltalk_does_not_repeat_generic_handoff(self):
        result = answer_query("How are you", "general", "en", history=[])

        self.assertIn("ready", result["answer"].lower())
        self.assertNotIn("I will decide whether legal retrieval is needed", result["answer"])


if __name__ == "__main__":
    unittest.main()
