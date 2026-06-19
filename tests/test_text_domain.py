import unittest

from backend.core.text import detect_domain


class TextDomainTests(unittest.TestCase):
    def test_custodial_violence_routes_to_human_rights(self):
        domain, _ = detect_domain("Police beat me in custody")

        self.assertEqual(domain, "human_rights")


if __name__ == "__main__":
    unittest.main()
