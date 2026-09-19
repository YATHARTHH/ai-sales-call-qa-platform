"""Complete energy-retailer QA checklist, version 1.

This is the full checklist a retailer audit is run against, expressed as pure data so the seeder,
the integration tests, and the accuracy harness all score against one identical definition. Every
factual check names the authoritative CRM path its expected value is read from — no expectation is
ever embedded in the evaluator.

Regulatory references are recorded per check so a score can be defended in a retailer audit.
"""

from dataclasses import dataclass
from typing import Any

from packages.domain.check_library import CheckType, RuleType

# Segment keyword scopes, shared so related checks stay consistent.
_PEAK_RATE_KEYWORDS = ["peak rate", "peak usage", "peak is", "peak tariff", "peak charge"]
_SUPPLY_KEYWORDS = ["supply charge", "daily supply", "service to property", "cents per day"]
_EMAIL_KEYWORDS = ["email", "e-mail", "send you", "confirmation"]


@dataclass(frozen=True)
class ChecklistEntry:
    """One check definition plus the parameters of its initial effective version."""

    check_id: str
    check_code: str
    name: str
    check_type: CheckType
    is_critical: bool
    weight: int
    parameters: dict[str, Any]
    description: str = ""
    rule_type: RuleType = RuleType.LEGAL_REQUIREMENT
    regulatory_reference: str | None = None
    jurisdiction: str = "AU-VIC"
    # Applicability dimensions; None means unrestricted.
    fuel_types: list[str] | None = None
    customer_types: list[str] | None = None
    states: list[str] | None = None
    campaign_ids: list[str] | None = None


# ======================================================================================
# Tier A — Verbatim / script adherence
# ======================================================================================

