"""fact_compare — Compare two facts and highlight differences."""

import sqlite3
import sys
from pathlib import Path
from difflib import unified_diff

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from i18n import t


def fact_compare(fact_id_a: str, fact_id_b: str) -> str:
    """Compare two facts and highlight differences in content, type, tags, and metadata."""
    if not fact_id_a or not fact_id_b:
        return t("fact_compare.missing_ids")

    if fact_id_a == fact_id_b:
        return t("fact_compare.same_id")

    db = open_db()
    try:
        # Fetch both facts
        fact_a = db.execute(
            "SELECT * FROM facts WHERE id = ?",
            (fact_id_a,)
        ).fetchone()

        fact_b = db.execute(
            "SELECT * FROM facts WHERE id = ?",
            (fact_id_b,)
        ).fetchone()

        if not fact_a:
            return t("fact_compare.not_found", id=fact_id_a[:8])
        if not fact_b:
            return t("fact_compare.not_found", id=fact_id_b[:8])

        lines = [t("fact_compare.header", id_a=fact_id_a[:8], id_b=fact_id_b[:8])]

        # Content comparison with diff
        lines.append("\n" + t("fact_compare.content_section"))
        if fact_a['content'] == fact_b['content']:
            lines.append(t("fact_compare.content_identical"))
        else:
            # Generate unified diff
            content_a = fact_a['content'].splitlines(keepends=True)
            content_b = fact_b['content'].splitlines(keepends=True)
            diff = list(unified_diff(
                content_a, content_b,
                fromfile=f"fact_{fact_id_a[:8]}",
                tofile=f"fact_{fact_id_b[:8]}",
                lineterm=""
            ))
            if diff:
                lines.append("```diff")
                # Limit diff output
                for line in diff[:30]:
                    lines.append(line.rstrip())
                if len(diff) > 30:
                    lines.append(f"... ({len(diff) - 30} more lines)")
                lines.append("```")
            else:
                lines.append(t("fact_compare.content_different_no_diff"))

        # Metadata comparison table
        lines.append("\n" + t("fact_compare.metadata_section"))

        fields = [
            ('Type', 'type'),
            ('Project', 'project'),
            ('Domain', 'domain'),
            ('Tags', 'tags'),
            ('Source File', 'source_file'),
        ]

        for label, field in fields:
            val_a = fact_a[field] or "(none)"
            val_b = fact_b[field] or "(none)"
            marker = "✓" if val_a == val_b else "≠"
            lines.append(f"  {marker} {label}: '{val_a}' | '{val_b}'")

        # Heat score comparison
        heat_a = fact_a['heat_score'] or 1.0
        heat_b = fact_b['heat_score'] or 1.0
        heat_marker = "✓" if abs(heat_a - heat_b) < 0.01 else "≠"
        lines.append(f"  {heat_marker} Heat Score: {heat_a:.2f} | {heat_b:.2f}")

        # Timestamp comparison
        ts_a = fact_a['timestamp'][:19] if fact_a['timestamp'] else "(none)"
        ts_b = fact_b['timestamp'][:19] if fact_b['timestamp'] else "(none)"
        ts_marker = "✓" if ts_a == ts_b else "≠"
        lines.append(f"  {ts_marker} Created: {ts_a} | {ts_b}")

        # Linked facts comparison
        try:
            links_a = db.execute("""
                SELECT target_id FROM fact_links WHERE source_id = ?
                UNION
                SELECT source_id FROM fact_links WHERE target_id = ?
            """, (fact_id_a, fact_id_a)).fetchall()
            links_b = db.execute("""
                SELECT target_id FROM fact_links WHERE source_id = ?
                UNION
                SELECT source_id FROM fact_links WHERE target_id = ?
            """, (fact_id_b, fact_id_b)).fetchall()

            set_a = set(r[0] for r in links_a)
            set_b = set(r[0] for r in links_b)

            common = set_a & set_b
            only_a = set_a - set_b
            only_b = set_b - set_a

            lines.append("\n" + t("fact_compare.links_section"))
            lines.append(f"  Common linked facts: {len(common)}")
            if only_a:
                lines.append(f"  Only in A: {len(only_a)} ({', '.join(id[:8] for id in list(only_a)[:3])}{'...' if len(only_a) > 3 else ''})")
            if only_b:
                lines.append(f"  Only in B: {len(only_b)} ({', '.join(id[:8] for id in list(only_b)[:3])}{'...' if len(only_b) > 3 else ''})")
        except sqlite3.OperationalError:
            pass  # fact_links table may not exist

        # Summary
        lines.append("\n" + t("fact_compare.summary"))
        differences = 0
        if fact_a['content'] != fact_b['content']:
            differences += 1
        if fact_a['type'] != fact_b['type']:
            differences += 1
        if fact_a['tags'] != fact_b['tags']:
            differences += 1
        if fact_a['domain'] != fact_b['domain']:
            differences += 1

        if differences == 0:
            lines.append(t("fact_compare.identical"))
        else:
            lines.append(t("fact_compare.differences_count", count=differences))

        return "\n".join(lines)

    finally:
        db.close()
