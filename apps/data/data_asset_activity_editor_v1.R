data_asset_activity_editor_error_codes_v1 <- function() c(
  "data_asset_activity_editor_state_invalid",
  "data_asset_activity_editor_context_invalid",
  "data_asset_activity_editor_catalog_unavailable",
  "data_asset_activity_editor_selection_invalid",
  "data_asset_activity_editor_input_invalid",
  "data_asset_activity_editor_preview_required",
  "data_asset_activity_editor_confirmation_required",
  "data_asset_activity_editor_confirmation_consumed",
  "data_asset_activity_editor_confirmation_expired",
  "data_asset_activity_editor_adapter_failed"
)

.data_asset_activity_editor_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% data_asset_activity_editor_error_codes_v1()) {
    stop("unregistered_data_asset_activity_editor_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_asset_activity_editor_error", "error", "condition")
  )
}

.data_asset_activity_editor_abort <- function(code) stop(.data_asset_activity_editor_condition(code))

.data_asset_activity_editor_check <- function(editor) {
  if (!inherits(editor, "spot_data_asset_activity_editor_v1") || !is.environment(editor) ||
      !is.environment(editor$previews) || !is.integer(editor$sequence) || length(editor$sequence) != 1L ||
      !is.function(editor$adapter$resolve_time) || !is.function(editor$adapter$read_view) ||
      !is.function(editor$adapter$catalog) || !is.function(editor$adapter$preview) ||
      !is.function(editor$adapter$apply)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_state_invalid")
  }
  invisible(TRUE)
}

.data_asset_activity_editor_context <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_context_invalid")
  }
  context
}

new_data_asset_activity_editor_v1 <- function(adapter) {
  if (!is.list(adapter) || !identical(names(adapter), c("resolve_time", "read_view", "catalog", "preview", "apply")) ||
      !all(vapply(adapter, is.function, logical(1L)))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_state_invalid")
  }
  editor <- new.env(hash = FALSE, parent = emptyenv())
  editor$adapter <- adapter
  editor$catalog <- NULL
  editor$selection <- NULL
  editor$previews <- new.env(hash = TRUE, parent = emptyenv())
  editor$sequence <- 0L
  class(editor) <- "spot_data_asset_activity_editor_v1"
  editor
}

.data_asset_activity_ref <- function(prefix, index) sprintf("%s%04d", prefix, as.integer(index))

.data_asset_activity_label <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      value != trimws(value) || nchar(value, type = "bytes") > 160L || grepl("[[:cntrl:]]", value)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  value
}

.data_asset_activity_index <- function(rows, prefix, id_field) {
  if (!is.list(rows) || !length(rows)) .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  identifiers <- vapply(rows, `[[`, character(1L), id_field)
  if (anyDuplicated(identifiers)) .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  refs <- vapply(seq_along(rows), function(index) .data_asset_activity_ref(prefix, index), character(1L))
  list(by_ref = setNames(rows, refs), ref_by_id = setNames(refs, identifiers))
}

