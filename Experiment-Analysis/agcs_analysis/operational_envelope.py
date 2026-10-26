"""Reproduce the conservative state-age envelope used in the manuscript."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import pandas as pd


SPEEDS_KMH = (15.0, 30.0, 50.0, 80.0)
YAW_RATES_DEG_S = (0.0, 10.0, 20.0, 30.0, 60.0)
FORWARD_LEAD_DISTANCE_M = 10.0
POSITION_TOLERANCE_M = 5.0


def maximum_allowable_state_age(
    speed_kmh: float,
    yaw_rate_deg_s: float,
    forward_lead_distance_m: float = FORWARD_LEAD_DISTANCE_M,
    position_tolerance_m: float = POSITION_TOLERANCE_M,
) -> float:
    """Return the conservative state-age bound in seconds."""

    speed_mps = speed_kmh / 3.6
    yaw_rate_rad_s = math.radians(yaw_rate_deg_s)
    mismatch_rate_mps = (
        speed_mps + forward_lead_distance_m * yaw_rate_rad_s
    )
    if mismatch_rate_mps <= 0.0:
        raise ValueError("speed and yaw rate must produce a positive mismatch rate")
    return position_tolerance_m / mismatch_rate_mps


def state_age_envelope() -> pd.DataFrame:
    """Build manuscript Table II using its speed and yaw-rate grid."""

    rows: list[dict[str, float]] = []
    for speed_kmh in SPEEDS_KMH:
        row = {"gv_speed_kmh": speed_kmh}
        row.update(
            {
                f"yaw_{rate:g}_deg_s": maximum_allowable_state_age(
                    speed_kmh, rate
                )
                for rate in YAW_RATES_DEG_S
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for the generated envelope CSV.",
    )
    args = parser.parse_args(argv)

    table = state_age_envelope()
    fieldnames = list(table.columns)
    print(",".join(fieldnames))
    for row in table.to_dict(orient="records"):
        print(
            f"{row['gv_speed_kmh']:g},"
            + ",".join(f"{row[name]:.6f}" for name in fieldnames[1:])
        )

    if args.output_dir is None:
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "operational_envelope.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(table.to_dict(orient="records"))


if __name__ == "__main__":
    main()
