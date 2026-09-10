import { state, preferences, prefersReducedMotion, $, setMsg, escapeHtml } from './state.js';

export function renderRewards() {
    const enabled = $("rewards-enabled").checked;
    $("rewards-panel").hidden = !enabled;
    $("rewards-off").hidden = enabled;
    $("daily-goal").disabled = !enabled;
    if (!enabled || !state.overviewCache) return;
    const total = state.overviewCache.done || 0;
    const today = state.overviewCache.done_today || 0;
    const goal = Number($("daily-goal").value);
    $("goal-count").textContent = `${today} / ${goal}`;
    $("daily-progress").max = goal;
    $("daily-progress").value = Math.min(today, goal);
    $("rewards-title").textContent = today >= goal ? "A little win, well earned." : "Small steps add up.";
    $("rewards-caption").textContent = today >= goal ? "You’ve met your goal. It’s okay to leave it here." : "Your progress stays with you. Breaks don’t reset it.";
    const rewards = state.overviewCache.rewards;
    if (!rewards) return;
    $("reward-level").textContent = `Level ${rewards.level} · ${rewards.xp} XP · ${total} finished`;
    $("rank-name").textContent = rewards.rank.name;
    $("rank-next").textContent = rewards.next_rank
      ? `${rewards.next_rank.remaining} more finished steps to ${rewards.next_rank.name}. Whenever you’re ready.`
      : "You’ve reached Trailblazer. Every little step still counts.";
    $("rank-progress").max = rewards.next_rank ? rewards.next_rank.threshold - rewards.rank.threshold : 1;
    $("rank-progress").value = rewards.next_rank ? total - rewards.rank.threshold : 1;
    $("rank-progress").setAttribute("aria-valuetext", rewards.next_rank ? `${rewards.next_rank.remaining} steps to ${rewards.next_rank.name}` : "Highest rank reached");
    const earned = rewards.badges.filter((badge) => badge.earned);
    $("badge-count").textContent = `${earned.length} of ${rewards.badges.length} earned`;
    $("badges").innerHTML = rewards.badges.map((badge, index) => `
      <li class="badge ${badge.earned ? "earned" : ""}">
        ${badgeIcon(index)}<strong>${escapeHtml(badge.name)}</strong>
        <span class="hint">${badge.threshold} finished ${badge.threshold === 1 ? "step" : "steps"}</span>
        <span class="badge-state">${badge.earned ? "Earned ✓" : `${badge.threshold - total} to go · no deadline`}</span>
      </li>`).join("");
  }
export function badgeIcon(index) {
    const paths = [
      '<path d="m9 16 5 5 10-11"/>',
      '<path d="M9 23v-6m7 6V9m7 14V5"/>',
      '<path d="M16 26V14M16 18C7 18 6 10 7 7c8 0 9 6 9 11Zm0-3c8 0 10-6 9-10-6 0-9 4-9 10Z"/>',
      '<path d="M16 27V11m0 9L7 12m9 3 9-8"/><circle cx="7" cy="9" r="3"/><circle cx="25" cy="5" r="3"/>',
      '<path d="m16 4 4 8 9 1-7 6 2 9-8-4-8 4 2-9-7-6 9-1Z"/>',
      '<path d="m6 11 5 5 5-10 5 10 5-5-3 15H9Z"/>',
    ];
    return `<svg class="badge-symbol" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[index % paths.length]}</svg>`;
  }
