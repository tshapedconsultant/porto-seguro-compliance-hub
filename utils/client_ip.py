"""
Client IP resolution for rate limiting behind optional reverse proxies.

Safe pattern (documented choice):
- Honor ``X-Forwarded-For`` **only** when the immediate TCP peer is in an explicit
  allowlist (``TRUSTED_PROXY_IPS`` / ``TRUSTED_PROXY_CIDRS``).
- When honored, use the **leftmost** XFF hop (original client as set by a single
  trusted reverse proxy that overwrites/sets the header). Multi-hop chains are
  not validated.
- If ``TRUST_PROXY`` is on but no allowlist is configured → fail closed: ignore XFF.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

_warned_no_allowlist = False


def parse_trusted_proxy_networks(
    ips: str = "",
    cidrs: str = "",
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse comma-separated IPs and CIDRs into networks (host bits ignored)."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in (*(p.strip() for p in ips.split(",")), *(p.strip() for p in cidrs.split(","))):
        if not raw:
            continue
        try:
            if "/" not in raw:
                addr = ipaddress.ip_address(raw)
                networks.append(ipaddress.ip_network(f"{addr}/{addr.max_prefixlen}", strict=False))
            else:
                networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid trusted proxy entry: %s", raw)
    return networks


def peer_is_trusted(
    peer_host: str,
    trusted: Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    if not peer_host or peer_host == "unknown":
        return False
    try:
        addr = ipaddress.ip_address(peer_host)
    except ValueError:
        return False
    return any(addr in net for net in trusted)


def resolve_client_ip(
    peer_host: str,
    x_forwarded_for: Optional[str],
    *,
    trust_proxy: bool,
    trusted_networks: Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> str:
    """
    Resolve client identity for rate-limit keys.

    Returns the direct peer unless trust_proxy is enabled, an allowlist is
    configured, the peer is trusted, and XFF is present — then leftmost XFF hop.
    """
    global _warned_no_allowlist
    peer = peer_host or "unknown"

    if not trust_proxy:
        return peer

    if not trusted_networks:
        if not _warned_no_allowlist:
            logger.warning(
                "TRUST_PROXY=true but TRUSTED_PROXY_IPS/CIDRS empty — "
                "ignoring X-Forwarded-For (fail closed for forwarded IP)."
            )
            _warned_no_allowlist = True
        return peer

    if not peer_is_trusted(peer, trusted_networks):
        return peer

    if not x_forwarded_for:
        return peer

    leftmost = x_forwarded_for.split(",")[0].strip()
    return leftmost or peer


def reset_trust_warning_for_tests() -> None:
    """Test helper: allow the no-allowlist warning to fire again."""
    global _warned_no_allowlist
    _warned_no_allowlist = False
