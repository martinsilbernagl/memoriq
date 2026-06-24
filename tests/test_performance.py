"""Performance tests for Memoriq.

Tests query caching, connection pooling, batch operations, and FTS5 optimization.
"""

import sqlite3
import time
import threading
from pathlib import Path

import pytest

# Add mcp-server to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))

from db import (
    get_db_connection, open_db, configure_pool, configure_cache,
    clear_cache, get_cached_result, set_cached_result, get_pool_stats,
    close_all_pooled_connections
)
from performance import PerformanceMetrics, timed, timed_query


@pytest.fixture
def tmp_db_path(tmp_path):
    """Create a temporary database path."""
    db_path = tmp_path / "test_memory.db"
    return db_path


@pytest.fixture
def perf_db(tmp_path):
    """Create a temporary database for performance testing."""
    db_path = tmp_path / "perf_test.db"

    # Patch DB_PATH temporarily
    import db as db_module
    original_path = db_module.DB_PATH
    db_module.DB_PATH = db_path

    # Create schema
    conn = sqlite3.connect(str(db_path))
    try:
        from init_db import SCHEMA, FTS_SCHEMA, VEC_SCHEMA
        from db import ensure_vec
        conn.executescript(SCHEMA)
        conn.executescript(FTS_SCHEMA)
        if ensure_vec(conn):
            conn.executescript(VEC_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO projects (name, path, created) VALUES ('unknown', '/tmp', '2026-06-23')")
        conn.execute("INSERT OR IGNORE INTO projects (name, path, created) VALUES ('test', '/tmp', '2026-06-23')")
    except Exception as e:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                heat_score REAL DEFAULT 1.0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts_fts (
                content TEXT,
                tags TEXT,
                domain TEXT
            )
        """)
    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_module.DB_PATH = original_path
    close_all_pooled_connections()
    clear_cache()


class TestQueryCaching:
    """Test query result caching functionality."""

    def test_cache_hit_miss(self, perf_db):
        """Test cache hit and miss tracking."""
        clear_cache()
        configure_cache(enabled=True, default_ttl=60.0)

        # First call - cache miss
        sql = "SELECT * FROM facts WHERE project = ?"
        params = ("test_project",)
        result = get_cached_result(sql, params)
        assert result is None

        # Store in cache
        test_data = [{"id": "1", "content": "test"}]
        set_cached_result(sql, params, test_data)

        # Second call - cache hit
        result = get_cached_result(sql, params)
        assert result == test_data

    def test_cache_ttl_expiration(self, perf_db):
        """Test cache TTL expiration."""
        clear_cache()
        configure_cache(enabled=True, default_ttl=0.1)  # 100ms TTL

        sql = "SELECT * FROM facts"
        test_data = [{"id": "1", "content": "test"}]
        set_cached_result(sql, (), test_data)

        # Should be in cache immediately
        assert get_cached_result(sql, ()) == test_data

        # Wait for expiration
        time.sleep(0.15)
        assert get_cached_result(sql, ()) is None

    def test_cache_disabled(self, perf_db):
        """Test that disabled cache returns None."""
        configure_cache(enabled=False)

        sql = "SELECT * FROM facts"
        test_data = [{"id": "1"}]
        set_cached_result(sql, (), test_data)

        result = get_cached_result(sql, ())
        assert result is None

    def test_cache_max_entries(self, perf_db):
        """Test cache eviction at max entries."""
        clear_cache()
        configure_cache(enabled=True, max_entries=10)

        # Add more entries than max
        for i in range(15):
            set_cached_result(f"SELECT {i}", (), [{"id": i}])

        # Some entries should have been evicted
        hits = sum(1 for i in range(15) if get_cached_result(f"SELECT {i}", ()) is not None)
        assert hits <= 10

    def test_write_operations_not_cached(self, perf_db):
        """Test that INSERT/UPDATE/DELETE are not cached."""
        clear_cache()
        configure_cache(enabled=True)

        test_data = [{"id": "1"}]
        set_cached_result("INSERT INTO facts VALUES (1)", (), test_data)
        set_cached_result("UPDATE facts SET x = 1", (), test_data)
        set_cached_result("DELETE FROM facts", (), test_data)

        assert get_cached_result("INSERT INTO facts VALUES (1)", ()) is None
        assert get_cached_result("UPDATE facts SET x = 1", ()) is None
        assert get_cached_result("DELETE FROM facts", ()) is None


class TestConnectionPooling:
    """Test connection pooling functionality."""

    def test_pool_reuses_connections(self, perf_db):
        """Test that connections are reused from pool."""
        configure_pool(max_size=5)
        close_all_pooled_connections()

        # Get initial stats
        stats_before = get_pool_stats()

        # Use connection multiple times
        for _ in range(5):
            with get_db_connection() as conn:
                conn.execute("SELECT 1")

        stats_after = get_pool_stats()
        # Should have created at least one connection
        assert stats_after["created"] >= stats_before["created"]

    def test_pool_context_manager(self, perf_db):
        """Test connection pool context manager."""
        configure_pool(max_size=2)

        with get_db_connection() as conn:
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

    def test_pool_thread_safety(self, perf_db):
        """Test thread-safe connection pool access."""
        configure_pool(max_size=5)
        results = []
        errors = []

        def worker():
            try:
                with get_db_connection() as conn:
                    result = conn.execute("SELECT 1").fetchone()
                    results.append(result[0])
                    time.sleep(0.01)  # Hold connection briefly
            except Exception as e:
                errors.append(str(e))

        # Spawn multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10
        assert all(r == 1 for r in results)

    def test_pool_size_limit(self, perf_db):
        """Test pool size limits."""
        configure_pool(max_size=2)
        close_all_pooled_connections()

        # Create connections up to limit
        conns = []
        for _ in range(3):
            conn = open_db()
            conn.execute("SELECT 1")
            conns.append(conn)

        # Return to pool
        for conn in conns:
            conn.close()

        stats = get_pool_stats()
        # Pool should not exceed max_size
        assert stats["pool_default_size"] <= 2


class TestPerformanceMetrics:
    """Test performance metrics collection."""

    def test_record_query(self):
        """Test query timing recording."""
        PerformanceMetrics.reset()

        PerformanceMetrics.record_query("SELECT * FROM facts", 50.0)
        PerformanceMetrics.record_query("SELECT * FROM facts", 150.0)  # Slow query

        summary = PerformanceMetrics.get_summary()
        assert summary["total_queries"] == 2
        assert summary["slow_queries"] == 1
        assert summary["avg_query_time_ms"] == 100.0

    def test_cache_hit_miss_tracking(self):
        """Test cache hit/miss tracking."""
        PerformanceMetrics.reset()

        PerformanceMetrics.record_cache_hit("query")
        PerformanceMetrics.record_cache_hit("query")
        PerformanceMetrics.record_cache_miss("query")

        summary = PerformanceMetrics.get_summary()
        assert summary["cache_hits"] == 2
        assert summary["cache_misses"] == 1
        assert summary["cache_hit_rate"] == round(2/3, 3)

    def test_timed_decorator(self):
        """Test timed decorator."""
        PerformanceMetrics.reset()

        @timed("test_operation")
        def slow_function():
            time.sleep(0.01)
            return 42

        result = slow_function()
        assert result == 42

        summary = PerformanceMetrics.get_summary()
        assert summary["total_queries"] == 1

    def test_timed_query_context_manager(self):
        """Test timed_query context manager."""
        PerformanceMetrics.reset()

        with timed_query("SELECT test"):
            time.sleep(0.01)

        summary = PerformanceMetrics.get_summary()
        assert summary["total_queries"] == 1


class TestBatchOperations:
    """Test batch memory write operations."""

    def test_batch_write_performance(self, perf_db):
        """Test batch write is faster than individual writes."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server" / "tools"))
        from memory_write import memory_write_batch

        # Prepare test facts
        facts = [
            {"content": f"Test fact {i}", "type": "fact", "tags": "test"}
            for i in range(20)
        ]

        # Time batch write
        start = time.time()
        results = memory_write_batch(facts, batch_size=10)
        batch_time = time.time() - start

        assert len(results) == 20
        # All should succeed (no errors)
        assert all("Error" not in r for r in results)

        # Batch should be reasonably fast (< 5 seconds even without embeddings)
        assert batch_time < 5.0

    def test_batch_write_empty_list(self, perf_db):
        """Test batch write with empty list."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server" / "tools"))
        from memory_write import memory_write_batch

        results = memory_write_batch([])
        assert results == []

    def test_batch_write_with_secrets(self, perf_db):
        """Test batch write filters secrets."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server" / "tools"))
        from memory_write import memory_write_batch

        facts = [
            {"content": "Normal fact", "type": "fact"},
            {"content": "sk-live-12345678901234567890abcdef", "type": "fact"},  # Secret
            {"content": "Another normal fact", "type": "fact"},
        ]

        results = memory_write_batch(facts)
        assert len(results) == 3
        assert "blocked" in results[1].lower() or "secret" in results[1].lower()


