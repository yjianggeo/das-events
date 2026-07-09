"""Tests for the directory-level teleseismic surface-wave detector."""
from datetime import datetime

import pytest

from das_events.config import DetectConfig
from das_events.pipeline import scan_dir
from das_events.teleseism import _runs, scan_teleseism_dir
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(detector="teleseism", freqmin=1.0, freqmax=5.0,
                semblance_channel_decimation=1, edge_skip_seconds=3.0,
                teleseism_min_coherence=0.3, teleseism_min_run=3)
    base.update(kw)
    return DetectConfig(**base)


def _write_minute(d, minute, tone=None):
    ts = datetime(2026, 6, 16, 17, minute)
    name = f"JJK_80m_8m_4m_5000Hz_100Hz_UTC8_20260616{17:02d}{minute:02d}.h5"
    write_synth_h5(d / name, ts, n_time=6000, n_ch=20, fs=100.0,
                   coherent_tone_hz=(2.0 if tone else None), coherent_tone_amp=2.0)


def test_teleseism_detects_sustained_train(tmp_path):
    d = tmp_path / "sess"; d.mkdir()
    # minutes 10,11 quiet; 12,13,14 coherent train; 15 quiet
    for m in (10, 11):
        _write_minute(d, m, tone=False)
    for m in (12, 13, 14):
        _write_minute(d, m, tone=True)
    _write_minute(d, 15, tone=False)

    events = scan_dir(d, _cfg())
    assert len(events) == 1
    ev = events[0]
    assert ev.method == "teleseism"
    assert ev.semblance > 0.3
    # spans the 3-minute run (~3 files x 60 s)
    assert ev.duration_s > 100
    assert ev.dom_freq_hz < 5.0


def test_teleseism_rejects_isolated_coherent_minute(tmp_path):
    d = tmp_path / "sess"; d.mkdir()
    _write_minute(d, 10, tone=False)
    _write_minute(d, 11, tone=True)          # a single coherent minute
    _write_minute(d, 12, tone=False)
    assert scan_dir(d, _cfg()) == []          # run of 1 < min_run 3


def test_teleseism_quiet_session_returns_nothing(tmp_path):
    d = tmp_path / "sess"; d.mkdir()
    for m in (10, 11, 12, 13):
        _write_minute(d, m, tone=False)
    assert scan_dir(d, _cfg()) == []


def test_teleseism_min_run_two_allows_shorter_train(tmp_path):
    d = tmp_path / "sess"; d.mkdir()
    _write_minute(d, 10, tone=False)
    _write_minute(d, 11, tone=True)
    _write_minute(d, 12, tone=True)
    _write_minute(d, 13, tone=False)
    assert scan_dir(d, _cfg(teleseism_min_run=2))          # run of 2 accepted
    assert scan_dir(d, _cfg(teleseism_min_run=3)) == []    # ...but not at 3


def test_runs_helper_requires_contiguity():
    from datetime import timedelta
    t0 = datetime(2026, 6, 16, 17, 0)
    starts = [t0 + timedelta(minutes=i) for i in range(4)]
    # a 5-minute gap between file 1 and 2 breaks the run
    starts[2] = starts[1] + timedelta(minutes=5)
    starts[3] = starts[2] + timedelta(minutes=1)
    flags = [True, True, True, True]
    assert _runs(flags, starts, min_run=3) == []           # no 3 contiguous
    assert _runs(flags, starts, min_run=2) == [(0, 1), (2, 3)]


def test_config_rejects_bad_teleseism_params():
    with pytest.raises(ValueError):
        DetectConfig(teleseism_min_run=0)
    with pytest.raises(ValueError):
        DetectConfig(teleseism_min_coherence=0.0)
