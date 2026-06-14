import unittest

from backend.core.chat_intelligence import plan_query, split_legal_issues


class QueryPlanningTests(unittest.TestCase):
    def test_smalltalk_does_not_need_retrieval(self):
        plan = plan_query("Tell me about yourself", [], "en")

        self.assertEqual(plan.query_type, "smalltalk")
        self.assertFalse(plan.needs_retrieval)
        self.assertEqual(plan.domain_hint, "general")

    def test_retry_uses_previous_legal_question(self):
        history = [{"role": "user", "content": "Police refused to register my FIR. What can I do?"}]
        plan = plan_query("rety", history, "en")

        self.assertEqual(plan.query_type, "followup")
        self.assertTrue(plan.needs_retrieval)
        self.assertTrue(plan.rewritten)
        self.assertIn("Police refused", plan.question)

    def test_multi_issue_query_is_split_into_actionable_issues(self):
        query = (
            "My employer is not paying my salary. My landlord is refusing to return my security deposit. "
            "I received a defective product. My husband is threatening me. Police refused to register my FIR."
        )
        issues = split_legal_issues(query)

        self.assertGreaterEqual(len(issues), 5)
        self.assertIn("salary", " ".join(issues).lower())
        self.assertIn("security deposit", " ".join(issues).lower())
        self.assertIn("defective product", " ".join(issues).lower())
        self.assertIn("threatening", " ".join(issues).lower())
        self.assertIn("FIR", " ".join(issues))

        plan = plan_query(query, [], "en")
        self.assertEqual(plan.query_type, "legal_multi_issue")
        self.assertTrue(plan.needs_retrieval)
        self.assertGreaterEqual(len(plan.issues), 5)

    def test_non_legal_chitchat_stays_out_of_rag(self):
        plan = plan_query("or btao", [], "en")

        self.assertFalse(plan.needs_retrieval)
        self.assertEqual(plan.query_type, "smalltalk")

    def test_domestic_threat_typo_routes_to_women_family(self):
        plan = plan_query("my husband is threatning me", [], "en")

        self.assertTrue(plan.needs_retrieval)
        self.assertEqual(plan.query_type, "legal_single")
        self.assertEqual(plan.domain_hint, "women_family")

    def test_basic_rights_routes_as_educational_knowledge_without_retrieval(self):
        plan = plan_query("What are my basic rights?", [], "en")

        self.assertEqual(plan.query_type, "legal_knowledge")
        self.assertFalse(plan.needs_retrieval)
        self.assertEqual(plan.domain_hint, "citizen_rights")
        self.assertEqual(plan.answer_style, "educational")

    def test_explain_rti_routes_as_retrieved_legal_knowledge(self):
        plan = plan_query("Explain RTI Act", [], "en")

        self.assertEqual(plan.query_type, "legal_knowledge")
        self.assertTrue(plan.needs_retrieval)
        self.assertEqual(plan.domain_hint, "rti")
        self.assertEqual(plan.answer_style, "educational")

    def test_clarification_choice_is_saved_without_retrieval(self):
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
                            "clarifying_question": "What type of discrimination is this?",
                            "clarification_choices": ["Disability", "Caste", "Gender", "Religion", "Police/Government abuse", "Other"],
                        }
                    }
                },
            },
        ]

        plan = plan_query("Caste", history, "en")

        self.assertFalse(plan.needs_retrieval)
        self.assertEqual(plan.query_type, "clarification_ack")
        self.assertEqual(plan.domain_hint, "human_rights")
        self.assertEqual(plan.clarification_state["intent"], "caste_discrimination")

    def test_followup_after_clarification_choice_runs_retrieval_context(self):
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
            {"role": "user", "content": "Caste"},
            {
                "role": "assistant",
                "content": "Please share what happened.",
                "meta": {
                    "diagnostics": {
                        "query_type": "clarification_ack",
                        "clarification_state": {
                            "domain": "human_rights",
                            "intent": "caste_discrimination",
                            "label": "Caste",
                            "base_question": "Discrimination by authority",
                            "awaiting_details": True,
                        },
                    }
                },
            },
        ]

        plan = plan_query("Authority favors same caste", history, "en")

        self.assertTrue(plan.needs_retrieval)
        self.assertTrue(plan.rewritten)
        self.assertEqual(plan.domain_hint, "human_rights")
        self.assertIn("Caste discrimination by authority", plan.question)
        self.assertIn("Authority favors same caste", plan.question)

    def test_new_legal_topic_resets_pending_clarification_details(self):
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
            {"role": "user", "content": "Religion"},
            {
                "role": "assistant",
                "content": "Please share what happened.",
                "meta": {
                    "diagnostics": {
                        "query_type": "clarification_ack",
                        "clarification_state": {
                            "domain": "human_rights",
                            "intent": "religious_discrimination",
                            "label": "Religion",
                            "topic": "Religious discrimination by authority",
                            "base_question": "Discrimination by authority",
                            "awaiting_details": True,
                        },
                    }
                },
            },
        ]

        plan = plan_query("Police refused FIR", history, "en")

        self.assertEqual(plan.query_type, "legal_single")
        self.assertTrue(plan.needs_retrieval)
        self.assertFalse(plan.rewritten)
        self.assertEqual(plan.domain_hint, "criminal_law")
        self.assertEqual(plan.question, "Police refused FIR")


if __name__ == "__main__":
    unittest.main()
