import numpy as np
from das_events.detect import bandpass_channel, characteristic_function


def test_bandpass_removes_dc():
    fs = 100.0
    x = np.ones(1000) + np.sin(2 * np.pi * 10 * np.arange(1000) / fs)
    y = bandpass_channel(x, fs, 1.0, 40.0)
    assert abs(y.mean()) < 0.05          # DC removed
    assert y.std() > 0.3                  # 10 Hz tone preserved


def test_cf_rises_at_transient():
    fs = 100.0
    n = 2000
    x = np.random.default_rng(0).normal(0, 0.02, n)
    t = np.arange(-60, 60)
    x[900:900 + 120] += 5 * np.exp(-(t / 18.0) ** 2) * np.sin(2 * np.pi * 10 * t / fs)
    cf = characteristic_function(x, fs, sta=0.5, lta=10.0)
    assert cf.shape == (n,)
    assert cf[900:1100].max() > cf[200:700].max() * 2   # clear rise at the event


from datetime import datetime
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(freqmin=1.0, freqmax=40.0, sta_seconds=0.2, lta_seconds=2.0,
                thr_on=3.0, min_coincidence=4, min_duration_seconds=0.1,
                merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_detect_finds_injected_event(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    dets = detect_file(das, _cfg())
    assert len(dets) == 1
    d = dets[0]
    assert abs((d.t_peak.timestamp() - das.time_at(1200).timestamp())) < 2.0
    assert d.peak_coincidence >= 4
    assert len(d.channel_indices) >= 4


def test_detect_quiet_file_returns_nothing(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040646.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 46), n_time=2000, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert detect_file(das, _cfg()) == []


def test_detect_rejects_single_channel_glitch(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040647.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 47), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1200, event_channels=[5])
    das = read_h5(p)
    assert detect_file(das, _cfg(min_coincidence=4)) == []


# ── regression tests added after code review ────────────────────────────────
import numpy as _np
import pytest as _pytest
from das_events.detect import _group_runs
from das_events.config import DetectConfig


def test_group_runs_gap_boundary():
    # max_gap=2: a gap of exactly 2 inactive samples merges; 3 splits.
    a = _np.array([1, 0, 0, 1, 0, 0, 0, 1], dtype=bool)
    # gap of 2 (idx 0->3) merges; gap of 3 (idx 3->7) splits off the last run
    assert _group_runs(a, max_gap=2) == [(0, 4), (7, 8)]
    assert _group_runs(a, max_gap=1) == [(0, 1), (3, 4), (7, 8)]


def test_group_runs_empty_and_single():
    assert _group_runs(_np.zeros(5, dtype=bool), max_gap=1) == []
    assert _group_runs(_np.array([0, 1, 0], dtype=bool), max_gap=1) == [(1, 2)]


def test_detect_rejects_short_event(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040648.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 48), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    # require an implausibly long duration -> the short wavelet is rejected
    assert detect_file(das, _cfg(min_duration_seconds=5.0)) == []


def test_detect_merges_close_events(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040649.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 49), n_time=3000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20),
                   second_event_sample=1260)  # 0.6 s apart
    das = read_h5(p)
    # large merge gap collapses the two arrivals into one detection
    assert len(detect_file(das, _cfg(merge_gap_seconds=5.0))) == 1


def test_config_rejects_bad_min_coincidence():
    with _pytest.raises(ValueError):
        DetectConfig(min_coincidence=0)


def test_config_rejects_bad_decimation():
    with _pytest.raises(ValueError):
        DetectConfig(channel_decimation=0)


def test_detect_skips_edge_transient(tmp_path):
    # an event inside the edge guard (near the file end) is suppressed
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040650.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 50), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1940, event_channels=range(20))
    das = read_h5(p)
    # 100 Hz, edge_skip 1.5 s -> last 150 samples (1850..2000) suppressed,
    # covering the whole wavelet at 1880..2000
    assert detect_file(das, _cfg(edge_skip_seconds=1.5)) == []
    # with no edge guard the same event is found
    assert len(detect_file(das, _cfg(edge_skip_seconds=0.0))) == 1
