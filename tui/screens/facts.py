"""Tab 2: Facts — Filterable fact browser with export."""

import json
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Input, Label, RadioButton, RadioSet, Select, Static
)

from tui.widgets.heat_cell import heat_color, heat_label
from tui import data


class ExportDialog(ModalScreen):
    """Modal dialog for exporting facts."""

    DEFAULT_CSS = """
    ExportDialog {
        align: center middle;
    }
    #export-container {
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }
    #export-title {
        text-align: center;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    #export-formats {
        margin: 1 0;
    }
    #export-buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, facts: list[dict], **kwargs):
        self.facts = facts
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical(id="export-container"):
            yield Label("Export Facts", id="export-title")
            yield Label(f"{len(self.facts)} facts will be exported")
            yield Label("Select format:")
            with RadioSet(id="export-formats"):
                yield RadioButton("Markdown (.md)", value=True, id="fmt-md")
                yield RadioButton("JSON (.json)", id="fmt-json")
                yield RadioButton("CSV (.csv)", id="fmt-csv")
            with Horizontal(id="export-buttons"):
                yield Button("Export", id="export-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-btn":
            # Get selected format
            radio_set = self.query_one("#export-formats", RadioSet)
            selected = radio_set.pressed_button
            fmt = "md"
            if selected:
                if selected.id == "fmt-json":
                    fmt = "json"
                elif selected.id == "fmt-csv":
                    fmt = "csv"
            self.dismiss(fmt)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FactsScreen(Static):
    """Fact browser with search and filters."""

    DEFAULT_CSS = """
    FactsScreen {
        height: 1fr;
    }
    .filter-bar {
        height: 3;
        padding: 0 1;
        dock: top;
    }
    .filter-bar Input {
        width: 1fr;
    }
    .filter-bar Select {
        width: 20;
    }
    """

    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("f", "focus_type", "Type filter"),
        ("d", "focus_domain", "Domain filter"),
        ("t", "focus_tier", "Tier filter"),
        ("e", "export_facts", "Export"),
    ]

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        self._current_facts: list[dict] = []
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        types = [("All types", None)] + [(t, t) for t in data.get_fact_types(self.project)]
        domains = [("All domains", None)] + [(d, d) for d in data.get_fact_domains(self.project)]
        tiers = [("All tiers", None), ("active", "active"), ("reference", "reference"), ("archive", "archive")]

        with Horizontal(classes="filter-bar"):
            yield Input(placeholder="Search facts...", id="fact-search")
            yield Select(types, id="type-filter", value=None)
            yield Select(domains, id="domain-filter", value=None)
            yield Select(tiers, id="tier-filter", value=None)

        yield DataTable(id="facts-table")

    def on_mount(self) -> None:
        table = self.query_one("#facts-table", DataTable)
        table.add_columns("Type", "Domain", "Content", "Heat", "Tier", "Age")
        self._load_data()

    def _load_data(self):
        table = self.query_one("#facts-table", DataTable)
        table.clear()

        search_input = self.query_one("#fact-search", Input)
        type_select = self.query_one("#type-filter", Select)
        domain_select = self.query_one("#domain-filter", Select)
        tier_select = self.query_one("#tier-filter", Select)

        type_val = type_select.value if type_select.value != Select.BLANK else None
        domain_val = domain_select.value if domain_select.value != Select.BLANK else None
        tier_val = tier_select.value if tier_select.value != Select.BLANK else None

        self._current_facts = data.get_facts(
            project=self.project,
            type_filter=type_val,
            domain_filter=domain_val,
            tier_filter=tier_val,
            search=search_input.value or None,
        )

        for fact in self._current_facts:
            heat = fact.get("heat_score", 0) or 0
            color = heat_color(heat)
            content = (fact.get("content") or "")[:60]
            age = _format_age(fact.get("timestamp"))

            table.add_row(
                fact.get("type", "?"),
                fact.get("domain") or "-",
                content,
                f"[{color}]{heat_label(heat)} {heat:.2f}[/]",
                fact.get("knowledge_tier") or "?",
                age,
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "fact-search":
            self._load_data()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._load_data()

    def action_focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#fact-search", Input).focus()

    def action_focus_type(self) -> None:
        """Focus the type filter."""
        self.query_one("#type-filter", Select).focus()

    def action_focus_domain(self) -> None:
        """Focus the domain filter."""
        self.query_one("#domain-filter", Select).focus()

    def action_focus_tier(self) -> None:
        """Focus the tier filter."""
        self.query_one("#tier-filter", Select).focus()

    def action_export_facts(self) -> None:
        """Open export dialog."""
        if not self._current_facts:
            self.app.notify("No facts to export", severity="warning")
            return

        def on_export_result(fmt: str | None) -> None:
            if fmt:
                self._do_export(fmt)

        self.app.push_screen(ExportDialog(self._current_facts), on_export_result)

    def _do_export(self, fmt: str) -> None:
        """Perform the actual export."""
        # Create exports directory
        export_dir = Path.home() / ".memoriq" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project_suffix = f"-{self.project}" if self.project else ""
        filename = f"memoriq-export{project_suffix}-{timestamp}.{fmt}"
        filepath = export_dir / filename

        try:
            if fmt == "json":
                self._export_json(filepath)
            elif fmt == "csv":
                self._export_csv(filepath)
            else:  # markdown
                self._export_markdown(filepath)

            self.app.notify(f"Exported to {filepath.name}", severity="information")
        except Exception as e:
            self.app.notify(f"Export failed: {e}", severity="error")

    def _export_json(self, filepath: Path) -> None:
        """Export facts as JSON."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._current_facts, f, indent=2, default=str)

    def _export_csv(self, filepath: Path) -> None:
        """Export facts as CSV."""
        import csv

        if not self._current_facts:
            return

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._current_facts[0].keys())
            writer.writeheader()
            writer.writerows(self._current_facts)

    def _export_markdown(self, filepath: Path) -> None:
        """Export facts as Markdown."""
        lines = [
            "# Memoriq Facts Export",
            "",
            f"**Project:** {self.project or 'All Projects'}",
            f"**Date:** {datetime.now().isoformat()}",
            f"**Facts:** {len(self._current_facts)}",
            "",
            "---",
            "",
        ]

        for fact in self._current_facts:
            fact_type = fact.get("type", "?")
            domain = fact.get("domain") or "-"
            content = fact.get("content", "")
            heat = fact.get("heat_score", 0) or 0
            tier = fact.get("knowledge_tier") or "?"
            timestamp = fact.get("timestamp", "?")

            lines.extend([
                f"## {fact_type} ({domain})",
                "",
                f"{content}",
                "",
                f"- **Heat Score:** {heat:.2f}",
                f"- **Tier:** {tier}",
                f"- **Timestamp:** {timestamp}",
                "",
                "---",
                "",
            ])

        filepath.write_text("\n".join(lines), encoding="utf-8")


def _format_age(timestamp: str | None) -> str:
    if not timestamp:
        return "?"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp)
        delta = datetime.now() - dt
        if delta.days > 30:
            return f"{delta.days // 30}mo"
        if delta.days > 0:
            return f"{delta.days}d"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h"
        return f"{delta.seconds // 60}m"
    except Exception:
        return "?"
