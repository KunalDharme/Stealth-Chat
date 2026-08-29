import re
import unittest

from stealth_chat.tui_format import format_ack_line, format_chat_line, format_presence_line, format_system_line


class TuiFormatTests(unittest.TestCase):
    def test_format_chat_line_uses_given_timestamp(self) -> None:
        line = format_chat_line("room1", "alice", "hello", timestamp="12:00:00")
        self.assertEqual(line, "[12:00:00] [room1] alice: hello")

    def test_format_presence_line_is_distinct(self) -> None:
        line = format_presence_line("room1", "bob", "join", ["alice", "bob"])
        self.assertIn("• [room1] bob joined", line)
        self.assertIn("online: alice, bob", line)
        self.assertRegex(line, r"^\[\d{2}:\d{2}:\d{2}\]")

    def test_format_system_line_has_timestamp(self) -> None:
        line = format_system_line("Type /help")
        self.assertTrue(line.endswith("Type /help"))
        self.assertRegex(line, r"^\[\d{2}:\d{2}:\d{2}\]")

    def test_ack_success_hidden_by_default(self) -> None:
        self.assertIsNone(format_ack_line({"message_id": "1", "status": "sent"}))
        self.assertIsNone(format_ack_line({"message_id": "1", "status": "delivered", "delivered_count": 2}))

    def test_ack_success_visible_when_enabled(self) -> None:
        line = format_ack_line({"message_id": "1", "status": "delivered", "delivered_count": 2}, show_success=True)
        self.assertEqual(line, "✓ ACK 1: delivered (2)")

    def test_ack_failure_is_shown(self) -> None:
        duplicate = format_ack_line({"message_id": "9", "status": "duplicate"})
        self.assertEqual(duplicate, "! ACK 9: duplicate ignored")


if __name__ == "__main__":
    unittest.main()
