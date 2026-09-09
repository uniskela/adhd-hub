---
layout: default
title: Documentation
permalink: /
nav_order: 0
---

<p class="eyebrow">Documentation</p>

# A calmer place to pick work back up

<p class="lede">ADHD Progress Hub keeps unfinished work findable. Start with one small action, save the context you will need later, then step away without losing the thread.</p>

<div class="actions">
  <a class="card" href="{{ '/writing/' | relative_url }}">
    <strong>Writing and planning</strong>
    Use one visible Now action, short next steps, explicit blockers, and a return cue.
  </a>
  <a class="card" href="{{ '/connect/' | relative_url }}">
    <strong>Connect (one-liner)</strong>
    Wire MCP, AGENTS.md, skills, and optional OpenClaw from a running Hub.
  </a>
  <a class="card" href="{{ '/setup/' | relative_url }}">
    <strong>Personal wire-up</strong>
    Set up a repeatable start, pause, and review loop across your tools.
  </a>
  <a class="card" href="{{ '/project-agent-setup/' | relative_url }}">
    <strong>Project agent setup</strong>
    Add a reversible AGENTS.md prompt so each project keeps its Hub progress current.
  </a>
  <a class="card" href="{{ '/dashboard/' | relative_url }}">
    <strong>Use the dashboard</strong>
    Keep one chosen task and a clear next step in view.
  </a>
</div>

## Start here

1. Give the project a durable purpose.
2. Keep one concrete **Now** action at the top of active progress.
3. When stopping, save a **Return cue**: “When I return, I will …”.

The [writing and planning guide]({{ '/writing/' | relative_url }}) includes ready-to-copy templates and the research behind the pattern.

## Documentation library

Every guide below is rendered from the reviewed Markdown source in this repository, so the wiki and source stay in sync.

<ul class="doc-list">
  <li><a class="card" href="{{ '/authentication/' | relative_url }}"><strong>Authentication</strong>Passwords, tokens, cookies, and recovery.</a></li>
  <li><a class="card" href="{{ '/openclaw/' | relative_url }}"><strong>OpenClaw connection and alerts</strong>Install the skills and set up private, gentle stale-work reminders.</a></li>
  <li><a class="card" href="{{ '/connect/' | relative_url }}"><strong>Connect</strong>One-liner and <code>adhd-hub connect</code> / <code>doctor</code>.</a></li>
  <li><a class="card" href="{{ '/project-agent-setup/' | relative_url }}"><strong>Project agent setup</strong>Install continuity guidance in a project's AGENTS.md.</a></li>
  <li><a class="card" href="{{ '/plans/improvement-roadmap/' | relative_url }}"><strong>Improvement roadmap</strong>Sequenced waves after v0.3.4.</a></li>
  <li><a class="card" href="{{ '/deploy-homelab/' | relative_url }}"><strong>Homelab deployment</strong>Run the Hub safely in your lab.</a></li>
  <li><a class="card" href="{{ '/forge-permissions/' | relative_url }}"><strong>Forge permissions</strong>Least-privilege GitHub and Gitea setup.</a></li>
  <li><a class="card" href="{{ '/indexer-schedule/' | relative_url }}"><strong>Indexer schedule</strong>Use summaries as a backstop, not raw transcripts.</a></li>
  <li><a class="card" href="{{ '/rewards-roadmap/' | relative_url }}"><strong>Rewards roadmap</strong>Optional, low-pressure encouragement.</a></li>
  <li><a class="card" href="{{ '/brand-guide/' | relative_url }}"><strong>Brand guide</strong>Voice, visual language, and reward principles.</a></li>
  <li><a class="card" href="{{ '/review-improvements/' | relative_url }}"><strong>Review improvements</strong>Follow-up ideas for the project.</a></li>
  <li><a class="card" href="{{ '/plans/adhd-hub-foundation/' | relative_url }}"><strong>Executed plans</strong>Foundation and project-CRUD delivery records.</a></li>
</ul>

## Publishing this site

In GitHub, open **Settings → Pages** and select **GitHub Actions** as the build source. The included workflow deploys only after `uniskela` merges documentation changes to protected `main`; it never executes for a pull request or from a manual run.
