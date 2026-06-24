"""Obsidian integration - Export facts to Obsidian markdown format.

Configuration (config.yaml):
    integrations:
      obsidian:
        enabled: true
        vault_path: "~/Obsidian/Memoriq"
        auto_export: true  # export on every memory_write
        export_on_demand: true  # allow manual export via CLI
        link_format: "wiki"  # wiki [[links]] or markdown [text](path)
        frontmatter:
          - tags
          - created
          - project
"""

import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .bus import get_bus

try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))
    from db import get_db_path, open_db_fast
    HAS_DB = True
except ImportError:
    HAS_DB = False

logger = logging.getLogger("memoriq.integrations.obsidian")


def _load_config() -> dict:
    """Load Obsidian integration config."""
    import yaml

    config_path = Path.home() / ".memoriq" / "config.yaml"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("integrations", {}).get("obsidian", {})
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = name.strip(".- ")
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


def _make_wiki_link(target: str, display: str = None) -> str:
    """Create a wiki-style link [[target|display]]."""
    if display and display != target:
        return f"[[{target}|{display}]]"
    return f"[[{target}]]"


def _make_markdown_link(target: str, display: str) -> str:
    """Create a markdown-style link [display](target)."""
    # Convert target to relative path
    target_path = target.replace(" ", "%20")
    return f"[{display}]({target_path})"


def _make_link(target: str, display: str = None, link_format: str = "wiki") -> str:
    """Create a link based on the configured format."""
    if link_format == "wiki":
        return _make_wiki_link(target, display)
    return _make_markdown_link(target, display)


def _format_frontmatter(fact: dict, fields: list[str]) -> str:
    """Format frontmatter for a fact."""
    lines = ["---"]

    if "id" in fields:
        lines.append(f"id: {fact.get('id', '')}")
    if "type" in fields:
        lines.append(f"type: {fact.get('type', 'fact')}")
    if "project" in fields:
        lines.append(f"project: {fact.get('project', 'unknown')}")
    if "tags" in fields and fact.get('tags'):
        tags = fact['tags']
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        lines.append(f"tags: {json.dumps(tags)}")
    if "created" in fields:
        ts = fact.get('timestamp', '')
        if ts:
            # Parse ISO format
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                lines.append(f"created: {dt.strftime('%Y-%m-%dT%H:%M:%S')}")
            except Exception:
                lines.append(f"created: {ts}")
    if "domain" in fields and fact.get('domain'):
        lines.append(f"domain: {fact.get('domain')}")
    if "source_file" in fields and fact.get('source_file'):
        lines.append(f"source_file: {fact.get('source_file')}")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _get_fact_title(content: str, max_len: int = 50) -> str:
    """Extract a title from fact content."""
    # Use first line, truncated
    first_line = content.split("\n")[0].strip()
    if len(first_line) > max_len:
        return first_line[:max_len].rstrip() + "..."
    return first_line


def _get_vault_path(config: dict) -> Path:
    """Get and validate the Obsidian vault path."""
    vault_path = config.get("vault_path", "~/Obsidian/Memoriq")
    vault_path = Path(vault_path).expanduser()

    # Ensure it's within home directory for security
    home = Path.home()
    try:
        vault_path.resolve().relative_to(home.resolve())
    except ValueError:
        logger.error(f"Obsidian vault path must be within home directory: {vault_path}")
        # Fall back to default
        vault_path = home / "Obsidian" / "Memoriq"

    return vault_path


def _ensure_vault_structure(vault_path: Path) -> None:
    """Create the vault directory structure if it doesn't exist."""
    dirs = ["facts", "projects", "tags", "daily"]
    for d in dirs:
        (vault_path / d).mkdir(parents=True, exist_ok=True)


