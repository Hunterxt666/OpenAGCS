from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .parsers import ControllerLog


def write_tex_table(data: pd.DataFrame, path: Path) -> None:
    columns = list(data.columns)

    def value_text(value) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "--"
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value).replace("_", r"\_")

    alignment = "l" + "r" * (len(columns) - 1)
    lines = [
        rf"\begin{{tabular}}{{{alignment}}}",
        r"\toprule",
        " & ".join(column.replace("_", r"\_") for column in columns)
        + r" \\",
        r"\midrule",
    ]
    for _, row in data.iterrows():
        lines.append(
            " & ".join(value_text(row[column]) for column in columns) + r" \\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def export_table(data: pd.DataFrame, name: str, output_dir: Path) -> None:
    data.to_csv(output_dir / f"{name}.csv", index=False)
    write_tex_table(data, output_dir / f"{name}.tex")


def export_timestamp_data(
    logs: dict[Path, ControllerLog], output_dir: Path
) -> None:
    sources = (
        "tasks",
        "positions",
        "deltas",
        "realtime_uav",
        "realtime_ugv",
        "remote_pos",
        "remote_yaw",
        "lora",
        "state_age",
        "payload_ugv_yaw",
    )
    rows: list[pd.DataFrame] = []
    for path, log in logs.items():
        for source in sources:
            data = getattr(log, source)
            if data.empty:
                continue
            columns = [
                column
                for column in (
                    "line_idx",
                    "wall_time",
                    "wall_elapsed_s",
                    "mission_wall_s",
                    "state_time_s",
                )
                if column in data.columns
            ]
            output = data[columns].copy()
            output.insert(0, "record_type", source)
            output.insert(0, "source_file", path.name)
            rows.append(output)
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(
            output_dir / "timestamp_reconstruction.csv", index=False
        )
