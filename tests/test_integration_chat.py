import socket
import threading
import time
import unittest

from stealth_chat.client_core import ChatClient
from stealth_chat.protocol import recv_json_line
from stealth_chat.server_core import ChatServer


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ChatIntegrationTests(unittest.TestCase):
    def test_two_clients_exchange_room_message_with_ack(self) -> None:
        chat_port = free_port()
        discovery_port = free_port()

        server = ChatServer(host="127.0.0.1", port=chat_port, discovery_port=discovery_port, server_name="test")
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        time.sleep(0.5)

        alice = ChatClient("alice", "room1", "pw", host="127.0.0.1", port=chat_port)
        bob = ChatClient("bob", "room1", "pw", host="127.0.0.1", port=chat_port)

        alice.connect()
        bob.connect()

        messages = []

        def bob_reader() -> None:
            for _ in range(4):
                frame = bob.cipher.decrypt_obj(recv_json_line(bob.sock_file))
                messages.append(frame)

        reader = threading.Thread(target=bob_reader, daemon=True)
        reader.start()

        alice._send_secure({"type": "chat", "message_id": "mid-1", "text": "hello"})

        got_ack = False
        deadline = time.time() + 5
        while time.time() < deadline:
            frame = alice.cipher.decrypt_obj(recv_json_line(alice.sock_file))
            if frame.get("type") == "ack" and frame.get("status") == "delivered":
                got_ack = True
                break
        self.assertTrue(got_ack)

        reader.join(timeout=3)
        self.assertTrue(any(m.get("type") == "message" and m.get("text") == "hello" for m in messages))

        alice.stop_event.set()
        bob.stop_event.set()
        if alice.sock:
            alice.sock.close()
        if bob.sock:
            bob.sock.close()
        server._stop_event.set()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
