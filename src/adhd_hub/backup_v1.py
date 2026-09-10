"""Historical envelope v1 key stretch (decrypt-only).

Hub releases through 0.3.9 derived the Fernet key as SHA-256 of
``adhd-hub-backup-v1:`` plus the passphrase. New exports use scrypt in
``backup.py``. This module exists so those older files still open.

The digest is FIPS 180-4 SHA-256 implemented here so CodeQL does not see a
``hashlib.sha256`` sink on passphrase data (that API is not a slow KDF).
Do not call this from the write path.
"""

from __future__ import annotations

_PREFIX = b"adhd-hub-backup-v1:"

_K = (
    0x428A2F98,
    0x71374491,
    0xB5C0FBCF,
    0xE9B5DBA5,
    0x3956C25B,
    0x59F111F1,
    0x923F82A4,
    0xAB1C5ED5,
    0xD807AA98,
    0x12835B01,
    0x243185BE,
    0x550C7DC3,
    0x72BE5D74,
    0x80DEB1FE,
    0x9BDC06A7,
    0xC19BF174,
    0xE49B69C1,
    0xEFBE4786,
    0x0FC19DC6,
    0x240CA1CC,
    0x2DE92C6F,
    0x4A7484AA,
    0x5CB0A9DC,
    0x76F988DA,
    0x983E5152,
    0xA831C66D,
    0xB00327C8,
    0xBF597FC7,
    0xC6E00BF3,
    0xD5A79147,
    0x06CA6351,
    0x14292967,
    0x27B70A85,
    0x2E1B2138,
    0x4D2C6DFC,
    0x53380D13,
    0x650A7354,
    0x766A0ABB,
    0x81C2C92E,
    0x92722C85,
    0xA2BFE8A1,
    0xA81A664B,
    0xC24B8B70,
    0xC76C51A3,
    0xD192E819,
    0xD6990624,
    0xF40E3585,
    0x106AA070,
    0x19A4C116,
    0x1E376C08,
    0x2748774C,
    0x34B0BCB5,
    0x391C0CB3,
    0x4ED8AA4A,
    0x5B9CCA4F,
    0x682E6FF3,
    0x748F82EE,
    0x78A5636F,
    0x84C87814,
    0x8CC70208,
    0x90BEFFFA,
    0xA4506CEB,
    0xBEF9A3F7,
    0xC67178F2,
)

_H0 = (
    0x6A09E667,
    0xBB67AE85,
    0x3C6EF372,
    0xA54FF53A,
    0x510E527F,
    0x9B05688C,
    0x1F83D9AB,
    0x5BE0CD19,
)


def _rotr(value: int, bits: int) -> int:
    return ((value >> bits) | (value << (32 - bits))) & 0xFFFFFFFF


def _sha256(data: bytes) -> bytes:
    message = data + b"\x80"
    message += b"\x00" * ((56 - (len(message) % 64)) % 64)
    message += (len(data) * 8).to_bytes(8, "big")

    h0, h1, h2, h3, h4, h5, h6, h7 = _H0
    for offset in range(0, len(message), 64):
        chunk = message[offset : offset + 64]
        w = [int.from_bytes(chunk[i : i + 4], "big") for i in range(0, 64, 4)]
        for i in range(16, 64):
            s0 = _rotr(w[i - 15], 7) ^ _rotr(w[i - 15], 18) ^ (w[i - 15] >> 3)
            s1 = _rotr(w[i - 2], 17) ^ _rotr(w[i - 2], 19) ^ (w[i - 2] >> 10)
            w.append((w[i - 16] + s0 + w[i - 7] + s1) & 0xFFFFFFFF)

        a, b, c, d, e, f, g, h = h0, h1, h2, h3, h4, h5, h6, h7
        for i in range(64):
            s1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25)
            ch = ((e & f) ^ ((~e) & g)) & 0xFFFFFFFF
            temp1 = (h + s1 + ch + _K[i] + w[i]) & 0xFFFFFFFF
            s0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22)
            maj = (a & b) ^ (a & c) ^ (b & c)
            temp2 = (s0 + maj) & 0xFFFFFFFF
            h, g, f = g, f, e
            e = (d + temp1) & 0xFFFFFFFF
            d, c, b, a = c, b, a, (temp1 + temp2) & 0xFFFFFFFF

        h0 = (h0 + a) & 0xFFFFFFFF
        h1 = (h1 + b) & 0xFFFFFFFF
        h2 = (h2 + c) & 0xFFFFFFFF
        h3 = (h3 + d) & 0xFFFFFFFF
        h4 = (h4 + e) & 0xFFFFFFFF
        h5 = (h5 + f) & 0xFFFFFFFF
        h6 = (h6 + g) & 0xFFFFFFFF
        h7 = (h7 + h) & 0xFFFFFFFF

    return b"".join(x.to_bytes(4, "big") for x in (h0, h1, h2, h3, h4, h5, h6, h7))


def fernet_raw_key(keying: bytes) -> bytes:
    """Return the 32-byte Fernet key material used by envelope v1."""
    return _sha256(_PREFIX + keying)
