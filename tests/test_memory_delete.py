"""Tests for memory_delete tool."""

import sqlite3


def test_delete_fact(temp_db, active_session):
    """Should delete a fact by ID."""
    from tools.memory_write import memory_write
    from tools.memory_delete import memory_delete

    memory_write(content="Temporary fact to delete", type="fact")

    db = sqlite3.connect(str(temp_db))
    fact_id = db.execute("SELECT id FROM facts").fetchone()[0]
    db.close()

    result = memory_delete(ids=[fact_id])
    assert "1" in result  # "Deleted 1 facts"

    db = sqlite3.connect(str(temp_db))
    count = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    db.close()
    assert count == 0


def test_delete_nonexistent(temp_db, active_session):
    """Deleting a nonexistent ID should not error."""
    from tools.memory_delete import memory_delete

    result = memory_delete(ids=["nonexistent-uuid-12345"])
    # Should report 0 deleted or handle gracefully
    assert "0" in result or "deleted" in result.lower() or "smazano" in result.lower()


def test_delete_no_ids(temp_db, active_session):
    """Empty IDs list should return appropriate message."""
    from tools.memory_delete import memory_delete

    result = memory_delete(ids=[])
    assert "no id" in result.lower() or "zadna" in result.lower()
