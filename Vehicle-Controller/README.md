# Vehicle-Controller

`Vehicle-Controller` is one subsystem of the full air-ground collaborative project.
It is responsible for **vehicle-side mission control logic**, including UAV follow-task orchestration, control command generation, and status interaction with upstream/downstream modules.

- Upstream modules (for example, Ground-Station / Communication-Framework) provide mission intent and control switches.
- This module translates intent into executable control actions.
- Downstream executors (for example, `UAV-Executor`) execute low-level flight commands.

## Scope in the Full Project

This repository section is **not a standalone project**. It is the control layer between:

1. mission-level coordination modules, and
2. onboard execution modules.

The current implementation focuses on UAV control. In the experiments reported in the paper, the UGV was operated manually, while its state information was consumed by the UAV follow-control and visualization modules. No autonomous UGV controller is included in this repository.

## Directory Organization

```text
Vehicle-Controller/
├── README.md
├── uav_main.py
├── run_controller.sh
├── requirements.txt
├── Tools/
│   ├── GvStateSupervisor.py
│   ├── LogUtil.py
│   ├── PosUtil.py
│   └── RequestTools.py
├── VehicleAgent/
│   └── DroneAgent.py
└── UAV-Executor/
    └── README.md
```

### Core Files and Responsibilities

- `uav_main.py`
  - Main process entry for UAV control.
  - Maintains control loop heartbeat.
  - Starts/stops follow tasks based on shared control flags.

- `VehicleAgent/DroneAgent.py`
  - Runtime UAV control agent.
  - Maintains UAV/UGV state cache (position, altitude, yaw, timestamps).
  - Generates velocity/yaw control sequence.
  - Manages task stages: takeoff -> follow -> return -> land.

- `Tools/RequestTools.py`
  - Lightweight HTTP request wrapper.
  - Unifies request error handling and logging.

- `Tools/GvStateSupervisor.py`
  - Rejects duplicate, out-of-order, stale, or wrong-mission GV packets.
  - Selects the freshest sensing timestamp across cellular and LoRa.

- `run_controller.sh`
  - Shell entrypoint for launching controller service in deployment.

- `UAV-Executor/`
  - Linked executor submodule docs.
  - Describes how control commands are consumed by onboard execution runtime.

## Control Pipeline (High-Level)

1. Receive mission/control intent from upper-layer modules.
2. Read current UAV/UGV state from communication interfaces.
3. Compute control sequence in `DroneAgent`.
4. Dispatch commands to executor-side interfaces.
5. Monitor feedback and update control state machine.

For the cellular path, the controller reads one atomic `/ugvState` snapshot:

```text
mission_id, [x_gv, y_gv], position_time,
filtered_heading_deg, heading_time, height,
[v_east, v_north], sensed_at
```

The LoRa fallback carries the equivalent state as:

```text
[x_gv, y_gv, filtered_heading_deg, sensed_at, height, mission_id,
 v_east, v_north]
```

Coordinates and filtered heading use the paper's ENU convention: `x` is east,
`y` is north, and yaw is counter-clockwise from east. Sensor compass headings
are converted when controller-facing packets are built. At the opposite
boundary, ENU velocity and yaw commands are converted to the DJI ground-frame
north/east velocity ordering and clockwise-from-north absolute yaw.

`sensed_at` is the earlier of the position and heading acquisition times, so a frozen heading cannot be made fresh by new position samples. Duplicate polls do not refresh a packet's receive time. `GvStateSupervisor` accepts only the active `mission_id` and applies the paper's `tau = 0.3 s` freshness threshold. Cellular is the primary route: whenever its state is healthy, fresh, causal, and no older than the last state consumed by the controller, it is selected even if LoRa carries a newer sample. LoRa is selected only when cellular is unusable. Once fallback is active, cellular must remain continuously usable for `1.0 s` before failback; any failure, stale/non-causal state, or backward sensing timestamp restarts that recovery window. This hysteresis prevents route flapping, while the monotonic guard prevents state time from moving backward. When neither path supplies a fresh state, the controller retains the newest causally available GV reference and continues recomputing velocity/yaw commands from the current UAV state for a bounded `2.0 s` hold interval. It commands zero velocity and retries `HOVER` only after that sustained-unavailability interval expires, or immediately if local UAV localization/height is invalid. Configure the hold interval with `--stale-state-hold-timeout` or `AGCS_STALE_STATE_HOLD_TIMEOUT`.

For a valid packet, the desired guiding point is:

