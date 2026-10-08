from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from adhd_hub.clock_off import ClockOffSchedule, clock_off_state
from adhd_hub.config import Settings
from adhd_hub.mcp_app import build_mcp
from adhd_hub.prefs import HubPrefs, load_prefs, save_prefs
from adhd_hub.service import HubService


def state(at, *, timezone="UTC", override_until=None, **settings):
    return clock_off_state(
        ClockOffSchedule(enabled=True, **settings),
        timezone=timezone,
        override_until=override_until,
        now=datetime.fromisoformat(at),
    )


@pytest.mark.parametrize(
    "at, expected, remaining",
    [
        ("2026-10-09T21:44:59Z", "normal", 16),
        ("2026-10-09T21:45:00Z", "winding_down", 15),
        ("2026-10-09T21:59:59Z", "winding_down", 1),
        ("2026-10-09T22:00:00Z", "clocked_off", 0),
        ("2026-10-09T23:59:59Z", "clocked_off", 0),
        ("2026-10-10T00:00:00Z", "clocked_off", 0),
        ("2026-10-10T05:59:59Z", "clocked_off", 0),
        ("2026-10-10T06:00:00Z", "normal", 9600),
    ],
)
def test_friday_window_and_exact_boundaries(at, expected, remaining):
    result = state(at, active_days=[4])
    assert result.state == expected
    assert result.minutes_remaining == remaining
    if expected != "normal":
        assert result.resumes_at == "2026-10-10T06:00:00Z"
        assert result.clock_off_at == "2026-10-09T22:00:00Z"


@pytest.mark.parametrize(
    "at, expected",
    [
        ("2026-10-08T23:45:00Z", "normal"),
        ("2026-10-09T23:45:00Z", "winding_down"),
        ("2026-10-10T00:00:00Z", "winding_down"),
        ("2026-10-10T00:15:00Z", "clocked_off"),
        ("2026-10-10T05:59:59Z", "clocked_off"),
        ("2026-10-10T06:00:00Z", "normal"),
    ],
)
def test_overnight_schedule_uses_activation_day(at, expected):
    result = state(at, active_days=[5], clock_off_time="00:15", wind_down_minutes=30)
    assert result.state == expected
    if expected != "normal":
        assert result.clock_off_at == "2026-10-10T00:15:00Z"
        assert result.resumes_at == "2026-10-10T06:00:00Z"
        assert result.wind_down_at == "2026-10-09T23:45:00Z"


def test_clock_off_at_reset_time_resets_the_following_morning():
    result = state("2026-10-09T06:00:00Z", clock_off_time="06:00")
    assert result.state == "clocked_off"
    assert result.resumes_at == "2026-10-10T06:00:00Z"


@pytest.mark.parametrize(
    "zone, at, off, reset",
    [
        (
            "Australia/Sydney",
            "2026-10-09T11:00:00Z",
            "2026-10-09T11:00:00Z",
            "2026-10-09T19:00:00Z",
        ),
        (
            "America/Los_Angeles",
            "2026-10-10T05:00:00Z",
            "2026-10-10T05:00:00Z",
            "2026-10-10T13:00:00Z",
        ),
        (
            "Pacific/Kiritimati",
            "2026-10-09T08:00:00Z",
            "2026-10-09T08:00:00Z",
            "2026-10-09T16:00:00Z",
        ),
        ("Asia/Kathmandu", "2026-10-09T16:15:00Z", "2026-10-09T16:15:00Z", "2026-10-10T00:15:00Z"),
    ],
)
def test_local_day_is_independent_of_utc_date(zone, at, off, reset):
    result = state(at, timezone=zone, active_days=[4])
    assert result.state == "clocked_off"
    assert result.clock_off_at == off
    assert result.resumes_at == reset


@pytest.mark.parametrize(
    "at, expected",
    [
        ("2026-03-08T06:59:59Z", "normal"),
        ("2026-03-08T07:00:00Z", "winding_down"),
        ("2026-03-08T07:30:00Z", "clocked_off"),
        ("2026-03-08T09:59:59Z", "clocked_off"),
        ("2026-03-08T10:00:00Z", "normal"),
    ],
)
def test_missing_dst_time_shifts_forward_by_gap(at, expected):
    result = state(
        at,
        timezone="America/New_York",
        active_days=[6],
        clock_off_time="02:30",
        wind_down_minutes=30,
    )
    assert result.state == expected
    if expected != "normal":
        assert result.clock_off_at == "2026-03-08T07:30:00Z"  # 03:30 EDT
        assert result.resumes_at == "2026-03-08T10:00:00Z"


