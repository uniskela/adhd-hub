#!/usr/bin/env python3
"""Split src/adhd_hub/ui/app.js IIFE into ES modules under ui/js/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src/adhd_hub/ui/app.js"
OUT = ROOT / "src/adhd_hub/ui/js"

# Exact names from current app.js
MODULE_MAP: dict[str, list[str]] = {
    "dom": [
        "copyReference",
        "safeHttpUrl",
        "safeLink",
        "browserTz",
        "fillTimezoneSelect",
        "formatWhen",
        "confirmDialog",
    ],
    "api": ["api"],
    "auth": [
        "showLogin",
        "showApp",
        "tryAuth",
        "handleLogin",
        "logout",
        "setLoginMode",
        "loadAuthStatus",
        "openPasswordDialog",
        "savePassword",
    ],
    "theme": ["applyTheme"],
    "screens": ["showScreen", "openWork"],
    "progress": [
        "renderRewards",
        "badgeIcon",
        "openSharePreview",
        "celebrate",
        "saveRewardPreferences",
        "renderStats",
    ],
    "now": [
        "rememberFocus",
        "chooseThread",
        "loadChosenThread",
        "suggestThread",
        "openPause",
        "pauseHere",
        "wireNotes",
        "captureStep",
        "renderFocus",
        "markDone",
        "renderReminders",
        "renderDriftBanner",
        "snoozeReminder",
        "dismissReminder",
        "openReminderDialog",
        "toggleReminderDue",
        "saveReminder",
        "startFocusSession",
        "clearFocusSession",
        "tickFocusSession",
        "updateFocusModeUi",
        "toggleFocusMode",
    ],
    "work": [
        "renderProjects",
        "renderArchivedProjects",
        "fillProjectForm",
        "renderProjectHeader",
        "openProjectDialog",
        "renderThreads",
        "loadThreads",
        "selectProject",
        "renderPending",
        "approvePending",
        "rejectPending",
        "archiveProject",
        "restoreProject",
        "saveProject",
        "renameProject",
        "deleteProject",
    ],
    "settings": [
        "selectSettingsTab",
        "loadPrefs",
        "loadForge",
        "loadOpenClaw",
        "openClawPayload",
        "saveOpenClaw",
        "testOpenClaw",
        "renderImportBanner",
        "scanForgeImport",
        "runForgeImport",
        "exportBackup",
        "importBackup",
        "saveSettings",
        "saveForge",
        "syncForge",
        "importForgeInbox",
    ],
    "load": ["loadOverview", "loadAll"],
}

STATE_EXPORT_ORDER = [
    "preferences",
    "authStatus",
    "loginMode",
    "celebrationTimeout",
    "completing",
    "threadsCache",
    "threadsRequest",
    "projectRequest",
    "tzKey",
    "currentView",
    "projectFilter",
    "overviewCache",
    "detailCache",
    "activeScreen",
    "chosenId",
    "chosenThread",
    "focusState",
    "focusRequest",
    "pauseTarget",
    "nowMessage",
    "shareFile",
    "shareVersion",
    "focusModeOn",
    "focusEndsAt",
    "focusTimerId",
    "archivedProjectsCache",
    "currentTz",
    "prefersReducedMotion",
    "$",
    "setMsg",
    "escapeHtml",
    "repoUrl",
    "repoDisplayUrl",
    "initRepoLinks",
]


def strip_iife(text: str) -> str:
    text = text.strip()
    if not text.startswith("(() => {"):
        raise SystemExit(f"Expected (() => {{ IIFE, got: {text[:40]!r}")
    if not text.endswith("})();"):
        raise SystemExit("Expected })(); IIFE close")
    return text[len("(() => {") : -len("})();")].strip("\n")


def find_load_all_end(body: str) -> int:
    m = list(re.finditer(r"\n  async function loadAll\(", body))
    if not m:
        raise SystemExit("loadAll not found")
    start = body.find("{", m[-1].start())
    depth = 0
    for i, ch in enumerate(body[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise SystemExit("Could not find end of loadAll")


def split_functions(region: str) -> tuple[str, dict[str, str]]:
    pat = re.compile(r"\n  (async )?function (\w+)\(", re.M)
    matches = list(pat.finditer(region))
    if not matches:
        raise SystemExit("No functions found")
    preamble = region[: matches[0].start()]
    functions: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(region)
        chunk = region[m.start() + 1 : end].rstrip() + "\n"
        chunk = re.sub(
            r"^  (async )?function (\w+)\(",
            lambda mm: f"export {mm.group(1) or ''}function {mm.group(2)}(",
            chunk,
            count=1,
        )
        functions[name] = chunk
    return preamble, functions


def build_state_js(preamble: str) -> str:
    pre = re.sub(
        r"^[\s\S]*?preferences\.removeItem\([^\n]+\);\n",
        "",
        preamble,
        count=1,
    )
    pre = re.sub(r"^  let ", "export let ", pre, flags=re.M)
    pre = re.sub(r"^  const completing =", "export const completing =", pre, flags=re.M)
    pre = re.sub(r"^  const tzKey =", "export const tzKey =", pre, flags=re.M)
    pre = re.sub(
        r"^  const (prefersReducedMotion|\$|setMsg|escapeHtml) =",
        r"export const \1 =",
        pre,
        flags=re.M,
    )
    pre = re.sub(
        r"^  const repoUrl = \$\(\"repo-link\"\)\.href;\n"
        r"  const repoDisplayUrl = repoUrl\.replace\(/\^https:\/\//, \"\"\);\n",
        "",
        pre,
        flags=re.M,
    )
    return (
        "/** Shared mutable UI state and helpers (ES module live bindings). */\n"
        "const preferenceCache = new Map();\n"
        "export const preferences = {\n"
        "  getItem(key) {\n"
        "    if (preferenceCache.has(key)) return preferenceCache.get(key);\n"
        "    try { return localStorage.getItem(key); } catch (_) { return null; }\n"
        "  },\n"
        "  setItem(key, value) {\n"
        "    preferenceCache.set(key, String(value));\n"
        "    try { localStorage.setItem(key, value); } catch (_) { /* In-memory fallback. */ }\n"
        "  },\n"
        "  removeItem(key) {\n"
        "    preferenceCache.set(key, null);\n"
        "    try { localStorage.removeItem(key); } catch (_) { /* Storage unavailable. */ }\n"
        "  },\n"
        "};\n"
        'preferences.removeItem("adhd_hub_token");\n\n'
        + pre.strip("\n")
        + "\n\n"
        'export let repoUrl = "";\n'
        'export let repoDisplayUrl = "";\n'
        "export function initRepoLinks() {\n"
        '  repoUrl = $("repo-link").href;\n'
        '  repoDisplayUrl = repoUrl.replace(/^https:\\/\\//, "");\n'
        "}\n"
    )


def used_names(chunk: str, names: list[str]) -> list[str]:
    found: list[str] = []
    for n in names:
        if n == "$":
            if re.search(r"(?<![\w$])\$(?![\w$])", chunk):
                found.append(n)
        elif re.search(rf"\b{re.escape(n)}\b", chunk):
            found.append(n)
    return found


def patch_celebrate(chunk: str) -> str:
    return re.sub(
        r"(export function celebrate\(\) \{\n"
        r"    if \(!\$\(\"rewards-enabled\"\)\.checked\) return;\n)",
        r"\1    if (prefersReducedMotion()) return;\n",
        chunk,
        count=1,
    )


def patch_show_screen(chunk: str) -> str:
    if "heading.focus" in chunk:
        return chunk
    return re.sub(
        r"(if \(screen !== \"work\"\) \{ \+\+projectRequest; \+\+threadsRequest; \}\n)"
        r"(  \})",
        r"\1"
        r'    const heading = $(screen + "-view")?.querySelector("h1");\n'
        r"    if (heading) {\n"
        r'      if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");\n'
        r"      try { heading.focus({ preventScroll: true }); } catch (_) { heading.focus(); }\n"
        r"    }\n"
        r"\2",
        chunk,
        count=1,
    )


def patch_render_stats(chunk: str) -> str:
    old = (
        "    if (!series.length) {\n"
        "      wrap.hidden = true;\n"
        "      return;\n"
        "    }\n"
        "    wrap.hidden = false;\n"
        '    chart.setAttribute("aria-label", "Last 14 days: " + series.map((day) => '
        '`${day.date}: ${day.added} added, ${day.finished} finished`).join("; "));\n'
    )
    new = (
        '    const summary = $("chart-summary");\n'
        "    if (!series.length) {\n"
        "      wrap.hidden = true;\n"
        '      if (summary) summary.textContent = "";\n'
        "      return;\n"
        "    }\n"
        "    wrap.hidden = false;\n"
        '    const label = "Last 14 days: " + series.map((day) => '
        '`${day.date}: ${day.added} added, ${day.finished} finished`).join("; ");\n'
        "    if (summary) {\n"
        "      summary.textContent = label;\n"
        '      chart.setAttribute("aria-hidden", "true");\n'
        '      chart.removeAttribute("aria-label");\n'
        '      chart.removeAttribute("role");\n'
        "    } else {\n"
        '      chart.setAttribute("role", "img");\n'
        '      chart.setAttribute("aria-label", label);\n'
        '      chart.removeAttribute("aria-hidden");\n'
        "    }\n"
    )
    if old not in chunk:
        raise SystemExit("renderStats chart block not found for a11y patch")
    return chunk.replace(old, new)


def write_module(
    mod: str,
    names: list[str],
    functions: dict[str, str],
    owner: dict[str, str],
) -> None:
    state_need: set[str] = set()
    from_mod: dict[str, set[str]] = {}
    chunks: list[str] = []
    state_names = [s for s in STATE_EXPORT_ORDER if s != "initRepoLinks"]
    for n in names:
        chunk = functions[n]
        if n == "celebrate":
            chunk = patch_celebrate(chunk)
        elif n == "showScreen":
            chunk = patch_show_screen(chunk)
        elif n == "renderStats":
            chunk = patch_render_stats(chunk)
        chunks.append(chunk)
        # Recompute after patches so injected symbols (e.g. $) are imported.
        state_need.update(used_names(chunk, state_names))
        for f in functions:
            if f == n:
                continue
            if re.search(rf"\b{re.escape(f)}\b", chunk):
                om = owner[f]
                if om != mod:
                    from_mod.setdefault(om, set()).add(f)
    lines: list[str] = []
    if state_need:
        ordered = [s for s in STATE_EXPORT_ORDER if s in state_need]
        lines.append("import { " + ", ".join(ordered) + " } from './state.js';\n")
    for om in sorted(from_mod):
        lines.append(
            "import { "
            + ", ".join(sorted(from_mod[om]))
            + " } from './"
            + om
            + ".js';\n"
        )
    lines.append("\n")
    lines.extend(chunks)
    (OUT / (mod + ".js")).write_text("".join(lines))


def write_boot(boot_code: str, functions: dict[str, str], owner: dict[str, str]) -> None:
    state_names = [s for s in STATE_EXPORT_ORDER if s != "initRepoLinks"]
    state_need = set(used_names(boot_code, state_names))
    state_need.update({"initRepoLinks", "$", "setMsg", "preferences"})
    from_mod: dict[str, set[str]] = {}
    for f in functions:
        if re.search(rf"\b{re.escape(f)}\b", boot_code):
            from_mod.setdefault(owner[f], set()).add(f)

    lines = [
        "import { "
        + ", ".join(s for s in STATE_EXPORT_ORDER if s in state_need)
        + " } from './state.js';\n"
    ]
    for om in sorted(from_mod):
        lines.append(
            "import { "
            + ", ".join(sorted(from_mod[om]))
            + " } from './"
            + om
            + ".js';\n"
        )
    lines.append("\n")
    lines.append("initRepoLinks();\n\n")
    dedented = re.sub(r"^  ", "", boot_code, flags=re.M)
    lines.append(dedented.strip("\n") + "\n")
    (OUT / "boot.js").write_text("".join(lines))


def main() -> None:
    body = strip_iife(APP_PATH.read_text())
    load_end = find_load_all_end(body)
    funcs_region = body[:load_end]
    boot_code = body[load_end:].strip("\n")
    preamble, functions = split_functions(funcs_region)

    mapped = {n for names in MODULE_MAP.values() for n in names}
    missing = set(functions) - mapped
    extra = mapped - set(functions)
    if missing:
        raise SystemExit(f"Unmapped functions: {sorted(missing)}")
    if extra:
        raise SystemExit(f"Missing in app.js: {sorted(extra)}")

    owner = {n: mod for mod, names in MODULE_MAP.items() for n in names}
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.js"):
        stale.unlink()

    (OUT / "state.js").write_text(build_state_js(preamble))
    for mod, names in MODULE_MAP.items():
        write_module(mod, names, functions, owner)
    write_boot(boot_code, functions, owner)
    print(f"Wrote {len(list(OUT.glob('*.js')))} modules to {OUT}")
    print("Functions:", ", ".join(sorted(functions)))


if __name__ == "__main__":
    main()
