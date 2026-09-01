from __future__ import annotations

import socket
import threading
import time
import json

from . import config

DISCOVER_MAGIC = "STEALTH_CHAT_DISCOVER_V1"
DISCOVERY_RESPONSE_MAGIC = "STEALTH_CHAT_HERE_V1"


class DiscoveryResponder(threading.Thread):
    def __init__(self, chat_port: int, discovery_port: int, server_name: str, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.chat_port = chat_port
        self.discovery_port = discovery_port
        self.server_name = server_name
        self.stop_event = stop_event

    def run(self) -> None:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.bind(("0.0.0.0", self.discovery_port))
        udp.settimeout(1.0)
        try:
            while not self.stop_event.is_set():
                try:
                    data, addr = udp.recvfrom(4096)
                except socket.timeout:
                    continue
                if data.decode("utf-8", errors="ignore") != DISCOVER_MAGIC:
                    continue
                response = {
                    "magic": DISCOVERY_RESPONSE_MAGIC,
                    "chat_port": self.chat_port,
                    "server_name": self.server_name,
                }
                udp.sendto(json.dumps(response, separators=(",", ":")).encode("utf-8"), addr)
        finally:
            udp.close()


def discover_server(
    *,
    discovery_port: int = config.DISCOVERY_PORT,
    timeout: float = config.DISCOVERY_TIMEOUT,
    retries: int = config.DISCOVERY_RETRIES,
) -> tuple[str, int]:
    errors: list[str] = []
    targets = ["255.255.255.255", "127.0.0.1"]
    for attempt in range(1, retries + 1):
        for target in targets:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.settimeout(timeout)
            try:
                udp.sendto(DISCOVER_MAGIC.encode("utf-8"), (target, discovery_port))
                raw_data, addr = udp.recvfrom(4096)
                data = json.loads(raw_data.decode("utf-8", errors="strict"))
                if data.get("magic") != DISCOVERY_RESPONSE_MAGIC:
                    raise ValueError("Unexpected discovery payload")
                chat_port = int(data["chat_port"])
                return addr[0], chat_port
            except (socket.timeout, ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                errors.append(f"attempt {attempt} ({target}): {exc}")
                time.sleep(0.15)
            finally:
                udp.close()

    try:
        fallback_ip = socket.gethostbyname("stealth-chat.local")
        return fallback_ip, config.CHAT_PORT
    except OSError as exc:
        errors.append(f"mdns fallback: {exc}")

    error_text = "; ".join(errors)
    raise ConnectionError(
        f"Server discovery failed after {retries} attempts. Check firewall/UDP {discovery_port}. Details: {error_text}"
    )
