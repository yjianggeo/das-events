# das-events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `das-events`, a package that scans per-minute ZD-DAS HDF5 files, detects seismic events directly from the DAS waterfall, records discriminating features + a waterfall plot per event, and stages only the event-bearing minute-files locally with a manifest for selective upload.

**Architecture:** A `src/das_events` library of focused modules (io, config, detect, features, catalog, waterfall, select, stage, pipeline) plus an argparse CLI. Detection is per-channel STA/LTA with channel-coincidence. Output is `events.csv` + `waterfall/*.png` + `staging/` + `manifest.csv`. No network transfer; staging is transport-agnostic.

**Tech Stack:** Python ≥3.11, numpy, scipy, h5py, obspy (STA/LTA + geodetics), matplotlib, PyYAML, pytest. Mirrors the `das-dvv` sibling-repo layout.

---

## File Structure

```
das-events/
  pyproject.toml
  README.md
  .gitignore
  src/das_events/
    __init__.py      # version + public re-exports
    io.py            # filename parsing, h5 read, channel depths, time helpers
    config.py        # DetectConfig dataclass + YAML loader + defaults
    detect.py        # characteristic function + coincidence detection
    features.py      # spectral / depth-range / time-of-day / P-S features
    catalog.py       # pure time/distance cross-match + thin FDSN fetch
    waterfall.py     # per-event waterfall plotting
    select.py        # detections -> minute-file upload set (+pad)
    stage.py         # copy/hardlink staging + sha256 manifest
    pipeline.py      # Event assembly, events.csv I/O, orchestration
    cli.py           # das-events {scan,plot,stage,run}
  tests/
    conftest.py      # write_synth_h5 fixture helper
    test_io.py
    test_config.py
    test_detect.py
    test_features.py
    test_catalog.py
    test_waterfall.py
    test_select.py
    test_stage.py
    test_pipeline.py
  examples/
    config.yaml
```

**Shared types** (defined once, referenced everywhere — keep names exact):
- `io.FileMeta`: `path, well, depth_m, gauge_length_m, dx_m, raw_hz, out_hz, start_time` (UTC `datetime`)
- `io.DasData`: `data (n_time, n_ch) float`, `times (n_time,) int64 µs`, `fs, dx, gauge_length, start_time, channel_depths (ndarray), meta (FileMeta|None)`; method `time_at(sample) -> datetime`
- `config.DetectConfig`: detection + selection + staging params (see Task 4)
- `detect.Detection`: `t_start, t_end, t_peak (datetime), peak_ratio, peak_coincidence, channel_indices (list[int]), source_file (str)`
- `features.EventFeatures`: `dom_freq_hz, bandwidth_hz, depth_min_m, depth_max_m, n_channels, ps_separation_s (float|None), local_time_of_day (str)`
- `pipeline.Event`: `event_id` + flattened Detection + EventFeatures + `catalog_match (str)` + `label (str)`

---

## Task 1: Project scaffolding + synthetic h5 fixture

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `src/das_events/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "das-events"
version = "0.1.0"
description = "Detect seismic events in DAS data and stage event-bearing minute-files for selective upload"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "yjianggeo", email = "yjianggeo@gmail.com" }]
dependencies = [
    "numpy>=1.24",
    "scipy>=1.10",
    "h5py>=3.8",
    "obspy>=1.4",
    "matplotlib>=3.7",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
das-events = "das_events.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
build/
dist/
staging/
out/
*.png
```

- [ ] **Step 3: Create `README.md` (stub) and `src/das_events/__init__.py`**

`README.md`:
```markdown
# das-events

Detect seismic events in per-minute DAS HDF5 files and stage only the
event-bearing files for selective upload. See `docs/superpowers/specs/`.
```

`src/das_events/__init__.py`:
```python
"""das-events: detect DAS events and stage minute-files for selective upload."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create `tests/conftest.py` with the synthetic h5 builder**

```python
import numpy as np
import h5py
import pytest
from datetime import datetime, timezone


