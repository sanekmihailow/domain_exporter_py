"""Two independent cache layers.

1. Domain result cache  — normalized per-domain results, TTL 24h. Both
   successful and failed lookups are cached so a broken upstream is not
   hammered by repeated scrapes.
2. Bootstrap cache      — the IANA dns.json zone registry, refreshed every 24h.
   Kept as a routing reference; the actual `.ru` override lives in
   rdap_router.

Stored result shape (see PLAN):
    {
        "source": "rdap_ss",
        "created_timestamp": 1704067200 | None,
        "expiry_timestamp": 1735689600 | None,
        "probe_up": 1,
        "domain_parsed": 1,
        "cached_at": 1780480560,
    }
"""

import logging
import time
from typing import Optional

import aiohttp
from cachetools import TTLCache

import config

logger = logging.getLogger("domain_exporter.cache")

# Per-domain normalized results.
domain_cache: TTLCache = TTLCache(
    maxsize=config.DOMAIN_CACHE_MAXSIZE, ttl=config.DOMAIN_CACHE_TTL
)


def get_domain(domain: str) -> Optional[dict]:
    return domain_cache.get(domain)


def set_domain(domain: str, result: dict) -> None:
    domain_cache[domain] = result


class BootstrapCache:
    """Lazily fetched IANA dns.json, refreshed at most once per TTL window."""

    def __init__(self) -> None:
        self._data: Optional[dict] = None
        self._fetched_at: float = 0.0

    @property
    def is_fresh(self) -> bool:
        return (
            self._data is not None
            and (time.time() - self._fetched_at) < config.BOOTSTRAP_CACHE_TTL
        )

    async def get(self, session: aiohttp.ClientSession) -> Optional[dict]:
        if self.is_fresh:
            return self._data
        await self._refresh(session)
        return self._data

    async def _refresh(self, session: aiohttp.ClientSession) -> None:
        timeout = aiohttp.ClientTimeout(total=config.RDAP_TIMEOUT)
        try:
            async with session.get(config.BOOTSTRAP_URL, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.info("Bootstrap fetch -> HTTP %s", resp.status)
                    return
                self._data = await resp.json(content_type=None)
                self._fetched_at = time.time()
                logger.info("Bootstrap registry refreshed")
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.warning("Bootstrap refresh failed: %s", exc)


bootstrap_cache = BootstrapCache()
