import unittest

from backend.core.chat_intelligence import (
    latest_user_question,
    make_chat_title,
    rewrite_followup,
)


class ChatIntelligenceTests(unittest.TestCase):
    def test_make_chat_title_detects_common_legal_topics(self):
        self.assertEqual(make_chat_title("How do I file an RTI application?"), "RTI Filing Help")
        self.assertEqual(make_chat_title("Police arrested my brother, what are his rights?"), "Police Arrest Rights")
        self.assertEqual(make_chat_title("A shop refused refund for a defective phone"), "Consumer Refund Issue")

    def test_latest_user_question_skips_current_command(self):
        history = [
            {"role": "user", "content": "How do I file an RTI application?"},
            {"role": "assistant", "content": "Use Form A..."},
            {"role": "user", "content": "retry"},
        ]
        self.assertEqual(latest_user_question(history), "How do I file an RTI application?")

    def test_rewrite_followup_handles_retry_and_detail_commands(self):
        history = [{"role": "user", "content": "What are my rights if police arrest me?"}]
        retry = rewrite_followup("rety", history, "en")
        detail = rewrite_followup("explain more", history, "en")

        self.assertEqual(
            retry.question,
            "Please retry and improve the previous answer for this question: What are my rights if police arrest me?",
        )
        self.assertTrue(retry.rewritten)
        self.assertEqual(
            detail.question,
            "Explain this in more practical detail with clear next steps: What are my rights if police arrest me?",
        )

    def test_rewrite_followup_combines_ambiguous_followup(self):
        history = [{"role": "user", "content": "My employer has not paid my salary. What can I do?"}]
        result = rewrite_followup("what if they refuse?", history, "en")

        self.assertTrue(result.rewritten)
        self.assertIn("Previous question: My employer has not paid my salary", result.question)
        self.assertIn("Follow-up: what if they refuse?", result.question)

    def test_rewrite_followup_leaves_standalone_question_unchanged(self):
        result = rewrite_followup("How do I file a consumer complaint?", [], "en")
        self.assertFalse(result.rewritten)
        self.assertEqual(result.question, "How do I file a consumer complaint?")


if __name__ == "__main__":
    unittest.main()
