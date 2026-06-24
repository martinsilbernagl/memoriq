"""MCP tool: code_dependencies — file-level dependency graph visualization."""

import logging
import sqlite3

from db import open_db
from i18n import t
from utils import get_active_session
from tools.code_helpers import has_index, reindex_dirty

_log = logging.getLogger("memoriq.tools.code_dependencies")


def code_dependencies(file_path: str | None = None, project_name: str | None = None) -> str:
    """Get file-level dependency graph.

    Shows:
    - Direct imports (outgoing dependencies)
    - Files that import this file (incoming dependencies)
    - Dependency chain depth
    - Circular dependency detection

    Args:
        file_path: Optional file to focus on (shows deps for this file)
        project_name: Optional project override
    """
    db = None
    try:
        session = get_active_session()
        project = project_name or session.get("project")
        project_path = session.get("project_path")

        if not project:
            return t("code.no_project")

        db = open_db()

        # Auto-index check
        if not has_index(db, project):
            try:
                import tree_sitter_language_pack  # noqa: F401
            except ImportError:
                return t("code.no_treesitter")
            return t("code.not_indexed", project=project)

        # Reindex dirty files first
        reindex_dirty(db, project, project_path)

        lines = []
        lines.append(f"## Dependency Graph for `{project}`")
        lines.append("")

        if file_path:
            # Focus on specific file
            return _analyze_file_deps(db, project, file_path)
        else:
            # Project-wide dependency overview
            return _analyze_project_deps(db, project)

    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return t("code.db_busy")
        return t("code.db_error", error=str(e))
    except Exception as e:
        _log.error("code_dependencies failed: %s", e, exc_info=True)
        return t("code.generic_error", error=str(e))
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _analyze_file_deps(db: sqlite3.Connection, project: str, file_path: str) -> str:
    """Analyze dependencies for a specific file."""
    lines = []

    # Normalize file path
    file_path = file_path.replace("\\", "/")

    # Find the file
    file_row = db.execute("""
        SELECT id, file_path, language FROM code_files
        WHERE project = ? AND file_path LIKE ?
    """, (project, f"%{file_path}%")).fetchone()

    if not file_row:
        # Try exact match
        file_row = db.execute("""
            SELECT id, file_path, language FROM code_files
            WHERE project = ? AND file_path = ?
        """, (project, file_path)).fetchone()

    if not file_row:
        return f"File not found: `{file_path}`. Run code_index() first or check the path."

    file_id = file_row["id"]
    full_path = file_row["file_path"]
    language = file_row["language"]

    lines.append(f"### File: `{full_path}`")
    lines.append(f"**Language:** {language}")
    lines.append("")

    # Outgoing dependencies (imports from this file)
    outgoing = db.execute("""
        SELECT DISTINCT r.to_name, r.kind, r.line,
               cf.file_path as imported_from
        FROM code_references r
        LEFT JOIN code_symbols cs ON cs.qualified_name = r.to_name
        LEFT JOIN code_files cf ON cf.id = cs.file_id
        WHERE r.file_id = ? AND r.project = ? AND r.kind = 'import'
        ORDER BY r.to_name
        LIMIT 50
    """, (file_id, project)).fetchall()

    if outgoing:
        lines.append("**Outgoing Dependencies (Imports):**")
        for ref in outgoing:
            r = dict(ref)
            imported_file = r.get("imported_from")
            if imported_file:
                lines.append(f"  - `{r['to_name']}` — from `{imported_file}`")
            else:
                lines.append(f"  - `{r['to_name']}` — external/unknown")
    else:
        lines.append("**Outgoing Dependencies:** None (no imports detected)")
    lines.append("")

    # Incoming dependencies (files that import this file)
    incoming = db.execute("""
        SELECT DISTINCT cf.file_path, cf.language,
               r.from_symbol_id, s.qualified_name as from_symbol
        FROM code_references r
        JOIN code_files cf ON cf.id = r.file_id
        LEFT JOIN code_symbols s ON s.id = r.from_symbol_id
        WHERE r.to_name LIKE ? AND r.project = ? AND r.file_id != ?
        ORDER BY cf.file_path
        LIMIT 50
    """, (f"%{full_path.split('/')[-1].split('.')[0]}%", project, file_id)).fetchall()

    # Also check for imports that match symbols defined in this file
    symbols_in_file = db.execute("""
        SELECT qualified_name FROM code_symbols
        WHERE file_id = ? AND project = ?
    """, (file_id, project)).fetchall()

    symbol_names = [s["qualified_name"] for s in symbols_in_file]
    if symbol_names:
        # Find references to symbols from this file
        placeholders = ",".join("?" for _ in symbol_names)
        query = f"""
            SELECT DISTINCT cf.file_path, cf.language, r.to_name
            FROM code_references r
            JOIN code_files cf ON cf.id = r.file_id
            WHERE r.to_name IN ({placeholders}) AND r.project = ? AND r.file_id != ?
            ORDER BY cf.file_path
            LIMIT 50
        """
        symbol_refs = db.execute(query, (*symbol_names, project, file_id)).fetchall()
    else:
        symbol_refs = []

    all_incoming = list(incoming) + list(symbol_refs)
    seen = set()
    unique_incoming = []
    for ref in all_incoming:
        key = ref["file_path"]
        if key not in seen:
            seen.add(key)
            unique_incoming.append(ref)

    if unique_incoming:
        lines.append("**Incoming Dependencies (Imported By):**")
        for ref in unique_incoming[:20]:  # Limit to 20
            r = dict(ref)
            lines.append(f"  - `{r['file_path']}`")
        if len(unique_incoming) > 20:
            lines.append(f"  - ... and {len(unique_incoming) - 20} more")
    else:
        lines.append("**Incoming Dependencies:** None (not imported by other project files)")
    lines.append("")

    # Dependency stats
    lines.append("**Dependency Stats:**")
    lines.append(f"- Outgoing: {len(outgoing)}")
    lines.append(f"- Incoming: {len(unique_incoming)}")

    # Circular dependency check (simple 2-hop check)
    if outgoing and unique_incoming:
        outgoing_files = set()
        for ref in outgoing:
            if ref.get("imported_from"):
                outgoing_files.add(ref["imported_from"])

        incoming_files = set(r["file_path"] for r in unique_incoming)

        circular = outgoing_files & incoming_files
        if circular:
            lines.append("")
            lines.append("⚠️ **Circular Dependencies Detected:**")
            for f in circular:
                lines.append(f"  - `{full_path}` ↔️ `{f}`")

    return "\n".join(lines)


