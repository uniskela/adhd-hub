from __future__ import annotations

import io
import os

from adhd_hub import cli_style


def test_color_disabled_when_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert cli_style.color_enabled(stream) is False
    assert "\x1b[" not in cli_style.style("hi", fg="green", stream=stream)


def test_color_disabled_when_not_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    assert cli_style.color_enabled(stream) is False


def test_color_enabled_on_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert cli_style.color_enabled(stream) is True
    out = cli_style.style("ok", fg="green", stream=stream)
    assert out.startswith("\x1b[")
    assert out.endswith("\x1b[0m")
    assert "ok" in out


def test_status_mark_mapping() -> None:
    assert cli_style.status_mark("ok") == "OK"
    assert cli_style.status_mark("skipped") == "--"
    assert cli_style.status_mark("manual") == "--"
    assert cli_style.status_mark("warn") == "!!"
    assert cli_style.status_mark("missing") == "!!"
    assert cli_style.status_mark("error") == "XX"


def test_print_running_dim_prefix(capsys, monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("ADHD_HUB_NO_COLOR", raising=False)
    monkeypatch.setattr(cli_style.sys.stdout, "isatty", lambda: False)
    cli_style.print_running(["graphify", "cursor", "install"])
    assert "→ Running  graphify cursor install" in capsys.readouterr().out
