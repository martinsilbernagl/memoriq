"""MCP tool: code_impact — blast radius analysis via BFS on reference graph."""

import logging
import sqlite3
from collections import deque

from db import open_db
from i18n import t
from utils import get_active_session
from tools.code_helpers import has_index, reindex_dirty, find_symbol

_log = logging.getLogger("memoriq.tools.code_impact")


def code_impact(symbol: str, max_depth: int = 3,
                project_name: str | None = None) -> str:
    """Analyze blast radius of changing a symbol.

    BFS traversal of incoming references to find everything affected.

    Args:
        symbol: Symbol name or qualified name
        max_depth: Max BFS depth (1-5, default 3)
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

        if not has_index(db, project):
            try:
                import tree_sitter_language_pack  # noqa: F401
            except ImportError:
                return t("code.no_treesitter")
            return t("code.not_indexed", project=project)

        # Reindex dirty
        reindex_dirty(db, project, path)

        # Find the symbol
        sym = find_symbol(db, project, symbol)
        if not sym:
            return t("code.symbol_not_found", symbol=symbol)

        sym_dict = dict(sym)
        sym_id = sym_dict["id"]
        max_depth = max(1, min(5, max_depth))

        # BFS: traverse incoming references
        visited: dict[int, int] = {sym_id: 0}  # symbol_id → depth
        queue = deque([(sym_id, 0)])
        impact_by_depth: dict[int, list[dict]] = {}
        affected_files: set[str] = set()

        import time
        start = time.time()
        timeout = 10.0

        while queue:
            if time.time() - start > timeout:
                break

            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Find all symbols that reference current_id
            refs = db.execute("""
                SELECT DISTINCT r.from_symbol_id, s.qualified_name, s.kind,
                       s.name, f.file_path, r.kind as ref_kind, r.line
                FROM code_references r
                JOIN code_symbols s ON s.id = r.from_symbol_id
                JOIN code_files f ON f.id = s.file_id
                WHERE r.to_symbol_id = ? AND r.project = ?
                    AND r.from_symbol_id IS NOT NULL
            """, (current_id, project)).fetchall()

            for ref in refs:
                r = dict(ref)
                from_id = r["from_symbol_id"]
                if from_id in visited:
                    continue

                next_depth = depth + 1
                visited[from_id] = next_depth

                impact_by_depth.setdefault(next_depth, []).append(r)
                affected_files.add(r["file_path"])
                queue.append((from_id, next_depth))

        # Format result
        total_affected = len(visited) - 1  # Exclude the symbol itself
        lines = [t("code.impact_header",
                    symbol=sym_dict["qualified_name"],
                    total=total_affected,
                    files=len(affected_files))]

        lines.append(f"**Symbol:** `{sym_dict['qualified_name']}` ({sym_dict['kind']})")
        lines.append(f"**File:** `{sym_dict['file_path']}:{sym_dict['line_start']}`")
        lines.append(f"**Max depth:** {max_depth}")
        lines.append("")

        if not impact_by_depth:
            lines.append(t("code.impact_no_refs"))
        else:
            for depth in sorted(impact_by_depth.keys()):
                items = impact_by_depth[depth]
                lines.append(t("code.impact_depth", depth=depth, count=len(items)))
                for item in items[:20]:  # Cap display per depth
                    lines.append(
                        f"  - [{item['ref_kind']}] `{item['qualified_name']}` "
                        f"— `{item['file_path']}:{item['line']}`"
                    )
                if len(items) > 20:
                    lines.append(f"  ... and {len(items) - 20} more")
                lines.append("")

        if affected_files:
            lines.append(t("code.impact_files"))
            for fp in sorted(affected_files):
                lines.append(f"  - `{fp}`")

        elapsed = time.time() - start
        if elapsed > timeout:
            lines.append(t("code.impact_timeout", elapsed=f"{elapsed:.1f}"))

        return "\n".join(lines)

    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return t("code.db_busy")
        return t("code.db_error", error=str(e))
    except Exception as e:
        _log.error("code_impact failed: %s", e, exc_info=True)
        return t("code.generic_error", error=str(e))
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


