"""MCP tool: code_context — 360-degree view of a symbol."""

import logging
import sqlite3

from db import open_db
from i18n import t
from utils import get_active_session
from tools.code_helpers import has_index, reindex_dirty, find_symbol

_log = logging.getLogger("memoriq.tools.code_context")


def code_context(symbol: str, project_name: str | None = None) -> str:
    """Get full context for a symbol: definition, callers, callees, references.

    Args:
        symbol: Symbol name or qualified name to look up
        project_name: Optional project override
    """
    db = None
    try:
        session = get_active_session()
        project = project_name or session.get("project")
        path = session.get("project_path")

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
        reindex_dirty(db, project, path)

        # Find the symbol
        sym = find_symbol(db, project, symbol)
        if not sym:
            return t("code.symbol_not_found", symbol=symbol)

        sym_dict = dict(sym)
        sym_id = sym_dict["id"]

        lines = []

        # Header: symbol definition
        lines.append(t("code.context_header", symbol=sym_dict["qualified_name"]))
        lines.append(f"**Kind:** {sym_dict['kind']}")
        lines.append(f"**File:** `{sym_dict['file_path']}:{sym_dict['line_start']}`")
        if sym_dict.get("signature"):
            lines.append(f"**Signature:** `{sym_dict['signature']}`")
        if sym_dict.get("docstring"):
            doc = sym_dict["docstring"][:300]
            lines.append(f"**Docstring:** {doc}")

        # Complexity metrics
        cyclomatic = sym_dict.get("cyclomatic_complexity", 0)
        cognitive = sym_dict.get("cognitive_complexity", 0)
        loc = sym_dict.get("lines_of_code", 0)

        if cyclomatic > 0 or cognitive > 0 or loc > 0:
            lines.append("")
            lines.append("**Complexity:**")
            if cyclomatic > 0:
                level = _complexity_level(cyclomatic, "cyclomatic")
                lines.append(f"- Cyclomatic: {cyclomatic} ({level})")
            if cognitive > 0:
                level = _complexity_level(cognitive, "cognitive")
                lines.append(f"- Cognitive: {cognitive} ({level})")
            if loc > 0:
                lines.append(f"- Lines: {loc}")

        # Unused function detection
        if sym_dict["kind"] in ("function", "method") and not sym_dict.get("exported"):
            incoming_count = db.execute("""
                SELECT COUNT(*) as cnt
                FROM code_references
                WHERE to_symbol_id = ? AND project = ?
            """, (sym_id, project)).fetchone()["cnt"]

            if incoming_count == 0:
                # Check if it's a special function name
                name = sym_dict["name"]
                if name not in ("main", "__init__", "__main__", "new", "default"):
                    lines.append("")
                    lines.append("**Suggestions:**")
                    lines.append(f"- This function appears unused (no incoming references)")

        lines.append("")

        # Incoming references (who calls/references this symbol)
        incoming = db.execute("""
            SELECT r.kind, r.line, r.confidence,
                   s.qualified_name as from_name, s.kind as from_kind,
                   f.file_path
            FROM code_references r
            JOIN code_files f ON f.id = r.file_id
            LEFT JOIN code_symbols s ON s.id = r.from_symbol_id
            WHERE r.to_symbol_id = ? AND r.project = ?
            ORDER BY r.kind, f.file_path
            LIMIT 50
        """, (sym_id, project)).fetchall()

        if incoming:
            lines.append(t("code.context_incoming", count=len(incoming)))
            for ref in incoming:
                r = dict(ref)
                from_name = r.get("from_name") or "(module level)"
                lines.append(
                    f"  - [{r['kind']}] `{from_name}` — "
                    f"`{r['file_path']}:{r['line']}`"
                )
        else:
            lines.append(t("code.context_no_incoming"))
        lines.append("")

        # Outgoing references (what this symbol calls/references)
        outgoing = db.execute("""
            SELECT r.kind, r.to_name, r.line, r.confidence,
                   ts.qualified_name as resolved_name, ts.kind as resolved_kind,
                   f.file_path as ref_file
            FROM code_references r
            LEFT JOIN code_symbols ts ON ts.id = r.to_symbol_id
            LEFT JOIN code_files f ON f.id = r.file_id
            WHERE r.from_symbol_id = ? AND r.project = ?
            ORDER BY r.kind, r.line
            LIMIT 50
        """, (sym_id, project)).fetchall()

        if outgoing:
            lines.append(t("code.context_outgoing", count=len(outgoing)))
            for ref in outgoing:
                r = dict(ref)
                target = r.get("resolved_name") or r["to_name"]
                resolved = "" if r.get("resolved_name") else " (unresolved)"
                lines.append(
                    f"  - [{r['kind']}] `{target}`{resolved} "
                    f"— L{r['line']}"
                )
        else:
            lines.append(t("code.context_no_outgoing"))

        # Children (methods of a class, etc.)
        children = db.execute("""
            SELECT s.name, s.kind, s.signature, s.line_start
            FROM code_symbols s
            WHERE s.parent_id = ? AND s.project = ?
            ORDER BY s.line_start
        """, (sym_id, project)).fetchall()

        if children:
            lines.append("")
            lines.append(t("code.context_children", count=len(children)))
            for child in children:
                c = dict(child)
                sig = f" — `{c['signature']}`" if c.get("signature") else ""
                lines.append(f"  - {c['kind']} **{c['name']}** L{c['line_start']}{sig}")

        return "\n".join(lines)

    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return t("code.db_busy")
        return t("code.db_error", error=str(e))
    except Exception as e:
        _log.error("code_context failed: %s", e, exc_info=True)
        return t("code.generic_error", error=str(e))
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _complexity_level(value: int, kind: str) -> str:
    """Return complexity level label (low, medium, high, very high)."""
    if kind == "cyclomatic":
        if value <= 10:
            return "low"
        elif value <= 20:
            return "medium"
        elif value <= 50:
            return "high"
        else:
            return "very high"
    elif kind == "cognitive":
        if value <= 15:
            return "low"
        elif value <= 30:
            return "medium"
        elif value <= 60:
            return "high"
        else:
            return "very high"
    return "unknown"

