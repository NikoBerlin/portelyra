.per_asset_review_adapter_sha <- function(value) {
  digest::digest(charToRaw(enc2utf8(value)), algo="sha256", serialize=FALSE)
}
.per_asset_review_adapter_ref <- function(prefix, value) paste0(prefix, substr(.per_asset_review_adapter_sha(value), 1L, 24L))
.per_asset_review_adapter_domain_codes <- function() c(
  "desktop_cash_coverage_catalog_invalid", "cash_statement_coverage_conflict", "cash_statement_source_invalid", "cash_statement_header_invalid", "cash_statement_pdf_tool_missing", "cash_statement_balance_confirmation_invalid", "cash_statement_input_invalid",
  "cash_statement_multiple_accounts",
  # Leser-Plugins (#486, rc.373): Abschottung, Ergebnispruefung und Absturz bleiben als eigener Grund sichtbar.
  "statement_reader_failed", "statement_reader_output_invalid", "statement_reader_isolation_unavailable", "statement_reader_timeout",
  "statement_reader_unavailable",
  # Pruefstand je Portfolio (rc.380): ungepruefter Leser ohne Bestaetigung, Portfolio unklar, Speicher nicht lesbar.
  "statement_reader_unchecked", "statement_reader_check_portfolio_unknown", "statement_reader_check_input_invalid", "statement_reader_check_store_invalid",
  # Aktivierung und Kompatibilitaet (rc.381): Leser im Portfolio nicht aktiv; installiertes Plugin nach einem Update nicht mehr kompatibel.
  "statement_reader_inactive", "statement_reader_incompatible",
  # Wertpapier-Belege (#446): der Grund der Ablehnung bleibt sichtbar.
  "securities_statement_adapter_unknown", "securities_statement_source_invalid", "securities_statement_pdf_tool_missing",
  "securities_statement_account_invalid", "securities_statement_context_invalid", "securities_statement_review_invalid", "securities_statement_confirmation_invalid",
  # Splitmitteilungen (#451, rc.372): eine Korrektur der Umstellung wurde abgewiesen.
  "securities_statement_stock_split_blocked",
  # Experimenteller generischer Leser (#514): Profil ungueltig oder nicht bestaetigt.
  "generic_profile_invalid", "generic_confirmation_required",
  # Ohne diese Codes wird jeder fachliche Fehler der Korrektur zum Sammelcode
  # desktop_product_boundary_failed, und die Ursache laesst sich nicht
  # erraten. Ein Mehrfachstorno kann etwa
  # an asset_activity_correction_fifo_invalid scheitern - der Verwahrbestand wäre negativ
  # geworden -, gemeldet würde nur "Aktion blockiert" (#421, #422).
  "asset_activity_correction_attempt_conflict", "asset_activity_correction_confirmation_expired",
  "asset_activity_correction_confirmation_invalid", "asset_activity_correction_context_invalid",
  "asset_activity_correction_fifo_invalid", "asset_activity_correction_generation_conflict",
  "asset_activity_correction_input_invalid", "asset_activity_correction_predecessor_missing",
  "asset_activity_correction_preview_stale", "asset_activity_correction_publication_failed",
  "asset_activity_correction_receipt_invalid", "asset_activity_correction_storage_invalid",
  "desktop_asset_activity_active_invalid", "desktop_asset_activity_already_committed",
  "desktop_asset_activity_boundary_failed", "desktop_asset_activity_canonical_changed",
  "desktop_asset_activity_canonical_invalid", "desktop_asset_activity_confirmation_expired",
  "desktop_asset_activity_context_invalid", "desktop_asset_activity_generation_conflict",
  "desktop_asset_activity_generation_invalid", "desktop_asset_activity_fifo_invalid",
  "desktop_asset_activity_input_invalid", "desktop_asset_activity_ledger_invalid",
  "desktop_asset_activity_lock_unavailable", "desktop_asset_activity_plan_stale",
  "desktop_asset_activity_projection_unsupported", "desktop_asset_activity_publication_failed",
  "desktop_asset_activity_source_invalid", "desktop_asset_activity_storage_invalid",
  "asset_maintenance_state_context_invalid", "asset_maintenance_state_input_invalid",
  "asset_maintenance_state_store_invalid", "asset_maintenance_state_ledger_invalid",
  "asset_activity_state_algorithm_changed", "asset_activity_state_boundary_failed",
  "asset_activity_state_context_invalid", "asset_activity_state_full_rebuild_mismatch",
  "asset_activity_state_input_invalid", "asset_activity_state_job_conflict",
  "asset_activity_state_ledger_invalid", "asset_activity_state_lock_unavailable",
  "asset_activity_state_source_invalid", "asset_activity_state_source_stale",
  "asset_activity_state_store_invalid", "asset_activity_state_write_failed",
  "activity_draft_attempt_conflict", "activity_draft_boundary_failed",
  "activity_draft_confirmation_expired", "activity_draft_confirmation_invalid",
  "activity_draft_context_invalid", "activity_draft_domain_invalid",
  "activity_draft_input_invalid", "activity_draft_not_found",
  "activity_draft_publication_failed", "activity_draft_revision_conflict",
  "activity_draft_source_binding_conflict", "activity_draft_state_conflict", "activity_draft_storage_invalid",
  "synthetic_activity_draft_failpoint",
  "redundant_activity_csv_boundary_invalid", "redundant_activity_csv_encoding_invalid",
  "redundant_activity_csv_header_invalid", "redundant_activity_csv_source_invalid",
  "redundant_activity_csv_source_limit_exceeded", "redundant_activity_csv_target_exists",
  "redundant_activity_csv_target_invalid",
  "asset_quantity_scale_attempt_conflict", "asset_quantity_scale_boundary_failed",
  "asset_quantity_scale_catalog_conflict", "asset_quantity_scale_confirmation_expired",
  "asset_quantity_scale_confirmation_invalid", "asset_quantity_scale_context_invalid",
  "asset_quantity_scale_fifo_invalid", "asset_quantity_scale_generation_conflict",
  "asset_quantity_scale_input_invalid", "asset_quantity_scale_no_increase",
  "asset_quantity_scale_preview_stale", "asset_quantity_scale_publication_failed",
  "asset_quantity_scale_receipt_invalid", "asset_quantity_scale_required_exceeds_limit",
  "asset_quantity_scale_storage_invalid", "synthetic_asset_quantity_scale_failpoint",
  "desktop_cash_coverage_boundary_failed", "desktop_cash_coverage_catalog_invalid",
  "desktop_cash_coverage_canonical_changed", "desktop_cash_coverage_canonical_invalid",
  "desktop_cash_coverage_command_conflict", "desktop_cash_coverage_confirmation_consumed",
  "desktop_cash_coverage_confirmation_expired", "desktop_cash_coverage_confirmation_invalid",
  "desktop_cash_coverage_confirmation_missing", "desktop_cash_coverage_context_invalid",
  "desktop_cash_coverage_event_outside_period", "desktop_cash_coverage_input_invalid",
  "desktop_cash_coverage_lock_unavailable", "desktop_cash_coverage_mode_invalid",
  "desktop_cash_coverage_period_overlap", "desktop_cash_coverage_predecessor_conflict",
  "desktop_cash_coverage_predecessor_missing", "desktop_cash_coverage_preview_stale",
  "desktop_cash_coverage_receipt_invalid", "desktop_cash_coverage_reconciliation_mismatch",
  "desktop_cash_coverage_recovery_confirmation_consumed", "desktop_cash_coverage_recovery_invalid",
  "desktop_cash_coverage_recovery_missing", "desktop_cash_coverage_recovery_stale",
  "desktop_cash_coverage_revision_invalid", "desktop_cash_coverage_store_exists",
  "desktop_cash_coverage_store_invalid", "desktop_cash_coverage_store_upgrade_required",
  "desktop_cash_coverage_write_failed", "synthetic_desktop_cash_coverage_failpoint"
)
.per_asset_review_adapter_domain_abort <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% .per_asset_review_adapter_domain_codes()) {
    .per_asset_review_abort("per_asset_review_adapter_failed")
  }
  stop(structure(
    list(message=code, call=NULL, code=code),
    class=c("spot_desktop_product_adapter_domain_error", "error", "condition")
  ))
}
.per_asset_review_adapter_utc_add <- function(value, seconds) {
  parsed <- as.POSIXct(value, "%Y-%m-%dT%H:%M:%SZ", tz="UTC")
  if (is.na(parsed)) .per_asset_review_abort("per_asset_review_adapter_failed")
  format(parsed + seconds, "%Y-%m-%dT%H:%M:%SZ", tz="UTC")
}
.per_asset_review_adapter_path_safe <- function(path, regular=TRUE) {
  if (!is.character(path) || length(path)!=1L || is.na(path) || !nzchar(path) || !grepl("^/", path)) return(FALSE)
  current <- "/"
  for (part in strsplit(sub("^/+", "", path), "/", fixed=TRUE)[[1L]]) {
    current <- file.path(current, part)
    if (file.exists(current) || dir.exists(current)) {
      link <- suppressWarnings(Sys.readlink(current)); if (length(link)!=1L || is.na(link) || nzchar(link)) return(FALSE)
    }
  }
  exists <- if (regular) file.exists(path) && !dir.exists(path) else dir.exists(path)
  isTRUE(exists)
}
.per_asset_review_adapter_decode_v1 <- function(output, status, stderr_size) {
  one_line <- length(output) == 1L && !is.na(output[[1L]]) &&
    nchar(output[[1L]], type = "bytes") <= 32000000L
  if (!one_line || is.na(stderr_size) || (!identical(status, 0L) && stderr_size != 0)) return(NULL)
  tryCatch(jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE), error = function(error) NULL)
}