_VERBATIM_CHECKS: list[ChecklistEntry] = [
    ChecklistEntry(
        check_id="chk-recording-disclaimer",
        check_code="VERBATIM_RECORDING_DISCLAIMER",
        name="Call Recording Disclosure",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent must disclose the call is recorded before collecting any information.",
        regulatory_reference="Privacy Act 1988 (Cth) APP 5; state surveillance devices legislation",
        parameters={
            "mandatory_concept_anchors": ["call", "recorded"],
            "required_phrases": [
                "This call is being recorded for training and quality assurance purposes."
            ],
            "must_occur_before_ms": 180000,
        },
    ),
    ChecklistEntry(
        check_id="chk-agent-identification",
        check_code="VERBATIM_AGENT_IDENTIFICATION",
        name="Agent and Company Identification",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=8,
        description="Agent states their name, the company they represent, and the purpose of the call.",
        regulatory_reference="National Energy Retail Rules r 63; ACMA Telemarketing Standard 2017",
        parameters={
            "mandatory_concept_anchors": ["my name is", "calling"],
            "required_phrases": [
                "My name is and I am calling on behalf of your energy comparison service."
            ],
            "similarity_threshold": 0.55,
        },
    ),
    ChecklistEntry(
        check_id="chk-account-holder",
        check_code="VERBATIM_ACCOUNT_HOLDER_AUTHORITY",
        name="Account Holder Authority Confirmed",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent confirms they are speaking to the account holder or an authorised representative.",
        regulatory_reference="National Energy Retail Law s 39 (explicit informed consent by the customer)",
        parameters={
            "mandatory_concept_anchors": ["account holder"],
            "required_phrases": [
                "Can I confirm that you are the account holder or authorised to make changes on this account?"
            ],
        },
    ),
    ChecklistEntry(
        check_id="chk-vdo-comparison",
        check_code="VERBATIM_VDO_COMPARISON",
        name="Victorian Default Offer Comparison Read",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent reads the plan's comparison against the Victorian Default Offer.",
        regulatory_reference="Energy Retail Code of Practice (Vic); Essential Services Commission VDO",
        jurisdiction="AU-VIC",
        states=["VIC"],
        parameters={
            "mandatory_concept_anchors": ["victorian default offer"],
            "required_phrases": [
                "Compared to the Victorian Default Offer, this plan is estimated to cost less over twelve months."
            ],
            "similarity_threshold": 0.55,
        },
    ),
    ChecklistEntry(
        check_id="chk-dmo-comparison",
        check_code="VERBATIM_DMO_COMPARISON",
        name="Default Market Offer Comparison Read",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent reads the plan's comparison against the DMO reference price.",
        regulatory_reference=(
            "Competition and Consumer (Industry Code—Electricity Retail) Regulations 2019; "
            "AER Retail Pricing Information Guidelines"
        ),
        jurisdiction="AU-NECF",
        states=["NSW", "SA", "QLD"],
        parameters={
            "mandatory_concept_anchors": ["reference price"],
            "required_phrases": [
                "Compared to the reference price set by the Australian Energy Regulator, this plan is estimated to cost less over twelve months."
            ],
            "similarity_threshold": 0.55,
        },
    ),
    ChecklistEntry(
        check_id="chk-explicit-consent",
        check_code="VERBATIM_EXPLICIT_INFORMED_CONSENT",
        name="Explicit Informed Consent (EIC)",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent obtains explicit informed consent to transfer the customer's energy account.",
        regulatory_reference="National Energy Retail Law s 39; National Energy Retail Rules r 38",
        parameters={
            "mandatory_concept_anchors": ["consent"],
            "required_phrases": [
                "Do you provide your explicit informed consent to proceed with this transfer?"
            ],
        },
    ),
    ChecklistEntry(
        check_id="chk-cooling-off",
        check_code="VERBATIM_COOLING_OFF_NOTICE",
        name="Cooling-off Period Notice",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent discloses the 10 business day cooling-off period and the right to cancel.",
        regulatory_reference="National Energy Retail Rules r 47",
        parameters={
            "mandatory_concept_anchors": ["cooling off"],
            "required_phrases": [
                "You have a 10 business day cooling off period during which you may cancel without penalty."
            ],
        },
    ),
    ChecklistEntry(
        check_id="chk-terms-conditions",
        check_code="VERBATIM_TERMS_AND_CONDITIONS",
        name="Terms, Conditions and Fact Sheet Disclosure",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=8,
        description="Agent advises the welcome pack, terms and conditions, and energy fact sheet will be sent.",
        regulatory_reference="National Energy Retail Rules r 46 (energy price fact sheet)",
        parameters={
            "mandatory_concept_anchors": ["terms and conditions"],
            "required_phrases": [
                "We will send you a welcome pack containing the full terms and conditions and the energy price fact sheet."
            ],
            "similarity_threshold": 0.55,
        },
    ),
    ChecklistEntry(
        check_id="chk-life-support-enquiry",
        check_code="VERBATIM_LIFE_SUPPORT_ENQUIRY",
        name="Life Support Equipment Enquiry",
        check_type=CheckType.VERBATIM,
        is_critical=True,
        weight=10,
        description="Agent asks whether anyone at the premises relies on life support equipment.",
        regulatory_reference="National Energy Retail Rules Part 7 (rr 124–131)",
        parameters={
            "mandatory_concept_anchors": ["life support"],
            "required_phrases": [
                "Does anyone at the premises rely on life support equipment?"
            ],
        },
    ),
    ChecklistEntry(
        check_id="chk-right-to-end-call",
        check_code="VERBATIM_RIGHT_TO_END_CALL",
        name="Customer Right to End Call Advised",
        check_type=CheckType.VERBATIM,
        is_critical=False,
        weight=4,
        description="Agent advises the customer may end the call at any time.",
        regulatory_reference="ACMA Telecommunications (Telemarketing and Research Calls) Industry Standard 2017",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={
            "mandatory_concept_anchors": ["end this call"],
            "required_phrases": ["You are free to end this call at any time."],
            "similarity_threshold": 0.55,
        },
    ),
]


