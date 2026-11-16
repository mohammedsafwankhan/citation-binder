"""
SSRF (Server-Side Request Forgery) and Network Security Guard for Citation Binder.

Validates URLs and resolved IP addresses to prevent access to:
- Private RFC 1918 networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Loopback addresses (127.0.0.0/8, ::1)
- Link-local and Cloud metadata endpoints (169.254.0.0/16, fe80::/10)
- Carrier-grade NAT (100.64.0.0/10)
- Multicast, broadcast, and reserved ranges
- Internal hostnames and non-standard schemes
"""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple, List

# Explicit prohibited network ranges (defense in depth)
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (source-only)
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 Private
    ipaddress.ip_network("100.64.0.0/10"),       # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),       # Link-local / Cloud Metadata
    ipaddress.ip_network("172.16.0.0/12"),       # RFC 1918 Private
    ipaddress.ip_network("192.0.0.0/24"),        # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),      # RFC 1918 Private
    ipaddress.ip_network("198.18.0.0/15"),       # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),              # Unspecified
    ipaddress.ip_network("::1/128"),             # Loopback
    ipaddress.ip_network("fc00::/7"),            # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),           # Link-local unicast
    ipaddress.ip_network("ff00::/8"),            # Multicast
]

# Sensitive cloud metadata hostnames
PROHIBITED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


class SSRFValidationError(ValueError):
    """Raised when a URL or target IP violates SSRF security boundaries."""
    pass


class DNSResolutionError(ValueError):
    """Raised when a public domain fails DNS resolution (e.g. NXDOMAIN, network down)."""
    pass


def is_ip_allowed(ip_str: str) -> Tuple[bool, str]:
    """
    Validates whether an IP address is safe to contact (public, non-reserved).
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address format: {ip_str}"

    # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped

    if ip_obj.is_loopback:
        return False, f"Loopback address forbidden: {ip_obj}"
    if ip_obj.is_private:
        return False, f"Private network address forbidden: {ip_obj}"
    if ip_obj.is_link_local:
        return False, f"Link-local / cloud metadata address forbidden: {ip_obj}"
    if ip_obj.is_multicast:
        return False, f"Multicast address forbidden: {ip_obj}"
    if ip_obj.is_reserved:
        return False, f"Reserved address forbidden: {ip_obj}"
    if ip_obj.is_unspecified:
        return False, f"Unspecified address forbidden: {ip_obj}"

    # Extra check against explicit prohibited networks
    for net in PROHIBITED_NETWORKS:
        if ip_obj in net:
            return False, f"IP {ip_obj} falls within prohibited block {net}"

    return True, "IP is public and allowed"


def resolve_and_validate_hostname(hostname: str) -> List[str]:
    """
    Resolves hostname to IP addresses and verifies that EVERY resolved IP
    is public and permitted.
    """
    hostname_clean = hostname.strip().lower()

    if hostname_clean in PROHIBITED_HOSTNAMES or hostname_clean.endswith(".local") or hostname_clean.endswith(".internal"):
        raise SSRFValidationError(f"Hostname '{hostname}' is a prohibited or internal domain.")

    # Check if hostname is directly an IP address
    try:
        direct_ip = ipaddress.ip_address(hostname_clean)
        allowed, reason = is_ip_allowed(str(direct_ip))
        if not allowed:
            raise SSRFValidationError(f"Target IP '{hostname}' is blocked: {reason}")
        return [str(direct_ip)]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(hostname_clean, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        # Hostname cannot be resolved - distinct from SSRF security attack!
        raise DNSResolutionError(f"Could not resolve hostname '{hostname}': {e}")

    resolved_ips = []
    for family, _, _, _, sockaddr in addr_info:
        ip = sockaddr[0]
        if ip not in resolved_ips:
            resolved_ips.append(ip)

    if not resolved_ips:
        raise DNSResolutionError(f"Hostname '{hostname}' did not resolve to any IP address.")

    for ip in resolved_ips:
        allowed, reason = is_ip_allowed(ip)
        if not allowed:
            raise SSRFValidationError(f"Access to '{hostname}' (resolved to {ip}) is blocked: {reason}")

    return resolved_ips


def validate_url(url: str) -> Tuple[str, List[str]]:
    """
    Validates a URL before fetching:
    1. Enforces http/https scheme.
    2. Strips and rejects credentials (user:pass).
    3. Resolves DNS and checks IP safety.
    Returns: (cleaned_canonical_url, resolved_public_ips)
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL must be a non-empty string.")

    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFValidationError(f"Disallowed scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted.")

    if not parsed.hostname:
        raise SSRFValidationError("URL must contain a valid hostname.")

    if parsed.username or parsed.password:
        raise SSRFValidationError("Embedded credentials (username:password) in URL are prohibited.")

    # Validate port if specified
    if parsed.port is not None:
        if parsed.port not in (80, 443, 8080, 8443):
            raise SSRFValidationError(f"Port {parsed.port} is not in the allowed HTTP/HTTPS ports whitelist.")

    # Validate hostname and all resolved IPs
    resolved_ips = resolve_and_validate_hostname(parsed.hostname)

    return cleaned_url, resolved_ips
