"""Progress bar widget for health metrics."""

from textual.widgets import Static


class ProgressBar(Static):
    """A simple progress bar widget."""

    DEFAULT_CSS = """
    ProgressBar {
        height: 3;
        padding: 0 1;
        content-align: left middle;
    }
    ProgressBar .bar-container {
        width: 100%;
        height: 1;
        background: $surface-darken-2;
    }
    ProgressBar .bar-fill {
        width: auto;
        height: 1;
    }
    """

    def __init__(self, value: float = 0, total: float = 100, color: str = "green", label: str = "", **kwargs):
        self.value = value
        self.total = total
        self.color = color
        self.label = label
        super().__init__(**kwargs)

    def render(self) -> str:
        pct = min(100, max(0, (self.value / self.total) * 100)) if self.total else 0
        filled = int(pct / 2)  # 50 chars wide
        empty = 50 - filled
        bar = f"[{'█' * filled}{'░' * empty}]"
        label = f"{self.label}: {self.value:.0f}/{self.total:.0f} ({pct:.1f}%)" if self.label else f"{pct:.1f}%"
        return f"{label}\n[{self.color}]{bar}[/]"

    def update_progress(self, value: float, total: float = None):
        self.value = value
        if total is not None:
            self.total = total
        self.refresh()
