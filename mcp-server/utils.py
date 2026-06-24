"""Shared utilities for Memoriq MCP tools."""

import json
import time
from pathlib import Path

MEMORIQ_HOME = Path.home() / ".memoriq"
SESSIONS_DIR = MEMORIQ_HOME / "sessions"
ACTIVE_SESSION_FILE = MEMORIQ_HOME / "active_session.json"

# Cache for get_active_session (avoid scanning sessions/ dir on every MCP tool call)
_session_cache = None
_session_cache_time = 0.0
_SESSION_CACHE_TTL = 5.0  # seconds


def get_active_session() -> dict:
    """Load active session info.

    Scans ~/.memoriq/sessions/ dir for per-session files,
    selects the newest one (or matches by CWD).
    Falls back to legacy ~/.memoriq/active_session.json.
    Results are cached for 5 seconds.
    """
    import logging
    _log = logging.getLogger("memoriq.utils")
    global _session_cache, _session_cache_time

    now = time.time()
    if _session_cache is not None and (now - _session_cache_time) < _SESSION_CACHE_TTL:
        _log.info("get_active_session: cache hit (age=%.1fs)", now - _session_cache_time)
        return _session_cache

    _log.info("get_active_session: cache miss, scanning sessions/")
    t0 = time.time()
    result = _scan_sessions()
    _log.info("get_active_session: scan done in %.3fs, project=%s", time.time() - t0, result.get("project", "?"))
    _session_cache = result
    _session_cache_time = now
    return result


def _scan_sessions() -> dict:
    """Scan per-session files, pick the best match."""
    # Try per-session files first
    if SESSIONS_DIR.exists():
        try:
            cwd = str(Path.cwd()).replace("\\", "/")
            best = None
            best_time = 0.0

            for f in SESSIONS_DIR.iterdir():
                if not f.name.endswith(".json"):
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    file_time = f.stat().st_mtime

                    # Prefer session matching current CWD
                    session_path = data.get("project_path", "")
                    if session_path and cwd.startswith(session_path):
                        if best is None or file_time > best_time or \
                                not str(best.get("project_path", "")).startswith(session_path):
                            best = data
                            best_time = file_time
                    elif best is None or file_time > best_time:
                        # No CWD match yet, take newest
                        if best is None or not cwd.startswith(best.get("project_path", "")):
                            best = data
                            best_time = file_time
                except Exception:
                    continue

            if best:
                return best
        except Exception:
            pass

    # Fallback to legacy active_session.json
    if ACTIVE_SESSION_FILE.exists():
        try:
            return json.loads(ACTIVE_SESSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
