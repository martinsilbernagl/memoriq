"""Tab 8: Code Graph — Code intelligence browser."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Tree, Select

from tui.widgets.stats_card import StatsCard
from tui import data


# Kind icons with colors
KIND_ICONS = {
    "function": ("[green]fn[/]", "green"),
    "class": ("[magenta]cls[/]", "magenta"),
    "method": ("[blue]mtd[/]", "blue"),
    "interface": ("[cyan]ifc[/]", "cyan"),
    "variable": ("[yellow]var[/]", "yellow"),
    "type_alias": ("[white]typ[/]", "white"),
    "enum": ("[dark_orange]enm[/]", "dark_orange"),
    "module": ("[dim]mod[/]", "dim"),
}

REF_KIND_ICONS = {
    "call": "->",
    "import": "use",
    "inherit": "ext",
    "implement": "impl",
    "type_ref": "typ",
    "decorator": "@",
}


class CodeGraphScreen(Static):
    """Code intelligence browser with file/symbol tree and detail pane."""

    DEFAULT_CSS = """
    CodeGraphScreen {
        height: 1fr;
    }
    .code-stats-row {
        height: 7;
        margin-bottom: 1;
    }
    .code-filter-bar {
        height: 3;
        padding: 0 1;
    }
    .code-filter-bar Select {
        width: 30;
    }
    #code-tree {
        width: 1fr;
        height: 1fr;
    }
    #code-detail {
        width: 45%;
        height: 1fr;
        border-left: solid $surface;
        padding: 1;
        overflow-y: auto;
    }
    .code-empty {
        width: 1fr;
        height: 1fr;
        text-align: center;
        padding: 5;
        content-align: center middle;
    }
    """

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        stats = data.get_code_stats(self.project)

        if stats is None or stats["files"] == 0:
            yield Static(
                "[bold yellow]🕸️ No code indexed.[/]\n\n"
                "Run [bold]code_index()[/] in Claude Code to index your project's source code.\n\n"
                "[dim]Code intelligence provides:\n"
                "  • Symbol browser (functions, classes, methods)\n"
                "  • Reference tracking (who calls what)\n"
                "  • Impact analysis (blast radius)[/]",
                classes="code-empty",
            )
            return

        # Stats row
        langs_str = ", ".join(stats["languages"][:5])
        with Horizontal(classes="code-stats-row"):
            yield StatsCard("📄 Files", stats["files"], color="blue")
            yield StatsCard("🔣 Symbols", stats["symbols"], color="green")
            yield StatsCard("🔗 References", stats["references"], color="magenta")
            yield StatsCard(f"🌐 Lang", langs_str or "?", color="cyan")

        # Kind filter
        kinds = data.get_code_symbol_kinds(self.project)
        kind_options = [("All kinds", None)] + [(k, k) for k in kinds]
        with Horizontal(classes="code-filter-bar"):
            yield Select(kind_options, id="kind-filter", value=None)

        # Tree + Detail
        with Horizontal():
            yield Tree("📁 Source Files", id="code-tree")
            yield Static("[dim]Select a symbol to see details[/]", id="code-detail")

    def on_mount(self) -> None:
        try:
            self.query_one("#code-tree", Tree)
        except Exception:
            return  # Empty state, no tree
        self._load_tree()

    def _load_tree(self, kind_filter: str | None = None) -> None:
        tree = self.query_one("#code-tree", Tree)
        tree.clear()

        files = data.get_code_files_with_symbols(
            project=self.project,
            kind_filter=kind_filter,
            limit=100,
        )

        if not files:
            tree.root.add_leaf("[dim]No symbols found.[/]")
            return

        for f in files:
            file_path = f.get("file_path", "?")
            lang = f.get("language", "?")
            sym_count = len(f.get("symbols", []))
            node = tree.root.add(
                f"📄 [bold]{file_path}[/] [dim]({lang}, {sym_count})[/]",
                data={"type": "file", "file": f},
            )

            for sym in f.get("symbols", []):
                kind = sym.get("kind", "?")
                icon, _color = KIND_ICONS.get(kind, ("[dim]?[/]", "dim"))
                name = sym.get("name", "?")
                lines = f"L{sym.get('line_start', '?')}-{sym.get('line_end', '?')}"
                sig = sym.get("signature") or ""
                if sig and len(sig) > 40:
                    sig = sig[:40] + "..."
                label = f"{icon} {name}"
                if sig:
                    label += f" [dim]{sig}[/]"
                label += f" [dim]{lines}[/]"
                node.add_leaf(label, data={"type": "symbol", "id": sym["id"]})

        tree.root.expand_all()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        detail_widget = self.query_one("#code-detail", Static)
        node_data = event.node.data

        if not node_data or not isinstance(node_data, dict):
            return

        if node_data.get("type") == "file":
            f = node_data.get("file", {})
            detail_widget.update(
                f"[bold]📄 {f.get('file_path', '?')}[/]\n\n"
                f"Language: {f.get('language', '?')}\n"
                f"Symbols: {f.get('symbol_count', len(f.get('symbols', [])))}\n"
            )
            return

        if node_data.get("type") != "symbol":
            return

        symbol_id = node_data.get("id")
        if not symbol_id:
            return

        sym = data.get_symbol_detail(symbol_id)
        if not sym:
            detail_widget.update("[red]Symbol not found[/]")
            return

        kind = sym.get("kind", "?")
        icon, color = KIND_ICONS.get(kind, ("[dim]?[/]", "dim"))

        text = (
            f"[bold {color}]{sym.get('name', '?')}[/] {icon}\n\n"
            f"Kind: {kind}\n"
            f"File: {sym.get('file_path', '?')}\n"
            f"Lines: {sym.get('line_start', '?')}-{sym.get('line_end', '?')}\n"
            f"Language: {sym.get('language', '?')}\n"
            f"Exported: {'yes' if sym.get('exported') else 'no'}\n"
        )

        if sym.get("qualified_name"):
            text += f"Qualified: {sym['qualified_name']}\n"
        if sym.get("signature"):
            text += f"\n[bold]Signature:[/]\n  {sym['signature']}\n"
        if sym.get("docstring"):
            doc = sym["docstring"]
            if len(doc) > 300:
                doc = doc[:300] + "..."
            text += f"\n[bold]Docstring:[/]\n  [dim]{doc}[/]\n"

        # Load references on-demand
        refs = data.get_symbol_references(symbol_id)
        incoming = refs.get("incoming", [])
        outgoing = refs.get("outgoing", [])

        if incoming:
            text += f"\n[bold green]↙ Incoming ({len(incoming)}):[/]\n"
            for ref in incoming[:15]:
                ref_kind = REF_KIND_ICONS.get(ref.get("kind", ""), "?")
                from_name = ref.get("from_name") or "[dim]<unknown>[/]"
                file_path = ref.get("file_path") or "?"
                line = ref.get("line", "?")
                text += f"  [{ref_kind}] {from_name} [dim]({file_path}:{line})[/]\n"
            if len(incoming) > 15:
                text += f"  [dim]... and {len(incoming) - 15} more[/]\n"

        if outgoing:
            text += f"\n[bold blue]↗ Outgoing ({len(outgoing)}):[/]\n"
            for ref in outgoing[:15]:
                ref_kind = REF_KIND_ICONS.get(ref.get("kind", ""), "?")
                to_name = ref.get("to_resolved_name") or ref.get("to_name", "?")
                file_path = ref.get("file_path") or "?"
                line = ref.get("line", "?")
                text += f"  [{ref_kind}] {to_name} [dim]({file_path}:{line})[/]\n"
            if len(outgoing) > 15:
                text += f"  [dim]... and {len(outgoing) - 15} more[/]\n"

        if not incoming and not outgoing:
            text += "\n[dim]No references found[/]\n"

        detail_widget.update(text)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "kind-filter":
            kind_val = event.value if event.value != Select.BLANK else None
            self._load_tree(kind_filter=kind_val)
