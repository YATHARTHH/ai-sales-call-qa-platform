"""Domain-level exception hierarchy."""


class DomainError(Exception):
    """Base domain exception."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class EntityNotFoundError(DomainError):
    """Raised when an entity cannot be found in the domain."""

    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            f"{entity_type} with ID '{entity_id}' not found.",
            code="ENTITY_NOT_FOUND",
        )
        self.entity_type = entity_type
        self.entity_id = entity_id


class StateTransitionError(DomainError):
    """Raised when an illegal state machine transition is attempted."""

    def __init__(self, current_state: str, target_state: str, context: str = ""):
        detail = f" for {context}" if context else ""
        super().__init__(
            f"Invalid state transition from '{current_state}' to '{target_state}'{detail}.",
            code="INVALID_STATE_TRANSITION",
        )
        self.current_state = current_state
        self.target_state = target_state


class ArtifactImmutableError(DomainError):
    """Raised when an attempt is made to mutate an immutable artifact."""

    def __init__(self, artifact_id: str):
        super().__init__(
            f"Artifact '{artifact_id}' is immutable and cannot be modified.",
            code="ARTIFACT_IMMUTABLE",
        )
        self.artifact_id = artifact_id


class IdempotencyConflictError(DomainError):
    """Raised when an operation conflicts with an existing idempotent execution."""

    def __init__(self, idempotency_key: str):
        super().__init__(
            f"Conflicting execution with idempotency key '{idempotency_key}'.",
            code="IDEMPOTENCY_CONFLICT",
        )
        self.idempotency_key = idempotency_key


class ArtifactIntegrityError(DomainError):
    """Raised when an audio or transcript artifact fails cryptographic or file integrity validation."""

    def __init__(self, message: str):
        super().__init__(message, code="ARTIFACT_INTEGRITY_ERROR")


class ProviderOutputValidationError(DomainError):
    """Raised when untrusted provider output fails schema, timing, or consistency checks."""

    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_OUTPUT_VALIDATION_ERROR")


class LeaseLostError(DomainError):
    """Raised when a worker attempts to commit or finalize a job whose lease ownership was lost."""

    def __init__(self, message: str):
        super().__init__(message, code="LEASE_LOST")

