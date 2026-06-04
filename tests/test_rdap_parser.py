"""Date extraction across the three upstream formats.

Covers the resilience contract: malformed/missing fields are skipped (returned
as ``None``), never raised, so the caller can still report
``domain_probe_up``/``domain_parsed`` honestly.
"""

import rdap_parser
import rdap_router

# 2024-01-01T00:00:00Z and 2035-01-01T00:00:00Z in Unix seconds (UTC).
CREATED_TS = 1704067200
EXPIRY_TS = 2051222400


class TestRfc3339ToUnix:
    def test_epoch(self):
        assert rdap_parser.rfc3339_to_unix("1970-01-01T00:00:00+00:00") == 0

    def test_z_suffix_is_utc(self):
        assert rdap_parser.rfc3339_to_unix("2024-01-01T00:00:00Z") == CREATED_TS

    def test_explicit_offset(self):
        # 03:00 at +03:00 is the same instant as 00:00Z.
        assert rdap_parser.rfc3339_to_unix("2024-01-01T03:00:00+03:00") == CREATED_TS

    def test_malformed_returns_none(self):
        assert rdap_parser.rfc3339_to_unix("not-a-date") is None

    def test_empty_returns_none(self):
        assert rdap_parser.rfc3339_to_unix("") is None

    def test_non_string_returns_none(self):
        assert rdap_parser.rfc3339_to_unix(None) is None
        assert rdap_parser.rfc3339_to_unix(1704067200) is None


class TestParseRdapEvents:
    def test_both_dates(self):
        data = {
            "events": [
                {"eventAction": "registration", "eventDate": "2024-01-01T00:00:00Z"},
                {"eventAction": "expiration", "eventDate": "2035-01-01T00:00:00Z"},
            ]
        }
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET)
        assert created == CREATED_TS
        assert expiry == EXPIRY_TS

    def test_only_registration(self):
        data = {"events": [{"eventAction": "registration", "eventDate": "2024-01-01T00:00:00Z"}]}
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET)
        assert created == CREATED_TS
        assert expiry is None

    def test_ignores_other_event_actions(self):
        data = {
            "events": [
                {"eventAction": "last changed", "eventDate": "2024-06-01T00:00:00Z"},
                {"eventAction": "expiration", "eventDate": "2035-01-01T00:00:00Z"},
            ]
        }
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET)
        assert created is None
        assert expiry == EXPIRY_TS

    def test_first_registration_wins(self):
        data = {
            "events": [
                {"eventAction": "registration", "eventDate": "2024-01-01T00:00:00Z"},
                {"eventAction": "registration", "eventDate": "1999-01-01T00:00:00Z"},
            ]
        }
        created, _ = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET)
        assert created == CREATED_TS

    def test_missing_events_key(self):
        assert rdap_parser.parse({}, rdap_router.SOURCE_RDAP_NET) == (None, None)

    def test_events_not_a_list(self):
        assert rdap_parser.parse({"events": "nope"}, rdap_router.SOURCE_RDAP_NET) == (None, None)

    def test_skips_non_dict_and_malformed_entries(self):
        data = {
            "events": [
                "garbage",
                {"eventAction": "registration", "eventDate": "bad-date"},
                {"eventAction": "expiration", "eventDate": "2035-01-01T00:00:00Z"},
            ]
        }
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET)
        assert created is None  # malformed date -> skipped, not raised
        assert expiry == EXPIRY_TS


class TestParseRdapSs:
    def test_both_dates(self):
        data = {
            "data": {
                "whoisData": {
                    "Created Date": "2024-01-01T00:00:00Z",
                    "Expiry Date": "2035-01-01T00:00:00Z",
                }
            }
        }
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_SS)
        assert created == CREATED_TS
        assert expiry == EXPIRY_TS

    def test_missing_data_key(self):
        assert rdap_parser.parse({}, rdap_router.SOURCE_RDAP_SS) == (None, None)

    def test_whois_data_not_a_dict(self):
        data = {"data": {"whoisData": []}}
        assert rdap_parser.parse(data, rdap_router.SOURCE_RDAP_SS) == (None, None)

    def test_partial(self):
        data = {"data": {"whoisData": {"Created Date": "2024-01-01T00:00:00Z"}}}
        created, expiry = rdap_parser.parse(data, rdap_router.SOURCE_RDAP_SS)
        assert created == CREATED_TS
        assert expiry is None

    def test_source_selects_format(self):
        # An rdap.ss payload parsed as rdap.net (events) yields nothing, proving
        # the source argument routes to the right parser.
        data = {"data": {"whoisData": {"Created Date": "2024-01-01T00:00:00Z"}}}
        assert rdap_parser.parse(data, rdap_router.SOURCE_RDAP_NET) == (None, None)


class TestParseTcinetWhois:
    def test_created_and_paid_till(self):
        text = (
            "domain: VK.RU\n"
            "created: 2024-01-01T00:00:00Z\n"
            "paid-till: 2035-01-01T00:00:00Z\n"
            "source: TCI\n"
        )
        created, expiry = rdap_parser.parse_tcinet_whois(text)
        assert created == CREATED_TS
        assert expiry == EXPIRY_TS

    def test_ignores_unrelated_lines_and_blanks(self):
        text = "\n% rate limit notice\ncreated: 2024-01-01T00:00:00Z\n"
        created, expiry = rdap_parser.parse_tcinet_whois(text)
        assert created == CREATED_TS
        assert expiry is None

    def test_empty_text(self):
        assert rdap_parser.parse_tcinet_whois("") == (None, None)

    def test_non_string(self):
        assert rdap_parser.parse_tcinet_whois(None) == (None, None)


class TestParseDispatch:
    def test_non_dict_data(self):
        assert rdap_parser.parse(None, rdap_router.SOURCE_RDAP_NET) == (None, None)
        assert rdap_parser.parse("text", rdap_router.SOURCE_RDAP_SS) == (None, None)
