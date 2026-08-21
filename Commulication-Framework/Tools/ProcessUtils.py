"""Helpers for validating long-lived subprocess startup."""

import math
import time


def ensure_processes_survive_startup(processes, grace_seconds):
    """Raise when a process exits during its initial startup grace period.

    ``processes`` is an iterable of ``(label, subprocess.Popen)`` pairs.
    A long-lived service is considered started only when every process remains
    alive for the complete grace period.
    """

    grace_seconds = float(grace_seconds)
    if not math.isfinite(grace_seconds) or grace_seconds < 0:
        raise ValueError("grace_seconds must be a non-negative finite value")

    process_entries = list(processes)
    deadline = time.monotonic() + grace_seconds
    while True:
        failures = [
            (label, process.returncode)
            for label, process in process_entries
            if process.poll() is not None
        ]
        if failures:
            details = ", ".join(
                f"{label} (exit code {return_code})"
                for label, return_code in failures
            )
            raise RuntimeError(
                f"Long-lived subprocess exited during startup: {details}"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.05, remaining))