def write_synth_h5(path, start_dt, n_time=2000, n_ch=20, fs=100.0,
                   dx=4.0, gl=8.0, event_sample=None, event_channels=None,
                   event_amp=8.0, event_freq=10.0, noise=0.02, seed=0,
                   second_event_sample=None):
    """Write a minimal ZD-DAS-style HDF5 file for tests.

    Injects a Gaussian-tapered sinusoid wavelet at ``event_sample`` on
    ``event_channels`` (default: all). Optionally a second wavelet at
    ``second_event_sample`` for P-S separation tests.
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, noise, (n_time, n_ch)).astype("float32")
    start_dt = start_dt.replace(tzinfo=timezone.utc)

    def _inject(center):
        t = np.arange(-60, 60)
        wav = (event_amp * np.exp(-(t / 18.0) ** 2)
               * np.sin(2 * np.pi * event_freq * t / fs)).astype("float32")
        chans = range(n_ch) if event_channels is None else event_channels
        s0 = center - 60
        for c in chans:
            data[s0:s0 + len(wav), c] += wav

    if event_sample is not None:
        _inject(event_sample)
    if second_event_sample is not None:
        _inject(second_event_sample)

    t0_us = int(start_dt.timestamp() * 1e6)
    times = (t0_us + np.arange(n_time) * (1e6 / fs)).astype("int64")

    with h5py.File(path, "w") as f:
        acq = f.create_group("Acquisition")
        acq.attrs["GaugeLength"] = gl
        acq.attrs["SpatialSamplingInterval"] = dx
        acq.attrs["MeasurementStartTime"] = \
            start_dt.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00").encode()
        acq.attrs["NumberOfLoci"] = n_ch
        acq.attrs["StartLocusIndex"] = 0
        raw = acq.create_group("Raw[0]")
        raw.attrs["OutputDataRate"] = fs
        raw.attrs["StartLocusIndex"] = 0
        raw.attrs["RawDataUnit"] = b"(nm/m)/s * Hz/m"
        raw.create_dataset("RawData", data=data)
        raw.create_dataset("RawDataTime", data=times)
    return path


@pytest.fixture
def synth_h5(tmp_path):
    """A clean (no-event) synthetic h5 named like real JJK files."""
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45))
    return p
```

- [ ] **Step 5: Verify the toolchain runs**

Run: `cd /d/Projects/das-events && pip install -e ".[dev]" && pytest -q`
Expected: install succeeds; pytest reports "no tests ran" (exit 5) — acceptable, confirms collection works.

- [ ] **Step 6: Commit**

```bash
cd /d/Projects/das-events
git add -A
git commit -m "chore: scaffold das-events package + synthetic h5 fixture"
```

---

## Task 2: io — filename parsing

**Files:**
- Create: `src/das_events/io.py`
- Test: `tests/test_io.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from das_events.io import parse_filename


def test_parse_filename_extracts_all_fields():
    m = parse_filename("JJK_3410m_8m_4m_5000Hz_1000Hz_UTC8_202501040645.h5")
    assert m.well == "JJK"
    assert m.depth_m == 3410.0
    assert m.gauge_length_m == 8.0
    assert m.dx_m == 4.0
    assert m.raw_hz == 5000.0
    assert m.out_hz == 1000.0
    assert m.start_time == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)


def test_parse_filename_accepts_full_path():
    m = parse_filename(r"D:\data\JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202502221325.h5")
    assert m.start_time == datetime(2025, 2, 22, 13, 25, tzinfo=timezone.utc)
    assert m.depth_m == 80.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_io.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: cannot import name 'parse_filename'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_io.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/io.py tests/test_io.py
git commit -m "feat(io): parse ZD-DAS filenames into FileMeta"
```

---

## Task 3: io — h5 reading, channel depths, time

**Files:**
- Modify: `src/das_events/io.py`
- Test: `tests/test_io.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_io.py`)**

```python
from datetime import datetime, timezone
import numpy as np
from das_events.io import read_h5
from conftest import write_synth_h5


def test_read_h5_returns_data_and_metadata(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert das.data.shape == (500, 20)
    assert das.fs == 100.0
    assert das.gauge_length == 8.0
    assert das.channel_depths.shape == (20,)
    assert das.start_time == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)


def test_time_at_returns_utc_datetime(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert das.time_at(0) == datetime(2025, 1, 4, 6, 45, tzinfo=timezone.utc)
    # sample 100 at 100 Hz == +1.0 s
    assert das.time_at(100).second == 1


def test_read_h5_channel_subset(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=500, n_ch=20, fs=100.0)
    das = read_h5(p, ch_slice=slice(0, 10))
    assert das.data.shape == (500, 10)
    assert das.channel_depths.shape == (10,)
```

(Note: `tests/conftest.py` is importable as `conftest` because pytest adds the
tests dir to `sys.path`; importing `write_synth_h5` directly is intentional.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_io.py -q`
Expected: FAIL — `ImportError: cannot import name 'read_h5'`.

- [ ] **Step 3: Write minimal implementation (append to `io.py`)**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_io.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/io.py tests/test_io.py
git commit -m "feat(io): read ZD-DAS h5 into DasData with depths and UTC times"
```

---

## Task 4: config — DetectConfig + YAML loader

**Files:**
- Create: `src/das_events/config.py`, `examples/config.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
from das_events.config import DetectConfig, load_config


def test_defaults_present():
    c = DetectConfig()
    assert c.freqmin < c.freqmax
    assert c.min_coincidence >= 1
    assert c.pad_seconds >= 0
    assert c.stage_mode in ("copy", "hardlink")


def test_load_config_overrides(tmp_path):
    p = tmp_path / "cfg.yaml"
    p.write_text("freqmin: 2.0\nfreqmax: 30.0\nmin_coincidence: 5\nstage_mode: hardlink\n")
    c = load_config(p)
    assert c.freqmin == 2.0
    assert c.freqmax == 30.0
    assert c.min_coincidence == 5
    assert c.stage_mode == "hardlink"
    # untouched keys keep defaults
    assert c.sta_seconds == DetectConfig().sta_seconds


def test_load_config_rejects_unknown_key(tmp_path):
    p = tmp_path / "cfg.yaml"
    p.write_text("not_a_real_key: 3\n")
    import pytest
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'DetectConfig'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Write `examples/config.yaml`**

```yaml
# das-events configuration (values shown are the built-in defaults)
freqmin: 1.0
freqmax: 40.0
sta_seconds: 0.5
lta_seconds: 10.0
thr_on: 4.0
min_coincidence: 4
min_duration_seconds: 0.2
merge_gap_seconds: 1.0
channel_decimation: 4
channel_min: 0
channel_max: null
pad_seconds: 60.0
stage_mode: copy
sta_lat: 30.28787
sta_lon: 101.27760
catalog_radius_km: 800.0
catalog_min_mag: 1.5
catalog_tol_seconds: 120.0
```

- [ ] **Step 6: Commit**

```bash
git add src/das_events/config.py examples/config.yaml tests/test_config.py
git commit -m "feat(config): DetectConfig dataclass + YAML loader"
```

---

## Task 5: detect — characteristic function

**Files:**
- Create: `src/das_events/detect.py`
- Test: `tests/test_detect.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from das_events.detect import bandpass_channel, characteristic_function


def test_bandpass_removes_dc():
    fs = 100.0
    x = np.ones(1000) + np.sin(2 * np.pi * 10 * np.arange(1000) / fs)
    y = bandpass_channel(x, fs, 1.0, 40.0)
    assert abs(y.mean()) < 0.05          # DC removed
    assert y.std() > 0.3                  # 10 Hz tone preserved


def test_cf_rises_at_transient():
    fs = 100.0
    n = 2000
    x = np.random.default_rng(0).normal(0, 0.02, n)
    t = np.arange(-60, 60)
    x[900:900 + 120] += 5 * np.exp(-(t / 18.0) ** 2) * np.sin(2 * np.pi * 10 * t / fs)
    cf = characteristic_function(x, fs, sta=0.5, lta=10.0)
    assert cf.shape == (n,)
    assert cf[900:1100].max() > cf[200:700].max() * 2   # clear rise at the event
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detect.py -q`
Expected: FAIL — `ImportError: cannot import name 'bandpass_channel'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_detect.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/detect.py tests/test_detect.py
git commit -m "feat(detect): bandpass + recursive STA/LTA characteristic function"
```

---

## Task 6: detect — coincidence detection over a file

**Files:**
- Modify: `src/das_events/detect.py`
- Test: `tests/test_detect.py`

- [ ] **Step 1: Write the failing test (append)**

```python
from datetime import datetime
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(freqmin=1.0, freqmax=40.0, sta_seconds=0.2, lta_seconds=2.0,
                thr_on=3.0, min_coincidence=4, min_duration_seconds=0.1,
                merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_detect_finds_injected_event(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    dets = detect_file(das, _cfg())
    assert len(dets) == 1
    d = dets[0]
    # event injected at sample 1200 == +12 s from 06:45:00
    assert abs((d.t_peak.timestamp() - das.time_at(1200).timestamp())) < 2.0
    assert d.peak_coincidence >= 4
    assert len(d.channel_indices) >= 4


def test_detect_quiet_file_returns_nothing(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040646.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 46), n_time=2000, n_ch=20, fs=100.0)
    das = read_h5(p)
    assert detect_file(das, _cfg()) == []


def test_detect_rejects_single_channel_glitch(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040647.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 47), n_time=2000, n_ch=20,
                   fs=100.0, event_sample=1200, event_channels=[5])
    das = read_h5(p)
    assert detect_file(das, _cfg(min_coincidence=4)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detect.py -q`
Expected: FAIL — `ImportError: cannot import name 'detect_file'`.

- [ ] **Step 3: Write minimal implementation (append to `detect.py`)**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_detect.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/detect.py tests/test_detect.py
git commit -m "feat(detect): coincidence detection over a minute-file"
```

---

## Task 7: features — spectral, depth-range, time-of-day, P-S

**Files:**
- Create: `src/das_events/features.py`
- Test: `tests/test_features.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime
import numpy as np
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from das_events.features import extract_features
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(sta_seconds=0.2, lta_seconds=2.0, thr_on=3.0, min_coincidence=4,
                min_duration_seconds=0.1, merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_features_recover_dominant_frequency(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20), event_freq=15.0)
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    assert 10.0 < f.dom_freq_hz < 20.0          # ~15 Hz
    assert f.n_channels >= 4


def test_features_depth_range_from_channels(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(0, 8))
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    # channels 0..7 -> depths up to ~28 m (dx=4); should not span the full borehole
    assert f.depth_min_m >= 0.0
    assert f.depth_max_m <= 40.0


def test_features_local_time_of_day_is_utc_plus_8(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    d = detect_file(das, _cfg())[0]
    f = extract_features(das, d, _cfg())
    # 06:45 UTC -> 14:45 local (UTC+8)
    assert f.local_time_of_day.startswith("14:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_features.py -q`
Expected: FAIL — `ImportError: cannot import name 'extract_features'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_features.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/features.py tests/test_features.py
git commit -m "feat(features): spectral, depth-range, time-of-day, P-S features"
```

---

## Task 8: waterfall — per-event plot

**Files:**
- Create: `src/das_events/waterfall.py`
- Test: `tests/test_waterfall.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime
from das_events.io import read_h5
from das_events.waterfall import plot_waterfall
from conftest import write_synth_h5


def test_plot_waterfall_writes_png(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    out = tmp_path / "wf.png"
    plot_waterfall(das, out_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_plot_waterfall_time_window(tmp_path):
    p = tmp_path / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5"
    write_synth_h5(p, datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    das = read_h5(p)
    out = tmp_path / "wf2.png"
    plot_waterfall(das, t0=das.time_at(1000), t1=das.time_at(1400), out_path=out)
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_waterfall.py -q`
Expected: FAIL — `ImportError: cannot import name 'plot_waterfall'`.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_waterfall.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/waterfall.py tests/test_waterfall.py
git commit -m "feat(waterfall): per-event channel x time plot"
```

---

## Task 9: select — detections → minute-file upload set

**Files:**
- Create: `src/das_events/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from das_events.io import FileMeta
from das_events.select import select_files


def _fm(ts, name):
    return FileMeta(path=name, well="JJK", depth_m=80, gauge_length_m=8, dx_m=4,
                    raw_hz=5000, out_hz=100, start_time=ts)


def _dt(minute, second=0):
    return datetime(2025, 1, 4, 6, minute, second, tzinfo=timezone.utc)


FILES = [
    _fm(_dt(44), "f44.h5"),
    _fm(_dt(45), "f45.h5"),
    _fm(_dt(46), "f46.h5"),
]


def test_event_midfile_selects_only_its_file():
    dets = [dict(event_id="e1", t_start=_dt(45, 20), t_end=_dt(45, 25))]
    sel = select_files(dets, FILES, pad_seconds=5.0)
    assert set(sel) == {"f45.h5"}
    assert sel["f45.h5"] == ["e1"]


def test_event_near_edge_pulls_adjacent_file():
    dets = [dict(event_id="e2", t_start=_dt(45, 58), t_end=_dt(45, 59))]
    sel = select_files(dets, FILES, pad_seconds=30.0)  # +pad crosses into 06:46
    assert set(sel) == {"f45.h5", "f46.h5"}


def test_event_near_start_pulls_previous_file():
    dets = [dict(event_id="e3", t_start=_dt(45, 2), t_end=_dt(45, 3))]
    sel = select_files(dets, FILES, pad_seconds=30.0)  # -pad crosses into 06:44
    assert set(sel) == {"f44.h5", "f45.h5"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_select.py -q`
Expected: FAIL — `ImportError: cannot import name 'select_files'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Map detections to the set of minute-files needed to capture them (+pad)."""

