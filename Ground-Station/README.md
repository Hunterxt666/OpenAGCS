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

## Quick Start

1. Enter module directory:
```bash
cd Ground-Station
```

2. Install dependencies:
```bash
npm install
```

3. Configure backend endpoints in the API config file used by `src/utils/api.js`.
   - File: `src/config/api_config.json`
   - Fields: `apiBaseUrl`, `amapKey`
   - Example (direct FastAPI service on port `26969`):
```json
{
  "apiBaseUrl": "http://<backend-ip>:26969/",
  "amapKey": "<YOUR_AMAP_WEB_JS_API_KEY>"
}
```
   - Keep the trailing `/` in `apiBaseUrl`, because frontend requests append paths such as `originPos`, `uavPos`, and `setDepart`.
   - Use `.../api/` only when a reverse proxy (for example Nginx) maps backend routes to an `/api/` prefix.
   - Create the `amapKey` from the AMap Web JS API console and enable the domain you use for local preview or deployment.
   - The frontend now loads the AMap SDK dynamically from `src/config/api_config.json`, so do not hardcode the key in `index.html`.

4. Start with npm (if scripts are configured):
```bash
npm run dev
```

5. Run the Comunication Service:

6. Open in browser:
```text
http://localhost:8080
```

7. Open browser DevTools (`F12`) to inspect request/console logs during integration.

## Runtime Notes

- This module expects backend communication/control services to be reachable.
- For local debugging, ensure CORS/network settings allow browser requests to your backend.
- For deployment, host as static web assets behind Nginx or any equivalent static server.

## Suggested Integration Position

Place `Ground-Station` as the **operator-facing top layer** in the full system:

1. Human operator input and visualization
2. Command/API dispatch to communication framework
3. Downstream execution feedback displayed back to operator
