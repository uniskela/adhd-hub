from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from adhd_hub.backlog.models import Advisory, DraftPlan, RecommendationItem, ScanSummary

if TYPE_CHECKING:
    from sqlite3 import Connection

    from adhd_hub.store import Store


def init_schema(conn: Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS backlog_scans (
            id TEXT PRIMARY KEY,
            target_key TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            summary TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS backlog_scan_active
            ON backlog_scans(target_key) WHERE status IN ('queued', 'running');
        CREATE INDEX IF NOT EXISTS backlog_scan_target
            ON backlog_scans(target_key, created_at);
        CREATE TABLE IF NOT EXISTS backlog_scan_items (
            scan_id TEXT NOT NULL REFERENCES backlog_scans(id) ON DELETE CASCADE,
            issue_number INTEGER NOT NULL,
            kind TEXT NOT NULL,
            cluster_key INTEGER,
            source_revision TEXT NOT NULL,
            item TEXT NOT NULL,
            PRIMARY KEY (scan_id, issue_number)
        );
        CREATE TABLE IF NOT EXISTS backlog_ai_recommendations (
            cache_key TEXT PRIMARY KEY,
            recommendation TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS backlog_plans (
            id TEXT PRIMARY KEY,
            scan_id TEXT NOT NULL REFERENCES backlog_scans(id),
            version INTEGER NOT NULL,
            draft TEXT NOT NULL
        );
    """)


class BacklogStorage:
    def __init__(self, store: Store):
        self.store = store

    def interrupt_scans(self):
        with self.store._conn() as conn:
            running = conn.execute(
                "SELECT summary FROM backlog_scans WHERE status IN ('queued', 'running')"
            ).fetchall()
            for row in running:
                scan = ScanSummary.model_validate_json(row["summary"])
                scan.status = "failed"
                scan.error_code = "interrupted"
                scan.finished_at = datetime.now(UTC)
                conn.execute(
                    "UPDATE backlog_scans SET status = ?, summary = ? WHERE id = ?",
                    (scan.status, scan.model_dump_json(), scan.scan_id),
                )
            # AI jobs run in the same process queue. Retain completed batches.
            conn.execute(
                """UPDATE backlog_scan_items SET item = json_set(item, '$.ai_status', 'interrupted')
                   WHERE json_extract(item, '$.ai_status') = 'queued'"""
            )

    def add_scan(self, scan: ScanSummary, target_key: str) -> bool:
        with self.store._conn() as conn:
            conn.execute(
                """DELETE FROM backlog_scans
                   WHERE created_at < ? AND status NOT IN ('queued', 'running')
                   AND NOT EXISTS (SELECT 1 FROM backlog_plans WHERE scan_id = backlog_scans.id)""",
                ((scan.created_at - timedelta(days=90)).isoformat(),),
            )
            conn.execute(
                "DELETE FROM backlog_ai_recommendations WHERE expires_at <= ?",
                (scan.created_at.isoformat(),),
            )
            result = conn.execute(
                "INSERT OR IGNORE INTO backlog_scans VALUES (?, ?, ?, ?, ?)",
                (
                    scan.scan_id,
                    target_key,
                    scan.status,
                    scan.created_at.isoformat(),
                    scan.model_dump_json(),
                ),
            )
            return result.rowcount == 1

    def scan(self, scan_id: str) -> ScanSummary | None:
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT summary FROM backlog_scans WHERE id = ?", (scan_id,)
            ).fetchone()
        return ScanSummary.model_validate_json(row["summary"]) if row else None

    def save_scan(
        self,
        scan: ScanSummary,
        items: tuple[RecommendationItem, ...] | list[RecommendationItem] = (),
    ):
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE backlog_scans SET status = ?, summary = ? WHERE id = ?",
                (scan.status, scan.model_dump_json(), scan.scan_id),
            )
            conn.executemany(
                "INSERT INTO backlog_scan_items VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        scan.scan_id,
                        item.issue.identity.number,
                        item.issue.kind,
                        item.deterministic.cluster_key,
                        item.issue.source_revision,
                        item.model_dump_json(),
                    )
                    for item in items
                ],
            )

    def items(
        self,
        scan_id: str,
        *,
        after: int = 0,
        limit: int = 1000,
        kind: str | None = None,
        cluster: int | None = None,
    ) -> list[RecommendationItem]:
        with self.store._conn() as conn:
            rows = conn.execute(
                """SELECT item FROM backlog_scan_items WHERE scan_id = ? AND issue_number > ?
                   AND (? IS NULL OR kind = ?) AND (? IS NULL OR cluster_key = ?)
                   ORDER BY issue_number LIMIT ?""",
                (scan_id, after, kind, kind, cluster, cluster, limit),
            ).fetchall()
        return [RecommendationItem.model_validate_json(row["item"]) for row in rows]

    def stale(self, scan_id: str) -> bool:
        with self.store._conn() as conn:
            if conn.execute(
                """SELECT 1 FROM backlog_scan_items WHERE scan_id = ?
                   AND json_extract(item, '$.ai_status') = 'stale_snapshot' LIMIT 1""",
                (scan_id,),
            ).fetchone():
                return True
            row = conn.execute(
                """SELECT 1 FROM backlog_scans old
                   JOIN backlog_scans new ON new.target_key = old.target_key
                        AND new.created_at > old.created_at
                        AND new.status IN ('completed', 'partial')
                   JOIN backlog_scan_items before ON before.scan_id = old.id
                   LEFT JOIN backlog_scan_items after ON after.scan_id = new.id
                        AND before.issue_number = after.issue_number
                   WHERE old.id = ? AND (
                       before.source_revision <> after.source_revision OR (
                           after.issue_number IS NULL AND new.status = 'completed'
                           AND NOT json_extract(new.summary, '$.truncated')
                           AND json_extract(new.summary, '$.selector') = json_extract(old.summary, '$.selector')
                           AND json_extract(new.summary, '$.include_closed') = json_extract(old.summary, '$.include_closed')
                       )
                   ) LIMIT 1""",
                (scan_id,),
            ).fetchone()
        return row is not None

    def cached(self, key: str) -> Advisory | None:
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT recommendation FROM backlog_ai_recommendations WHERE cache_key = ? AND expires_at > ?",
                (key, datetime.now(UTC).isoformat()),
            ).fetchone()
        return Advisory.model_validate_json(row["recommendation"]) if row else None

    def save_advice(self, scan_id: str, results: list[tuple[RecommendationItem, str | None]]):
        expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        with self.store._conn() as conn:
            for item, key in results:
                if key and item.ai:
                    conn.execute(
                        "INSERT OR REPLACE INTO backlog_ai_recommendations VALUES (?, ?, ?)",
                        (key, item.ai.model_dump_json(), expires),
                    )
                conn.execute(
                    "UPDATE backlog_scan_items SET item = ? WHERE scan_id = ? AND issue_number = ?",
                    (item.model_dump_json(), scan_id, item.issue.identity.number),
                )

    def plan(self, plan_id: str) -> DraftPlan | None:
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT draft FROM backlog_plans WHERE id = ?", (plan_id,)
            ).fetchone()
        return DraftPlan.model_validate_json(row["draft"]) if row else None

    def add_plan(self, plan: DraftPlan):
        with self.store._conn() as conn:
            conn.execute(
                "INSERT INTO backlog_plans VALUES (?, ?, ?, ?)",
                (plan.plan_id, plan.scan_id, plan.version, plan.model_dump_json()),
            )

    def update_plan(self, plan: DraftPlan, expected_version: int) -> bool:
        with self.store._conn() as conn:
            result = conn.execute(
                "UPDATE backlog_plans SET version = ?, draft = ? WHERE id = ? AND version = ?",
                (plan.version, plan.model_dump_json(), plan.plan_id, expected_version),
            )
            return result.rowcount == 1
