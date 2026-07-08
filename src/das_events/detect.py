"""Event detection.

Two complementary backends, selected by ``DetectConfig.detector``:

* ``"stalta"``  – per-channel band-pass + recursive STA/LTA with channel
  coincidence. Sharp, impulsive, high-SNR arrivals; gives a per-channel
  amplitude ratio. This is the historical default.
* ``"semblance"`` – slant-stack spatial **coherence** across the borehole.
  Amplitude-agnostic and baseline-free, so it catches *weak, emergent*
  coherent arrivals ("continuous first arrivals") that never push any single
  channel's STA/LTA above threshold, and events that fill the whole file with
  no quiet window to normalise against.
* ``"both"`` – run both and merge overlapping detections (best recall).

The two backends emit the same :class:`Detection` objects, so features,
waterfalls and staging are identical downstream.
"""

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


def bandpass_cols(x: np.ndarray, fs: float, freqmin: float, freqmax: float) -> np.ndarray:
    """Zero-phase Butterworth bandpass applied column-wise (n_time, n_ch)."""
    nyq = fs / 2.0
    hi = min(freqmax, 0.999 * nyq)
    sos = butter(4, [freqmin / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, np.asarray(x, dtype=float), axis=0)


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
    peak_ratio: float                 # peak STA/LTA ratio (0.0 if only semblance fired)
    peak_coincidence: int
    channel_indices: list[int]
    source_file: str
    method: str = "stalta"            # "stalta" | "semblance" | "stalta+semblance"
    semblance: float = 0.0            # peak slant-stack coherence (0.0 if only STA/LTA)


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


def resolve_channel_range(das, cfg) -> tuple[int, int]:
    """Return (lo, hi) channel bounds honouring channel_min/max and depth_min/max_m.

    Depth limits (metres) are resolved against ``das.channel_depths`` so the
    same config transfers across devices with a different channel count / dx.
    """
    n_ch_total = das.data.shape[1]
    depths = das.channel_depths
    lo = int(cfg.channel_min)
    hi = int(cfg.channel_max) if cfg.channel_max is not None else n_ch_total
    if cfg.depth_min_m is not None:
        lo = max(lo, int(np.searchsorted(depths, cfg.depth_min_m, side="left")))
    if cfg.depth_max_m is not None:
        hi = min(hi, int(np.searchsorted(depths, cfg.depth_max_m, side="right")))
    lo = max(0, min(lo, n_ch_total))
    hi = max(lo + 1, min(hi, n_ch_total))
    return lo, hi


# ── STA/LTA backend ─────────────────────────────────────────────────────────
def detect_stalta(das, cfg, lo: int, hi: int) -> list:
    """Per-channel STA/LTA with channel coincidence over channels [lo, hi)."""
    data = das.data
    fs = das.fs
    n_time = data.shape[0]
    ch_idx = np.arange(lo, hi, cfg.channel_decimation)

    trig = np.zeros((len(ch_idx), n_time), dtype=bool)
    cf_max = np.zeros(n_time)
    for i, c in enumerate(ch_idx):
        filt = bandpass_channel(data[:, c], fs, cfg.freqmin, cfg.freqmax)
        cf = characteristic_function(filt, fs, cfg.sta_seconds, cfg.lta_seconds)
        trig[i] = cf > cfg.thr_on
        cf_max = np.maximum(cf_max, cf)

    # Suppress filter/STA-LTA edge transients at both file boundaries, which
    # otherwise fire a spurious full-borehole detection in every minute-file.
    n_skip = int(cfg.edge_skip_seconds * fs)
    if n_skip > 0 and 2 * n_skip < n_time:
        trig[:, :n_skip] = False
        trig[:, n_time - n_skip:] = False

    coincidence = trig.sum(axis=0)
    active = coincidence >= cfg.min_coincidence
    min_dur = max(1, int(cfg.min_duration_seconds * fs))
    max_gap = int(cfg.merge_gap_seconds * fs)

    dets = []
    for s0, s1 in _group_runs(active, max_gap):
        if s1 - s0 < min_dur:
            continue
        seg = coincidence[s0:s1]
        on = active[s0:s1]                       # samples actually at/above threshold
        peak = s0 + int(np.argmax(seg))
        # restrict to active samples so features reflect the event, not gap noise
        live = np.flatnonzero(trig[:, s0:s1][:, on].any(axis=1))
        ratio = float(cf_max[s0:s1][on].max())
        dets.append(Detection(
            t_start=das.time_at(s0),
            t_end=das.time_at(s1 - 1),
            t_peak=das.time_at(peak),
            peak_ratio=ratio,
            peak_coincidence=int(seg.max()),
            channel_indices=[int(ch_idx[i]) for i in live],
            source_file=das.meta.path if das.meta else "",
            method="stalta",
            semblance=0.0,
        ))
    return dets


# ── semblance backend ───────────────────────────────────────────────────────
def _movingsum(a: np.ndarray, w: int) -> np.ndarray:
    c = np.cumsum(np.insert(a, 0, 0.0))
    return c[w:] - c[:-w]                         # length len(a) - w + 1


def _slowness_grid(cfg) -> np.ndarray:
    if cfg.semblance_n_slowness <= 1:
        return np.array([0.0])
    return np.linspace(-cfg.semblance_slowness_max, cfg.semblance_slowness_max,
                       cfg.semblance_n_slowness)


def detect_semblance(das, cfg, lo: int, hi: int) -> list:
    """Slant-stack spatial-coherence detection over channels [lo, hi).

    Filters the aperture once, whitens each channel's amplitude, then scans a
    grid of apparent slownesses, taking the peak semblance at each time over
    the configured depth sub-bands. Coherent arrivals score high regardless of
    amplitude; incoherent noise sits near the 1/M floor. For each slowness the
    whole aperture is time-aligned once and every band is read off as a column
    subset (one gather per slowness, not per band).
    """
    fs = das.fs
    n_time = das.data.shape[0]
    depths = das.channel_depths
    ch_all = np.arange(lo, hi, cfg.semblance_channel_decimation)
    if len(ch_all) < 4:
        return []

    x = bandpass_cols(das.data[:, ch_all], fs, cfg.freqmin, cfg.freqmax)
    std = x.std(axis=0)
    x /= (std + 1e-12)                            # amplitude whitening per channel
    x[:, std < 1e-9] = 0.0                        # neutralize dead channels
    z_all = depths[ch_all].astype(float)
    z0 = z_all - z_all.mean()

    if cfg.semblance_depth_bands:
        bands = [(float(a), float(b)) for a, b in cfg.semblance_depth_bands]
    else:
        bands = [(z_all[0], z_all[-1])]
    band_sel = [np.where((z_all >= blo) & (z_all <= bhi))[0] for blo, bhi in bands]

    w = max(1, int(cfg.semblance_win_seconds * fs))
    if w >= n_time:
        return []
    slows = _slowness_grid(cfg)
    tvec = np.arange(n_time)

    # peak semblance per sample (window value assigned to window centre) and the
    # band that produced it (for the depth features of the detection).
    sem = np.zeros(n_time)
    band_of = np.full(n_time, -1, dtype=int)
    off = w // 2
    for p in slows:
        shifts = np.round(p * z0 * fs).astype(int)
        idx = tvec[:, None] - shifts[None, :]     # (n_time, M): time index per channel
        np.clip(idx, 0, n_time - 1, out=idx)
        aligned = np.take_along_axis(x, idx, axis=0)      # shift each channel in time
        sq = aligned * aligned
        for bi, sel in enumerate(band_sel):
            if sel.size < 4:
                continue
            beam = aligned[:, sel].sum(axis=1)
            esum = sq[:, sel].sum(axis=1)
            num = _movingsum(beam * beam, w)
            den = sel.size * _movingsum(esum, w) + 1e-12
            best = num / den
            seg = sem[off:off + best.size]
            better = best > seg
            seg[better] = best[better]
            band_of[off:off + best.size][better] = bi

    # edge-transient suppression (same rationale as STA/LTA path)
    n_skip = int(cfg.edge_skip_seconds * fs)
    if n_skip > 0 and 2 * n_skip < n_time:
        sem[:n_skip] = 0.0
        sem[n_time - n_skip:] = 0.0

    active = sem >= cfg.semblance_thr
    min_dur = max(1, int(cfg.min_duration_seconds * fs))
    max_gap = int(cfg.merge_gap_seconds * fs)

    dets = []
    for s0, s1 in _group_runs(active, max_gap):
        if s1 - s0 < min_dur:
            continue
        peak = s0 + int(np.argmax(sem[s0:s1]))
        bi = int(band_of[peak])
        if bi >= 0:
            blo, bhi = bands[bi]
            live = [int(c) for c in ch_all if blo <= depths[c] <= bhi]
        else:
            live = [int(c) for c in ch_all]
        dets.append(Detection(
            t_start=das.time_at(s0),
            t_end=das.time_at(s1 - 1),
            t_peak=das.time_at(peak),
            peak_ratio=0.0,
            peak_coincidence=len(live),
            channel_indices=live,
            source_file=das.meta.path if das.meta else "",
            method="semblance",
            semblance=float(sem[peak]),
        ))
    return dets


# ── merge (for detector="both") ─────────────────────────────────────────────
def _merge_detections(dets: list, gap_seconds: float) -> list:
    """Merge detections whose time spans overlap (within ``gap_seconds``)."""
    if not dets:
        return []
    dets = sorted(dets, key=lambda d: d.t_start)
    merged = [dets[0]]
    for d in dets[1:]:
        m = merged[-1]
        if d.t_start.timestamp() <= m.t_end.timestamp() + gap_seconds:
            methods = sorted(set(m.method.split("+")) | set(d.method.split("+")))
            # STA/LTA detection (if present) wins t_peak: its onset is sharper.
            hot = m if m.peak_ratio >= d.peak_ratio else d
            merged[-1] = Detection(
                t_start=min(m.t_start, d.t_start),
                t_end=max(m.t_end, d.t_end),
                t_peak=hot.t_peak,
                peak_ratio=max(m.peak_ratio, d.peak_ratio),
                peak_coincidence=max(m.peak_coincidence, d.peak_coincidence),
                channel_indices=sorted(set(m.channel_indices) | set(d.channel_indices)),
                source_file=m.source_file or d.source_file,
                method="+".join(methods),
                semblance=max(m.semblance, d.semblance),
            )
        else:
            merged.append(d)
    return merged


def detect_file(das, cfg) -> list:
    """Detect events in one DasData object per DetectConfig (dispatches backend)."""
    lo, hi = resolve_channel_range(das, cfg)
    dets = []
    if cfg.detector in ("stalta", "both"):
        dets += detect_stalta(das, cfg, lo, hi)
    if cfg.detector in ("semblance", "both"):
        dets += detect_semblance(das, cfg, lo, hi)
    if cfg.detector == "both":
        dets = _merge_detections(dets, cfg.merge_gap_seconds)
    dets.sort(key=lambda d: d.t_start)
    return dets
