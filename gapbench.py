"""Benchmark loss of descent level-offs under simulated ADS-B report gaps."""
import argparse
import csv
import gzip
import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from traffic.core import Flight

SOURCE = (
    "https://raw.githubusercontent.com/xoolive/traffic/"
    "1d34bad4ec54cd27b75952d67302f918a836acbd/"
    "src/traffic/data/samples/collections/quickstart.json.gz"
)
SHA256 = "0ef1a97f6b96c31a58e2d9cf58af01a90016eb97472f37718dcba3913c682403"
SPANS = (30, 60, 90)


def load_tracks(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SOURCE, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Download checksum does not match the pinned sample")
    tracks = defaultdict(dict)
    with gzip.open(path, "rt") as stream:
        for row in json.load(stream):
            callsign = (row["callsign"] or "").strip()
            if row["onground"] is not False or not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9]*", callsign):
                continue
            if any(row.get(field) is None for field in ("altitude", "latitude", "longitude")):
                continue
            tracks[row["icao24"], callsign][row["timestamp"] // 1000] = row
    for key, reports in sorted(tracks.items()):
        times = np.array(sorted(reports))
        for segment in np.split(times, np.flatnonzero(np.diff(times) > 3) + 1):
            if len(segment) >= 100:
                yield key, [reports[t] for t in segment]


def resample(reports):
    frame = pd.DataFrame(reports, columns=["timestamp", "altitude", "latitude", "longitude"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    result = Flight(frame).resample("1s").data
    return result["timestamp"].dt.as_unit("s").astype("int64").to_numpy(), result["altitude"].to_numpy()


def leveloffs(times, altitude):
    """Find flat runs with a descent immediately before and after."""
    flat_width, shoulder = 21, 25
    if len(altitude) < flat_width + 2 * shoulder:
        return []
    flat = np.ptp(np.lib.stride_tricks.sliding_window_view(altitude, flat_width), axis=1) <= 50
    starts = np.flatnonzero(flat & ~np.r_[False, flat[:-1]])
    ends = np.flatnonzero(flat & ~np.r_[flat[1:], False]) + flat_width - 1
    events = []
    for start, end in zip(starts, ends):
        if start < shoulder or end + shoulder >= len(altitude):
            continue
        plateau = altitude[start:end+1]
        if np.ptp(plateau) > 75:
            continue
        if altitude[start-shoulder] - altitude[start] < 150:
            continue
        if altitude[end] - altitude[end+shoulder] < 150:
            continue
        events.append((int(times[start]), int(times[end])))
    return events


def overlaps(reference, candidate):
    start = max(reference[0], candidate[0])
    end = min(reference[1], candidate[1])
    return end - start >= 0.5 * (reference[1] - reference[0])


def split(aircraft):
    bucket = hashlib.sha256(aircraft.encode()).digest()[0]
    return "discovery" if bucket < 128 else "holdout"


def evaluate(path):
    for (aircraft, callsign), reports in load_tracks(path):
        times, altitude = resample(reports)
        for event in leveloffs(times, altitude):
            midpoint = sum(event) // 2
            context = [row for row in reports if abs(row["timestamp"] // 1000 - midpoint) <= 90]
            if len(context) < 2:
                continue
            context_times, context_altitude = resample(context)
            if not any(overlaps(event, other) for other in leveloffs(context_times, context_altitude)):
                continue
            for span in SPANS:
                left = midpoint - span // 2
                right = left + span
                if context_times[0] > left - 25 or context_times[-1] < right + 25:
                    continue
                retained = [row for row in context if not left < row["timestamp"] // 1000 < right]
                gap_times, gap_altitude = resample(retained)
                retained_times = [row["timestamp"] // 1000 for row in retained]
                left_anchor = max(t for t in retained_times if t <= left)
                right_anchor = min(t for t in retained_times if t >= right)
                candidates = leveloffs(gap_times, gap_altitude)
                row = dict(
                    aircraft=aircraft, callsign=callsign, split=split(aircraft),
                    event_start=event[0], event_end=event[1], target_span_s=span,
                    left_anchor=left_anchor, right_anchor=right_anchor,
                    removed_reports=len(context)-len(retained),
                    erased=not any(overlaps(event, other) for other in candidates),
                )
                yield row, context_times, context_altitude, gap_altitude


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(".cache/quickstart.json.gz"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    fixture = None
    for row, times, altitude, filled in evaluate(args.data):
        rows.append(row)
        if fixture is None and row["split"] == "discovery" and row["target_span_s"] == 60 and row["erased"]:
            fixture = row, times, altitude, filled
    if not rows or fixture is None:
        parser.error("Expected reference events and a discovery failure")
    with (args.output / "events.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    record, times, altitude, filled = fixture
    (args.output / "fixture.json").write_text(json.dumps(record, indent=2) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    origin = record["left_anchor"]
    fig, ax = plt.subplots(figsize=(8.8, 4.5), layout="constrained")
    ax.plot(times-origin, altitude, label="Reference", color="#23599b")
    ax.plot(times-origin, filled, label="After gap filling", color="#a04427", linestyle="--")
    ax.axvspan(0, record["right_anchor"]-origin, alpha=0.13, color="#a04427", label="Masked reports")
    ax.axvspan(record["event_start"]-origin, record["event_end"]-origin,
               alpha=0.15, color="#23599b", label="Detected level-off")
    ax.set(xlabel="Seconds from last pre-gap report", ylabel="Reported altitude (ft)",
           title=f"Descent level-off erased by interpolation · {record['callsign']}")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)
    fig.savefig(args.output / "level-off.png", dpi=160)
    print(f"traffic {version('traffic')}")
    for group in ("discovery", "holdout"):
        for span in SPANS:
            subset = [r for r in rows if r["split"] == group and r["target_span_s"] == span]
            aircraft = len({r["aircraft"] for r in subset})
            print(group, span, sum(r["erased"] for r in subset), len(subset), aircraft)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
