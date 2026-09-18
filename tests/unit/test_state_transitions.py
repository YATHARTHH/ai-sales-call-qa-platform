"""Tests for PipelineStatus and GateStatus state transition policies."""

import pytest

from packages.domain.exceptions import StateTransitionError
from packages.domain.state import GateStatus, PipelineStatus, StateTransitionPolicy


def test_pipeline_valid_transitions():
    """Valid pipeline flow must pass without error."""
    StateTransitionPolicy.validate_pipeline_transition(
        PipelineStatus.RECEIVED, PipelineStatus.INGESTING
    )
    StateTransitionPolicy.validate_pipeline_transition(
        PipelineStatus.INGESTING, PipelineStatus.TRANSCRIBING
    )
    StateTransitionPolicy.validate_pipeline_transition(
        PipelineStatus.TRANSCRIBING, PipelineStatus.TRANSCRIBED
    )
    StateTransitionPolicy.validate_pipeline_transition(
        PipelineStatus.TRANSCRIBED, PipelineStatus.EVALUATING
    )
    StateTransitionPolicy.validate_pipeline_transition(
        PipelineStatus.EVALUATING, PipelineStatus.EVALUATED
    )


def test_pipeline_illegal_jumps_rejected():
    """Jumping straight from RECEIVED to EVALUATED must be rejected."""
    with pytest.raises(StateTransitionError) as exc_info:
        StateTransitionPolicy.validate_pipeline_transition(
            PipelineStatus.RECEIVED, PipelineStatus.EVALUATED
        )
    assert exc_info.value.code == "INVALID_STATE_TRANSITION"


def test_gate_valid_and_invalid_transitions():
    """GateStatus must govern compliance outcomes and block unauthorized bypass."""
    # Allowed: PENDING -> HELD
    StateTransitionPolicy.validate_gate_transition(
        GateStatus.PENDING, GateStatus.HELD
    )
    # Allowed: HELD -> PASSED (Team Lead override)
    StateTransitionPolicy.validate_gate_transition(
        GateStatus.HELD, GateStatus.PASSED
    )

    # Illegal: PASSED cannot transition back to HELD
    with pytest.raises(StateTransitionError):
        StateTransitionPolicy.validate_gate_transition(
            GateStatus.PASSED, GateStatus.HELD
        )
