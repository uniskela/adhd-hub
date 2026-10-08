"""Wave 7 return-cue coaching — advisory quality signal for ``resume_step``.

Deterministic and local: no LLM, no network, no forge lookups. The assessment
reads one thread's own structured fields (resume / goal / title / focus / next)
and never invents files, commands or project facts. A suggestion only ever
echoes text the same thread already stores.

Advisory only. Nothing here may block a save, pause or completion.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from adhd_hub.models import Thread, ThreadStatus

RETURN_CUE_CONTRACT_VERSION = 1

QUALITY_MISSING = "missing"
QUALITY_VAGUE = "vague"
QUALITY_CONCRETE = "concrete"

SIGNAL_EMPTY = "empty"
SIGNAL_PLACEHOLDER = "placeholder"
SIGNAL_NO_SPECIFICS = "no_specifics"
SIGNAL_REPEATS_GOAL = "repeats_goal"

HINT_MISSING = "No resume step yet. Add the first thing to do when you come back."
HINT_VAGUE = (
    "This resume step names nothing specific yet. "
    "Add what to open, run or check first."
)
HINT_REPEATS_GOAL = (
    "This repeats the goal. Name the first action that moves it forward."
)

_PLACEHOLDERS = frozenset(
    {"tbd", "tba", "todo", "wip", "n/a", "na", "none", "nothing", "-", "?", "...", "…", "x"}
)



def _words(block: str) -> frozenset[str]:
    return frozenset(re.findall(r"\S+", block))


# Words that carry no re-entry information on their own.
_FILLER = _words(
    """
    a an the and or then to of in on at for with from by as so but if
    it its this that these those i we my our me us you your they them
    is are was were be been being am do does did will would should can could
    may might must need needs needed have has had just also still only very
    up off out back into over through about around again
    later soon now tomorrow today tonight yesterday morning afternoon evening
    monday tuesday wednesday thursday friday saturday sunday week weekend
    next after before until once when where what how here there
    some any all more most rest maybe probably etc please
    """
)

# Verbs that say "do something" without saying what or where.
_GENERIC_VERBS = _words(
    """
    continue continuing resume resuming keep keeping carry go going proceed
    work working fix fixing finish finishing complete completing make making
    handle sort address resolve look looking check checking see review
    investigate figure think debug try start starting pick wrap finalize
    finalise polish clean cleanup improve update updating change tweak get
    come return revisit follow implement add run open left leave
    """
)

# Nouns and adjectives that point at nothing in particular.
_GENERIC_NOUNS = _words(
    """
    issue issues bug bugs problem problems error errors stuff thing things
    task tasks work job item items part parts bit rest remainder step steps
    changes code file files test tests testing feature features project
    thread ticket pr notes note above below everything something anything
    same one way progress session failing broken remaining last other
    previous current new old few final done
    """
)

_GENERIC = _FILLER | _GENERIC_VERBS | _GENERIC_NOUNS

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
# Concrete anchors: something a person or agent can open, run or look up.
_ANCHOR_RES = (
    re.compile(r"`[^`\n]+`"),  # inline code
    re.compile(r"(?<![\w.])[\w-]{2,}(?:[./][\w-]+)*\.[A-Za-z][A-Za-z0-9]{0,4}(?![\w.])"),  # file.ext
    re.compile(r"(?<![\w./-])(?!and/or\b)[\w.-]{2,}/[\w.-]{2,}"),  # path/segment
    re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b"),  # snake_case
    re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),  # camelCase
    re.compile(r"\b[A-Za-z_][\w.]*\(\)"),  # call()
    re.compile(r"(?<!\w)#\d+\b"),  # issue / PR reference
)


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    return " ".join(text.split()).strip()


def _fold(value: str | None) -> str:
    return _normalize(value).casefold().strip(" .!?…:;,-")


def _has_anchor(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ANCHOR_RES)


def _specific_words(text: str) -> list[str]:
    specifics: list[str] = []
    for match in _WORD_RE.finditer(text):
        word = match.group(0).casefold()
        if word in _GENERIC:
            continue
        # A lone ASCII letter says nothing; a lone CJK glyph can be a full word.
        if len(word) < 2 and word.isascii():
            continue
        specifics.append(word)
    return specifics


def _is_concrete_text(text: str) -> bool:
    return bool(text) and (_has_anchor(text) or bool(_specific_words(text)))


def _classify(cue: str, *, goal: str | None, title: str | None) -> tuple[str, list[str]]:
    if not cue:
        return QUALITY_MISSING, [SIGNAL_EMPTY]
    folded = _fold(cue)
    if not folded or folded in _PLACEHOLDERS:
        return QUALITY_VAGUE, [SIGNAL_PLACEHOLDER]
    if not _is_concrete_text(cue):
        return QUALITY_VAGUE, [SIGNAL_NO_SPECIFICS]
    # A cue that only restates the outcome gives no first action to start from.
    if folded in {_fold(goal), _fold(title)} - {""}:
        return QUALITY_VAGUE, [SIGNAL_REPEATS_GOAL]
    return QUALITY_CONCRETE, []


def _suggestion(
    cue: str,
    *,
    goal: str | None,
    title: str | None,
    focus: str | None,
    next_steps: list[str] | None,
) -> dict[str, str] | None:
    """Offer the thread's own Focus / first Next step when it is more concrete."""
    candidates = [("focus", focus)]
    if next_steps:
        candidates.append(("next_steps", next_steps[0]))
    for source, raw in candidates:
        text = _normalize(raw)
        if not text or _fold(text) == _fold(cue):
            continue
        quality, _ = _classify(text, goal=goal, title=title)
        if quality == QUALITY_CONCRETE:
            return {"source": source, "text": text}
    return None


def assess_return_cue(
    resume_step: str | None,
    *,
    goal: str | None = None,
    title: str | None = None,
    focus: str | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Assess one resume cue against its own thread context.

    Returns a small advisory dict::

        {"quality": "missing" | "vague" | "concrete",
         "signals": [...],          # stable machine-readable reasons
         "hint": str | None,        # one calm sentence; None when concrete
         "suggestion": {"source": "focus" | "next_steps", "text": ...} | None,
         "advisory": True,
         "version": 1}
    """
    cue = _normalize(resume_step)
    quality, signals = _classify(cue, goal=goal, title=title)
    hint: str | None = None
    suggestion: dict[str, str] | None = None
    if quality != QUALITY_CONCRETE:
        if quality == QUALITY_MISSING:
            hint = HINT_MISSING
        elif SIGNAL_REPEATS_GOAL in signals:
            hint = HINT_REPEATS_GOAL
        else:
            hint = HINT_VAGUE
        suggestion = _suggestion(
            cue, goal=goal, title=title, focus=focus, next_steps=next_steps
        )
    return {
        "quality": quality,
        "signals": signals,
        "hint": hint,
        "suggestion": suggestion,
        "advisory": True,
        "version": RETURN_CUE_CONTRACT_VERSION,
    }


def thread_return_cue(thread: Thread) -> dict[str, Any] | None:
    """Coaching for an unfinished thread; ``None`` once there is nothing to resume."""
    if thread.status in {ThreadStatus.done, ThreadStatus.dismissed} or thread.merged_into:
        return None
    return assess_return_cue(
        thread.resume_step,
        goal=thread.goal,
        title=thread.summary,
        focus=thread.focus,
        next_steps=list(thread.next_steps or []),
    )
