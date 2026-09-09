"""Versioned milestones derived from hub completions; no public leaderboard."""

RANKS = (
    ("seedling", "Seedling", 0),
    ("sprout", "Sprout", 5),
    ("grower", "Grower", 15),
    ("pathfinder", "Pathfinder", 30),
    ("wayfinder", "Wayfinder", 60),
    ("trailblazer", "Trailblazer", 100),
)
BADGES = (
    ("first-step", "First step", 1),
    ("finding-rhythm", "Finding rhythm", 5),
    ("taking-root", "Taking root", 15),
    ("branching-out", "Branching out", 30),
    ("making-space", "Making space", 60),
    ("hundred-wins", "100 little wins", 100),
)


def reward_summary(completed: int) -> dict:
    """Count finished threads once, using stable IDs for future integrations."""
    total = max(0, completed)
    current = max(i for i, (_, _, threshold) in enumerate(RANKS) if total >= threshold)
    rank_id, name, threshold = RANKS[current]
    next_rank = RANKS[current + 1] if current + 1 < len(RANKS) else None
    return {
        "version": 1,
        "scope": "hub",
        "completed": total,
        "xp": total * 10,
        "level": total // 5 + 1,
        "rank": {"id": rank_id, "name": name, "threshold": threshold},
        "next_rank": (
            {
                "id": next_rank[0],
                "name": next_rank[1],
                "threshold": next_rank[2],
                "remaining": next_rank[2] - total,
            }
            if next_rank
            else None
        ),
        "badges": [
            {"id": badge_id, "name": title, "threshold": count, "earned": total >= count}
            for badge_id, title, count in BADGES
        ],
    }
