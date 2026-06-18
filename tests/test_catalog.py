from datetime import datetime, timezone
from das_events.catalog import match_catalog


def _dt(s):
    return datetime(2025, 1, 4, 6, 45, s, tzinfo=timezone.utc)


CAT = [
    dict(time=_dt(20), mag=4.4, dist_km=105.0, event_id="us6000lgwr"),
    dict(time=_dt(50), mag=3.1, dist_km=300.0, event_id="us0000zzzz"),
]


def test_match_within_tolerance():
    dets = [dict(event_id="e1", t_peak=_dt(22))]
    out = match_catalog(dets, CAT, tol_seconds=5.0)
    assert "us6000lgwr" in out["e1"]
    assert "M4.4" in out["e1"]


def test_no_match_returns_empty_string():
    dets = [dict(event_id="e1", t_peak=_dt(35))]
    out = match_catalog(dets, CAT, tol_seconds=5.0)
    assert out["e1"] == ""