.per_asset_review_adapter_run <- function(project_root, command, payload) {
  python <- Sys.which("python3"); script <- file.path(project_root, "scripts", "per_asset_legacy_review.py")
  if (!nzchar(python) || !file.exists(script) || nzchar(Sys.readlink(script))) .per_asset_review_abort("per_asset_review_adapter_failed")
  input <- as.character(jsonlite::toJSON(payload, auto_unbox=TRUE, null="null", digits=NA, pretty=FALSE, POSIXt="ISO8601", Date="ISO8601"))
  if(nchar(input,type="bytes")>32000000L) .per_asset_review_abort("per_asset_review_adapter_failed")
  stderr_path<-tempfile("portelyra-adapter-stderr-");on.exit(unlink(stderr_path,force=TRUE),add=TRUE);file.create(stderr_path);Sys.chmod(stderr_path,"0600")
  output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(script), command), stdout=TRUE, stderr=stderr_path, input=input)), error=function(error) structure(character(), status=1L))
  status <- attr(output, "status"); if (is.null(status)) status <- 0L
  stderr_size<-if(file.exists(stderr_path))file.info(stderr_path)$size else NA_real_
  value <- .per_asset_review_adapter_decode_v1(output, status, stderr_size)
  if(!is.list(value)||is.null(names(value))) value<-NULL
  expected <- switch(command,
    open="opened", plan="planned", apply="applied",
    `product-binding`="product_binding_read", `product-activity-view`="product_activity_view_read",
    `product-catalog`="product_catalog_read", `product-preview`="product_previewed", `product-apply`="product_applied",
    `product-republish`="product_republished",
    `native-activity-time`="native_activity_time_resolved", `native-activity-preview`="native_activity_previewed",
    `native-activity-apply`="native_activity_applied",
    `redundant-activity-inspect`="redundant_activity_inspected",
    `activity-draft-create`="activity_draft_created", `activity-draft-create-or-reuse`="activity_draft_created_or_reused",
    `activity-draft-update`="activity_draft_updated", `activity-draft-resolve-fee`="activity_draft_fee_resolved",
    # Seit rc.324: Diese Befehle rief die App auf, ohne ihre Rueckmeldung zu kennen - jeder Aufruf endete als
    # "adapter_failed", obwohl die Python-Seite ihn ausgefuehrt hatte. Der Abgleich steht jetzt im Vertragstest der Bruecke.
    `activity-draft-shift-second`="activity_draft_shift_checked",
    `activity-draft-bind-fifo-order`="activity_draft_fifo_order_bound", `activity-draft-bind-fifo-order-group`="activity_draft_fifo_order_group_bound",
    `activity-draft-standard-recovery-prepare`="activity_draft_standard_recovery_prepared",
    `activity-draft-standard-recovery-simulate`="activity_draft_standard_recovery_simulated",
    `cash-statement-gross-preview`="cash_statement_gross_previewed", `cash-statement-gross-apply`="cash_statement_gross_applied",
    `activity-draft-read`="activity_draft_read", `activity-draft-validate`="activity_draft_validated",
    `activity-draft-explain`="activity_draft_explained",
    `activity-draft-confirmation`="activity_draft_confirmation_built",
    `activity-draft-apply`="activity_draft_applied", `activity-draft-resume`="activity_draft_resumed",
    `activity-draft-list`="activity_draft_listed", `activity-draft-retire-preview`="activity_draft_retire_previewed", `activity-draft-retire-apply`="activity_draft_retired",
    `activity-mapping-profile-save`="activity_mapping_profile_saved",
    `activity-mapping-profile-list`="activity_mapping_profiles_listed", `activity-mapping-profile-read`="activity_mapping_profile_read",
    `activity-csv-inspect`="activity_csv_inspected", `activity-csv-preview`="activity_csv_previewed",
    `activity-csv-confirmation`="activity_csv_confirmation_built", `activity-csv-apply`="activity_csv_applied",
    `activity-csv-resumable`="activity_csv_resumable_read", `activity-csv-resume`="activity_csv_resumed",
    `activity-csv-export`="activity_csv_exported", `reward-booked-match`="reward_booked_matched", `reward-references-record`="reward_references_recorded",
    `asset-maintenance-state`="asset_maintenance_state_read", `asset-maintenance-preview`="asset_maintenance_declaration_previewed", `asset-maintenance-apply`="asset_maintenance_declaration_applied", `asset-maintenance-runs`="asset_maintenance_runs_read", `cash-statement-adapters`="cash_statement_adapters_listed", `cash-statement-detect`="cash_statement_detected", `cash-statement-preview`="cash_statement_previewed", `cash-statement-apply`="cash_statement_applied", `statement-reader-check`="statement_reader_check_read", `statement-reader-check-confirm`="statement_reader_check_confirmed", `statement-reader-offered`="statement_reader_offered_read", `cash-movements`="cash_movements_listed", `securities-statement-adapters`="securities_statement_adapters_listed", `securities-statement-review`="securities_statement_reviewed", `securities-statement-csv`="securities_statement_csv_written",`securities-statement-confirm`="securities_statement_confirmation_recorded", `securities-statement-advance-lump-sums`="securities_statement_advance_lump_sums_recorded", `securities-statement-stock-splits`="securities_statement_stock_splits_recorded", `securities-statement-references`="securities_statement_references_recorded", `generic-statement-propose`="generic_statement_proposed", `generic-statement-profile-save`="generic_statement_profile_saved", `booked-latest-dates`="booked_latest_dates_read", `reward-account-suggest`="reward_accounts_suggested",
    `activity-correction-candidates`="activity_correction_candidates_read",
    `generation-retention-plan`="generation_retention_planned", `generation-retention-apply`="generation_retention_applied",
    `activity-correction-preview`="activity_correction_previewed",
    `activity-correction-confirmation`="activity_correction_confirmation_built",
    `activity-correction-apply`="activity_correction_applied", `activity-correction-history`="activity_correction_history_read",
    `quantity-scale-preview`="quantity_scale_previewed", `quantity-scale-confirmation`="quantity_scale_confirmation_built",
    `quantity-scale-begin`="quantity_scale_begun", `quantity-scale-finalize`="quantity_scale_finalized",
    `quantity-scale-pending`="quantity_scale_pending_read",
    `realized-state-materialize`="realized_state_materialized", `realized-state-read`="realized_state_read",
    `realized-state-verify`="realized_state_verified", `portfolio-readiness-read`="portfolio_readiness_read",
    `cash-coverage-catalog`="cash_coverage_catalog_read", `cash-coverage-view`="cash_coverage_view_read",
    `cash-coverage-revision-candidates`="cash_coverage_revision_candidates_read",
    `cash-coverage-recovery-candidates`="cash_coverage_recovery_candidates_read",
    `cash-coverage-preview`="cash_coverage_previewed", `cash-coverage-reviewed-preview`="cash_coverage_reviewed_previewed",
    `cash-coverage-confirmation`="cash_coverage_confirmation_built", `cash-coverage-apply`="cash_coverage_applied",
    `cash-check-balance-prepare`="cash_check_balance_prepared", `cash-manual-booking-prepare`="cash_manual_booking_prepared",
    `cash-manual-batch-apply`="cash_manual_batch_applied", `cash-evidence-overview`="cash_evidence_overview_read",
    `cash-coverage-recovery-preview`="cash_coverage_recovery_previewed",
    `cash-coverage-recovery-confirmation`="cash_coverage_recovery_confirmation_built",
    `cash-coverage-recovery-apply`="cash_coverage_recovery_applied", NULL)
  if (!identical(status, 0L) && is.list(value) && identical(value$status, "blocked") &&
      is.character(value$code) && length(value$code) == 1L && value$code %in% .per_asset_review_adapter_domain_codes()) {
    .per_asset_review_adapter_domain_abort(value$code)
  }
  if (!identical(status, 0L) || !is.list(value) || is.null(expected) || !identical(value$status, expected)) .per_asset_review_abort("per_asset_review_adapter_failed")
  value
}
.per_asset_review_adapter_fixture_review <- function(projection, target, accounts) {
  bindings <- lapply(seq_along(projection$source_account_candidates), function(index) {
    candidate <- projection$source_account_candidates[[index]]
    account <- accounts[[index]]; if (is.null(account)) .per_asset_review_abort("per_asset_review_adapter_failed")
    list(source_account_fingerprint=candidate$source_account_fingerprint, account_ref=account$account_id)
  })
  row_reviews <- lapply(projection$rows, function(row) {
    review <- list(source_row_ref=row$source_row_ref, basis_evidence_mode=NULL, basis_amount_mode=NULL, provided_basis_decimal=NULL,
      original_acquired_time_evidence=NULL, original_acquired_local_date=NULL, original_acquired_local_time=NULL,
      original_acquired_time_zone=NULL, original_acquired_at_utc=NULL, movement_context_code=NULL, fee_treatment=NULL,
      memo_action=if (is.null(row$source_memo)) NULL else "accept_source", duplicate_action=NULL, dividend_input_mode=NULL,
      dividend_gross_total_decimal=NULL, same_day_fifo_sequence=NULL)
    if (identical(row$normalized_event_type, "reward")) { review$basis_evidence_mode <- "valuation_confirmed_as_basis"; review$basis_amount_mode <- "source_quantity_unit_price" }
    if (identical(row$normalized_event_type, "deposit")) { review$basis_evidence_mode <- "provided_basis"; review$basis_amount_mode <- "source_quantity_unit_price"; review$original_acquired_time_evidence <- "date_only"; review$original_acquired_local_date <- "2024-02-01"; review$original_acquired_time_zone <- "Europe/Berlin"; review$movement_context_code <- "unclassified" }
    if (identical(row$normalized_event_type, "withdrawal")) { review$fee_treatment <- "principal_asset_quantity"; review$movement_context_code <- "custody_exit" }
    if (identical(row$normalized_event_type, "transfer")) review$fee_treatment <- "principal_asset_quantity"
    review
  })
  list(per_asset_trade_plan_version=1L, projection_fingerprint=projection$projection_fingerprint,
       target_asset=list(asset_ref=target$asset_id, asset_type=target$asset_type, quantity_scale=target$quantity_scale, target_review_confirmed=TRUE),
       basis_currency="EUR", execution_currency="EUR", time_zone="Europe/Berlin",
       accounts=lapply(accounts, function(account) list(account_ref=account$account_id, account_type=account$account_type)),
       account_bindings=bindings, companion_review=NULL, row_reviews=row_reviews)
}
.per_asset_review_adapter_public_source <- function(state, projection) {
  rows <- lapply(projection$rows, function(row) list(
    source_row_id=row$source_row_ref, ordinal=as.integer(row$source_row_ordinal), date=row$local_date,
    time=row$local_time, time_evidence=row$event_time_evidence,
    event_type=if (is.null(row$normalized_event_type)) "interest" else row$normalized_event_type,
    quantity_decimal=row$quantity_decimal, unit_price_decimal=row$unit_price_decimal, fee_decimal=row$source_fee_decimal,
    memo=row$source_memo, initial_disposition=row$initial_disposition,
    decision_codes=as.character(unlist(row$decision_codes, use.names=FALSE)), blocker_codes=as.character(unlist(row$blocker_codes, use.names=FALSE))
  ))
  source_accounts <- lapply(projection$source_account_candidates, function(value) list(source_account_key=value$source_account_fingerprint, label=value$source_account_label))
  companion <- state$companion_projection
  public_companion <- if (is.null(companion)) NULL else list(
    status="available", display_name_candidate=companion$display_name_candidate,
    isin_candidate=companion$optional_candidates$isin, wkn_candidate=companion$optional_candidates$wkn,
    note_candidate=companion$optional_candidates$note, provider_listing_field_count=as.integer(companion$provider_listing_field_count),
    tax_hint_present=isTRUE(companion$classification_hint_presence$tax_type_present),
    account_binding_imported=FALSE, provider_listing_value_imported=FALSE, tax_value_imported=FALSE
  )
  list(source_contract_version=1L, source_status=projection$projection_status, source_token=state$source_token, companion=public_companion,
       target_assets=lapply(state$assets, function(value) list(asset_id=value$asset_id, label=value$label, asset_type=value$asset_type, quantity_scale=value$quantity_scale)),
       target_accounts=lapply(state$accounts, function(value) list(account_id=value$account_id, label=value$label, account_type=value$account_type)),
       source_accounts=source_accounts, rows=rows, source_row_count=length(rows))
}
.per_asset_review_adapter_exact <- function(value) {
  if (is.null(value)) return("—")
  if (!is.list(value) || !setequal(names(value), c("exact_number_status", "decimal", "numerator_integer", "denominator_integer"))) .per_asset_review_abort("per_asset_review_adapter_failed")
  if (identical(value$exact_number_status, "exact_decimal") && is.character(value$decimal)) return(value$decimal)
  if (identical(value$exact_number_status, "exact_ratio") && is.character(value$numerator_integer) && is.character(value$denominator_integer)) return(paste0(value$numerator_integer, "/", value$denominator_integer))
  .per_asset_review_abort("per_asset_review_adapter_failed")
}
.per_asset_review_adapter_reconciliation <- function(fifo) {
  empty <- list(
    status="not_computed", event_counts=list(), account_positions=list(), remaining_lot_count=0L,
    realized_sales=list(), outgoing_receipt_count=0L, transfer_receipt_count=0L,
    cost_average=list(status="not_computed", remaining_quantity="—", remaining_fifo_basis="—", cost_average="—"),
    totals=list(monetary_fee="—", monetary_fee_currency="—", asset_fee_quantity="—", dividend_income="—", reward_income="—", income_currency="—"),
    cash_posting_count=0L, synthetic_cash_posting_created=FALSE, provider_price_used=FALSE, tax_classification_inferred=FALSE
  )
  if (is.null(fifo)) return(empty)
  if (!is.list(fifo) || !is.character(fifo$fifo_status) || !is.list(fifo$event_counts) || !is.list(fifo$account_positions) ||
      !is.list(fifo$remaining_lots) || !is.list(fifo$realized_sales) || !is.list(fifo$outgoing_lot_receipts) ||
      !is.list(fifo$transfer_lot_receipts) || !is.list(fifo$cost_average) || !is.list(fifo$totals)) .per_asset_review_abort("per_asset_review_adapter_failed")
  event_counts <- lapply(fifo$event_counts, function(value) list(event_type=value$event_type, count=as.integer(value$count)))
  account_positions <- lapply(seq_along(fifo$account_positions), function(index) {
    value <- fifo$account_positions[[index]]
    list(account_label=sprintf("Konto %d", index), quantity=.per_asset_review_adapter_exact(value$quantity),
         known_fifo_basis=.per_asset_review_adapter_exact(value$known_fifo_basis), basis_status=value$basis_status)
  })
  sales <- lapply(seq_along(fifo$realized_sales), function(index) {
    value <- fifo$realized_sales[[index]]
    list(sale_ref=sprintf("reconciled_sale_%04d", index), quantity=.per_asset_review_adapter_exact(value$quantity),
         net_proceeds=.per_asset_review_adapter_exact(value$net_proceeds), consumed_fifo_basis=.per_asset_review_adapter_exact(value$consumed_fifo_basis),
         realized_gain=.per_asset_review_adapter_exact(value$realized_gain), realized_gain_status=value$realized_gain_status)
  })
  cost <- fifo$cost_average; totals <- fifo$totals
  list(
    status=fifo$fifo_status, event_counts=event_counts, account_positions=account_positions,
    remaining_lot_count=as.integer(length(fifo$remaining_lots)), realized_sales=sales,
    outgoing_receipt_count=as.integer(length(fifo$outgoing_lot_receipts)), transfer_receipt_count=as.integer(length(fifo$transfer_lot_receipts)),
    cost_average=list(status=cost$cost_average_status, remaining_quantity=.per_asset_review_adapter_exact(cost$remaining_quantity),
                      remaining_fifo_basis=.per_asset_review_adapter_exact(cost$remaining_fifo_basis), cost_average=.per_asset_review_adapter_exact(cost$cost_average)),
    totals=list(monetary_fee=.per_asset_review_adapter_exact(totals$monetary_fee), monetary_fee_currency=totals$monetary_fee_currency,
                asset_fee_quantity=.per_asset_review_adapter_exact(totals$asset_fee_quantity), dividend_income=.per_asset_review_adapter_exact(totals$dividend_income),
                reward_income=.per_asset_review_adapter_exact(totals$reward_income), income_currency=totals$income_currency),
    cash_posting_count=as.integer(fifo$cash_posting_count), synthetic_cash_posting_created=isTRUE(fifo$synthetic_cash_posting_created),
    provider_price_used=isTRUE(fifo$provider_price_used), tax_classification_inferred=isTRUE(fifo$tax_classification_inferred)
  )
}
.per_asset_review_adapter_plan_public <- function(state, plan, token) {
  source_by_id <- setNames(state$projection$rows, vapply(state$projection$rows, `[[`, character(1L), "source_row_ref"))
  rows <- lapply(plan$rows, function(row) {
    source <- source_by_id[[row$source_row_ref]]; effect <- row$activity_effect
    list(source_row_id=row$source_row_ref, ordinal=as.integer(row$source_row_ordinal), date=source$local_date, time=source$local_time,
         event_type=if (is.null(row$normalized_event_type)) "interest" else row$normalized_event_type, disposition=row$disposition,
         decision_codes=as.character(unlist(row$decision_codes, use.names=FALSE)), blocker_codes=as.character(unlist(row$blocker_codes, use.names=FALSE)),
         asset_effect=if (is.null(effect)) "unavailable" else paste(effect$inventory_effect_code, effect$portfolio_quantity_change_decimal, sep=":"),
         fifo_effect=if (is.null(effect)) "unavailable" else effect$fifo_effect_code,
         guv_effect=if (is.null(effect) || is.null(effect$net_trade_proceeds_decimal)) "none_or_pending_fifo" else paste0("net_proceeds:", effect$net_trade_proceeds_decimal),
         income_effect=if (is.null(effect) || is.null(effect$gross_income_decimal)) "none" else paste0("gross_income:", effect$gross_income_decimal),
         fee_effect=if (is.null(effect)) "unavailable" else paste("money", if (is.null(effect$monetary_fee_decimal)) "0" else effect$monetary_fee_decimal, "asset", if (is.null(effect$asset_fee_quantity_decimal)) "0" else effect$asset_fee_quantity_decimal),
         transfer_effect=if (is.null(effect) || !isTRUE(effect$transfer_lot_carry_required)) "none" else "carry_lots")
  })
  status <- if (startsWith(plan$plan_status, "ready_for_sandbox_apply")) "ready" else plan$plan_status
  list(plan_contract_version=1L, status=status, row_dispositions=rows,
       reconciliation=.per_asset_review_adapter_reconciliation(plan$fifo_reconciliation),
       summary=list(ready_count=as.integer(plan$ready_row_count), decision_required_count=as.integer(plan$decision_required_row_count), blocked_count=as.integer(plan$blocked_row_count)), plan_token=token)
}

