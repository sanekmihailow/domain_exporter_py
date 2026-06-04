"""Exposition output — the metric contract from CLAUDE.md.

The critical rule under test: a missing timestamp is *omitted*, never emitted as
0 (which would read as 1970-01-01 and corrupt dashboards).
"""

import metrics


def _lines(body: bytes):
    """Non-comment metric sample lines from exposition output."""
    return [
        ln for ln in body.decode("utf-8").splitlines()
        if ln and not ln.startswith("#")
    ]


def _value(body: bytes, metric: str, domain: str):
    """Return the float value of `metric{domain=...}`, or None if absent."""
    needle = f'{metric}{{domain="{domain}"}}'
    for ln in _lines(body):
        name, _, value = ln.rpartition(" ")
        if name == needle:
            return float(value)
    return None


class TestAlwaysEmitted:
    def test_probe_up_and_parsed_present_on_success(self):
        result = {
            "probe_up": 1,
            "domain_parsed": 1,
            "created_timestamp": 1704067200,
            "expiry_timestamp": 2051222400,
        }
        body = metrics.render("vk.ru", result)
        assert _value(body, "domain_probe_up", "vk.ru") == 1.0
        assert _value(body, "domain_parsed", "vk.ru") == 1.0

    def test_probe_up_and_parsed_present_on_total_failure(self):
        # Upstream down: empty result dict -> both booleans default to 0.
        body = metrics.render("down.example", {})
        assert _value(body, "domain_probe_up", "down.example") == 0.0
        assert _value(body, "domain_parsed", "down.example") == 0.0

    def test_label_is_carried(self):
        body = metrics.render("docker.io", {"probe_up": 1, "domain_parsed": 0})
        assert 'domain_probe_up{domain="docker.io"}' in body.decode("utf-8")


class TestTimestampOmission:
    def test_timestamps_omitted_when_missing(self):
        body = metrics.render("down.example", {"probe_up": 0, "domain_parsed": 0})
        text = body.decode("utf-8")
        # Never emit the timestamp metrics at all when there's no date.
        assert "domain_created_timestamp_seconds" not in text
        assert "domain_expiry_timestamp_seconds" not in text

    def test_only_created_emitted_when_expiry_missing(self):
        result = {
            "probe_up": 1,
            "domain_parsed": 0,
            "created_timestamp": 1704067200,
            "expiry_timestamp": None,
        }
        body = metrics.render("partial.example", result)
        assert _value(body, "domain_created_timestamp_seconds", "partial.example") == 1704067200.0
        assert "domain_expiry_timestamp_seconds" not in body.decode("utf-8")

    def test_zero_timestamp_is_never_synthesized(self):
        # The reachable-but-unparsed case: probe_up=1, parsed=0, no dates.
        result = {"probe_up": 1, "domain_parsed": 0,
                  "created_timestamp": None, "expiry_timestamp": None}
        body = metrics.render("reachable.example", result)
        text = body.decode("utf-8")
        assert "timestamp_seconds" not in text

    def test_genuine_zero_timestamp_is_still_emitted(self):
        # A real epoch date (0) is a present value, so it must be emitted —
        # omission is keyed on None, not on falsiness.
        result = {"probe_up": 1, "domain_parsed": 1,
                  "created_timestamp": 0, "expiry_timestamp": 2051222400}
        body = metrics.render("epoch.example", result)
        assert _value(body, "domain_created_timestamp_seconds", "epoch.example") == 0.0


class TestRegistryIsolation:
    def test_label_does_not_accumulate_across_renders(self):
        # Each render uses a fresh registry, so output for one domain must not
        # carry samples for a previously rendered domain.
        metrics.render("first.example", {"probe_up": 1, "domain_parsed": 0})
        body = metrics.render("second.example", {"probe_up": 1, "domain_parsed": 0})
        text = body.decode("utf-8")
        assert 'domain="second.example"' in text
        assert 'domain="first.example"' not in text
