"""Tab 1: Overview — Enhanced stats dashboard."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Rule

from tui.widgets.stats_card import StatsCard
from tui.widgets.progress_bar import ProgressBar
from tui.widgets.heat_cell import outcome_color
from tui import data


class OverviewScreen(Static):
    """Enhanced overview dashboard with stats grid, health metrics and progress bars."""

    DEFAULT_CSS = """
    OverviewScreen {
        height: auto;
        padding: 1 2;
    }
    .stats-row {
        height: auto;
        margin-bottom: 1;
    }
    .section-header {
        text-style: bold;
        padding: 1 0;
        margin-top: 1;
    }
    .health-section {
        height: auto;
        padding: 1;
        border: solid $surface;
        background: $surface-darken-1;
        margin-bottom: 1;
    }
    .health-grid {
        height: auto;
        margin-top: 1;
    }
    .session-section {
        height: auto;
        padding: 1;
        border: solid $surface;
        background: $surface-darken-1;
    }
    .quick-actions {
        height: auto;
        margin-bottom: 1;
        padding: 1;
    }
    """

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        stats = data.get_stats(self.project)

        # Section: Stats Grid
        yield Static("📊 Memory Statistics", classes="section-header")
        with Horizontal(classes="stats-row"):
            yield StatsCard("Facts", stats["facts"], color="white", trend="")
            yield StatsCard("Sessions", stats["sessions"], color="green", trend="")
            yield StatsCard("Changes", stats["changes"], color="blue", trend="")
            yield StatsCard("Projects", stats["projects"], color="magenta", trend="")

        with Horizontal(classes="stats-row"):
            yield StatsCard("Hot", stats["hot"], color="red", trend="▲")
            yield StatsCard("Warm", stats["warm"], color="yellow", trend="→")
            yield StatsCard("Cold", stats["cold"], color="cyan", trend="▼")
            yield StatsCard("Gaps", stats["gaps"], color="dark_orange", trend="!")

        # Section: Health with Progress Bars
        yield Rule()
        yield Static("🏥 Memory Health", classes="section-header")
        with Vertical(classes="health-section"):
            total = stats["facts"] or 1
            hot = stats["hot"]
            warm = stats["warm"]
            cold = stats["cold"]

            with Horizontal(classes="health-grid"):
                yield ProgressBar(hot, total, "red", "🔥 Hot")
                yield ProgressBar(warm, total, "yellow", "🌡️ Warm")
                yield ProgressBar(cold, total, "cyan", "❄️ Cold")

            yield Static(
                f"\n[dim]Contradictions: {stats['contradictions']}  |  "
                f"Knowledge Gaps: {stats['gaps']}[/]"
            )

        # Section: Last Session
        last = stats.get("last_session")
        if last:
            yield Rule()
            yield Static("💬 Last Session", classes="section-header")
            with Vertical(classes="session-section"):
                title = last.get("episode_title") or "Untitled"
                outcome = last.get("outcome") or "?"
                bridge = last.get("bridge_content") or "No bridge"
                # Truncate bridge
                if len(bridge) > 200:
                    bridge = bridge[:200] + "..."

                outcome_emoji = "✅" if outcome == "success" else "⚠️" if outcome == "warning" else "❌" if outcome == "error" else "❓"

                yield Static(
                    f"{outcome_emoji} [{outcome_color(outcome)}][bold]{outcome}[/][/] — {title}\n"
                    f"[dim]{last.get('start_time', '?')}[/]\n"
                    f"[italic]{bridge}[/]"
                )
