"""Shared DB helper for Memoriq. Used by MCP server, hooks, and scripts."""

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from performance import PerformanceMetrics, timed_query

MEMORIQ_HOME = Path.home() / ".memoriq"
DB_PATH = MEMORIQ_HOME / "memory.db"

# Cache: None = not checked, True = available, False = not available
_vec_system_available = None

# Connection pool configuration
_pool_lock = threading.Lock()
_connection_pools = {
    "default": [],  # List of (connection, last_used_time)
    "vec": [],      # List of (connection, last_used_time)
}
_pool_config = {
    "max_size": 5,
    "timeout": 30.0,
    "connection_ttl": 300.0,  # Recycle connections after 5 minutes
}
_pool_stats = {
    "created": 0,
    "reused": 0,
    "closed": 0,
}

# Query cache configuration
_cache_lock = threading.RLock()
_query_cache = {}  # key -> (result, timestamp, ttl)
_cache_config = {
    "enabled": True,
    "default_ttl": 60.0,  # 60 seconds default TTL
    "max_entries": 1000,
}


def get_db_path() -> Path:
    return DB_PATH


def _create_connection(with_vec: bool = False) -> sqlite3.Connection:
    """Create a new database connection with proper settings."""
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA wal_autocheckpoint=1000")
    db.execute("PRAGMA foreign_keys=ON")
    # Performance optimizations
    db.execute("PRAGMA cache_size=-64000")  # 64MB page cache
    db.execute("PRAGMA temp_store=memory")
    db.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
    db.row_factory = sqlite3.Row

    if with_vec:
        _load_sqlite_vec(db)

    return db


def _is_connection_alive(conn: sqlite3.Connection) -> bool:
    """Check if a connection is still valid."""
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _get_from_pool(pool_key: str) -> Optional[sqlite3.Connection]:
    """Get a connection from the pool if available."""
    global _pool_stats

    with _pool_lock:
        pool = _connection_pools.get(pool_key, [])
        now = time.time()

        while pool:
            conn, last_used = pool.pop()
            # Check if connection is still valid and not too old
            if (now - last_used) < _pool_config["connection_ttl"] and _is_connection_alive(conn):
                _pool_stats["reused"] += 1
                return conn
            else:
                # Close stale connection
                try:
                    conn.close()
                except Exception:
                    pass
                _pool_stats["closed"] += 1

    return None


def _return_to_pool(conn: sqlite3.Connection, pool_key: str):
    """Return a connection to the pool."""
    with _pool_lock:
        # Don't add if pool is full
        if len(_connection_pools[pool_key]) >= _pool_config["max_size"]:
            try:
                conn.close()
            except Exception:
                pass
            _pool_stats["closed"] += 1
            return

        _connection_pools[pool_key].append((conn, time.time()))


def configure_pool(max_size: int = 5, timeout: float = 30.0, connection_ttl: float = 300.0):
    """Configure connection pool settings.

    Args:
        max_size: Maximum number of connections to keep in pool
        timeout: Timeout for getting connection from pool
        connection_ttl: Maximum age of connection before recycling
    """
    global _pool_config
    _pool_config["max_size"] = max_size
    _pool_config["timeout"] = timeout
    _pool_config["connection_ttl"] = connection_ttl


def configure_cache(enabled: bool = True, default_ttl: float = 60.0, max_entries: int = 1000):
    """Configure query cache settings.

    Args:
        enabled: Whether caching is enabled
        default_ttl: Default TTL for cache entries in seconds
        max_entries: Maximum number of cache entries
    """
    global _cache_config
    _cache_config["enabled"] = enabled
    _cache_config["default_ttl"] = default_ttl
    _cache_config["max_entries"] = max_entries

    if not enabled:
        clear_cache()


def clear_cache():
    """Clear all cached query results."""
    with _cache_lock:
        _query_cache.clear()


def _make_cache_key(sql: str, params: tuple) -> str:
    """Create a cache key from SQL and parameters using SHA-256."""
    import hashlib
    key_data = f"{sql}:{repr(params)}"
    # Use SHA-256 instead of MD5 for better collision resistance
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]  # Truncate to save memory


