"""Unit tests for check applicability and resolution service."""

from datetime import UTC, datetime

import pytest

from packages.application.services.check_resolver import (
    CheckResolutionService,
    SaleContext,
    is_check_applicable,
)
from packages.domain.check_library import (
    CheckApplicability,
    CheckDefinition,
    CheckType,
    CheckVersion,
)
from packages.domain.exceptions import DomainError


def test_applicability_unrestricted_when_none():
    app = CheckApplicability()  # all None
    context = SaleContext(fuel_type="GAS", customer_type="RESIDENTIAL", state="VIC", campaign_id="CAMP-1")
    assert is_check_applicable(app, context) is True


def test_applicability_empty_list_raises_domain_error():
    with pytest.raises(DomainError, match="cannot be an empty list"):
        app = CheckApplicability(fuel_types=[])
        app.validate()


def test_applicability_allow_list_matching():
    app = CheckApplicability(fuel_types=["ELECTRICITY", "DUAL_FUEL"], states=["VIC"])

    # Matching
    ctx_match = SaleContext(fuel_type="ELECTRICITY", state="vic")
    assert is_check_applicable(app, ctx_match) is True

    # Non-matching fuel
    ctx_no_match = SaleContext(fuel_type="GAS", state="VIC")
    assert is_check_applicable(app, ctx_no_match) is False

    # Non-matching state
    ctx_no_state = SaleContext(fuel_type="ELECTRICITY", state="NSW")
    assert is_check_applicable(app, ctx_no_state) is False


def test_check_resolution_service_categorizes_applicable_and_skipped():
    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)

    elec_check = CheckDefinition(
        id="chk-elec",
        check_code="ELEC_RATE",
        name="Electricity Rate Check",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
    )
    gas_check = CheckDefinition(
        id="chk-gas",
        check_code="GAS_RATE",
        name="Gas Rate Check",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
    )

    v_elec = CheckVersion.create(
        check_id="chk-elec",
        retailer_id="ret-1",
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={"tolerance": 0.01},
        applicability=CheckApplicability(fuel_types=["ELECTRICITY"]),
    )
    v_gas = CheckVersion.create(
        check_id="chk-gas",
        retailer_id="ret-1",
        version_number=1,
        effective_from=now,
        effective_to=None,
        parameters_json={"tolerance": 0.01},
        applicability=CheckApplicability(fuel_types=["GAS"]),
    )

    context = SaleContext(fuel_type="ELECTRICITY", state="VIC")
    resolved_set = CheckResolutionService.resolve_checks_for_sale(
        check_definitions=[elec_check, gas_check],
        check_versions_by_id={"chk-elec": [v_elec], "chk-gas": [v_gas]},
        call_date=now,
        context=context,
    )

    assert len(resolved_set.applicable_checks) == 1
    assert resolved_set.applicable_checks[0].check_id == "chk-elec"
    assert len(resolved_set.skipped_checks) == 1
    assert resolved_set.skipped_checks[0].check_id == "chk-gas"
    assert resolved_set.skipped_checks[0].reason == "NOT_APPLICABLE"
