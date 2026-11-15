import pytest

from reglens.context import coverage, validate_metadata
from reglens.retrieve.search import Filters, Hit


def test_unknown_dates_are_not_reported_as_historical_certainty():
    h = Hit("x", "s", "r", None, "t", "L1", "v", 1)
    filters = Filters(as_of="2026-01-01", conditions={"approach": ["SA"]})
    assert coverage([h], filters)["temporal"] == "unknown"
    assert coverage([h], filters)["applicability"] == "unknown"
    h.temporal_verified = True
    h.applicability = {"approach": ["SA"]}
    assert coverage([h], filters)["temporal"] == "known"


def test_invalid_intervals_and_condition_shapes_are_rejected():
    with pytest.raises(ValueError):
        validate_metadata({"effective_from": "2027-01-01", "effective_until": "2026-01-01"})
    with pytest.raises(ValueError):
        validate_metadata({"temporal_verified": True})
    with pytest.raises(ValueError):
        Filters(conditions={"approach": "SA"})
