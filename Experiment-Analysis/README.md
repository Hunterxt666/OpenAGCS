# AGCS Experiment Analysis

This directory is a feature-oriented analysis project for the outdoor AGCS
experiments reported in *Real-Time Air-Ground Cooperative Control with Onboard
UAV Computation and Dual-Mode Communication*. It reads the released CSV data,
computes reusable experiment metrics, and generates paper Tables I--IV and VII,
auxiliary response/delay tables, and Figures 5--13.

The project is organized by analysis capability rather than paper numbering:

| Feature | Analysis capability | Paper outputs |
| --- | --- | --- |
| `tracking` | Trajectory reconstruction, tracking accuracy, analytical state-age envelope, response-model fitting, and delay sensitivity | Tables I--II, auxiliary response/delay tables, Figures 5--8 |
| `communication` | Control-layer state age, link intervals, source switching, fallback duration, and communication-related tracking error | Table III, Figures 9--11 |
| `heading` | RTK-course reference, yaw filters, baseline tuning, and heading-error metrics | Table IV, Figure 12 |
| `platoon` | Deterministic leader-only platoon escort simulation under relay delay and packet loss | Table VII, Figure 13 |

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
│   ├── communication/          # Table III and Figures 9--11 inputs
│   └── raw/                    # Optional private source archive
└── agcs_analysis/
    ├── project.py               # Feature selection and project orchestration
    ├── cli.py                   # Package command-line interface
    ├── dataset.py               # Lazy, cached access to experiment inputs
    ├── models.py                # Output and feature-result models
    ├── reporting.py             # CSV and LaTeX table exporters
    ├── parsers.py               # Log/CSV parsing and timestamp reconstruction
    ├── metrics.py               # Reusable numerical analysis functions
    ├── operational_envelope.py  # Analytical state-age envelope for Table II
    ├── yaw_comparison.py        # RTK-course Table IV analysis and audits
    ├── platoon_simulation.py    # Appendix-B simulation and Figure 13
    ├── figures.py               # Publication figure rendering
    ├── runtime_filter.py        # Online AKF implementation loader
    └── features/
        ├── tracking.py
        ├── communication.py
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
python -m agcs_analysis all --clean
```

This runs all four features and generates paper Tables I--IV and VII,
auxiliary response/delay tables, Figures 5--13, intermediate CSV data, and
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
python -m agcs_analysis all --clean --tables-only
```

## Output Layout

For the default complete run:

```text
output/
├── analysis_summary.json
├── tables/          # Paper Tables I--IV and VII plus auxiliary tables
├── figures/         # Figures 5--13 in PNG and PDF
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
- `figure_13_simulation_series.csv`
- `figure_13_simulation_metadata.json`
- `timestamp_reconstruction.csv`

## Released Data

All paths are relative to this directory. `manifest.json` is the authoritative
mapping between input files, analysis windows, parameters, and paper outputs.

| Dataset | Released inputs | Primary use |
| --- | --- | --- |
| Four tracking trials | `data/trials/controller/uav_202411011105.csv`, `uav_202411011223.csv`, `uav_202411041454.csv`, `uav_202411061732.csv` | Table I duration, tracking, height, yaw, and update-gap metrics |
| Four canonical RTK trajectories | `data/heading/202410211227.csv`, `202410211256.csv`, `202410211327.csv`, `202410211350.csv` | Table I speed and heading-filter analysis |
| Representative trial | `data/trials/controller/uav_202411061732.csv`, `data/trials/uav/202411061732.csv` | Trajectory and tracking figures |
| 4G comparison | `data/trials/controller/uav_202410291603.csv` | Communication stream comparison |
| 5G/LoRa controller trial | `data/trials/controller/uav_202411041454.csv` | Figure 9 stream comparison and auxiliary outer-loop/delay analysis |
| Control-aligned 5G/LoRa positions | `data/communication/control_aligned_positions_202411041454.csv` | Table III |
| Accepted link updates and full communication streams | `data/communication/accepted_link_updates_202410291603_202411041454.csv`, `gv_5g_position_updates_202411041454.csv`, `gv_lora_position_updates_202411041454.csv`, `tracking_errors_202411041454.csv` | Figures 9--11 |

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

The final two columns of Table I are computed from the canonical RTK
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

Table II is an analytical operating envelope and does not consume an
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

`features/communication.py` reproduces Table III from the control-aligned GV
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
over a 1.0 s half-window. Table IV metrics use only moving samples whose
reconstructed speed is at least 0.5 m/s; raw GV yaw remains a magnetometer
measurement, not ground truth.

The proposed innovation-gated AKF uses fixed parameters from the paper
revision. The EKF-labelled moving-average KF, EKF-AR-labelled short-history KF,
and Huber-based KF are grid-tuned on the first 35% of valid RTK-course samples
from each trial. The complete tuning grid, selected parameters, Q sensitivity,
motion-reference audit, per-trial metrics, and aligned estimates are exported
under `output/intermediate/`.

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

The command writes Table VII as CSV and LaTeX, Figure 13 as PNG and PDF, the
complete plotted time series as CSV, and a JSON record containing every model
parameter, the fixed seed, and full-precision metrics.

## Figure Generation Notes

- Figure 5 renders the released geodetic trajectories in local east/north
  coordinates without requiring the network-fetched Esri basemap.
- Figure 9 uses controller-accepted cellular and LoRa position/yaw updates;
  LoRa points are successful fallback updates rather than every received radio
  packet. Figure 10 uses the complete 5G-trial position streams and marks the
  first update after a gap greater than 1.0 s. Figure 11 uses the corrected
  causal reconstruction with the 10 m forward-lead target; its proposed curve
  comes from the controller's logged `delta_x` and `delta_y` values.
- Figures 8 and 11 plot errors directly in metres with no legacy plotting
  scale. The separate Table III aligned CSV is not used to draw Figures 9--11.
- Figure 13 is generated from the fixed-seed Appendix-B simulation and its
  complete time series is exported for independent metric reconstruction.
- Every figure is exported as a 300-dpi PNG and a vector PDF.
- Matplotlib uses a non-interactive backend, so the complete project runs on a
  headless workstation or CI runner.
