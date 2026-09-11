# A calmer place to pick work back up

ADHD Progress Hub keeps unfinished work findable. Start with one small action, save the context you will need later, then step away without losing the thread.

## Start here

1. Give the project a durable purpose.
2. Keep one concrete **Now** action at the top of active progress.
3. When stopping, save a **Return cue**: “When I return, I will …”.

- [Writing and planning](writing.md) — one visible Now action, short next steps, blockers, and a return cue
- [Personal wire-up](setup.md) — a repeatable start, pause, and review loop
- [Connect (one-liner)](connect.md) — MCP, AGENTS.md, skills, and optional OpenClaw from a running Hub
- [Project agent setup](project-agent-setup.md) — reversible AGENTS.md continuity guidance
- [Recommended coding companions](coding-companions.md) — optional i-have-adhd, Graphify, RTK

## Guides

- [Authentication](authentication.md)
- [Dashboard](dashboard.md)
- [OpenClaw connection and alerts](openclaw.md)
- [Homelab deployment](deploy-homelab.md)
- [Forge permissions](forge-permissions.md)
- [Forge issue inbox](forge-issue-inbox.md)
- [Indexer schedule](indexer-schedule.md)
- [Rewards roadmap](rewards-roadmap.md)
- [Brand guide](brand-guide.md)
- [Review improvements](review-improvements.md)

## Plans

- [Improvement roadmap](plans/improvement-roadmap.md)
- [Next waves](plans/next-waves.md)
- [ADHD Hub foundation](plans/adhd-hub-foundation.md)
- [Projects CRUD revamp](plans/projects-crud-ui-revamp.md)

## Publishing this site

In GitHub, open **Settings → Pages** and select **GitHub Actions** as the build source. The included workflow builds with [Zensical](https://zensical.org/) and deploys only after `uniskela` merges documentation changes to protected `main`; it never executes for a pull request or from a manual run.

Preview locally:

```bash
uv sync --extra dev
uv run zensical serve
```