from datetime import timedelta

_FILE_SECONDS = 60.0


def select_files(detections, files, pad_seconds: float) -> dict:
    """Return {file_path: [event_id, ...]} for every minute-file overlapping
    any padded detection window.

    ``detections`` is an iterable of mappings with keys
    ``event_id``, ``t_start``, ``t_end`` (UTC datetimes).
    ``files`` is an iterable of FileMeta. Each file covers
    [start_time, start_time + 60 s).
    """
    selection: dict = {}
    spans = [(fm, fm.start_time,
              fm.start_time + timedelta(seconds=_FILE_SECONDS)) for fm in files]
    for det in detections:
        w0 = det["t_start"] - timedelta(seconds=pad_seconds)
        w1 = det["t_end"] + timedelta(seconds=pad_seconds)
        for fm, f0, f1 in spans:
            if f0 < w1 and w0 < f1:          # interval overlap
                selection.setdefault(fm.path, [])
                if det["event_id"] not in selection[fm.path]:
                    selection[fm.path].append(det["event_id"])
    return selection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_select.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/select.py tests/test_select.py
git commit -m "feat(select): map detections to minute-file upload set with pad"
```

---

## Task 10: stage — copy/hardlink + sha256 manifest

**Files:**
- Create: `src/das_events/stage.py`
- Test: `tests/test_stage.py`

- [ ] **Step 1: Write the failing test**

```python
import csv
import hashlib
from das_events.stage import stage_files, ManifestRow


