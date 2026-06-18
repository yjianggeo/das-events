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
