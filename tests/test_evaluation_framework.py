import unittest
from pathlib import Path

from evaluation.evaluate_retrieval import evaluate_cases, load_cases


class EvaluationFrameworkTests(unittest.TestCase):
    def test_evaluate_cases_scores_domain_intent_and_aspects(self):
        cases = [
            {
                "query": "My husband is threatening me",
                "expected_domain": "women_family",
                "expected_intent": "domestic_violence",
                "expected_aspects": ["procedure"],
                "expected_secondary_domains": ["criminal_law"],
            },
            {
                "query": "PIO has not replied to my RTI application",
                "expected_domain": "rti",
                "expected_intent": "appeal",
                "expected_aspects": ["timeline", "procedure"],
            },
            {
                "query": "Discrimination by authority",
                "expected_domain": "human_rights",
                "expected_intent": "ambiguous_discrimination",
                "expected_needs_clarification": True,
            },
        ]

        result = evaluate_cases(cases, run_retrieval=False)

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["domain_accuracy"], 1.0)
        self.assertEqual(result["intent_accuracy"], 1.0)
        self.assertEqual(result["aspect_recall"], 1.0)
        self.assertEqual(result["secondary_domain_recall"], 1.0)
        self.assertEqual(result["clarification_accuracy"], 1.0)
        self.assertEqual(len(result["cases"]), 3)
        self.assertIn("retrieval_inspection", result["cases"][0])

    def test_seed_query_set_is_currently_passing_offline(self):
        cases = load_cases(Path("evaluation/test_queries.json"))

        result = evaluate_cases(cases, run_retrieval=False)

        self.assertEqual(result["domain_accuracy"], 1.0)
        self.assertEqual(result["intent_accuracy"], 1.0)
        self.assertEqual(result["aspect_recall"], 1.0)
        self.assertEqual(result["secondary_domain_recall"], 1.0)
        self.assertEqual(result["clarification_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
