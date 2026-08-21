#!/usr/bin/env bash
set -euo pipefail

framework_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_executable="${AGCS_PYTHON_EXECUTABLE:-python3}"
config_path="${1:-${AGCS_REMOTE_SERVER_CONFIG:-Configs/RemoteServerConfig.yaml}}"

if [[ "${config_path}" != /* ]]; then
    config_path="${framework_dir}/${config_path}"
fi

cd -- "${framework_dir}"
export PYTHONPATH="${framework_dir}${PYTHONPATH:+:${PYTHONPATH}}"
export AGCS_REMOTE_SERVER_CONFIG="${config_path}"
exec "${python_executable}" "${framework_dir}/remote_backend_api.py"
