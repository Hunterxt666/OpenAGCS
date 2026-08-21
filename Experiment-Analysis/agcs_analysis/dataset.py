from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import load_manifest, resolve_path
from .parsers import ControllerLog, parse_controller_input


class ExperimentDataset:
    """Lazy access to the released experiment inputs."""

    def __init__(self, manifest: dict | None = None) -> None:
        self.manifest = manifest or load_manifest()
        self.settings = self.manifest["analysis"]
        self._controller_cache: dict[Path, ControllerLog] = {}

    @property
    def loaded_controllers(self) -> dict[Path, ControllerLog]:
        return dict(self._controller_cache)

    def controller(self, value: str | Path) -> ControllerLog:
        path = resolve_path(value)
        if path not in self._controller_cache:
            self._controller_cache[path] = parse_controller_input(path)
        return self._controller_cache[path]

    def tracking_trials(self) -> list[tuple[str, ControllerLog, Path]]:
        return [
            (
                trial["label"],
                self.controller(trial["file"]),
                resolve_path(trial["speed_file"]),
            )
            for trial in self.manifest["trials"]["table_i"]
        ]

    def representative_controller(self) -> ControllerLog:
        return self.controller(
            self.manifest["trials"]["representative"]["controller"]
        )

    def representative_uav_path(self) -> Path:
        return resolve_path(self.manifest["trials"]["representative"]["uav"])

    def communication_4g(self) -> ControllerLog:
        return self.controller(self.manifest["trials"]["communication_4g"])

    def communication_5g(self) -> ControllerLog:
        return self.controller(self.manifest["trials"]["communication_5g"])

    def communication_metrics(self) -> pd.DataFrame:
        """Return the control-aligned 5G/LoRa stream used by Table III."""
        path = resolve_path(self.manifest["trials"]["communication_metrics"])
        data = pd.read_csv(path, encoding="utf-8-sig")
        required = {
            "time",
            "ugv_5g_time",
            "dt_5g",
            "ugv_lora_time",
            "dt_lora",
        }
        missing = required - set(data.columns)
        if missing:
            raise ValueError(
                f"Missing aligned communication columns in {path}: "
                f"{', '.join(sorted(missing))}"
            )
        return data.sort_values("time").reset_index(drop=True)

    def figure_9_update_streams(self) -> pd.DataFrame:
        """Return controller-accepted cellular and LoRa update events."""
        path = resolve_path(self.manifest["trials"]["figure_9_update_streams"])
        data = pd.read_csv(path)
        required = {
            "cellular_mode",
            "source",
            "record_type",
            "state_time_s",
            "x_m",
            "y_m",
            "yaw_deg",
        }
        missing = required - set(data.columns)
        if missing:
            raise ValueError(
                f"Missing Figure 9 columns in {path}: "
                + ", ".join(sorted(missing))
            )
        return data.sort_values(
            ["cellular_mode", "line_idx"], kind="stable"
        ).reset_index(drop=True)

    def figure_10_position_streams(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return the full 5G and LoRa position streams used by Figure 10."""
        streams = []
        for key in ("figure_10_5g_positions", "figure_10_lora_positions"):
            path = resolve_path(self.manifest["trials"][key])
            data = pd.read_csv(path)
            required = {"state_time_s", "x_m", "y_m"}
            missing = required - set(data.columns)
            if missing:
                raise ValueError(
                    f"Missing Figure 10 columns in {path}: "
                    + ", ".join(sorted(missing))
                )
            streams.append(
                data.sort_values("state_time_s", kind="stable")
                .drop_duplicates("state_time_s", keep="first")
                .reset_index(drop=True)
            )
        return streams[0], streams[1]

    def figure_11_errors(self) -> pd.DataFrame:
        """Return the corrected forward-lead error reconstruction."""
        path = resolve_path(self.manifest["trials"]["figure_11_errors"])
        data = pd.read_csv(path, encoding="utf-8-sig")
        required = {
            "time",
            "err_x_5g",
            "err_y_5g",
            "err_x_lora",
            "err_y_lora",
            "err_x_proposed",
            "err_y_proposed",
        }
        missing = required - set(data.columns)
        if missing:
            raise ValueError(
                f"Missing Figure 11 columns in {path}: "
                + ", ".join(sorted(missing))
            )
        return data.sort_values("time", kind="stable").reset_index(drop=True)

    def heading_directory(self) -> Path:
        return resolve_path("data/heading")

    def heading_stems(self) -> list[str]:
        return list(self.manifest["trials"]["heading_stems"])

    def heading_settings(self) -> dict:
        return self.manifest["heading_filter"]