# ======================================================================================
# Tier B — Factual match against CRM and the retailer rate card
# ======================================================================================

_FACTUAL_CHECKS: list[ChecklistEntry] = [
    ChecklistEntry(
        check_id="chk-peak-rate",
        check_code="FACTUAL_PEAK_RATE",
        name="Peak Usage Rate Matches Plan",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description="Peak c/kWh rate quoted on the call must equal the rate on the plan attached to the lead.",
        regulatory_reference="National Energy Retail Rules r 46; Australian Consumer Law s 18",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.tariff_peak_c_kwh",
            "tolerance": "0.00",
            "keywords": _PEAK_RATE_KEYWORDS,
            "min_value": "5",
            "max_value": "200",
        },
    ),
    ChecklistEntry(
        check_id="chk-supply-charge",
        check_code="FACTUAL_DAILY_SUPPLY_CHARGE",
        name="Daily Supply Charge Matches Plan",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description="Daily supply charge quoted must equal the charge on the plan attached to the lead.",
        regulatory_reference="National Energy Retail Rules r 46",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.daily_supply_charge_cents",
            "tolerance": "0.00",
            "keywords": _SUPPLY_KEYWORDS,
            "min_value": "20",
            "max_value": "400",
        },
    ),
    ChecklistEntry(
        check_id="chk-email",
        check_code="FACTUAL_EMAIL_ADDRESS",
        name="Customer Email Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description="Email read back on the call must exactly match the email stored against the lead.",
        regulatory_reference="National Energy Retail Rules r 46 (delivery of required documents)",
        parameters={
            "comparator": "EMAIL",
            "crm_fields": ["customer_email", "email"],
            "keywords": _EMAIL_KEYWORDS,
        },
    ),
    ChecklistEntry(
        check_id="chk-customer-name",
        check_code="FACTUAL_CUSTOMER_NAME",
        name="Customer Name Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="Account holder name confirmed on the call must match the lead record.",
        regulatory_reference="National Energy Retail Law s 39",
        parameters={
            "comparator": "TEXT",
            "crm_field": "customer_name",
            "keywords": ["name", "speaking", "account holder", "confirm"],
            "speaker": "ANY",
            "near_miss_threshold": 0.80,
        },
    ),
    ChecklistEntry(
        check_id="chk-dob",
        check_code="FACTUAL_DATE_OF_BIRTH",
        name="Date of Birth Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="Date of birth used for identity verification must match the lead record.",
        regulatory_reference="Privacy Act 1988 (Cth) APP 10 (quality of personal information)",
        parameters={
            "comparator": "DATE",
            "crm_fields": ["date_of_birth", "details.date_of_birth"],
            "question_keywords": ["date of birth", "born", "dob"],
            "response_window_ms": 30000,
        },
    ),
    ChecklistEntry(
        check_id="chk-supply-address",
        check_code="FACTUAL_SUPPLY_ADDRESS",
        name="Supply Address Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description="Supply address confirmed on the call must match the address on the lead.",
        regulatory_reference="National Energy Retail Rules r 38",
        parameters={
            "comparator": "TEXT",
            "crm_fields": ["supply_address", "details.supply_address"],
            "keywords": ["address", "street", "road", "supply", "property"],
            "near_miss_threshold": 0.80,
        },
    ),
    ChecklistEntry(
        check_id="chk-nmi",
        check_code="FACTUAL_NMI",
        name="NMI Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="National Metering Identifier read on the call must match the electricity lead record.",
        regulatory_reference="National Electricity Rules Chapter 7 (metering)",
        fuel_types=["ELECTRICITY", "DUAL"],
        parameters={
            "comparator": "IDENTIFIER",
            "crm_field": "details.nmi",
            "keywords": ["nmi", "metering identifier", "meter number"],
            "identifier_length": [10, 11],
        },
    ),
    ChecklistEntry(
        check_id="chk-mirn",
        check_code="FACTUAL_MIRN",
        name="MIRN Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="Meter Identification Registration Number read on the call must match the gas lead record.",
        regulatory_reference="National Gas Rules Part 15A",
        fuel_types=["GAS", "DUAL"],
        parameters={
            "comparator": "IDENTIFIER",
            "crm_field": "details.mirn",
            "keywords": ["mirn", "gas meter", "meter number"],
            "identifier_length": [10, 11],
        },
    ),
    ChecklistEntry(
        check_id="chk-fuel-type",
        check_code="FACTUAL_FUEL_TYPE",
        name="Fuel Type Matches Sale",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=6,
        description="Fuel type discussed on the call must match the fuel type recorded on the sale.",
        regulatory_reference="National Energy Retail Rules r 38",
        parameters={
            "comparator": "TEXT",
            "crm_field": "details.fuel_type",
            "keywords": ["electricity", "gas", "dual fuel", "both"],
            "near_miss_threshold": 0.75,
        },
    ),
    ChecklistEntry(
        check_id="chk-concession",
        check_code="FACTUAL_CONCESSION_STATUS",
        name="Concession Status Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=6,
        description="Concession eligibility confirmed by the customer must match the sale record.",
        regulatory_reference="State concession schemes; National Energy Retail Rules r 39",
        parameters={
            "comparator": "BOOLEAN",
            "crm_field": "details.concession_applied",
            "question_keywords": ["concession", "pension card", "health care card", "seniors card"],
            "response_window_ms": 30000,
        },
    ),
    ChecklistEntry(
        check_id="chk-life-support-flag",
        check_code="FACTUAL_LIFE_SUPPORT_STATUS",
        name="Life Support Status Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=10,
        description="Life support answer given by the customer must match the flag recorded on the sale.",
        regulatory_reference="National Energy Retail Rules Part 7 (rr 124–131)",
        parameters={
            "comparator": "BOOLEAN",
            "crm_field": "details.life_support",
            "question_keywords": ["life support", "medical equipment"],
            "response_window_ms": 30000,
        },
    ),
    ChecklistEntry(
        check_id="chk-move-in-date",
        check_code="FACTUAL_MOVE_IN_DATE",
        name="Move-in Date Matches CRM",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=6,
        description="Requested connection or move-in date must match the sale record.",
        regulatory_reference="National Energy Retail Rules r 38",
        parameters={
            "comparator": "DATE",
            "crm_fields": ["details.move_in_date", "move_in_date"],
            "keywords": ["move in", "moving", "connection date", "start date", "transfer date"],
            "speaker": "ANY",
        },
    ),
    ChecklistEntry(
        check_id="chk-gift-card",
        check_code="FACTUAL_GIFT_CARD_VALUE",
        name="Gift Card Value Matches Offer",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="Any incentive or gift card value promised must match the value on the sale.",
        regulatory_reference="Australian Consumer Law s 18 (misleading or deceptive conduct)",
        rule_type=RuleType.RETAILER_POLICY,
        parameters={
            "comparator": "MONEY",
            "crm_fields": ["details.gift_card_value", "gift_card_value"],
            "keywords": ["gift card", "voucher", "credit", "bonus", "incentive"],
            "min_value": "5",
            "max_value": "1000",
        },
    ),
    ChecklistEntry(
        check_id="chk-cooling-off-days",
        check_code="FACTUAL_COOLING_OFF_DAYS",
        name="Cooling-off Days Quoted Correctly",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=True,
        weight=8,
        description="Number of cooling-off business days quoted must match the sale record.",
        regulatory_reference="National Energy Retail Rules r 47",
        parameters={
            "comparator": "DECIMAL",
            "crm_field": "details.cooling_off_days",
            "tolerance": "0",
            "keywords": ["cooling off", "business day"],
            "min_value": "1",
            "max_value": "30",
        },
    ),
    ChecklistEntry(
        check_id="chk-plan-name",
        check_code="FACTUAL_PLAN_NAME",
        name="Plan Name Matches Sale",
        check_type=CheckType.FACTUAL_MATCH,
        is_critical=False,
        weight=4,
        description="Plan name stated on the call should match the plan attached to the sale.",
        rule_type=RuleType.RETAILER_POLICY,
        regulatory_reference="National Energy Retail Rules r 46",
        parameters={
            "comparator": "TEXT",
            "crm_field": "details.plan_name",
            "keywords": ["plan", "product", "offer"],
            "near_miss_threshold": 0.70,
        },
    ),
]


