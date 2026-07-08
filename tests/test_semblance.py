"""Tests for the semblance backend, depth-based channel selection, and merge."""
from datetime import datetime

import numpy as np
import pytest

from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import (
    detect_file, detect_semblance, resolve_channel_range, _merge_detections,
    Detection,
)
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(
        detector="semblance", freqmin=2.0, freqmax=40.0,
        min_duration_seconds=0.1, merge_gap_seconds=0.5, edge_skip_seconds=0.3,
        semblance_thr=0.15, semblance_win_seconds=0.5,
        semblance_channel_decimation=1, semblance_n_slowness=9,
        semblance_slowness_max=2e-3,
    )
    base.update(kw)
    return DetectConfig(**base)


def test_semblance_detects_coherent_event(tmp_path):
    # A wavefront aligned across all channels is maximally coherent.
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=3000, n_ch=100, fs=100.0,
                   event_sample=1500, event_channels=range(100), event_amp=3.0)
    das = read_h5(p)
    dets = detect_file(das, _cfg())
    assert len(dets) >= 1
    d = max(dets, key=lambda x: x.semblance)
    assert d.method == "semblance"
    assert d.semblance > _cfg().semblance_thr
    assert d.peak_ratio == 0.0                     # STA/LTA did not run
    assert abs(d.t_peak.timestamp() - das.time_at(1500).timestamp()) < 1.0


def test_semblance_detects_moving_wavefront(tmp_path):
    # A slanted arrival is still coherent — the slowness scan must find it.
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040646.h5"
    # 0.4 samples/channel slant -> apparent slowness 1e-3 s/m, inside the scan.
    write_synth_h5(p, datetime(2025, 1, 4, 6, 46), n_time=3000, n_ch=100, fs=100.0,
                   event_sample=1500, event_channels=range(100), event_amp=3.0,
                   event_moveout=0.4)
    das = read_h5(p)
    dets = detect_file(das, _cfg())
    assert len(dets) >= 1
    assert max(d.semblance for d in dets) > _cfg().semblance_thr


def test_semblance_quiet_file_returns_nothing(tmp_path):
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040647.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 47), n_time=3000, n_ch=100, fs=100.0)
    das = read_h5(p)
    assert detect_file(das, _cfg()) == []


def test_semblance_rejects_incoherent_single_channel(tmp_path):
    # A big transient on one channel is loud but not coherent -> no semblance det.
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040648.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 48), n_time=3000, n_ch=100, fs=100.0,
                   event_sample=1500, event_channels=[7], event_amp=40.0)
    das = read_h5(p)
    assert detect_file(das, _cfg()) == []


def test_depth_limits_resolve_to_channels(tmp_path):
    # 100 channels @ dx=4 m -> depths 0,4,...,396. depth 40..200 m -> ch 10..50.
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040649.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 49), n_time=1000, n_ch=100, fs=100.0)
    das = read_h5(p)
    lo, hi = resolve_channel_range(das, DetectConfig(depth_min_m=40.0, depth_max_m=200.0))
    assert lo == 10
    assert 50 <= hi <= 51                           # inclusive of 200 m (ch 50)
    assert das.channel_depths[lo] >= 40.0
    # depth limits combine with (are bounded by) explicit channel_min/max
    lo2, hi2 = resolve_channel_range(
        das, DetectConfig(depth_min_m=40.0, channel_min=20))
    assert lo2 == 20


def test_both_merges_overlapping_detections(tmp_path):
    # A strong aligned event fires BOTH backends; "both" must yield one row.
    p = tmp_path / "JJK_400m_8m_4m_5000Hz_100Hz_UTC8_202501040650.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 50), n_time=3000, n_ch=100, fs=100.0,
                   event_sample=1500, event_channels=range(100), event_amp=6.0)
    das = read_h5(p)
    cfg = _cfg(detector="both", sta_seconds=0.2, lta_seconds=2.0, thr_on=3.0,
               min_coincidence=5, channel_decimation=2)
    dets = detect_file(das, cfg)
    assert len(dets) == 1
    d = dets[0]
    assert "stalta" in d.method and "semblance" in d.method
    assert d.peak_ratio > 0.0 and d.semblance > 0.0     # both scores populated


def test_merge_keeps_disjoint_detections():
    def mk(t0, t1, method, ratio=0.0, sem=0.0):
        return Detection(
            t_start=datetime(2025, 1, 1, 0, 0, t0),
            t_end=datetime(2025, 1, 1, 0, 0, t1),
            t_peak=datetime(2025, 1, 1, 0, 0, t0),
            peak_ratio=ratio, peak_coincidence=5, channel_indices=[1, 2, 3],
            source_file="f", method=method, semblance=sem)
    a = mk(1, 3, "stalta", ratio=5.0)
    b = mk(4, 6, "semblance", sem=0.2)              # 1 s after a -> merges at gap>=1
    c = mk(30, 32, "semblance", sem=0.3)            # far away -> stays separate
    merged = _merge_detections([a, b, c], gap_seconds=1.0)
    assert len(merged) == 2
    assert merged[0].method == "semblance+stalta"
    assert merged[0].peak_ratio == 5.0 and merged[0].semblance == 0.2


def test_config_rejects_bad_detector():
    with pytest.raises(ValueError):
        DetectConfig(detector="magic")


def test_config_rejects_bad_semblance_thr():
    with pytest.raises(ValueError):
        DetectConfig(semblance_thr=0.0)
    with pytest.raises(ValueError):
        DetectConfig(semblance_thr=1.5)
