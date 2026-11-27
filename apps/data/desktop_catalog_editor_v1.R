desktop_catalog_editor_error_codes_v1 <- function() c(
  "desktop_catalog_state_invalid", "desktop_catalog_context_invalid", "desktop_catalog_input_invalid",
  "desktop_catalog_catalog_unavailable", "desktop_catalog_preview_required",
  "desktop_catalog_confirmation_required", "desktop_catalog_confirmation_consumed",
  "desktop_catalog_catalog_changed", "desktop_catalog_command_failed", "desktop_catalog_boundary_failed",
  "desktop_catalog_isin_invalid", "desktop_catalog_isin_taken"
)
.desktop_catalog_abort_v1 <- function(code) {
  if (!code %in% desktop_catalog_editor_error_codes_v1()) stop("desktop_catalog_unregistered_error", call. = FALSE)
  condition <- structure(list(message = code, call = NULL, code = code), class = c("spot_desktop_catalog_error_v1", "error", "condition"))
  stop(condition)
}
.desktop_catalog_boundary_v1 <- function(expression) {
  result <- tryCatch(expression, spot_desktop_catalog_error_v1 = function(error) error, error = function(error) {
    structure(list(message = "desktop_catalog_boundary_failed", call = NULL, code = "desktop_catalog_boundary_failed"), class = c("spot_desktop_catalog_error_v1", "error", "condition"))
  })
  if (inherits(result, "spot_desktop_catalog_error_v1")) stop(result)
  result
}
.desktop_catalog_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .desktop_catalog_abort_v1("desktop_catalog_context_invalid")
  }
}
new_desktop_catalog_editor_v1 <- function() {
  editor <- new.env(hash = FALSE, parent = emptyenv())
  editor$catalog <- NULL; editor$previews <- new.env(hash = TRUE, parent = emptyenv())
  class(editor) <- "spot_desktop_catalog_editor_v1"; editor
}
.desktop_catalog_editor_valid_v1 <- function(editor) {
  if (!inherits(editor, "spot_desktop_catalog_editor_v1") || !is.environment(editor) || !is.environment(editor$previews)) {
    .desktop_catalog_abort_v1("desktop_catalog_state_invalid")
  }
}
.desktop_catalog_text_v1 <- function(value, optional = FALSE, maximum = 120L) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) || value != trimws(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  value
}
.desktop_catalog_ref_v1 <- function(kind, index) sprintf("%s_ref_%04d", kind, as.integer(index))

