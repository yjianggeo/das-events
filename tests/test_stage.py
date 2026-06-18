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