```text
x_d = x_gv + D cos(filtered_heading)
y_d = y_gv + D sin(filtered_heading)
z_d = H
```

The velocity outer loop implements the paper's per-axis PD law:

```text
v_j = Kp_j e_j + Kd_j LPF((e_j[k] - e_j[k-1]) / dt)
```

The finite-difference derivative is first-order low-pass filtered, bounded, and
reset whenever a mission phase changes or telemetry becomes stale. Defaults are
`Kp_xy = 0.8`, `Kd_xy = 0.2`, `Kp_z = 0.8`, `Kd_z = 0.15`, and a derivative
filter time constant of `0.2 s`. They can be changed with the corresponding
`--kp-*`, `--kd-*`, and `--derivative-filter-tau` options (or `AGCS_PD_*`
environment variables). Velocity output is still constrained by the configured
horizontal and vertical safety limits.

The same filtered ENU GV heading is used as the desired **absolute** UAV yaw.
The communication boundary converts it to DJI's compass-angle convention before
the Executor uses `DJI_FLIGHT_CONTROLLER_YAW_ANGLE_CONTROL_MODE`; it is not a
quantized yaw error or a yaw-rate command. The executor interpolates absolute
yaw on the circle, so transitions across `+/-180 deg` take the shortest rotation.

`D` and `H` are read from the Ground Station through `/checkDH` at mission start. Valid values are `0 <= D <= 100 m` and `0 < H <= 120 m`. If no D/H value has been supplied, the fallback is the reported experiment setting `D = 10 m, H = 30 m`.

### Mission Start and Stop

The operator starts the mission from the Ground Station, which calls the remote `/setDepart` endpoint. The communication framework stores this request in the shared `depart` state, and `DroneAgent.check_depart_status()` polls `/depart` to update `remote_depart_order`. The poll has three states: active, inactive, and unknown. A timeout, connection error, malformed response, or unexpected HTTP status is unknown and leaves the last valid order unchanged; it cannot trigger landing. When the remote order becomes active while the local `depart_flag` is false, `uav_main.py` calls `depart_and_start_follow()`.

Before takeoff, the controller obtains a non-empty mission ID and activates that
telemetry epoch. It then requires fresh same-mission UAV position and height, a
usable GV state, and confirmed cellular and LoRa heartbeat health for a
continuous `0.5 s` preflight window. A failed check inhibits `TAKEOFF`.
`TAKEOFF` must then be accepted by the local command API, and altitude above the lift-off threshold with low absolute vertical speed must remain stable for `0.5 s` before joystick control is enabled. The UAV must then reach `H` within bounded time. Periodic joystick publication remains disabled while DJI's automatic takeoff owns the aircraft and starts only after lift-off is confirmed. The controller then acquires the full guiding pose `(x_d, y_d, H)` and requires position, height, and absolute velocity to remain within tolerance for a continuous stability window before marking escort active. Every flight-stage wait has a configurable timeout.

Selecting land clears the remote `depart` state. The guarded workflow first
tracks `D = 0` while holding the current altitude and verifies planar stability.
Only then does a second controller stage descend at `D = 0` to the `2 m`
approach height and verify the full pose. The guidance thread is then stopped, a zero-velocity handoff is accepted by the local API, and periodic velocity publication is disabled before `LAND`. A failed or timed-out `LAND` request is treated as an ambiguous result: the controller retains `LANDING`, keeps joystick publication disabled, and continues observation instead of issuing `HOVER`. Touchdown success requires an accepted `COFIRMLAND`, observed descent, and a fresh low-height/low-vertical-speed signal for a continuous stability window. Mission state is cleared only after `OFFCONTROL` is also accepted. Earlier-stage timeout commands a safe hover; a landing-stage failure never re-enables joystick control or reports successful landing.

The controller polls emergency state over both paths. The UAV-local
`/emergencyStop` endpoint consumes the mission-scoped LoRa command and is
checked first; the remote endpoint supplies the cellular copy. Either active
signal immediately stops guidance, writes zero velocity, and commands `HOVER`.
An unavailable endpoint is an unknown state and cannot clear a latched
emergency. This is a process-level hard stop: clearing the source endpoints
does not clear either the Python controller latch or the Executor suspension.
After inspecting the aircraft, restart both Controller and Executor before
starting another mission. If the stop arrives after `LAND`, the controller
keeps the automatic-landing phase, sends no velocity or `HOVER` command, and
continues touchdown monitoring; this prevents joystick authority from being
reacquired during descent.

