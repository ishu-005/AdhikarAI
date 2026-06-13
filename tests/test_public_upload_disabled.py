import unittest

from backend.app import app


class PublicUploadDisabledTests(unittest.TestCase):
    def test_public_pdf_upload_route_is_not_registered(self):
        paths = {route.path for route in app.routes}

        self.assertNotIn("/api/upload-pdf", paths)


if __name__ == "__main__":
    unittest.main()
