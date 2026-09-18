"""SQLAlchemy implementation of CheckLibraryRepositoryPort."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import CheckLibraryRepositoryPort
from packages.domain.check_library import (
    CheckDefinition,
    CheckVersion,
    CheckVersionResolver,
)
from packages.infrastructure.database.models.checks import (
    CheckDefinitionModel,
    CheckVersionModel,
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
        model = CheckVersionModel(
            id=version.id,
            check_id=version.check_id,
            retailer_id=version.retailer_id,
            version_number=version.version_number,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            parameters_json=version.parameters_json,
            created_at=version.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

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
        return [
            CheckVersion(
                id=r.id,
                check_id=r.check_id,
                retailer_id=r.retailer_id,
                version_number=r.version_number,
                effective_from=r.effective_from,
                effective_to=r.effective_to,
                parameters_json=r.parameters_json,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def get_retailer_checklist(
        self, retailer_id: str, call_date: datetime
    ) -> list[CheckVersion]:
        """Resolve all active check versions for a retailer on the call date."""
        stmt = (
            select(CheckVersionModel)
            .where(CheckVersionModel.retailer_id == retailer_id)
            .order_by(CheckVersionModel.version_number.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        # Group by check_id
        grouped: dict[str, list[CheckVersion]] = defaultdict(list)
        for r in rows:
            grouped[r.check_id].append(
                CheckVersion(
                    id=r.id,
                    check_id=r.check_id,
                    retailer_id=r.retailer_id,
                    version_number=r.version_number,
                    effective_from=r.effective_from,
                    effective_to=r.effective_to,
                    parameters_json=r.parameters_json,
                    created_at=r.created_at,
                )
            )

        active_checklist: list[CheckVersion] = []
        for _check_id, versions in grouped.items():
            active_version = CheckVersionResolver.resolve(versions, call_date)
            active_checklist.append(active_version)

        return active_checklist
