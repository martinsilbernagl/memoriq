"""Tab 3: Heat Map — Heat distribution visualization."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from tui.widgets.heat_cell import heat_color
from tui import data


class HeatmapScreen(Static):
    """Heat distribution by type and project."""

    DEFAULT_CSS = """
    HeatmapScreen {
        height: auto;
        padding: 1;
    }
    .heat-section {
        margin-bottom: 1;
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
        yield Static("🔥 Heat Distribution", classes="section-header")

        with Vertical(classes="heat-section", id="heat-by-type"):
            yield Static("[bold]By Type[/]", id="heat-type-header")

        with Vertical(classes="heat-section", id="heat-by-project"):
            yield Static("[bold]By Project[/]", id="heat-project-header")

    def on_mount(self) -> None:
        """Load heat data after mount."""
        # Check if we have any facts
        stats = data.get_stats(self.project)
        if stats["facts"] == 0:
            self._show_empty_state()
            return

        # Load heat by type
        type_container = self.query_one("#heat-by-type", Vertical)
        type_dist = data.get_heat_distribution(self.project)
        if type_dist:
            max_total = max(d["total"] for d in type_dist) or 1
            for d in type_dist:
                type_container.mount(Static(_heat_bar_row(d, max_total)))
        else:
            type_container.mount(Static("[dim]No type data available.[/]"))

        # Load heat by project
        proj_container = self.query_one("#heat-by-project", Vertical)
        proj_dist = data.get_heat_by_project()
        if proj_dist:
            max_total = max(d["total"] for d in proj_dist) or 1
            for d in proj_dist:
                proj_container.mount(Static(_project_heat_row(d, max_total)))
        else:
            proj_container.mount(Static("[dim]No project data available.[/]"))

    def _show_empty_state(self) -> None:
        """Show empty state message."""
        self.query_one("#heat-by-type", Vertical).mount(Static(
            "[yellow]No facts in memory.[/]\n\n"
            "Run [bold]/onboard[/] in Claude Code to initialize your project.\n"
            "Facts will appear here once you start using Memoriq.",
            classes="empty-state"
        ))


def _heat_bar_row(d: dict, max_total: int) -> str:
    """Render a heat bar for a type."""
    name = d.get("type", "?")
    total = d.get("total", 0)
    hot = d.get("hot", 0)
    warm = d.get("warm", 0)
    cold = d.get("cold", 0)
    avg = d.get("avg_heat", 0) or 0

    bar_width = 30
    scale = bar_width / max_total if max_total > 0 else 0

    hot_w = max(1, int(hot * scale)) if hot else 0
    warm_w = max(1, int(warm * scale)) if warm else 0
    cold_w = max(1, int(cold * scale)) if cold else 0

    bar = f"[red]{'█' * hot_w}[/][yellow]{'█' * warm_w}[/][cyan]{'█' * cold_w}[/]"
    color = heat_color(avg)

    return f"  {name:<15} {bar} [{color}]{total:>3}[/] (avg {avg:.2f})"


def _project_heat_row(d: dict, max_total: int) -> str:
    """Render a heat bar for a project."""
    name = d.get("project", "?")
    total = d.get("total", 0)
    hot = d.get("hot", 0)
    warm = d.get("warm", 0)
    cold = d.get("cold", 0)
    avg = d.get("avg_heat", 0) or 0

    bar_width = 30
    scale = bar_width / max_total if max_total > 0 else 0

    hot_w = max(1, int(hot * scale)) if hot else 0
    warm_w = max(1, int(warm * scale)) if warm else 0
    cold_w = max(1, int(cold * scale)) if cold else 0

    bar = f"[red]{'█' * hot_w}[/][yellow]{'█' * warm_w}[/][cyan]{'█' * cold_w}[/]"
    color = heat_color(avg)

    return f"  {name:<20} {bar} [{color}]{total:>3}[/] (avg {avg:.2f})"
