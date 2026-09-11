import { state, $, setMsg } from './state.js';
import { api } from './api.js';
import { loadAll } from './load.js';
import { savedScreen, showScreen } from './screens.js';

export function showLogin(message) {
    ++state.projectRequest;
    ++state.threadsRequest;
    ++state.focusRequest;
    clearTimeout(state.celebrationTimeout);
    $("celebration").hidden = true;
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    $("app-shell").hidden = true;
    $("login-gate").hidden = false;
    $("login-error").textContent = message || "";
    $("login-token").value = "";
    setLoginMode(state.authStatus.password_configured ? "password" : "token");
    $("login-token").focus();
  }
export function showApp() {
    $("login-gate").hidden = true;
    $("app-shell").hidden = false;
    $("password-banner").hidden = state.authStatus.password_configured || state.authStatus.development_mode;
    // Restore last tab without focusing the page heading (avoids green outline on refresh).
    showScreen(savedScreen(), { focusHeading: false });
  }
function safeOAuthReturnPath(value) {
    if (!value || typeof value !== "string" || value.length > 2048) return "";
    if (value.includes("\\") || value.startsWith("//")) return "";
    try {
      const parsed = new URL(value, location.origin);
      if (parsed.origin !== location.origin) return "";
      if (parsed.pathname !== "/api/oauth/authorize") return "";
      if (parsed.hash) return "";
      const qs = parsed.searchParams.toString();
      return `/api/oauth/authorize${qs ? `?${qs}` : ""}`;
    } catch (_) {
      return "";
    }
  }
function consumeOAuthReturn() {
    try {
      const params = new URLSearchParams(location.search);
      const raw = params.get("oauth_return") || "";
      const path = safeOAuthReturnPath(raw);
      if (!path) return false;
      params.delete("oauth_return");
      const next = `${location.pathname}${params.toString() ? `?${params}` : ""}${location.hash || ""}`;
      history.replaceState({}, "", next);
      window.location.assign(path);
      return true;
    } catch (_) {
      return false;
    }
  }
export async function tryAuth() {
    try {
      await api("/overview");
      if (consumeOAuthReturn()) return true;
      showApp();
      return true;
    } catch (e) {
      if (e.status === 401) {
        showLogin("");
        return false;
      }
      showLogin("Could not reach your hub. Check your connection and try again.");
      return false;
    }
  }
export async function handleLogin(ev) {
    ev.preventDefault();
    const value = state.loginMode === "token" ? $("login-token").value.trim() : $("login-token").value;
    if (!value) return;
    const button = $("login-form").querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Signing in…";
    $("login-error").textContent = "";
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ [state.loginMode]: value }) });
      $("login-token").value = "";
      if (consumeOAuthReturn()) return;
      showApp();
      await loadAll();
    } catch (error) {
      if (error.status === 401) { $("login-error").textContent = error.message; $("login-token").focus(); }
      else if (!$("app-shell").hidden) setMsg("Could not load dashboard: " + error.message);
      else $("login-error").textContent = error.status ? error.message : "Could not sign in. Check your connection and try again.";
    } finally {
      button.disabled = false;
      button.textContent = "Sign in";
    }
  }
export async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      state.overviewCache = null;
      state.detailCache = null;
      state.threadsCache = [];
      showLogin("Signed out.");
    } catch (error) {
      setMsg("Could not sign out. Please try again: " + error.message);
    }
  }
export function setLoginMode(mode) {
    state.loginMode = mode;
    const password = mode === "password";
    $("login-label").textContent = password ? "Password" : "Access token";
    $("login-description").textContent = password ? "Your next step is right where you left it." :
      "Use your hub token to get started. You can create a password once you’re in.";
    $("btn-login-method").textContent = password ? "Use recovery access token" : "Use dashboard password";
    $("btn-login-method").hidden = !state.authStatus.password_configured;
    $("login-token").type = "password";
    $("btn-show-password").textContent = "Show";
    $("btn-show-password").setAttribute("aria-pressed", "false");
    $("btn-show-password").setAttribute("aria-label", password ? "Show password" : "Show access token");
  }
export async function loadAuthStatus() {
    state.authStatus = await api("/auth/status");
    setLoginMode(state.authStatus.password_configured ? "password" : "token");
    $("password-banner").hidden = state.authStatus.password_configured || state.authStatus.development_mode;
    $("password-status").textContent = state.authStatus.development_mode
      ? "Local development mode. Set a private ADHD_HUB_AUTH_TOKEN on your server to enable password setup."
      : state.authStatus.password_configured ? "Dashboard password is set. Your assistant access token is separate."
      : "Create a password so you can keep the access token in your assistant configuration.";
  }
export function openPasswordDialog() {
    $("settings-dialog").close();
    $("password-title").textContent = state.authStatus.password_configured ? "Change your password" : "Set a dashboard password";
    $("password-method").value = state.authStatus.password_configured ? "password" : "token";
    $("password-dialog").showModal();
  }
export async function savePassword(event) {
    event.preventDefault();
    if ($("password-new").value !== $("password-confirm").value) {
      $("password-error").textContent = "The new passwords don’t match yet.";
      $("password-confirm").focus();
      return;
    }
    const button = $("password-form").querySelector('[type="submit"]');
    button.disabled = true;
    $("password-error").textContent = "";
    try {
      await api("/auth/password", { method: "PUT", body: JSON.stringify({
        current_secret: $("password-current").value,
        current_method: $("password-method").value,
        password: $("password-new").value,
      }) });
      $("password-dialog").close();
      await loadAuthStatus();
      setMsg("Password saved. Other browser sessions have been signed out.");
    } catch (error) { $("password-error").textContent = error.message; }
    finally { button.disabled = false; }
  }
