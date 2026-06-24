"""Tests for session auto-initialization fallback."""

import pytest
import sys
import os
from pathlib import Path
import sqlite3
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server/tools"))

from memory_write import memory_write


class TestSessionFallback:
    def test_memory_write_with_unknown_session(self, tmp_path, monkeypatch):
        """Test memory_write attempts init when session is unknown."""
        memoriq_home = tmp_path / ".memoriq"
        memoriq_home.mkdir()

        db_path = memoriq_home / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY, path TEXT, created TEXT, last_session TEXT
            );
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY, project TEXT, content TEXT, type TEXT,
                domain TEXT, tags TEXT, timestamp TEXT, heat_score REAL,
                session_id TEXT, source_file TEXT, source_mtime REAL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, project TEXT, start_time TEXT, end_time TEXT
            );
        """)
        conn.close()

        session_file = memoriq_home / "active_session.json"
        session_file.write_text(json.dumps({
            "session_id": "test-session-id",
            "project": "unknown",
            "project_path": str(tmp_path),
            "start_time": "2026-03-11T00:00:00"
        }))

        import utils
        import db
        monkeypatch.setattr(utils, "MEMORIQ_HOME", memoriq_home)
        monkeypatch.setattr(utils, "ACTIVE_SESSION_FILE", session_file)
        monkeypatch.setattr(db, "MEMORIQ_HOME", memoriq_home)
        monkeypatch.setattr(db, "DB_PATH", db_path)
        monkeypatch.chdir(tmp_path)

        try:
            result = memory_write(content="Test fact", type="fact")
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"memory_write crashed: {e}")
