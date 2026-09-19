"""SQLAlchemy models for compliance check definitions and date-effective versions."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.infrastructure.database.base import Base

if TYPE_CHECKING:
    from packages.infrastructure.database.models.sales import RetailerModel


class CheckDefinitionModel(Base):
    __tablename__ = "check_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    check_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_weight: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    versions: Mapped[list["CheckVersionModel"]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class CheckVersionModel(Base):
    __tablename__ = "check_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    check_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("check_definitions.id"), nullable=False, index=True
    )
    retailer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("retailers.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(32), default="AU-VIC", nullable=False)
    regulatory_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(32), default="LEGAL_REQUIREMENT", nullable=False)
    applicability_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    check: Mapped[CheckDefinitionModel] = relationship(back_populates="versions")
    retailer: Mapped["RetailerModel"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "check_id", "retailer_id", "version_number", name="uq_check_retailer_version_number"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_check_version_effective_dates",
        ),
        CheckConstraint("version_number > 0", name="ck_check_version_number_positive"),
        Index(
            "ix_check_versions_lookup", "retailer_id", "check_id", "effective_from", "effective_to"
        ),
    )
