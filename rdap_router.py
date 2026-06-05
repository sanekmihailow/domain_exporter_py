"""Decide which upstream(s) to query for a given domain.

TCI zones (`.ru`, `.su`, `.рф`) are served by the Russian registry whois server
`whois.tcinet.ru`; rdap.ss is an HTTP wrapper over it. We query rdap.ss first
and keep `whois.tcinet.ru` as a raw-WHOIS fallback for when rdap.ss is down.
Everything else goes to rdap.net (standard RDAP), with no fallback.

`.рф` is matched in its IDNA/punycode form `xn--p1ai`, since domains are
normalized to ASCII before routing.
"""

from dataclasses import dataclass
from typing import Optional

import config

SOURCE_RDAP_SS = "rdap_ss"
SOURCE_RDAP_NET = "rdap_net"
SOURCE_WHOIS_TCINET = "whois_tcinet"

# Zones handled by the TCI registry. `.рф` -> `xn--p1ai` after IDNA encoding.
TCI_ZONES = (".ru", ".su", ".xn--p1ai")


@dataclass
class Route:
    source: str  # primary source name
    domain: str  # normalized, IDNA/ASCII domain used for outbound queries
    url: str  # primary RDAP/HTTP endpoint
    whois_server: Optional[str] = None  # raw-WHOIS fallback server, if any


def _normalize(domain: str) -> str:
    """Lowercase, strip trailing dot, and convert IDN labels to ASCII."""
    d = domain.strip().rstrip(".").lower()
    try:
        d = d.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        # Leave as-is; a malformed domain will simply fail the lookup later.
        pass
    return d


def to_unicode(domain: str) -> str:
    """Return the human-readable Unicode form of a domain, for metric labels.

    Inverse of the IDNA encoding done in ``_normalize``: decodes punycode/ACE
    labels (``xn--…``) back to Unicode so the ``domain`` label always reads as
    ``президент.рф`` regardless of whether the scrape requested the ASCII form
    (``xn--d1abbgf6aiiy.xn--p1ai``) or the native Unicode one. Already-Unicode
    or plain-ASCII input is returned unchanged, and anything that fails to
    decode falls back to the cleaned input — this never raises.
    """
    d = domain.strip().rstrip(".").lower()
    try:
        return d.encode("ascii").decode("idna")
    except (UnicodeError, ValueError):
        # Non-ASCII (already Unicode) or an undecodable ACE label: leave as-is.
        return d


def select_endpoint(domain: str) -> Route:
    """Return the routing decision for the given domain."""
    d = _normalize(domain)
    if d.endswith(TCI_ZONES):
        return Route(
            source=SOURCE_RDAP_SS,
            domain=d,
            url=config.RDAP_SS_URL.format(domain=d),
            whois_server=config.WHOIS_TCINET_SERVER,
        )
    return Route(
        source=SOURCE_RDAP_NET,
        domain=d,
        url=config.RDAP_NET_URL.format(domain=d),
        whois_server=None,
    )
