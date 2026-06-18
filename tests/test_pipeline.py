from datetime import datetime
import csv
from das_events.config import DetectConfig
from das_events.pipeline import scan_dir, write_events_csv, EVENT_COLUMNS
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(sta_seconds=0.2, lta_seconds=2.0, thr_on=3.0, min_coincidence=4,
                min_duration_seconds=0.1, merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_scan_dir_finds_event_and_builds_event(tmp_path):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040646.h5",
                   datetime(2025, 1, 4, 6, 46), n_time=2000, n_ch=20, fs=100.0)
    events = scan_dir(d, _cfg())
    assert len(events) == 1
    ev = events[0]
    assert ev.event_id.startswith("JJK_2025")
    assert ev.n_channels >= 4
    assert ev.label == ""


def test_write_events_csv_roundtrip(tmp_path):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    events = scan_dir(d, _cfg())
    out = tmp_path / "events.csv"
    write_events_csv(events, out)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0].keys()) == EVENT_COLUMNS
    assert rows[0]["event_id"] == events[0].event_id
