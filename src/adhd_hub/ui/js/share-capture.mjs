/** Pure helpers for Web Share Target → Save a thought (Wave 8). */

/** Compose Save-a-thought text from Web Share Target query params. */
export function composeShareCaptureSummary(params) {
  const title = (params.get("title") || "").trim();
  const text = (params.get("text") || "").trim();
  const url = (params.get("url") || "").trim();
  const parts = [];
  if (title) parts.push(title);
  if (text && text !== title) parts.push(text);
  if (url && url !== title && url !== text && !text.includes(url)) parts.push(url);
  return parts.join("\n").slice(0, 500);
}
