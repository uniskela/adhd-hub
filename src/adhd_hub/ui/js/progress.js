import { state, preferences, prefersReducedMotion, $, setMsg, escapeHtml } from './state.js';

export function renderRewards() {
    const enabled = $("rewards-enabled").checked;
    $("rewards-panel").hidden = !enabled;
    $("rewards-off").hidden = enabled;
    $("daily-goal").disabled = !enabled;
    $("btn-share-progress").hidden = !enabled || !state.overviewCache?.rewards;
    if (!enabled || !state.overviewCache) return;
    const total = state.overviewCache.done || 0;
    const today = state.overviewCache.done_today || 0;
    const goal = Number($("daily-goal").value);
    const met = today >= goal;
    $("goal-count").textContent = `${today} of ${goal} small ${goal === 1 ? "win" : "wins"}.`;
    $("rewards-caption").textContent = met ? "A little win, well earned. It’s okay to leave it here." : "Missing it changes nothing.";
    const rewards = state.overviewCache.rewards;
    if (!rewards) return;
    $("reward-level").textContent = `Level ${rewards.level} · ${rewards.xp} XP · ${total} ${total === 1 ? "step" : "steps"} finished`;
    $("rank-name").textContent = rewards.rank.name;
    $("rank-next").textContent = rewards.next_rank
      ? `${rewards.next_rank.remaining} more finished ${rewards.next_rank.remaining === 1 ? "step" : "steps"} until ${rewards.next_rank.name}. Whenever you’re ready.`
      : "You’ve reached Trailblazer. Every little step still counts.";
    $("rank-progress").max = rewards.next_rank ? rewards.next_rank.threshold - rewards.rank.threshold : 1;
    $("rank-progress").value = rewards.next_rank ? total - rewards.rank.threshold : 1;
    $("rank-progress").setAttribute("aria-valuetext", rewards.next_rank ? `${rewards.next_rank.remaining} steps to ${rewards.next_rank.name}` : "Highest rank reached");
    const earned = rewards.badges.filter((badge) => badge.earned);
    $("badge-count").textContent = `${earned.length} of ${rewards.badges.length} earned`;
    $("badges").innerHTML = rewards.badges.map((badge) => `
      <li class="badge${badge.earned ? " earned" : ""}" title="${badge.threshold} finished ${badge.threshold === 1 ? "step" : "steps"}">
        <strong>${escapeHtml(badge.name)}</strong>
        <span class="badge-state">${badge.earned ? "Earned" : `Not yet · ${badge.threshold - total} to go`}</span>
      </li>`).join("");
  }