desktop_catalog_editor_refresh_v1 <- function(editor, context) {
  .desktop_catalog_boundary_v1({
    .desktop_catalog_editor_valid_v1(editor); .desktop_catalog_context_v1(context)
    catalog <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    if (is.null(catalog)) .desktop_catalog_abort_v1("desktop_catalog_catalog_unavailable")
    build <- function(rows, kind, fields) lapply(seq_along(rows), function(index) {
      row <- rows[[index]]
      c(list(ref = .desktop_catalog_ref_v1(kind, index)), row[fields])
    })
    public <- list(
      contract_version = 1L, status = "ready",
      portfolios = build(catalog$portfolios, "portfolio", c("display_name", "base_currency", "status")),
      accounts = build(catalog$accounts, "account", c("display_name", "account_type", "institution_label", "status")),
      assets = build(catalog$assets, "asset", c("display_name", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin", "status")),
      context_exposed = FALSE, internal_ids_exposed = FALSE, canonical_write = FALSE
    )
    editor$catalog <- list(
      context_fingerprint = runtime_context_fingerprint(context), catalog_fingerprint = catalog$catalog_fingerprint,
      maps = list(
        portfolio = stats::setNames(catalog$portfolios, vapply(seq_along(catalog$portfolios), function(index) .desktop_catalog_ref_v1("portfolio", index), character(1L))),
        account = stats::setNames(catalog$accounts, vapply(seq_along(catalog$accounts), function(index) .desktop_catalog_ref_v1("account", index), character(1L))),
        asset = stats::setNames(catalog$assets, vapply(seq_along(catalog$assets), function(index) .desktop_catalog_ref_v1("asset", index), character(1L)))
      ), public = public
    )
    public
  })
}
.desktop_catalog_state_v1 <- function(editor, context) {
  .desktop_catalog_editor_valid_v1(editor); .desktop_catalog_context_v1(context)
  if (is.null(editor$catalog) || !identical(editor$catalog$context_fingerprint, runtime_context_fingerprint(context))) {
    .desktop_catalog_abort_v1("desktop_catalog_catalog_unavailable")
  }
  editor$catalog
}

desktop_catalog_editor_internal_identity_v1 <- function(editor, context, entity_type, public_ref) {
  catalog <- .desktop_catalog_state_v1(editor, context)
  if (!is.character(entity_type) || length(entity_type) != 1L || is.na(entity_type) ||
      !entity_type %in% c("asset", "account") || !is.character(public_ref) ||
      length(public_ref) != 1L || is.na(public_ref) || !nzchar(public_ref)) {
    .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  }
  row <- catalog$maps[[entity_type]][[public_ref]]
  field <- paste0(entity_type, "_id")
  value <- if (is.null(row)) NULL else row[[field]]
  if (is.null(value) || !is.character(value) || length(value) != 1L || !nzchar(value)) {
    .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  }
  value
}
.desktop_catalog_prepare_command_v1 <- function(context, catalog, form, prepared_at_utc) {
  fields <- c("action", "entity_type", "entity_ref", "portfolio_ref", "display_name", "base_currency", "account_type", "institution_label", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin")
  if (!is.list(form) || !identical(names(form), fields) || !.desktop_product_utc_valid_v1(prepared_at_utc)) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  action <- .desktop_catalog_text_v1(form$action, maximum = 30L); entity_type <- .desktop_catalog_text_v1(form$entity_type, maximum = 10L)
  if (!action %in% c("create", "update", "archive", "revise_price_currency", "revise_valuation_method", "set_isin", "revise_asset_type") ||
      !entity_type %in% c("portfolio", "account", "asset") ||
      (action %in% c("revise_price_currency", "revise_valuation_method", "set_isin", "revise_asset_type") && !identical(entity_type, "asset"))) {
    .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  }
  token <- .desktop_product_random_id_v1("tok_cat_")
  selected <- NULL
  if (action != "create") {
    ref <- .desktop_catalog_text_v1(form$entity_ref, maximum = 40L); selected <- catalog$maps[[entity_type]][[ref]]
    if (is.null(selected) || identical(selected$status, "archived")) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
  }
  display <- if (action %in% c("archive", "revise_price_currency", "revise_valuation_method", "set_isin", "revise_asset_type")) NULL else .desktop_catalog_text_v1(form$display_name)
  command <- if (entity_type == "portfolio") {
    if (action == "create") {
      currency <- .desktop_catalog_text_v1(form$base_currency, maximum = 3L)
      if (!grepl("^[A-Z]{3}$", currency)) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      .catalog_build_create_portfolio_v1(context, token, display, currency, prepared_at_utc)
    } else if (action == "update") .catalog_build_update_portfolio_v1(context, token, selected$portfolio_id, selected$revision, display, prepared_at_utc)
    else .catalog_build_archive_portfolio_v1(context, token, selected$portfolio_id, selected$revision, prepared_at_utc)
  } else if (entity_type == "account") {
    if (action == "create") {
      portfolio_ref <- .desktop_catalog_text_v1(form$portfolio_ref, maximum = 40L); portfolio <- catalog$maps$portfolio[[portfolio_ref]]
      account_type <- .desktop_catalog_text_v1(form$account_type, maximum = 30L)
      if (is.null(portfolio) || portfolio$status != "active" || !account_type %in% c("securities", "cash", "bank", "crypto_wallet", "external", "other")) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      .catalog_build_create_account_v1(context, token, portfolio$portfolio_id, display, account_type, .desktop_catalog_text_v1(form$institution_label, optional = TRUE), prepared_at_utc)
    } else if (action == "update") .catalog_build_update_account_v1(context, token, selected$account_id, selected$revision, display, .desktop_catalog_text_v1(form$institution_label, optional = TRUE), prepared_at_utc)
    else .catalog_build_archive_account_v1(context, token, selected$account_id, selected$revision, prepared_at_utc)
  } else {
    if (action == "create") {
      asset_type <- .desktop_catalog_text_v1(form$asset_type, maximum = 20L); currency <- .desktop_catalog_text_v1(form$price_currency, maximum = 3L)
      scale <- suppressWarnings(as.integer(form$quantity_scale)); method <- .desktop_catalog_text_v1(form$valuation_method, maximum = 30L)
      if (!asset_type %in% c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "cash", "fx", "index", "other") ||
          !grepl("^[A-Z]{3}$", currency) || length(scale) != 1L || is.na(scale) || scale < 0L || scale > 24L ||
          !method %in% c("external_market", "manual", "unit_value", "transaction_only") ||
          (identical(asset_type, "cash") && !identical(method, "unit_value"))) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      .catalog_build_create_asset_v1(context, token, display, asset_type, currency, as.integer(scale), method, .desktop_catalog_text_v1(form$isin, optional = TRUE, maximum = 12L), prepared_at_utc)
    } else if (action == "update") {
      .catalog_build_update_asset_v1(context, token, selected$asset_id, selected$revision, display, .desktop_catalog_text_v1(form$isin, optional = TRUE, maximum = 12L), prepared_at_utc)
    } else if (action == "set_isin") {
      isin <- .desktop_catalog_text_v1(form$isin, maximum = 12L)
      # Beide Gruende weist der Kern ohnehin ab - hier vorab, damit die Data-App sie benennen kann statt
      # "Aktion blockiert" mit Sammelcode (etwa dasselbe Papier in zwei Depots).
      if (!.catalog_isin_checksum_valid(isin)) .desktop_catalog_abort_v1("desktop_catalog_isin_invalid")
      if (any(vapply(catalog$maps$asset, function(row) identical(row$isin, isin) && !identical(row$asset_id, selected$asset_id), logical(1L))))
        .desktop_catalog_abort_v1("desktop_catalog_isin_taken")
      .catalog_build_set_asset_isin_v1(context, token, selected$asset_id, selected$revision, isin, prepared_at_utc)
    } else if (action == "revise_valuation_method") {
      method <- .desktop_catalog_text_v1(form$valuation_method, maximum = 30L)
      if (identical(method, selected$valuation_method) ||
          (identical(selected$asset_type, "cash") && !identical(method, "unit_value"))) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      .catalog_build_revise_asset_valuation_method_v1(context, token, selected$asset_id, selected$revision, method, prepared_at_utc)
    } else if (action == "revise_asset_type") {
      # Nur zwischen ETF und Fonds (#447: beides ein Investmentfonds); jeder andere Typwechsel bleibt gesperrt.
      asset_type <- .desktop_catalog_text_v1(form$asset_type, maximum = 20L)
      if (!asset_type %in% c("etf", "fund") || !selected$asset_type %in% c("etf", "fund") || identical(asset_type, selected$asset_type))
        .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      .catalog_build_revise_asset_type_v1(context, token, selected$asset_id, selected$revision, asset_type, prepared_at_utc)
    } else if (action == "revise_price_currency") {
      currency <- .desktop_catalog_text_v1(form$price_currency, maximum = 3L)
      if (!grepl("^[A-Z]{3}$", currency) || identical(currency, selected$price_currency)) {
        .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
      }
      .catalog_build_revise_asset_price_currency_v1(
        context, token, selected$asset_id, selected$revision, currency, prepared_at_utc
      )
    } else {
      .catalog_build_archive_asset_v1(context, token, selected$asset_id, selected$revision, prepared_at_utc)
    }
  }
  list(
    command = command, action = action, entity_type = entity_type,
    display_name = if (is.null(display)) selected$display_name else display,
    current_price_currency = if (identical(action, "revise_price_currency")) selected$price_currency else NULL,
    proposed_price_currency = if (identical(action, "revise_price_currency")) command$fields$price_currency else NULL,
    current_asset_type = if (identical(action, "revise_asset_type")) selected$asset_type else NULL,
    proposed_asset_type = if (identical(action, "revise_asset_type")) command$fields$asset_type else NULL
  )
}

desktop_catalog_editor_prepare_v1 <- function(editor, context, form, prepared_at_utc) {
  .desktop_catalog_boundary_v1({
    catalog <- .desktop_catalog_state_v1(editor, context)
    prepared <- .desktop_catalog_prepare_command_v1(context, catalog, form, prepared_at_utc)
    preview_ref <- paste0("catp_", substr(.catalog_fingerprint(list(command = prepared$command, catalog = catalog$catalog_fingerprint)), 1L, 32L))
    public <- list(
      contract_version = 1L, status = "pending_confirmation", preview_ref = preview_ref,
      action = prepared$action, entity_type = prepared$entity_type, display_name = prepared$display_name,
      current_price_currency = prepared$current_price_currency,
      proposed_price_currency = prepared$proposed_price_currency,
      confirmation_required = TRUE, canonical_write = FALSE, context_exposed = FALSE,
      internal_ids_exposed = FALSE, paths_exposed = FALSE
    )
    if (identical(prepared$action, "revise_asset_type")) {
      public$current_asset_type <- prepared$current_asset_type
      public$proposed_asset_type <- prepared$proposed_asset_type
    }
    if (identical(prepared$action, 'revise_valuation_method')) {
      public$current_valuation_method <- catalog$maps$asset[[form$entity_ref]]$valuation_method
      public$proposed_valuation_method <- prepared$command$fields$valuation_method
    }
    assign(preview_ref, list(
      consumed = FALSE, context_fingerprint = runtime_context_fingerprint(context),
      catalog_fingerprint = catalog$catalog_fingerprint, command = prepared$command, public = public
    ), envir = editor$previews)
    public
  })
}

desktop_catalog_editor_execute_v1 <- function(editor, context, preview, confirmed) {
  .desktop_catalog_boundary_v1({
    .desktop_catalog_editor_valid_v1(editor); .desktop_catalog_context_v1(context)
    if (!isTRUE(confirmed)) .desktop_catalog_abort_v1("desktop_catalog_confirmation_required")
    if (!is.list(preview) || !is.character(preview$preview_ref) || length(preview$preview_ref) != 1L ||
        !exists(preview$preview_ref, envir = editor$previews, inherits = FALSE)) .desktop_catalog_abort_v1("desktop_catalog_preview_required")
    state <- get(preview$preview_ref, envir = editor$previews, inherits = FALSE)
    if (isTRUE(state$consumed)) .desktop_catalog_abort_v1("desktop_catalog_confirmation_consumed")
    if (!identical(state$public, preview) || !identical(state$context_fingerprint, runtime_context_fingerprint(context))) .desktop_catalog_abort_v1("desktop_catalog_preview_required")
    current <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    if (is.null(current) || !identical(current$catalog_fingerprint, state$catalog_fingerprint)) .desktop_catalog_abort_v1("desktop_catalog_catalog_changed")
    state$consumed <- TRUE; assign(preview$preview_ref, state, envir = editor$previews)
    result <- tryCatch(.catalog_execute_public(context, state$command), error = function(error) NULL)
    if (is.null(result) || !result$status %in% c("committed", "already_committed")) .desktop_catalog_abort_v1("desktop_catalog_command_failed")
    list(contract_version = 1L, status = result$status, action = preview$action, entity_type = preview$entity_type, canonical_write = TRUE)
  })
}

# Resolves the public ref of the entity a preview targets. A create command
# carries its deterministic entity id, so the new row is found after refresh
# without matching on display names.
desktop_catalog_editor_preview_target_ref_v1 <- function(editor, context, preview) {
  .desktop_catalog_boundary_v1({
    catalog <- .desktop_catalog_state_v1(editor, context)
    if (!is.list(preview) || !is.character(preview$preview_ref) || length(preview$preview_ref) != 1L ||
        !exists(preview$preview_ref, envir = editor$previews, inherits = FALSE)) .desktop_catalog_abort_v1("desktop_catalog_preview_required")
    command <- get(preview$preview_ref, envir = editor$previews, inherits = FALSE)$command
    if (!command$entity_type %in% c("portfolio", "account", "asset")) .desktop_catalog_abort_v1("desktop_catalog_input_invalid")
    field <- paste0(command$entity_type, "_id")
    matched <- names(Filter(function(row) identical(row[[field]], command$entity_id), catalog$maps[[command$entity_type]]))
    if (length(matched) != 1L) .desktop_catalog_abort_v1("desktop_catalog_catalog_unavailable")
    matched[[1L]]
  })
}
