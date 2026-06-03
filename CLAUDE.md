# CLAUDE.md

## Project status

Greenfield. `.md/PLAN.md` — the full specification for the exporter. No source code, dependency manifest, or tests exist yet.
When implementing, treat `.md/PLAN.md` as the source of truth for behavior and metric contracts.

## What this is

A Python Prometheus exporter for domain RDAP data, built on the **probe model** (like
`blackbox_exporter`): Prometheus scrapes `/get?target=<domain>`, and the exporter performs a
live RDAP lookup for that single domain and returns metrics. Domains are configured on the
Prometheus side, not in the exporter. There is no preloading or batch processing — work happens
lazily, per scrape.

The exporter extracts exactly two RDAP `events[]` entries and exposes them as Unix timestamps:
- `eventAction == "registration"` → created date
- `eventAction == "expiration"` → expiry date

## Metric contract (do not deviate)

```
domain_probe_up{domain="..."}              # always emitted: 1 if RDAP responded with valid JSON, else 0
domain_parsed{domain="..."}                # always emitted: 1 only if BOTH registration and expiration were extracted
domain_created_timestamp_seconds{domain="..."}   # emitted ONLY if registration was found
domain_expiry_timestamp_seconds{domain="..."}    # emitted ONLY if expiration was found
```

Critical rule: never emit a timestamp metric with value `0` for a missing date — that reads as
1970-01-01 and corrupts dashboards. Omit the metric instead. Booleans are `0`/`1`.

Success is two-tier: `domain_probe_up` means the upstream answered and JSON parsed;
`domain_parsed` means both required fields were additionally extracted and converted. A reachable
RDAP that is missing one field yields `probe_up=1, parsed=0`.

## Routing (intentional override of IANA bootstrap)

TCI zones — `.ru`, `.su`, `.рф` — are served by the Russian registry
(`whois.tcinet.ru`); rdap.ss is an HTTP wrapper over it:

- TCI zones → primary `https://rdap.ss/api/query?q=<domain>`, with raw-WHOIS
  fallback on `whois.tcinet.ru:43` when rdap.ss is down
- everything else → `https://www.rdap.net/domain/<domain>` (no fallback)

Domains are IDNA-normalized before routing, so `.рф` is matched in its punycode
form `.xn--p1ai`. The IANA bootstrap registry (`dns.json`) is cached as a
routing reference but the TCI zones are handled by the explicit override above
rather than via bootstrap lookup.

The WHOIS fallback is a genuine last resort: `whois.tcinet.ru` rate-limits
aggressively, so under load it will often return an empty response (which is
treated as a failure → `domain_probe_up=0`, never a false success).

## Caching (two independent layers)

1. **Bootstrap cache** — only the IANA `dns.json` zone registry, refreshed every 24h. Used for
   routing reference, not a domain list.
2. **Domain result cache** — normalized per-domain results, TTL 24h. Both successful *and* failed
   lookups are cached so a broken upstream is not hammered by repeated scrapes. Cache stores
   normalized timestamps (see `PLAN.md` for the dict shape), never raw RDAP strings.

## Resilience requirements

The exporter process must never crash on bad input. For every edge case (upstream down, non-JSON
response, missing `events`, only one of the two dates, unexpected date format, nonexistent domain,
unsupported zone) it must still return a valid scrape with `domain_probe_up`/`domain_parsed` set
correctly and log the cause.

## Planned module layout & stack

Per `PLAN.md`, the intended async stack is `aiohttp` (client + server), `prometheus_client`, and a
TTL cache (`cachetools` or hand-rolled). Async is required so external RDAP calls never block the
server.

```
main.py          # HTTP server + /get endpoint
config.py        # port, TTL, timeouts, endpoint settings
metrics.py       # metric definitions and exposition formatting
cache.py         # bootstrap cache + domain TTL cache
rdap_router.py   # TCI zones -> rdap.ss (+whois fallback), rdap.net otherwise
rdap_client.py   # RDAP HTTP requests with timeout/error handling
rdap_parser.py   # extract dates (events[] for RDAP, whoisData/whois text for TCI)
whois_client.py  # raw WHOIS (port 43) fallback client
prometheus/domain-exporter.example.yml  # example scrape config
```

Default listen port in the plan's example is `9223`.

## Date normalization

RDAP `eventDate` is RFC3339. Convert to Unix seconds immediately on ingestion and store only the
timestamp:

```python
from datetime import datetime

def rfc3339_to_unix(value: str) -> int:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp())
```

## Test targets

Verify against `vk.ru` (the `.ru` / rdap.ss path), and `docker.io` + `timeweb.com` (the
rdap.net path), plus the negative cases listed above.
