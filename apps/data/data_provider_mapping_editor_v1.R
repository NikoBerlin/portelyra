data_provider_mapping_error_codes_v1 <- function() c(
  "data_provider_mapping_state_invalid", "data_provider_mapping_context_invalid",
  "data_provider_mapping_input_invalid", "data_provider_mapping_catalog_unavailable",
  "data_provider_mapping_preview_required", "data_provider_mapping_confirmation_required",
  "data_provider_mapping_confirmation_consumed", "data_provider_mapping_catalog_changed",
  "data_provider_mapping_command_failed", "data_provider_mapping_boundary_failed"
)

.data_provider_mapping_abort_v1 <- function(code) {
  if (!code %in% data_provider_mapping_error_codes_v1()) stop("data_provider_mapping_unregistered_error", call. = FALSE)
  stop(structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_provider_mapping_error_v1", "error", "condition")
  ))
}

.data_provider_mapping_boundary_v1 <- function(expression) {
  result <- tryCatch(
    expression,
    spot_data_provider_mapping_error_v1 = function(error) error,
    error = function(error) structure(
      list(message = "data_provider_mapping_boundary_failed", call = NULL, code = "data_provider_mapping_boundary_failed"),
      class = c("spot_data_provider_mapping_error_v1", "error", "condition")
    )
  )
  if (inherits(result, "spot_data_provider_mapping_error_v1")) stop(result)
  result
}

.data_provider_mapping_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .data_provider_mapping_abort_v1("data_provider_mapping_context_invalid")
  }
}

# Seit rc.394 (#495) laufen Testabruf, Einrichten und Kurshistorie fuer jeden Anbieter mit Tageskursen, der Momentkurs fuer jeden mit
# "quote". Die Data-App gibt die Anbieter aus den Plugin-Manifesten mit (data_price_provider_operations_v1); ohne Angabe nur Yahoo.
new_data_provider_mapping_editor_v1 <- function(history_providers = "yahoo", quote_providers = "yahoo") {
  editor <- new.env(hash = FALSE, parent = emptyenv())
  editor$state <- NULL
  editor$history_providers <- as.character(history_providers)
  editor$quote_providers <- as.character(quote_providers)
  editor$previews <- new.env(hash = TRUE, parent = emptyenv())
  class(editor) <- "spot_data_provider_mapping_editor_v1"
  editor
}

.data_provider_mapping_editor_valid_v1 <- function(editor) {
  if (!inherits(editor, "spot_data_provider_mapping_editor_v1") || !is.environment(editor) ||
      !is.environment(editor$previews)) {
    .data_provider_mapping_abort_v1("data_provider_mapping_state_invalid")
  }
}

.data_provider_mapping_text_v1 <- function(value, maximum, optional = FALSE) {
  if (isTRUE(optional) && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      !identical(value, trimws(value)) || nchar(value, type = "bytes") > maximum ||
      grepl("[[:cntrl:]]", value)) {
    .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
  }
  value
}

.data_provider_mapping_ref_v1 <- function(kind, index) sprintf("%s_ref_%04d", kind, as.integer(index))

