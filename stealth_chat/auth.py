from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from . import config
from .protocol import validate_room_name


def hash_room_secret(room_password: str) -> str:
    return hashlib.sha256(room_password.encode("utf-8")).hexdigest()


@dataclass
class AuthRateLimiter:
    max_failures: int = config.AUTH_MAX_FAILURES
    window_seconds: int = config.AUTH_WINDOW_SECONDS
    block_seconds: int = config.AUTH_BLOCK_SECONDS
    _failures: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _blocked_until: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_blocked(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            blocked_until = self._blocked_until.get(ip, 0)
            if blocked_until > now:
                return True
            if ip in self._blocked_until:
                del self._blocked_until[ip]
            return False

    def register_failure(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            failures = self._failures[ip]
            failures.append(now)
            while failures and now - failures[0] > self.window_seconds:
                failures.popleft()
            if len(failures) >= self.max_failures:
                self._blocked_until[ip] = now + self.block_seconds

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
            self._blocked_until.pop(ip, None)


@dataclass
class Room:
    name: str
    secret_hash: str
    members: set[str] = field(default_factory=set)


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = threading.Lock()

    def join(self, username: str, room_name: str, room_password: str) -> tuple[bool, list[str]]:
        if not validate_room_name(room_name):
            raise ValueError("Invalid room name")
        room_secret = hash_room_secret(room_password)
        with self._lock:
            room = self._rooms.get(room_name)
            created = False
            if room is None:
                room = Room(name=room_name, secret_hash=room_secret)
                self._rooms[room_name] = room
                created = True
            elif not hmac.compare_digest(room.secret_hash, room_secret):
                raise PermissionError("Invalid room password")
            room.members.add(username)
            return created, sorted(room.members)

    def leave(self, username: str, room_name: str) -> None:
        with self._lock:
            room = self._rooms.get(room_name)
            if room is None:
                return
            room.members.discard(username)
            if not room.members:
                del self._rooms[room_name]

    def users(self, room_name: str) -> list[str]:
        with self._lock:
            room = self._rooms.get(room_name)
            if room is None:
                return []
            return sorted(room.members)

    def list_rooms(self) -> list[dict[str, int | str]]:
        with self._lock:
            return [
                {"room": name, "members": len(room.members)}
                for name, room in sorted(self._rooms.items())
            ]
