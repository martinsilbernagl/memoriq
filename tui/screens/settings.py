"""Settings/configuration tab for TUI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp-server"))

from textual.widgets import Static, Button, Select, Switch
from textual.containers import Vertical, Horizontal
import yaml


class SettingsTab(Static):
    """Settings and configuration tab."""

    DEFAULT_CSS = """
    SettingsTab {
        padding: 1;
    }
    SettingsTab .setting-row {
        height: auto;
        margin: 1 0;
    }
    SettingsTab .setting-label {
        width: 30;
    }
    SettingsTab .button-row {
        height: auto;
        margin-top: 2;
    }
    SettingsTab .header {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    SettingsTab .section-header {
        text-style: bold;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_path = Path.home() / ".memoriq" / "config.yaml"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load current config."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def _save_config(self):
        """Save config to file."""
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False)
            return True
        except Exception as e:
            self.notify(f"Failed to save: {e}", severity="error")
            return False

    def compose(self):
        from textual.widgets import Static
        yield Static("## Settings", classes="header")

        # Update settings
        yield Static("### Updates", classes="section-header")

        with Horizontal(classes="setting-row"):
            yield Static("Check for updates on startup:", classes="setting-label")
            check_updates = self.config.get("updates", {}).get("check_on_startup", True)
            yield Switch(value=check_updates, id="check_updates")

        # Language
        with Horizontal(classes="setting-row"):
            yield Static("Language:", classes="setting-label")
            current_lang = self.config.get("language", "en")
            yield Select(
                [("English", "en"), ("Czech", "cs")],
                value=current_lang,
                id="language"
            )

        # Buttons
        with Horizontal(classes="button-row"):
            yield Button("Save Settings", variant="primary", id="save")
            yield Button("Check for Updates", variant="success", id="check_update")
            yield Button("Clear Cache", variant="warning", id="clear_cache")

        yield Static("", id="status")

    def on_switch_changed(self, event) -> None:
        """Handle switch toggle."""
        if event.switch.id == "check_updates":
            if "updates" not in self.config:
                self.config["updates"] = {}
            self.config["updates"]["check_on_startup"] = event.value

    def on_select_changed(self, event) -> None:
        """Handle select change."""
        if event.select.id == "language":
            self.config["language"] = event.value

    def on_button_pressed(self, event) -> None:
        """Handle button presses."""
        if event.button.id == "save":
            if self._save_config():
                self.query_one("#status", Static).update("✓ Settings saved!")
            else:
                self.query_one("#status", Static).update("✗ Failed to save settings")

        elif event.button.id == "check_update":
            self.query_one("#status", Static).update("Checking for updates...")
            # Trigger update check via app
            if hasattr(self.app, "check_for_updates"):
                self.app.check_for_updates()

        elif event.button.id == "clear_cache":
            # Clear query cache
            try:
                from tui.updater import clear_cache
                clear_cache()
                self.query_one("#status", Static).update("✓ Cache cleared")
            except Exception as e:
                self.query_one("#status", Static).update(f"✗ Failed: {e}")
