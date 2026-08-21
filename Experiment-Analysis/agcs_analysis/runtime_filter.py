from __future__ import annotations

import importlib.util
from pathlib import Path

from .config import PROJECT_DIR


RUNTIME_FILTER_PATH = (
    PROJECT_DIR.parent
    / "Commulication-Framework"
    / "Tools"
    / "HeadingFilter.py"
)


def load_runtime_heading_filter():
    """Load the exact AKF class used by the online heading uploader."""
    if not RUNTIME_FILTER_PATH.exists():
        raise FileNotFoundError(
            f"Online heading filter not found: {RUNTIME_FILTER_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "agcs_runtime_heading_filter", RUNTIME_FILTER_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot load online heading filter: {RUNTIME_FILTER_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AdaptiveHeadingKalmanFilter


AdaptiveHeadingKalmanFilter = load_runtime_heading_filter()
