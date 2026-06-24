"""Memoriq TUI — Read-only data access layer for memory.db."""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".memoriq" / "memory.db"


def _open() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = sqlite3.Row
    return db


def get_stats(project: str | None = None) -> dict:
    """Get overview statistics."""
    db = _open()
    try:
        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        facts_count = db.execute(
            f"SELECT COUNT(*) FROM facts {where}", params
        ).fetchone()[0]

        hot = db.execute(
            f"SELECT COUNT(*) FROM facts {where + (' AND' if where else 'WHERE')} heat_score >= 0.7",
            params
        ).fetchone()[0]

        warm = db.execute(
            f"SELECT COUNT(*) FROM facts {where + (' AND' if where else 'WHERE')} heat_score >= 0.3 AND heat_score < 0.7",
            params
        ).fetchone()[0]

        cold = facts_count - hot - warm

        sessions_count = db.execute(
            f"SELECT COUNT(*) FROM sessions {where}", params
        ).fetchone()[0]

        changes_count = db.execute(
            f"SELECT COUNT(*) FROM changes {where}", params
        ).fetchone()[0]

        projects_count = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        gaps_count = db.execute(
            f"SELECT COUNT(*) FROM knowledge_gaps {where + (' AND' if where else 'WHERE')} resolved = 0",
            params
        ).fetchone()[0]

        contradictions_count = db.execute(
            f"SELECT COUNT(*) FROM contradictions {where + (' AND' if where else 'WHERE')} resolved = 0",
            params
        ).fetchone()[0]

        # Last session
        last_session = db.execute(
            f"SELECT start_time, bridge_content, episode_title, outcome FROM sessions {where} ORDER BY start_time DESC LIMIT 1",
            params
        ).fetchone()

        return {
            "facts": facts_count,
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "sessions": sessions_count,
            "changes": changes_count,
            "projects": projects_count,
            "gaps": gaps_count,
            "contradictions": contradictions_count,
            "last_session": dict(last_session) if last_session else None,
        }
    finally:
        db.close()