def export_fact(fact_id: str, vault_path: Path = None, config: dict = None) -> Path:
    """Export a single fact to Obsidian markdown.

    Args:
        fact_id: The UUID of the fact to export
        vault_path: Optional override for vault path
        config: Optional config override

    Returns:
        Path to the exported file
    """
    if not HAS_DB:
        raise RuntimeError("Database access not available")

    if config is None:
        config = _load_config()

    if vault_path is None:
        vault_path = _get_vault_path(config)

    _ensure_vault_structure(vault_path)

    # Fetch fact from database
    db = open_db_fast()
    try:
        row = db.execute(
            "SELECT * FROM facts WHERE id = ?", (fact_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Fact not found: {fact_id}")

        fact = dict(row)
    finally:
        db.close()

    # Build markdown content
    link_format = config.get("link_format", "wiki")
    frontmatter_fields = config.get("frontmatter", ["id", "type", "project", "tags", "created"])

    content_lines = []

    # Frontmatter
    content_lines.append(_format_frontmatter(fact, frontmatter_fields))

    # Title
    title = _get_fact_title(fact['content'])
    content_lines.append(f"# {title}")
    content_lines.append("")

    # Body
    content_lines.append(fact['content'])
    content_lines.append("")

    # Related facts (from fact_links table)
    db = open_db_fast()
    try:
        related = db.execute("""
            SELECT f.id, f.content, fl.score
            FROM fact_links fl
            JOIN facts f ON fl.target_id = f.id
            WHERE fl.source_id = ?
            ORDER BY fl.score DESC
            LIMIT 10
        """, (fact_id,)).fetchall()

        if related:
            content_lines.append("## Related Facts")
            for rel in related:
                rel_title = _get_fact_title(rel['content'], 40)
                rel_link = _make_link(
                    f"facts/{rel['id']}",
                    rel_title,
                    link_format
                )
                content_lines.append(f"- {rel_link}")
            content_lines.append("")

        # Backlinks (facts that link to this one)
        backlinks = db.execute("""
            SELECT f.id, f.content
            FROM fact_links fl
            JOIN facts f ON fl.source_id = f.id
            WHERE fl.target_id = ?
            LIMIT 10
        """, (fact_id,)).fetchall()

        if backlinks:
            content_lines.append("## Backlinks")
            for back in backlinks:
                back_title = _get_fact_title(back['content'], 40)
                back_link = _make_link(
                    f"facts/{back['id']}",
                    back_title,
                    link_format
                )
                content_lines.append(f"- {back_link}")
            content_lines.append("")
    finally:
        db.close()

    # Write file
    fact_filename = _sanitize_filename(f"{fact_id}") + ".md"
    fact_path = vault_path / "facts" / fact_filename

    with open(fact_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content_lines))

    logger.info(f"Exported fact to {fact_path}")
    return fact_path


def export_all(vault_path: Path = None, config: dict = None) -> dict:
    """Export all facts to Obsidian vault.

    Returns:
        Dict with export statistics
    """
    if not HAS_DB:
        raise RuntimeError("Database access not available")

    if config is None:
        config = _load_config()

    if vault_path is None:
        vault_path = _get_vault_path(config)

    _ensure_vault_structure(vault_path)

    # Get all facts
    db = open_db_fast()
    try:
        facts = db.execute(
            "SELECT id FROM facts ORDER BY timestamp DESC"
        ).fetchall()
    finally:
        db.close()

    exported = 0
    failed = 0

    for fact in facts:
        try:
            export_fact(fact['id'], vault_path, config)
            exported += 1
        except Exception as e:
            logger.error(f"Failed to export fact {fact['id']}: {e}")
            failed += 1

    # Generate index file
    _generate_index(vault_path, config)

    # Generate project overviews
    _generate_project_pages(vault_path, config)

    # Generate tag pages
    _generate_tag_pages(vault_path, config)

    return {
        "exported": exported,
        "failed": failed,
        "vault_path": str(vault_path),
    }


def _generate_index(vault_path: Path, config: dict) -> None:
    """Generate the main index file."""
    if not HAS_DB:
        return

    link_format = config.get("link_format", "wiki")

    db = open_db_fast()
    try:
        # Get stats
        total_facts = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        projects = db.execute(
            "SELECT DISTINCT project FROM facts WHERE project IS NOT NULL"
        ).fetchall()
        tags = db.execute(
            "SELECT DISTINCT tags FROM facts WHERE tags IS NOT NULL"
        ).fetchall()

        # Collect all unique tags
        all_tags = set()
        for t in tags:
            if t['tags']:
                all_tags.update(t['tags'].split(","))
        all_tags = {t.strip() for t in all_tags if t.strip()}

        # Recent facts
        recent = db.execute(
            "SELECT id, content, timestamp FROM facts ORDER BY timestamp DESC LIMIT 20"
        ).fetchall()
    finally:
        db.close()

    lines = [
        "---",
        "title: Memoriq Index",
        "auto-generated: true",
        "---",
        "",
        "# Memoriq Memory Index",
        "",
        f"**Total Facts:** {total_facts}",
        "",
        "## Projects",
        "",
    ]

    for proj in projects:
        proj_name = proj['project']
        proj_link = _make_link(f"projects/{proj_name}", proj_name, link_format)
        lines.append(f"- {proj_link}")

    lines.extend(["", "## Tags", ""])

    for tag in sorted(all_tags):
        tag_link = _make_link(f"tags/{tag}", f"#{tag}", link_format)
        lines.append(f"- {tag_link}")

    lines.extend(["", "## Recent Facts", ""])

    for fact in recent:
        fact_title = _get_fact_title(fact['content'], 50)
        fact_link = _make_link(f"facts/{fact['id']}", fact_title, link_format)
        ts = fact['timestamp'][:10] if fact['timestamp'] else ""
        lines.append(f"- {fact_link} ({ts})")

    index_path = vault_path / "index.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Generated index at {index_path}")


