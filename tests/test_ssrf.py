"""
Unit tests for SSRF and network security guard.
"""

import pytest
from app.services.ssrf_guard import (
    validate_url,
    is_ip_allowed,
    SSRFValidationError,
    DNSResolutionError,
)


def test_public_ip_allowed():
    allowed, _ = is_ip_allowed("8.8.8.8")
    assert allowed is True

    allowed, _ = is_ip_allowed("1.1.1.1")
    assert allowed is True


def test_private_ips_blocked():
    blocked_ips = [
        "127.0.0.1",
        "127.0.1.1",
        "10.0.0.1",
        "10.254.254.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.100.50",
        "169.254.169.254",  # AWS / Cloud metadata
        "100.64.0.1",       # Carrier-grade NAT
        "0.0.0.0",
        "::1",              # IPv6 loopback
        "fe80::1",          # IPv6 link-local
    ]
    for ip in blocked_ips:
        allowed, reason = is_ip_allowed(ip)
        assert allowed is False, f"Expected {ip} to be blocked, but was allowed: {reason}"


def test_url_scheme_validation():
    with pytest.raises(SSRFValidationError, match="Disallowed scheme"):
        validate_url("ftp://example.com/file.txt")

    with pytest.raises(SSRFValidationError, match="Disallowed scheme"):
        validate_url("file:///etc/passwd")

    with pytest.raises(SSRFValidationError, match="Disallowed scheme"):
        validate_url("gopher://127.0.0.1:70")


def test_credentials_in_url_blocked():
    with pytest.raises(SSRFValidationError, match="credentials"):
        validate_url("http://admin:secret@example.com")


def test_localhost_and_cloud_metadata_blocked():
    with pytest.raises(SSRFValidationError):
        validate_url("http://localhost:8000")

    with pytest.raises(SSRFValidationError):
        validate_url("http://127.0.0.1:8000/secret")

    with pytest.raises(SSRFValidationError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_dns_resolution_failure_is_distinct_from_ssrf():
    """Unresolvable hostnames raise DNSResolutionError, not an SSRF attack error."""
    with pytest.raises(DNSResolutionError):
        validate_url("https://nonexistent-domain-404-xyz123.invalid")
