from datetime import datetime, timezone
from das_events.io import FileMeta
from das_events.select import select_files


def _fm(ts, name):
    return FileMeta(path=name, well="JJK", depth_m=80, gauge_length_m=8, dx_m=4,
                    raw_hz=5000, out_hz=100, start_time=ts)


def _dt(minute, second=0):
    return datetime(2025, 1, 4, 6, minute, second, tzinfo=timezone.utc)


FILES = [
    _fm(_dt(44), "f44.h5"),
    _fm(_dt(45), "f45.h5"),
    _fm(_dt(46), "f46.h5"),
]


def test_event_midfile_selects_only_its_file():
    dets = [dict(event_id="e1", t_start=_dt(45, 20), t_end=_dt(45, 25))]
    sel = select_files(dets, FILES, pad_seconds=5.0)
    assert set(sel) == {"f45.h5"}
    assert sel["f45.h5"] == ["e1"]


def test_event_near_edge_pulls_adjacent_file():
    dets = [dict(event_id="e2", t_start=_dt(45, 58), t_end=_dt(45, 59))]
    sel = select_files(dets, FILES, pad_seconds=30.0)
    assert set(sel) == {"f45.h5", "f46.h5"}


def test_event_near_start_pulls_previous_file():
    dets = [dict(event_id="e3", t_start=_dt(45, 2), t_end=_dt(45, 3))]
    sel = select_files(dets, FILES, pad_seconds=30.0)
    assert set(sel) == {"f44.h5", "f45.h5"}
