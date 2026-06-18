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
