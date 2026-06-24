"""Progress tracking for long-running operations.

Since MCP protocol doesn't support streaming progress, we use:
1. Progress logging - Write to ~/.memoriq/logs/progress.log
2. Status queries - Tools can check progress of ongoing operations
3. Status messages - Return intermediate status in tool responses
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Global progress registry
_progress_registry: dict[str, "ProgressTracker"] = {}
_registry_lock = threading.Lock()


def get_progress(operation_id: str) -> Optional["ProgressTracker"]:
    """Get a progress tracker by operation ID."""
    with _registry_lock:
        return _progress_registry.get(operation_id)


def list_active_operations() -> list[dict]:
    """List all currently active operations."""
    with _registry_lock:
        return [
            {
                "id": op_id,
                "operation": tracker.operation,
                "current": tracker.current,
                "total": tracker.total,
                "percent": tracker.percent,
                "message": tracker.message,
                "elapsed": tracker.elapsed_seconds,
            }
            for op_id, tracker in _progress_registry.items()
            if tracker.is_active
        ]


@dataclass
class ProgressTracker:
    """Track progress of a long-running operation.

    Example:
        tracker = ProgressTracker("code_index", "my-project")
        tracker.start(total=100)

        for i, file in enumerate(files):
            process(file)
            tracker.update(i + 1, f"Processing {file.name}")

        tracker.finish("Indexing complete")
    """

    operation: str
    project: Optional[str] = None
    current: int = 0
    total: int = 0
    message: str = ""
    is_active: bool = False
    _start_time: float = field(default=0.0, repr=False)
    _end_time: Optional[float] = field(default=None, repr=False)
    _callbacks: list[Callable] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _operation_id: str = field(default="", repr=False)

    def __post_init__(self):
        """Register in global registry."""
        self._operation_id = f"{self.operation}:{self.project or 'global'}:{time.time()}"
        with _registry_lock:
            _progress_registry[self._operation_id] = self

        # Setup logging
        self._logger = logging.getLogger(f"memoriq.progress.{self.operation}")
        self._log_file = self._get_log_path()

    def _get_log_path(self) -> Path:
        """Get path to progress log file."""
        log_dir = Path.home() / ".memoriq" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "progress.log"

    def _log_progress(self):
        """Write progress to log file."""
        try:
            entry = {
                "timestamp": time.time(),
                "operation": self.operation,
                "project": self.project,
                "current": self.current,
                "total": self.total,
                "percent": self.percent,
                "message": self.message,
                "elapsed": self.elapsed_seconds,
            }
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Don't let logging break the operation

    def start(self, total: int, message: str = "Starting..."):
        """Start tracking a new operation.

        Args:
            total: Total number of items to process
            message: Initial status message
        """
        with self._lock:
            self.total = max(1, total)  # Avoid division by zero
            self.current = 0
            self.message = message
            self.is_active = True
            self._start_time = time.time()
            self._end_time = None

        self._log_progress()
        self._notify()

    def update(self, current: int, message: Optional[str] = None):
        """Update progress.

        Args:
            current: Current item number (1-based)
            message: Optional new status message
        """
        with self._lock:
            self.current = min(current, self.total)
            if message:
                self.message = message

        self._log_progress()
        self._notify()

    def increment(self, amount: int = 1, message: Optional[str] = None):
        """Increment progress by amount.

        Args:
            amount: Number of items completed
            message: Optional new status message
        """
        with self._lock:
            self.current = min(self.current + amount, self.total)
            if message:
                self.message = message

        self._log_progress()
        self._notify()

    def finish(self, message: str = "Complete"):
        """Mark operation as complete.

        Args:
            message: Final status message
        """
        with self._lock:
            self.current = self.total
            self.message = message
            self.is_active = False
            self._end_time = time.time()

        self._log_progress()
        self._notify()

        # Unregister after a delay (keep history briefly)
        def _cleanup():
            time.sleep(60)  # Keep for 1 minute
            with _registry_lock:
                _progress_registry.pop(self._operation_id, None)

        threading.Thread(target=_cleanup, daemon=True).start()

    def error(self, message: str):
        """Mark operation as failed.

        Args:
            message: Error message
        """
        with self._lock:
            self.message = f"ERROR: {message}"
            self.is_active = False
            self._end_time = time.time()

        self._log_progress()
        self._notify()

    def add_callback(self, callback: Callable[["ProgressTracker"], None]):
        """Add a callback to be called on progress updates."""
        with self._lock:
            self._callbacks.append(callback)

    def _notify(self):
        """Notify all callbacks."""
        with self._lock:
            callbacks = self._callbacks.copy()
        for cb in callbacks:
            try:
                cb(self)
            except Exception:
                pass

    @property
    def percent(self) -> float:
        """Get completion percentage (0-100)."""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        if not self._start_time:
            return 0.0
        end = self._end_time or time.time()
        return end - self._start_time

    @property
    def estimated_remaining(self) -> Optional[float]:
        """Estimate remaining time in seconds."""
        if self.current == 0 or not self.is_active:
            return None
        rate = self.current / self.elapsed_seconds
        remaining = (self.total - self.current) / rate
        return remaining

    def get_status(self) -> dict:
        """Get current status as a dictionary."""
        with self._lock:
            result = {
                "operation": self.operation,
                "project": self.project,
                "current": self.current,
                "total": self.total,
                "percent": round(self.percent, 1),
                "message": self.message,
                "is_active": self.is_active,
                "elapsed_seconds": round(self.elapsed_seconds, 1),
            }

            remaining = self.estimated_remaining
            if remaining is not None:
                result["estimated_remaining_seconds"] = round(remaining, 1)

            return result

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto-finish or error."""
        if exc_type:
            self.error(str(exc_val))
        elif self.is_active:
            self.finish()
        return False


class ProgressReporter:
    """Helper for reporting progress at regular intervals.

    Use this to throttle progress updates and avoid flooding logs.
    """

    def __init__(self, tracker: ProgressTracker, report_every: int = 10):
        """Initialize reporter.

        Args:
            tracker: ProgressTracker to report to
            report_every: Report every N items
        """
        self.tracker = tracker
        self.report_every = report_every
        self._last_reported = 0

    def maybe_report(self, current: int, message: Optional[str] = None):
        """Report progress if enough items have passed."""
        if current - self._last_reported >= self.report_every:
            self.tracker.update(current, message)
            self._last_reported = current

    def finish(self, message: str = "Complete"):
        """Mark as finished."""
        self.tracker.finish(message)


def format_progress_line(status: dict) -> str:
    """Format a progress status dict as a human-readable line.

    Example:
        "Indexing: 45/100 (45%) - Processing src/main.py"
    """
    op = status.get("operation", "Working")
    current = status.get("current", 0)
    total = status.get("total", 0)
    percent = status.get("percent", 0)
    message = status.get("message", "")

    line = f"{op}: {current}/{total} ({percent}%)"
    if message:
        line += f" - {message}"

    return line
