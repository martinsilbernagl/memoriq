"""Centralized error handling for Memoriq."""

import traceback
import sys
from enum import Enum
from typing import Optional


class ErrorCode(Enum):
    """Error codes for different failure modes."""
    MCP_NOT_INSTALLED = "E001"
    DB_LOCKED = "E002"
    DB_CORRUPTED = "E003"
    SESSION_INVALID = "E004"
    VENV_MISSING = "E005"
    UNKNOWN = "E999"


def classify_error(error: Exception) -> tuple[ErrorCode, str]:
    """Classify an exception into an error code with user-friendly message."""
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Module not found errors
    if "modulenotfound" in error_type or "importerror" in error_type:
        if "mcp" in error_str:
            return ErrorCode.MCP_NOT_INSTALLED, (
                "MCP module not installed. "
                "Run: bash ~/.memoriq/bin/setup-venv.sh"
            )
        return ErrorCode.MCP_NOT_INSTALLED, f"Missing dependency: {error}"

    # Database errors
    if "sqlite" in error_type or "operationalerror" in error_type:
        if "locked" in error_str:
            return ErrorCode.DB_LOCKED, (
                "Database is locked by another process. "
                "Wait a moment and try again."
            )
        if "corrupt" in error_str or "malformed" in error_str:
            return ErrorCode.DB_CORRUPTED, (
                "Database appears corrupted. "
                "Restore from backup: ~/.memoriq/memory.db.backup-*"
            )
        return ErrorCode.DB_CORRUPTED, f"Database error: {error}"

    # Session errors
    if "session" in error_str or "no active" in error_str:
        return ErrorCode.SESSION_INVALID, (
            "No valid session found. "
            "Run: /onboard or restart Claude Code"
        )

    return ErrorCode.UNKNOWN, f"Unexpected error: {error}"


def handle_tool_error(tool_name: str, error: Exception, log_func=None) -> str:
    """Handle an error from a tool call and return user-friendly message."""
    code, message = classify_error(error)

    # Log full traceback for debugging
    if log_func:
        log_func.error(f"Tool {tool_name} failed [{code.value}]: {error}")
        log_func.debug(traceback.format_exc())

    return f"[Memoriq Error {code.value}] {message}"


def check_venv_exists() -> bool:
    """Check if virtual environment exists."""
    from pathlib import Path
    venv_path = Path.home() / ".memoriq" / "venv"
    return venv_path.exists()


def get_fix_instructions(error_code: ErrorCode) -> str:
    """Get instructions for fixing an error."""
    fixes = {
        ErrorCode.MCP_NOT_INSTALLED: (
            "To fix this issue:\n"
            "1. Run: bash ~/.memoriq/bin/setup-venv.sh\n"
            "2. Restart Claude Code\n"
            "3. If still failing, run: python ~/.memoriq/diagnose.py --fix"
        ),
        ErrorCode.VENV_MISSING: (
            "Virtual environment not found.\n"
            "Run: bash ~/.memoriq/bin/setup-venv.sh"
        ),
        ErrorCode.DB_LOCKED: (
            "Database is busy. Try:\n"
            "1. Wait 10 seconds and retry\n"
            "2. Close other Claude Code windows\n"
            "3. Check for zombie processes: ps aux | grep memoriq"
        ),
        ErrorCode.DB_CORRUPTED: (
            "Database may be damaged.\n"
            "Check for backups: ls -la ~/.memoriq/memory.db.backup-*\n"
            "Restore: cp ~/.memoriq/memory.db.backup-XXX ~/.memoriq/memory.db"
        ),
        ErrorCode.SESSION_INVALID: (
            "Session issue detected.\n"
            "Try: /onboard command or restart Claude Code"
        ),
    }
    return fixes.get(error_code, "Please check logs: ~/.memoriq/logs/memoriq.log")
