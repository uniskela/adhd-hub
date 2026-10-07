"""Generic sample pack for Settings / ADHD_HUB_SEED_DEMO (never overwrites real data)."""

from __future__ import annotations

from typing import Any

# Marker on every sample thread — Remove sample data deletes only these.
DEMO_SOURCE_TOOL = "demo"

# Stable slugs — Load is a no-op if any of these projects already exist.
SAMPLE_PROJECT_SLUGS: tuple[str, ...] = (
    "sample-demo-site",
    "sample-home-admin",
    "sample-learning",
)


def sample_payload() -> dict[str, Any]:
    """Generic Demo website / Home admin / Learning notes pack (README gallery style)."""
    projects = [
        {
            "slug": "sample-demo-site",
            "title": "Demo website",
            "tags": ["Creative", "Sample"],
        },
        {
            "slug": "sample-home-admin",
            "title": "Home admin",
            "tags": ["Personal", "Sample"],
        },
        {
            "slug": "sample-learning",
            "title": "Learning notes",
            "tags": ["Learning", "Sample"],
        },
    ]
    threads = [
        {
            "summary": "Polish the landing page",
            "project_slug": "sample-demo-site",
            "status": "open",
            "focus": "Tighten the hero copy",
            "goal": "Ship a calmer first viewport for the demo site.",
            "next_steps": ["Draft one clearer headline"],
            "resume_step": "Draft one clearer headline",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Book a dentist visit",
            "project_slug": "sample-home-admin",
            "status": "open",
            "focus": "Find a nearby clinic",
            "goal": "Schedule routine care without overthinking it.",
            "next_steps": ["Check opening hours"],
            "resume_step": "Check opening hours",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Review design notes",
            "project_slug": "sample-learning",
            "status": "open",
            "focus": "Skim last week's notes",
            "goal": "Keep learning notes scannable for the next session.",
            "next_steps": ["Write one takeaway"],
            "resume_step": "Write one takeaway",
            "source_tool": DEMO_SOURCE_TOOL,
        },
        {
            "summary": "Collect homepage ideas",
            "project_slug": "sample-demo-site",
            "status": "done",
            "focus": "Choose a direction",
            "goal": "Archive finished exploration.",
            "next_steps": ["Save three examples"],
            "resume_step": "Save three examples",
            "source_tool": DEMO_SOURCE_TOOL,
        },
    ]
    return {
        "projects": projects,
        "threads": threads,
        "stale_summary": "Book a dentist visit",
        "progress_note": {
            "project_slug": "sample-demo-site",
            "title": "Polish the landing page",
            "goal": "Ship a calmer first viewport for the demo site.",
            "focus": "Tighten the hero copy",
            "next_steps": ["Draft one clearer headline"],
            "resume_step": "Draft one clearer headline",
            "content": (
                "Sample note: keep the hero quiet — brand, one line, one CTA."
            ),
            "source_tool": DEMO_SOURCE_TOOL,
            "create_thread_if_missing": False,
        },
    }
