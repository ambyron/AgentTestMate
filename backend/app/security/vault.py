"""Credential vault — AES-256-GCM encryption for API credentials."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialVault:
    """AES-256-GCM based credential encryption/decryption."""

    def __init__(self, key: bytes | None = None, key_file: Path | None = None):
        if key is not None:
            self._key = key
        elif key_file is not None and key_file.exists():
            self._key = key_file.read_bytes()
        else:
            self._key = AESGCM.generate_key(bit_length=256)
            if key_file is not None:
                key_file.parent.mkdir(parents=True, exist_ok=True)
                key_file.write_bytes(self._key)

    def encrypt(self, plaintext: str) -> str:
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        aesgcm = AESGCM(self._key)
        data = base64.b64decode(encrypted)
        nonce, ciphertext = data[:12], data[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