@pytest.mark.parametrize(
    "at, expected",
    [
        ("2026-11-01T05:14:59Z", "normal"),
        ("2026-11-01T05:15:00Z", "winding_down"),
        ("2026-11-01T05:30:00Z", "clocked_off"),
        ("2026-11-01T06:00:00Z", "clocked_off"),
        ("2026-11-01T06:30:00Z", "clocked_off"),
        ("2026-11-01T11:00:00Z", "normal"),
    ],
)
def test_repeated_dst_time_activates_once_at_first_occurrence(at, expected):
    result = state(at, timezone="America/New_York", active_days=[6], clock_off_time="01:30")
    assert result.state == expected
    if expected != "normal":
        assert result.clock_off_at == "2026-11-01T05:30:00Z"
        assert result.resumes_at == "2026-11-01T11:00:00Z"


@pytest.mark.parametrize(
    "at, reset",
    [
        ("2026-03-08T03:00:00Z", "2026-03-08T10:00:00Z"),
        ("2026-11-01T02:00:00Z", "2026-11-01T11:00:00Z"),
    ],
)
def test_evening_window_spans_dst_transition(at, reset):
    result = state(at, timezone="America/New_York", active_days=[5])
    assert result.state == "clocked_off"
    assert result.resumes_at == reset


def test_non_hour_dst_gap_and_elapsed_wind_down():
    result = state(
        "2026-10-03T15:15:00Z",
        timezone="Australia/Lord_Howe",
        active_days=[6],
        clock_off_time="02:15",
        wind_down_minutes=30,
    )
    assert result.state == "winding_down"
    assert result.clock_off_at == "2026-10-03T15:45:00Z"  # 02:45 +11
    assert result.resumes_at == "2026-10-03T19:00:00Z"


@pytest.mark.parametrize(
    "at, expected",
    [
        ("2026-10-09T22:29:59Z", "overridden"),
        ("2026-10-09T22:30:00Z", "clocked_off"),
        ("2026-10-10T00:00:00Z", "clocked_off"),
        ("2026-10-10T06:00:00Z", "normal"),
    ],
)
def test_override_expiry_is_exclusive_and_schedule_unchanged(at, expected):
    result = state(at, override_until="2026-10-10T00:30:00+02:00")
    assert result.state == expected
    assert result.override_until == ("2026-10-09T22:30:00Z" if expected == "overridden" else None)


def test_override_can_expire_into_wind_down():
    result = state("2026-10-09T21:50:00Z", override_until="2026-10-09T21:50:00Z")
    assert result.state == "winding_down"


def test_disabled_and_no_active_days_have_no_guidance():
    result = clock_off_state(
        ClockOffSchedule(), timezone="Australia/Sydney", override_until="2099-01-01T00:00:00Z"
    )
    assert result.state == "normal"
    assert not result.enabled
    assert result.guidance == []
    assert result.clock_off_at is result.resumes_at is result.override_until is None
    result = state("2026-10-09T22:00:00Z", active_days=[])
    assert result.state == "normal"
    assert result.clock_off_at is None
    assert result.guidance == []


def test_zero_lead_and_previous_off_window_precedence():
    assert state("2026-10-09T21:59:59Z", wind_down_minutes=0).state == "normal"
    assert state("2026-10-09T22:00:00Z", wind_down_minutes=0).state == "clocked_off"
    result = state("2026-10-09T05:00:00Z", clock_off_time="06:00", wind_down_minutes=240)
    assert result.state == "clocked_off"
    assert result.clock_off_at == "2026-10-08T06:00:00Z"


