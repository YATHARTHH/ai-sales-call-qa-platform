"""Turns a declarative checklist catalogue into domain check definitions and versions."""

from collections.abc import Sequence
from datetime import UTC, datetime

from packages.domain.check_library import (
    CheckApplicability,
    CheckDefinition,
    CheckVersion,
)
from packages.evaluation.checklists.energy_retailer_v1 import ChecklistEntry

DEFAULT_EFFECTIVE_FROM = datetime(2026, 1, 1, tzinfo=UTC)


def build_check_library(
    entries: Sequence[ChecklistEntry],
    retailer_id: str,
    effective_from: datetime = DEFAULT_EFFECTIVE_FROM,
    version_number: int = 1,
) -> tuple[list[CheckDefinition], dict[str, list[CheckVersion]]]:
    """Build the definitions and date-effective versions for one retailer's checklist.

    Version ids are derived from the check id and retailer so a rebuild is stable; an evaluation
    replayed later resolves to the same version identifier it recorded originally.
    """
    definitions: list[CheckDefinition] = []
    versions_by_id: dict[str, list[CheckVersion]] = {}

    for entry in entries:
        definitions.append(
            CheckDefinition(
                id=entry.check_id,
                check_code=entry.check_code,
                name=entry.name,
                check_type=entry.check_type,
                is_critical=entry.is_critical,
                default_weight=entry.weight,
                description=entry.description,
            )
        )

        applicability = None
        if any(
            (entry.fuel_types, entry.customer_types, entry.states, entry.campaign_ids)
        ):
            applicability = CheckApplicability(
                fuel_types=entry.fuel_types,
                customer_types=entry.customer_types,
                states=entry.states,
                campaign_ids=entry.campaign_ids,
            )

        versions_by_id[entry.check_id] = [
            CheckVersion.create(
                check_id=entry.check_id,
                retailer_id=retailer_id,
                version_number=version_number,
                effective_from=effective_from,
                effective_to=None,
                parameters_json=dict(entry.parameters),
                jurisdiction=entry.jurisdiction,
                regulatory_reference=entry.regulatory_reference,
                rule_type=entry.rule_type,
                applicability=applicability,
                version_id=f"{entry.check_id}-{retailer_id}-v{version_number}",
            )
        ]

    return definitions, versions_by_id
