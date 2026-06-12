import unittest
from types import SimpleNamespace

from backend.rag.citations import build_citations


class CitationTests(unittest.TestCase):
    def test_build_citations_prefers_section_and_filename_metadata(self):
        docs = [
            SimpleNamespace(
                page_content="Section text",
                metadata={
                    "title": "Right To Information Act, 2005",
                    "source": "pdf",
                    "domain": "citizen_rights",
                    "similarity": 0.87,
                    "metadata": {
                        "section": "Section 6: Request for obtaining information",
                        "filename": "RTI_Act_2005.pdf",
                        "chunk_index": 12,
                    },
                },
            )
        ]

        chunks, citations = build_citations(docs)

        self.assertEqual(chunks, ["[1] Section text"])
        self.assertEqual(citations[0]["section"], "Section 6: Request for obtaining information")
        self.assertEqual(citations[0]["source"], "RTI_Act_2005.pdf")
        self.assertEqual(citations[0]["title"], "Right To Information Act, 2005")
        self.assertEqual(citations[0]["chunk_index"], 12)
        self.assertEqual(citations[0]["score"], 0.87)


if __name__ == "__main__":
    unittest.main()
