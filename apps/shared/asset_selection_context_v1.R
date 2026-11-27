asset_selection_context_error_codes_v1 <- function() c(
  "asset_selection_context_state_invalid",
  "asset_selection_context_catalog_invalid",
  "asset_selection_context_input_invalid",
  "asset_selection_context_selection_invalid",
  "asset_selection_context_read_model_invalid"
)

.asset_selection_context_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% asset_selection_context_error_codes_v1()) {
    stop("asset_selection_context_error_unregistered", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_asset_selection_context_error", "error", "condition")
  )
}

.asset_selection_context_abort_v1 <- function(code) {
  stop(.asset_selection_context_condition_v1(code))
}

asset_selection_context_legacy_reference_v1 <- function() list(
  source_role = "superseded_legacy_product_reference",
  relative_paths = c("ui.R", "server_functions/asset_selection_model.R"),
  adopted_patterns = c(
    "searchable_manual_multi_selection",
    "explicit_selection_mode",
    "visible_selection_summary"
  ),
  rejected_patterns = c(
    "buy_sell_row_count_as_position_status",
    "legacy_path_as_identity",
    "selection_triggered_calculation"
  ),
  copied_runtime_or_write_logic = FALSE
)

.asset_selection_context_text_v1 <- function(
  value, maximum = 160L, error_code = "asset_selection_context_catalog_invalid"
) {
  if (!error_code %in% asset_selection_context_error_codes_v1()) {
    .asset_selection_context_abort_v1("asset_selection_context_state_invalid")
  }
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      value != trimws(value) || nchar(value, type = "bytes") > maximum ||
      grepl("[[:cntrl:]]", value)) {
    .asset_selection_context_abort_v1(error_code)
  }
  value
}

.asset_selection_context_selected_refs_v1 <- function(value) {
  if (is.null(value)) return(character())
  if (!is.character(value) || anyNA(value) || length(value) > 5000L ||
      any(!nzchar(value)) || any(value != trimws(value)) ||
      any(nchar(value, type = "bytes") > 80L) || any(grepl("[[:cntrl:]]", value)) ||
      anyDuplicated(value)) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  value
}

.asset_selection_context_catalog_assets_v1 <- function(catalog) {
  boundary_fields <- c(
    "canonical_ids_exposed", "path_exposed", "canonical_write",
    "provider_access", "network_access"
  )
  if (!is.list(catalog) || !identical(catalog$status, "ready") ||
      !is.list(catalog$assets) || !all(boundary_fields %in% names(catalog)) ||
      !all(vapply(boundary_fields, function(field) identical(catalog[[field]], FALSE), logical(1L)))) {
    .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
  }
  if (!length(catalog$assets)) return(list())
  assets <- lapply(catalog$assets, function(row) {
    forbidden <- c("asset_id", "canonical_id", "internal_id", "path", "fingerprint")
    if (!is.list(row) || any(forbidden %in% names(row)) ||
        !all(c("ref", "label", "selection_label", "asset_type") %in% names(row))) {
      .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
    }
    ref <- .asset_selection_context_text_v1(row$ref, 80L)
    if (!grepl("^activity_asset_[0-9]{4,10}$", ref)) {
      .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
    }
    list(
      ref = ref,
      label = .asset_selection_context_text_v1(row$label, 160L),
      selection_label = .asset_selection_context_text_v1(row$selection_label, 240L),
      asset_type = .asset_selection_context_text_v1(row$asset_type, 40L)
    )
  })
  refs <- vapply(assets, `[[`, character(1L), "ref")
  selection_labels <- vapply(assets, `[[`, character(1L), "selection_label")
  # Presentation labels may repeat. Public refs and their visible browser-only
  # disambiguators remain one-to-one.
  if (anyDuplicated(refs) || anyDuplicated(selection_labels)) {
    .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
  }
  assets
}

asset_selection_context_resolve_v1 <- function(catalog, view_mode, selected_asset_refs = character()) {
  if (!is.character(view_mode) || length(view_mode) != 1L || is.na(view_mode) ||
      !view_mode %in% c("selected", "all")) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  assets <- .asset_selection_context_catalog_assets_v1(catalog)
  selected_asset_refs <- .asset_selection_context_selected_refs_v1(selected_asset_refs)
  available_refs <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  if (length(setdiff(selected_asset_refs, available_refs))) {
    .asset_selection_context_abort_v1("asset_selection_context_selection_invalid")
  }
  selected <- Filter(function(row) row$ref %in% selected_asset_refs, assets)
  resolved <- if (identical(view_mode, "all")) assets else selected
  list(
    asset_selection_context_version = 1L,
    status = if (!length(resolved)) "empty" else "ready",
    view_mode = view_mode,
    available_asset_count = as.integer(length(assets)),
    selected_asset_count = as.integer(length(selected)),
    resolved_asset_count = as.integer(length(resolved)),
    selected_assets = selected,
    resolved_assets = resolved,
    browser_local = TRUE,
    calculation_started = FALSE,
    provider_access = FALSE,
    network_access = FALSE,
    canonical_write = FALSE,
    path_exposed = FALSE,
    internal_id_exposed = FALSE
  )
}

