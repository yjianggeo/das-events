from das_events.config import DetectConfig, load_config


def test_defaults_present():
    c = DetectConfig()
    assert c.freqmin < c.freqmax
    assert c.min_coincidence >= 1
    assert c.pad_seconds >= 0
    assert c.stage_mode in ("copy", "hardlink")


def test_load_config_overrides(tmp_path):
    p = tmp_path / "cfg.yaml"
    p.write_text("freqmin: 2.0\nfreqmax: 30.0\nmin_coincidence: 5\nstage_mode: hardlink\n")
    c = load_config(p)
    assert c.freqmin == 2.0
    assert c.freqmax == 30.0
    assert c.min_coincidence == 5
    assert c.stage_mode == "hardlink"
    assert c.sta_seconds == DetectConfig().sta_seconds


def test_load_config_rejects_unknown_key(tmp_path):
    p = tmp_path / "cfg.yaml"
    p.write_text("not_a_real_key: 3\n")
    import pytest
    with pytest.raises(ValueError):
        load_config(p)
