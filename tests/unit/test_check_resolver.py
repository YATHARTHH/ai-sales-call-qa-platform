"""Unit tests for CheckVersionResolver and temporal validity rules."""

from datetime import UTC, datetime, timedelta

import pytest

from packages.domain.check_library import (
    CheckVersion,
    CheckVersionResolver,
    VersionResolutionError,
)
from packages.domain.exceptions import DomainError


def test_check_version_effective_dates_validation():
    now = datetime.now(UTC)
    # effective_to preceding effective_from must raise DomainError
    with pytest.raises(DomainError) as exc:
        CheckVersion.create(
            check_id="chk-1",
            retailer_id="ret-1",
            version_number=1,
            effective_from=now,
            effective_to=now - timedelta(days=1),
            parameters_json={},
        )
    assert "cannot precede" in str(exc.value)


def test_resolve_active_version_single():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=None,
        parameters_json={"rule": "active"},
    )

    call_date = datetime(2026, 6, 1, tzinfo=UTC)
    resolved = CheckVersionResolver.resolve([v1], call_date)
    assert resolved.version_number == 1
    assert resolved.parameters_json == {"rule": "active"}


def test_resolve_active_version_multiple_chronological():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 6, 1, tzinfo=UTC)
    t2 = datetime(2026, 6, 2, tzinfo=UTC)

    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=t1,
        parameters_json={"rule": "v1"},
    )
    v2 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=2,
        effective_from=t2,
        effective_to=None,
        parameters_json={"rule": "v2"},
    )

    # Call on May 1 resolves to v1
    call_may = datetime(2026, 5, 1, tzinfo=UTC)
    assert CheckVersionResolver.resolve([v1, v2], call_may).version_number == 1

    # Call on boundary June 1 resolves to v1
    assert CheckVersionResolver.resolve([v1, v2], t1).version_number == 1

    # Call on July 1 resolves to v2
    call_july = datetime(2026, 7, 1, tzinfo=UTC)
    assert CheckVersionResolver.resolve([v1, v2], call_july).version_number == 2


def test_resolve_raises_if_call_date_before_any_version():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=None,
        parameters_json={},
    )

    call_before = datetime(2025, 12, 31, tzinfo=UTC)
    with pytest.raises(VersionResolutionError) as exc:
        CheckVersionResolver.resolve([v1], call_before)
    assert "No applicable CheckVersion found" in str(exc.value)


def test_resolve_raises_if_call_date_in_gap_or_after_ended_version():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 3, 1, tzinfo=UTC)
    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=t1,
        parameters_json={},
    )

    call_after = datetime(2026, 4, 1, tzinfo=UTC)
    with pytest.raises(VersionResolutionError):
        CheckVersionResolver.resolve([v1], call_after)


def test_resolve_rejects_overlapping_effective_windows():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 6, 1, tzinfo=UTC)
    t_overlap = datetime(2026, 5, 1, tzinfo=UTC)

    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=t1,
        parameters_json={},
    )
    # v2 starts before v1 ends
    v2 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=2,
        effective_from=t_overlap,
        effective_to=None,
        parameters_json={},
    )

    with pytest.raises(VersionResolutionError) as exc:
        CheckVersionResolver.resolve([v1, v2], datetime(2026, 5, 15, tzinfo=UTC))
    assert "Overlapping effective period" in str(exc.value)


def test_resolve_rejects_subsequent_version_when_prior_is_indefinite():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 6, 1, tzinfo=UTC)

    # v1 has no end date
    v1 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=1,
        effective_from=t0,
        effective_to=None,
        parameters_json={},
    )
    v2 = CheckVersion.create(
        check_id="chk-1",
        retailer_id="ret-1",
        version_number=2,
        effective_from=t1,
        effective_to=None,
        parameters_json={},
    )

    with pytest.raises(VersionResolutionError) as exc:
        CheckVersionResolver.resolve([v1, v2], datetime(2026, 7, 1, tzinfo=UTC))
    assert "has no end date but Version 2 starts" in str(exc.value)
