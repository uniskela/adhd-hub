from __future__ import annotations

import base64
import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from adhd_hub.backup_v1 import fernet_raw_key

# Files/dirs under data/ that make a movable hub instance.
_INCLUDE_NAMES = {
    "hub.sqlite3",
    "wiki",
    "forge.json",
    "prefs.json",
    "openclaw.json",
}

_ENC_MAGIC = b"ADHDHUB1"
_ENC_FORMAT = "adhd-hub-backup-encrypted"
_ENC_VERSION_V1 = 1
_ENC_VERSION_CURRENT = 2
_ENC_META_MAX = 64 * 1024

# scrypt (stdlib/OpenSSL via cryptography) — salted, memory-hard, no extra dependency.
# Argon2id is not a project dependency; adding argon2-cffi would churn the lockfile.
# N=2^15 (~32 MiB) is a practical homelab default; parameters are stored in the envelope.
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_LEN = 16
_SCRYPT_N_MAX = 2**16
_SCRYPT_R_MAX = 8
_SCRYPT_P_MAX = 1


def _fernet_from_raw_key(raw: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(raw))


def _legacy_v1_decrypt_cipher(keying: str) -> Fernet:
    """Rebuild the Fernet key for historical envelope v1 backups.

    Compat-only decrypt path. New encryption always uses scrypt (v2).
    """
    return _fernet_from_raw_key(fernet_raw_key(keying.encode("utf-8")))


def _passphrase_cipher_v2(passphrase: str, *, salt: bytes, n: int, r: int, p: int) -> Fernet:
    kdf = Scrypt(salt=salt, length=_SCRYPT_DKLEN, n=n, r=r, p=p)
    return _fernet_from_raw_key(kdf.derive(passphrase.encode("utf-8")))


def _parse_encrypted_archive(archive: bytes) -> tuple[dict[str, Any], bytes]:
    if not is_encrypted_backup(archive):
        raise ValueError("archive is not an encrypted ADHD Hub backup")
    if len(archive) < 12:
        raise ValueError("corrupt encrypted backup header")
    meta_len = int.from_bytes(archive[8:12], "big")
    header_end = 12 + meta_len
    if meta_len < 2 or meta_len > _ENC_META_MAX or header_end > len(archive):
        raise ValueError("corrupt encrypted backup header")
    meta_raw = archive[12:header_end]
    try:
        meta = json.loads(meta_raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("corrupt encrypted backup header") from exc
    if not isinstance(meta, dict) or meta.get("format") != _ENC_FORMAT:
        raise ValueError("unsupported encrypted backup format")
    return meta, archive[header_end:]


def encrypted_backup_meta(archive: bytes) -> dict[str, Any]:
    """Return the JSON envelope header for an encrypted backup."""
    meta, _token = _parse_encrypted_archive(archive)
    return meta


def _scrypt_params_from_meta(meta: dict[str, Any]) -> tuple[bytes, int, int, int]:
    if meta.get("kdf") != "scrypt":
        raise ValueError("unsupported encrypted backup KDF")
    try:
        salt = base64.b64decode(meta["salt"], validate=True)
        n = int(meta["n"])
        r = int(meta["r"])
        p = int(meta["p"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("corrupt encrypted backup header") from exc
    if (
        not (16 <= len(salt) <= 64)
        or n < 2
        or n > _SCRYPT_N_MAX
        or (n & (n - 1)) != 0
        or r < 1
        or r > _SCRYPT_R_MAX
        or p < 1
        or p > _SCRYPT_P_MAX
    ):
        raise ValueError("unsupported encrypted backup KDF parameters")
    return salt, n, r, p


def _cipher_from_meta(passphrase: str, meta: dict[str, Any]) -> Fernet:
    version = meta.get("version")
    if version == _ENC_VERSION_V1:
        return _legacy_v1_decrypt_cipher(passphrase)
    if version == _ENC_VERSION_CURRENT:
        salt, n, r, p = _scrypt_params_from_meta(meta)
        return _passphrase_cipher_v2(passphrase, salt=salt, n=n, r=r, p=p)
    raise ValueError("unsupported encrypted backup version")


def export_data_dir(data_dir: Path, *, passphrase: str | None = None) -> bytes:
    """Zip hub data (SQLite, wiki, forge/prefs) for migrate/restore.

    When passphrase is set, wraps the zip in a versioned Fernet envelope.
    New exports use scrypt (v2); decrypt still accepts legacy SHA-256 (v1).
    """
    data_dir = data_dir.resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "adhd-hub-backup.json",
            json.dumps({"format": "adhd-hub-backup", "version": 1}) + "\n",
        )
        for name in sorted(_INCLUDE_NAMES):
            path = data_dir / name
            if not path.exists():
                continue
            if path.is_file():
                zf.write(path, arcname=name)
                continue
            for file in path.rglob("*"):
                if file.is_file():
                    zf.write(file, arcname=str(file.relative_to(data_dir)).replace("\\", "/"))
    raw = buf.getvalue()
    if not passphrase:
        return raw
    salt = os.urandom(_SCRYPT_SALT_LEN)
    token = _passphrase_cipher_v2(
        passphrase, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    ).encrypt(raw)
    meta = json.dumps(
        {
            "format": _ENC_FORMAT,
            "version": _ENC_VERSION_CURRENT,
            "kdf": "scrypt",
            "salt": base64.b64encode(salt).decode("ascii"),
            "n": _SCRYPT_N,
            "r": _SCRYPT_R,
            "p": _SCRYPT_P,
        }
    ).encode()
    return _ENC_MAGIC + len(meta).to_bytes(4, "big") + meta + token


def is_encrypted_backup(archive: bytes) -> bool:
    return archive.startswith(_ENC_MAGIC)


def decrypt_backup(archive: bytes, passphrase: str) -> bytes:
    meta, token = _parse_encrypted_archive(archive)
    cipher = _cipher_from_meta(passphrase, meta)
    try:
        return cipher.decrypt(token)
    except InvalidToken as exc:
        raise ValueError("wrong passphrase or corrupt encrypted backup") from exc


def import_data_dir(
    data_dir: Path,
    archive: bytes,
    *,
    replace: bool = True,
    passphrase: str | None = None,
) -> dict:
    """
    Restore a backup zip into data_dir.

    When replace=True (default), replaces known hub files after extracting to a
    staging folder. Does not touch unrelated files in data_dir.
    Encrypted archives require passphrase.
    """
    if is_encrypted_backup(archive):
        if not passphrase:
            raise ValueError("encrypted backup requires a passphrase")
        archive = decrypt_backup(archive, passphrase)
    elif passphrase:
        raise ValueError("passphrase provided but archive is not encrypted")

    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adhd-hub-import-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(archive), "r") as zf:
            # Prevent zip-slip
            for info in zf.infolist():
                dest = (tmp_path / info.filename).resolve()
                if not str(dest).startswith(str(tmp_path.resolve())):
                    raise ValueError(f"unsafe path in archive: {info.filename}")
            zf.extractall(tmp_path)

        restored: list[str] = []
        for name in sorted(_INCLUDE_NAMES):
            src = tmp_path / name
            if not src.exists():
                continue
            dest = data_dir / name
            if replace and dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            restored.append(name)
        if not restored:
            raise ValueError("archive contained no hub data files")
        return {"restored": restored, "data_dir": str(data_dir)}
