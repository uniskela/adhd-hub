from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

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


def _passphrase_cipher(passphrase: str) -> Fernet:
    digest = hashlib.sha256(f"adhd-hub-backup-v1:{passphrase}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def export_data_dir(data_dir: Path, *, passphrase: str | None = None) -> bytes:
    """Zip hub data (SQLite, wiki, forge/prefs) for migrate/restore.

    When passphrase is set, wraps the zip in a Fernet envelope (not a plain zip).
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
    token = _passphrase_cipher(passphrase).encrypt(raw)
    meta = json.dumps({"format": _ENC_FORMAT, "version": 1}).encode()
    return _ENC_MAGIC + len(meta).to_bytes(4, "big") + meta + token


def is_encrypted_backup(archive: bytes) -> bool:
    return archive.startswith(_ENC_MAGIC)


def decrypt_backup(archive: bytes, passphrase: str) -> bytes:
    if not is_encrypted_backup(archive):
        raise ValueError("archive is not an encrypted ADHD Hub backup")
    meta_len = int.from_bytes(archive[8:12], "big")
    meta_raw = archive[12 : 12 + meta_len]
    try:
        meta = json.loads(meta_raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("corrupt encrypted backup header") from exc
    if meta.get("format") != _ENC_FORMAT:
        raise ValueError("unsupported encrypted backup format")
    token = archive[12 + meta_len :]
    try:
        return _passphrase_cipher(passphrase).decrypt(token)
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
