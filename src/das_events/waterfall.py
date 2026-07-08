"""Waterfall (channel x time) plotting for DAS events."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .detect import bandpass_cols


def plot_waterfall(das, t0=None, t1=None, out_path=None,
                   clip_pct=(1.0, 99.0), title=None,
                   freqmin=None, freqmax=None, normalize=False,
                   depth_min_m=None, depth_max_m=None):
    """Render a channel x time waterfall. Returns the matplotlib Figure.

    ``t0``/``t1`` are UTC datetimes bounding the time window (default: whole file).
    Amplitude is clipped to the given percentile range for display.

    Optional processing (off by default, matching the historical output):

    * ``freqmin``/``freqmax`` – band-pass each channel before display, so a
      weak event isn't buried under low-frequency drift or high-frequency noise.
    * ``normalize`` – divide each channel by its own robust amplitude (MAD), so
      a coherent arrival is visible even on quiet deep channels that a global
      colour scale would wash out. This is what makes semblance-only detections
      (very weak events) reviewable.
    * ``depth_min_m``/``depth_max_m`` – restrict the plotted depth range to the
      detection aperture (drops the loud shallow band / out-of-well tail).
    """
    fs = das.fs
    base = das.time_at(0).timestamp()
    s0 = 0 if t0 is None else max(0, int(round((t0.timestamp() - base) * fs)))
    s1 = das.data.shape[0] if t1 is None else min(
        das.data.shape[0], int(round((t1.timestamp() - base) * fs)))

    depths = das.channel_depths
    c0, c1 = 0, das.data.shape[1]
    if depth_min_m is not None:
        c0 = int(np.searchsorted(depths, depth_min_m, side="left"))
    if depth_max_m is not None:
        c1 = int(np.searchsorted(depths, depth_max_m, side="right"))
    c0 = max(0, min(c0, das.data.shape[1] - 1))
    c1 = max(c0 + 1, min(c1, das.data.shape[1]))

    seg = das.data[s0:s1, c0:c1].astype(float)
    if freqmin is not None and freqmax is not None:
        seg = bandpass_cols(seg, fs, freqmin, freqmax)
    if normalize:
        mad = np.median(np.abs(seg - np.median(seg, axis=0)), axis=0)
        seg = seg / (mad + 1e-12)

    lo, hi = np.percentile(seg, clip_pct)
    vmax = max(abs(lo), abs(hi)) or 1.0

    fig, ax = plt.subplots(figsize=(10, 6))
    extent = [0, (s1 - s0) / fs, depths[c1 - 1], depths[c0]]
    ax.imshow(seg.T, aspect="auto", cmap="seismic",
              vmin=-vmax, vmax=vmax, extent=extent)
    ax.set_xlabel(f"Time (s) from {das.time_at(s0).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    ax.set_ylabel("Depth (m)")
    ax.set_title(title or "DAS waterfall")
    fig.tight_layout()
    if out_path is not None:
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
    return fig
