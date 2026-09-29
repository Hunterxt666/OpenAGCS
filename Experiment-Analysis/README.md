# AGCS Experiment Analysis

This directory is a feature-oriented analysis project for the outdoor AGCS
experiments reported in *Real-Time Air-Ground Cooperative Control with Onboard
UAV Computation and Dual-Mode Communication*. It reads the released CSV data,
computes reusable experiment metrics and generates the currently reproducible
R2 manuscript outputs, including Tables II, IV--VII, IX--XII, and XIV and
Figures 5--8 and 10--15.

The project is organized by analysis capability rather than paper numbering:

| Feature | Analysis capability | Paper outputs |
| --- | --- | --- |
| `tracking` | Trajectory reconstruction, tracking accuracy, analytical state-age envelope, response-model fitting, and delay sensitivity | Tables II and IV; Figures 5--8 |
| `communication` | Control-layer state age, link intervals, source switching, fallback duration, and communication-related tracking error | Table V; Figures 10--11 |
| `closed_loop` | Separate 5G-only, LoRa-only, and dual-mode flight comparison | Table VI; Figures 12--13 |
| `heading` | RTK-course reference, yaw filters, baseline tuning, and heading-error metrics | Tables VII, IX--XII; Figure 14 |
| `platoon` | Deterministic leader-only platoon escort simulation under relay delay and packet loss | Table XIV; Figure 15 |

## Project Structure

```text
Experiment-Analysis/
├── reproduce.py                 # Compatibility CLI wrapper
├── extract_data.py              # Private-log to public-CSV extraction
├── manifest.json                # Input mapping and analysis parameters
├── requirements.txt
├── data/
│   ├── trials/                 # Controller and UAV trial records
│   ├── heading/                # Canonical RTK/yaw trials
│   ├── communication/          # Table V and Figures 10--11 inputs
│   ├── closed_loop/            # Table VI and Figures 12--13 inputs
│   └── raw/                    # Optional private source archive
└── agcs_analysis/
    ├── project.py               # Feature selection and project orchestration
    ├── cli.py                   # Package command-line interface
    ├── dataset.py               # Lazy, cached access to experiment inputs
    ├── models.py                # Output and feature-result models
    ├── reporting.py             # CSV and LaTeX table exporters
    ├── parsers.py               # Log/CSV parsing and timestamp reconstruction
    ├── metrics.py               # Reusable numerical analysis functions
    ├── operational_envelope.py  # Analytical state-age envelope for Table IV
    ├── yaw_comparison.py        # RTK-course Tables VII/XII analysis and audits
    ├── platoon_simulation.py    # Appendix-B simulation and Figure 15
    ├── figures.py               # Publication figure rendering
    ├── runtime_filter.py        # Online AKF implementation loader
    └── features/
        ├── tracking.py
        ├── communication.py
        ├── closed_loop.py
        ├── heading.py
        └── platoon.py
```

Both `pipeline.reproduce()` and `reproduce.py` remain as compatibility wrappers
around the feature-oriented package entry point.

## Quick Start

The analysis requires Python 3.9. It does not require flight hardware, Redis,
MySQL, LoRa radios, or DJI PSDK.

### 1. Create and activate the Conda environment

From the repository root:

```bash
cd Experiment-Analysis
conda create --name agcs-analysis python=3.9 pip -y
conda activate agcs-analysis
python -m pip install -r requirements.txt
```

Activate `agcs-analysis` before each later analysis session.

### 2. Run the complete project

```bash
.\run_paper_reproduction.ps1 -Python python
```

This runs all five features and generates the currently reproducible R2 tables,
figures, intermediate CSV data, and
`output/analysis_summary.json`.

### 3. Run one analysis feature

Use a separate output directory when retaining results from multiple
independent runs:

```bash
python -m agcs_analysis tracking \
  --clean \
  --output output/tracking

python -m agcs_analysis communication \
  --clean \
  --output output/communication

python -m agcs_analysis closed_loop \
  --clean \
  --output output/closed-loop

python -m agcs_analysis heading \
  --clean \
  --output output/heading

python -m agcs_analysis platoon \
  --clean \
  --output output/platoon
```

