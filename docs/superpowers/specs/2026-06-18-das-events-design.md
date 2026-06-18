# das-events — Design Spec

**Date:** 2026-06-18
**Status:** Approved (design phase)
**Repo:** `D:\Projects\das-events` (sibling to `das-dvv`), module `das_events`

## 1. Purpose

The Jiakika (JJK) borehole DAS produces per-minute HDF5 files at high volume
(60000 samples × ~834 channels per minute, 1000 Hz strain rate). Uploading
every file to a server is impractical. `das-events` scans a directory of these
files, **data-drives event detection** directly on the DAS waterfall, records
discriminating features and a per-event waterfall plot so a human can label each
event as earthquake vs. blast, then **stages only the event-bearing minute-files
locally** with a manifest for upload by any transport.

Non-goals (YAGNI):
- No built-in network transfer (SSH/rsync/S3). The package stages files + a
  manifest; the user moves them. Transport-agnostic by design.
- No automated earthquake/blast classifier. The package surfaces features and
  waterfalls; the human makes the call.
- No ML / template matching in v1.

## 2. Input data format

ZD-DAS / "Smart Earth Sensing" PRODML-style HDF5, one file per minute.

- `Acquisition/Raw[0]/RawData` — `(n_time, n_channels)` float32 strain rate
  (`(nm/m)/s * Hz/m`); typically (60000, 834).
- `Acquisition/Raw[0]/RawDataTime` — `(n_time,)` int64 **microsecond** UTC
  timestamps.
- Useful attrs:
  - `Acquisition`: `GaugeLength`, `SpatialSamplingInterval`,
    `MeasurementStartTime` (ISO 8601 UTC), `PulseRate`, `NumberOfLoci`,
    `StartLocusIndex`.
  - `Acquisition/Raw[0]`: `OutputDataRate` (Hz), `RawDataUnit`, `StartLocusIndex`.
- Filename encodes metadata:
  `JJK_<depth>m_<GL>m_<dx>m_<rawHz>Hz_<outHz>Hz_UTC8_<YYYYMMDDHHMM>.h5`
  e.g. `JJK_3410m_8m_4m_5000Hz_1000Hz_UTC8_202501040645.h5`.

Metadata is read from h5 attrs first, with the filename as a fallback /
cross-check. Channel depth = `StartLocusIndex` + index × `SpatialSamplingInterval`.

## 3. Data flow

```
data_dir/*.h5 ──▶ detect ──▶ features + waterfall PNG ──▶ events.csv
                                                              │
                                          (human review/label)┘
                                                              ▼
                                  select minute-files (+pad) ──▶ staging/ + manifest.csv
```

## 4. Detector

**Chosen approach: per-channel STA/LTA + coincidence.**

1. Read a minute-file. Optionally decimate channels (process every Nth channel,
   configurable) and restrict to a channel/depth range to control cost.
2. Bandpass each retained channel (configurable corners, default ~1–40 Hz).
3. Build a characteristic function per channel (default: recursive STA/LTA on the
   squared/abs signal via `obspy.signal.trigger.recursive_sta_lta`).
4. Per channel, mark samples where STA/LTA exceeds the on-threshold.
5. **Coincidence trace** = number of channels triggered at each sample. An event
   is declared where the coincidence count crosses a configurable minimum (e.g.
   ≥ N channels) for at least a minimum duration.
6. Merge nearby triggers into single events (configurable gap).

This yields detection plus a free spatial feature (how many / which channels lit
up).

Rejected alternatives:
- *Pure channel-stack STA/LTA*: simplest/fastest but washes out few-channel
  events and lets single-channel glitches through.
- *ML / template matching*: overkill for v1.

**Boundary handling:** a trigger within `pad_seconds` of a file edge pulls the
adjacent minute-file into the upload set (mirrors `das_phases.suggest_h5_window`
pad logic). Detection itself is per-file; cross-file event continuity is handled
at the *selection* stage, not by stitching raw data.

**Performance:** files are processed independently with multiprocessing.
Channel decimation and optional time decimation of the CF keep multi-day
sessions tractable.

## 5. Per-event features

Recorded in `events.csv`, one row per event, to support the human earthquake vs.
blast decision:

