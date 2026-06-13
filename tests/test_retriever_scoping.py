import unittest
from unittest.mock import patch

from backend.rag.retriever import build_retriever


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


if __name__ == "__main__":
    unittest.main()
