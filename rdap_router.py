"""Decide which RDAP endpoint to query for a given domain.

`.ru` is routed to rdap.ss via an explicit override; everything else goes to
rdap.net. This is intentional and bypasses IANA bootstrap for `.ru`.
"""

from typing import Tuple

import config

SOURCE_RDAP_SS = "rdap_ss"
SOURCE_RDAP_NET = "rdap_net"


def select_endpoint(domain: str) -> Tuple[str, str]:
    """Return (source_name, url) for the given domain."""
    normalized = domain.strip().rstrip(".").lower()
    if normalized.endswith(".ru"):
        return SOURCE_RDAP_SS, config.RDAP_SS_URL.format(domain=normalized)
    return SOURCE_RDAP_NET, config.RDAP_NET_URL.format(domain=normalized)
