"""Minimal async WHOIS (port 43) client.

Used as a fallback for TCI zones when rdap.ss is unavailable. Sends the domain
followed by CRLF and reads the server's plain-text response until EOF. Never
raises — returns None on any network error so the caller can report
``domain_probe_up=0``.
"""

import asyncio
import logging
from typing import Optional

import config

logger = logging.getLogger("domain_exporter.whois")


async def query_whois(server: str, domain: str) -> Optional[str]:
    """Query a WHOIS server for `domain`. Returns the text body, or None."""
    logger.debug("WHOIS %s:%s query %s", server, config.WHOIS_PORT, domain)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(server, config.WHOIS_PORT),
            timeout=config.WHOIS_TIMEOUT,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        logger.warning("WHOIS connect to %s failed for %s: %s", server, domain, exc)
        return None

    try:
        writer.write(f"{domain}\r\n".encode("ascii"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(), timeout=config.WHOIS_TIMEOUT)
    except (OSError, asyncio.TimeoutError) as exc:
        logger.warning("WHOIS query to %s failed for %s: %s", server, domain, exc)
        return None
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    # An accepted-but-empty response (common when the registry rate-limits) is
    # a failure, not a successful probe — report it as such.
    if not raw.strip():
        logger.info("WHOIS %s returned an empty response for %s", server, domain)
        return None

    return raw.decode("utf-8", errors="replace")
