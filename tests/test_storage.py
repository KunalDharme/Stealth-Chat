import os
import sqlite3
import tempfile
import unittest

from stealth_chat.storage import EncryptedHistoryStore, derive_history_key


class StorageTests(unittest.TestCase):
    def test_encrypted_storage_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "history.db")
            store = EncryptedHistoryStore(db_path, derive_history_key("secret"), retention_days=7, max_messages=100)
            store.save_message("general", "alice", "id-1", "hello")

            rows = store.get_recent(limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "hello")

            with sqlite3.connect(db_path) as conn:
                raw = conn.execute("SELECT ciphertext FROM messages WHERE message_id='id-1'").fetchone()[0]
                self.assertNotIn(b"hello", raw)


if __name__ == "__main__":
    unittest.main()