export function openSharePreview() {
    const rewards = state.overviewCache?.rewards;
    if (!rewards || !$("rewards-enabled").checked) return;
    const version = ++state.shareVersion;
    state.shareFile = null;
    $("btn-native-share").hidden = true;
    $("share-msg").textContent = "";
    const earned = rewards.badges.filter((badge) => badge.earned);
    const text = `My Progress Hub: ${rewards.rank.name} · Level ${rewards.level} · ${rewards.xp} XP · ${rewards.completed} finished ${rewards.completed === 1 ? "step" : "steps"}.\n${earned.length ? "Milestones: " + earned.map((badge) => badge.name).join(", ") + "." : "A fresh start. One step at a time."}\nSmall steps. Your pace.\n${state.repoUrl}`;
    $("share-text").value = text;
    const canvas = $("share-card");
    canvas.setAttribute("aria-label", text);
    const ctx = canvas.getContext("2d");
    if (!ctx) { setMsg("Your browser cannot create a progress card."); return; }
    const font = (size, weight = 400) => `${weight} ${size}px Figtree, system-ui, sans-serif`;
    ctx.fillStyle = "#F7F6F3"; ctx.fillRect(0, 0, 1200, 720);
    ctx.fillStyle = "#176B60"; ctx.beginPath(); ctx.roundRect(64, 58, 64, 64, 18); ctx.fill();
    ctx.strokeStyle = "#F7F5EF"; ctx.lineWidth = 7; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(82, 102); ctx.lineTo(91, 102); ctx.quadraticCurveTo(104, 102, 104, 89); ctx.lineTo(104, 79); ctx.stroke();
    ctx.fillStyle = "#EFC978"; ctx.beginPath(); ctx.arc(83, 81, 5, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = "#1F2328"; ctx.font = font(30, 700); ctx.fillText("Progress Hub", 148, 101);
    ctx.fillStyle = "#5F6570"; ctx.font = font(24, 500); ctx.fillText("My hub’s little wins", 64, 188);
    ctx.fillStyle = "#1F2328"; ctx.font = font(76, 700); ctx.fillText(rewards.rank.name, 60, 279);
    ctx.fillStyle = "#176B60"; ctx.font = font(32, 500);
    ctx.fillText(`Level ${rewards.level}   ·   ${rewards.xp} XP   ·   ${rewards.completed} finished ${rewards.completed === 1 ? "step" : "steps"}`, 64, 343, 1070);
    ctx.fillStyle = "#E6E4DE"; ctx.fillRect(64, 385, 1072, 2);
    ctx.fillStyle = "#5F6570"; ctx.font = font(24, 500); ctx.fillText("Earned milestones", 64, 437);
    if (!earned.length) { ctx.font = font(24); ctx.fillText("A fresh start. One step at a time.", 64, 490); }
    earned.forEach((badge, i) => {
      const x = 64 + (i % 3) * 358, y = 462 + Math.floor(i / 3) * 66;
      ctx.fillStyle = "#F7F0DD"; ctx.beginPath(); ctx.roundRect(x, y, 338, 52, 12); ctx.fill();
      ctx.fillStyle = "#765815"; ctx.font = font(21, 700); ctx.fillText("✓ " + badge.name, x + 18, y + 33);
    });
    ctx.fillStyle = "#5F6570"; ctx.font = font(22); ctx.fillText("Small steps. Your pace.", 64, 658);
    ctx.textAlign = "right"; ctx.font = font(21);
    ctx.fillText(state.repoDisplayUrl, 1136, 658); ctx.textAlign = "left";
    $("share-dialog").showModal();
    canvas.toBlob((blob) => {
      if (!blob || version !== state.shareVersion || !$("share-dialog").open) return;
      state.shareFile = new File([blob], "progress-hub.png", { type: "image/png" });
      try { $("btn-native-share").hidden = !(navigator.share && navigator.canShare?.({ files: [state.shareFile] })); }
      catch (_) { $("btn-native-share").hidden = true; }
    }, "image/png");
  }
/** Sticky key for the rewards Done cue — lives in toast-host (not a second fixed banner). */
export const CELEBRATION_TOAST_KEY = "celebration";

/** Hide legacy #celebration and dismiss the keyed celebration toast. */
export function dismissCelebration() {
    clearTimeout(state.celebrationTimeout);
    state.celebrationTimeout = undefined;
    const el = $("celebration");
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
    setMsg("", { key: CELEBRATION_TOAST_KEY, dismiss: true });
  }

/**
 * Quiet rewards acknowledgment after Done.
 * Uses the shared toast stack (gap + keys) so it never overlaps Done/Undo toasts
 * that sit in the same bottom band as the old fixed #celebration banner.
 */
export function celebrate() {
    if (!$("rewards-enabled").checked) return;
    if (prefersReducedMotion()) return;
    // Keep the legacy fixed banner hidden — toast-host owns this cue now.
    const el = $("celebration");
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
    clearTimeout(state.celebrationTimeout);
    state.celebrationTimeout = undefined;
    setMsg("One step finished. Take a breath.", {
      key: CELEBRATION_TOAST_KEY,
      variant: "success",
      duration: 4500,
    });
  }
export function saveRewardPreferences() {
    preferences.setItem("adhd_hub_rewards", String($("rewards-enabled").checked));
    preferences.setItem("adhd_hub_daily_goal", $("daily-goal").value);
    if (!$("rewards-enabled").checked) {
      dismissCelebration();
      $("share-dialog").close();
    }
    renderRewards();
  }
/** Calendar date ("YYYY-MM-DD") in the hub's time zone, read as a local date. */
function chartDate(value) {
    const [y, m, d] = String(value || "").split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

function chartDayName(value) {
    const date = chartDate(value);
    return date ? date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) : String(value || "");
  }

export function renderStats(o) {
    $("stats").textContent = `${o.open ?? 0} open now · ${o.done_week ?? 0} finished this week`;
    renderRewards();
    const series = o.added_vs_finished || [];
    const wrap = $("chart-wrap");
    const chart = $("chart");
    const summary = $("chart-summary");
    const totals = $("activity-totals");
    if (!series.length) {
      wrap.hidden = true;
      $("chart-empty").hidden = false;
      if (summary) summary.textContent = "";
      if (totals) totals.textContent = "";
      return;
    }
    wrap.hidden = false;
    $("chart-empty").hidden = true;
    const days = series.map((d) => ({
      date: d.date,
      name: chartDayName(d.date),
      label: chartDate(d.date)?.getDate() ?? "",
      added: Number(d.added) || 0,
      finished: Number(d.finished) || 0,
    }));
    const added = days.reduce((sum, d) => sum + d.added, 0);
    const finished = days.reduce((sum, d) => sum + d.finished, 0);
    const line = `${added} ${added === 1 ? "step" : "steps"} added, ${finished} finished`;
    if (totals) totals.textContent = line;
    if (summary) summary.textContent = `Bar chart of the last 14 days: ${line}. A table version follows.`;
    chart.setAttribute("role", "group");
    chart.setAttribute("aria-label", "Daily activity");
    chart.removeAttribute("aria-hidden");
    // Side-by-side bars share one scale, so the taller of the two sets the top.
    const max = Math.max(1, ...days.map((d) => Math.max(d.added, d.finished)));
    const bar = (kind, value) => value
      ? `<span class="bar ${kind}" style="height:${Math.round((value / max) * 100)}%"></span>`
      : `<span class="bar ${kind} is-zero"></span>`;
    chart.innerHTML = days
      .map((d) => `<div class="col" tabindex="0" role="img" aria-label="${escapeHtml(`${d.name}: ${d.added} added, ${d.finished} finished`)}" data-date="${escapeHtml(d.name)}" data-added="${d.added}" data-finished="${d.finished}">${bar("add", d.added)}${bar("done", d.finished)}</div>`)
      .join("");
    $("chart-days").innerHTML = days.map((d) => `<span>${escapeHtml(d.label)}</span>`).join("");
    $("chart-table-body").innerHTML = days
      .map((d) => `<tr><th scope="row">${escapeHtml(d.name)}</th><td>${d.added}</td><td>${d.finished}</td></tr>`)
      .join("");
    wireChartDayTips(chart);
  }

function wireChartDayTips(chart) {
    const tip = $("chart-day-tip");
    if (!chart || !tip) return;
    const hide = () => {
      tip.hidden = true;
      tip.textContent = "";
    };
    const showFor = (col) => {
      if (!col) return;
      const date = col.dataset.date || "";
      const added = Number(col.dataset.added || 0);
      const finished = Number(col.dataset.finished || 0);
      tip.innerHTML = `<strong>${escapeHtml(date)}</strong><br>${added} added · ${finished} finished`;
      tip.hidden = false;
      const wrap = chart.closest(".chart-wrap") || chart;
      const wrapRect = wrap.getBoundingClientRect();
      const colRect = col.getBoundingClientRect();
      const left = colRect.left - wrapRect.left + colRect.width / 2;
      const top = colRect.top - wrapRect.top;
      tip.style.left = `${Math.max(48, Math.min(left, wrapRect.width - 48))}px`;
      tip.style.top = `${Math.max(8, top)}px`;
    };
    chart.querySelectorAll(".col").forEach((col) => {
      col.addEventListener("mouseenter", () => showFor(col));
      col.addEventListener("mouseleave", hide);
      col.addEventListener("focus", () => showFor(col));
      col.addEventListener("blur", hide);
      col.addEventListener("click", () => showFor(col));
    });
  }
