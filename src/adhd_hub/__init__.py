"""ADHD Progress Hub — self-hosted unfinished-work memory for coding agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("adhd-hub")
except PackageNotFoundError:  # pragma: no cover - editable / source tree
    __version__ = "0.3.10"
