data_market_history_review_error_codes_v1 <- function() c(
  "data_market_history_review_invalid", "data_market_history_review_plot_invalid"
)

data_market_history_review_abort_v1 <- function(code) {
  if (!code %in% data_market_history_review_error_codes_v1()) {
    stop("data_market_history_review_error_unregistered", call. = FALSE)
  }
  stop(structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_market_history_review_error_v1", "error", "condition")
  ))
}

.data_market_history_review_enum_v1 <- function(value, choices) {
  is.character(value) && length(value) == 1L && !is.na(value) && value %in% choices
}

.data_market_history_review_pattern_v1 <- function(value, pattern) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl(pattern, value)
}

.data_market_history_review_warning_codes_v1 <- function() c(
  "market_review_candidate_correction", "market_review_corporate_action_pending",
  "market_review_current_observation_retained",
  "market_review_non_trading_close_carried_forward",
  "market_review_non_trading_without_predecessor",
  "market_review_observation_on_non_trading_day",
  "market_review_provider_closed_day_absence_normalized", "market_review_source_gap"
)

.data_market_history_review_recovery_codes_v1 <- function() c(
  "desktop_market_history_review_boundary_failed",
  "desktop_market_history_review_confirmation_required",
  "desktop_market_history_review_context_invalid",
  "desktop_market_history_review_cost_limit",
  "desktop_market_history_review_credential_unavailable",
  "desktop_market_history_review_scheduled_disabled",
  "desktop_market_history_review_discard_invalid",
  "desktop_market_history_review_fetch_attempt_consumed",
  "desktop_market_history_review_input_invalid",
  "desktop_market_history_review_preview_invalid",
  "desktop_market_history_review_publication_invalid",
  "desktop_market_history_review_publish_attempt_consumed",
  "desktop_market_history_review_publish_write_failed",
  "desktop_market_history_review_recovery_required",
  "desktop_market_history_review_rejected",
  "desktop_market_history_review_response_currency_mismatch",
  "desktop_market_history_review_response_invalid",
  "desktop_market_history_review_response_timezone_mismatch",
  "desktop_market_history_review_source_not_listed",
  "desktop_market_history_review_source_rejected",
  "desktop_market_history_review_stage_invalid",
  "desktop_market_history_review_store_invalid",
  "desktop_market_history_review_transport_failed",
  "desktop_market_history_review_fetch_interrupted",
  "market_history_review_boundary_failed", "market_history_review_calendar_invalid",
  "market_history_review_candidate_invalid", "market_history_review_confirmation_required",
  "market_history_review_input_invalid", "market_history_review_stale"
)

.data_market_history_review_decimal_v1 <- function(value, nullable = TRUE) {
  if (is.null(value)) return(isTRUE(nullable))
  is.character(value) && length(value) == 1L && !is.na(value) && nchar(value) <= 80L &&
    grepl("^(0\\.[0-9]*[1-9]|[1-9][0-9]*(\\.[0-9]*[1-9])?)$", value)
}

.data_market_history_review_integer_v1 <- function(value, minimum, maximum, nullable = TRUE) {
  if (is.null(value)) return(isTRUE(nullable))
  is.numeric(value) && length(value) == 1L && !is.na(value) && is.finite(value) &&
    value == trunc(value) && value >= minimum && value <= maximum
}

.data_market_history_review_date_v1 <- function(value, nullable = FALSE) {
  if (is.null(value)) return(isTRUE(nullable))
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value) &&
    !is.na(suppressWarnings(tryCatch(as.Date(value), error = function(error) as.Date(NA))))
}

.data_market_history_review_decimal_compare_v1 <- function(left, right) {
  decimal_parts <- function(value) {
    pieces <- strsplit(value, ".", fixed = TRUE)[[1L]]
    list(integer = pieces[[1L]], fraction = if (length(pieces) == 2L) pieces[[2L]] else "")
  }
  compare_digits <- function(left_digits, right_digits) {
    left_codes <- utf8ToInt(left_digits)
    right_codes <- utf8ToInt(right_digits)
    for (index in seq_len(length(left_codes))) {
      if (left_codes[[index]] < right_codes[[index]]) return(-1L)
      if (left_codes[[index]] > right_codes[[index]]) return(1L)
    }
    0L
  }
  left_parts <- decimal_parts(left)
  right_parts <- decimal_parts(right)
  if (nchar(left_parts$integer) < nchar(right_parts$integer)) return(-1L)
  if (nchar(left_parts$integer) > nchar(right_parts$integer)) return(1L)
  integer_comparison <- compare_digits(left_parts$integer, right_parts$integer)
  if (integer_comparison != 0L) return(integer_comparison)
  width <- max(nchar(left_parts$fraction), nchar(right_parts$fraction))
  if (width == 0L) return(0L)
  left_fraction <- paste0(left_parts$fraction, strrep("0", width - nchar(left_parts$fraction)))
  right_fraction <- paste0(right_parts$fraction, strrep("0", width - nchar(right_parts$fraction)))
  compare_digits(left_fraction, right_fraction)
}

