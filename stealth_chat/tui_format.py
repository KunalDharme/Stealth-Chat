from __future__ import annotations

from datetime import datetime

SUCCESS_ACK_STATUSES = {"sent", "delivered"}


def _now_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def format_chat_line(room: str, sender: str, text: str, timestamp: str | None = None) -> str:
    ts = timestamp or _now_timestamp()
    return f"[{ts}] [{room}] {sender}: {text}"


def format_presence_line(room: str, username: str, action: str, users: list[str]) -> str:
    ts = _now_timestamp()
    suffix = ""
    if users:
        suffix = f" | online: {', '.join(users)}"
    return f"[{ts}] • [{room}] {username} {action}ed{suffix}"


def format_system_line(text: str) -> str:
    ts = _now_timestamp()
    return f"[{ts}] {text}"


def format_ack_line(payload: dict[str, object], show_success: bool = False) -> str | None:
    status = str(payload.get("status", ""))
    message_id = str(payload.get("message_id", ""))

    if status in SUCCESS_ACK_STATUSES and not show_success:
        return None

    if status == "delivered":
        delivered_count = payload.get("delivered_count")
        if delivered_count is None:
            return f"✓ ACK {message_id}: delivered"
        return f"✓ ACK {message_id}: delivered ({delivered_count})"

    if status == "sent":
        return f"✓ ACK {message_id}: sent"

    if status == "duplicate":
        return f"! ACK {message_id}: duplicate ignored"

    if not status:
        return f"! ACK {message_id}: unknown status"

    return f"! ACK {message_id}: {status}"