.asset_selection_context_read_model_v1 <- function(read_view) {
  required <- c(
    "product_asset_activity_read_model_version", "status", "ledger_schema_version",
    "fifo_version", "fifo_world_dimension", "custody_dimension", "asset_ref_scheme",
    "asset_identity_bridge", "duplicate_labels_supported", "fifo_state",
    "full_rebuild_verified", "portfolio_count", "event_count", "position_count",
    "custody_position_count", "semantic_sources", "portfolios",
    "coupled_transaction_facts_included", "calculation_started", "provider_access",
    "network_access", "canonical_write", "path_exposed", "internal_id_exposed"
  )
  if (!is.list(read_view) || !setequal(required, names(read_view)) ||
      !identical(read_view$product_asset_activity_read_model_version, 3L) ||
      !identical(read_view$asset_ref_scheme, "activity_catalog_ephemeral_v1") ||
      !identical(read_view$asset_identity_bridge, "server_bound_not_label") ||
      !identical(read_view$duplicate_labels_supported, TRUE) ||
      !read_view$status %in% c("absent", "available") ||
      !read_view$fifo_state %in% c("unavailable", "stale", "stale_pending", "stale_failed", "fresh") ||
      !is.list(read_view$portfolios) || !identical(read_view$calculation_started, FALSE) ||
      !identical(read_view$provider_access, FALSE) || !identical(read_view$network_access, FALSE) ||
      !identical(read_view$canonical_write, FALSE) || !identical(read_view$path_exposed, FALSE) ||
      !identical(read_view$internal_id_exposed, FALSE)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  read_view
}

.asset_selection_context_activity_rows_v1 <- function(rows, catalog_by_ref) {
  if (!is.list(rows) || !is.list(catalog_by_ref)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  if (!length(rows)) return(list())
  lapply(rows, function(row) {
    forbidden <- c("asset_id", "canonical_id", "internal_id", "path", "fingerprint")
    if (!is.list(row) || any(forbidden %in% names(row)) ||
        !all(c("asset_ref", "asset_label", "asset_type") %in% names(row))) {
      .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
    }
    ref <- .asset_selection_context_text_v1(
      row$asset_ref, 80L, "asset_selection_context_read_model_invalid"
    )
    asset <- catalog_by_ref[[ref]]
    label <- .asset_selection_context_text_v1(
      row$asset_label, 160L, "asset_selection_context_read_model_invalid"
    )
    asset_type <- .asset_selection_context_text_v1(
      row$asset_type, 40L, "asset_selection_context_read_model_invalid"
    )
    if (is.null(asset) || !identical(label, asset$label) || !identical(asset_type, asset$asset_type)) {
      .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
    }
    row$asset_selection_label <- asset$selection_label
    row
  })
}

asset_selection_context_project_activity_v1 <- function(
  catalog, read_view, view_mode, selected_asset_refs = character()
) {
  selection <- asset_selection_context_resolve_v1(catalog, view_mode, selected_asset_refs)
  read_view <- .asset_selection_context_read_model_v1(read_view)
  catalog_assets <- .asset_selection_context_catalog_assets_v1(catalog)
  catalog_refs <- if (length(catalog_assets)) {
    vapply(catalog_assets, `[[`, character(1L), "ref")
  } else character()
  catalog_by_ref <- stats::setNames(catalog_assets, catalog_refs)
  resolved_refs <- if (length(selection$resolved_assets)) {
    vapply(selection$resolved_assets, `[[`, character(1L), "ref")
  } else character()

  if (identical(read_view$status, "absent")) {
    portfolios <- list()
  } else {
    portfolios <- lapply(read_view$portfolios, function(portfolio) {
      if (!is.list(portfolio) || !all(c(
        "portfolio_ordinal", "portfolio_label", "positions", "custody_positions", "events_newest_first"
      ) %in% names(portfolio))) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      # Validate every identity-bearing row against the current browser Catalog
      # before applying refs. No unknown or mismatched row may disappear silently.
      positions <- .asset_selection_context_activity_rows_v1(portfolio$positions, catalog_by_ref)
      custody <- .asset_selection_context_activity_rows_v1(portfolio$custody_positions, catalog_by_ref)
      events <- .asset_selection_context_activity_rows_v1(portfolio$events_newest_first, catalog_by_ref)
      portfolio$positions <- positions[vapply(positions, function(row) row$asset_ref %in% resolved_refs, logical(1L))]
      portfolio$custody_positions <- custody[vapply(custody, function(row) row$asset_ref %in% resolved_refs, logical(1L))]
      portfolio$events_newest_first <- events[vapply(events, function(row) row$asset_ref %in% resolved_refs, logical(1L))]
      portfolio
    })
  }
  count_rows <- function(field) as.integer(sum(vapply(portfolios, function(row) length(row[[field]]), integer(1L))))
  list(
    asset_selection_activity_projection_version = 1L,
    status = if (identical(read_view$status, "absent")) "unavailable" else selection$status,
    view_mode = selection$view_mode,
    fifo_state = read_view$fifo_state,
    available_asset_count = selection$available_asset_count,
    selected_asset_count = selection$selected_asset_count,
    resolved_asset_count = selection$resolved_asset_count,
    visible_position_count = count_rows("positions"),
    visible_custody_position_count = count_rows("custody_positions"),
    visible_event_count = count_rows("events_newest_first"),
    selected_assets = selection$selected_assets,
    resolved_assets = selection$resolved_assets,
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
