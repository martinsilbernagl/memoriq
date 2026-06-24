"""Enhanced stats card widget with icons and trends."""

from textual.widgets import Static


ICONS = {
    "Facts": "📝",
    "Sessions": "💬",
    "Changes": "🔄",
    "Projects": "📁",
    "Hot": "🔥",
    "Warm": "🌡️",
    "Cold": "❄️",
    "Gaps": "⚠️",
}


class StatsCard(Static):
    """An enhanced statistics card with icon, value and label."""

    DEFAULT_CSS = """
    StatsCard {
        width: 1fr;
        height: 6;
        border: solid $accent-darken-2;
        background: $surface-darken-1;
        padding: 0;
        text-align: center;
        content-align: center middle;
    }
    StatsCard:hover {
        border: solid $accent;
        background: $surface;
    }
    StatsCard .card-icon {
        text-style: bold;
        text-align: center;
    }
    StatsCard .card-value {
        text-style: bold;
        text-align: center;
        padding: 0;
    }
    StatsCard .card-label {
        text-align: center;
        padding: 0;
    }
    """

    def __init__(self, label: str, value: str | int, color: str = "white", trend: str = "", **kwargs):
        self.label = label
        self.value = str(value)
        self.color = color
        self.trend = trend
        self.icon = ICONS.get(label, "📊")
        super().__init__(**kwargs)

    def render(self) -> str:
        trend_indicator = f" {self.trend}" if self.trend else ""
        return f"[{self.color}]{self.icon}[/]\n[bold {self.color}]{self.value}{trend_indicator}[/]\n[dim]{self.label}[/]"

    def update_value(self, value: str | int, trend: str = ""):
        self.value = str(value)
        self.trend = trend
        self.refresh()
