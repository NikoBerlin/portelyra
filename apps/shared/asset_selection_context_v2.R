# Additive RC27 selection algebra over the identity-bearing Activity v4 read model.
# V1 remains the frozen selected/all compatibility projection used by RC26.

.asset_selection_context_accounts_v2 <- function(catalog) {
  if (!is.list(catalog) || !is.list(catalog$accounts)) {
    .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
  }
  if (!length(catalog$accounts)) return(list())
  accounts <- lapply(catalog$accounts, function(row) {
    forbidden <- c("account_id", "canonical_id", "internal_id", "path", "fingerprint")
    required <- c("ref", "label", "selection_label", "portfolio_ref", "account_type")
    if (!is.list(row) || any(forbidden %in% names(row)) || !all(required %in% names(row))) {
      .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
    }
    ref <- .asset_selection_context_text_v1(row$ref, 80L)
    portfolio_ref <- .asset_selection_context_text_v1(row$portfolio_ref, 80L)
    if (!grepl("^activity_account_[0-9]{4,10}$", ref) ||
        !grepl("^activity_portfolio_[0-9]{4,10}$", portfolio_ref)) {
      .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
    }
    list(
      ref = ref,
      label = .asset_selection_context_text_v1(row$label, 160L),
      selection_label = .asset_selection_context_text_v1(row$selection_label, 240L),
      portfolio_ref = portfolio_ref,
      account_type = .asset_selection_context_text_v1(row$account_type, 40L)
    )
  })
  refs <- vapply(accounts, `[[`, character(1L), "ref")
  labels <- vapply(accounts, `[[`, character(1L), "selection_label")
  if (anyDuplicated(refs) || anyDuplicated(labels)) {
    .asset_selection_context_abort_v1("asset_selection_context_catalog_invalid")
  }
  accounts
}

.asset_selection_context_refs_v2 <- function(value, pattern) {
  refs <- .asset_selection_context_selected_refs_v1(value)
  if (length(refs) && any(!grepl(pattern, refs))) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  refs
}

.asset_selection_context_domains_v2 <- function(value) {
  if (!is.character(value) || !length(value) || anyNA(value) || anyDuplicated(value) ||
      any(!value %in% c("cash", "noncash"))) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  value
}

asset_selection_context_asset_domain_v2 <- function(asset_type) {
  asset_type <- .asset_selection_context_text_v1(
    asset_type, 40L, "asset_selection_context_input_invalid"
  )
  allowed <- c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "cash", "fx", "index", "other")
  if (!asset_type %in% allowed) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  if (identical(asset_type, "cash")) "cash" else "noncash"
}

.asset_selection_context_positive_decimal_v2 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^(0|[1-9][0-9]*)([.][0-9]+)?$", value) && grepl("[1-9]", value)
}

