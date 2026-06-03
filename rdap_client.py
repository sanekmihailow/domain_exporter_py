"""Async RDAP HTTP client.

Performs a single RDAP request and returns the decoded JSON body. Never raises
on network/protocol errors — returns None instead so the exporter can report
``domain_probe_up=0`` and keep serving.
"""

import json
import logging
from typing import Optional

import aiohttp

import config

logger = logging.getLogger("domain_exporter.client")

# A generous, RDAP-ish Accept header. Some endpoints (e.g. rdap.ss) are happy
# with plain JSON too.
_HEADERS = {
    "Accept": "application/rdap+json, application/json",
    "User-Agent": "domain_exporter_py/0.1",
}


async def fetch_rdap(
    session: aiohttp.ClientSession, url: str, domain: str
) -> Optional[dict]:
    """Fetch and decode RDAP JSON. Returns the dict, or None on any failure."""
    timeout = aiohttp.ClientTimeout(total=config.RDAP_TIMEOUT)
    logger.debug("RDAP GET %s", url)
    try:
        async with session.get(url, headers=_HEADERS, timeout=timeout) as resp:
            # RDAP returns 404 for "domain not found"; that is still a usable
            # answer in many registries, but most won't carry events, so we
            # treat non-2xx as "no data" while reading the body defensively.
            if resp.status != 200:
                logger.info("RDAP %s -> HTTP %s for %s", url, resp.status, domain)
                return None
            raw = await resp.read()
            logger.debug("RDAP %s -> HTTP 200, %d bytes", url, len(raw))
    except aiohttp.ClientError as exc:
        logger.warning("RDAP request failed for %s (%s): %s", domain, url, exc)
        return None
    except TimeoutError:
        logger.warning("RDAP request timed out for %s (%s)", domain, url)
        return None

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("RDAP response for %s was not valid JSON: %s", domain, exc)
        return None
