"""Tab 6: Gaps — Knowledge gaps viewer."""

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from tui import data


class GapsScreen(Static):
    """Knowledge gaps browser."""

    DEFAULT_CSS = """
    GapsScreen {
        height: 1fr;
    }
    .empty-state {
        height: 1fr;
        content-align: center middle;
        text-align: center;
        padding: 2;
    }
    """

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield DataTable(id="gaps-table")

    def on_mount(self) -> None:
        table = self.query_one("#gaps-table", DataTable)
        table.add_columns("Query", "Times Seen", "Best Score", "First Seen", "Last Seen", "Status")

        # Check if we have any facts
        stats = data.get_stats(self.project)
        if stats["facts"] == 0:
            table.add_row(
                "[yellow]No data - run /onboard first", "-", "-", "-", "-", "-"
            )
            return

        gaps = data.get_gaps(self.project)

        if not gaps:
            table.add_row(
                "[dim]No knowledge gaps found", "-", "-", "-", "-", "-"
            )
            return

        for g in gaps:
            query = (g.get("query") or "?")[:50]
            times = g.get("times_seen") or 0
            best = g.get("best_score")
            best_str = f"{best:.2f}" if best is not None else "-"
            first = (g.get("first_seen") or "?")[:10]
            last = (g.get("last_seen") or "?")[:10]
            resolved = g.get("resolved", 0)

            if resolved:
                status = "[green]Resolved[/]"
            else:
                status = "[red]Open[/]"

            table.add_row(query, str(times), best_str, first, last, status)
