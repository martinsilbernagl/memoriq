"""memory_export — Export memory to JSON or Markdown."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from utils import get_active_session
from i18n import t


def memory_export(
    format: str = "json",
    scope: str = "project",
    output_path: str | None = None,
    include_metadata: bool = True
) -> str:
    """Export memory to JSON or Markdown.

    Args:
        format: "json" or "markdown"
        scope: "project" (default) or "all"
        output_path: Optional output file path
        include_metadata: Include heat scores, timestamps, tags

    Returns:
        Success message or file path
    """
    session = get_active_session()
    project = session.get("project", "unknown") if scope == "project" else None

    db = open_db()
    try:
        # Build project filter
        project_filter = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        # Fetch facts
        cursor = db.execute(
            f"SELECT * FROM facts {project_filter} ORDER BY timestamp DESC",
            params
        )
        facts = [dict(row) for row in cursor.fetchall()]

        if not facts:
            return t("memory_export.no_facts")

        # Generate export
        if format == "json":
            export_data = {
                "export_metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "format": "json",
                    "scope": scope,
                    "project": project or "all",
                    "fact_count": len(facts)
                },
                "facts": facts if include_metadata else [
                    {"content": f["content"], "type": f["type"]} for f in facts
                ]
            }
            content = json.dumps(export_data, indent=2, default=str)
            ext = "json"
        else:  # markdown
            lines = ["# Memoriq Memory Export", ""]
            lines.append(f"**Exported:** {datetime.now().isoformat()}")
            lines.append(f"**Project:** {project or 'all'}")
            lines.append(f"**Facts:** {len(facts)}")
            lines.append("")

            for fact in facts:
                if include_metadata:
                    lines.append(f"## {fact['type'].upper()}: {fact['content'][:50]}...")
                    lines.append("")
                    lines.append(f"**Project:** {fact['project']}")
                    lines.append(f"**Tags:** {fact.get('tags', 'none')}")
                    lines.append(f"**Heat:** {fact.get('heat_score', 0):.2f}")
                    lines.append(f"**Created:** {fact.get('timestamp', 'unknown')}")
                    if fact.get('source_file'):
                        lines.append(f"**Source:** {fact['source_file']}")
                    lines.append("")
                    lines.append("### Content")
                    lines.append("")
                lines.append(fact['content'])
                lines.append("")
                lines.append("---")
                lines.append("")

            content = "\n".join(lines)
            ext = "md"

        # Write to file or return content
        if output_path:
            path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            project_slug = project or "all"
            path = Path.home() / ".memoriq" / "exports" / f"memory-{project_slug}-{timestamp}.{ext}"
            path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")
        return t("memory_export.saved", path=str(path), count=len(facts))

    except sqlite3.Error as e:
        return t("memory_export.error", error=str(e))
    except Exception as e:
        return t("memory_export.error", error=str(e))
    finally:
        db.close()
