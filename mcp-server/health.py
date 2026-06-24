"""Health check system for Memoriq.

Validates that all components are functional before operations.
"""

import json
import sqlite3
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

MEMORIQ_HOME = Path.home() / ".memoriq"
DB_PATH = MEMORIQ_HOME / "memory.db"


@dataclass
class HealthStatus:
    """Health check results."""
    healthy: bool
    mcp_server: bool
    database: bool
    database_writable: bool
    session_valid: bool
    vector_search: bool
    errors: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def check_mcp_server() -> tuple[bool, Optional[str]]:
    """Check if MCP server dependencies are available."""
    try:
        import mcp
        return True, None
    except ImportError as e:
        return False, f"MCP module not installed: {e}"


def check_database() -> tuple[bool, Optional[str]]:
    """Check if database exists and is accessible."""
    if not DB_PATH.exists():
        return False, f"Database not found at {DB_PATH}"

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        return True, None
    except sqlite3.Error as e:
        return False, f"Database error: {e}"


def check_database_writable() -> tuple[bool, Optional[str]]:
    """Check if database is writable."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
        conn.close()
        return True, None
    except sqlite3.Error as e:
        return False, f"Database not writable: {e}"


def check_session() -> tuple[bool, Optional[str]]:
    """Check if active session exists and is valid."""
    session_file = MEMORIQ_HOME / "active_session.json"

    if not session_file.exists():
        return False, "No active session file found"

    try:
        data = json.loads(session_file.read_text())
        required = ["session_id", "project", "project_path"]
        for field in required:
            if field not in data:
                return False, f"Session missing field: {field}"
        return True, None
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Session file error: {e}"


def check_vector_search() -> tuple[bool, Optional[str]]:
    """Check if vector search is available."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.execute("SELECT vec_version()")
        conn.close()
        return True, None
    except Exception:
        # Vector search is optional
        return False, "Vector search not available (optional)"


def run_health_check() -> HealthStatus:
    """Run all health checks and return status."""
    errors = []

    mcp_ok, mcp_err = check_mcp_server()
    if mcp_err:
        errors.append(mcp_err)

    db_ok, db_err = check_database()
    if db_err:
        errors.append(db_err)

    db_write_ok, db_write_err = check_database_writable()
    if db_write_err:
        errors.append(db_write_err)

    session_ok, session_err = check_session()
    if session_err:
        errors.append(session_err)

    vec_ok, vec_err = check_vector_search()
    # Vector is optional, so we don't add to errors if it fails

    healthy = mcp_ok and db_ok and db_write_ok and session_ok

    return HealthStatus(
        healthy=healthy,
        mcp_server=mcp_ok,
        database=db_ok,
        database_writable=db_write_ok,
        session_valid=session_ok,
        vector_search=vec_ok,
        errors=errors
    )


def print_health_report():
    """Print health report to stderr."""
    status = run_health_check()

    print("\n=== Memoriq Health Check ===", file=sys.stderr)
    print(f"Overall: {'HEALTHY' if status.healthy else 'UNHEALTHY'}", file=sys.stderr)
    print(f"  MCP Server: {'OK' if status.mcp_server else 'FAIL'}", file=sys.stderr)
    print(f"  Database: {'OK' if status.database else 'FAIL'}", file=sys.stderr)
    print(f"  DB Writable: {'OK' if status.database_writable else 'FAIL'}", file=sys.stderr)
    print(f"  Session: {'OK' if status.session_valid else 'FAIL'}", file=sys.stderr)
    print(f"  Vector Search: {'OK' if status.vector_search else 'OFF'}", file=sys.stderr)

    if status.errors:
        print("\nErrors:", file=sys.stderr)
        for err in status.errors:
            print(f"  - {err}", file=sys.stderr)

    print("================================\n", file=sys.stderr)

    return status.healthy


if __name__ == "__main__":
    healthy = print_health_report()
    sys.exit(0 if healthy else 1)
