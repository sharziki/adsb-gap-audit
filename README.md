# ADS-B Gap Audit

**Measuring downstream bias from ADS-B gap filling**

ADS-B Gap Audit is a standalone benchmark for retrospective civil flight analysis. The first task checks whether resampling a flight with missing reports can erase a descent level-off and leave a continuous-looking altitude trace.

## Reproduce

Use Python 3.12. The benchmark downloads an exact revision of the [traffic OpenSky quickstart sample](https://traffic-viz.github.io/quickstart.html) and checks its SHA-256. Source observations are fetched separately from the code.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python gapbench.py
GAPBENCH_DATA=.cache/quickstart.json.gz python -m unittest -v
```

Use `--data` to reuse a local copy of the pinned sample and `--output` to select the results directory. pandas is pinned to 2.3.3 because traffic 2.13 imports an internal class removed in pandas 3.1.

## Protocol

- The input is a three-hour OpenSky sample from October 7, 2021. Keep airborne observations with commercial-style callsigns and complete altitude and position records. Split aircraft-and-callsign tracks at original gaps longer than three seconds.
- Create a one-second reference grid with `traffic.Flight.resample("1s")`. Detect a level-off using consecutive 20-second windows with at most 50 ft of altitude range. Require at most 75 ft of range across the combined plateau and at least 150 ft of net descent in each adjacent 25-second shoulder. These parameters define the benchmark event.
- Mask original observations inside a nominal 30-, 60-, or 90-second span centered on the event and rerun the same default resampler. Count an event as erased when no detection overlaps at least half its reference duration. The CSV records actual anchor timestamps.
- Partition by ICAO address using the first byte of SHA-256. Select the recorded example from discovery aircraft and report rates from the disjoint holdout aircraft. A flight in the count is an aircraft/callsign track within this sample.

These rates are conditional on a simulated outage centered on a detector-defined level-off. They do not estimate actual ADS-B outage frequency or the percentage of all flights affected. The reference may include interpolation over up to three seconds and has no independent flight-recorder labels. Same-day holdout flights establish separation from the example, while a separate time and airport sample would test generalization.

## First run

MSR799 contains a 24-second level-off near 11,000 ft. After masking 59 reports between anchors 60 seconds apart, default resampling replaces the plateau with continuous descent. The event detector loses the level-off.

| Target span | Holdout events erased | Erasure rate | Holdout flight tracks |
|---|---:|---:|---:|
| 30 s | 6 / 31 | 19.4% | 23 |
| 60 s | 16 / 30 | 53.3% | 23 |
| 90 s | 22 / 30 | 73.3% | 23 |

The same reference event may be evaluated at multiple spans. Each test uses both pre-gap and post-gap observations.

## Outputs

- `results/events.csv` contains event-level outcomes for both splits.
- `results/fixture.json` identifies the exact discovery event and report mask.
- `results/level-off.png` overlays the reference and interpolated altitude.
- `UPSTREAM.md` is a proposed maintainer report with a replay command.
