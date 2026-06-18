from datetime import datetime
import csv
from das_events.config import DetectConfig
from das_events.pipeline import scan_dir, write_events_csv, EVENT_COLUMNS
from das_events.cli import main
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


def test_cli_scan_then_stage(tmp_path, monkeypatch):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("sta_seconds: 0.2\nlta_seconds: 2.0\nthr_on: 3.0\n"
                   "min_coincidence: 4\nmin_duration_seconds: 0.1\n"
                   "merge_gap_seconds: 0.5\nchannel_decimation: 1\npad_seconds: 5.0\n")
    events_csv = tmp_path / "events.csv"
    rc = main(["scan", str(d), "--config", str(cfg), "--events", str(events_csv)])
    assert rc == 0 and events_csv.exists()

    staging = tmp_path / "staging"
    rc = main(["stage", "--events", str(events_csv), "--data-dir", str(d),
               "--out", str(staging), "--config", str(cfg)])
    assert rc == 0
    assert (staging / "manifest.csv").exists()
    assert (staging / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5").exists()


def test_dedupe_ids_disambiguates_same_second():
    from das_events.pipeline import _dedupe_ids, Event
    def mk():
        return Event(event_id="JJK_20250104T064500", t_peak_utc="x", t_start_utc="x",
                     t_end_utc="x", duration_s=0.1, peak_ratio=1.0, peak_coincidence=4,
                     n_channels=4, depth_min_m=0.0, depth_max_m=1.0, dom_freq_hz=1.0,
                     bandwidth_hz=1.0, local_time_of_day="14:45:00", ps_separation_s=None,
                     source_file="f", catalog_match="", label="")
    evs = [mk(), mk(), mk()]
    _dedupe_ids(evs)
    assert [e.event_id for e in evs] == [
        "JJK_20250104T064500", "JJK_20250104T064500_2", "JJK_20250104T064500_3"]


def test_cli_run_end_to_end(tmp_path):
    from das_events.cli import main
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1000, event_channels=range(20))
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("sta_seconds: 0.2\nlta_seconds: 2.0\nthr_on: 3.0\n"
                   "min_coincidence: 4\nmin_duration_seconds: 0.1\n"
                   "merge_gap_seconds: 0.5\nchannel_decimation: 1\n"
                   "pad_seconds: 5.0\nedge_skip_seconds: 0.5\n")
    out = tmp_path / "out"
    rc = main(["run", str(d), "--config", str(cfg), "--out", str(out)])
    assert rc == 0
    assert (out / "events.csv").exists()
    assert (out / "staging" / "manifest.csv").exists()
    assert (out / "staging" / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5").exists()
    assert list((out / "waterfall").glob("*.png"))