.data_provider_mapping_public_v1 <- function(catalog, mappings) {
  asset_refs <- vapply(seq_along(catalog$assets), function(index) .data_provider_mapping_ref_v1("asset", index), character(1L))
  asset_ids <- vapply(catalog$assets, `[[`, character(1L), "asset_id")
  asset_ref_by_id <- stats::setNames(asset_refs, asset_ids)
  assets <- lapply(seq_along(catalog$assets), function(index) {
    row <- catalog$assets[[index]]
    list(
      ref = asset_refs[[index]], label = row$display_name, asset_type = row$asset_type,
      price_currency = row$price_currency, status = row$status
    )
  })
  mapping_refs <- vapply(seq_along(mappings$mappings), function(index) .data_provider_mapping_ref_v1("mapping", index), character(1L))
  public_mappings <- lapply(seq_along(mappings$mappings), function(index) {
    row <- mappings$mappings[[index]]
    asset_ref <- unname(asset_ref_by_id[[row$asset_id]])
    if (is.null(asset_ref)) .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
    list(
      ref = mapping_refs[[index]], asset_ref = asset_ref,
      asset_label = catalog$assets[[match(row$asset_id, asset_ids)]]$display_name,
      capability = row$capability, provider_id = row$provider_id,
      provider_symbol = row$provider_symbol, exchange_code = row$exchange_code,
      mic_code = row$mic_code, provider_currency = row$provider_currency,
      verification_status = row$verification_status, expert_only = as.logical(row$expert_only),
      enabled = as.logical(row$enabled), revision = as.integer(row$revision)
    )
  })
  list(
    public = list(
      contract_version = 1L, status = "ready", assets = assets, mappings = public_mappings,
      provider_access = FALSE, network_access = FALSE, canonical_write = FALSE,
      context_exposed = FALSE, internal_ids_exposed = FALSE, paths_exposed = FALSE
    ),
    asset_map = stats::setNames(catalog$assets, asset_refs),
    mapping_map = stats::setNames(lapply(mappings$mappings, function(row) {
      row$verification_evidence_ref <- NULL
      row
    }), mapping_refs)
  )
}

# Eine Listing-Freigabe haengt am betroffenen Asset, nicht am Gesamtkatalog.
# Vorher trug sie den Fingerprint des ganzen Katalogs: jedes neue Asset, jede
# Umbenennung und jedes neue Konto entwertete damit saemtliche Freigaben und
# sperrte Bewertung wie Historienabruf (#189).
.provider_mapping_asset_scope_fingerprint_v1 <- function(state, asset_id) {
  rows <- Filter(function(row) identical(row$asset_id, asset_id), state$asset_map)
  if (length(rows) != 1L) .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
  row <- rows[[1L]]
  .catalog_fingerprint(list(
    asset_catalog_scope_version = 1L,
    asset = row[c("asset_id", "display_name", "asset_type", "price_currency", "quantity_scale",
                  "valuation_method", "isin", "status", "revision")]
  ))
}

data_provider_mapping_editor_refresh_v1 <- function(editor, context) {
  .data_provider_mapping_boundary_v1({
    .data_provider_mapping_editor_valid_v1(editor)
    .data_provider_mapping_context_v1(context)
    catalog <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    mappings <- tryCatch(provider_mapping_read_v1(context), error = function(error) NULL)
    if (is.null(catalog) || is.null(mappings)) {
      .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
    }
    projected <- .data_provider_mapping_public_v1(catalog, mappings)
    editor$state <- list(
      context_fingerprint = runtime_context_fingerprint(context),
      catalog_fingerprint = catalog$catalog_fingerprint,
      mapping_fingerprint = mappings$provider_mapping_fingerprint,
      asset_map = projected$asset_map, mapping_map = projected$mapping_map,
      public = projected$public
    )
    projected$public
  })
}

