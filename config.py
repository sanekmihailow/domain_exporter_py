"""Runtime configuration, overridable via environment variables."""

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# HTTP server
HOST: str = os.environ.get("EXPORTER_HOST", "0.0.0.0")
PORT: int = _int("EXPORTER_PORT", 9223)

# Cache TTLs (seconds)
DOMAIN_CACHE_TTL: int = _int("DOMAIN_CACHE_TTL", 24 * 60 * 60)
DOMAIN_CACHE_MAXSIZE: int = _int("DOMAIN_CACHE_MAXSIZE", 10000)
BOOTSTRAP_CACHE_TTL: int = _int("BOOTSTRAP_CACHE_TTL", 24 * 60 * 60)

# Outbound RDAP request timeout (seconds)
RDAP_TIMEOUT: int = _int("RDAP_TIMEOUT", 10)

# RDAP endpoints. {domain} is substituted with the requested domain.
RDAP_SS_URL: str = os.environ.get("RDAP_SS_URL", "https://rdap.ss/api/query?q={domain}")
RDAP_NET_URL: str = os.environ.get("RDAP_NET_URL", "https://www.rdap.net/domain/{domain}")

# IANA bootstrap registry (cached reference for TLD routing).
BOOTSTRAP_URL: str = os.environ.get("BOOTSTRAP_URL", "https://data.iana.org/rdap/dns.json")
