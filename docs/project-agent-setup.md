# Keep each project connected

Use the CLI once in a project folder to add a small, reversible ADHD Hub section to that folder's `AGENTS.md`:

```bash
adhd-hub setup /path/to/my-project
```

`adhd-hub connect` writes the same managed block. The heading is **ADHD Hub continuity**. Agents should skip Hub tools for trivial or read-only questions, tiny edits, and other work that does not need continuity tracking. For substantial work:

- Once per meaningful session: `resolve_project` (current absolute project root), then `session_digest` with that path and a brief task query. Reuse resolved context when you can.
- **One thread = one independently finishable outcome.** Compare new work to the thread Goal before updating; different goal → separate thread.
- Known thread → `upsert_progress(thread_id=...)` with compact structured state (goal / focus / ≤3 next / blocked if any / resume).
- If resuming a known thread, reuse its `thread_id`. Otherwise `check_overlap` only before potentially new/duplicate work; reuse a candidate only when its Goal matches.
- When leaving mid-task: checkpoint with `upsert_progress`, then `pause_thread(thread_id, next_step=...)` with one concrete resume action.
- On genuine completion: `mark_done` only for that known thread; never close unrelated overlap results.
- If Hub MCP is unavailable, warn on the first substantial Hub-worthy turn after detecting the outage. Repeat only when Hub status changes, another persistence attempt fails, or silence could imply that continuity was saved. Never invent Hub continuity/progress/thread state or claim a Hub write succeeded.
- Detect unavailability by checking MCP tools (missing / errored / unauthorized / auth failure) — do not invent “I'm in cloud.” Optional hints: `CURSOR_AGENT`, Cursor Cloud / remote-sandbox markers. Use `env-check` for CLOUD_AGENT vs LOCAL_WORKSPACE. CLOUD_AGENT must not assume local skill CLIs like `graphify` exist (one-line notice if missing; continue via repo tools / committed `graphify-out/`). When MCP is unreachable and forge issue-write access exists (identity on Hub Inbox authors), open/update a GitHub/Gitea issue titled `[ADHD] …` with a short Goal/Focus/Next/Resume cue (optional labels `adhd-hub`, `project:<slug>`, `source:cursor` when allowed). Recommended: append `Made with [ADHD Progress Hub](https://github.com/uniskela/adhd-hub)` under a non-imported heading (e.g. `## Attribution`). See [forge issue inbox](forge-issue-inbox.md).
- Drift: `adhd-hub doctor --project .` reports outdated Hub-managed AGENTS.md / Cursor rule / Hub skills; repair with `adhd-hub setup . --refresh` (and `--install-skills` when opting into global Hub skill updates). Setup `--check` is dry-run only.

The block also reminds the agent to send summaries only and to keep secrets, credentials, env files, transcripts, private Hub URLs, internal hosts/IPs, and absolute machine paths out of public artifacts. Prefer short repository-relative summaries in forge issues.

The command is safe to repeat. Re-running `adhd-hub setup` or `adhd-hub connect` refreshes only the section between these markers and preserves the rest of `AGENTS.md`:

```text
<!-- adhd-hub:project-agent:start -->
<!-- adhd-hub:project-agent:end -->
```

The managed block includes an internal guidance version marker. `doctor` uses that marker plus content checks to detect stale or locally modified Hub-managed guidance; do not hand-edit inside the managed markers.

## Install the skills too

Skill installation is opt-in because it changes the global skills directory and may use the network:

```bash
# From the public repository
adhd-hub setup /path/to/my-project --install-skills

# From a local checkout while developing
adhd-hub setup /path/to/my-project \
  --install-skills --skills-source /path/to/adhd-hub/skills
```

`setup --install-skills` installs Hub skills (`adhd-hub-session`, `adhd-hub-projects`, `env-check`) for every skills.sh agent (`npx skills add <source> -g -y --skill '*' --agent '*'`). It runs the command as an argument list without a shell, so paths and arguments are not interpolated as commands. If you want to target selected agents instead, use `adhd-hub connect ... --skills --agents cursor,codex,claude`.

Review the skill source and keep MCP credentials outside project guidance. The generated block itself contains no operator-specific Hub URL, token, internal hostname, or machine path. At runtime, the agent may send the current workspace path and short progress metadata to the operator's configured Hub; do not copy that path, internal URLs, or private Hub responses into public commits, issues, or notes.

## Check or refresh an existing project

```bash
# Report drift without writing files
adhd-hub setup /path/to/my-project --check

# Refresh only Hub-managed AGENTS.md guidance
adhd-hub setup /path/to/my-project --refresh
```

After upgrading Hub guidance, `adhd-hub doctor --project /path/to/my-project` is the broader check because it also reports Cursor-rule and installed Hub-skill versions. When Hub credentials work, doctor **records** those local versions on the Hub so the next `session_digest.guidance` status is honest (the Hub never inspects your checkout itself).

## Keeping guidance and skills current

| Who | What to do |
|-----|------------|
| **You (operator)** | After a Hub upgrade (or when an agent mentions stale guidance): run `adhd-hub doctor --project .`. Repair with `setup . --refresh` (AGENTS block) and, when you want global skill updates, `setup . --install-skills`. Cursor Marketplace users also pull skill/rule updates via the [plugin sync](cursor-plugin-skill-sync.md) PR → publish path. |
| **Coding agent** | On substantial session start, read `session_digest.guidance`. If status is `local_verification_required` or `verification_recommended`, mention once and recommend doctor / refresh / install-skills. Do not invent “up to date.” After a local check, optionally call MCP `report_guidance_health` with the versions verified. Never hand-edit inside `<!-- adhd-hub:project-agent:* -->` markers. |

Dry-run only (no writes, no Hub record): `adhd-hub setup . --check`.

## Remove the managed section

```bash
adhd-hub setup /path/to/my-project --uninstall
```

Only the ADHD Hub block is removed. The command refuses to edit a symlink or an incomplete managed block.
