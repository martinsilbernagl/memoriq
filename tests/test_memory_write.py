"""Tests for memory_write tool."""

import sqlite3


def test_write_fact(temp_db, active_session):
    """Writing a fact should insert into facts table."""
    from tools.memory_write import memory_write

    result = memory_write(content="Test fact content", type="fact")
    assert "test-project" in result.lower() or "saved" in result.lower() or "ulozeno" in result.lower()

    db = sqlite3.connect(str(temp_db))
    row = db.execute("SELECT content, type, project FROM facts").fetchone()
    db.close()

    assert row is not None
    assert row[0] == "Test fact content"
    assert row[1] == "fact"
    assert row[2] == "test-project"


def test_write_different_types(temp_db, active_session):
    """Should support all 14 fact types."""
    from tools.memory_write import memory_write

    types = [
        "decision", "fact", "pattern", "issue", "task", "skill",
        "gotcha", "procedure", "error_fix", "command",
        "performance", "api_contract", "dependency", "client_rule",
    ]
    for t in types:
        result = memory_write(content=f"Test {t}", type=t)
        assert "blocked" not in result.lower(), f"Type {t} was blocked: {result}"

    db = sqlite3.connect(str(temp_db))
    count = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    db.close()
    assert count == 14


def test_deduplication_same_content(temp_db, active_session):
    """Writing same content + source_file + type should not create duplicate."""
    from tools.memory_write import memory_write

    memory_write(content="Unique fact", type="fact", source_file="test.py")
    result = memory_write(content="Unique fact", type="fact", source_file="test.py")

    assert "exists" in result.lower() or "existuje" in result.lower() or "unchanged" in result.lower()

    db = sqlite3.connect(str(temp_db))
    count = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    db.close()
    assert count == 1


def test_deduplication_updated_content(temp_db, active_session):
    """Updating content for same source_file + type should update, not insert."""
    from tools.memory_write import memory_write

    memory_write(content="Original fact", type="fact", source_file="test.py")
    memory_write(content="Updated fact", type="fact", source_file="test.py")

    db = sqlite3.connect(str(temp_db))
    count = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    content = db.execute("SELECT content FROM facts").fetchone()[0]
    db.close()

    assert count == 1
    assert content == "Updated fact"


def test_write_with_tags_and_domain(temp_db, active_session):
    """Tags and domain should be stored."""
    from tools.memory_write import memory_write

    memory_write(content="Tagged fact", type="fact", tags="auth,security", domain="backend")

    db = sqlite3.connect(str(temp_db))
    row = db.execute("SELECT tags, domain FROM facts").fetchone()
    db.close()

    assert row[0] == "auth,security"
    assert row[1] == "backend"
