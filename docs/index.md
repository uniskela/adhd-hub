---
layout: default
title: Documentation
---

<p class="eyebrow">Documentation</p>

# A calmer place to pick work back up

<p class="lede">ADHD Progress Hub keeps unfinished work findable. Start with one small action, save the context you will need later, then step away without losing the thread.</p>

<div class="actions">
  <a class="card" href="{{ '/writing/' | relative_url }}">
    <strong>Writing and planning</strong>
    Use one visible Now action, short next steps, explicit blockers, and a return cue.
  </a>
  <a class="card" href="https://github.com/uniskela/adhd-hub#quick-start">
    <strong>Run the Hub</strong>
    Install it locally or with Docker, then connect your MCP client.
  </a>
  <a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/personal-wireup.md">
    <strong>Personal wire-up</strong>
    Set up a repeatable start, pause, and review loop across your tools.
  </a>
</div>

## Start here

1. Give the project a durable purpose.
2. Keep one concrete **Now** action at the top of active progress.
3. When stopping, save a **Return cue**: “When I return, I will …”.

The [writing and planning guide]({{ '/writing/' | relative_url }}) includes ready-to-copy templates and the research behind the pattern.

## Documentation library

The full source documents are maintained as Markdown in the repository, so each link always shows the current reviewed version.

<ul class="doc-list">
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/authentication.md"><strong>Authentication</strong>Passwords, tokens, cookies, and recovery.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/dashboard.md"><strong>Dashboard</strong>Focus, quick capture, and pausing work.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/deploy-homelab.md"><strong>Homelab deployment</strong>Run the Hub safely in your lab.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/forge-permissions.md"><strong>Forge permissions</strong>Least-privilege GitHub and Gitea setup.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/indexer-schedule.md"><strong>Indexer schedule</strong>Use summaries as a backstop, not raw transcripts.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/rewards-roadmap.md"><strong>Rewards roadmap</strong>Optional, low-pressure encouragement.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/brand-guide.md"><strong>Brand guide</strong>Voice, visual language, and reward principles.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/blob/main/docs/review-improvements.md"><strong>Review improvements</strong>Follow-up ideas for the project.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/tree/main/docs/plans"><strong>Executed plans</strong>Foundation and project-CRUD delivery records.</a></li>
  <li><a class="card" href="https://github.com/uniskela/adhd-hub/tree/main/docs"><strong>All source docs</strong>Browse the current reviewed Markdown library.</a></li>
</ul>

## Publishing this site

In GitHub, open **Settings → Pages** and select **GitHub Actions** as the build source. The included workflow deploys only after `uniskela` merges documentation changes to protected `main`; it never executes for a pull request or from a manual run.
