"""Regression checks for the level-off detector and the recorded replay."""
import os
import unittest
from pathlib import Path

import numpy as np

from gapbench import evaluate, leveloffs


class LevelOffTests(unittest.TestCase):
    def test_descent_with_plateau(self):
        times = np.arange(101)
        altitude = np.interp(times, [0, 35, 65, 100], [3000, 2400, 2400, 1800])
        events = leveloffs(times, altitude)
        self.assertEqual(len(events), 1)
        start, end = events[0]
        self.assertLessEqual(start, 35)
        self.assertGreaterEqual(end, 65)

    def test_continuous_descent(self):
        times = np.arange(101)
        self.assertEqual(leveloffs(times, 3000 - 10 * times), [])

    @unittest.skipUnless(os.environ.get("GAPBENCH_DATA"), "Set GAPBENCH_DATA for recorded replay")
    def test_recorded_leveloff_erased(self):
        path = Path(os.environ["GAPBENCH_DATA"])
        fixture = next(
            (row, times, reference, filled)
            for row, times, reference, filled in evaluate(path)
            if row["aircraft"] == "0101de"
            and row["callsign"] == "MSR799"
            and row["event_start"] == 1633608934
            and row["target_span_s"] == 60
        )
        row, times, reference, filled = fixture
        self.assertEqual(row["split"], "discovery")
        self.assertEqual(row["removed_reports"], 59)
        self.assertTrue(row["erased"])
        self.assertTrue(np.all(np.isfinite(filled)))
        self.assertEqual(reference.shape, times.shape)
        self.assertEqual(filled.shape, times.shape)


if __name__ == "__main__":
    unittest.main()
