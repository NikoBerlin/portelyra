data_per_asset_review_error_codes_v1 <- function() c(
  "per_asset_review_adapter_failed", "per_asset_review_adapter_invalid",
  "per_asset_review_confirmation_consumed", "per_asset_review_confirmation_expired",
  "per_asset_review_confirmation_required", "per_asset_review_context_invalid",
  "per_asset_review_form_invalid", "per_asset_review_not_ready",
  "per_asset_review_preview_missing", "per_asset_review_source_invalid",
  "per_asset_review_source_missing", "per_asset_review_state_invalid"
)
.per_asset_review_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% data_per_asset_review_error_codes_v1()) stop("unregistered_per_asset_review_error_code", call. = FALSE)
  structure(list(message = code, call = NULL, code = code), class = c("spot_per_asset_review_error", "error", "condition"))
}
.per_asset_review_abort <- function(code) stop(.per_asset_review_condition(code))

new_data_per_asset_review_adapter_v1 <- function(open_source, plan_review, apply_plan) {
  if (!is.function(open_source) || !is.function(plan_review) || !is.function(apply_plan)) {
    .per_asset_review_abort("per_asset_review_adapter_invalid")
  }
  structure(list(open_source = open_source, plan_review = plan_review, apply_plan = apply_plan), class = "spot_per_asset_review_adapter_v1")
}
.per_asset_review_context_valid <- function(context) {
  isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) && identical(context$role, "desktop_owner")
}
new_data_per_asset_review_center_v1 <- function(context, adapter) {
  if (!.per_asset_review_context_valid(context)) .per_asset_review_abort("per_asset_review_context_invalid")
  if (!inherits(adapter, "spot_per_asset_review_adapter_v1") || !is.list(adapter) ||
      !identical(names(adapter), c("open_source", "plan_review", "apply_plan")) ||
      !all(vapply(adapter, is.function, logical(1L)))) .per_asset_review_abort("per_asset_review_adapter_invalid")
  center <- new.env(hash = FALSE, parent = emptyenv())
  center$context <- context; center$context_fingerprint <- runtime_context_fingerprint(context)
  center$adapter <- adapter; center$sequence <- 0L; center$source <- NULL; center$selection <- NULL; center$current <- NULL; center$product <- NULL
  class(center) <- "spot_per_asset_review_center_v1"; center
}
.per_asset_review_assert <- function(center) {
  valid <- inherits(center, "spot_per_asset_review_center_v1") && is.environment(center) &&
    is.integer(center$sequence) && .per_asset_review_context_valid(center$context) &&
    identical(center$context_fingerprint, runtime_context_fingerprint(center$context)) &&
    inherits(center$adapter, "spot_per_asset_review_adapter_v1") && is.list(center$adapter) &&
    identical(names(center$adapter), c("open_source", "plan_review", "apply_plan")) &&
    all(vapply(center$adapter, is.function, logical(1L)))
  if (!isTRUE(valid)) .per_asset_review_abort("per_asset_review_state_invalid")
}
.per_asset_review_text <- function(value, optional = FALSE, maximum = 4000L) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) .per_asset_review_abort("per_asset_review_form_invalid")
  value
}
.per_asset_review_decimal <- function(value) {
  if (is.null(value) || identical(value, "")) return(NULL)
  value <- .per_asset_review_text(value, maximum = 80L)
  if (!grepl("^(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value)) .per_asset_review_abort("per_asset_review_form_invalid")
  value
}
.per_asset_review_date <- function(value) {
  if (inherits(value, "Date")) value <- format(value, "%Y-%m-%d")
  if (is.null(value) || identical(value, "")) return(NULL)
  value <- .per_asset_review_text(value, maximum = 10L); parsed <- suppressWarnings(as.Date(value, "%Y-%m-%d"))
  if (is.na(parsed) || !identical(format(parsed, "%Y-%m-%d"), value)) .per_asset_review_abort("per_asset_review_form_invalid")
  value
}
.per_asset_review_time <- function(value) {
  if (is.null(value) || identical(value, "")) return(NULL)
  value <- .per_asset_review_text(value, maximum = 8L); if (grepl("^[0-9]{2}:[0-9]{2}$", value)) value <- paste0(value, ":00")
  parsed <- suppressWarnings(strptime(value, "%H:%M:%S", tz = "UTC"))
  if (is.na(parsed) || !identical(format(parsed, "%H:%M:%S"), value)) .per_asset_review_abort("per_asset_review_form_invalid")
  value
}
.per_asset_review_utc_valid <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) return(FALSE)
  parsed <- suppressWarnings(as.POSIXct(value, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  !is.na(parsed) && identical(format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), value)
}

.per_asset_review_source_validate <- function(source) {
  required <- c("source_contract_version", "source_status", "source_token", "companion", "target_assets", "target_accounts", "source_accounts", "rows", "source_row_count")
  if (!is.list(source) || !identical(names(source), required) || !identical(source$source_contract_version, 1L) ||
      !source$source_status %in% c("review_required", "blocked") || !is.character(source$source_token) || length(source$source_token) != 1L || is.na(source$source_token) || !nzchar(source$source_token) ||
      !is.list(source$target_assets) || !length(source$target_assets) || !is.list(source$target_accounts) || !length(source$target_accounts) ||
      !is.list(source$source_accounts) || !is.list(source$rows) || !length(source$rows) || !identical(source$source_row_count, length(source$rows))) {
    .per_asset_review_abort("per_asset_review_source_invalid")
  }
  exact <- function(row, fields) is.list(row) && identical(names(row), fields)
  if (!is.null(source$companion)) {
    companion_fields <- c("status", "display_name_candidate", "isin_candidate", "wkn_candidate", "note_candidate", "provider_listing_field_count", "tax_hint_present", "account_binding_imported", "provider_listing_value_imported", "tax_value_imported")
    if (!exact(source$companion, companion_fields) || !identical(source$companion$status, "available") ||
        !is.integer(source$companion$provider_listing_field_count) || length(source$companion$provider_listing_field_count) != 1L ||
        is.na(source$companion$provider_listing_field_count) || source$companion$provider_listing_field_count < 0L ||
        !is.logical(source$companion$tax_hint_present) || length(source$companion$tax_hint_present) != 1L || is.na(source$companion$tax_hint_present) ||
        !identical(source$companion$account_binding_imported, FALSE) || !identical(source$companion$provider_listing_value_imported, FALSE) ||
        !identical(source$companion$tax_value_imported, FALSE)) .per_asset_review_abort("per_asset_review_source_invalid")
    .per_asset_review_text(source$companion$display_name_candidate, maximum=160L)
    .per_asset_review_text(source$companion$isin_candidate, TRUE, 12L)
    .per_asset_review_text(source$companion$wkn_candidate, TRUE, 6L)
    .per_asset_review_text(source$companion$note_candidate, TRUE, 4000L)
  }
  for (asset in source$target_assets) {
    if (!exact(asset, c("asset_id", "label", "asset_type", "quantity_scale")) || !is.character(asset$asset_id) || length(asset$asset_id) != 1L || is.na(asset$asset_id) || !nzchar(asset$asset_id) ||
        !is.character(asset$asset_type) || length(asset$asset_type) != 1L || is.na(asset$asset_type) || !asset$asset_type %in% c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "fx", "index", "other") ||
        !is.integer(asset$quantity_scale) || length(asset$quantity_scale) != 1L || is.na(asset$quantity_scale) || asset$quantity_scale < 0L || asset$quantity_scale > 24L) .per_asset_review_abort("per_asset_review_source_invalid")
    .per_asset_review_text(asset$label, maximum = 160L)
  }
  for (account in source$target_accounts) {
    if (!exact(account, c("account_id", "label", "account_type")) || !is.character(account$account_id) || length(account$account_id) != 1L || is.na(account$account_id) || !nzchar(account$account_id) ||
        !is.character(account$account_type) || length(account$account_type) != 1L || is.na(account$account_type) || !account$account_type %in% c("securities", "crypto_wallet", "other")) .per_asset_review_abort("per_asset_review_source_invalid")
    .per_asset_review_text(account$label, maximum = 160L)
  }
  for (account in source$source_accounts) {
    if (!exact(account, c("source_account_key", "label")) || !is.character(account$source_account_key) || length(account$source_account_key) != 1L || is.na(account$source_account_key) || !nzchar(account$source_account_key)) .per_asset_review_abort("per_asset_review_source_invalid")
    .per_asset_review_text(account$label, maximum = 160L)
  }
  row_fields <- c("source_row_id", "ordinal", "date", "time", "time_evidence", "event_type", "quantity_decimal", "unit_price_decimal", "fee_decimal", "memo", "initial_disposition", "decision_codes", "blocker_codes")
  for (row in source$rows) {
    if (!exact(row, row_fields) || !is.character(row$source_row_id) || length(row$source_row_id) != 1L || is.na(row$source_row_id) || !nzchar(row$source_row_id) ||
        !is.integer(row$ordinal) || length(row$ordinal) != 1L || is.na(row$ordinal) || row$ordinal < 1L ||
        !is.character(row$time_evidence) || length(row$time_evidence) != 1L || is.na(row$time_evidence) || !row$time_evidence %in% c("exact", "date_only") ||
        !is.character(row$event_type) || length(row$event_type) != 1L || is.na(row$event_type) || !row$event_type %in% c("buy", "sell", "dividend", "stock_dividend", "reward", "deposit", "withdrawal", "transfer", "interest") ||
        !is.character(row$initial_disposition) || length(row$initial_disposition) != 1L || is.na(row$initial_disposition) || !row$initial_disposition %in% c("decision_required", "blocked") ||
        !is.character(row$decision_codes) || anyNA(row$decision_codes) || !is.character(row$blocker_codes) || anyNA(row$blocker_codes)) .per_asset_review_abort("per_asset_review_source_invalid")
    if (is.null(.per_asset_review_date(row$date))) .per_asset_review_abort("per_asset_review_source_invalid")
    .per_asset_review_time(row$time); .per_asset_review_decimal(row$quantity_decimal); .per_asset_review_decimal(row$unit_price_decimal); .per_asset_review_decimal(row$fee_decimal)
    if (!is.null(row$memo)) .per_asset_review_text(row$memo)
  }
  unique_field <- function(rows, field) { values <- vapply(rows, `[[`, character(1L), field); length(values) == length(unique(values)) }
  if (!unique_field(source$target_assets, "asset_id") || !unique_field(source$target_accounts, "account_id") || !unique_field(source$source_accounts, "source_account_key") ||
      !unique_field(source$rows, "source_row_id") || !identical(sort(vapply(source$rows, `[[`, integer(1L), "ordinal")), seq_len(length(source$rows)))) .per_asset_review_abort("per_asset_review_source_invalid")
  source
}
.per_asset_review_index <- function(rows, id_field, prefix) {
  refs <- sprintf("%s%04d", prefix, seq_along(rows)); ids <- vapply(rows, `[[`, character(1L), id_field)
  list(by_ref = setNames(rows, refs), ref_by_id = setNames(refs, ids))
}
.per_asset_review_type_label <- function(value) unname(c(buy="Kauf", sell="Verkauf", dividend="Bardividende", stock_dividend="Stockdividende", reward="Reward", deposit="Einlieferung", withdrawal="Auslieferung", transfer="Interner Transfer", interest="Zins")[[value]])

