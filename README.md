# das-events

Detect seismic events in per-minute DAS (Distributed Acoustic Sensing) HDF5
files and **stage only the event-bearing minute-files** for selective upload —
so you don't have to ship a whole multi-day, multi-terabyte session to a server.

Built for the Jiakika (JJK) borehole ZD-DAS dataset (per-minute files,
~60000 samples × ~834 channels, 1000 Hz strain rate), but works on any
PRODML-style ZD-DAS HDF5.

## What it does

```
data_dir/*.h5 ──▶ detect ──▶ features + waterfall PNG ──▶ events.csv
                                                              │
                                          (you review/label) ─┘
                                                              ▼
                                  select minute-files (+pad) ──▶ staging/ + manifest.csv
```

1. **Detect** — per-channel band-pass + STA/LTA with channel **coincidence**
   (an event must light up several channels at once, which rejects
   single-channel glitches).
2. **Describe** — for every detection it records discriminating features and
   renders a channel × time waterfall, so *you* make the final
   earthquake-vs-blast call (no black-box classifier).
3. **Stage** — copies (or hard-links) only the minute-files that contain events
   (plus a time pad that pulls in adjacent files) into a `staging/` directory
   with a checksummed `manifest.csv`. Upload that directory however you like.

## Install

```bash
cd das-events
pip install -e .
```

Requires Python ≥ 3.11 and: numpy, scipy, h5py, obspy, matplotlib, PyYAML.

## Quick start

```bash
# 1. Detect events across a session directory and render waterfalls
das-events scan /path/to/h5_dir --config examples/config.yaml \
    --events out/events.csv --plots out/waterfall

# 2. Review out/waterfall/*.png, then fill the `label` column in events.csv
#    with earthquake / blast / noise

# 3. Stage only the files for the events you kept
das-events stage --events out/events.csv --data-dir /path/to/h5_dir \
    --out out/staging --label earthquake,blast --config examples/config.yaml
```

Or run the whole pipeline in one shot (scan → plot → stage everything):

```bash
das-events run /path/to/h5_dir --config examples/config.yaml --out out/
```

Plot a single file's waterfall:

```bash
das-events plot /path/to/one_file.h5 --out wf.png
```

> Note: `--config` goes **after** the subcommand
> (`das-events scan DIR --config cfg.yaml`).

## Commands

| Command | Purpose |
|---------|---------|
| `scan DATA_DIR [--events CSV] [--plots DIR] [--catalog]` | Detect events in every `*.h5`, write `events.csv` (+ optional waterfalls). |
| `plot H5 [--out PNG]` | Waterfall of a single file. |
| `stage --events CSV --data-dir DIR [--out DIR] [--label L1,L2]` | Select event-bearing minute-files (+pad), copy/hardlink to `staging/`, write `manifest.csv`. |
| `run DATA_DIR [--out DIR] [--catalog]` | scan + plot + stage end to end. |

`--catalog` annotates the `catalog_match` column by cross-matching each
detection against the USGS FDSN catalog (needs network; degrades to blank
offline). Without it, `catalog_match` is left blank.

## Configuration

All knobs live in a YAML file (see [`examples/config.yaml`](examples/config.yaml));
omitted keys fall back to the built-in defaults. Key parameters:

| Key | Default | Meaning |
|-----|---------|---------|
| `freqmin` / `freqmax` | 1.0 / 40.0 | Band-pass corners (Hz). |
| `sta_seconds` / `lta_seconds` | 0.5 / 10.0 | STA/LTA windows. |
| `thr_on` | 4.0 | STA/LTA trigger threshold (per channel). |
| `min_coincidence` | 4 | Channels that must trigger simultaneously to declare an event. |
| `min_duration_seconds` | 0.2 | Reject triggers shorter than this. |
| `merge_gap_seconds` | 1.0 | Merge triggers separated by less than this. |
| `edge_skip_seconds` | 1.0 | Ignore triggers within this margin of each file edge (see below). |
| `channel_decimation` | 4 | Use every Nth channel for detection (speed vs. sensitivity). |
| `channel_min` / `channel_max` | 0 / all | Restrict the channel (depth) range. |
| `pad_seconds` | 60.0 | Time pad around each event when selecting minute-files. |
| `stage_mode` | `copy` | `copy` or `hardlink` (hardlink saves space but needs same volume). |
| `catalog_*`, `sta_lat`, `sta_lon` | — | Optional FDSN cross-match (annotation only). |

These defaults are **starting points to calibrate on real data**. Raise
`thr_on` / `min_coincidence` if you get too many detections; lower them if you
miss known events.

## `events.csv` columns

`event_id`, `t_peak_utc`, `t_start_utc`, `t_end_utc`, `duration_s`,
`peak_ratio`, `peak_coincidence`, `n_channels`, `depth_min_m`, `depth_max_m`,
`dom_freq_hz`, `bandwidth_hz`, `local_time_of_day` (UTC+8), `ps_separation_s`,
`source_file`, `catalog_match`, `label`.

The `label` column is left blank — fill it in during review. Reading the
features helps the call: a **surface blast** tends to be shallow-channel-heavy,
impulsive, daytime, and recurring at regular times; a **regional earthquake**
typically lights up the full borehole with a visible P–S separation.

## Notes / known limitations

- **File-boundary edge transient.** Zero-phase band-pass filtering produces a
  large transient (~10× the mid-file amplitude) at the very start and end of
  each independently-processed minute-file, which would otherwise fire one
  spurious full-borehole detection per file. `edge_skip_seconds` (default 1 s)
  suppresses it. The cost is that a *genuine* event in the first/last second of
  a file may be missed; lower `edge_skip_seconds` if your files are short.
- **Waterfall pad truncation.** Per-event waterfalls load only the event's own
  `source_file`, so the pad region that extends into an adjacent minute-file is
  clipped in the *plot*. The *staged data* is complete (the adjacent file is
  included), only the visual is truncated.
- **Catalog cross-match is optional and annotation-only.** Detection is purely
  data-driven; the `--catalog` flag labels which detections coincide with
  cataloged FDSN events and degrades gracefully offline. Without the flag,
  `catalog_match` stays blank.
- **Detection is currently single-threaded.** Each minute-file takes ~1 s, so a
  multi-day session (thousands of files) can take tens of minutes. Files are
  processed independently, so this is a natural candidate for parallelisation
  in a future version; `scan_dir` skips unreadable files with a warning so a
  long run survives the occasional corrupt file.
