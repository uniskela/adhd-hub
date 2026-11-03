/** Wave 8 — Short vs Deep Now return view (local preference only). */

export const RETURN_DENSITY_KEY = "adhd_hub_return_density";

/** @param {string | null | undefined} value */
export function normalizeReturnDensity(value) {
  return value === "short" ? "short" : "deep";
}

/** Apply body class for CSS-hidden Now chrome. */
export function applyReturnDensity(density) {
  const mode = normalizeReturnDensity(density);
  document.body.classList.toggle("return-short", mode === "short");
  document.body.classList.toggle("return-deep", mode === "deep");
  return mode;
}
