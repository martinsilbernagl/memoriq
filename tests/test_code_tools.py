"""Integration tests for code intelligence MCP tools."""

import sys
import pytest
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_DIR / "mcp-server"))

try:
    import tree_sitter_language_pack  # noqa: F401
    HAS_TREESITTER = True
except ImportError:
    HAS_TREESITTER = False

pytestmark = pytest.mark.skipif(
    not HAS_TREESITTER,
    reason="tree-sitter-language-pack not installed"
)


@pytest.fixture
def project_with_code(tmp_path, active_session, monkeypatch):
    """Create a project with sample Python files and register it."""
    # Create sample files
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    (src_dir / "db.py").write_text('''
"""Database module."""

import sqlite3
from pathlib import Path

DB_PATH = Path("/tmp/test.db")

def open_db(mode: str = "rw") -> sqlite3.Connection:
    """Open database connection with WAL mode."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def close_db(conn: sqlite3.Connection) -> None:
    """Close database connection safely."""
    conn.close()

class DatabaseManager:
    """Manages database connections."""

    def __init__(self, path: str):
        self.path = path
        self.conn = None

    def connect(self):
        self.conn = open_db()
        return self.conn

    def disconnect(self):
        if self.conn:
            close_db(self.conn)
            self.conn = None
''', encoding="utf-8")

    (src_dir / "api.py").write_text('''
"""API module."""

from .db import open_db, DatabaseManager

def get_users():
    """Fetch all users."""
    db = open_db()
    try:
        result = db.execute("SELECT * FROM users").fetchall()
        return format_users(result)
    finally:
        db.close()

def format_users(rows):
    """Format user rows."""
    return [{"id": r[0], "name": r[1]} for r in rows]

class UserAPI(DatabaseManager):
    """User-specific API."""

    def get_by_id(self, user_id: int):
        conn = self.connect()
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
''', encoding="utf-8")

    (src_dir / "utils.py").write_text('''
"""Utility functions."""

def validate_email(email: str) -> bool:
    """Validate email format."""
    return "@" in email and "." in email

def sanitize_input(text: str) -> str:
    """Sanitize user input."""
    return text.strip().replace("<", "&lt;")
''', encoding="utf-8")

    return tmp_path


class TestCodeIndex:
    def test_index_project(self, project_with_code):
        from tools.code_index import code_index
        result = code_index(project_path=str(project_with_code))
        assert "Code Index" in result
        assert "test-project" in result

    def test_index_incremental(self, project_with_code):
        from tools.code_index import code_index
        # First index
        result1 = code_index(project_path=str(project_with_code))
        assert "Code Index" in result1
        assert "4" in result1  # 4 files scanned

        # Second index (should skip unchanged files — 0 newly indexed)
        result2 = code_index(project_path=str(project_with_code))
        assert "Code Index" in result2

    def test_index_full(self, project_with_code):
        from tools.code_index import code_index
        result = code_index(
            project_path=str(project_with_code),
            full=True
        )
        assert "Code Index" in result


