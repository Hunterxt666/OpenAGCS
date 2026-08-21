# Commulication-Framework

`Commulication-Framework` is one subsystem of the full air-ground collaborative project.
It serves as the **middle communication layer** between the Ground-Station/Vehicle-Controller and execution-side services, handling API bridging, telemetry relay, shared state synchronization, and media/data transfer.

## Architecture Description

The communication framework is organized into two server roles:

- Local server (onboard/edge node)
  - Supports bidirectional UAV/UGV data exchange with the remote server over `4G`.
  - Supports additional peer data exchange over `LoRa` mesh networking.
  - Exposes local service interfaces (`local_backend_api.py`) for control processes to read state and issue control commands.
  - Coordinates `4G` cloud connectivity and `LoRa` local connectivity for communication robustness.

- Remote server (cloud/central node)
  - Aggregates and relays UAV/UGV data uploaded through `4G`.
  - Exposes unified data-query and command-dispatch APIs for frontend and upper-layer systems (`remote_backend_api.py`).
  - Handles cross-node state synchronization, telemetry aggregation, and media distribution.

### Remote-Side 4G-Redis-MySQL Acceleration Logic

- UAV/UGV telemetry is uploaded to remote APIs via `4G`.
- Fresh runtime state is written to Redis first (low-latency read/write path).
- Real-time APIs read from Redis to accelerate frontend visualization and control interaction.
- MySQL is used for persistent historical storage, traceability, and offline analytics.
- The design follows a layered pattern: Redis for real-time state, MySQL for durable history.

### Local Dual-Network Coordination (4G + LoRa)

- `4G` is used as the primary cloud link for remote synchronization and long-range command/data exchange.
- `LoRa` is used as a complementary local link for short-range or degraded-network conditions.
- Coordination principle: unify the control plane through local services, while allowing the data plane to cooperate across `4G` and `LoRa` based on link availability.

## Scope in the Full Project

This module is **not a standalone project**. It is the transport-and-coordination layer in the architecture:

- Northbound: receives mission/control requests and data queries from upper layers.
- Southbound: forwards data/commands to local executors, remote services, and storage/state backends.
- Lateral: synchronizes UAV/UGV runtime state (position, yaw, altitude, photos, task status).

## Directory Organization

```text
Commulication-Framework/
├── README.md
├── local_backend_api.py
├── remote_backend_api.py
├── run_local_server.sh
├── run_upload.sh
├── run_remote_server.sh
├── runcmd
├── Configs/
├── Models/
├── Tools/
└── RunPySHPath/
```

## Core Files and Responsibilities

- `local_backend_api.py`
  - API service for local-node data ingestion and controller-facing interfaces.
  - Accepts local uploads (state, photos, telemetry) and exposes local query endpoints.

- `remote_backend_api.py`
  - API service for remote aggregation and cross-node synchronization.
  - Provides unified remote access for system status, media retrieval, and coordination data.

- `Configs/`
  - Runtime configuration for communication endpoints, upload policies, and local uploader settings.

- `Models/`
  - Communication runtime components (uploaders, server data models, LoRa handlers, state managers).

- `Tools/`
  - Utility layer for DB/cache access, HTTP requests, data parsing/format conversion, and media helpers.
  - `HeadingFilter.py` implements the paper's wrapped-innovation adaptive Kalman filter for GV heading.

- `run_local_server.sh`
  - Launches the role-specific local API, uploader pipeline, and LoRa process.

- `run_upload.sh`
  - Launches an explicitly selected UAV or UGV uploader configuration.

- `run_remote_server.sh`
  - Launches remote backend service.

- `runcmd`
  - Utility launcher for scripted operations.

## Communication Role (High-Level)

1. Receive control/data requests from upper-layer modules.
2. Normalize and route requests to local or remote service paths.
3. Synchronize runtime state across UAV/UGV communication channels.
4. Provide unified query endpoints back to upper layers.
5. Relay media and telemetry streams for monitoring and feedback.

### GV Heading Filtering

Before GV heading telemetry is sent to either the local or remote server, `YawUploader` passes each sensor measurement through `Tools/HeadingFilter.py`. The filter implements Algorithm 1 from the paper:

