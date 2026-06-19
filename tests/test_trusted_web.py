import unittest
from unittest.mock import Mock, patch

from backend.core.web import _best_snippet, _is_trusted_url, live_fetch_for_domain


class TrustedWebTests(unittest.TestCase):
    def test_best_snippet_focuses_around_query_terms(self):
        text = "Intro text. " * 50 + (
            "Section 173 says information relating to cognizable offence may be given to an officer in charge "
            "of a police station and Zero FIR can be registered."
        )

        snippet = _best_snippet(text, "How do I file a FIR", fallback_terms=["zero fir", "cognizable offence"])

        self.assertIn("Section 173", snippet)
        self.assertIn("Zero FIR", snippet)

    def test_trusted_url_allows_official_sources_and_blocks_random_sites(self):
        self.assertTrue(_is_trusted_url("https://www.mha.gov.in/sites/default/files/bnss.pdf"))
        self.assertTrue(_is_trusted_url("https://www.indiacode.nic.in/handle/123456789/20062"))
        self.assertFalse(_is_trusted_url("https://random-blog.example/fir-guide"))

    def test_live_fetch_skips_untrusted_configured_source(self):
        links = [
            {
                "url": "https://random-blog.example/fir-guide",
                "label": "Random FIR Guide",
                "domain": "criminal_law",
                "enabled": True,
            },
            {
                "url": "https://www.mha.gov.in/sites/default/files/bnss.pdf",
                "label": "BNSS PDF",
                "domain": "criminal_law",
                "enabled": True,
            },
        ]

        with (
            patch("backend.core.web.load_links_config", return_value=links),
            patch("backend.core.web.fetch_page_text", return_value="Section 173 Zero FIR cognizable offence") as fetch,
        ):
            sources = live_fetch_for_domain("criminal_law", query="How do I file a FIR", max_sources=3)

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["official"], True)
        self.assertEqual(sources[0]["source_type"], "official_legal_web")


if __name__ == "__main__":
    unittest.main()
