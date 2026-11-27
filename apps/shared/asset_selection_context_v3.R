# Additive interval selection over the identity-bearing Activity v5 read model.
# V1 and V2 remain frozen compatibility projections.

# Das gepruefte Lesemodell haengt allein von Katalog und Activity-Sicht ab. Jede
# Projektion pruefte beides von vorn - beim Sitzungsstart drei Mal dieselben
# Eingaben, jedes Mal spuerbar.
# Gemerkt wird genau ein Ergebnis, und nur fuer dieselben Eingaben: identical()
# erkennt dasselbe Objekt sofort und vergleicht sonst den Inhalt. Eine Abweisung
# wird nie gemerkt.
.asset_selection_context_read_model_memo_v3 <- new.env(parent = emptyenv())
.asset_selection_context_read_model_v3 <- function(catalog, read_view) {
  memo <- .asset_selection_context_read_model_memo_v3
  if (!is.null(memo$result) && identical(memo$catalog, catalog) && identical(memo$read_view, read_view)) return(memo$result)
  result <- .asset_selection_context_read_model_checked_v3(catalog, read_view)
  memo$catalog <- catalog; memo$read_view <- read_view; memo$result <- result
  result
}

.asset_selection_context_read_model_checked_v3 <- function(catalog, read_view) {
  required <- c(
    "product_asset_activity_read_model_version", "status", "ledger_schema_version",
    "fifo_version", "fifo_world_dimension", "custody_dimension", "asset_ref_scheme",
    "asset_identity_bridge", "duplicate_labels_supported", "account_ref_scheme",
    "account_identity_bridge", "duplicate_account_labels_supported", "supported_asset_domains",
    "interval_holding_evidence", "fifo_state", "full_rebuild_verified", "portfolio_count",
    "event_count", "position_count", "custody_position_count", "semantic_sources", "portfolios",
    "coupled_transaction_facts_included", "calculation_started", "provider_access",
    "network_access", "canonical_write", "path_exposed", "internal_id_exposed"
  )
  if (!is.list(read_view) || !setequal(required, names(read_view)) ||
      !identical(read_view$product_asset_activity_read_model_version, 5L) ||
      !is.character(read_view$interval_holding_evidence) ||
      !is.list(read_view$semantic_sources) ||
      length(read_view$interval_holding_evidence) != 1L ||
      is.na(read_view$interval_holding_evidence) ||
      !read_view$interval_holding_evidence %in% c("unavailable", "fresh_completed_fifo_event_quantities") ||
      !identical(
        identical(read_view$interval_holding_evidence, "fresh_completed_fifo_event_quantities"),
        identical(read_view$fifo_state, "fresh")
      )) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }

  # Reuse the frozen v2 identity/account validator through an explicit v5 -> v4
  # compatibility projection. Event-level v5 fields remain additive and are retained.
  compatibility <- read_view
  compatibility$product_asset_activity_read_model_version <- 4L
  compatibility$interval_holding_evidence <- NULL
  validated <- .asset_selection_context_validate_activity_v2(catalog, compatibility)
  validated$read_view <- read_view

  integer_count <- function(value) {
    is.integer(value) && length(value) == 1L && !is.na(value) && value >= 0L
  }
  actual_events <- as.integer(sum(vapply(validated$portfolios, function(row) {
    length(row$events_newest_first)
  }, integer(1L))))
  actual_positions <- as.integer(sum(vapply(validated$portfolios, function(row) {
    length(row$positions)
  }, integer(1L))))
  actual_custody <- as.integer(sum(vapply(validated$portfolios, function(row) {
    length(row$custody_positions)
  }, integer(1L))))
  counts <- c("portfolio_count", "event_count", "position_count", "custody_position_count")
  if (!all(vapply(read_view[counts], integer_count, logical(1L))) ||
      !identical(read_view$portfolio_count, as.integer(length(validated$portfolios))) ||
      !identical(read_view$event_count, actual_events) ||
      !identical(read_view$position_count, actual_positions) ||
      !identical(read_view$custody_position_count, actual_custody) ||
      !is.logical(read_view$full_rebuild_verified) || length(read_view$full_rebuild_verified) != 1L ||
      is.na(read_view$full_rebuild_verified) ||
      (!identical(read_view$fifo_state, "fresh") &&
        any(c(actual_positions, actual_custody) != 0L)) ||
      (identical(read_view$status, "absent") && (
        !is.null(read_view$ledger_schema_version) ||
        !identical(read_view$fifo_state, "unavailable") ||
        !identical(read_view$interval_holding_evidence, "unavailable") ||
        !identical(read_view$full_rebuild_verified, FALSE) ||
        length(read_view$semantic_sources) != 0L || length(read_view$portfolios) != 0L ||
        any(c(actual_events, actual_positions, actual_custody) != 0L)
      )) ||
      (identical(read_view$status, "available") && !identical(read_view$ledger_schema_version, 401L))) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }

  decimal <- "^(0|[1-9][0-9]*)([.][0-9]*[1-9])?$"
  ordinal_valid <- vapply(validated$portfolios, function(portfolio) {
    is.integer(portfolio$portfolio_ordinal) && length(portfolio$portfolio_ordinal) == 1L &&
      !is.na(portfolio$portfolio_ordinal) && portfolio$portfolio_ordinal >= 1L
  }, logical(1L))
  if (!all(ordinal_valid)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  portfolio_ordinals <- if (length(validated$portfolios)) vapply(
    validated$portfolios, `[[`, integer(1L), "portfolio_ordinal"
  ) else integer()
  if (anyDuplicated(portfolio_ordinals) ||
      (length(portfolio_ordinals) && !identical(sort(portfolio_ordinals), seq_along(portfolio_ordinals)))) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  for (portfolio_index in seq_along(validated$portfolios)) {
    portfolio <- validated$portfolios[[portfolio_index]]
    event_groups <- split(portfolio$events_newest_first, vapply(
      portfolio$events_newest_first, `[[`, character(1L), "asset_ref"
    ))
    for (row in portfolio$events_newest_first) {
      fields <- c("fifo_event_sequence", "asset_quantity_before_decimal", "asset_quantity_after_decimal")
      if (!all(c(fields, "calculation_status") %in% names(row)) ||
          !is.character(row$calculation_status) || length(row$calculation_status) != 1L ||
          is.na(row$calculation_status) ||
          !row$calculation_status %in% c(
            "fresh_completed", "unavailable", "stale", "stale_pending", "stale_failed"
          )) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      parsed_date <- if (is.character(row$local_date) && length(row$local_date) == 1L &&
                         !is.na(row$local_date) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$local_date)) {
        suppressWarnings(as.Date(row$local_date, format = "%Y-%m-%d"))
      } else as.Date(NA)
      if (is.na(parsed_date) || !identical(format(parsed_date, "%Y-%m-%d"), row$local_date)) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      fresh_row <- identical(row$calculation_status, "fresh_completed")
      if (identical(read_view$fifo_state, "fresh")) {
        if (!fresh_row || !is.character(row$fifo_event_sequence) ||
            length(row$fifo_event_sequence) != 1L || is.na(row$fifo_event_sequence) ||
            !grepl("^[1-9][0-9]{0,8}$", row$fifo_event_sequence) ||
            !is.character(row$asset_quantity_before_decimal) ||
            length(row$asset_quantity_before_decimal) != 1L || is.na(row$asset_quantity_before_decimal) ||
            !grepl(decimal, row$asset_quantity_before_decimal) ||
            !is.character(row$asset_quantity_after_decimal) ||
            length(row$asset_quantity_after_decimal) != 1L || is.na(row$asset_quantity_after_decimal) ||
            !grepl(decimal, row$asset_quantity_after_decimal)) {
          .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
        }
      } else if (fresh_row || !is.null(row$fifo_event_sequence) ||
                 !is.null(row$asset_quantity_before_decimal) ||
                 !is.null(row$asset_quantity_after_decimal)) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
    }
    if (identical(read_view$fifo_state, "fresh")) {
      position_refs <- if (length(portfolio$positions)) vapply(
        portfolio$positions, `[[`, character(1L), "asset_ref"
      ) else character()
      if (anyDuplicated(position_refs) || !setequal(position_refs, names(event_groups))) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      positions <- stats::setNames(portfolio$positions, position_refs)
      for (asset_ref in names(event_groups)) {
        ordered <- event_groups[[asset_ref]][order(as.integer(vapply(
          event_groups[[asset_ref]], `[[`, character(1L), "fifo_event_sequence"
        )))]
        sequences <- vapply(ordered, `[[`, character(1L), "fifo_event_sequence")
        dates <- vapply(ordered, `[[`, character(1L), "local_date")
        if (!identical(sequences, as.character(seq_along(ordered))) ||
            !identical(dates, sort(dates)) ||
            (length(ordered) > 1L && any(vapply(seq_len(length(ordered) - 1L), function(index) {
              !identical(
                ordered[[index]]$asset_quantity_after_decimal,
                ordered[[index + 1L]]$asset_quantity_before_decimal
              )
            }, logical(1L))))) {
          .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
        }
        position <- positions[[asset_ref]]
        if (is.null(position) || !identical(
          ordered[[length(ordered)]]$asset_quantity_after_decimal,
          position$remaining_quantity_decimal
        )) {
          .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
        }
      }
    }
    validated$portfolios[[portfolio_index]] <- portfolio
  }
  validated
}