def get_projects() -> list[str]:
    """Get list of project names."""
    db = _open()
    try:
        rows = db.execute("SELECT name FROM projects ORDER BY last_session DESC").fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def get_facts(project: str | None = None, type_filter: str | None = None,
              domain_filter: str | None = None, tier_filter: str | None = None,
              search: str | None = None, limit: int = 200) -> list[dict]:
    """Get facts with optional filters."""
    db = _open()
    try:
        conditions = []
        params = []
        if project:
            conditions.append("f.project = ?")
            params.append(project)
        if type_filter:
            conditions.append("f.type = ?")
            params.append(type_filter)
        if domain_filter:
            conditions.append("f.domain = ?")
            params.append(domain_filter)
        if tier_filter:
            conditions.append("f.knowledge_tier = ?")
            params.append(tier_filter)
        if search:
            conditions.append("f.content LIKE ?")
            params.append(f"%{search}%")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        rows = db.execute(f"""
            SELECT f.id, f.project, f.content, f.type, f.domain, f.heat_score,
                   f.knowledge_tier, f.timestamp, f.retrieval_count, f.tags
            FROM facts f
            {where}
            ORDER BY f.heat_score DESC
            LIMIT ?
        """, params).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def get_fact_types(project: str | None = None) -> list[str]:
    """Get distinct fact types."""
    db = _open()
    try:
        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()
        rows = db.execute(
            f"SELECT DISTINCT type FROM facts {where} ORDER BY type", params
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def get_fact_domains(project: str | None = None) -> list[str]:
    """Get distinct fact domains."""
    db = _open()
    try:
        where = "WHERE project = ? AND domain IS NOT NULL" if project else "WHERE domain IS NOT NULL"
        params = (project,) if project else ()
        rows = db.execute(
            f"SELECT DISTINCT domain FROM facts {where} ORDER BY domain", params
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        db.close()


def get_heat_distribution(project: str | None = None) -> dict:
    """Get heat score distribution by type."""
    db = _open()
    try:
        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        rows = db.execute(f"""
            SELECT type,
                   COUNT(*) as total,
                   SUM(CASE WHEN heat_score >= 0.7 THEN 1 ELSE 0 END) as hot,
                   SUM(CASE WHEN heat_score >= 0.3 AND heat_score < 0.7 THEN 1 ELSE 0 END) as warm,
                   SUM(CASE WHEN heat_score < 0.3 THEN 1 ELSE 0 END) as cold,
                   AVG(heat_score) as avg_heat
            FROM facts
            {where}
            GROUP BY type
            ORDER BY avg_heat DESC
        """, params).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def get_heat_by_project() -> list[dict]:
    """Get heat distribution grouped by project."""
    db = _open()
    try:
        rows = db.execute("""
            SELECT project,
                   COUNT(*) as total,
                   SUM(CASE WHEN heat_score >= 0.7 THEN 1 ELSE 0 END) as hot,
                   SUM(CASE WHEN heat_score >= 0.3 AND heat_score < 0.7 THEN 1 ELSE 0 END) as warm,
                   SUM(CASE WHEN heat_score < 0.3 THEN 1 ELSE 0 END) as cold,
                   AVG(heat_score) as avg_heat
            FROM facts
            GROUP BY project
            ORDER BY avg_heat DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_clusters(project: str | None = None) -> list[dict]:
    """Get fact clusters with member facts."""
    db = _open()
    try:
        where = "WHERE c.project = ?" if project else ""
        params = (project,) if project else ()

        clusters = db.execute(f"""
            SELECT c.id, c.project, c.label, c.summary, c.fact_count, c.created
            FROM fact_clusters c
            {where}
            ORDER BY c.fact_count DESC
        """, params).fetchall()

        result = []
        for c in clusters:
            members = db.execute("""
                SELECT id, substr(content, 1, 80) as preview, type, heat_score
                FROM facts WHERE cluster_id = ?
                ORDER BY heat_score DESC LIMIT 20
            """, (c["id"],)).fetchall()
            result.append({
                **dict(c),
                "members": [dict(m) for m in members],
            })

        return result
    finally:
        db.close()


def get_sessions(project: str | None = None, limit: int = 50) -> list[dict]:
    """Get session timeline."""
    db = _open()
    try:
        where = "WHERE s.project = ?" if project else ""
        params = list((project,)) if project else []
        params.append(limit)

        rows = db.execute(f"""
            SELECT s.id, s.project, s.start_time, s.end_time, s.summary,
                   s.bridge_content, s.episode_title, s.episode_tags, s.outcome,
                   s.facts_count, s.changes_count
            FROM sessions s
            {where}
            ORDER BY s.start_time DESC
            LIMIT ?
        """, params).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def get_gaps(project: str | None = None) -> list[dict]:
    """Get knowledge gaps."""
    db = _open()
    try:
        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        rows = db.execute(f"""
            SELECT id, project, query, hit_count, best_score,
                   first_seen, last_seen, times_seen, resolved
            FROM knowledge_gaps
            {where}
            ORDER BY resolved ASC, times_seen DESC
        """, params).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def get_contradictions(project: str | None = None) -> list[dict]:
    """Get contradictions."""
    db = _open()
    try:
        where = "WHERE c.project = ?" if project else ""
        params = (project,) if project else ()

        rows = db.execute(f"""
            SELECT c.id, c.project, c.reason, c.detected, c.resolved,
                   fa.content as fact_a_content, fa.type as fact_a_type,
                   fb.content as fact_b_content, fb.type as fact_b_type
            FROM contradictions c
            LEFT JOIN facts fa ON c.fact_id_a = fa.id
            LEFT JOIN facts fb ON c.fact_id_b = fb.id
            {where}
            ORDER BY c.resolved ASC, c.detected DESC
        """, params).fetchall()

        return [dict(r) for r in rows]
    finally:
        db.close()


def get_code_stats(project: str | None = None) -> dict | None:
    """Get code intelligence statistics. Returns None if tables don't exist."""
    db = _open()
    try:
        # Check if code tables exist
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('code_files','code_symbols','code_references')"
        ).fetchall()
        if len(tables) < 3:
            return None

        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        files_count = db.execute(
            f"SELECT COUNT(*) FROM code_files {where}", params
        ).fetchone()[0]
        symbols_count = db.execute(
            f"SELECT COUNT(*) FROM code_symbols {where}", params
        ).fetchone()[0]
        refs_count = db.execute(
            f"SELECT COUNT(*) FROM code_references {where}", params
        ).fetchone()[0]

        langs = db.execute(
            f"SELECT DISTINCT language FROM code_files {where} ORDER BY language", params
        ).fetchall()

        return {
            "files": files_count,
            "symbols": symbols_count,
            "references": refs_count,
            "languages": [r[0] for r in langs],
        }
    except Exception:
        return None
    finally:
        db.close()


def get_code_symbol_kinds(project: str | None = None) -> list[str]:
    """Get distinct symbol kinds for filter dropdown."""
    db = _open()
    try:
        where = "WHERE project = ?" if project else ""
        params = (project,) if project else ()
        rows = db.execute(
            f"SELECT DISTINCT kind FROM code_symbols {where} ORDER BY kind", params
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def get_code_files_with_symbols(project: str | None = None, kind_filter: str | None = None,
                                 limit: int = 100) -> list[dict]:
    """Get files with their symbols (2-phase: files, then batch symbols)."""
    db = _open()
    try:
        # Phase 1: Get files
        conditions = []
        params = []
        if project:
            conditions.append("f.project = ?")
            params.append(project)

        # Only get files that have symbols matching the kind filter
        if kind_filter:
            conditions.append("f.id IN (SELECT DISTINCT file_id FROM code_symbols WHERE kind = ?)")
            params.append(kind_filter)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        files = db.execute(f"""
            SELECT f.id, f.file_path, f.language, f.symbol_count
            FROM code_files f
            {where}
            ORDER BY f.file_path
            LIMIT ?
        """, params).fetchall()

        if not files:
            return []

        # Phase 2: Batch load symbols for these files
        file_ids = [f["id"] for f in files]
        placeholders = ",".join("?" * len(file_ids))

        sym_params = list(file_ids)
        kind_clause = ""
        if kind_filter:
            kind_clause = "AND s.kind = ?"
            sym_params.append(kind_filter)

        symbols = db.execute(f"""
            SELECT s.id, s.file_id, s.name, s.kind, s.line_start, s.line_end, s.signature
            FROM code_symbols s
            WHERE s.file_id IN ({placeholders}) {kind_clause}
            ORDER BY s.line_start
        """, sym_params).fetchall()

        # Group symbols by file_id
        sym_by_file: dict[int, list[dict]] = {}
        for s in symbols:
            fid = s["file_id"]
            if fid not in sym_by_file:
                sym_by_file[fid] = []
            sym_by_file[fid].append(dict(s))

        result = []
        for f in files:
            file_syms = sym_by_file.get(f["id"], [])
            if kind_filter and not file_syms:
                continue
            result.append({
                **dict(f),
                "symbols": file_syms,
            })

        return result
    except Exception:
        return []
    finally:
        db.close()


def get_symbol_detail(symbol_id: int) -> dict | None:
    """Get full symbol detail with file info."""
    db = _open()
    try:
        row = db.execute("""
            SELECT s.id, s.name, s.qualified_name, s.kind, s.line_start, s.line_end,
                   s.signature, s.docstring, s.exported, s.parent_id,
                   f.file_path, f.language
            FROM code_symbols s
            JOIN code_files f ON s.file_id = f.id
            WHERE s.id = ?
        """, (symbol_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        db.close()


def get_symbol_references(symbol_id: int) -> dict:
    """Get incoming and outgoing references for a symbol."""
    db = _open()
    try:
        incoming = db.execute("""
            SELECT r.kind, r.line, r.confidence,
                   s.name as from_name, s.kind as from_kind,
                   f.file_path
            FROM code_references r
            LEFT JOIN code_symbols s ON r.from_symbol_id = s.id
            LEFT JOIN code_files f ON r.file_id = f.id
            WHERE r.to_symbol_id = ?
            ORDER BY f.file_path, r.line
        """, (symbol_id,)).fetchall()

        outgoing = db.execute("""
            SELECT r.kind, r.line, r.confidence, r.to_name,
                   s.name as to_resolved_name, s.kind as to_kind,
                   f.file_path
            FROM code_references r
            LEFT JOIN code_symbols s ON r.to_symbol_id = s.id
            LEFT JOIN code_files f ON r.file_id = f.id
            WHERE r.from_symbol_id = ?
            ORDER BY f.file_path, r.line
        """, (symbol_id,)).fetchall()

        return {
            "incoming": [dict(r) for r in incoming],
            "outgoing": [dict(r) for r in outgoing],
        }
    except Exception:
        return {"incoming": [], "outgoing": []}
    finally:
        db.close()


def resolve_contradiction(contradiction_id: int) -> bool:
    """Mark a contradiction as resolved. Returns True on success."""
    db = _open()
    try:
        db.execute("UPDATE contradictions SET resolved = 1 WHERE id = ?", (contradiction_id,))
        db.commit()
        return True
    except Exception:
        return False
    finally:
        db.close()
