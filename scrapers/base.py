"""
Rate-limited HTTP session with retry logic and disk-based response caching.
Both the SofaScore and Transfermarkt scrapers inherit from RateLimitedSession.
"""

import hashlib
import json
import time
from pathlib import Path

import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import FORCE_RESCRAPE, SCRAPE_DELAY, RAW_DIR


class RateLimitedSession:
    """Thin wrapper around requests.Session with caching and back-off."""

    SOURCE: str = "base"   # overridden by subclasses

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/html, */*",
    }

    def __init__(self, delay: float = SCRAPE_DELAY):
        self.delay = delay
        self.cache_dir: Path = RAW_DIR / self.SOURCE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        self._last_request_at: float = 0.0

    # ──────────────────────────────────────────────
    # Cache helpers
    # ──────────────────────────────────────────────

    def _cache_path(self, cache_key: str) -> Path:
        safe = cache_key.replace("/", "_").replace("?", "_").replace("&", "_")
        # Truncate very long keys and append a hash suffix to avoid collisions
        if len(safe) > 200:
            h = hashlib.md5(safe.encode()).hexdigest()[:8]
            safe = safe[:192] + "_" + h
        return self.cache_dir / f"{safe}.json"

    def _load_cache(self, cache_key: str) -> dict | list | None:
        if FORCE_RESCRAPE:
            return None
        path = self._cache_path(cache_key)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Corrupt cache for {cache_key}, re-fetching")
        return None

    def _save_cache(self, cache_key: str, data: dict | list) -> None:
        path = self._cache_path(cache_key)
        path.write_text(json.dumps(data, ensure_ascii=False))

    # ──────────────────────────────────────────────
    # HTTP
    # ──────────────────────────────────────────────

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_at = time.time()

    @retry(
        retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        resp = self._session.get(url, timeout=30, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning(f"Rate-limited by {url}. Sleeping {retry_after}s")
            time.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, cache_key: str | None = None, **kwargs) -> dict | list:
        key = cache_key or url
        cached = self._load_cache(key)
        if cached is not None:
            return cached
        logger.debug(f"GET {url}")
        resp = self._get(url, **kwargs)
        data = resp.json()
        self._save_cache(key, data)
        return data

    def get_html(self, url: str, cache_key: str | None = None, **kwargs) -> str:
        key = cache_key or url
        path = self._cache_path(key)
        if not FORCE_RESCRAPE and path.exists():
            return path.read_text()
        logger.debug(f"GET {url}")
        resp = self._get(url, **kwargs)
        path.write_text(resp.text)
        return resp.text
