"""Domain result cache and bootstrap freshness."""

import time

import cache


class TestDomainCache:
    def setup_method(self):
        cache.domain_cache.clear()

    def test_miss_returns_none(self):
        assert cache.get_domain("absent.example") is None

    def test_set_then_get_roundtrip(self):
        result = {"probe_up": 1, "domain_parsed": 1, "created_timestamp": 1, "expiry_timestamp": 2}
        cache.set_domain("vk.ru", result)
        assert cache.get_domain("vk.ru") is result

    def test_failed_lookup_is_cached_too(self):
        # Broken upstreams must be cached so repeated scrapes don't hammer them.
        failure = {"probe_up": 0, "domain_parsed": 0,
                   "created_timestamp": None, "expiry_timestamp": None}
        cache.set_domain("down.example", failure)
        assert cache.get_domain("down.example") == failure


class TestBootstrapFreshness:
    def test_empty_cache_is_not_fresh(self):
        bc = cache.BootstrapCache()
        assert bc.is_fresh is False

    def test_recently_fetched_is_fresh(self):
        bc = cache.BootstrapCache()
        bc._data = {"services": []}
        bc._fetched_at = time.time()
        assert bc.is_fresh is True

    def test_stale_fetch_is_not_fresh(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "BOOTSTRAP_CACHE_TTL", 100)
        bc = cache.BootstrapCache()
        bc._data = {"services": []}
        bc._fetched_at = time.time() - 200  # older than TTL
        assert bc.is_fresh is False
