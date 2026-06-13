import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from backend.rag.prompts import fallback_answer
from backend.core.chat_intelligence import plan_query
from backend.rag.pipeline import _assemble, _expand_retrieval_query, answer_query


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

    def test_domestic_threat_query_expands_for_retrieval(self):
        expanded = _expand_retrieval_query("my husband is threatning me", "women_family")

        self.assertIn("my husband is threatning me", expanded)
        self.assertIn("domestic violence", expanded)
        self.assertIn("protection officer", expanded)

    def test_fallback_does_not_suggest_public_upload(self):
        answer = fallback_answer("unsupported issue", [], [], "en", ["general knowledge"])

        self.assertNotIn("upload", answer.lower())

    def test_domain_profile_retrieves_balanced_secondary_domain_context(self):
        question = "My husband is threatening me"
        plan = plan_query(question, [], "en")
        women_doc = Document(page_content="Domestic violence protection order", metadata={"domain": "women_family", "source": "dv"})
        criminal_doc = Document(page_content="Criminal intimidation FIR", metadata={"domain": "criminal_law", "source": "bns"})

        with (
            patch("backend.rag.pipeline.live_fetch_for_domain", return_value=[]),
            patch("backend.rag.pipeline.retrieve", side_effect=[[women_doc], [women_doc], [], [criminal_doc]]) as retrieve,
        ):
            ctx = _assemble(question, "women_family", "en", plan)

        called_domains = [call.args[1] for call in retrieve.call_args_list]
        self.assertIn("women_family", called_domains)
        self.assertIn("criminal_law", called_domains)
        self.assertTrue(all(call.kwargs.get("scoped") is True for call in retrieve.call_args_list))
        self.assertIn("procedure", [item["aspect"] for item in ctx["diagnostics"]["retrieval_queries"]])
        self.assertEqual(ctx["diagnostics"]["query_intent"]["domain"], "women_family")
        self.assertEqual(ctx["diagnostics"]["query_intent"]["intent"], "domestic_violence")
        self.assertEqual([doc.page_content for doc in ctx["docs"]], [
            "Domestic violence protection order",
            "Criminal intimidation FIR",
        ])
        self.assertIn("retrieval_queries", ctx["diagnostics"])

    def test_ambiguous_discrimination_asks_clarifying_question_without_retrieval(self):
        with patch("backend.rag.pipeline.retrieve") as retrieve:
            result = answer_query("Discrimination by authority", "human_rights", "en", history=[])

        retrieve.assert_not_called()
        self.assertIn("What type of discrimination", result["answer"])
        self.assertIn("Disability", result["answer"])
        self.assertTrue(result["diagnostics"]["query_intent"]["needs_clarification"])
        self.assertEqual(result["context_source_label"], "clarification")

    def test_clarification_choice_is_acknowledged_without_retrieval(self):
        history = [
            {"role": "user", "content": "Discrimination by authority"},
            {
                "role": "assistant",
                "content": "What type of discrimination is this?",
                "meta": {
                    "diagnostics": {
                        "query_intent": {
                            "domain": "human_rights",
                            "intent": "ambiguous_discrimination",
                            "needs_clarification": True,
                            "clarification_choices": ["Disability", "Caste", "Gender", "Religion", "Police/Government abuse", "Other"],
                        }
                    }
                },
            },
        ]

        with patch("backend.rag.pipeline.retrieve") as retrieve:
            result = answer_query("Caste", "human_rights", "en", history=history)

        retrieve.assert_not_called()
        self.assertIn("Got it: Caste", result["answer"])
        self.assertIn("Share what happened", result["answer"])
        self.assertEqual(result["diagnostics"]["query_type"], "clarification_ack")
        self.assertTrue(result["diagnostics"]["clarification_state"]["awaiting_details"])

    def test_fir_missing_escalation_support_is_added_to_prompt(self):
        question = "Police refused FIR"
        plan = plan_query(question, [], "en")
        witness_doc = Document(
            page_content="Section 216. Threatening any person to give false evidence as a witness.",
            metadata={"domain": "criminal_law", "source": "bns"},
        )

        with (
            patch("backend.rag.pipeline.live_fetch_for_domain", return_value=[]),
            patch("backend.rag.pipeline.retrieve", side_effect=[[witness_doc], [], []]),
        ):
            ctx = _assemble(question, "criminal_law", "en", plan)

        self.assertIn(
            "source missing for exact FIR escalation procedure",
            ctx["prompt_vars"]["support_block"],
        )


if __name__ == "__main__":
    unittest.main()
