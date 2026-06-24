"""Shared helpers for code intelligence tools (code_context, code_impact, code_search)."""

import logging
import sqlite3

_log = logging.getLogger("memoriq.tools.code_helpers")


def has_index(db, project):
    """Check if project has any indexed files."""
    try:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM code_files WHERE project = ?",
            (project,)
        ).fetchone()
        return row["cnt"] > 0
    except sqlite3.OperationalError:
        return False


def reindex_dirty(db, project, path):
    """Reindex dirty files if any. Called before queries."""
    if not path:
        return
    try:
        dirty = db.execute(
            "SELECT COUNT(*) as cnt FROM code_files WHERE project = ? AND is_dirty = 1",
            (project,)
        ).fetchone()
        if dirty and dirty["cnt"] > 0:
            from code.indexer import reindex_dirty as _reindex
            _reindex(db, project, path, time_budget=5.0)
    except Exception as e:
        _log.warning("Dirty reindex failed: %s", e)


def find_symbol(db, project, symbol):
    """Find a symbol by name or qualified_name.

    3-stage lookup: exact qualified_name -> exact name -> LIKE fallback.
    Deterministic ordering: exported first, then by line_start.
    """
    # Try exact qualified_name first
    row = db.execute("""
        SELECT s.*, f.file_path
        FROM code_symbols s
        JOIN code_files f ON f.id = s.file_id
        WHERE s.project = ? AND s.qualified_name = ?
    """, (project, symbol)).fetchone()

    if row:
        return row

    # Try exact name
    row = db.execute("""
        SELECT s.*, f.file_path
        FROM code_symbols s
        JOIN code_files f ON f.id = s.file_id
        WHERE s.project = ? AND s.name = ?
        ORDER BY s.exported DESC, s.line_start
        LIMIT 1
    """, (project, symbol)).fetchone()

    if row:
        return row

    # LIKE fallback
    row = db.execute("""
        SELECT s.*, f.file_path
        FROM code_symbols s
        JOIN code_files f ON f.id = s.file_id
        WHERE s.project = ? AND (s.name LIKE ? OR s.qualified_name LIKE ?)
        ORDER BY s.exported DESC, s.line_start
        LIMIT 1
    """, (project, f"%{symbol}%", f"%{symbol}%")).fetchone()

    return row
