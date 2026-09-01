from __future__ import annotations

import logging
import socket
import threading
import uuid
import base64
from typing import Any

from . import config
from .crypto import CryptoError, SessionCipher, b64_encode, derive_session_key, generate_x25519_keypair
from .discovery import discover_server
from .protocol import ProtocolError, recv_json_line, send_json
from .storage import EncryptedHistoryStore, derive_history_key

logger = logging.getLogger(__name__)


class ChatClient:
    def __init__(self, username: str, room: str, room_password: str, host: str | None = None, port: int | None = None) -> None:
        self.username = username
        self.room = room
        self.room_password = room_password
        self.host = host
        self.port = port

        self.sock: socket.socket | None = None
        self.sock_file: Any | None = None
        self.cipher: SessionCipher | None = None
        self.stop_event = threading.Event()

        self.history_store: EncryptedHistoryStore | None = None

    def connect(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

        if self.host is None or self.port is None:
            self.host, self.port = discover_server()
        logger.info("Connecting to %s:%s", self.host, self.port)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(config.SOCKET_TIMEOUT)
        self.sock.connect((self.host, self.port))
        self.sock_file = self.sock.makefile("rb")

        server_hello = recv_json_line(self.sock_file)
        if server_hello.get("type") != "server_hello":
            raise ProtocolError("Invalid handshake from server")

        private_key, public_key = generate_x25519_keypair()
        send_json(self.sock, {"type": "client_hello", "client_pubkey": b64_encode(public_key)})

        session_key = derive_session_key(private_key, base64.b64decode(server_hello["server_pubkey"]))
        self.cipher = SessionCipher(session_key)

        send_json(
            self.sock,
            self.cipher.encrypt_obj(
                {
                    "type": "auth",
                    "username": self.username,
                    "room": self.room,
                    "room_password": self.room_password,
                }
            ),
        )

        auth_result = recv_json_line(self.sock_file)
        if auth_result.get("type") == "error":
            raise PermissionError(auth_result.get("reason", "Authentication failed"))

        auth = self.cipher.decrypt_obj(auth_result)
        if auth.get("type") != "auth_ok":
            raise PermissionError("Authentication rejected")
        self.room = auth["room"]
        print(f"Connected as {self.username} in room '{self.room}'. Users: {', '.join(auth.get('users', []))}")

        if config.HISTORY_ENABLED:
            key_source = self.room_password if self.room_password else self.username
            history_key = derive_history_key(key_source)
            self.history_store = EncryptedHistoryStore(
                db_path=config.HISTORY_DB_PATH,
                key=history_key,
                retention_days=config.HISTORY_RETENTION_DAYS,
                max_messages=config.HISTORY_MAX_MESSAGES,
            )

        # enable TCP keepalive at the OS level (best-effort)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        # start periodic application-level pings to keep NAT/firewalls from dropping idle connections
        self._keepalive_interval = 10.0
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def run(self) -> None:
        if self.sock is None or self.sock_file is None or self.cipher is None:
            raise RuntimeError("Client not connected")

        receiver = threading.Thread(target=self._recv_loop, daemon=True)
        receiver.start()

        print("Type /help for commands")
        try:
            while not self.stop_event.is_set():
                text = input("").strip()
                if not text:
                    continue
                if text == "/help":
                    print("Commands: /help /rooms /users /join <room> <password> /leave /history [n] /exit")
                    continue
                if text == "/rooms":
                    self._send_secure({"type": "list_rooms"})
                    continue
                if text == "/users":
                    self._send_secure({"type": "list_users"})
                    continue
                if text.startswith("/join "):
                    parts = text.split(maxsplit=2)
                    if len(parts) != 3:
                        print("Usage: /join <room> <password>")
                        continue
                    self._send_secure({"type": "join_room", "room": parts[1], "room_password": parts[2]})
                    continue
                if text == "/leave":
                    self._send_secure({"type": "leave_room"})
                    continue
                if text.startswith("/history"):
                    self._print_history(text)
                    continue
                if text == "/exit":
                    break

                message_id = str(uuid.uuid4())
                self._send_secure({"type": "chat", "message_id": message_id, "text": text})
                if self.history_store:
                    self.history_store.save_message(self.room, self.username, message_id, f"(me) {text}")
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            self.stop_event.set()
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass

    def _send_secure(self, payload: dict[str, Any]) -> None:
        if self.sock is None or self.cipher is None:
            return
        send_json(self.sock, self.cipher.encrypt_obj(payload))

    def _recv_loop(self) -> None:
        assert self.sock_file is not None and self.cipher is not None
        while not self.stop_event.is_set():
            try:
                frame = recv_json_line(self.sock_file)
                if frame.get("type") == "error":
                    print(f"Server error: {frame.get('reason', 'unknown')}")
                    self.stop_event.set()
                    break
                payload = self.cipher.decrypt_obj(frame)
                self._handle_payload(payload)
            except socket.timeout:
                # no data received within timeout; keep waiting instead of disconnecting
                continue
            except (ConnectionError, OSError, ProtocolError, CryptoError) as exc:
                print(f"Disconnected: {exc}")
                self.stop_event.set()
                break

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        msg_type = payload.get("type")
        if msg_type == "message":
            sender = payload["sender"]
            text = payload["text"]
            self.room = payload.get("room", self.room)
            print(f"[{self.room}] {sender}: {text}")
            if self.history_store:
                self.history_store.save_message(self.room, sender, payload["message_id"], text)
            return
        if msg_type == "ack":
            delivered = payload.get("delivered_count")
            if delivered is None:
                print(f"ACK {payload['message_id']}: {payload['status']}")
            else:
                print(f"ACK {payload['message_id']}: {payload['status']} to {delivered} client(s)")
            return
        if msg_type == "presence":
            print(
                f"[{payload['room']}] {payload['username']} {payload['action']}ed. "
                f"Online: {', '.join(payload.get('users', []))}"
            )
            return
        if msg_type == "rooms":
            rooms = payload.get("rooms", [])
            if not rooms:
                print("No active rooms")
                return
            print("Rooms:")
            for room in rooms:
                print(f" - {room['room']} ({room['members']} online)")
            return
        if msg_type == "users":
            users = payload.get("users", [])
            print(f"Users in {payload.get('room', self.room)}: {', '.join(users)}")
            return
        if msg_type == "room_joined":
            self.room = payload["room"]
            print(f"Switched to room '{self.room}'. Users: {', '.join(payload.get('users', []))}")
            return

    def _print_history(self, text: str) -> None:
        if not self.history_store:
            print("History disabled")
            return
        parts = text.split(maxsplit=1)
        limit = 10
        if len(parts) == 2 and parts[1].isdigit():
            limit = max(1, min(100, int(parts[1])))
        rows = self.history_store.get_recent(limit=limit)
        if not rows:
            print("No local history")
            return
        print(f"Last {len(rows)} message(s):")
        for row in reversed(rows):
            print(f"{row['created_at']} [{row['room']}] {row['sender']}: {row['text']}")

