"""I/O for ZD-DAS per-minute HDF5 files: filename parsing and data reading."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import h5py

_FNAME_RE = re.compile(
    r"(?P<well>[A-Za-z]+)_(?P<depth>\d+(?:\.\d+)?)m_"
    r"(?P<gl>\d+(?:\.\d+)?)m_(?P<dx>\d+(?:\.\d+)?)m_"
    r"(?P<raw>\d+(?:\.\d+)?)Hz_(?P<out>\d+(?:\.\d+)?)Hz_"
    r"UTC8_(?P<ts>\d{12})"
)


@dataclass
class FileMeta:
    path: str
    well: str
    depth_m: float
    gauge_length_m: float
    dx_m: float
    raw_hz: float
    out_hz: float
    start_time: datetime


def parse_filename(path) -> FileMeta:
    """Parse metadata encoded in a JJK ZD-DAS filename.

    The 12-digit timestamp is treated as UTC (it matches the file's
    MeasurementStartTime attribute despite the UTC8 label in the name).
    """
    name = Path(path).name
    m = _FNAME_RE.search(name)
    if not m:
        raise ValueError(f"Unrecognized DAS filename: {name!r}")
    ts = datetime.strptime(m["ts"], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    return FileMeta(
        path=str(path),
        well=m["well"],
        depth_m=float(m["depth"]),
        gauge_length_m=float(m["gl"]),
        dx_m=float(m["dx"]),
        raw_hz=float(m["raw"]),
        out_hz=float(m["out"]),
        start_time=ts,
    )
