"""Static contract checks for PWA update detection (ts6-manager-inspired)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "adhd_hub" / "ui"


def test_sw_waits_for_skip_waiting_message() -> None:
    sw = (UI / "sw.js").read_text(encoding="utf-8")
    assert 'CACHE = "adhd-hub-shell-v38"' in sw
    assert 'event.data.type === "SKIP_WAITING"' in sw
    assert "self.skipWaiting()" in sw
    assert "self.clients.claim()" in sw
    # Must not auto-activate on install (would skip the Refresh toast).
    assert "then(() => self.skipWaiting())" not in sw
    assert "/ui/js/pwa-update.js" in sw


def test_pwa_update_client_offers_refresh_toast() -> None:
    src = (UI / "js" / "pwa-update.js").read_text(encoding="utf-8")
    assert "export function registerPwaUpdates" in src
    assert 'updateViaCache: "none"' in src
    assert 'postMessage({ type: "SKIP_WAITING" })' in src
    assert 'key: UPDATE_TOAST_KEY' in src or 'key: "pwa-update"' in src
    assert 'label: "Refresh"' in src
    assert "controllerchange" in src
    # Reload only the tab that clicked Refresh (activating), not every controlled tab.
    assert "hadController && activating && !refreshing" in src
    assert "registration.update()" in src
    assert "visibilitychange" in src


def test_boot_registers_pwa_updates() -> None:
    boot = (UI / "js" / "boot.js").read_text(encoding="utf-8")
    assert "registerPwaUpdates" in boot
    assert "from './pwa-update.js'" in boot or 'from "./pwa-update.js"' in boot
    # Legacy bare register without update probing should be gone from boot.
    assert 'register("/ui/sw.js", { scope: "/ui/" })' not in boot


def test_toast_supports_action_button() -> None:
    state = (UI / "js" / "state.js").read_text(encoding="utf-8")
    css = (UI / "app.css").read_text(encoding="utf-8")
    assert "_toastSetAction" in state
    assert "opts.action" in state
    assert ".toast-action" in css
