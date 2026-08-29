import io
import unittest

from stealth_chat.protocol import ProtocolError, encode_json_line, recv_json_line, validate_room_name, validate_username


class ProtocolTests(unittest.TestCase):
    def test_validate_username(self) -> None:
        self.assertTrue(validate_username("user_123"))
        self.assertFalse(validate_username("ab"))
        self.assertFalse(validate_username("bad name"))

    def test_validate_room_name(self) -> None:
        self.assertTrue(validate_room_name("general-room"))
        self.assertFalse(validate_room_name(""))
        self.assertFalse(validate_room_name("bad room"))

    def test_recv_json_line_errors_on_invalid_json(self) -> None:
        with self.assertRaises(ProtocolError):
            recv_json_line(io.BytesIO(b"not-json\n"))

    def test_encode_decode_roundtrip(self) -> None:
        payload = {"type": "ping", "value": 1}
        decoded = recv_json_line(io.BytesIO(encode_json_line(payload)))
        self.assertEqual(payload, decoded)


if __name__ == "__main__":
    unittest.main()