def _write(p, content=b"das-bytes"):
    p.write_bytes(content)
    return p


def test_stage_copy_creates_files_and_manifest(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    out = tmp_path / "staging"
    a = _write(src / "f45.h5", b"AAA")
    b = _write(src / "f46.h5", b"BBBB")
    selection = {str(a): ["e1"], str(b): ["e1", "e2"]}
    rows = stage_files(selection, out, mode="copy")
    assert (out / "f45.h5").read_bytes() == b"AAA"
    assert (out / "f46.h5").read_bytes() == b"BBBB"
    by_name = {r.source.split("\\")[-1].split("/")[-1]: r for r in rows}
    assert by_name["f45.h5"].size == 3
    assert by_name["f45.h5"].sha256 == hashlib.sha256(b"AAA").hexdigest()
    assert by_name["f46.h5"].event_ids == "e1;e2"


def test_stage_writes_manifest_csv(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    out = tmp_path / "staging"
    a = _write(src / "f45.h5", b"AAA")
    rows = stage_files({str(a): ["e1"]}, out, mode="copy")
    from das_events.stage import write_manifest
    man = out / "manifest.csv"
    write_manifest(rows, man)
    got = list(csv.DictReader(man.open()))
    assert got[0]["event_ids"] == "e1"
    assert got[0]["sha256"] == rows[0].sha256
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stage.py -q`
Expected: FAIL — `ImportError: cannot import name 'stage_files'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Stage selected minute-files locally and write a sha256 manifest."""

import csv
import hashlib
import os
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ManifestRow:
    source: str
    staged: str
    size: int
    sha256: str
    event_ids: str        # ";"-joined


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_files(selection: dict, out_dir, mode: str = "copy") -> list:
    """Copy or hardlink each selected file into ``out_dir``.

    ``selection`` is {source_path: [event_id, ...]} (from select.select_files).
    Returns a list of ManifestRow. ``mode`` is "copy" or "hardlink".
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for src, event_ids in selection.items():
        src_p = Path(src)
        dst = out / src_p.name
        if mode == "hardlink":
            if dst.exists():
                dst.unlink()
            os.link(src_p, dst)
        elif mode == "copy":
            shutil.copy2(src_p, dst)
        else:
            raise ValueError(f"Unknown stage mode: {mode!r}")
        rows.append(ManifestRow(
            source=str(src_p),
            staged=str(dst),
            size=src_p.stat().st_size,
            sha256=_sha256(src_p),
            event_ids=";".join(event_ids),
        ))
    return rows


def write_manifest(rows, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "staged", "size",
                                          "sha256", "event_ids"])
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stage.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/stage.py tests/test_stage.py
git commit -m "feat(stage): copy/hardlink staging + sha256 manifest"
```

---

## Task 11: catalog — pure time/distance cross-match

**Files:**
- Create: `src/das_events/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from das_events.catalog import match_catalog


def _dt(s):
    return datetime(2025, 1, 4, 6, 45, s, tzinfo=timezone.utc)


CAT = [
    dict(time=_dt(20), mag=4.4, dist_km=105.0, event_id="us6000lgwr"),
    dict(time=_dt(50), mag=3.1, dist_km=300.0, event_id="us0000zzzz"),
]


def test_match_within_tolerance():
    dets = [dict(event_id="e1", t_peak=_dt(22))]
    out = match_catalog(dets, CAT, tol_seconds=5.0)
    assert "us6000lgwr" in out["e1"]
    assert "M4.4" in out["e1"]


def test_no_match_returns_empty_string():
    dets = [dict(event_id="e1", t_peak=_dt(35))]
    out = match_catalog(dets, CAT, tol_seconds=5.0)
    assert out["e1"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_catalog.py -q`
Expected: FAIL — `ImportError: cannot import name 'match_catalog'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Cross-match detections against an earthquake catalog.

``match_catalog`` is a pure function (unit-tested). ``fetch_fdsn_catalog``
is a thin network helper that reuses the JJK find_earthquakes heuristic and
is intentionally not unit-tested.
"""

from datetime import timezone


def match_catalog(detections, catalog, tol_seconds: float) -> dict:
    """Return {event_id: annotation} where annotation names the nearest-in-time
    catalog event within ``tol_seconds`` of t_peak, or "" if none.

    ``catalog`` is an iterable of mappings with keys
    ``time`` (UTC datetime), ``mag``, ``dist_km``, ``event_id``.
    """
    out = {}
    for det in detections:
        tp = det["t_peak"]
        best, best_dt = None, None
        for ev in catalog:
            dt = abs((ev["time"] - tp).total_seconds())
            if dt <= tol_seconds and (best_dt is None or dt < best_dt):
                best, best_dt = ev, dt
        if best is None:
            out[det["event_id"]] = ""
        else:
            out[det["event_id"]] = (
                f"{best['event_id']} M{best['mag']:.1f} "
                f"{best['dist_km']:.0f}km dt={best_dt:.0f}s"
            )
    return out


def fetch_fdsn_catalog(t_start, t_end, sta_lat, sta_lon,
                       radius_km, min_mag, client_name="USGS"):
    """Fetch events from an FDSN client as catalog dicts for match_catalog.

    Returns [] on any network error so the pipeline degrades gracefully.
    """
    try:
        from obspy.clients.fdsn import Client
        from obspy import UTCDateTime
        from obspy.geodetics import gps2dist_azimuth, kilometers2degrees
        client = Client(client_name)
        cat = client.get_events(
            starttime=UTCDateTime(t_start.isoformat()),
            endtime=UTCDateTime(t_end.isoformat()),
            latitude=sta_lat, longitude=sta_lon,
            maxradius=kilometers2degrees(radius_km),
            minmagnitude=min_mag, orderby="time",
        )
    except Exception:
        return []
    out = []
    for ev in cat:
        try:
            o = ev.preferred_origin() or ev.origins[0]
            m = ev.preferred_magnitude() or ev.magnitudes[0]
            dist_m, _, _ = gps2dist_azimuth(o.latitude, o.longitude, sta_lat, sta_lon)
            out.append(dict(
                time=o.time.datetime.replace(tzinfo=timezone.utc),
                mag=m.mag, dist_km=dist_m / 1e3,
                event_id=str(ev.resource_id).split("/")[-1].split("=")[-1].split("&")[0],
            ))
        except Exception:
            continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_catalog.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): pure time cross-match + thin FDSN fetch"
```

---

## Task 12: pipeline — Event assembly, events.csv, orchestration

**Files:**
- Create: `src/das_events/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime
import csv
from das_events.config import DetectConfig
from das_events.pipeline import scan_dir, write_events_csv, EVENT_COLUMNS
from conftest import write_synth_h5


def _cfg(**kw):
    base = dict(sta_seconds=0.2, lta_seconds=2.0, thr_on=3.0, min_coincidence=4,
                min_duration_seconds=0.1, merge_gap_seconds=0.5, channel_decimation=1)
    base.update(kw)
    return DetectConfig(**base)


def test_scan_dir_finds_event_and_builds_event(tmp_path):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040646.h5",
                   datetime(2025, 1, 4, 6, 46), n_time=2000, n_ch=20, fs=100.0)
    events = scan_dir(d, _cfg())
    assert len(events) == 1
    ev = events[0]
    assert ev.event_id.startswith("JJK_2025")
    assert ev.n_channels >= 4
    assert ev.label == ""


def test_write_events_csv_roundtrip(tmp_path):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    events = scan_dir(d, _cfg())
    out = tmp_path / "events.csv"
    write_events_csv(events, out)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0].keys()) == EVENT_COLUMNS
    assert rows[0]["event_id"] == events[0].event_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -q`
Expected: FAIL — `ImportError: cannot import name 'scan_dir'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Orchestration: scan a directory, build Events, read/write events.csv."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .io import read_h5
from .detect import detect_file
from .features import extract_features

EVENT_COLUMNS = [
    "event_id", "t_peak_utc", "t_start_utc", "t_end_utc", "duration_s",
    "peak_ratio", "peak_coincidence", "n_channels", "depth_min_m", "depth_max_m",
    "dom_freq_hz", "bandwidth_hz", "local_time_of_day", "ps_separation_s",
    "source_file", "catalog_match", "label",
]


@dataclass
class Event:
    event_id: str
    t_peak_utc: str
    t_start_utc: str
    t_end_utc: str
    duration_s: float
    peak_ratio: float
    peak_coincidence: int
    n_channels: int
    depth_min_m: float
    depth_max_m: float
    dom_freq_hz: float
    bandwidth_hz: float
    local_time_of_day: str
    ps_separation_s: object        # float | None
    source_file: str
    catalog_match: str
    label: str

    def as_row(self) -> dict:
        return {
            "event_id": self.event_id,
            "t_peak_utc": self.t_peak_utc,
            "t_start_utc": self.t_start_utc,
            "t_end_utc": self.t_end_utc,
            "duration_s": f"{self.duration_s:.3f}",
            "peak_ratio": f"{self.peak_ratio:.3f}",
            "peak_coincidence": self.peak_coincidence,
            "n_channels": self.n_channels,
            "depth_min_m": f"{self.depth_min_m:.1f}",
            "depth_max_m": f"{self.depth_max_m:.1f}",
            "dom_freq_hz": f"{self.dom_freq_hz:.3f}",
            "bandwidth_hz": f"{self.bandwidth_hz:.3f}",
            "local_time_of_day": self.local_time_of_day,
            "ps_separation_s": "" if self.ps_separation_s is None
                               else f"{self.ps_separation_s:.3f}",
            "source_file": self.source_file,
            "catalog_match": self.catalog_match,
            "label": self.label,
        }


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_event(das, detection, cfg) -> Event:
    feats = extract_features(das, detection, cfg)
    eid = "JJK_" + detection.t_peak.strftime("%Y%m%dT%H%M%S")
    dur = (detection.t_end - detection.t_start).total_seconds()
    return Event(
        event_id=eid,
        t_peak_utc=_iso(detection.t_peak),
        t_start_utc=_iso(detection.t_start),
        t_end_utc=_iso(detection.t_end),
        duration_s=dur,
        peak_ratio=detection.peak_ratio,
        peak_coincidence=detection.peak_coincidence,
        n_channels=feats.n_channels,
        depth_min_m=feats.depth_min_m,
        depth_max_m=feats.depth_max_m,
        dom_freq_hz=feats.dom_freq_hz,
        bandwidth_hz=feats.bandwidth_hz,
        local_time_of_day=feats.local_time_of_day,
        ps_separation_s=feats.ps_separation_s,
        source_file=detection.source_file,
        catalog_match="",
        label="",
    )


def scan_dir(data_dir, cfg, progress=None) -> list:
    """Detect events in every .h5 in ``data_dir`` (sorted). Returns list[Event]."""
    files = sorted(Path(data_dir).glob("*.h5"))
    events = []
    for i, fp in enumerate(files):
        if progress:
            progress(i, len(files), fp.name)
        das = read_h5(fp)
        for det in detect_file(das, cfg):
            events.append(_make_event(das, det, cfg))
    events.sort(key=lambda e: e.t_peak_utc)
    return events


def write_events_csv(events, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_COLUMNS)
        w.writeheader()
        for ev in events:
            w.writerow(ev.as_row())


def read_events_csv(path) -> list:
    """Read events.csv back into row dicts (for the stage command)."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/das_events/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): Event assembly + events.csv read/write + scan_dir"
```

---

## Task 13: cli — scan / plot / stage / run

**Files:**
- Create: `src/das_events/cli.py`
- Test: `tests/test_pipeline.py` (CLI smoke tests appended here to reuse fixtures)

- [ ] **Step 1: Write the failing test (append to `tests/test_pipeline.py`)**

```python
from datetime import datetime
from das_events.cli import main
from conftest import write_synth_h5


def test_cli_scan_then_stage(tmp_path, monkeypatch):
    d = tmp_path / "data"; d.mkdir()
    write_synth_h5(d / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5",
                   datetime(2025, 1, 4, 6, 45), n_time=2000, n_ch=20, fs=100.0,
                   event_sample=1200, event_channels=range(20))
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("sta_seconds: 0.2\nlta_seconds: 2.0\nthr_on: 3.0\n"
                   "min_coincidence: 4\nmin_duration_seconds: 0.1\n"
                   "merge_gap_seconds: 0.5\nchannel_decimation: 1\npad_seconds: 5.0\n")
    events_csv = tmp_path / "events.csv"
    rc = main(["scan", str(d), "--config", str(cfg), "--events", str(events_csv)])
    assert rc == 0 and events_csv.exists()

    staging = tmp_path / "staging"
    rc = main(["stage", "--events", str(events_csv), "--data-dir", str(d),
               "--out", str(staging), "--config", str(cfg)])
    assert rc == 0
    assert (staging / "manifest.csv").exists()
    assert (staging / "JJK_80m_8m_4m_5000Hz_100Hz_UTC8_202501040645.h5").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -q`
Expected: FAIL — `ImportError: cannot import name 'main'` from `das_events.cli`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Command-line interface: das-events {scan, plot, stage, run}."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .config import DetectConfig, load_config
from .io import read_h5, parse_filename
from .detect import detect_file
from .pipeline import (scan_dir, write_events_csv, read_events_csv,
                       _make_event, EVENT_COLUMNS)
from .select import select_files
from .stage import stage_files, write_manifest
from .waterfall import plot_waterfall


def _cfg(args) -> DetectConfig:
    return load_config(args.config) if args.config else DetectConfig()


def _progress(i, n, name):
    print(f"  [{i + 1}/{n}] {name}", file=sys.stderr)


def cmd_scan(args) -> int:
    cfg = _cfg(args)
    events = scan_dir(args.data_dir, cfg, progress=_progress)
    write_events_csv(events, args.events)
    print(f"{len(events)} event(s) -> {args.events}")
    if args.plots:
        _plot_events(events, cfg, Path(args.plots))
    return 0


def _plot_events(events, cfg, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for ev in events:
        das = read_h5(ev.source_file)
        t0 = datetime.fromisoformat(ev.t_start_utc.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(ev.t_end_utc.replace("Z", "+00:00"))
        from datetime import timedelta
        plot_waterfall(das, t0=t0 - timedelta(seconds=cfg.pad_seconds),
                       t1=t1 + timedelta(seconds=cfg.pad_seconds),
                       out_path=out_dir / f"{ev.event_id}.png",
                       title=ev.event_id)


def cmd_plot(args) -> int:
    cfg = _cfg(args)
    das = read_h5(args.h5)
    plot_waterfall(das, out_path=args.out, title=Path(args.h5).name)
    print(f"waterfall -> {args.out}")
    return 0


def cmd_stage(args) -> int:
    cfg = _cfg(args)
    rows = read_events_csv(args.events)
    if args.label:
        wanted = set(args.label.split(","))
        rows = [r for r in rows if r["label"] in wanted]
    dets = [dict(event_id=r["event_id"],
                 t_start=datetime.fromisoformat(r["t_start_utc"].replace("Z", "+00:00")),
                 t_end=datetime.fromisoformat(r["t_end_utc"].replace("Z", "+00:00")))
            for r in rows]
    files = [parse_filename(p) for p in Path(args.data_dir).glob("*.h5")]
    selection = select_files(dets, files, cfg.pad_seconds)
    out = Path(args.out)
    manifest_rows = stage_files(selection, out, mode=cfg.stage_mode)
    write_manifest(manifest_rows, out / "manifest.csv")
    print(f"staged {len(manifest_rows)} file(s) -> {out}  (manifest.csv)")
    return 0


def cmd_run(args) -> int:
    cfg = _cfg(args)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    events_csv = out / "events.csv"
    events = scan_dir(args.data_dir, cfg, progress=_progress)
    write_events_csv(events, events_csv)
    _plot_events(events, cfg, out / "waterfall")
    dets = [dict(event_id=e.event_id,
                 t_start=datetime.fromisoformat(e.t_start_utc.replace("Z", "+00:00")),
                 t_end=datetime.fromisoformat(e.t_end_utc.replace("Z", "+00:00")))
            for e in events]
    files = [parse_filename(p) for p in Path(args.data_dir).glob("*.h5")]
    selection = select_files(dets, files, cfg.pad_seconds)
    manifest_rows = stage_files(selection, out / "staging", mode=cfg.stage_mode)
    write_manifest(manifest_rows, out / "staging" / "manifest.csv")
    print(f"{len(events)} event(s); staged {len(manifest_rows)} file(s) -> {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="das-events")
    p.add_argument("--config", help="YAML config file")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="detect events across a directory")
    s.add_argument("data_dir")
    s.add_argument("--events", default="events.csv")
    s.add_argument("--plots", help="also write per-event waterfalls to this dir")
    s.set_defaults(func=cmd_scan)

    pl = sub.add_parser("plot", help="waterfall of one h5 file")
    pl.add_argument("h5")
    pl.add_argument("--out", default="waterfall.png")
    pl.set_defaults(func=cmd_plot)

    st = sub.add_parser("stage", help="stage event-bearing minute-files")
    st.add_argument("--events", required=True)
    st.add_argument("--data-dir", required=True)
    st.add_argument("--out", default="staging")
    st.add_argument("--label", help="comma-separated labels to keep (e.g. earthquake,blast)")
    st.set_defaults(func=cmd_stage)

    r = sub.add_parser("run", help="scan + plot + stage end to end")
    r.add_argument("data_dir")
    r.add_argument("--out", default="out")
    r.set_defaults(func=cmd_run)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

Note: the subcommand functions read `args.config` via `_cfg`, but `--config` is
defined on the top-level parser. `argparse` exposes it on the parsed namespace
for all subcommands, so `args.config` resolves correctly.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -q`
Expected: PASS (all pipeline + CLI tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS (all tests across all modules green).

- [ ] **Step 6: Commit**

```bash
git add src/das_events/cli.py tests/test_pipeline.py
git commit -m "feat(cli): scan/plot/stage/run commands"
```

---

## Task 14: README + end-to-end smoke on real data (manual)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Flesh out `README.md`**

Document install (`pip install -e .`), the four CLI commands with examples, the
config keys (point to `examples/config.yaml`), the `events.csv` columns, and the
review workflow: run `scan --plots`, eyeball waterfalls, fill the `label` column,
then `stage --label earthquake,blast`.

- [ ] **Step 2: Manual smoke test on a real session**

Run:
```bash
cd /d/Projects/das-events
das-events scan /d/Projects/JJK/data/20260616/h5_file \
    --config examples/config.yaml --events out/events.csv --plots out/waterfall
```
Expected: completes without error; `out/events.csv` written; PNGs in
`out/waterfall/`. Inspect a few waterfalls and the CSV; tune `thr_on`,
`min_coincidence`, `freqmin/freqmax`, `channel_decimation` in the config as
needed (these defaults are starting points to calibrate on real data).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README usage + review workflow"
```

---

## Self-Review

**Spec coverage:**
- §2 input format → Task 2 (filename), Task 3 (h5 read + attrs + depths + µs time). ✓
- §3 data flow → Task 12/13 orchestration. ✓
- §4 detector (per-channel STA/LTA + coincidence, boundary pad) → Task 5/6 (detect), Task 9 (pad in select). ✓
- §5 features (all listed fields incl. catalog_match, label) → Task 7 (features), Task 11 (catalog_match), Task 12 (label column). ✓
- §6 outputs (events.csv, waterfall PNGs, staging/, manifest.csv) → Task 12, 8, 10, 13. ✓
- §7 module layout → all module tasks. ✓
- §8 CLI (scan/plot/stage/run + YAML config) → Task 4, 13. ✓
- §9 testing → every task is TDD; synthetic h5 fixture in Task 1. ✓
- §10 notes: `event_id` format `JJK_<YYYYMMDDTHHMMSS>` (Task 12); copy/hardlink modes (Task 10); robust percentile clip (Task 8); catalog logic ported, no JJK-script dependency (Task 11). Bad-channel dropping is the one §10 *optional* note deliberately deferred (YAGNI; `channel_min/max` + decimation already bound the channel set; revisit after real-data calibration in Task 14).

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test shows assertions. ✓

**Type consistency:** `DasData.time_at`, `Detection` fields, `EventFeatures` fields, `Event`/`EVENT_COLUMNS`, `ManifestRow`, `select_files`/`stage_files`/`match_catalog` signatures are defined once and used with identical names downstream. CLI imports only symbols defined in earlier tasks (`scan_dir`, `write_events_csv`, `read_events_csv`, `_make_event`, `select_files`, `stage_files`, `write_manifest`, `plot_waterfall`, `parse_filename`, `read_h5`). ✓