.per_asset_review_public_source <- function(center) {
  source <- center$source; selection <- center$selection
  list(
    per_asset_review_source_version = 1L, status = source$source_status, source_ref = selection$source_ref,
    companion = source$companion,
    counts = list(
      source_row_count = source$source_row_count,
      decision_required_count = sum(vapply(source$rows, function(row) row$initial_disposition == "decision_required", logical(1L))),
      blocked_count = sum(vapply(source$rows, function(row) row$initial_disposition == "blocked", logical(1L)))
    ),
    target_assets = lapply(names(selection$assets$by_ref), function(ref) {
      value <- selection$assets$by_ref[[ref]]; list(ref=ref, label=value$label, asset_type=value$asset_type, quantity_scale=value$quantity_scale)
    }),
    target_accounts = lapply(names(selection$accounts$by_ref), function(ref) {
      value <- selection$accounts$by_ref[[ref]]; list(ref=ref, label=value$label, account_type=value$account_type)
    }),
    source_accounts = lapply(names(selection$source_accounts$by_ref), function(ref) {
      value <- selection$source_accounts$by_ref[[ref]]; list(ref=ref, label=value$label)
    }),
    rows = lapply(names(selection$rows$by_ref), function(ref) {
      value <- selection$rows$by_ref[[ref]]
      list(ref=ref, ordinal=value$ordinal, date=value$date, time=if (is.null(value$time)) "—" else value$time,
           time_evidence=value$time_evidence, event_type=value$event_type, event_label=.per_asset_review_type_label(value$event_type),
           quantity_decimal=if (is.null(value$quantity_decimal)) "—" else value$quantity_decimal,
           unit_price_decimal=if (is.null(value$unit_price_decimal)) "—" else value$unit_price_decimal,
           fee_decimal=if (is.null(value$fee_decimal)) "—" else value$fee_decimal,
           memo=if (is.null(value$memo)) "" else value$memo, disposition=value$initial_disposition,
           decision_codes=value$decision_codes, blocker_codes=value$blocker_codes)
    })
  )
}