## Runtime Notes

- Designed to run as a long-lived process.
- Logs are expected to be collected by external process manager (`nohup`, `systemd`, or container runtime).
- Threaded loops are used for periodic control emission and state polling.
- Dual-link defaults are a `0.3 s` state/heartbeat timeout, a `2.0 s` stale-reference hold limit, three consecutive delivery failures, and a `1.0 s` cellular recovery window. Configure them with `--state-freshness-timeout`, `--stale-state-hold-timeout`, `--link-heartbeat-timeout`, `--link-failure-threshold`, and `--cellular-recovery-window`, or the corresponding `AGCS_*` environment variables.
- The `0.5 s` takeoff stability window is configurable with `--takeoff-stable-window` or `AGCS_TAKEOFF_STABLE_WINDOW`.
- Preflight confirmation uses `--preflight-timeout` and
  `--preflight-stable-window`, or `AGCS_PREFLIGHT_TIMEOUT` and
  `AGCS_PREFLIGHT_STABLE_WINDOW`. Both cellular and LoRa must be healthy before
  takeoff.
- UAV and UGV system clocks must be synchronized (NTP/PTP or GNSS-disciplined time). The supervisor enforces `t_i <= t_k` by default. A small, explicit `--clock-skew-tolerance` may be configured when measured clock uncertainty requires it; it cannot exceed the `0.3 s` freshness timeout.
- The local `/height` response must contain `mission_id`, `height`, and its source `time`. Wrong-mission and repeated samples are rejected. Every flight stage also compares the height source time with the current mission clock extrapolated from a fresh, same-mission UAV position sample, so neither a delayed altitude sample nor a frozen clock anchor is actionable.

## Quick Start

The controller must run on the UAV computer after the UAV-local Communication
Framework and authorized UAV Executor are available.

### 1. Create and activate the Conda environment

From the repository root:

```bash
cd Vehicle-Controller
conda create --name agcs-controller python=3.9 pip -y
conda activate agcs-controller
python -m pip install -r requirements.txt
```

Run `conda activate agcs-controller` before every later controller session.

### 2. Verify upstream and downstream services

The default local API is `http://127.0.0.1:26969`. Verify the local and remote
Communication Framework instances before starting the controller:

```bash
curl --fail http://127.0.0.1:26969/alive
curl --fail "http://REMOTE_HOST:REMOTE_PORT/alive"
```

The UAV Executor must also be running and connected to the local command API.
See the [UAV Executor deployment guide](UAV-Executor/README.md).

### 3. Start the controller

```bash
conda activate agcs-controller
python uav_main.py \
  --remote-url "http://REMOTE_HOST:REMOTE_PORT"
```

The local endpoint defaults to `http://127.0.0.1:26969`. Override it only when
the UAV-local API is bound elsewhere:

```bash
python uav_main.py \
  --remote-url "http://REMOTE_HOST:REMOTE_PORT" \
  --local-url "http://LOCAL_HOST:LOCAL_PORT"
```

For deployment through the launcher, export the active Conda interpreter and
remote endpoint:

```bash
conda activate agcs-controller
export AGCS_PYTHON_EXECUTABLE="$(command -v python)"
export AGCS_REMOTE_URL="http://REMOTE_HOST:REMOTE_PORT"
./run_controller.sh
```

At startup the process waits until the mission origin is available. This is
expected; initialize the origin from the Ground Station before requesting
departure.

### 4. Confirm readiness

Before flight, confirm from the controller logs that:

- the active mission ID is non-empty;
- UAV position and height belong to the active mission;
- a fresh GV state is available;
- cellular and LoRa link-health checks both pass;
- the controller remains in `IDLE` until the operator requests departure.

For a managed background process, keep the Conda interpreter explicit:

```bash
mkdir -p logs
nohup env \
  AGCS_PYTHON_EXECUTABLE="$(command -v python)" \
  AGCS_REMOTE_URL="http://REMOTE_HOST:REMOTE_PORT" \
  ./run_controller.sh \
  > ./logs/uav_controller.log 2>&1 &
```

Inspect logs with:

```bash
tail -f ./logs/uav_controller.log
```

## Current Status

- UAV control path: available.
- UGV operation: manually controlled in the reported experiments.
- UGV controller implementation: not included in the current open-source release.

## Suggested Integration Position

In the complete project, place `Vehicle-Controller` as the **middle control layer**:

- Northbound: mission coordination / UI / communication framework.
- Southbound: UAV onboard executor and actuator interfaces.
