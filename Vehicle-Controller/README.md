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

Current implementation focuses on UAV control. UGV logic is scaffolded and can be extended in the same pattern.

## Directory Organization

```text
Vehicle-Controller/
├── README.md
├── uav_main.py
├── run_uav_controller.sh
├── runcmd
├── Tools/
│   └── RequestTools.py
├── VehicleAgent/
│   └── DroneAgent.py
├── SimulationController/
│   ├── VehicleAgent/
│   │   └── DroneAgent.py
│   └── test_ipynb/
│       └── toturial.ipynb
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

- `SimulationController/VehicleAgent/DroneAgent.py`
  - Simulation-oriented drone agent implementation.
  - Used for PX4/Gazebo workflow validation and algorithm rehearsal.

- `SimulationController/test_ipynb/toturial.ipynb`
  - Development notebook for simulation experiments.
  - Documents quick start and interactive testing steps.

- `run_uav_controller.sh`
  - Shell entrypoint for launching controller service in deployment.

- `runcmd`
  - Utility command launcher for local ops.

- `UAV-Executor/`
  - Linked executor submodule docs.
  - Describes how control commands are consumed by onboard execution runtime.

## Control Pipeline (High-Level)

1. Receive mission/control intent from upper-layer modules.
2. Read current UAV/UGV state from communication interfaces.
3. Compute control sequence in `DroneAgent`.
4. Dispatch commands to executor-side interfaces.
5. Monitor feedback and update control state machine.

## Runtime Notes

- Designed to run as a long-lived process.
- Logs are expected to be collected by external process manager (`nohup`, `systemd`, or container runtime).
- Threaded loops are used for periodic control emission and state polling.

## Quick Start

1. Enter the module directory:
```bash
cd Vehicle-Controller
```

2. (Optional) Create and activate a Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies (adjust to your environment):
```bash
pip install -r requirements.txt
```

4. Start the UAV controller:
```bash
python3 uav_main.py
```

5. Or run in background with log redirection:
```bash
nohup bash run_uav_controller.sh > ./logs/uav_controller_$(date +%Y%m%d%H%M%S).log 2>&1 &
```

6. Check runtime logs:
```bash
tail -f ./logs/uav_controller_*.log
```

## Current Status

- UAV control path: available.
- UGV controller: temporarily closed-source.

## Suggested Integration Position

In the complete project, place `Vehicle-Controller` as the **middle control layer**:

- Northbound: mission coordination / UI / communication framework.
- Southbound: UAV onboard executor and actuator interfaces.
