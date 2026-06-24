"""Heat score widget with color coding and shared display utilities."""

from textual.widgets import Static


def heat_color(score: float) -> str:
    """Return Rich color name for heat score."""
    if score >= 0.7:
        return "red"
    elif score >= 0.3:
        return "yellow"
    return "cyan"


def heat_label(score: float) -> str:
    """Return human label for heat score."""
    if score >= 0.7:
        return "HOT"
    elif score >= 0.3:
        return "WARM"
    return "COLD"


def heat_bar(score: float, width: int = 10) -> str:
    """Return a colored bar representation."""
    filled = int(score * width)
    color = heat_color(score)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar}[/] {score:.2f}"


def outcome_color(outcome: str) -> str:
    """Return Rich color name for session outcome."""
    o = (outcome or "").lower()
    if o in ("success", "completed"):
        return "green"
    if o in ("partial", "interrupted"):
        return "yellow"
    if o in ("failed", "crashed"):
        return "red"
    return "white"


class HeatCell(Static):
    """A colored heat score display."""

    def __init__(self, score: float, **kwargs):
        self.score = score
        super().__init__(**kwargs)

    def render(self) -> str:
        color = heat_color(self.score)
        label = heat_label(self.score)
        return f"[bold {color}]{label}[/] ({self.score:.2f})"
