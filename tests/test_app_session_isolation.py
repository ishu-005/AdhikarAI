import unittest

from fastapi.testclient import TestClient

from backend.app import app
from backend.core import chat_store


class AppSessionIsolationTests(unittest.TestCase):
    def setUp(self):
        self._client_fn = chat_store.get_supabase_client
        chat_store.get_supabase_client = lambda: None
        with chat_store._lock:
            chat_store._threads.clear()
            chat_store._metadata.clear()
        self.client = TestClient(app)

    def tearDown(self):
        chat_store.get_supabase_client = self._client_fn

    def test_chat_endpoints_are_scoped_by_browser_session(self):
        first = self.client.post("/api/chat/new", headers={"X-AdhikarAI-Session": "browser-one"})
        second = self.client.post("/api/chat/new", headers={"X-AdhikarAI-Session": "browser-two"})
        first.raise_for_status()
        second.raise_for_status()
        first_id = first.json()["conversation_id"]
        second_id = second.json()["conversation_id"]

        first_list = self.client.get("/api/chats", headers={"X-AdhikarAI-Session": "browser-one"})
        first_read_other = self.client.get(
            f"/api/chat/{second_id}", headers={"X-AdhikarAI-Session": "browser-one"}
        )

        self.assertEqual([item["id"] for item in first_list.json()["chats"]], [first_id])
        self.assertEqual(first_read_other.json()["messages"], [])


if __name__ == "__main__":
    unittest.main()
