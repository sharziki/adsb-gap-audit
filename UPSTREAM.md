# Proposed traffic documentation example and regression fixture

**Title** Preserve altitude gaps before detecting descent level-offs

In traffic 2.13, `Flight.resample("1s")` fills numeric fields across missing reports by default. This is documented behavior. A downstream event detector can mistake a filled altitude segment for observed descent.

The OpenSky quickstart sample includes a reproducible case in MSR799 (ICAO `0101de`) on October 7, 2021. The reference altitude plateaus near 11,000 ft from 12:15:34 to 12:15:58 UTC. Keep the reports at 12:15:16 and 12:16:16 UTC and remove the 59 reports strictly between them. Default resampling fills the gap with a descent and the level-off detector no longer finds the event.

From the ADS-B Gap Audit repository, with the dependencies in `requirements.txt` installed:

```sh
python gapbench.py
GAPBENCH_DATA=.cache/quickstart.json.gz python -m unittest -v \
  test_gapbench.LevelOffTests.test_recorded_leveloff_erased
```

**Proposed upstream change.** Add this case to the resampling guide as an example of why event detection should preserve missing values. Show `Flight.resample("1s", how=None)` and require event detectors to treat null altitude as missing evidence. A small test can assert that default resampling fills the 59 interior bins, while `how=None` preserves them as missing and leaves the two anchor values intact. The upstream example can use the existing quickstart sample.

The example documents a consequence of current behavior. A future opt-in maximum gap size or an imputation flag would be a separate API discussion.
