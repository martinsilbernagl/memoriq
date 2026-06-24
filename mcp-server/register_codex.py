"""Register Memoriq MCP server in Codex CLI config.toml."""

import shutil
import sys
import tomllib
from pathlib import Path

CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
MEMORIQ_HOME = Path.home() / ".memoriq"


def _escape_toml_string(value: str) -> str:
    """Escape special characters for TOML string value."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _serialize_toml_value(value) -> str:
    """Serialize a Python value to TOML format."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return f'"{_escape_toml_string(value)}"'
    if isinstance(value, list):
        items = ", ".join(_serialize_toml_value(v) for v in value)
        return f"[{items}]"
    return f'"{_escape_toml_string(str(value))}"'


def _write_toml(data: dict, path: Path):
    """Write a dict to TOML file, preserving section structure."""
    lines = []
    top_keys = {k: v for k, v in data.items() if not isinstance(v, dict)}
    nested_keys = {k: v for k, v in data.items() if isinstance(v, dict)}

    # Top-level keys
    for k, v in top_keys.items():
        lines.append(f"{k} = {_serialize_toml_value(v)}")

    if top_keys and nested_keys:
        lines.append("")

    # Nested sections
    for section, values in nested_keys.items():
        has_sub = any(isinstance(v, dict) for v in values.values())
        if has_sub:
            # Write non-dict keys under [section] header first
            simple_keys = {k: v for k, v in values.items() if not isinstance(v, dict)}
            if simple_keys:
                lines.append(f"[{section}]")
                for k, v in simple_keys.items():
                    lines.append(f"{k} = {_serialize_toml_value(v)}")
                lines.append("")
            # Then sub-tables
            for sub_name, sub_values in values.items():
                if isinstance(sub_values, dict):
                    lines.append(f"[{section}.{sub_name}]")
                    for k, v in sub_values.items():
                        lines.append(f"{k} = {_serialize_toml_value(v)}")
                    lines.append("")
        else:
            lines.append(f"[{section}]")
            for k, v in values.items():
                lines.append(f"{k} = {_serialize_toml_value(v)}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def register():
    """Add Memoriq MCP server to ~/.codex/config.toml."""
    home_str = str(MEMORIQ_HOME).replace("\\", "/")
    server_path = f"{home_str}/mcp-server/server.py"
    python_cmd = sys.executable.replace("\\", "/")

    # Read existing config (with error handling for malformed TOML)
    data = {}
    if CODEX_CONFIG.exists():
        try:
            with open(CODEX_CONFIG, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            print(f"[WARNING] Existing config.toml is malformed: {e}")
            backup = CODEX_CONFIG.with_suffix(".toml.bak")
            shutil.copy2(CODEX_CONFIG, backup)
            print(f"  Backed up to {backup}, starting fresh.")
            data = {}

    # Ensure mcp_servers section exists
    if "mcp_servers" not in data:
        data["mcp_servers"] = {}


    # Set Memoriq server entry (idempotent — overwrites existing)
    data["mcp_servers"]["memoriq"] = {
        "command": python_cmd,
        "args": [server_path],
        "startup_timeout_sec": 15,
        "enabled": True,
    }

    # Write config
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _write_toml(data, CODEX_CONFIG)

    print(f"Memoriq registered in {CODEX_CONFIG}")
    print(f"  MCP server: {server_path}")
    print(f"  Command: {python_cmd}")
    print(f"  Note: Codex has no hooks. Use AGENTS.md instructions instead.")
    return data


if __name__ == "__main__":
    register()