new_data_per_asset_legacy_review_fixture_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  fixture_root <- normalizePath(file.path(project_root, "fixtures", "product", "legacy-per-asset-review-v1"), winslash="/", mustWork=TRUE)
  source_path <- file.path(fixture_root, "invented_asset_trades.csv"); companion_path <- file.path(fixture_root, "invented_assets.csv")
  if (!.per_asset_review_adapter_path_safe(source_path) || !.per_asset_review_adapter_path_safe(companion_path)) .per_asset_review_abort("per_asset_review_adapter_failed")
  target_root <- file.path(runtime_data_space_path(context), "per_asset_review_sandbox")
  state <- new.env(parent=emptyenv()); state$projection <- NULL; state$companion_projection <- NULL; state$plans <- new.env(hash=TRUE, parent=emptyenv())
  state$source_token <- .per_asset_review_adapter_ref("src_", paste(runtime_context_fingerprint(context), source_path, sep="|"))
  state$assets <- list(list(asset_id="ast_aaaaaaaaaaaaaaaa", label="Invented Alpha Asset", asset_type="crypto", quantity_scale=8L))
  state$accounts <- list(list(account_id="acc_aaaaaaaaaaaaaaaa", label="Invented Target Wallet A", account_type="crypto_wallet"), list(account_id="acc_bbbbbbbbbbbbbbbb", label="Invented Target Wallet B", account_type="crypto_wallet"))
  open_source <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    if (!.per_asset_review_adapter_path_safe(source_path) || !.per_asset_review_adapter_path_safe(companion_path)) .per_asset_review_abort("per_asset_review_adapter_failed")
    value <- .per_asset_review_adapter_run(project_root, "open", structure(list(), names=character()))
    state$projection <- value$projection; state$companion_projection <- value$companion_projection
    .per_asset_review_adapter_public_source(state, state$projection)
  }
  plan_review <- function(bound_context, source_token, browser_review) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context)) || !identical(source_token, state$source_token) || is.null(state$projection)) .per_asset_review_abort("per_asset_review_context_invalid")
    review <- .per_asset_review_adapter_fixture_review(state$projection, state$assets[[1L]], state$accounts)
    browser_bindings <- setNames(browser_review$source_account_bindings, vapply(browser_review$source_account_bindings, `[[`, character(1L), "source_account_key"))
    for (index in seq_along(review$account_bindings)) {
      binding <- browser_bindings[[review$account_bindings[[index]]$source_account_fingerprint]]
      if (is.null(binding)) .per_asset_review_abort("per_asset_review_form_invalid")
      review$account_bindings[[index]]$account_ref <- binding$target_account_id
    }
    review$target_asset$asset_ref <- browser_review$target_asset_id
    selected_asset <- Filter(function(value) identical(value$asset_id, browser_review$target_asset_id), state$assets)
    if (length(selected_asset)!=1L) .per_asset_review_abort("per_asset_review_form_invalid")
    review$target_asset$asset_type <- selected_asset[[1L]]$asset_type
    review$target_asset$quantity_scale <- selected_asset[[1L]]$quantity_scale
    selected <- setNames(browser_review$row_reviews, vapply(browser_review$row_reviews, `[[`, character(1L), "source_row_id"))
    review$row_reviews <- lapply(review$row_reviews, function(default) {
      item <- selected[[default$source_row_ref]]
      if (is.null(item) || !identical(item$decision, "accept")) return(list(source_row_ref=default$source_row_ref, basis_evidence_mode=NULL, basis_amount_mode=NULL, provided_basis_decimal=NULL, original_acquired_time_evidence=NULL, original_acquired_local_date=NULL, original_acquired_local_time=NULL, original_acquired_time_zone=NULL, original_acquired_at_utc=NULL, movement_context_code=NULL, fee_treatment=NULL, memo_action=NULL, duplicate_action=NULL, dividend_input_mode=NULL, dividend_gross_total_decimal=NULL, same_day_fifo_sequence=NULL))
      list(source_row_ref=default$source_row_ref, basis_evidence_mode=item$basis_evidence_mode, basis_amount_mode=item$basis_amount_mode,
           provided_basis_decimal=item$provided_basis_decimal, original_acquired_time_evidence=item$original_acquired_time_evidence,
           original_acquired_local_date=item$original_acquired_local_date, original_acquired_local_time=item$original_acquired_local_time,
           original_acquired_time_zone=item$original_acquired_time_zone, original_acquired_at_utc=item$original_acquired_at_utc,
           movement_context_code=item$movement_context_code, fee_treatment=item$fee_treatment, memo_action=item$memo_action,
           duplicate_action=item$duplicate_action, dividend_input_mode=item$dividend_input_mode,
           dividend_gross_total_decimal=item$dividend_gross_total_decimal, same_day_fifo_sequence=item$same_day_fifo_sequence)
    })
    browser_companion <- browser_review$companion_review
    companion_projection <- state$companion_projection
    companion_review <- NULL
    if (!is.null(browser_companion) && identical(browser_companion$action, "bind")) {
      companion_review <- list(
        asset_companion_version=1L, projection_fingerprint=companion_projection$projection_fingerprint,
        source_asset_link_fingerprint=companion_projection$source_asset_link_fingerprint,
        display_name_action=browser_companion$display_name_action, manual_display_name=browser_companion$manual_display_name,
        asset_type="crypto", quantity_scale=8L,
        optional_field_actions=list(isin=if (isTRUE(browser_companion$accept_isin)) "accept_candidate" else "skip",
                                    wkn=if (isTRUE(browser_companion$accept_wkn)) "accept_candidate" else "skip",
                                    note=if (isTRUE(browser_companion$accept_note)) "accept_candidate" else "skip")
      )
    } else {
      companion_projection <- NULL
    }
    value <- .per_asset_review_adapter_run(project_root, "plan", list(projection=state$projection, review=review, companion_projection=companion_projection, companion_review=companion_review))
    token <- .per_asset_review_adapter_ref("pln_", value$plan$plan_fingerprint); assign(token, list(plan=value$plan, review=value$review), envir=state$plans)
    .per_asset_review_adapter_plan_public(state, value$plan, token)
  }
  apply_plan <- function(bound_context, plan_token) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context)) || !exists(plan_token, envir=state$plans, inherits=FALSE)) .per_asset_review_abort("per_asset_review_context_invalid")
    entry <- get(plan_token, envir=state$plans, inherits=FALSE); data_space <- runtime_data_space_path(context)
    if (!dir.exists(data_space)) dir.create(data_space, recursive=TRUE, mode="0700")
    if (!.per_asset_review_adapter_path_safe(data_space, regular=FALSE)) .per_asset_review_abort("per_asset_review_adapter_failed")
    Sys.chmod(data_space, "0700", use_umask=FALSE)
    if (!dir.exists(target_root)) dir.create(target_root, recursive=FALSE, mode="0700")
    if (!.per_asset_review_adapter_path_safe(target_root, regular=FALSE)) .per_asset_review_abort("per_asset_review_adapter_failed")
    Sys.chmod(target_root, "0700", use_umask=FALSE)
    now <- format(as.POSIXct(Sys.time(), tz="UTC"), "%Y-%m-%dT%H:%M:%SZ", tz="UTC"); suffix <- substr(entry$plan$plan_fingerprint, 1L, 16L)
    value <- .per_asset_review_adapter_run(project_root, "apply", list(projection=state$projection, review=entry$review, expected_plan_fingerprint=entry$plan$plan_fingerprint,
      context=list(tenant_ref=.per_asset_review_adapter_ref("ten_", context$tenant_id), user_ref=.per_asset_review_adapter_ref("usr_", context$user_id), data_space_ref=.per_asset_review_adapter_ref("sbx_", context$data_space_id), actor_ref=.per_asset_review_adapter_ref("act_", context$actor_id), role="desktop_owner"),
      target_root=target_root, bundle_name=paste0("invented-per-asset-", suffix), challenge_id=paste0("pac_", substr(.per_asset_review_adapter_sha(paste(now, plan_token)), 1L, 32L)), issued_at_utc=now, confirmed_at_utc=now, expires_at_utc=.per_asset_review_adapter_utc_add(now, 300), applied_at_utc=now))
    list(apply_contract_version=1L, status="completed", receipt_ref=value$result$bundle_ref, row_count=as.integer(entry$plan$source_row_count), artifact_count=4L, sandbox_only=TRUE, canonical_write_performed=FALSE, cash_settlement_created=FALSE)
  }
  adapter <- new_data_per_asset_review_adapter_v1(open_source, plan_review, apply_plan)
  attr(adapter, "trusted_catalog_setter") <- function(assets, accounts) {
    if (!is.list(assets) || !length(assets) || !is.list(accounts) || !length(accounts)) .per_asset_review_abort("per_asset_review_adapter_failed")
    state$assets <- assets; state$accounts <- accounts; invisible(TRUE)
  }
  attr(adapter, "trusted_plan_resolver") <- function(plan_token) {
    if (!is.character(plan_token) || length(plan_token)!=1L || !exists(plan_token, envir=state$plans, inherits=FALSE)) .per_asset_review_abort("per_asset_review_context_invalid")
    entry <- get(plan_token, envir=state$plans, inherits=FALSE)
    list(projection=state$projection, plan=entry$plan, review=entry$review)
  }
  adapter
}

