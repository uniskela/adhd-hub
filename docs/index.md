# ADHD Progress Hub

Keep enough context to resume unfinished work without reconstructing your last session.

![My work with Notes & context](images/my-work-notes-hero.png)

[Install](installation.md) · [Connect an agent](connect.md) · [View on GitHub](https://github.com/uniskela/adhd-hub) · [Screenshots](../README.md#screenshots)

**Self-hosted · MCP (Streamable HTTP + local stdio) + REST · Cursor / Codex / Claude Code · GitHub/Gitea optional**

## The loop

**Work → Save continuity → Leave → Come back → Resume**

The Hub keeps the parts that matter when you return: what you were trying to do, what matters now, what is blocking you, and the next concrete place to continue.

## Start here

1. [Install the Hub](installation.md).
2. [Connect your coding agent](connect.md).
3. [Set up project continuity](project-agent-setup.md) for substantial work.
4. Open the [dashboard](dashboard.md) when you want to choose, pause, or resume work visually.

For a practical day-to-day routine, see [Personal setup](setup.md). For concise Goal / Focus / Next / Blocked / Resume notes, see [Writing & continuity](writing.md). To read that continuity on My work, see [Notes & context](notes.md).

## What belongs here?

Repository work can be linked to GitHub/Gitea while the Hub keeps local continuity around it. Non-repository work — homelab changes, migrations, research, admin, or a PC setup — can stay entirely local to the Hub.

The project is designed to be useful without streaks, competitive pressure, or a requirement to keep every task in one system.

## Deploy and configure

- [Homelab deployment](deploy-homelab.md)
- [Remote MCP access (tunnels for cloud agents)](https://uniskela.com/docs/adhd-hub/remote-mcp-access/)
- [Authentication](authentication.md)
- [Environment variables](environment-variables.md)
- [MCP transports: HTTP and local stdio](connect.md#local-stdio-transport-optional)
- [Forge permissions](forge-permissions.md)
- [Forge issue inbox](forge-issue-inbox.md)
- [OpenClaw](openclaw.md)

## Project

The [public roadmap](plans/improvement-roadmap.md) is the single documentation page for current sequencing. GitHub issue [#15](https://github.com/uniskela/adhd-hub/issues/15) is the canonical planning tracker. See the [brand guide](brand-guide.md) for the visual and interaction principles used by the project.

Historical implementation plans remain in the repository for maintainers, but are intentionally kept out of the main documentation navigation.
