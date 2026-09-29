from __future__ import annotations

import unittest

import numpy as np

from agcs_analysis.dataset import ExperimentDataset
from agcs_analysis.features.closed_loop import summarize_modes


class ClosedLoopModeTests(unittest.TestCase):
    def test_summary_matches_manuscript_values(self):
        summary = summarize_modes(ExperimentDataset().closed_loop_mode_trials())
        values = summary.set_index("mode")
        self.assertEqual(values.loc["5G-only", "completion"], "yes")
        self.assertEqual(values.loc["LoRa-only", "completion"], "no")
        self.assertEqual(values.loc["Dual-mode", "completion"], "yes")
        np.testing.assert_allclose(
            values.loc[:, [
                "gv_path_length_m", "uav_active_duration_s", "x_mae_m",
                "y_mae_m", "planar_rmse_m", "max_state_age_s",
                "lora_fallback_duration_s",
            ]].to_numpy(dtype=float),
            [
                [513.503209, 122.65, 0.938913, 0.677196, 1.739973, 1.174872, 0.0],
                [88.783214, 2.1, 0.572885, 0.961521, 1.183203, 1.980414, 0.0],
                [491.014043, 124.61583, 0.812885, 0.555837, 1.316589, 0.766505, 10.9],
            ],
            atol=1e-6,
            rtol=0,
        )


if __name__ == "__main__":
    unittest.main()
