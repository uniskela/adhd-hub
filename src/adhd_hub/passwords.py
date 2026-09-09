"""Local dashboard password storage, separate from the MCP/REST token."""

from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
from pathlib import Path


class PasswordStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "dashboard-password.hash"

    @property
    def configured(self) -> bool:
        return self.path.exists()

    @staticmethod
    def _derive(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode(), salt=salt, n=32768, r=8, p=3, dklen=32, maxmem=64 * 1024 * 1024
        )

    def verify(self, password: str) -> bool:
        if not self.configured:
            return False
        version, salt_hex, digest_hex = self.path.read_text().strip().split("$")
        if version != "scrypt-v1" or len(salt_hex) != 32 or len(digest_hex) != 64:
            raise ValueError("Invalid password file")
        actual = self._derive(password, bytes.fromhex(salt_hex))
        return secrets.compare_digest(actual, bytes.fromhex(digest_hex))

    def save(self, password: str) -> None:
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # NamedTemporaryFile creates a private file; replace atomically so a crash
        # cannot leave a partially written credential behind.
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as file:
                name = file.name
                os.chmod(name, 0o600)
                file.write(f"scrypt-v1${salt.hex()}${digest.hex()}\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