data_per_asset_review_open_v1 <- function(center) {
  .per_asset_review_assert(center)
  source <- tryCatch(
    center$adapter$open_source(center$context),
    spot_per_asset_review_error = function(error) stop(error),
    error = function(error) .per_asset_review_abort("per_asset_review_adapter_failed")
  )
  source <- tryCatch(
    .per_asset_review_source_validate(source),
    spot_per_asset_review_error = function(error) {
      if (identical(error$code, "per_asset_review_form_invalid")) .per_asset_review_abort("per_asset_review_source_invalid")
      stop(error)
    }
  )
  center$sequence <- center$sequence + 1L
  center$source <- source
  center$selection <- list(
    source_ref=sprintf("legacy_source_%04d", center$sequence),
    assets=.per_asset_review_index(source$target_assets, "asset_id", "asset_choice_"),
    accounts=.per_asset_review_index(source$target_accounts, "account_id", "account_choice_"),
    source_accounts=.per_asset_review_index(source$source_accounts, "source_account_key", "source_account_"),
    rows=.per_asset_review_index(source$rows, "source_row_id", "row_review_")
  )
  center$current <- NULL; center$product <- NULL
  .per_asset_review_public_source(center)
}

data_per_asset_review_invalidate_v1 <- function(center) {
  .per_asset_review_assert(center); center$current <- NULL; center$product <- NULL; invisible(TRUE)
}

