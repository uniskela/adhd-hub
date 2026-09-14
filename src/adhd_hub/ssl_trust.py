"""Use the OS certificate store for outbound HTTPS (especially Windows).

CPython on Windows verifies TLS with a bundled CA set (via OpenSSL), not the
Windows certificate store. Browsers and Debian/system Python often succeed for
the same Hub URL because they trust OS / system CAs (including private CAs and
current intermediates). ``truststore`` bridges that gap for ``urllib``/``ssl``.
"""

from __future__ import annotations

import logging
import ssl

log = logging.getLogger(__name__)
_injected = False


def ensure_os_truststore() -> bool:
    """Inject OS trust into the stdlib ssl module once. Returns True if active."""
    global _injected
    if _injected:
        return True
    try:
        import truststore
    except ImportError:
        return False
    try:
        truststore.inject_into_ssl()
    except Exception:
        # Optional integration: platform and third-party SSL patches can fail.
        # Keep the CLI usable, but make the failed initialization diagnosable.
        log.debug("OS truststore injection failed", exc_info=True)
        return False
    _injected = True
    return True


def format_tls_failure(exc: BaseException) -> str:
    """Human guidance for TLS failures (expired cert, private CA, clock skew)."""
    text = str(exc)
    lowered = text.lower()
    if "certificate has expired" in lowered or "cert_has_expired" in lowered:
        return (
            f"{text} — Hub TLS looks expired to this Python. Check: (1) Windows "
            "clock/date is correct, (2) the Hub certificate is renewed (browser "
            "padlock on the Hub URL), (3) any private CA is in the Windows "
            "Trusted Root store (this CLI uses the OS store when truststore is "
            "available). Debian often works already because it uses system CAs."
        )
    if "certificate verify failed" in lowered or "sslcertverificationerror" in lowered:
        return (
            f"{text} — TLS verify failed. On Windows, install your private/internal "
            "CA into Trusted Root Certification Authorities, or set SSL_CERT_FILE "
            "to a PEM bundle. Confirm the Hub certificate chain in a browser."
        )
    if isinstance(exc, ssl.SSLError) or "ssl" in lowered:
        return f"{text} — TLS error talking to the Hub."
    return text


def annotate_connection_error(exc: BaseException) -> ConnectionError:
    """Wrap transport failures with TLS-aware wording when applicable."""
    err = ConnectionError(format_tls_failure(exc))
    err.__cause__ = exc
    return err


def reset_for_tests() -> None:
    """Test helper: allow re-injection after mocks."""
    global _injected
    _injected = False
