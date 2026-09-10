#!/usr/bin/env bash
# One-shot GitHub issue hygiene after v0.3.10.
# Idempotent: comments include a marker and are skipped if already present.
set -euo pipefail

REPO="${GH_REPO:-uniskela/adhd-hub}"
MARKER="<!-- post-v0.3.10-issue-hygiene -->"

has_marker() {
  local number="$1"
  gh api "repos/${REPO}/issues/${number}/comments" --paginate \
    --jq '.[].body' | grep -Fq "${MARKER}"
}

ensure_comment() {
  local number="$1"
  local body="$2"
  if has_marker "${number}"; then
    echo "skip comment on #${number} (marker present)"
    return 0
  fi
  gh issue comment "${number}" --repo "${REPO}" --body "${body}"
}

echo "Creating label adhd-hub if missing..."
if gh label list --repo "${REPO}" --json name --jq '.[].name' | grep -Fxq "adhd-hub"; then
  echo "label adhd-hub already exists"
else
  gh label create "adhd-hub" --repo "${REPO}" \
    --description "Forge inbox / Hub tracking (required for inbox import)" \
    --color "0D9488"
fi

echo "Labeling [ADHD] trackers #15–#20..."
for n in 15 16 17 18 19 20; do
  gh issue edit "${n}" --repo "${REPO}" --add-label "adhd-hub"
done

ensure_comment 16 "$(cat <<EOF
${MARKER}
Shipped in Wave 1 ([PR #22](https://github.com/uniskela/adhd-hub/pull/22)) as of **v0.3.6**. Scope is complete: reminders, soft-archive, focus mode, quick capture, and pause/resume (\`resume_step\`).

Later releases through **v0.3.10** (wiki #32, runtime #33, backup KDF #35) did not reopen this work. Adding \`adhd-hub\` so the tracker is visible to the forge inbox protocol.
EOF
)"

if [[ "$(gh issue view 16 --repo "${REPO}" --json state --jq .state)" == "OPEN" ]]; then
  gh issue close 16 --repo "${REPO}" --reason completed
else
  echo "skip close #16 (already closed)"
fi

ensure_comment 17 "$(cat <<EOF
${MARKER}
Confirming close: Wave 2 shipped in [PR #24](https://github.com/uniskela/adhd-hub/pull/24) / **v0.3.6** (MCP pause/dismiss/reminders/overview, \`register_workspace\`, OpenClaw memory). Adding \`adhd-hub\` for forge inbox visibility.
EOF
)"

ensure_comment 18 "$(cat <<EOF
${MARKER}
Confirming close: Wave 3 shipped in [PR #26](https://github.com/uniskela/adhd-hub/pull/26) / **v0.3.7** (durable sessions, PWA, encrypted backups, ops/doctor). Encrypted-backup KDF follow-up landed in [PR #35](https://github.com/uniskela/adhd-hub/pull/35) / **v0.3.10**. Adding \`adhd-hub\` for forge inbox visibility.
EOF
)"

ensure_comment 19 "$(cat <<EOF
${MARKER}
Confirming close: Wave 4 shipped in [PR #28](https://github.com/uniskela/adhd-hub/pull/28) / **v0.3.8** (UI modules, facades, a11y). Follow-ups: [PR #30](https://github.com/uniskela/adhd-hub/pull/30) / v0.3.9 (module state), [PR #33](https://github.com/uniskela/adhd-hub/pull/33) / **v0.3.10** (offline-safe Docker, splitter guard, PWA \`/ui/\`). Adding \`adhd-hub\` for forge inbox visibility.
EOF
)"

ensure_comment 15 "$(cat <<EOF
${MARKER}
Post-**v0.3.10** status (tag [v0.3.10](https://github.com/uniskela/adhd-hub/releases/tag/v0.3.10)):

- Wave 1 (#16 / [PR #22](https://github.com/uniskela/adhd-hub/pull/22)) — shipped **v0.3.6** (closing)
- Wave 2 (#17 / [PR #24](https://github.com/uniskela/adhd-hub/pull/24)) — shipped **v0.3.6**
- Wave 3 (#18 / [PR #26](https://github.com/uniskela/adhd-hub/pull/26)) — shipped **v0.3.7**; backup KDF in [PR #35](https://github.com/uniskela/adhd-hub/pull/35) / v0.3.10
- Wave 4 (#19 / [PR #28](https://github.com/uniskela/adhd-hub/pull/28)) — shipped **v0.3.8**; runtime follow-ups #30 / #33
- Wiki Jekyll → Zensical — [PR #32](https://github.com/uniskela/adhd-hub/pull/32) / v0.3.10
- Wave 5 (#20) — still opt-in future work; do not start early

Leaving this parent open while #20 remains. Added \`adhd-hub\` for forge inbox visibility (title-only never imports).
EOF
)"

ensure_comment 20 "$(cat <<EOF
${MARKER}
Still future / opt-in. Waves 1–4 and **v0.3.10** follow-ups ([PR #32](https://github.com/uniskela/adhd-hub/pull/32) wiki, [PR #33](https://github.com/uniskela/adhd-hub/pull/33) runtime, [PR #35](https://github.com/uniskela/adhd-hub/pull/35) backup KDF) do not cover Slack/Discord nudges, calendar blocks, or a public leaderboard.

Leaving open. Do not start this wave early. Added \`adhd-hub\` so it can participate in the forge inbox protocol.
EOF
)"

echo "Done. Current [ADHD] issues:"
gh issue list --repo "${REPO}" --state all --limit 20 --json number,title,state,labels \
  --jq '.[] | select(.title | startswith("[ADHD]")) | {number, title, state, labels: [.labels[].name]}'
