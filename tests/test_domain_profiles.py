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

    def test_fir_filing_profile_mentions_zero_fir_and_cognizable_information(self):
        plan = build_domain_retrieval_plan("How do I file a FIR", "criminal_law")
        intent = classify_query_intent("How do I file a FIR", "criminal_law")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "fir_filing")
        self.assertIn("fir_filing_keyword", {q.aspect for q in plan.queries})
        self.assertIn("first information report", joined)
        self.assertIn("section 173 bnss", joined)
        self.assertIn("police complaint procedure", joined)
        self.assertIn("section 173 information in cognizable cases", joined)
        self.assertIn("zero fir", joined)
        self.assertIn("officer in charge", joined)
        self.assertIn("cognizable offence", joined)

    def test_fir_refusal_profile_uses_bnss_refusal_aliases(self):
        plan = build_domain_retrieval_plan("Police refused FIR", "criminal_law")
        intent = classify_query_intent("Police refused FIR", "criminal_law")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "fir_refusal")
        self.assertIn("fir_refusal_keyword", {q.aspect for q in plan.queries})
        self.assertIn("refusal on the part of an officer in charge", joined)
        self.assertIn("section 173 bnss", joined)
        self.assertIn("section 173(4)", joined)
        self.assertIn("section 175 bnss", joined)
        self.assertIn("magistrate complaint", joined)
        self.assertIn("escalation of fir refusal", joined)
        self.assertIn("first information report", joined)

    def test_fir_refusal_profile_prioritizes_fir_and_procedure_queries(self):
        plan = build_domain_retrieval_plan("Police refused FIR", "criminal_law")

        self.assertEqual(
            [query.aspect for query in plan.queries],
            ["fir_refusal", "fir_refusal_keyword", "fir_refusal_keyword", "fir_refusal_keyword", "fir_refusal_keyword"],
        )

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

    def test_fir_refusal_reranks_section_173_above_district_magistrate_sanction_chunk(self):
        sanction = Document(
            page_content="Section 217. Prosecution sanction may involve the District Magistrate.",
            metadata={"source": "bnss"},
        )
        refusal = Document(
            page_content=(
                "Section 173. Information in cognizable cases. If an officer in charge refuses to record "
                "information, send the substance of such information in writing to the Superintendent of Police."
            ),
            metadata={"source": "bnss"},
        )

        ranked = rank_documents_for_intent("Police refused FIR", "criminal_law", [sanction, refusal])

        self.assertEqual(ranked[0].page_content, refusal.page_content)
        self.assertNotIn(sanction, ranked)

    def test_support_requirements_give_fir_refusal_action_plan_when_supported(self):
        docs = [
            Document(
                page_content=(
                    "If refusal on the part of an officer in charge occurs, send the substance of information "
                    "in writing to the Superintendent of Police. A Magistrate may order investigation."
                ),
                metadata={"source": "bnss"},
            )
        ]

        block = build_support_requirements("Police refused FIR", "criminal_law", docs)

        lowered = block.lower()
        self.assertIn("send written complaint to the superintendent of police", lowered)
        self.assertIn("keep a copy and acknowledgement", lowered)
        self.assertIn("approach the magistrate", lowered)
        self.assertIn("preserve evidence", lowered)
        self.assertNotIn("district magistrate", lowered)
        self.assertNotIn("ask why", lowered)
        self.assertNotIn("give more information", lowered)

    def test_arrest_rights_profile_has_rights_specific_terms(self):
        plan = build_domain_retrieval_plan("What are my rights if police arrest me?", "criminal_law")
        intent = classify_query_intent("What are my rights if police arrest me?", "criminal_law")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "arrest_rights")
        self.assertIn("arrest_rights_keyword", {q.aspect for q in plan.queries})
        self.assertEqual(plan.queries[0].aspect, "arrest_rights_keyword")
        self.assertIn("section 38", joined)
        self.assertIn("section 47", joined)
        self.assertIn("section 48", joined)
        self.assertIn("section 58", joined)
        self.assertIn("rights of arrested person", joined)
        self.assertIn("grounds of arrest", joined)
        self.assertIn("advocate during interrogation", joined)
        self.assertIn("inform relative", joined)
        self.assertIn("twenty four hours", joined)

    def test_arrest_rights_reranks_rights_chunks_above_bail_chunks(self):
        bail = Document(
            page_content="A High Court or Court of Session may grant bail.",
            metadata={"source": "bnss"},
        )
        rights = Document(
            page_content=(
                "Arrested person shall be informed of grounds of arrest, may consult a legal practitioner, "
                "inform a relative, and be produced before Magistrate within twenty four hours."
            ),
            metadata={"source": "bnss"},
        )

        ranked = rank_documents_for_intent("What are my rights if police arrest me?", "criminal_law", [bail, rights])

        self.assertEqual(ranked[0].page_content, rights.page_content)
        self.assertNotIn("bail", ranked[0].page_content.lower())
        self.assertNotIn(bail, ranked)

    def test_support_requirements_give_arrest_rights_action_plan_when_supported(self):
        docs = [
            Document(
                page_content=(
                    "The arrested person must know grounds of arrest, consult a legal practitioner, "
                    "inform a relative, and be produced before Magistrate within 24 hours. "
                    "Medical examination may be requested where applicable."
                ),
                metadata={"source": "bnss"},
            )
        ]

        block = build_support_requirements("What are my rights if police arrest me?", "criminal_law", docs)
        lowered = block.lower()

        self.assertIn("know the grounds of arrest", lowered)
        self.assertIn("contact a lawyer", lowered)
        self.assertIn("inform a family member", lowered)
        self.assertIn("24 hours", lowered)
        self.assertIn("medical examination", lowered)
        self.assertNotIn("proclaimed offender", lowered)
        self.assertNotIn("trial in absence", lowered)
        self.assertNotIn("bail procedure", lowered)


    def test_fir_filing_reranks_section_173_above_unrelated_procedure_chunks(self):
        witness = Document(
            page_content="Section 216. Procedure for witnesses in case of threatening.",
            metadata={"source": "bnss"},
        )
        filing = Document(
            page_content=(
                "Section 173. Information in cognizable cases may be given orally or by "
                "electronic communication to an officer in charge of a police station."
            ),
            metadata={"source": "bnss"},
        )

        ranked = rank_documents_for_intent("How do I file FIR", "criminal_law", [witness, filing])

        self.assertEqual(ranked[0].page_content, filing.page_content)

    def test_religious_discrimination_profile_mentions_minority_and_constitutional_terms(self):
        plan = build_domain_retrieval_plan(
            "Religious discrimination by public authority",
            "human_rights",
        )
        intent = classify_query_intent("Religious discrimination by public authority", "human_rights")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "religious_discrimination")
        self.assertIn("religious_discrimination_keyword", {q.aspect for q in plan.queries})
        self.assertIn("article 25", joined)
        self.assertIn("article 26", joined)
        self.assertIn("minority rights", joined)
        self.assertIn("freedom of religion", joined)
        self.assertIn("constitutional remedy", joined)

    def test_caste_discrimination_profile_mentions_sc_st_and_article_17(self):
        plan = build_domain_retrieval_plan("Caste discrimination by authority", "human_rights")
        intent = classify_query_intent("Caste discrimination by authority", "human_rights")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "caste_discrimination")
        self.assertIn("caste_discrimination_keyword", {q.aspect for q in plan.queries})
        self.assertIn("sc/st", joined)
        self.assertIn("untouchability", joined)
        self.assertIn("article 14", joined)
        self.assertIn("article 15", joined)
        self.assertIn("article 17", joined)
        self.assertIn("sc/st protections", joined)
        self.assertIn("equality", joined)

    def test_custodial_violence_profile_mentions_commission_complaint_and_compensation(self):
        plan = build_domain_retrieval_plan("Police beat me in custody", "human_rights")
        intent = classify_query_intent("Police beat me in custody", "human_rights")
        joined = " ".join(q.query for q in plan.queries).lower()

        self.assertEqual(intent.intent, "custodial_violence")
        self.assertIn("custodial_violence_keyword", {q.aspect for q in plan.queries})
        self.assertIn("human rights commission", joined)
        self.assertIn("custodial violence", joined)
        self.assertIn("custodial torture", joined)
        self.assertIn("police abuse", joined)
        self.assertIn("complaint against police", joined)
        self.assertIn("nhrc complaint", joined)
        self.assertIn("complaint procedure", joined)
        self.assertIn("compensation", joined)

    def test_support_requirements_mark_missing_fir_escalation_procedure(self):
        docs = [
            Document(
                page_content="Section 216. Threatening any person to give false evidence as a witness.",
                metadata={"source": "bns"},
            )
        ]

        block = build_support_requirements("Police refused FIR", "criminal_law", docs)

        self.assertIn("retrieved legal sources do not provide additional guidance on the exact FIR escalation procedure", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_accept_arrest_rights_context(self):
        docs = [
            Document(
                page_content=(
                    "The arrested person must know grounds of arrest, consult a legal practitioner, "
                    "inform a relative, and be produced before Magistrate within 24 hours."
                ),
                metadata={"source": "bnss"},
            )
        ]

        block = build_support_requirements("What are my rights if police arrest me?", "criminal_law", docs)

        self.assertIn("Arrest-rights context appears supported", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_accept_fir_filing_procedure_context(self):
        docs = [
            Document(
                page_content=(
                    "Section 173. Information in cognizable cases may be given orally or by electronic "
                    "communication to an officer in charge of a police station, and a Zero FIR may be registered."
                ),
                metadata={"source": "bnss"},
            )
        ]

        block = build_support_requirements("How do I file a FIR", "criminal_law", docs)

        self.assertIn("FIR filing procedure appears supported", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_mark_religious_discrimination_constitution_gap(self):
        docs = [
            Document(
                page_content=(
                    "The Protection of Human Rights Act mentions complaints involving minorities "
                    "and powers of the Human Rights Commission."
                ),
                metadata={"source": "human_rights"},
            )
        ]

        block = build_support_requirements("Religious discrimination by public authority", "human_rights", docs)

        self.assertIn(
            "Article 25, Article 26, freedom of religion, or minority-rights remedies",
            block,
        )
        self.assertNotIn("Religious discrimination context appears supported", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_accept_religious_discrimination_constitution_context(self):
        docs = [
            Document(
                page_content=(
                    "Article 25 protects freedom of religion. Article 26 protects religious denominations. "
                    "Minority rights and constitutional remedies may be relevant."
                ),
                metadata={"source": "constitution"},
            )
        ]

        block = build_support_requirements("Religious discrimination by public authority", "human_rights", docs)

        self.assertIn("Religious discrimination context appears supported", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_mark_caste_discrimination_constitution_gap(self):
        docs = [
            Document(
                page_content=(
                    "The Human Rights Commission may inquire into complaints and may refer matters "
                    "concerning Scheduled Castes to appropriate authorities."
                ),
                metadata={"source": "human_rights"},
            )
        ]

        block = build_support_requirements("Caste discrimination by government officer", "human_rights", docs)

        self.assertIn(
            "Article 14, Article 15, Article 17, untouchability, or SC/ST protections",
            block,
        )
        self.assertNotIn("Caste discrimination context appears supported", block)
        self.assertNotIn("source missing", block.lower())

    def test_support_requirements_accept_caste_discrimination_constitution_context(self):
        docs = [
            Document(
                page_content=(
                    "Article 14 protects equality. Article 15 prohibits discrimination. "
                    "Article 17 abolishes untouchability. SC/ST protections may apply."
                ),
                metadata={"source": "constitution"},
            )
        ]

        block = build_support_requirements("Caste discrimination by government officer", "human_rights", docs)

        self.assertIn("Caste discrimination context appears supported", block)
        self.assertNotIn("source missing", block.lower())

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
