"""Parser registry — maps file extensions to parsers."""

from __future__ import annotations

from .base import BaseParser


# Lazy-loaded parser instances
_parsers: dict[str, BaseParser] = {}

# Extension → (parser_class_path, language)
_REGISTRY: dict[str, tuple[str, str]] = {
    ".py": ("code.parsers.python_parser.PythonParser", "python"),
    ".ts": ("code.parsers.typescript_parser.TypeScriptParser", "typescript"),
    ".tsx": ("code.parsers.typescript_parser.TypeScriptParser", "typescript"),
    ".js": ("code.parsers.typescript_parser.JavaScriptParser", "javascript"),
    ".jsx": ("code.parsers.typescript_parser.JavaScriptParser", "javascript"),
    ".mjs": ("code.parsers.typescript_parser.JavaScriptParser", "javascript"),
    ".cjs": ("code.parsers.typescript_parser.JavaScriptParser", "javascript"),
    ".go": ("code.parsers.go_parser.GoParser", "go"),
    ".rs": ("code.parsers.rust_parser.RustParser", "rust"),
}

SUPPORTED_EXTENSIONS = set(_REGISTRY.keys())


def get_parser(extension: str) -> BaseParser | None:
    """Get parser for a file extension. Returns None if unsupported.

    Parsers are lazily instantiated and cached.
    """
    if extension not in _REGISTRY:
        return None

    if extension not in _parsers:
        class_path, language = _REGISTRY[extension]
        module_path, class_name = class_path.rsplit(".", 1)

        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        _parsers[extension] = cls()

    return _parsers[extension]


def get_language(extension: str) -> str | None:
    """Get language name for a file extension."""
    entry = _REGISTRY.get(extension)
    return entry[1] if entry else None
