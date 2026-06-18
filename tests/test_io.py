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
