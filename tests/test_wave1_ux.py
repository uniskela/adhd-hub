from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adhd_hub.config import Settings
from adhd_hub.models import ProjectUpsert, ReminderCreate, ReminderKind
from adhd_hub.service import HubService


def _service(tmp_path):
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_reminder_snooze_and_dismiss(tmp_path) -> None:
    service = _service(tmp_path)
    due = datetime.now(UTC) - timedelta(minutes=5)
    rem = service.set_reminder(
        ReminderCreate(message="Drink water", kind=ReminderKind.once, due_at=due)
    )
    assert any(r.id == rem.id for r in service.store.due_reminders())

    snoozed = service.snooze_reminder(rem.id, minutes=60)
    assert snoozed.due_at is not None
    assert snoozed.due_at > datetime.now(UTC)
    assert rem.id not in {r.id for r in service.store.due_reminders()}

    dismissed = service.dismiss_reminder(rem.id)
    assert dismissed.handled is True
    assert rem.id not in {r.id for r in service.store.list_reminders(include_handled=False)}


def test_session_reminder_respects_snooze_gate(tmp_path) -> None:
    service = _service(tmp_path)
    rem = service.set_reminder(
        ReminderCreate(message="Return to draft", kind=ReminderKind.session)
    )
    assert any(r.id == rem.id for r in service.store.due_reminders())
    service.snooze_reminder(rem.id, minutes=30)
    assert rem.id not in {r.id for r in service.store.due_reminders()}


def test_soft_archive_and_restore_project(tmp_path) -> None:
    service = _service(tmp_path)
    service.upsert_project(ProjectUpsert(title="Side Quest", slug="side-quest"))
    active = service.list_projects()
    assert any(p["slug"] == "side-quest" for p in active)

    archived = service.archive_project("side-quest")
    assert archived["archived"] is True
    assert not any(p["slug"] == "side-quest" for p in service.list_projects())
    assert any(
        p["slug"] == "side-quest" for p in service.list_projects(include_archived=True)
    )

    restored = service.restore_project("side-quest")
    assert restored["archived"] is False
    assert any(p["slug"] == "side-quest" for p in service.list_projects())


def test_inbox_cannot_be_archived(tmp_path) -> None:
    import pytest

    service = _service(tmp_path)
    service.store.ensure_project_for_slug("unclassified", title="Inbox")
    with pytest.raises(ValueError, match="Inbox"):
        service.archive_project("unclassified")


def test_snooze_preserves_future_once_due(tmp_path) -> None:
    service = _service(tmp_path)
    future = datetime.now(UTC) + timedelta(hours=5)
    rem = service.set_reminder(
        ReminderCreate(message="Later", kind=ReminderKind.once, due_at=future)
    )
    snoozed = service.snooze_reminder(rem.id, minutes=60)
    assert snoozed.due_at is not None
    assert abs((snoozed.due_at - future).total_seconds()) < 2


def test_daily_snooze_can_resurface_same_day(tmp_path) -> None:
    service = _service(tmp_path)
    rem = service.set_reminder(
        ReminderCreate(message="Daily stretch", kind=ReminderKind.daily)
    )
    fired_at = datetime.now(UTC) - timedelta(minutes=30)
    snooze_end = datetime.now(UTC) - timedelta(minutes=1)
    with service.store._conn() as conn:
        conn.execute(
            "UPDATE reminders SET last_fired_at = ?, due_at = ? WHERE id = ?",
            (fired_at.isoformat(), snooze_end.isoformat(), rem.id),
        )
    due_ids = {r.id for r in service.store.due_reminders()}
    assert rem.id in due_ids


def test_overview_includes_due_reminders(tmp_path) -> None:
    service = _service(tmp_path)
    service.set_reminder(ReminderCreate(message="Stretch", kind=ReminderKind.session))
    overview = service.overview()
    assert any(r["message"] == "Stretch" for r in overview["due_reminders"])

