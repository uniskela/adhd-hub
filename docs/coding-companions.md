# Recommended coding companions

Optional tools that pair well with ADHD Progress Hub. **Hub does not require them.** They are independent projects: Hub does not ship, warranty, or auto-update them.

| Role | Tool |
|------|------|
| Continuity & progress | ADHD Progress Hub |
| Reply shape | [i-have-adhd](https://github.com/ayghri/i-have-adhd) |
| Agent workflow | [Superpowers](https://github.com/obra/superpowers) |
| Codebase map | [Graphify](https://github.com/Graphify-Labs/graphify) |
| Current library docs | [Context7](https://github.com/upstash/context7) |
| Browser verification | [agent-browser](https://github.com/vercel-labs/agent-browser) |
| Quieter shell output | [RTK](https://github.com/rtk-ai/rtk) |

### Advanced companions

| Role | Tool |
|------|------|
| Semantic code navigation & editing | [Serena](https://github.com/oraios/serena) |

These tools solve different parts of the coding-agent workflow. Installing all of them is **not** recommended by default—choose companions that address problems in your existing workflow.

After `adhd-hub connect` or `adhd-hub doctor`, the CLI prints a short companions checklist. Enable Hub-installable ones in **Hub Settings → Agents & install → Coding companions**, or pass install flags:

```bash
adhd-hub connect /path/to/project \
  --agents cursor,codex,claude \
  --with-i-have-adhd \
  --with-graphify \
  --with-rtk \
  --with-superpowers \
  --with-context7 \
  --with-agent-browser \
  --with-serena
```

Use the same `--agents` list as Hub MCP/skills. With no agents selected, the CLI links this guide instead of guessing per-agent setup.

You can also put flags in `ADHD_HUB_CONNECT_FLAGS` for the install one-liner.

Hub can opt-in install **i-have-adhd**, **Graphify**, **RTK**, **Superpowers**, **Context7**, **agent-browser**, and **Serena** (Settings checkboxes + `--with-*`). Superpowers is best-effort (many harnesses need an in-app plugin install); Context7/Serena merge MCP configs; agent-browser installs the CLI + skill. Optional companion failures warn and never fail Hub connect.

---

## i-have-adhd

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

**License:** [MIT](https://github.com/obra/superpowers/blob/main/LICENSE)  
**What it does:** Agent workflow skills (brainstorm → plan → TDD → review).  
**Privacy:** Local skills/plugin; see upstream for any optional telemetry (visual companion).  
**Install (opt-in):** `--with-superpowers` / Settings checkbox. Hub prints harness-specific steps and best-effort CLI install where available (e.g. Gemini extensions). Most harnesses still need an in-app plugin install — see [obra/superpowers](https://github.com/obra/superpowers).

---

## Graphify

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

**License:** [MIT](https://github.com/upstash/context7/blob/master/LICENSE)  
**What it does:** Up-to-date library docs via MCP/CLI.  
**Privacy:** Queries go to Context7’s service; may need an API key — see upstream.  
**Install (opt-in):** `--with-context7` / Settings checkbox. Hub merges an MCP stdio entry (`npx -y @upstash/context7-mcp`) into selected agent configs. Optional API key improves rate limits — see [upstash/context7](https://github.com/upstash/context7).

---

## agent-browser

**License:** [Apache-2.0](https://github.com/vercel-labs/agent-browser/blob/main/LICENSE) (confirmed from upstream LICENSE)  
**What it does:** Browser automation for agents to verify UI.  
**Privacy:** Drives a local browser; review upstream before enabling.  
**Install (opt-in):** `--with-agent-browser` / Settings checkbox. Hub runs `npm i -g agent-browser`, `agent-browser install`, and `npx skills add vercel-labs/agent-browser` for selected agents. See [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser).

---

## RTK

**License:** [Apache-2.0](https://github.com/rtk-ai/rtk/blob/develop/LICENSE)  
**What it does:** Compresses shell/tool output before your agent reads it; optional hooks rewrite bash commands.  
**Privacy:** Telemetry is **opt-in** (see upstream [TELEMETRY.md](https://github.com/rtk-ai/rtk/blob/develop/docs/TELEMETRY.md) / README). Leave it disabled unless you consent at RTK’s prompt. Hooks change how agents run shell commands — review before enabling.

### Install binary

```bash
# macOS (Homebrew)
brew install rtk

# Linux / macOS script (review before piping)
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

Windows: download a release zip from [rtk releases](https://github.com/rtk-ai/rtk/releases), put `rtk.exe` on `PATH`.

### Init for your agents

| Agent | Init |
|-------|------|
| Claude Code | `rtk init -g` |
| Cursor | `rtk init -g --agent cursor` |
| Codex | `rtk init -g --codex` |
| Gemini CLI | `rtk init -g --gemini` |
| Other supported agents | `rtk init -g --agent <name>` (see upstream README) |

Restart the coding agent after init. Upstream: [RTK README](https://github.com/rtk-ai/rtk).

---

## Serena (advanced)

**License:** [MIT](https://github.com/oraios/serena/blob/main/LICENSE)  
**What it does:** Semantic code navigation / editing via MCP. Heavier setup than the companions above—use when you want LSP-style repo intelligence.  
**Privacy:** Typically local LSP/MCP; confirm upstream if using remote options.  
**Install (opt-in):** `--with-serena` / Settings checkbox. Hub runs `uv tool install -p 3.13 serena-agent`, best-effort `serena init`, and merges MCP launch config for selected agents. See [oraios/serena](https://github.com/oraios/serena).

---

## Ethics and expectations

- These are **recommendations**, not Hub dependencies.
- Prefer linking and opt-in CLI flags over silent installs.
- Hub install paths: `--with-i-have-adhd` / `--with-graphify` / `--with-rtk` / `--with-superpowers` / `--with-context7` / `--with-agent-browser` / `--with-serena` (and matching Settings checkboxes). All are opt-in; failures warn and never fail Hub connect.
- Respect each project’s license and attribution when redistributing (Hub does not vendor their code).
- For RTK, prefer the README/TELEMETRY docs over any conflicting one-line disclaimer about defaults.