def _analyze_project_deps(db: sqlite3.Connection, project: str) -> str:
    """Analyze project-wide dependencies."""
    lines = []

    # File count by language
    lang_stats = db.execute("""
        SELECT language, COUNT(*) as cnt FROM code_files
        WHERE project = ?
        GROUP BY language
        ORDER BY cnt DESC
    """, (project,)).fetchall()

    lines.append("**Files by Language:**")
    for row in lang_stats:
        lines.append(f"- {row['language']}: {row['cnt']}")
    lines.append("")

    # Most connected files (highest dependency count)
    connected = db.execute("""
        SELECT cf.file_path, cf.language,
               COUNT(DISTINCT r_out.to_name) as outgoing,
               COUNT(DISTINCT r_in.from_symbol_id) as incoming
        FROM code_files cf
        LEFT JOIN code_references r_out ON r_out.file_id = cf.id
        LEFT JOIN code_references r_in ON r_in.to_symbol_id IN (
            SELECT id FROM code_symbols WHERE file_id = cf.id
        )
        WHERE cf.project = ?
        GROUP BY cf.id
        ORDER BY (outgoing + incoming) DESC
        LIMIT 10
    """, (project,)).fetchall()

    if connected:
        lines.append("**Most Connected Files:**")
        for row in connected:
            lines.append(
                f"- `{row['file_path']}` — "
                f"out: {row['outgoing']}, in: {row['incoming']}"
            )
        lines.append("")

    # Import statistics
    import_stats = db.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT to_name) as unique_imports,
               COUNT(CASE WHEN to_symbol_id IS NOT NULL THEN 1 END) as resolved
        FROM code_references
        WHERE project = ? AND kind = 'import'
    """, (project,)).fetchone()

    if import_stats and import_stats["total"]:
        lines.append("**Import Statistics:**")
        lines.append(f"- Total imports: {import_stats['total']}")
        lines.append(f"- Unique imports: {import_stats['unique_imports']}")
        lines.append(f"- Resolved: {import_stats['resolved']} ({import_stats['resolved'] * 100 // import_stats['total']}%)")
        lines.append("")

    # Orphan files (no imports, not imported)
    orphans = db.execute("""
        SELECT cf.file_path
        FROM code_files cf
        LEFT JOIN code_references r_out ON r_out.file_id = cf.id AND r_out.kind = 'import'
        LEFT JOIN code_references r_in ON r_in.to_symbol_id IN (
            SELECT id FROM code_symbols WHERE file_id = cf.id
        )
        WHERE cf.project = ?
        GROUP BY cf.id
        HAVING COUNT(DISTINCT r_out.id) = 0 AND COUNT(DISTINCT r_in.id) = 0
        LIMIT 10
    """, (project,)).fetchall()

    if orphans:
        lines.append("**Orphan Files (no imports, not imported):**")
        for row in orphans:
            lines.append(f"- `{row['file_path']}`")
        lines.append("")

    return "\n".join(lines)