.data_provider_mapping_state_v1 <- function(editor, context) {
  .data_provider_mapping_editor_valid_v1(editor)
  .data_provider_mapping_context_v1(context)
  if (is.null(editor$state) || !identical(editor$state$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
  }
  editor$state
}

.data_provider_mapping_prepare_command_v1 <- function(context, state, form, prepared_at_utc) {
  fields <- c(
    "action", "mapping_ref", "asset_ref", "capability", "provider_id",
    "provider_symbol", "exchange_code", "mic_code", "provider_currency", "expert_only"
  )
  if (!is.list(form) || !identical(names(form), fields) || !.desktop_product_utc_valid_v1(prepared_at_utc)) {
    .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
  }
  action <- .data_provider_mapping_text_v1(form$action, 10L)
  if (!action %in% c("create", "revise", "disable")) {
    .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
  }
  if (!is.logical(form$expert_only) || length(form$expert_only) != 1L || is.na(form$expert_only)) {
    .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
  }
  token <- .desktop_product_random_id_v1("tok_prv_")
  selected <- NULL
  if (!identical(action, "create")) {
    mapping_ref <- .data_provider_mapping_text_v1(form$mapping_ref, 40L)
    selected <- state$mapping_map[[mapping_ref]]
    asset <- state$asset_map[[form$asset_ref]]
    if (is.null(selected) || is.null(asset) || !identical(selected$asset_id, asset$asset_id))
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
  }
  if (identical(action, "create")) {
    asset_ref <- .data_provider_mapping_text_v1(form$asset_ref, 40L)
    asset <- state$asset_map[[asset_ref]]
    if (is.null(asset) || !identical(asset$status, "active")) {
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
    }
    command <- .provider_mapping_build_create_v1(
      context, token, asset$asset_id,
      .data_provider_mapping_text_v1(form$capability, 30L),
      .data_provider_mapping_text_v1(form$provider_id, 64L),
      .data_provider_mapping_text_v1(form$provider_symbol, 120L),
      .data_provider_mapping_text_v1(form$exchange_code, 80L, optional = TRUE),
      .data_provider_mapping_text_v1(form$mic_code, 4L, optional = TRUE),
      .data_provider_mapping_text_v1(form$provider_currency, 3L),
      isTRUE(form$expert_only), prepared_at_utc
    )
    asset_label <- asset$display_name
  } else if (identical(action, "revise")) {
    command <- .provider_mapping_build_revise_v1(
      context, token, selected$mapping_id, as.integer(selected$revision),
      .data_provider_mapping_text_v1(form$provider_symbol, 120L),
      .data_provider_mapping_text_v1(form$exchange_code, 80L, optional = TRUE),
      .data_provider_mapping_text_v1(form$mic_code, 4L, optional = TRUE),
      .data_provider_mapping_text_v1(form$provider_currency, 3L),
      isTRUE(form$expert_only), prepared_at_utc
    )
    matched_assets <- Filter(function(item) identical(item$asset_id, selected$asset_id), unname(state$asset_map))
    if (length(matched_assets) != 1L) .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
    asset_label <- matched_assets[[1L]]$display_name
  } else {
    command <- .provider_mapping_build_disable_v1(
      context, token, selected$mapping_id, as.integer(selected$revision), prepared_at_utc
    )
    matched_assets <- Filter(function(item) identical(item$asset_id, selected$asset_id), unname(state$asset_map))
    if (length(matched_assets) != 1L) .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
    asset_label <- matched_assets[[1L]]$display_name
  }
  list(
    command = command, action = action, asset_label = asset_label,
    provider_id = if (identical(action, "create")) command$fields$provider_id else selected$provider_id,
    provider_symbol = if (identical(action, "disable")) selected$provider_symbol else command$fields$provider_symbol,
    provider_currency = if (identical(action, "disable")) selected$provider_currency else command$fields$provider_currency
  )
}

# Spiegelbild des Testabrufs: Der Testabruf prueft eine noch unverifizierte
# Zuordnung, die Kursabfrage nutzt eine bereits verifizierte und aktive. Beide
# lesen nur; die Trennung haelt fest, wofuer der Abruf gedacht ist
# (Festlegung Snapshot-Test, 22.09.2026, #283/#373).
data_provider_mapping_editor_resolve_quote_scope_v1 <- function(editor, context, mapping_ref) {
  .data_provider_mapping_boundary_v1({
    state <- .data_provider_mapping_state_v1(editor, context)
    ref <- .data_provider_mapping_text_v1(mapping_ref, 40L)
    row <- state$mapping_map[[ref]]
    if (is.null(row) || !isTRUE(row$provider_id %in% editor$quote_providers) ||
        !identical(row$capability, "daily_history") ||
        !identical(row$verification_status, "verified") || row$enabled != 1L) {
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
    }
    list(
      mapping_id = row$mapping_id, mapping_revision = as.integer(row$revision),
      asset_id = row$asset_id, provider_id = row$provider_id,
      provider_symbol = row$provider_symbol, provider_currency = row$provider_currency,
      capability = row$capability,
      mapping_fingerprint = .provider_mapping_entity_fingerprint_v1(row),
      catalog_fingerprint = .provider_mapping_asset_scope_fingerprint_v1(state, row$asset_id)
    )
  })
}
data_provider_mapping_editor_resolve_probe_scope_v1 <- function(editor, context, mapping_ref) {
  .data_provider_mapping_boundary_v1({
    state <- .data_provider_mapping_state_v1(editor, context)
    ref <- .data_provider_mapping_text_v1(mapping_ref, 40L)
    row <- state$mapping_map[[ref]]
    if (is.null(row) || !isTRUE(row$provider_id %in% editor$history_providers) ||
        !identical(row$capability, "daily_history") ||
        !identical(row$verification_status, "unverified") || row$enabled != 0L) {
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
    }
    list(
      mapping_id = row$mapping_id, mapping_revision = as.integer(row$revision),
      asset_id = row$asset_id, provider_id = row$provider_id,
      provider_symbol = row$provider_symbol, provider_currency = row$provider_currency,
      capability = row$capability,
      mapping_fingerprint = .provider_mapping_entity_fingerprint_v1(row),
      catalog_fingerprint = .provider_mapping_asset_scope_fingerprint_v1(state, row$asset_id)
    )
  })
}

data_provider_mapping_editor_resolve_history_scope_v1 <- function(editor, context, mapping_ref) {
  .data_provider_mapping_boundary_v1({
    state <- .data_provider_mapping_state_v1(editor, context)
    ref <- .data_provider_mapping_text_v1(mapping_ref, 40L)
    row <- state$mapping_map[[ref]]
    if (is.null(row) || !isTRUE(row$provider_id %in% editor$history_providers) ||
        !identical(row$capability, "daily_history") ||
        !identical(row$verification_status, "verified") || row$enabled != 1L) {
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
    }
    list(
      mapping_id = row$mapping_id, mapping_revision = as.integer(row$revision),
      asset_id = row$asset_id, provider_id = row$provider_id,
      provider_symbol = row$provider_symbol, provider_currency = row$provider_currency,
      capability = row$capability,
      mapping_fingerprint = .provider_mapping_entity_fingerprint_v1(row),
      catalog_fingerprint = .provider_mapping_asset_scope_fingerprint_v1(state, row$asset_id),
      verification_status = row$verification_status, enabled = TRUE
    )
  })
}

data_provider_mapping_editor_prepare_verify_v1 <- function(
  editor, context, mapping_ref, probe_evidence_fingerprint, prepared_at_utc
) {
  .data_provider_mapping_boundary_v1({
    state <- .data_provider_mapping_state_v1(editor, context)
    ref <- .data_provider_mapping_text_v1(mapping_ref, 40L)
    selected <- state$mapping_map[[ref]]
    if (is.null(selected) || !identical(selected$verification_status, "unverified") || selected$enabled != 0L ||
        !is.character(probe_evidence_fingerprint) || length(probe_evidence_fingerprint) != 1L ||
        !grepl("^[a-f0-9]{64}$", probe_evidence_fingerprint) || !.desktop_product_utc_valid_v1(prepared_at_utc)) {
      .data_provider_mapping_abort_v1("data_provider_mapping_input_invalid")
    }
    matched_assets <- Filter(function(item) identical(item$asset_id, selected$asset_id), unname(state$asset_map))
    if (length(matched_assets) != 1L) .data_provider_mapping_abort_v1("data_provider_mapping_catalog_unavailable")
    command <- .provider_mapping_build_verify_v1(
      context, .desktop_product_random_id_v1("tok_prv_"), selected$mapping_id,
      as.integer(selected$revision), probe_evidence_fingerprint, prepared_at_utc
    )
    preview_ref <- paste0("prvp_", substr(.catalog_fingerprint(list(
      command = command, catalog = state$catalog_fingerprint, mappings = state$mapping_fingerprint
    )), 1L, 32L))
    public <- list(
      contract_version = 1L, status = "pending_confirmation", preview_ref = preview_ref,
      action = "verify", asset_label = matched_assets[[1L]]$display_name,
      provider_id = selected$provider_id, provider_symbol = selected$provider_symbol,
      provider_currency = selected$provider_currency,
      resulting_verification_status = "verified",
      resulting_enabled = !identical(selected$provider_id, "twelve_data"),
      confirmation_required = TRUE, provider_access = FALSE, network_access = FALSE,
      canonical_write = FALSE, context_exposed = FALSE, internal_ids_exposed = FALSE,
      paths_exposed = FALSE, fingerprints_exposed = FALSE
    )
    assign(preview_ref, list(
      consumed = FALSE, context_fingerprint = runtime_context_fingerprint(context),
      catalog_fingerprint = state$catalog_fingerprint, mapping_fingerprint = state$mapping_fingerprint,
      command = command, public = public
    ), envir = editor$previews)
    public
  })
}

data_provider_mapping_editor_prepare_v1 <- function(editor, context, form, prepared_at_utc) {
  .data_provider_mapping_boundary_v1({
    state <- .data_provider_mapping_state_v1(editor, context)
    prepared <- .data_provider_mapping_prepare_command_v1(context, state, form, prepared_at_utc)
    preview_ref <- paste0("prvp_", substr(.catalog_fingerprint(list(
      command = prepared$command, catalog = state$catalog_fingerprint,
      mappings = state$mapping_fingerprint
    )), 1L, 32L))
    public <- list(
      contract_version = 1L, status = "pending_confirmation", preview_ref = preview_ref,
      action = prepared$action, asset_label = prepared$asset_label,
      provider_id = prepared$provider_id,
      provider_symbol = prepared$provider_symbol,
      provider_currency = prepared$provider_currency,
      resulting_verification_status = if (identical(prepared$action, "disable")) "disabled" else "unverified",
      resulting_enabled = FALSE, confirmation_required = TRUE,
      provider_access = FALSE, network_access = FALSE, canonical_write = FALSE,
      context_exposed = FALSE, internal_ids_exposed = FALSE, paths_exposed = FALSE
    )
    assign(preview_ref, list(
      consumed = FALSE, context_fingerprint = runtime_context_fingerprint(context),
      catalog_fingerprint = state$catalog_fingerprint,
      mapping_fingerprint = state$mapping_fingerprint,
      command = prepared$command, public = public
    ), envir = editor$previews)
    public
  })
}

data_provider_mapping_editor_execute_v1 <- function(editor, context, preview, confirmed) {
  .data_provider_mapping_boundary_v1({
    .data_provider_mapping_editor_valid_v1(editor)
    .data_provider_mapping_context_v1(context)
    if (!isTRUE(confirmed)) .data_provider_mapping_abort_v1("data_provider_mapping_confirmation_required")
    if (!is.list(preview) || !is.character(preview$preview_ref) || length(preview$preview_ref) != 1L ||
        !exists(preview$preview_ref, envir = editor$previews, inherits = FALSE)) {
      .data_provider_mapping_abort_v1("data_provider_mapping_preview_required")
    }
    stored <- get(preview$preview_ref, envir = editor$previews, inherits = FALSE)
    if (isTRUE(stored$consumed)) .data_provider_mapping_abort_v1("data_provider_mapping_confirmation_consumed")
    if (!identical(stored$public, preview) ||
        !identical(stored$context_fingerprint, runtime_context_fingerprint(context))) {
      .data_provider_mapping_abort_v1("data_provider_mapping_preview_required")
    }
    catalog <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    mappings <- tryCatch(provider_mapping_read_v1(context), error = function(error) NULL)
    if (is.null(catalog) || is.null(mappings) ||
        !identical(catalog$catalog_fingerprint, stored$catalog_fingerprint) ||
        !identical(mappings$provider_mapping_fingerprint, stored$mapping_fingerprint)) {
      .data_provider_mapping_abort_v1("data_provider_mapping_catalog_changed")
    }
    stored$consumed <- TRUE
    assign(preview$preview_ref, stored, envir = editor$previews)
    result <- tryCatch(.provider_mapping_execute_v1(context, stored$command), error = function(error) NULL)
    if (is.null(result) || !result$status %in% c("committed", "already_committed")) {
      .data_provider_mapping_abort_v1("data_provider_mapping_command_failed")
    }
    list(
      contract_version = 1L, status = result$status, action = preview$action,
      verification_status = result$verification_status, enabled = result$enabled,
      provider_access = FALSE, network_access = FALSE, canonical_write = TRUE
    )
  })
}
