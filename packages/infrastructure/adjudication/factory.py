"""Builds the configured adjudicator and the policy that governs what it may change.

The default is no adjudicator at all: the engine stays fully deterministic and every ambiguous
finding routes to a human. A provider is opted into explicitly, and even then the policy below
still decides what its proposals are allowed to do.
"""

from packages.application.ports.adjudicator import AdjudicatorPort, NullAdjudicator
from packages.evaluation.policy.adjudication_policy import AdjudicationPolicy
from packages.infrastructure.config.settings import settings
from packages.observability.logging import get_logger

logger = get_logger("adjudication.factory")


def build_adjudicator(provider: str | None = None) -> AdjudicatorPort:
    """Build the adjudicator named by configuration.

    An unknown or unconfigured provider degrades to the null adjudicator rather than raising:
    losing a second opinion is safe (ambiguity goes to a human), so it must never take the
    pipeline down.
    """
    choice = (provider or settings.adjudicator_provider).strip().lower()

    if choice in ("claude", "anthropic"):
        from packages.infrastructure.adjudication.claude_adjudicator import (
            DEFAULT_MODEL,
            ClaudeAdjudicator,
        )

        logger.info("adjudicator_selected", provider="anthropic")
        return ClaudeAdjudicator(
            model=settings.adjudicator_model or DEFAULT_MODEL,
            api_key=settings.anthropic_api_key,
        )

    if choice in ("gemini", "google"):
        from packages.infrastructure.adjudication.gemini_adjudicator import (
            DEFAULT_MODEL,
            GeminiAdjudicator,
        )

        logger.info("adjudicator_selected", provider="google")
        return GeminiAdjudicator(
            model=settings.adjudicator_model or DEFAULT_MODEL,
            api_key=settings.gemini_api_key,
        )

    if choice not in ("none", ""):
        logger.warning("adjudicator_provider_unknown", provider=choice)

    return NullAdjudicator()


def build_adjudication_policy() -> AdjudicationPolicy:
    return AdjudicationPolicy(
        min_confidence=settings.adjudicator_min_confidence,
        allow_upgrade_to_pass_on_critical=settings.adjudicator_allow_critical_pass,
    )
