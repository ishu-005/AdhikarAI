import unittest

from backend.core import chat_store


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self._client_fn = chat_store.get_supabase_client
        chat_store.get_supabase_client = lambda: None
        with chat_store._lock:
            chat_store._threads.clear()
            chat_store._metadata.clear()

    def tearDown(self):
        chat_store.get_supabase_client = self._client_fn

    def test_append_first_user_message_generates_summary_title(self):
        convo_id = chat_store.create_conversation()

        chat_store.append_message(convo_id, "user", "How do I file an RTI application?", {"domain": "rti", "language": "en"})

        summaries = chat_store.list_conversations()
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["id"], convo_id)
        self.assertEqual(summaries[0]["title"], "RTI Filing Help")
        self.assertEqual(summaries[0]["message_count"], 1)
        self.assertEqual(summaries[0]["domain"], "rti")
        self.assertEqual(summaries[0]["language"], "en")

    def test_rename_conversation_updates_in_memory_summary(self):
        convo_id = chat_store.create_conversation()
        chat_store.append_message(convo_id, "user", "Police arrested my friend", {"domain": "criminal_law"})

        chat_store.rename_conversation(convo_id, "Urgent Arrest Help")

        self.assertEqual(chat_store.list_conversations()[0]["title"], "Urgent Arrest Help")

    def test_conversations_are_scoped_by_owner(self):
        owner_one_chat = chat_store.create_conversation(owner_id="browser-one")
        owner_two_chat = chat_store.create_conversation(owner_id="browser-two")
        chat_store.append_message(owner_one_chat, "user", "How do I file RTI?", {"domain": "rti"})
        chat_store.append_message(owner_two_chat, "user", "Police refused FIR", {"domain": "criminal_law"})

        owner_one_summaries = chat_store.list_conversations(owner_id="browser-one")

        self.assertEqual([item["id"] for item in owner_one_summaries], [owner_one_chat])
        self.assertEqual(len(chat_store.get_conversation(owner_two_chat, owner_id="browser-one")), 0)

    def test_get_conversation_returns_defensive_message_copies(self):
        convo_id = chat_store.create_conversation(owner_id="browser-one")
        chat_store.append_message(convo_id, "user", "Police refused FIR", {"domain": "criminal_law"})

        messages = chat_store.get_conversation(convo_id, owner_id="browser-one")
        messages[0]["meta"]["domain"] = "mutated"

        fresh = chat_store.get_conversation(convo_id, owner_id="browser-one")
        self.assertEqual(fresh[0]["meta"]["domain"], "criminal_law")


if __name__ == "__main__":
    unittest.main()