.per_asset_review_resolve <- function(index, ref, required=FALSE) {
  if (is.null(ref) || identical(ref, "")) {
    if (required) .per_asset_review_abort("per_asset_review_form_invalid")
    return(NULL)
  }
  if (!is.character(ref) || length(ref) != 1L || is.na(ref) || is.null(index$by_ref[[ref]])) .per_asset_review_abort("per_asset_review_form_invalid")
  index$by_ref[[ref]]
}
.per_asset_review_form <- function(center, form) {
  if (!is.list(form) || !identical(names(form), c("source_ref", "target_asset_ref", "companion_review", "source_account_bindings", "row_reviews")) ||
      !identical(form$source_ref, center$selection$source_ref) || !is.list(form$source_account_bindings) || !is.list(form$row_reviews)) .per_asset_review_abort("per_asset_review_form_invalid")
  asset <- .per_asset_review_resolve(center$selection$assets, form$target_asset_ref, TRUE)
  companion_review <- NULL
  if (is.null(center$source$companion)) {
    if (!is.null(form$companion_review)) .per_asset_review_abort("per_asset_review_form_invalid")
  } else {
    fields <- c("action", "display_name_action", "manual_display_name", "accept_isin", "accept_wkn", "accept_note")
    value <- form$companion_review
    if (!is.list(value) || !identical(names(value), fields) || !is.character(value$action) || length(value$action) != 1L ||
        is.na(value$action) || !value$action %in% c("skip", "bind") || !is.character(value$display_name_action) ||
        length(value$display_name_action) != 1L || is.na(value$display_name_action) ||
        !value$display_name_action %in% c("accept_candidate", "replace_manually") ||
        !is.logical(value$accept_isin) || length(value$accept_isin) != 1L || is.na(value$accept_isin) ||
        !is.logical(value$accept_wkn) || length(value$accept_wkn) != 1L || is.na(value$accept_wkn) ||
        !is.logical(value$accept_note) || length(value$accept_note) != 1L || is.na(value$accept_note)) .per_asset_review_abort("per_asset_review_form_invalid")
    manual <- .per_asset_review_text(value$manual_display_name, TRUE, 160L)
    if ((value$action == "bind" && (value$display_name_action == "replace_manually") != !is.null(manual)) ||
        (value$action == "skip" && (!is.null(manual) || isTRUE(value$accept_isin) || isTRUE(value$accept_wkn) || isTRUE(value$accept_note))) ||
        (isTRUE(value$accept_isin) && is.null(center$source$companion$isin_candidate)) ||
        (isTRUE(value$accept_wkn) && is.null(center$source$companion$wkn_candidate)) ||
        (isTRUE(value$accept_note) && is.null(center$source$companion$note_candidate))) .per_asset_review_abort("per_asset_review_form_invalid")
    companion_review <- list(action=value$action, display_name_action=value$display_name_action, manual_display_name=manual,
                             accept_isin=value$accept_isin, accept_wkn=value$accept_wkn, accept_note=value$accept_note)
  }
  bindings <- lapply(form$source_account_bindings, function(binding) {
    if (!is.list(binding) || !identical(names(binding), c("source_account_ref", "target_account_ref"))) .per_asset_review_abort("per_asset_review_form_invalid")
    source_account <- .per_asset_review_resolve(center$selection$source_accounts, binding$source_account_ref, TRUE)
    target_account <- .per_asset_review_resolve(center$selection$accounts, binding$target_account_ref, TRUE)
    list(source_account_key=source_account$source_account_key, target_account_id=target_account$account_id)
  })
  source_binding_keys <- vapply(bindings, `[[`, character(1L), "source_account_key")
  expected_binding_keys <- vapply(center$source$source_accounts, `[[`, character(1L), "source_account_key")
  if (length(bindings) != length(expected_binding_keys) || anyDuplicated(source_binding_keys) ||
      !setequal(source_binding_keys, expected_binding_keys)) .per_asset_review_abort("per_asset_review_form_invalid")
  rows <- lapply(form$row_reviews, function(review) {
    fields <- c("row_ref", "decision", "basis_evidence_mode", "basis_amount_mode", "provided_basis_decimal", "original_acquired_time_evidence", "original_acquired_local_date", "original_acquired_local_time", "original_acquired_time_zone", "original_acquired_at_utc", "movement_context_code", "fee_treatment", "memo_action", "duplicate_action", "dividend_input_mode", "dividend_gross_total_decimal", "same_day_fifo_sequence")
    if (!is.list(review) || !identical(names(review), fields) || !is.character(review$decision) || length(review$decision) != 1L || is.na(review$decision) ||
        !review$decision %in% c("accept", "unresolved")) .per_asset_review_abort("per_asset_review_form_invalid")
    source_row <- .per_asset_review_resolve(center$selection$rows, review$row_ref, TRUE)
    choice <- function(value, allowed) {
      if (is.null(value) || identical(value, "")) return(NULL)
      if (!is.character(value) || length(value) != 1L || is.na(value) || !value %in% allowed) .per_asset_review_abort("per_asset_review_form_invalid")
      value
    }
    sequence <- if (is.null(review$same_day_fifo_sequence) || identical(review$same_day_fifo_sequence, "")) NULL else suppressWarnings(as.integer(review$same_day_fifo_sequence))
    if (!is.null(sequence) && (is.na(sequence) || sequence < 1L || !identical(as.character(sequence), review$same_day_fifo_sequence))) .per_asset_review_abort("per_asset_review_form_invalid")
    acquisition_date <- .per_asset_review_date(review$original_acquired_local_date)
    acquisition_time <- .per_asset_review_time(review$original_acquired_local_time)
    acquisition_utc <- .per_asset_review_text(review$original_acquired_at_utc, TRUE, 20L)
    if (!is.null(acquisition_utc) && !.per_asset_review_utc_valid(acquisition_utc)) .per_asset_review_abort("per_asset_review_form_invalid")
    list(
      source_row_id=source_row$source_row_id, decision=review$decision,
      basis_evidence_mode=choice(review$basis_evidence_mode, c("valuation_confirmed_as_basis", "provided_basis", "basis_missing")),
      basis_amount_mode=choice(review$basis_amount_mode, c("source_quantity_unit_price", "manual_total", "not_applicable")),
      provided_basis_decimal=.per_asset_review_decimal(review$provided_basis_decimal),
      original_acquired_time_evidence=choice(review$original_acquired_time_evidence, c("date_only", "exact")),
      original_acquired_local_date=acquisition_date, original_acquired_local_time=acquisition_time,
      original_acquired_time_zone=.per_asset_review_text(review$original_acquired_time_zone, TRUE, 80L), original_acquired_at_utc=acquisition_utc,
      movement_context_code=choice(review$movement_context_code, c("unclassified", "gift", "inheritance", "debt_settlement", "donation", "payment", "custody_exit", "other")),
      fee_treatment=choice(review$fee_treatment, c("principal_asset_quantity", "monetary_basis_currency", "separate_event_required")),
      memo_action=choice(review$memo_action, c("accept_source", "skip")), duplicate_action=choice(review$duplicate_action, "keep_confirmed"),
      dividend_input_mode=choice(review$dividend_input_mode, c("quantity_unit_price", "gross_total")),
      dividend_gross_total_decimal=.per_asset_review_decimal(review$dividend_gross_total_decimal), same_day_fifo_sequence=sequence
    )
  })
  if (length(rows) != length(center$source$rows) || !setequal(vapply(rows, `[[`, character(1L), "source_row_id"), vapply(center$source$rows, `[[`, character(1L), "source_row_id"))) .per_asset_review_abort("per_asset_review_form_invalid")
  list(target_asset_id=asset$asset_id, companion_review=companion_review, source_account_bindings=bindings, row_reviews=rows)
}

