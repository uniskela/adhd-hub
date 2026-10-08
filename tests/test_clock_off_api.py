from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adhd_hub.app import create_app
from adhd_hub.config import Settings

AUTH = {"Authorization": "Bearer secret"}
SCHEDULE = {
    "enabled": True,
    "active_days": [0, 1, 2, 3, 4],
    "clock_off_time": "23:30",
    "wind_down_minutes": 45,
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", auth_token="secret")


def test_clock_off_endpoints_require_authentication(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/clock-off").status_code == 401
        assert client.post("/api/clock-off/override", json={"minutes": 30}).status_code == 401
        assert client.delete("/api/clock-off/override").status_code == 401
        assert client.put("/api/prefs", json={"clock_off": SCHEDULE}).status_code == 401
        response = client.get("/api/clock-off", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["schedule"]["enabled"] is False
        assert response.json()["clock_off"]["state"] == "normal"


def test_schedule_partial_updates_preserve_preferences_and_override(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.put(
            "/api/prefs", headers=AUTH, json={"timezone": "Europe/Helsinki", "clock_off": SCHEDULE}
        )
        assert response.status_code == 200
        override = client.post("/api/clock-off/override", headers=AUTH, json={"minutes": 60})
        assert override.status_code == 200
        deadline = client.get("/api/prefs", headers=AUTH).json()["clock_off_override_until"]
        assert deadline is not None

        response = client.put(
            "/api/prefs", headers=AUTH, json={"clock_off": {"wind_down_minutes": 10}}
        )
        assert response.status_code == 200
        prefs = response.json()
        assert prefs["clock_off"] == {**SCHEDULE, "wind_down_minutes": 10}
        assert prefs["timezone"] == "Europe/Helsinki"
        assert prefs["clock_off_override_until"] == deadline
        unrelated = client.put("/api/prefs", headers=AUTH, json={"connect_skills_mode": "off"})
        assert unrelated.status_code == 200
        assert unrelated.json()["clock_off"] == {**SCHEDULE, "wind_down_minutes": 10}
        assert unrelated.json()["clock_off_override_until"] == deadline


@pytest.mark.parametrize(
    "schedule",
    [
        None,
        [],
        {"enabled": "true"},
        {"enabled": 1},
        {"active_days": [7]},
        {"active_days": [-1]},
        {"active_days": [True]},
        {"active_days": ["1"]},
        {"active_days": "Monday"},
        {"clock_off_time": "24:00"},
        {"clock_off_time": "9:30"},
        {"wind_down_minutes": -1},
        {"wind_down_minutes": 241},
        {"wind_down_minutes": True},
        {"wind_down_minutes": "30"},
        {"unknown": True},
        {"override_until": "2099-01-01T00:00:00Z"},
    ],
)
def test_invalid_schedule_does_not_mutate_prefs(settings: Settings, schedule: object) -> None:
    with TestClient(create_app(settings)) as client:
        before = client.get("/api/prefs", headers=AUTH).json()
        response = client.put("/api/prefs", headers=AUTH, json={"clock_off": schedule})
        assert response.status_code == 400
        assert client.get("/api/prefs", headers=AUTH).json() == before


@pytest.mark.parametrize("deadline", [None, "2099-01-01T00:00:00Z"])
def test_override_cannot_be_written_via_preferences(settings: Settings, deadline: object) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.put(
            "/api/prefs", headers=AUTH, json={"clock_off_override_until": deadline}
        )
        assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"minutes": 0},
        {"minutes": 1441},
        {"minutes": True},
        {"minutes": "30"},
        {"minutes": 1.5},
        {"minutes": None},
        {"minutes": 30, "until": "2099-01-01"},
    ],
)
def test_invalid_override_requests(settings: Settings, payload: dict) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/clock-off/override", headers=AUTH, json=payload).status_code == 422
        assert client.get("/api/prefs", headers=AUTH).json()["clock_off_override_until"] is None


def test_clock_off_schedule_and_override_survive_restart(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.put(
            "/api/prefs", headers=AUTH, json={"timezone": "America/New_York", "clock_off": SCHEDULE}
        )
        assert response.status_code == 200
        override = client.post("/api/clock-off/override", headers=AUTH, json={"minutes": 60})
        assert override.status_code == 200
        assert override.json()["schedule"] == SCHEDULE
        assert override.json()["clock_off"]["state"] == "overridden"
        saved = client.get("/api/prefs", headers=AUTH).json()

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/prefs", headers=AUTH).json() == saved
        state = client.get("/api/clock-off", headers=AUTH).json()
        assert state["schedule"] == SCHEDULE
        assert state["clock_off"]["state"] == "overridden"
        cancelled = client.delete("/api/clock-off/override", headers=AUTH)
        assert cancelled.status_code == 200
        assert cancelled.json()["clock_off"]["state"] != "overridden"
        assert client.get("/api/prefs", headers=AUTH).json()["clock_off_override_until"] is None

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/prefs", headers=AUTH).json()["clock_off_override_until"] is None


def test_override_expires_at_exact_deadline(settings: Settings, monkeypatch) -> None:
    import adhd_hub.clock_off as clock_off_module
    import adhd_hub.service as service_module

    instant = datetime(2026, 10, 5, 22, 30, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", Clock)
    monkeypatch.setattr(clock_off_module, "datetime", Clock)
    with TestClient(create_app(settings)) as client:
        client.put(
            "/api/prefs", headers=AUTH, json={"clock_off": {**SCHEDULE, "clock_off_time": "22:00"}}
        ).raise_for_status()
        assert (
            client.get("/api/clock-off", headers=AUTH).json()["clock_off"]["state"] == "clocked_off"
        )
        response = client.post("/api/clock-off/override", headers=AUTH, json={"minutes": 30})
        assert response.status_code == 200
        assert response.json()["clock_off"]["state"] == "overridden"
        assert response.json()["clock_off"]["override_until"] == "2026-10-05T23:00:00Z"
        instant += timedelta(minutes=29, seconds=59)
        assert (
            client.get("/api/clock-off", headers=AUTH).json()["clock_off"]["state"] == "overridden"
        )
        instant += timedelta(seconds=1)
        expired = client.get("/api/clock-off", headers=AUTH).json()["clock_off"]
        assert expired["state"] == "clocked_off"
        assert expired["override_until"] is None


@pytest.mark.parametrize("minutes", [1, 1440])
def test_override_duration_boundaries_are_accepted(settings: Settings, minutes: int) -> None:
    with TestClient(create_app(settings)) as client:
        client.put("/api/prefs", headers=AUTH, json={"clock_off": SCHEDULE}).raise_for_status()
        response = client.post("/api/clock-off/override", headers=AUTH, json={"minutes": minutes})
        assert response.status_code == 200
        assert response.json()["clock_off"]["state"] == "overridden"


def test_browser_clock_off_mutations_require_same_origin(settings: Settings) -> None:
    browser_headers = {"X-Hub-Request": "1", "Origin": "http://testserver"}
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/auth/login", headers=browser_headers, json={"token": "secret"}
        ).raise_for_status()
        client.put(
            "/api/prefs", headers=browser_headers, json={"clock_off": SCHEDULE}
        ).raise_for_status()
        assert client.get("/api/clock-off").status_code == 200
        for method, path, kwargs in [
            ("put", "/api/prefs", {"json": {"clock_off": {"enabled": False}}}),
            ("post", "/api/clock-off/override", {"json": {"minutes": 30}}),
            ("delete", "/api/clock-off/override", {}),
        ]:
            assert getattr(client, method)(path, **kwargs).status_code == 403
            assert (
                getattr(client, method)(
                    path, headers={**browser_headers, "Origin": "https://evil.example"}, **kwargs
                ).status_code
                == 403
            )
            assert (
                getattr(client, method)(path, headers=browser_headers, **kwargs).status_code == 200
            )