data_asset_activity_editor_read_view_v1 <- function(editor, context) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  value <- tryCatch(
    editor$adapter$read_view(context),
    error = function(error) {
      if (inherits(error, "spot_desktop_product_adapter_domain_error")) stop(error)
      .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
    }
  )
  required <- c(
    "product_asset_activity_read_model_version", "status", "ledger_schema_version",
    "fifo_version", "fifo_world_dimension", "custody_dimension", "asset_ref_scheme",
    "asset_identity_bridge", "duplicate_labels_supported", "account_ref_scheme",
    "account_identity_bridge", "duplicate_account_labels_supported", "supported_asset_domains",
    "interval_holding_evidence", "fifo_state",
    "full_rebuild_verified", "portfolio_count", "event_count", "position_count",
    "custody_position_count", "semantic_sources", "portfolios",
    "coupled_transaction_facts_included", "calculation_started", "provider_access",
    "network_access", "canonical_write", "path_exposed", "internal_id_exposed"
  )
  if (!is.list(value) || !setequal(names(value), required) ||
      !identical(value$product_asset_activity_read_model_version, 5L) ||
      !identical(value$fifo_version, 2L) ||
      !identical(value$fifo_world_dimension, "portfolio_asset") ||
      !identical(value$custody_dimension, "portfolio_account_asset") ||
      !identical(value$asset_ref_scheme, "activity_catalog_ephemeral_v1") ||
      !identical(value$asset_identity_bridge, "server_bound_not_label") ||
      !identical(value$duplicate_labels_supported, TRUE) ||
      !identical(value$account_ref_scheme, "activity_account_ephemeral_v1") ||
      !identical(value$account_identity_bridge, "server_bound_not_label") ||
      !identical(value$duplicate_account_labels_supported, TRUE) ||
      !identical(value$supported_asset_domains, list("noncash")) ||
      !is.character(value$interval_holding_evidence) ||
      length(value$interval_holding_evidence) != 1L || is.na(value$interval_holding_evidence) ||
      !value$interval_holding_evidence %in% c("unavailable", "fresh_completed_fifo_event_quantities") ||
      !identical(
        identical(value$interval_holding_evidence, "fresh_completed_fifo_event_quantities"),
        identical(value$fifo_state, "fresh")
      ) ||
      !value$fifo_state %in% c("unavailable", "stale", "stale_pending", "stale_failed", "fresh") ||
      !identical(value$coupled_transaction_facts_included, FALSE) ||
      !identical(value$calculation_started, FALSE) ||
      !value$status %in% c("absent", "available") ||
      !identical(value$provider_access, FALSE) || !identical(value$network_access, FALSE) ||
      !identical(value$canonical_write, FALSE) || !identical(value$path_exposed, FALSE) ||
      !identical(value$internal_id_exposed, FALSE) || !is.list(value$portfolios) ||
      !is.list(value$semantic_sources)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  if (identical(value$status, "available") && !identical(value$ledger_schema_version, 401L)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  value
}

data_asset_activity_editor_refresh_v1 <- function(editor, context) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  value <- tryCatch(
    editor$adapter$catalog(context),
    error = function(error) {
      if (inherits(error, "spot_desktop_product_adapter_domain_error")) stop(error)
      .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
    }
  )
  if (!is.list(value) || !is.list(value$portfolios) || !length(value$portfolios) ||
      !is.list(value$accounts) || !length(value$accounts) || !is.list(value$assets) || !length(value$assets)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  portfolios <- .data_asset_activity_index(value$portfolios, "activity_portfolio_", "portfolio_id")
  accounts <- .data_asset_activity_index(value$accounts, "activity_account_", "account_id")
  assets <- .data_asset_activity_index(value$assets, "activity_asset_", "asset_id")
  editor$selection <- list(
    context_fingerprint = runtime_context_fingerprint(context),
    portfolios = portfolios, accounts = accounts, assets = assets
  )
  choice <- function(ref, row, fields = list()) c(list(ref = ref, label = .data_asset_activity_label(row$label)), fields)
  account_refs <- names(accounts$by_ref)
  account_labels <- vapply(account_refs, function(ref) {
    .data_asset_activity_label(accounts$by_ref[[ref]]$label)
  }, character(1L))
  account_label_counts <- table(account_labels)
  account_selection_labels <- vapply(seq_along(account_refs), function(index) {
    label <- account_labels[[index]]
    if (account_label_counts[[label]] == 1L) return(label)
    duplicate_ordinal <- sum(account_labels[seq_len(index)] == label)
    paste(
      label, "·", accounts$by_ref[[account_refs[[index]]]]$account_type,
      "· Auswahl", duplicate_ordinal, "von", account_label_counts[[label]]
    )
  }, character(1L))
  if (anyDuplicated(account_selection_labels)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  asset_refs <- names(assets$by_ref)
  asset_labels <- vapply(asset_refs, function(ref) {
    .data_asset_activity_label(assets$by_ref[[ref]]$label)
  }, character(1L))
  asset_label_counts <- table(asset_labels)
  asset_selection_labels <- vapply(seq_along(asset_refs), function(index) {
    label <- asset_labels[[index]]
    if (asset_label_counts[[label]] == 1L) return(label)
    duplicate_ordinal <- sum(asset_labels[seq_len(index)] == label)
    paste(
      label, "·", assets$by_ref[[asset_refs[[index]]]]$asset_type,
      "· Auswahl", duplicate_ordinal, "von", asset_label_counts[[label]]
    )
  }, character(1L))
  if (anyDuplicated(asset_selection_labels)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_catalog_unavailable")
  }
  editor$catalog <- list(
    asset_activity_editor_catalog_version = 1L, status = "ready",
    portfolios = lapply(names(portfolios$by_ref), function(ref) {
      row <- portfolios$by_ref[[ref]]; choice(ref, row, list(currency = row$base_currency))
    }),
    accounts = lapply(account_refs, function(ref) {
      row <- accounts$by_ref[[ref]]; choice(ref, row, list(
        selection_label = account_selection_labels[[match(ref, account_refs)]],
        portfolio_ref = unname(portfolios$ref_by_id[[row$portfolio_id]]), account_type = row$account_type
      ))
    }),
    assets = lapply(asset_refs, function(ref) {
      row <- assets$by_ref[[ref]]
      choice(ref, row, list(
        selection_label = asset_selection_labels[[match(ref, asset_refs)]],
        asset_type = row$asset_type, quantity_scale = as.integer(row$quantity_scale), currency = row$price_currency
      ))
    }),
    canonical_ids_exposed = FALSE, path_exposed = FALSE, canonical_write = FALSE,
    provider_access = FALSE, network_access = FALSE
  )
  editor$catalog
}

.data_asset_activity_selection <- function(editor, context) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  selection <- editor$selection
  if (is.null(selection) || !identical(selection$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  }
  selection
}

data_asset_activity_editor_ref_for_internal_v1 <- function(editor, context, entity_type, internal_id) {
  selection <- .data_asset_activity_selection(editor, context)
  if (!is.character(entity_type) || length(entity_type) != 1L || is.na(entity_type) ||
      !entity_type %in% c("asset", "account") || !is.character(internal_id) ||
      length(internal_id) != 1L || is.na(internal_id) || !nzchar(internal_id)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  }
  area <- paste0(entity_type, "s")
  ref <- unname(selection[[area]]$ref_by_id[[internal_id]])
  if (is.null(ref) || !is.character(ref) || length(ref) != 1L || !nzchar(ref)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  }
  ref
}

.data_asset_activity_resolve <- function(selection, area, ref, optional = FALSE) {
  if (optional && (is.null(ref) || identical(ref, ""))) return(NULL)
  if (!is.character(ref) || length(ref) != 1L || is.na(ref) || !nzchar(ref)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  }
  value <- selection[[area]]$by_ref[[ref]]
  if (is.null(value)) .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  value
}

.data_asset_activity_account_asset_compatible <- function(account_type, asset_type) {
  if (!is.character(account_type) || length(account_type) != 1L || is.na(account_type) ||
      !is.character(asset_type) || length(asset_type) != 1L || is.na(asset_type)) return(FALSE)
  if (identical(asset_type, "crypto")) account_type %in% c("crypto_wallet", "securities", "other")
  else account_type %in% c("securities", "other")
}

.data_asset_activity_account_choice_state_v1 <- function(catalog, portfolio_ref, asset_ref, account_ref, related_account_ref) {
  empty <- list(accounts = list(), account_ref = "", related_account_ref = "")
  if (!is.list(catalog) || !is.list(catalog$portfolios) || !is.list(catalog$accounts) || !is.list(catalog$assets)) return(empty)
  scalar <- function(value) if (is.character(value) && length(value) == 1L && !is.na(value)) value else ""
  portfolio_ref <- scalar(portfolio_ref); asset_ref <- scalar(asset_ref)
  account_ref <- scalar(account_ref); related_account_ref <- scalar(related_account_ref)
  portfolios <- Filter(function(value) is.list(value) && identical(value$ref, portfolio_ref), catalog$portfolios)
  assets <- Filter(function(value) is.list(value) && identical(value$ref, asset_ref), catalog$assets)
  accounts <- Filter(function(value) is.list(value) && is.character(value$ref) && length(value$ref) == 1L, catalog$accounts)
  if (nzchar(portfolio_ref)) {
    accounts <- if (length(portfolios) == 1L) Filter(
      function(value) identical(value$portfolio_ref, portfolio_ref), accounts
    ) else list()
  }
  if (nzchar(asset_ref)) {
    accounts <- if (length(assets) == 1L) Filter(
      function(value) .data_asset_activity_account_asset_compatible(value$account_type, assets[[1L]]$asset_type), accounts
    ) else list()
  }
  refs <- vapply(accounts, `[[`, character(1L), "ref")
  retain <- function(value) if (nzchar(value) && value %in% refs) value else ""
  list(accounts = accounts, account_ref = retain(account_ref), related_account_ref = retain(related_account_ref))
}

.data_asset_activity_scalar <- function(value, optional = FALSE, allowed = NULL, maximum = 100L) {
  if (inherits(value, "Date")) value <- if (length(value) == 1L && !is.na(value)) format(value, "%Y-%m-%d") else ""
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      value != trimws(value) || nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value) ||
      (!is.null(allowed) && !value %in% allowed)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
  }
  value
}

