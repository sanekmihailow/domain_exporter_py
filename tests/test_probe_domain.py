"""End-to-end orchestration in main.probe_domain.

Network is stubbed via monkeypatch; these tests pin the two-tier success
contract (probe_up vs domain_parsed), the rdap.ss -> whois fallback, and that
results (success *and* failure) are cached.
"""

import cache
import main
import rdap_client
import rdap_router
import whois_client

CREATED = "2024-01-01T00:00:00Z"
EXPIRY = "2035-01-01T00:00:00Z"
CREATED_TS = 1704067200
EXPIRY_TS = 2051222400

SESSION = object()  # opaque; stubbed clients ignore it


class _Recorder:
    """Counts calls so we can assert cache hits skip the network."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.value


def _patch_rdap(monkeypatch, value):
    rec = _Recorder(value)
    monkeypatch.setattr(rdap_client, "fetch_rdap", rec)
    return rec


def _patch_whois(monkeypatch, value):
    rec = _Recorder(value)
    monkeypatch.setattr(whois_client, "query_whois", rec)
    return rec


def setup_function():
    cache.domain_cache.clear()


async def test_rdap_net_success_both_dates(monkeypatch):
    _patch_rdap(monkeypatch, {
        "events": [
            {"eventAction": "registration", "eventDate": CREATED},
            {"eventAction": "expiration", "eventDate": EXPIRY},
        ]
    })
    result = await main.probe_domain(SESSION, "docker.io")
    assert result["probe_up"] == 1
    assert result["domain_parsed"] == 1
    assert result["created_timestamp"] == CREATED_TS
    assert result["expiry_timestamp"] == EXPIRY_TS
    assert result["source"] == rdap_router.SOURCE_RDAP_NET


async def test_reachable_but_one_date_missing_is_probe_up_not_parsed(monkeypatch):
    # The CLAUDE.md two-tier rule: JSON parsed -> probe_up=1, but a missing
    # field keeps parsed=0, and the absent timestamp stays None (-> omitted).
    _patch_rdap(monkeypatch, {
        "events": [{"eventAction": "registration", "eventDate": CREATED}]
    })
    result = await main.probe_domain(SESSION, "docker.io")
    assert result["probe_up"] == 1
    assert result["domain_parsed"] == 0
    assert result["created_timestamp"] == CREATED_TS
    assert result["expiry_timestamp"] is None


async def test_upstream_down_is_total_failure(monkeypatch):
    # rdap.net has no fallback -> probe_up=0, no dates.
    _patch_rdap(monkeypatch, None)
    result = await main.probe_domain(SESSION, "docker.io")
    assert result["probe_up"] == 0
    assert result["domain_parsed"] == 0
    assert result["created_timestamp"] is None
    assert result["expiry_timestamp"] is None


async def test_tci_uses_rdap_ss_when_up(monkeypatch):
    _patch_rdap(monkeypatch, {
        "data": {"whoisData": {"Created Date": CREATED, "Expiry Date": EXPIRY}}
    })
    whois = _patch_whois(monkeypatch, "should not be called")
    result = await main.probe_domain(SESSION, "vk.ru")
    assert result["source"] == rdap_router.SOURCE_RDAP_SS
    assert result["probe_up"] == 1
    assert result["domain_parsed"] == 1
    assert whois.calls == 0  # fallback untouched while primary works


async def test_tci_falls_back_to_whois_when_rdap_ss_down(monkeypatch):
    _patch_rdap(monkeypatch, None)  # rdap.ss down
    _patch_whois(monkeypatch,
                 f"domain: VK.RU\ncreated: {CREATED}\npaid-till: {EXPIRY}\n")
    result = await main.probe_domain(SESSION, "vk.ru")
    assert result["source"] == rdap_router.SOURCE_WHOIS_TCINET
    assert result["probe_up"] == 1
    assert result["domain_parsed"] == 1
    assert result["created_timestamp"] == CREATED_TS
    assert result["expiry_timestamp"] == EXPIRY_TS


async def test_tci_total_failure_when_both_down(monkeypatch):
    # rdap.ss down and whois rate-limited (empty -> None): never a false success.
    _patch_rdap(monkeypatch, None)
    _patch_whois(monkeypatch, None)
    result = await main.probe_domain(SESSION, "vk.ru")
    assert result["probe_up"] == 0
    assert result["domain_parsed"] == 0


async def test_cache_hit_skips_network(monkeypatch):
    rec = _patch_rdap(monkeypatch, {
        "events": [
            {"eventAction": "registration", "eventDate": CREATED},
            {"eventAction": "expiration", "eventDate": EXPIRY},
        ]
    })
    await main.probe_domain(SESSION, "docker.io")
    await main.probe_domain(SESSION, "docker.io")
    assert rec.calls == 1  # second scrape served from cache


async def test_failed_lookup_is_cached(monkeypatch):
    rec = _patch_rdap(monkeypatch, None)
    await main.probe_domain(SESSION, "docker.io")
    await main.probe_domain(SESSION, "docker.io")
    assert rec.calls == 1  # broken upstream not re-hammered
