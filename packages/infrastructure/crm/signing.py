"""HMAC-SHA256 signing and verification for webhook delivery integrity."""

import hashlib
import hmac


def compute_webhook_signature(timestamp: str, raw_body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for outgoing webhook payload: HMAC(timestamp + '.' + raw_body, secret)."""
    payload_to_sign = f"{timestamp}.{raw_body}".encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    return hmac.new(secret_bytes, payload_to_sign, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    provided_signature: str, timestamp: str, raw_body: str, secret: str
) -> bool:
    """Verify webhook signature in constant time against timing attacks."""
    expected_signature = compute_webhook_signature(timestamp, raw_body, secret)
    return hmac.compare_digest(provided_signature, expected_signature)