- heading state and measurement residuals are wrapped to `[-pi, pi)`;
- normal innovations use the nominal measurement covariance;
- moderate innovations continuously inflate the measurement covariance;
- the first severe innovation is rejected and records its direction; a second
  consecutive severe innovation in the same direction is accepted with the
  nominal measurement covariance, while a direction change restarts confirmation.

The paper parameters are configured in `Configs/LocalUploaderConfigs/YawUploadConfig.yaml`: `Q=0.03 rad^2`, `R=2.742e-3 rad^2`, `delta_1=35 deg`, `delta_2=140 deg`, and `alpha=10`. The first valid sensor reading initializes the heading estimate, with an initial covariance of `1.0 rad^2`. Only the filtered heading is placed in the local/remote upload buffer; the raw reading is retained in memory for diagnostics.

The pose-sensor parser assigns a monotonically increasing sequence number and an acquisition timestamp to every valid `0x53` angle frame. Valid frames are queued until `YawUploader` processes them in sequence, then removed after acknowledgement by the filter loop. A frame is therefore filtered exactly once even if the polling loop observes the latest cached value repeatedly. The uploader retains the source-frame acquisition timestamp with the filtered value. Local and remote delivery are acknowledged independently only after a successful HTTP response; failed delivery is retried without inventing a newer timestamp. Opening an unavailable serial device terminates the uploader with an explicit error instead of reporting a false connection.

For a GV node, use `Configs/UploadMainConfigUGV.yaml`; it includes `YawUploader.py` and its filter configuration in the uploader process list:

```bash
bash run_upload.sh Configs/UploadMainConfigUGV.yaml
```

Set `RemoteURL` in `Configs/UploadMainConfigUGV.yaml` and the heading
sensor serial port in
`Configs/LocalUploaderConfigs/YawUploadConfig.yaml` before starting the
process. Because that role launches the complete GV sensing pipeline, also
configure:

- RTK/NTRIP credentials and the GGA serial device in
  `LocationUploadConfig.yaml`;
- the altitude-sensor serial device in `HeightUploadConfig.yaml`;
- the camera device in `PhotoUploadConfig.yaml`;
- the LoRa UART in `LoraSenderConfigs.yaml`.

On the UAV computer, set `RemoteURL` in `UploadMainConfig.yaml` and the LoRa
UART in `LoraReceiverConfig.yaml`. The serial-device user must have permission
to open every configured UART (normally membership in the Linux `dialout`
group).

For the standard local-service launch, select the node role explicitly:

```bash
# On the UAV computer: UAV telemetry upload + LoRa receiver
bash run_local_server.sh uav

# On the GV computer: GV telemetry/filtered-heading upload + LoRa sender
bash run_local_server.sh ugv
```

The UAV role uses `Configs/LocalServerConfigs.yaml` and `Configs/UploadMainConfig.yaml`. The GV role uses `Configs/LocalServerConfigsUGV.yaml` and `Configs/UploadMainConfigUGV.yaml`, which includes `YawUploader.py`. Both local-server configurations use one API worker so `/startUpload` and `/endUpload` retain ownership of the same child process. The GV LoRa sender publishes `posData` and `emergencyData`; the UAV LoRa receiver consumes both message types. The sender obtains `posData` from the GV local API and `emergencyData` from the `RemoteURL` configured in `UploadMainConfigUGV.yaml`. `posData` is emitted only after the mission ID, position, and filtered yaw have valid values and both sensor fields have mission-relative timestamps. Its exact list schema is:

```text
[x_east, y_north, filtered_heading_enu_deg, sensed_at, height, mission_id,
 v_east, v_north]
```

The controller-facing coordinate convention is standard ENU: `x` is east, `y`
is north, and heading is counter-clockwise from east. Raw clockwise-from-north
sensor heading is converted only when the synchronized control packet is built.
`sensed_at` is the earlier of the position and heading source times, so it represents freshness of the complete sensing packet rather than only its newest field. If heading updates stop while position continues, the packet timestamp therefore remains stale and the controller can enter its freshness-safety hover. The local `/pos` response also includes `mission_id` in both its geodetic-only and local-coordinate forms.

Unchanged `posData` values are retransmitted at the configured heartbeat interval. One sender scheduler rate-limits position frames and gives changed or active emergency commands priority, so message types cannot build competing UART queues. The receiver forwards received heartbeats with their original radio-arrival time, available through `GET /loraLinkStatus?data_type=posData`; a delayed HTTP retry cannot make an old radio frame look new. A repeated heartbeat updates link liveness but does not change `sensed_at`, so a live radio cannot make frozen sensor data appear fresh. Radio frames use JSON; receivers retain compatibility with the previous Python-literal position frames during rolling upgrades.

