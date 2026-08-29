from __future__ import annotations

import json
import re
import socket
from typing import Any

from . import config

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
ROOM_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ProtocolError(ValueError):
    pass


def validate_username(username: str) -> bool:
    return (
        isinstance(username, str)
        and config.USERNAME_MIN_LEN <= len(username) <= config.USERNAME_MAX_LEN
        and USERNAME_RE.fullmatch(username) is not None
    )


def validate_room_name(room: str) -> bool:
    return (
        isinstance(room, str)
        and config.ROOM_MIN_LEN <= len(room) <= config.ROOM_MAX_LEN
        and ROOM_RE.fullmatch(room) is not None
    )


def encode_json_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def recv_json_line(sock_file: Any, *, max_bytes: int = 65536) -> dict[str, Any]:
    line = sock_file.readline(max_bytes + 1)
    if not line:
        raise ConnectionError("Connection closed")
    if len(line) > max_bytes:
        raise ProtocolError("Frame too large")
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Invalid JSON frame") from exc
    if not isinstance(data, dict):
        raise ProtocolError("JSON frame must be an object")
    return data


def send_json(sock: socket.socket, payload: dict[str, Any]) -> None:
    sock.sendall(encode_json_line(payload))


def safe_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        raise ProtocolError("Expected string")
    if len(value) > max_len:
        raise ProtocolError("String too long")
    return value
