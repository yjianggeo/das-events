"""Event detection: per-channel STA/LTA with channel coincidence."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.signal import butter, sosfiltfilt
from obspy.signal.trigger import recursive_sta_lta


def bandpass_channel(x: np.ndarray, fs: float, freqmin: float, freqmax: float) -> np.ndarray:
    """Zero-phase Butterworth bandpass of one channel."""
    nyq = fs / 2.0
    hi = min(freqmax, 0.999 * nyq)
    sos = butter(4, [freqmin / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=float))


def characteristic_function(x: np.ndarray, fs: float, sta: float, lta: float) -> np.ndarray:
    """Recursive STA/LTA characteristic function of an already-filtered trace."""
    nsta = max(1, int(sta * fs))
    nlta = max(nsta + 1, int(lta * fs))
    return recursive_sta_lta(np.ascontiguousarray(x, dtype=float), nsta, nlta)


@dataclass
class Detection:
    t_start: datetime
    t_end: datetime
    t_peak: datetime
    peak_ratio: float
    peak_coincidence: int
    channel_indices: list
    source_file: str


def _group_runs(active: np.ndarray, max_gap: int):
    """Yield (start, end) sample index pairs of True runs, merging gaps <= max_gap."""
    idx = np.flatnonzero(active)
    if idx.size == 0:
        return []
    runs = []
    s = prev = idx[0]
    for i in idx[1:]:
        if i - prev > max_gap + 1:
            runs.append((s, prev + 1))
            s = i
        prev = i
    runs.append((s, prev + 1))
    return runs


def detect_file(das, cfg) -> list:
    """Detect coincident events in one DasData object per DetectConfig."""
    data = das.data
    fs = das.fs
    n_time, n_ch_total = data.shape
    ch_hi = cfg.channel_max if cfg.channel_max is not None else n_ch_total
    ch_idx = np.arange(cfg.channel_min, ch_hi, cfg.channel_decimation)

    trig = np.zeros((len(ch_idx), n_time), dtype=bool)
    cf_max = np.zeros(n_time)
    for i, c in enumerate(ch_idx):
        filt = bandpass_channel(data[:, c], fs, cfg.freqmin, cfg.freqmax)
        cf = characteristic_function(filt, fs, cfg.sta_seconds, cfg.lta_seconds)
        trig[i] = cf > cfg.thr_on
        cf_max = np.maximum(cf_max, cf)

    coincidence = trig.sum(axis=0)
    active = coincidence >= cfg.min_coincidence
    min_dur = max(1, int(cfg.min_duration_seconds * fs))
    max_gap = int(cfg.merge_gap_seconds * fs)

    dets = []
    for s0, s1 in _group_runs(active, max_gap):
        if s1 - s0 < min_dur:
            continue
        seg = coincidence[s0:s1]
        peak = s0 + int(np.argmax(seg))
        live = np.flatnonzero(trig[:, s0:s1].any(axis=1))
        dets.append(Detection(
            t_start=das.time_at(s0),
            t_end=das.time_at(s1 - 1),
            t_peak=das.time_at(peak),
            peak_ratio=float(cf_max[s0:s1].max()),
            peak_coincidence=int(seg.max()),
            channel_indices=[int(ch_idx[i]) for i in live],
            source_file=das.meta.path if das.meta else "",
        ))
    return dets
