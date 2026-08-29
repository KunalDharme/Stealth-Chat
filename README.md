# Stealth-Chat

Stealth-Chat is a LAN-first secure Python chat application with automatic server discovery, room-based access control, end-to-end message encryption, delivery acknowledgments, and optional encrypted local history.

## Features

- Zero-config LAN discovery (UDP broadcast, optional mDNS fallback)
- TCP chat transport bound to `0.0.0.0` for same-router access
- End-to-end encrypted payloads with X25519 session key exchange + AES-GCM
- Multi-room support (`join`, `leave`, room list, room member list)
- Room access via room password / invite code
- Username and payload validation
- Failed-auth rate limiting per client IP
- Message IDs + sent/delivered ACK semantics
- Basic duplicate message protection by message ID cache
- Presence updates (join/leave + online users in room)
- Optional encrypted local chat history (SQLite + retention)
- Unit + integration tests and GitHub Actions CI

## Project Structure

```text
Stealth-Chat/
├── stealth_chat/
│   ├── auth.py
│   ├── client_core.py
│   ├── config.py
│   ├── crypto.py
│   ├── discovery.py
│   ├── protocol.py
│   ├── server_core.py
│   └── storage.py
├── tests/
├── .github/workflows/ci.yml
├── client.py
├── server.py
└── requirements.txt
```

## Quick Start

```bash
pip install -r requirements.txt
python server.py
```

In a second terminal (same machine or another device on same router):

```bash
python client.py
```

Client auto-discovers server on LAN. No manual IP entry required.

## Configuration (Environment Variables)

- `STEALTH_CHAT_HOST` (default: `0.0.0.0`)
- `STEALTH_CHAT_PORT` (default: `54321`)
- `STEALTH_DISCOVERY_PORT` (default: `54322`)
- `STEALTH_DISCOVERY_TIMEOUT` (default: `1.5`)
- `STEALTH_DISCOVERY_RETRIES` (default: `4`)
- `STEALTH_HISTORY_ENABLED` (`1`/`0`, default: `1`)
- `STEALTH_HISTORY_DB` (default: `chat_history.db`)
- `STEALTH_HISTORY_RETENTION_DAYS` (default: `7`)
- `STEALTH_HISTORY_MAX_MESSAGES` (default: `2000`)

## Command Reference

- `/help` show commands
- `/rooms` list active rooms
- `/users` list users in current room
- `/join <room> <password>` create/join room
- `/leave` return to `lobby`
- `/history [n]` show local decrypted history preview
- `/exit` disconnect

## Architecture and Message Flow

1. **Discovery**: Client sends UDP broadcast probe on discovery port.
2. **Discovery Reply**: Server replies with chat TCP port.
3. **TCP Connect**: Client opens TCP to discovered server.
4. **Key Exchange**: Server/client exchange X25519 public keys.
5. **Session Key**: Both derive shared key via HKDF.
6. **Secure Auth**: Client sends encrypted auth payload (`username`, `room`, `room_password`).
7. **Chat**: All protocol messages after handshake are AES-GCM encrypted JSON envelopes.

## Security Model and Limitations

### Threat Model
- Intended for private LAN usage.
- Message payload confidentiality/integrity is protected by AES-GCM session encryption.
- Room password controls room entry.
- Rate limiter reduces trivial brute-force auth abuse.

### Limitations
- No PKI/identity pinning; active MITM on LAN is still a caveat.
- Discovery is LAN-scoped and depends on router/firewall allowing UDP broadcast.
- mDNS fallback is best-effort (`stealth-chat.local` lookup).
- Local history key is derived from local client secret input/environment (protect host access).

## Reliability/Usability Notes

- Message IDs support duplicate detection cache on server.
- Sender receives `sent` and `delivered` acknowledgments.
- Presence broadcasts show room join/leave and current room users.
- Helpful discovery error output includes retries and firewall hints.

## Testing

Run all tests with one command:

```bash
python -m unittest discover -s tests -v
```

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs:
- dependency install
- syntax lint via `python -m compileall -q .`
- full test suite

## Migration Notes

- Client/server protocol is now JSON-frame based and encrypted at the application layer.
- Legacy admin `/kick` and `/ban` commands were removed in favor of room auth and rate-limited access control.
- Start server/client with same entrypoints: `python server.py`, `python client.py`.

## Resume Bullet Points

- Built a zero-config LAN chat system in Python using UDP service discovery + TCP messaging.
- Implemented end-to-end encrypted messaging with X25519 key exchange and AES-GCM authenticated encryption.
- Added room-level access control, presence, multi-room messaging, message ACKs, and deduplication.
- Implemented encrypted local message persistence in SQLite with retention policies.
- Created unit/integration tests and automated CI with GitHub Actions.

## License

MIT
