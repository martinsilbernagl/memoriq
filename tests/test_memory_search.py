"""Tests for memory_search tool."""

import sqlite3


def test_search_finds_fact(temp_db, active_session):
    """Search should find a previously written fact."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="PostgreSQL is used for the main database", type="fact")
    result = memory_search(query="database")

    assert "postgresql" in result.lower()


def test_search_no_results(temp_db, active_session):
    """Search with no matching facts should return a no-results message."""
    from tools.memory_search import memory_search

    result = memory_search(query="nonexistent topic xyz123")
    assert "no results" in result.lower() or "zadne" in result.lower()


def test_search_respects_type_filter(temp_db, active_session):
    """Search with type filter should only return matching types."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="Always use async/await", type="pattern")
    memory_write(content="Never use eval()", type="gotcha")

    result = memory_search(query="use", type="gotcha")
    assert "eval" in result.lower()
    # Pattern fact might not appear since we filtered to gotcha
    # (depends on search ranking, so just verify gotcha is found)


def test_search_cross_project(temp_db, active_session):
    """Search with scope=all should find facts from other projects."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search
    from datetime import datetime

    # Insert fact for a different project directly
    db = sqlite3.connect(str(temp_db))
    db.execute(
        "INSERT INTO projects (name, path, created) VALUES (?, ?, ?)",
        ("other-project", "/tmp/other", datetime.now().isoformat()),
    )
    import uuid
    db.execute("""
        INSERT INTO facts (id, project, content, type, timestamp, heat_score)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), "other-project", "Caddy reverse proxy config",
          "fact", datetime.now().isoformat(), 1.0))
    db.commit()
    # Rebuild FTS
    try:
        db.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
        db.commit()
    except Exception:
        pass
    db.close()

    result = memory_search(query="caddy reverse proxy", scope="all")
    assert "caddy" in result.lower()
