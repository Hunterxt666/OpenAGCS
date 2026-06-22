# UAVcmd - UAV Onboard Executor Based on DJI Payload SDK

This module is built on DJI Payload SDK and serves as the UAV onboard executor in the larger system. The core runtime is `UAVcmd`, covering command execution, flight-interface integration, and network communication.

## Architecture Slice

This executor is designed as the onboard execution endpoint in our air-ground communication architecture.

- **Control framework**: DJI Payload SDK (PSDK) is used as the low-level flight/control interface.
- **Communication path**: Commands are delivered through the communication architecture described in this work (Ground Station -> Communication Framework -> Upper-Layer Controller -> UAV Executor).
- **Execution node**: The onboard development board (Raspberry Pi class device) receives commands and triggers control actions via `UAVcmd`.

### Command Execution Flow

1. Ground station issues high-level mission/control intent.
2. The communication framework serializes and forwards control messages to the UAV onboard node.
3. `request_utils` parses incoming requests and maps them to UAV control primitives.
4. `fly_controller` converts primitives to DJI PSDK calls.
5. The onboard board executes commands in real time and reports state/telemetry back to upstream modules.

### Why This Matters

- Decouples mission orchestration from hardware-level control.
- Keeps command transport and flight execution independently evolvable.
- Fits IoT deployment patterns: distributed command source + edge-side deterministic execution.

## Project Structure

- `doc/`: project documentation
- `out/`: build output
- `psdk_lib/`: DJI Payload SDK libraries
- `samples/`: sample code
- `tools/`: development utilities
- `UAVcmd/`: UAV control module
  - `common/`: common tools and libraries
  - `dji_utils/`: DJI-related utilities and interfaces
  - `fly_controller/`: flight control logic and commands
  - `raspi/`: Raspberry Pi related code
  - `request_utils/`: request/network utilities

## Notes

- `CMakeLists.txt` and `UAVcmd` are maintained by HUEAI.
- Other SDK files are provided by DJI.

## Build and Run

1. Enter project directory.
2. Configure/build with CMake.
3. Run `UAVcmd` after successful build.

## References

- DJI Payload SDK docs: https://developer.dji.com/payload-sdk/
