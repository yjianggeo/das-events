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


@dataclass
class DasData:
    data: np.ndarray            # (n_time, n_ch) float
    times: np.ndarray           # (n_time,) int64 microseconds UTC
    fs: float
    dx: float
    gauge_length: float
    start_time: datetime
    channel_depths: np.ndarray  # (n_ch,) metres
    meta: FileMeta | None = None

    def time_at(self, sample: int) -> datetime:
        us = int(self.times[sample])
        return datetime.fromtimestamp(us / 1e6, tz=timezone.utc)


def channel_depths(n_ch: int, start_locus: int, dx: float) -> np.ndarray:
    return (start_locus + np.arange(n_ch)) * dx


def read_h5(path, ch_slice: slice | None = None) -> DasData:
    """Read a ZD-DAS minute-file into a DasData object.

    ``ch_slice`` restricts the channel (column) range at read time.
    """
    try:
        meta = parse_filename(path)
    except ValueError:
        meta = None
    with h5py.File(path, "r") as f:
        acq = f["Acquisition"]
        raw = acq["Raw[0]"]
        cols = ch_slice if ch_slice is not None else slice(None)
        data = raw["RawData"][:, cols].astype(np.float64)
        times = raw["RawDataTime"][:].astype(np.int64)
        fs = float(raw.attrs["OutputDataRate"])
        dx = float(acq.attrs["SpatialSamplingInterval"])
        gl = float(acq.attrs["GaugeLength"])
        start_locus = int(acq.attrs.get("StartLocusIndex", 0))
        n_ch_total = int(acq.attrs.get("NumberOfLoci", data.shape[1]))
    depths_all = channel_depths(n_ch_total, start_locus, dx)
    depths = depths_all[cols] if ch_slice is not None else depths_all[:data.shape[1]]
    start_time = datetime.fromtimestamp(int(times[0]) / 1e6, tz=timezone.utc)
    return DasData(
        data=data, times=times, fs=fs, dx=dx, gauge_length=gl,
        start_time=start_time, channel_depths=depths, meta=meta,
    )