.per_asset_review_public_preview <- function(plan, generation, source_ref, source_rows) {
  if (!is.list(plan) || !identical(names(plan), c("plan_contract_version", "status", "row_dispositions", "reconciliation", "summary", "plan_token")) ||
      !identical(plan$plan_contract_version, 1L) || !is.character(plan$status) || length(plan$status) != 1L || is.na(plan$status) || !plan$status %in% c("ready", "decision_required", "blocked") ||
      !is.list(plan$row_dispositions) || !length(plan$row_dispositions) || !is.list(plan$reconciliation) || !is.list(plan$summary) ||
      !is.character(plan$plan_token) || length(plan$plan_token) != 1L || is.na(plan$plan_token) || !nzchar(plan$plan_token)) .per_asset_review_abort("per_asset_review_adapter_invalid")
  required_row <- c("source_row_id", "ordinal", "date", "time", "event_type", "disposition", "decision_codes", "blocker_codes", "asset_effect", "fifo_effect", "guv_effect", "income_effect", "fee_effect", "transfer_effect")
  rows <- lapply(seq_along(plan$row_dispositions), function(index) {
    row <- plan$row_dispositions[[index]]
    if (!is.list(row) || !identical(names(row), required_row) || !is.character(row$source_row_id) || length(row$source_row_id) != 1L || is.na(row$source_row_id) || !nzchar(row$source_row_id) ||
        !is.integer(row$ordinal) || length(row$ordinal) != 1L || is.na(row$ordinal) || row$ordinal < 1L ||
        !is.character(row$event_type) || length(row$event_type) != 1L || is.na(row$event_type) || !row$event_type %in% c("buy", "sell", "dividend", "stock_dividend", "reward", "deposit", "withdrawal", "transfer", "interest") ||
        !is.character(row$disposition) || length(row$disposition) != 1L || is.na(row$disposition) || !row$disposition %in% c("ready", "decision_required", "blocked") ||
        !is.character(row$decision_codes) || anyNA(row$decision_codes) || !is.character(row$blocker_codes) || anyNA(row$blocker_codes)) .per_asset_review_abort("per_asset_review_adapter_invalid")
    list(row_ref=sprintf("planned_row_%04d", index), ordinal=row$ordinal, date=row$date, time=if (is.null(row$time)) "—" else row$time,
         event_type=row$event_type, event_label=.per_asset_review_type_label(row$event_type), disposition=row$disposition,
         decision_codes=row$decision_codes, blocker_codes=row$blocker_codes, asset_effect=row$asset_effect, fifo_effect=row$fifo_effect,
         guv_effect=row$guv_effect, income_effect=row$income_effect, fee_effect=row$fee_effect, transfer_effect=row$transfer_effect)
  })
  source_ids <- vapply(plan$row_dispositions, `[[`, character(1L), "source_row_id")
  ordinals <- vapply(plan$row_dispositions, `[[`, integer(1L), "ordinal")
  expected_ids <- vapply(source_rows, `[[`, character(1L), "source_row_id")
  if (length(source_ids) != length(expected_ids) || anyDuplicated(source_ids) || !setequal(source_ids, expected_ids) ||
      !identical(sort(ordinals), seq_len(length(ordinals)))) .per_asset_review_abort("per_asset_review_adapter_invalid")
  counts <- vapply(c("ready", "decision_required", "blocked"), function(value) sum(vapply(rows, function(row) row$disposition == value, logical(1L))), integer(1L))
  expected_status <- if (counts[["blocked"]] > 0L) "blocked" else if (counts[["decision_required"]] > 0L) "decision_required" else "ready"
  if (!identical(plan$status, expected_status)) .per_asset_review_abort("per_asset_review_adapter_invalid")
  reconciliation <- plan$reconciliation
  if (!is.list(reconciliation) || !identical(names(reconciliation), c(
    "status", "event_counts", "account_positions", "remaining_lot_count", "realized_sales",
    "outgoing_receipt_count", "transfer_receipt_count", "cost_average", "totals",
    "cash_posting_count", "synthetic_cash_posting_created", "provider_price_used",
    "tax_classification_inferred"
  ))) .per_asset_review_abort("per_asset_review_adapter_invalid")
  list(per_asset_review_preview_version=1L, preview_ref=sprintf("review_preview_%04d", generation), source_ref=source_ref,
       status=plan$status, counts=list(row_count=length(rows), ready_count=unname(counts[["ready"]]), decision_required_count=unname(counts[["decision_required"]]), blocked_count=unname(counts[["blocked"]])),
       rows=rows, reconciliation=reconciliation, summary=plan$summary,
       safeguards=list(cash_settlement_created=FALSE, canonical_write_authorized=FALSE, provider_access_authorized=FALSE))
}

