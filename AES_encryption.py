
encryption.py


Handles AES-256 encryption of captured input logs before they are
written to disk / uploaded to IPFS.

Key handling: a fresh symmetric key is derived for every game session
(session-scoped key), rather than using one static key for the
lifetime of the application. This limits exposure if a single
session's key is ever compromised - it cannot be used to decrypt
logs from any other session.

Derivation: PBKDF2-HMAC-SHA256 over a per-session random salt and a
secret seed (e.g. server-issued session token / wallet signature).
In production the seed should come from something the player cannot
forge - for example a value signed by the game server when the
session starts.
"""

import os
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class SessionEncryptor:
    def __init__(self, session_seed: bytes, salt: bytes = None, iterations: int = 200_000):
        """
        session_seed: secret bytes unique to this session (e.g. a session
                      token issued by the game server, or a signed nonce
                      from the player's wallet). This is NOT the AES key
                      itself - the actual key is derived from it.
        salt:         random salt for this session. Generated automatically
                      if not provided. Must be stored/transmitted alongside
                      the encrypted logs so the key can be re-derived for
                      verification later (e.g. by validators).
        """
        self.salt = salt or os.urandom(16)
        self.key = hashlib.pbkdf2_hmac(
            "sha256", session_seed, self.salt, iterations, dklen=32
        )

    def encrypt(self, plaintext: bytes) -> bytes:
        iv = os.urandom(16)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
        # prepend IV so it's available for decryption later
        return iv + ciphertext

    def decrypt(self, blob: bytes) -> bytes:
        iv, ciphertext = blob[:16], blob[16:]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size)

    def export_salt(self) -> str:
        """Hex-encoded salt, safe to store alongside encrypted logs."""
        return self.salt.hex()

    @staticmethod
    def rederive(session_seed: bytes, salt_hex: str, iterations: int = 200_000):
        """Recreate the same encryptor (e.g. server/validator side) given
        the session seed and the stored salt."""
        return SessionEncryptor(session_seed, salt=bytes.fromhex(salt_hex), iterations=iterations)
