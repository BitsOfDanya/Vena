"""Package aggregate-only local follow-up outputs for versioned review."""

import hashlib
import json
from pathlib import Path

OUTPUTS = {
    "pump_episode_coverage": "analysis/pump_episode_coverage.jsonl",
    "fan_episode_coverage": "analysis/fan_episode_coverage.jsonl",
    "pump_earlier_years": "analysis/pump_earlier_years.jsonl",
    "fan_earlier_years": "analysis/fan_earlier_years.jsonl",
    "fan_feature_shift_2025": "analysis/fan_feature_shift_2025.json",
    "fan_feature_shift_2026": "analysis/fan_feature_shift_2026.json",
    "fan_monthly_shift_2025": "analysis/fan_monthly_shift_2025.jsonl",
    "fan_monthly_shift_2026": "analysis/fan_monthly_shift_2026.jsonl",
    "fan_high_volume_cohort": "analysis/fan_high_volume_cohort.json",
    "fan_prior_failure_groups_2025": "analysis/fan_prior_failure_groups_2025.jsonl",
    "fan_prior_failure_groups_2026": "analysis/fan_prior_failure_groups_2026.jsonl",
    "fan_first_failure_cohorts": "analysis/fan_first_failure_cohorts.jsonl",
    "fan_entry_cohort_ap_2025": "analysis/fan_entry_cohort_ap_2025.jsonl",
    "fan_same_second_batch": "analysis/fan_same_second_batch.jsonl",
    "fan_recurrence_phase_2024": "analysis/fan_recurrence_phase_2024.jsonl",
    "pump_entry_cohort_ap_2025": "analysis/pump_entry_cohort_ap_2025.jsonl",
    "pump_same_second_batch": "analysis/pump_same_second_batch.jsonl",
    "pump_first_failure_cohorts": "analysis/pump_first_failure_cohorts.jsonl",
    "pump_episode_weight_2024": "analysis/pump_episode_weight_2024.jsonl",
    "pump_online_alerts_2024": "analysis/pump_online_alerts_2024.jsonl",
    "pump_online_alerts_2025": "analysis/pump_online_alerts_2025.jsonl",
    "pump_online_cooldown_2024": "analysis/pump_online_cooldown_2024.jsonl",
    "pump_trigger_2024": "analysis/pump_trigger_2024.jsonl",
    "pump_trigger_2025": "analysis/pump_trigger_2025.jsonl",
    "pump_channel_age_2024": "analysis/pump_channel_age_2024.jsonl",
    "pump_prior_state_2024": "analysis/pump_prior_state_2024.jsonl",
    "pump_prior_state_2025": "analysis/pump_prior_state_2025.jsonl",
    "pump_state_counts_2024": "analysis/pump_state_counts_2024.jsonl",
    "pump_state_counts_2025": "analysis/pump_state_counts_2025.jsonl",
    "pump_multi_horizon_2024": "analysis/pump_multi_horizon_2024.jsonl",
    "pump_multi_horizon_2025": "analysis/pump_multi_horizon_2025.jsonl",
    "pump_channel_normalization_2024": "analysis/pump_channel_normalization_2024.jsonl",
    "pump_recurrence_phase_2024": "analysis/pump_recurrence_phase_2024.jsonl",
    "pump_recurrence_phase_2025": "analysis/pump_recurrence_phase_transfer_2025.jsonl",
    "pump_score_fusion_2024": "analysis/pump_score_fusion_2024.jsonl",
    "pump_score_fusion_2025": "analysis/pump_score_fusion_transfer_2025.jsonl",
    "pump_score_fusion_2026": "analysis/pump_score_fusion_diagnostic_2026.jsonl",
    "pump_tree_grid_2024": "analysis/pump_tree_grid_followup_2024.jsonl",
    "pump_tree_class_weight_2022": "analysis/pump_tree_class_weight_2022.jsonl",
    "pump_tree_class_weight_2023": "analysis/pump_tree_class_weight_2023.jsonl",
    "pump_tree_class_weight_2024": "analysis/pump_tree_class_weight_2024.jsonl",
    "pump_tree_class_weight_2025": "analysis/pump_tree_class_weight_2025.jsonl",
    "pump_tree_class_weight_2026": "analysis/pump_tree_class_weight_2026.jsonl",
    "pump_shallow_xgb_2024": "analysis/pump_shallow_xgb_2024.jsonl",
    "pump_tree_selected_2024": "analysis/pump_tree_variant_operational_2024.jsonl",
    "pump_tree_selected_2025": "analysis/pump_tree_variant_operational_2025.jsonl",
    "pump_tree_selected_2026": "analysis/pump_tree_variant_diagnostic_2026.jsonl",
    "pump_seasonal_phase_2024": "analysis/pump_seasonal_phase_2024.jsonl",
    "pump_seasonal_phase_2025": "analysis/pump_seasonal_phase_2025.jsonl",
    "pump_seasonal_phase_2026": "analysis/pump_seasonal_phase_diagnostic_2026.jsonl",
    "pump_fusion_bootstrap_week_2025": "analysis/pump_fusion_bootstrap_week_2025.json",
    "pump_phase_bootstrap_week_2025": "analysis/pump_phase_bootstrap_week_2025.json",
    "pump_phase_bootstrap_channel_2025": "analysis/pump_phase_bootstrap_channel_2025.json",
    "pump_synthetic_cold_start_7": "analysis/pump_synthetic_cold_start_7.json",
    "pump_synthetic_cold_start_42": "analysis/pump_synthetic_cold_start_42.json",
    "pump_synthetic_cold_start_2026": "analysis/pump_synthetic_cold_start_2026.json",
    "pump_cold_fallback_2025": "analysis/pump_cold_fallback_2025.jsonl",
    "pump_boundary_transfer_2025": "analysis/pump_boundary_transfer_2025.json",
    "pump_boundary_transfer_2026": "analysis/pump_boundary_transfer_2026.json",
    "fan_recency_2024": "analysis/fan_recheck_2024.jsonl",
    "fan_recency_2025": "analysis/fan_recheck_2025.jsonl",
    "fan_blend_weights_2024": "analysis/fan_blend_weights_2024.jsonl",
    "fan_blend_2025": "analysis/fan_allhistory_blend_transfer_2025.jsonl",
    "fan_blend_2026": "analysis/fan_allhistory_blend_diagnostic_2026.jsonl",
    "fan_baseline_2026": "analysis/fan_baseline_diagnostic_2026.jsonl",
    "fan_quarters_2024": "analysis/fan_quarters_2024.jsonl",
    "fan_quarters_2025": "analysis/fan_quarters_2025.jsonl",
    "fan_quarters_2026": "analysis/fan_quarters_2026.jsonl",
    "fan_consistency_2024": "analysis/fan_consistency_2024.jsonl",
    "fan_consistency_2025": "analysis/fan_consistency_2025.jsonl",
    "fan_consistency_2026": "analysis/fan_consistency_2026.jsonl",
    "fan_state_counts_2024": "analysis/fan_state_counts_2024.jsonl",
    "fan_tree_recheck_2024": "analysis/fan_tree_recheck_2024.jsonl",
    "fan_tree_class_weight_2024": "analysis/fan_tree_class_weight_2024.jsonl",
    "fan_duty_recheck_2024": "analysis/fan_duty_recheck_2024.jsonl",
    "fan_regularization_recheck_2024": "analysis/fan_regularization_recheck_2024.jsonl",
    "fan_ablation_recheck_2024": "analysis/fan_ablation_recheck_2024.jsonl",
    "fan_channel_recheck_2024": "analysis/fan_channel_recheck_2024.jsonl",
    "fan_blend_bootstrap_week_2025": "analysis/fan_blend_bootstrap_week_2025.json",
    "fan_blend_bootstrap_channel_2025": "analysis/fan_blend_bootstrap_channel_2025.json",
    "fan_blend_bootstrap_week_2026": "analysis/fan_blend_bootstrap_week_2026.json",
    "fan_blend_bootstrap_channel_2026": "analysis/fan_blend_bootstrap_channel_2026.json",
    "fan_threshold_scale_transfer": "analysis/fan_threshold_scale_transfer.jsonl",
    "fan_boundary_transfer_2025": "analysis/fan_boundary_transfer_2025.json",
    "fan_boundary_transfer_2026": "analysis/fan_boundary_transfer_2026.json",
    "fan_online_linear_2024": "analysis/fan_online_linear_2024.jsonl",
    "fan_online_blend_2024": "analysis/fan_online_blend_2024.jsonl",
    "fan_online_linear_transfer_2025": "analysis/fan_online_linear_transfer_2025.jsonl",
    "fan_online_blend_transfer_2025": "analysis/fan_online_blend_transfer_2025.jsonl",
    "fan_online_linear_2025": "analysis/fan_online_linear_2025.jsonl",
    "fan_online_blend_2025": "analysis/fan_online_blend_2025.jsonl",
    "fan_online_linear_transfer_2026": "analysis/fan_online_linear_transfer_2026.jsonl",
    "fan_online_blend_transfer_2026": "analysis/fan_online_blend_transfer_2026.jsonl",
    "fan_online_bootstrap_2025": "analysis/fan_online_bootstrap_2025.json",
    "fan_online_bootstrap_2026": "analysis/fan_online_bootstrap_2026.json",
    "fan_online_months_2025": "analysis/fan_online_months_2025.jsonl",
    "fan_online_months_2026": "analysis/fan_online_months_2026.jsonl",
    "fan_adaptive_online_2025": "analysis/fan_adaptive_online_2025.jsonl",
    "fan_adaptive_online_2026": "analysis/fan_adaptive_online_2026.jsonl",
    "fan_window_blend_2024": "analysis/fan_window_blend_2024.jsonl",
    "fan_window_blend_2025": "analysis/fan_window_blend_2025.jsonl",
    "fan_window3_blend_2024": "analysis/fan_window3_blend_2024.jsonl",
}
DESTINATION = Path("experiments/followup-results-2026-09-24.json")
FORBIDDEN_KEYS = {"channel_id", "event_id", "raw_value", "tag", "ts", "score"}


def reject_row_fields(value):
    """Fail closed if a source unexpectedly contains row-level identifiers."""
    if isinstance(value, dict):
        if FORBIDDEN_KEYS.intersection(value):
            raise ValueError("Aggregate output unexpectedly contains row-level fields")
        for nested in value.values():
            reject_row_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_row_fields(nested)


def read_aggregate(path):
    """Read one JSON record or a JSONL list from an ignored local output."""
    source = Path(path)
    if source.suffix == ".jsonl":
        return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    return json.loads(source.read_text(encoding="utf-8"))


def main():
    """Write one reviewable report containing only aggregate experiment output."""
    manifest = Path("experiments/dataset_manifest.sha256").read_bytes()
    result = {
        "run_id": "followup-20260924-1016utc",
        "starting_commit": "2ce75eb",
        "dataset_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "results": {name: read_aggregate(path) for name, path in OUTPUTS.items()},
    }
    reject_row_fields(result)
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {DESTINATION}: {len(OUTPUTS)} aggregate groups")


if __name__ == "__main__":
    main()
