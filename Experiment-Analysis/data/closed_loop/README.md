# Closed-Loop Communication-Mode Inputs

These CSV files are the released, plotting-ready records for the three
separate closed-loop field flights cited by the R2 manuscript:

- `5G-only_test.csv`
- `LoRa-only_test.csv`
- `dual-mode_test.csv`
- `route_geometry_500m.csv`

Each mode file contains the measured UAV/GV local positions, signed tracking
errors, selected-state age, cellular-state age, selected source, and a
termination marker. `terminated = 0` identifies active UAV samples. The one
LoRa-only terminal row is retained so the plot can mark the supervisory
timeout, but it is not used for any reported metric.

Run `python -m agcs_analysis closed_loop --clean` from `Experiment-Analysis`
to generate `tables/table_VI_closed_loop_mode_summary.csv` and the figures
`figure_12_uav_gv_trajectories.{png,pdf}` and
`figure_13_xy_error_comparison.{png,pdf}`.
