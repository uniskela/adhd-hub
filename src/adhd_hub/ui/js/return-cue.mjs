/**
 * Advisory return-cue coaching for the dashboard.
 * Displays `return_cue` from thread payloads. Does not score cues.
 */

function normalize(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

/** @param {object|null|undefined} suggestion */
export function suggestionAction(suggestion) {
  const text = normalize(suggestion?.text);
  if (!text) return null;
  if (suggestion.source === "focus") return { label: "Use Focus", text, source: "focus" };
  if (suggestion.source === "next_steps") return { label: "Use next step", text, source: "next_steps" };
  return null;
}

/**
 * Pickup text worth showing on Now and in the thread list.
 * Missing payloads stay visible. Vague or missing cues do not.
 * @param {object|null|undefined} thread
 */
export function usefulResumeText(thread) {
  const text = String(thread?.resume_step ?? "").trim();
  if (!text) return "";
  const cue = thread?.return_cue;
  if (cue == null) return text;
  return cue.quality === "concrete" ? text : "";
}

/**
 * @param {object|null|undefined} cue
 * @param {string} fieldValue
 * @param {string|null|undefined} savedResume
 * @param {{ previous?: string, text?: string }|null} [applied]
 */
export function coachingView(cue, fieldValue, savedResume, applied = null) {
  const field = normalize(fieldValue);
  const saved = normalize(savedResume);
  const quality = cue?.quality;
  const coach = quality === "missing" || quality === "vague";
  const matchesSaved = field === saved;
  const hint = coach && matchesSaved && typeof cue.hint === "string" ? cue.hint.trim() : "";
  const action = coach && matchesSaved ? suggestionAction(cue?.suggestion) : null;
  const previous = normalize(applied?.previous);
  const showUndo = Boolean(applied) && field !== previous;
  return {
    showHint: Boolean(hint),
    hint,
    action,
    showUndo,
    pendingLabel: showUndo ? "Not saved yet. Edit or undo." : "",
    blockSave: false,
  };
}

/** Copy a suggestion into the field. Does not save. */
export function applyCueFill(currentValue, action) {
  if (!action?.text) return null;
  return {
    value: action.text,
    fill: { previous: String(currentValue ?? ""), text: action.text, source: action.source },
  };
}

export function undoCueFill(fill) {
  return fill ? String(fill.previous ?? "") : "";
}
