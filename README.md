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
| `detector` | Backend: `stalta` \| `semblance` \| `both` | `stalta` |
| `freqmin`, `freqmax` | Band-pass corners (Hz) | `1.0`, `40.0` |
| `sta_seconds`, `lta_seconds` | STA / LTA windows (s) | `0.5`, `10.0` |
| `thr_on` | Per-channel STA/LTA trigger threshold | `4.0` |
| `min_coincidence` | Channels that must trigger at once | `4` |
| `min_duration_seconds` | Reject triggers shorter than this | `0.2` |
| `merge_gap_seconds` | Merge triggers closer than this | `1.0` |
| `edge_skip_seconds` | Ignore triggers within this margin of each file edge | `1.0` |
| `channel_decimation` | Use every Nth channel for detection | `4` |
| `channel_min`, `channel_max` | Restrict the channel (index) range | `0`, all |
| `depth_min_m`, `depth_max_m` | Restrict the depth (metres) range — **transfers across devices** | `null`, `null` |
| `semblance_thr` | Trigger threshold on peak semblance (0–1) | `0.04` |
| `semblance_win_seconds` | Sliding coherence window (s) | `2.0` |
| `semblance_slowness_max` | Apparent-slowness scan half-range (s/m) | `6e-4` |
| `semblance_n_slowness` | Slowness grid points (odd → includes 0) | `11` |
| `semblance_channel_decimation` | Use every Nth channel for semblance | `3` |
| `semblance_depth_bands` | `[[lo_m, hi_m], …]` sub-bands (max over bands); `null` = whole aperture | `null` |
| `teleseism_min_coherence` | (teleseism) per-file slowness≈0 coherence gate | `0.12` |
| `teleseism_min_run` | (teleseism) consecutive coherent minute-files required | `3` |
| `pad_seconds` | Time pad around each event when selecting files | `60.0` |
| `stage_mode` | `copy` \| `hardlink` | `copy` |
| `sta_lat`, `sta_lon` | Station coordinates (catalog match) | JJK |
| `catalog_radius_km`, `catalog_min_mag`, `catalog_tol_seconds` | FDSN cross-match params | `800`, `1.5`, `120` |

These defaults are **starting points to calibrate on real data**. Raise `thr_on` / `min_coincidence` (or `semblance_thr`) if you get too many detections; lower them if you miss known events.

### Detection backends

- **`stalta`** – per-channel band-pass + recursive STA/LTA with channel coincidence. Best for sharp, impulsive, high-SNR arrivals; yields a per-channel amplitude ratio. Historical default.
- **`semblance`** – slant-stack spatial **coherence** across the borehole. It is **amplitude-agnostic and baseline-free**, so it catches *weak, emergent* coherent arrivals ("continuous first arrivals") that never push any single channel's STA/LTA over threshold, and events that fill the whole file with no quiet window to normalise against. Scans a grid of apparent slownesses (and optional depth sub-bands) and triggers when the peak semblance exceeds `semblance_thr`.
- **`both`** – run both and merge overlapping detections (best recall). The `method` column records which backend(s) fired; strong events show `stalta+semblance`.
- **`teleseism`** – **directory-level** detector for teleseismic **surface-wave** trains (a different physical class — see below). Unlike the other backends it looks across neighbouring minute-files, so scan a whole session at once.

#### Teleseismic surface waves (`detector: teleseism`)

Teleseismic surface waves are very low frequency (**~0.05–0.2 Hz**, 5–20 s period), **multi-minute dispersive** trains that arrive near-uniformly down the borehole (apparent slowness ≈ 0). Two consequences:

- The regional-event config's 2–40 Hz band **filters them out entirely** — use `examples/config_teleseism.yaml`, which sets a 0.05–0.2 Hz band.
- At those frequencies DAS is dominated by spatially-**coherent common-mode noise**, so a single minute's coherence or energy cannot separate a surface wave from a coherent-noise burst. The discriminant that works is **temporal persistence**: the detector flags minutes whose slowness-0 coherence exceeds `teleseism_min_coherence`, then reports only **runs of ≥ `teleseism_min_run` consecutive** coherent minute-files (isolated coherent bursts are rejected as noise), emitting one Event per run.

Calibrated on the 2026-06-16 ~17:12–17:16 UTC surface-wave train (JJK/data/20260616), verified by a coherent-beam spectrogram; the detector returns exactly that train (`dom_freq_hz` ≈ 0.08 Hz). **Caveat:** this is inherently harder than body-wave detection — surface waves sit near the DAS common-mode-noise floor, so treat detections as review candidates and calibrate `teleseism_min_coherence` / `teleseism_min_run` on your device (lower them to surface weaker trains at the cost of more coherent-noise false positives). A co-located broadband seismometer, if available, is the surest cross-check.

### Calibrating on a well, then scanning another device of it

`examples/config_jjk.yaml` is calibrated on the Jiakika (JJK) 2904 m borehole against three known regional-earthquake sessions (2025-01-04, 2025-02-22, 2026-05-28 — the last very weak). It uses `detector: both`, a 2–40 Hz band, a **260–2904 m** depth window (skips the 20–100× louder near-surface noise and the out-of-well tail fibre), and sub-band semblance. On that set it detects all three sessions (the weak one via semblance only) with zero false positives across a 55-minute reference session.

Because `depth_min_m` / `depth_max_m`, the frequency band, and `semblance_depth_bands` are all **physical** (metres and Hz, resolved against each file's channel table), the same config transfers to another acquisition device on the same well even if its channel count or exact `dx` differ — no index editing. If the new device's noise floor is very different, re-check `semblance_thr` on a stretch of its *quiet* data (quiet minutes should peak well below it).

### `events.csv` columns

`event_id`, `t_peak_utc`, `t_start_utc`, `t_end_utc`, `duration_s`,
`method`, `semblance`, `peak_ratio`, `peak_coincidence`, `n_channels`,
`depth_min_m`, `depth_max_m`, `dom_freq_hz`, `bandwidth_hz`,
`local_time_of_day` (UTC+8), `ps_separation_s`,
`source_file`, `catalog_match`, `label`.

`method` is the backend(s) that fired; `semblance` (0–1) is the peak coherence
(0 for STA/LTA-only detections); `peak_ratio` is the peak STA/LTA ratio (0 for
semblance-only detections). A high `semblance` with `peak_ratio` 0 is the
signature of a weak-but-coherent regional arrival.

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
| `detect` | STA/LTA + channel-coincidence **and** slant-stack semblance backends; depth→channel resolution |
| `teleseism` | Directory-level teleseismic surface-wave detector (coherence + persistence) |
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
| `detector` | 检测后端：`stalta` \| `semblance` \| `both` | `stalta` |
| `freqmin`, `freqmax` | 带通频带（Hz） | `1.0`, `40.0` |
| `sta_seconds`, `lta_seconds` | STA / LTA 窗长（s） | `0.5`, `10.0` |
| `thr_on` | 单道 STA/LTA 触发阈值 | `4.0` |
| `min_coincidence` | 需同时触发的道数 | `4` |
| `min_duration_seconds` | 短于此时长的触发被剔除 | `0.2` |
| `merge_gap_seconds` | 间隔小于此值的触发合并 | `1.0` |
| `edge_skip_seconds` | 忽略每个文件边缘此范围内的触发 | `1.0` |
| `channel_decimation` | 检测时每 N 道取一道 | `4` |
| `channel_min`, `channel_max` | 限定道（索引）范围 | `0`, 全部 |
| `depth_min_m`, `depth_max_m` | 限定深度（米）范围——**可跨设备迁移** | `null`, `null` |
| `semblance_thr` | 相干（semblance）峰值触发阈值（0–1） | `0.04` |
| `semblance_win_seconds` | 滑动相干窗长（s） | `2.0` |
| `semblance_slowness_max` | 视慢度扫描半量程（s/m） | `6e-4` |
| `semblance_n_slowness` | 慢度网格点数（奇数含 0） | `11` |
| `semblance_channel_decimation` | semblance 每 N 道取一道 | `3` |
| `semblance_depth_bands` | `[[lo_m, hi_m], …]` 深度子带（取各带最大）；`null`=整段井孔 | `null` |
| `teleseism_min_coherence` | （远震）单文件 slowness≈0 相干门限 | `0.12` |
| `teleseism_min_run` | （远震）需连续相干的分钟文件数 | `3` |
| `pad_seconds` | 选文件时每个事件前后的时间余量 | `60.0` |
| `stage_mode` | `copy`（复制）\| `hardlink`（硬链接） | `copy` |
| `sta_lat`, `sta_lon` | 台站坐标（目录匹配用） | JJK |
| `catalog_radius_km`, `catalog_min_mag`, `catalog_tol_seconds` | FDSN 交叉匹配参数 | `800`, `1.5`, `120` |

这些默认值是**在真实数据上调参的起点**。检测过多就调高 `thr_on` / `min_coincidence`（或 `semblance_thr`）；漏掉已知事件就调低。

### 检测后端

- **`stalta`** —— 逐道带通 + 递归 STA/LTA + 多道符合。适合尖锐、冲击性、高信噪比的到时；输出逐道幅值比。历史默认。
- **`semblance`** —— 沿井孔的**斜叠相干**（slant-stack semblance）。**与幅值无关、无需静默基线**，因此能捕获那些**微弱、缓起**的相干到时（“连续初至”）——它们不足以让任何单道 STA/LTA 越过阈值；也能捕获贯穿整段文件、没有静默窗可归一的事件。它在一组视慢度（及可选深度子带）上扫描，峰值 semblance 超过 `semblance_thr` 即触发。
- **`both`** —— 两者都跑并合并时间重叠的检测（召回最高）。`method` 列记录是哪个后端触发；强事件会显示 `stalta+semblance`。
- **`teleseism`** —— **目录级**的远震**面波**检测（不同的物理类别，见下）。它需要跨相邻分钟文件，因此要对整个时段目录一次性扫描。

#### 远震面波（`detector: teleseism`）

远震面波是极低频（**~0.05–0.2 Hz**，周期 5–20 s）、持续数分钟、频散的波列，沿井孔近乎同时到达（视慢度≈0）。两个后果：

- 区域事件配置的 2–40 Hz 频带会把它**完全滤掉**——请用 `examples/config_teleseism.yaml`（0.05–0.2 Hz 频带）。
- 在这些频率上 DAS 被空间**相干的共模噪声**主导，因此**单分钟**的相干或能量无法把面波和相干噪声爆发区分开。真正有效的判据是**时间持续性**：检测器先标记 slowness≈0 相干超过 `teleseism_min_coherence` 的分钟，再仅报告**连续 ≥ `teleseism_min_run` 个**相干分钟文件构成的**波列**（孤立的相干爆发被当作噪声剔除），每个波列输出一个事件。

已在 2026-06-16 约 17:12–17:16 UTC 的面波波列（JJK/data/20260616）上标定，并用相干波束谱图核实；检测器精确返回该波列（`dom_freq_hz`≈0.08 Hz）。**注意：** 面波检测本质上比体波更难——面波接近 DAS 共模噪声底，所以请把检测结果当作**复核候选**，并在你的设备上标定 `teleseism_min_coherence` / `teleseism_min_run`（调低可捞出更弱的波列，代价是更多相干噪声误报）。若有并置的宽频地震计，是最可靠的交叉验证。

### 先在一口井上标定，再扫描该井的另一台设备

`examples/config_jjk.yaml` 已在甲基卡（JJK）2904 m 井孔上、针对三次已知区域地震时段（2025-01-04、2025-02-22、2026-05-28，最后一次极弱）完成标定。它使用 `detector: both`、2–40 Hz 频带、**260–2904 m** 深度窗（剔除比井内噪声大 20–100 倍的近地表噪声与出井尾纤），以及子带 semblance。在该数据集上三次时段全部检出（最弱的一次仅靠 semblance），并在一段 55 分钟参考时段上零误报。

由于 `depth_min_m` / `depth_max_m`、频带、`semblance_depth_bands` 都是**物理量**（米与 Hz，按每个文件的道-深度表解析），即使另一台采集设备的道数或 `dx` 略有不同，同一份配置也可直接迁移，无需改索引。若新设备噪声水平差异很大，请在其一段**静默**数据上复核 `semblance_thr`（静默分钟的峰值应明显低于该阈值）。

### `events.csv` 列

`event_id`、`t_peak_utc`、`t_start_utc`、`t_end_utc`、`duration_s`、
`method`、`semblance`、`peak_ratio`、`peak_coincidence`、`n_channels`、
`depth_min_m`、`depth_max_m`、`dom_freq_hz`、`bandwidth_hz`、
`local_time_of_day`（UTC+8）、`ps_separation_s`、
`source_file`、`catalog_match`、`label`。

`method` 是触发的后端；`semblance`（0–1）是峰值相干（纯 STA/LTA 检测为 0）；
`peak_ratio` 是峰值 STA/LTA 比（纯 semblance 检测为 0）。**高 `semblance` 且
`peak_ratio` 为 0** 正是微弱但相干的区域到时的特征。

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
| `detect` | STA/LTA 多道符合 **与** 斜叠相干（semblance）两种后端；深度→道解析 |
| `teleseism` | 目录级远震面波检测（相干 + 持续性） |
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