.data_asset_activity_event_ref <- function(context, sequence, form) {
  material <- paste(
    "native-asset-activity-event-v1", runtime_context_fingerprint(context), as.character(sequence),
    as.character(form$local_date), form$local_time, form$event_type, form$account_ref,
    form$asset_ref, sep = "|"
  )
  paste0("evt_", substr(digest::digest(charToRaw(enc2utf8(material)), algo = "sha256", serialize = FALSE), 1L, 32L))
}

.data_asset_activity_form <- function(editor, context, form) {
  required <- c(
    "event_type", "portfolio_ref", "account_ref", "related_account_ref", "asset_ref", "source_asset_ref",
    "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc",
    "original_acquired_time_evidence", "original_acquired_local_date", "original_acquired_local_time",
    "original_acquired_time_zone", "original_acquired_at_utc", "amount_input_mode", "basis_evidence_mode",
    "quantity_decimal", "eligible_quantity_decimal", "unit_price_decimal", "gross_amount_decimal",
    "monetary_fee_decimal", "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code"
  )
  if (!is.list(form) || !identical(names(form), required)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
  }
  selection <- .data_asset_activity_selection(editor, context)
  portfolio <- .data_asset_activity_resolve(selection, "portfolios", form$portfolio_ref)
  account <- .data_asset_activity_resolve(selection, "accounts", form$account_ref)
  related <- .data_asset_activity_resolve(selection, "accounts", form$related_account_ref, optional = TRUE)
  asset <- .data_asset_activity_resolve(selection, "assets", form$asset_ref)
  source_asset <- .data_asset_activity_resolve(selection, "assets", form$source_asset_ref, optional = TRUE)
  event_type <- .data_asset_activity_scalar(form$event_type, allowed = c("buy", "sell", "dividend", "stock_dividend", "reward", "deposit", "withdrawal", "transfer"))
  if (!identical(account$portfolio_id, portfolio$portfolio_id) ||
      (!is.null(related) && (!identical(related$portfolio_id, portfolio$portfolio_id) ||
        !.data_asset_activity_account_asset_compatible(related$account_type, asset$asset_type))) ||
      !.data_asset_activity_account_asset_compatible(account$account_type, asset$asset_type) ||
      (identical(event_type, "reward") && !identical(asset$asset_type, "crypto"))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_selection_invalid")
  }
  editor$sequence <- editor$sequence + 1L
  event_time_evidence <- .data_asset_activity_scalar(form$event_time_evidence, allowed = c("exact", "date_only"))
  local_date <- .data_asset_activity_scalar(form$local_date, maximum = 10L)
  local_time <- .data_asset_activity_scalar(form$local_time, optional = TRUE, maximum = 8L)
  time_zone <- .data_asset_activity_scalar(form$time_zone, maximum = 80L)
  if (identical(event_time_evidence, "exact")) {
    if (is.null(local_time)) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    resolved <- tryCatch(
      editor$adapter$resolve_time(context, local_date, local_time, time_zone),
      error = function(error) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    )
    if (!is.list(resolved) || !identical(names(resolved), c("effective_at_utc", "local_date", "local_time", "time_zone")) ||
        !identical(resolved$local_date, local_date) || !identical(resolved$local_time, local_time) ||
        !identical(resolved$time_zone, time_zone)) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
      effective_at_utc <- resolved$effective_at_utc
    supplied_utc <- .data_asset_activity_scalar(form$effective_at_utc, optional = TRUE, maximum = 20L)
    if (!is.null(supplied_utc) && !identical(supplied_utc, effective_at_utc)) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
  } else {
    if (!is.null(local_time)) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    if (!is.null(.data_asset_activity_scalar(form$effective_at_utc, optional = TRUE, maximum = 20L))) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
    effective_at_utc <- NULL
  }
  original_evidence <- .data_asset_activity_scalar(
    form$original_acquired_time_evidence, allowed = c("exact", "date_only", "not_applicable")
  )
  original_date <- .data_asset_activity_scalar(form$original_acquired_local_date, optional = TRUE, maximum = 10L)
  original_time <- .data_asset_activity_scalar(form$original_acquired_local_time, optional = TRUE, maximum = 8L)
  original_zone <- .data_asset_activity_scalar(form$original_acquired_time_zone, optional = TRUE, maximum = 80L)
  supplied_original_utc <- .data_asset_activity_scalar(form$original_acquired_at_utc, optional = TRUE, maximum = 20L)
  if (identical(original_evidence, "not_applicable")) {
    if (any(!vapply(list(original_date, original_time, original_zone, supplied_original_utc), is.null, logical(1L)))) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
    original_utc <- NULL
  } else if (identical(original_evidence, "date_only")) {
    if (is.null(original_date) || is.null(original_zone) || !is.null(original_time) || !is.null(supplied_original_utc)) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
    original_utc <- NULL
  } else {
    if (is.null(original_date) || is.null(original_time) || is.null(original_zone)) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
    resolved_original <- tryCatch(
      editor$adapter$resolve_time(context, original_date, original_time, original_zone),
      error = function(error) .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    )
    original_utc <- resolved_original$effective_at_utc
    if (!is.null(supplied_original_utc) && !identical(supplied_original_utc, original_utc)) {
      .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
    }
  }
  event <- list(
    event_ref = .data_asset_activity_event_ref(context, editor$sequence, form),
    event_type = event_type,
    account_ref = account$account_id,
    related_account_ref = if (is.null(related)) NULL else related$account_id,
    asset_ref = asset$asset_id,
    source_asset_ref = if (is.null(source_asset)) NULL else source_asset$asset_id,
    event_time_evidence = event_time_evidence,
    local_date = local_date,
    local_time = local_time,
    time_zone = time_zone,
    effective_at_utc = effective_at_utc,
    original_acquired_time_evidence = original_evidence,
    original_acquired_local_date = original_date,
    original_acquired_local_time = original_time,
    original_acquired_time_zone = original_zone,
    original_acquired_at_utc = original_utc,
    amount_input_mode = .data_asset_activity_scalar(form$amount_input_mode, allowed = c("quantity_unit_price", "gross_total", "not_applicable")),
    basis_evidence_mode = .data_asset_activity_scalar(form$basis_evidence_mode, allowed = c("derived_trade", "valuation_confirmed_as_basis", "provided_basis", "basis_missing", "not_applicable")),
    quantity_decimal = .data_asset_activity_scalar(form$quantity_decimal, optional = TRUE, maximum = 80L),
    eligible_quantity_decimal = .data_asset_activity_scalar(form$eligible_quantity_decimal, optional = TRUE, maximum = 80L),
    unit_price_decimal = .data_asset_activity_scalar(form$unit_price_decimal, optional = TRUE, maximum = 80L),
    gross_amount_decimal = .data_asset_activity_scalar(form$gross_amount_decimal, optional = TRUE, maximum = 80L),
    monetary_fee_decimal = .data_asset_activity_scalar(form$monetary_fee_decimal, optional = TRUE, maximum = 80L),
    asset_fee_quantity_decimal = .data_asset_activity_scalar(form$asset_fee_quantity_decimal, optional = TRUE, maximum = 80L),
    provided_basis_decimal = .data_asset_activity_scalar(form$provided_basis_decimal, optional = TRUE, maximum = 80L),
    movement_context_code = .data_asset_activity_scalar(form$movement_context_code, allowed = c("not_applicable", "unclassified", "gift", "inheritance", "debt_settlement", "donation", "payment", "custody_exit", "other"))
  )
  list(portfolio_id = portfolio$portfolio_id, events = list(event), selection = selection)
}

