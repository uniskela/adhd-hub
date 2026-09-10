from __future__ import annotations

import json
from pathlib import Path

import pytest

from adhd_hub.backup import (
    decrypt_backup,
    encrypted_backup_meta,
    export_data_dir,
    import_data_dir,
    is_encrypted_backup,
)

_LEGACY_V1 = Path(__file__).parent / "fixtures" / "encrypted_backup_v1.enc"
_LEGACY_PASSPHRASE = "legacy-v1-passphrase"


def _enc_meta(archive: bytes) -> dict:
    assert archive.startswith(b"ADHDHUB1")
    meta_len = int.from_bytes(archive[8:12], "big")
    return json.loads(archive[12 : 12 + meta_len].decode())


def _tiny_data(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "prefs.json").write_text('{"timezone":"UTC"}', encoding="utf-8")
    (data / "hub.sqlite3").write_bytes(b"sqlite-placeholder")
    return data


def test_new_encrypted_export_uses_v2_scrypt_envelope(tmp_path: Path) -> None:
    archive = export_data_dir(_tiny_data(tmp_path), passphrase="correct horse")
    assert is_encrypted_backup(archive)
    meta = encrypted_backup_meta(archive)
    assert meta == _enc_meta(archive)
    assert meta["format"] == "adhd-hub-backup-encrypted"
    assert meta["version"] == 2
    assert meta["kdf"] == "scrypt"
    assert meta["salt"]
    assert int(meta["n"]) >= 2**14
    dest = tmp_path / "restored"
    result = import_data_dir(dest, archive, passphrase="correct horse")
    assert "prefs.json" in result["restored"]
    assert (dest / "prefs.json").read_text(encoding="utf-8") == '{"timezone":"UTC"}'


def test_new_encrypted_exports_use_distinct_salts(tmp_path: Path) -> None:
    data = _tiny_data(tmp_path)
    a = export_data_dir(data, passphrase="same")
    b = export_data_dir(data, passphrase="same")
    assert _enc_meta(a)["salt"] != _enc_meta(b)["salt"]
    assert a != b


def test_decrypt_legacy_v1_fixture(tmp_path: Path) -> None:
    archive = _LEGACY_V1.read_bytes()
    meta = _enc_meta(archive)
    assert meta["version"] == 1
    assert "kdf" not in meta
    dest = tmp_path / "restored"
    result = import_data_dir(dest, archive, passphrase=_LEGACY_PASSPHRASE)
    assert "prefs.json" in result["restored"]
    text = (dest / "prefs.json").read_text(encoding="utf-8")
    assert "encrypted-backup-v1" in text


def test_wrong_passphrase_fails_for_new_and_legacy(tmp_path: Path) -> None:
    archive = export_data_dir(_tiny_data(tmp_path), passphrase="correct horse")
    with pytest.raises(ValueError, match="wrong passphrase"):
        decrypt_backup(archive, "not the passphrase")
    with pytest.raises(ValueError, match="wrong passphrase"):
        decrypt_backup(_LEGACY_V1.read_bytes(), "not the passphrase")


def test_unknown_envelope_version_rejected() -> None:
    meta = json.dumps({"format": "adhd-hub-backup-encrypted", "version": 99}).encode()
    archive = b"ADHDHUB1" + len(meta).to_bytes(4, "big") + meta + b"not-a-fernet-token"
    with pytest.raises(ValueError, match="unsupported encrypted backup version"):
        decrypt_backup(archive, "any")


def test_oversized_scrypt_params_rejected() -> None:
    meta = json.dumps(
        {
            "format": "adhd-hub-backup-encrypted",
            "version": 2,
            "kdf": "scrypt",
            "salt": "AAAAAAAAAAAAAAAAAAAAAA==",
            "n": 2**30,
            "r": 8,
            "p": 1,
        }
    ).encode()
    archive = b"ADHDHUB1" + len(meta).to_bytes(4, "big") + meta + b"not-a-fernet-token"
    with pytest.raises(ValueError, match="KDF parameters"):
        decrypt_backup(archive, "any")
