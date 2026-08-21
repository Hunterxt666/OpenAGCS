#!/usr/bin/env bash
set -euo pipefail

framework_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_path="${1:-${AGCS_UPLOAD_CONFIG:-Configs/UploadMainConfig.yaml}}"
python_executable="${AGCS_PYTHON_EXECUTABLE:-python3}"

if [[ "${config_path}" != /* ]]; then
    config_path="${framework_dir}/${config_path}"
fi

cd -- "${framework_dir}"
export PYTHONPATH="${framework_dir}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${python_executable}" \
    "${framework_dir}/Models/UploadMainData.py" \
    "${config_path}"
