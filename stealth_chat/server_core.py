from __future__ import annotations

import logging
import socket
import threading
import time
import base64
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import config
from .auth import AuthRateLimiter, RoomManager
from .crypto import CryptoError, SessionCipher, b64_encode, derive_session_key, generate_x25519_keypair
from .discovery import DiscoveryResponder
from .protocol import ProtocolError, recv_json_line, safe_str, send_json, validate_username

logger = logging.getLogger(__name__)


@dataclass
class ClientSession:
    sock: socket.socket
    file: Any
    ip: str
    username: str
    room: str
    cipher: SessionCipher
    seen_ids: deque[str] = field(default_factory=deque)
    seen_set: set[str] = field(default_factory=set)

    def remember_message_id(self, message_id: str, cap: int = 500) -> bool:
        if message_id in self.seen_set:
            return False
        self.seen_set.add(message_id)
        self.seen_ids.append(message_id)
        while len(self.seen_ids) > cap:
            old = self.seen_ids.popleft()
            self.seen_set.discard(old)
        return True


class ChatServer:
    def __init__(
        self,
        host: str = config.CHAT_HOST,
        port: int = config.CHAT_PORT,
        discovery_port: int = config.DISCOVERY_PORT,
        server_name: str = config.SERVER_NAME,
    ) -> None:
        self.host = host
        self.port = port
        self.discovery_port = discovery_port
        self.server_name = server_name

        self._stop_event = threading.Event()
        self._sessions: dict[socket.socket, ClientSession] = {}
        self._user_to_sock: dict[str, socket.socket] = {}
        self._lock = threading.Lock()

        self.rooms = RoomManager()
        self.rate_limiter = AuthRateLimiter()

    def serve_forever(self) -> None:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        discovery = DiscoveryResponder(self.port, self.discovery_port, self.server_name, self._stop_event)
        discovery.start()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.host, self.port))
            server_sock.listen()
            server_sock.settimeout(1.0)

            logger.info("Chat server listening on %s:%s", self.host, self.port)
            logger.info("Discovery responder active on UDP %s", self.discovery_port)

            try:
                while not self._stop_event.is_set():
                    try:
                        client_sock, addr = server_sock.accept()
                    except socket.timeout:
                        continue
                    thread = threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True)
                    thread.start()
            except KeyboardInterrupt:
                logger.info("Server shutdown requested")
            finally:
                self._stop_event.set()
                self._close_all_sessions()

    def _close_all_sessions(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._user_to_sock.clear()
        for session in sessions:
            try:
                session.sock.close()
            except OSError:
                pass

    def _handle_client(self, client_sock: socket.socket, addr: tuple[str, int]) -> None:
        ip = addr[0]
        client_sock.settimeout(config.SOCKET_TIMEOUT)
        sock_file = client_sock.makefile("rb")
        session: ClientSession | None = None
        try:
            if self.rate_limiter.is_blocked(ip):
                send_json(client_sock, {"type": "error", "reason": "Too many auth failures. Try later."})
                return

            private_key, public_key = generate_x25519_keypair()
            send_json(client_sock, {"type": "server_hello", "server_pubkey": b64_encode(public_key)})

            hello = recv_json_line(sock_file)
            if hello.get("type") != "client_hello":
                raise ProtocolError("Expected client_hello")
            peer_key_b64 = safe_str(hello.get("client_pubkey"), 128)
            session_key = derive_session_key(private_key, base64.b64decode(peer_key_b64))
            cipher = SessionCipher(session_key)

            secure_auth = recv_json_line(sock_file)
            if secure_auth.get("type") != "secure":
                raise ProtocolError("Expected secure auth payload")
            auth = cipher.decrypt_obj(secure_auth)
            if auth.get("type") != "auth":
                raise ProtocolError("Expected auth payload")

            username = safe_str(auth.get("username"), config.USERNAME_MAX_LEN)
            room = safe_str(auth.get("room"), config.ROOM_MAX_LEN)
            room_password = safe_str(auth.get("room_password"), config.MAX_AUTH_PAYLOAD_LEN)

            if not validate_username(username):
                raise ProtocolError("Invalid username")
            if not room_password:
                raise ProtocolError("Room password cannot be empty")

            with self._lock:
                if username in self._user_to_sock:
                    raise ProtocolError("Username already in use")

            self.rooms.join(username, room, room_password)
            self.rate_limiter.reset(ip)

            session = ClientSession(
                sock=client_sock,
                file=sock_file,
                ip=ip,
                username=username,
                room=room,
                cipher=cipher,
            )
            with self._lock:
                self._sessions[client_sock] = session
                self._user_to_sock[username] = client_sock

            send_json(client_sock, cipher.encrypt_obj({"type": "auth_ok", "room": room, "users": self.rooms.users(room)}))
            self._broadcast_presence(room, "join", username)

            while not self._stop_event.is_set():
                try:
                    frame = recv_json_line(sock_file)
                except ConnectionError:
                    break
                if frame.get("type") != "secure":
                    raise ProtocolError("Expected secure frame")
                payload = cipher.decrypt_obj(frame)
                self._handle_secure_payload(session, payload)
        except PermissionError:
            self.rate_limiter.register_failure(ip)
            send_json(client_sock, {"type": "error", "reason": "Invalid room password"})
        except (ProtocolError, CryptoError, ValueError) as exc:
            self.rate_limiter.register_failure(ip)
            logger.warning("Rejected client %s: %s", ip, exc)
            try:
                send_json(client_sock, {"type": "error", "reason": str(exc)})
            except OSError:
                pass
        except OSError as exc:
            logger.info("Connection closed for %s: %s", ip, exc)
        finally:
            if session:
                self._remove_session(session)
            try:
                client_sock.close()
            except OSError:
                pass

    def _remove_session(self, session: ClientSession) -> None:
        with self._lock:
            self._sessions.pop(session.sock, None)
            self._user_to_sock.pop(session.username, None)
        self.rooms.leave(session.username, session.room)
        self._broadcast_presence(session.room, "leave", session.username)

    def _broadcast_room(self, room: str, payload: dict[str, Any], *, exclude: str | None = None) -> int:
        sent = 0
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            if session.room != room or (exclude and session.username == exclude):
                continue
            try:
                send_json(session.sock, session.cipher.encrypt_obj(payload))
                sent += 1
            except OSError:
                pass
        return sent

    def _broadcast_presence(self, room: str, action: str, username: str) -> None:
        users = self.rooms.users(room)
        payload = {
            "type": "presence",
            "action": action,
            "username": username,
            "room": room,
            "users": users,
        }
        self._broadcast_room(room, payload)

    def _send_to_session(self, session: ClientSession, payload: dict[str, Any]) -> None:
        send_json(session.sock, session.cipher.encrypt_obj(payload))

    def _handle_secure_payload(self, session: ClientSession, payload: dict[str, Any]) -> None:
        msg_type = payload.get("type")
        if msg_type == "chat":
            message_id = safe_str(payload.get("message_id"), 64)
            text = safe_str(payload.get("text"), config.MAX_TEXT_LEN)
            if not session.remember_message_id(message_id):
                self._send_to_session(session, {"type": "ack", "message_id": message_id, "status": "duplicate"})
                return
            self._send_to_session(session, {"type": "ack", "message_id": message_id, "status": "sent"})
            delivered = self._broadcast_room(
                session.room,
                {
                    "type": "message",
                    "message_id": message_id,
                    "room": session.room,
                    "sender": session.username,
                    "text": text,
                    "ts": int(time.time()),
                },
                exclude=session.username,
            )
            self._send_to_session(
                session,
                {
                    "type": "ack",
                    "message_id": message_id,
                    "status": "delivered",
                    "delivered_count": delivered,
                },
            )
            return

        if msg_type == "list_rooms":
            self._send_to_session(session, {"type": "rooms", "rooms": self.rooms.list_rooms()})
            return

        if msg_type == "list_users":
            self._send_to_session(session, {"type": "users", "room": session.room, "users": self.rooms.users(session.room)})
            return

        if msg_type == "join_room":
            new_room = safe_str(payload.get("room"), config.ROOM_MAX_LEN)
            room_password = safe_str(payload.get("room_password"), config.MAX_AUTH_PAYLOAD_LEN)
            if not room_password:
                raise ProtocolError("Room password cannot be empty")
            old_room = session.room
            self.rooms.join(session.username, new_room, room_password)
            self.rooms.leave(session.username, old_room)
            session.room = new_room
            self._send_to_session(session, {"type": "room_joined", "room": new_room, "users": self.rooms.users(new_room)})
            self._broadcast_presence(old_room, "leave", session.username)
            self._broadcast_presence(new_room, "join", session.username)
            return

        if msg_type == "leave_room":
            old_room = session.room
            self.rooms.leave(session.username, old_room)
            session.room = "lobby"
            self.rooms.join(session.username, "lobby", "public")
            self._send_to_session(session, {"type": "room_joined", "room": "lobby", "users": self.rooms.users("lobby")})
            self._broadcast_presence(old_room, "leave", session.username)
            self._broadcast_presence("lobby", "join", session.username)
            return

        if msg_type == "ping":
            self._send_to_session(session, {"type": "pong", "ts": int(time.time())})
            return

        raise ProtocolError("Unknown secure message type")
