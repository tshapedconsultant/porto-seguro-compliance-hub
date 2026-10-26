"""Client IP trust + rate-limit backend helpers (no Redis / no SSO claims)."""

from __future__ import annotations

import ipaddress

import pytest

from utils.client_ip import (
    parse_trusted_proxy_networks,
    peer_is_trusted,
    reset_trust_warning_for_tests,
    resolve_client_ip,
)


@pytest.fixture(autouse=True)
def _reset_xff_warning():
    reset_trust_warning_for_tests()
    yield
    reset_trust_warning_for_tests()


def test_trust_proxy_false_ignores_xff():
    nets = parse_trusted_proxy_networks("10.0.0.1", "")
    ip = resolve_client_ip(
        "10.0.0.1",
        "203.0.113.9, 10.0.0.1",
        trust_proxy=False,
        trusted_networks=nets,
    )
    assert ip == "10.0.0.1"


def test_trust_proxy_true_without_allowlist_ignores_xff():
    ip = resolve_client_ip(
        "10.0.0.1",
        "203.0.113.9",
        trust_proxy=True,
        trusted_networks=[],
    )
    assert ip == "10.0.0.1"


def test_trust_proxy_true_untrusted_peer_ignores_xff():
    nets = parse_trusted_proxy_networks("10.0.0.1", "")
    ip = resolve_client_ip(
        "192.0.2.50",
        "203.0.113.9",
        trust_proxy=True,
        trusted_networks=nets,
    )
    assert ip == "192.0.2.50"


def test_trust_proxy_true_trusted_peer_uses_leftmost_xff():
    nets = parse_trusted_proxy_networks("10.0.0.1", "")
    assert peer_is_trusted("10.0.0.1", nets)
    ip = resolve_client_ip(
        "10.0.0.1",
        "203.0.113.9, 198.51.100.1",
        trust_proxy=True,
        trusted_networks=nets,
    )
    assert ip == "203.0.113.9"


def test_trusted_proxy_cidr():
    nets = parse_trusted_proxy_networks("", "10.0.0.0/8")
    assert peer_is_trusted("10.1.2.3", nets)
    assert not peer_is_trusted("203.0.113.1", nets)
    assert isinstance(nets[0], (ipaddress.IPv4Network, ipaddress.IPv6Network))


def test_rate_limit_backend_disabled_skips_bucket(monkeypatch):
    import api_server

    monkeypatch.setattr(api_server, "RATE_LIMIT_BACKEND", "disabled")
    api_server.rate_limit_bucket.clear()

    class _Client:
        host = "203.0.113.1"

    class _Req:
        client = _Client()
        headers = {}

    api_server._enforce_rate_limit(_Req())
    assert api_server.rate_limit_bucket == {}
