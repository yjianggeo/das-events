"""Command-line interface: das-events {scan, plot, stage, run}."""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .config import DetectConfig, load_config
from .io import read_h5, parse_filename
from .detect import detect_file
from .pipeline import scan_dir, write_events_csv, read_events_csv
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
        plot_waterfall(das, t0=t0 - timedelta(seconds=cfg.pad_seconds),
                       t1=t1 + timedelta(seconds=cfg.pad_seconds),
                       out_path=out_dir / f"{ev.event_id}.png",
                       title=ev.event_id)


def cmd_plot(args) -> int:
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
    # --config lives on each subparser (single source of truth) so it is
    # accepted after the subcommand, e.g. `das-events scan DIR --config cfg.yaml`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="YAML config file")

    p = argparse.ArgumentParser(prog="das-events")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", parents=[common],
                       help="detect events across a directory")
    s.add_argument("data_dir")
    s.add_argument("--events", default="events.csv")
    s.add_argument("--plots", help="also write per-event waterfalls to this dir")
    s.set_defaults(func=cmd_scan)

    pl = sub.add_parser("plot", parents=[common], help="waterfall of one h5 file")
    pl.add_argument("h5")
    pl.add_argument("--out", default="waterfall.png")
    pl.set_defaults(func=cmd_plot)

    st = sub.add_parser("stage", parents=[common],
                        help="stage event-bearing minute-files")
    st.add_argument("--events", required=True)
    st.add_argument("--data-dir", required=True)
    st.add_argument("--out", default="staging")
    st.add_argument("--label", help="comma-separated labels to keep (e.g. earthquake,blast)")
    st.set_defaults(func=cmd_stage)

    r = sub.add_parser("run", parents=[common],
                       help="scan + plot + stage end to end")
    r.add_argument("data_dir")
    r.add_argument("--out", default="out")
    r.set_defaults(func=cmd_run)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
