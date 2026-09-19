"""Gemini-backed adjudicator for checks the deterministic evaluators left ambiguous.

Interchangeable with the Claude adjudicator: same port, same structured verdict, and the same
deterministic policy applied to whatever it proposes. The response is constrained by a JSON schema
so the verdict is always a value from a fixed set rather than prose to be parsed.
"""

import json
from typing import Any

from packages.application.ports.adjudicator import (
    AdjudicationRequest,
    AdjudicationVerdict,
    AdjudicationVerdictType,
    AdjudicatorPort,
)
from packages.domain.exceptions import DomainError
from packages.infrastructure.adjudication.prompt import (
    ADJUDICATION_SYSTEM_PROMPT,
    build_adjudication_payload,
    build_verdict,
)
from packages.observability.logging import get_logger

logger = get_logger("adjudication.gemini")

DEFAULT_MODEL = "gemini-2.5-pro"

# Mirrors the Claude adapter's schema so both providers return the same shape.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["SATISFIED", "NOT_SATISFIED", "CANNOT_DETERMINE"],
        },
        "confidence": {"type": "number"},
        "supporting_segment_id": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["verdict", "confidence", "rationale"],
}


class ProviderConfigurationError(DomainError):
    """Raised when the adjudication provider is not installed or configured."""

    def __init__(self, message: str):
        super().__init__(message, code="PROVIDER_CONFIGURATION_ERROR")


class GeminiAdjudicator(AdjudicatorPort):
    """Adjudicates ambiguous findings with Gemini, returning a structured verdict."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = 0.0,
    ):
        self.model = model
        self._api_key = api_key
        self._temperature = temperature
        self._client: Any | None = None

    def provider_name(self) -> str:
        return f"google:{self.model}"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The 'google-genai' package is not installed. Install with 'pip install .[gemini]' "
                "or leave the adjudicator unconfigured to route ambiguity to a human."
            ) from exc

        self._client = genai.Client(api_key=self._api_key) if self._api_key else genai.Client()
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
            response = client.models.generate_content(
                model=self.model,
                contents=json.dumps(build_adjudication_payload(request), indent=2),
                config={
                    "system_instruction": ADJUDICATION_SYSTEM_PROMPT,
                    "temperature": self._temperature,
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                },
            )
            parsed = json.loads(response.text)
        except Exception as exc:
            # An adjudicator outage must never fail an evaluation or influence its outcome.
            logger.warning(
                "adjudication_failed", check_code=request.check_code, error=str(exc)
            )
            return AdjudicationVerdict.undetermined(f"Adjudication unavailable: {exc}")

        return build_verdict(
            parsed=parsed,
            request=request,
            provider="google",
            model=self.model,
            model_version=self.model,
        )
