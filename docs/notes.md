# Notes & context

**Notes & context** is the reader for one thread’s saved continuity. Open it from **My work**: each thread has a **Notes & context** button. On the list itself, a short **scan line** under the title (when Focus / Resume / Goal / Next is set) keeps the card scannable; the reader still holds the full continuity. The reader sits beside the thread list on a wide screen (**Dock right**). **Expand** uses the work area for reading; **Dock right** returns to the split layout. On a narrow screen the reader opens expanded. Close it with × or Escape.

The reader shows what is already stored. It does not edit Goal, Focus, Next, Blocked, or Resume. Use **Now** (**Pause here**, **Save continuity**) or your agent’s `upsert_progress` for that.

## Project overview

The strip at the top stays visible:

- Project title and slug.
- How many threads in that project are still active (open or blocked, including this one).
- **Updated** — this thread’s last Hub update, shown in the hub timezone (the same clock as other dashboard times).
- A forge link when one exists: the linked issue, or the project repository when there is no issue URL.

## This thread

The continuity card under the strip is always visible. It is built from the thread’s structured fields, in this order, and empty fields are left out:

1. **Goal**
2. **Focus**
3. **Next** — at most three steps
4. **Blocked** — only when something is waiting
5. **Resume**

The card also shows the thread title and status. If none of those fields are set, it says so and points you to **Pause here** or **Save continuity** on Now.

## Thread notes

**Thread notes** is the feed of notes saved on this thread. It opens when the feed is short or clearly written by a person, and stays closed when it is mostly ritual checkpoints. Open or close it without losing the feed.

Human notes are shown as Markdown and kept visually stronger. Ritual milestones — field-change lines and ceremony such as “Thread upserted from …” — are muted one-line summaries, with small chips for the fields that changed (Goal, Focus, Next, and so on). Consecutive checkpoints collapse into one closed line: **N checkpoints · last: …**. Expand that line to see each checkpoint.

The reader shows about the latest five feed items. Anything older stays under **Show older**.

## Other active threads

Other unfinished threads in the same project are listed under the notes, each closed by default. A summary shows the title, status, and **Choose this step**. Opening one shows a shorter continuity card. **Choose this step** closes the reader and returns to Now with that thread selected.

## Full PROGRESS.md

**Full PROGRESS.md** is closed by default. It is the project file the Hub rewrites (active threads, recent milestones, and older history), not a second copy of the continuity card. Open it when you need the whole project file.

## Forge activity

**Forge activity** is an accordion for the linked issue: comments, plus a short timeline. It opens when comments exist. Comments stay display-only. They are not copied into Goal, Focus, Next, Blocked, or Resume.

If the forge cannot be reached, the section says activity is unavailable. The Hub sections above remain the current continuity. With no linked issue, the section says so. With a link and no comments yet, it says there are no comments.

## Copy agent prompt

On Now, **Copy agent prompt** builds a short prompt from the chosen thread:

- Project slug and title, the thread title, and `thread_id`.
- The linked forge issue number and URL, when the thread has one.
- **Resume**, **Next**, **Goal**, **Focus**, and **Blocked**, when those fields are set.
- A **Progress** snippet only when it is a human note. Milestone and boilerplate snippets are left out, so the prompt does not repeat checkpoint walls.

Empty sections are omitted. **Next** is capped at three steps.

## What to write on a routine checkpoint

Update the structured fields (Goal, Focus, Next, Blocked, Resume) and leave freeform note text out. Reserve a freeform note for a real decision, blocker, or ship note — not a line such as “Thread upserted from …”. The reader is built for that habit: the continuity card stays in front, and ritual history stays muted.

The writing convention, including the 30-second minimum, is in [Writing & continuity](writing.md).