.data_asset_activity_time <- function(value) as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")

.data_asset_activity_exact_display_v2 <- function(value) {
  if (!is.list(value) || !is.character(value$exactness_status) || length(value$exactness_status)!=1L) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
  }
  if (identical(value$exactness_status,"exact_decimal")) return(value$decimal)
  if (identical(value$exactness_status,"exact_ratio")) return(paste0(value$numerator_integer,"/",value$denominator_integer))
  if (value$exactness_status %in% c("basis_missing","not_applicable")) return("not_applicable")
  .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
}

data_asset_activity_editor_prepare_v1 <- function(editor, context, form, now_utc) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  if (!is.character(now_utc) || length(now_utc) != 1L || is.na(.data_asset_activity_time(now_utc))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_input_invalid")
  }
  built <- .data_asset_activity_form(editor, context, form)
  value <- tryCatch(
    editor$adapter$preview(context, built$portfolio_id, built$events, now_utc),
    # Ein bekannter Ablehnungsgrund traegt interne Kennungen; hier werden daraus
    # Konto- und Assetbezeichnungen der Sitzung, bevor er die Oberflaeche erreicht (#420).
    spot_data_activity_block_reason_signal = function(signal) {
      selection <- tryCatch(.data_asset_activity_selection(editor, context), error = function(error) NULL)
      label <- function(kind, internal_id) {
        area <- selection[[paste0(kind, "s")]]; ref <- unname(area$ref_by_id[[internal_id]])
        if (is.null(ref)) NULL else area$by_ref[[ref]]$label
      }
      data_activity_block_reason_abort_v1(signal$explanation, label)
    },
    error = function(error) {
      # Der fertige Grund entsteht im Handler darueber und kommt hier noch einmal
      # vorbei; er geht durch wie ein Fachfehler des Adapters.
      if (inherits(error, "spot_data_asset_activity_editor_error") ||
          inherits(error, "spot_desktop_product_adapter_domain_error") ||
          inherits(error, "spot_desktop_product_block_reason_error")) stop(error)
      .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
    }
  )
  required <- c(
    "native_asset_activity_preview_version", "status", "schema_version", "command_ref", "event_type",
    "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc",
    "inventory_effect_code", "fifo_effect_code", "portfolio_quantity_change_decimal",
    "fifo_basis_created_decimal", "net_trade_proceeds_decimal", "gross_income_decimal",
    "distribution_value_decimal", "cash_posting_count", "existing_asset_activity_event_count",
    "cost_average", "event_result", "fifo_version", "fifo_world_dimension", "custody_dimension",
    "rounding_performed", "coupled_transaction_facts_in_fifo", "semantic_contracts",
    "confirmation_required", "one_attempt_only",
    "canonical_write", "schema201_canonical_write", "automatic_cash_posting_created",
    "provider_access", "network_access", "private_data_access", "path_exposed", "internal_id_exposed",
    "preview_fingerprint"
  )
  if (!is.list(value) || !all(required %in% names(value)) ||
      !identical(value$native_asset_activity_preview_version, 2L) ||
      !identical(value$status, "ready_for_confirmation") || !identical(value$schema_version, 401L) ||
      !identical(value$fifo_version, 2L) || !identical(value$fifo_world_dimension, "portfolio_asset") ||
      !identical(value$custody_dimension, "portfolio_account_asset") ||
      !identical(value$rounding_performed, FALSE) ||
      !identical(value$coupled_transaction_facts_in_fifo, FALSE) ||
      !identical(value$cash_posting_count, 0L) || !isTRUE(value$confirmation_required) ||
      !isTRUE(value$one_attempt_only) || !identical(value$canonical_write, FALSE) ||
      !identical(value$schema201_canonical_write, FALSE) ||
      !identical(value$automatic_cash_posting_created, FALSE) ||
      !identical(value$provider_access, FALSE) || !identical(value$network_access, FALSE) ||
      !identical(value$private_data_access, FALSE) || !identical(value$path_exposed, FALSE) ||
      !identical(value$internal_id_exposed, FALSE) || !is.list(value$event_result) ||
      !identical(value$event_result$semantic_contract, "asset_activity_v1") ||
      !identical(value$event_result$coupled_transaction_fact, "0") ||
      !identical(value$event_result$automatic_cash_posting_created, "0") ||
      !identical(value$event_result$cash_balance_delta_decimal, "0") ||
      !identical(value$event_result$fifo_authority, "semantic_realized_fifo_v2") ||
      !identical(as.character(unlist(value$semantic_contracts, use.names = FALSE)), "asset_activity_v1")) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
  }
  preview_ref <- .data_asset_activity_ref("activity_preview_", editor$sequence)
  expires_at_utc <- format(.data_asset_activity_time(now_utc) + 600, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  public <- list(
    asset_activity_editor_preview_version = 1L, status = "pending_confirmation",
    preview_ref = preview_ref, command_ref = value$command_ref, event_type = value$event_type,
    event_time_evidence = value$event_time_evidence, local_date = value$local_date,
    local_time = value$local_time, time_zone = value$time_zone, effective_at_utc = value$effective_at_utc,
    inventory_effect_code = value$inventory_effect_code, fifo_effect_code = value$fifo_effect_code,
    portfolio_quantity_change_decimal = value$portfolio_quantity_change_decimal,
    fifo_basis_created_decimal = value$fifo_basis_created_decimal,
    net_trade_proceeds_decimal = value$net_trade_proceeds_decimal,
    gross_income_decimal = value$gross_income_decimal,
    distribution_value_decimal = value$distribution_value_decimal,
    realized_gross_gain_decimal = value$event_result$realized_gross_gain_decimal,
    realized_gross_gain_exact = value$event_result$realized_gross_gain_exact,
    realized_gross_gain_display = .data_asset_activity_exact_display_v2(value$event_result$realized_gross_gain_exact),
    consumed_fifo_basis_decimal = value$event_result$basis_consumed_decimal,
    consumed_fifo_basis_exact = value$event_result$basis_consumed_exact,
    consumed_fifo_basis_display = .data_asset_activity_exact_display_v2(value$event_result$basis_consumed_exact),
    cash_balance_delta_decimal = value$event_result$cash_balance_delta_decimal,
    cost_average_status = value$cost_average$cost_average_status,
    remaining_quantity_decimal = value$cost_average$remaining_quantity_decimal,
    remaining_fifo_basis_decimal = value$cost_average$remaining_fifo_basis_decimal,
    cost_average_decimal = value$cost_average$cost_average_decimal,
    cost_average_exact = value$cost_average$cost_average_exact,
    cost_average_display = .data_asset_activity_exact_display_v2(value$cost_average$cost_average_exact),
    fifo_version = 2L, fifo_world_dimension = "portfolio_asset", custody_dimension = "portfolio_account_asset",
    cash_posting_count = 0L, existing_asset_activity_event_count = as.integer(value$existing_asset_activity_event_count),
    confirmation_required = TRUE, one_attempt_only = TRUE, schema201_canonical_write = FALSE,
    automatic_cash_posting_created = FALSE, provider_access = FALSE, network_access = FALSE,
    canonical_ids_exposed = FALSE, path_exposed = FALSE, expires_at_utc = expires_at_utc
  )
  assign(preview_ref, list(
    context_fingerprint = runtime_context_fingerprint(context), portfolio_id = built$portfolio_id,
    events = built$events, expected_preview_fingerprint = value$preview_fingerprint,
    expires_at_utc = expires_at_utc, confirmed = FALSE, consumed = FALSE, public = public
  ), envir = editor$previews)
  public
}

