"""Rust parser using tree-sitter.

Extracts: functions, structs, traits, impls, enums, imports, calls.
"""

from __future__ import annotations

from .base import BaseParser, Symbol, Reference, ParseResult


class RustParser(BaseParser):
    language = "rust"
    ts_language = "rust"

    def _extract(self, root_node, source: bytes, result: ParseResult) -> None:
        self._walk(root_node, source, result, parent_name=None, module_path=None)

    def _walk(self, node, source: bytes, result: ParseResult,
              parent_name: str | None, module_path: str | None) -> None:
        ntype = node.type

        if ntype == "mod_item":
            self._extract_module(node, source, result, parent_name, module_path)
        elif ntype == "function_item":
            self._extract_function(node, source, result, parent_name, module_path)
        elif ntype == "struct_item":
            self._extract_struct(node, source, result, module_path)
        elif ntype == "enum_item":
            self._extract_enum(node, source, result, module_path)
        elif ntype == "trait_item":
            self._extract_trait(node, source, result, module_path)
        elif ntype == "impl_item":
            self._extract_impl(node, source, result, module_path)
        elif ntype == "use_declaration":
            self._extract_import(node, source, result, parent_name)
        elif ntype == "call_expression":
            self._extract_call(node, source, result, parent_name)
        elif ntype == "macro_invocation":
            self._extract_macro(node, source, result, parent_name)
        else:
            for child in node.children:
                self._walk(child, source, result, parent_name, module_path)

    def _extract_module(self, node, source: bytes, result: ParseResult,
                        parent_name: str | None, module_path: str | None) -> None:
        """Extract module declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        new_module_path = f"{module_path}::{name}" if module_path else name

        # Check for visibility
        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=new_module_path,
            kind="module",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=module_path,
            signature=f"mod {name}",
            docstring=None,
            exported=exported,
        ))

        # Walk body if present
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                self._walk(child, source, result, parent_name, new_module_path)

    def _extract_function(self, node, source: bytes, result: ParseResult,
                          parent_name: str | None, module_path: str | None) -> None:
        """Extract function or method definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)

        # Determine qualified name
        if parent_name:
            qname = f"{parent_name}::{name}"
            kind = "method"
        elif module_path:
            qname = f"{module_path}::{name}"
            kind = "function"
        else:
            qname = name
            kind = "function"

        # Build signature
        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"

        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            ret = self._node_text(ret_node, source)
            signature = f"fn {name}{sig} -> {ret}"
        else:
            signature = f"fn {name}{sig}"

        # Check visibility
        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        # Calculate complexity
        body = node.child_by_field_name("body")
        cyclomatic, cognitive, loc = self._calculate_complexity(body, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind=kind,
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
                self._walk(child, source, result, parent_name=qname, module_path=module_path)

    def _extract_struct(self, node, source: bytes, result: ParseResult,
                        module_path: str | None) -> None:
        """Extract struct definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{module_path}::{name}" if module_path else name

        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        # Check for generic parameters
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            generics = self._node_text(type_params, source)
            signature = f"struct {name}{generics}"
        else:
            signature = f"struct {name}"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="class",  # Using class to represent struct
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=module_path,
            signature=signature,
            docstring=None,
            exported=exported,
        ))

        # Extract field references (embedded types)
        body = node.child_by_field_name("body")
        if body:
            for field in body.children:
                if field.type == "field_declaration":
                    type_node = field.child_by_field_name("type")
                    if type_node:
                        type_name = self._extract_type_name(type_node, source)
                        if type_name and type_name[0].isupper():
                            result.references.append(Reference(
                                from_symbol=qname,
                                to_name=type_name,
                                kind="type_ref",
                                line=type_node.start_point[0] + 1,
                                confidence=0.8,
                            ))

    def _extract_enum(self, node, source: bytes, result: ParseResult,
                      module_path: str | None) -> None:
        """Extract enum definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{module_path}::{name}" if module_path else name

        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="enum",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=module_path,
            signature=f"enum {name}",
            docstring=None,
            exported=exported,
        ))

        # Extract enum variants as child symbols
        body = node.child_by_field_name("body")
        if body:
            for variant in body.children:
                if variant.type == "enum_variant":
                    variant_name_node = variant.child_by_field_name("name")
                    if variant_name_node:
                        variant_name = self._node_text(variant_name_node, source)
                        variant_qname = f"{qname}::{variant_name}"
                        result.symbols.append(Symbol(
                            name=variant_name,
                            qualified_name=variant_qname,
                            kind="variable",
                            line_start=variant.start_point[0] + 1,
                            line_end=variant.end_point[0] + 1,
                            parent_name=qname,
                            signature=f"{variant_name}",
                            exported=exported,
                        ))

    def _extract_trait(self, node, source: bytes, result: ParseResult,
                       module_path: str | None) -> None:
        """Extract trait definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{module_path}::{name}" if module_path else name

        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="interface",  # Using interface to represent trait
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=module_path,
            signature=f"trait {name}",
            docstring=None,
            exported=exported,
        ))

        # Extract trait items (methods, associated types, consts)
        body = node.child_by_field_name("body")
        if body:
            for item in body.children:
                if item.type == "function_signature_item":
                    self._extract_trait_method(item, source, result, qname)

    def _extract_trait_method(self, node, source: bytes, result: ParseResult,
                              trait_name: str) -> None:
        """Extract method signature from trait definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{trait_name}::{name}"

        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"

        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            ret = self._node_text(ret_node, source)
            signature = f"fn {name}{sig} -> {ret}"
        else:
            signature = f"fn {name}{sig}"

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="method",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=trait_name,
            signature=signature,
            exported=True,
        ))

    def _extract_impl(self, node, source: bytes, result: ParseResult,
                      module_path: str | None) -> None:
        """Extract impl block (inherent or trait implementation)."""
        # Check if this is a trait impl (impl Trait for Type) or inherent impl (impl Type)
        trait_node = node.child_by_field_name("trait")
        type_node = node.child_by_field_name("type")

        if trait_node and type_node:
            # Trait implementation: impl Trait for Type
            trait_name = self._extract_type_name(trait_node, source)
            type_name = self._extract_type_name(type_node, source)
            impl_desc = f"impl {trait_name} for {type_name}"
            parent_name = type_name
        elif type_node:
            # Inherent implementation: impl Type
            type_name = self._extract_type_name(type_node, source)
            impl_desc = f"impl {type_name}"
            parent_name = type_name
        else:
            return

        qname = f"{module_path}::{impl_desc}" if module_path else impl_desc

        result.symbols.append(Symbol(
            name=impl_desc,
            qualified_name=qname,
            kind="class",  # Using class for impl blocks
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=module_path,
            signature=impl_desc,
            exported=True,  # impl blocks are always public
        ))

        # Add reference to trait if this is a trait impl
        if trait_node and type_node:
            result.references.append(Reference(
                from_symbol=qname,
                to_name=trait_name,
                kind="implement",
                line=trait_node.start_point[0] + 1,
                confidence=0.9,
            ))

        # Walk body to extract methods
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "function_item":
                    self._extract_impl_method(child, source, result, parent_name, module_path)
                else:
                    self._walk(child, source, result, parent_name, module_path)

    def _extract_impl_method(self, node, source: bytes, result: ParseResult,
                             impl_type: str, module_path: str | None) -> None:
        """Extract method from impl block."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._node_text(name_node, source)
        qname = f"{impl_type}::{name}"

        params_node = node.child_by_field_name("parameters")
        sig = self._node_text(params_node, source) if params_node else "()"

        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            ret = self._node_text(ret_node, source)
            signature = f"fn {name}{sig} -> {ret}"
        else:
            signature = f"fn {name}{sig}"

        # Check for self parameter to determine if it's a method
        is_method = False
        if params_node:
            for param in params_node.children:
                if param.type == "parameter":
                    param_type = param.child_by_field_name("type")
                    if param_type:
                        type_text = self._node_text(param_type, source)
                        if "Self" in type_text or type_text == "Self":
                            is_method = True
                            break

        visibility = self._extract_visibility(node, source)
        exported = visibility == "pub"

        # Calculate complexity
        body = node.child_by_field_name("body")
        cyclomatic, cognitive, loc = self._calculate_complexity(body, source)

        result.symbols.append(Symbol(
            name=name,
            qualified_name=qname,
            kind="method" if is_method else "function",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parent_name=impl_type,
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
                self._walk(child, source, result, parent_name=qname, module_path=module_path)

    def _extract_import(self, node, source: bytes, result: ParseResult,
                        parent_name: str | None) -> None:
        """Extract use declarations."""
        argument = node.child_by_field_name("argument")
        if not argument:
            return

        import_path = self._extract_use_path(argument, source)
        if import_path:
            result.references.append(Reference(
                from_symbol=parent_name,
                to_name=import_path,
                kind="import",
                line=node.start_point[0] + 1,
                confidence=0.9,
            ))

    def _extract_use_path(self, node, source: bytes) -> str | None:
        """Extract the full path from a use tree node."""
        if node.type == "identifier":
            return self._node_text(node, source)
        elif node.type == "scoped_identifier":
            return self._node_text(node, source)
        elif node.type == "use_as_clause":
            # Handle: use path as alias
            path_node = node.child_by_field_name("path")
            if path_node:
                return self._extract_use_path(path_node, source)
        elif node.type == "use_list":
            # Handle: use path::{a, b, c}
            prefix = ""
            for child in node.children:
                if child.type in ("identifier", "scoped_identifier"):
                    prefix = self._node_text(child, source)
                elif child.type == "use_list":
                    items = []
                    for item in child.children:
                        if item.type in ("identifier", "scoped_identifier", "use_as_clause"):
                            item_path = self._extract_use_path(item, source)
                            if item_path:
                                items.append(f"{prefix}::{item_path}")
                    return prefix if not items else items[0]  # Return first for now
            return prefix

        # Try to get text directly for other types
        return self._node_text(node, source)

    def _extract_call(self, node, source: bytes, result: ParseResult,
                      parent_name: str | None) -> None:
        """Extract function call references."""
        func_node = node.child_by_field_name("function")
        if not func_node:
            return

        call_name = self._node_text(func_node, source)

        # Skip common builtins
        if call_name in ("print", "println", "eprint", "eprintln",
                         "format", "panic", "assert", "assert_eq",
                         "vec", "Some", "None", "Ok", "Err"):
            pass  # Still need to walk arguments

        result.references.append(Reference(
            from_symbol=parent_name,
            to_name=call_name,
            kind="call",
            line=node.start_point[0] + 1,
            confidence=0.7,
        ))

        # Walk arguments
        args = node.child_by_field_name("arguments")
        if args:
            for child in args.children:
                self._walk(child, source, result, parent_name, None)

    def _extract_macro(self, node, source: bytes, result: ParseResult,
                       parent_name: str | None) -> None:
        """Extract macro invocations."""
        macro_node = node.child_by_field_name("macro")
        if not macro_node:
            return

        macro_name = self._node_text(macro_node, source)
        if macro_name:
            result.references.append(Reference(
                from_symbol=parent_name,
                to_name=f"{macro_name}!",
                kind="call",
                line=node.start_point[0] + 1,
                confidence=0.8,
            ))

        # Walk macro arguments
        for child in node.children:
            if child != macro_node:
                self._walk(child, source, result, parent_name, None)

    def _extract_visibility(self, node, source: bytes) -> str:
        """Extract visibility modifier (pub, pub(crate), etc.)."""
        for child in node.children:
            if child.type == "visibility_modifier":
                return self._node_text(child, source)
        return ""

    def _extract_type_name(self, node, source: bytes) -> str | None:
        """Extract type name from a type node."""
        if node.type == "type_identifier":
            return self._node_text(node, source)
        elif node.type == "scoped_type_identifier":
            return self._node_text(node, source)
        elif node.type == "generic_type":
            # Handle Vec<T>, Option<T>, etc.
            type_node = node.child_by_field_name("type")
            if type_node:
                return self._extract_type_name(type_node, source)
        elif node.type == "reference_type":
            # Handle &T and &mut T
            type_node = node.child_by_field_name("type")
            if type_node:
                return self._extract_type_name(type_node, source)

        # Fallback: return the text
        return self._node_text(node, source)

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
            "if_expression", "if_let_expression",
            "match_expression", "match_arm",
            "for_expression", "while_expression", "while_let_expression",
            "loop_expression",
        }

        # Logical operators
        logical_ops = {"&&", "||", "and", "or"}

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

            # Match arms add complexity
            if ntype == "match_arm":
                # Each arm (except wildcard) adds to complexity
                pattern = node.child_by_field_name("pattern")
                if pattern:
                    pattern_text = self._node_text(pattern, source)
                    if pattern_text != "_":
                        cyclomatic += 1

            # Recurse into children with increased nesting for certain nodes
            new_depth = nesting_depth + 1 if ntype in decision_nodes else nesting_depth
            for child in node.children:
                walk_for_complexity(child, new_depth)

        walk_for_complexity(body_node)
        return cyclomatic, cognitive, loc
