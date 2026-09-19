"""Unit tests for the Broadband / Telco QA checklist and builder integration."""

from datetime import UTC, datetime

from packages.domain.check_library import CheckType
from packages.evaluation.checklists import BROADBAND_RETAILER_CHECKLIST_V1
from packages.evaluation.checklists.builder import build_check_library


def test_broadband_checklist_structure() -> None:
    """Verify broadband checklist contains valid entries and correct types."""
    assert len(BROADBAND_RETAILER_CHECKLIST_V1) == 9

    codes = [e.check_code for e in BROADBAND_RETAILER_CHECKLIST_V1]
    assert "TELCO_VERBATIM_RECORDING_DISCLOSURE" in codes
    assert "TELCO_FACTUAL_NBN_SPEEDS" in codes
    assert "TELCO_BEHAVIOUR_PCI_MUTE" in codes
    assert "TELCO_VERBATIM_EIC_OTP" in codes


def test_build_broadband_check_library() -> None:
    """Verify building check library definitions and versions for telco retailer."""
    definitions, versions = build_check_library(
        entries=BROADBAND_RETAILER_CHECKLIST_V1,
        retailer_id="RET-TELCO-AU",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert len(definitions) == 9
    assert len(versions) == 9

    pci_check = next(d for d in definitions if d.check_code == "TELCO_BEHAVIOUR_PCI_MUTE")
    assert pci_check.is_critical is True
    assert pci_check.check_type == CheckType.BEHAVIOUR

    pci_vers = versions[pci_check.id][0]
    assert pci_vers.retailer_id == "RET-TELCO-AU"
    assert pci_vers.parameters_json["behaviour"] == "DEAD_AIR_BEFORE_PAYMENT"
