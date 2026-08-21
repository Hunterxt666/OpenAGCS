from __future__ import annotations

from ..dataset import ExperimentDataset
from ..models import FeatureResult, OutputPaths
from ..platoon_simulation import (
    EscortConfig,
    PlatoonConfig,
    figure_13,
    simulate_platoon,
    simulate_uav_escort,
    simulation_series,
    summarize_escort,
    table_vii,
    write_simulation_metadata,
)
from ..reporting import export_table


def run(
    dataset: ExperimentDataset,
    outputs: OutputPaths,
    generate_figures: bool,
) -> FeatureResult:
    """Reproduce the Appendix-B leader-only platoon simulation."""

    del dataset  # This deterministic simulation has no external input files.
    platoon_config = PlatoonConfig()
    escort_config = EscortConfig()
    time_s, platoon_states = simulate_platoon(platoon_config)
    result = simulate_uav_escort(time_s, platoon_states, escort_config)
    metrics = summarize_escort(result)

    export_table(table_vii(metrics), "table_VII", outputs.tables)
    simulation_series(time_s, platoon_states, result).to_csv(
        outputs.intermediate / "figure_13_simulation_series.csv", index=False
    )
    write_simulation_metadata(
        outputs.intermediate / "figure_13_simulation_metadata.json",
        platoon_config,
        escort_config,
        metrics,
    )

    figures: list[int] = []
    if generate_figures:
        figure_13(
            time_s,
            platoon_states,
            result,
            outputs.figures,
            escort_config.freshness_threshold_s,
        )
        figures = [13]

    return FeatureResult(
        name="platoon",
        tables=["table_VII"],
        figures=figures,
        details={
            "random_seed": escort_config.random_seed,
            "relay_delay_s": escort_config.relay_delay_s,
            "packet_loss_rate": escort_config.packet_loss_rate,
            "relative_air_ground_state_load": 1.0 / 7.0,
        },
    )
