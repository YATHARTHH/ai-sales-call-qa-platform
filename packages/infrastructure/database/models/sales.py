"""SQLAlchemy models for retailers, campaigns, agents, leads, and sales."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.infrastructure.database.base import Base


class RetailerModel(Base):
    __tablename__ = "retailers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    vertical: Mapped[str] = mapped_column(String(64), default="ENERGY", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class CampaignModel(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), default="INBOUND", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    team_lead_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class LeadModel(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    suburb: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    postcode: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class SaleModel(Base):
    __tablename__ = "sales"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("leads.id"), nullable=False, index=True
    )
    retailer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("retailers.id"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agents.id"), nullable=False, index=True
    )
    sale_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING_QA", nullable=False, index=True
    )
    product_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    lead: Mapped[LeadModel] = relationship()
    retailer: Mapped[RetailerModel] = relationship()
    campaign: Mapped[CampaignModel] = relationship()
    agent: Mapped[AgentModel] = relationship()

    __table_args__ = (Index("ix_sales_retailer_date", "retailer_id", "sale_date"),)
