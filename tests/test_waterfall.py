from datetime import datetime
from das_events.io import read_h5
from das_events.waterfall import plot_waterfall
from conftest import write_synth_h5


def test_plot_waterfall_writes_png(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    out = tmp_path / "wf.png"
    plot_waterfall(das, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_plot_waterfall_time_window(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    out = tmp_path / "wf2.png"
    plot_waterfall(das, t0=das.time_at(1000), t1=das.time_at(1400), out_path=out)
    assert out.exists()
