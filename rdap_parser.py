"""Extract the two required dates from an upstream response.

There are two upstream formats, selected by source (see rdap_router):

* rdap_net — standard RDAP (RFC 7483): dates live in the ``events[]`` array
  under ``eventAction`` == "registration"/"expiration".
* rdap_ss  — a whois wrapper for ``.ru``: dates live as strings in
  ``data.whoisData["Created Date"]`` / ``["Expiry Date"]``.

Both formats use RFC3339 dates, which we convert to Unix seconds. Anything
malformed or missing is skipped rather than raising.
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

import rdap_router

logger = logging.getLogger("domain_exporter.parser")


def rfc3339_to_unix(value: str) -> Optional[int]:
    """Convert an RFC3339 timestamp to Unix seconds, or None if unparseable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.info("Unrecognized date format: %r", value)
        return None
    return int(dt.timestamp())


def _parse_rdap_events(data: dict) -> Tuple[Optional[int], Optional[int]]:
    """Standard RDAP: read registration/expiration from events[]."""
    created: Optional[int] = None
    expiry: Optional[int] = None

    events = data.get("events")
    if not isinstance(events, list):
        return None, None

    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("eventAction")
        date = event.get("eventDate")
        if action == "registration" and created is None:
            created = rfc3339_to_unix(date)
        elif action == "expiration" and expiry is None:
            expiry = rfc3339_to_unix(date)

    return created, expiry


def _parse_rdap_ss(data: dict) -> Tuple[Optional[int], Optional[int]]:
    """rdap.ss whois wrapper: read dates from data.whoisData."""
    payload = data.get("data")
    if not isinstance(payload, dict):
        return None, None
    whois = payload.get("whoisData")
    if not isinstance(whois, dict):
        return None, None

    created = rfc3339_to_unix(whois.get("Created Date"))
    expiry = rfc3339_to_unix(whois.get("Expiry Date"))
    return created, expiry


def parse_tcinet_whois(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse whois.tcinet.ru plain-text output (`.ru`/`.su`/`.рф`).

    Relevant fields:
        created:    <RFC3339>   -> registration
        paid-till:  <RFC3339>   -> expiration
    """
    created: Optional[int] = None
    expiry: Optional[int] = None

    if not isinstance(text, str):
        return None, None

    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "created" and created is None:
            created = rfc3339_to_unix(value)
        elif key == "paid-till" and expiry is None:
            expiry = rfc3339_to_unix(value)

    return created, expiry


def parse(data: dict, source: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (created_timestamp, expiry_timestamp) for the given source.

    Either value may be None if the corresponding field is absent or its date
    is malformed.
    """
    if not isinstance(data, dict):
        return None, None
    if source == rdap_router.SOURCE_RDAP_SS:
        return _parse_rdap_ss(data)
    return _parse_rdap_events(data)
