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
