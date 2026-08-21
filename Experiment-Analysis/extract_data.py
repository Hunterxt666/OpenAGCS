#!/usr/bin/env python3
"""Extract the analysis fields from internal logs into releasable CSV files."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from agcs_analysis.config import PROJECT_DIR
from agcs_analysis.parsers import (
    UAV_GEO_COLUMNS,
    export_controller_csv,
    parse_controller_log,
    parse_uav_geo_log,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract all fields used by the reproduction pipeline from "
            "internally archived controller and UAV logs."
        )
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_DIR / "data" / "raw",
        help="Internal raw-data directory (default: data/raw).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "data",
        help="Publishable CSV directory (default: data).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raw_dir = args.raw_dir.resolve()
    output_dir = args.output_dir.resolve()

    released: list[Path] = []
    for source in sorted((raw_dir / "controller").glob("*.log")):
        destination = output_dir / "trials" / "controller" / f"{source.stem}.csv"
        export_controller_csv(parse_controller_log(source), destination)
        released.append(destination)
        print(f"Extracted {source.name} -> {destination.relative_to(PROJECT_DIR)}")

    for source in sorted((raw_dir / "uav").glob("*.log")):
        destination = output_dir / "trials" / "uav" / f"{source.stem}.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        uav_geo = parse_uav_geo_log(source).reindex(columns=UAV_GEO_COLUMNS)
        uav_geo.to_csv(
            destination,
            index=False,
            float_format="%.12g",
        )
        released.append(destination)
        print(f"Extracted {source.name} -> {destination.relative_to(PROJECT_DIR)}")

    for source in sorted((raw_dir / "heading" / "ugv").glob("*.csv")):
        destination = output_dir / "heading" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        released.append(destination)
        print(f"Copied {source.name} -> {destination.relative_to(PROJECT_DIR)}")

    if not released:
        raise RuntimeError(f"No internal inputs found below {raw_dir}")
    print(f"Released {len(released)} CSV inputs.")


if __name__ == "__main__":
    main()
