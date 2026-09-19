"""Exceptions for outbox processing, claiming, and dispatching."""


class OutboxError(Exception):
    """Base exception for outbox processing errors."""


class LeaseExpiredError(OutboxError):
    """Raised when an outbox claim lease has expired before completion."""


class PermanentDeliveryError(OutboxError):
    """Raised when delivery fails with a non-retryable fatal error (e.g. 400 Bad Request, 422)."""


class TransientDeliveryError(OutboxError):
    """Raised when delivery fails with a transient retryable error (e.g. timeout, 5xx, 429)."""
