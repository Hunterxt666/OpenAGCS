from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PROJECT_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AGCS tracking, communication, heading, and platoon analyses."
        )
    )
    parser.add_argument(
        "feature",
        nargs="*",
        choices=("all", "tracking", "communication", "heading", "platoon"),
        default=["all"],
        help="analysis feature to run (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "output",
        help="output directory (default: Experiment-Analysis/output)",
    )
    parser.add_argument(
        "--tables-only",
        action="store_true",
        help="generate tables and intermediate data without rendering figures",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove the selected output directory before analysis",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    from .project import run_project

    summary = run_project(
        output_dir=args.output,
        selected_features=args.feature,
        generate_figures=not args.tables_only,
        clean=args.clean,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
