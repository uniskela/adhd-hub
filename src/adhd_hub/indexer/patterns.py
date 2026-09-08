from __future__ import annotations

import re

# Inspired by shaheer-00/claude-adhd transcript heuristics (see ATTRIBUTION.md).

TASK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\bi(?:'ll| will| gonna| need to| have to| should| want to)\b[^.!?]{3,120}\b"
        r"(later|tomorrow|next time|soon|eventually)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bremind me\b", re.IGNORECASE),
    re.compile(r"\bdon'?t let me forget\b", re.IGNORECASE),
    re.compile(r"\bi'?ll get (back|around) to\b", re.IGNORECASE),
    re.compile(r"\badd (it|this) to (my|the) (todo|list)\b", re.IGNORECASE),
    re.compile(r"\bnext step\b", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"\btodo:\s", re.IGNORECASE),
    re.compile(r"\bwe should (do|try|build|add|fix|refactor|test|migrate)\b", re.IGNORECASE),
    re.compile(r"\blet'?s (do|try|build|add|fix|refactor|test|migrate)\b", re.IGNORECASE),
    re.compile(r"\bhalf[- ]?(done|finished|complete)\b", re.IGNORECASE),
    re.compile(r"\bin progress\b", re.IGNORECASE),
    re.compile(r"\bmigration\b", re.IGNORECASE),
    re.compile(r"\bwhat if we\b", re.IGNORECASE),
]

COMPLETION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(finished|done|shipped|fixed|resolved|implemented|completed|migrated|deployed)\b", re.IGNORECASE),
    re.compile(r"\bworks? now\b", re.IGNORECASE),
    re.compile(r"\ball (tests? )?pass(ing|ed)?\b", re.IGNORECASE),
]

QUESTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\?\s*$"),
    re.compile(r"\b( wh(?:at|ich|ere|en|o|y)|how|should i|do you want|want me to)\b", re.IGNORECASE),
]

SKIP_PREFIXES = ("<", "[{", "{")


def looks_like_command(text: str) -> bool:
    return any(text.startswith(p) for p in SKIP_PREFIXES)


def clean_summary(text: str, max_len: int = 200) -> str:
    return re.sub(r"\s+", " ", text).strip()[:max_len]


def matches_task(text: str) -> bool:
    return any(p.search(text) for p in TASK_PATTERNS)


def looks_like_question(text: str) -> bool:
    t = text.strip()
    if len(t) < 20 or len(t) > 500:
        return False
    return any(p.search(t) for p in QUESTION_PATTERNS)
