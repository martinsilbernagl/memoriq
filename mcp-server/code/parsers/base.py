"""Base parser ABC and data classes for code intelligence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Symbol:
    """A code symbol (function, class, method, interface, etc.)."""
    name: str
    qualified_name: str
    kind: str  # function, class, method, interface, variable, type_alias, enum, module
    line_start: int
    line_end: int
    parent_name: str | None = None
    signature: str | None = None
    docstring: str | None = None
    exported: bool = False
    # Complexity metrics (v2)
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    lines_of_code: int = 0


@dataclass
class Reference:
    """A reference from one symbol to another (call, import, etc.)."""
    from_symbol: str | None  # qualified_name of the source symbol (None = module level)
    to_name: str  # name being referenced
    kind: str  # call, import, inherit, implement, type_ref, decorator
    line: int
    confidence: float = 0.5


@dataclass
class ParseResult:
    """Result of parsing a single file."""
    file_path: str
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract base class for language-specific parsers."""

    # Subclasses must set this
    language: str = ""
    # tree-sitter language name (e.g. "python", "typescript")
    ts_language: str = ""

    def __init__(self):
        self._parser = None
        self._ts_lang = None

    def _ensure_parser(self):
        """Lazy-init tree-sitter parser."""
        if self._parser is not None:
            return

        try:
            import tree_sitter_language_pack as tslp
        except ImportError:
            raise ImportError(
                "tree-sitter-language-pack is not installed. "
                "Run: pip install tree-sitter-language-pack"
            )

        self._ts_lang = tslp.get_language(self.ts_language)
        self._parser = tslp.get_parser(self.ts_language)

    def parse_file(self, file_path: str | Path) -> ParseResult:
        """Parse a file and extract symbols + references.

        Returns ParseResult even on errors (with error messages in .errors).
        """
        file_path = Path(file_path)
        result = ParseResult(
            file_path=str(file_path),
            language=self.language,
        )

        try:
            source = file_path.read_bytes()
        except (OSError, IOError) as e:
            result.errors.append(f"Cannot read file: {e}")
            return result

        # Skip very large files (>500KB)
        if len(source) > 512_000:
            result.errors.append(f"File too large ({len(source)} bytes), skipping")
            return result

        try:
            self._ensure_parser()
            tree = self._parser.parse(source)
            self._extract(tree.root_node, source, result)
        except ImportError as e:
            result.errors.append(str(e))
        except Exception as e:
            result.errors.append(f"Parse error: {e}")

        return result

    @abstractmethod
    def _extract(self, root_node, source: bytes, result: ParseResult) -> None:
        """Extract symbols and references from tree-sitter AST.

        Subclasses implement this to walk the AST and populate result.symbols
        and result.references.
        """
        ...

    def _node_text(self, node, source: bytes) -> str:
        """Get text content of a tree-sitter node."""
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
