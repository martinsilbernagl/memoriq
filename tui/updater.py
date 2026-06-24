"""Auto-update checker and installer for Memoriq."""

import re
import subprocess
from pathlib import Path
from typing import Tuple, Optional
import sys


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse version string to tuple."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str.strip())
    if not match:
        return (0, 0, 0)
    return tuple(int(x) for x in match.groups())


def compare_versions(local: str, remote: str) -> int:
    """Compare versions. Returns >0 if remote is newer, 0 if same, <0 if older."""
    local_t = parse_version(local)
    remote_t = parse_version(remote)
    if remote_t > local_t:
        return 1
    elif remote_t < local_t:
        return -1
    return 0


def get_local_version() -> str:
    """Get installed version from VERSION file."""
    version_file = Path.home() / ".memoriq" / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "0.0.0"


def get_remote_version() -> Optional[str]:
    """Fetch latest version from git remote."""
    try:
        # Try to get VERSION from origin/main
        result = subprocess.run(
            ["git", "show", "origin/main:VERSION"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path.home() / ".memoriq"
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def check_for_update() -> Optional[dict]:
    """Check if update is available. Returns None if no update or error."""
    local = get_local_version()
    remote = get_remote_version()

    if not remote:
        return None

    comparison = compare_versions(local, remote)
    if comparison > 0:  # remote is newer
        return {
            "local": local,
            "remote": remote,
            "has_update": True
        }
    return None


def _get_python_executable() -> str:
    """Get the Python executable to use for updates."""
    # Check for ~/.memoriq/venv first
    venv_dir = Path.home() / ".memoriq" / "venv"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if venv_python.exists():
        return str(venv_python)

    # Check if currently running in a venv
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return sys.executable

    # Fallback to system python3
    return "python3"


def run_update(callback=None) -> tuple[bool, str]:
    """Run update process using safe subprocess calls. Returns (success, message)."""
    memoriq_home = Path.home() / ".memoriq"
    python_exe = _get_python_executable()

    try:
        # Step 1: git pull
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=memoriq_home,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, f"git pull failed: {result.stderr}"

        # Step 2: pip install
        packages = ["mcp", "pyyaml", "textual", "tree-sitter-language-pack", "fastembed", "sqlite-vec"]
        result = subprocess.run(
            [python_exe, "-m", "pip", "install"] + packages + ["--quiet"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            # Try with --break-system-packages
            result = subprocess.run(
                [python_exe, "-m", "pip", "install"] + packages + ["--quiet", "--break-system-packages"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                return False, f"pip install failed: {result.stderr}"

        # Step 3: database migrations
        result = subprocess.run(
            [python_exe, "-c", "import sys; sys.path.insert(0, 'mcp-server'); from init_db import init_db; init_db()"],
            cwd=memoriq_home,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, f"database migration failed: {result.stderr}"

        # Step 4: copy files
        result = subprocess.run(
            [python_exe, "install.py", "--skip-wizard"],
            cwd=memoriq_home,
            capture_output=True,
            text=True,
            timeout=30
        )
        # install.py may return non-zero if already installed, so we ignore return code

        return True, "Update completed successfully! Restart TUI to apply changes."
    except subprocess.TimeoutExpired as e:
        return False, f"Update timed out: {str(e)}"
    except Exception as e:
        return False, str(e)


def clear_cache():
    """Clear query result cache."""
    # Import from db module
    try:
        sys.path.insert(0, str(Path.home() / ".memoriq" / "mcp-server"))
        from db import _query_cache
        _query_cache.clear()
    except Exception:
        pass