data_per_asset_review_prepare_v1 <- function(center, form, prepared_at_utc) {
  .per_asset_review_assert(center)
  if (is.null(center$source)) .per_asset_review_abort("per_asset_review_source_missing")
  if (!.per_asset_review_utc_valid(prepared_at_utc)) .per_asset_review_abort("per_asset_review_form_invalid")
  center$current <- NULL; center$product <- NULL
  review <- .per_asset_review_form(center, form)
  plan <- tryCatch(
    center$adapter$plan_review(center$context, center$source$source_token, review),
    spot_per_asset_review_error = function(error) stop(error),
    error = function(error) .per_asset_review_abort("per_asset_review_adapter_failed")
  )
  center$sequence <- center$sequence + 1L
  public <- .per_asset_review_public_preview(plan, center$sequence, center$selection$source_ref, center$source$rows)
  center$current <- list(generation=center$sequence, prepared_at_utc=prepared_at_utc, plan_token=plan$plan_token, public=public, consumed=FALSE, confirmed=FALSE)
  public
}

data_per_asset_review_confirm_v1 <- function(center, preview_ref) {
  .per_asset_review_assert(center)
  if (is.null(center$current)) .per_asset_review_abort("per_asset_review_preview_missing")
  if (!is.character(preview_ref) || length(preview_ref) != 1L || is.na(preview_ref) || !identical(preview_ref, center$current$public$preview_ref)) .per_asset_review_abort("per_asset_review_confirmation_expired")
  if (isTRUE(center$current$consumed)) .per_asset_review_abort("per_asset_review_confirmation_consumed")
  if (!identical(center$current$public$status, "ready")) .per_asset_review_abort("per_asset_review_not_ready")
  center$current$confirmed <- TRUE
  list(confirmation_version=1L, preview_ref=preview_ref, status="confirmed", one_use=TRUE)
}

