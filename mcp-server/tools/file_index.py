"""file_index — MCP tool to index project documentation into file_chunks.

Indexes README, configs, PRDs, YAML, JSON, TOML, and other documentation files
into the file_chunks table so that file_search() returns results.

Without this, file_search returns empty because no other code path triggers
reindex_project() — the SessionStart hook skipped it for performance,
and session_init intentionally doesn't call it.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db import open_db
from utils import get_active_session
from indexer.file_indexer import reindex_project, scan_project_files
from i18n import t
from progress import ProgressTracker, format_progress_line

logger = logging.getLogger("memoriq.file_index")


def file_index(project_path: str | None = None, full: bool = False,
               time_budget: float = 30.0, report_progress: bool = True) -> str:
    """Index project documentation files into file_chunks for file_search.

    Args:
        project_path: Override project path (uses session path if not provided)
        full: If True, re-index all files (not just changed ones)
        time_budget: Maximum seconds to spend indexing
        report_progress: If True, track and report progress
    """
    session = get_active_session()
    project = session.get("project", "")
    path_str = project_path or session.get("project_path", "")

    if not path_str:
        return t("file_index.no_path")

    path = Path(path_str).resolve()
    if not path.exists() or not path.is_dir():
        return t("file_index.invalid_path", path=str(path))

    if not project:
        project = path.name

    logger.info("file_index: project=%s path=%s full=%s budget=%.1f",
                project, path, full, time_budget)

    # Initialize progress tracker
    tracker = None
    if report_progress:
        tracker = ProgressTracker("file_index", project)
        tracker.start(total=100, message="Scanning files...")

    db = open_db()
    try:
        # If full reindex, clear existing chunks first
        if full:
            db.execute("DELETE FROM file_chunks WHERE project = ?", (project,))
            logger.info("Full reindex: cleared existing chunks for %s", project)
            if tracker:
                tracker.update(0, "Cleared existing index...")

        # Scan files first for progress reporting
        files_to_index = scan_project_files(path)
        if tracker:
            tracker.start(total=len(files_to_index), message=f"Found {len(files_to_index)} files...")

        # Custom reindex with progress tracking
        if tracker and files_to_index:
            indexed_count = _reindex_with_progress(db, project, path, files_to_index,
                                                   time_budget, tracker)
        else:
            indexed_count = reindex_project(db, project, path, time_budget=time_budget)

        db.commit()

        # Get stats
        total_chunks = db.execute(
            "SELECT COUNT(*) FROM file_chunks WHERE project = ?", (project,)
        ).fetchone()[0]
        total_files = db.execute(
            "SELECT COUNT(DISTINCT file_path) FROM file_chunks WHERE project = ?",
            (project,)
        ).fetchone()[0]

        if tracker:
            tracker.finish(f"Complete: {indexed_count} files indexed")

    except Exception as e:
        logger.error("file_index failed: %s", e, exc_info=True)
        if tracker:
            tracker.error(str(e))
        return t("file_index.error", error=str(e))
    finally:
        db.close()

    # Scan to report what's available
    available = len(scan_project_files(path))

    result = t("file_index.success",
               project=project,
               indexed=indexed_count,
               total_files=total_files,
               total_chunks=total_chunks,
               available=available)

    # Include progress summary if tracker was used
    if tracker:
        result += "\n\n" + format_progress_line(tracker.get_status())

    return result


def _reindex_with_progress(db, project: str, path: Path, files_to_index: list,
                           time_budget: float, tracker: ProgressTracker) -> int:
    """Reindex files with progress tracking."""
    import time
    from indexer.chunker import chunk_file
    from indexer.file_indexer import DOC_EXTENSIONS, IGNORE_DIRS, IGNORE_FILES
    from indexer.file_indexer import NEVER_INDEX, MAX_FILE_SIZE
    from db import ensure_vec

    start = time.time()
    indexed_count = 0

    # Get currently indexed files from DB
    indexed = {}
    for row in db.execute(
        "SELECT DISTINCT file_path, file_mtime FROM file_chunks WHERE project = ?",
        (project,)
    ).fetchall():
        indexed[row[0]] = row[1]

    report_every = max(1, len(files_to_index) // 10)  # Report every 10%

    for i, file_path in enumerate(files_to_index):
        if time.time() - start > time_budget:
            tracker.update(i, "Time budget exhausted")
            break

        rel_path = str(file_path.relative_to(path)).replace("\\", "/")
        current_mtime = file_path.stat().st_mtime

        # Skip if unchanged
        if rel_path in indexed and abs(indexed[rel_path] - current_mtime) < 1:
            continue

        # Read and chunk file
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        chunks = chunk_file(content, rel_path)
        if not chunks:
            continue

        # Get old rowids before deleting
        old_rowids = [r[0] for r in db.execute(
            "SELECT rowid FROM file_chunks WHERE project = ? AND file_path = ?",
            (project, rel_path)
        ).fetchall()]

        # Delete old chunks for this file
        db.execute(
            "DELETE FROM file_chunks WHERE project = ? AND file_path = ?",
            (project, rel_path)
        )

        # Clean orphaned chunks_vec entries
        if old_rowids and ensure_vec(db):
            for rid in old_rowids:
                try:
                    db.execute("DELETE FROM chunks_vec WHERE rowid = ?", (rid,))
                except Exception:
                    pass

        # Insert new chunks
        new_rowids = []
        chunk_texts = []
        for chunk in chunks:
            cursor = db.execute("""
                INSERT INTO file_chunks (project, file_path, file_mtime,
                                        section_title, chunk_index, content)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                project, rel_path, current_mtime,
                chunk["section_title"], chunk["chunk_index"], chunk["content"]
            ))
            rowid = cursor.lastrowid
            new_rowids.append(rowid)
            text = chunk["content"]
            if chunk["section_title"]:
                text = f"{chunk['section_title']}: {text}"
            chunk_texts.append(text)

        # Generate embeddings for new chunks
        try:
            if ensure_vec(db):
                from embedder import embed_texts
                embeddings = embed_texts(chunk_texts)
                for rowid, emb in zip(new_rowids, embeddings):
                    db.execute(
                        "INSERT OR REPLACE INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                        (rowid, emb)
                    )
        except Exception:
            pass  # Embedding not available, FTS5 still works

        indexed_count += 1

        # Update progress periodically
        if (i + 1) % report_every == 0 or i == len(files_to_index) - 1:
            tracker.update(i + 1, f"Indexing {rel_path}")

    # Clean up deleted files
    current_files = {str(f.relative_to(path)).replace("\\", "/") for f in files_to_index}
    for indexed_path in list(indexed.keys()):
        if indexed_path not in current_files:
            orphan_rowids = [r[0] for r in db.execute(
                "SELECT rowid FROM file_chunks WHERE project = ? AND file_path = ?",
                (project, indexed_path)
            ).fetchall()]

            db.execute(
                "DELETE FROM file_chunks WHERE project = ? AND file_path = ?",
                (project, indexed_path)
            )

            if orphan_rowids and ensure_vec(db):
                for rid in orphan_rowids:
                    try:
                        db.execute("DELETE FROM chunks_vec WHERE rowid = ?", (rid,))
                    except Exception:
                        pass

    return indexed_count
