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
