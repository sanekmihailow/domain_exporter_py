"""Build Prometheus exposition output from a normalized result dict.

A fresh registry is created per request so the single ``domain`` label does not
accumulate across scrapes (probe pattern). Timestamp metrics are omitted when
the date is missing — never emitted as 0.
"""

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest


def render(domain: str, result: dict) -> bytes:
    registry = CollectorRegistry()

    probe_up = Gauge(
        "domain_probe_up",
        "1 if the RDAP endpoint responded with valid JSON, else 0.",
        ["domain"],
        registry=registry,
    )
    parsed = Gauge(
        "domain_parsed",
        "1 if both registration and expiration were extracted, else 0.",
        ["domain"],
        registry=registry,
    )
    probe_up.labels(domain=domain).set(result.get("probe_up", 0))
    parsed.labels(domain=domain).set(result.get("domain_parsed", 0))

    created = result.get("created_timestamp")
    if created is not None:
        created_g = Gauge(
            "domain_created_timestamp_seconds",
            "Domain registration (created) date as a Unix timestamp.",
            ["domain"],
            registry=registry,
        )
        created_g.labels(domain=domain).set(created)

    expiry = result.get("expiry_timestamp")
    if expiry is not None:
        expiry_g = Gauge(
            "domain_expiry_timestamp_seconds",
            "Domain expiry date as a Unix timestamp.",
            ["domain"],
            registry=registry,
        )
        expiry_g.labels(domain=domain).set(expiry)

    return generate_latest(registry)


CONTENT_TYPE = CONTENT_TYPE_LATEST
