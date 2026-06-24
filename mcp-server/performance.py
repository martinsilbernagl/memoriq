"""Performance metrics and monitoring for Memoriq.

Provides query timing, cache tracking, and slow query logging.
"""

import functools
import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional

# Logger for performance metrics
_perf_log = logging.getLogger("memoriq.performance")

# Thread-local storage for metrics collection
_local = threading.local()

# Global metrics storage (thread-safe)
_metrics_lock = threading.Lock()
_metrics = {
    "queries": defaultdict(lambda: {"count": 0, "total_ms": 0.0, "slow_count": 0}),
    "cache_hits": defaultdict(int),
    "cache_misses": defaultdict(int),
    "slow_queries": [],  # List of (sql, duration_ms, timestamp)
}

# Configuration
SLOW_QUERY_THRESHOLD_MS = 100.0
MAX_SLOW_QUERIES = 100


def _get_trace_file() -> Optional[Path]:
    """Get trace log file path."""
    try:
        return Path.home() / ".memoriq" / "logs" / "performance.log"
    except Exception:
        return None


def _log_performance(msg: str):
    """Log to performance log file."""
    _perf_log.info(msg)
    trace_file = _get_trace_file()
    if trace_file:
        try:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        except Exception:
            pass


class PerformanceMetrics:
    """Collect and report performance metrics."""

    @staticmethod
    def record_query(sql: str, duration_ms: float):
        """Record a database query execution."""
        # Truncate SQL for storage
        sql_key = sql[:100] if len(sql) > 100 else sql

        with _metrics_lock:
            _metrics["queries"][sql_key]["count"] += 1
            _metrics["queries"][sql_key]["total_ms"] += duration_ms

            if duration_ms > SLOW_QUERY_THRESHOLD_MS:
                _metrics["queries"][sql_key]["slow_count"] += 1
                _metrics["slow_queries"].append({
                    "sql": sql[:200],
                    "duration_ms": round(duration_ms, 2),
                    "timestamp": time.time(),
                })
                # Trim slow queries list
                if len(_metrics["slow_queries"]) > MAX_SLOW_QUERIES:
                    _metrics["slow_queries"] = _metrics["slow_queries"][-MAX_SLOW_QUERIES:]

                _log_performance(f"SLOW QUERY: {duration_ms:.1f}ms - {sql[:100]}")

    @staticmethod
    def record_cache_hit(cache_name: str):
        """Record a cache hit."""
        with _metrics_lock:
            _metrics["cache_hits"][cache_name] += 1

    @staticmethod
    def record_cache_miss(cache_name: str):
        """Record a cache miss."""
        with _metrics_lock:
            _metrics["cache_misses"][cache_name] += 1

    @staticmethod
    def get_summary() -> dict:
        """Get performance summary."""
        with _metrics_lock:
            total_queries = sum(q["count"] for q in _metrics["queries"].values())
            total_slow = sum(q["slow_count"] for q in _metrics["queries"].values())
            total_cache_hits = sum(_metrics["cache_hits"].values())
            total_cache_misses = sum(_metrics["cache_misses"].values())
            total_cache_ops = total_cache_hits + total_cache_misses
            cache_hit_rate = (
                total_cache_hits / total_cache_ops if total_cache_ops > 0 else 0.0
            )

            # Calculate average query time
            total_time = sum(q["total_ms"] for q in _metrics["queries"].values())
            avg_query_time = total_time / total_queries if total_queries > 0 else 0.0

            return {
                "total_queries": total_queries,
                "slow_queries": total_slow,
                "avg_query_time_ms": round(avg_query_time, 2),
                "cache_hit_rate": round(cache_hit_rate, 3),
                "cache_hits": total_cache_hits,
                "cache_misses": total_cache_misses,
                "top_slow_queries": _metrics["slow_queries"][-10:],
            }

    @staticmethod
    def reset():
        """Reset all metrics."""
        with _metrics_lock:
            _metrics["queries"].clear()
            _metrics["cache_hits"].clear()
            _metrics["cache_misses"].clear()
            _metrics["slow_queries"].clear()


def timed(operation_name: str):
    """Decorator to time function execution and record metrics.

    Usage:
        @timed("memory_search")
        def memory_search(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000
                PerformanceMetrics.record_query(operation_name, duration_ms)

        return wrapper

    return decorator


@contextmanager
def timed_query(sql: str):
    """Context manager for timing database queries.

    Usage:
        with timed_query("SELECT ..."):
            cursor.execute(sql)
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        PerformanceMetrics.record_query(sql, duration_ms)


class QueryTimer:
    """Manual query timer for complex operations."""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time: Optional[float] = None
        self.duration_ms: Optional[float] = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        if self.start_time is not None:
            self.duration_ms = (time.perf_counter() - self.start_time) * 1000
            PerformanceMetrics.record_query(self.operation_name, self.duration_ms)

    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.duration_ms is not None:
            return self.duration_ms
        if self.start_time is not None:
            return (time.perf_counter() - self.start_time) * 1000
        return 0.0


def get_metrics() -> PerformanceMetrics:
    """Get the global PerformanceMetrics instance."""
    return PerformanceMetrics()


def log_summary():
    """Log performance summary."""
    summary = PerformanceMetrics.get_summary()
    _log_performance(f"PERFORMANCE SUMMARY: {summary}")
    return summary
