# das-events

Detect seismic events in per-minute **DAS** (Distributed Acoustic Sensing) HDF5 files and stage only the event-bearing minute-files for selective upload.
从逐分钟的 **DAS**（分布式声学传感）HDF5 数据中检测地震/爆破事件，只挑出含事件的分钟文件用于按需上传。

**Pipeline / 流水线:** scan h5 → detect (STA/LTA + channel coincidence) → features + waterfall → review/label → stage event-bearing files + manifest
扫描 h5 → 检测（STA/LTA + 多道符合）→ 特征 + 瀑布图 → 人工复核/标注 → 暂存含事件文件 + 清单

🌐 **[English](#english)** | **[中文](#中文)**

---

<a name="english"></a>

## English

### Features

- **Data-driven detection** straight from the DAS waterfall — finds both earthquakes and local blasts, including events in no public catalog.
- Per-channel band-pass + **STA/LTA with channel coincidence**, so an event must light up several channels at once (rejects single-channel glitches).
- **Per-event features + waterfall PNG** for human earthquake-vs-blast review — no black-box classifier.
- **Selective staging**: copies (or hard-links) only the minute-files that contain events (plus a time pad pulling in adjacent files) with a checksummed `manifest.csv`. Transport-agnostic — upload the staging directory however you like.
- Optional **FDSN catalog cross-match** to annotate which detections coincide with cataloged events.
- Use it as a YAML-driven **CLI** or as a **Python library**.

### Install

```bash
git clone https://github.com/yjianggeo/das-events.git
cd das-events
pip install -e .
```

Requires Python ≥ 3.11. Dependencies: numpy, scipy, h5py, obspy, matplotlib, PyYAML.

> **Note:** the `das-events` console script is installed into your Python `Scripts/` directory. If that directory is not on your `PATH`, run the CLI as `python -m das_events.cli ...` instead of `das-events ...`.

### Input data

ZD-DAS / PRODML-style HDF5, **one file per minute**. Each file holds
`Acquisition/Raw[0]/RawData` (`n_time × n_channels` float32 strain rate) and
`RawDataTime` (int64 microsecond UTC). Metadata (gauge length, channel spacing,
output rate, start time) is read from the HDF5 attributes, with the filename as
a fallback:

```
JJK_<depth>m_<GL>m_<dx>m_<rawHz>Hz_<outHz>Hz_UTC8_<YYYYMMDDHHMM>.h5
e.g. JJK_3400m_8m_4m_5000Hz_1000Hz_UTC8_202606161133.h5
```

The 12-digit timestamp is treated as UTC (it matches the file's
`MeasurementStartTime`).

### Workflow

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

Run the whole pipeline in one shot (scan → plot → stage everything):

```bash
das-events run /path/to/h5_dir --config examples/config.yaml --out out/
```

Plot a single file's waterfall:

```bash
das-events plot /path/to/one_file.h5 --out wf.png
```

> `--config` goes **after** the subcommand (`das-events scan DIR --config cfg.yaml`).

### Commands

| Command | Purpose |
|---------|---------|
| `scan DATA_DIR [--events CSV] [--plots DIR] [--catalog]` | Detect events in every `*.h5`, write `events.csv` (+ optional waterfalls). |
| `plot H5 [--out PNG]` | Waterfall of a single file. |
| `stage --events CSV --data-dir DIR [--out DIR] [--label L1,L2]` | Select event-bearing minute-files (+pad), copy/hardlink to `staging/`, write `manifest.csv`. |
| `run DATA_DIR [--out DIR] [--catalog]` | scan + plot + stage end to end. |

`--catalog` annotates the `catalog_match` column via a USGS FDSN cross-match (needs network; degrades to blank offline).

### Configuration reference

A run is driven by one YAML file (see `examples/config.yaml`); omitted keys fall back to the built-in defaults.

| Key | Meaning | Default |
|-----|---------|---------|
| `freqmin`, `freqmax` | Band-pass corners (Hz) | `1.0`, `40.0` |
| `sta_seconds`, `lta_seconds` | STA / LTA windows (s) | `0.5`, `10.0` |
| `thr_on` | Per-channel STA/LTA trigger threshold | `4.0` |
| `min_coincidence` | Channels that must trigger at once | `4` |
| `min_duration_seconds` | Reject triggers shorter than this | `0.2` |
| `merge_gap_seconds` | Merge triggers closer than this | `1.0` |
| `edge_skip_seconds` | Ignore triggers within this margin of each file edge | `1.0` |
| `channel_decimation` | Use every Nth channel for detection | `4` |
| `channel_min`, `channel_max` | Restrict the channel (depth) range | `0`, all |
| `pad_seconds` | Time pad around each event when selecting files | `60.0` |
| `stage_mode` | `copy` \| `hardlink` | `copy` |
| `sta_lat`, `sta_lon` | Station coordinates (catalog match) | JJK |
| `catalog_radius_km`, `catalog_min_mag`, `catalog_tol_seconds` | FDSN cross-match params | `800`, `1.5`, `120` |

These defaults are **starting points to calibrate on real data**. Raise `thr_on` / `min_coincidence` if you get too many detections; lower them if you miss known events.

### `events.csv` columns

`event_id`, `t_peak_utc`, `t_start_utc`, `t_end_utc`, `duration_s`,
`peak_ratio`, `peak_coincidence`, `n_channels`, `depth_min_m`, `depth_max_m`,
`dom_freq_hz`, `bandwidth_hz`, `local_time_of_day` (UTC+8), `ps_separation_s`,
`source_file`, `catalog_match`, `label`.

`label` is left blank — fill it during review. The features guide the call: a
**surface blast** tends to be shallow-channel-heavy, impulsive, daytime, and
recurring at regular times; a **regional earthquake** typically lights up the
full borehole with a visible P–S separation.

### Library API

```python
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from das_events.features import extract_features
from das_events.waterfall import plot_waterfall

das = read_h5("JJK_3400m_8m_4m_5000Hz_1000Hz_UTC8_202606161133.h5")
cfg = DetectConfig(thr_on=4.0, min_coincidence=4)

for det in detect_file(das, cfg):
    feats = extract_features(das, det, cfg)
    print(det.t_peak, feats.dom_freq_hz, feats.depth_min_m, feats.depth_max_m)

plot_waterfall(das, out_path="wf.png")
```

Full-directory pipeline:

```python
from das_events.config import load_config
from das_events.pipeline import scan_dir, write_events_csv

cfg = load_config("examples/config.yaml")
events = scan_dir("data/h5_dir", cfg)
write_events_csv(events, "events.csv")
```

### Modules

| Module | Responsibility |
|--------|----------------|
| `io` | Read ZD-DAS h5 into `DasData`; parse filenames; channel depths; UTC times |
| `config` | `DetectConfig` dataclass + YAML loader |
| `detect` | Band-pass + recursive STA/LTA + channel-coincidence detection |
| `features` | Spectral, depth-range, time-of-day, P–S features per event |
| `waterfall` | Per-event channel × time plot |
| `select` | Map detections → minute-file upload set (+pad) |
| `stage` | Copy / hard-link staging + sha256 `manifest.csv` |
| `catalog` | Pure time cross-match + thin FDSN fetch |
| `pipeline` / `cli` | `Event` assembly, `events.csv` I/O, orchestration, CLI |

### Notes & limitations

- **File-boundary edge transient.** Zero-phase band-pass filtering produces a large transient (~10× mid-file amplitude) at the start/end of each independently-processed minute-file, which would otherwise fire one spurious full-borehole detection per file. `edge_skip_seconds` (default 1 s) suppresses it; a genuine event in the first/last second of a file may then be missed.
- **Waterfall pad truncation.** Per-event waterfalls load only the event's own `source_file`, so the pad region spilling into an adjacent minute-file is clipped in the *plot* — the *staged data* is complete.
- **Single-threaded.** Each minute-file takes ~1 s, so a multi-day session (thousands of files) can take tens of minutes; `scan_dir` skips unreadable files with a warning so a long run survives a corrupt file. Parallelisation is a natural future addition.
- **Catalog match is optional and annotation-only.** Detection is purely data-driven; `--catalog` just labels coincidences and degrades gracefully offline.

### License

MIT

---

<a name="中文"></a>

## 中文

### 功能特性

- **数据驱动检测**，直接作用于 DAS 瀑布图——既能找到地震，也能找到本地爆破，包括任何公开目录里都没有的事件。
- 逐道带通 + **STA/LTA 多道符合检测**：一个事件必须同时触发多道才被认定（剔除单道毛刺）。
- 为每个事件输出**特征 + 瀑布图 PNG**，供人工判别地震/爆破——不用黑盒分类器。
- **选择性暂存**：只复制（或硬链接）含事件的分钟文件（外加时间余量带入相邻文件），并生成带校验和的 `manifest.csv`。与传输方式无关——暂存目录怎么上传都行。
- 可选 **FDSN 目录交叉匹配**，标注哪些检测与已编目事件重合。
- 既可作 YAML 驱动的**命令行工具**，也可作 **Python 库**调用。

### 安装

```bash
git clone https://github.com/yjianggeo/das-events.git
cd das-events
pip install -e .
```

需要 Python ≥ 3.11。依赖：numpy、scipy、h5py、obspy、matplotlib、PyYAML。

> **注意：** `das-events` 命令会装到 Python 的 `Scripts/` 目录。如果该目录不在你的 `PATH` 上，请用 `python -m das_events.cli ...` 代替 `das-events ...`。

### 输入数据

ZD-DAS / PRODML 风格的 HDF5，**每分钟一个文件**。每个文件包含
`Acquisition/Raw[0]/RawData`（`n_time × n_channels` float32 应变率）与
`RawDataTime`（int64 微秒 UTC）。元数据（标距、道间距、输出采样率、起始时间）
优先从 HDF5 属性读取，文件名作为兜底：

```
JJK_<深度>m_<标距>m_<道距>m_<原始Hz>Hz_<输出Hz>Hz_UTC8_<YYYYMMDDHHMM>.h5
例如 JJK_3400m_8m_4m_5000Hz_1000Hz_UTC8_202606161133.h5
```

文件名中的 12 位时间戳按 UTC 处理（与文件的 `MeasurementStartTime` 一致）。

### 工作流程

```bash
# 1. 扫描一个时段目录，检测事件并生成瀑布图
das-events scan /path/to/h5_dir --config examples/config.yaml \
    --events out/events.csv --plots out/waterfall

# 2. 查看 out/waterfall/*.png，然后在 events.csv 的 `label` 列填写
#    earthquake / blast / noise

# 3. 只暂存你保留的事件对应的文件
das-events stage --events out/events.csv --data-dir /path/to/h5_dir \
    --out out/staging --label earthquake,blast --config examples/config.yaml
```

一条命令跑完整条流水线（扫描 → 出图 → 暂存全部）：

```bash
das-events run /path/to/h5_dir --config examples/config.yaml --out out/
```

绘制单个文件的瀑布图：

```bash
das-events plot /path/to/one_file.h5 --out wf.png
```

> `--config` 要放在**子命令之后**（`das-events scan DIR --config cfg.yaml`）。

### 命令

| 命令 | 用途 |
|---------|---------|
| `scan DATA_DIR [--events CSV] [--plots DIR] [--catalog]` | 检测目录下每个 `*.h5` 的事件，写出 `events.csv`（+ 可选瀑布图）。 |
| `plot H5 [--out PNG]` | 绘制单个文件的瀑布图。 |
| `stage --events CSV --data-dir DIR [--out DIR] [--label L1,L2]` | 选出含事件的分钟文件（+余量），复制/硬链接到 `staging/`，写出 `manifest.csv`。 |
| `run DATA_DIR [--out DIR] [--catalog]` | 扫描 + 出图 + 暂存一气呵成。 |

`--catalog` 通过 USGS FDSN 交叉匹配填充 `catalog_match` 列（需要联网；离线时自动留空）。

### 配置项说明

一次运行由一个 YAML 文件驱动（见 `examples/config.yaml`）；未填写的项使用内置默认值。

| 配置项 | 含义 | 默认值 |
|-----|---------|---------|
| `freqmin`, `freqmax` | 带通频带（Hz） | `1.0`, `40.0` |
| `sta_seconds`, `lta_seconds` | STA / LTA 窗长（s） | `0.5`, `10.0` |
| `thr_on` | 单道 STA/LTA 触发阈值 | `4.0` |
| `min_coincidence` | 需同时触发的道数 | `4` |
| `min_duration_seconds` | 短于此时长的触发被剔除 | `0.2` |
| `merge_gap_seconds` | 间隔小于此值的触发合并 | `1.0` |
| `edge_skip_seconds` | 忽略每个文件边缘此范围内的触发 | `1.0` |
| `channel_decimation` | 检测时每 N 道取一道 | `4` |
| `channel_min`, `channel_max` | 限定道（深度）范围 | `0`, 全部 |
| `pad_seconds` | 选文件时每个事件前后的时间余量 | `60.0` |
| `stage_mode` | `copy`（复制）\| `hardlink`（硬链接） | `copy` |
| `sta_lat`, `sta_lon` | 台站坐标（目录匹配用） | JJK |
| `catalog_radius_km`, `catalog_min_mag`, `catalog_tol_seconds` | FDSN 交叉匹配参数 | `800`, `1.5`, `120` |

这些默认值是**在真实数据上调参的起点**。检测过多就调高 `thr_on` / `min_coincidence`；漏掉已知事件就调低。

### `events.csv` 列

`event_id`、`t_peak_utc`、`t_start_utc`、`t_end_utc`、`duration_s`、
`peak_ratio`、`peak_coincidence`、`n_channels`、`depth_min_m`、`depth_max_m`、
`dom_freq_hz`、`bandwidth_hz`、`local_time_of_day`（UTC+8）、`ps_separation_s`、
`source_file`、`catalog_match`、`label`。

`label` 留空，复核时填写。特征有助于判别：**地表爆破**往往集中在浅道、冲击性强、
发生在白天、且按固定时间重复；**区域地震**通常照亮整个井孔，并能看到明显的 P–S 间隔。

### 库调用 API

```python
from das_events.io import read_h5
from das_events.config import DetectConfig
from das_events.detect import detect_file
from das_events.features import extract_features
from das_events.waterfall import plot_waterfall

das = read_h5("JJK_3400m_8m_4m_5000Hz_1000Hz_UTC8_202606161133.h5")
cfg = DetectConfig(thr_on=4.0, min_coincidence=4)

for det in detect_file(das, cfg):
    feats = extract_features(das, det, cfg)
    print(det.t_peak, feats.dom_freq_hz, feats.depth_min_m, feats.depth_max_m)

plot_waterfall(das, out_path="wf.png")
```

整目录流水线：

```python
from das_events.config import load_config
from das_events.pipeline import scan_dir, write_events_csv

cfg = load_config("examples/config.yaml")
events = scan_dir("data/h5_dir", cfg)
write_events_csv(events, "events.csv")
```

### 模块

| 模块 | 职责 |
|--------|----------------|
| `io` | 读取 ZD-DAS h5 为 `DasData`；解析文件名；道深；UTC 时间 |
| `config` | `DetectConfig` 数据类 + YAML 加载 |
| `detect` | 带通 + 递归 STA/LTA + 多道符合检测 |
| `features` | 每个事件的频谱、深度范围、当地时刻、P–S 特征 |
| `waterfall` | 单事件的 道 × 时间 瀑布图 |
| `select` | 把检测映射为需上传的分钟文件集合（+余量） |
| `stage` | 复制 / 硬链接暂存 + sha256 `manifest.csv` |
| `catalog` | 纯时间交叉匹配 + 轻量 FDSN 拉取 |
| `pipeline` / `cli` | `Event` 组装、`events.csv` 读写、编排、命令行 |

### 说明与局限

- **文件边界瞬变。** 零相位带通滤波会在每个独立处理的分钟文件首尾产生很大的瞬变（约为文件中段幅值的 10 倍），否则会在每个文件触发一次贯穿全井孔的伪检测。`edge_skip_seconds`（默认 1 s）将其抑制；代价是文件首/末 1 秒内的真实事件可能被漏掉。
- **瀑布图余量截断。** 单事件瀑布图只加载该事件自身的 `source_file`，因此延伸到相邻分钟文件的余量部分在**图上**会被截断——但**暂存的数据是完整的**。
- **单线程。** 每个分钟文件约耗时 1 s，因此多天的时段（数千文件）可能需要几十分钟；`scan_dir` 遇到无法读取的文件会警告并跳过，使长时间运行不至于因单个坏文件中断。并行化是自然的后续改进方向。
- **目录匹配是可选的、仅作标注。** 检测完全数据驱动；`--catalog` 只标注重合事件，离线时自动降级。

### 许可证

MIT
