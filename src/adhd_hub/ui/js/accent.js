// Keep arbitrary user colours readable on every neutral and selected surface.
export function normalizeAccent(value) {
  return /^#[0-9a-f]{6}$/i.test(value || "") ? value.toLowerCase() : null;
}

function rgb(hex) {
  return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
}

function mix(colour, target, amount) {
  const to = rgb(target);
  return "#" + rgb(colour).map((channel, i) =>
    Math.round(channel + (to[i] - channel) * amount).toString(16).padStart(2, "0")
  ).join("");
}

export function contrast(a, b) {
  const luminance = (hex) => rgb(hex).map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, channel, i) => sum + channel * [0.2126, 0.7152, 0.0722][i], 0);
  const values = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (values[1] + 0.05) / (values[0] + 0.05);
}

export function accentPalette(value, dark) {
  const chosen = normalizeAccent(value);
  if (!chosen) return null;
  const surfaces = dark ? ["#14141c", "#1e1e29", "#292937"] : ["#f7f7fa", "#ffffff", "#eeeef4"];
  const target = dark ? "#ffffff" : "#000000";
  let accent = chosen;
  let soft;
  for (let step = 0; step <= 100; step++) {
    accent = mix(chosen, target, step / 100);
    soft = mix(surfaces[1], accent, 0.12);
    if ([...surfaces, soft].every((surface) => contrast(accent, surface) >= 4.8)) break;
  }
  const ink = contrast(accent, "#ffffff") > contrast(accent, "#000000") ? "#ffffff" : "#000000";
  const hover = mix(accent, target, 0.1);
  return { accent, soft, ink, hover };
}