.data_market_history_review_private_key_v1 <- function(value) {
  private <- c(
    "candidate_fingerprint", "staged_candidate_fingerprint", "context_fingerprint",
    "listing_ref", "asset_ref", "stage_ref", "request_ref", "receipt_fingerprint",
    "preview_fingerprint", "mapping_fingerprint", "promotion_binding_fingerprint",
    "source_ref", "context", "tenant_id", "user_id", "data_space_id",
    "data_space_path", "store_path"
  )
  if (is.character(value)) {
    return(any(grepl("^(lsr|mhs|mrq|msr|asf|ast|map)_[A-Za-z0-9_-]+$", value)))
  }
  if (!is.list(value)) return(FALSE)
  if (length(intersect(names(value), private))) return(TRUE)
  any(vapply(value, .data_market_history_review_private_key_v1, logical(1L)))
}

.data_market_history_review_exact_object_v1 <- function(value, fields) {
  is.list(value) && length(names(value)) == length(fields) &&
    setequal(names(value), fields) &&
    !.data_market_history_review_private_key_v1(value)
}

.data_market_history_review_false_fields_v1 <- function(value, fields) {
  all(vapply(value[fields], identical, logical(1L), FALSE))
}

.data_market_history_review_array_v1 <- function(value, allow_character = FALSE) {
  valid_type <- is.list(value) || (isTRUE(allow_character) && is.character(value))
  valid_type && (is.null(names(value)) || !any(nzchar(names(value))))
}