The emergency payload schema is:

```text
[emergency_stop, mission_id, source_time_unix]
```

The UAV local `GET /emergencyStop` endpoint becomes active only when the command is true and its mission ID matches the current mission. A true command remains fail-safe latched if its source later becomes unavailable. A false command is reported as an explicit source clear only while both its remote-source timestamp and radio-arrival timestamp are fresh; stale state returns HTTP `503` rather than false. This prevents a cached false value from clearing a stop and prevents a command from an earlier mission from stopping a later one. The flight Controller and Executor treat any accepted true command as a process-level hard stop, so clearing the communication source does not resume flight: inspect the aircraft and restart both processes before another mission. The remote endpoints `GET /setEmergencyStop` and `GET /clearEmergencyStop` control only the transmitted source state. Run the two role commands on their respective onboard computers, not on the same Redis instance.

### Epoch-Safe UGV State API

The remote controller retrieves position, height, derived planar velocity, and
filtered heading with one `GET /ugvState` request. The endpoint reads one Redis
snapshot and returns:

```json
{
  "mission_id": "20260731120000",
  "current_pos": [4.0, 5.0],
  "position_time": 3.4,
  "filtered_heading": -91.0,
  "heading_time": 3.2,
  "height": 2.0,
  "height_time": 3.1,
  "current_velocity": [0.5, 1.0],
  "velocity_time": 3.4,
  "sensed_at": 3.2
}
```

`position_time`, `heading_time`, and `sensed_at` are seconds relative to the active mission origin. `sensed_at` is `min(position_time, heading_time)`. The endpoint returns HTTP `404` if the mission ID, local position, filtered heading, or either mission-relative source timestamp is unavailable. Writers commit every value/timestamp pair with one Redis transaction, mission changes atomically invalidate prior telemetry and cached flight commands, and readers use one `MGET`. Upload requests must carry `mission_id`; one Redis-side conditional write rejects a delayed request if that mission is no longer active. Mission activation itself is monotonic and atomic, so an older delayed `/setTimeStr` request cannot roll back a newer numeric mission ID. This prevents a controller from observing a new timestamp with an old value or combining data across a mission reset. The local `/height`, velocity-command, and flight-mode-command responses likewise return each value and its timestamp from one snapshot.

The controller publishes its confirmed mission phase, airborne state, and
selected link to `POST /missionState` once per second and on every phase change.
The operator reads this through `GET /missionState`; `/setDepart` and `/setLand`
only report request acceptance. This separates operator intent from confirmed
`ESCORT`, `DESCENDING`, `LANDING`, and `IDLE` execution state.

Position, height, and heading uploaders acknowledge a sample only after a `2xx` HTTP response. Timeouts and non-`2xx` responses retain that destination's pending sample for retry, even if a newer sensor sample arrives in the meantime. Failed attempts use a short retry backoff.

The remote `GET /setDH?D=<metres>&H=<metres>` endpoint validates both values before storing them. `D` must be finite and in `[0, 100]` m; `H` must be finite and in `(0, 120]` m. Invalid input returns HTTP `422` and does not replace the previous configuration. The paper's `H=30` m setting is within this supported range.

All launchers resolve paths relative to this repository rather than a fixed
deployment directory. In a Conda session, set `AGCS_PYTHON_EXECUTABLE` to the
active interpreter as shown below. Child uploader and LoRa processes then reuse
that interpreter. Launch scripts do not install packages or flush an entire
Redis database.

## Quick Start

This module is deployed in three roles. Run each role on its designated host.

| Role | Configuration | Started process |
| --- | --- | --- |
| Remote server | `Configs/RemoteServerConfig.yaml` | Remote FastAPI service |
| UAV computer | `Configs/LocalServerConfigs.yaml`, `Configs/UploadMainConfig.yaml` | Local API, UAV uploaders, LoRa receiver |
| GV computer | `Configs/LocalServerConfigsUGV.yaml`, `Configs/UploadMainConfigUGV.yaml` | Local API, GV uploaders, LoRa sender |

Do not run the UAV and GV local roles against the same Redis database.

