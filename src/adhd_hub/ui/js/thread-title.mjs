/**
 * Safe display title for Now / pause / focus chrome.
 * GET /threads/{id} once merged a notes-summary *object* onto `summary`
 * (or null), which rendered as "[object Object]" or blank — prefer strings only.
 * @param {object | null | undefined} thread
 * @returns {string}
 */
export function threadDisplayTitle(thread) {
  if (!thread || typeof thread !== "object") return "";
  const raw = thread.summary;
  if (typeof raw === "string") return raw.trim();
  // Legacy clobber: notes card parked under summary — never stringify it.
  if (raw && typeof raw === "object") return "";
  return "";
}
