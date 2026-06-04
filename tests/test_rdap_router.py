"""Routing: TCI zones -> rdap.ss (+whois fallback), everything else -> rdap.net.

The intentional override of IANA bootstrap (see CLAUDE.md) is what these tests
pin down, including IDNA normalization of `.рф` to `xn--p1ai`.
"""

import config
import rdap_router


class TestTciZones:
    def test_ru_goes_to_rdap_ss(self):
        route = rdap_router.select_endpoint("vk.ru")
        assert route.source == rdap_router.SOURCE_RDAP_SS
        assert route.url == config.RDAP_SS_URL.format(domain="vk.ru")
        assert route.whois_server == config.WHOIS_TCINET_SERVER

    def test_su_goes_to_rdap_ss(self):
        route = rdap_router.select_endpoint("example.su")
        assert route.source == rdap_router.SOURCE_RDAP_SS
        assert route.whois_server == config.WHOIS_TCINET_SERVER

    def test_cyrillic_rf_is_punycoded(self):
        route = rdap_router.select_endpoint("пример.рф")
        assert route.source == rdap_router.SOURCE_RDAP_SS
        # Whole domain is IDNA-encoded; the .рф zone becomes xn--p1ai.
        assert route.domain.endswith(".xn--p1ai")
        assert route.url == config.RDAP_SS_URL.format(domain=route.domain)

    def test_fallback_is_whois_tcinet_only_for_tci(self):
        assert rdap_router.select_endpoint("vk.ru").whois_server is not None


class TestNonTciZones:
    def test_com_goes_to_rdap_net(self):
        route = rdap_router.select_endpoint("docker.io")
        assert route.source == rdap_router.SOURCE_RDAP_NET
        assert route.url == config.RDAP_NET_URL.format(domain="docker.io")
        assert route.whois_server is None

    def test_timeweb_com(self):
        route = rdap_router.select_endpoint("timeweb.com")
        assert route.source == rdap_router.SOURCE_RDAP_NET
        assert route.whois_server is None


class TestNormalization:
    def test_uppercase_lowered(self):
        assert rdap_router.select_endpoint("VK.RU").domain == "vk.ru"

    def test_trailing_dot_stripped(self):
        assert rdap_router.select_endpoint("vk.ru.").domain == "vk.ru"

    def test_surrounding_whitespace_stripped(self):
        assert rdap_router.select_endpoint("  docker.io  ").domain == "docker.io"

    def test_substring_ru_not_misrouted(self):
        # A `.com` domain that merely contains "ru" must not match the .ru zone.
        route = rdap_router.select_endpoint("guru.com")
        assert route.source == rdap_router.SOURCE_RDAP_NET
