"""memory_stats — Show memory usage statistics for Memoriq."""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from utils import get_active_session
from i18n import t


def memory_stats(scope: str = "project") -> str:
    """Show memory usage statistics (facts count by type, heat distribution, project sizes)."""
    session = get_active_session()
    project = session.get("project", "")

    db = open_db()
    try:
        lines = [t("memory_stats.header")]

        # Determine project filter
        if scope == "all":
            project_filter = None
        else:
            project_filter = project if project else None

        # Total facts count
        if project_filter:
            total = db.execute(
                "SELECT COUNT(*) FROM facts WHERE project = ?",
                (project_filter,)
            ).fetchone()[0]
            lines.append(t("memory_stats.total_project", project=project_filter, count=total))
        else:
            total = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            lines.append(t("memory_stats.total_all", count=total))

        if total == 0:
            lines.append(t("memory_stats.no_facts"))
            return "\n".join(lines)

        # Facts by type
        lines.append("\n" + t("memory_stats.by_type"))
        if project_filter:
            rows = db.execute("""
                SELECT type, COUNT(*) as cnt
                FROM facts
                WHERE project = ?
                GROUP BY type
                ORDER BY cnt DESC
            """, (project_filter,)).fetchall()
        else:
            rows = db.execute("""
                SELECT type, COUNT(*) as cnt
                FROM facts
                GROUP BY type
                ORDER BY cnt DESC
            """).fetchall()

        for row in rows:
            lines.append(f"  {row['type']}: {row['cnt']}")

        # Heat distribution
        lines.append("\n" + t("memory_stats.heat_distribution"))
        heat_query = """
            SELECT
                CASE
                    WHEN heat_score >= 0.7 THEN 'hot'
                    WHEN heat_score >= 0.3 THEN 'warm'
                    ELSE 'cold'
                END as heat_label,
                COUNT(*) as cnt,
                ROUND(AVG(heat_score), 2) as avg_heat
            FROM facts
        """
        if project_filter:
            heat_query += " WHERE project = ?"
            heat_rows = db.execute(heat_query + " GROUP BY heat_label ORDER BY cnt DESC",
                                   (project_filter,)).fetchall()
        else:
            heat_rows = db.execute(heat_query + " GROUP BY heat_label ORDER BY cnt DESC").fetchall()

        for row in heat_rows:
            lines.append(f"  {row['heat_label']}: {row['cnt']} (avg heat: {row['avg_heat']})")

        # Top projects (if scope is all)
        if scope == "all":
            lines.append("\n" + t("memory_stats.top_projects"))
            proj_rows = db.execute("""
                SELECT project, COUNT(*) as cnt
                FROM facts
                GROUP BY project
                ORDER BY cnt DESC
                LIMIT 10
            """).fetchall()
            for row in proj_rows:
                lines.append(f"  {row['project']}: {row['cnt']} facts")

        # Knowledge gaps
        try:
            if project_filter:
                gaps = db.execute("""
                    SELECT COUNT(*) FROM knowledge_gaps
                    WHERE project = ? AND resolved = 0
                """, (project_filter,)).fetchone()[0]
            else:
                gaps = db.execute("""
                    SELECT COUNT(*) FROM knowledge_gaps WHERE resolved = 0
                """).fetchone()[0]
            lines.append("\n" + t("memory_stats.knowledge_gaps", count=gaps))
        except sqlite3.OperationalError:
            pass  # Table may not exist

        # Linked facts statistics
        try:
            if project_filter:
                links = db.execute("""
                    SELECT COUNT(DISTINCT fl.source_id) as linked_facts,
                           COUNT(*) as total_links
                    FROM fact_links fl
                    JOIN facts f ON fl.source_id = f.id
                    WHERE f.project = ?
                """, (project_filter,)).fetchone()
            else:
                links = db.execute("""
                    SELECT COUNT(DISTINCT source_id) as linked_facts,
                           COUNT(*) as total_links
                    FROM fact_links
                """).fetchone()
            if links and links['total_links']:
                lines.append("\n" + t("memory_stats.linked_facts",
                    linked_facts=links['linked_facts'],
                    total_links=links['total_links']))
        except sqlite3.OperationalError:
            pass  # Table may not exist

        # Storage estimate (rough approximation)
        try:
            if project_filter:
                size_rows = db.execute("""
                    SELECT SUM(LENGTH(content)) as content_size,
                           COUNT(*) as fact_count
                    FROM facts
                    WHERE project = ?
                """, (project_filter,)).fetchone()
            else:
                size_rows = db.execute("""
                    SELECT SUM(LENGTH(content)) as content_size,
                           COUNT(*) as fact_count
                    FROM facts
                """).fetchone()

            if size_rows and size_rows['content_size']:
                kb = size_rows['content_size'] / 1024
                lines.append("\n" + t("memory_stats.storage",
                    kb=round(kb, 1),
                    avg_bytes=round(size_rows['content_size'] / size_rows['fact_count'])))
        except Exception:
            pass

        # Recent activity (last 7 days)
        try:
            from datetime import timedelta
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            if project_filter:
                recent = db.execute("""
                    SELECT COUNT(*) FROM facts
                    WHERE project = ? AND timestamp > ?
                """, (project_filter, week_ago)).fetchone()[0]
            else:
                recent = db.execute("""
                    SELECT COUNT(*) FROM facts WHERE timestamp > ?
                """, (week_ago,)).fetchone()[0]
            lines.append("\n" + t("memory_stats.recent_activity", count=recent))
        except Exception:
            pass

        return "\n".join(lines)

    finally:
        db.close()
