import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from backend.rag.retriever import _fuse_documents, build_retriever


class RetrieverScopingTests(unittest.TestCase):
    def test_scoped_retriever_uses_requested_domain(self):
        with (
            patch("backend.rag.retriever._get_reranker", return_value=None),
            patch("backend.rag.retriever.get_settings") as get_settings,
        ):
            settings = get_settings.return_value
            settings.top_k = 5
            settings.retrieve_multiplier = 3
            settings.retrieval_domain_filter = False
            settings.hybrid_enabled = False
            retriever = build_retriever("women_family", scoped=True)

        self.assertEqual(retriever.domain, "women_family")

    def test_unscoped_retriever_preserves_legacy_general_search(self):
        with (
            patch("backend.rag.retriever._get_reranker", return_value=None),
            patch("backend.rag.retriever.get_settings") as get_settings,
        ):
            settings = get_settings.return_value
            settings.top_k = 5
            settings.retrieve_multiplier = 3
            settings.retrieval_domain_filter = False
            settings.hybrid_enabled = False
            retriever = build_retriever("women_family", scoped=False)

        self.assertEqual(retriever.domain, "general")

    def test_fuse_documents_keeps_keyword_only_fir_section(self):
        vector_doc = Document(
            page_content="Section 216. Procedure for witnesses in case of threatening.",
            metadata={"source": "bnss", "title": "Witness procedure", "similarity": 0.55},
        )
        fulltext_doc = Document(
            page_content="Section 173. Information in cognizable cases may be given to an officer in charge of a police station.",
            metadata={"source": "bnss", "title": "Information in cognizable cases", "similarity": 0.0},
        )

        fused = _fuse_documents([vector_doc], [fulltext_doc], vector_weight=0.6, fulltext_weight=0.4)

        self.assertIn(fulltext_doc, fused)
        self.assertEqual(len(fused), 2)

    def test_hybrid_retriever_does_not_depend_on_langchain_ensemble_import(self):
        with (
            patch("backend.rag.retriever._get_reranker", return_value=None),
            patch("backend.rag.retriever.get_settings") as get_settings,
        ):
            settings = get_settings.return_value
            settings.top_k = 5
            settings.retrieve_multiplier = 3
            settings.retrieval_domain_filter = False
            settings.hybrid_enabled = True
            settings.vector_weight = 0.6
            settings.fulltext_weight = 0.4
            retriever = build_retriever("criminal_law", scoped=True)

        self.assertEqual(retriever.__class__.__name__, "_HybridRetriever")


if __name__ == "__main__":
    unittest.main()
