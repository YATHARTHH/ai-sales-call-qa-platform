"""Unit tests for EnergyProductDetails and Sale domain entities."""

from datetime import UTC, datetime

import pytest

from packages.domain.exceptions import DomainError
from packages.domain.retail import (
    EnergyProductDetails,
    FuelType,
    Sale,
    SaleStatus,
)


def test_energy_product_details_valid_electricity():
    details = EnergyProductDetails(
        plan_code="ELEC_STD_2026",
        plan_name="Standard Electricity",
        fuel_type=FuelType.ELECTRICITY,
        tariff_peak_c_kwh=31.9,
        daily_supply_charge_cents=115.5,
        nmi="6102123456",
    )
    details.validate()
    assert details.nmi == "6102123456"
    assert details.tariff_peak_c_kwh == 31.9


def test_energy_product_details_valid_gas():
    details = EnergyProductDetails(
        plan_code="GAS_STD_2026",
        plan_name="Standard Gas",
        fuel_type=FuelType.GAS,
        tariff_peak_c_kwh=4.5,
        daily_supply_charge_cents=85.0,
        mirn="5310123456",
    )
    details.validate()
    assert details.mirn == "5310123456"


def test_energy_product_details_rejects_missing_or_invalid_nmi():
    with pytest.raises(DomainError) as exc:
        EnergyProductDetails(
            plan_code="ELEC_STD_2026",
            plan_name="Standard Electricity",
            fuel_type=FuelType.ELECTRICITY,
            tariff_peak_c_kwh=31.9,
            daily_supply_charge_cents=115.5,
            nmi="INVALID-NMI!",
        ).validate()
    assert "Invalid Australian NMI format" in str(exc.value)


def test_energy_product_details_rejects_invalid_mirn():
    with pytest.raises(DomainError) as exc:
        EnergyProductDetails(
            plan_code="GAS_STD_2026",
            plan_name="Standard Gas",
            fuel_type=FuelType.GAS,
            tariff_peak_c_kwh=4.5,
            daily_supply_charge_cents=85.0,
            mirn="123",  # Too short
        ).validate()
    assert "Invalid Australian MIRN format" in str(exc.value)


def test_energy_product_details_rejects_non_positive_rates():
    with pytest.raises(DomainError) as exc:
        EnergyProductDetails(
            plan_code="ELEC_STD_2026",
            plan_name="Standard Electricity",
            fuel_type=FuelType.ELECTRICITY,
            tariff_peak_c_kwh=0.0,
            daily_supply_charge_cents=115.5,
            nmi="6102123456",
        ).validate()
    assert "Tariff peak rate must be positive" in str(exc.value)


def test_sale_creation_factory_defaults():
    sale = Sale.create(
        lead_id="lead-123",
        retailer_id="ret-1",
        campaign_id="camp-1",
        agent_id="agent-1",
        sale_date=datetime.now(UTC),
        product_details={"plan": "Basic"},
    )
    assert sale.status == SaleStatus.PENDING_QA
    assert sale.lead_id == "lead-123"
    assert sale.product_details["plan"] == "Basic"
    assert sale.id is not None
