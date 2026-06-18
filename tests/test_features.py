from datetime import datetime
import numpy as np
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from das_events.features import extract_features
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(sta_seconds=0.2, lta_seconds=2.0, thr_on=3.0, min_coincidence=4,
                min_duration_seconds=0.1, merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_features_recover_dominant_frequency(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20), event_freq=15.0)
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    assert 10.0 < f.dom_freq_hz < 20.0          # ~15 Hz
    assert f.n_channels >= 4


def test_features_depth_range_from_channels(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(0, 8))
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    assert f.depth_min_m >= 0.0
    assert f.depth_max_m <= 40.0


def test_features_local_time_of_day_is_utc_plus_8(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    assert f.local_time_of_day.startswith("14:")
