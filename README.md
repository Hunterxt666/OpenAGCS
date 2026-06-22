<div align="center">
<h1>Real-Time Air-Ground Cooperative Control with Onboard UAV Computation and Dual-Mode Communication</h1>
</div>

<div align="center">

Jingjun Tan†, Qien Chen†, Binhan Sun, Shimin Wang, Hengxing Cai, Renxin Zhong*

**Guangdong Provincial Key Laboratory of Intelligent Transportation Systems, School of Intelligent Systems Engineering, Sun Yat-sen University, Shenzhen 518107, China**  
**School of Data Science, Lingnan University, Tuen Mun, Hong Kong**

† J. Tan and Q. Chen contributed equally to this work.  
\* Corresponding author: Renxin Zhong (`zhrenxin@mail.sysu.edu.cn`)

</div>

## Overview

This repository `OpenAGCS` is the open-source artifact for the paper above. It implements a real-time air-ground cooperative stack in which:

- the `Ground-Station` provides operator-facing mission monitoring and control,
- the `Commulication-Framework` bridges 4G and LoRa communication paths while synchronizing shared state,
- the `Vehicle-Controller` runs onboard UAV follow-control logic close to the execution side.

The design goal is to keep perception feedback, cross-layer state synchronization, and mission control tightly coupled while preserving modular deployment across edge and remote nodes.

## Demo

<p align="center">
  <img src="Docs/GIF/demo.gif" alt="System demo" style="max-width: 100%;">
</p>

[Original Demo Video](https://youtu.be/gD_MNeUHup0)

## System Architecture

![System architecture](Docs/Figure/system-architecture.png)

The implementation follows the same three-layer decomposition used in the paper:

| Layer | Module | Role in the system |
| --- | --- | --- |
| Interaction layer | `Ground-Station` | Displays UAV/UGV state, media, trajectories, and exposes mission actions to the operator |
| Middleware layer | `Commulication-Framework` | Synchronizes telemetry, bridges local/remote APIs, and coordinates 4G + LoRa communication |
| Control layer | `Vehicle-Controller` | Converts mission intent into onboard UAV follow, return, and landing actions |

## Repository Structure

- [Ground-Station](Ground-Station/README.md): visualization panels, map interaction, operator commands
- [Commulication-Framework](Commulication-Framework/README.md): local/remote FastAPI services, state relay, media and telemetry transport
- [Vehicle-Controller](Vehicle-Controller/README.md): onboard UAV mission loop and follow-control logic

## Paper-to-Code Mapping

### 1. Human-in-the-loop interaction

`Ground-Station` implements the top-level interface used to:

- initialize the mission origin,
- display UAV and UGV trajectories in real time,
- issue takeoff, return, landing, and parameter-setting actions,
- review live image feedback synchronized by the backend.

### 2. Dual-mode communication and state synchronization

`Commulication-Framework` contains the communication logic described in the paper:

- `local_backend_api.py` serves the edge-side API used by onboard processes,
- `remote_backend_api.py` aggregates UAV/UGV data for remote querying and supervision,
- Redis is used for low-latency runtime state,
- MySQL is used for persistent storage and traceable history,
- the local/remote split allows the system to combine 4G uplink with LoRa-side local exchange.

### 3. Onboard cooperative control

`Vehicle-Controller` holds the mission-side UAV control logic:

- `uav_main.py` keeps the controller alive and switches between idle, follow, and return states,
- `VehicleAgent/DroneAgent.py` maintains the state cache and generates velocity/yaw commands,
- `UAV-Executor` consumes the generated commands on the execution side.

## Data and Control Flow

The end-to-end runtime loop is:

1. `Ground-Station` requests origin initialization and mission actions.
2. `Commulication-Framework` stores and relays UAV/UGV state across local and remote services.
3. `Vehicle-Controller` reads shared state and computes follow-control commands onboard.
4. `UAV-Executor` executes the control stream and feeds state back into the middleware.
5. The operator observes the updated trajectory, altitude, orientation, and image feedback in `Ground-Station`.

## Quick Start

Use each module's setup guide for environment-specific installation:

- [Ground-Station Quick Start](Ground-Station/README.md)
- [Commulication-Framework Quick Start](Commulication-Framework/README.md)
- [Vehicle-Controller Quick Start](Vehicle-Controller/README.md)

For integrated reproduction, start services in the following order:

1. `Commulication-Framework`
2. `Vehicle-Controller`
3. `Ground-Station`

This order ensures the shared communication endpoints are available before the controller and UI connect.

## Reproducibility Notes

- Keep backend endpoint configuration consistent across all three modules.
- Verify Redis, MySQL, and any network-facing endpoints before starting experiments.
- Use the same origin definition for controller and visualization runs.
- Preserve logs and uploaded media when reproducing paper experiments.

## Citation

If you use this artifact in research, please cite:

```bibtex
@article{iot64019_2026,
  title   = {Real-Time Air--Ground Cooperative Control with Onboard UAV Computation and Dual-Mode Communication},
  author  = {Tan, Jingjun and Chen, Qien and Sun, Binhan and Wang, Shimin and Cai, Hengxing and Zhong, Renxin},
  year    = {2026}
}
```

## License

See the `LICENSE` file for the license terms of this repository.
