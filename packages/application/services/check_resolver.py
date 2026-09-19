"""Service for resolving active check versions and evaluating check applicability."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from packages.domain.check_library import (
    CheckApplicability,
    CheckDefinition,
    CheckVersion,
    CheckVersionResolver,
)
from packages.domain.exceptions import DomainError


@dataclass(frozen=True)
class SaleContext:
    """Factual attributes of a sale used to evaluate check applicability."""

    fuel_type: str | None = None
    customer_type: str | None = None
    state: str | None = None
    campaign_id: str | None = None


@dataclass(frozen=True)
class ResolvedCheck:
    """An applicable check resolved for a specific sale execution."""

    check_id: str
    check_code: str
    name: str
    check_type: str
    is_critical: bool
    weight: int
    version_id: str
    version_number: int
    parameters: dict[str, Any]
    jurisdiction: str
    regulatory_reference: str | None
    rule_type: str

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_code": self.check_code,
            "name": self.name,
            "check_type": self.check_type,
            "is_critical": self.is_critical,
            "weight": self.weight,
            "version_id": self.version_id,
            "version_number": self.version_number,
            "parameters": self.parameters,
            "jurisdiction": self.jurisdiction,
            "regulatory_reference": self.regulatory_reference,
            "rule_type": self.rule_type,
        }


@dataclass(frozen=True)
class SkippedCheck:
    """A check that was evaluated but determined not applicable for this sale."""

    check_id: str
    check_code: str
    reason: str


@dataclass(frozen=True)
class ResolvedCheckSet:
    """The complete result of check version resolution and applicability evaluation."""

    applicable_checks: list[ResolvedCheck] = field(default_factory=list)
    skipped_checks: list[SkippedCheck] = field(default_factory=list)

    def to_snapshot_list(self) -> list[dict[str, Any]]:
        return [c.to_snapshot_dict() for c in self.applicable_checks]


def is_dimension_applicable(allowed: list[str] | None, actual: str | None) -> bool:
    """Evaluates applicability for a single dimension.

    - None: Unrestricted (applies to all sales)
    - Non-empty list: Allow-list matching actual value (case-insensitive)
    - Empty list: raises DomainError (invalid configuration)
    """
    if allowed is None:
        return True

    if len(allowed) == 0:
        raise DomainError(
            "Applicability list cannot be empty; use None for unrestricted.",
            code="INVALID_APPLICABILITY_CONFIGURATION",
        )

    if actual is None:
        return False

    normalized_allowed = {item.strip().upper() for item in allowed}
    return actual.strip().upper() in normalized_allowed


def is_check_applicable(applicability: CheckApplicability | None, context: SaleContext) -> bool:
    """Evaluates all dimensions of applicability for a check against sale context."""
    if applicability is None:
        return True

    applicability.validate()

    return (
        is_dimension_applicable(applicability.fuel_types, context.fuel_type)
        and is_dimension_applicable(applicability.customer_types, context.customer_type)
        and is_dimension_applicable(applicability.states, context.state)
        and is_dimension_applicable(applicability.campaign_ids, context.campaign_id)
    )


class CheckResolutionService:
    """Resolves active date-effective check versions and applies deterministic applicability."""

    @classmethod
    def resolve_checks_for_sale(
        cls,
        check_definitions: list[CheckDefinition],
        check_versions_by_id: dict[str, list[CheckVersion]],
        call_date: datetime,
        context: SaleContext,
    ) -> ResolvedCheckSet:
        applicable_checks: list[ResolvedCheck] = []
        skipped_checks: list[SkippedCheck] = []

        for definition in check_definitions:
            versions = check_versions_by_id.get(definition.id, [])
            if not versions:
                continue

            active_version = CheckVersionResolver.resolve(versions, call_date)

            if not is_check_applicable(active_version.applicability, context):
                skipped_checks.append(
                    SkippedCheck(
                        check_id=definition.id,
                        check_code=definition.check_code,
                        reason="NOT_APPLICABLE",
                    )
                )
                continue

            applicable_checks.append(
                ResolvedCheck(
                    check_id=definition.id,
                    check_code=definition.check_code,
                    name=definition.name,
                    check_type=definition.check_type.value,
                    is_critical=definition.is_critical,
                    weight=definition.default_weight,
                    version_id=active_version.id,
                    version_number=active_version.version_number,
                    parameters=active_version.parameters_json,
                    jurisdiction=active_version.jurisdiction,
                    regulatory_reference=active_version.regulatory_reference,
                    rule_type=active_version.rule_type.value,
                )
            )

        return ResolvedCheckSet(
            applicable_checks=applicable_checks,
            skipped_checks=skipped_checks,
        )
