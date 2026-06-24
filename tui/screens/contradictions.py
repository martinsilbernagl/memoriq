"""Tab 7: Contradictions — Contradiction review."""

from textual.app import ComposeResult
from textual.widgets import DataTable, Static
from textual.containers import Vertical

from tui import data


class ContradictionsScreen(Static):
    """Contradictions browser with resolve action. Press Enter to resolve selected."""

    DEFAULT_CSS = """
    ContradictionsScreen {
        height: 1fr;
    }
    .resolve-hint {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        self._contradictions = []
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield DataTable(id="contradictions-table")
        yield Static("[dim]Select a row and press Enter to resolve[/]", classes="resolve-hint")

    def on_mount(self) -> None:
        table = self.query_one("#contradictions-table", DataTable)
        table.add_columns("Fact A", "Fact B", "Reason", "Detected", "Status")
        table.cursor_type = "row"

        # Check if we have any facts
        stats = data.get_stats(self.project)
        if stats["facts"] == 0:
            table.add_row(
                "[yellow]No data - run /onboard first", "", "", "", ""
            )
            return

        self._load_data()

    def _load_data(self):
        table = self.query_one("#contradictions-table", DataTable)
        table.clear()

        self._contradictions = data.get_contradictions(self.project)

        if not self._contradictions:
            table.add_row(
                "[dim]No contradictions found", "", "", "", ""
            )
            return

        for c in self._contradictions:
            fact_a = (c.get("fact_a_content") or "?")[:35]
            fact_b = (c.get("fact_b_content") or "?")[:35]
            reason = (c.get("reason") or "-")[:30]
            detected = (c.get("detected") or "?")[:10]
            resolved = c.get("resolved", 0)

            if resolved:
                status = "[green]Resolved[/]"
            else:
                status = "[red]Open[/]"

            table.add_row(fact_a, fact_b, reason, detected, status, key=str(c.get("id", "")))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Resolve contradiction when row is selected (Enter key)."""
        row_idx = event.cursor_row
        if row_idx is not None and row_idx < len(self._contradictions):
            c = self._contradictions[row_idx]
            if not c.get("resolved"):
                if data.resolve_contradiction(c["id"]):
                    self._load_data()
                    self.notify("Contradiction resolved", severity="information")
                else:
                    self.notify("Failed to resolve — DB may be busy", severity="error")
