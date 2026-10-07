# Recommended third-party companions

Optional tools that pair well with ADHD Progress Hub. **Hub does not require them.** They are independent projects: Hub does not ship, warranty, or auto-update them.

> Formerly titled “coding companions.” The URL `docs/coding-companions.md` is kept stable; the set now includes writing and workflow tools as well as coding helpers.

For the Cursor Marketplace client plugin (skills + rule + BYO MCP), see
[`adhd-hub-cursorskill`](https://github.com/uniskela/adhd-hub-cursorskill). Hub remains the skill source of truth; sync opens a plugin PR — [Cursor plugin skill sync](cursor-plugin-skill-sync.md).

| Category | Role | Tool |
|----------|------|------|
| Continuity | Continuity & progress | ADHD Progress Hub |
| ADHD & interaction | Reply shape | [i-have-adhd](https://github.com/ayghri/i-have-adhd) |
| Agent workflow | Workflow skills | [Superpowers](https://github.com/obra/superpowers) |
| Code quality | Scope control | [Ponytail](https://github.com/DietrichGebert/ponytail) |
| Code intelligence | Codebase map | [Graphify](https://github.com/Graphify-Labs/graphify) |
| Code intelligence | Library docs | [Context7](https://github.com/upstash/context7) |
| Execution & verification | Browser verification | [agent-browser](https://github.com/vercel-labs/agent-browser) |
| Execution & verification | Quieter shell output | [RTK](https://github.com/rtk-ai/rtk) |
| Writing | Natural prose | [Humanizer](https://github.com/blader/humanizer) |

### Advanced companions

| Category | Role | Tool |
|----------|------|------|
| Code intelligence | Semantic code navigation & editing | [Serena](https://github.com/oraios/serena) |

## Choose only what solves a real problem

Installing every companion is **not** recommended. Start with the Hub by itself, then add a tool only when it fixes a specific workflow problem.

Examples:

- need more action-first replies → **i-have-adhd**;
- want structured agent workflows → **Superpowers**;
- want less unnecessary abstraction → **Ponytail**;
- need codebase/library context → **Graphify** or **Context7**;
- need browser verification → **agent-browser**;
- want quieter shell output → **RTK**;
- want natural prose cleanup → **Humanizer**;
- need heavier semantic code navigation → **Serena**.

After `adhd-hub connect` or `adhd-hub doctor`, the CLI prints a short companions checklist. Enable Hub-installable ones in **Hub Settings → Coding agents → Helpful extras**, or pass install flags:

```bash
adhd-hub connect /path/to/project \
  --agents cursor,codex,claude \
  --with-i-have-adhd \
  --with-superpowers \
  --with-ponytail \
  --with-graphify \
  --with-rtk \
  --with-context7 \
  --with-agent-browser \
  --with-serena \
  --with-humanizer
```

Use the same `--agents` list as Hub MCP/skills. With no agents selected, the CLI links this guide instead of guessing per-agent setup.

You can also put flags in `ADHD_HUB_CONNECT_FLAGS` for the install one-liner (including `--with-ponytail` and `--with-humanizer`).

### What Hub automation can do

Hub can opt-in install **i-have-adhd**, **Superpowers**, **Ponytail**, **Graphify**, **RTK**, **Context7**, **agent-browser**, **Serena**, and **Humanizer** through Settings or `--with-*` flags.

Important differences:

- Superpowers and Claude Code Ponytail are best-effort because some hosts require an in-app plugin install.
- Context7 and Serena merge MCP configuration.
- agent-browser installs its CLI and skill.
- Humanizer installs the skills.sh skill only.
- Optional companion failures are warnings; they never fail Hub connect.

Hub passes `--yes` to npx as well as `-y` to the skills CLI, so npm's first-use
package prompt does not interrupt these installs. With `--agents '*'`, some
agents do not support global skills; partial installations are reported as
warnings even if the upstream CLI exits zero. Install those agents' skills at
project scope or select only the agents you use. Manual plugin and hook-trust
steps remain under **Needs attention** until completed in the relevant agent.
Each skills installation has a five-minute timeout; stalled optional installs
warn so Hub connect can continue. Retry the command after resolving the stall.

---

## i-have-adhd

**Category:** ADHD & interaction
**License:** [MIT](https://github.com/ayghri/i-have-adhd/blob/main/LICENSE)
**What it does:** Shapes assistant replies for action-first, numbered steps (opt-in skill; no ADHD diagnosis required). Credits *The Adult ADHD Tool Kit* (Ramsay & Rostain).
**Privacy:** Markdown skill / plugin rules — no product telemetry.

### Install (skills CLI)

```bash
# One or more skills.sh agent ids (Hub maps claude → claude-code):
npx skills add ayghri/i-have-adhd -g -y -a cursor -a codex -a claude-code

# Or every skills.sh agent:
npx skills add ayghri/i-have-adhd -g -y --agent '*'
```

Then invoke `/i-have-adhd` (or `$i-have-adhd` in Codex) in a new session. Full platform matrix (Claude plugin, Gemini, Pi, …): upstream [INSTALL.md](https://github.com/ayghri/i-have-adhd/blob/main/INSTALL.md).

---

## Superpowers

**Category:** Agent workflow
**License:** [MIT](https://github.com/obra/superpowers/blob/main/LICENSE)
**What it does:** Agent workflow skills (brainstorm → plan → TDD → review).
**Privacy:** Local skills/plugin; see upstream for any optional telemetry (visual companion).
**Install (opt-in):** `--with-superpowers` / Settings checkbox. Hub prints harness-specific steps and best-effort CLI install where available (e.g. Gemini extensions). Most harnesses still need an in-app plugin install — see [obra/superpowers](https://github.com/obra/superpowers).

---

## Ponytail

**Category:** Code quality
**License:** [MIT](https://github.com/DietrichGebert/ponytail/blob/main/LICENSE)
**Upstream:** [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)
**What it does:** Encourages agents to prefer the smallest correct implementation, avoid premature abstractions and review changes for unnecessary complexity.
**Privacy / execution:** Local plugin, hooks, or rules. Upstream may inject a ruleset via agent lifecycle hooks. Hub does not send Ponytail traffic anywhere. Review upstream before enabling.
**Independence:** Completely optional and independently maintained. Hub does not vendor Ponytail source and never makes it mandatory.

### Install vs activation

- **Install** = place the plugin/hooks/extension for your agent (what `--with-ponytail` does).
- **Activation / mode** = upstream-controlled (`lite` / `full` / `ultra` / `off`). Hub does **not** force a strictness level. Upstream’s default after install is typically `full` unless you set `PONYTAIL_DEFAULT_MODE` or `~/.config/ponytail/config.json`. Switch with `/ponytail lite|full|ultra|off` (or plain messages in Cursor hooks).

### Hub opt-in install

`--with-ponytail` / Settings checkbox. Hub follows **upstream** recipes per selected agent (not skills.sh as the primary path — Ponytail’s README documents plugins/hooks/extensions):

| Agent | Hub behaviour |
|-------|----------------|
| Cursor | Clone to `~/.local/share/adhd-hub/companions/ponytail` (or `$XDG_DATA_HOME/...`) and run `node scripts/cursor-hooks.js install` (merges hooks; needs `git` + `node`) |
| Codex | `codex plugin marketplace add DietrichGebert/ponytail` then `codex plugin add ponytail@ponytail` when `codex` is on `PATH`; then trust hooks in `/hooks` |
| Claude Code | Manual hint only (`/plugin marketplace add` + `/plugin install`) — Hub cannot drive the interactive `/plugin` UI |
| Gemini CLI | `gemini extensions install https://github.com/DietrichGebert/ponytail` when `gemini` is on `PATH` |

### Manual upstream install

See the upstream [README Install section](https://github.com/DietrichGebert/ponytail#install) for Claude, Codex, Cursor, Gemini, and other hosts. Failures warn and never fail Hub connect.

---

## Graphify

**Category:** Code intelligence
**License:** [Apache-2.0](https://github.com/Graphify-Labs/graphify/blob/v8/LICENSE) (older portions also under MIT; see upstream `NOTICE`)
**What it does:** Builds a local knowledge graph of your repo so agents can `query` / `path` / `explain` instead of blind grepping.
**Privacy:** Code AST extraction is local. No product telemetry. Docs/media semantic passes use your assistant or a configured API key. Commercial [graphify.com](https://graphify.com) is separate from the open-source CLI.

### Install

```bash
uv tool install graphifyy   # package name is graphifyy; CLI is still `graphify`
```

Register for the agents you actually use (examples):

| Agent | Register |
|-------|----------|
| Claude Code | `graphify install` |
| Cursor | `graphify cursor install` |
| Codex | `graphify install --platform codex` |
| Gemini CLI | `graphify install --platform gemini` |
| Cross-framework skills | `graphify agents install` |
| Many / unknown | Prefer `graphify agents install` or upstream platform table |

Then in a project: `/graphify .` (PowerShell: `graphify .`). Upstream: [Graphify README](https://github.com/Graphify-Labs/graphify).

---

## Context7

**Category:** Code intelligence
**License:** [MIT](https://github.com/upstash/context7/blob/master/LICENSE)
**What it does:** Up-to-date library docs via MCP/CLI.
**Privacy:** Queries go to Context7’s service; may need an API key — see upstream.
**Install (opt-in):** `--with-context7` / Settings checkbox. Hub merges an MCP stdio entry (`npx -y @upstash/context7-mcp`) into selected agent configs. Optional API key improves rate limits — see [upstash/context7](https://github.com/upstash/context7).

---

## agent-browser

**Category:** Execution & verification
**License:** [Apache-2.0](https://github.com/vercel-labs/agent-browser/blob/main/LICENSE) (confirmed from upstream LICENSE)
**What it does:** Browser automation for agents to verify UI.
**Privacy:** Drives a local browser; review upstream before enabling.
**Install (opt-in):** `--with-agent-browser` / Settings checkbox. Hub runs
`npm install -g --allow-scripts=agent-browser agent-browser`,
`agent-browser install`, and the skills installer for selected agents. The npm
option permits this package's postinstall script without changing your global
npm configuration. Hub then opens a local `about:blank` page in a temporary
session with an empty browser configuration and no `AGENT_BROWSER_*` overrides,
and attempts to close that session. A download alone does not count as a verified launch.
Launch and cleanup failures warn; cleanup warnings include the session's close
command for recovery. Hub does not install system packages, change the browser
sandbox, or attach this check to an existing browser.
See [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser).

---

## RTK

**Category:** Execution & verification
**License:** [Apache-2.0](https://github.com/rtk-ai/rtk/blob/develop/LICENSE)
**What it does:** Compresses shell/tool output before your agent reads it; optional hooks rewrite bash commands.
**Privacy:** Telemetry is **opt-in** (see upstream [TELEMETRY.md](https://github.com/rtk-ai/rtk/blob/develop/docs/TELEMETRY.md) / README). Leave it disabled unless you consent at RTK’s prompt. Hooks change how agents run shell commands — review before enabling.

### Install binary

`adhd-hub connect . --with-rtk --agents cursor,codex` (or the Settings checkbox
with agents selected) tries **Homebrew** when `brew` is on `PATH`, otherwise runs
the upstream installer below (needs `curl`). The binary install still runs when
`--with-rtk` is set without `--agents`; `rtk init` needs agents. The script
installs into `~/.local/bin`. RTK hooks call bare `rtk`, so that directory must be
on your `PATH`; Hub warns with the exact `export PATH=…` line when it is not.

```bash
# macOS (Homebrew) — preferred when brew is available
brew install rtk

# Linux / macOS script (review before piping) — used by Hub when brew is absent
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

Windows: download a release zip from [rtk releases](https://github.com/rtk-ai/rtk/releases), put `rtk.exe` on `PATH` (Hub does not auto-download on Windows).

### Init for your agents

| Agent | Init |
|-------|------|
| Claude Code | `rtk init -g --auto-patch` (Hub passes `--auto-patch` so the hook is written to `settings.json` without a prompt; drop it to be asked first) |
| Cursor | `rtk init -g --agent cursor` |
| Codex | `rtk init -g --codex` |
| Gemini CLI | `rtk init -g --gemini` |
| Other supported agents | `rtk init -g --agent <name>` (see upstream README) |

Restart the coding agent after init. Upstream: [RTK README](https://github.com/rtk-ai/rtk).

---

## Humanizer

**Category:** Writing
**License:** [MIT](https://github.com/blader/humanizer/blob/main/LICENSE)
**Upstream:** [blader/humanizer](https://github.com/blader/humanizer)
**What it does:** Rewrites AI-generated prose to sound more natural while preserving the original meaning. Best suited to documentation and user-facing writing. Built on Wikipedia’s [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
**Privacy:** Local skill; runs in your agent when you invoke it. No Hub post-processing layer.
**Independence:** Completely optional and independently maintained. Hub does not vendor Humanizer source.

### Behaviour (important)

Hub **only installs** the skill. It does **not**:

- auto-rewrite every agent response
- run Humanizer against source code, YAML/JSON/config, generated structured data, shell commands, or internal agent state

Invoke on demand (`/humanizer`, or ask the agent to humanize a prose draft). When pointed at a file, upstream edits prose and leaves code/data/frontmatter alone — still use it intentionally on writing, not as a blanket pass.

### Install (skills CLI / Hub opt-in)

```bash
# Hub:
adhd-hub connect . --agents cursor,codex,claude --with-humanizer

# Manual (skills.sh):
npx skills add blader/humanizer -g -y -a cursor -a codex -a claude-code
# or: npx skills add blader/humanizer -g -y --agent '*'
```

Claude Code can also use the upstream plugin marketplace (`/plugin marketplace add blader/humanizer` then `/plugin install humanizer@humanizer`) — see [blader/humanizer](https://github.com/blader/humanizer).

---

## Serena (advanced)

**Category:** Code intelligence
**License:** [MIT](https://github.com/oraios/serena/blob/main/LICENSE)
**What it does:** Semantic code navigation / editing via MCP. Heavier setup than the companions above—use when you want LSP-style repo intelligence.
**Privacy:** Typically local LSP/MCP; confirm upstream if using remote options.
**Install (opt-in):** `--with-serena` / Settings checkbox. Hub runs `uv tool install -p 3.13 serena-agent`, best-effort `serena init`, and merges MCP launch config for selected agents. See [oraios/serena](https://github.com/oraios/serena).

---

## Ethics and expectations

- These are **recommendations**, not Hub dependencies.
- Prefer linking and opt-in CLI flags over silent installs.
- Hub install paths: `--with-i-have-adhd` / `--with-superpowers` / `--with-ponytail` / `--with-graphify` / `--with-rtk` / `--with-context7` / `--with-agent-browser` / `--with-serena` / `--with-humanizer` (and matching Settings checkboxes). All are opt-in; failures warn and never fail Hub connect.
- Respect each project’s license and attribution when redistributing (Hub does not vendor their code).
- For RTK, prefer the README/TELEMETRY docs over any conflicting one-line disclaimer about defaults.