- `event_id` (stable, derived from peak UTC time)
- `t_peak_utc`, `t_start_utc`, `t_end_utc`, `duration_s`
- `peak_ratio` (max STA/LTA), `peak_coincidence` (max # channels triggered)
- `n_channels`, `depth_min_m`, `depth_max_m` of triggered channels
  (shallow-only ⇒ surface-blast moveout; full-borehole ⇒ deep earthquake)
- `dom_freq_hz`, `bandwidth_hz` (spectral centroid + spread)
- `local_time_of_day` (UTC+8; blasts cluster in working hours)
- `ps_separation_s` (rough P–S delay if a second arrival is visible; else blank)
- `source_files` (minute-file(s) the event spans)
- `catalog_match` (optional): event id / distance / magnitude if it matches an
  FDSN catalog within a tolerance. Annotation only — detection stays
  data-driven. Reuses logic from `JJK/code/find_earthquakes.py`.
- `label` (blank; human fills in `earthquake` / `blast` / `noise`)

## 6. Outputs

- `events.csv` — detection catalog (all features above).
- `waterfall/<event_id>.png` — channel × time waterfall around each event
  (window = event ± pad), amplitude clipped to a robust percentile.
- `staging/` — copies (or hardlinks, configurable) of the selected minute-files,
  ready to upload.
- `manifest.csv` — one row per staged file: source path, staged path, byte size,
  sha256, triggering `event_id`(s).

## 7. Module layout (mirrors das-dvv)

```
das-events/
  pyproject.toml          # name das-events, script das-events = das_events.cli:main
  README.md
  src/das_events/
    __init__.py
    io.py        # h5 read, attr + filename parsing, UTC time handling, channel depths
    config.py    # YAML config + dataclass defaults
    detect.py    # CF + per-channel STA/LTA + coincidence
    features.py  # spectral / moveout / time-of-day extraction
    catalog.py   # optional FDSN cross-match (reuses find_earthquakes logic)
    waterfall.py # plotting
    select.py    # detections -> minute-file set (+pad)
    stage.py     # copy/hardlink + manifest + checksums
    pipeline.py  # orchestration (scan -> detect -> features -> plot -> stage)
    cli.py       # das-events {scan,plot,stage,run}
  tests/
  examples/
```

Dependencies (same family as das-dvv): `numpy`, `scipy`, `h5py`, `obspy`,
`matplotlib`, `PyYAML`. Optional `rich` for console tables (already used by the
JJK scripts). Python ≥ 3.11.

## 8. CLI

- `das-events scan <data_dir> [--config cfg.yaml] [--plots]`
  → detect events across all h5 in dir, write `events.csv` (+ waterfalls).
- `das-events plot <event_id | h5_file>` → render a waterfall.
- `das-events stage --events events.csv --out staging/ [--label earthquake,blast]`
  → select minute-files (+pad) for the chosen labels/events, copy to `staging/`,
  write `manifest.csv`.
- `das-events run <data_dir> --out out/` → full pipeline end to end from config.

A YAML config (`config.py` dataclass + loader) holds: bandpass corners, STA/LTA
windows, on/off thresholds, coincidence minimum, min event duration, merge gap,
channel decimation + depth range, `pad_seconds`, output paths, stage mode
(copy/hardlink), optional catalog cross-match params (station lat/lon, radius,
min mag).

## 9. Testing (TDD)

- **io**: filename parser (all fields), attr parsing, microsecond-UTC → datetime,
  channel-depth computation. Synthetic in-memory/temp h5.
- **detect**: synthetic h5 with an injected transient on a band of channels →
  detector returns one event at the correct time and channel range; pure noise →
  no events; single-channel glitch → rejected by coincidence.
- **select**: trigger near file edge pulls in the adjacent minute-file; triggers
  far from edges do not; overlapping events de-duplicated.
- **stage**: manifest rows match staged files; sha256 correct; copy vs hardlink
  modes both work.
- **features**: dominant frequency recovered from a known sinusoid; depth-range
  reflects injected channel band; time-of-day from a known UTC timestamp.

## 10. Open implementation notes (defaults, not blockers)

- Bad/dead channels: optionally drop channels whose variance is near zero or
  extreme before detection (configurable).
- Waterfall amplitude scaling: robust percentile clip (e.g. 1–99%) per event.
- `event_id` format: `JJK_<YYYYMMDDTHHMMSS>` from peak UTC time.
- The existing `find_earthquakes.py` / `das_phases.py` stay where they are; only
  detection-relevant logic is ported into `catalog.py` (cross-match) — no hard
  dependency on the JJK scripts.
