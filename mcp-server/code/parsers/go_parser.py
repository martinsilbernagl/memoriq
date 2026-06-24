"""Go parser using tree-sitter.

Extracts: functions, structs, interfaces, methods, imports, calls.
"""

from __future__ import annotations

from .base import BaseParser, Symbol, Reference, ParseResult


class GoParser(BaseParser):
    language = "go"
    ts_language = "go"

    def _extract(self, root_node, source: bytes, result: ParseResult) -> None:
        self._walk(root_node, source, result, parent_name=None, package_name=None)

    def _walk(self, node, source: bytes, result: ParseResult,
              parent_name: str | None, package_name: str | None) -> None:
        ntype = node.type

        if ntype == "package_clause":
            package_name = self._extract_package(node, source)
        elif ntype == "function_declaration":
            self._extract_function(node, source, result, parent_name, package_name)
        elif ntype == "method_declaration":
            self._extract_method(node, source, result, package_name)
        elif ntype == "type_declaration":
            self._extract_type_decl(node, source, result, package_name)
        elif ntype == "import_declaration":
            self._extract_import(node, source, result, package_name)
        elif ntype == "call_expression":
            self._extract_call(node, source, result, parent_name)
        elif ntype == "composite_literal":
            # Track struct initialization
            self._extract_composite_literal(node, source, result, parent_name)
        else:
            for child in node.children:
                self._walk(child, source, result, parent_name, package_name)

    def _extract_package(self, node, source: bytes) -> str | None:
        """Extract package name from package clause."""
        for child in node.children:
            if child.type == "package_identifier":
                return self._node_text(child, source)
        return None

    def _extract_function(self, node, source: bytes, result: ParseResult,
                          parent_name: str | None, package_name: str | None) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{package_name}.{name}" if package_name else name

        # Extract parameters for signature
        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"

        # Return values
        results_node = node.child_by_field_name("result")
        if results_node:
            ret = self._node_text(results_node, source)
            signature = f"func {name}{sig} {ret}"
        else:
            signature = f"func {name}{sig}"

        # Check if exported (starts with uppercase)
        exported = name[0].isupper() if name else False

        # Calculate complexity metrics
        body = node.child_by_field_name("body")
        cyclomatic, cognitive, loc = self._calculate_complexity(body, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="function",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=signature,
            docstring=None,  # Go uses // comments, not docstrings
            exported=exported,
            cyclomatic_complexity=cyclomatic,
            cognitive_complexity=cognitive,
            lines_of_code=loc,
        ))

        # Walk body for nested calls
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname, package_name=package_name)

    def _extract_method(self, node, source: bytes, result: ParseResult,
                        package_name: str | None) -> None:
        """Extract method with receiver."""
        name_node = node.child_by_field_name("name")
        recv_node = node.child_by_field_name("receiver")

        if not name_node:
            return

        name = self._node_text(name_node, source)

        # Extract receiver type for qualified name
        receiver_type = None
        if recv_node:
            receiver_type = self._extract_receiver_type(recv_node, source)

        if receiver_type:
            qname = f"{receiver_type}.{name}"
            parent_name = receiver_type
        else:
            qname = f"{package_name}.{name}" if package_name else name
            parent_name = None

        # Extract parameters
        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"

        # Return values
        results_node = node.child_by_field_name("result")
        if results_node:
            ret = self._node_text(results_node, source)
            signature = f"func ({receiver_type}) {name}{sig} {ret}" if receiver_type else f"func {name}{sig} {ret}"
        else:
            signature = f"func ({receiver_type}) {name}{sig}" if receiver_type else f"func {name}{sig}"

        exported = name[0].isupper() if name else False

        # Calculate complexity metrics
        body = node.child_by_field_name("body")
        cyclomatic, cognitive, loc = self._calculate_complexity(body, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="method",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=parent_name,
            signature=signature,
            docstring=None,
            exported=exported,
            cyclomatic_complexity=cyclomatic,
            cognitive_complexity=cognitive,
            lines_of_code=loc,
        ))

        # Walk body
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name=qname, package_name=package_name)

    def _extract_receiver_type(self, recv_node, source: bytes) -> str | None:
        """Extract the type name from a receiver declaration."""
        # Receiver structure: (param_list) -> parameter -> type_identifier
        for child in recv_node.children:
            if child.type == "parameter_list":
                for param in child.children:
                    if param.type == "parameter":
                        type_node = param.child_by_field_name("type")
                        if type_node:
                            # Handle pointer types
                            if type_node.type == "pointer_type":
                                inner = type_node.child_by_field_name("type")
                                if inner:
                                    return self._node_text(inner, source)
                            else:
                                return self._node_text(type_node, source)
        return None

    def _extract_type_decl(self, node, source: bytes, result: ParseResult,
                           package_name: str | None) -> None:
        """Extract struct, interface, and other type declarations."""
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")

                if not name_node or not type_node:
                    continue

                name = self._node_text(name_node, source)
                qname = f"{package_name}.{name}" if package_name else name
                exported = name[0].isupper() if name else False

                if type_node.type == "struct_type":
                    self._extract_struct(child, name, qname, type_node, source, result, exported)
                elif type_node.type == "interface_type":
                    self._extract_interface(child, name, qname, type_node, source, result, exported)
                elif type_node.type == "enum_type":
                    self._extract_enum(child, name, qname, source, result, exported)

    def _extract_struct(self, node, name: str, qname: str, type_node, source: bytes,
                        result: ParseResult, exported: bool) -> None:
        """Extract struct definition."""
        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="class",  # Using class to represent struct
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=None,
            signature=f"type {name} struct",
            docstring=None,
            exported=exported,
        ))

        # Extract field references (embedded types)
        for field in type_node.children:
            if field.type == "field_declaration_list":
                for decl in field.children:
                    if decl.type == "field_declaration":
                        type_ref = decl.child_by_field_name("type")
                        if type_ref and type_ref.type == "type_identifier":
                            ref_name = self._node_text(type_ref, source)
                            if ref_name[0].isupper():
                                result.references.append(Reference(
                                    from_symbol=qname,
                                    to_name=ref_name,
                                    kind="type_ref",
                                    line=type_ref.start_point[0] + 1,
                                    confidence=0.8,
                                ))

    def _extract_interface(self, node, name: str, qname: str, type_node, source: bytes,
                           result: ParseResult, exported: bool) -> None:
        """Extract interface definition."""
        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="interface",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=None,
            signature=f"type {name} interface",
            docstring=None,
            exported=exported,
        ))

        # Extract method signatures within interface
        for method in type_node.children:
            if method.type == "method_spec":
                method_name_node = method.child_by_field_name("name")
                if method_name_node:
                    method_name = self._node_text(method_name_node, source)
                    method_qname = f"{qname}.{method_name}"

                    params_node = method.child_by_field_name("parameters")
                    sig = self._node_text(params_node, source) if params_node else "()"

                    result.symbols.append(Symbol(
                        name=method_name,
                        qualified_name=method_qname,
                        kind="method",
                        line_start=method.start_point[0] + 1,
                        line_end=method.end_point[0] + 1,
                        parent_name=qname,
                        signature=f"{method_name}{sig}",
                        exported=True,
                    ))

    def _extract_enum(self, node, name: str, qname: str, source: bytes,
                      result: ParseResult, exported: bool) -> None:
        """Extract enum (const block) definition."""
        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="enum",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=None,
            signature=f"type {name} int",  # Simplified
            docstring=None,
            exported=exported,
        ))

    def _extract_import(self, node, source: bytes, result: ParseResult,
                        package_name: str | None) -> None:
        """Extract import statements."""
        # Handle single import: import "path"
        # Handle import block: import ( "path1" "path2" )
        for child in node.children:
            if child.type == "import_spec":
                path_node = child.child_by_field_name("path")
                name_node = child.child_by_field_name("name")

                if path_node:
                    import_path = self._node_text(path_node, source).strip('"')
                    alias = None
                    if name_node:
                        alias = self._node_text(name_node, source)

                    # Use alias if present, otherwise derive from last path component
                    if alias and alias != "_":  # Skip blank imports
                        ref_name = alias
                    else:
                        ref_name = import_path.split("/")[-1]

                    result.references.append(Reference(
                        from_symbol=package_name,
                        to_name=ref_name,
                        kind="import",
                        line=node.start_point[0] + 1,
                        confidence=0.9,
                    ))
            elif child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        path_node = spec.child_by_field_name("path")
                        name_node = spec.child_by_field_name("name")

                        if path_node:
                            import_path = self._node_text(path_node, source).strip('"')
                            alias = None
                            if name_node:
                                alias = self._node_text(name_node, source)

                            if alias and alias != "_":
                                ref_name = alias
                            else:
                                ref_name = import_path.split("/")[-1]

                            result.references.append(Reference(
                                from_symbol=package_name,
                                to_name=ref_name,
                                kind="import",
                                line=spec.start_point[0] + 1,
                                confidence=0.9,
                            ))

    def _extract_call(self, node, source: bytes, result: ParseResult,
                      parent_name: str | None) -> None:
        """Extract function/method call references."""
        func_node = node.child_by_field_name("function")
        if not func_node:
            return

        call_name = self._node_text(func_node, source)

        # Skip common builtins
        if call_name in ("len", "cap", "make", "new", "append", "copy",
                         "close", "delete", "panic", "recover", "print", "println"):
            pass  # Still need to walk arguments

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
                self._walk(child, source, result, parent_name, None)

    def _extract_composite_literal(self, node, source: bytes, result: ParseResult,
                                   parent_name: str | None) -> None:
        """Extract struct initialization references."""
        type_node = node.child_by_field_name("type")
        if type_node:
            type_name = self._node_text(type_node, source)
            result.references.append(Reference(
                from_symbol=parent_name,
                to_name=type_name,
                kind="type_ref",
                line=node.start_point[0] + 1,
                confidence=0.8,
            ))

        # Walk body
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name, None)

    def _calculate_complexity(self, body_node, source: bytes) -> tuple[int, int, int]:
        """Calculate cyclomatic complexity, cognitive complexity, and LOC for a function body.

        Returns: (cyclomatic, cognitive, lines_of_code)
        """
        if not body_node:
            return 1, 0, 0

        cyclomatic = 1  # Base complexity
        cognitive = 0
        loc = body_node.end_point[0] - body_node.start_point[0] + 1

        # Decision points that increase cyclomatic complexity
        decision_nodes = {
            "if_statement", "for_statement", "range_clause",
            "switch_statement", "type_switch_statement", "select_statement",
        }

        # Logical operators
        logical_ops = {"&&", "||"}

        def walk_for_complexity(node, nesting_depth: int = 0):
            nonlocal cyclomatic, cognitive

            ntype = node.type

            # Count decision points
            if ntype in decision_nodes:
                cyclomatic += 1
                cognitive += 1 + nesting_depth  # Nested complexity penalty

            # Count logical operators
            if ntype in logical_ops:
                cyclomatic += 1

            # Recurse into children with increased nesting for certain nodes
            new_depth = nesting_depth + 1 if ntype in decision_nodes else nesting_depth
            for child in node.children:
                walk_for_complexity(child, new_depth)

        walk_for_complexity(body_node)
        return cyclomatic, cognitive, loc
