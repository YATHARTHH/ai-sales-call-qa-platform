"""Reference check-library catalogues expressed as pure data."""

from packages.evaluation.checklists.broadband_retailer_v1 import (
    BROADBAND_RETAILER_CHECKLIST_V1,
)
from packages.evaluation.checklists.energy_retailer_v1 import (
    ENERGY_RETAILER_CHECKLIST_V1,
    ChecklistEntry,
)

__all__ = [
    "BROADBAND_RETAILER_CHECKLIST_V1",
    "ENERGY_RETAILER_CHECKLIST_V1",
    "ChecklistEntry",
]
