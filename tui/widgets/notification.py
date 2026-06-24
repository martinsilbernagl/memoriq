"""Toast notification widget for TUI."""

from textual.widgets import Static
from textual.reactive import reactive
from textual.containers import Horizontal


class Notification(Static):
    """A toast notification that auto-dismisses."""

    DEFAULT_CSS = """
    Notification {
        width: auto;
        height: auto;
        padding: 1 2;
        margin: 1;
        border: solid;
        color: $text;
        text-style: bold;
    }
    Notification.info {
        background: $primary-darken-2;
        border: solid $primary;
    }
    Notification.success {
        background: $success-darken-2;
        border: solid $success;
    }
    Notification.warning {
        background: $warning-darken-2;
        border: solid $warning;
    }
    Notification.error {
        background: $error-darken-2;
        border: solid $error;
    }
    """

    message = reactive("")
    notif_type = reactive("info")

    def __init__(self, message: str, notif_type: str = "info", dismiss_after: float = 5.0, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.notif_type = notif_type
        self.dismiss_after = dismiss_after
        self.add_class(notif_type)

    def compose(self):
        yield Static(self.message)

    def on_mount(self):
        if self.dismiss_after > 0:
            self.set_timer(self.dismiss_after, self.dismiss)

    def dismiss(self):
        self.remove()


class NotificationContainer(Horizontal):
    """Container for notifications, fixed to top-right."""

    DEFAULT_CSS = """
    NotificationContainer {
        dock: top;
        width: 100%;
        height: auto;
        content-align: right top;
    }
    """

    def notify(self, message: str, notif_type: str = "info", dismiss_after: float = 5.0):
        """Show a notification."""
        notification = Notification(message, notif_type, dismiss_after)
        self.mount(notification)
