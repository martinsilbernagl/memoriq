"""Tab 5: Timeline — Session history."""

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from tui.widgets.heat_cell import outcome_color
from tui import data


class TimelineScreen(Static):
    """Session timeline with episode info."""

    DEFAULT_CSS = """
    TimelineScreen {
        height: 1fr;
    }
    """

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield DataTable(id="timeline-table")

    def on_mount(self) -> None:
        table = self.query_one("#timeline-table", DataTable)
        table.add_columns("Date", "Episode", "Outcome", "Facts", "Changes", "Bridge")

        sessions = data.get_sessions(self.project)

        for s in sessions:
            date = (s.get("start_time") or "?")[:16]
            title = s.get("episode_title") or "-"
            outcome = s.get("outcome") or "?"
            facts_c = s.get("facts_count") or 0
            changes_c = s.get("changes_count") or 0
            bridge = (s.get("bridge_content") or "")[:50]

            color = outcome_color(outcome)

            table.add_row(
                date,
                title[:30],
                f"[{color}]{outcome}[/]",
                str(facts_c),
                str(changes_c),
                bridge or "-",
            )
