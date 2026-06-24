"""Tests for database creation and schema integrity."""

import sqlite3


def test_db_creates_file(temp_db):
    """DB file should be created by fixture."""
    assert temp_db.exists()


def test_core_tables_exist(temp_db):
    """All core tables should exist after schema creation."""
    db = sqlite3.connect(str(temp_db))
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    db.close()

    expected = {
        "projects", "facts", "file_chunks", "decisions", "sessions",
        "changes", "project_identity", "identity_audit_log", "tech_templates",
        "fact_links", "knowledge_gaps", "fact_clusters", "contradictions",
        "causal_chains",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_fts_tables_exist(temp_db):
    """FTS5 virtual tables should exist."""
    db = sqlite3.connect(str(temp_db))
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    db.close()

    assert "facts_fts" in tables
    assert "chunks_fts" in tables


def test_wal_mode(temp_db):
    """Database should use WAL journal mode."""
    from db import open_db
    db = open_db()
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    db.close()
    assert mode == "wal"


def test_foreign_keys_enabled(temp_db):
    """Foreign keys should be enabled."""
    from db import open_db
    db = open_db()
    fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
    db.close()
    assert fk == 1
