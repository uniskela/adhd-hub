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
- If Hub MCP is unavailable, warn on the first substantial Hub-worthy turn after detecting the outage. Repeat only when Hub status changes, another persistence attempt fails, or silence could imply that continuity was saved.
- Drift: `adhd-hub doctor --project .` reports outdated Hub-managed AGENTS.md / Cursor rule / Hub skills; repair with `adhd-hub setup . --refresh` (and `--install-skills` when opting into global Hub skill updates). Setup `--check` is dry-run only.

The block also reminds the agent to send summaries only and to keep secrets, credentials, env files, transcripts, private Hub URLs, internal hosts/IPs, and absolute machine paths out of public artifacts.

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

`setup --install-skills` installs both Hub skills for every skills.sh agent (`npx skills add <source> -g -y --skill '*' --agent '*'`). It runs the command as an argument list without a shell, so paths and arguments are not interpolated as commands. If you want to target selected agents instead, use `adhd-hub connect ... --skills --agents cursor,codex,claude`.

Review the skill source and keep MCP credentials outside project guidance. The generated block itself contains no operator-specific Hub URL, token, internal hostname, or machine path. At runtime, the agent may send the current workspace path and short progress metadata to the operator's configured Hub; do not copy that path, internal URLs, or private Hub responses into public commits, issues, or notes.

## Check or refresh an existing project

```bash
# Report drift without writing files
adhd-hub setup /path/to/my-project --check

# Refresh only Hub-managed AGENTS.md guidance
adhd-hub setup /path/to/my-project --refresh
```

After upgrading Hub guidance, `adhd-hub doctor --project /path/to/my-project` is the broader check because it also reports Cursor-rule and installed Hub-skill versions.

## Remove the managed section

```bash
adhd-hub setup /path/to/my-project --uninstall
```

Only the ADHD Hub block is removed. The command refuses to edit a symlink or an incomplete managed block.
