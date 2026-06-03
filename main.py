"""HTTP server exposing the /get probe endpoint.

Prometheus scrapes /get?target=<domain>. For each request we consult the TTL
cache, and on a miss we route -> fetch -> parse, derive the probe_up/parsed
flags, cache the normalized result (success or failure), and render metrics.
"""

import argparse
import logging
import time

import aiohttp
from aiohttp import web

import cache
import config
import metrics
import rdap_client
import rdap_parser
import rdap_router
import whois_client

logger = logging.getLogger("domain_exporter")


def setup_logging(debug: bool) -> None:
    # Keep the root logger at INFO so third-party libraries (aiohttp, asyncio)
    # don't flood the output; only raise our own loggers to DEBUG.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("domain_exporter").setLevel(
        logging.DEBUG if debug else logging.INFO
    )


async def probe_domain(session: aiohttp.ClientSession, domain: str) -> dict:
    """Return a normalized result dict for the domain (cached for TTL)."""
    cached = cache.get_domain(domain)
    if cached is not None:
        logger.info("cache HIT  %s", domain)
        return cached

    route = rdap_router.select_endpoint(domain)
    logger.info("cache MISS %s -> %s", domain, route.source)
    logger.debug("route %s: url=%s whois_fallback=%s", domain, route.url, route.whois_server)

    created = expiry = None
    probe_up = 0
    source_used = route.source

    data = await rdap_client.fetch_rdap(session, route.url, domain)
    if data is not None:
        created, expiry = rdap_parser.parse(data, route.source)
        probe_up = 1
    elif route.whois_server is not None:
        # Primary (rdap.ss) is down — fall back to raw WHOIS for TCI zones.
        text = await whois_client.query_whois(route.whois_server, route.domain)
        if text is not None:
            created, expiry = rdap_parser.parse_tcinet_whois(text)
            probe_up = 1
            source_used = rdap_router.SOURCE_WHOIS_TCINET

    parsed = 1 if (created is not None and expiry is not None) else 0
    result = {
        "source": source_used,
        "created_timestamp": created,
        "expiry_timestamp": expiry,
        "probe_up": probe_up,
        "domain_parsed": parsed,
        "cached_at": int(time.time()),
    }

    cache.set_domain(domain, result)
    logger.debug(
        "result %s: source=%s probe_up=%s parsed=%s created=%s expiry=%s",
        domain, source_used, probe_up, parsed, created, expiry,
    )
    return result


async def handle_get(request: web.Request) -> web.Response:
    domain = request.query.get("target", "").strip()
    if not domain:
        return web.Response(status=400, text="missing 'target' query parameter\n")

    session: aiohttp.ClientSession = request.app["session"]
    result = await probe_domain(session, domain)
    body = metrics.render(domain, result)
    return web.Response(body=body, content_type="text/plain", charset="utf-8")


async def handle_index(request: web.Request) -> web.Response:
    return web.Response(
        text="domain_exporter_py\nProbe a domain at /get?target=<domain>\n"
    )


async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="ok\n")


async def _on_startup(app: web.Application) -> None:
    app["session"] = aiohttp.ClientSession()


async def _on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def build_app() -> web.Application:
    app = web.Application()
    app.add_routes(
        [
            web.get("/", handle_index),
            web.get("/get", handle_get),
            web.get("/health", handle_health),
        ]
    )
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prometheus exporter for domain registration/expiry dates via RDAP."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=config.DEBUG,
        help="enable verbose debug logging (env: DEBUG)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.debug)
    logger.info("Starting domain_exporter_py on %s:%s", config.HOST, config.PORT)
    logger.debug("Debug logging enabled")
    web.run_app(build_app(), host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
