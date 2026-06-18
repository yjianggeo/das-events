from datetime import datetime, timezone
from das_events.io import parse_filename


def test_parse_filename_extracts_all_fields():
    m = parse_filename("JJK_3410m_8m_4m_5000Hz_1000Hz_UTC8_202501040645.h5")
    assert m.well == "JJK"
    assert m.depth_m == 3410.0
    assert m.gauge_length_m == 8.0
    assert m.dx_m == 4.0
    assert m.raw_hz == 5000.0
    assert m.out_hz == 1000.0
    assert m.start_time == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)


def test_parse_filename_accepts_full_path():
    m = parse_filename(r"D:\data\JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202502221325.h5")
    assert m.start_time == datetime(2025, 2, 22, 13, 25, tzinfo=timezone.utc)
    assert m.depth_m == 80.0


import numpy as np
from das_events.io import read_h5
from conftest import write_synth_h5


def test_read_h5_returns_data_and_metadata(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert das.data.shape == (500, 20)
    assert das.fs == 100.0
    assert das.gauge_length == 8.0
    assert das.channel_depths.shape == (20,)
    assert das.start_time == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)


def test_time_at_returns_utc_datetime(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert das.time_at(0) == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)
    assert das.time_at(100).second == 1


def test_read_h5_channel_subset(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p, ch_slice=slice(0, 10))
    assert das.data.shape == (500, 10)
    assert das.channel_depths.shape == (10,)