Multiple features can be combined:

```bash
python -m agcs_analysis tracking communication \
  --clean \
  --output output/control-and-links
```

To compute tables and intermediate data without rendering figures:

```bash
.\run_paper_reproduction.ps1 -Python python -TablesOnly
```

`run_paper_reproduction.ps1` is the official paper-result entry point. It
validates Python 3.9 and the pinned dependencies, sets
`NPY_DISABLE_CPU_FEATURES=AVX512F,AVX2` before NumPy is imported, and runs the
default held-out protocol. The main-text Raw/AKF diagnostic, the held-out
baseline comparison, and the full-log process-noise sensitivity table are
exported together under their manuscript table names. The lower-level package
CLI remains available for development runs, but is not the reproducibility
command cited for the paper.

## Output Layout

For the default complete run:

```text
output/
├── analysis_summary.json
├── tables/          # Current R2 manuscript tables plus auxiliary tables
├── figures/         # Current R2 manuscript figures in PNG and PDF
└── intermediate/    # Reconstructed and derived CSV time series
```

Intermediate filenames describe their analysis role:

- `tracking_trial_metrics.csv`
- `outer_loop_reconstruction.csv`
- `delay_sensitivity_metrics.csv`
- `delay_response_series.csv`
- `tracking_error_series.csv`
- `communication_source_modes.csv` (aligned state ages and selected source)
- `communication_gap_markers.csv`
- `communication_error_series.csv`
- `yaw_metrics_by_trial.csv`
- `yaw_reference_estimates_*.csv`
- `yaw_reference_motion_summary.csv`
- `yaw_baseline_tuning_grid.csv`
- `yaw_selected_filter_parameters.csv`
- `yaw_akf_q_sensitivity.csv`
- `figure_15_simulation_series.csv`
- `figure_15_simulation_metadata.json`
- `timestamp_reconstruction.csv`
- `table_VI_closed_loop_mode_summary.csv`

## Threshold Sensitivity Diagnostics

Using the same pinned Python 3.9 environment as the heading comparison, run
the following from this directory in PowerShell:

```powershell
$env:NPY_DISABLE_CPU_FEATURES = "AVX512F,AVX2"
python -B -m agcs_analysis.yaw_threshold_sensitivity
```

The two threshold scans in `output/threshold_sensitivity/` use all 1,807 valid
moving samples, matching the main-text Raw/AKF diagnostic. They reuse
`yaw_comparison.py` preprocessing, reference construction and the deployed
filter. Moderate/severe shares use all 2,543 filter inputs. The Trial 3 spike
deviation is a separate local diagnostic against the circular mean of its
adjacent raw headings, not an RTK-course error. The nominal rows are checked
against the main diagnostic before export (absolute tolerance 1e-12 degrees).
Separate held-out columns are checked against the complete baseline table;
its 1,176 evaluation samples are not the threshold tables' scoring subset.
The output includes CSV scans, both comparison tables, split counts and a
JSON protocol record. The scan does not retune the deployed thresholds.

## Released Data

All paths are relative to this directory. `manifest.json` is the authoritative
mapping between input files, analysis windows, parameters, and paper outputs.

| Dataset | Released inputs | Primary use |
| --- | --- | --- |
| Four tracking trials | `data/trials/controller/uav_202411011105.csv`, `uav_202411011223.csv`, `uav_202411041454.csv`, `uav_202411061732.csv` | Table II duration, tracking, height, yaw, and update-gap metrics |
| Four canonical RTK trajectories | `data/heading/202410211227.csv`, `202410211256.csv`, `202410211327.csv`, `202410211350.csv` | Table II speed and heading-filter analysis |
| Representative trial | `data/trials/controller/uav_202411061732.csv`, `data/trials/uav/202411061732.csv` | Trajectory and tracking figures |
| 4G comparison | `data/trials/controller/uav_202410291603.csv` | Communication stream comparison |
| 5G/LoRa controller trial | `data/trials/controller/uav_202411041454.csv` | Figure 10 stream comparison and auxiliary outer-loop/delay analysis |
| Control-aligned 5G/LoRa positions | `data/communication/control_aligned_positions_202411041454.csv` | Table V |
| Accepted link updates and full communication streams | `data/communication/accepted_link_updates_202410291603_202411041454.csv`, `gv_5g_position_updates_202411041454.csv`, `gv_lora_position_updates_202411041454.csv`, `tracking_errors_202411041454.csv` | Figures 10--11 and supplementary diagnostic series |
| Separate closed-loop mode trials | `data/closed_loop/5G-only_test.csv`, `LoRa-only_test.csv`, `dual-mode_test.csv`, `route_geometry_500m.csv` | Table VI and Figures 12--13 |

