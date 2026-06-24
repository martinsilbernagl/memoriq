"""Interactive installation wizard for Memoriq.

Usage:
    python install.py --wizard    # Run interactive wizard
"""

import sys
from pathlib import Path


def _clear():
    """Clear the terminal screen."""
    print("\033[2J\033[H", end="")


def _print_header(version: str):
    """Print wizard header."""
    print("=" * 50)
    print(f"  Memoriq v{version} Setup Wizard")
    print("=" * 50)
    print()


def _input_default(prompt: str, default: str) -> str:
    """Get input with a default value."""
    value = input(f"{prompt} [{default}]: ").strip()
    return value if value else default


def _select_option(prompt: str, options: list[tuple[str, str]]) -> str:
    """Display options and get selection.

    Returns the value of the selected option.
    """
    print(f"\n{prompt}")
    for i, (label, _) in enumerate(options, 1):
        print(f"  {i}. {label}")

    while True:
        try:
            choice = input(f"Select (1-{len(options)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][1]
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(options)}")


def _confirm(prompt: str, default: bool = True) -> bool:
    """Get yes/no confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        value = input(f"{prompt} {suffix}: ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'")


def _print_section(step: int, total: int, title: str):
    """Print section header."""
    print(f"\n[{step}/{total}] {title}")
    print("-" * 40)


def run_wizard(version: str) -> dict:
    """Run the interactive setup wizard.

    Returns a dictionary with the configuration.
    """
    _clear()
    _print_header(version)

    config = {
        "language": "en",
        "projects_path": str(Path.home() / "projects"),
        "features": {
            "tui": True,
            "code_intelligence": True,
            "vector_search": False,
        },
        "integrations": {
            "claude_code": True,
            "slash_commands": True,
            "codex_cli": False,
        },
    }

    total_steps = 5

    # Step 1: Language preference
    _print_section(1, total_steps, "Language Preference")
    lang = _select_option("Select language:", [
        ("English", "en"),
        ("Czech", "cs"),
    ])
    config["language"] = lang

    # Step 2: Projects directory
    _print_section(2, total_steps, "Projects Directory")
    print("Where do you keep your projects?")
    print("(This is where Memoriq will look for your code)")
    default_path = str(Path.home() / "projects")
    path = _input_default("Projects directory", default_path)
    # Expand ~ and resolve path
    path = Path(path).expanduser().resolve()
    config["projects_path"] = str(path)

    # Create directory if it doesn't exist
    if not path.exists():
        if _confirm(f"Directory does not exist. Create it?", default=True):
            path.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {path}")

    # Step 3: Optional features
    _print_section(3, total_steps, "Optional Features")
    print("Select which features to install:")
    print()

    config["features"]["tui"] = _confirm(
        "Install TUI dashboard (textual)?\n"
        "  Provides: memoriq command for memory browsing",
        default=True
    )
    config["features"]["code_intelligence"] = _confirm(
        "Install code intelligence (tree-sitter)?\n"
        "  Provides: code indexing, symbol search, impact analysis",
        default=True
    )
    config["features"]["vector_search"] = _confirm(
        "Install vector search (fastembed + sqlite-vec)?\n"
        "  Provides: semantic search for facts and code",
        default=False
    )

    # Step 4: Claude Code integration
    _print_section(4, total_steps, "AI Assistant Integration")
    print("Configure integration with AI assistants:")
    print()

    config["integrations"]["claude_code"] = _confirm(
        "Register MCP server for Claude Code?",
        default=True
    )
    config["integrations"]["slash_commands"] = _confirm(
        "Install slash commands for Claude Code?\n"
        "  Provides: /onboard, /harvest, /status, etc.",
        default=True
    )
    config["integrations"]["codex_cli"] = _confirm(
        "Also register for Codex CLI?\n"
        "  (For OpenAI Codex CLI users)",
        default=False
    )

    # Step 5: Review
    _print_section(5, total_steps, "Review Configuration")
    print()
    print("Configuration summary:")
    print(f"  Language:     {config['language']}")
    print(f"  Projects:     {config['projects_path']}")
    print(f"  Features:     ", end="")
    features = []
    if config["features"]["tui"]:
        features.append("TUI")
    if config["features"]["code_intelligence"]:
        features.append("Code Intelligence")
    if config["features"]["vector_search"]:
        features.append("Vector Search")
    print(", ".join(features) if features else "None")

    targets = []
    if config["integrations"]["claude_code"]:
        targets.append("Claude Code")
    if config["integrations"]["codex_cli"]:
        targets.append("Codex CLI")
    print(f"  Target:       {', '.join(targets) if targets else 'None'}")
    print()

    if not _confirm("Proceed with installation?", default=True):
        print("\nInstallation cancelled.")
        sys.exit(0)

    print()
    return config


def generate_config_yaml(config: dict) -> str:
    """Generate config.yaml content from wizard configuration."""
    lines = [
        f'# Memoriq Configuration',
        f'# Generated by setup wizard',
        f'',
        f'language: "{config["language"]}"',
        f'',
        f'projects:',
        f'  base_path: "{config["projects_path"]}"',
        f'',
        f'indexer:',
        f'  scan_depth: 3',
        f'  chunk_max_chars: 2000',
        f'',
        f'search:',
        f'  default_limit: 5',
        f'',
        f'# Features enabled during setup:',
    ]

    if config["features"]["tui"]:
        lines.append('# - TUI Dashboard')
    if config["features"]["code_intelligence"]:
        lines.append('# - Code Intelligence')
    if config["features"]["vector_search"]:
        lines.append('# - Vector Search')

    lines.append('')
    return '\n'.join(lines)


if __name__ == "__main__":
    # Test the wizard
    test_version = "5.0.0"
    config = run_wizard(test_version)
    print("\nGenerated config:")
    print(generate_config_yaml(config))