new_data_per_asset_legacy_review_product_adapter_v1 <- function(project_root, context, source_adapter) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  if (!inherits(source_adapter, "spot_per_asset_review_adapter_v1")) .per_asset_review_abort("per_asset_review_adapter_invalid")
  data_space <- runtime_data_space_path(context); canonical <- runtime_canonical_path(context)
  resolver <- attr(source_adapter, "trusted_plan_resolver", exact=TRUE)
  catalog_setter <- attr(source_adapter, "trusted_catalog_setter", exact=TRUE)
  if (!is.function(resolver) || !is.function(catalog_setter)) .per_asset_review_abort("per_asset_review_adapter_invalid")
  product <- new.env(hash=TRUE, parent=emptyenv()); product$entries <- new.env(hash=TRUE, parent=emptyenv())
  open_source <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    source <- source_adapter$open_source(bound_context)
    catalog <- .per_asset_review_adapter_run(project_root, "product-catalog", list(
      context=list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner"),
      canonical_path=canonical
    ))$catalog
    if (!is.list(catalog) || !is.list(catalog$assets) || !length(catalog$assets) || !is.list(catalog$accounts) || !length(catalog$accounts)) .per_asset_review_abort("per_asset_review_adapter_failed")
    source$target_assets <- lapply(catalog$assets, function(value) list(asset_id=value$asset_id, label=value$label, asset_type=value$asset_type, quantity_scale=as.integer(value$quantity_scale)))
    source$target_accounts <- lapply(catalog$accounts, function(value) list(account_id=value$account_id, label=value$label, account_type=value$account_type))
    catalog_setter(source$target_assets, source$target_accounts)
    source
  }
  plan_review <- function(bound_context, source_token, browser_review) {
    public <- source_adapter$plan_review(bound_context, source_token, browser_review)
    if (!is.list(public) || !is.character(public$plan_token) || length(public$plan_token)!=1L) .per_asset_review_abort("per_asset_review_adapter_failed")
    entry <- tryCatch(resolver(public$plan_token), spot_per_asset_review_error=function(error) stop(error), error=function(error) .per_asset_review_abort("per_asset_review_adapter_failed"))
    assign(public$plan_token, entry, envir=product$entries)
    public
  }
  product_preview <- function(bound_context, plan_token) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context)) || !exists(plan_token, envir=product$entries, inherits=FALSE)) .per_asset_review_abort("per_asset_review_context_invalid")
    entry <- get(plan_token, envir=product$entries, inherits=FALSE)
    accounts <- vapply(entry$review$accounts, `[[`, character(1L), "account_ref")
    target <- entry$review$target_asset$asset_ref
    value <- .per_asset_review_adapter_run(project_root, "product-preview", list(
      projection=entry$projection, review=entry$review,
      expected_plan_fingerprint=entry$plan$plan_fingerprint,
      context=list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner"),
      canonical_path=canonical, data_space_path=data_space, target_asset_id=target, selected_account_ids=as.list(accounts)
    ))
    value$preview
  }
  product_apply <- function(bound_context, plan_token, expected_preview_fingerprint, committed_at_utc) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context)) || !exists(plan_token, envir=product$entries, inherits=FALSE)) .per_asset_review_abort("per_asset_review_context_invalid")
    entry <- get(plan_token, envir=product$entries, inherits=FALSE); accounts <- vapply(entry$review$accounts, `[[`, character(1L), "account_ref")
    value <- .per_asset_review_adapter_run(project_root, "product-apply", list(
      projection=entry$projection, review=entry$review,
      expected_plan_fingerprint=entry$plan$plan_fingerprint, expected_preview_fingerprint=expected_preview_fingerprint,
      context=list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner"),
      canonical_path=canonical, data_space_path=data_space, target_asset_id=entry$review$target_asset$asset_ref,
      selected_account_ids=as.list(accounts), committed_at_utc=committed_at_utc
    ))
    value$result
  }
  product_binding <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    value <- .per_asset_review_adapter_run(project_root, "product-binding", list(
      context=list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner"),
      data_space_path=data_space
    ))$binding
    if (!is.list(value) || !value$status %in% c("absent", "available")) .per_asset_review_abort("per_asset_review_adapter_failed")
    value
  }
  source <- new_data_per_asset_review_adapter_v1(open_source, plan_review, source_adapter$apply_plan)
  structure(list(source_adapter=source, product_preview=product_preview, product_apply=product_apply, product_binding=product_binding), class="spot_per_asset_review_product_adapter_v1")
}

