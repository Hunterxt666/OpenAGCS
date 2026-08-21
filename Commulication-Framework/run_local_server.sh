#!/usr/bin/env bash
set -euo pipefail

framework_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
node_role="${1:-uav}"
python_executable="${AGCS_PYTHON_EXECUTABLE:-python3}"

case "${node_role}" in
    uav)
        config_path="${framework_dir}/Configs/LocalServerConfigs.yaml"
        ;;
    ugv)
        config_path="${framework_dir}/Configs/LocalServerConfigsUGV.yaml"
        ;;
    *)
        config_path="${node_role}"
        if [[ "${config_path}" != /* ]]; then
            config_path="${framework_dir}/${config_path}"
        fi
        ;;
esac

cd -- "${framework_dir}"
export PYTHONPATH="${framework_dir}${PYTHONPATH:+:${PYTHONPATH}}"
export AGCS_LOCAL_SERVER_CONFIG="${config_path}"
export AGCS_PYTHON_EXECUTABLE="${python_executable}"

"${python_executable}" "${framework_dir}/local_backend_api.py" "${config_path}" &
server_pid=$!

stop_server() {
    if kill -0 "${server_pid}" 2>/dev/null; then
        kill "${server_pid}"
        wait "${server_pid}" || true
    fi
}
trap stop_server EXIT INT TERM

for _ in {1..30}; do
    if curl --fail --silent "http://127.0.0.1:26969/alive" >/dev/null; then
        break
    fi
    if ! kill -0 "${server_pid}" 2>/dev/null; then
        echo "Local backend exited before becoming ready" >&2
        exit 1
    fi
    sleep 1
done

curl --fail --silent --show-error "http://127.0.0.1:26969/startUpload"
wait "${server_pid}"