data_asset_activity_editor_confirm_v1 <- function(editor, context, preview_ref) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  if (!is.character(preview_ref) || length(preview_ref) != 1L ||
      !exists(preview_ref, envir = editor$previews, inherits = FALSE)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_preview_required")
  }
  state <- get(preview_ref, envir = editor$previews, inherits = FALSE)
  if (isTRUE(state$consumed)) .data_asset_activity_editor_abort("data_asset_activity_editor_confirmation_consumed")
  if (!identical(state$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_confirmation_expired")
  }
  state$confirmed <- TRUE
  assign(preview_ref, state, envir = editor$previews)
  list(confirmation_version = 1L, preview_ref = preview_ref, status = "confirmed", one_use = TRUE)
}

data_asset_activity_editor_execute_v1 <- function(editor, context, preview_ref, now_utc) {
  .data_asset_activity_editor_check(editor); .data_asset_activity_editor_context(context)
  if (!is.character(preview_ref) || length(preview_ref) != 1L ||
      !exists(preview_ref, envir = editor$previews, inherits = FALSE)) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_preview_required")
  }
  state <- get(preview_ref, envir = editor$previews, inherits = FALSE)
  if (isTRUE(state$consumed)) .data_asset_activity_editor_abort("data_asset_activity_editor_confirmation_consumed")
  if (!isTRUE(state$confirmed)) .data_asset_activity_editor_abort("data_asset_activity_editor_confirmation_required")
  if (!is.character(now_utc) || length(now_utc) != 1L || is.na(.data_asset_activity_time(now_utc)) ||
      .data_asset_activity_time(now_utc) > .data_asset_activity_time(state$expires_at_utc) ||
      !identical(state$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_confirmation_expired")
  }
  state$consumed <- TRUE; state$confirmed <- FALSE
  assign(preview_ref, state, envir = editor$previews)
  result <- tryCatch(
    editor$adapter$apply(
      context, state$portfolio_id, state$events,
      state$expected_preview_fingerprint, now_utc
    ),
    error = function(error) {
      if (inherits(error, "spot_desktop_product_adapter_domain_error")) stop(error)
      .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
    }
  )
  if (!is.list(result) || !result$status %in% c("committed", "already_committed", "recovered_committed") ||
      !identical(result$schema_version, 401L) || !identical(result$event_count, 1L) ||
      !is.numeric(result$total_asset_activity_event_count) || result$total_asset_activity_event_count < 1L ||
      !identical(result$cash_posting_count, 0L) ||
      !identical(as.character(unlist(result$semantic_contracts, use.names = FALSE)), c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1")) ||
      (identical(result$status, "committed") && !isTRUE(result$canonical_write)) ||
      (!identical(result$status, "committed") && !identical(result$canonical_write, FALSE))) {
    .data_asset_activity_editor_abort("data_asset_activity_editor_adapter_failed")
  }
  list(
    asset_activity_editor_result_version = 1L, status = result$status,
    command_ref = result$command_ref, event_count = 1L,
    total_asset_activity_event_count = as.integer(result$total_asset_activity_event_count),
    schema_version = 401L, asset_activity_authority_write = isTRUE(result$canonical_write),
    schema201_canonical_write = FALSE, cash_posting_count = 0L,
    semantic_contracts = as.character(unlist(result$semantic_contracts, use.names = FALSE)),
    confirmation_consumed = TRUE, provider_access = FALSE, network_access = FALSE,
    canonical_ids_exposed = FALSE, path_exposed = FALSE,
    # Nur serverseitig: Die Maske traegt Transaktions-ID und Adresse an genau diese Buchung ein (#439).
    trusted_event_ref = as.character(state$events[[1L]]$event_ref)
  )
}
