"""Configuration for das-events detection, selection, and staging."""

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass
class DetectConfig:
    # --- detector backend ---
    detector: str = "stalta"          # "stalta" | "semblance" | "both" | "teleseism"
    # --- bandpass ---
    freqmin: float = 1.0
    freqmax: float = 40.0
    # --- STA/LTA ---
    sta_seconds: float = 0.5
    lta_seconds: float = 10.0
    thr_on: float = 4.0
    # --- coincidence ---
    min_coincidence: int = 4          # channels triggered simultaneously
    min_duration_seconds: float = 0.2
    merge_gap_seconds: float = 1.0
    edge_skip_seconds: float = 1.0    # suppress triggers within this margin of
                                      # each file edge (bandpass/STA-LTA transient)
    # --- channel sub-sampling ---
    channel_decimation: int = 4       # use every Nth channel for detection
    channel_min: int = 0              # first channel index (inclusive)
    channel_max: int | None = None    # last channel index (exclusive); None=all
    # --- depth-based channel selection (transfers across devices/dx;
    #     overrides channel_min/channel_max when set) ---
    depth_min_m: float | None = None  # ignore channels shallower than this (m)
    depth_max_m: float | None = None  # ignore channels deeper than this (m)
    # --- semblance detector (slant-stack spatial coherence) ---
    # Amplitude-agnostic, baseline-free: catches weak *coherent* arrivals
    # (continuous first arrivals) that per-channel STA/LTA misses.
    semblance_thr: float = 0.04            # trigger threshold on peak semblance (0..1)
    semblance_win_seconds: float = 2.0     # sliding coherence window
    semblance_slowness_max: float = 6e-4   # apparent slowness scan half-range (s/m)
    semblance_n_slowness: int = 11         # slowness grid points (odd -> includes 0)
    semblance_channel_decimation: int = 3  # every Nth channel in the aperture
    semblance_depth_bands: list | None = None  # [[lo_m, hi_m], ...] sub-bands to
                                          # scan (max over bands); None = whole aperture
    # --- teleseism (surface-wave) detector: directory-level, cross-file ---
    # Teleseismic surface waves are very low frequency (~0.05-0.2 Hz), multi-minute
    # dispersive trains, near-uniform across the borehole (slowness~=0). They sit in
    # DAS common-mode noise, so the discriminant is spatial coherence sustained over
    # several consecutive minute-files (isolated coherent bursts are noise).
    teleseism_min_coherence: float = 0.12  # per-file slowness~=0 semblance gate
    teleseism_min_run: int = 3             # consecutive coherent minute-files required
    # --- selection / staging ---
    pad_seconds: float = 60.0         # boundary pad pulling adjacent minute-files
    stage_mode: str = "copy"          # "copy" | "hardlink"
    # --- optional catalog cross-match ---
    sta_lat: float = 30.28787
    sta_lon: float = 101.27760
    catalog_radius_km: float = 800.0
    catalog_min_mag: float = 1.5
    catalog_tol_seconds: float = 120.0

    def __post_init__(self):
        if self.min_coincidence < 1:
            raise ValueError("min_coincidence must be >= 1")
        if self.channel_decimation < 1:
            raise ValueError("channel_decimation must be >= 1")
        if self.detector not in ("stalta", "semblance", "both", "teleseism"):
            raise ValueError(
                "detector must be 'stalta', 'semblance', 'both', or 'teleseism'")
        if self.teleseism_min_run < 1:
            raise ValueError("teleseism_min_run must be >= 1")
        if not (0.0 < self.teleseism_min_coherence <= 1.0):
            raise ValueError("teleseism_min_coherence must be in (0, 1]")
        if self.semblance_channel_decimation < 1:
            raise ValueError("semblance_channel_decimation must be >= 1")
        if self.semblance_n_slowness < 1:
            raise ValueError("semblance_n_slowness must be >= 1")
        if not (0.0 < self.semblance_thr <= 1.0):
            raise ValueError("semblance_thr must be in (0, 1]")


def load_config(path) -> DetectConfig:
    """Load a DetectConfig from YAML, applying overrides onto the defaults."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    valid = {f.name for f in fields(DetectConfig)}
    unknown = set(raw) - valid
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")
    return DetectConfig(**raw)
