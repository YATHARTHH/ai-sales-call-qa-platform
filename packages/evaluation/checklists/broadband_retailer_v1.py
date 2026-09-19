"""Broadband / Telco QA checklist, version 1 — aligned to the Econnex NBN call.

Regulatory references:
- ACMA Telecommunications Consumer Protections (TCP) Code 2024
- ACCC Broadband Speed Guidelines (NBN Key Fact Sheet)
- PCI-DSS v4.0 Requirement 4.2 (card data on a recorded call)
- Australian Privacy Act 1988 (Cth) APP 5 (recording disclosure)
- Telecommunications (Consumer Protection and Service Standards) Act 1999

Every factual check names the authoritative CRM field path.  No expectation is
ever hardcoded in the evaluator; the engine reads from the sale snapshot.
"""

from packages.domain.check_library import CheckType, RuleType
from packages.evaluation.checklists.energy_retailer_v1 import ChecklistEntry

# Keyword scopes shared across related checks
_SPEED_KEYWORDS = ["mbps", "megabit", "download speed", "upload speed", "evening peak", "7pm", "11pm"]
_PRICE_KEYWORDS = ["dollars", "per month", "monthly", "charge", "fee", "plan", "price", "cost"]
_EIC_KEYWORDS = ["consent", "authorise", "authorize", "agree", "proceed", "confirm"]


# ======================================================================================
# BROADBAND_RETAILER_CHECKLIST_V1
# 9 checks covering the full Econnex / NBN 25/8.5 Mbps outbound sale
# ======================================================================================

