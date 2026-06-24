"""Unit tests for code parsers (tree-sitter based)."""

import sys
import pytest
from pathlib import Path

# Add mcp-server to path
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
def sample_python_file(tmp_path):
    """Create a sample Python file for testing."""
    code = '''
"""Module docstring."""

import os
from pathlib import Path

DB_PATH = Path("/tmp/test.db")

def open_db(with_vec: bool = False) -> "Connection":
    """Open database connection."""
    db = connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    return db

class MyClass(BaseClass):
    """A test class."""

    def method_one(self, arg: str) -> bool:
        """Do something."""
        result = open_db()
        return helper_func(result)

    def _private_method(self):
        pass

def helper_func(db):
    db.close()
    return True
'''
    f = tmp_path / "sample.py"
    f.write_text(code, encoding="utf-8")
    return f


@pytest.fixture
def sample_typescript_file(tmp_path):
    """Create a sample TypeScript file for testing."""
    code = '''
import { Request, Response } from "express";
import { Database } from "./db";

interface UserConfig {
    name: string;
    email: string;
}

export class UserService extends BaseService {
    private db: Database;

    constructor(db: Database) {
        super();
        this.db = db;
    }

    async getUser(id: string): Promise<UserConfig> {
        const result = await this.db.query("SELECT * FROM users WHERE id = ?", [id]);
        return transformUser(result);
    }
}

export function transformUser(raw: any): UserConfig {
    return { name: raw.name, email: raw.email };
}

export const fetchUsers = async (limit: number): Promise<UserConfig[]> => {
    const service = new UserService(getDb());
    return service.getAll(limit);
};

type UserId = string;
enum Role { Admin, User, Guest }
'''
    f = tmp_path / "sample.ts"
    f.write_text(code, encoding="utf-8")
    return f


@pytest.fixture
def sample_javascript_file(tmp_path):
    """Create a sample JavaScript file."""
    code = '''
const path = require("path");

function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}

class ShoppingCart {
    constructor() {
        this.items = [];
    }

    addItem(item) {
        this.items.push(item);
        return this;
    }

    getTotal() {
        return calculateTotal(this.items);
    }
}

module.exports = { ShoppingCart, calculateTotal };
'''
    f = tmp_path / "sample.js"
    f.write_text(code, encoding="utf-8")
    return f


