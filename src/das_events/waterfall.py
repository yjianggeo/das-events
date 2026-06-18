"""Waterfall (channel x time) plotting for DAS events."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_waterfall(das, t0=None, t1=None, out_path=None,
                   clip_pct=(1.0, 99.0), title=None):
    """Render a channel x time waterfall. Returns the matplotlib Figure.

    ``t0``/``t1`` are UTC datetimes bounding the time window (default: whole file).
    Amplitude is clipped to the given percentile range for display.
    """
    fs = das.fs
    base = das.time_at(0).timestamp()
    s0 = 0 if t0 is None else max(0, int(round((t0.timestamp() - base) * fs)))
    s1 = das.data.shape[0] if t1 is None else min(
        das.data.shape[0], int(round((t1.timestamp() - base) * fs)))
    seg = das.data[s0:s1, :]

    lo, hi = np.percentile(seg, clip_pct)
    vmax = max(abs(lo), abs(hi)) or 1.0

    fig, ax = plt.subplots(figsize=(10, 6))
    extent = [0, (s1 - s0) / fs,
              das.channel_depths[-1], das.channel_depths[0]]
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