# Den Buchungsbestand gegen die heutigen Stammdaten neu veroeffentlichen, ohne
# Buchung. Schreibt eine neue Generation mit denselben Buchungen; `status` sagt,
# ob das noetig war ("republished"), der Bestand schon passte ("already_current")
# oder es noch keinen gibt ("absent").
new_data_asset_activity_republication_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  canonical <- runtime_canonical_path(context); data_space <- runtime_data_space_path(context)
  list(republish=function(bound_context, committed_at_utc) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    value <- .per_asset_review_adapter_run(project_root, "product-republish", list(
      context=list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner"),
      canonical_path=canonical, data_space_path=data_space, committed_at_utc=committed_at_utc
    ))$result
    if (!is.list(value) || !is.character(value$status) || length(value$status) != 1L ||
        !value$status %in% c("republished", "already_current", "absent")) .per_asset_review_abort("per_asset_review_adapter_failed")
    value
  })
}

# Was der Eigentuemer liest, wenn das Run Center den Buchungsbestand vor dem Plan
# angeglichen hat - und was, wenn das nicht ging. Der nackte Sammelcode sagte
# weder, dass es an den Stammdaten lag, noch, was zu tun ist (11.10.2026).
data_run_plan_alignment_notice_text_v1 <- function() paste(
  "Hinweis: Seit der letzten Buchung waren Stammdaten geändert worden; der Buchungsbestand wurde vorher daran angeglichen.",
  "An den Buchungen selbst hat sich nichts geändert.")