class TestPythonParser:
    def test_parse_functions(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        assert not result.errors
        names = [s.name for s in result.symbols]
        assert "open_db" in names
        assert "helper_func" in names

    def test_parse_classes(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        classes = [s for s in result.symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_parse_methods(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        methods = [s for s in result.symbols if s.kind == "method"]
        assert len(methods) == 2
        method_names = {m.name for m in methods}
        assert "method_one" in method_names
        assert "_private_method" in method_names

    def test_qualified_names(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        qnames = {s.qualified_name for s in result.symbols}
        assert "MyClass.method_one" in qnames
        assert "MyClass._private_method" in qnames

    def test_signatures(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        open_db = [s for s in result.symbols if s.name == "open_db"][0]
        assert "def open_db" in open_db.signature
        assert "with_vec" in open_db.signature

    def test_docstrings(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        open_db = [s for s in result.symbols if s.name == "open_db"][0]
        assert open_db.docstring is not None
        assert "Open database" in open_db.docstring

    def test_imports(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        imports = [r for r in result.references if r.kind == "import"]
        import_names = {r.to_name for r in imports}
        assert "os" in import_names

    def test_calls(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        calls = [r for r in result.references if r.kind == "call"]
        call_names = {r.to_name for r in calls}
        assert "open_db" in call_names or "connect" in call_names

    def test_inheritance(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        inherits = [r for r in result.references if r.kind == "inherit"]
        assert len(inherits) >= 1
        assert any(r.to_name == "BaseClass" for r in inherits)

    def test_exported_flag(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        open_db = [s for s in result.symbols if s.name == "open_db"][0]
        assert open_db.exported is True

        private = [s for s in result.symbols if s.name == "_private_method"][0]
        assert private.exported is False

    def test_module_level_variables(self, sample_python_file):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file(sample_python_file)

        variables = [s for s in result.symbols if s.kind == "variable"]
        var_names = {v.name for v in variables}
        assert "DB_PATH" in var_names

    def test_large_file_skipped(self, tmp_path):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()

        # Create a file larger than 500KB
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 100_000, encoding="utf-8")

        result = parser.parse_file(large_file)
        assert len(result.errors) > 0
        assert "too large" in result.errors[0].lower()

    def test_nonexistent_file(self):
        from code.parsers.python_parser import PythonParser
        parser = PythonParser()
        result = parser.parse_file("/nonexistent/file.py")
        assert len(result.errors) > 0


class TestTypeScriptParser:
    def test_parse_functions(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        assert not result.errors
        func_names = {s.name for s in result.symbols if s.kind == "function"}
        assert "transformUser" in func_names

    def test_parse_classes(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        classes = [s for s in result.symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "UserService"

    def test_parse_interfaces(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        interfaces = [s for s in result.symbols if s.kind == "interface"]
        assert len(interfaces) == 1
        assert interfaces[0].name == "UserConfig"

    def test_parse_methods(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        methods = [s for s in result.symbols if s.kind == "method"]
        method_names = {m.name for m in methods}
        assert "getUser" in method_names

    def test_parse_arrow_functions(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        func_names = {s.name for s in result.symbols if s.kind == "function"}
        assert "fetchUsers" in func_names

    def test_parse_type_alias(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        types = [s for s in result.symbols if s.kind == "type_alias"]
        assert any(t.name == "UserId" for t in types)

    def test_parse_enum(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        enums = [s for s in result.symbols if s.kind == "enum"]
        assert any(e.name == "Role" for e in enums)

    def test_imports(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        imports = [r for r in result.references if r.kind == "import"]
        assert len(imports) >= 2

    def test_inheritance(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        inherits = [r for r in result.references if r.kind == "inherit"]
        assert any(r.to_name == "BaseService" for r in inherits)

    def test_calls(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        calls = [r for r in result.references if r.kind == "call"]
        call_names = {r.to_name for r in calls}
        assert "transformUser" in call_names

    def test_exported_flag(self, sample_typescript_file):
        from code.parsers.typescript_parser import TypeScriptParser
        parser = TypeScriptParser()
        result = parser.parse_file(sample_typescript_file)

        user_service = [s for s in result.symbols if s.name == "UserService"][0]
        assert user_service.exported is True


class TestJavaScriptParser:
    def test_parse_js(self, sample_javascript_file):
        from code.parsers.typescript_parser import JavaScriptParser
        parser = JavaScriptParser()
        result = parser.parse_file(sample_javascript_file)

        assert not result.errors
        names = {s.name for s in result.symbols}
        assert "calculateTotal" in names
        assert "ShoppingCart" in names

    def test_methods(self, sample_javascript_file):
        from code.parsers.typescript_parser import JavaScriptParser
        parser = JavaScriptParser()
        result = parser.parse_file(sample_javascript_file)

        methods = [s for s in result.symbols if s.kind == "method"]
        method_names = {m.name for m in methods}
        assert "addItem" in method_names
        assert "getTotal" in method_names

    def test_calls_in_methods(self, sample_javascript_file):
        from code.parsers.typescript_parser import JavaScriptParser
        parser = JavaScriptParser()
        result = parser.parse_file(sample_javascript_file)

        calls = [r for r in result.references if r.kind == "call"]
        call_names = {r.to_name for r in calls}
        assert "calculateTotal" in call_names


class TestRegistry:
    def test_supported_extensions(self):
        from code.parsers.registry import SUPPORTED_EXTENSIONS
        assert ".py" in SUPPORTED_EXTENSIONS
        assert ".ts" in SUPPORTED_EXTENSIONS
        assert ".tsx" in SUPPORTED_EXTENSIONS
        assert ".js" in SUPPORTED_EXTENSIONS
        assert ".jsx" in SUPPORTED_EXTENSIONS

    def test_get_parser_python(self):
        from code.parsers.registry import get_parser
        parser = get_parser(".py")
        assert parser is not None
        assert parser.language == "python"

    def test_get_parser_typescript(self):
        from code.parsers.registry import get_parser
        parser = get_parser(".ts")
        assert parser is not None
        assert parser.language == "typescript"

    def test_get_parser_javascript(self):
        from code.parsers.registry import get_parser
        parser = get_parser(".js")
        assert parser is not None
        assert parser.language == "javascript"

    def test_get_parser_unsupported(self):
        from code.parsers.registry import get_parser
        parser = get_parser(".cpp")
        assert parser is None

    def test_parser_caching(self):
        from code.parsers.registry import get_parser
        p1 = get_parser(".py")
        p2 = get_parser(".py")
        assert p1 is p2