.asset_selection_context_interval_date_v3 <- function(value) {
  if (is.null(value) || (is.character(value) && length(value) == 1L && !is.na(value) && !nzchar(value))) {
    return(NULL)
  }
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value)) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  parsed <- suppressWarnings(as.Date(value, format = "%Y-%m-%d"))
  if (is.na(parsed) || !identical(format(parsed, "%Y-%m-%d"), value)) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  value
}

.asset_selection_context_interval_parameters_v3 <- function(
  interval_enabled, interval_from, interval_to, interval_relation, holding_mode
) {
  if (!is.logical(interval_enabled) || length(interval_enabled) != 1L || is.na(interval_enabled) ||
      !is.character(interval_relation) || length(interval_relation) != 1L || is.na(interval_relation) ||
      !interval_relation %in% c("activity", "holding", "activity_or_holding", "activity_and_holding") ||
      !is.character(holding_mode) || length(holding_mode) != 1L || is.na(holding_mode) ||
      !holding_mode %in% c("any_time", "at_start", "at_end", "throughout")) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  interval_from <- .asset_selection_context_interval_date_v3(interval_from)
  interval_to <- .asset_selection_context_interval_date_v3(interval_to)
  if (!is.null(interval_from) && !is.null(interval_to) && interval_from > interval_to) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  list(
    enabled = interval_enabled, from = interval_from, to = interval_to,
    relation = interval_relation, holding_mode = holding_mode,
    holding_required = interval_enabled && interval_relation %in% c(
      "holding", "activity_or_holding", "activity_and_holding"
    )
  )
}

