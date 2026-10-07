# Keep each project connected

Use the CLI once in a project folder to add a small, reversible ADHD Hub section to that project's `AGENTS.md`:

```bash
adhd-hub setup /path/to/my-project
```

`adhd-hub connect` writes the same managed block. Agents should skip Hub continuity work for trivial read-only questions, tiny edits, and other work that does not need a return point.

## What agents should do for substantial work

### Start the session

1. Run `resolve_project` with the current absolute project root and `create_if_missing=false`.
2. Run `session_digest` with that path and a short description of the task.
3. Reuse the resolved project context for the rest of the session.

Only register or create a project after the workspace is intentionally authorised as a Hub project.

### Choose the right thread

**One thread = one independently finishable outcome.**

- If you already know the thread, reuse its `thread_id`.
- If the work may be new or duplicated, run `check_overlap`.
- Reuse an overlap candidate only when its **Goal** matches the work you are actually doing.
- A different Goal belongs in a separate thread.

### Checkpoint progress

For a known thread, use `upsert_progress(thread_id=...)` with compact structured state:

- **goal**
- **focus**
- up to three **next_steps**
- **blocked_reason** only when blocked
- **resume_step**

Do not add ritual freeform content for routine checkpoints.

### Leave or finish cleanly

When stopping mid-task:

1. checkpoint with `upsert_progress`;
2. call `pause_thread(thread_id, next_step=...)` with one concrete pickup action.

When the outcome is genuinely complete, call `mark_done` for that known thread only. Do not close unrelated overlap results.

## If Hub MCP is unavailable

Do not invent Hub state or claim a write succeeded.

1. Detect the problem from the MCP tool surface: missing tools, errors, unauthorised responses, or auth failures.
2. On the first substantial Hub-worthy turn after the outage is detected, make the reply's first line state that Hub MCP is unavailable and include a short recovery hint: check this Hub's `/mcp` endpoint and `ADHD_HUB_AUTH_TOKEN`, restart the agent, and cancel a stalled Auth flow until Hub OAuth is enabled. Repeat the warning only if Hub status changes, another persistence attempt fails, or the reply could otherwise imply continuity was saved.
3. Continue with repository tools when possible.
4. If forge issue-write access is authorised for the Hub inbox, create or update a `[ADHD] ...` issue with a short **Goal / Focus / Next / Resume** handoff.
5. If neither Hub nor forge persistence is available, continue the work but make the missing continuity explicit.

Optional environment hints such as `CURSOR_AGENT` or remote-sandbox markers can support detection, but they are not a substitute for checking the actual tool surface. Use `env-check` for CLOUD_AGENT vs LOCAL_WORKSPACE. Cloud agents must not assume local helper CLIs such as `graphify` exist.

For the forge fallback format and allowlist rules, see [Forge issue inbox](forge-issue-inbox.md).

## Keep generated guidance current

`adhd-hub doctor --project .` reports stale Hub-managed AGENTS guidance, Cursor rules, Hub skills, and project-sync drift.

Use the matching repair:

| Drift | Repair |
| --- | --- |
| Managed AGENTS block | `adhd-hub setup . --refresh` |
| Repo-scoped Hub skills | `adhd-hub sync-project .` or `setup . --project-skills` |
| Global Hub skills | `adhd-hub setup . --install-skills` |
| Stronger Cursor enforcement wanted | `adhd-hub setup . --continuity-guard` |

`setup --check` is dry-run only. See [Project sync](project-sync.md) and [Continuity Guard](continuity-guard.md).

The block also reminds the agent to send summaries only and to keep secrets, credentials, env files, transcripts, private Hub URLs, internal hosts/IPs, and absolute machine paths out of public artifacts. Prefer short repository-relative summaries in forge issues.

The command is safe to repeat. Re-running `adhd-hub setup` or `adhd-hub connect` refreshes only the section between these markers and preserves the rest of `AGENTS.md`:

```text
<!-- adhd-hub:project-agent:start -->
<!-- adhd-hub:project-agent:end -->
```

The managed block includes an internal guidance version marker. `doctor` uses that marker plus content checks to detect stale or locally modified Hub-managed guidance; do not hand-edit inside the managed markers.

## Install the skills too

### Project-scoped (recommended for repos)

Deterministic copy into `.agents/skills` (no LLM, preserves unrelated skills):

```bash
adhd-hub sync-project /path/to/my-project --source /path/to/adhd-hub
# or
adhd-hub setup /path/to/my-project --project-skills --skills-source /path/to/adhd-hub
```

Details: [project sync](project-sync.md).

### Global (opt-in)

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
| **You (operator)** | After a Hub upgrade (or when an agent mentions stale guidance): run `adhd-hub doctor --project .`. Repair with `setup . --refresh` (AGENTS block), `sync-project .` / `setup . --project-skills` (repo-scoped skills), and, when you want global skill updates, `setup . --install-skills`. Cursor Marketplace users also pull skill/rule updates via the [plugin sync](cursor-plugin-skill-sync.md) PR → publish path. |
| **Coding agent** | On substantial session start, read `session_digest.guidance`. If status is `local_verification_required` or `verification_recommended`, mention once and recommend doctor / refresh / sync-project / install-skills. Do not invent “up to date.” After a local check, optionally call MCP `report_guidance_health` with the versions verified. Never hand-edit inside `<!-- adhd-hub:project-agent:* -->` markers. |

Dry-run only (no writes, no Hub record): `adhd-hub setup . --check`.

## Remove the managed section

```bash
adhd-hub setup /path/to/my-project --uninstall
```

Only the ADHD Hub block is removed. The command refuses to edit a symlink or an incomplete managed block.
