import numpy as np
import h5py
import pytest
from datetime import datetime, timezone


def write_synth_h5(path, start_dt, n_time=2000, n_ch=20, fs=100.0,
                   dx=4.0, gl=8.0, event_sample=None, event_channels=None,
                   event_amp=8.0, event_freq=10.0, noise=0.02, seed=0,
                   second_event_sample=None):
    """Write a minimal ZD-DAS-style HDF5 file for tests.

    Injects a Gaussian-tapered sinusoid wavelet at ``event_sample`` on
    ``event_channels`` (default: all). Optionally a second wavelet at
    ``second_event_sample`` for P-S separation tests.
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, noise, (n_time, n_ch)).astype("float32")
    start_dt = start_dt.replace(tzinfo=timezone.utc)

    def _inject(center):
        t = np.arange(-60, 60)
        wav = (event_amp * np.exp(-(t / 18.0) ** 2)
               * np.sin(2 * np.pi * event_freq * t / fs)).astype("float32")
        chans = range(n_ch) if event_channels is None else event_channels
        s0 = center - 60
        for c in chans:
            data[s0:s0 + len(wav), c] += wav

    if event_sample is not None:
        _inject(event_sample)
    if second_event_sample is not None:
        _inject(second_event_sample)

    t0_us = int(start_dt.timestamp() * 1e6)
    times = (t0_us + np.arange(n_time) * (1e6 / fs)).astype("int64")

    with h5py.File(path, "w") as f:
        acq = f.create_group("Acquisition")
        acq.attrs["GaugeLength"] = gl
        acq.attrs["SpatialSamplingInterval"] = dx
        acq.attrs["MeasurementStartTime"] = \
            start_dt.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00").encode()
        acq.attrs["NumberOfLoci"] = n_ch
        acq.attrs["StartLocusIndex"] = 0
        raw = acq.create_group("Raw[0]")
        raw.attrs["OutputDataRate"] = fs
        raw.attrs["StartLocusIndex"] = 0
        raw.attrs["RawDataUnit"] = b"(nm/m)/s * Hz/m"
        raw.create_dataset("RawData", data=data)
        raw.create_dataset("RawDataTime", data=times)
    return path


@pytest.fixture
def synth_h5(tmp_path):
    """A clean (no-event) synthetic h5 named like real JJK files."""
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45))
    return p
