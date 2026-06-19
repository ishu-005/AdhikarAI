import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from backend.rag.prompts import fallback_answer
from backend.core.chat_intelligence import plan_query
from backend.rag.pipeline import _assemble, _expand_retrieval_query, _retrieve_with_profile, answer_query


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

    def test_basic_rights_uses_educational_answer_without_problem_actions(self):
        with patch("backend.rag.pipeline.retrieve") as retrieve:
            result = answer_query("What are my basic rights?", "citizen_rights", "en", history=[])

        retrieve.assert_not_called()
        self.assertEqual(result["diagnostics"]["query_type"], "legal_knowledge")
        self.assertEqual(result["diagnostics"]["answer_style"], "educational")
        self.assertIn("Right to Equality", result["answer"])
        self.assertIn("Right to Constitutional Remedies", result["answer"])
        self.assertNotIn("Contact NHRC", result["answer"])
        self.assertNotIn("Approach High Court", result["answer"])

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
            patch("backend.rag.pipeline.retrieve", side_effect=[[witness_doc], [], [], [], []]),
        ):
            ctx = _assemble(question, "criminal_law", "en", plan)

        self.assertIn(
            "retrieved legal sources do not provide additional guidance on the exact FIR escalation procedure",
            ctx["prompt_vars"]["support_block"],
        )
        self.assertNotIn("source missing", ctx["prompt_vars"]["support_block"].lower())

    def test_retrieval_profile_ranks_each_query_group_before_merging(self):
        noise_1 = Document(page_content="Section 256 public servant record entry.", metadata={"source": "bns-1"})
        noise_2 = Document(page_content="Section 284 summary trial by Magistrate of second class.", metadata={"source": "bnss-2"})
        noise_3 = Document(page_content="Section 113 unrelated threat offence.", metadata={"source": "bns-3"})
        noise_4 = Document(page_content="Section 175 unrelated election false statement.", metadata={"source": "bns-4"})
        noise_5 = Document(page_content="Section 336 false document unrelated offence.", metadata={"source": "bns-5"})
        section_38 = Document(
            page_content="Section 38. Right of arrested person to meet an advocate during interrogation.",
            metadata={"source": "bnss"},
        )
        section_47 = Document(
            page_content="Section 47. Person arrested to be informed of grounds of arrest and right to bail.",
            metadata={"source": "bnss"},
        )
        section_48 = Document(
            page_content="Section 48. Obligation to inform relative or friend of the arrested person.",
            metadata={"source": "bnss"},
        )
        section_58 = Document(
            page_content="Section 58. Person arrested not to be detained more than twenty four hours before Magistrate.",
            metadata={"source": "bnss"},
        )
        section_53 = Document(
            page_content="Section 53. Examination of arrested person by medical officer.",
            metadata={"source": "bnss"},
        )

        with patch(
            "backend.rag.pipeline.retrieve",
            side_effect=[
                [noise_1, section_38],
                [section_47],
                [noise_2, section_48],
                [noise_3, section_58],
                [section_53],
                [noise_4, noise_5],
            ],
        ):
            docs, _blocks, _limit = _retrieve_with_profile("What are my rights if police arrest me?", "criminal_law")

        joined = " ".join(doc.page_content.lower() for doc in docs)
        self.assertIn("section 38", joined)
        self.assertIn("section 47", joined)
        self.assertIn("section 48", joined)
        self.assertIn("section 58", joined)
        self.assertIn("section 53", joined)
        self.assertLess(joined.index("section 48"), joined.index("section 256"))

    def test_response_format_uses_professional_missing_source_wording(self):
        question = "Police refused FIR"
        plan = plan_query(question, [], "en")

        with (
            patch("backend.rag.pipeline.live_fetch_for_domain", return_value=[]),
            patch("backend.rag.pipeline.retrieve", side_effect=[[], [], [], [], []]),
        ):
            ctx = _assemble(question, "criminal_law", "en", plan)

        self.assertIn("retrieved legal sources do not provide additional guidance on this point", ctx["prompt_vars"]["response_format"])
        self.assertNotIn("source missing", ctx["prompt_vars"]["response_format"].lower())

    def test_strong_database_context_skips_trusted_web_fallback(self):
        question = "How do I file RTI?"
        plan = plan_query(question, [], "en")
        doc = Document(
            page_content="Section 6 request for obtaining information through public information officer.",
            metadata={
                "domain": "rti",
                "source": "rti_act",
                "title": "Right to Information Act, 2005",
                "similarity": 0.91,
                "metadata": {"section": "Section 6", "act_name": "Right to Information Act, 2005"},
            },
        )

        with (
            patch("backend.rag.pipeline.live_fetch_for_domain", return_value=[]) as live_fetch,
            patch("backend.rag.pipeline.retrieve", side_effect=[[doc], [doc], [doc]]),
        ):
            ctx = _assemble(question, "rti", "en", plan)

        live_fetch.assert_not_called()
        self.assertEqual(ctx["diagnostics"]["source_confidence"]["level"], "strong")
        self.assertFalse(ctx["diagnostics"]["source_confidence"]["used_web_fallback"])

    def test_missing_database_context_uses_trusted_web_fallback(self):
        question = "Where can I file RTI online?"
        plan = plan_query(question, [], "en")
        live_source = {
            "label": "RTI Filing Portal",
            "url": "https://rtionline.gov.in",
            "snippet": "Official RTI online filing portal.",
            "trusted": True,
        }

        with (
            patch("backend.rag.pipeline.live_fetch_for_domain", return_value=[live_source]) as live_fetch,
            patch("backend.rag.pipeline.retrieve", side_effect=[[], [], []]),
        ):
            ctx = _assemble(question, "rti", "en", plan)

        live_fetch.assert_called_once()
        self.assertEqual(live_fetch.call_args.args[0], "rti")
        self.assertEqual(live_fetch.call_args.kwargs["query"], question)
        self.assertEqual(ctx["diagnostics"]["source_confidence"]["level"], "web_fallback")
        self.assertTrue(ctx["diagnostics"]["source_confidence"]["used_web_fallback"])
        self.assertEqual(ctx["live_chunks"], [live_source])


if __name__ == "__main__":
    unittest.main()