def _generate_project_pages(vault_path: Path, config: dict) -> None:
    """Generate overview pages for each project."""
    if not HAS_DB:
        return

    link_format = config.get("link_format", "wiki")

    db = open_db_fast()
    try:
        projects = db.execute(
            "SELECT DISTINCT project FROM facts WHERE project IS NOT NULL"
        ).fetchall()

        for proj in projects:
            proj_name = proj['project']
            facts = db.execute(
                "SELECT id, content, timestamp, tags FROM facts WHERE project = ? ORDER BY timestamp DESC",
                (proj_name,)
            ).fetchall()

            lines = [
                "---",
                f"title: {proj_name}",
                "auto-generated: true",
                "---",
                "",
                f"# Project: {proj_name}",
                "",
                f"**Facts:** {len(facts)}",
                "",
                "## Facts",
                "",
            ]

            for fact in facts:
                fact_title = _get_fact_title(fact['content'], 50)
                fact_link = _make_link(f"facts/{fact['id']}", fact_title, link_format)
                ts = fact['timestamp'][:10] if fact['timestamp'] else ""
                lines.append(f"- {fact_link} ({ts})")

            proj_filename = _sanitize_filename(proj_name) + ".md"
            proj_path = vault_path / "projects" / proj_filename

            with open(proj_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.debug(f"Generated project page for {proj_name}")
    finally:
        db.close()


def _generate_tag_pages(vault_path: Path, config: dict) -> None:
    """Generate index pages for each tag."""
    if not HAS_DB:
        return

    link_format = config.get("link_format", "wiki")

    db = open_db_fast()
    try:
        # Get all tags
        rows = db.execute(
            "SELECT DISTINCT tags FROM facts WHERE tags IS NOT NULL"
        ).fetchall()

        # Collect tag -> facts mapping
        tag_facts: dict[str, list] = {}
        for row in rows:
            if row['tags']:
                for tag in row['tags'].split(","):
                    tag = tag.strip()
                    if tag:
                        if tag not in tag_facts:
                            tag_facts[tag] = []
                        # Get facts with this tag
                        facts = db.execute(
                            "SELECT id, content FROM facts WHERE tags LIKE ?",
                            (f"%{tag}%",)
                        ).fetchall()
                        tag_facts[tag] = facts

        for tag, facts in tag_facts.items():
            lines = [
                "---",
                f"title: #{tag}",
                "auto-generated: true",
                "---",
                "",
                f"# Tag: #{tag}",
                "",
                f"**Facts:** {len(facts)}",
                "",
                "## Facts",
                "",
            ]

            for fact in facts:
                fact_title = _get_fact_title(fact['content'], 50)
                fact_link = _make_link(f"facts/{fact['id']}", fact_title, link_format)
                lines.append(f"- {fact_link}")

            tag_filename = _sanitize_filename(tag) + ".md"
            tag_path = vault_path / "tags" / tag_filename

            with open(tag_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.debug(f"Generated tag page for #{tag}")
    finally:
        db.close()


def _handle_event(event: str, payload: dict[str, Any]) -> None:
    """Handle events from the integration bus."""
    config = _load_config()

    if not config.get("enabled"):
        return

    if not config.get("auto_export", True):
        return

    if event not in ("memory_write", "memory_update"):
        return

    # Get fact ID from payload
    data = payload.get("data", {})
    fact_id = data.get("fact_id")

    if not fact_id:
        return

    try:
        export_fact(fact_id, config=config)
    except Exception as e:
        logger.error(f"Failed to auto-export fact: {e}")


def init() -> None:
    """Initialize the Obsidian integration."""
    bus = get_bus()
    bus.register("obsidian", _handle_event)
    logger.info("Obsidian integration registered")


def cli_export(vault_path: str = None, fact_id: str = None) -> dict:
    """CLI entry point for manual export.

    Args:
        vault_path: Optional override for vault path
        fact_id: Optional single fact to export (exports all if None)

    Returns:
        Export result dict
    """
    config = _load_config()

    if vault_path:
        config["vault_path"] = vault_path

    if fact_id:
        path = export_fact(fact_id, config=config)
        return {"exported": 1, "path": str(path)}
    else:
        return export_all(config=config)
