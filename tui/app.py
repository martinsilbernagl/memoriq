"""Memoriq TUI Dashboard — Main application."""

import sys
import threading
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static, Input, Label
from textual.containers import Horizontal, Vertical
from textual.binding import Binding

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-server"))

from tui.screens.overview import OverviewScreen
from tui.screens.facts import FactsScreen
from tui.screens.heatmap import HeatmapScreen
from tui.screens.clusters import ClustersScreen
from tui.screens.timeline import TimelineScreen
from tui.screens.gaps import GapsScreen
from tui.screens.contradictions import ContradictionsScreen
from tui.screens.code_graph import CodeGraphScreen
from tui.screens.help import HelpScreen
from tui.screens.settings import SettingsTab
from tui.updater import check_for_update, run_update
from tui.widgets.notification import NotificationContainer
import yaml


def _get_version() -> str:
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "3"


class MemoriqTUI(App):
    """Memoriq Memory Dashboard with modern UI."""

    TITLE = f"🧠 Memoriq v{_get_version()}"
    SUB_TITLE = ""
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f5", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
        Binding("s", "settings", "Settings"),
        Binding("u", "update", "Update"),
        Binding("ctrl+k", "command_palette", "Command", show=True),
        Binding("1", "tab_1", "Overview"),
        Binding("2", "tab_2", "Facts"),
        Binding("3", "tab_3", "Heatmap"),
        Binding("4", "tab_4", "Clusters"),
        Binding("5", "tab_5", "Timeline"),
        Binding("6", "tab_6", "Gaps"),
        Binding("7", "tab_7", "Contradictions"),
        Binding("8", "tab_8", "Code Graph"),
        Binding("9", "tab_9", "Settings"),
    ]

    def __init__(self, project: str | None = None, **kwargs):
        self.project = project
        self.show_palette = False
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Header()
        yield NotificationContainer(id="notifications")

        with Vertical(id="main-container"):
            # Command palette (hidden by default)
            with Vertical(id="command-palette", classes="hidden"):
                yield Input(placeholder="Type a command...", id="palette-input")

            # Tabs with icons
            with TabbedContent(id="tabs"):
                with TabPane("📊 Overview", id="tab-overview"):
                    yield OverviewScreen(project=self.project)
                with TabPane("📋 Facts", id="tab-facts"):
                    yield FactsScreen(project=self.project)
                with TabPane("🗺️ Heatmap", id="tab-heatmap"):
                    yield HeatmapScreen(project=self.project)
                with TabPane("🔍 Clusters", id="tab-clusters"):
                    yield ClustersScreen(project=self.project)
                with TabPane("📅 Timeline", id="tab-timeline"):
                    yield TimelineScreen(project=self.project)
                with TabPane("⚠️ Gaps", id="tab-gaps"):
                    yield GapsScreen(project=self.project)
                with TabPane("🔀 Contradictions", id="tab-contradictions"):
                    yield ContradictionsScreen(project=self.project)
                with TabPane("🕸️ Code Graph", id="tab-code-graph"):
                    yield CodeGraphScreen(project=self.project)
                with TabPane("⚙️ Settings", id="tab-settings"):
                    yield SettingsTab()

        yield Footer()

    def action_command_palette(self) -> None:
        """Toggle command palette."""
        palette = self.query_one("#command-palette", Vertical)
        if "hidden" in palette.classes:
            palette.remove_class("hidden")
            self.query_one("#palette-input", Input).focus()
        else:
            palette.add_class("hidden")
            self.query_one("#tabs", TabbedContent).focus()

    def on_input_changed(self, event) -> None:
        """Handle command palette input."""
        if event.input.id == "palette-input":
            # Simple command routing
            cmd = event.value.lower().strip()
            if cmd == "overview" or cmd == "1":
                self.action_tab_1()
            elif cmd == "facts" or cmd == "2":
                self.action_tab_2()
            elif cmd == "heatmap" or cmd == "3":
                self.action_tab_3()
            elif cmd == "settings" or cmd == "9":
                self.action_tab_9()
            elif cmd == "quit" or cmd == "exit":
                self.action_quit()
            elif cmd == "update":
                self.action_update()

    def action_tab_1(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-overview"

    def action_tab_2(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-facts"

    def action_tab_3(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-heatmap"

    def action_tab_4(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-clusters"

    def action_tab_5(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-timeline"

    def action_tab_6(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-gaps"

    def action_tab_7(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-contradictions"

    def action_tab_8(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-code-graph"

    def action_tab_9(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-settings"

    def action_settings(self) -> None:
        """Open settings tab."""
        self.query_one("#tabs", TabbedContent).active = "tab-settings"

    def action_update(self) -> None:
        """Check for and install updates."""
        # First check if update is available
        def check_then_update():
            result = check_for_update()
            if result and result.get("has_update"):
                self.call_from_thread(self._confirm_and_update, result["local"], result["remote"])
            else:
                self.call_from_thread(self._show_no_update_notification)

        threading.Thread(target=check_then_update, daemon=True).start()

    def _confirm_and_update(self, local: str, remote: str) -> None:
        """Show confirmation dialog and run update."""
        from textual.screen import Screen
        from textual.widgets import Static, Button
        from textual.containers import Vertical, Horizontal

        class ConfirmUpdateScreen(Screen):
            def compose(self):
                with Vertical(id="dialog"):
                    yield Static(f"Update available: v{local} → v{remote}")
                    yield Static("This will:\n  • Pull latest changes from git\n  • Install dependencies\n  • Run database migrations\n  • Restart required after update")
                    with Horizontal(id="buttons"):
                        yield Button("Update Now", variant="success", id="update")
                        yield Button("Cancel", variant="error", id="cancel")

            def on_button_pressed(self, event):
                if event.button.id == "update":
                    self.dismiss(True)
                else:
                    self.dismiss(False)

        def on_confirm(confirmed: bool):
            if confirmed:
                self._run_update()

        self.push_screen(ConfirmUpdateScreen(), on_confirm)

    def _run_update(self) -> None:
        """Run the update process."""
        self._notify("Starting update...", "info", 3.0)

        def do_update():
            success, message = run_update()
            if success:
                self.call_from_thread(
                    self._notify,
                    f"Update complete! {message}",
                    "success",
                    10.0
                )
            else:
                self.call_from_thread(
                    self._notify,
                    f"Update failed: {message}",
                    "error",
                    10.0
                )

        threading.Thread(target=do_update, daemon=True).start()

    def _notify(self, message: str, notif_type: str = "info", dismiss_after: float = 5.0) -> None:
        """Show a notification."""
        try:
            notif_container = self.query_one("#notifications", NotificationContainer)
            notif_container.notify(message, notif_type, dismiss_after)
        except Exception:
            pass

    def on_mount(self) -> None:
        """Called when app is mounted. Check for updates if enabled."""
        # Check if auto-update check is enabled
        try:
            config_path = Path.home() / ".memoriq" / "config.yaml"
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f) or {}
                updates_config = config.get("updates", {})
                if updates_config.get("check_on_startup", True):
                    # Delay slightly to let UI render first
                    self.set_timer(2, self.check_for_updates)
        except Exception:
            pass

    def check_for_updates(self, manual: bool = False) -> None:
        """Check for updates and notify user if available."""
        def do_check():
            result = check_for_update()
            if result and result.get("has_update"):
                local = result["local"]
                remote = result["remote"]
                self.call_from_thread(self._show_update_notification, local, remote)
            elif manual:
                self.call_from_thread(self._show_no_update_notification)

        # Run check in background thread
        import threading
        threading.Thread(target=do_check, daemon=True).start()

    def _show_update_notification(self, local: str, remote: str) -> None:
        """Show update available notification."""
        self._notify(
            f"Update available: v{local} → v{remote}\nPress [U] to update or see Settings",
            "info",
            10.0
        )

    def _show_no_update_notification(self) -> None:
        """Show no updates available notification."""
        self._notify(
            "No updates available. You're on the latest version!",
            "success",
            5.0
        )

    def action_refresh(self) -> None:
        """Refresh by remounting the active tab content."""
        self.notify("Refreshing...", severity="information")
        # Simple approach: exit and re-run
        # For now just notify — full refresh would require remounting widgets

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())


def _reindex_project(project: str | None = None):
    """Reindex project files - called via 'memoriq reindex' command."""
    import sqlite3
    from pathlib import Path
    from indexer.file_indexer import reindex_project
    from db import open_db_fast

    db_path = Path.home() / ".memoriq" / "memory.db"
    if not db_path.exists():
        print("Error: Memoriq database not found. Run memoriq setup first.")
        sys.exit(1)

    db = open_db_fast()
    try:
        if project:
            # Reindex specific project
            row = db.execute(
                "SELECT name, path FROM projects WHERE name = ?",
                (project,)
            ).fetchone()
            if not row:
                print(f"Error: Project '{project}' not found.")
                sys.exit(1)
            projects_to_reindex = [(row[0], Path(row[1]))]
        else:
            # Reindex current directory project
            cwd = Path.cwd()
            project_name = None
            project_path = None

            # Try to detect project name from current directory
            pkg = cwd / "package.json"
            if pkg.exists():
                try:
                    import json
                    data = json.loads(pkg.read_text(encoding="utf-8"))
                    project_name = data.get("name", cwd.name)
                except Exception:
                    project_name = cwd.name
            else:
                pyproj = cwd / "pyproject.toml"
                if pyproj.exists():
                    try:
                        for line in pyproj.read_text(encoding="utf-8").splitlines():
                            if line.strip().startswith("name"):
                                project_name = line.split("=")[1].strip().strip('"')
                                break
                    except Exception:
                        project_name = cwd.name
                else:
                    project_name = cwd.name

            # Check if project is registered
            row = db.execute(
                "SELECT name, path FROM projects WHERE name = ?",
                (project_name,)
            ).fetchone()
            if row:
                projects_to_reindex = [(row[0], Path(row[1]))]
            else:
                # Use current directory
                projects_to_reindex = [(project_name, cwd)]

        # Perform reindexing
        for name, path in projects_to_reindex:
            if path.exists():
                print(f"Reindexing project: {name}...")
                reindex_project(db, name, path, time_budget=30.0)
                print(f"  ✓ {name} reindexed successfully")
            else:
                print(f"  ✗ Path not found for {name}: {path}")

        db.commit()
        print("\nReindex complete!")
    except Exception as e:
        print(f"Error during reindex: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    # Show version if requested
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        version = _get_version()
        print(f"Memoriq v{version}")
        sys.exit(0)

    # Show help if requested
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        version = _get_version()
        print(f"Memoriq v{version}")
        print("")
        print("Usage: memoriq [COMMAND] [OPTIONS]")
        print("")
        print("Commands:")
        print("  reindex [PROJECT]    Reindex project files")
        print("  update --check       Check for updates")
        print("  --project NAME       Open TUI for specific project")
        print("  --demo               Run TUI in demo mode")
        print("  --version, -v        Show version")
        print("  --help, -h           Show this help message")
        print("")
        print("With no command, opens the TUI dashboard.")
        sys.exit(0)

    # Check for update --check command
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        if len(sys.argv) > 2 and sys.argv[2] == "--check":
            from tui.updater import check_for_update
            result = check_for_update()
            if result and result.get("has_update"):
                print(f"Update available: v{result['local']} → v{result['remote']}")
                print("Run 'memoriq' and press [U] to update, or run 'git pull' in ~/.memoriq")
            else:
                version = _get_version()
                print(f"Memoriq v{version} — you're on the latest version!")
            sys.exit(0)
        else:
            print("Usage: memoriq update --check")
            sys.exit(1)

    # Check for reindex command
    if len(sys.argv) > 1 and sys.argv[1] == "reindex":
        if len(sys.argv) > 2 and sys.argv[2] in ("--help", "-h"):
            print("Usage: memoriq reindex [PROJECT]")
            print("")
            print("Reindex project files for the current directory or specified project.")
            print("")
            print("Arguments:")
            print("  PROJECT    Optional project name to reindex")
            print("             If not provided, uses the current directory")
            print("")
            print("Examples:")
            print("  memoriq reindex           # Reindex current directory")
            print("  memoriq reindex myapp     # Reindex project 'myapp'")
            sys.exit(0)
        project_arg = sys.argv[2] if len(sys.argv) > 2 else None
        _reindex_project(project_arg)
        sys.exit(0)

    project = None
    demo_mode = "--demo" in sys.argv

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--project" and i < len(sys.argv) - 1:
            project = sys.argv[i + 1]

    if demo_mode:
        from tui.demo import create_demo_db
        import tui.data as data_module
        demo_path = create_demo_db()
        data_module.DB_PATH = Path(demo_path)

    app = MemoriqTUI(project=project)
    app.run()

    # Cleanup demo DB
    if demo_mode:
        try:
            Path(demo_path).unlink(missing_ok=True)
        except Exception:
            pass
