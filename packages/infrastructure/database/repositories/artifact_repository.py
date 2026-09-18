"""SQLAlchemy implementation of ArtifactRepositoryPort."""

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import ArtifactRepositoryPort
from packages.domain.artifacts import Artifact
from packages.infrastructure.database.models.artifacts import ArtifactModel


class SqlAlchemyArtifactRepository(ArtifactRepositoryPort):
    """Persistence adapter for immutable content-hashed audio artifacts."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, artifact_id: str) -> Artifact | None:
        stmt = select(ArtifactModel).where(ArtifactModel.id == artifact_id)
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return Artifact(
            id=model.id,
            lead_id=model.lead_id,
            storage_key=model.storage_key,
            content_hash=model.content_hash,
            content_type=model.content_type,
            size_bytes=model.size_bytes,
            duration_seconds=model.duration_seconds,
            created_at=model.created_at,
            metadata=dict(model.metadata_json or {}),
        )

    async def get_by_content_hash(self, content_hash: str) -> Artifact | None:
        stmt = select(ArtifactModel).where(ArtifactModel.content_hash == content_hash)
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return Artifact(
            id=model.id,
            lead_id=model.lead_id,
            storage_key=model.storage_key,
            content_hash=model.content_hash,
            content_type=model.content_type,
            size_bytes=model.size_bytes,
            duration_seconds=model.duration_seconds,
            created_at=model.created_at,
            metadata=dict(model.metadata_json or {}),
        )

    async def save_artifact_idempotent(self, artifact: Artifact) -> tuple[Artifact, bool]:
        """Persist artifact, returning existing one on content_hash uniqueness conflict."""
        existing = await self.get_by_content_hash(artifact.content_hash)
        if existing:
            return existing, False

        model = ArtifactModel(
            id=artifact.id,
            lead_id=artifact.lead_id,
            storage_key=artifact.storage_key,
            content_hash=artifact.content_hash,
            content_type=artifact.content_type,
            size_bytes=artifact.size_bytes,
            duration_seconds=artifact.duration_seconds,
            metadata_json=artifact.metadata,
            created_at=artifact.created_at,
        )

        is_inserted = False
        async with self._session.begin_nested():
            try:
                self._session.add(model)
                await self._session.flush()
                is_inserted = True
            except IntegrityError:
                pass

        if is_inserted:
            return artifact, True

        winner = await self.get_by_content_hash(artifact.content_hash)
        if winner is None:
            for _ in range(30):
                await asyncio.sleep(0.05)
                winner = await self.get_by_content_hash(artifact.content_hash)
                if winner is not None:
                    break
        if winner is not None:
            return winner, False
        raise RuntimeError("Failed to resolve artifact on content_hash conflict")