def get_cached_result(sql: str, params: tuple = ()) -> Optional[list]:
    """Get cached query result if available and not expired.

    Args:
        sql: SQL query string
        params: Query parameters

    Returns:
        Cached result or None if not found/expired
    """
    if not _cache_config["enabled"]:
        return None

    cache_key = _make_cache_key(sql, params)

    with _cache_lock:
        if cache_key in _query_cache:
            result, timestamp, ttl = _query_cache[cache_key]
            if time.time() - timestamp < ttl:
                PerformanceMetrics.record_cache_hit("query")
                return result
            else:
                # Expired
                del _query_cache[cache_key]

    PerformanceMetrics.record_cache_miss("query")
    return None


def set_cached_result(sql: str, params: tuple, result: list, ttl: Optional[float] = None):
    """Cache a query result.

    Args:
        sql: SQL query string
        params: Query parameters
        result: Query result to cache
        ttl: Optional custom TTL (uses default if not specified)
    """
    if not _cache_config["enabled"]:
        return

    # Don't cache write operations
    sql_upper = sql.strip().upper()
    if any(sql_upper.startswith(cmd) for cmd in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")):
        return

    # Don't cache large results (>10k rows)
    if len(result) > 10000:
        return

    # Estimate result size and skip if too large (>10MB)
    try:
        result_size = len(str(result).encode())
        if result_size > 10 * 1024 * 1024:  # 10MB
            return
    except Exception:
        pass  # If we can't calculate size, proceed with caution

    cache_key = _make_cache_key(sql, params)
    ttl = ttl or _cache_config["default_ttl"]

    with _cache_lock:
        # Periodic cleanup: remove expired entries
        now = time.time()
        expired_keys = [
            k for k, (_, timestamp, entry_ttl) in _query_cache.items()
            if now - timestamp > entry_ttl
        ]
        for k in expired_keys:
            del _query_cache[k]

        # Simple eviction: clear half the cache if full
        if len(_query_cache) >= _cache_config["max_entries"]:
            # Remove oldest entries
            sorted_items = sorted(_query_cache.items(), key=lambda x: x[1][1])
            for key, _ in sorted_items[:_cache_config["max_entries"] // 2]:
                del _query_cache[key]

        _query_cache[cache_key] = (result, now, ttl)


def invalidate_cache_for_table(table_name: str):
    """Invalidate cache entries that reference a specific table.

    Args:
        table_name: Name of table that was modified
    """
    if not _cache_config["enabled"]:
        return

    with _cache_lock:
        # Remove entries where SQL contains the table name
        keys_to_remove = [
            key for key, (result, timestamp, ttl) in _query_cache.items()
            if table_name.lower() in str(result).lower()
        ]
        for key in keys_to_remove:
            del _query_cache[key]


@contextmanager
def get_db_connection(with_vec: bool = False):
    """Get a database connection from the pool (context manager).

    Usage:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT ...")

    Args:
        with_vec: Whether to load sqlite-vec extension

    Yields:
        sqlite3.Connection
    """
    pool_key = "vec" if with_vec else "default"

    # Try to get from pool
    conn = _get_from_pool(pool_key)

    if conn is None:
        # Create new connection
        conn = _create_connection(with_vec=with_vec)
        global _pool_stats
        with _pool_lock:
            _pool_stats["created"] += 1

    try:
        yield conn
    finally:
        _return_to_pool(conn, pool_key)


def open_db_fast() -> sqlite3.Connection:
    """Fast-path DB open for hooks (no logging, no vec). All PRAGMAs consistent with open_db."""
    # Try to get from pool first
    conn = _get_from_pool("default")
    if conn is not None:
        return conn
    return _create_connection(with_vec=False)


def open_db(with_vec: bool = False) -> sqlite3.Connection:
    """Open DB with WAL mode + busy_timeout for multi-CLI safety.

    Args:
        with_vec: Load sqlite-vec extension. Only needed for vector search/write.
    """
    import logging

    _log = logging.getLogger("memoriq.db")
    t0 = time.time()
    _log.info("open_db: connecting to %s", DB_PATH)

    # Try to get from pool first
    pool_key = "vec" if with_vec else "default"
    conn = _get_from_pool(pool_key)

    if conn is not None:
        _log.info("open_db: reused pooled connection in %.3fs", time.time() - t0)
        return conn

    # Create new connection
    conn = _create_connection(with_vec=with_vec)
    global _pool_stats
    with _pool_lock:
        _pool_stats["created"] += 1

    _log.info("open_db: new connection in %.3fs", time.time() - t0)
    return conn


def close_all_pooled_connections():
    """Close all connections in the pool. Call on shutdown."""
    global _pool_stats

    with _pool_lock:
        for pool_key in ["default", "vec"]:
            pool = _connection_pools.get(pool_key, [])
            for conn, _ in pool:
                try:
                    conn.close()
                except Exception:
                    pass
                _pool_stats["closed"] += 1
            pool.clear()


def get_pool_stats() -> dict:
    """Get connection pool statistics."""
    with _pool_lock:
        return {
            "created": _pool_stats["created"],
            "reused": _pool_stats["reused"],
            "closed": _pool_stats["closed"],
            "pool_default_size": len(_connection_pools["default"]),
            "pool_vec_size": len(_connection_pools["vec"]),
            "config": _pool_config.copy(),
        }


def _trace_db(msg):
    """Unbuffered trace to file for debugging."""
    from datetime import datetime
    try:
        trace_file = MEMORIQ_HOME / "logs" / "trace.log"
        with open(trace_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} [db] {msg}\n")
    except Exception:
        pass


def ensure_vec(db: sqlite3.Connection) -> bool:
    """Ensure sqlite-vec is loaded on this connection. Returns True if available.

    Safe to call multiple times — uses module-level cache to avoid
    repeated ImportError exceptions when sqlite-vec is not installed.
    """
    global _vec_system_available

    _trace_db(f"ensure_vec: _vec_system_available={_vec_system_available}")

    # Fast path: already know it's not available on this system
    if _vec_system_available is False:
        _trace_db("ensure_vec: fast path False")
        return False

    # Check if already loaded on this connection
    _trace_db("ensure_vec: trying SELECT vec_version()")
    try:
        db.execute("SELECT vec_version()")
        _vec_system_available = True
        _trace_db("ensure_vec: vec already loaded, True")
        return True
    except Exception as e:
        _trace_db(f"ensure_vec: vec_version failed: {e}")

    # Try loading
    _trace_db("ensure_vec: calling _load_sqlite_vec")
    return _load_sqlite_vec(db)


def _load_sqlite_vec(db: sqlite3.Connection) -> bool:
    """Load sqlite-vec extension if available. Returns True on success."""
    global _vec_system_available

    _trace_db("_load_sqlite_vec: attempting load")
    try:
        # Load vec0 extension directly by path instead of `import sqlite_vec`
        # which can hang in MCP server context on Windows (numpy import in
        # sqlite_vec.__init__.py blocks when stdin/stdout are MCP pipes).
        vec_dir = Path(__file__).parent.parent
        # Check common install locations for vec0.dll
        import importlib.util
        spec = importlib.util.find_spec("sqlite_vec")
        if spec is None:
            _vec_system_available = False
            _trace_db("_load_sqlite_vec: find_spec=None, not installed")
            return False

        # Load the DLL directly without importing the Python wrapper
        vec0_path = Path(spec.origin).parent / "vec0"
        _trace_db(f"_load_sqlite_vec: loading extension from {vec0_path}")
        db.enable_load_extension(True)
        db.load_extension(str(vec0_path))
        db.enable_load_extension(False)
        _vec_system_available = True
        _trace_db("_load_sqlite_vec: loaded OK via direct path")
        return True
    except ImportError:
        _vec_system_available = False
        _trace_db("_load_sqlite_vec: ImportError, not installed")
        return False
    except Exception as e:
        _vec_system_available = False
        _trace_db(f"_load_sqlite_vec: error: {e}")
        return False
