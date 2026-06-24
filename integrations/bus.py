"""Integration Bus - Central event dispatcher for all integrations.

All integrations are fire-and-forget to avoid blocking core Memoriq operations.
"""

import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Setup logging
logger = logging.getLogger("memoriq.integrations")

# Singleton instance
_bus_instance = None
_bus_lock = threading.Lock()


class IntegrationBus:
    """Central event dispatcher for Memoriq integrations.

    Events are dispatched asynchronously via a thread pool to avoid blocking
    core memory operations.
    """

    def __init__(self, max_workers: int = 3):
        self._handlers: dict[str, list[Callable]] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cogni_int_")
        self._enabled = True
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load integration config from config.yaml."""
        config_path = Path.home() / ".memoriq" / "config.yaml"
        if not config_path.exists():
            return {}

        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("integrations", {})
        except Exception as e:
            logger.debug(f"Failed to load integration config: {e}")
            return {}

    def register(self, name: str, handler: Callable[[str, dict], None]) -> None:
        """Register an integration handler.

        Args:
            name: Integration name (e.g., "webhook", "obsidian")
            handler: Callback function(event_type, data_dict)
        """
        if name not in self._handlers:
            self._handlers[name] = []
        self._handlers[name].append(handler)
        logger.debug(f"Registered integration handler: {name}")

    def unregister(self, name: str) -> None:
        """Remove all handlers for an integration."""
        if name in self._handlers:
            del self._handlers[name]

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event to all registered integrations.

        This is fire-and-forget. The call returns immediately and handlers
        execute in background threads.

        Args:
            event: Event type (e.g., "memory_write", "session_end")
            data: Event payload data
        """
        if not self._enabled:
            return

        payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data,
        }

        for name, handlers in self._handlers.items():
            # Check if integration is enabled in config
            if not self._is_enabled(name):
                continue

            for handler in handlers:
                try:
                    self._executor.submit(self._wrap_handler, name, handler, event, payload)
                except Exception as e:
                    logger.error(f"Failed to submit handler {name}: {e}")

    def _is_enabled(self, name: str) -> bool:
        """Check if an integration is enabled in config."""
        integration_config = self._config.get(name, {})
        return integration_config.get("enabled", False)

    def _wrap_handler(self, name: str, handler: Callable, event: str, payload: dict):
        """Wrapper to catch and log handler exceptions."""
        try:
            handler(event, payload)
        except Exception as e:
            logger.error(f"Integration {name} handler failed: {e}")

    def shutdown(self, wait: bool = False, timeout: float = 5.0) -> None:
        """Shutdown the integration bus.

        Args:
            wait: If True, wait for pending tasks to complete
            timeout: Maximum time to wait
        """
        self._enabled = False
        if wait:
            self._executor.shutdown(wait=True)
        else:
            self._executor.shutdown(wait=False)


def get_bus() -> IntegrationBus:
    """Get the singleton IntegrationBus instance."""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = IntegrationBus()
    return _bus_instance


def emit_event(event: str, **data) -> None:
    """Convenience function to emit an event to the bus."""
    get_bus().emit(event, data)


# Auto-initialize integrations on first import
def _auto_init():
    """Auto-initialize enabled integrations."""
    bus = get_bus()
    config = bus._config

    # Webhook integration
    if config.get("webhooks", {}).get("enabled"):
        try:
            from . import webhook
            webhook.init()
            logger.info("Webhook integration initialized")
        except Exception as e:
            logger.error(f"Failed to initialize webhook integration: {e}")

    # Obsidian integration
    if config.get("obsidian", {}).get("enabled"):
        try:
            from . import obsidian
            obsidian.init()
            logger.info("Obsidian integration initialized")
        except Exception as e:
            logger.error(f"Failed to initialize obsidian integration: {e}")

    # Git hooks integration (registration only, hooks installed separately)
    if config.get("git", {}).get("enabled"):
        try:
            from . import git_hooks
            # Git hooks don't auto-init; they run via git commands
            logger.info("Git hooks integration available (install with: memoriq git-install-hooks)")
        except Exception as e:
            logger.error(f"Failed to load git hooks integration: {e}")


# Run auto-init in background to avoid blocking import
threading.Thread(target=_auto_init, daemon=True, name="cogni_int_init").start()