BROADBAND_RETAILER_CHECKLIST_V1: list[ChecklistEntry] = [

    # ---- Tier A: Verbatim / Script Adherence ----------------------------------------

    ChecklistEntry(
        check_id="chk-telco-recording-disclosure",
        check_code="TELCO_VERBATIM_RECORDING_DISCLOSURE",
        name="Call Recording Disclosure (TCP Code)",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description=(
            "Agent must disclose at the start of the call that it is being recorded "
            "for quality assurance and/or training purposes, before collecting any PII."
        ),
        regulatory_reference="TCP Code 2024 cl 4.2; Privacy Act 1988 (Cth) APP 5",
        jurisdiction="AU",
        parameters={
            "mandatory_concept_anchors": ["recorded", "quality"],
            "required_phrases": [
                "Please be advised that this call will be recorded for quality assurance and training purposes."
            ],
            "similarity_threshold": 0.65,
            "must_occur_before_ms": 120000,  # within first 2 minutes
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-nbn-speeds",
        check_code="TELCO_FACTUAL_NBN_SPEEDS",
        name="NBN Evening Peak Speed Disclosure",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=12,
        description=(
            "Agent must verbally disclose the NBN Key Fact Sheet typical download and "
            "upload speeds during the evening busy period (7 pm–11 pm)."
        ),
        regulatory_reference="ACCC Broadband Performance Report; TCP Code cl 5.3; NBN Key Fact Sheet",
        jurisdiction="AU",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.download_mbps",
            "keywords": _SPEED_KEYWORDS,
            "min_value": "1",
            "max_value": "10000",
            "tolerance": "0.5",
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-promo-price",
        check_code="TELCO_FACTUAL_PROMO_PRICE",
        name="Promotional Monthly Price ($42.90 / 6 months)",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=12,
        description=(
            "Agent must state the correct promotional price for the introductory period "
            "before moving to the regular rate."
        ),
        regulatory_reference="TCP Code 2024 cl 5.4 (pricing disclosure); ACL s 18 (misleading conduct)",
        jurisdiction="AU",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.promo_price",
            "keywords": ["dollars", "forty", "42", "promo", "first", "month"],
            "min_value": "1",
            "max_value": "500",
            "tolerance": "0.05",
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-regular-price",
        check_code="TELCO_FACTUAL_REGULAR_PRICE",
        name="Regular Monthly Price after Promotion",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description=(
            "Agent must state the regular (post-promotion) monthly price so the customer "
            "understands ongoing cost."
        ),
        regulatory_reference="TCP Code 2024 cl 5.4; ACL s 18",
        jurisdiction="AU",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.regular_price",
            "keywords": ["regular", "then", "after", "seventy", "72", "going up"],
            "min_value": "1",
            "max_value": "500",
            "tolerance": "0.05",
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-minimum-total-cost",
        check_code="TELCO_FACTUAL_MINIMUM_TOTAL_COST",
        name="Total Minimum Cost / Contract Form Alignment",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description=(
            "The total minimum cost stated verbally must match the contract form (e.g. $317). "
            "A discrepancy between verbal and written total is a TCP Code breach."
        ),
        regulatory_reference="TCP Code 2024 cl 4.3 (minimum cost disclosure); ACL s 18",
        jurisdiction="AU",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.minimum_total_cost",
            "keywords": ["minimum", "total", "contract", "overall", "cost", "fee"],
            "min_value": "1",
            "max_value": "10000",
            "tolerance": "1.00",
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-pci-mute",
        check_code="TELCO_BEHAVIOUR_PCI_MUTE",
        name="PCI-DSS Payment Card Mute Protocol",
        check_type=CheckType.BEHAVIOUR,
        is_critical=True,
        weight=12,
        description=(
            "Recording must be paused/muted before the customer reads out card numbers. "
            "Any card data on a recording is a PCI-DSS breach."
        ),
        regulatory_reference="PCI-DSS v4.0 Requirement 4.2.1; TCP Code cl 8.1",
        jurisdiction="AU",
        parameters={
            "behaviour": "DEAD_AIR_BEFORE_PAYMENT",
            "dead_air_threshold_ms": 2000,
            "keywords": ["card", "payment", "credit", "debit", "mute", "hold"],
            "expect_silence_before_keyword": True,
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-eic-otp",
        check_code="TELCO_VERBATIM_EIC_OTP",
        name="Explicit Informed Consent & OTP Authorization",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=15,
        description=(
            "Customer must give explicit informed consent verbally, confirmed by OTP. "
            "Both the verbal consent and the OTP verification must be present."
        ),
        regulatory_reference=(
            "Telecommunications Act 1997 (Cth) s 276; TCP Code 2024 cl 4.4; "
            "Privacy Act 1988 (Cth) APP 3"
        ),
        jurisdiction="AU",
        parameters={
            "mandatory_concept_anchors": ["consent", "otp", "one-time", "verification"],
            "required_phrases": [
                "Do you provide your explicit informed consent to proceed with this transfer?"
            ],
            "similarity_threshold": 0.55,
            "speaker": "AGENT",
        },
    ),

    # ---- Tier A: Non-critical / advisory ----------------------------------------

    ChecklistEntry(
        check_id="chk-telco-hardware-modem",
        check_code="TELCO_FACTUAL_HARDWARE_MODEM",
        name="Hardware / Modem Inclusion Disclosure",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=False,
        weight=5,
        description=(
            "If a modem or router is included in the offer, agent must state this clearly "
            "so the customer does not purchase separately."
        ),
        regulatory_reference="ACL s 18 (misleading by omission); TCP Code cl 5.4",
        jurisdiction="AU",
        parameters={
            "comparator": "TEXT",
            "crm_field": "details.hardware_included",
            "keywords": ["modem", "router", "wifi", "wi-fi", "device", "equipment", "free"],
        },
    ),

    ChecklistEntry(
        check_id="chk-telco-script-accuracy",
        check_code="TELCO_VERBATIM_SCRIPT_ACCURACY",
        name="Promotional Duration Script Accuracy",
        check_type=CheckType.VERBATIM,
        is_critical=False,
        weight=5,
        description=(
            "Agent must state the correct promotional duration (e.g. '6 months', not '6 weeks'). "
            "A misstatement is a soft fail; a blatant misstatement may escalate to critical."
        ),
        regulatory_reference="TCP Code 2024 cl 5.4; ACL s 18",
        jurisdiction="AU",
        parameters={
            "mandatory_concept_anchors": ["month", "months"],
            "required_phrases": [
                "for the first six months"
            ],
            "similarity_threshold": 0.60,
            "ambiguous_threshold": 0.40,
        },
    ),
]
