"""Teleseismic surface-wave detection (directory-level, cross-file).

Teleseismic surface waves are very low frequency (~0.05-0.2 Hz), multi-minute
dispersive trains that arrive near-simultaneously across the whole borehole
(apparent slowness ~= 0). At those frequencies DAS is dominated by spatially
coherent common-mode noise, so *per-minute* coherence or energy does not
separate a surface wave from a coherent-noise burst.

The discriminant that does work is **temporal persistence**: a surface-wave
train keeps the borehole coherent for several consecutive minutes, whereas
coherent-noise bursts are isolated single minutes. So this detector:

1. band-passes each minute-file to the surface-wave band, tapers the edges
   (low-frequency band-pass rings hard on a 60 s file), forms the depth beam
   (slowness~=0 stack) and measures its coherence = ``(std(beam)/mean(std_ch))**2``
   (the slowness-0 semblance);
2. flags minutes whose coherence exceeds ``teleseism_min_coherence``;
3. reports a detection only for **runs of >= ``teleseism_min_run`` consecutive**
   flagged minute-files, emitting one Event spanning the whole run.

This is inherently a directory-level pass (it needs neighbouring files), unlike
the per-file :func:`das_events.detect.detect_file` backends.
"""

import warnings
from datetime import timedelta
from pathlib import Path

import numpy as np

from .io import read_h5
from .detect import Detection, bandpass_cols, resolve_channel_range


def file_coherence(das, cfg, lo: int, hi: int) -> float:
    """Slowness~=0 spatial coherence of one file in the surface-wave band.

    Edges are cosine-tapered over ``edge_skip_seconds`` because a low-frequency
    band-pass produces a large, depth-coherent transient at each file boundary
    that would otherwise read as signal.
    """
    fs = das.fs
    ch = np.arange(lo, hi, cfg.semblance_channel_decimation)
    if len(ch) < 4:
        return 0.0
    x = bandpass_cols(das.data[:, ch], fs, cfg.freqmin, cfg.freqmax)
    n = x.shape[0]
    k = int(cfg.edge_skip_seconds * fs)
    if k > 0 and 2 * k < n:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(k) / k))
        x[:k] *= ramp[:, None]
        x[n - k:] *= ramp[::-1][:, None]
    beam = x.mean(axis=1)                       # coherent (slowness~=0) stack
    denom = x.std(axis=0).mean()
    if denom <= 0:
        return 0.0
    return float((beam.std() / denom) ** 2)


def _runs(flags, starts, min_run, max_gap_s=90.0):
    """Index ranges (i0, i1) of >= min_run consecutive flagged, time-contiguous files."""
    out = []
    n = len(flags)
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while (j + 1 < n and flags[j + 1]
                   and (starts[j + 1] - starts[j]).total_seconds() <= max_gap_s):
                j += 1
            if j - i + 1 >= min_run:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def scan_teleseism_dir(data_dir, cfg, progress=None) -> list:
    """Detect teleseismic surface-wave trains across every ``*.h5`` in a directory.

    Returns a list of :class:`das_events.detect.Detection`, one per sustained
    coherent run. A file that cannot be read is skipped with a warning.
    """
    files = sorted(Path(data_dir).glob("*.h5"))
    recs = []                                    # (path, start_time, coherence)
    for i, fp in enumerate(files):
        if progress:
            progress(i, len(files), fp.name)
        try:
            das = read_h5(fp)
            lo, hi = resolve_channel_range(das, cfg)
            coh = file_coherence(das, cfg, lo, hi)
        except Exception as exc:
            warnings.warn(f"skipping unreadable file {fp.name}: {exc}")
            continue
        recs.append((fp, das.start_time, coh))

    if not recs:
        return []
    starts = [r[1] for r in recs]
    cohs = np.array([r[2] for r in recs])
    flags = cohs >= cfg.teleseism_min_coherence

    dets = []
    for i0, i1 in _runs(flags, starts, cfg.teleseism_min_run):
        pk = i0 + int(np.argmax(cohs[i0:i1 + 1]))
        peak_fp, peak_start, peak_coh = recs[pk]
        das = read_h5(peak_fp)
        lo, hi = resolve_channel_range(das, cfg)
        ch = list(range(lo, hi, cfg.semblance_channel_decimation))
        file_len = timedelta(seconds=(das.data.shape[0] - 1) / das.fs)
        dets.append(Detection(
            t_start=starts[i0],
            t_end=starts[i1] + file_len,
            t_peak=peak_start + file_len / 2,
            peak_ratio=0.0,
            peak_coincidence=len(ch),
            channel_indices=ch,
            source_file=str(peak_fp),
            method="teleseism",
            semblance=float(peak_coh),
        ))
    return dets
