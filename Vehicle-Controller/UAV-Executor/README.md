# UAV Executor Overlay for DJI Payload SDK

This directory contains the public AGCS source overlay for the onboard DJI
Payload SDK executor. It covers command ingestion, flight-control integration,
absolute-yaw handling, emergency suspension, and stale-command rejection.

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

## Public Artifact Structure

```text
UAV-Executor/
├── CMakeLists.txt
├── README.md
├── UAVcmd/
│   ├── fly_controller/
│   ├── raspi/
│   └── request_utils/
└── tests/
```

DJI sample support code, SDK libraries, aircraft credentials, and build output
are not part of this directory. They are supplied only inside an authorized
private DJI PSDK deployment tree.

## Reproducible Deployment

### 1. Create and activate the Conda build environment

Conda provides the user-space CMake and build frontends. The system compiler,
native libraries, licensed DJI PSDK, and aircraft credentials remain separate
requirements.

From the repository root:

```bash
cd Vehicle-Controller/UAV-Executor
conda create --name agcs-executor \
  --channel conda-forge \
  python=3.9 cmake ninja pkg-config -y
conda activate agcs-executor
```

Run `conda activate agcs-executor` before each later configuration, test, or
build session.

### 2. Confirm the tested platform

- **DJI Payload SDK (PSDK)**: [3.9.1](https://github.com/dji-sdk/Payload-SDK/releases/tag/3.9.1)
- **PSDK tag commit**: `159708e6ef8920f41dce11ce666a3446e91481f5`
- **AGCS source**: use the immutable public artifact revision accompanying
  the paper; the repository contains the executor overlay source, not a
  redistributable DJI-linked executable
- **Target system**: 64-bit Linux (`aarch64` or `x86_64`)
- **Compiler**: GCC/G++ with C++11 support
- **FFmpeg**: 4.x (the supplied CMake configuration rejects FFmpeg 5.x and newer)

Ubuntu 20.04/22.04 or a Debian/Raspberry Pi OS release that supplies FFmpeg 4.x is recommended. OpenCV is optional; if it is installed, the build enables image display support automatically.

The complete DJI PSDK distribution, aircraft-specific developer credentials,
and linked executor binary are not redistributed in this repository. Access to
those materials is governed by DJI's license, account authorization, and
applicable regulatory requirements. An authorized user must obtain the
compatible PSDK package and credentials privately from DJI. Because the final
binary is platform-specific and links against that licensed SDK, publishing a
generic executable would neither be legally appropriate nor operationally
usable on another aircraft.

### 3. Install system dependencies

Install the compiler, CMake, and all libraries required by this executor:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  cmake \
  git \
  pkg-config \
  ffmpeg \
  libavcodec-dev \
  libavformat-dev \
  libavutil-dev \
  libswscale-dev \
  libcurl4-openssl-dev \
  libopus-dev \
  libusb-1.0-0-dev \
  nlohmann-json3-dev
```

Verify that the target architecture and FFmpeg version are supported:

```bash
uname -m
ffmpeg -version | head -n 1
```

`uname -m` must print `aarch64` or `x86_64`, and FFmpeg must report a 4.x release.

### 4. Assemble the licensed build tree

The executor is an overlay on a complete, privately obtained DJI PSDK source
tree. After obtaining PSDK 3.9.1 under the appropriate DJI authorization,
point `PSDK_DIR` to that private tree and `AGCS_DIR` to an immutable checkout
of this artifact. The commands below verify the required inputs, copy the DJI
sample support code, and place the public HUEAI executor overlay into the
private build tree.

```bash
set -euo pipefail

: "${PSDK_DIR:?Set PSDK_DIR to the private DJI PSDK 3.9.1 source tree}"
: "${AGCS_DIR:?Set AGCS_DIR to the immutable public AGCS artifact checkout}"

test -d "$PSDK_DIR/samples"
test -d "$PSDK_DIR/psdk_lib"
test -d "$AGCS_DIR/.git"
test -f \
  "$AGCS_DIR/Vehicle-Controller/UAV-Executor/UAVcmd/fly_controller/yaw_angle_utils.h"

mkdir -p "$PSDK_DIR/UAVcmd/raspi"

cp -a "$PSDK_DIR/samples/sample_c++/platform/linux/common" \
  "$PSDK_DIR/UAVcmd/common"
cp -a "$PSDK_DIR/samples/sample_c/module_sample/utils" \
  "$PSDK_DIR/UAVcmd/dji_utils"
cp -a "$PSDK_DIR/samples/sample_c++/platform/linux/nvidia_jetson/hal" \
  "$PSDK_DIR/UAVcmd/raspi/hal"

cp -a "$AGCS_DIR/Vehicle-Controller/UAV-Executor/UAVcmd/." \
  "$PSDK_DIR/UAVcmd/"
cp "$AGCS_DIR/Vehicle-Controller/UAV-Executor/CMakeLists.txt" \
  "$PSDK_DIR/CMakeLists.txt"

# request_utils.cpp includes "json.hpp"; expose the packaged nlohmann header
# under that expected name.
ln -sfn /usr/include/nlohmann/json.hpp \
  "$PSDK_DIR/UAVcmd/request_utils/json.hpp"

# The tested CMake file links the static Opus archive at this location.
sudo install -d /usr/local/lib
sudo ln -sfn "/usr/lib/$(gcc -print-multiarch)/libopus.a" \
  /usr/local/lib/libopus.a
```

### 5. Configure the executor

Before building, provide the PSDK application credentials issued for your DJI developer application in:

```text
Payload-SDK/UAVcmd/raspi/application/dji_sdk_app_info.h
```

The repository copy contains placeholders intentionally. Fill only the copied
header inside the private deployment tree, never commit real DJI credentials,
and rotate/revoke any credential that has previously appeared in repository
history.

Check these deployment-specific settings as well:

- `UAVcmd/raspi/application/dji_sdk_config.h`: hardware connection mode. The tested source defaults to `DJI_USE_ONLY_UART`.
- `UAVcmd/raspi/hal/hal_uart.h`: UART devices. The imported DJI HAL defaults to `/dev/ttyUSB0` and `/dev/ttyACM0`.
- `UAVcmd/request_utils/request_utils.h`: upstream controller URLs. Replace `REMOTE_IP_ADDRESS` with the actual remote endpoint, including the URL scheme and port when applicable.
- `UAVcmd/fly_controller/config/flying_config.json`: flight limits, return-to-home behavior, home position, RTK, and obstacle-avoidance settings.

The local controller service is expected at `http://127.0.0.1:26969`; start that service before launching the executor.

### 6. Verify absolute-yaw semantics

The fourth controller field is an absolute ground-frame yaw angle in degrees,
matching `DJI_FLIGHT_CONTROLLER_YAW_ANGLE_CONTROL_MODE`. It is not a yaw rate
or a quantized yaw error. `fly_controller/yaw_angle_utils.h` normalizes the
target to `[-180, 180)` and rate-limits it along the shortest circular path;
for example, `179 deg -> -179 deg` is a `2 deg` transition rather than a
`358 deg` turn.

The circular-angle helper can be checked without the proprietary PSDK
libraries:

```bash
c++ -std=c++11 -Wall -Wextra -Werror \
  tests/yaw_angle_utils_test.cpp \
  -o /tmp/uav_executor_yaw_test
/tmp/uav_executor_yaw_test
```

### 7. Build

```bash
cmake -S "$PSDK_DIR" -B "$PSDK_DIR/build" \
  -DUSE_SYSTEM_ARCH=LINUX \
  -DCMAKE_BUILD_TYPE=Release

cmake --build "$PSDK_DIR/build" --parallel "$(nproc)"
```

The resulting executable is:

```text
Payload-SDK/build/bin/uav_executor
```

This executable remains inside the authorized private deployment tree and must
not be committed to or redistributed with the public artifact.

### 8. Connect and run

1. Connect the onboard Linux computer to the aircraft payload/extension port using the UART link selected in `dji_sdk_config.h`.
2. Confirm that the configured serial device exists, for example with `ls -l /dev/ttyUSB0`.
3. Power on the aircraft and remote controller, and start the local controller service on port `26969`.
4. Run the executor from the PSDK root:

```bash
cd "$PSDK_DIR"
sudo ./build/bin/uav_executor
```

Successful startup prints `[Main] App started successfully` and creates runtime logs under `Payload-SDK/Logs/`.

## References

- [DJI Payload SDK 3.9.1 release](https://github.com/dji-sdk/Payload-SDK/releases/tag/3.9.1)
- [DJI Payload SDK documentation](https://developer.dji.com/payload-sdk/)
