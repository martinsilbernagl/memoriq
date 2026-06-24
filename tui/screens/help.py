"""Help modal screen - Keyboard shortcuts reference."""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label


HELP_CONTENT = """
[b]Navigation[/b]
  [cyan]1-8[/cyan]        Switch to tab 1-8
  [cyan]Tab[/cyan]         Next tab
  [cyan]Shift+Tab[/cyan]   Previous tab

[b]Actions[/b]
  [cyan]F5[/cyan]          Refresh current view
  [cyan]?[/cyan]           Show this help
  [cyan]q[/cyan]           Quit application

[b]Facts Tab[/b]
  [cyan]/[/cyan]           Focus search box
  [cyan]f[/cyan]           Focus type filter
  [cyan]d[/cyan]           Focus domain filter
  [cyan]t[/cyan]           Focus tier filter
  [cyan]e[/cyan]           Export current view

[b]Code Graph Tab[/b]
  [cyan]s[/cyan]           Focus symbol search
  [cyan]Enter[/cyan]       View symbol details
  [cyan]r[/cyan]           Show references

[b]Tips[/b]
  • Use filters to narrow down facts
  • Export saves current filtered view
  • Press F5 after external changes
"""


class HelpScreen(ModalScreen):
    """Modal screen showing keyboard shortcuts."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 70;
        height: auto;
        max-height: 90%;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }

    #help-content {
        height: auto;
        max-height: 30;
        overflow-y: auto;
        padding: 0 1;
    }

    #help-footer {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    #close-btn {
        width: 20;
    }
    """

    BINDINGS = [
        ("q,escape", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("Memoriq Keyboard Shortcuts", id="help-title")
            yield Static(HELP_CONTENT, id="help-content")
            with Horizontal(id="help-footer"):
                yield Button("Close (q)", id="close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()

    def action_close(self) -> None:
        self.dismiss()
