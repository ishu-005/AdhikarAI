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


if __name__ == "__main__":
    unittest.main()
