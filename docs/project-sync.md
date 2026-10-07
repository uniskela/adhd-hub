# Project sync (deterministic)

Use project sync when you want a repository to carry the same Hub-owned skills, guidance, and Cursor rule as ADHD Hub itself.

The sync is **deterministic and non-LLM**. Do not hand-edit generated copies in downstream repositories; change the canonical Hub files, then sync them out.

```text
Canonical Hub skills / guidance / Cursor rule
        │
        ▼
  adhd-hub sync-project .
  (or setup . --project-skills)
        │
        ▼
Downstream project files (.agents/skills, AGENTS.md, Cursor rule, skills-lock)
        │
        ▼
Reusable GitHub workflow → reviewable sync PR (never pushes main)
```

## What is managed

| Path | Behaviour |
|------|-----------|
| `AGENTS.md` | Only the block between `<!-- adhd-hub:project-agent:start -->` and `end` |
| `.cursor/rules/adhd-hub.mdc` | Replaced with the canonical Hub Cursor rule |
| `.agents/skills/adhd-hub-projects/**` | Mirrored from Hub `skills/adhd-hub-projects/` |
| `.agents/skills/adhd-hub-session/**` | Mirrored from Hub `skills/adhd-hub-session/` |
| `.agents/skills/env-check/**` | Mirrored from Hub `skills/env-check/` (executable bit preserved) |
| `skills-lock.json` | Hub-owned skill entries only; unrelated skills preserved |
| `.cursor/hooks/adhd-hub-guard.sh` | Opt-in continuity guard wrapper (`--continuity-guard`) |
| `.cursor/hooks.json` | Opt-in: merge Hub guard hooks; preserve unrelated entries |

Everything outside those paths is left alone (except merge-safe Hub hook
entries when continuity guard is enrolled). Malformed / incomplete AGENTS
markers fail safely (no rewrite).

Generated skill copies should **not** normally be patched in downstream repos.
Fix the canonical files here, bump `hub_skill_version` / guidance versions, then
sync.

## Quick commands

From a machine with the ADHD Hub package installed (or this checkout):

```bash
# Apply
adhd-hub sync-project /path/to/my-project --source /path/to/adhd-hub

# Report drift (exit 1 when sync is needed); no writes
adhd-hub sync-project /path/to/my-project --check

# Explain changes; no writes
adhd-hub sync-project /path/to/my-project --dry-run
```

Via setup:

```bash
# AGENTS.md + project-scoped skills (deterministic)
adhd-hub setup . --project-skills --skills-source /path/to/adhd-hub

# Opt-in Cursor continuity-guard hooks (does not replace unrelated hooks)
adhd-hub setup . --continuity-guard
# or: adhd-hub sync-project . --continuity-guard
```

| Flag | Scope |
|------|--------|
| `--project-skills` / `sync-project` | Repo-scoped `.agents/skills` + AGENTS + Cursor rule |
| `--continuity-guard` | Opt-in Hub Cursor hooks merge + guard wrapper |
| `--install-skills` | Global `npx skills add … -g` |

See [continuity-guard.md](continuity-guard.md) for lifecycle behaviour, Cloud vs
local limits, and `adhd-hub guard` CLI.

## Doctor

```bash
adhd-hub doctor --project .
```

Reports AGENTS / Cursor rule / skill versions, project-sync drift, and whether a
wrapper workflow calling this repo’s reusable sync is present.

## GitHub Actions (downstream)

Create a tiny wrapper in the consumer repository. Do **not** copy the sync
implementation.

Until a stable `v1` tag is published, pin an **immutable commit SHA** of the
reusable workflow:

```yaml
name: ADHD Hub Sync

on:
  workflow_dispatch:
  schedule:
    - cron: "17 3 * * 1"

jobs:
  sync:
    # Replace <sha> with an immutable commit from uniskela/adhd-hub that contains
    # .github/workflows/sync-project.yml (after that change lands on main).
    uses: uniskela/adhd-hub/.github/workflows/sync-project.yml@<sha>
    permissions:
      contents: write
      pull-requests: write
    with:
      agents: "cursor,codex"
      # Optional: pin Hub *source* skills independently of the workflow ref
      # hub_ref: "<sha-or-tag>"
```

After Hub publishes a reusable-workflow `v1` tag, migrate the `uses:` line to:

```yaml
    uses: uniskela/adhd-hub/.github/workflows/sync-project.yml@v1
```

Do not copy `@v1` until that tag exists — callers that pin a missing ref fail.

The reusable workflow:

1. Checks out the caller repository and the requested Hub ref
2. Runs `adhd-hub sync-project` (deterministic)
3. Exits cleanly when there is no drift
4. Creates/updates **one** reviewable PR on a dedicated branch when changes exist
5. Never pushes directly to the consumer default branch
6. Uses concurrency + minimal permissions
7. Documents Hub ref/SHA and validation in the PR body

Authentication: caller `GITHUB_TOKEN` is enough for same-repo PRs where GitHub
allows it. Optional GitHub App secrets (`APP_ID` + `APP_PRIVATE_KEY`) can be
passed for stronger automation.

## Uninstall / disable

- Remove the managed AGENTS block: `adhd-hub setup . --uninstall`
- Delete `.cursor/rules/adhd-hub.mdc` and Hub skill trees under `.agents/skills/`
  if you no longer want project-scoped copies
- Remove or disable the downstream wrapper workflow
- Leave unrelated skills and lock entries untouched

## Security

- Sync never embeds credentials into generated files
- Canonical skills require HTTPS (or an authenticated encrypted overlay such as
  Tailscale) for non-loopback bearer MCP; plain HTTP is loopback-only
- Forge mailbox guidance forbids secrets, private hosts/IPs, absolute local
  paths, and transcripts in public issues
- Automated sync must not call Grok/Codex/Cursor/Claude or unpinned `npx skills
  add` to mutate the repo in CI

## Related

- [Project agent setup](project-agent-setup.md)
- [Cursor plugin skill sync](cursor-plugin-skill-sync.md) (Marketplace mirror;
  separate from project-sync)