### 1. Create and activate the Conda environment

From the repository root:

```bash
cd Commulication-Framework
conda create --name agcs-communication python=3.9 pip -y
conda activate agcs-communication
python -m pip install -r requirements.txt
export AGCS_PYTHON_EXECUTABLE="$(command -v python)"
```

Run `conda activate agcs-communication` and export
`AGCS_PYTHON_EXECUTABLE` in every new shell used for this module.

### 2. Install platform services and hardware support

Redis is required by every API role. MySQL is required when the configured
uploaders enable persistent storage.

Ubuntu example:

```bash
sudo apt-get update
sudo apt-get install -y redis-server mysql-server
sudo systemctl enable --now redis-server
sudo systemctl enable --now mysql
```

The UAV and GV roles additionally require the Raspberry Pi camera and GPIO
packages used by `PhotoUtils.py` and `LoraTools.py`. Install the
platform-supported `picamera2` and `RPi.GPIO` packages so they are importable
from the active `agcs-communication` environment, then verify them with:

```bash
python -c "from picamera2 import Picamera2; import RPi.GPIO"
```

On onboard Linux computers, also enable the configured UART devices and grant
the runtime user access to them, normally through the `dialout` group.

### 3. Configure the deployment

Replace configuration placeholders before starting a service:

| Setting | Files |
| --- | --- |
| Remote API URL | `Configs/UploadMainConfig.yaml`, `Configs/UploadMainConfigUGV.yaml` |
| Redis host, port, and database | Role-specific local/remote server configuration |
| MySQL host and credentials | Enabled files under `Configs/LocalUploaderConfigs/` |
| UAV/GV sensor serial ports | `LocationUploadConfig.yaml`, `HeightUploadConfig.yaml`, `YawUploadConfig.yaml` |
| UAV/GV LoRa UART | `LoraReceiverConfig.yaml`, `LoraSenderConfigs.yaml` |
| Camera device | `PhotoUploadConfig.yaml` |

On both onboard computers, synchronize system time with NTP/PTP or a
GNSS-disciplined clock before starting a mission. The controller uses the
paper's `0.3 s` sensing timeout, so the inter-node clock error must remain
below that bound.

### 4. Start and verify the remote service

On the remote server:

```bash
conda activate agcs-communication
export AGCS_PYTHON_EXECUTABLE="$(command -v python)"
bash run_remote_server.sh
```

From another shell, verify:

```bash
curl --fail "http://REMOTE_HOST:26969/alive"
```

The default remote bind address is `0.0.0.0:26969`, configured by `Host` and
`Port` in `Configs/RemoteServerConfig.yaml`. If you change `Port`, use the same
port in both `RemoteURL` values and the Ground Station `apiBaseUrl`. A
deployment can override the bind without editing YAML by setting
`AGCS_REMOTE_HOST` and `AGCS_REMOTE_PORT`.

### 5. Start and verify the UAV local service

On the UAV computer:

```bash
conda activate agcs-communication
export AGCS_PYTHON_EXECUTABLE="$(command -v python)"
bash run_local_server.sh uav
```

The launcher starts the local API, UAV telemetry uploaders, and
`LoraReceiver.py`. Verify locally:

```bash
curl --fail http://127.0.0.1:26969/alive
```

### 6. Start and verify the GV local service

On the GV computer:

```bash
conda activate agcs-communication
export AGCS_PYTHON_EXECUTABLE="$(command -v python)"
bash run_local_server.sh ugv
```

The launcher starts the local API, GV sensing/upload processes, adaptive
heading filter, and `LoraSender.py`. Verify locally:

```bash
curl --fail http://127.0.0.1:26969/alive
```

Successful API health checks confirm process availability; they do not confirm
sensor, radio, database, or remote-link health. Inspect console logs for those
subsystems before enabling a mission.

## Runtime Notes

- Run local and remote services with correct endpoint/network configuration in `Configs/`.
- If using Redis/DB/message channels, ensure those services are reachable before startup.
- For production deployment, use `systemd` or container orchestration to keep services alive.

## Suggested Integration Position

Place `Commulication-Framework` as the **middle transport layer** in the full system:

1. Ground-Station / Vehicle-Controller (intent and query source)
2. Commulication-Framework (routing, synchronization, relay)
3. UAV-Executor and related runtime endpoints (final execution and feedback)
