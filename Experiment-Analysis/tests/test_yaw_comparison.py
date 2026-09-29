from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from agcs_analysis import yaw_comparison as yaw


class HeadingProtocolTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((yaw.PROJECT_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.stems = self.manifest["trials"]["heading_stems"]
        self.settings = copy.deepcopy(self.manifest["heading_filter"])

    def base(self, stem=None):
        return yaw.prepare_reference_base(stem or self.stems[0], 1.0, 0.5, 0.35)

    def test_split_is_by_sample_count_not_elapsed_time(self):
        time = np.array([0, 1, 2, 3, 4, 100, 200, 300, 400, 500, 900], dtype=float)
        valid = np.ones(len(time), dtype=bool)
        valid[0] = False
        mask = yaw.calibration_mask(valid, time, 0.35)
        np.testing.assert_array_equal(np.flatnonzero(mask), [1, 2, 3])

    def test_invalid_splits_fail_explicitly(self):
        for fraction in [0, 1, -0.1, np.nan]:
            with self.subTest(fraction=fraction), self.assertRaises(ValueError):
                yaw.calibration_mask(np.ones(10, dtype=bool), np.arange(10), fraction)
        with self.assertRaises(ValueError):
            yaw.calibration_mask(np.ones(1, dtype=bool), np.arange(1), 0.35)
        with self.assertRaises(ValueError):
            yaw.calibration_mask(np.ones(10, dtype=bool), np.zeros(10), 0.35)

    def test_held_out_yaw_and_targets_cannot_change_tuning(self):
        base = self.base()
        changed = base.copy()
        cutoff = np.flatnonzero(base["calibration_sample"].to_numpy())[-1]
        changed.loc[cutoff + 1:, ["ugv_yaw_rad", "reference_yaw_rad"]] = np.nan

        def candidates(method):
            params = yaw.DEFAULT_FILTER_PARAMS[method]
            yield dict(params, process_variance=0.001)
            yield dict(params, process_variance=1.0)

        with patch.object(yaw, "baseline_candidate_params", side_effect=candidates):
            original_grid, original_params = yaw.tune_baselines({"trial": base})
            changed_grid, changed_params = yaw.tune_baselines({"trial": changed})
        self.assertEqual(original_params, changed_params)
        pd.testing.assert_frame_equal(original_grid, changed_grid)
        self.assertNotIn("AKF (proposed)", set(original_grid["method"]))

    def test_scoring_excludes_calibration_and_preserves_warmup_state(self):
        base = self.base()
        _, summary, series = yaw.compute_filter_comparison(["trial"], {"trial": base})
        trial = series["trial"]
        mask = trial["evaluation_sample"].to_numpy()
        expected = yaw.estimate_one_method("AKF (proposed)", base["ugv_yaw_rad"].to_numpy())
        np.testing.assert_allclose(trial["AKF (proposed)_yaw_deg"], np.rad2deg(expected))
        errors = yaw.angular_error_deg(expected[mask], base.loc[mask, "reference_yaw_rad"].to_numpy())
        self.assertAlmostEqual(summary.set_index("method").loc["AKF (proposed)", "rmse_deg"],
                               np.sqrt(np.mean(errors ** 2)))
        changed = base.copy()
        changed.loc[changed["calibration_sample"], "reference_yaw_rad"] += 1.0
        _, changed_summary, _ = yaw.compute_filter_comparison(["trial"], {"trial": changed})
        pd.testing.assert_frame_equal(summary, changed_summary)
        self.assertTrue((summary["n_samples"] == int(mask.sum())).all())

    def test_full_analysis_keeps_akf_fixed_and_reports_disjoint_counts(self):
        results = yaw.analyze_yaw_filters(yaw.UGV_DIR, self.stems, self.settings)
        self.assertEqual(results.selected_parameters_by_method["AKF (proposed)"],
                         yaw.DEFAULT_FILTER_PARAMS["AKF (proposed)"])
        self.assertTrue((results.split_summary["overlap_samples"] == 0).all())
        self.assertTrue((results.split_summary["calibration_end_s"] <
                         results.split_summary["evaluation_start_s"]).all())
        for trial in results.series.values():
            np.testing.assert_array_equal(trial["calibration_sample"] | trial["evaluation_sample"],
                                          trial["valid_reference"])
        counts = results.protocol["sample_counts"]
        self.assertEqual(counts["valid_reference_samples"], counts["calibration_samples"] + counts["evaluation_samples"])
        self.assertEqual(set(results.tuning_grid["method"]), set(yaw.TUNABLE_BASELINES))
        self.assertTrue((results.tuning_grid["n_samples"] == counts["calibration_samples"]).all())
        self.assertTrue((results.q_sensitivity["n_samples"] == counts["valid_reference_samples"]).all())
        self.assertEqual(int(results.tuning_grid["selected"].sum()), 3)
        self.assertTrue((results.deployed_diagnostic["n_samples"] == counts["valid_reference_samples"]).all())
        self.assertEqual(list(results.quantitative_table["method"]),
                         [yaw.RAW_METHOD, "AKF (deployed)"])
        if os.environ.get("NPY_DISABLE_CPU_FEATURES") == "AVX512F,AVX2":
            self.assertEqual(counts["valid_reference_samples"], 1807)
            self.assertEqual(counts["evaluation_samples"], 1176)
            np.testing.assert_allclose(
                results.quantitative_table.iloc[:, 1:].to_numpy(dtype=float),
                [[11.860, 18.199, 28.859, 70.448],
                 [11.847, 18.182, 28.952, 70.559]], atol=0.0005, rtol=0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            names = yaw.export_yaw_tables(results, output)
            self.assertEqual(set(names), {"table_VII_yaw_filter_quantitative", "table_XII_yaw_filter_baselines"})
            pd.testing.assert_frame_equal(pd.read_csv(output / "table_VII_yaw_filter_quantitative.csv"),
                                          results.quantitative_table)
            baseline = pd.read_csv(output / "table_XII_yaw_filter_baselines.csv")
            self.assertTrue((baseline["n_samples"] == counts["evaluation_samples"]).all())
            self.assertIn("AKF (deployed)", (output / "table_VII_yaw_filter_quantitative.tex").read_text())

    def test_nondefault_settings_reach_report_metadata(self):
        self.settings["course_reference"].update(half_window_s=0.75, min_speed_mps=0.7, calibration_fraction=0.4)
        self.settings["tune_baselines"] = False
        results = yaw.analyze_yaw_filters(yaw.UGV_DIR, self.stems[:1], self.settings)
        self.assertEqual(results.protocol["course_half_window_s"], 0.75)
        self.assertEqual(results.protocol["course_min_speed_mps"], 0.7)
        self.assertEqual(results.protocol["calibration_fraction"], 0.4)
        self.assertFalse(results.protocol["baseline_tuning_enabled"])
        self.assertFalse(results.selected_parameters["tuned_in_this_run"].any())

    def test_threshold_scan_uses_all_valid_samples_and_shared_akf(self):
        from agcs_analysis.yaw_threshold_sensitivity import evaluate_thresholds

        trials = {stem: self.base(stem) for stem in self.stems}
        params = yaw.DEFAULT_FILTER_PARAMS["AKF (proposed)"]
        row = evaluate_thresholds(trials, params)
        errors = []
        for trial in trials.values():
            estimate = yaw.estimate_one_method("AKF (proposed)", trial["ugv_yaw_rad"].to_numpy())
            error = yaw.angular_error_deg(estimate, trial["reference_yaw_rad"].to_numpy())
            errors.append(error[trial["valid_reference"].to_numpy()])
        expected = yaw.metrics_from_error(np.concatenate(errors))
        for metric in ["n_samples", "mae_deg", "rmse_deg"]:
            self.assertAlmostEqual(row[metric], expected[metric], places=12)
        self.assertGreater(row["n_samples"], row["held_out_n_samples"])
        self.assertEqual(row["regime_total_samples"], sum(len(trial) for trial in trials.values()))
        upper = evaluate_thresholds(trials, params, delta2_deg=180)
        self.assertEqual(upper["n_samples"], row["n_samples"])
        self.assertEqual(upper["severe_share_pct"], 0)
        self.assertGreater(upper["spike_deviation_deg"], 80)
        self.assertLess(row["spike_deviation_deg"], 0.1)

    @unittest.skipUnless(os.environ.get("NPY_DISABLE_CPU_FEATURES") == "AVX512F,AVX2",
                         "Historical numbers require the documented CPU dispatch setting")
    def test_legacy_comment_3_5_reproduction(self):
        yaw.validate_paper_environment()
        self.settings["evaluation_protocol"] = "legacy-paper"
        results = yaw.analyze_yaw_filters(yaw.UGV_DIR, self.stems, self.settings)
        table = results.table.set_index("method")
        np.testing.assert_allclose(table.loc["AKF (proposed)", ["mae_deg", "rmse_deg", "p95_ae_deg"]],
                                   [11.847, 18.182, 28.952], atol=0.0005, rtol=0)
        self.assertAlmostEqual(table.loc["Huber-based KF", "p95_ae_deg"], 29.705, delta=0.0005)
        self.assertEqual(results.protocol["sample_counts"]["evaluation_samples"], 1807)
        self.assertEqual(results.protocol["sample_counts"]["overlap_samples"], 634)


if __name__ == "__main__":
    unittest.main()
