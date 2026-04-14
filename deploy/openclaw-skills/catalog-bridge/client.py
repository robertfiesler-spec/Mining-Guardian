"""
CatalogAPIClient — async HTTP client for the Mining Intelligence Catalog API.

Runs on the VPS side (OpenClaw). Communicates with the Catalog API on ROBS-PC
over Tailscale VPN.

Features:
- Async HTTP calls via aiohttp
- In-memory TTL cache (5 min bundles, 1 hour firmware, 24 hours repair)
- Disk cache fallback (/tmp/catalog_cache/)
- Circuit breaker (5 failures → OPEN for 60s → HALF_OPEN)
- Bearer token auth
- Never raises to caller — returns data or empty fallback
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("catalog-bridge.client")

# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple circuit breaker: 5 failures → OPEN for 60s → HALF_OPEN test."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0

    @property
    def is_available(self) -> bool:
        """Check if requests are allowed through the circuit."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker → HALF_OPEN (testing)")
                return True
            return False
        # HALF_OPEN — allow one test request
        return True

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker → CLOSED (recovered)")
        self.state = CircuitState.CLOSED
        self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker → OPEN after %d failures", self.failure_count)
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker → OPEN (half-open test failed)")


# ---------------------------------------------------------------------------
# TTL cache (in-memory)
# ---------------------------------------------------------------------------
class TTLCacheEntry:
    """A cache entry with an expiration timestamp."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.expires_at = time.monotonic() + ttl

    @property
    def is_expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class SimpleTTLCache:
    """Minimal TTL cache. Not thread-safe — fine for single-event-loop async."""

    def __init__(self, maxsize: int = 256):
        self._store: dict[str, TTLCacheEntry] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[Any]:
        """Get a value if it exists and hasn't expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: float) -> None:
        """Set a value with a TTL in seconds."""
        if len(self._store) >= self._maxsize:
            self._evict_expired()
        self._store[key] = TTLCacheEntry(value, ttl)

    def _evict_expired(self) -> None:
        """Remove expired entries."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now >= v.expires_at]
        for k in expired:
            del self._store[k]


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------
class DiskCache:
    """JSON-file disk cache in /tmp/catalog_cache/."""

    def __init__(self, cache_dir: str = "/tmp/catalog_cache"):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self._dir / f"{safe_key}.json"

    def get(self, key: str, max_age_seconds: float = 3600) -> Optional[dict]:
        """Read from disk if the file exists and isn't too old."""
        path = self._path(key)
        try:
            if not path.exists():
                return None
            age = time.time() - path.stat().st_mtime
            if age > max_age_seconds:
                path.unlink(missing_ok=True)
                return None
            data = json.loads(path.read_text())
            logger.debug("Disk cache HIT for %s", key)
            return data
        except Exception as exc:
            logger.warning("Disk cache read error: %s", exc)
            return None

    def set(self, key: str, value: dict) -> None:
        """Write data to disk cache."""
        path = self._path(key)
        try:
            path.write_text(json.dumps(value, default=str))
            logger.debug("Disk cache WRITE for %s", key)
        except Exception as exc:
            logger.warning("Disk cache write error: %s", exc)