data_run_plan_alignment_failure_text_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code)) code <- "desktop_product_boundary_failed"
  lead <- "Seit der letzten Buchung wurden Stammdaten geändert; der Buchungsbestand muss vor dem Plan daran angeglichen werden."
  reason <- if (identical(code, "asset_quantity_scale_attempt_conflict"))
    "Das geht erst, wenn die unterbrochene Skalenanpassung abgeschlossen ist: unter „1. Transaktionen“ „Unterbrochene Skalenanpassungen lesen“ und abschließen, dann den Abschlussplan erneut prüfen."
  else if (identical(code, "desktop_asset_activity_canonical_changed"))
    "Währenddessen haben sich die Stammdaten erneut geändert. Bitte den Abschlussplan noch einmal prüfen."
  else if (identical(code, "desktop_asset_activity_lock_unavailable"))
    "Der Buchungsbestand wird gerade von einem anderen Vorgang geschrieben. Bitte kurz warten und den Abschlussplan erneut prüfen."
  else "Das Angleichen ist nicht gelungen; an Buchungen und Stammdaten wurde nichts verändert."
  paste0(lead, " ", reason, " (Code: ", code, ")")
}

# Nur lesend: Pflegestand je Asset und Konto (#423).
new_data_asset_maintenance_product_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  data_space <- runtime_data_space_path(context)
  gebunden <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner")
  }
  list(
    read=function(bound_context, as_of_date) .per_asset_review_adapter_run(project_root, "asset-maintenance-state", list(
      context=gebunden(bound_context), data_space_path=data_space, as_of_date=as_of_date))$state,
    # Vorschau und Anwenden tragen denselben Auftrag; der Abdruck der Vorschau
    # bindet beides aneinander. Ein veraenderter Auftrag ergibt einen anderen
    # Abdruck, und das Anwenden weist ihn ab (#423).
    preview=function(bound_context, request, as_of_date) .per_asset_review_adapter_run(project_root, "asset-maintenance-preview", list(
      context=gebunden(bound_context), data_space_path=data_space, request=request, as_of_date=as_of_date))$preview,
    apply=function(bound_context, request, as_of_date, preview_fingerprint, declared_at_utc) .per_asset_review_adapter_run(project_root, "asset-maintenance-apply", list(
      context=gebunden(bound_context), data_space_path=data_space, request=request, as_of_date=as_of_date,
      preview_fingerprint=preview_fingerprint, declared_at_utc=declared_at_utc, confirmed=TRUE))$result,
    runs=function(bound_context) .per_asset_review_adapter_run(project_root, "asset-maintenance-runs", list(
      context=gebunden(bound_context), data_space_path=data_space))$runs
  )
}

