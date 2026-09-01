from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class CryptoError(Exception):
    pass


def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64_decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)


def generate_x25519_keypair() -> tuple[X25519PrivateKey, bytes]:
    private = X25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, public


def derive_session_key(private_key: X25519PrivateKey, peer_public_bytes: bytes) -> bytes:
    peer_public = X25519PublicKey.from_public_bytes(peer_public_bytes)
    shared_secret = private_key.exchange(peer_public)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stealth-chat-session-key-v1",
    )
    return hkdf.derive(shared_secret)


@dataclass
class NonceSequence:
    prefix: bytes = field(default_factory=lambda: os.urandom(4))
    counter: int = 0

    def next(self) -> bytes:
        nonce = self.prefix + self.counter.to_bytes(8, "big")
        self.counter += 1
        return nonce


@dataclass
class SessionCipher:
    key: bytes
    _nonces: NonceSequence = field(default_factory=NonceSequence)

    def __post_init__(self) -> None:
        self._aead = AESGCM(self.key)

    def encrypt_obj(self, payload: dict[str, Any]) -> dict[str, str]:
        plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        nonce = self._nonces.next()
        ciphertext = self._aead.encrypt(nonce, plaintext, None)
        return {"type": "secure", "nonce": b64_encode(nonce), "ciphertext": b64_encode(ciphertext)}

    def decrypt_obj(self, envelope: dict[str, str]) -> dict[str, Any]:
        try:
            nonce = b64_decode(envelope["nonce"])
            ciphertext = b64_decode(envelope["ciphertext"])
            plaintext = self._aead.decrypt(nonce, ciphertext, None)
            decoded = json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, InvalidTag, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CryptoError("Failed to decrypt secure payload") from exc
        if not isinstance(decoded, dict):
            raise CryptoError("Secure payload must be object")
        return decoded
