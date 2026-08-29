from __future__ import annotations

import logging
import threading
import uuid
from queue import Empty, Queue
from typing import Any

try:
    import curses
except ImportError:  # pragma: no cover - import error only on unsupported platforms
    curses = None

from stealth_chat import config
from stealth_chat.client_core import ChatClient
from stealth_chat.crypto import CryptoError
from stealth_chat.protocol import ProtocolError, recv_json_line
from stealth_chat.tui_format import format_ack_line, format_chat_line, format_presence_line, format_system_line

logger = logging.getLogger(__name__)


class TuiClient:
    def __init__(self, client: ChatClient) -> None:
        self.client = client
        self.stop_event = threading.Event()
        self.events: Queue[tuple[str, str]] = Queue()
        self.lines: list[tuple[str, str]] = []
        self.scroll_offset = 0
        self.input_buffer: list[str] = []
        self.cursor = 0
        self.show_ack_success = False
        self.receiver_thread: threading.Thread | None = None

        self.stdscr: Any | None = None
        self.log_win: Any | None = None
        self.input_win: Any | None = None

    def run(self) -> None:
        if curses is None:
            print("curses is unavailable on this system.")
            print("On Windows, install optional dependency: pip install windows-curses")
            return

        self.receiver_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.receiver_thread.start()

        curses.wrapper(self._curses_main)

        self.stop_event.set()
        self.client.stop_event.set()
        try:
            if self.client.sock:
                self.client.sock.close()
        except OSError:
            pass

    def _recv_loop(self) -> None:
        assert self.client.sock_file is not None and self.client.cipher is not None
        while not self.stop_event.is_set() and not self.client.stop_event.is_set():
            try:
                frame = recv_json_line(self.client.sock_file)
                if frame.get("type") == "error":
                    self.events.put(("warn", format_system_line(f"Server error: {frame.get('reason', 'unknown')}")))
                    self.stop_event.set()
                    break
                payload = self.client.cipher.decrypt_obj(frame)
                self._handle_payload(payload)
            except (ConnectionError, OSError, ProtocolError, CryptoError) as exc:
                self.events.put(("warn", format_system_line(f"Disconnected: {exc}")))
                self.stop_event.set()
                break

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        msg_type = payload.get("type")
        if msg_type == "message":
            sender = str(payload.get("sender", ""))
            text = str(payload.get("text", ""))
            self.client.room = str(payload.get("room", self.client.room))
            self.events.put(("chat", format_chat_line(self.client.room, sender, text)))
            if self.client.history_store and payload.get("message_id"):
                self.client.history_store.save_message(self.client.room, sender, str(payload["message_id"]), text)
            return

        if msg_type == "ack":
            ack_line = format_ack_line(payload, show_success=self.show_ack_success)
            if ack_line:
                kind = "warn" if "!" in ack_line else "system"
                self.events.put((kind, format_system_line(ack_line)))
            return

        if msg_type == "presence":
            room = str(payload.get("room", self.client.room))
            username = str(payload.get("username", ""))
            action = str(payload.get("action", ""))
            users = [str(u) for u in payload.get("users", [])]
            self.events.put(("presence", format_presence_line(room, username, action, users)))
            return

        if msg_type == "rooms":
            rooms = payload.get("rooms", [])
            if not rooms:
                self.events.put(("system", format_system_line("No active rooms")))
                return
            self.events.put(("system", format_system_line("Rooms:")))
            for room in rooms:
                self.events.put(("system", format_system_line(f" - {room['room']} ({room['members']} online)")))
            return

        if msg_type == "users":
            users = [str(u) for u in payload.get("users", [])]
            room = str(payload.get("room", self.client.room))
            self.events.put(("system", format_system_line(f"Users in {room}: {', '.join(users)}")))
            return

        if msg_type == "room_joined":
            self.client.room = str(payload.get("room", self.client.room))
            users = [str(u) for u in payload.get("users", [])]
            self.events.put(("system", format_system_line(f"Switched to room '{self.client.room}'. Users: {', '.join(users)}")))

    def _curses_main(self, stdscr: Any) -> None:
        self.stdscr = stdscr
        curses.curs_set(1)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_WHITE, -1)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_GREEN, -1)

        self._resize_windows()
        self.lines.append(("system", format_system_line("Type /help for commands. /exit to quit.")))
        self.lines.append(("system", format_system_line("ACK success is hidden. Use /acks on to show.")))

        while not self.stop_event.is_set() and not self.client.stop_event.is_set():
            self._drain_events()
            self._render()

            ch = stdscr.getch()
            if ch == -1:
                curses.napms(25)
                continue

            if ch == curses.KEY_RESIZE:
                self._resize_windows()
                continue

            if ch in (10, 13, curses.KEY_ENTER):
                if not self._submit_input():
                    break
                continue

            if ch == curses.KEY_PPAGE:
                self.scroll_offset = min(len(self.lines), self.scroll_offset + 5)
                continue

            if ch == curses.KEY_NPAGE:
                self.scroll_offset = max(0, self.scroll_offset - 5)
                continue

            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.cursor > 0:
                    del self.input_buffer[self.cursor - 1]
                    self.cursor -= 1
                continue

            if ch == curses.KEY_DC:
                if self.cursor < len(self.input_buffer):
                    del self.input_buffer[self.cursor]
                continue

            if ch == curses.KEY_LEFT:
                self.cursor = max(0, self.cursor - 1)
                continue

            if ch == curses.KEY_RIGHT:
                self.cursor = min(len(self.input_buffer), self.cursor + 1)
                continue

            if ch == curses.KEY_HOME:
                self.cursor = 0
                continue

            if ch == curses.KEY_END:
                self.cursor = len(self.input_buffer)
                continue

            if 32 <= ch <= 126:
                self.input_buffer.insert(self.cursor, chr(ch))
                self.cursor += 1

    def _drain_events(self) -> None:
        while True:
            try:
                kind, line = self.events.get_nowait()
                self.lines.append((kind, line))
                if self.scroll_offset > 0:
                    self.scroll_offset = max(0, self.scroll_offset - 1)
            except Empty:
                return

    def _resize_windows(self) -> None:
        assert self.stdscr is not None
        h, w = self.stdscr.getmaxyx()
        log_height = max(1, h - 2)

        self.log_win = curses.newwin(log_height, w, 0, 0)
        self.input_win = curses.newwin(1, w, h - 1, 0)

        self.log_win.keypad(True)
        self.input_win.keypad(True)

    def _render(self) -> None:
        assert self.stdscr is not None and self.log_win is not None and self.input_win is not None
        h, w = self.stdscr.getmaxyx()
        log_height = max(1, h - 2)

        self.log_win.erase()
        start = max(0, len(self.lines) - log_height - self.scroll_offset)
        end = max(start, len(self.lines) - self.scroll_offset)

        for idx, (kind, line) in enumerate(self.lines[start:end]):
            attr = curses.A_NORMAL
            if curses.has_colors():
                if kind == "chat":
                    attr = curses.color_pair(1)
                elif kind in {"presence", "system"}:
                    attr = curses.color_pair(2)
                elif kind == "warn":
                    attr = curses.color_pair(3)
                elif kind == "me":
                    attr = curses.color_pair(4)
            self.log_win.addnstr(idx, 0, line, w - 1, attr)

        self.stdscr.hline(h - 2, 0, "-", w)

        prompt = "> "
        full_text = "".join(self.input_buffer)
        input_width = max(1, w - len(prompt) - 1)
        start = 0
        if self.cursor > input_width:
            start = self.cursor - input_width
        visible = full_text[start : start + input_width]
        cursor_x = len(prompt) + (self.cursor - start)

        self.input_win.erase()
        self.input_win.addnstr(0, 0, prompt + visible, w - 1)

        self.log_win.noutrefresh()
        self.stdscr.noutrefresh()
        self.input_win.noutrefresh()

        self.stdscr.move(h - 1, min(w - 1, cursor_x))
        curses.doupdate()

    def _submit_input(self) -> bool:
        text = "".join(self.input_buffer).strip()
        self.input_buffer.clear()
        self.cursor = 0

        if not text:
            return True

        if text == "/help":
            self.lines.append(("system", format_system_line("Commands: /help /rooms /users /join <room> <password> /leave /history [n] /acks on|off /exit")))
            return True

        if text == "/exit":
            self.stop_event.set()
            return False

        if text == "/rooms":
            self.client._send_secure({"type": "list_rooms"})
            return True

        if text == "/users":
            self.client._send_secure({"type": "list_users"})
            return True

        if text.startswith("/join "):
            parts = text.split(maxsplit=2)
            if len(parts) != 3:
                self.lines.append(("warn", format_system_line("Usage: /join <room> <password>")))
                return True
            self.client._send_secure({"type": "join_room", "room": parts[1], "room_password": parts[2]})
            return True

        if text == "/leave":
            self.client._send_secure({"type": "leave_room"})
            return True

        if text.startswith("/history"):
            self._show_history(text)
            return True

        if text.startswith("/acks "):
            mode = text.split(maxsplit=1)[1].strip().lower()
            if mode in {"on", "off"}:
                self.show_ack_success = mode == "on"
                self.lines.append(("system", format_system_line(f"ACK success display: {mode}")))
            else:
                self.lines.append(("warn", format_system_line("Usage: /acks on|off")))
            return True

        message_id = str(uuid.uuid4())
        self.client._send_secure({"type": "chat", "message_id": message_id, "text": text})
        self.lines.append(("me", format_chat_line(self.client.room, self.client.username, text)))
        if self.client.history_store:
            self.client.history_store.save_message(self.client.room, self.client.username, message_id, f"(me) {text}")
        return True

    def _show_history(self, text: str) -> None:
        if not self.client.history_store:
            self.lines.append(("warn", format_system_line("History disabled")))
            return
        parts = text.split(maxsplit=1)
        limit = 10
        if len(parts) == 2 and parts[1].isdigit():
            limit = max(1, min(100, int(parts[1])))

        rows = self.client.history_store.get_recent(limit=limit)
        if not rows:
            self.lines.append(("system", format_system_line("No local history")))
            return

        self.lines.append(("system", format_system_line(f"Last {len(rows)} message(s):")))
        for row in reversed(rows):
            self.lines.append(("system", f"{row['created_at']} [{row['room']}] {row['sender']}: {row['text']}"))


def main() -> None:
    username = input("Choose a username: ").strip()
    room = input("Room name: ").strip() or "lobby"
    room_password = input("Room password/invite code: ").strip()

    try:
        client = ChatClient(username=username, room=room, room_password=room_password)
        client.connect()
        app = TuiClient(client)
        app.run()
    except Exception as exc:
        print(f"Failed to start TUI client: {exc}")
        print(
            f"Hint: verify server is running, TCP port {config.CHAT_PORT} and UDP discovery port {config.DISCOVERY_PORT} "
            "are allowed by firewall."
        )


if __name__ == "__main__":
    main()
