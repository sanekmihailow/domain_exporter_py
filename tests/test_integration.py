"""Live integration tests — hit the real RDAP/WHOIS upstreams.

Skipped by default (see pytest.ini `addopts`). Run explicitly with:

    pytest -m integration

These are inherently slow and may flake when an upstream is down or
rate-limiting; that is expected and is exactly why they are gated behind a
marker rather than run in the normal suite. The target domains come from the
CLAUDE.md test-target list.
"""

import aiohttp
import pytest

import cache
import main
import metrics
import rdap_router

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_domain_cache():
    # The domain cache is module-level and persists for the whole process, so a
    # failed probe would otherwise leak into later tests that hit the same
    # domain. Clear it before each test for independent live probes.
    cache.domain_cache.clear()
    yield


async def _probe(domain: str) -> dict:
    """Run a real probe through a live aiohttp session."""
    async with aiohttp.ClientSession() as session:
        return await main.probe_domain(session, domain)


def _assert_parsed(result: dict, expected_source: str) -> None:
    assert result["probe_up"] == 1, "upstream did not return valid JSON"
    assert result["domain_parsed"] == 1, "both dates should have been extracted"
    assert result["source"] == expected_source
    # Both timestamps present and ordered created < expiry.
    assert result["created_timestamp"] is not None
    assert result["expiry_timestamp"] is not None
    assert result["created_timestamp"] < result["expiry_timestamp"]


async def test_vk_ru_via_rdap_ss():
    # The .ru / rdap.ss path (source may degrade to whois fallback if rdap.ss
    # is down — both are valid TCI sources).
    result = await _probe("vk.ru")
    assert result["probe_up"] == 1
    assert result["domain_parsed"] == 1
    assert result["source"] in (
        rdap_router.SOURCE_RDAP_SS,
        rdap_router.SOURCE_WHOIS_TCINET,
    )
    assert result["created_timestamp"] < result["expiry_timestamp"]


async def test_docker_io_via_rdap_net():
    _assert_parsed(await _probe("docker.io"), rdap_router.SOURCE_RDAP_NET)


async def test_timeweb_com_via_rdap_net():
    _assert_parsed(await _probe("timeweb.com"), rdap_router.SOURCE_RDAP_NET)


async def test_nonexistent_domain_is_not_a_false_success():
    # Negative case: a bogus domain must never report parsed=1.
    result = await _probe("this-domain-should-not-exist-zzz999.com")
    assert result["domain_parsed"] == 0


async def test_metrics_render_for_live_probe():
    # The full path a Prometheus scrape takes: probe -> render exposition.
    result = await _probe("docker.io")
    body = metrics.render("docker.io", result)
    text = body.decode("utf-8")
    assert 'domain_probe_up{domain="docker.io"}' in text
    assert 'domain_expiry_timestamp_seconds{domain="docker.io"}' in text
