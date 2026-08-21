#!/usr/bin/env bash
set -euo pipefail

controller_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_executable="${AGCS_PYTHON_EXECUTABLE:-python3}"

cd -- "${controller_dir}"
export PYTHONPATH="${controller_dir}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${python_executable}" "${controller_dir}/uav_main.py" "$@"