data_market_history_fetch_preview_validate_v1 <- function(value) {
  fields <- c(
    "market_history_review_fetch_preview_version", "status", "listing_browser_ref",
    "quote_currency", "market_code", "calendar_kind", "mode", "scope_start_date",
    "scope_end_date", "target_day_count", "provider_call_count",
    "fetch_confirmation_required", "provider_access", "network_access",
    "staging_write_after_confirmation", "market_history_write",
    "publish_confirmation_required_later", "provider_refetch_on_publish",
    "canonical_write", "automatic_retry", "candidate_fingerprint_exposed",
    "context_exposed", "paths_exposed", "internal_id_exposed"
  )
  if (!.data_market_history_review_exact_object_v1(value, fields) ||
      !.data_market_history_review_integer_v1(value$market_history_review_fetch_preview_version, 1, 1, FALSE) ||
      !.data_market_history_review_enum_v1(value$status, "pending_fetch_confirmation") ||
      !.data_market_history_review_pattern_v1(value$listing_browser_ref, "^market_listing_[a-f0-9]{32}$") ||
      !.data_market_history_review_pattern_v1(value$quote_currency, "^[A-Z]{3}$") ||
      !.data_market_history_review_pattern_v1(value$market_code, "^[A-Z0-9]{2,12}$") ||
      !.data_market_history_review_enum_v1(value$calendar_kind, c("exchange_calendar", "continuous_24_7")) ||
      !.data_market_history_review_enum_v1(value$mode, c("incremental", "retry_source_gaps", "full_refresh")) ||
      !.data_market_history_review_date_v1(value$scope_start_date) ||
      !.data_market_history_review_date_v1(value$scope_end_date) ||
      as.Date(value$scope_end_date) < as.Date(value$scope_start_date) ||
      !.data_market_history_review_integer_v1(value$target_day_count, 1, 3650, FALSE) ||
      value$target_day_count != as.integer(as.Date(value$scope_end_date) - as.Date(value$scope_start_date)) + 1L ||
      !.data_market_history_review_integer_v1(value$provider_call_count, 1, 1, FALSE) ||
      !isTRUE(value$fetch_confirmation_required) ||
      !isTRUE(value$staging_write_after_confirmation) ||
      !isTRUE(value$publish_confirmation_required_later) ||
      !.data_market_history_review_false_fields_v1(value, c(
        "provider_access", "network_access", "market_history_write",
        "provider_refetch_on_publish", "canonical_write", "automatic_retry",
        "candidate_fingerprint_exposed", "context_exposed", "paths_exposed",
        "internal_id_exposed"
      ))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  value
}

data_market_history_publication_result_validate_v1 <- function(value) {
  fields <- c(
    "market_history_review_publication_result_version", "status", "review_ref", "mode",
    "scope_start_date", "scope_end_date", "appended_day_count", "corrected_day_count",
    "unchanged_day_count", "observed_candidate_count", "non_trading_day_count",
    "source_gap_count", "imputed_non_trading_day_count", "warning_count", "exact_replay",
    "provider_access", "network_access", "provider_refetch", "market_history_write",
    "canonical_write", "tax_write", "reward_valuation_write", "automatic_retry",
    "candidate_fingerprint_exposed", "receipt_fingerprint_exposed", "context_exposed",
    "paths_exposed", "internal_id_exposed"
  )
  count_fields <- c(
    "appended_day_count", "corrected_day_count", "unchanged_day_count",
    "observed_candidate_count", "non_trading_day_count", "source_gap_count",
    "imputed_non_trading_day_count", "warning_count"
  )
  if (!.data_market_history_review_exact_object_v1(value, fields) ||
      !.data_market_history_review_integer_v1(value$market_history_review_publication_result_version, 1, 1, FALSE) ||
      !.data_market_history_review_enum_v1(value$status, "published") ||
      !.data_market_history_review_pattern_v1(value$review_ref, "^mhr_[a-f0-9]{32}$") ||
      !.data_market_history_review_enum_v1(value$mode, c("incremental", "retry_source_gaps", "full_refresh")) ||
      !.data_market_history_review_date_v1(value$scope_start_date) ||
      !.data_market_history_review_date_v1(value$scope_end_date) ||
      as.Date(value$scope_end_date) < as.Date(value$scope_start_date) ||
      any(!vapply(value[count_fields], .data_market_history_review_integer_v1, logical(1L), minimum = 0, maximum = 3650, nullable = FALSE)) ||
      !(identical(value$exact_replay, TRUE) || identical(value$exact_replay, FALSE)) ||
      !identical(value$market_history_write, TRUE) ||
      !.data_market_history_review_false_fields_v1(value, c(
        "provider_access", "network_access", "provider_refetch", "canonical_write",
        "tax_write", "reward_valuation_write", "automatic_retry",
        "candidate_fingerprint_exposed", "receipt_fingerprint_exposed", "context_exposed",
        "paths_exposed", "internal_id_exposed"
      ))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  days <- as.integer(as.Date(value$scope_end_date) - as.Date(value$scope_start_date)) + 1L
  if (value$appended_day_count + value$corrected_day_count + value$unchanged_day_count != days ||
      value$observed_candidate_count + value$non_trading_day_count + value$source_gap_count != days ||
      value$imputed_non_trading_day_count > value$non_trading_day_count ||
      value$warning_count > length(.data_market_history_review_warning_codes_v1())) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  value
}

data_market_history_rejection_result_validate_v1 <- function(value) {
  fields <- c(
    "market_history_review_rejection_result_version", "status", "review_ref",
    "provider_access", "network_access", "market_history_write", "canonical_write",
    "automatic_retry", "candidate_fingerprint_exposed", "context_exposed",
    "paths_exposed", "internal_id_exposed"
  )
  if (!.data_market_history_review_exact_object_v1(value, fields) ||
      !.data_market_history_review_integer_v1(value$market_history_review_rejection_result_version, 1, 1, FALSE) ||
      !.data_market_history_review_enum_v1(value$status, "rejected") ||
      !.data_market_history_review_pattern_v1(value$review_ref, "^mhr_[a-f0-9]{32}$") ||
      !.data_market_history_review_false_fields_v1(value, setdiff(fields, c(
        "market_history_review_rejection_result_version", "status", "review_ref"
      )))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  value
}

data_market_history_recovery_result_validate_v1 <- function(value) {
  fields <- c(
    "market_history_review_recovery_result_version", "status", "code",
    "provider_access_possible", "network_access_possible", "market_history_write_possible",
    "canonical_write", "automatic_retry", "candidate_fingerprint_exposed",
    "receipt_fingerprint_exposed", "context_exposed", "paths_exposed", "internal_id_exposed"
  )
  if (!.data_market_history_review_exact_object_v1(value, fields) ||
      !.data_market_history_review_integer_v1(value$market_history_review_recovery_result_version, 1, 1, FALSE) ||
      !.data_market_history_review_enum_v1(value$status, c("fetch_failed", "recovery_required")) ||
      !.data_market_history_review_enum_v1(value$code, .data_market_history_review_recovery_codes_v1()) ||
      !(identical(value$provider_access_possible, TRUE) || identical(value$provider_access_possible, FALSE)) ||
      !(identical(value$network_access_possible, TRUE) || identical(value$network_access_possible, FALSE)) ||
      !(identical(value$market_history_write_possible, TRUE) || identical(value$market_history_write_possible, FALSE)) ||
      !identical(value$provider_access_possible, value$network_access_possible) ||
      !.data_market_history_review_false_fields_v1(value, c(
        "canonical_write", "automatic_retry", "candidate_fingerprint_exposed",
        "receipt_fingerprint_exposed", "context_exposed", "paths_exposed", "internal_id_exposed"
      )) ||
      (identical(value$status, "fetch_failed") &&
       (!isTRUE(value$provider_access_possible) || isTRUE(value$market_history_write_possible))) ||
      (identical(value$status, "recovery_required") &&
       (!identical(value$code, "desktop_market_history_review_recovery_required") ||
        identical(value$provider_access_possible, value$market_history_write_possible)))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  value
}

data_market_history_review_validate_v1 <- function(value) {
  required <- c(
    "market_history_review_version", "status", "review_ref", "listing_browser_ref",
    "quote_currency", "market_code", "calendar_kind", "scope_start_date", "scope_end_date",
    "plot_scale_min_decimal", "plot_scale_max_decimal", "series", "summary", "warning_codes",
    "machine_validation_status", "visual_review_required", "publish_confirmation_required",
    "fetch_attempt_consumed", "staged_candidate_persisted", "candidate_fingerprint_exposed",
    "provider_access", "network_access", "market_history_write", "canonical_write", "tax_write",
    "reward_valuation_write", "automatic_retry", "path_exposed", "context_exposed",
    "internal_id_exposed"
  )
  if (!is.list(value) || length(names(value)) != length(required) || !setequal(names(value), required) ||
      !.data_market_history_review_integer_v1(value$market_history_review_version, 1, 1, FALSE) ||
      !.data_market_history_review_enum_v1(value$status, c("ready", "ready_with_warnings")) ||
      !.data_market_history_review_enum_v1(value$calendar_kind, c("exchange_calendar", "continuous_24_7")) ||
      !.data_market_history_review_enum_v1(value$machine_validation_status, "passed") ||
      !.data_market_history_review_pattern_v1(value$review_ref, "^mhr_[a-f0-9]{32}$") ||
      !.data_market_history_review_pattern_v1(value$listing_browser_ref, "^market_listing_[a-f0-9]{32}$") ||
      !.data_market_history_review_pattern_v1(value$quote_currency, "^[A-Z]{3}$") ||
      !.data_market_history_review_pattern_v1(value$market_code, "^[A-Z0-9]{2,12}$") ||
      !.data_market_history_review_date_v1(value$scope_start_date) ||
      !.data_market_history_review_date_v1(value$scope_end_date) ||
      !.data_market_history_review_decimal_v1(value$plot_scale_min_decimal) ||
      !.data_market_history_review_decimal_v1(value$plot_scale_max_decimal) ||
      !isTRUE(value$visual_review_required) || !isTRUE(value$publish_confirmation_required) ||
      !isTRUE(value$fetch_attempt_consumed) || !isTRUE(value$staged_candidate_persisted) ||
      !all(vapply(value[c(
        "candidate_fingerprint_exposed", "provider_access", "network_access",
        "market_history_write", "canonical_write", "tax_write", "reward_valuation_write",
        "automatic_retry", "path_exposed", "context_exposed", "internal_id_exposed"
      )], identical, logical(1L), FALSE)) ||
      !.data_market_history_review_array_v1(value$series) || !length(value$series) ||
      !is.list(value$summary) ||
      !.data_market_history_review_array_v1(value$warning_codes, allow_character = TRUE) ||
      .data_market_history_review_private_key_v1(value)) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  top_warnings <- unlist(value$warning_codes, use.names = FALSE)
  if (as.Date(value$scope_end_date) < as.Date(value$scope_start_date) ||
      as.integer(as.Date(value$scope_end_date) - as.Date(value$scope_start_date)) + 1L > 3650L ||
      length(value$series) > 3650L ||
      xor(is.null(value$plot_scale_min_decimal), is.null(value$plot_scale_max_decimal)) ||
      (!is.null(value$plot_scale_min_decimal) &&
       .data_market_history_review_decimal_compare_v1(
         value$plot_scale_min_decimal, value$plot_scale_max_decimal
       ) > 0L) ||
      !identical(value$status, if (length(top_warnings)) "ready_with_warnings" else "ready") ||
      length(top_warnings) != length(unique(top_warnings)) ||
      !identical(as.character(top_warnings), sort(as.character(top_warnings))) ||
      (length(top_warnings) && (!is.character(top_warnings) ||
                               any(!(top_warnings %in% .data_market_history_review_warning_codes_v1()))))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  row_fields <- c(
    "trading_date", "x_ordinal", "calendar_day_status", "calendar_reason",
    "candidate_day_status", "comparison_status", "current_close_decimal",
    "candidate_close_decimal", "effective_close_decimal", "effective_close_status",
    "source_observation_date", "effective_close_age_days", "plot_style",
    "current_plot_y", "candidate_plot_y", "effective_plot_y", "warning_codes"
  )
  summary_fields <- c(
    "calendar_day_count", "observed_candidate_count", "non_trading_day_count",
    "source_gap_count", "imputed_non_trading_day_count", "correction_candidate_count",
    "unavailable_effective_close_count", "warning_count"
  )
  if (length(names(value$summary)) != length(summary_fields) || !setequal(names(value$summary), summary_fields) ||
      any(!vapply(value$summary, .data_market_history_review_integer_v1, logical(1L), minimum = 0, maximum = 3650, nullable = FALSE)) ||
      value$summary$calendar_day_count < 1L ||
      value$summary$calendar_day_count != length(value$series) ||
      value$summary$warning_count != length(top_warnings)) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  for (row in value$series) {
    if (!is.list(row) || length(names(row)) != length(row_fields) || !setequal(names(row), row_fields) ||
        !.data_market_history_review_array_v1(row$warning_codes, allow_character = TRUE)) {
      data_market_history_review_abort_v1("data_market_history_review_invalid")
    }
    warnings <- unlist(row$warning_codes, use.names = FALSE)
    if (length(warnings) != length(unique(warnings)) ||
        !identical(as.character(warnings), sort(as.character(warnings))) ||
        (length(warnings) && (!is.character(warnings) ||
                              any(!(warnings %in% .data_market_history_review_warning_codes_v1())))) ||
        !.data_market_history_review_enum_v1(row$calendar_day_status, c("trading_day", "non_trading_day")) ||
        !.data_market_history_review_enum_v1(row$calendar_reason, c("scheduled_session", "weekend", "exchange_holiday", "continuous_market")) ||
        !.data_market_history_review_enum_v1(row$candidate_day_status, c("observed", "non_trading_day", "source_gap")) ||
        !.data_market_history_review_enum_v1(row$comparison_status, c("new_observation", "gap_resolution_candidate", "correction_candidate", "unchanged_observation", "new_calendar_day", "unchanged_calendar_day", "current_observation_retained", "new_source_gap", "unchanged_source_gap")) ||
        !.data_market_history_review_enum_v1(row$effective_close_status, c("observed_candidate", "observed_current", "imputed_non_trading_day", "unavailable_source_gap", "unavailable_no_predecessor", "unavailable_corporate_action")) ||
        !.data_market_history_review_enum_v1(row$plot_style, c("solid", "dashed", "gap")) ||
        !.data_market_history_review_date_v1(row$trading_date) ||
        !.data_market_history_review_date_v1(row$source_observation_date, nullable = TRUE) ||
        !.data_market_history_review_integer_v1(row$x_ordinal, 0, 3650, nullable = FALSE) ||
        !.data_market_history_review_integer_v1(row$effective_close_age_days, 0, 3650) ||
        any(!vapply(row[c("current_close_decimal", "candidate_close_decimal", "effective_close_decimal")], .data_market_history_review_decimal_v1, logical(1L))) ||
        any(!vapply(row[c("current_plot_y", "candidate_plot_y", "effective_plot_y")], .data_market_history_review_integer_v1, logical(1L), minimum = 0, maximum = 10000))) {
      data_market_history_review_abort_v1("data_market_history_review_invalid")
    }
    close_plot_pairs <- list(
      c("current_close_decimal", "current_plot_y"),
      c("candidate_close_decimal", "candidate_plot_y"),
      c("effective_close_decimal", "effective_plot_y")
    )
    if (any(vapply(close_plot_pairs, function(fields) {
          xor(is.null(row[[fields[[1L]]]]), is.null(row[[fields[[2L]]]]))
        }, logical(1L))) ||
        (identical(row$candidate_day_status, "observed") != !is.null(row$candidate_close_decimal)) ||
        (identical(row$candidate_day_status, "non_trading_day") &&
         !identical(row$calendar_day_status, "non_trading_day")) ||
        (identical(row$candidate_day_status, "source_gap") &&
         !identical(row$calendar_day_status, "trading_day")) ||
        (identical(row$calendar_day_status, "non_trading_day") &&
         !(row$calendar_reason %in% c("weekend", "exchange_holiday"))) ||
        (identical(row$calendar_day_status, "trading_day") &&
         row$calendar_reason %in% c("weekend", "exchange_holiday")) ||
        (identical(value$calendar_kind, "continuous_24_7") &&
         (!identical(row$calendar_day_status, "trading_day") ||
          !identical(row$calendar_reason, "continuous_market"))) ||
        (identical(value$calendar_kind, "exchange_calendar") &&
         identical(row$calendar_reason, "continuous_market")) ||
        (identical(row$effective_close_status, "observed_candidate") &&
         (!identical(row$effective_close_decimal, row$candidate_close_decimal) ||
          !identical(row$source_observation_date, row$trading_date) ||
          !identical(row$effective_close_age_days, 0L) ||
          !identical(row$plot_style, "solid"))) ||
        (identical(row$effective_close_status, "observed_current") &&
         (is.null(row$current_close_decimal) ||
          !identical(row$effective_close_decimal, row$current_close_decimal) ||
          !identical(row$source_observation_date, row$trading_date) ||
          !identical(row$effective_close_age_days, 0L) ||
          !identical(row$plot_style, "solid"))) ||
        (identical(row$effective_close_status, "imputed_non_trading_day") &&
         (!identical(row$candidate_day_status, "non_trading_day") ||
          is.null(row$effective_close_decimal) || is.null(row$source_observation_date) ||
          as.Date(row$source_observation_date) >= as.Date(row$trading_date) ||
          !identical(
            row$effective_close_age_days,
            as.integer(as.Date(row$trading_date) - as.Date(row$source_observation_date))
          ) || !identical(row$plot_style, "dashed"))) ||
        (startsWith(row$effective_close_status, "unavailable_") &&
         (!is.null(row$effective_close_decimal) || !is.null(row$source_observation_date) ||
          !is.null(row$effective_close_age_days) || !identical(row$plot_style, "gap")))) {
      data_market_history_review_abort_v1("data_market_history_review_invalid")
    }
    has_warning <- function(code) code %in% warnings
    warning_expectations <- c(
      market_review_candidate_correction = identical(row$comparison_status, "correction_candidate"),
      market_review_corporate_action_pending = identical(row$effective_close_status, "unavailable_corporate_action"),
      market_review_current_observation_retained = identical(row$effective_close_status, "observed_current"),
      market_review_non_trading_close_carried_forward = identical(row$effective_close_status, "imputed_non_trading_day"),
      market_review_non_trading_without_predecessor = identical(row$effective_close_status, "unavailable_no_predecessor"),
      market_review_observation_on_non_trading_day = identical(row$calendar_day_status, "non_trading_day") &&
        (identical(row$candidate_day_status, "observed") || identical(row$effective_close_status, "observed_current")),
      market_review_source_gap = identical(row$candidate_day_status, "source_gap")
    )
    if (any(vapply(names(warning_expectations), function(code) {
          !identical(has_warning(code), unname(warning_expectations[[code]]))
        }, logical(1L))) ||
        (has_warning("market_review_provider_closed_day_absence_normalized") &&
         !identical(row$candidate_day_status, "non_trading_day"))) {
      data_market_history_review_abort_v1("data_market_history_review_invalid")
    }
  }
  plotted_values <- unlist(lapply(value$series, function(row) {
    unlist(row[c("current_close_decimal", "candidate_close_decimal", "effective_close_decimal")],
           use.names = FALSE)
  }), use.names = FALSE)
  if ((!length(plotted_values) &&
       (!is.null(value$plot_scale_min_decimal) || !is.null(value$plot_scale_max_decimal))) ||
      (length(plotted_values) &&
       (is.null(value$plot_scale_min_decimal) || is.null(value$plot_scale_max_decimal) ||
        !any(vapply(plotted_values, identical, logical(1L), value$plot_scale_min_decimal)) ||
        !any(vapply(plotted_values, identical, logical(1L), value$plot_scale_max_decimal)) ||
        any(vapply(plotted_values, function(decimal) {
          .data_market_history_review_decimal_compare_v1(
            decimal, value$plot_scale_min_decimal
          ) < 0L || .data_market_history_review_decimal_compare_v1(
            decimal, value$plot_scale_max_decimal
          ) > 0L
        }, logical(1L)))))) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  if (length(plotted_values)) {
    equal_scale <- identical(value$plot_scale_min_decimal, value$plot_scale_max_decimal)
    endpoint_invalid <- any(vapply(value$series, function(row) {
      pairs <- list(
        c("current_close_decimal", "current_plot_y"),
        c("candidate_close_decimal", "candidate_plot_y"),
        c("effective_close_decimal", "effective_plot_y")
      )
      any(vapply(pairs, function(fields) {
        decimal <- row[[fields[[1L]]]]
        coordinate <- row[[fields[[2L]]]]
        if (is.null(decimal)) return(FALSE)
        if (equal_scale) return(!identical(coordinate, 5000L))
        (identical(decimal, value$plot_scale_min_decimal) && !identical(coordinate, 0L)) ||
          (identical(decimal, value$plot_scale_max_decimal) && !identical(coordinate, 10000L))
      }, logical(1L)))
    }, logical(1L)))
    if (endpoint_invalid) {
      data_market_history_review_abort_v1("data_market_history_review_invalid")
    }
  }
  row_warnings <- unique(unlist(lapply(value$series, `[[`, "warning_codes"), use.names = FALSE))
  expected_counts <- c(
    observed_candidate_count = sum(vapply(value$series, function(row) identical(row$candidate_day_status, "observed"), logical(1L))),
    non_trading_day_count = sum(vapply(value$series, function(row) identical(row$candidate_day_status, "non_trading_day"), logical(1L))),
    source_gap_count = sum(vapply(value$series, function(row) identical(row$candidate_day_status, "source_gap"), logical(1L))),
    imputed_non_trading_day_count = sum(vapply(value$series, function(row) identical(row$effective_close_status, "imputed_non_trading_day"), logical(1L))),
    correction_candidate_count = sum(vapply(value$series, function(row) identical(row$comparison_status, "correction_candidate"), logical(1L))),
    unavailable_effective_close_count = sum(vapply(value$series, function(row) startsWith(row$effective_close_status, "unavailable_"), logical(1L)))
  )
  x_values <- vapply(value$series, `[[`, numeric(1L), "x_ordinal")
  date_values <- vapply(value$series, `[[`, character(1L), "trading_date")
  date_objects <- as.Date(date_values)
  if (any(vapply(names(expected_counts), function(field) value$summary[[field]] != expected_counts[[field]], logical(1L))) ||
      !identical(sort(as.character(top_warnings)), sort(as.character(row_warnings))) ||
      !identical(as.numeric(x_values), as.numeric(seq.int(0L, length(value$series) - 1L))) ||
      !identical(date_values, sort(date_values)) ||
      length(date_values) != as.integer(as.Date(value$scope_end_date) - as.Date(value$scope_start_date)) + 1L ||
      (length(date_objects) > 1L && any(as.integer(diff(date_objects)) != 1L)) ||
      date_values[[1L]] != value$scope_start_date ||
      date_values[[length(date_values)]] != value$scope_end_date) {
    data_market_history_review_abort_v1("data_market_history_review_invalid")
  }
  value
}

.data_market_history_review_text_v1 <- function(value) {
  if (is.null(value) || !length(value) || is.na(value[[1L]])) "—" else as.character(value[[1L]])
}

data_market_history_review_rows_v1 <- function(value) {
  review <- data_market_history_review_validate_v1(value)
  labels <- c(
    observed = "beobachtet", non_trading_day = "Nicht-Handelstag", source_gap = "Quelllücke",
    new_observation = "neu", unchanged_observation = "unverändert",
    correction_candidate = "Korrekturkandidat", gap_resolution_candidate = "Lücke geschlossen",
    current_observation_retained = "bestehende Beobachtung bleibt",
    unchanged_calendar_day = "Kalendertag unverändert", new_calendar_day = "neuer Kalendertag",
    unchanged_source_gap = "Quelllücke unverändert", new_source_gap = "neue Quelllücke",
    observed_candidate = "Kandidat", observed_current = "bestehend",
    imputed_non_trading_day = "abgeleitet fortgetragen",
    unavailable_source_gap = "nicht verfügbar · Quelllücke",
    unavailable_no_predecessor = "nicht verfügbar · kein Vorgänger",
    unavailable_corporate_action = "blockiert · Corporate Action"
  )
  label <- function(value) {
    result <- unname(labels[value])
    if (is.na(result) || !length(result)) value else result
  }
  rows <- lapply(review$series, function(row) {
    warnings <- if (!length(row$warning_codes)) "—" else paste(unlist(row$warning_codes, use.names = FALSE), collapse = ", ")
    list(
      Datum = row$trading_date,
      Kandidat_Status = label(row$candidate_day_status),
      Vergleich = label(row$comparison_status),
      Bisheriger_Close = .data_market_history_review_text_v1(row$current_close_decimal),
      Kandidat_Close = .data_market_history_review_text_v1(row$candidate_close_decimal),
      Effektiver_Close = .data_market_history_review_text_v1(row$effective_close_decimal),
      Effektiv_Status = label(row$effective_close_status),
      Herkunftsdatum = .data_market_history_review_text_v1(row$source_observation_date),
      Alter_Tage = .data_market_history_review_text_v1(row$effective_close_age_days),
      Warnungen = warnings
    )
  })
  as.data.frame(do.call(rbind, lapply(rows, as.data.frame, stringsAsFactors = FALSE)),
                stringsAsFactors = FALSE, check.names = FALSE)
}

data_market_history_review_summary_v1 <- function(value) {
  review <- data_market_history_review_validate_v1(value)
  summary <- review$summary
  data.frame(
    Kennzahl = c(
      "Kalendertage", "Beobachtete Kandidaten", "Nicht-Handelstage", "Quelllücken",
      "Abgeleitet fortgetragen", "Korrekturkandidaten", "Ohne effektiven Close", "Warncodes"
    ),
    Wert = as.integer(c(
      summary$calendar_day_count, summary$observed_candidate_count,
      summary$non_trading_day_count, summary$source_gap_count,
      summary$imputed_non_trading_day_count, summary$correction_candidate_count,
      summary$unavailable_effective_close_count, summary$warning_count
    )),
    stringsAsFactors = FALSE, check.names = FALSE
  )
}

data_market_history_review_status_v1 <- function(value) {
  review <- data_market_history_review_validate_v1(value)
  labels <- c(market_review_candidate_correction='Vorhandene Kurse würden korrigiert.',
    market_review_corporate_action_pending='Corporate Action ungeklärt: Bewertung gesperrt.',
    market_review_current_observation_retained='Vorhandener Originalkurs bleibt erhalten.',
    market_review_non_trading_close_carried_forward='Kalenderbedingte Forttragung nur in der Vorschau.',
    market_review_non_trading_without_predecessor='An einzelnen Tagen fehlt ein zulässiger Vorgängerkurs.',
    market_review_observation_on_non_trading_day='Echter Kurs trotz kalenderseitigem Schließtag.',
    market_review_provider_closed_day_absence_normalized='Fehlende Providerzeilen an Kalenderschließtagen normalisiert.',
    market_review_source_gap='Quelllücken bleiben dokumentiert; Ersatzbewertung wird später separat gewählt.')
  list(
    tone = if (review$summary$correction_candidate_count > 0L ||
                 review$summary$source_gap_count > 0L ||
                 review$summary$unavailable_effective_close_count > 0L) "warning" else "neutral",
    title = if (identical(review$status, "ready_with_warnings"))
      "Gestagter Kurskandidat · Prüfung mit Hinweisen" else "Gestagter Kurskandidat · prüfbereit",
    copy = paste(
      review$scope_start_date, "bis", review$scope_end_date, "·",
      review$summary$observed_candidate_count, "Beobachtungen ·",
      review$summary$non_trading_day_count, "Nicht-Handelstage ·",
      review$summary$source_gap_count, "Quelllücken · noch nicht veröffentlicht.",
      paste(unname(labels[unlist(review$warning_codes)]),collapse=' ')
    )
  )
}

data_market_history_review_plot_v1 <- function(value) {
  review <- data_market_history_review_validate_v1(value)
  rows <- review$series
  number <- function(field) vapply(rows, function(row) {
    value <- row[[field]]
    if (is.null(value) || !length(value)) NA_real_ else as.numeric(value)
  }, numeric(1L))
  x <- number("x_ordinal")
  current <- number("current_plot_y")
  candidate <- number("candidate_plot_y")
  effective <- number("effective_plot_y")
  if (!length(x) || any(!is.finite(x))) {
    data_market_history_review_abort_v1("data_market_history_review_plot_invalid")
  }
  graphics::plot(
    x, rep(NA_real_, length(x)), type = "n", ylim = c(0, 10000), xaxt = "n", yaxt = "n",
    xlab = "Handelstag", ylab = "Relative exakte Close-Skala",
    main = paste("Kursprüfung", review$quote_currency, "·", review$market_code)
  )
  tick_count <- min(8L, length(x))
  tick_index <- unique(round(seq(1L, length(x), length.out = tick_count)))
  graphics::axis(1, at = x[tick_index], labels = vapply(rows[tick_index], `[[`, character(1L), "trading_date"), las = 2, cex.axis = 0.75)
  graphics::axis(2, at = c(0, 5000, 10000), labels = c("Minimum", "Mitte", "Maximum"), las = 1)
  graphics::grid(nx = NA, ny = NULL, col = "#e5e7eb")
  graphics::lines(x, current, type = "o", col = "#2563eb", pch = 16, lwd = 2)
  graphics::lines(x, candidate, type = "o", col = "#d97706", pch = 17, lwd = 2)
  imputed <- vapply(rows, function(row) identical(row$plot_style, "dashed"), logical(1L))
  graphics::points(x[is.finite(effective) & !imputed], effective[is.finite(effective) & !imputed], col = "#047857", pch = 15, lwd = 2)
  graphics::points(x[is.finite(effective) & imputed], effective[is.finite(effective) & imputed], col = "#047857", pch = 1, cex = 1.4, lwd = 2)
  if (length(x) > 1L) {
    for (index in 2:length(x)) {
      if (is.finite(effective[index - 1L]) && is.finite(effective[index])) {
        graphics::segments(
          x[index - 1L], effective[index - 1L], x[index], effective[index],
          col = "#047857", lty = if (imputed[index]) 2 else 1, lwd = 2
        )
      }
    }
  }
  graphics::legend(
    "topleft", legend = c("Bisher", "Kandidat", "Effektiv", "Effektiv abgeleitet"),
    col = c("#2563eb", "#d97706", "#047857", "#047857"),
    lty = c(1, 1, 1, 2), pch = c(16, 17, 15, 1), bty = "n", cex = 0.8
  )
  invisible(TRUE)
}
