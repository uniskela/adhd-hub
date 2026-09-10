import { showLogin } from './auth.js';

export async function api(path, opts = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json", "X-Hub-Request": "1" },
      opts.headers || {}
    );
    const res = await fetch("/api" + path, Object.assign({}, opts, { headers }));
    if (!res.ok) {
      let message = "Something went wrong. Please try again.";
      try {
        const body = await res.json();
        message = typeof body.detail === "string" ? body.detail : "Please check the fields and try again.";
      } catch (_) { /* The server may return a non-JSON gateway error. */ }
      if (res.status === 401 && !path.startsWith("/auth/")) {
        showLogin("Your session ended. Sign in to continue.");
      }
      const err = new Error(message);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }
