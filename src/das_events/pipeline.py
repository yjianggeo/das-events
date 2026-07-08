"""Orchestration: scan a directory, build Events, read/write events.csv."""

import csv
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .io import read_h5
from .detect import detect_file
from .features import extract_features

EVENT_COLUMNS = [
    "event_id", "t_peak_utc", "t_start_utc", "t_end_utc", "duration_s",
    "method", "semblance", "peak_ratio", "peak_coincidence", "n_channels",
    "depth_min_m", "depth_max_m",
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
    method: str = "stalta"
    semblance: float = 0.0

    def as_row(self) -> dict:
        return {
            "event_id": self.event_id,
            "t_peak_utc": self.t_peak_utc,
            "t_start_utc": self.t_start_utc,
            "t_end_utc": self.t_end_utc,
            "duration_s": f"{self.duration_s:.3f}",
            "method": self.method,
            "semblance": f"{self.semblance:.4f}",
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
        method=detection.method,
        semblance=detection.semblance,
    )


def _dedupe_ids(events) -> None:
    """Ensure event_id uniqueness when two peaks share a wall-clock second."""
    seen: dict = {}
    for ev in events:
        n = seen.get(ev.event_id, 0)
        seen[ev.event_id] = n + 1
        if n:
            ev.event_id = f"{ev.event_id}_{n + 1}"


def scan_dir(data_dir, cfg, progress=None) -> list:
    """Detect events in every .h5 in ``data_dir`` (sorted). Returns list[Event].

    A file that cannot be read is skipped with a warning so one corrupt file
    does not abort a multi-day scan.
    """
    files = sorted(Path(data_dir).glob("*.h5"))
    events = []
    for i, fp in enumerate(files):
        if progress:
            progress(i, len(files), fp.name)
        try:
            das = read_h5(fp)
        except Exception as exc:               # corrupt / truncated / wrong format
            warnings.warn(f"skipping unreadable file {fp.name}: {exc}")
            continue
        for det in detect_file(das, cfg):
            events.append(_make_event(das, det, cfg))
    events.sort(key=lambda e: e.t_peak_utc)
    _dedupe_ids(events)
    return events


def apply_catalog(events, cfg, client_name="USGS") -> None:
    """Backfill each event's catalog_match via an FDSN cross-match.

    Network failure degrades gracefully (fetch returns [] -> all blank).
    Mutates the events in place.
    """
    from .catalog import fetch_fdsn_catalog, match_catalog
    if not events:
        return
    t_start = min(datetime.fromisoformat(e.t_start_utc.replace("Z", "+00:00"))
                  for e in events)
    t_end = max(datetime.fromisoformat(e.t_end_utc.replace("Z", "+00:00"))
                for e in events)
    catalog = fetch_fdsn_catalog(t_start, t_end, cfg.sta_lat, cfg.sta_lon,
                                 cfg.catalog_radius_km, cfg.catalog_min_mag,
                                 client_name=client_name)
    dets = [dict(event_id=e.event_id,
                 t_peak=datetime.fromisoformat(e.t_peak_utc.replace("Z", "+00:00")))
            for e in events]
    matches = match_catalog(dets, catalog, cfg.catalog_tol_seconds)
    for e in events:
        e.catalog_match = matches.get(e.event_id, "")


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
