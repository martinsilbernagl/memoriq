"""MCP tool: code_index — index project source code for code intelligence."""

import logging
import sqlite3
import time

from db import open_db
from i18n import t
from utils import get_active_session
from progress import ProgressTracker, format_progress_line

_log = logging.getLogger("memoriq.tools.code_index")


def code_index(project_path: str | None = None,
               full: bool = False,
               time_budget: float = 30.0,
               report_progress: bool = True) -> str:
    """Index project source code using tree-sitter.

    Extracts symbols (functions, classes, methods, interfaces) and references
    (calls, imports, inheritance) into SQLite for code intelligence queries.

    Args:
        project_path: Override project path (uses session path if not provided)
        full: If True, re-index all files (not just changed ones)
        time_budget: Maximum seconds to spend indexing
        report_progress: If True, include progress information in output
    """
    db = None
    tracker = None
    try:
        # Check tree-sitter availability
        try:
            import tree_sitter_language_pack  # noqa: F401
        except ImportError:
            return t("code.no_treesitter")

        session = get_active_session()
        project = session.get("project")
        path = project_path or session.get("project_path")

        if not project or not path:
            return t("code.no_project")

        db = open_db()

        # Ensure code tables exist
        _ensure_tables(db)

        from code.indexer import index_project

        incremental = not full

        # Initialize progress tracker
        if report_progress:
            tracker = ProgressTracker("code_index", project)
            tracker.start(total=100, message="Scanning files...")

        # Wrap index_project to report progress
        if tracker:
            original_index = index_project

            def index_with_progress(*args, **kwargs):
                # Get files first to report progress
                from code.indexer import scan_files
                files = scan_files(path)
                tracker.start(total=len(files) if files else 1, message=f"Found {len(files)} files...")

                # Process with periodic updates
                stats = {
                    "files_total": len(files),
                    "files_indexed": 0,
                    "files_skipped": 0,
                    "symbols": 0,
                    "references": 0,
                    "resolved": 0,
                    "errors": [],
                    "elapsed": 0.0,
                    "partial": False,
                }

                start_time = time.time()
                files_to_index = files

                if incremental:
                    from code.indexer import _filter_changed_files
                    files_to_index = _filter_changed_files(db, project, files)
                    stats["files_skipped"] = len(files) - len(files_to_index)

                if not files_to_index:
                    stats["elapsed"] = time.time() - start_time
                    return stats

                # Index files with progress updates
                from code.parsers.registry import get_parser, get_language
                from code.resolver import resolve_references

                report_every = max(1, len(files_to_index) // 10)  # Report every 10%

                for i, finfo in enumerate(files_to_index):
                    elapsed = time.time() - start_time
                    if elapsed >= time_budget:
                        stats["partial"] = True
                        break

                    ext = finfo["extension"]
                    parser = get_parser(ext)
                    if not parser:
                        continue

                    language = get_language(ext) or "unknown"

                    try:
                        result = parser.parse_file(finfo["path"])
                    except Exception as e:
                        stats["errors"].append(f"{finfo['rel_path']}: {e}")
                        continue

                    if result.errors and not result.symbols and not result.references:
                        continue

                    try:
                        from code.indexer import _store_file, _store_symbols, _store_references
                        file_id = _store_file(db, project, finfo, language, len(result.symbols))
                        _store_symbols(db, project, file_id, result.symbols)
                        _store_references(db, project, file_id, result.references)
                        db.commit()
                        stats["files_indexed"] += 1
                        stats["symbols"] += len(result.symbols)
                        stats["references"] += len(result.references)
                    except sqlite3.OperationalError as e:
                        if "locked" in str(e) or "busy" in str(e):
                            stats["errors"].append(f"{finfo['rel_path']}: DB locked")
                            try:
                                db.rollback()
                            except sqlite3.OperationalError:
                                pass
                        else:
                            raise

                    # Update progress periodically
                    if (i + 1) % report_every == 0 or i == len(files_to_index) - 1:
                        tracker.update(
                            i + 1,
                            f"Indexing {finfo['rel_path']} ({stats['symbols']} symbols, {stats['references']} refs)"
                        )

                # Resolve references
                try:
                    unresolved = db.execute("""
                        SELECT COUNT(*) FROM code_references
                        WHERE project = ? AND to_symbol_id IS NULL
                    """, (project,)).fetchone()[0]

                    if stats["files_indexed"] > 0 or unresolved > 0:
                        tracker.update(tracker.current, "Resolving references...")
                        stats["resolved"] = resolve_references(db, project)
                except Exception as e:
                    _log.warning("Reference resolution failed: %s", e)

                stats["elapsed"] = time.time() - start_time
                tracker.finish(f"Complete: {stats['files_indexed']} files, {stats['symbols']} symbols")
                return stats

            stats = index_with_progress(db, project, path, time_budget, incremental)
        else:
            stats = index_project(
                db=db,
                project=project,
                project_path=path,
                time_budget=time_budget,
                incremental=incremental,
            )

        # Format result
        lines = [t("code.index_header", project=project)]

        if stats["partial"]:
            lines.append(t("code.index_partial",
                           elapsed=f"{stats['elapsed']:.1f}",
                           files=stats["files_indexed"],
                           total=stats["files_total"]))
        else:
            lines.append(t("code.index_complete",
                           elapsed=f"{stats['elapsed']:.1f}"))

        lines.append(t("code.index_stats",
                        files_total=stats["files_total"],
                        files_indexed=stats["files_indexed"],
                        files_skipped=stats["files_skipped"],
                        symbols=stats["symbols"],
                        references=stats["references"],
                        resolved=stats["resolved"]))

        if stats["errors"]:
            lines.append(t("code.index_errors", count=len(stats["errors"])))
            for err in stats["errors"][:5]:
                lines.append(f"  - {err}")
            if len(stats["errors"]) > 5:
                lines.append(f"  ... and {len(stats['errors']) - 5} more")

        # Always show DB totals so incremental runs don't look empty
        try:
            total_sym = db.execute(
                "SELECT COUNT(*) FROM code_symbols WHERE project = ?", (project,)
            ).fetchone()[0]
            total_ref = db.execute(
                "SELECT COUNT(*) FROM code_references WHERE project = ?", (project,)
            ).fetchone()[0]
            lines.append(t("code.index_db_totals",
                           symbols=total_sym, references=total_ref))
        except Exception:
            pass

        # Include progress summary if tracker was used
        if tracker:
            lines.append("")
            lines.append(format_progress_line(tracker.get_status()))

        return "\n".join(lines)

    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return t("code.db_busy")
        return t("code.db_error", error=str(e))
    except Exception as e:
        _log.error("code_index failed: %s", e, exc_info=True)
        return t("code.generic_error", error=str(e))
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _ensure_tables(db: sqlite3.Connection) -> None:
    """Ensure code intelligence tables exist (idempotent)."""
    try:
        db.execute("SELECT 1 FROM code_files LIMIT 1")
    except sqlite3.OperationalError:
        # Tables don't exist — run migration
        from init_db import upgrade_schema
        upgrade_schema(db)

    # Ensure FTS table exists (separate check — migration path doesn't create it)
    _ensure_fts(db)


def _ensure_fts(db: sqlite3.Connection) -> None:
    """Ensure code_symbols_fts exists and is populated. Safe to call repeatedly."""
    try:
        db.execute("SELECT 1 FROM code_symbols_fts LIMIT 1")
        return  # Already exists
    except sqlite3.OperationalError:
        pass  # Doesn't exist — create it

    try:
        db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS code_symbols_fts USING fts5(
                name, qualified_name, signature, docstring,
                content=code_symbols, content_rowid=rowid
            );
            CREATE TRIGGER IF NOT EXISTS code_symbols_ai AFTER INSERT ON code_symbols BEGIN
                INSERT INTO code_symbols_fts(rowid, name, qualified_name, signature, docstring)
                VALUES (new.rowid, new.name, new.qualified_name, new.signature, new.docstring);
            END;
            CREATE TRIGGER IF NOT EXISTS code_symbols_ad AFTER DELETE ON code_symbols BEGIN
                INSERT INTO code_symbols_fts(code_symbols_fts, rowid, name, qualified_name, signature, docstring)
                VALUES ('delete', old.rowid, old.name, old.qualified_name, old.signature, old.docstring);
            END;
            CREATE TRIGGER IF NOT EXISTS code_symbols_au AFTER UPDATE ON code_symbols BEGIN
                INSERT INTO code_symbols_fts(code_symbols_fts, rowid, name, qualified_name, signature, docstring)
                VALUES ('delete', old.rowid, old.name, old.qualified_name, old.signature, old.docstring);
                INSERT INTO code_symbols_fts(rowid, name, qualified_name, signature, docstring)
                VALUES (new.rowid, new.name, new.qualified_name, new.signature, new.docstring);
            END;
        """)
        # Backfill existing symbols into FTS
        count = db.execute("SELECT COUNT(*) FROM code_symbols").fetchone()[0]
        if count > 0:
            db.execute("""
                INSERT INTO code_symbols_fts(rowid, name, qualified_name, signature, docstring)
                SELECT rowid, name, qualified_name, COALESCE(signature, ''), COALESCE(docstring, '')
                FROM code_symbols
            """)
            db.commit()
            _log.info("Backfilled %d symbols into code_symbols_fts", count)
    except Exception as e:
        _log.warning("FTS creation failed (non-critical): %s", e)
