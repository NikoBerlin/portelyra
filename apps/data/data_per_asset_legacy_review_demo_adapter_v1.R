new_data_per_asset_legacy_review_disabled_adapter_v1 <- function() {
  unavailable <- function(...) .per_asset_review_abort("per_asset_review_source_missing")
  new_data_per_asset_review_adapter_v1(
    open_source = unavailable,
    plan_review = unavailable,
    apply_plan = unavailable
  )
}
