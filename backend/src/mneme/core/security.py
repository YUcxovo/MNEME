"""Small, provider-independent security helpers."""

import hashlib
import hmac


def token_sha256(raw_token: str) -> str:
    """Return the lowercase SHA-256 hex digest for an opaque token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def token_matches_sha256(raw_token: str, expected_digest: str) -> bool:
    """Compare an opaque token with a configured SHA-256 digest in constant time."""
    return hmac.compare_digest(token_sha256(raw_token), expected_digest.lower())