# ======================================================================================
# Tier C — Behaviour. Never blocks a sale; produces coaching signal only.
# ======================================================================================

_BEHAVIOUR_CHECKS: list[ChecklistEntry] = [
    ChecklistEntry(
        check_id="chk-dead-air",
        check_code="BEHAVIOUR_DEAD_AIR",
        name="Dead Air Within Threshold",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
        weight=4,
        description="No single silence gap should exceed the coaching threshold.",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={"metric": "DEAD_AIR", "max_silence_threshold_ms": 30000},
    ),
    ChecklistEntry(
        check_id="chk-interruptions",
        check_code="BEHAVIOUR_INTERRUPTIONS",
        name="Agent Interruptions Within Threshold",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
        weight=3,
        description="Agent should not talk over the customer more than the permitted number of times.",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={
            "metric": "INTERRUPTIONS",
            "max_interruptions": 3,
            "overlap_tolerance_ms": 300,
        },
    ),
    ChecklistEntry(
        check_id="chk-talk-ratio",
        check_code="BEHAVIOUR_TALK_RATIO",
        name="Agent Talk Ratio Within Range",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
        weight=3,
        description="Agent share of talk time should sit within the coaching band; a proxy for rapport.",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={"metric": "TALK_RATIO", "min_agent_ratio": 0.30, "max_agent_ratio": 0.90},
    ),
    ChecklistEntry(
        check_id="chk-objection-handling",
        check_code="BEHAVIOUR_OBJECTION_HANDLING",
        name="Objections Acknowledged",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
        weight=3,
        description="Every customer objection should be followed by an agent acknowledgement.",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={
            "metric": "OBJECTION_HANDLING",
            "objection_markers": [
                "not interested",
                "too expensive",
                "i don't want",
                "no thanks",
                "happy with",
                "think about it",
                "call me back",
                "how did you get my number",
            ],
            "acknowledgement_markers": [
                "i understand",
                "i appreciate",
                "that's fair",
                "absolutely",
                "of course",
                "no problem",
                "i hear you",
                "completely understand",
            ],
            "response_window_ms": 30000,
        },
    ),
    ChecklistEntry(
        check_id="chk-speech-rate",
        check_code="BEHAVIOUR_SPEECH_RATE",
        name="Agent Speech Rate Within Range",
        check_type=CheckType.BEHAVIOUR,
        is_critical=False,
        weight=3,
        description="Agent words per minute should stay within the intelligibility band.",
        rule_type=RuleType.INTERNAL_QA_STANDARD,
        parameters={"metric": "SPEECH_RATE", "min_wpm": 110, "max_wpm": 200},
    ),
]


ENERGY_RETAILER_CHECKLIST_V1: list[ChecklistEntry] = [
    *_VERBATIM_CHECKS,
    *_FACTUAL_CHECKS,
    *_BEHAVIOUR_CHECKS,
]


def checklist_by_code() -> dict[str, ChecklistEntry]:
    return {entry.check_code: entry for entry in ENERGY_RETAILER_CHECKLIST_V1}


def critical_check_ids() -> list[str]:
    return [entry.check_id for entry in ENERGY_RETAILER_CHECKLIST_V1 if entry.is_critical]
