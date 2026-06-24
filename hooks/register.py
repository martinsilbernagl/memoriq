"""Register Memoriq in Claude Code settings.json."""

import json
import platform
import sys
from pathlib import Path

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
MEMORIQ_HOME = Path.home() / ".memoriq"

# Virtual environment Python path
VENV_PATH = MEMORIQ_HOME / "venv"
VENV_PYTHON = VENV_PATH / "bin" / "python" if platform.system() != "Windows" else VENV_PATH / "Scripts" / "python.exe"


def register():
    """Add Memoriq MCP server and hooks to settings.json."""
    # Use forward slashes for all paths (Git Bash compatibility on Windows)
    home_str = str(MEMORIQ_HOME).replace("\\", "/")
    server_path = f"{home_str}/mcp-server/server.py"

    # Read existing settings
    settings = {}
    if CLAUDE_SETTINGS.exists():
        settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))

    # Add MCP server
    if "mcpServers" not in settings:
        settings["mcpServers"] = {}


    # Use venv Python if available, otherwise fall back to sys.executable
    if VENV_PYTHON.exists():
        python_cmd = str(VENV_PYTHON).replace("\\", "/")
    else:
        python_cmd = sys.executable.replace("\\", "/")

    settings["mcpServers"]["memoriq"] = {
        "command": python_cmd,
        "args": [server_path]
    }

    # Add hooks
    if "hooks" not in settings:
        settings["hooks"] = {}

    hook_start = f'"{python_cmd}" "{home_str}/hooks/on_session_start.py"'
    hook_end = f'"{python_cmd}" "{home_str}/hooks/on_session_end.py"'
    hook_change = f'"{python_cmd}" "{home_str}/hooks/on_file_change.py"'
    hook_compact = f'"{python_cmd}" "{home_str}/hooks/on_pre_compact.py"'

    memoriq_hooks = {
        "SessionStart": {
            "matcher": "*",
            "hooks": [{"type": "command", "command": hook_start}]
        },
        "SessionEnd": {
            "matcher": "*",
            "hooks": [{"type": "command", "command": hook_end}]
        },
        "PreCompact": {
            "matcher": "*",
            "hooks": [{"type": "command", "command": hook_compact}]
        },
        "PostToolUse": {
            "matcher": "Write|Edit|NotebookEdit",
            "hooks": [{"type": "command", "command": hook_change}]
        },
    }

    for hook_type, new_entry in memoriq_hooks.items():
        existing = settings.get("hooks", {}).get(hook_type, [])
        # Remove any existing Memoriq entries
        filtered = [
            entry for entry in existing
            if not any(
                "memoriq" in h.get("command", "") or ".memoriq" in h.get("command", "")
                for h in entry.get("hooks", [])
            )
        ]
        # Append the new Memoriq hook entry
        filtered.append(new_entry)
        settings["hooks"][hook_type] = filtered

    # Write back
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    print(f"Memoriq registered in {CLAUDE_SETTINGS}")
    print(f"  MCP server: {server_path}")
    print(f"  Hooks: SessionStart, SessionEnd, PreCompact, PostToolUse")
    return settings


if __name__ == "__main__":
    register()
