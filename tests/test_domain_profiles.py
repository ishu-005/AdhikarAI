import unittest

from langchain_core.documents import Document

from backend.rag.domain_profiles import (
    build_domain_retrieval_plan,
    build_support_requirements,
    classify_query_intent,
    dedupe_ranked_documents,
    rank_documents_for_intent,
)


class DomainProfilesTests(unittest.TestCase):
    def test_rti_query_gets_domain_specific_retrieval_aspects(self):
        plan = build_domain_retrieval_plan("PIO has not replied to my RTI application", "rti")

        self.assertEqual(plan.primary_domain, "rti")
        self.assertGreaterEqual(plan.context_limit, 5)
        joined = " ".join(q.query for q in plan.queries).lower()
        self.assertIn("first appeal", joined)
        self.assertIn("information commission", joined)
        self.assertTrue(all(q.domain == "rti" for q in plan.queries))

    def test_women_family_threat_adds_criminal_law_secondary_query(self):
        plan = build_domain_retrieval_plan("My husband is threatening me", "women_family")

        self.assertIn("women_family", {q.domain for q in plan.queries})
        self.assertIn("criminal_law", {q.domain for q in plan.queries})
        joined = " ".join(q.query for q in plan.queries).lower()
        self.assertIn("protection officer", joined)
        self.assertIn("criminal intimidation", joined)
        self.assertIn("application to magistrate", joined)
        self.assertIn("domestic incident report", joined)

    def test_query_intent_exposes_domain_intent_aspects_and_secondary_domains(self):
        intent = classify_query_intent("My husband is threatening me", "women_family")

        self.assertEqual(intent.domain, "women_family")
        self.assertEqual(intent.intent, "domestic_violence")
        self.assertIn("procedure", intent.aspects)
        self.assertIn("criminal_law", intent.secondary_domains)

    def test_rti_query_intent_prefers_appeal_when_no_reply(self):
        intent = classify_query_intent("PIO has not replied to my RTI application", "rti")

        self.assertEqual(intent.domain, "rti")
        self.assertEqual(intent.intent, "appeal")
        self.assertIn("timeline", intent.aspects)
        self.assertIn("procedure", intent.aspects)

    def test_broad_discrimination_query_requires_clarification(self):
        intent = classify_query_intent("Discrimination by authority", "human_rights")

        self.assertTrue(intent.needs_clarification)
        self.assertEqual(intent.intent, "ambiguous_discrimination")
        self.assertIn("Disability", intent.clarification_choices)
        self.assertIn("Caste", intent.clarification_choices)
        self.assertIn("Police/Government abuse", intent.clarification_choices)

    def test_specific_disability_discrimination_does_not_require_clarification(self):
        intent = classify_query_intent("Disability discrimination by public authority", "human_rights")

        self.assertFalse(intent.needs_clarification)
        self.assertEqual(intent.intent, "disability")

    def test_fir_refusal_profile_mentions_sp_and_magistrate_procedure(self):
        plan = build_domain_retrieval_plan("Police refused FIR", "criminal_law")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertIn("superintendent of police", joined)
        self.assertIn("magistrate", joined)
        self.assertIn("refusal to register fir", joined)

    def test_fir_refusal_profile_prioritizes_fir_and_procedure_queries(self):
        plan = build_domain_retrieval_plan("Police refused FIR", "criminal_law")

        self.assertEqual([query.aspect for query in plan.queries[:2]], ["fir", "procedure"])

    def test_fir_refusal_reranks_procedure_chunks_above_witness_threat_chunks(self):
        witness = Document(
            page_content="Section 216. Threatening any person to give false evidence as a witness.",
            metadata={"source": "bns"},
        )
        procedure = Document(
            page_content="If police refuse to register an FIR, send the complaint to the Superintendent of Police or approach the Magistrate.",
            metadata={"source": "bnss"},
        )

        ranked = rank_documents_for_intent("Police refused FIR", "criminal_law", [witness, procedure])

        self.assertEqual(ranked[0].page_content, procedure.page_content)

    def test_religious_discrimination_profile_mentions_minority_and_constitutional_terms(self):
        plan = build_domain_retrieval_plan(
            "Religious discrimination by public authority",
            "human_rights",
        )
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertIn("minority rights", joined)
        self.assertIn("freedom of religion", joined)
        self.assertIn("constitutional remedy", joined)

    def test_support_requirements_mark_missing_fir_escalation_procedure(self):
        docs = [
            Document(
                page_content="Section 216. Threatening any person to give false evidence as a witness.",
                metadata={"source": "bns"},
            )
        ]

        block = build_support_requirements("Police refused FIR", "criminal_law", docs)

        self.assertIn("source missing for exact FIR escalation procedure", block)

    def test_each_core_domain_adds_remedy_procedure_query(self):
        expectations = {
            "consumer": "consumer commission",
            "labour": "labour authority",
            "criminal_law": "fir procedure",
            "property_finance": "registrar",
            "rti": "first appeal",
        }

        for domain, expected in expectations.items():
            with self.subTest(domain=domain):
                plan = build_domain_retrieval_plan("What can I do next?", domain)
                joined = " ".join(q.query for q in plan.queries).lower()

                self.assertIn("procedure", joined)
                self.assertIn(expected, joined)

    def test_dedupe_ranked_documents_balances_query_groups(self):
        first = Document(page_content="Domestic violence protection order", metadata={"source": "a"})
        duplicate = Document(page_content="Domestic violence protection order", metadata={"source": "a"})
        second = Document(page_content="Criminal intimidation FIR", metadata={"source": "b"})
        third = Document(page_content="Residence order", metadata={"source": "c"})

        docs = dedupe_ranked_documents([[first, duplicate, third], [second]], limit=3)

        self.assertEqual([d.page_content for d in docs], [
            "Domestic violence protection order",
            "Criminal intimidation FIR",
            "Residence order",
        ])


if __name__ == "__main__":
    unittest.main()
