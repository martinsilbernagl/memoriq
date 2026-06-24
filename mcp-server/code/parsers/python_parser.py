"""Python parser using tree-sitter.

Extracts: functions, classes, methods, decorators, imports, calls, inheritance.
"""

from __future__ import annotations

from .base import BaseParser, Symbol, Reference, ParseResult


class PythonParser(BaseParser):
    language = "python"
    ts_language = "python"

    def _extract(self, root_node, source: bytes, result: ParseResult) -> None:
        self._walk(root_node, source, result, parent_name=None)

    def _walk(self, node, source: bytes, result: ParseResult,
              parent_name: str | None) -> None:
        """Recursively walk AST nodes."""

        if node.type == "function_definition":
            self._extract_function(node, source, result, parent_name)
        elif node.type == "class_definition":
            self._extract_class(node, source, result, parent_name)
        elif node.type == "decorated_definition":
            self._extract_decorated(node, source, result, parent_name)
        elif node.type == "import_statement":
            self._extract_import(node, source, result, parent_name)
        elif node.type == "import_from_statement":
            self._extract_from_import(node, source, result, parent_name)
        elif node.type == "call":
            self._extract_call(node, source, result, parent_name)
        elif node.type == "assignment":
            # Module-level assignments could be important variables
            if parent_name is None and node.parent and node.parent.type == "module":
                self._extract_assignment(node, source, result)
            # Always recurse into assignment children to catch calls on RHS
            for child in node.children:
                self._walk(child, source, result, parent_name)
        else:
            # Recurse into children
            for child in node.children:
                self._walk(child, source, result, parent_name)

    def _extract_function(self, node, source: bytes, result: ParseResult,
                          parent_name: str | None) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        kind = "method" if parent_name else "function"
        qname = f"{parent_name}.{name}" if parent_name else name

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"
        signature = f"def {name}{sig}"

        # Return type
        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            signature += f" -> {self._node_text(ret_node, source)}"

        # Docstring
        docstring = self._extract_docstring(node, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=signature,
            docstring=docstring,
            exported=not name.startswith("_"),
        ))

        # Walk body for nested calls/imports
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname)

    def _extract_class(self, node, source: bytes, result: ParseResult,
                       parent_name: str | None) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        # Base classes → inheritance references
        superclasses = node.child_by_field_name("superclasses")
        if superclasses:
            for arg in superclasses.children:
                if arg.type in ("identifier", "attribute"):
                    base_name = self._node_text(arg, source)
                    result.references.append(Reference(
                        from_symbol=qname,
                        to_name=base_name,
                        kind="inherit",
                        line=arg.start_point[0] + 1,
                        confidence=0.8,
                    ))

        docstring = self._extract_docstring(node, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="class",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=f"class {name}",
            docstring=docstring,
            exported=not name.startswith("_"),
        ))

        # Walk body for methods
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname)

    def _extract_decorated(self, node, source: bytes, result: ParseResult,
                           parent_name: str | None) -> None:
        """Handle decorated definitions — extract decorator refs then process the definition."""
        for child in node.children:
            if child.type == "decorator":
                # Extract decorator name as a reference
                for deco_child in child.children:
                    if deco_child.type in ("identifier", "attribute", "call"):
                        if deco_child.type == "call":
                            func = deco_child.child_by_field_name("function")
                            if func:
                                deco_name = self._node_text(func, source)
                            else:
                                continue
                        else:
                            deco_name = self._node_text(deco_child, source)
                        result.references.append(Reference(
                            from_symbol=parent_name,
                            to_name=deco_name,
                            kind="decorator",
                            line=child.start_point[0] + 1,
                            confidence=0.85,
                        ))
                        break
            elif child.type in ("function_definition", "class_definition"):
                self._walk(child, source, result, parent_name)

    def _extract_import(self, node, source: bytes, result: ParseResult,
                        parent_name: str | None) -> None:
        """Handle `import X` statements."""
        for child in node.children:
            if child.type == "dotted_name":
                mod_name = self._node_text(child, source)
                result.references.append(Reference(
                    from_symbol=parent_name,
                    to_name=mod_name,
                    kind="import",
                    line=node.start_point[0] + 1,
                    confidence=0.9,
                ))

    def _extract_from_import(self, node, source: bytes, result: ParseResult,
                             parent_name: str | None) -> None:
        """Handle `from X import Y` statements."""
        module_name = None
        for child in node.children:
            if child.type in ("dotted_name", "relative_import"):
                module_name = self._node_text(child, source)

        # Extract imported names
        for child in node.children:
            if child.type == "import_prefix":
                continue
            if child.type == "dotted_name" and child == node.children[1]:
                continue  # This is the module name
            if child.type in ("dotted_name", "aliased_import"):
                if child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    imported = self._node_text(name_node, source) if name_node else ""
                else:
                    imported = self._node_text(child, source)

                if imported and imported not in ("import", "from"):
                    full_name = f"{module_name}.{imported}" if module_name else imported
                    result.references.append(Reference(
                        from_symbol=parent_name,
                        to_name=full_name,
                        kind="import",
                        line=node.start_point[0] + 1,
                        confidence=0.9,
                    ))

    def _extract_call(self, node, source: bytes, result: ParseResult,
                      parent_name: str | None) -> None:
        """Extract function/method call references."""
        func_node = node.child_by_field_name("function")
        if not func_node:
            return

        call_name = self._node_text(func_node, source)

        # Skip very common builtins that add noise
        if call_name in ("print", "len", "str", "int", "float", "bool", "list",
                         "dict", "set", "tuple", "type", "isinstance", "range",
                         "enumerate", "zip", "map", "filter", "sorted", "reversed",
                         "super", "repr", "hasattr", "getattr", "setattr"):
            return

        result.references.append(Reference(
            from_symbol=parent_name,
            to_name=call_name,
            kind="call",
            line=node.start_point[0] + 1,
            confidence=0.7,
        ))

        # Don't recurse into call arguments here — parent walk handles that
        # But we do need to walk arguments for nested calls
        args = node.child_by_field_name("arguments")
        if args:
            for child in args.children:
                self._walk(child, source, result, parent_name)

    def _extract_assignment(self, node, source: bytes, result: ParseResult) -> None:
        """Extract module-level variable assignments (e.g. constants, type aliases)."""
        left = node.child_by_field_name("left")
        if not left or left.type != "identifier":
            return

        name = self._node_text(left, source)
        if not name:
            return
        # Only track ALL_CAPS constants or type aliases
        if not name.isupper() and not name[0].isupper():
            return

        result.symbols.append(Symbol(
            name=name,
            qualified_name=name,
            kind="variable",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            exported=not name.startswith("_"),
        ))

    def _extract_docstring(self, node, source: bytes) -> str | None:
        """Extract docstring from function/class body."""
        body = node.child_by_field_name("body")
        if not body or not body.children:
            return None

        first = body.children[0]

        # tree-sitter may represent docstrings as:
        # 1. expression_statement > string (older tree-sitter)
        # 2. string directly in body (newer tree-sitter-language-pack)
        doc_node = None
        if first.type == "expression_statement" and first.children:
            expr = first.children[0]
            if expr.type == "string":
                doc_node = expr
        elif first.type == "string":
            doc_node = first

        if doc_node:
            doc = self._node_text(doc_node, source)
            # Strip quotes
            for q in ('"""', "'''", '"', "'"):
                if doc.startswith(q) and doc.endswith(q):
                    doc = doc[len(q):-len(q)]
                    break
            return doc.strip()[:500]  # Cap at 500 chars
        return None
