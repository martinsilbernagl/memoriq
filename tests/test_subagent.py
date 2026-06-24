"""Tests for subagent memory workflow — tags filter, rapid writes, lock error handling."""

import sqlite3


def test_write_subagent_tags(temp_db, active_session):
    """Subagent-style tags should be stored and searchable via FTS5."""
    from tools.memory_write import memory_write

    result = memory_write(
        content="FastMCP is the most popular MCP framework",
        type="fact",
        tags="subagent,mcp-research",
        domain="architecture",
    )
    assert "saved" in result.lower() or "ulozeno" in result.lower()

    db = sqlite3.connect(str(temp_db))
    row = db.execute("SELECT tags, domain FROM facts WHERE content LIKE '%FastMCP%'").fetchone()
    db.close()

    assert row is not None
    assert "subagent" in row[0]
    assert "mcp-research" in row[0]
    assert row[1] == "architecture"


def test_search_tags_filter(temp_db, active_session):
    """Search with tags filter should return only facts matching all tags."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="Auth uses JWT tokens", type="fact", tags="subagent,auth-review")
    memory_write(content="Redis caching is fast", type="fact", tags="subagent,perf-analysis")
    memory_write(content="Untagged general fact about auth", type="fact")

    # Filter by specific tag — only auth-review tagged facts
    result = memory_search(query="JWT", tags="auth-review")
    assert "jwt" in result.lower()
    assert "redis" not in result.lower()


def test_search_tags_filter_multiple(temp_db, active_session):
    """Multiple tags should ALL match (AND logic)."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="Auth perf issue in token validation", type="fact", tags="subagent,auth-review,perf-analysis")
    memory_write(content="Auth flow uses OAuth2", type="fact", tags="subagent,auth-review")

    # Require both tags — only first fact has both auth-review AND perf-analysis
    result = memory_search(query="token", tags="auth-review,perf-analysis")
    assert "token validation" in result.lower()


def test_search_tags_filter_no_match(temp_db, active_session):
    """Tags filter with no matching facts should return no results."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="Some fact about deployment", type="fact", tags="deploy")

    result = memory_search(query="deployment", tags="subagent")
    assert "no results" in result.lower() or "zadne" in result.lower()


def test_search_tags_filter_subagent(temp_db, active_session):
    """Filter by 'subagent' tag should find all subagent facts regardless of topic tag."""
    from tools.memory_write import memory_write
    from tools.memory_search import memory_search

    memory_write(content="Auth subagent finding about JWT", type="fact", tags="subagent,auth-review")
    memory_write(content="Perf subagent finding about caching", type="fact", tags="subagent,perf-analysis")
    memory_write(content="Manual finding not from subagent", type="fact", tags="auth")

    result = memory_search(query="finding", tags="subagent")
    assert "jwt" in result.lower()
    assert "caching" in result.lower()


def test_rapid_sequential_writes(temp_db, active_session):
    """10 rapid sequential writes should all persist without data loss."""
    from tools.memory_write import memory_write

    for i in range(10):
        result = memory_write(
            content=f"Rapid write fact number {i}: unique content xyz{i}",
            type="fact",
            tags=f"subagent,rapid-test-{i}",
        )
        assert "saved" in result.lower() or "ulozeno" in result.lower(), \
            f"Write {i} failed: {result}"

    db = sqlite3.connect(str(temp_db))
    count = db.execute(
        "SELECT COUNT(*) FROM facts WHERE tags LIKE '%rapid-test%'"
    ).fetchone()[0]
    db.close()

    assert count == 10, f"Expected 10 facts, got {count}"


def test_lock_timeout_returns_error(temp_db, active_session, monkeypatch):
    """When DB is locked and write fails, memory_write should return error, not success."""
    import tools.memory_write as mw_mod
    import db as db_module

    # Lock DB exclusively from another connection
    lock_conn = sqlite3.connect(str(temp_db))
    lock_conn.execute("BEGIN EXCLUSIVE")

    # Patch open_db to use 1ms timeout (so test doesn't wait 30s)
    original_open_db = db_module.open_db

    def short_timeout_open_db(**kwargs):
        conn = original_open_db(**kwargs)
        conn.execute("PRAGMA busy_timeout=1")
        return conn

    monkeypatch.setattr(mw_mod, "open_db", short_timeout_open_db)

    try:
        result = mw_mod.memory_write(content="This should fail due to lock", type="fact")
        # Must NOT contain success indicators
        assert "saved" not in result.lower() or "failed" in result.lower() or "neuloženo" in result.lower(), \
            f"Expected error message but got: {result}"
        # Must contain failure indicator
        assert "failed" in result.lower() or "neuloženo" in result.lower() or "not persisted" in result.lower(), \
            f"Expected failure indicator in: {result}"
    finally:
        lock_conn.rollback()
        lock_conn.close()
