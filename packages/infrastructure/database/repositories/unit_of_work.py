"""SQLAlchemy unit of work implementation coordinating domain repositories."""

from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import UnitOfWorkPort
from packages.infrastructure.database.repositories.artifact_repository import (
    SqlAlchemyArtifactRepository,
)
from packages.infrastructure.database.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from packages.infrastructure.database.repositories.job_repository import (
    SqlAlchemyJobRepository,
)
from packages.infrastructure.database.repositories.sale_repository import (
    SqlAlchemySaleRepository,
)
from packages.infrastructure.database.repositories.transcript_repository import (
    SqlAlchemyTranscriptRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWorkPort):
    """Atomic transactional boundary managing database transactions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.sales = SqlAlchemySaleRepository(session)
        self.transcripts = SqlAlchemyTranscriptRepository(session)
        self.artifacts = SqlAlchemyArtifactRepository(session)
        self.jobs = SqlAlchemyJobRepository(session)
        self.audit = SqlAlchemyAuditRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