The original application logs remain outside the public repository. They are
approximately 111 MB and contain repeated diagnostic and transport records.
`extract_data.py` documents the conversion from the private archive to the
released CSV schema:

```bash
python extract_data.py \
  --raw-dir /path/to/private/raw \
  --output-dir data
```

The public analysis does not require the private logs.

## Analysis Methods

### Tracking and response

`features/tracking.py` uses the domain functions
`summarize_tracking_trials()`, `reconstruct_outer_loop()`,
`fit_response_models()`, and `analyze_delay_sensitivity()`.

The final two columns of Table II are computed from the canonical RTK
trajectory files under `data/heading/`. For every interior trajectory
sample at time $t$, the analysis linearly interpolates position at
$t-1.0$ s and $t+1.0$ s, divides the planar displacement by 2.0 s, and
converts the result to km/h. The table reports the mean and 95th percentile of
these centered speed estimates. The exact controller-to-speed-file mapping is
recorded in `manifest.json`.

UAV and GV streams are aligned causally: a UAV sample at time $t$ may use
only the newest GV state whose source timestamp is no later than $t$.
The fitted first-order response model is

$$
p_{k+1}=\alpha p_k+(1-\alpha)u_k+\epsilon_k,
\qquad
\lambda=-\frac{\log\alpha}{\Delta t}.
$$

Table IV is an analytical operating envelope and does not consume an
experiment CSV. For a 5 m planar reference-mismatch tolerance and a 10 m
forward-lead distance, it evaluates

$$
a_{\max}=\frac{5}{v_{\mathrm{GV}}+10\omega_{\mathrm{GV}}},
$$

where speed is converted from km/h to m/s and yaw rate from degrees/s to
radians/s. It is generated automatically with the tracking feature. It can
also be generated independently:

```bash
python state_age_envelope.py --output-dir output/tables
```

The standalone command prints the table and writes
`output/tables/operational_envelope.csv`.

### Communication

`features/communication.py` reproduces Table V from the control-aligned GV
position stream in `data/communication/control_aligned_positions_202411041454.csv`. The
configured analysis window is 148--540 s. The first released control sample in
that requested window is at 149.1 s, so the actual evaluated interval is
149.1--540 s and contains 3,720 rows.

For each link, mean, P95, and maximum update intervals are computed after
deduplicating its sensing timestamps (`ugv_5g_time` or `ugv_lora_time`) while
preserving their occurrence order. The effective dual-mode timestamp is the
newer of the two sensing timestamps on each control row. Source switches count
changes in the controller-facing selected source: 5G remains selected while its
state age is no greater than 0.3 s; LoRa is selected only when 5G is stale and
LoRa has a newer sensing timestamp.

The timeout rate follows manuscript Eq. (14):

$$
N_{\mathrm{miss}}=\sum_j\left\lfloor
\frac{\max(0,\Delta t_j-\tau)}{T_s}\right\rfloor,
\qquad
r_{\mathrm{timeout}}=100\frac{N_{\mathrm{miss}}}
{\lfloor T_{\mathrm{mission}}/T_s\rfloor},
\qquad \tau=0.3~\mathrm{s},\;T_s=0.1~\mathrm{s}.
$$

