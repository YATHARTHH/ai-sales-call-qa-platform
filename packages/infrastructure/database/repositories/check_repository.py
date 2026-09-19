"""SQLAlchemy implementation of CheckLibraryRepositoryPort."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import CheckLibraryRepositoryPort
from packages.domain.check_library import (
    CheckApplicability,
    CheckDefinition,
    CheckType,
    CheckVersion,
    CheckVersionResolver,
    RuleType,
)
from packages.infrastructure.database.models.checks import (
    CheckDefinitionModel,
    CheckVersionModel,
)


def _to_domain_check_version(r: CheckVersionModel) -> CheckVersion:
    applicability = None
    if r.applicability_json:
        applicability = CheckApplicability(
            fuel_types=r.applicability_json.get("fuel_types"),
            customer_types=r.applicability_json.get("customer_types"),
            states=r.applicability_json.get("states"),
            campaign_ids=r.applicability_json.get("campaign_ids"),
        )
    return CheckVersion(
        id=r.id,
        check_id=r.check_id,
        retailer_id=r.retailer_id,
        version_number=r.version_number,
        effective_from=r.effective_from,
        effective_to=r.effective_to,
        parameters_json=r.parameters_json,
        jurisdiction=r.jurisdiction or "AU-VIC",
        regulatory_reference=r.regulatory_reference,
        rule_type=RuleType(r.rule_type) if r.rule_type else RuleType.LEGAL_REQUIREMENT,
        applicability=applicability,
        created_at=r.created_at,
    )


class SqlAlchemyCheckLibraryRepository(CheckLibraryRepositoryPort):
    """Persistence adapter for compliance checklist definitions and versions."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_check_definition(self, check: CheckDefinition) -> None:
        model = CheckDefinitionModel(
            id=check.id,
            check_code=check.check_code,
            name=check.name,
            check_type=check.check_type.value,
            is_critical=check.is_critical,
            default_weight=check.default_weight,
            description=check.description,
            created_at=check.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def save_check_version(self, version: CheckVersion) -> None:
        app_json = None
        if version.applicability:
            app_json = {
                "fuel_types": version.applicability.fuel_types,
                "customer_types": version.applicability.customer_types,
                "states": version.applicability.states,
                "campaign_ids": version.applicability.campaign_ids,
            }
        model = CheckVersionModel(
            id=version.id,
            check_id=version.check_id,
            retailer_id=version.retailer_id,
            version_number=version.version_number,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            parameters_json=version.parameters_json,
            jurisdiction=version.jurisdiction,
            regulatory_reference=version.regulatory_reference,
            rule_type=version.rule_type.value if hasattr(version.rule_type, "value") else str(version.rule_type),
            applicability_json=app_json,
            created_at=version.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_check_definitions(self) -> list[CheckDefinition]:
        stmt = select(CheckDefinitionModel).order_by(CheckDefinitionModel.check_code.asc())
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            CheckDefinition(
                id=r.id,
                check_code=r.check_code,
                name=r.name,
                check_type=CheckType(r.check_type),
                is_critical=r.is_critical,
                default_weight=r.default_weight,
                description=r.description or "",
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def get_check_versions(self, retailer_id: str, check_code: str) -> list[CheckVersion]:
        stmt = (
            select(CheckVersionModel)
            .join(CheckDefinitionModel, CheckVersionModel.check_id == CheckDefinitionModel.id)
            .where(
                CheckVersionModel.retailer_id == retailer_id,
                CheckDefinitionModel.check_code == check_code,
            )
            .order_by(CheckVersionModel.version_number.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [_to_domain_check_version(r) for r in rows]

    async def get_all_check_versions_by_check_id(
        self, retailer_id: str | None = None
    ) -> dict[str, list[CheckVersion]]:
        stmt = select(CheckVersionModel).order_by(CheckVersionModel.version_number.asc())
        if retailer_id:
            stmt = stmt.where(CheckVersionModel.retailer_id == retailer_id)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        grouped: dict[str, list[CheckVersion]] = defaultdict(list)
        for r in rows:
            grouped[r.check_id].append(_to_domain_check_version(r))
        return grouped

    async def get_retailer_checklist(
        self, retailer_id: str, call_date: datetime
    ) -> list[CheckVersion]:
        """Resolve all active check versions for a retailer on the call date."""
        grouped = await self.get_all_check_versions_by_check_id(retailer_id)
        active_checklist: list[CheckVersion] = []
        for _check_id, versions in grouped.items():
            active_version = CheckVersionResolver.resolve(versions, call_date)
            active_checklist.append(active_version)

        return active_checklist
