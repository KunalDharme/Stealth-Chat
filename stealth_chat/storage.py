from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive_history_key(secret: str, salt: bytes = b"stealth-chat-history-v1") -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        200_000,
        dklen=32,
    )


class EncryptedHistoryStore:
    def __init__(self, db_path: str, key: bytes, retention_days: int, max_messages: int) -> None:
        self.db_path = db_path
        self.key = key
        self.retention_days = retention_days
        self.max_messages = max_messages
        self._aead = AESGCM(self.key)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    room TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message_id TEXT NOT NULL UNIQUE,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                )
                """
            )

    def save_message(self, room: str, sender: str, message_id: str, text: str) -> None:
        nonce = os.urandom(12)
        ciphertext = self._aead.encrypt(nonce, text.encode("utf-8"), None)
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO messages (created_at, room, sender, message_id, nonce, ciphertext)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (created_at, room, sender, message_id, nonce, ciphertext),
            )
            self._apply_retention(conn)

    def _apply_retention(self, conn: sqlite3.Connection) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
        row = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        count = int(row[0]) if row else 0
        if count > self.max_messages:
            to_delete = count - self.max_messages
            conn.execute(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages ORDER BY id ASC LIMIT ?
                )
                """,
                (to_delete,),
            )

    def get_recent(self, limit: int = 20) -> list[dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT created_at, room, sender, message_id, nonce, ciphertext
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        output: list[dict[str, str]] = []
        for created_at, room, sender, message_id, nonce, ciphertext in rows:
            text = self._aead.decrypt(nonce, ciphertext, None).decode("utf-8")
            output.append(
                {
                    "created_at": created_at,
                    "room": room,
                    "sender": sender,
                    "message_id": message_id,
                    "text": text,
                }
            )
        return output
