"""Notes Summarise v1: parse/gates, persist, API soft AI-off."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from adhd_hub.ai_client import (
    AiNotesSummaryResult,
    generate_notes_summary,
    structured_notes_summary_prompt,
)
from adhd_hub.config import Settings
from adhd_hub.models import Thread, ThreadStatus, ThreadUpsert
from adhd_hub.notes_summary import (
    NotesSummaryCard,
    card_from_ai_text,
    extract_json_object,
    notes_summary_cache_key,
    notes_summary_card_html,
    parse_notes_summary_payload,
)
from adhd_hub.service import HubService


def _thread(**kwargs) -> Thread:
    now = datetime.now(UTC)
    base = {
        "id": "t-sum",
        "summary": "Ship notes summarise",
        "status": ThreadStatus.open,
        "project_slug": "demo",
        "focus": "Persist AI card only",
        "goal": "One-shot summarise on reader",
        "next_steps": ["Wire API", "Add tests"],
        "resume_step": "Open notes reader",
        "created_at": now,
        "updated_at": now,
    }
    base.update(kwargs)
    return Thread(**base)


def _service(tmp_path: Path) -> HubService:
    return HubService(Settings(data_dir=tmp_path / "data", auth_token="t"))


def test_extract_json_object_from_fence() -> None:
    raw = 'Here you go:\n```json\n{"done":"Shipped API","plan_focus":"Tests","next":["docs"]}\n```\n'
    data = extract_json_object(raw)
    assert data is not None
    assert data["done"] == "Shipped API"


def test_card_from_ai_text_caps_next_and_rejects_empty() -> None:
    card, reject = card_from_ai_text(
        json.dumps(
            {
                "done": "Built parser",
                "plan_focus": "Ship v1",
                "next": ["Wire API", "Add tests", "Update docs", "Extra fourth"],
                "blocked": None,
                "resume": "Run pytest",
            }
        )
    )
    assert reject is None
    assert card is not None
    assert card.next_steps == ["Wire API", "Add tests", "Update docs"]
    empty, reject_empty = card_from_ai_text('{"blocked":"waiting"}')
    assert empty is None
    assert reject_empty


def test_notes_summary_card_html_escapes() -> None:
    html = notes_summary_card_html(
        NotesSummaryCard(
            done='Shipped <script>alert(1)</script>',
            plan_focus="Focus",
            next_steps=["One"],
        )
    )
    assert "notes-summary-card" in html
    assert "<script>" not in html
    assert "Plan · Focus" in html
    assert "Done" in html


def test_structured_notes_summary_prompt_skips_boilerplate_notes() -> None:
    thread = _thread()
    prompt = structured_notes_summary_prompt(
        thread,
        note_contents=[
            "Thread upserted from Cursor — ritual",
            "## Human note\n\nChose store meta for persistence",
        ],
    )
    assert "Chose store meta" in prompt or "persistence" in prompt
    assert "Thread upserted from" not in prompt
    assert '"done"' in prompt


def test_generate_notes_summary_parses_provider_json(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        auth_token="t",
        ai_enabled=True,
        ai_base_url="http://ai.test/v1",
        ai_model="llama3.2",
    )

    class FakeResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "done": "Wired endpoint",
                                    "plan_focus": "Persist card",
                                    "next": ["Tests", "Docs"],
                                    "blocked": None,
                                    "resume": "Open PR",
                                }
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, *args, **kwargs):
            return FakeResp()

        def close(self) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = generate_notes_summary(settings, _thread())
    assert result.card is not None
    assert result.card.done == "Wired endpoint"
    assert result.card.next_steps == ["Tests", "Docs"]


def test_summarise_notes_ai_off_settings_hint_no_invent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(
            summary="Need summarise",
            project_slug="demo",
            focus="Soft AI-off",
            next_steps=["Open settings"],
        )
    )
    service.store.add_progress_note("demo", "## Note\n\nHuman body", thread_id=thread.id)
    before = service.store.list_progress_notes("demo", thread_id=thread.id)
    out = service.summarise_notes(thread.id)
    assert out["ai_attempted"] is False
    assert out["settings_hint"] is True
    assert out["summary"] is None
    assert "Settings" in out["message"]
    after = service.store.list_progress_notes("demo", thread_id=thread.id)
    assert len(after) == len(before)
    assert after[0]["content"] == before[0]["content"]
    assert "notes-summary-card" not in (out["progress_html"] or "")


def test_summarise_notes_persists_and_regenerate_overwrites(
    monkeypatch, tmp_path: Path
) -> None:
    service = _service(tmp_path)
    object.__setattr__(service.settings, "ai_enabled", True)
    object.__setattr__(service.settings, "ai_base_url", "http://ai.test/v1")
    object.__setattr__(service.settings, "ai_model", "llama3.2")

    thread = service.store.upsert_thread(
        ThreadUpsert(
            summary="Persist summary",
            project_slug="demo",
            goal="Keep notes intact",
            focus="Cache meta",
            next_steps=["Call AI"],
            resume_step="Press Summarise",
        )
    )
    service.store.add_progress_note(
        "demo", "## Decision\n\nUse store meta", thread_id=thread.id
    )
    note_count = len(service.store.list_progress_notes("demo", thread_id=thread.id))

    cards = [
        NotesSummaryCard(
            done="First card",
            plan_focus="v1",
            next_steps=["A"],
            resume="Ship",
        ),
        NotesSummaryCard(
            done="Second card",
            plan_focus="v1 regenerate",
            next_steps=["B", "C"],
            resume="Merge",
        ),
    ]
    calls = {"n": 0}

    def fake_generate(settings, thr, *, note_contents=None, client=None):
        idx = min(calls["n"], len(cards) - 1)
        calls["n"] += 1
        return AiNotesSummaryResult(card=cards[idx])

    monkeypatch.setattr("adhd_hub.ai_client.generate_notes_summary", fake_generate)
    monkeypatch.setattr("adhd_hub.ai_client.ai_configured", lambda _s: True)

    out1 = service.summarise_notes(thread.id)
    assert out1["ai_attempted"] is True
    assert out1["summary"]["done"] == "First card"
    assert "notes-summary-card" in out1["progress_html"]
    assert "First card" in out1["progress_html"]
    key = notes_summary_cache_key(thread.id)
    raw = service.store.get_meta(key)
    assert raw
    stored = parse_notes_summary_payload(json.loads(raw) if isinstance(raw, str) else raw)
    assert stored and stored.done == "First card"

    out2 = service.summarise_notes(thread.id)
    assert out2["summary"]["done"] == "Second card"
    assert "Second card" in out2["progress_html"]
    assert "First card" not in out2["progress_html"]

    after = service.store.list_progress_notes("demo", thread_id=thread.id)
    assert len(after) == note_count
    assert after[0]["content"] == "## Decision\n\nUse store meta"


def test_reader_html_includes_persisted_summary_without_api(tmp_path: Path) -> None:
    service = _service(tmp_path)
    thread = service.store.upsert_thread(
        ThreadUpsert(summary="Reopen", project_slug="demo", focus="Show card")
    )
    service._write_notes_summary(
        thread.id,
        NotesSummaryCard(
            done="Already summarised",
            plan_focus="Survive reopen",
            next_steps=["Verify HTML"],
        ),
    )
    html = service.thread_notes_context_html(thread)
    assert "notes-summary-card" in html
    assert "Already summarised" in html
    assert "notes-continuity-card" in html
    assert "Reopen" in html
