"""Unit tests for Wiro authentication headers."""

import hashlib
import hmac

import pytest

from genimg.core.providers.wiro_auth import build_wiro_headers


@pytest.mark.unit
class TestWiroAuth:
    def test_api_key_only_headers(self):
        headers = build_wiro_headers("test-api-key", None)
        assert headers == {"x-api-key": "test-api-key"}
        assert "x-nonce" not in headers
        assert "x-signature" not in headers

    def test_signature_headers_with_fixed_nonce(self):
        api_key = "key123"
        api_secret = "secret456"
        nonce = "1700000000"
        headers = build_wiro_headers(api_key, api_secret, nonce=nonce)
        expected_sig = hmac.new(
            api_key.encode("utf-8"),
            (api_secret + nonce).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert headers["x-api-key"] == api_key
        assert headers["x-nonce"] == nonce
        assert headers["x-signature"] == expected_sig

    def test_empty_secret_uses_key_only(self):
        headers = build_wiro_headers("key", "")
        assert headers == {"x-api-key": "key"}
