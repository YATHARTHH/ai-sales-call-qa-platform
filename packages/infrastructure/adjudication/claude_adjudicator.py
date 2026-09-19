"""Claude-backed adjudicator for checks the deterministic evaluators left ambiguous.

Used only for the narrow band the rule engine cannot settle: a disclosure read in different words
than the script, a value the transcript garbled. The model is given the requirement and the
candidate transcript lines and must cite the line it relied on; it is never given authority over
the outcome. The deterministic policy engine applies the verdict under its own rules.

The response is constrained by a JSON schema, so the verdict is always a well-formed value from a
fixed set rather than free prose that has to be parsed.
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from packages.application.ports.adjudicator import (
    AdjudicationRequest,
    AdjudicationVerdict,
    AdjudicatorPort,
)
from packages.domain.exceptions import DomainError
from packages.infrastructure.adjudication.prompt import (
    ADJUDICATION_SYSTEM_PROMPT,
    build_adjudication_payload,
    build_verdict,
)
from packages.observability.logging import get_logger

logger = get_logger("adjudication.claude")

DEFAULT_MODEL = "claude-opus-5"


class _AdjudicationResponse(BaseModel):
    """Schema the model's response is constrained to."""

    verdict: str = Field(description="SATISFIED, NOT_SATISFIED, or CANNOT_DETERMINE")
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_segment_id: str | None = Field(
        default=None, description="segment_id of the line the verdict rests on, or null"
    )
    rationale: str = Field(description="One or two sentences citing the wording relied on")


class ProviderConfigurationError(DomainError):
    """Raised when the adjudication provider is not installed or configured."""

    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_CONFIGURATION_ERROR")


class ClaudeAdjudicator(AdjudicatorPort):
    """Adjudicates ambiguous findings with Claude, returning a structured verdict."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_tokens: int = 2048,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client: Any | None = None

    def provider_name(self) -> str:
        return f"anthropic:{self.model}"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The 'anthropic' package is not installed. Install with 'pip install .[llm]' "
                "or leave the adjudicator unconfigured to route ambiguity to a human."
            ) from exc

        kwargs: dict[str, Any] = {
            "timeout": self._timeout_seconds,
            "max_retries": self._max_retries,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationVerdict:
        """Propose a verdict. Any failure degrades to CANNOT_DETERMINE, never to a pass."""
        if not request.segments:
            return AdjudicationVerdict.undetermined("No candidate transcript lines supplied.")

        try:
            client = self._get_client()
        except ProviderConfigurationError as exc:
            logger.warning("adjudicator_unavailable", error=str(exc))
            return AdjudicationVerdict.undetermined(str(exc))

        try:
            response = client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=ADJUDICATION_SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": self._build_user_message(request)}],
                output_format=_AdjudicationResponse,
            )
            parsed = response.parsed_output
        except Exception as exc:
            # An adjudicator outage must never fail an evaluation or influence its outcome.
            logger.warning(
                "adjudication_failed", check_code=request.check_code, error=str(exc)
            )
            return AdjudicationVerdict.undetermined(f"Adjudication unavailable: {exc}")

        if parsed is None:
            return AdjudicationVerdict.undetermined("Adjudicator returned no parsable verdict.")

        return build_verdict(
            parsed=parsed.model_dump(),
            request=request,
            provider="anthropic",
            model=self.model,
            model_version=getattr(response, "model", self.model),
        )

    def _build_user_message(self, request: AdjudicationRequest) -> str:
        payload = json.dumps(build_adjudication_payload(request), indent=2, ensure_ascii=False)
        return (
            "Decide whether the transcript satisfies this single compliance requirement.\n\n"
            + payload
        )
