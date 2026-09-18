"""Domain models for checklist definitions, versioning, and temporal resolution."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from packages.domain.exceptions import DomainError


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class CheckType(StrEnum):
    VERBATIM = "VERBATIM"  # Script vs transcript verbatim match (disclaimer, DMO, T&Cs)
    FACTUAL_MATCH = (
        "FACTUAL_MATCH"  # Transcript vs CRM vs rate card (rates, email, NMI, concession)
    )
    BEHAVIOUR = "BEHAVIOUR"  # Non-blocking behavioral check (dead air, interruptions, rapport)


class VersionResolutionError(DomainError):
    """Raised when active check version cannot be unambiguously resolved."""

    def __init__(self, message: str):
        super().__init__(message, code="VERSION_RESOLUTION_ERROR")


@dataclass(frozen=True)
class CheckDefinition:
    id: str
    check_code: str
    name: str
    check_type: CheckType
    is_critical: bool
    default_weight: int = 10
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CheckVersion:
    """Historical version of a check rule with date-effective validity."""

    id: str
    check_id: str
    retailer_id: str
    version_number: int
    effective_from: datetime
    effective_to: datetime | None  # None indicates currently active indefinite version
    parameters_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        check_id: str,
        retailer_id: str,
        version_number: int,
        effective_from: datetime,
        effective_to: datetime | None,
        parameters_json: dict[str, Any],
        version_id: str | None = None,
    ) -> "CheckVersion":
        eff_from = _ensure_utc(effective_from)
        eff_to = _ensure_utc(effective_to)

        if eff_to and eff_to < eff_from:
            raise DomainError(
                f"effective_to ({eff_to}) cannot precede effective_from ({eff_from})",
                code="INVALID_EFFECTIVE_PERIOD",
            )
        return cls(
            id=version_id or str(uuid.uuid4()),
            check_id=check_id,
            retailer_id=retailer_id,
            version_number=version_number,
            effective_from=eff_from,
            effective_to=eff_to,
            parameters_json=parameters_json,
            created_at=datetime.now(UTC),
        )


class CheckVersionResolver:
    """Domain service resolving active CheckVersion on the date of the call."""

    @staticmethod
    def validate_non_overlapping(versions: list[CheckVersion]) -> None:
        """Ensure no two versions for the same check/retailer overlap in effective dates."""
        sorted_versions = sorted(versions, key=lambda v: _ensure_utc(v.effective_from))
        for i in range(len(sorted_versions) - 1):
            curr_v = sorted_versions[i]
            next_v = sorted_versions[i + 1]

            # If current version has no end date, next version cannot exist
            if curr_v.effective_to is None:
                raise VersionResolutionError(
                    f"Overlapping version found: Version {curr_v.version_number} has no end date but Version {next_v.version_number} starts at {next_v.effective_from}"
                )
            if _ensure_utc(curr_v.effective_to) >= _ensure_utc(next_v.effective_from):
                raise VersionResolutionError(
                    f"Overlapping effective period between Version {curr_v.version_number} (ends {curr_v.effective_to}) and Version {next_v.version_number} (starts {next_v.effective_from})"
                )

    @classmethod
    def resolve(
        cls,
        versions: list[CheckVersion],
        call_date: datetime,
    ) -> CheckVersion:
        """Resolve the single active check version for the call date."""
        cls.validate_non_overlapping(versions)
        target_date = _ensure_utc(call_date)

        matches = []
        for v in versions:
            v_from = _ensure_utc(v.effective_from)
            v_to = _ensure_utc(v.effective_to)
            if v_from <= target_date:
                if v_to is None or target_date <= v_to:
                    matches.append(v)

        if not matches:
            raise VersionResolutionError(
                f"No applicable CheckVersion found for call date {target_date.isoformat()}"
            )
        if len(matches) > 1:
            raise VersionResolutionError(
                f"Multiple ({len(matches)}) conflicting CheckVersions matched for call date {target_date.isoformat()}"
            )

        return matches[0]
