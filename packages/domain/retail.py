"""Domain models for retail, campaigns, agents, leads, and sales."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from packages.domain.exceptions import DomainError


class FuelType(StrEnum):
    ELECTRICITY = "ELECTRICITY"
    GAS = "GAS"
    DUAL = "DUAL"


class SaleStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_QA = "PENDING_QA"
    APPROVED = "APPROVED"
    HELD = "HELD"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Retailer:
    id: str
    code: str
    name: str
    vertical: str = "ENERGY"
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Campaign:
    id: str
    code: str
    name: str
    channel: str = "INBOUND"  # INBOUND, AFFILIATE, OWNED_SITE, PAID_SEARCH
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Agent:
    id: str
    staff_id: str
    name: str
    email: str
    team_lead_id: str | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Lead:
    id: str
    customer_name: str
    customer_email: str
    phone: str
    suburb: str = ""
    state: str = ""
    postcode: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class EnergyProductDetails:
    """Typed product specification for Australian Energy sales."""

    plan_code: str
    plan_name: str
    fuel_type: FuelType
    tariff_peak_c_kwh: float
    daily_supply_charge_cents: float
    nmi: str | None = None  # National Metering Identifier (10-11 chars for electricity)
    mirn: str | None = None  # Meter Identification Registration Number (10-11 chars for gas)
    cooling_off_days: int = 10
    concession_applied: bool = False
    life_support: bool = False

    def validate(self) -> None:
        if self.fuel_type in (FuelType.ELECTRICITY, FuelType.DUAL):
            if not self.nmi or not re.match(r"^[A-Za-z0-9]{10,11}$", self.nmi):
                raise DomainError(f"Invalid Australian NMI format: {self.nmi}", code="INVALID_NMI")
        if self.fuel_type in (FuelType.GAS, FuelType.DUAL):
            if not self.mirn or not re.match(r"^[A-Za-z0-9]{10,11}$", self.mirn):
                raise DomainError(f"Invalid Australian MIRN format: {self.mirn}", code="INVALID_MIRN")
        if self.tariff_peak_c_kwh <= 0:
            raise DomainError("Tariff peak rate must be positive", code="INVALID_RATE")


@dataclass(frozen=True)
class Sale:
    """Generic commercial sale entity with decoupled product details."""

    id: str
    lead_id: str
    retailer_id: str
    campaign_id: str
    agent_id: str
    sale_date: datetime
    status: SaleStatus = SaleStatus.PENDING_QA
    product_details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        lead_id: str,
        retailer_id: str,
        campaign_id: str,
        agent_id: str,
        sale_date: datetime,
        product_details: dict[str, Any],
        sale_id: str | None = None,
    ) -> "Sale":
        return cls(
            id=sale_id or str(uuid.uuid4()),
            lead_id=lead_id,
            retailer_id=retailer_id,
            campaign_id=campaign_id,
            agent_id=agent_id,
            sale_date=sale_date,
            status=SaleStatus.PENDING_QA,
            product_details=product_details,
            created_at=datetime.now(UTC),
        )