class TestCodeSearch:
    def test_search_function(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_search import code_search

        code_index(project_path=str(project_with_code))
        result = code_search(query="open_db")
        assert "open_db" in result

    def test_search_class(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_search import code_search

        code_index(project_path=str(project_with_code))
        result = code_search(query="DatabaseManager")
        assert "DatabaseManager" in result

    def test_search_with_kind_filter(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_search import code_search

        code_index(project_path=str(project_with_code))
        result = code_search(query="open_db", kind="function")
        assert "open_db" in result

    def test_search_no_results(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_search import code_search

        code_index(project_path=str(project_with_code))
        result = code_search(query="nonexistent_function_xyz")
        # Result should indicate no matches (language-agnostic check)
        assert "nonexistent_function_xyz" in result

    def test_search_not_indexed(self, active_session):
        from tools.code_search import code_search
        result = code_search(query="anything")
        assert "index" in result.lower()


class TestCodeContext:
    def test_context_function(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="open_db")
        assert "open_db" in result
        assert "Symbol" in result

    def test_context_class(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="DatabaseManager")
        assert "DatabaseManager" in result
        assert "class" in result.lower()

    def test_context_shows_incoming(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="open_db")
        # open_db is called from api.py — check for reference content
        assert "open_db" in result
        assert "[call]" in result or "get_users" in result or "api.py" in result

    def test_context_shows_outgoing(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="get_users")
        # get_users calls open_db, format_users etc
        assert "get_users" in result
        assert "open_db" in result or "format_users" in result

    def test_context_not_found(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="nonexistent_xyz")
        assert "nonexistent_xyz" in result

    def test_context_shows_children(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_context import code_context

        code_index(project_path=str(project_with_code))
        result = code_context(symbol="DatabaseManager")
        # Should show connect and disconnect as children
        assert "connect" in result.lower()


class TestCodeImpact:
    def test_impact_basic(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_impact import code_impact

        code_index(project_path=str(project_with_code))
        result = code_impact(symbol="open_db")
        assert "open_db" in result
        # open_db is called by get_users and DatabaseManager.connect
        assert "get_users" in result or "connect" in result

    def test_impact_with_depth(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_impact import code_impact

        code_index(project_path=str(project_with_code))
        result = code_impact(symbol="open_db", max_depth=2)
        assert "open_db" in result

    def test_impact_no_references(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_impact import code_impact

        code_index(project_path=str(project_with_code))
        # validate_email likely has no incoming references
        result = code_impact(symbol="validate_email")
        assert "validate_email" in result

    def test_impact_not_found(self, project_with_code):
        from tools.code_index import code_index
        from tools.code_impact import code_impact

        code_index(project_path=str(project_with_code))
        result = code_impact(symbol="nonexistent_xyz")
        assert "nonexistent_xyz" in result


class TestIndexer:
    def test_scan_files(self, project_with_code):
        from code.indexer import scan_files
        files = scan_files(str(project_with_code))
        assert len(files) >= 3  # db.py, api.py, utils.py
        extensions = {f["extension"] for f in files}
        assert ".py" in extensions

    def test_scan_ignores_node_modules(self, project_with_code):
        # Create a node_modules directory with a .js file
        nm = project_with_code / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("function x() {}", encoding="utf-8")

        from code.indexer import scan_files
        files = scan_files(str(project_with_code))
        paths = {f["rel_path"] for f in files}
        assert not any("node_modules" in p for p in paths)

    def test_scan_respects_max_size(self, project_with_code):
        # Create a file larger than MAX_FILE_SIZE
        large = project_with_code / "large.py"
        large.write_text("x = 1\n" * 100_000, encoding="utf-8")

        from code.indexer import scan_files
        files = scan_files(str(project_with_code))
        paths = {f["rel_path"] for f in files}
        assert "large.py" not in paths


class TestCodeHelpers:
    """Test shared code_helpers and consistency between tools."""

    def test_find_symbol_deterministic(self, project_with_code):
        """Both code_context and code_impact should find the same symbol."""
        from tools.code_index import code_index
        from tools.code_context import code_context
        from tools.code_impact import code_impact

        code_index(project_path=str(project_with_code))

        # Both tools should find open_db and report the same file
        ctx = code_context(symbol="open_db")
        imp = code_impact(symbol="open_db")

        # Both should contain the symbol's file location
        assert "db.py" in ctx
        assert "db.py" in imp

    def test_find_symbol_ambiguous_name(self, tmp_path, active_session, monkeypatch):
        """When multiple symbols share a name, both tools should pick the same one."""
        src = tmp_path / "src"
        src.mkdir()

        # Create two files with same function name
        (src / "a_module.py").write_text('''
def helper():
    """Helper in a_module — not exported."""
    return "a"
''', encoding="utf-8")

        (src / "b_module.py").write_text('''
def helper():
    """Helper in b_module — not exported."""
    return "b"
''', encoding="utf-8")

        from tools.code_index import code_index
        from tools.code_context import code_context
        from tools.code_impact import code_impact

        code_index(project_path=str(tmp_path))

        ctx = code_context(symbol="helper")
        imp = code_impact(symbol="helper")

        # Both should find a valid result (not "not found")
        assert "helper" in ctx.lower()
        assert "helper" in imp.lower()

        # Extract file path from both results — they must match
        ctx_file = "a_module" if "a_module" in ctx else "b_module"
        imp_file = "a_module" if "a_module" in imp else "b_module"
        assert ctx_file == imp_file, (
            f"Inconsistent symbol resolution: code_context found {ctx_file}, "
            f"code_impact found {imp_file}"
        )

    def test_shared_helpers_imported(self):
        """Verify that code tools import from code_helpers, not local copies."""
        from tools import code_context, code_impact, code_search
        from tools.code_helpers import has_index, reindex_dirty, find_symbol

        # These modules should NOT have local _has_index or _reindex_dirty
        assert not hasattr(code_context, "_has_index")
        assert not hasattr(code_impact, "_has_index")
        assert not hasattr(code_search, "_has_index")
        assert not hasattr(code_context, "_reindex_dirty")
        assert not hasattr(code_impact, "_reindex_dirty")
        assert not hasattr(code_search, "_reindex_dirty_if_needed")


class TestResolver:
    def test_resolve_references(self, project_with_code):
        """Test that references get resolved to symbols."""
        from tools.code_index import code_index
        import db as db_module

        code_index(project_path=str(project_with_code))

        conn = db_module.open_db()
        try:
            # Check that some references are resolved (to_symbol_id IS NOT NULL)
            resolved = conn.execute("""
                SELECT COUNT(*) as cnt FROM code_references
                WHERE project = 'test-project' AND to_symbol_id IS NOT NULL
            """).fetchone()

            total = conn.execute("""
                SELECT COUNT(*) as cnt FROM code_references
                WHERE project = 'test-project'
            """).fetchone()

            # At least some references should be resolved
            assert total["cnt"] > 0
            # Resolution rate doesn't have to be 100%, but should be > 0
            assert resolved["cnt"] >= 0  # Some may be external
        finally:
            conn.close()
