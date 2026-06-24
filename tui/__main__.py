"""Entry point: python -m memoriq.tui or python ~/.memoriq/tui/__main__.py."""

import sys
from pathlib import Path

# Ensure tui package and mcp-server are importable
tui_dir = Path(__file__).parent
sys.path.insert(0, str(tui_dir.parent))
sys.path.insert(0, str(tui_dir.parent / "mcp-server"))

from tui.app import MemoriqTUI


def main():
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


if __name__ == "__main__":
    main()
