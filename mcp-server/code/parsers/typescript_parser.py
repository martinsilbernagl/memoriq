"""TypeScript/JavaScript parser using tree-sitter.

Extracts: functions, classes, methods, interfaces, imports, calls, inheritance, type refs.
"""

from __future__ import annotations

from .base import BaseParser, Symbol, Reference, ParseResult


class TypeScriptParser(BaseParser):
    language = "typescript"
    ts_language = "typescript"

    def _extract(self, root_node, source: bytes, result: ParseResult) -> None:
        self._walk(root_node, source, result, parent_name=None)

    def _walk(self, node, source: bytes, result: ParseResult,
              parent_name: str | None) -> None:
        ntype = node.type

        if ntype == "function_declaration":
            self._extract_function(node, source, result, parent_name)
        elif ntype == "class_declaration":
            self._extract_class(node, source, result, parent_name)
        elif ntype in ("method_definition", "public_field_definition"):
            if parent_name:
                self._extract_method(node, source, result, parent_name)
        elif ntype == "interface_declaration":
            self._extract_interface(node, source, result, parent_name)
        elif ntype == "type_alias_declaration":
            self._extract_type_alias(node, source, result, parent_name)
        elif ntype == "enum_declaration":
            self._extract_enum(node, source, result, parent_name)
        elif ntype in ("import_statement", "import_clause"):
            self._extract_import(node, source, result, parent_name)
        elif ntype == "call_expression":
            self._extract_call(node, source, result, parent_name)
        elif ntype == "arrow_function" and parent_name is None:
            # Top-level arrow functions assigned to variables
            pass  # Handled by variable_declarator
        elif ntype == "lexical_declaration" or ntype == "variable_declaration":
            self._extract_variable_decl(node, source, result, parent_name)
        elif ntype in ("export_statement",):
            self._extract_export(node, source, result, parent_name)
        else:
            for child in node.children:
                self._walk(child, source, result, parent_name)

    def _extract_function(self, node, source: bytes, result: ParseResult,
                          parent_name: str | None, exported: bool = False) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"
        signature = f"function {name}{sig}"

        ret = node.child_by_field_name("return_type")
        if ret:
            signature += f": {self._node_text(ret, source)}"

        # JSDoc
        docstring = self._extract_jsdoc(node, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="function",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=signature,
            docstring=docstring,
            exported=exported,
        ))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname)

    def _extract_class(self, node, source: bytes, result: ParseResult,
                       parent_name: str | None, exported: bool = False) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        # Heritage: extends, implements
        for child in node.children:
            if child.type == "class_heritage":
                self._extract_heritage(child, source, result, qname)

        docstring = self._extract_jsdoc(node, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="class",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=f"class {name}",
            docstring=docstring,
            exported=exported,
        ))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname)

    def _extract_method(self, node, source: bytes, result: ParseResult,
                        parent_name: str) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}"

        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"
        signature = f"{name}{sig}"

        ret = node.child_by_field_name("return_type")
        if ret:
            signature += f": {self._node_text(ret, source)}"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="method",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=signature,
            exported=True,
        ))

        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname)

    def _extract_interface(self, node, source: bytes, result: ParseResult,
                           parent_name: str | None, exported: bool = False) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        docstring = self._extract_jsdoc(node, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="interface",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=f"interface {name}",
            docstring=docstring,
            exported=exported,
        ))

        # Check for extends
        for child in node.children:
            if child.type == "extends_type_clause":
                for tc in child.children:
                    if tc.type in ("type_identifier", "generic_type"):
                        type_name = self._node_text(tc, source).split("<")[0]
                        result.references.append(Reference(
                            from_symbol=qname,
                            to_name=type_name,
                            kind="inherit",
                            line=tc.start_point[0] + 1,
                            confidence=0.85,
                        ))

    def _extract_type_alias(self, node, source: bytes, result: ParseResult,
                            parent_name: str | None, exported: bool = False) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="type_alias",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=f"type {name}",
            exported=exported,
        ))

    def _extract_enum(self, node, source: bytes, result: ParseResult,
                      parent_name: str | None, exported: bool = False) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{parent_name}.{name}" if parent_name else name

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="enum",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=f"enum {name}",
            exported=exported,
        ))

    def _extract_heritage(self, node, source: bytes, result: ParseResult,
                          qname: str) -> None:
        """Extract extends/implements from class heritage.

        AST structure: class_heritage > extends_clause/implements_clause > identifier/type_identifier
        """
        for child in node.children:
            if child.type == "extends_clause":
                self._extract_heritage_clause(child, source, result, qname, "inherit")
            elif child.type == "implements_clause":
                self._extract_heritage_clause(child, source, result, qname, "implement")
            elif child.type in ("type_identifier", "identifier", "generic_type"):
                # Direct child (fallback for different tree-sitter versions)
                type_name = self._node_text(child, source).split("<")[0]
                if type_name not in ("extends", "implements"):
                    result.references.append(Reference(
                        from_symbol=qname,
                        to_name=type_name,
                        kind="inherit",
                        line=child.start_point[0] + 1,
                        confidence=0.85,
                    ))

    def _extract_heritage_clause(self, node, source: bytes, result: ParseResult,
                                 qname: str, kind: str) -> None:
        """Extract type references from extends_clause or implements_clause."""
        for child in node.children:
            if child.type in ("type_identifier", "identifier", "generic_type",
                              "member_expression"):
                type_name = self._node_text(child, source).split("<")[0]
                if type_name not in ("extends", "implements"):
                    result.references.append(Reference(
                        from_symbol=qname,
                        to_name=type_name,
                        kind=kind,
                        line=child.start_point[0] + 1,
                        confidence=0.85,
                    ))

    def _extract_import(self, node, source: bytes, result: ParseResult,
                        parent_name: str | None) -> None:
        """Extract import statements."""
        source_node = node.child_by_field_name("source")
        if not source_node:
            # Walk children for nested import clauses
            for child in node.children:
                if child.type == "import_clause":
                    self._extract_import(child, source, result, parent_name)
                elif child.type == "string" or child.type == "string_fragment":
                    mod = self._node_text(child, source).strip("'\"")
                    result.references.append(Reference(
                        from_symbol=parent_name,
                        to_name=mod,
                        kind="import",
                        line=node.start_point[0] + 1,
                        confidence=0.9,
                    ))
            return

        mod = self._node_text(source_node, source).strip("'\"")

        # Find imported names
        found_names = False
        for child in node.children:
            if child.type == "import_clause":
                for clause_child in child.children:
                    if clause_child.type == "named_imports":
                        for spec in clause_child.children:
                            if spec.type == "import_specifier":
                                name_node = spec.child_by_field_name("name")
                                if name_node:
                                    imported = self._node_text(name_node, source)
                                    result.references.append(Reference(
                                        from_symbol=parent_name,
                                        to_name=f"{mod}.{imported}",
                                        kind="import",
                                        line=node.start_point[0] + 1,
                                        confidence=0.9,
                                    ))
                                    found_names = True
                    elif clause_child.type == "identifier":
                        # Default import
                        result.references.append(Reference(
                            from_symbol=parent_name,
                            to_name=mod,
                            kind="import",
                            line=node.start_point[0] + 1,
                            confidence=0.9,
                        ))
                        found_names = True

        if not found_names:
            result.references.append(Reference(
                from_symbol=parent_name,
                to_name=mod,
                kind="import",
                line=node.start_point[0] + 1,
                confidence=0.9,
            ))

    def _extract_call(self, node, source: bytes, result: ParseResult,
                      parent_name: str | None) -> None:
        func_node = node.child_by_field_name("function")
        if not func_node:
            return

        call_name = self._node_text(func_node, source)

        # Skip very common builtins
        if call_name in ("console.log", "console.error", "console.warn",
                         "JSON.stringify", "JSON.parse", "parseInt", "parseFloat",
                         "Array.isArray", "Object.keys", "Object.values",
                         "Object.entries", "Promise.resolve", "Promise.all",
                         "require"):
            return

        result.references.append(Reference(
            from_symbol=parent_name,
            to_name=call_name,
            kind="call",
            line=node.start_point[0] + 1,
            confidence=0.7,
        ))

        # Walk arguments for nested calls
        args = node.child_by_field_name("arguments")
        if args:
            for child in args.children:
                self._walk(child, source, result, parent_name)

    def _extract_variable_decl(self, node, source: bytes, result: ParseResult,
                               parent_name: str | None, exported: bool = False) -> None:
        """Extract const/let/var declarations — especially arrow function assignments."""
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")

                if not name_node or not value_node:
                    continue

                name = self._node_text(name_node, source)

                if value_node.type == "arrow_function":
                    qname = f"{parent_name}.{name}" if parent_name else name
                    params_node = value_node.child_by_field_name("parameters")
                    if params_node:
                        sig = self._node_text(params_node, source)
                    else:
                        # Single param without parens
                        param = value_node.child_by_field_name("parameter")
                        sig = f"({self._node_text(param, source)})" if param else "()"

                    signature = f"const {name} = {sig} =>"

                    ret = value_node.child_by_field_name("return_type")
                    if ret:
                        signature += f": {self._node_text(ret, source)}"

                    result.symbols.append(Symbol(
                        name=name,
                        qualified_name=qname,
                        kind="function",
                        line_start=child.start_point[0] + 1,
                        line_end=child.end_point[0] + 1,
                        parent_name=parent_name,
                        signature=signature,
                        exported=exported,
                    ))

                    body = value_node.child_by_field_name("body")
                    if body:
                        for bchild in body.children:
                            self._walk(bchild, source, result, parent_name=qname)
                else:
                    # Walk value for calls etc
                    self._walk(value_node, source, result, parent_name)

    def _extract_export(self, node, source: bytes, result: ParseResult,
                        parent_name: str | None) -> None:
        """Handle export statements — mark children as exported."""
        for child in node.children:
            if child.type == "function_declaration":
                self._extract_function(child, source, result, parent_name, exported=True)
            elif child.type == "class_declaration":
                self._extract_class(child, source, result, parent_name, exported=True)
            elif child.type == "interface_declaration":
                self._extract_interface(child, source, result, parent_name, exported=True)
            elif child.type == "type_alias_declaration":
                self._extract_type_alias(child, source, result, parent_name, exported=True)
            elif child.type == "enum_declaration":
                self._extract_enum(child, source, result, parent_name, exported=True)
            elif child.type in ("lexical_declaration", "variable_declaration"):
                self._extract_variable_decl(child, source, result, parent_name, exported=True)
            else:
                self._walk(child, source, result, parent_name)

    def _extract_jsdoc(self, node, source: bytes) -> str | None:
        """Extract JSDoc comment preceding a node."""
        # Look for comment node in previous siblings or parent's children
        if node.prev_named_sibling and node.prev_named_sibling.type == "comment":
            comment = self._node_text(node.prev_named_sibling, source)
            if comment.startswith("/**"):
                # Strip /** and */ and leading *
                lines = comment.split("\n")
                cleaned = []
                for line in lines:
                    line = line.strip()
                    line = line.lstrip("/*").rstrip("*/").strip()
                    if line:
                        cleaned.append(line)
                return "\n".join(cleaned)[:500] if cleaned else None
        return None


class JavaScriptParser(TypeScriptParser):
    """JavaScript parser — same logic as TypeScript, different tree-sitter language."""
    language = "javascript"
    ts_language = "javascript"
