import time
import unittest

from stealth_chat.auth import AuthRateLimiter, RoomManager


class AuthRoomTests(unittest.TestCase):
    def test_rate_limiter_blocks_after_failures(self) -> None:
        limiter = AuthRateLimiter(max_failures=2, window_seconds=60, block_seconds=1)
        ip = "127.0.0.1"
        limiter.register_failure(ip)
        self.assertFalse(limiter.is_blocked(ip))
        limiter.register_failure(ip)
        self.assertTrue(limiter.is_blocked(ip))
        time.sleep(1.1)
        self.assertFalse(limiter.is_blocked(ip))

    def test_room_join_and_password_validation(self) -> None:
        manager = RoomManager()
        created, users = manager.join("alice", "general", "pw")
        self.assertTrue(created)
        self.assertEqual(users, ["alice"])

        created, users = manager.join("bob", "general", "pw")
        self.assertFalse(created)
        self.assertEqual(users, ["alice", "bob"])

        with self.assertRaises(PermissionError):
            manager.join("mallory", "general", "wrong")


if __name__ == "__main__":
    unittest.main()
