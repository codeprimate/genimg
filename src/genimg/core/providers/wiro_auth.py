"""Wiro API authentication headers (API key and optional HMAC signature)."""

from __future__ import annotations

import hashlib
import hmac
import time


def build_wiro_headers(
    api_key: str,
    api_secret: str | None,
    *,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build Wiro request headers for API key or signature-based auth.

    When ``api_secret`` is set, adds ``x-nonce`` and ``x-signature`` per Wiro docs:
    ``HMAC-SHA256(key=API_KEY, message=API_SECRET + NONCE)`` as hex digest.
    """
    headers = {"x-api-key": api_key}
    secret = (api_secret or "").strip()
    if not secret:
        return headers

    nonce_value = nonce if nonce is not None else str(int(time.time()))
    message = secret + nonce_value
    signature = hmac.new(
        api_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers["x-nonce"] = nonce_value
    headers["x-signature"] = signature
    return headers
