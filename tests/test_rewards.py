from datetime import UTC, datetime

from adhd_hub.config import Settings
from adhd_hub.models import ThreadStatus, ThreadUpsert
from adhd_hub.prefs import HubPrefs
from adhd_hub.service import HubService


def test_rewards_follow_local_day_and_use_real_completions(tmp_path, monkeypatch):
    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    service.save_prefs(HubPrefs(timezone="America/Los_Angeles"))
    # 00:30 UTC is still the previous day in Los Angeles.
    now = datetime(2026, 9, 8, 0, 30, tzinfo=UTC)
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: now)
    completed = service.store.upsert_thread(
        ThreadUpsert(summary="One step", status=ThreadStatus.done)
    )
    service.store.upsert_thread(ThreadUpsert(summary="Still open"))
    overview = service.overview()
    assert overview["done"] == 1
    assert overview["done_today"] == 1
    assert overview["next_up"]["summary"] == "Still open"
    assert overview["added_vs_finished"][-1]["date"] == "2026-09-07"
    assert overview["added_vs_finished"][-1]["finished"] == 1
    service.store.mark_status(completed.id, ThreadStatus.done)
    assert service.overview()["done"] == 1
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: datetime(2026, 9, 8, 8, tzinfo=UTC))
    assert service.overview()["done_today"] == 0
    assert service.overview()["done"] == 1


def test_rewards_count_beyond_the_thread_listing_limit(tmp_path):
    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    for i in range(501):
        service.store.upsert_thread(ThreadUpsert(summary=f"Step {i}", status=ThreadStatus.done))
    assert service.overview()["done"] == 501


def test_repeated_completion_keeps_original_day_and_wiki(tmp_path, monkeypatch):
    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    first_day = datetime(2026, 9, 7, 12, tzinfo=UTC)
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: first_day)
    thread = service.store.upsert_thread(ThreadUpsert(summary="Finish once", project_slug="repeat"))
    completed = service.mark_done(thread.id, note="Finished for real")
    progress = service.wiki.read_progress("repeat")
    monkeypatch.setattr("adhd_hub.store.utcnow", lambda: datetime(2026, 9, 9, 12, tzinfo=UTC))
    retried = service.mark_done(thread.id, note="Retry from another browser")
    assert retried.updated_at == completed.updated_at
    assert service.wiki.read_progress("repeat") == progress
    assert service.overview()["done_today"] == 0
    assert service.overview()["done"] == 1
    assert service.overview()["added_vs_finished"][-1]["finished"] == 0


def test_concurrent_status_changes_record_one_transition(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="One completion", project_slug="race")
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(
                lambda _: service.store.transition_status(
                    thread.id, ThreadStatus.done, note="Done"
                ),
                range(8),
            )
        )
    assert sum(changed for _, changed in results) == 1
    assert len({result.updated_at for result, _ in results}) == 1
    with service.store._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM progress_notes").fetchone()[0] == 1


def test_reward_milestones_and_rank_boundaries():
    from adhd_hub.rewards import reward_summary

    for total, rank, badges in [
        (0, "Seedling", 0),
        (1, "Seedling", 1),
        (4, "Seedling", 1),
        (5, "Sprout", 2),
        (15, "Grower", 3),
        (30, "Pathfinder", 4),
        (60, "Wayfinder", 5),
        (100, "Trailblazer", 6),
        (501, "Trailblazer", 6),
    ]:
        summary = reward_summary(total)
        assert summary["rank"]["name"] == rank
        assert sum(b["earned"] for b in summary["badges"]) == badges
        assert summary["xp"] == total * 10
        assert summary["level"] == total // 5 + 1
        assert summary["scope"] == "hub"
        if total < 100:
            assert summary["next_rank"]["remaining"] > 0
        else:
            assert summary["next_rank"] is None


def test_reward_overview_recomputes_after_reopening(tmp_path):
    service = HubService(Settings(data_dir=tmp_path, auth_token="secret"))
    threads = [
        service.store.upsert_thread(
            ThreadUpsert(summary=f"Private task {i}", status=ThreadStatus.done)
        )
        for i in range(5)
    ]
    assert service.overview()["rewards"]["rank"]["id"] == "sprout"
    service.store.mark_status(threads[0].id, ThreadStatus.open)
    rewards = service.overview()["rewards"]
    assert rewards["rank"]["id"] == "seedling"
    assert rewards["xp"] == 40
    assert rewards["next_rank"]["remaining"] == 1
    assert "Private task" not in str(rewards)