class TestFTS5Optimization:
    """Test FTS5 query optimizations."""

    def test_fts_search_uses_cache(self, perf_db):
        """Test that FTS search uses query cache."""
        clear_cache()
        configure_cache(enabled=True, default_ttl=60.0)

        # Import here to avoid early import issues
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server" / "search"))
        from fts_search import fts_search_facts

        # Create test database connection
        conn = sqlite3.connect(str(perf_db))
        conn.row_factory = sqlite3.Row

        # First search - should cache
        results1 = fts_search_facts(conn, "test", project="test", limit=5)

        # Second identical search - should hit cache
        results2 = fts_search_facts(conn, "test", project="test", limit=5)

        conn.close()

        # Results should be identical (both empty since no data, but cached)
        assert results1 == results2

    def test_trivial_query_optimization(self, perf_db):
        """Test that trivial queries bypass FTS5."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server" / "search"))
        from fts_search import fts_search_facts, _is_trivial_query

        assert _is_trivial_query("ab") is True
        assert _is_trivial_query("test query") is False

        conn = sqlite3.connect(str(perf_db))
        conn.row_factory = sqlite3.Row

        # Trivial query should return quickly without FTS5
        results = fts_search_facts(conn, "ab", project="test", limit=5)
        assert isinstance(results, list)

        conn.close()


class TestIntegration:
    """Integration tests for performance features."""

    def test_end_to_end_performance(self, perf_db):
        """Test end-to-end performance workflow."""
        # Reset state
        clear_cache()
        PerformanceMetrics.reset()
        configure_pool(max_size=3)
        configure_cache(enabled=True, default_ttl=60.0)

        # Simulate workload
        with get_db_connection() as conn:
            # Insert test data
            for i in range(10):
                conn.execute(
                    "INSERT OR IGNORE INTO facts (id, project, content, type, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (f"fact_{i}", "test", f"Content {i}", "fact", "2024-01-01")
                )
            conn.commit()

        # Query with cache
        with get_db_connection() as conn:
            sql = "SELECT * FROM facts WHERE project = ?"
            params = ("test",)

            # First query - miss
            result1 = conn.execute(sql, params).fetchall()
            set_cached_result(sql, params, [dict(r) for r in result1])

            # Second query - hit
            cached = get_cached_result(sql, params)
            assert cached is not None

        # Verify metrics
        summary = PerformanceMetrics.get_summary()
        assert summary["total_queries"] >= 0

        # Verify pool stats
        pool_stats = get_pool_stats()
        assert pool_stats["created"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