def test_legacy_defaults_and_preferences_persistence(tmp_path):
    (tmp_path / "prefs.json").write_text('{"timezone":"Australia/Sydney"}')
    assert not load_prefs(tmp_path).clock_off.enabled
    prefs = HubPrefs(
        timezone="Australia/Sydney",
        clock_off=ClockOffSchedule(
            enabled=True, active_days=[6, 4, 4], clock_off_time="00:30", wind_down_minutes=45
        ),
        clock_off_override_until="2026-10-10T10:00:00+11:00",
    )
    save_prefs(tmp_path, prefs)
    assert load_prefs(tmp_path) == prefs
    assert prefs.clock_off.active_days == [4, 6]
    assert prefs.clock_off_override_until == "2026-10-09T23:00:00Z"


@pytest.mark.parametrize(
    "settings",
    [
        {"enabled": "false"},
        {"enabled": 1},
        {"active_days": [True]},
        {"active_days": [-1]},
        {"active_days": [7]},
        {"active_days": ["4"]},
        {"clock_off_time": "24:00"},
        {"clock_off_time": "2:00"},
        {"clock_off_time": "22:00:00"},
        {"wind_down_minutes": -1},
        {"wind_down_minutes": 241},
        {"wind_down_minutes": True},
        {"wind_down_minutes": 2.5},
        {"surprise": "ignored?"},
    ],
)
def test_schedule_validation(settings):
    with pytest.raises(ValidationError):
        ClockOffSchedule(**settings)


@pytest.mark.parametrize("expiry", ["nonsense", "2026-10-09T22:30:00", "2026-10-09"])
def test_override_storage_requires_an_instant(expiry):
    with pytest.raises(ValidationError):
        HubPrefs(clock_off_override_until=expiry)


@pytest.mark.parametrize(
    "at, expected",
    [
        ("2026-10-09T20:00:00Z", "normal"),
        ("2026-10-09T21:50:00Z", "winding_down"),
        ("2026-10-09T22:30:00Z", "clocked_off"),
    ],
)
async def test_mcp_paths_share_state_and_advisory_guidance(tmp_path, monkeypatch, at, expected):
    service = HubService(Settings(data_dir=tmp_path, auth_token="test"))
    service.save_prefs(HubPrefs(clock_off=ClockOffSchedule(enabled=True)))
    now = datetime.fromisoformat(at)
    evaluator = service.clock_off_state
    monkeypatch.setattr(service, "clock_off_state", lambda: evaluator(now=now))
    server = build_mcp(service)
    for tool in ("get_overview", "session_digest"):
        result = await server.call_tool(tool, {})
        assert not result.is_error
        payload = result.structured_content["clock_off"]
        assert payload == evaluator(now=now).model_dump(mode="json")
        assert payload["state"] == expected
        if expected == "normal":
            assert payload["guidance"] == []
        else:
            guidance = " ".join(payload["guidance"])
            assert "substantial new work" in guidance
            assert "upsert_progress" in guidance
            assert "pause_thread" in guidance
            assert "concrete resume step" in guidance
            assert "advisory" in guidance and "user" in guidance
    catalog = {tool.name: tool for tool in await server.list_tools()}
    schema = catalog["session_digest"].output_schema
    assert "clock_off" in schema["properties"]
    assert schema["$defs"]["ClockOffState"]["properties"]["state"]["enum"] == [
        "normal",
        "winding_down",
        "clocked_off",
        "overridden",
    ]


async def test_disabled_mcp_keeps_current_behaviour_and_override_is_visible(tmp_path):
    service = HubService(Settings(data_dir=tmp_path, auth_token="test"))
    server = build_mcp(service)
    for tool in ("get_overview", "session_digest"):
        result = await server.call_tool(tool, {})
        assert result.structured_content["clock_off"]["state"] == "normal"
        assert result.structured_content["clock_off"]["guidance"] == []
    service.save_prefs(HubPrefs(clock_off=ClockOffSchedule(enabled=True)))
    service.set_clock_off_override(30)
    for tool in ("get_overview", "session_digest"):
        result = await server.call_tool(tool, {})
        assert result.structured_content["clock_off"]["state"] == "overridden"
        assert result.structured_content["clock_off"]["override_until"]
    service.set_clock_off_override(None)
    assert service.clock_off_state().override_until is None


def test_naive_now_uses_existing_utc_convention():
    aware = state("2026-10-09T22:00:00Z")
    naive = state("2026-10-09T22:00:00")
    assert aware == naive
    assert datetime.fromisoformat(aware.clock_off_at).tzinfo == UTC
