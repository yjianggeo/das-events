"""Configuration for das-events detection, selection, and staging."""

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass
class DetectConfig:
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
    # --- channel sub-sampling ---
    channel_decimation: int = 4       # use every Nth channel for detection
    channel_min: int = 0              # first channel index (inclusive)
    channel_max: int | None = None    # last channel index (exclusive); None=all
    # --- selection / staging ---
    pad_seconds: float = 60.0         # boundary pad pulling adjacent minute-files
    stage_mode: str = "copy"          # "copy" | "hardlink"
    # --- optional catalog cross-match ---
    sta_lat: float = 30.28787
    sta_lon: float = 101.27760
    catalog_radius_km: float = 800.0
    catalog_min_mag: float = 1.5
    catalog_tol_seconds: float = 120.0


def load_config(path) -> DetectConfig:
    """Load a DetectConfig from YAML, applying overrides onto the defaults."""
    raw = yaml.safe_load(Path(path).read_text()) or {}
    valid = {f.name for f in fields(DetectConfig)}
    unknown = set(raw) - valid
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")
    return DetectConfig(**raw)
