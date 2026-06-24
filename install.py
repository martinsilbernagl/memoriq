"""Memoriq installer — copies files to ~/.memoriq/ and registers in Claude Code.

Usage:
    python install.py           # Install for Claude Code (default)
    python install.py --codex   # Install for Codex CLI
    python install.py --both    # Install for both
    python install.py --wizard  # Interactive setup wizard
"""

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MEMORIQ_HOME = Path.home() / ".memoriq"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CLAUDE_COMMANDS = Path.home() / ".claude" / "commands"
REPO_DIR = Path(__file__).parent.resolve()
VERSION = (REPO_DIR / "VERSION").read_text(encoding="utf-8").strip()
IS_SAME_DIR = REPO_DIR.resolve() == MEMORIQ_HOME.resolve()

# Virtual environment path (inside memoriq home)
VENV_PATH = MEMORIQ_HOME / "venv"
VENV_PYTHON = VENV_PATH / "Scripts" / "python.exe" if sys.platform == "win32" else VENV_PATH / "bin" / "python"
VENV_PIP = VENV_PATH / "Scripts" / "pip.exe" if sys.platform == "win32" else VENV_PATH / "bin" / "pip"


def ensure_venv():
    """Ensure virtual environment exists and has dependencies."""
    venv_path = MEMORIQ_HOME / "venv"

    if not venv_path.exists():
        print("[Memoriq] Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        print(f"[Memoriq] Virtual environment created at {venv_path}")

    pip_path = venv_path / "bin" / "pip"
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"

    # Check if mcp is installed, if not install dependencies
    try:
        result = subprocess.run(
            [str(pip_path), "show", "mcp"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError("mcp not installed")
    except Exception:
        print("[Memoriq] Installing dependencies in virtual environment...")
        req_file = REPO_DIR / "requirements.txt"
        subprocess.run([
            str(pip_path), "install", "-r", str(req_file)
        ], check=True)
        print("[Memoriq] Dependencies installed successfully")

    return venv_path


def _ensure_venv():
    """Ensure we're running from the memoriq virtual environment."""
    # Check if already in venv
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return  # Already in a venv

    # Check if memoriq venv exists
    if VENV_PYTHON.exists():
        print("[!] Detected Memoriq virtual environment.")
        print(f"    Re-running with: {VENV_PYTHON}")
        # Re-run this script with the venv Python
        result = subprocess.run([str(VENV_PYTHON), __file__] + sys.argv[1:])
        sys.exit(result.returncode)
    else:
        print("[!] Virtual environment not found.")
        print(f"    Creating one at: {VENV_PATH}")
        print("    This is required because your system Python is externally managed.")

        # Create venv using ensure_venv
        ensure_venv()

        # Re-run with venv
        print(f"    Re-running with: {VENV_PYTHON}")
        result = subprocess.run([str(VENV_PYTHON), __file__] + sys.argv[1:])
        sys.exit(result.returncode)


# Check venv before anything else
_ensure_venv()


def _find_scripts_dir() -> Path | None:
    """Find Python Scripts/bin directory that's likely in PATH."""
    if sys.platform == "win32":
        # Python Scripts dir (usually in PATH on Windows)
        scripts = Path(sys.executable).parent / "Scripts"
        if scripts.exists():
            return scripts
    else:
        # ~/.local/bin is standard on Linux/Mac
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        return local_bin
    return None


def check_python_version():
    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required (for tomllib). You have {sys.version}")
        sys.exit(1)


def _pip_install(package: str, label: str = None):
    """Install a pip package, with clear error on failure."""
    label = label or package
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
        )
        print(f"[ok] {label} installed")
    except subprocess.CalledProcessError:
        print(f"[ERROR] Failed to install {label}.")
        print(f"  Run manually: {sys.executable} -m pip install {package}")
        sys.exit(1)


def check_mcp_installed():
    try:
        import mcp  # noqa: F401
        print("[ok] mcp package found")
    except ImportError:
        print("[!] mcp package not found. Installing...")
        _pip_install("mcp")


def check_pyyaml_installed():
    try:
        import yaml  # noqa: F401
        print("[ok] pyyaml package found")
    except ImportError:
        print("[!] pyyaml package not found. Installing...")
        _pip_install("pyyaml")


def check_textual_installed():
    try:
        import textual  # noqa: F401
        print(f"[ok] textual package found (v{textual.__version__})")
    except ImportError:
        print("[!] textual not found. Installing (needed for TUI dashboard)...")
        _pip_install("textual")


def check_treesitter_installed():
    try:
        import tree_sitter_language_pack  # noqa: F401
        print("[ok] tree-sitter-language-pack found")
    except ImportError:
        print("[!] tree-sitter-language-pack not found. Installing (needed for Code Intelligence)...")
        _pip_install("tree-sitter-language-pack")


def backup_database():
    """Backup memory.db before migration if it exists."""
    db_path = MEMORIQ_HOME / "memory.db"
    if db_path.exists():
        backup_name = f"memory.db.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        backup_path = MEMORIQ_HOME / backup_name
        shutil.copy2(db_path, backup_path)
        print(f"  [ok] Database backed up: {backup_name}")


def _build_wrapper_script() -> str:
    """Build the wrapper script content with auto-git-init."""
    return f'''#!/usr/bin/env bash
# Memoriq TUI Launcher - Auto-updating wrapper

MEMORIQ_HOME="{MEMORIQ_HOME}"
VENV_PYTHON="{VENV_PYTHON}"

# Ensure git repository is initialized (for updates)
if [ ! -d "$MEMORIQ_HOME/.git" ]; then
    echo "[memoriq] Initializing update repository..."
    cd "$MEMORIQ_HOME"
    git init --quiet 2>/dev/null
    git remote add origin ssh://tajny.domapp.tech:2222/domess/Memoriq.git 2>/dev/null || true
    git fetch origin main --quiet 2>/dev/null || echo "[memoriq] Note: Could not fetch updates (ssh key may be needed)"
fi

# Launch TUI
cd "$MEMORIQ_HOME"
"$VENV_PYTHON" -m tui "$@"
'''


def install_cli_wrapper():
    """Install 'memoriq' command so users can type it from anywhere."""
    scripts_dir = _find_scripts_dir()
    if not scripts_dir:
        print("  [skip] Could not find Scripts directory for CLI wrapper")
        return

    if sys.platform == "win32":
        wrapper = scripts_dir / "memoriq.bat"
        wrapper.write_text(
            '@echo off\n'
            f'cd /d "{MEMORIQ_HOME}"\n'
            f'"{VENV_PYTHON}" -m tui %*\n',
            encoding="utf-8",
        )
        print(f"  [ok] CLI wrapper installed: {wrapper}")
    else:
        wrapper = scripts_dir / "memoriq"
        wrapper.write_text(_build_wrapper_script(), encoding="utf-8")
        wrapper.chmod(0o755)
        print(f"  [ok] CLI wrapper installed: {wrapper}")

        # Check if ~/.local/bin is in PATH
        path_dirs = (os.environ.get("PATH") or "").split(":")
        if str(scripts_dir) not in path_dirs:
            print(f"  [!] Add to PATH: export PATH=\"{scripts_dir}:$PATH\"")


def _safe_copy(src: Path, dst: Path, label: str):
    """Copy file, skip if src == dst (running from ~/.memoriq/)."""
    if src.resolve() == dst.resolve():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  [copy] {label}")


def copy_files():
    """Copy source files to ~/.memoriq/"""
    if IS_SAME_DIR:
        print("  [info] Running from ~/.memoriq/ — skipping file copy (already in place)")
        install_cli_wrapper()
        return
    dirs_to_create = [
        MEMORIQ_HOME,
        MEMORIQ_HOME / "mcp-server" / "indexer",
        MEMORIQ_HOME / "mcp-server" / "search",
        MEMORIQ_HOME / "mcp-server" / "tools",
        MEMORIQ_HOME / "mcp-server" / "code" / "parsers",
        MEMORIQ_HOME / "hooks",
        MEMORIQ_HOME / "logs",
        MEMORIQ_HOME / "cache" / "embeddings",
        MEMORIQ_HOME / "tui" / "screens",
        MEMORIQ_HOME / "tui" / "widgets",
        CLAUDE_COMMANDS,
    ]
    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    # Copy MCP server files
    mcp_src = REPO_DIR / "mcp-server"
    mcp_dst = MEMORIQ_HOME / "mcp-server"

    for src_file in mcp_src.rglob("*.py"):
        rel = src_file.relative_to(mcp_src)
        dst_file = mcp_dst / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        print(f"  [copy] mcp-server/{rel}")

    # Copy hooks
    hooks_src = REPO_DIR / "hooks"
    hooks_dst = MEMORIQ_HOME / "hooks"
    for src_file in hooks_src.glob("*.py"):
        shutil.copy2(src_file, hooks_dst / src_file.name)
        print(f"  [copy] hooks/{src_file.name}")

    # Copy TUI dashboard
    tui_src = REPO_DIR / "tui"
    tui_dst = MEMORIQ_HOME / "tui"
    if tui_src.exists():
        for src_file in tui_src.rglob("*.py"):
            rel = src_file.relative_to(tui_src)
            dst_file = tui_dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"  [copy] tui/{rel}")
        for src_file in tui_src.rglob("*.tcss"):
            rel = src_file.relative_to(tui_src)
            dst_file = tui_dst / rel
            shutil.copy2(src_file, dst_file)
            print(f"  [copy] tui/{rel}")

    # Copy config
    config_src = REPO_DIR / "config.yaml"
    config_dst = MEMORIQ_HOME / "config.yaml"
    if not config_dst.exists():
        shutil.copy2(config_src, config_dst)
        print("  [copy] config.yaml (new)")
    else:
        print("  [skip] config.yaml (already exists, not overwriting)")

    # Copy onboard helper
    helper_src = REPO_DIR / "onboard_helper.py"
    if helper_src.exists():
        shutil.copy2(helper_src, MEMORIQ_HOME / "onboard_helper.py")
        print("  [copy] onboard_helper.py")

    # Copy diagnostic tool
    diag_src = REPO_DIR / "diagnose.py"
    if diag_src.exists():
        shutil.copy2(diag_src, MEMORIQ_HOME / "diagnose.py")
        print("  [copy] diagnose.py")

    # Copy VERSION file
    shutil.copy2(REPO_DIR / "VERSION", MEMORIQ_HOME / "VERSION")
    print(f"  [copy] VERSION ({VERSION})")

    # Install CLI wrapper (memoriq command)
    install_cli_wrapper()

    # Copy slash commands (locale-aware)
    config_dst = MEMORIQ_HOME / "config.yaml"
    language = "en"
    if config_dst.exists():
        try:
            import yaml
            with open(config_dst, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            language = cfg.get("language", "en")
        except Exception:
            pass
    commands_src = REPO_DIR / "commands" / language
    if not commands_src.exists():
        commands_src = REPO_DIR / "commands" / "en"
    for src_file in commands_src.glob("*.md"):
        shutil.copy2(src_file, CLAUDE_COMMANDS / src_file.name)
        print(f"  [copy] commands/{language}/{src_file.name}")


def init_database():
    """Initialize SQLite database."""
    sys.path.insert(0, str(MEMORIQ_HOME / "mcp-server"))
    from init_db import init_db
    tables, all_names = init_db()
    print(f"  [ok] Database initialized: {len(all_names)} objects")


def register_mcp(codex: bool = False):
    """Register MCP server and hooks in Claude Code or Codex CLI."""
    sys.path.insert(0, str(MEMORIQ_HOME / "hooks"))
    sys.path.insert(0, str(MEMORIQ_HOME / "mcp-server"))
    if codex:
        from register_codex import register
        register()
    else:
        from register import register
        register()


def test_server():
    """Test the server as a subprocess — exactly as Claude Code would start it.

    This catches dependency issues that in-process imports would miss
    (e.g., mcp not installed for the registered Python version).
    """
    import json as json_mod

    # Read registration info
    registered_python = sys.executable.replace("\\", "/")
    server_path = str(MEMORIQ_HOME / "mcp-server" / "server.py").replace("\\", "/")

    if CLAUDE_SETTINGS.exists():
        settings = json_mod.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        mcp_cfg = settings.get("mcpServers", {}).get("memoriq", {})
        if mcp_cfg:
            registered_python = mcp_cfg.get("command", registered_python)
            server_path = (mcp_cfg.get("args") or [server_path])[0]
            print(f"[ok] MCP server registered in settings.json")
            print(f"     command: {registered_python}")
            print(f"     server:  {server_path}")
        else:
            print("[WARNING] MCP server NOT found in settings.json — registration may have failed")
    else:
        print("[WARNING] ~/.claude/settings.json not found — Claude Code may not be installed")

    # Verify Python executable exists
    python_path = Path(registered_python.replace("/", os.sep))
    if not python_path.exists():
        print(f"\n[WARNING] Python executable not found: {registered_python}")
        print(f"          MCP server will fail to start!")
        print(f"          Fix: re-run install.py with the correct Python")
        return

    # Actually run the server --test as subprocess (catches missing deps)
    print(f"\n  Testing server startup (subprocess)...")
    try:
        result = subprocess.run(
            [registered_python, server_path, "--test"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Count tools from output
            for line in result.stdout.split("\n"):
                if "Registered tools:" in line:
                    print(f"  {line.strip()}")
                if line.startswith("OK:") or line.startswith("\nOK:"):
                    print(f"\n[ok] {line.strip()}")
        else:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            error = stderr or stdout
            print(f"\n[ERROR] Server test failed (exit code {result.returncode}):")
            # Show error, highlighting missing modules
            for line in error.split("\n"):
                if "ModuleNotFoundError" in line or "ImportError" in line:
                    print(f"  >>> {line}")
                    # Extract module name and suggest fix
                    if "No module named" in line and "'" in line:
                        module = line.split("'")[1]
                        print(f"\n  Fix: \"{registered_python}\" -m pip install {module}")
                elif line.strip():
                    print(f"  {line}")
    except subprocess.TimeoutExpired:
        print(f"\n[WARNING] Server test timed out (30s)")
    except Exception as e:
        print(f"\n[ERROR] Could not test server: {e}")


def generate_agents_md():
    """Generate AGENTS.md in current directory for Codex CLI."""
    try:
        sys.path.insert(0, str(MEMORIQ_HOME / "hooks"))
        sys.path.insert(0, str(MEMORIQ_HOME / "mcp-server"))
        from generate_agents_md import main as gen_main
        gen_main()
    except Exception as e:
        print(f"  [WARNING] Could not generate AGENTS.md: {e}")
        print(f"  Run manually: python {MEMORIQ_HOME}/hooks/generate_agents_md.py")


def _write_config_from_wizard(config: dict):
    """Write config.yaml from wizard configuration."""
    from wizard import generate_config_yaml
    config_path = MEMORIQ_HOME / "config.yaml"
    config_content = generate_config_yaml(config)
    config_path.write_text(config_content, encoding="utf-8")
    print(f"  [ok] Config written: {config_path}")


def main():
    codex_mode = "--codex" in sys.argv
    both_mode = "--both" in sys.argv
    wizard_mode = "--wizard" in sys.argv
    target = "Codex CLI" if codex_mode else "Both" if both_mode else "Claude Code"
    need_codex = codex_mode or both_mode

    # Run wizard if requested
    wizard_config = None
    if wizard_mode:
        from wizard import run_wizard
        wizard_config = run_wizard(VERSION)
        # Update modes based on wizard selection
        codex_mode = wizard_config["integrations"]["codex_cli"] and not wizard_config["integrations"]["claude_code"]
        both_mode = wizard_config["integrations"]["codex_cli"] and wizard_config["integrations"]["claude_code"]
        target = "Codex CLI" if codex_mode else "Both" if both_mode else "Claude Code"
        need_codex = wizard_config["integrations"]["codex_cli"]

    total_steps = 7 if need_codex else 6

    print("=" * 50)
    print(f"  Memoriq v{VERSION} Installer ({target})")
    print("=" * 50)
    print()

    print(f"[1/{total_steps}] Checking Python version...")
    check_python_version()
    print(f"  [ok] Python {sys.version.split()[0]}")

    print(f"\n[2/{total_steps}] Checking dependencies...")
    check_mcp_installed()
    check_pyyaml_installed()
    check_textual_installed()
    check_treesitter_installed()
    print("  [info] Optional (vector search): pip install fastembed sqlite-vec")

    # Install optional features selected in wizard
    if wizard_config:
        if wizard_config["features"]["vector_search"]:
            print("\n  [info] Installing vector search (selected in wizard)...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "fastembed", "sqlite-vec"],
                    stdout=subprocess.DEVNULL,
                )
                print("  [ok] Vector search installed")
            except subprocess.CalledProcessError:
                print("  [WARNING] Failed to install vector search packages")

    print(f"\n[3/{total_steps}] Copying files...")
    copy_files()

    # Write config from wizard if used
    if wizard_config:
        print(f"\n[3a/{total_steps}] Writing configuration...")
        _write_config_from_wizard(wizard_config)

    print(f"\n[4/{total_steps}] Backing up database...")
    backup_database()

    print(f"\n[5/{total_steps}] Initializing database...")
    init_database()

    print(f"\n[6/{total_steps}] Registering...")
    if both_mode:
        register_mcp(codex=False)
        print()
        register_mcp(codex=True)
    else:
        register_mcp(codex=codex_mode)

    if need_codex:
        print(f"\n[7/{total_steps}] Generating AGENTS.md for Codex CLI...")
        generate_agents_md()

    # Run verification
    print("\nRunning verification...")
    test_server()

    # Show diagnostic summary
    python_cmd = sys.executable.replace("\\", "/")
    print("\n" + "=" * 50)
    print(f"  Memoriq v{VERSION} — Installation complete!")
    print("=" * 50)
    print()
    print(f"  Python:     {python_cmd}")
    print(f"  Home:       {str(MEMORIQ_HOME).replace(chr(92), '/')}")
    if not codex_mode:
        print(f"  Settings:   {str(CLAUDE_SETTINGS).replace(chr(92), '/')}")
    print()

    if codex_mode:
        print("  Next steps:")
        print("  1. Open your project directory and run: codex")
        print("  2. Codex will auto-detect Memoriq via AGENTS.md")
        print("  3. It will call session_init() to load project context")
        print("  4. Say: 'Scan this project and build memory' for onboarding")
        print("  5. Say: 'Index the source code' for code intelligence")
        print("  6. Run 'memoriq' in terminal for TUI dashboard")
        print()
        print("  For each new project, generate AGENTS.md:")
        print(f"  python {MEMORIQ_HOME}/hooks/generate_agents_md.py".replace("\\", "/"))
    elif both_mode:
        print("  Next steps:")
        print("  1. Restart Claude Code (required for MCP server to connect)")
        print("  2. Edit ~/.memoriq/config.yaml — set projects.base_path")
        print("  3. Claude Code: Run /onboard to build initial memory")
        print("  4. Codex CLI: Open project dir and run 'codex'")
        print("  5. Run 'memoriq' in terminal for TUI dashboard")
        print()
        print("  For each new Codex project, generate AGENTS.md:")
        print(f"  python {MEMORIQ_HOME}/hooks/generate_agents_md.py".replace("\\", "/"))
    else:
        print("  Next steps:")
        print("  1. Restart Claude Code (required for MCP server to connect)")
        print("  2. Edit ~/.memoriq/config.yaml — set projects.base_path")
        print("  3. Run /onboard to build initial memory")
        print("  4. Use code_index() in Claude Code to index your codebase")
        print("  5. Run /memoriqhelp to see all commands")
        print("  6. Run 'memoriq' in terminal for TUI dashboard")

    print()
    print("  Trouble? Run: python diagnose.py --fix")
    print()


if __name__ == "__main__":
    main()
