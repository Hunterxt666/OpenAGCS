# Ground-Station

`Ground-Station` is one subsystem of the full air-ground collaborative project.
It provides the operator-facing interface for mission monitoring and command dispatch, including trajectory visualization, system status panels, and control actions.

## Scope in the Full Project

This module is **not a standalone project**. It acts as the front-end interaction layer:

- Northbound: human operator interaction (UI + mission operations).
- Southbound: API calls to backend communication/control services.

In the overall architecture, Ground-Station issues high-level control intent, while lower layers handle command transport and onboard execution.

## Directory Organization

```text
Ground-Station/
├── README.md
├── requirements.txt
├── server.py
├── index.html
├── assets/
│   ├── car.png
│   ├── drone.png
│   ├── favicon.ico
│   └── star.png
├── css/
│   ├── demo-center.css
│   └── styles.css
└── src/
    ├── config/
    │   └── api_config.json
    ├── main.js
    └── utils/
        ├── api.js
        ├── basicSettings.js
        ├── fillData.js
        ├── hideBlock.js
        ├── map.js
        ├── orderExecute.js
        └── showTime.js
```

## Core Files and Responsibilities

- `server.py`
  - Runs the operator-side FastAPI Web service.
  - Serves the UI and proxies a fixed allowlist of requests to the cloud API.

- `index.html`
  - Main UI container and panel layout.
  - Binds buttons, status areas, and operator actions.

- `src/main.js`
  - Front-end bootstrap logic.
  - Initializes core UI workflows.

- `src/utils/api.js`
  - Encapsulates API access and request timeout behavior.
  - Handles retrieval/submission for control and telemetry endpoints.

- `src/utils/map.js`
  - Initializes AMap instance.
  - Renders UAV/UGV markers, trajectory paths, and map updates.

- `src/utils/basicSettings.js`
  - Handles high-level operations (refresh origin, start/stop tracking, takeoff/land actions, cleanup).

- `src/utils/orderExecute.js`
  - Processes command-setting actions (for example threshold and D/H configuration).

- `src/utils/fillData.js`
  - Fills status panels with latest telemetry/state values.

- `src/utils/hideBlock.js`
  - Controls collapsible UI panels.

- `src/utils/showTime.js`
  - Maintains real-time clock updates in the UI.

## Feature Summary

- Real-time UAV/UGV trajectory visualization
- Air-ground collaborative monitoring dashboard
- Operator command dispatch and mission parameter configuration

The D/H dialog accepts `0 <= D <= 100 m` and `0 < H <= 120 m`. Its success
message is shown only after the remote `/setDH` request has completed
successfully. To reproduce the paper's reported flight height, set `H = 30 m`
and wait for that confirmation before issuing takeoff.

## Quick Start

The Ground Station runs on the operator workstation and proxies only an
allowlist of requests to the remote Communication Framework.

### 1. Create and activate the Conda environment

From the repository root:

```bash
cd Ground-Station
conda create --name agcs-ground-station python=3.9 pip -y
conda activate agcs-ground-station
python -m pip install -r requirements.txt
```

Run `conda activate agcs-ground-station` before every later operator-server
session.

### 2. Configure the browser client

Set the AMap Web JavaScript API key in `src/config/api_config.json`. Keep
`apiBaseUrl` as `/api/` when using the bundled proxy:

```json
{
  "apiBaseUrl": "/api/",
  "amapKey": "<YOUR_AMAP_WEB_JS_API_KEY>",
  "photo_timeout": 500,
  "timeout": 500
}
```

Do not commit production API keys.

### 3. Verify the remote service

```bash
curl --fail "http://REMOTE_HOST:26969/alive"
```

### 4. Start the operator server

```bash
conda activate agcs-ground-station
python server.py \
  --remote-url "http://REMOTE_HOST:26969" \
  --host 127.0.0.1 \
  --port 8080
```

The terminal should report that Uvicorn is listening on
`http://127.0.0.1:8080`.

### 5. Open and verify the interface

```text
http://127.0.0.1:8080
```

The mission panel displays controller-confirmed phases and active cellular/LoRa
source. Takeoff reports success only after `ESCORT`; landing reports success only
after confirmed `IDLE` with `airborne=false`.

## Runtime Notes

- This module expects backend communication/control services to be reachable.
- Set `AGCS_REMOTE_URL` instead of `--remote-url` when using a process manager.
- For deployment, place `server.py` behind Nginx or an equivalent reverse proxy.

## Suggested Integration Position

Place `Ground-Station` as the **operator-facing top layer** in the full system:

1. Human operator input and visualization
2. Command/API dispatch to communication framework
3. Downstream execution feedback displayed back to operator