new_data_activity_draft_product_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  data_space <- runtime_data_space_path(context); canonical <- runtime_canonical_path(context)
  trusted_context <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .per_asset_review_abort("per_asset_review_context_invalid")
    list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner")
  }
  run <- function(command, payload) .per_asset_review_adapter_run(project_root, command, payload)
  list(
    resolve_time=function(bound_context,local_date,local_time,time_zone){invisible(trusted_context(bound_context));run("native-activity-time",list(local_date=local_date,local_time=local_time,time_zone=time_zone))$resolved},
    inspect_redundant=function(bound_context,source_path){invisible(trusted_context(bound_context));run("redundant-activity-inspect",list(source_path=source_path))$inspection},
    create=function(bound_context,portfolio_id,origin_type,action_type,event_fields,created_at_utc,predecessor_event_ref=NULL) run("activity-draft-create",list(context=trusted_context(bound_context),data_space_path=data_space,portfolio_id=portfolio_id,origin_type=origin_type,action_type=action_type,event_fields=event_fields,created_at_utc=created_at_utc,predecessor_event_ref=predecessor_event_ref))$draft,
    create_or_reuse=function(bound_context,portfolio_id,event_fields,source_binding,source_auxiliary,created_at_utc) run("activity-draft-create-or-reuse",list(context=trusted_context(bound_context),data_space_path=data_space,portfolio_id=portfolio_id,event_fields=event_fields,source_binding=source_binding,source_auxiliary=source_auxiliary,created_at_utc=created_at_utc))$draft,
    shift_second=function(bound_context,draft_ref,expected_revision,updated_at_utc) run("activity-draft-shift-second",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),updated_at_utc=updated_at_utc)),
    update=function(bound_context,draft_ref,expected_revision,event_patch,remove_fields,updated_at_utc) run("activity-draft-update",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),event_patch=event_patch,remove_fields=as.list(remove_fields),updated_at_utc=updated_at_utc))$draft,
    resolve_fee=function(bound_context,draft_ref,expected_revision,resolution,updated_at_utc) run("activity-draft-resolve-fee",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),resolution=resolution,updated_at_utc=updated_at_utc))$draft,
    bind_fifo_order=function(bound_context,draft_ref,expected_revision,fifo_order_evidence,updated_at_utc) run("activity-draft-bind-fifo-order",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),fifo_order_evidence=fifo_order_evidence,updated_at_utc=updated_at_utc))$draft,
    bind_fifo_order_group=function(bound_context,draft_ref,expected_revision,peer_draft_refs,updated_at_utc) run("activity-draft-bind-fifo-order-group",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),peer_draft_refs=unname(peer_draft_refs),updated_at_utc=updated_at_utc))$draft,
    read=function(bound_context,draft_ref) run("activity-draft-read",list(context=trusted_context(bound_context),data_space_path=data_space,draft_ref=draft_ref))$draft,
    # Der Grund blockierter Entwuerfe: nur lesend, mehrere Entwuerfe in einem Aufruf (#420).
    explain=function(bound_context,draft_refs) run("activity-draft-explain",list(context=trusted_context(bound_context),canonical_path=canonical,data_space_path=data_space,draft_refs=as.list(unname(draft_refs))))$explanations,
    validate=function(bound_context,draft_ref,expected_revision,validated_at_utc) run("activity-draft-validate",list(context=trusted_context(bound_context),canonical_path=canonical,data_space_path=data_space,draft_ref=draft_ref,expected_revision=as.integer(expected_revision),validated_at_utc=validated_at_utc))$draft,
    confirmation=function(bound_context,trusted_draft,challenge_ref,issued_at_utc,confirmed_at_utc,expires_at_utc) {
      payload<-list(context=trusted_context(bound_context),trusted_draft=trusted_draft,challenge_ref=challenge_ref,issued_at_utc=issued_at_utc,confirmed_at_utc=confirmed_at_utc,expires_at_utc=expires_at_utc)
      if(identical(as.integer(trusted_draft$activity_draft_version),2L)&&identical(trusted_draft$draft_state,'applying'))payload$data_space_path<-data_space
      run('activity-draft-confirmation',payload)$confirmation
    },
    apply=function(bound_context,draft_ref,confirmation,committed_at_utc) run("activity-draft-apply",list(context=trusted_context(bound_context),canonical_path=canonical,data_space_path=data_space,draft_ref=draft_ref,confirmation=confirmation,committed_at_utc=committed_at_utc))$result,
    resume=function(bound_context,draft_ref) run("activity-draft-resume",list(context=trusted_context(bound_context),canonical_path=canonical,data_space_path=data_space,draft_ref=draft_ref))$result,
    list=function(bound_context) run("activity-draft-list",list(context=trusted_context(bound_context),data_space_path=data_space))$drafts,
    # Erledigten Reward-Lauf stilllegen (#520): Vorschau liest nur; Anwenden schreibt nach ausdruecklicher Bestaetigung.
    retire_preview=function(bound_context,source_fingerprint,replacement_source_fingerprint,expected_draft_count,expected_committed_draft_count,previewed_at_utc) run("activity-draft-retire-preview",list(context=trusted_context(bound_context),data_space_path=data_space,source_fingerprint=source_fingerprint,replacement_source_fingerprint=replacement_source_fingerprint,expected_draft_count=as.integer(expected_draft_count),expected_committed_draft_count=as.integer(expected_committed_draft_count),previewed_at_utc=previewed_at_utc)),
    retire_apply=function(bound_context,mode,trusted_preview_token,confirmed_at_utc) run("activity-draft-retire-apply",list(context=trusted_context(bound_context),data_space_path=data_space,mode=mode,trusted_preview_token=trusted_preview_token,confirmed_at_utc=confirmed_at_utc)),
    profile_save=function(bound_context,profile_label,is_standard,default_portfolio_id,default_account_id,portfolio_mappings,account_mappings,asset_mappings,saved_at_utc) run("activity-mapping-profile-save",list(context=trusted_context(bound_context),data_space_path=data_space,profile_label=profile_label,is_standard=isTRUE(is_standard),default_portfolio_id=default_portfolio_id,default_account_id=default_account_id,portfolio_mappings=portfolio_mappings,account_mappings=account_mappings,asset_mappings=asset_mappings,saved_at_utc=saved_at_utc))$profile,
    profile_list=function(bound_context) run("activity-mapping-profile-list",list(context=trusted_context(bound_context),data_space_path=data_space))$profiles,
    profile_read=function(bound_context,profile_ref) run("activity-mapping-profile-read",list(context=trusted_context(bound_context),data_space_path=data_space,profile_ref=profile_ref))$profile
  )
}