data_per_asset_review_apply_v1 <- function(center, preview_ref) {
  .per_asset_review_assert(center)
  if (is.null(center$current)) .per_asset_review_abort("per_asset_review_preview_missing")
  if (!is.character(preview_ref) || length(preview_ref) != 1L || is.na(preview_ref) || !identical(preview_ref, center$current$public$preview_ref)) .per_asset_review_abort("per_asset_review_confirmation_expired")
  if (isTRUE(center$current$consumed)) .per_asset_review_abort("per_asset_review_confirmation_consumed")
  if (!isTRUE(center$current$confirmed)) .per_asset_review_abort("per_asset_review_confirmation_required")
  if (!identical(center$current$public$status, "ready")) .per_asset_review_abort("per_asset_review_not_ready")
  center$current$consumed <- TRUE; center$current$confirmed <- FALSE
  result <- tryCatch(
    center$adapter$apply_plan(center$context, center$current$plan_token),
    spot_per_asset_review_error = function(error) stop(error),
    error = function(error) .per_asset_review_abort("per_asset_review_adapter_failed")
  )
  if (!is.list(result) || !identical(names(result), c("apply_contract_version", "status", "receipt_ref", "row_count", "artifact_count", "sandbox_only", "canonical_write_performed", "cash_settlement_created")) ||
      !identical(result$apply_contract_version, 1L) || !identical(result$status, "completed") || !is.character(result$receipt_ref) || !nzchar(result$receipt_ref) ||
      !is.integer(result$row_count) || !is.integer(result$artifact_count) || !isTRUE(result$sandbox_only) || !identical(result$canonical_write_performed, FALSE) || !identical(result$cash_settlement_created, FALSE)) .per_asset_review_abort("per_asset_review_adapter_invalid")
  list(per_asset_review_result_version=1L, status="completed", receipt_ref=result$receipt_ref, row_count=result$row_count,
       artifact_count=result$artifact_count, sandbox_only=TRUE, canonical_write_performed=FALSE, cash_settlement_created=FALSE)
}


.per_asset_review_product_adapter <- function(value) {
  valid <- inherits(value, "spot_per_asset_review_product_adapter_v1") && is.list(value) &&
    identical(names(value), c("source_adapter", "product_preview", "product_apply", "product_binding")) &&
    inherits(value$source_adapter, "spot_per_asset_review_adapter_v1") &&
    is.function(value$product_preview) && is.function(value$product_apply) && is.function(value$product_binding)
  if (!isTRUE(valid)) .per_asset_review_abort("per_asset_review_adapter_invalid")
  value
}

