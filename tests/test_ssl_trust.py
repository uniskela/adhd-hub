"""Tests for OS truststore injection and TLS error wording."""

from __future__ import annotations

from urllib.error import URLError

import pytest

from adhd_hub import ssl_trust


@pytest.fixture(autouse=True)
def _reset_trust_injection() -> None:
    ssl_trust.reset_for_tests()
    yield
    ssl_trust.reset_for_tests()


def test_format_tls_failure_expired_cert_mentions_windows_guidance() -> None:
    exc = URLError(
        "certificate verify failed: certificate has expired (_ssl.c:1082)"
    )
    msg = ssl_trust.format_tls_failure(exc)
    assert "certificate has expired" in msg
    assert "Windows" in msg
    assert "clock" in msg.lower()


def test_format_tls_failure_generic_verify_mentions_private_ca() -> None:
    exc = URLError("certificate verify failed: unable to get local issuer certificate")
    msg = ssl_trust.format_tls_failure(exc)
    assert "private" in msg.lower() or "Trusted Root" in msg


def test_annotate_connection_error_wraps_urlerror() -> None:
    exc = URLError("certificate verify failed: certificate has expired")
    wrapped = ssl_trust.annotate_connection_error(exc)
    assert isinstance(wrapped, ConnectionError)
    assert "expired" in str(wrapped).lower()
    assert wrapped.__cause__ is exc


def test_ensure_os_truststore_idempotent() -> None:
    first = ssl_trust.ensure_os_truststore()
    second = ssl_trust.ensure_os_truststore()
    assert first is True
    assert second is True
