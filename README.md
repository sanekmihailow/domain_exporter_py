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
- Routes by domain zone: TCI zones (`.ru`/`.su`/`.рф`) to rdap.ss with a raw-WHOIS
  fallback (`whois.tcinet.ru`), everything else to rdap.net.
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

## Routing

TCI zones (`.ru`, `.su`, `.рф`) are served by the Russian registry; rdap.ss is
an HTTP wrapper over `whois.tcinet.ru`. They are queried via rdap.ss first, with
a raw-WHOIS fallback when rdap.ss is down. Everything else goes to rdap.net.

| Zone                | Primary                                  | Fallback                  |
| ------------------- | ---------------------------------------- | ------------------------- |
| `.ru` `.su` `.рф`   | `https://rdap.ss/api/query?q=<domain>`   | `whois.tcinet.ru:43`      |
| others              | `https://www.rdap.net/domain/<domain>`   | —                         |

Domains are IDNA-normalized before routing, so `.рф` is matched as `.xn--p1ai`.
The TCI zones use this explicit override rather than IANA bootstrap. The WHOIS
fallback is a last resort — `whois.tcinet.ru` rate-limits hard, and an empty
response counts as a failure (`domain_probe_up=0`), never a false success.

## Running

Locally:

```bash
pip install -r requirements.txt
python main.py            # listens on 0.0.0.0:9223
python main.py --debug    # verbose per-request logging
```

With Docker:

```bash
docker build -t domain-exporter .
docker run -d -p 9223:9223 domain-exporter
# or the example stack:
docker compose -f docker-compose.example.yml up --build -d
```

### Configuration

All settings are environment variables (defaults shown):

| Variable             | Default            | Description                                  |
| -------------------- | ------------------ | -------------------------------------------- |
| `EXPORTER_HOST`      | `0.0.0.0`          | Listen address                               |
| `EXPORTER_PORT`      | `9223`             | Listen port                                  |
| `RDAP_TIMEOUT`       | `10`               | Outbound RDAP/WHOIS timeout (seconds)        |
| `DOMAIN_CACHE_TTL`   | `86400`            | Per-domain result cache TTL (seconds)        |
| `DEBUG`              | `false`            | Verbose logging (same as `--debug`)          |

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