new_data_asset_activity_product_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  data_space <- runtime_data_space_path(context); canonical <- runtime_canonical_path(context)
  drafts <- new_data_activity_draft_product_adapter_v1(project_root, context)
  draft_previews <- new.env(hash=TRUE,parent=emptyenv())
  trusted_context <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .data_asset_activity_editor_abort("data_asset_activity_editor_context_invalid")
    list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner")
  }
  resolve_time <- function(bound_context, local_date, local_time, time_zone) {
    invisible(trusted_context(bound_context))
    .per_asset_review_adapter_run(project_root, "native-activity-time", list(local_date=local_date, local_time=local_time, time_zone=time_zone))$resolved
  }
  read_view <- function(bound_context) .per_asset_review_adapter_run(project_root, "product-activity-view", list(
    context=trusted_context(bound_context),canonical_path=canonical,data_space_path=data_space
  ))$view
  catalog <- function(bound_context) {
    value <- .per_asset_review_adapter_run(project_root, "product-catalog", list(context=trusted_context(bound_context),canonical_path=canonical))$catalog
    if (!is.list(value)||!is.list(value$assets)||!is.list(value$accounts)||!is.list(value$portfolios)) .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
    value
  }
  preview <- function(bound_context, portfolio_id, events, previewed_at_utc) {
    if(!is.list(events)||length(events)!=1L||!is.character(previewed_at_utc)||length(previewed_at_utc)!=1L) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    created <- drafts$create(bound_context,portfolio_id,"manual_form","create",events[[1L]],previewed_at_utc)
    validated <- drafts$validate(bound_context,created$trusted_draft$draft_ref,created$trusted_draft$revision,previewed_at_utc)
    trusted <- validated$trusted_draft
    if(identical(trusted$validation_status,"blocked")) {
      # Der Kern hat die neue Buchung abgelehnt. Statt beim Sammelcode zu enden,
      # wird der Grund geholt - nur lesend - und nach oben gereicht (#420).
      # Scheitert das Erklaeren selbst, bleibt es beim bisherigen Code.
      explanation <- tryCatch(drafts$explain(bound_context,trusted$draft_ref)[[1L]],error=function(error)NULL)
      if(is.list(explanation)&&explanation$status%in%c("explained","no_longer_blocked")) data_activity_block_reason_signal_v1(explanation)
    }
    if(!identical(trusted$validation_status,"ready")||!is.list(trusted$validation$trusted_preview)) .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
    expected <- trusted$validation$expected_preview_fingerprint
    assign(expected,list(draft_ref=trusted$draft_ref,trusted=trusted,portfolio_id=portfolio_id,event=events[[1L]]),envir=draft_previews)
    trusted$validation$trusted_preview
  }
  apply <- function(bound_context, portfolio_id, events, expected_preview_fingerprint, committed_at_utc) {
    if(!is.character(expected_preview_fingerprint)||length(expected_preview_fingerprint)!=1L||!exists(expected_preview_fingerprint,envir=draft_previews,inherits=FALSE)) .data_asset_activity_editor_abort("data_asset_activity_editor_preview_required")
    entry <- get(expected_preview_fingerprint,envir=draft_previews,inherits=FALSE)
    if(!identical(entry$portfolio_id,portfolio_id)||!identical(entry$event,events[[1L]])) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    expires <- format(as.POSIXct(committed_at_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")+300,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
    challenge <- paste0("adc_",substr(digest::digest(charToRaw(enc2utf8(paste(entry$trusted$validation$validation_fingerprint,committed_at_utc,sep="|"))),algo="sha256",serialize=FALSE),1L,32L))
    confirmation <- drafts$confirmation(bound_context,entry$trusted,challenge,committed_at_utc,committed_at_utc,expires)
    result <- drafts$apply(bound_context,entry$draft_ref,confirmation,committed_at_utc)
    result$trusted_draft$domain_result
  }
  list(resolve_time=resolve_time,read_view=read_view,catalog=catalog,preview=preview,apply=apply)
}

new_data_cash_coverage_product_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash="/", mustWork=TRUE)
  data_space <- runtime_data_space_path(context); canonical <- runtime_canonical_path(context)
  trusted_context <- function(bound_context) {
    if (!identical(runtime_context_fingerprint(bound_context), runtime_context_fingerprint(context))) .data_cash_coverage_editor_abort("data_cash_coverage_editor_context_invalid")
    list(tenant_id=context$tenant_id, user_id=context$user_id, data_space_id=context$data_space_id, actor_id=context$actor_id, role="desktop_owner")
  }
  catalog <- function(bound_context) .per_asset_review_adapter_run(project_root, "cash-coverage-catalog", list(
    context=trusted_context(bound_context), canonical_path=canonical
  ))$catalog
  read_view <- function(bound_context) .per_asset_review_adapter_run(project_root, "cash-coverage-view", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space
  ))$view
  revision_candidates <- function(bound_context) .per_asset_review_adapter_run(project_root, "cash-coverage-revision-candidates", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space
  ))$candidates
  recovery_candidates <- function(bound_context) .per_asset_review_adapter_run(project_root, "cash-coverage-recovery-candidates", list(
    context=trusted_context(bound_context), data_space_path=data_space
  ))$candidates
  preview <- function(bound_context, command) .per_asset_review_adapter_run(project_root, "cash-coverage-preview", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space, command=command
  ))$preview
  reviewed_preview <- function(bound_context, reviewed_candidate, request_ref) .per_asset_review_adapter_run(project_root, "cash-coverage-reviewed-preview", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space,
    reviewed_candidate=reviewed_candidate, request_ref=request_ref
  ))$preview
  confirmation <- function(bound_context, preview, confirmation_ref, issued_at_utc, expires_at_utc) .per_asset_review_adapter_run(project_root, "cash-coverage-confirmation", list(
    context=trusted_context(bound_context), preview=preview, confirmation_ref=confirmation_ref,
    issued_at_utc=issued_at_utc, expires_at_utc=expires_at_utc
  ))$confirmation
  apply <- function(bound_context, command, confirmation_value, committed_at_utc) .per_asset_review_adapter_run(project_root, "cash-coverage-apply", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space,
    command=command, confirmation=confirmation_value, committed_at_utc=committed_at_utc
  ))$result
  recovery_preview <- function(bound_context, recovery_ref) .per_asset_review_adapter_run(project_root, "cash-coverage-recovery-preview", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space,
    recovery_ref=recovery_ref
  ))$recovery
  recovery_confirmation <- function(bound_context, trusted_preview, confirmation_ref, issued_at_utc, expires_at_utc) .per_asset_review_adapter_run(project_root, "cash-coverage-recovery-confirmation", list(
    context=trusted_context(bound_context), trusted_preview=trusted_preview, confirmation_ref=confirmation_ref,
    issued_at_utc=issued_at_utc, expires_at_utc=expires_at_utc
  ))$confirmation
  recovery_apply <- function(bound_context, trusted_preview, confirmation_value, recovered_at_utc) .per_asset_review_adapter_run(project_root, "cash-coverage-recovery-apply", list(
    context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space,
    trusted_preview=trusted_preview, recovery_confirmation=confirmation_value, recovered_at_utc=recovered_at_utc
  ))$result
  # Einfache Handbuchung und nachtraeglicher Pruef-Saldo (#417, #419). Der Kern
  # bildet die Kommandos; hier wird nur der Auftrag durchgereicht.
  scope_paths <- function(bound_context) list(context=trusted_context(bound_context), canonical_path=canonical, data_space_path=data_space)
  check_balance <- function(bound_context, request) .per_asset_review_adapter_run(project_root, "cash-check-balance-prepare",
    c(scope_paths(bound_context), list(request=request)))$prepared
  manual_booking <- function(bound_context, request) .per_asset_review_adapter_run(project_root, "cash-manual-booking-prepare",
    c(scope_paths(bound_context), list(request=request)))$prepared
  manual_batch_apply <- function(bound_context, commands, preview_fingerprint, confirmed_by_owner_at_utc, committed_at_utc)
    .per_asset_review_adapter_run(project_root, "cash-manual-batch-apply", c(scope_paths(bound_context), list(
      commands=commands, preview_fingerprint=preview_fingerprint,
      confirmed_by_owner_at_utc=confirmed_by_owner_at_utc, committed_at_utc=committed_at_utc)))$result
  evidence_overview <- function(bound_context, as_of_date) .per_asset_review_adapter_run(project_root, "cash-evidence-overview",
    c(scope_paths(bound_context), list(as_of_date=as_of_date)))$overview
  list(catalog=catalog,read_view=read_view,revision_candidates=revision_candidates,recovery_candidates=recovery_candidates,
    preview=preview,reviewed_preview=reviewed_preview,confirmation=confirmation,apply=apply,
    recovery_preview=recovery_preview,recovery_confirmation=recovery_confirmation,recovery_apply=recovery_apply,
    check_balance=check_balance,manual_booking=manual_booking,manual_batch_apply=manual_batch_apply,
    evidence_overview=evidence_overview)
}

new_data_per_asset_legacy_review_fixture_adapter_if_available_v1 <- function(project_root, context) {
  fixture_root <- file.path(project_root, "fixtures", "product", "legacy-per-asset-review-v1")
  required <- c(
    file.path(fixture_root, "invented_asset_trades.csv"),
    file.path(fixture_root, "invented_assets.csv"),
    file.path(project_root, "scripts", "per_asset_legacy_review.py"),
    file.path(project_root, "migrations", "reference", "legacy_per_asset_trade_planner_v1.py"),
    file.path(project_root, "migrations", "reference", "per_asset_sandbox_apply_v1.py")
  )
  if (all(file.exists(required)) && !any(vapply(required, function(path) nzchar(Sys.readlink(path)), logical(1L)))) {
    return(new_data_per_asset_legacy_review_fixture_adapter_v1(project_root, context))
  }
  new_data_per_asset_legacy_review_disabled_adapter_v1()
}
