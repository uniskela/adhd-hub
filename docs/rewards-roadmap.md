# Rewards and future leaderboards

Implemented: a versioned, authenticated `overview.rewards` payload derived from actual hub completion totals; six ranks; six badges; a next-rank cue; and a local PNG/text export with preview. The `scope` is `hub`. No public leaderboard, profile, share endpoint, external publishing service, or new user identity model is introduced.

A future leaderboard should be an explicit opt-in service with a separate implementation review:

1. Add individual identities and decide whether scores belong to a person or a shared hub. Existing hub totals cannot identify who did the work.
2. Define eligibility for imports, retries, reopened tasks, deletion, and restored backups. Introduce an auditable completion/award ledger if permanent awards are desired.
3. Publish only a chosen display name and agreed public totals. Make preview, unpublish, data deletion, and private use first-class flows.
4. Define score verification and abuse handling. Current local PNG/text cards are self-reported snapshots, not signed proof.
5. Prefer optional small groups and milestones over a default global ranking. Avoid penalties for breaks and competitive interruptions in Now.

The current export is user-controlled and works without public hosting. Its content is a snapshot; later changes to hub records will not update a downloaded card.