.asset_selection_context_read_model_v2 <- function(read_view) {
  required <- c(
    "product_asset_activity_read_model_version", "status", "ledger_schema_version",
    "fifo_version", "fifo_world_dimension", "custody_dimension", "asset_ref_scheme",
    "asset_identity_bridge", "duplicate_labels_supported", "account_ref_scheme",
    "account_identity_bridge", "duplicate_account_labels_supported", "supported_asset_domains",
    "fifo_state", "full_rebuild_verified", "portfolio_count", "event_count", "position_count",
    "custody_position_count", "semantic_sources", "portfolios",
    "coupled_transaction_facts_included", "calculation_started", "provider_access",
    "network_access", "canonical_write", "path_exposed", "internal_id_exposed"
  )
  if (!is.list(read_view) || !setequal(required, names(read_view)) ||
      !identical(read_view$product_asset_activity_read_model_version, 4L) ||
      !identical(read_view$asset_ref_scheme, "activity_catalog_ephemeral_v1") ||
      !identical(read_view$asset_identity_bridge, "server_bound_not_label") ||
      !identical(read_view$duplicate_labels_supported, TRUE) ||
      !identical(read_view$account_ref_scheme, "activity_account_ephemeral_v1") ||
      !identical(read_view$account_identity_bridge, "server_bound_not_label") ||
      !identical(read_view$duplicate_account_labels_supported, TRUE) ||
      !identical(read_view$supported_asset_domains, list("noncash")) ||
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

.asset_selection_context_account_row_v2 <- function(
  row, account_by_ref, ref_field = "account_ref", label_field = "account_label",
  optional = FALSE
) {
  ref <- row[[ref_field]]
  label <- row[[label_field]]
  if (optional && is.null(ref) && is.null(label)) return(NULL)
  if (is.null(ref) || is.null(label)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  ref <- .asset_selection_context_text_v1(ref, 80L, "asset_selection_context_read_model_invalid")
  label <- .asset_selection_context_text_v1(label, 160L, "asset_selection_context_read_model_invalid")
  account <- account_by_ref[[ref]]
  if (!grepl("^activity_account_[0-9]{4,10}$", ref) || is.null(account) ||
      !identical(label, account$label)) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  account
}

.asset_selection_context_validate_activity_v2 <- function(catalog, read_view) {
  assets <- .asset_selection_context_catalog_assets_v1(catalog)
  accounts <- .asset_selection_context_accounts_v2(catalog)
  asset_refs <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  account_refs <- if (length(accounts)) vapply(accounts, `[[`, character(1L), "ref") else character()
  asset_by_ref <- stats::setNames(assets, asset_refs)
  account_by_ref <- stats::setNames(accounts, account_refs)
  read_view <- .asset_selection_context_read_model_v2(read_view)
  supported <- unlist(read_view$supported_asset_domains, use.names = FALSE)
  catalog_domains <- vapply(
    assets, function(row) asset_selection_context_asset_domain_v2(row$asset_type), character(1L)
  )
  if (length(setdiff(catalog_domains, supported))) {
    .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
  }
  if (identical(read_view$status, "absent")) {
    return(list(assets = assets, accounts = accounts, portfolios = list(), read_view = read_view))
  }
  portfolios <- lapply(read_view$portfolios, function(portfolio) {
    required <- c("portfolio_ordinal", "portfolio_label", "positions", "custody_positions", "events_newest_first")
    if (!is.list(portfolio) || !all(required %in% names(portfolio))) {
      .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
    }
    positions <- .asset_selection_context_activity_rows_v1(portfolio$positions, asset_by_ref)
    custody <- .asset_selection_context_activity_rows_v1(portfolio$custody_positions, asset_by_ref)
    custody <- lapply(custody, function(row) {
      forbidden <- c("account_id", "canonical_account_id", "internal_account_id")
      if (any(forbidden %in% names(row))) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      account <- .asset_selection_context_account_row_v2(row, account_by_ref)
      row$account_selection_label <- account$selection_label
      row
    })
    events <- .asset_selection_context_activity_rows_v1(portfolio$events_newest_first, asset_by_ref)
    events <- lapply(events, function(row) {
      forbidden <- c("account_id", "related_account_id", "canonical_account_id", "internal_account_id")
      if (any(forbidden %in% names(row))) {
        .asset_selection_context_abort_v1("asset_selection_context_read_model_invalid")
      }
      account <- .asset_selection_context_account_row_v2(row, account_by_ref)
      related <- .asset_selection_context_account_row_v2(
        row, account_by_ref, "related_account_ref", "related_account_label", optional = TRUE
      )
      row$account_selection_label <- account$selection_label
      row$related_account_selection_label <- if (is.null(related)) NULL else related$selection_label
      row
    })
    portfolio$positions <- positions
    portfolio$custody_positions <- custody
    portfolio$events_newest_first <- events
    portfolio
  })
  list(assets = assets, accounts = accounts, portfolios = portfolios, read_view = read_view)
}

.asset_selection_context_filter_refs_v2 <- function(
  validated, asset_domains, account_refs, account_match, account_usage
) {
  asset_domains <- .asset_selection_context_domains_v2(asset_domains)
  account_refs <- .asset_selection_context_refs_v2(account_refs, "^activity_account_[0-9]{4,10}$")
  if (!is.character(account_match) || length(account_match) != 1L || is.na(account_match) ||
      !account_match %in% c("any", "all", "none") ||
      !is.character(account_usage) || length(account_usage) != 1L || is.na(account_usage) ||
      !account_usage %in% c("current", "historical")) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  assets <- validated$assets
  available_refs <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  available_account_refs <- if (length(validated$accounts)) {
    vapply(validated$accounts, `[[`, character(1L), "ref")
  } else character()
  if (length(setdiff(account_refs, available_account_refs))) {
    .asset_selection_context_abort_v1("asset_selection_context_selection_invalid")
  }
  supported <- unlist(validated$read_view$supported_asset_domains, use.names = FALSE)
  unsupported <- setdiff(asset_domains, supported)
  if (length(unsupported)) {
    return(list(
      status = "unavailable", reason = "unsupported_asset_domain", refs = character(),
      requested_asset_domains = asset_domains, supported_asset_domains = supported,
      account_refs = account_refs, account_match = account_match, account_usage = account_usage
    ))
  }
  if (identical(validated$read_view$status, "absent")) {
    return(list(
      status = "unavailable", reason = "read_model_absent", refs = character(),
      requested_asset_domains = asset_domains, supported_asset_domains = supported,
      account_refs = account_refs, account_match = account_match, account_usage = account_usage
    ))
  }
  if (length(account_refs) && identical(account_usage, "current") &&
      !identical(validated$read_view$fifo_state, "fresh")) {
    return(list(
      status = "unavailable", reason = "current_custody_not_fresh", refs = character(),
      requested_asset_domains = asset_domains, supported_asset_domains = supported,
      account_refs = account_refs, account_match = account_match, account_usage = account_usage
    ))
  }
  relations <- stats::setNames(rep(list(character()), length(available_refs)), available_refs)
  if (length(account_refs)) {
    for (portfolio in validated$portfolios) {
      if (identical(account_usage, "current")) {
        for (row in portfolio$custody_positions) {
          if (.asset_selection_context_positive_decimal_v2(row$remaining_quantity_decimal)) {
            relations[[row$asset_ref]] <- unique(c(relations[[row$asset_ref]], row$account_ref))
          }
        }
      } else {
        for (row in portfolio$events_newest_first) {
          values <- row$account_ref
          if (!is.null(row$related_account_ref)) values <- c(values, row$related_account_ref)
          relations[[row$asset_ref]] <- unique(c(relations[[row$asset_ref]], values))
        }
      }
    }
  }
  domain_match <- vapply(assets, function(asset) {
    asset_selection_context_asset_domain_v2(asset$asset_type) %in% asset_domains
  }, logical(1L))
  account_match_result <- if (!length(account_refs)) {
    rep(TRUE, length(available_refs))
  } else vapply(available_refs, function(ref) {
    related <- relations[[ref]]
    if (identical(account_match, "any")) return(any(account_refs %in% related))
    if (identical(account_match, "all")) return(all(account_refs %in% related))
    !any(account_refs %in% related)
  }, logical(1L))
  list(
    status = "available", reason = NULL,
    refs = available_refs[domain_match & account_match_result],
    requested_asset_domains = asset_domains, supported_asset_domains = supported,
    account_refs = account_refs, account_match = account_match, account_usage = account_usage
  )
}

asset_selection_context_resolve_v2 <- function(
  catalog, manual_asset_refs = character(), filter_asset_refs = character(),
  scope_mode = "all", excluded_asset_refs = character(), filter_status = "available"
) {
  if (!is.character(scope_mode) || length(scope_mode) != 1L || is.na(scope_mode) ||
      !scope_mode %in% c("all", "manual", "filter", "union", "intersection") ||
      !is.character(filter_status) || length(filter_status) != 1L ||
      !filter_status %in% c("available", "unavailable")) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  assets <- .asset_selection_context_catalog_assets_v1(catalog)
  available <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  manual <- .asset_selection_context_refs_v2(manual_asset_refs, "^activity_asset_[0-9]{4,10}$")
  filtered <- .asset_selection_context_refs_v2(filter_asset_refs, "^activity_asset_[0-9]{4,10}$")
  excluded <- .asset_selection_context_refs_v2(excluded_asset_refs, "^activity_asset_[0-9]{4,10}$")
  if (length(setdiff(c(manual, filtered, excluded), available))) {
    .asset_selection_context_abort_v1("asset_selection_context_selection_invalid")
  }
  if (identical(filter_status, "unavailable")) {
    resolved <- character()
    status <- "unavailable"
  } else {
    resolved <- switch(
      scope_mode,
      all = available,
      manual = manual,
      filter = filtered,
      union = available[available %in% union(manual, filtered)],
      intersection = available[available %in% intersect(manual, filtered)]
    )
    resolved <- resolved[!resolved %in% excluded]
    status <- if (length(resolved)) "ready" else "empty"
  }
  by_ref <- stats::setNames(assets, available)
  rows <- function(refs) unname(by_ref[refs])
  list(
    asset_selection_context_version = 2L,
    status = status,
    scope_mode = scope_mode,
    available_asset_count = as.integer(length(available)),
    manual_asset_count = as.integer(length(manual)),
    filter_asset_count = as.integer(length(filtered)),
    excluded_asset_count = as.integer(length(excluded)),
    resolved_asset_count = as.integer(length(resolved)),
    manual_assets = rows(manual), filter_assets = rows(filtered),
    excluded_assets = rows(excluded), resolved_assets = rows(resolved),
    browser_local = TRUE, calculation_started = FALSE, provider_access = FALSE,
    network_access = FALSE, canonical_write = FALSE, path_exposed = FALSE,
    internal_id_exposed = FALSE
  )
}

asset_selection_context_project_activity_v2 <- function(
  catalog, read_view, manual_asset_refs = character(), scope_mode = "all",
  excluded_asset_refs = character(), asset_domains = "noncash",
  account_refs = character(), account_match = "any", account_usage = "current"
) {
  validated <- .asset_selection_context_validate_activity_v2(catalog, read_view)
  filter <- .asset_selection_context_filter_refs_v2(
    validated, asset_domains, account_refs, account_match, account_usage
  )
  resolver_filter_status <- filter$status
  if (identical(filter$reason, "read_model_absent") && scope_mode %in% c("all", "manual")) {
    # Keep an explicit Catalog selection visible for a first Activity command while
    # the read tables remain unavailable. Unsupported domains and stale custody
    # evidence never receive this exception.
    resolver_filter_status <- "available"
  }
  selection <- asset_selection_context_resolve_v2(
    catalog, manual_asset_refs, filter$refs, scope_mode, excluded_asset_refs,
    resolver_filter_status
  )
  resolved_refs <- if (length(selection$resolved_assets)) {
    vapply(selection$resolved_assets, `[[`, character(1L), "ref")
  } else character()
  if (identical(validated$read_view$status, "absent") || identical(selection$status, "unavailable")) {
    portfolios <- list()
  } else {
    portfolios <- lapply(validated$portfolios, function(portfolio) {
      keep <- function(rows) rows[vapply(rows, function(row) row$asset_ref %in% resolved_refs, logical(1L))]
      portfolio$positions <- keep(portfolio$positions)
      portfolio$custody_positions <- keep(portfolio$custody_positions)
      portfolio$events_newest_first <- keep(portfolio$events_newest_first)
      portfolio
    })
  }
  count_rows <- function(field) as.integer(sum(vapply(portfolios, function(row) length(row[[field]]), integer(1L))))
  status <- if (identical(validated$read_view$status, "absent")) "unavailable" else selection$status
  list(
    asset_selection_activity_projection_version = 2L,
    status = status,
    unavailable_reason = if (identical(validated$read_view$status, "absent")) "read_model_absent" else filter$reason,
    scope_mode = selection$scope_mode,
    fifo_state = validated$read_view$fifo_state,
    supported_asset_domains = filter$supported_asset_domains,
    requested_asset_domains = filter$requested_asset_domains,
    account_filter_status = filter$status,
    account_match = filter$account_match,
    account_usage = filter$account_usage,
    selected_account_count = as.integer(length(filter$account_refs)),
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
    selected_accounts = unname(stats::setNames(validated$accounts, vapply(validated$accounts, `[[`, character(1L), "ref"))[filter$account_refs]),
    portfolios = portfolios,
    browser_local = TRUE, calculation_started = FALSE, provider_access = FALSE,
    network_access = FALSE, canonical_write = FALSE, path_exposed = FALSE,
    internal_id_exposed = FALSE
  )
}
