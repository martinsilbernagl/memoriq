"""Tests for health check module."""

import pytest
from pathlib import Path
import sys
import sqlite3

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))

from health import (
    run_health_check,
    check_mcp_server,
    check_database,
    HealthStatus
)


class TestHealthCheck:
    def test_health_status_dataclass(self):
        status = HealthStatus(
            healthy=True,
            mcp_server=True,
            database=True,
            database_writable=True,
            session_valid=True,
            vector_search=False,
            errors=[]
        )
        assert status.healthy is True
        assert status.to_dict()["healthy"] is True

    def test_check_mcp_server(self):
        ok, err = check_mcp_server()
        assert isinstance(ok, bool)
        assert err is None or isinstance(err, str)

    def test_check_database(self, tmp_path):
        import health
        original_path = health.DB_PATH

        try:
            test_db = tmp_path / "test.db"
            health.DB_PATH = test_db

            ok, err = check_database()
            assert ok is False
            assert "not found" in err.lower()

            conn = sqlite3.connect(str(test_db))
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.close()

            ok, err = check_database()
            assert ok is True
            assert err is None
        finally:
            health.DB_PATH = original_path

    def test_run_health_check_returns_status(self):
        status = run_health_check()
        assert isinstance(status, HealthStatus)
        assert hasattr(status, 'healthy')
        assert hasattr(status, 'errors')