export function openSharePreview() {
    const rewards = state.overviewCache?.rewards;
    if (!rewards || !$("rewards-enabled").checked) return;
    const version = ++state.shareVersion;
    state.shareFile = null;
    $("btn-native-share").hidden = true;
    $("share-msg").textContent = "";
    const earned = rewards.badges.filter((badge) => badge.earned);
    const text = `My Progress Hub: ${rewards.rank.name} · Level ${rewards.level} · ${rewards.xp} XP · ${rewards.completed} finished steps.\n${earned.length ? "Milestones: " + earned.map((badge) => badge.name).join(", ") + "." : "A fresh start. One step at a time."}\nSmall steps. Your pace.\n${state.repoUrl}`;
    $("share-text").value = text;
    const canvas = $("share-card");
    canvas.setAttribute("aria-label", text);
    const ctx = canvas.getContext("2d");
    if (!ctx) { setMsg("Your browser cannot create a progress card."); return; }
    ctx.fillStyle = "#F7F5EF"; ctx.fillRect(0, 0, 1200, 720);
    ctx.fillStyle = "#E4F0E9"; ctx.fillRect(0, 0, 1200, 18);
    ctx.fillStyle = "#176B60"; ctx.beginPath(); ctx.roundRect(64, 58, 64, 64, 18); ctx.fill();
    ctx.strokeStyle = "#F7F5EF"; ctx.lineWidth = 7; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(82, 102); ctx.lineTo(91, 102); ctx.quadraticCurveTo(104, 102, 104, 89); ctx.lineTo(104, 79); ctx.stroke();
    ctx.fillStyle = "#EFC978"; ctx.beginPath(); ctx.arc(83, 81, 5, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = "#203832"; ctx.font = "bold 30px system-ui, sans-serif"; ctx.fillText("Progress Hub", 148, 101);
    ctx.fillStyle = "#5B6F66"; ctx.font = "20px system-ui, sans-serif"; ctx.fillText("MY HUB’S LITTLE WINS", 64, 188);
    ctx.fillStyle = "#203832"; ctx.font = "bold 76px system-ui, sans-serif"; ctx.fillText(rewards.rank.name, 60, 279);
    ctx.fillStyle = "#176B60"; ctx.font = "32px system-ui, sans-serif";
    ctx.fillText(`Level ${rewards.level}   ·   ${rewards.xp} XP   ·   ${rewards.completed} finished steps`, 64, 343, 1070);
    ctx.fillStyle = "#D4DDD5"; ctx.fillRect(64, 385, 1072, 2);
    ctx.fillStyle = "#5B6F66"; ctx.font = "20px system-ui, sans-serif"; ctx.fillText("EARNED MILESTONES", 64, 437);
    if (!earned.length) { ctx.fillText("A fresh start. One step at a time.", 64, 490); }
    earned.forEach((badge, i) => {
      const x = 64 + (i % 3) * 358, y = 462 + Math.floor(i / 3) * 66;
      ctx.fillStyle = "#FAF0D6"; ctx.beginPath(); ctx.roundRect(x, y, 338, 52, 12); ctx.fill();
      ctx.fillStyle = "#715017"; ctx.font = "bold 21px system-ui, sans-serif"; ctx.fillText("✓ " + badge.name, x + 18, y + 33);
    });
    ctx.fillStyle = "#5B6F66"; ctx.font = "22px system-ui, sans-serif"; ctx.fillText("Small steps. Your pace.", 64, 658);
    ctx.textAlign = "right"; ctx.font = "21px system-ui, sans-serif";
    ctx.fillText(state.repoDisplayUrl, 1136, 658); ctx.textAlign = "left";
    $("share-dialog").showModal();
    canvas.toBlob((blob) => {
      if (!blob || version !== state.shareVersion || !$("share-dialog").open) return;
      state.shareFile = new File([blob], "progress-hub.png", { type: "image/png" });
      try { $("btn-native-share").hidden = !(navigator.share && navigator.canShare?.({ files: [state.shareFile] })); }
      catch (_) { $("btn-native-share").hidden = true; }
    }, "image/png");
  }
export function celebrate() {
    if (!$("rewards-enabled").checked) return;
    if (prefersReducedMotion()) return;
    clearTimeout(state.celebrationTimeout);
    $("celebration").textContent = "One step finished. Take a breath.";
    $("celebration").hidden = false;
    state.celebrationTimeout = setTimeout(() => { $("celebration").hidden = true; }, 4500);
  }
export function saveRewardPreferences() {
    preferences.setItem("adhd_hub_rewards", String($("rewards-enabled").checked));
    preferences.setItem("adhd_hub_daily_goal", $("daily-goal").value);
    if (!$("rewards-enabled").checked) {
      $("celebration").hidden = true;
      $("share-dialog").close();
    }
    renderRewards();
  }
export function renderStats(o) {
    $("stats").innerHTML = [
      ["Open", o.open],
      ["Finished this week", o.done_week],
    ]
      .map(
        ([k, v]) =>
          `<span class="stat"><strong>${escapeHtml(v)}</strong> ${escapeHtml(k)}</span>`
      )
      .join("");
    renderRewards();
    const series = o.added_vs_finished || [];
    const wrap = $("chart-wrap");
    const chart = $("chart");
    const summary = $("chart-summary");
    if (!series.length) {
      wrap.hidden = true;
      if (summary) summary.textContent = "";
      return;
    }
    wrap.hidden = false;
    const label = "Last 14 days: " + series.map((day) => `${day.date}: ${day.added} added, ${day.finished} finished`).join("; ");
    if (summary) {
      summary.textContent = label;
      chart.setAttribute("aria-hidden", "true");
      chart.removeAttribute("aria-label");
      chart.removeAttribute("role");
    } else {
      chart.setAttribute("role", "img");
      chart.setAttribute("aria-label", label);
      chart.removeAttribute("aria-hidden");
    }
    const max = Math.max(1, ...series.map((d) => (d.added || 0) + (d.finished || 0)));
    chart.innerHTML = series
      .map((d) => {
        const a = Math.round(((d.added || 0) / max) * 100);
        const f = Math.round(((d.finished || 0) / max) * 100);
        return `<div class="col" title="${escapeHtml(d.date)}: +${d.added || 0} / ✓${d.finished || 0}">
          <div class="bar add" style="height:${a}%"></div>
          <div class="bar done" style="height:${f}%"></div>
        </div>`;
      })
      .join("");
  }
