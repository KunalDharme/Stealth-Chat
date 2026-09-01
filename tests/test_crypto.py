import unittest

from stealth_chat.crypto import CryptoError, SessionCipher, derive_session_key, generate_x25519_keypair


class CryptoTests(unittest.TestCase):
    def test_key_exchange_derives_same_key(self) -> None:
        priv_a, pub_a = generate_x25519_keypair()
        priv_b, pub_b = generate_x25519_keypair()

        key_a = derive_session_key(priv_a, pub_b)
        key_b = derive_session_key(priv_b, pub_a)

        self.assertEqual(key_a, key_b)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        key = b"x" * 32
        cipher = SessionCipher(key)
        payload = {"type": "chat", "text": "hello"}
        encrypted = cipher.encrypt_obj(payload)
        decrypted = cipher.decrypt_obj(encrypted)
        self.assertEqual(payload, decrypted)

    def test_invalid_tag_raises(self) -> None:
        key = b"y" * 32
        cipher = SessionCipher(key)
        encrypted = cipher.encrypt_obj({"type": "chat", "text": "hello"})
        encrypted["ciphertext"] = encrypted["ciphertext"][:-2] + "AA"
        with self.assertRaises(CryptoError):
            cipher.decrypt_obj(encrypted)


if __name__ == "__main__":
    unittest.main()
