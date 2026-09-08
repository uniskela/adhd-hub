from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

# Files/dirs under data/ that make a movable hub instance.
_INCLUDE_NAMES = {
    "hub.sqlite3",
    "wiki",
    "forge.json",
    "prefs.json",
}


def export_data_dir(data_dir: Path) -> bytes:
    """Zip hub data (SQLite, wiki, forge/prefs) for migrate/restore."""
    data_dir = data_dir.resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "adhd-hub-backup.json",
            '{"format":"adhd-hub-backup","version":1}\n',
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
    return buf.getvalue()


def import_data_dir(data_dir: Path, archive: bytes, *, replace: bool = True) -> dict:
    """
    Restore a backup zip into data_dir.

    When replace=True (default), replaces known hub files after extracting to a
    staging folder. Does not touch unrelated files in data_dir.
    """
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