.per_asset_review_product_public <- function(value, public_ref) {
  required <- c(
    "product_asset_activity_preview_version", "status", "schema_version",
    "plan_fingerprint", "event_count", "source_row_count",
    "existing_asset_activity_event_count", "semantic_contracts", "authority_contract",
    "active_generation_ref", "canonical_write", "provider_access", "network_access",
    "private_data_access", "product_preview_fingerprint"
  )
  if (!is.list(value) || !all(required %in% names(value)) ||
      !identical(value$product_asset_activity_preview_version, 1L) ||
      !value$status %in% c("ready_for_confirmation", "already_committed") ||
      !identical(value$schema_version, 401L) || !identical(value$canonical_write, FALSE) ||
      !identical(value$provider_access, FALSE) || !identical(value$network_access, FALSE) ||
      !identical(value$private_data_access, FALSE) || !identical(value$authority_contract, "schema201_derived_base_plus_asset_activity_v1") ||
      !identical(unlist(value$semantic_contracts, use.names=FALSE), c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1")) ||
      !is.numeric(value$event_count) || length(value$event_count)!=1L || value$event_count < 1L ||
      !is.numeric(value$source_row_count) || length(value$source_row_count)!=1L || value$source_row_count < 1L ||
      !is.numeric(value$existing_asset_activity_event_count) || length(value$existing_asset_activity_event_count)!=1L || value$existing_asset_activity_event_count < 0L) {
    .per_asset_review_abort("per_asset_review_adapter_invalid")
  }
  list(
    product_preview_version=1L, product_preview_ref=public_ref, status=value$status,
    schema_version=401L, event_count=as.integer(value$event_count), source_row_count=as.integer(value$source_row_count),
    existing_asset_activity_event_count=as.integer(value$existing_asset_activity_event_count),
    semantic_contracts=as.character(unlist(value$semantic_contracts, use.names=FALSE)),
    safeguards=list(
      schema201_canonical_write=FALSE,
      asset_activity_write_requires_confirmation=identical(value$status, "ready_for_confirmation"),
      automatic_cash_posting_created=FALSE, provider_access=FALSE, network_access=FALSE,
      browser_internal_authority=FALSE
    )
  )
}

data_per_asset_review_product_prepare_v1 <- function(center, product_adapter) {
  .per_asset_review_assert(center); adapter <- .per_asset_review_product_adapter(product_adapter)
  if (is.null(center$current)) .per_asset_review_abort("per_asset_review_preview_missing")
  if (!identical(center$current$public$status, "ready")) .per_asset_review_abort("per_asset_review_not_ready")
  center$product <- NULL
  value <- tryCatch(
    adapter$product_preview(center$context, center$current$plan_token),
    spot_per_asset_review_error=function(error) stop(error),
    error=function(error) .per_asset_review_abort("per_asset_review_adapter_failed")
  )
  center$sequence <- center$sequence + 1L
  public_ref <- sprintf("product_preview_%04d", center$sequence)
  public <- .per_asset_review_product_public(value, public_ref)
  center$product <- list(
    product_preview_ref=public_ref, plan_token=center$current$plan_token,
    expected_preview_fingerprint=value$preview_fingerprint,
    status=value$status, consumed=FALSE, confirmed=FALSE, public=public
  )
  public
}

data_per_asset_review_product_confirm_v1 <- function(center, product_preview_ref) {
  .per_asset_review_assert(center)
  if (is.null(center$product)) .per_asset_review_abort("per_asset_review_preview_missing")
  if (!is.character(product_preview_ref) || length(product_preview_ref)!=1L || is.na(product_preview_ref) ||
      !identical(product_preview_ref, center$product$product_preview_ref)) .per_asset_review_abort("per_asset_review_confirmation_expired")
  if (isTRUE(center$product$consumed)) .per_asset_review_abort("per_asset_review_confirmation_consumed")
  if (!identical(center$product$status, "ready_for_confirmation")) .per_asset_review_abort("per_asset_review_not_ready")
  center$product$confirmed <- TRUE
  list(confirmation_version=1L, product_preview_ref=product_preview_ref, status="confirmed", one_use=TRUE)
}

data_per_asset_review_product_apply_v1 <- function(center, product_adapter, product_preview_ref, committed_at_utc) {
  .per_asset_review_assert(center); adapter <- .per_asset_review_product_adapter(product_adapter)
  if (is.null(center$product)) .per_asset_review_abort("per_asset_review_preview_missing")
  if (!is.character(product_preview_ref) || length(product_preview_ref)!=1L || is.na(product_preview_ref) ||
      !identical(product_preview_ref, center$product$product_preview_ref)) .per_asset_review_abort("per_asset_review_confirmation_expired")
  if (isTRUE(center$product$consumed)) .per_asset_review_abort("per_asset_review_confirmation_consumed")
  if (!isTRUE(center$product$confirmed)) .per_asset_review_abort("per_asset_review_confirmation_required")
  if (!.per_asset_review_utc_valid(committed_at_utc)) .per_asset_review_abort("per_asset_review_form_invalid")
  center$product$consumed <- TRUE; center$product$confirmed <- FALSE
  result <- tryCatch(
    adapter$product_apply(center$context, center$product$plan_token, center$product$expected_preview_fingerprint, committed_at_utc),
    spot_per_asset_review_error=function(error) stop(error),
    error=function(error) .per_asset_review_abort("per_asset_review_adapter_failed")
  )
  if (!is.list(result) || !result$status %in% c("committed", "already_committed", "recovered_committed") ||
      !identical(result$schema_version, 401L) || !is.numeric(result$event_count) || result$event_count < 1L ||
      !is.numeric(result$total_asset_activity_event_count) || result$total_asset_activity_event_count < result$event_count ||
      !identical(result$cash_posting_count, 0L) ||
      !identical(unlist(result$semantic_contracts, use.names=FALSE), c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1")) ||
      (identical(result$status, "committed") && !isTRUE(result$canonical_write)) ||
      (!identical(result$status, "committed") && !identical(result$canonical_write, FALSE))) {
    .per_asset_review_abort("per_asset_review_adapter_invalid")
  }
  list(
    product_result_version=1L, status=result$status, event_count=as.integer(result$event_count),
    total_asset_activity_event_count=as.integer(result$total_asset_activity_event_count), schema_version=401L,
    asset_activity_authority_write=isTRUE(result$canonical_write), schema201_canonical_write=FALSE,
    cash_posting_count=0L, semantic_contracts=as.character(unlist(result$semantic_contracts, use.names=FALSE))
  )
}