# ---------------------------------------------------------------------------
# CatalogAPIClient
# ---------------------------------------------------------------------------
class CatalogAPIClient:
    """
    Async HTTP client for the Mining Intelligence Catalog API.

    Never raises exceptions to caller. Always returns data or an empty fallback.
    """

    # TTL values in seconds
    BUNDLE_TTL = 300       # 5 min
    FIRMWARE_TTL = 3600    # 1 hour
    REPAIR_TTL = 86400     # 24 hours
    DISK_MAX_AGE = 7200    # 2 hours for disk fallback

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.getenv("CATALOG_API_URL", "http://100.110.87.1:8420")).rstrip("/")
        self.api_key = api_key or os.getenv("CATALOG_API_KEY", "")
        self.timeout = timeout
        self._circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        self._mem_cache = SimpleTTLCache(maxsize=256)
        self._disk_cache = DiskCache()
        self._session = None

    async def _get_session(self):
        """Lazily create an aiohttp session."""
        if self._session is None or self._session.closed:
            try:
                import aiohttp
                self._session = aiohttp.ClientSession(
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                )
            except ImportError:
                logger.error("aiohttp not installed — install with: pip install aiohttp")
                return None
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, body: Optional[dict] = None) -> Optional[dict]:
        """
        Make an HTTP request with circuit breaker protection.
        Returns the parsed JSON response or None on failure.
        """
        if not self._circuit.is_available:
            logger.warning("Circuit OPEN — skipping request to %s", path)
            return None

        session = await self._get_session()
        if session is None:
            return None

        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                async with session.get(url) as resp:
                    if resp.status == 200:
                        self._circuit.record_success()
                        return await resp.json()
                    logger.warning("API %s %s returned %d", method, path, resp.status)
                    self._circuit.record_failure()
                    return None
            elif method == "POST":
                async with session.post(url, json=body) as resp:
                    if resp.status == 200:
                        self._circuit.record_success()
                        return await resp.json()
                    logger.warning("API %s %s returned %d", method, path, resp.status)
                    self._circuit.record_failure()
                    return None
        except asyncio.TimeoutError:
            logger.warning("Timeout on %s %s", method, url)
            self._circuit.record_failure()
        except Exception as exc:
            logger.warning("Request error on %s %s: %s", method, url, exc)
            self._circuit.record_failure()

        return None

    async def health_check(self) -> dict:
        """Check if the Catalog API is reachable and healthy."""
        result = await self._request("GET", "/api/v1/health")
        return result or {"status": "unreachable"}

    async def get_scan_context_bundle(
        self,
        miner_models: list[str],
        active_issues: list[str] | None = None,
        chip_dies: list[str] | None = None,
        firmware_versions: list[str] | None = None,
        include_sections: list[str] | None = None,
    ) -> dict:
        """
        Fetch a knowledge bundle for a scan context.

        Returns a dict with 'context_bundle', 'prompt_text', 'cache_key', etc.
        On failure, returns a minimal fallback dict with empty prompt_text.
        """
        active_issues = active_issues or []
        chip_dies = chip_dies or []
        firmware_versions = firmware_versions or []
        include_sections = include_sections or [
            "failure_patterns", "firmware", "thresholds", "repair", "env_factors", "baselines"
        ]

        # Build cache key
        cache_key = self._cache_key("bundle", miner_models, active_issues)

        # Check memory cache
        cached = self._mem_cache.get(cache_key)
        if cached is not None:
            logger.info("Memory cache HIT for bundle")
            return cached

        # Try API
        body = {
            "miner_models": miner_models,
            "active_issues": active_issues,
            "chip_dies": chip_dies,
            "firmware_versions": firmware_versions,
            "include_sections": include_sections,
        }
        result = await self._request("POST", "/api/v1/context/scan-bundle", body)

        if result:
            self._mem_cache.set(cache_key, result, self.BUNDLE_TTL)
            self._disk_cache.set(cache_key, result)
            logger.info("Bundle fetched from API — %d sources", len(result.get("sources", [])))
            return result

        # Fallback to disk cache
        disk_result = self._disk_cache.get(cache_key, max_age_seconds=self.DISK_MAX_AGE)
        if disk_result:
            logger.info("Using DISK CACHE fallback for bundle")
            return disk_result

        # Empty fallback — never raise
        logger.warning("No bundle available — returning empty fallback")
        return {
            "context_bundle": {},
            "prompt_text": "",
            "cache_key": cache_key,
            "generated_at": "",
            "sources": [],
            "_fallback": True,
        }

    async def get_miner_knowledge(
        self,
        model_slug: str,
        include: str = "specs,firmware,failures,repair,thresholds",
    ) -> dict:
        """
        Look up knowledge for a single miner model by slug.

        Returns model data or empty fallback on failure.
        """
        cache_key = f"miner:{model_slug}:{include}"

        cached = self._mem_cache.get(cache_key)
        if cached is not None:
            logger.info("Memory cache HIT for miner '%s'", model_slug)
            return cached

        result = await self._request("GET", f"/api/v1/knowledge/miner/{model_slug}?include={include}")

        if result:
            self._mem_cache.set(cache_key, result, self.FIRMWARE_TTL)
            self._disk_cache.set(cache_key, result)
            return result

        disk_result = self._disk_cache.get(cache_key, max_age_seconds=self.DISK_MAX_AGE)
        if disk_result:
            logger.info("Using DISK CACHE fallback for miner '%s'", model_slug)
            return disk_result

        return {"model": {}, "_fallback": True}

    @property
    def circuit_state(self) -> str:
        """Current circuit breaker state."""
        return self._circuit.state.value

    def _cache_key(self, prefix: str, *args: Any) -> str:
        """Generate a deterministic cache key."""
        payload = json.dumps(args, sort_keys=True, default=str)
        h = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{prefix}:{h}"