.asset_selection_context_event_in_interval_v3 <- function(local_date, interval) {
  if (!is.character(local_date) || length(local_date) != 1L || is.na(local_date) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", local_date)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  (is.null(interval$from) || local_date >= interval$from) &&
    (is.null(interval$to) || local_date <= interval$to)
}

.asset_selection_context_interval_states_v3 <- function(validated, interval) {
  assets <- validated$assets
  asset_refs <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  aggregate_activity <- stats::setNames(rep(FALSE, length(asset_refs)), asset_refs)
  aggregate_holding <- stats::setNames(rep(FALSE, length(asset_refs)), asset_refs)
  portfolio_states <- vector("list", length(validated$portfolios))
  positive <- .asset_selection_context_positive_decimal_v2

  for (portfolio_index in seq_along(validated$portfolios)) {
    portfolio <- validated$portfolios[[portfolio_index]]
    groups <- split(portfolio$events_newest_first, vapply(
      portfolio$events_newest_first, `[[`, character(1L), "asset_ref"
    ))
    states <- list()
    for (asset_ref in names(groups)) {
      rows <- groups[[asset_ref]]
      if (identical(validated$read_view$fifo_state, "fresh")) {
        rows <- rows[order(as.integer(vapply(rows, `[[`, character(1L), "fifo_event_sequence")))]
      }
      in_interval <- vapply(rows, function(row) {
        .asset_selection_context_event_in_interval_v3(row$local_date, interval)
      }, logical(1L))
      earlier <- if (is.null(interval$from)) rep(FALSE, length(rows)) else vapply(
        rows, function(row) row$local_date < interval$from, logical(1L)
      )
      activity <- any(in_interval)
      opening <- closing <- held <- NULL
      if (interval$holding_required) {
        opening <- if (any(earlier)) {
          rows[[max(which(earlier))]]$asset_quantity_after_decimal
        } else {
          rows[[1L]]$asset_quantity_before_decimal
        }
        through_end <- if (is.null(interval$to)) rep(TRUE, length(rows)) else vapply(
          rows, function(row) row$local_date <= interval$to, logical(1L)
        )
        closing <- if (any(through_end)) {
          rows[[max(which(through_end))]]$asset_quantity_after_decimal
        } else {
          rows[[1L]]$asset_quantity_before_decimal
        }
        interval_rows <- rows[in_interval]
        held_any <- positive(opening) || (length(interval_rows) && any(vapply(
          interval_rows, function(row) positive(row$asset_quantity_before_decimal) ||
            positive(row$asset_quantity_after_decimal), logical(1L)
        )))
        held <- switch(
          interval$holding_mode,
          any_time = held_any,
          at_start = positive(opening),
          at_end = positive(closing),
          throughout = positive(opening) && (!length(interval_rows) || all(vapply(
            interval_rows, function(row) positive(row$asset_quantity_after_decimal), logical(1L)
          )))
        )
      }
      first <- rows[[1L]]
      states[[length(states) + 1L]] <- list(
        asset_ref = asset_ref,
        asset_label = first$asset_label,
        asset_selection_label = first$asset_selection_label,
        asset_type = first$asset_type,
        activity_in_interval = activity,
        held_in_interval = held,
        opening_quantity_decimal = opening,
        closing_quantity_decimal = closing,
        opening_context_event_count = as.integer(sum(earlier))
      )
      aggregate_activity[[asset_ref]] <- aggregate_activity[[asset_ref]] || activity
      if (!is.null(held)) aggregate_holding[[asset_ref]] <- aggregate_holding[[asset_ref]] || held
    }
    portfolio_states[[portfolio_index]] <- states
  }

  relation_match <- switch(
    interval$relation,
    activity = aggregate_activity,
    holding = aggregate_holding,
    activity_or_holding = aggregate_activity | aggregate_holding,
    activity_and_holding = aggregate_activity & aggregate_holding
  )
  list(
    refs = asset_refs[relation_match],
    activity_refs = asset_refs[aggregate_activity],
    holding_refs = if (interval$holding_required) asset_refs[aggregate_holding] else character(),
    portfolio_states = portfolio_states
  )
}

asset_selection_context_project_activity_v3 <- function(
  catalog, read_view, manual_asset_refs = character(), scope_mode = "all",
  excluded_asset_refs = character(), asset_domains = "noncash",
  account_refs = character(), account_match = "any", account_usage = "current",
  interval_enabled = FALSE, interval_from = NULL, interval_to = NULL,
  interval_relation = "activity", holding_mode = "any_time"
) {
  interval <- .asset_selection_context_interval_parameters_v3(
    interval_enabled, interval_from, interval_to, interval_relation, holding_mode
  )
  validated <- .asset_selection_context_read_model_v3(catalog, read_view)
  account_filter <- .asset_selection_context_filter_refs_v2(
    validated, asset_domains, account_refs, account_match, account_usage
  )

  interval_status <- if (interval$enabled) "available" else "not_applied"
  interval_reason <- NULL
  interval_states <- list(
    refs = if (length(validated$assets)) vapply(validated$assets, `[[`, character(1L), "ref") else character(),
    activity_refs = character(), holding_refs = character(),
    portfolio_states = rep(list(list()), length(validated$portfolios))
  )
  if (interval$enabled && identical(validated$read_view$status, "absent")) {
    interval_status <- "unavailable"
    interval_reason <- "read_model_absent"
    interval_states$refs <- character()
  } else if (interval$holding_required &&
             (!identical(validated$read_view$fifo_state, "fresh") ||
              !identical(validated$read_view$interval_holding_evidence, "fresh_completed_fifo_event_quantities"))) {
    interval_status <- "unavailable"
    interval_reason <- "holding_interval_not_fresh"
    interval_states$refs <- character()
  } else if (interval$enabled) {
    interval_states <- .asset_selection_context_interval_states_v3(validated, interval)
  }

  filter_status <- if (identical(account_filter$status, "available") &&
                       !identical(interval_status, "unavailable")) "available" else "unavailable"
  unavailable_reason <- if (!identical(account_filter$status, "available")) {
    account_filter$reason
  } else {
    interval_reason
  }
  filter_refs <- intersect(account_filter$refs, interval_states$refs)
  resolver_filter_status <- filter_status
  if (!interval$enabled && identical(unavailable_reason, "read_model_absent") &&
      scope_mode %in% c("all", "manual")) {
    resolver_filter_status <- "available"
  }
  selection <- asset_selection_context_resolve_v2(
    catalog, manual_asset_refs, filter_refs, scope_mode, excluded_asset_refs,
    resolver_filter_status
  )
  resolved_refs <- if (length(selection$resolved_assets)) {
    vapply(selection$resolved_assets, `[[`, character(1L), "ref")
  } else character()

  if (identical(validated$read_view$status, "absent") || identical(selection$status, "unavailable")) {
    portfolios <- list()
  } else {
    portfolios <- lapply(seq_along(validated$portfolios), function(index) {
      portfolio <- validated$portfolios[[index]]
      keep <- function(rows) rows[vapply(rows, function(row) row$asset_ref %in% resolved_refs, logical(1L))]
      portfolio$positions <- keep(portfolio$positions)
      portfolio$custody_positions <- keep(portfolio$custody_positions)
      events <- keep(portfolio$events_newest_first)
      if (interval$enabled) events <- events[vapply(events, function(row) {
        .asset_selection_context_event_in_interval_v3(row$local_date, interval)
      }, logical(1L))]
      portfolio$events_newest_first <- events
      states <- interval_states$portfolio_states[[index]]
      portfolio$interval_asset_states <- states[vapply(states, function(row) {
        row$asset_ref %in% resolved_refs
      }, logical(1L))]
      portfolio
    })
  }
  count_rows <- function(field) as.integer(sum(vapply(portfolios, function(row) length(row[[field]]), integer(1L))))
  status <- if (identical(validated$read_view$status, "absent")) "unavailable" else selection$status
  selected_accounts <- if (length(account_filter$account_refs)) unname(stats::setNames(
    validated$accounts, vapply(validated$accounts, `[[`, character(1L), "ref")
  )[account_filter$account_refs]) else list()

  list(
    asset_selection_activity_projection_version = 3L,
    status = status,
    unavailable_reason = if (identical(validated$read_view$status, "absent")) "read_model_absent" else unavailable_reason,
    scope_mode = selection$scope_mode,
    fifo_state = validated$read_view$fifo_state,
    supported_asset_domains = account_filter$supported_asset_domains,
    requested_asset_domains = account_filter$requested_asset_domains,
    account_filter_status = account_filter$status,
    account_match = account_filter$account_match,
    account_usage = account_filter$account_usage,
    selected_account_count = as.integer(length(account_filter$account_refs)),
    interval_filter_status = interval_status,
    interval_enabled = interval$enabled,
    interval_from = interval$from,
    interval_to = interval$to,
    interval_relation = interval$relation,
    holding_mode = interval$holding_mode,
    holding_evidence_status = if (!interval$holding_required) "not_required" else if (
      identical(interval_status, "available")
    ) "fresh" else "unavailable",
    activity_interval_asset_count = as.integer(length(interval_states$activity_refs)),
    holding_interval_asset_count = as.integer(length(interval_states$holding_refs)),
    interval_filter_asset_count = as.integer(length(interval_states$refs)),
    opening_context_event_count = as.integer(sum(vapply(
      unlist(interval_states$portfolio_states, recursive = FALSE),
      function(row) row$opening_context_event_count, integer(1L)
    ))),
    available_asset_count = selection$available_asset_count,
    manual_asset_count = selection$manual_asset_count,
    filter_asset_count = selection$filter_asset_count,
    excluded_asset_count = selection$excluded_asset_count,
    resolved_asset_count = selection$resolved_asset_count,
    visible_position_count = count_rows("positions"),
    visible_custody_position_count = count_rows("custody_positions"),
    visible_event_count = count_rows("events_newest_first"),
    manual_assets = selection$manual_assets,
    filter_assets = selection$filter_assets,
    excluded_assets = selection$excluded_assets,
    resolved_assets = selection$resolved_assets,
    selected_accounts = selected_accounts,
    portfolios = portfolios,
    browser_local = TRUE,
    calculation_started = FALSE,
    provider_access = FALSE,
    network_access = FALSE,
    canonical_write = FALSE,
    path_exposed = FALSE,
    internal_id_exposed = FALSE
  )
}