The mission duration is the requested 148--540 s analysis window. LoRa fallback
duration counts 0.1 s control rows where 5G is stale and LoRa contains a newer
state. With the released CSV, Eq. (14) and the control-source rule produce:

| Mode | Mean interval (s) | P95 interval (s) | Max gap (s) | Timeout rate (%) | Switches | LoRa fallback (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5G-only | 0.233 | 0.7 | 1.8 | 21.3 | -- | -- |
| LoRa-only | 0.852 | 1.1 | 18.1 | 66.4 | -- | -- |
| Dual-mode | 0.203 | 0.5 | 1.1 | 13.9 | 228 | 46.1 |

### Heading filters

`features/heading.py` reads only the four stems listed under `heading_stems` in
`manifest.json`; the communication CSV in the same directory is not treated as
a heading trial. For each UGV timestamp, `yaw_comparison.py` reconstructs an
independent RTK course-angle reference from the centered trajectory displacement
over a 1.0 s half-window. Table VII metrics use only moving samples whose
reconstructed speed is at least 0.5 m/s; raw GV yaw remains a magnetometer
measurement, not ground truth.

The default `held-out` protocol keeps the AKF parameters fixed at their previous
paper settings: Q = 0.03 rad^2, R = 0.002742 rad^2, thresholds 35/140 degrees,
and inflation 10. AKF does not participate in parameter search. The three
baselines retain the original candidate grids and are selected using only the
first `floor(0.35 * N_valid)` chronological valid samples in each trial. One
parameter set per baseline is chosen across all four calibration segments by
pooled RMSE, with ties resolved by MAE, P95 absolute error, then candidate order.
Table XII scores **only the remaining valid samples**, identically for raw yaw,
AKF, and all baselines. The shared evaluation subset does not imply identical
parameter-selection procedures or independence of earlier AKF development from
these logs.

Filters process the full causal measurement sequence, including stationary
samples, from each trial's start. Their states are retained at the split.
Baseline candidate evaluation stops at the last calibration sample; no held-out
yaw or reference error is used to select a candidate. The centered RTK reference
is an offline target, never a filter input. Adjacent reference windows may share
positions near the split, so this is a within-trial temporal evaluation, not an
independent-trial generalization test. Full-replay figures shade the unscored
calibration/warm-up prefix.

The pinned environment is still Python 3.9 plus the unchanged `requirements.txt`.
For a complete paper reproduction, use `run_paper_reproduction.ps1` above. The
heading-only compatibility launcher is retained for focused heading audits:

```powershell
.\run_heading_paper_compat.ps1 -Python python -Figures
```

This validates Python and every pinned package, sets
`NPY_DISABLE_CPU_FEATURES=AVX512F,AVX2` before NumPy import, and writes to
`output/heading_held_out_paper_compat`. Omit `-Figures` for tables only. Specify
`-Python C:\path\to\environment\python.exe` when the environment is not activated.
The script restores the caller's CPU-feature environment variable on exit.
The default run exports both manuscript tables as CSV and LaTeX:

- `tables/table_VII_yaw_filter_quantitative.csv` and `.tex`: main-text
  `tab:yaw_filter_quantitative`, Raw yaw versus deployed AKF on all 1,807 valid
  samples. MAE/RMSE remain 11.860/18.199 degrees for Raw and 11.847/18.182 degrees
  for AKF. This is the full-log diagnostic retained in the main text.
- `tables/table_XII_yaw_filter_baselines.csv` and `.tex`: appendix
  `tab:yaw_filter_baselines`, all five methods on the 1,176 held-out samples.

`heading_evaluation_protocol.json` records the scoring subset and sample count
for each table. No separate historical run is needed for the main-text Raw/AKF
table; both exports reuse the same fixed AKF replay.

Quicksort/deduplication remains unchanged to preserve the previously audited
input sequences; this launcher documents a tested environment, not universal
cross-platform sorting reproducibility.

The historical five-method comparison from Comment 3.5 is available as a separate audit:

```powershell
.\run_heading_paper_compat.ps1 -Python python -Protocol legacy-paper
```

That mode retains the original timestamp-quantile calibration rule, fixed AKF,
baseline grids, and all-valid evaluation, including the overlap. Its default
directory is `output/heading_legacy_paper_compat`. It is not the revised held-out
table. In Comment 3.5, the old numbers should therefore be identified as the
historical reproduction check; the revised comparison uses the held-out result.
The output names use the current manuscript table numbers, so the table mapping
does not depend on legacy aliases.

The package CLI also accepts `--heading-protocol held-out` or `legacy-paper`;
without it the setting comes from `manifest.json`. The standalone entry point
`python -m agcs_analysis.yaw_comparison --protocol held-out` uses the same analysis
and the manifest's heading trial list. Its output goes to
`output/yaw_comparison_revision/held-out` by default.
The standalone command writes the same named table files directly in its output
directory (without the package workflow's `tables/` subdirectory).

Alongside the comparison, the heading feature exports:

- `heading_evaluation_protocol.json`: active protocol, counts, reference and
  selection rules, runtime versions, CPU settings, and input/source hashes.
- `intermediate/yaw_split_summary.csv`: counts and start/end times per trial.
- `intermediate/yaw_reference_estimates_*.csv`: calibration, held-out, and
  evaluation masks plus the full causal estimates. Error columns contain all
  valid errors for diagnostics; apply `evaluation_sample` to reconstruct Table XII.
- `intermediate/yaw_baseline_tuning_grid.csv`: all baseline candidates, their
  calibration-only metrics, and the selected-candidate flag. AKF is absent.
- `intermediate/yaw_selected_filter_parameters.csv`: fixed AKF settings and
  selected baseline settings, including whether each method was tuned.
- `intermediate/yaw_akf_q_sensitivity.csv`: a full-log diagnostic on all valid
  moving samples in both protocols; it never changes AKF.
- `intermediate/yaw_deployed_akf_all_valid_diagnostic.csv`: separately labelled
  full-log Raw/AKF metrics for consistency with earlier deployment diagnostics.

The original motion-reference audit and per-trial metrics are also retained.
`reviewer_response_quantitative.md` summarizes the active protocol and actual
results; it is analysis output, not an automatic edit to the response letter.

Protocol regression tests use only the existing dependencies and `unittest`:

```powershell
$env:NPY_DISABLE_CPU_FEATURES = "AVX512F,AVX2"
python -m unittest discover -s tests -v
```

### Leader-only platoon escort simulation

`features/platoon.py` runs the deterministic Appendix-B simulation implemented
in `platoon_simulation.py`. The model contains one leader GV, six follower GVs,
and one UAV that subscribes only to the timestamped leader state. It uses a
0.2 s relay delay, 10% packet loss, 0.1 s transmissions, and random seed 70061.
The UAV causally extrapolates the received leader position using the transmitted
velocity before constructing its 10 m forward escort reference.

Run only this simulation with:

```bash
python -m agcs_analysis platoon --clean --output output/platoon
```

The command writes Table XIV as CSV and LaTeX, Figure 15 as PNG and PDF, the
complete plotted time series as CSV, and a JSON record containing every model
parameter, the fixed seed, and full-precision metrics.

## Figure Generation Notes

- Figure 5 renders the released geodetic trajectories in local east/north
  coordinates without requiring the network-fetched Esri basemap.
- Figure 10 uses controller-accepted cellular and LoRa position/yaw updates;
  LoRa points are successful fallback updates rather than every received radio
  packet. Figure 11 uses the complete 5G-trial position streams and marks the
  first update after a gap greater than 1.0 s. The corrected communication-error
  reconstruction is exported as an unnumbered supplementary diagnostic.
- Figures 8 and 13 plot errors directly in metres with no legacy plotting
  scale. The separate Table V aligned CSV is not used to draw Figures 10--11.
- Figure 15 is generated from the fixed-seed Appendix-B simulation and its
  complete time series is exported for independent metric reconstruction.
- Every figure is exported as a 300-dpi PNG and a vector PDF.
- Matplotlib uses a non-interactive backend, so the complete project runs on a
  headless workstation or CI runner.
