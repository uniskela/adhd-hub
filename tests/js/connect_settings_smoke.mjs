import assert from "node:assert/strict";

const elements = new Map();
for (const [id, value] of Object.entries({
  ca_cursor: "cursor", ca_codex: "codex", ca_claude: "claude", ca_all: "*",
  "install-cmd": "", "install-cmd-win": "",
  "btn-copy-install": "", "btn-copy-install-win": "",
  "agents-user-setup": "", "agents-doctor-command": "", "connect-selection-summary": "",
})) elements.set(id, { value, checked: false, disabled: false, textContent: "" });
let apiCalls = 0;
globalThis.document = { getElementById: (id) => elements.get(id) };
globalThis.location = { origin: "https://hub.example" };
globalThis.fetch = () => {
  apiCalls += 1;
  throw new Error("Selection must not call the Hub");
};
// The Python runner copies the UI modules alongside this fixture with ESM enabled.
const { applyConnectAgents, syncConnectCommands, selectedConnectAgents } = await import("./settings.js");
const value = (id) => elements.get(id).value;
const text = (id) => elements.get(id).textContent;

applyConnectAgents([]);
assert.equal(value("install-cmd"), "");
assert.equal(value("install-cmd-win"), "");
assert.equal(elements.get("btn-copy-install").disabled, true);
assert.equal(elements.get("btn-copy-install-win").disabled, true);

applyConnectAgents(["claude-code"]);
assert.equal(selectedConnectAgents().join(","), "claude");
assert.equal(value("install-cmd"), 'curl -fsSL "https://hub.example/install.sh" | sh -s -- . --agents "claude"');
assert.equal(value("install-cmd-win"), '& ([scriptblock]::Create((irm "https://hub.example/install.ps1"))) -Agents "claude"');
assert.equal(elements.get("btn-copy-install").disabled, false);
assert.equal(elements.get("btn-copy-install-win").disabled, false);
assert.match(text("agents-user-setup"), /agents setup --agents claude --scope user/);
assert.match(text("agents-doctor-command"), /agents doctor --agents claude --scope user/);

applyConnectAgents(["cursor", "codex"]);
assert.match(text("connect-selection-summary"), /MCP setup: Cursor, Codex\./);
assert.match(value("install-cmd"), /--agents "cursor,codex"$/);
assert.match(value("install-cmd-win"), /-Agents "cursor,codex"$/);
assert.doesNotMatch(text("agents-user-setup"), /claude/);

applyConnectAgents(["*"]);
assert.match(value("install-cmd"), /--agents "\*"$/);
assert.match(value("install-cmd-win"), /-Agents "\*"$/);
assert.match(text("agents-user-setup"), /--agents codex,claude,cursor/);
assert.doesNotMatch(text("agents-doctor-command"), /\*/);

elements.get("ca_all").checked = false;
elements.get("ca_codex").checked = false;
syncConnectCommands();
assert.match(value("install-cmd"), /--agents "cursor,claude"$/);
applyConnectAgents([]);
assert.equal(value("install-cmd"), "");
assert.equal(elements.get("btn-copy-install").disabled, true);
assert.equal(apiCalls, 0);
console.log("connect_settings_smoke: ok");
