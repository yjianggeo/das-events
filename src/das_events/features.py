"""Per-event feature extraction for earthquake/blast review."""

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from .detect import bandpass_channel


@dataclass
class EventFeatures:
    dom_freq_hz: float
    bandwidth_hz: float
    depth_min_m: float
    depth_max_m: float
    n_channels: int
    ps_separation_s: float | None
    local_time_of_day: str


def _sample_index(das, when) -> int:
    return int(round((when.timestamp() - das.time_at(0).timestamp()) * das.fs))


def extract_features(das, detection, cfg) -> EventFeatures:
    fs = das.fs
    s0 = max(0, _sample_index(das, detection.t_start))
    s1 = min(das.data.shape[0], _sample_index(das, detection.t_end) + 1)
    chans = detection.channel_indices or list(range(das.data.shape[1]))

    # Representative trace: bandpassed mean over triggered channels in the window.
    seg = das.data[s0:s1, chans]
    filt = np.column_stack([
        bandpass_channel(seg[:, j], fs, cfg.freqmin, cfg.freqmax)
        for j in range(seg.shape[1])
    ])
    rep = filt.mean(axis=1)

    # Spectral centroid + spread (energy-weighted).
    spec = np.abs(np.fft.rfft(rep)) ** 2
    freqs = np.fft.rfftfreq(rep.size, d=1.0 / fs)
    power = spec.sum()
    if power > 0:
        centroid = float((freqs * spec).sum() / power)
        spread = float(np.sqrt(((freqs - centroid) ** 2 * spec).sum() / power))
    else:
        centroid = spread = 0.0

    depths = das.channel_depths[chans]
    ps = _ps_separation(rep, fs, cfg)

    local = (detection.t_peak + timedelta(hours=8)).strftime("%H:%M:%S")

    return EventFeatures(
        dom_freq_hz=round(centroid, 3),
        bandwidth_hz=round(spread, 3),
        depth_min_m=float(np.min(depths)),
        depth_max_m=float(np.max(depths)),
        n_channels=len(chans),
        ps_separation_s=ps,
        local_time_of_day=local,
    )


def _ps_separation(rep, fs, cfg):
    """Rough P-S delay: separation of the two largest envelope peaks, else None."""
    from scipy.signal import find_peaks
    env = np.abs(rep)
    if env.max() <= 0:
        return None
    peaks, props = find_peaks(env, height=0.4 * env.max(),
                              distance=int(0.3 * fs) or 1)
    if peaks.size < 2:
        return None
    order = np.argsort(props["peak_heights"])[::-1][:2]
    two = np.sort(peaks[order])
    return round(abs(two[1] - two[0]) / fs, 3)
