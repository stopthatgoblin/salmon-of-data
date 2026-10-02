"""Regression tests for consequential scientific calculations and safeguards."""
import unittest

import numpy as np

from build_matchups import aligned_core, common_footprint, decode_reflectance, group_measurements, nearest_measurement
from extract_screening import select_items, screening_mask
from model_screening import metrics, predict, splits
from audit_radiometry import verify_differences


def observation(seconds, value, objectid="1"):
    return {"Probe_Ref_No": "A", "Metric_Type": "Turbidity", "Date": str(seconds*1000),
            "Metric_Value": value, "OBJECTID": objectid, "timestamp_utc": str(seconds)}


class ScienceTests(unittest.TestCase):
    def test_offset_conflict_is_not_silently_approved(self):
        for counts in [{}, {0: 10}, {1000: 10, 999: 1}]:
            with self.assertRaises(ValueError):
                verify_differences(counts)
        verify_differences({1000: 20})

    def index(self, rows):
        return group_measurements(rows)[("A", "Turbidity")]

    def test_nearest_tie_is_earlier_and_keeps_source(self):
        m = nearest_measurement(self.index([observation(0, "2", "7"), observation(1800, "8", "8")]), 900)
        self.assertEqual((m["value"], m["delta_minutes"], m["objectids"]), (2, -15, "7"))
        self.assertTrue(m["bracketed_30min"])

    def test_no_widening_when_data_gap(self):
        self.assertIsNone(nearest_measurement(self.index([observation(0, "2")]), 901))

    def test_null_nearest_not_replaced_with_more_distant_valid_value(self):
        m = nearest_measurement(self.index([observation(0, ""), observation(600, "8")]), 1)
        self.assertTrue(m["missing"])
        self.assertIsNone(m["value"])
        self.assertEqual(m["local_2h_missing_n"], 1)

    def test_conflicting_duplicates_not_averaged(self):
        m = nearest_measurement(self.index([observation(0, "2", "7"), observation(0, "8", "8")]), 0)
        self.assertTrue(m["conflicting"])
        self.assertIsNone(m["value"])
        self.assertFalse(m["bracketed_30min"])

    def test_identical_duplicates_preserve_provenance(self):
        m = nearest_measurement(self.index([observation(0, "2", "7"), observation(0, "2", "8")]), 0)
        self.assertEqual(m["value"], 2)
        self.assertEqual(m["objectids"], "7;8")

    def test_no_bracketing_across_missing_value(self):
        m = nearest_measurement(self.index([observation(0, "2"), observation(1800, "")]), 500)
        self.assertFalse(m["bracketed_30min"])

    def test_native_10m_cells_align_to_20m_footprint(self):
        bounds = common_footprint([20, 0, 0, 0, -20, 1020])
        data = np.arange(169).reshape(13, 13)
        # Deliberately different 10m centre parity, as in real archived patches.
        core = aligned_core(data, [10, 0, 440, 0, -10, 570], bounds)
        np.testing.assert_array_equal(core, data[3:9, 4:10])
        self.assertEqual(core.shape, (6, 6))

    def test_non_aligned_grids_fail(self):
        with self.assertRaises(ValueError):
            aligned_core(np.ones((13, 13)), [10, 0, 441, 0, -10, 570], (480, 480, 540, 540))

    def test_scale_offset_nodata_and_negative_preserved(self):
        x = decode_reflectance(np.array([0, 900, 1000, 1400]), {"raster:bands": [{"nodata": 0, "scale": .0001, "offset": -.1}]})
        self.assertTrue(np.isnan(x[0]))
        np.testing.assert_allclose(x[1:], [-.01, 0, .04], atol=1e-14)

    def test_cloud_and_land_mask_are_distinct(self):
        x = np.full((51, 51), 6)
        x[20, 20] = 9
        r = screening_mask(x)
        self.assertEqual(r["scl_core_water_pixels"], 9)
        self.assertTrue(r["scl_cloud_shadow_snow_within_120m"])
        self.assertFalse(r["scl_land_within_120m"])

    def rows(self):
        return [{"overpass_group": f"2025-01-{i:02d}", "station": s, "probe_value": str(i),
                 "red_median": str(i/1000), "nir_median": str(i/2000)}
                for i in range(1, 21) for s in (["A", "B"] if i%2 else ["A"])]

    def test_all_schemes_hold_out_entire_dates(self):
        for scheme in ["leave_one_date_out", "forward_blocks", "station_and_date_holdout"]:
            for _, train, test in splits(self.rows(), scheme):
                self.assertFalse({r["overpass_group"] for r in train} & {r["overpass_group"] for r in test})
                if scheme == "station_and_date_holdout":
                    self.assertFalse({r["station"] for r in train} & {r["station"] for r in test})
                if scheme == "forward_blocks":
                    self.assertLess(max(r["overpass_group"] for r in train), min(r["overpass_group"] for r in test))

    def test_test_data_never_changes_fit_or_scaling(self):
        train = self.rows()[:10]
        test = self.rows()[15:16]
        a, _ = predict(train, test, "red_linear")
        extreme = {**test[0], "red_median": "100000", "probe_value": "999999"}
        b, _ = predict(train, test+[extreme], "red_linear")
        self.assertAlmostEqual(a[0], b[0])

    def test_metrics_keep_negative_r2_and_prediction(self):
        r = metrics([1, 3], [-1, -1])
        self.assertEqual(r["mae"], 3)
        self.assertAlmostEqual(r["rmse"], 10**.5)
        self.assertEqual(r["bias"], -3)
        self.assertEqual(r["r2"], -9)
        self.assertEqual(r["negative_predictions"], 2)


if __name__ == "__main__":
    unittest.main()
