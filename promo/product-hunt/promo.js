/* ADHD Progress Hub · Product Hunt launch film
 *
 * Deterministic: every pixel is a pure function of absolute time t (seconds).
 * render(t) writes styles only; it never reads layout or remembers earlier frames.
 * Layout is measured once in build(), after fonts load, and frozen.
 *
 * Public API: window.promo = { seek(t), duration, fps, frames, beats, ready }
 */
(() => {
  "use strict";

  const W = 1920, H = 1080, T = 17.5, FPS = 60;
  const BEATS = [
    { t: 0.45, label: "Fragments arrive" },
    { t: 2.0, label: "Where was I?" },
    { t: 3.0, label: "Hub catches the dot" },
    { t: 4.0, label: "Resume cue" },
    { t: 6.0, label: "My work unfolds" },
    { t: 8.5, label: "Agents connect" },
    { t: 12.0, label: "Save and pause" },
    { t: 12.5, label: "Where you left off returns" },
    { t: 14.5, label: "Logo lands" },
  ];

  /* ---------------- palette (app.css tokens) ---------------- */
  const C = {
    paper: "#f7f6f3", card: "#ffffff", surface: "#efede8", ink: "#1f2328", inkSoft: "#454a52",
    muted: "#5f6570", line: "#e6e4de", controlLine: "#d9d7d0", accent: "#176b60",
    accentTint: "#f2f8f6", accentStrong: "#115348", gold: "#efc978",
    dCanvas: "#15171a", dCard: "#1d2024", dInk: "#eceef0", dMuted: "#a9aeb5",
    dLine: "#33373d", dControl: "#474c53", mint: "#7fc8b8",
  };

  /* ---------------- math ---------------- */
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const ease = {
    outCubic: (p) => 1 - (1 - p) ** 3,
    inCubic: (p) => p * p * p,
    inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - (-2 * p + 2) ** 3 / 2),
    outQuint: (p) => 1 - (1 - p) ** 5,
    inOutSine: (p) => -(Math.cos(Math.PI * p) - 1) / 2,
  };
  /* Closed-form under-damped spring, normalised so it starts at rest and settles by p = 1.
     zeta 0.8 overshoots ~1.5 %, zeta 0.7 ~4.6 %. Residual at p = 1 is < 0.1 %. */
  function spring(p, zeta = 0.8) {
    if (p <= 0) return 0;
    if (p >= 1) return 1;
    const w = 7 / zeta, wd = w * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w * p) * (Math.cos(wd * p) + ((zeta * w) / wd) * Math.sin(wd * p));
  }
  /* Travel ease for long hops: smooth departure, ~1.2 % landing overshoot, exact arrival.
     Peak speed ≈ 1.8 × average (inOutCubic is 3 ×, this spring ≈ 3.5 ×). */
  function travel(p) {
    if (p <= 0) return 0;
    if (p >= 1) return 1;
    const q = clamp((p - 0.55) / 0.45);
    return ease.inOutSine(clamp(p / 0.9)) + 0.03 * Math.sin(Math.PI * q) * (1 - q);
  }
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, p) => {
    const A = hex(a), B = hex(b);
    return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], p))).join(",")})`;
  };
  const lp = (a, b, p) => [lerp(a[0], b[0], p), lerp(a[1], b[1], p)];
  /* Arc between two points: p moves along, the bulge rides a sine of the eased progress. */
  function arc(a, b, p, bulge = 0.12, pe = p) {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    const k = Math.sin(Math.PI * clamp(pe)) * bulge * len;
    return [a[0] + dx * p + (-dy / len) * k, a[1] + dy * p + (dx / len) * k];
  }
  function poly(pts, u) {
    const segs = [];
    let total = 0;
    for (let i = 1; i < pts.length; i++) {
      const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      segs.push(l);
      total += l;
    }
    let d = clamp(u) * total;
    for (let i = 0; i < segs.length; i++) {
      if (d <= segs[i] || i === segs.length - 1) return lp(pts[i], pts[i + 1], segs[i] ? clamp(d / segs[i]) : 1);
      d -= segs[i];
    }
    return pts[pts.length - 1];
  }

  /* ---------------- DOM helpers ---------------- */
  const stage = document.getElementById("stage");
  function mk(cls, parent = stage, text, tag = "div") {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    parent.appendChild(e);
    return e;
  }
  function vis(e, o) {
    const v = clamp(o);
    e.style.opacity = v.toFixed(4);
    e.style.visibility = v <= 0.0005 ? "hidden" : "visible";
  }
  function place(e, x, y, s = 1) { e.style.transform = `translate(${x.toFixed(2)}px,${y.toFixed(2)}px) scale(${s.toFixed(4)})`; }
  function box(e, r, radius) {
    e.style.transform = `translate(${r[0].toFixed(2)}px,${r[1].toFixed(2)}px)`;
    e.style.width = `${Math.max(0, r[2]).toFixed(2)}px`;
    e.style.height = `${Math.max(0, r[3]).toFixed(2)}px`;
    if (radius != null) e.style.borderRadius = `${Math.max(0, Math.min(radius, r[2] / 2, r[3] / 2)).toFixed(2)}px`;
  }
  const lerpRect = (a, b, p) => a.map((v, i) => lerp(v, b[i], p));
  const z = (e, n) => { e.style.zIndex = n; };

  /* A line of display type that enters and leaves word by word.
     In and out windows never overlap within one caption, and captions are scheduled
     so that no two are visible at once. */
  function caption(text, cy, size, color, zi, parent = stage) {
    const c = mk("caption", parent);
    c.style.fontSize = `${size}px`;
    c.style.color = color;
    z(c, zi);
    const words = text.split(" ").map((w, i, all) => {
      const s = mk("w", c, w, "span");
      if (i < all.length - 1) c.appendChild(document.createTextNode(" "));
      return s;
    });
    place(c, 0, cy - size * 0.6);
    return {
      el: c,
      words,
      render(t, tin, tout, stagger = 0.055) {
        const on = t >= tin - 0.001 && t <= tout + 0.25;
        c.style.visibility = on ? "visible" : "hidden";
        if (!on) return;
        const po = ease.inCubic(prog(t, tout, tout + 0.22));
        words.forEach((w, i) => {
          const a = tin + i * stagger;
          const pin = spring(prog(t, a, a + 0.55), 0.82);
          const fade = ease.outCubic(prog(t, a, a + 0.22));
          const y = (1 - pin) * size * 0.42 - po * size * 0.22;
          w.style.transform = `translateY(${y.toFixed(2)}px)`;
          w.style.opacity = (fade * (1 - po)).toFixed(4);
        });
      },
    };
  }

  /* Text that morphs between layouts: one element, transform scale from a 40 px base. */
  function mtext(text, zi) {
    const e = mk("mtext", stage, text);
    z(e, zi);
    return {
      el: e,
      set(x, y, size, weight, color, o = 1) {
        place(e, x, y, size / 40);
        e.style.fontWeight = Math.round(weight);
        e.style.color = color;
        vis(e, o);
      },
    };
  }

  const SVGNS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs, parent) {
    const e = document.createElementNS(SVGNS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  /* Official assets, geometry verbatim from docs/assets/*.svg (never transformed per-frame). */
  const ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="100%" height="100%"><rect width="64" height="64" rx="18" fill="#176B60"/><path d="M18 44h9a13 13 0 0 0 13-13V21" fill="none" stroke="#F7F5EF" stroke-width="7" stroke-linecap="round"/><circle cx="19" cy="23" r="5" fill="#EFC978"/></svg>';
  /* Wordmark text uses Figtree, as the in-app wordmark does; logo.svg's system-ui varies by OS. */
  const LOGO_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 80" width="720" height="160"><rect x="8" y="8" width="64" height="64" rx="18" fill="#176B60"/><path d="M26 52h9a13 13 0 0 0 13-13V29" fill="none" stroke="#F7F5EF" stroke-width="7" stroke-linecap="round"/><circle cx="27" cy="31" r="5" fill="#EFC978"/><text x="90" y="51" font-family="Figtree, system-ui, sans-serif" font-weight="700" font-size="32" letter-spacing="-1" fill="#203832">Progress Hub</text></svg>';
  const BEND = "M26 52h9a13 13 0 0 0 13-13V29";

  /* ====================================================================
     BUILD (once, after fonts load)
     ==================================================================== */
  const G = {}; // geometry measured at build time
  const E = {}; // elements

  function build() {
    const center = [960, 540];
    G.center = center;

    /* ---------- Scene 1 ---------- */
    // Visited in this order, round the ring, so no hop crosses the frame.
    G.envs = [
      { name: "Cursor", a: [330, 300], frag: "Refactor auth" },
      { name: "Dev LXC", a: [250, 726], frag: "Finish migration" },
      { name: "Laptop", a: [900, 880], frag: null },
      { name: "Claude", a: [1500, 690], frag: "Fix deployment" },
      { name: "Codex", a: [1430, 282], frag: "Test API" },
    ];
    G.hops = [0.45, 0.8, 1.15, 1.5, 1.85];
    E.env = G.envs.map((v) => {
      const label = mk("env", stage, v.name);
      z(label, 12);
      let chip = null;
      if (v.frag) {
        chip = mk("chip");
        z(chip, 11);
        // Text lives in a separate element so it can travel on its own later.
        const tt = mtext(v.frag, 13);
        chip.style.width = "10px";
        chip.__text = tt;
      }
      return { label, chip };
    });
    // Chip widths from their text (26 px, 600) + 2 × 17 px padding.
    E.env.forEach((o) => {
      if (!o.chip) return;
      o.chip.__text.el.style.fontWeight = 600;
      const w = o.chip.__text.el.offsetWidth * (26 / 40);
      o.chip.__w = w + 34;
      o.chip.style.width = `${o.chip.__w}px`;
    });
    E.question = caption("Where was I?", 520, 120, C.ink, 20);

    /* ---------- Scene 2: Now card, "Welcome back" ---------- */
    G.k = 1.5;
    G.card2 = [420, 248, 1080, 390 * 1.5];
    E.shell2 = mk("shell");
    z(E.shell2, 20);
    const g2 = mk("ui");
    z(g2, 30);
    E.g2 = g2;
    E.g2eyebrow = mk("eyebrow", g2, "Welcome back");
    place(E.g2eyebrow, 32, 32);
    E.g2meta = mk("meta", g2, "Auth service · last touched 4 days ago");
    place(E.g2meta, 32, 96);
    E.g2menu = mk("menu", g2);
    place(E.g2menu, 644, 32);
    [0, 1, 2].forEach((i) => { const d = mk("", E.g2menu, null, "i"); d.style.left = `${13 + i * 7}px`; });
    E.g2panel = mk("panel", g2);
    box(E.g2panel, [32, 142, 656, 86]);
    E.g2plabel = mk("plabel", g2, "Where you left off");
    place(E.g2plabel, 50, 158);
    E.g2ptext = mk("ptext", g2, "Finish the auth callback test.");
    place(E.g2ptext, 50, 186);
    E.g2btns = mk("btns flow", g2);
    place(E.g2btns, 32, 252);
    E.g2resume = mk("btn primary", E.g2btns, "Resume");
    E.g2choose = mk("btn ghost", E.g2btns, "Choose something else");
    E.g2div = mk("divider", g2);
    place(E.g2div, 32, 320);
    E.g2notes = mk("notes", g2);
    E.g2notes.innerHTML = "<b></b>Project notes";
    place(E.g2notes, 32, 336);
    G.resume2 = { x: E.g2resume.offsetLeft, w: E.g2resume.offsetWidth };

    // Title of the "Refactor auth" thread: chip text → Now title → row 1 title.
    E.tRefactor = E.env[0].chip.__text;
    z(E.tRefactor.el, 32);

    /* ---------- Scene 3: My work (real px × 1.2 from 240,220) ---------- */
    G.mk = 1.2;
    G.mwO = [240, 220];
    const mw = mk("mw");
    z(mw, 25); // above the card shell it unfolds from
    place(mw, G.mwO[0], G.mwO[1], G.mk);
    E.mw = mw;
    E.mwH1 = mk("mw-h1", mw, "My work");
    E.mwSub = mk("mw-sub", mw, "Everything you’ve started, with notes for picking it back up.");
    place(E.mwSub, 0, 46);
    E.mwSearch = mk("search", mw);
    place(E.mwSearch, 733, 0);
    const sIcon = mk("", E.mwSearch);
    sIcon.innerHTML = '<svg viewBox="0 0 16 16" width="16" height="16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="#454a52" stroke-width="1.5"/><path d="M10.4 10.4 14 14" stroke="#454a52" stroke-width="1.5" stroke-linecap="round"/></svg>';
    place(sIcon, 13, 13);
    place(mk("search-text", E.mwSearch, "Search your work"), 40, 11);
    E.mwNew = mk("newbtn", mw);
    E.mwNew.innerHTML = '<span style="position:static;font-weight:400;font-size:22px;margin-right:9px;vertical-align:-2px">+</span>New';
    E.mwNew.style.width = "auto";
    place(E.mwNew, 1200 - E.mwNew.offsetWidth, 0);
    place(E.mwSearch, 1200 - E.mwNew.offsetWidth - 12 - 376, 0);
    E.railH = mk("rail-h", mw, "Projects");
    place(E.railH, 12, 112);
    const projs = [["All projects", "", 10, true], ["Auth service", "2", 31], ["Homelab", "1", 31], ["Deploy pipeline", "1", 31]];
    E.projs = projs.map(([name, n, ind, active], i) => {
      const r = mk(`proj${active ? " active" : ""}`, mw);
      place(r, 0, 138 + i * 54);
      place(mk("proj-name", r, name), ind, 12);
      if (n) place(mk("proj-count", r, n), 280, 12);
      return r;
    });
    E.listH = mk("list-h", mw, "All projects");
    place(E.listH, 350, 116);
    E.seg = mk("seg flow", mw);
    E.seg.style.display = "flex";
    E.seg.style.gap = "2px";
    E.seg.style.padding = "3px";
    [["Open", "4", true], ["Later", "0"], ["Finished", "3"]].forEach(([l, n, a]) => {
      const tab = mk(`tab${a ? " active" : ""}`, E.seg);
      tab.style.padding = "0 14px";
      tab.style.display = "inline-block";
      tab.innerHTML = `${l}<span>${n}</span>`;
    });
    place(E.seg, 1200 - E.seg.offsetWidth, 110);

    // Step rows, clipped to the card's rounded rectangle.
    G.rowsCard = [660, 412, 1020, 417 * 1.2];
    const clip = mk("", mw);
    clip.style.overflow = "hidden";
    clip.style.borderRadius = "14px";
    box(clip, [351, 161, 848, 415]);
    E.rowClip = clip;
    G.rows = [
      { title: "Refactor auth", scan: "Finish the auth callback test.", proj: "Auth service", when: "4 days ago", badge: "In focus" },
      { title: "Finish migration", scan: "Move the last two LXCs to the new node.", proj: "Homelab", when: "last week" },
      { title: "Test API", scan: "Add a test for the empty-token case.", proj: "Auth service", when: "yesterday" },
      { title: "Fix deployment", scan: "New base image builds locally.", proj: "Deploy pipeline", when: "2 days ago" },
    ];
    E.rows = G.rows.map((r, i) => {
      const top = i * 104; // clip starts 1 px inside the card border
      const o = {};
      o.bg = mk("row-bg", clip);
      place(o.bg, 0, top);
      o.bg.style.background = C.accentTint;
      if (i > 0) { o.line = mk("row-line", clip); place(o.line, 0, top - 1); }
      if (i === 0) { o.edge = mk("row-edge", clip); place(o.edge, 0, top); }
      o.title = mk("row-title", clip, r.title);
      place(o.title, 19, top + 16);
      o.scan = mk("row-scan", clip, `Left off: ${r.scan}`);
      place(o.scan, 19, top + 42.4);
      o.proj = mk("row-proj", clip, r.proj);
      place(o.proj, 19, top + 67.4);
      let wy = top + 18;
      if (r.badge) {
        o.badge = mk("row-badge", clip, r.badge);
        place(o.badge, 829 - o.badge.offsetWidth, top + 17);
        wy = top + 17 + 20 + 6;
      }
      o.when = mk("row-when", clip, r.when);
      place(o.when, 829 - o.when.offsetWidth, wy);
      o.parts = [o.scan, o.proj, o.when, o.badge, o.line].filter(Boolean);
      return o;
    });
    const mwPt = (rx, ry) => [G.mwO[0] + rx * G.mk, G.mwO[1] + ry * G.mk];
    G.mwPt = mwPt;
    // +1.92 px: the 40 px-based morph text has a shorter line box than .row-title (22.4 px × 1.2)
    G.rowTitle = (i) => { const p = mwPt(351 + 19, 161 + i * 104 + 16); return [p[0], p[1] + 1.92]; };
    G.rowMarker = (i) => [624, mwPt(0, 161 + i * 104 + 16 + 11.2)[1]];
    E.cap3 = caption("Your unfinished work. One place.", 132, 60, C.ink, 40);

    /* ---------- Scene 4: dark agent scene ---------- */
    E.darkMask = mk("mask");
    E.darkMask.style.background = C.dCanvas;
    z(E.darkMask, 50);
    G.hubCard = [680, 400, 560, 264];
    G.portY = 526;
    G.pills = [
      { name: "Cursor", c: [330, G.portY] },
      { name: "Codex", c: [1590, G.portY] },
      { name: "Claude Code", c: [960, 860] },
    ];
    E.pills = G.pills.map((p) => {
      const e = mk("pill", stage, p.name);
      z(e, 60);
      p.w = e.offsetWidth;
      return e;
    });
    G.cursorPort = [G.pills[0].c[0] + G.pills[0].w / 2, G.portY];
    G.codexPort = [G.pills[1].c[0] - G.pills[1].w / 2, G.portY];
    G.claudePort = [960, G.pills[2].c[1] - 36];
    G.hubL = [G.hubCard[0], G.portY];
    G.hubR = [G.hubCard[0] + G.hubCard[2], G.portY];
    G.hubB = [960, G.hubCard[1] + G.hubCard[3]];
    G.hubMarker = [G.hubCard[0] - 36, G.portY];
    const lines = svgEl("svg", { class: "layer", width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    stage.appendChild(lines);
    z(lines, 58);
    E.lines = lines;
    const segs = [
      [G.hubL, G.cursorPort],
      [G.hubR, G.codexPort],
      [G.hubB, G.claudePort],
    ];
    E.base = segs.map(([a, b]) => svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: C.dControl, "stroke-width": 2, "stroke-linecap": "round" }, lines));
    E.lit = segs.map(([a, b]) => svgEl("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: C.mint, "stroke-width": 3, "stroke-linecap": "round" }, lines));
    G.segLen = segs.map(([a, b]) => Math.hypot(b[0] - a[0], b[1] - a[1]));
    E.tools = [
      { text: "check overlap", at: [(G.hubL[0] + G.cursorPort[0]) / 2, G.portY - 50], center: true },
      { text: "resume context", at: [(G.hubR[0] + G.codexPort[0]) / 2, G.portY - 50], center: true },
      { text: "save progress", at: [984, (G.hubB[1] + G.claudePort[1]) / 2 - 14], center: false },
    ].map((d) => {
      const e = mk("tool", stage, d.text);
      z(e, 61);
      d.x = d.center ? d.at[0] - e.offsetWidth / 2 : d.at[0];
      d.el = e;
      return d;
    });
    E.overlapResult = mk("result", stage, "Already in progress");
    z(E.overlapResult, 61);
    G.overlapResultX = G.pills[0].c[0] - E.overlapResult.offsetWidth / 2;
    E.cap4 = caption("Your agents can remember too.", 196, 60, C.dInk, 62);

    // Hub card contents (stage px)
    E.hubIcon = mk("");
    E.hubIcon.innerHTML = ICON_SVG;
    E.hubIcon.style.width = "44px";
    E.hubIcon.style.height = "44px";
    z(E.hubIcon, 82);
    E.hubName = mk("hub-name", stage, "Progress Hub");
    E.hubName.style.color = C.dInk;
    z(E.hubName, 82);
    E.hubDiv = mk("");
    E.hubDiv.style.background = C.dLine;
    z(E.hubDiv, 82);
    E.hubMetaOld = mk("hub-meta", stage, "Deploy pipeline · last touched 2 days ago");
    E.hubMetaNew = mk("hub-meta", stage, "Deploy pipeline · last touched just now");
    E.hubLeft = mk("hub-left", stage, "Left off: New base image builds locally.");
    [E.hubMetaOld, E.hubMetaNew, E.hubLeft].forEach((e) => z(e, 82));
    E.lightMask = mk("mask");
    E.lightMask.style.background = C.paper;
    z(E.lightMask, 70);

    /* ---------- Shell A: row 4 → Hub card → Now card (scenes 4–5) ---------- */
    // Two copies, one per theme. The copy on top is clipped by the same circle that
    // reveals the new theme behind it, so the card changes theme exactly where the mask passes.
    E.shellL = mk("shell");
    E.shellD = mk("shell");
    E.shellD.style.background = C.dCard;
    E.shellD.style.borderColor = C.dLine;
    E.shellD.style.boxShadow = "none";
    E.tFixL = mtext("Fix deployment", 83);
    E.tFixD = mtext("Fix deployment", 83);
    // Row-3 secondary text copies that ride with the shell during the lift.
    E.aScan = mk("row-scan", stage, "Left off: New base image builds locally.");
    E.aProj = mk("row-proj", stage, "Deploy pipeline");
    E.aWhen = mk("row-when", stage, "2 days ago");
    [E.aScan, E.aProj, E.aWhen].forEach((e) => z(e, 82));
    G.aWhenW = E.aWhen.offsetWidth;

    /* ---------- Scene 5: Now card states ---------- */
    G.card5 = [420, 290];
    G.h5 = { working: 328, pausing: 428, welcome: 390 };
    const g5 = mk("ui");
    z(g5, 84);
    E.g5 = g5;
    E.e5 = ["You’re on it", "Leave a note for later", "Welcome back"].map((s) => { const e = mk("eyebrow", g5, s); place(e, 32, 32); return e; });
    E.g5meta = mk("meta", g5, "Deploy pipeline · last touched just now");
    place(E.g5meta, 32, 96);
    E.g5menu = mk("menu", g5);
    place(E.g5menu, 644, 32);
    [0, 1, 2].forEach((i) => { const d = mk("", E.g5menu, null, "i"); d.style.left = `${13 + i * 7}px`; });
    // working
    E.g5cue = mk("cue", g5, "Start with the smallest part. You can leave a note for later whenever you stop.");
    place(E.g5cue, 32, 142);
    E.g5wbtns = mk("btns flow", g5);
    place(E.g5wbtns, 32, 190);
    E.g5done = mk("btn primary", E.g5wbtns, "Mark step done");
    E.g5pause = mk("btn ghost", E.g5wbtns, "Pause and leave a note");
    G.pauseBtn = { x: E.g5pause.offsetLeft, w: E.g5pause.offsetWidth };
    // pausing
    E.g5flabel = mk("flabel", g5, "What’s the next tiny step?");
    place(E.g5flabel, 32, 142);
    E.g5pbtns = mk("btns flow", g5);
    place(E.g5pbtns, 32, 290);
    E.g5save = mk("btn primary", E.g5pbtns, "Save and pause");
    E.g5keep = mk("btn ghost", E.g5pbtns, "Keep working");
    G.saveBtn = { x: E.g5save.offsetLeft, w: E.g5save.offsetWidth };
    // welcome
    E.g5plabel = mk("plabel", g5, "Where you left off");
    place(E.g5plabel, 50, 158);
    E.g5rbtns = mk("btns flow", g5);
    place(E.g5rbtns, 32, 252);
    E.g5resume = mk("btn primary", E.g5rbtns, "Resume");
    E.g5choose = mk("btn ghost", E.g5rbtns, "Choose something else");
    // notes (y follows the card state)
    E.g5div = mk("divider", g5);
    E.g5notes = mk("notes", g5);
    E.g5notes.innerHTML = "<b></b>Project notes";
    // stage-level morph pieces: field, panel, typed sentence
    E.field = mk("field");
    z(E.field, 83);
    E.ring = mk("");
    E.ring.style.border = `3px solid ${C.accent}`;
    z(E.ring, 83);
    E.placeholder = mk("placeholder", g5, "Open the draft and write the first sentence");
    place(E.placeholder, 47, 183);
    E.panel5 = mk("panel");
    z(E.panel5, 83);
    E.note = mk("mtext");
    z(E.note, 85);
    E.noteText = mk("", E.note, "", "span");
    E.noteText.style.position = "static";
    E.caret = mk("caret", E.note, null, "span");
    E.caret.style.height = "42px";
    E.caret.style.width = "3px";
    E.caret.style.verticalAlign = "-9px";
    G.noteFull = "Verify the Docker health check.";
    E.noteText.textContent = G.noteFull;
    G.noteW = E.noteText.offsetWidth; // at 40 px
    E.toast = mk("toast");
    z(E.toast, 86);
    const td = mk("toast-dot", E.toast);
    place(td, 16, 19);
    place(mk("toast-text", E.toast, "Next step saved. You can stop here."), 34, 12);
    place(mk("toast-x", E.toast, "×"), 334, 12);
    E.toast.style.height = "46px";
    E.cap5 = caption("Stop now. Pick it up later.", 160, 60, C.ink, 87);

    /* ---------- Scene 6: brand ---------- */
    E.logo = mk("");
    E.logo.innerHTML = LOGO_SVG;
    z(E.logo, 90);
    const txt = E.logo.querySelector("text");
    const bb = txt.getBBox();
    G.logoVBRight = bb.x + bb.width;
    G.logoS = 2;
    const vbCenter = (8 + G.logoVBRight) / 2;
    G.logoO = [Math.round(960 - vbCenter * G.logoS), 236];
    place(E.logo, G.logoO[0], G.logoO[1]);
    G.vb = (x, y) => [G.logoO[0] + x * G.logoS, G.logoO[1] + y * G.logoS];
    // Trail: a separate path with the bend's exact geometry, drawn only before the logo appears.
    const trailSvg = svgEl("svg", { class: "layer", width: 720, height: 160, viewBox: "0 0 360 80" });
    stage.appendChild(trailSvg);
    place(trailSvg, G.logoO[0], G.logoO[1]);
    z(trailSvg, 89);
    E.trailSvg = trailSvg;
    E.trail = svgEl("path", { d: BEND, fill: "none", stroke: "#176B60", "stroke-width": 7, "stroke-linecap": "round" }, trailSvg);
    G.bendLen = E.trail.getTotalLength();
    E.trail.setAttribute("stroke-dasharray", `${G.bendLen} ${G.bendLen}`);
    G.bendAt = (u) => { const p = E.trail.getPointAtLength(clamp(u) * G.bendLen); return G.vb(p.x, p.y); };
    G.bendPts = Array.from({ length: 121 }, (_, i) => G.bendAt(i / 120)); // frozen lookup, no per-frame SVG reads
    G.logoDot = G.vb(27, 31);
    E.tag = caption("Small steps. Your pace.", 512, 76, C.ink, 91);
    E.name = caption("ADHD Progress Hub", 620, 36, C.ink, 91);
    E.sub = caption("Self-hosted continuity for unfinished work.", 672, 30, C.inkSoft, 91);
    E.sub.el.style.fontWeight = 500;
    E.sub.el.style.letterSpacing = "-0.01em";
    E.chips = caption("Open source · MCP · Cursor · Codex · Claude Code", 726, 24, C.muted, 91);
    E.chips.el.style.fontWeight = 500;
    E.chips.el.style.letterSpacing = "0";
    E.cta = mk("cta", stage, "Now on Product Hunt");
    z(E.cta, 91);
    G.ctaW = E.cta.offsetWidth;

    /* ---------- the dot (always last) ---------- */
    E.dot = mk("dot");
    z(E.dot, 100);
  }

  /* ====================================================================
     MOTION FUNCTIONS — shared by everything the dot drives
     ==================================================================== */

  // Scene 1 drift: everything eases 6 % away from centre while dimming.
  const driftP = (t) => ease.inOutCubic(prog(t, 1.6, 2.4));
  function drifted(p, t) {
    const f = 1 + 0.06 * driftP(t);
    return [G.center[0] + (p[0] - G.center[0]) * f, G.center[1] + (p[1] - G.center[1]) * f];
  }
  // Scene 2 card bloom grows out of the dot at frame centre.
  function card2Rect(t) {
    const s = spring(prog(t, 3.0, 3.45), 0.78);
    const [x, y, w, h] = G.card2;
    const cx = x + w / 2, cy = y + h / 2;
    return [cx - (w * s) / 2, cy - (h * s) / 2, w * s, h * s];
  }
  const p23 = (t) => spring(prog(t, 5.5, 6.05), 0.86); // card → step list
  function shell2Rect(t) {
    if (t < 5.5) return card2Rect(t);
    return lerpRect(G.card2, G.rowsCard, p23(t));
  }
  const nowPt = (o, rx, ry) => [o[0] + rx * G.k, o[1] + ry * G.k];
  const title2 = () => nowPt(G.card2, 32, 58);
  // Shell A: lift (8.0) → hub card (8.1–8.6) → Now card (10.3–10.8) → state heights (scene 5)
  const pA1 = (t) => spring(prog(t, 8.1, 8.62), 0.86);
  const pA2 = (t) => spring(prog(t, 10.34, 10.86), 0.86);
  const pW2P = (t) => spring(prog(t, 11.25, 11.65), 0.84);
  const pP2W = (t) => spring(prog(t, 12.05, 12.6), 0.78);
  function card5H(t) {
    let h = lerp(G.h5.working, G.h5.pausing, pW2P(t));
    if (t >= 12.05) h = lerp(G.h5.pausing, G.h5.welcome, pP2W(t));
    return h;
  }
  function rowRect(i) {
    const y = G.mwPt(0, 161 + i * 104)[1];
    return [660, y, 1020, 103 * G.mk];
  }
  function shellARect(t) {
    if (t < 10.3) return lerpRect(rowRect(3), G.hubCard, pA1(t));
    const now = [G.card5[0], G.card5[1], 720 * G.k, card5H(t) * G.k];
    if (t < 10.86) return lerpRect(G.hubCard, [G.card5[0], G.card5[1], 720 * G.k, G.h5.working * G.k], pA2(t));
    return now;
  }
  const hubTitle = [708, 508];
  const now5Title = () => nowPt(G.card5, 32, 58);
  function tFixState(t) {
    const row = G.rowTitle(3);
    if (t < 10.3) {
      const p = pA1(t);
      return { x: lerp(row[0], hubTitle[0], p), y: lerp(row[1], hubTitle[1], p), size: lerp(16 * G.mk, 30, p), w: lerp(600, 700, p), c: p };
    }
    const p = pA2(t), n = now5Title();
    return { x: lerp(hubTitle[0], n[0], p), y: lerp(hubTitle[1], n[1], p), size: lerp(30, 26 * G.k, p), w: 700, c: 1 - p, light: true };
  }

  /* Theme masks: circles that grow from the dot past every frame corner. */
  function maskDark(t) {
    const c = G.rowMarker(3);
    return { c, R: ease.inOutCubic(prog(t, 8.0, 8.36)) * 1640 };
  }
  function maskLight(t) {
    return { c: G.hubMarker, R: ease.inOutCubic(prog(t, 10.3, 10.62)) * 1480 };
  }

  /* ---------- the dot ---------- */
  function dotAt(t) {
    const env = (i) => drifted(G.envs[i].a, t);
    const Q = [960, 646];
    // Scene 1 hops
    if (t < 0.15) return G.center;
    for (let i = 0; i < 5; i++) {
      const start = i === 0 ? 0.15 : G.hops[i - 1] + 0.03;
      const end = G.hops[i];
      if (t < start) return env(i - 1);
      if (t < end) {
        const from = i === 0 ? G.center : env(i - 1);
        const u = prog(t, start, end);
        return arc(from, env(i), travel(u), 0.12, ease.inOutCubic(u));
      }
    }
    if (t < 1.88) return env(4);
    if (t < 2.27) { const u = prog(t, 1.88, 2.27); return arc(env(4), Q, travel(u), -0.45, ease.inOutCubic(u)); } /* around the headline, never through it */
    if (t < 2.8) return Q;
    if (t < 3.0) return lp(Q, G.center, ease.inOutCubic(prog(t, 2.8, 3.0)));
    // Scene 2
    const panelM2 = [384, G.card2[1] + (142 + 26) * G.k];
    const resumePtr = nowPt(G.card2, 32 + G.resume2.x + G.resume2.w - 9, 274);
    const titleM2 = [384, title2()[1] + 26 * G.k * 0.6];
    if (t < 3.6) return G.center;
    if (t < 3.95) { const u = prog(t, 3.6, 3.95); return arc(G.center, panelM2, travel(u), 0.1, ease.inOutCubic(u)); }
    if (t < 4.75) return panelM2;
    if (t < 4.98) { const u = prog(t, 4.75, 4.98); return arc(panelM2, resumePtr, travel(u), 0.12, ease.inOutCubic(u)); }
    if (t < 5.12) return resumePtr;
    if (t < 5.42) { const u = prog(t, 5.12, 5.42); return arc(resumePtr, titleM2, travel(u), 0.1, ease.inOutCubic(u)); }
    if (t < 5.5) return titleM2;
    // Scene 3: ride the morph (same p as the shell and the title)
    if (t < 6.05) {
      const p = p23(t), r = shell2Rect(t);
      return [r[0] - 36, lerp(titleM2[1], G.rowMarker(0)[1], p)];
    }
    const rowHops = [[6.2, 6.45], [6.55, 6.8], [6.9, 7.15]];
    for (let i = 0; i < 3; i++) {
      const [a, b] = rowHops[i];
      if (t < a) return G.rowMarker(i);
      if (t < b) return lp(G.rowMarker(i), G.rowMarker(i + 1), spring(prog(t, a, b), 0.78));
    }
    if (t < 8.0) return G.rowMarker(3);
    // Scene 4
    if (t < 8.62) {
      const r = shellARect(t), s = tFixState(t);
      return [r[0] - 36, s.y + (s.size * 1.2) / 2];
    }
    const hubM = [G.hubCard[0] - 36, hubTitle[1] + 18];
    if (t < 8.88) return lp(hubM, G.cursorPort, ease.inOutSine(prog(t, 8.62, 8.88)));
    if (t < 8.95) return G.cursorPort;
    if (t < 9.4) return poly([G.cursorPort, G.hubL, G.hubR, G.codexPort], ease.inOutSine(prog(t, 8.95, 9.4)));
    if (t < 9.5) return G.codexPort;
    if (t < 9.95) return poly([G.codexPort, G.hubR, G.hubB, G.claudePort], ease.inOutSine(prog(t, 9.5, 9.95)));
    if (t < 10.0) return G.claudePort;
    if (t < 10.25) return poly([G.claudePort, G.hubB, G.hubL, hubM], ease.inOutSine(prog(t, 10.0, 10.25)));
    if (t < 10.3) return hubM;
    // Scene 5
    if (t < 10.86) {
      const r = shellARect(t), s = tFixState(t);
      return [r[0] - 36, s.y + (s.size * 1.2) / 2];
    }
    const titleM5 = [384, now5Title()[1] + 26 * G.k * 0.6];
    const pausePtr = nowPt(G.card5, 32 + G.pauseBtn.x + G.pauseBtn.w - 9, 212);
    const fieldM = [384, G.card5[1] + (170 + 48) * G.k];
    const savePtr = nowPt(G.card5, 32 + G.saveBtn.x + G.saveBtn.w - 9, 312);
    const panelM5 = [384, G.card5[1] + (142 + 26) * G.k];
    if (t < 10.88) return titleM5;
    if (t < 11.18) { const u = prog(t, 10.88, 11.18); return arc(titleM5, pausePtr, travel(u), 0.1, ease.inOutCubic(u)); }
    if (t < 11.24) return pausePtr;
    if (t < 11.55) { const u = prog(t, 11.24, 11.55); return arc(pausePtr, fieldM, travel(u), -0.12, ease.inOutCubic(u)); }
    if (t < 11.72) return fieldM;
    if (t < 11.98) { const u = prog(t, 11.72, 11.98); return arc(fieldM, savePtr, travel(u), 0.12, ease.inOutCubic(u)); }
    if (t < 12.08) return savePtr;
    if (t < 12.5) { const u = prog(t, 12.08, 12.5); return arc(savePtr, panelM5, travel(u), -0.32, ease.inOutCubic(u)); /* swings out past the card edge, never over the sentence */ }
    if (t < 13.7) return panelM5;
    // Scene 6
    const bend0 = G.bendPts[0];
    if (t < 14.1) { const u = prog(t, 13.7, 14.1); return arc(panelM5, bend0, ease.inOutCubic(u), -0.1, u); }
    if (t < 14.45) return bendPoint(ease.inOutSine(prog(t, 14.1, 14.45)));
    const bend1 = G.bendPts[120];
    if (t < 14.62) { const u = prog(t, 14.45, 14.62); return arc(bend1, G.logoDot, travel(u), 0.35, ease.inOutCubic(u)); }
    if (t < 17.0) return G.logoDot;
    return lp(G.logoDot, G.center, ease.inOutCubic(prog(t, 17.0, T)));
  }
  function bendPoint(u) {
    const f = clamp(u) * 120, i = Math.min(119, Math.floor(f));
    return lp(G.bendPts[i], G.bendPts[i + 1], f - i);
  }
  function dotPress(t) {
    // brief squeeze on each press, shared with the pressed button
    const presses = [5.0, 11.2, 12.0];
    for (const p of presses) if (t >= p && t < p + 0.2) return Math.sin(Math.PI * prog(t, p, p + 0.2));
    return 0;
  }

  /* ====================================================================
     RENDER — pure function of t
     ==================================================================== */
  function render(tRaw) {
    let t = ((tRaw % T) + T) % T;
    if (tRaw >= T) t = tRaw === T ? T : t; // seek(T) shows the last frame (== frame 0)

    /* ---------- Scene 1 ---------- */
    const dim = 1 - 0.55 * driftP(t);
    const out1 = ease.inCubic(prog(t, 2.75, 3.0));
    G.envs.forEach((v, i) => {
      const o = E.env[i];
      const a = drifted(v.a, t);
      const pin = ease.outCubic(prog(t, 0.05 + i * 0.07, 0.4 + i * 0.07));
      place(o.label, a[0] + 24, a[1] - 22 + (1 - pin) * 14);
      vis(o.label, pin * dim * (1 - out1));
      if (!o.chip) return;
      const ta = G.hops[i];
      const pc = spring(prog(t, ta - 0.02, ta + 0.42), 0.78);
      const fc = ease.outCubic(prog(t, ta - 0.02, ta + 0.16));
      const cx0 = a[0] + 24, cy0 = a[1] + 32;
      // Converge (scene 2): chips sink toward centre and under the card, except "Refactor auth".
      const conv = ease.inOutCubic(prog(t, 2.82, 3.2));
      const chipX = lerp(cx0, 960 - o.chip.__w / 2, i === 0 ? 0 : conv);
      const chipY = lerp(cy0, 520, i === 0 ? 0 : conv);
      const s = lerp(0.9, 1, pc) * (i === 0 ? 1 : 1 - 0.3 * conv);
      const chipO = fc * lerp(1, 0.75, driftP(t)) * (i === 0 ? 1 - ease.outCubic(prog(t, 2.85, 3.1)) : 1 - ease.inCubic(prog(t, 2.95, 3.2)));
      place(o.chip, chipX + (1 - s) * o.chip.__w * 0.5, chipY - (1 - pc) * 10, s);
      vis(o.chip, chipO);
      z(o.chip, i === 0 ? 11 : 19); // below the blooming card
      z(o.chip.__text.el, i === 0 ? 32 : 19);
      if (i === 0) return; // tRefactor is driven below
      o.chip.__text.set(chipX + 17 * s + (1 - s) * o.chip.__w * 0.5, chipY + 11 * s - (1 - pc) * 10, 26 * s, 600, C.inkSoft, chipO);
    });
    E.question.render(t, 1.9, 2.7, 0.07);

    /* ---------- tRefactor: chip → Now title → row 1 title ---------- */
    {
      const v = G.envs[0], a = drifted(v.a, t);
      const ta = G.hops[0];
      const pc = spring(prog(t, ta - 0.02, ta + 0.42), 0.78);
      const fc = ease.outCubic(prog(t, ta - 0.02, ta + 0.16));
      const s = lerp(0.9, 1, pc);
      const chip = [a[0] + 24 + 17 * s + (1 - s) * E.env[0].chip.__w * 0.5, a[1] + 32 + 11 * s - (1 - pc) * 10];
      const tt = title2();
      const row = G.rowTitle(0);
      let x, y, size, w, col, o;
      if (t < 2.85) {
        [x, y] = chip; size = 26 * s; w = 600; col = C.inkSoft; o = fc * lerp(1, 0.75, driftP(t));
      } else if (t < 5.5) {
        const p = spring(prog(t, 2.88, 3.5), 0.85);
        const brighten = ease.inOutCubic(prog(t, 2.85, 3.2));
        x = lerp(chip[0], tt[0], p); y = lerp(chip[1], tt[1], p);
        size = lerp(26, 26 * G.k, p); w = lerp(600, 700, p);
        col = mix(C.inkSoft, C.ink, brighten); o = lerp(0.75, 1, brighten);
      } else {
        const p = p23(t);
        x = lerp(tt[0], row[0], p); y = lerp(tt[1], row[1], p);
        size = lerp(26 * G.k, 16 * G.mk, p); w = lerp(700, 600, p); col = C.ink; o = 1;
      }
      // Leaves with the rest of scene 3 under the dark mask.
      if (t >= 8.47) o = 0;
      E.tRefactor.set(x, y, size, w, col, o);
    }

    /* ---------- Scene 2 + 3 shell ---------- */
    {
      const r = shell2Rect(t);
      const on = t >= 3.0 && t < 8.47;
      const radius = t < 5.5 ? 16 * G.k : lerp(16 * G.k, 14 * G.mk, p23(t));
      box(E.shell2, r, radius);
      vis(E.shell2, on ? 1 : 0);
      // Scene 2 contents
      const out = 1 - ease.outCubic(prog(t, 5.45, 5.6));
      place(E.g2, G.card2[0], G.card2[1], G.k);
      const show = (e, a, d = 0.25, dy = 6) => {
        const p = ease.outCubic(prog(t, a, a + d));
        e.style.translate = `0 ${((1 - p) * dy).toFixed(2)}px`;
        vis(e, p * out);
      };
      E.g2.style.visibility = t >= 3.2 && t < 5.65 ? "visible" : "hidden";
      show(E.g2eyebrow, 3.3);
      show(E.g2meta, 3.4);
      show(E.g2menu, 3.42, 0.25, 0);
      // Resume panel opens beside the dot on beat 4.0
      {
        const p = spring(prog(t, 3.92, 4.3), 0.82);
        box(E.g2panel, [32, 142 + 43 * (1 - p), 656, 86 * p], 12);
        vis(E.g2panel, ease.outCubic(prog(t, 3.92, 4.02)) * out);
      }
      show(E.g2plabel, 3.98, 0.22);
      show(E.g2ptext, 4.06, 0.25);
      {
        const p = spring(prog(t, 4.5, 4.9), 0.72);
        const press = t >= 5.0 && t < 5.2 ? Math.sin(Math.PI * prog(t, 5.0, 5.2)) : 0;
        E.g2resume.style.transform = `scale(${(lerp(0.92, 1, p) - press * 0.03).toFixed(4)})`;
        E.g2resume.style.transformOrigin = "50% 50%";
        E.g2resume.style.background = mix(C.accent, C.accentStrong, press);
        E.g2resume.style.opacity = (ease.outCubic(prog(t, 4.5, 4.62)) * out).toFixed(4);
        const p2 = ease.outCubic(prog(t, 4.58, 4.8));
        E.g2choose.style.opacity = (p2 * out).toFixed(4);
        E.g2choose.style.transform = `translateY(${((1 - p2) * 6).toFixed(2)}px)`;
        E.g2btns.style.opacity = 1;
      }
      show(E.g2div, 4.62, 0.3, 0);
      show(E.g2notes, 4.66);
    }

    /* ---------- Scene 3: My work ---------- */
    {
      const inP = (a) => ease.outCubic(prog(t, a, a + 0.32));
      const gone = t >= 8.47 ? 0 : 1;
      E.mw.style.visibility = t >= 5.6 && t < 8.47 ? "visible" : "hidden";
      const frame = [
        [E.mwH1, 5.7], [E.mwSub, 5.76], [E.mwSearch, 5.82], [E.mwNew, 5.86], [E.railH, 5.8],
        [E.projs[0], 5.84], [E.projs[1], 5.88], [E.projs[2], 5.92], [E.projs[3], 5.96],
        [E.listH, 5.86], [E.seg, 5.9],
      ];
      frame.forEach(([e, a]) => {
        const p = inP(a);
        e.style.translate = `0 ${((1 - p) * 12).toFixed(2)}px`;
        vis(e, p * gone);
      });
      E.rows.forEach((o, i) => {
        // Row 1 is the card itself; rows 2–4 unfold downward from under it.
        const a = i === 0 ? 5.86 : 5.94 + (i - 1) * 0.07;
        const p = spring(prog(t, a, a + 0.5), 0.86);
        const f = ease.outCubic(prog(t, a, a + 0.25));
        const dy = i === 0 ? (1 - f) * 6 : -(1 - p) * 34 * i;
        const lifted = i === 3 && t >= 8.0; // handed to shell A
        [o.title, ...o.parts].forEach((e) => {
          e.style.translate = `0 ${dy.toFixed(2)}px`;
          vis(e, f * gone * (lifted ? 0 : 1));
        });
        if (i === 0) vis(o.title, 0); // drawn by tRefactor
        if (o.edge) vis(o.edge, ease.outCubic(prog(t, 5.95, 6.2)) * gone);
        // Selected tint where the dot stops (the row a click would open in the reader).
        vis(o.bg, i === 3 && !lifted ? ease.outCubic(prog(t, 7.1, 7.3)) * gone : 0);
      });
    }
    E.cap3.render(t, 6.0, 7.68, 0.06);

    /* ---------- Scene 4: dark ---------- */
    {
      const { c: d0, R } = maskDark(t);
      box(E.darkMask, [d0[0] - R, d0[1] - R, 2 * R, 2 * R], R);
      vis(E.darkMask, t >= 8.0 && t < 10.75 ? 1 : 0);
      const on = t >= 8.4 && t < 10.75;
      const pinPill = (i) => spring(prog(t, 8.42 + i * 0.05, 8.86 + i * 0.05), 0.75);
      E.pills.forEach((e, i) => {
        const p = pinPill(i), c = G.pills[i].c, w = G.pills[i].w;
        const s = lerp(0.86, 1, p);
        place(e, c[0] - (w * s) / 2, c[1] - 36 * s, s);
        vis(e, on ? ease.outCubic(prog(t, 8.42 + i * 0.05, 8.6 + i * 0.05)) : 0);
      });
      E.lines.style.visibility = on ? "visible" : "hidden";
      E.base.forEach((l, i) => {
        const p = ease.inOutCubic(prog(t, 8.45 + i * 0.05, 8.75 + i * 0.05));
        l.setAttribute("stroke-dasharray", `${G.segLen[i]} ${G.segLen[i]}`);
        l.setAttribute("stroke-dashoffset", ((1 - p) * G.segLen[i]).toFixed(2));
      });
      // Lit length derives directly from the dot's position (same motion value).
      const dp = dotAt(t);
      const lit = [0, 0, 0];
      if (t >= 8.62) lit[0] = t >= 8.88 ? 1 : clamp((G.hubL[0] - dp[0]) / G.segLen[0]);
      if (t >= 8.95) lit[1] = t >= 9.4 ? 1 : clamp((dp[0] - G.hubR[0]) / G.segLen[1]);
      if (t >= 9.5) lit[2] = t >= 9.95 ? 1 : clamp((dp[1] - G.hubB[1]) / G.segLen[2]);
      E.lit.forEach((l, i) => {
        l.setAttribute("stroke-dasharray", `${G.segLen[i]} ${G.segLen[i]}`);
        l.setAttribute("stroke-dashoffset", ((1 - lit[i]) * G.segLen[i]).toFixed(2));
        l.style.visibility = on && lit[i] > 0 ? "visible" : "hidden";
      });
      const toolIn = [8.72, 9.24, 9.72];
      E.tools.forEach((d, i) => {
        const p = spring(prog(t, toolIn[i], toolIn[i] + 0.4), 0.8);
        place(d.el, d.x, d.at[1] - 14 + (1 - p) * 10);
        vis(d.el, on ? ease.outCubic(prog(t, toolIn[i], toolIn[i] + 0.18)) : 0);
      });
      {
        const p = ease.outCubic(prog(t, 8.9, 9.15));
        place(E.overlapResult, G.overlapResultX, G.portY + 52 + (1 - p) * 8);
        vis(E.overlapResult, on ? p : 0);
      }
      E.cap4.render(t, 8.5, 10.25, 0.06);
      if (t >= 10.75) E.cap4.el.style.visibility = "hidden";
    }

    /* ---------- Shell A (row 4 → hub card → Now card) ---------- */
    {
      const on = t >= 8.0 && t < 13.95;
      const r = shellARect(t);
      const radius = t < 10.3 ? lerp(0, 16, pA1(t)) : lerp(16, 16 * G.k, pA2(t));
      const out6 = ease.inCubic(prog(t, 13.6, 13.9));
      const o = on ? 1 - out6 : 0;
      const dark = maskDark(t), light = maskLight(t);
      // which copy is on top, and the circle that clips it
      const darkPhase = t < 10.3;
      const top = darkPhase ? "D" : "L";
      const circ = darkPhase ? dark : light;
      E.shellL.style.background = darkPhase ? C.accentTint : C.card;
      E.shellL.style.borderColor = C.line;
      E.shellL.style.boxShadow = darkPhase ? "none" : "";
      box(E.shellL, r, radius);
      box(E.shellD, r, radius);
      const clipFor = (ox, oy, sc = 1) => `circle(${(circ.R / sc).toFixed(2)}px at ${((circ.c[0] - ox) / sc).toFixed(2)}px ${((circ.c[1] - oy) / sc).toFixed(2)}px)`;
      const fullD = darkPhase && t >= 8.36, fullL = !darkPhase && t >= 10.62;
      // bottom copy
      const bottomShell = top === "D" ? E.shellL : E.shellD;
      const topShell = top === "D" ? E.shellD : E.shellL;
      z(bottomShell, 80);
      z(topShell, 81);
      bottomShell.style.clipPath = "none";
      topShell.style.clipPath = clipFor(r[0], r[1]);
      vis(bottomShell, o * (fullD || fullL ? 0 : 1));
      vis(topShell, o * (t >= 8.0 ? 1 : 0));
      if (fullD || fullL) topShell.style.clipPath = "none";
      const st = tFixState(t);
      const sc = st.size / 40;
      E.tFixL.set(st.x, st.y, st.size, st.w, C.ink, 0);
      E.tFixD.set(st.x, st.y, st.size, st.w, C.dInk, 0);
      const bottomText = top === "D" ? E.tFixL : E.tFixD;
      const topText = top === "D" ? E.tFixD : E.tFixL;
      z(bottomText.el, 83);
      z(topText.el, 84);
      bottomText.el.style.clipPath = "none";
      topText.el.style.clipPath = fullD || fullL ? "none" : clipFor(st.x, st.y, sc);
      vis(bottomText.el, o * (fullD || fullL ? 0 : 1));
      vis(topText.el, o);
      // Row secondary text rides along for the first instant, then hands over to hub content.
      const rr = rowRect(3);
      const dx = r[0] - rr[0], dy = r[1] - rr[1];
      const rowOut = 1 - ease.outCubic(prog(t, 8.04, 8.18));
      const rowOn = t >= 8.0 && t < 8.2 ? rowOut : 0;
      const mwp = (rx, ry) => G.mwPt(rx, ry);
      const scanP = mwp(370, 161 + 312 + 42.4), projP = mwp(370, 161 + 312 + 67.4), whenP = mwp(1180 - G.aWhenW, 161 + 312 + 18);
      place(E.aScan, scanP[0] + dx, scanP[1] + dy, G.mk); vis(E.aScan, rowOn);
      place(E.aProj, projP[0] + dx, projP[1] + dy, G.mk); vis(E.aProj, rowOn);
      place(E.aWhen, whenP[0] + dx + (r[2] - rr[2]), whenP[1] + dy, G.mk); vis(E.aWhen, rowOn);
      // Hub contents
      const hubIn = ease.outCubic(prog(t, 8.42, 8.66));
      const hubOut = 1 - ease.outCubic(prog(t, 10.3, 10.42));
      const hubO = t < 10.3 ? hubIn : hubOut;
      const hy = (1 - hubIn) * 6;
      place(E.hubIcon, 708, 424 + hy); vis(E.hubIcon, hubO);
      place(E.hubName, 764, 431 + hy); vis(E.hubName, hubO);
      box(E.hubDiv, [708, 488, 504 * hubIn, 1]); vis(E.hubDiv, hubO);
      const swap = ease.inOutCubic(prog(t, 10.1, 10.24));
      place(E.hubMetaOld, 708, 552 + hy); vis(E.hubMetaOld, hubO * (1 - swap));
      place(E.hubMetaNew, 708, 552 + hy); vis(E.hubMetaNew, hubO * swap);
      E.hubMetaNew.style.color = mix(C.dMuted, C.mint, Math.sin(Math.PI * prog(t, 10.1, 10.9)));
      place(E.hubLeft, 708, 586 + hy); vis(E.hubLeft, hubO);
    }
    {
      const { c: L, R } = maskLight(t);
      box(E.lightMask, [L[0] - R, L[1] - R, 2 * R, 2 * R], R);
      vis(E.lightMask, t >= 10.3 && t < 13.95 ? 1 : 0);
    }

    /* ---------- Scene 5: Now card states ---------- */
    {
      const on = t >= 10.6 && t < 13.95;
      const out6 = ease.inCubic(prog(t, 13.6, 13.9));
      const o5 = on ? 1 - out6 : 0;
      E.g5.style.visibility = on ? "visible" : "hidden";
      place(E.g5, G.card5[0], G.card5[1], G.k);
      const fin = (a, d = 0.22) => ease.outCubic(prog(t, a, a + d));
      const fout = (a, d = 0.1) => 1 - ease.outCubic(prog(t, a, a + d));
      // Eyebrows: separate in/out windows, no overlap.
      const eIn = [fin(10.66), fin(11.35, 0.12), fin(12.18, 0.14)];
      const eOut = [fout(11.25, 0.08), fout(12.05, 0.08), 1];
      E.e5.forEach((e, i) => vis(e, eIn[i] * eOut[i] * o5));
      vis(E.g5meta, fin(10.7) * o5);
      vis(E.g5menu, fin(10.72) * o5);
      // working state
      const wO = fin(10.72) * fout(11.25, 0.1) * o5;
      vis(E.g5cue, wO);
      vis(E.g5wbtns, wO);
      const pressP = t >= 11.2 && t < 11.4 ? Math.sin(Math.PI * prog(t, 11.2, 11.4)) : 0;
      E.g5pause.style.background = mix(C.card, C.surface, pressP);
      E.g5pause.style.transform = `scale(${(1 - 0.03 * pressP).toFixed(4)})`;
      E.g5pause.style.transformOrigin = "50% 50%";
      // pausing state
      const pIn = fin(11.35, 0.2);
      const pOut = fout(12.05, 0.1);
      E.g5flabel.style.translate = `0 ${((1 - pIn) * 6).toFixed(2)}px`;
      vis(E.g5flabel, pIn * pOut * o5);
      E.g5pbtns.style.translate = `0 ${((1 - pIn) * 6).toFixed(2)}px`;
      vis(E.g5pbtns, pIn * pOut * o5);
      const sPress = t >= 12.0 && t < 12.2 ? Math.sin(Math.PI * prog(t, 12.0, 12.2)) : 0;
      E.g5save.style.background = mix(C.accent, C.accentStrong, sPress);
      E.g5save.style.transform = `scale(${(1 - 0.03 * sPress).toFixed(4)})`;
      E.g5save.style.transformOrigin = "50% 50%";
      vis(E.placeholder, pIn * (t < 11.45 ? 1 : 0) * o5);
      // welcome state
      const lIn = fin(12.42, 0.16);
      E.g5plabel.style.translate = `0 ${((1 - lIn) * -5).toFixed(2)}px`;
      vis(E.g5plabel, lIn * o5);
      const rb = spring(prog(t, 12.3, 12.7), 0.74);
      E.g5rbtns.style.transform = `translate(32px,252px)`;
      E.g5resume.style.transform = `scale(${lerp(0.92, 1, rb).toFixed(4)})`;
      E.g5resume.style.transformOrigin = "50% 50%";
      E.g5choose.style.transform = `translateY(${((1 - fin(12.36, 0.24)) * 6).toFixed(2)}px)`;
      vis(E.g5rbtns, fin(12.3, 0.12) * o5);
      // notes follow the card height
      const h = card5H(t);
      place(E.g5div, 32, h - 70);
      place(E.g5notes, 32, h - 54);
      vis(E.g5div, fin(10.75) * o5);
      vis(E.g5notes, fin(10.78) * o5);

      // --- the key move: field contracts onto the sentence, panel blooms from it ---
      const c0 = G.card5;
      const fieldRect = [c0[0] + 32 * G.k, c0[1] + 170 * G.k, 656 * G.k, 96 * G.k];
      const panelRect = [c0[0] + 32 * G.k, c0[1] + 142 * G.k, 656 * G.k, 86 * G.k];
      const typedPos = [c0[0] + 47 * G.k, c0[1] + 183 * G.k];
      const restPos = [c0[0] + 50 * G.k, c0[1] + 186 * G.k];
      const noteSizeA = 16 * G.k, noteSizeB = 17 * G.k;
      const sentence = [typedPos[0] - 10, typedPos[1] - 6, (G.noteW * noteSizeA) / 40 + 20, noteSizeA * 1.2 + 12];
      // field
      const fieldIn = fin(11.38, 0.2);
      const contract = ease.inOutCubic(prog(t, 12.04, 12.24));
      const fr = lerpRect(fieldRect, sentence, contract);
      box(E.field, fr, lerp(10 * G.k, 8, contract));
      vis(E.field, t < 12.24 ? fieldIn * o5 : 0);
      const ringPad = 2 * G.k + 3;
      box(E.ring, [fr[0] - ringPad, fr[1] - ringPad, fr[2] + 2 * ringPad, fr[3] + 2 * ringPad], lerp(10 * G.k + ringPad, 8 + ringPad, contract));
      vis(E.ring, t < 12.24 ? fin(11.4, 0.12) * (1 - contract) * o5 : 0);
      // panel
      const bloom = spring(prog(t, 12.16, 12.62), 0.74);
      const pr = lerpRect(sentence, panelRect, bloom);
      box(E.panel5, pr, lerp(8, 12 * G.k, bloom));
      vis(E.panel5, t >= 12.16 ? ease.outCubic(prog(t, 12.16, 12.26)) * o5 : 0);
      // sentence: typed, then lifted and set as the resume cue
      const nChars = Math.round(ease.inOutSine(prog(t, 11.42, 11.92)) * G.noteFull.length);
      E.noteText.textContent = G.noteFull.slice(0, nChars);
      const caretOn = t >= 11.38 && t < 12.02 && (t < 11.95 || Math.floor((t - 11.38) / 0.5) % 2 === 0);
      E.caret.style.visibility = caretOn ? "visible" : "hidden";
      const settle = spring(prog(t, 12.06, 12.56), 0.78);
      const lift = Math.sin(Math.PI * clamp(prog(t, 12.04, 12.5))) * 16;
      const nx = lerp(typedPos[0], restPos[0], settle);
      const ny = lerp(typedPos[1], restPos[1], settle) - lift;
      const ns = lerp(noteSizeA, noteSizeB, settle);
      place(E.note, nx, ny, ns / 40);
      E.note.style.lineHeight = "1.2";
      E.note.style.fontWeight = 400;
      E.note.style.color = C.ink;
      vis(E.note, t >= 11.4 ? o5 : 0);
      // toast
      const tp = spring(prog(t, 12.24, 12.64), 0.8);
      const tw = 360 * G.k;
      place(E.toast, W - 48 - tw, H - 48 - 46 * G.k + (1 - tp) * 24, G.k);
      vis(E.toast, ease.outCubic(prog(t, 12.24, 12.4)) * o5);
      E.cap5.render(t, 12.6, 13.55, 0.06);
    }

    /* ---------- Scene 6: brand ---------- */
    {
      const trailP = ease.inOutSine(prog(t, 14.1, 14.45));
      E.trail.setAttribute("stroke-dashoffset", ((1 - trailP) * G.bendLen).toFixed(3));
      const trailO = t >= 14.1 && t < 14.9 ? 1 - ease.outCubic(prog(t, 14.78, 14.9)) : 0;
      E.trailSvg.style.visibility = trailO > 0 ? "visible" : "hidden";
      E.trailSvg.style.opacity = trailO.toFixed(4);
      const loopOut = ease.inCubic(prog(t, 16.85, 17.1));
      // Logo: opacity only. Never scaled, moved or redrawn.
      vis(E.logo, ease.inOutCubic(prog(t, 14.5, 14.8)) * (1 - loopOut));
      const textOut = ease.inCubic(prog(t, 16.8, 17.02));
      E.tag.render(t, 15.0, 99, 0.07);
      E.name.render(t, 15.25, 99, 0.05);
      E.sub.render(t, 15.32, 99, 0.025);
      E.chips.render(t, 15.4, 99, 0.02);
      [E.tag, E.name, E.sub, E.chips].forEach((c) => { c.el.style.opacity = (1 - textOut).toFixed(4); if (t < 14.9) c.el.style.visibility = "hidden"; });
      const cp = spring(prog(t, 15.6, 16.05), 0.78);
      const s = lerp(0.94, 1, cp);
      place(E.cta, 960 - (G.ctaW * s) / 2, 790 + (1 - cp) * 10, s);
      vis(E.cta, ease.outCubic(prog(t, 15.6, 15.75)) * (1 - textOut));
    }

    /* ---------- the dot ---------- */
    {
      const p = dotAt(t);
      const press = dotPress(t);
      const r = 10 * (1 - 0.18 * press);
      E.dot.style.transform = `translate(${(p[0] - r).toFixed(2)}px,${(p[1] - r).toFixed(2)}px)`;
      E.dot.style.width = E.dot.style.height = `${(2 * r).toFixed(2)}px`;
      z(E.dot, t >= 8.0 && t < 10.3 ? 75 : 100);
    }
    return t;
  }

  /* ====================================================================
     boot
     ==================================================================== */
  const api = { duration: T, fps: FPS, frames: Math.round(T * FPS), beats: BEATS, ready: false, seek: (t) => render(t), dotAt: (t) => dotAt(t), geometry: G };
  window.promo = api;

  async function boot() {
    await Promise.all(["400 40px Figtree", "500 40px Figtree", "600 40px Figtree", "700 40px Figtree"].map((f) => document.fonts.load(f)));
    await document.fonts.ready;
    build();
    const q = new URLSearchParams(location.search);
    render(parseFloat(q.get("t") || "0") || 0);
    api.ready = true;
    document.dispatchEvent(new CustomEvent("promo:ready"));
  }
  boot();
})();
