# domain_exporter_py

A Python Prometheus exporter that reports domain registration and expiry dates obtained via RDAP.
It runs in **probe mode** (like `blackbox_exporter`): Prometheus passes the domain in a `target`
parameter, and the exporter performs a live RDAP lookup and returns the metrics.

> **Status:** under development.

## Features

- Probe model: `/get?target=<domain>` — one domain handled per scrape, no preloading or batching.
- Extracts exactly two dates from the RDAP `events[]` array:
  - `registration` → created date,
  - `expiration` → expiry date.
- Converts RFC3339 dates into Unix timestamps.
- Routes the RDAP source based on the domain zone.
- Two independent cache layers (the IANA bootstrap registry and per-domain results), TTL 24h.
- Resilient: the process never crashes on upstream errors and always returns a valid scrape.

## Metrics

```
domain_probe_up{domain="..."}                      # 1 if RDAP responded with valid JSON, else 0
domain_parsed{domain="..."}                        # 1 only if BOTH fields (registration and expiration) were extracted
domain_created_timestamp_seconds{domain="..."}     # emitted only if registration was found
domain_expiry_timestamp_seconds{domain="..."}      # emitted only if expiration was found
```

`domain_probe_up` and `domain_parsed` are always emitted. Timestamp metrics are published only when
the corresponding date is present — a missing date is **not** set to `0`, since that would be
misread as `1970-01-01`.

Example response:

```
domain_probe_up{domain="vk.ru"} 1
domain_parsed{domain="vk.ru"} 1
domain_created_timestamp_seconds{domain="vk.ru"} 1704067200
domain_expiry_timestamp_seconds{domain="vk.ru"} 1735689600
```

## RDAP routing

| Zone      | Source                                    |
| --------- | ----------------------------------------- |
| `.ru`     | `https://rdap.ss/api/query?q=<domain>`    |
| others    | `https://www.rdap.net/domain/<domain>`    |

The `.ru` zone is handled by an explicit override rather than through IANA bootstrap.

## Prometheus configuration

```yaml
- job_name: "domain_expiry"
  metrics_path: /get
  relabel_configs:
    - source_labels: [__address__]
      target_label: __param_target
    - source_labels: [__param_target]
      target_label: domain
    - target_label: __address__
      replacement: localhost:9223
  static_configs:
    - targets:
        - vk.ru
        - timeweb.com
        - example.com
```

The domain list is configured on the Prometheus side.

## Stack

- `aiohttp` — async HTTP client and server
- `prometheus_client` — metric exposition
- TTL cache (`cachetools` or a hand-rolled implementation)

## License

[MIT](LICENSE)
