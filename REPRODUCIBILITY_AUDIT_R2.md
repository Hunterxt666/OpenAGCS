# R2 Manuscript Reproducibility Inventory

This inventory is synchronized to the compiled current manuscript. The source
of truth is `main.aux` generated from
`IoT-70061-2026.R2__Manuscript&Response/IOTJ_Round2_Overleaf_Manuscript_Draft/main.tex`.
The manuscript currently contains Tables I--XIV and Figures 1--15.

## Reproducible Current Outputs

| Current manuscript item | Label / asset | Repository output | Entry point |
| --- | --- | --- | --- |
| Table II | `tab:repeated_trial_metrics` | `table_II_repeated_trial_metrics` | `features/tracking.py` |
| Table IV | `tab:operational_envelope` | `table_IV_operational_envelope` | `features/tracking.py` |
| Table V | `tab:comm_metrics` | `table_V_communication_metrics` | `features/communication.py` |
| Table VI | `tab:closed_loop_mode_summary` | `table_VI_closed_loop_mode_summary` | `features/closed_loop.py` |
| Table VII | `tab:yaw_filter_quantitative` | `table_VII_yaw_filter_quantitative` | `features/heading.py` |
| Table IX | `tab:akf_q_sensitivity` | `table_IX_akf_q_sensitivity` | `features/heading.py` |
| Table X | `tab:akf_delta1_sensitivity` | `table_X_akf_delta1_sensitivity` | `yaw_threshold_sensitivity.py` |
| Table XI | `tab:akf_delta2_sensitivity` | `table_XI_akf_delta2_sensitivity` | `yaw_threshold_sensitivity.py` |
| Table XII | `tab:yaw_filter_baselines` | `table_XII_yaw_filter_baselines` | `features/heading.py` |
| Table XIV | `tab:platoon_uav_delay_loss_metrics` | `table_XIV_platoon_uav_delay_loss_metrics` | `features/platoon.py` |
| Figure 5 | `trajectory.png` | `figure_05_trajectory` | `features/tracking.py` |
| Figure 6 | `curve.pdf` | `figure_06_state_timeseries` | `features/tracking.py` |
| Figure 7 | `filter.pdf` | `figure_07_yaw_tracking` | `features/tracking.py` |
| Figure 8 | `error.pdf` | `figure_08_tracking_errors` | `features/tracking.py` |
| Figure 10 | `4g_5g_comparison.png` | `figure_10_dual_mode_streams` | `features/communication.py` |
| Figure 11 | `5g_lora_position_comparison.png` | `figure_11_single_link_gaps` | `features/communication.py` |
| Figure 12 | `uav_gv_trajectories.png` | `figure_12_uav_gv_trajectories` | `features/closed_loop.py` |
| Figure 13 | `xy_error_comparison.png` | `figure_13_xy_error_comparison` | `features/closed_loop.py` |
| Figure 14 | `yaw_filters_comparison_raw_akf.pdf` | `figure_14_heading_filters` | `features/heading.py` |
| Figure 15 | `platoon_uav_delay_loss_simulation.pdf` | `figure_15_platoon_uav_delay_loss` | `features/platoon.py` |

Run the official paper pipeline from `Experiment-Analysis/` with
`./run_paper_reproduction.ps1 -Python python`. Run
`python -B -m agcs_analysis.yaw_threshold_sensitivity` separately for Tables X
and XI. Generated file stems deliberately include the current manuscript
number. They are not the manuscript's `\includegraphics` filename; use the
mapping above when copying a regenerated asset into the manuscript directory.

## Current Gaps And Non-Generated Assets

| Current manuscript item | Status | Required follow-up or rationale |
| --- | --- | --- |
| Table I, `tab:state_age_supervision` | Manual source table | It describes the controller state machine; retain its LaTex source or extract it from the implementation, but do not claim an analysis export. |
| Table III, `tab:distance_shortfall` | Reproduction gap | The released tracking CSVs are present, but no exporter currently produces the table's median shortfall and speed-stratified statistics. |
| Table VIII, `tab:severe_innovation_diagnostic` | Reproduction gap | The scan computes the underlying event, but does not export this exact five-column manuscript table. |
| Table XIII, `tab:lora_energy_overhead` | Manual calculation | Values derive from the stated specifications and flight duration; no calculation script is currently released. |
| Figure 1, `System architecture.png` | Manually authored diagram | A PNG is released at `Docs/Figure/system-architecture.png`; editable source is unavailable. |
| Figure 2, `workflow1.drawio.pdf` | Workflow diagram | PDF export is present beside the manuscript; add the `.drawio` source if editable release is required. |
| Figures 3--4, hardware PDFs | Field-hardware evidence | Photographs/layout, not data-derived plots. |
| Figure 9, `comment4_trial4_error_timeline.pdf` | Reproduction gap | Only the PDF is present in the manuscript package; add the plotting script and its exact input extraction. |
| Supplementary communication-error plot | Not a current manuscript figure | The pipeline writes `supplementary_communication_errors`; it is retained for audit but no longer occupies a numbered figure. |

## Excluded Duplicates

| Source directory | Decision | Reason |
| --- | --- | --- |
| `小论文_空地协同伴飞_二轮评审修改/_communication_metrics_reproduction` | Exclude | Superseded by the current Table V communication feature and released input CSVs. |
| `小论文_空地协同伴飞_二轮评审修改/AKF_threshold_sensitivity_analysis` | Exclude | Superseded by the package-integrated Table X/XI exporter. |
| `小论文_空地协同伴飞_二轮评审修改/车辆队列研究/Disturbance_Observer_Platoon_Control_Code` | Exclude | It is not the deterministic Figure 15/Table XIV simulation used in R2. |
| `closed_loop_comparison_github/github_closed_loop_comparison` | Migrated selectively | Its four source CSVs and reproduction logic now live under `Experiment-Analysis/data/closed_loop` and `features/closed_loop.py`. |

Do not commit `Experiment-Analysis/output/`, caches, or private raw logs.
