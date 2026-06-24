"""Webhook integration - POST events to external URLs.

Configuration (config.yaml):
    integrations:
      webhooks:
        enabled: true
        endpoints:
          - url: "https://hooks.slack.com/services/..."
            events: ["memory_write", "session_end"]
            headers:
              Authorization: "Bearer ${WEBHOOK_TOKEN}"
          - url: "http://localhost:3000/webhook"
            events: ["*"]  # all events
            timeout: 5
            retries: 3
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from .bus import get_bus

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

logger = logging.getLogger("memoriq.integrations.webhook")

# In-memory deduplication for retry tracking
_retry_tracker: dict[str, list[float]] = {}
_retry_lock = threading.Lock()

# Circuit breaker state
_circuit_breakers: dict[str, dict] = {}
_CB_LOCK = threading.Lock()

# Common secret environment variable name patterns
_SECRET_PATTERNS = ['secret', 'token', 'key', 'password', 'auth', 'credential', 'api_key']


@dataclass
class WebhookEndpoint:
    """Configuration for a single webhook endpoint."""
    url: str
    events: list[str]
    headers: dict[str, str]
    timeout: int = 5
    retries: int = 3
    retry_delay: float = 1.0

    def should_handle(self, event: str) -> bool:
        """Check if this endpoint handles the given event type."""
        return "*" in self.events or event in self.events

    def get_url(self) -> str:
        """Get URL with environment variable substitution."""
        return _substitute_env_vars(self.url)

    def get_headers(self) -> dict[str, str]:
        """Get headers with environment variable substitution."""
        return {k: _substitute_env_vars(v) for k, v in self.headers.items()}


def _substitute_env_vars(value: str) -> str:
    """Substitute ${VAR} or $VAR with environment variable values."""
    def replacer(match):
        var_name = match.group(1) or match.group(2)
        return os.environ.get(var_name, match.group(0))

    # Match ${VAR} or $VAR
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', replacer, value)


def _load_endpoints() -> list[WebhookEndpoint]:
    """Load webhook endpoints from config."""
    import yaml
    from pathlib import Path

    config_path = Path.home() / ".memoriq" / "config.yaml"
    if not config_path.exists():
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return []

    webhooks_config = config.get("integrations", {}).get("webhooks", {})
    endpoints = []

    for ep in webhooks_config.get("endpoints", []):
        try:
            endpoint = WebhookEndpoint(
                url=ep["url"],
                events=ep.get("events", ["*"]),
                headers=ep.get("headers", {}),
                timeout=ep.get("timeout", 5),
                retries=ep.get("retries", 3),
                retry_delay=ep.get("retry_delay", 1.0),
            )
            endpoints.append(endpoint)
        except KeyError as e:
            logger.warning(f"Invalid webhook endpoint config: missing {e}")

    return endpoints


def _cleanup_old_retry_entries():
    """Remove old entries from retry tracker to prevent memory growth."""
    with _retry_lock:
        now = time.time()
        urls_to_remove = []
        for url, attempts in _retry_tracker.items():
            recent = [t for t in attempts if now - t < 60]
            if recent:
                _retry_tracker[url] = recent
            else:
                urls_to_remove.append(url)
        for url in urls_to_remove:
            del _retry_tracker[url]


def _check_circuit_breaker(url: str) -> bool:
    """Check if circuit breaker allows request. Returns True if allowed."""
    with _CB_LOCK:
        cb = _circuit_breakers.get(url)
        if not cb:
            return True

        if cb["state"] == "open":
            if time.time() - cb["opened_at"] > 60:  # 1 minute cooldown
                cb["state"] = "half-open"
                return True
            return False

        return True


def _record_failure(url: str):
    """Record failure for circuit breaker."""
    with _CB_LOCK:
        cb = _circuit_breakers.setdefault(url, {
            "state": "closed",
            "failures": 0,
            "opened_at": 0
        })
        cb["failures"] += 1

        if cb["failures"] >= 5:  # Open after 5 failures
            cb["state"] = "open"
            cb["opened_at"] = time.time()


def _record_success(url: str):
    """Record success for circuit breaker."""
    with _CB_LOCK:
        if url in _circuit_breakers:
            del _circuit_breakers[url]


def _should_retry(url: str, max_retries: int) -> bool:
    """Check if we should retry this URL (rate limiting)."""
    _cleanup_old_retry_entries()

    with _retry_lock:
        now = time.time()
        attempts = _retry_tracker.get(url, [])
        # Keep only last minute of attempts
        attempts = [t for t in attempts if now - t < 60]
        _retry_tracker[url] = attempts

        if len(attempts) >= max_retries * 2:  # Too many recent failures
            return False
        attempts.append(now)
        return True


def _mask_secrets(value: str) -> str:
    """Mask potential secret values in strings for safe logging."""
    masked = value
    for key, val in os.environ.items():
        if any(pattern in key.lower() for pattern in _SECRET_PATTERNS):
            if len(val) > 4 and val in masked:
                masked = masked.replace(val, "***")
    return masked


def _send_webhook(endpoint: WebhookEndpoint, payload: dict[str, Any]) -> bool:
    """Send a single webhook request with retry logic.

    Returns True if successful, False otherwise.
    """
    if not HAS_URLLIB:
        logger.error("urllib not available, cannot send webhooks")
        return False

    url = endpoint.get_url()
    headers = endpoint.get_headers()

    # Check circuit breaker
    if not _check_circuit_breaker(url):
        logger.warning(f"Circuit breaker open for {url}, skipping")
        return False

    # Set default content-type if not specified
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    data = json.dumps(payload).encode("utf-8")

    # Mask secrets for logging
    safe_url = _mask_secrets(url)

    for attempt in range(endpoint.retries):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=endpoint.timeout) as response:
                if 200 <= response.status < 300:
                    _record_success(url)
                    logger.debug(f"Webhook delivered: {response.status}")
                    return True
                else:
                    logger.warning(f"Webhook returned {response.status}")

        except urllib.error.HTTPError as e:
            _record_failure(url)
            logger.warning(f"Webhook HTTP error {e.code} from {safe_url}")
            # Don't retry 4xx errors (client errors)
            if 400 <= e.code < 500:
                return False

        except urllib.error.URLError as e:
            _record_failure(url)
            logger.warning(f"Webhook URL error to {safe_url}: {e.reason}")

        except Exception as e:
            _record_failure(url)
            logger.warning(f"Webhook failed to {safe_url}: {e}")

        # Retry with capped exponential backoff
        if attempt < endpoint.retries - 1:
            delay = min(endpoint.retry_delay * (2 ** attempt), 30)  # Cap at 30s
            time.sleep(delay)

    logger.error(f"Webhook failed after {endpoint.retries} attempts: {safe_url}")
    return False


def _handle_event(event: str, payload: dict[str, Any]) -> None:
    """Handle an incoming event from the bus."""
    endpoints = _load_endpoints()

    for endpoint in endpoints:
        if not endpoint.should_handle(event):
            continue

        if not _should_retry(endpoint.url, endpoint.retries):
            logger.warning(f"Skipping webhook to {endpoint.url} - too many recent failures")
            continue

        # Add endpoint-specific metadata
        enriched_payload = {
            **payload,
            "_webhook": {
                "endpoint_name": endpoint.url[:50] + "..." if len(endpoint.url) > 50 else endpoint.url,
            }
        }

        _send_webhook(endpoint, enriched_payload)


def init() -> None:
    """Initialize the webhook integration."""
    bus = get_bus()
    bus.register("webhook", _handle_event)
    logger.info("Webhook integration registered")


def test_webhook(url: str, event: str = "test") -> bool:
    """Test a webhook endpoint manually.

    Returns True if the webhook was delivered successfully.
    """
    endpoint = WebhookEndpoint(
        url=url,
        events=[event],
        headers={"Content-Type": "application/json"},
        timeout=10,
        retries=1,
    )

    payload = {
        "event": "test",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data": {"message": "Memoriq webhook test"},
    }

    return _send_webhook(endpoint, payload)
