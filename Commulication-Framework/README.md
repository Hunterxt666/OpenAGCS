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
├── run_local_upload.sh
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

- `run_local_upload.sh`
  - Launches local upload pipeline.

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

## Quick Start

### 0) Deployment Checklist

- Remote server: `>=4 CPU`, `>=8 GB RAM`
- Onboard node: `>=4 CPU`, `>=8 GB RAM` (recommended: `Raspberry Pi 5`)

### 1) Enter module directory

```bash
cd Commulication-Framework
```

### 2) Install MySQL / Redis (Ubuntu example)

```bash
sudo apt update
sudo apt install -y redis-server mysql-server
sudo systemctl enable --now redis-server
sudo systemctl enable --now mysql
```

### 3) (Optional) Create and activate a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4) Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5) Update config (database + public IP / remote URL)

Update the remote public endpoint (`RemoteURL`) in the local uploader config:

```bash
sed -i '' 's|RemoteURL: "REMOTE_URL"|RemoteURL: "http://<REMOTE_PUBLIC_IP>:8000"|' Configs/UploadMainConfig.yaml
```

Update MySQL parameters (`host/user/pw/db_name`) in uploader configs:

```bash
sed -i '' "s|host: 'MYSQL_HOST'|host: '<MYSQL_HOST>'|" Configs/LocalUploaderConfigs/LocationUploadConfig.yaml
sed -i '' "s|user: 'MYSQL_USER'|user: '<MYSQL_USER>'|" Configs/LocalUploaderConfigs/LocationUploadConfig.yaml
sed -i '' "s|pw: 'MYSQL_PASSWORD'|pw: '<MYSQL_PASSWORD>'|" Configs/LocalUploaderConfigs/LocationUploadConfig.yaml
sed -i '' "s|db_name: 'MYSQL_DB_NAME'|db_name: '<MYSQL_DB_NAME>'|" Configs/LocalUploaderConfigs/LocationUploadConfig.yaml

sed -i '' "s|host: 'MYSQL_HOST'|host: '<MYSQL_HOST>'|" Configs/LocalUploaderConfigs/HeightUploadConfig.yaml
sed -i '' "s|user: 'MYSQL_USER'|user: '<MYSQL_USER>'|" Configs/LocalUploaderConfigs/HeightUploadConfig.yaml
sed -i '' "s|pw: 'MYSQL_PASSWORD'|pw: '<MYSQL_PASSWORD>'|" Configs/LocalUploaderConfigs/HeightUploadConfig.yaml
sed -i '' "s|db_name: 'MYSQL_DB_NAME'|db_name: '<MYSQL_DB_NAME>'|" Configs/LocalUploaderConfigs/HeightUploadConfig.yaml
```

If you run on Linux, replace `sed -i ''` with `sed -i`.

### 6) Start services (where to start)

Run the following commands from `Commulication-Framework/`:

- Start local service (local API + uploader pipeline):
```bash
bash run_local_upload.sh
```

- Start remote service (remote API aggregation):
```bash
bash run_remote_server.sh
```

Check logs from console output or your process manager.

## Runtime Notes

- Run local and remote services with correct endpoint/network configuration in `Configs/`.
- If using Redis/DB/message channels, ensure those services are reachable before startup.
- For production deployment, use `systemd` or container orchestration to keep services alive.

## Suggested Integration Position

Place `Commulication-Framework` as the **middle transport layer** in the full system:

1. Ground-Station / Vehicle-Controller (intent and query source)
2. Commulication-Framework (routing, synchronization, relay)
3. UAV-Executor and related runtime endpoints (final execution and feedback)
