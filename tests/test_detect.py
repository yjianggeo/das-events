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
