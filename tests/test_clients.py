"""rdap_client and whois_client never raise — they return None on any error.

These stub the network primitives (aiohttp session / asyncio.open_connection)
so the error-handling contract is exercised without real sockets.
"""

import asyncio
import json

import aiohttp

import rdap_client
import whois_client


# --- rdap_client ----------------------------------------------------------

class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        return self._body


class _FakeSession:
    """Minimal stand-in for aiohttp.ClientSession.get()."""

    def __init__(self, *, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    def get(self, url, headers=None, timeout=None):
        if self._exc is not None:
            raise self._exc
        return self._resp


async def test_fetch_rdap_returns_decoded_json_on_200():
    body = json.dumps({"events": [{"eventAction": "registration"}]}).encode()
    session = _FakeSession(resp=_FakeResp(200, body))
    data = await rdap_client.fetch_rdap(session, "https://rdap/x", "x.com")
    assert data == {"events": [{"eventAction": "registration"}]}


async def test_fetch_rdap_non_200_returns_none():
    session = _FakeSession(resp=_FakeResp(404, b"not found"))
    assert await rdap_client.fetch_rdap(session, "https://rdap/x", "x.com") is None


async def test_fetch_rdap_invalid_json_returns_none():
    session = _FakeSession(resp=_FakeResp(200, b"this is not json"))
    assert await rdap_client.fetch_rdap(session, "https://rdap/x", "x.com") is None


async def test_fetch_rdap_client_error_returns_none():
    session = _FakeSession(exc=aiohttp.ClientError("boom"))
    assert await rdap_client.fetch_rdap(session, "https://rdap/x", "x.com") is None


# --- whois_client ---------------------------------------------------------

class _FakeReader:
    def __init__(self, data):
        self._data = data

    async def read(self):
        return self._data


class _FakeWriter:
    def write(self, data):
        pass

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass


def _patch_connection(monkeypatch, reader=None, exc=None):
    async def fake_open_connection(server, port):
        if exc is not None:
            raise exc
        return reader, _FakeWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)


async def test_query_whois_returns_text(monkeypatch):
    _patch_connection(monkeypatch, reader=_FakeReader(b"created: 2024-01-01T00:00:00Z\n"))
    text = await whois_client.query_whois("whois.tcinet.ru", "vk.ru")
    assert "created" in text


async def test_query_whois_empty_response_returns_none(monkeypatch):
    # Rate-limited registries return an accepted-but-empty body: a failure.
    _patch_connection(monkeypatch, reader=_FakeReader(b"   \n"))
    assert await whois_client.query_whois("whois.tcinet.ru", "vk.ru") is None


async def test_query_whois_connect_error_returns_none(monkeypatch):
    _patch_connection(monkeypatch, exc=OSError("refused"))
    assert await whois_client.query_whois("whois.tcinet.ru", "vk.ru") is None
