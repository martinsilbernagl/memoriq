"""Tab 4: Clusters — Cluster tree view."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Tree

from tui.widgets.heat_cell import heat_color
from tui import data


class ClustersScreen(Static):
    """Cluster browser with tree widget."""

    DEFAULT_CSS = """
    ClustersScreen {
        height: 1fr;
    }
    #cluster-tree {
        width: 1fr;
        height: 1fr;
    }
    #cluster-detail {
        width: 40%;
        height: 1fr;
        border-left: solid $surface;
        padding: 1;
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
        self._clusters = []
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Tree("📦 Clusters", id="cluster-tree")
            yield Static("[dim]Select a cluster to see details[/]", id="cluster-detail")

    def on_mount(self) -> None:
        tree = self.query_one("#cluster-tree", Tree)

        # Check if we have any facts first
        stats = data.get_stats(self.project)
        if stats["facts"] == 0:
            self._show_empty_state("No facts in memory. Run /onboard first.")
            return

        self._clusters = data.get_clusters(self.project)

        if not self._clusters:
            self._show_empty_state(
                "No clusters found.\n\n"
                "Clusters are created automatically when you run /consolidate.\n"
                "They group related facts together."
            )
            return

        for cluster in self._clusters:
            label = cluster.get("label") or f"Cluster #{cluster['id']}"
            count = cluster.get("fact_count", 0)
            node = tree.root.add(f"📦 {label} ({count} facts)", data=cluster)

            for member in cluster.get("members", []):
                preview = member.get("preview", "?")
                heat = member.get("heat_score", 0) or 0
                color = heat_color(heat)
                icon = "🔥" if heat >= 0.7 else "🌡️" if heat >= 0.3 else "❄️"
                node.add_leaf(f"{icon} [{color}]{member.get('type', '?')}[/] {preview}")

        tree.root.expand_all()

    def _show_empty_state(self, message: str) -> None:
        """Show empty state message."""
        tree = self.query_one("#cluster-tree", Tree)
        tree.root.add_leaf(f"[yellow]{message}[/]")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        detail = self.query_one("#cluster-detail", Static)
        node_data = event.node.data

        if not node_data or not isinstance(node_data, dict):
            return

        label = node_data.get("label") or f"Cluster #{node_data.get('id', '?')}"
        summary = node_data.get("summary") or "No summary"
        count = node_data.get("fact_count", 0)
        project = node_data.get("project", "?")

        detail.update(
            f"[bold]📦 {label}[/]\n\n"
            f"Project: {project}\n"
            f"Facts: {count}\n"
            f"Created: {node_data.get('created', '?')}\n\n"
            f"[dim]{summary}[/]"
        )
