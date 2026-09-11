# Keep each project connected

Use the CLI once in a project folder to add a small, reversible ADHD Hub section to that folder's `AGENTS.md`:

```bash
adhd-hub setup /path/to/my-project
```

`adhd-hub connect` writes the same managed block. The heading is **ADHD Hub continuity**. Agents should skip Hub tools for trivial or read-only questions, tiny edits, and other work that does not need continuity tracking. For substantial work:

- Once per meaningful session: `resolve_project` (current absolute project root), then `session_digest` with that path and a brief task query. Reuse resolved context when you can.
- **One thread = one independently finishable outcome.** Compare new work to the thread Goal before updating; different goal → separate thread.
- Known thread → `upsert_progress(thread_id=...)` with compact structured state (goal / focus / ≤3 next / blocked if any / resume).
- `check_overlap` only before potentially new work; never close unrelated overlap results.
- On genuine completion: `mark_done` only for that known thread.

The block also reminds the agent to send summaries only (no secrets, credentials, env files, or transcripts) and not to publish Hub URLs, tokens, internal hosts, or machine paths.

The command is safe to repeat. Re-running `adhd-hub setup` or `adhd-hub connect` refreshes only the section between these markers and preserves the rest of `AGENTS.md`:

```text
<!-- adhd-hub:project-agent:start -->
<!-- adhd-hub:project-agent:end -->
```

## Install the skills too

Skill installation is opt-in because it changes the global skills directory and may use the network:

```bash
# From the public repository
adhd-hub setup /path/to/my-project --install-skills

# From a local checkout while developing
adhd-hub setup /path/to/my-project \
  --install-skills --skills-source /path/to/adhd-hub/skills
```

This runs `npx skills add <source> -g` without a shell, so paths and arguments are not interpolated as commands. Review the source and keep the MCP bearer token in an environment variable; never add it to `AGENTS.md`.

The generated block is safe to commit to a public repository: it contains no Hub URL, token, internal hostname, or machine path. At runtime, the agent may send the current workspace path and short progress metadata to the operator’s configured Hub. Do not copy that path, internal URLs, or private Hub responses into public commits, issues, or notes.

## Remove the managed section

```bash
adhd-hub setup /path/to/my-project --uninstall
```

Only the ADHD Hub block is removed. The command refuses to edit a symlink or an incomplete managed block.
