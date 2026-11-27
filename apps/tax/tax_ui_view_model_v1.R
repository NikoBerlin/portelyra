tax_ui_view_abort_v1 <- function(code) stop(code, call. = FALSE)
tax_ui_safe_text_v1 <- function(value, maximum = 160L) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) || nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) tax_ui_view_abort_v1("tax_ui_browser_model_invalid")
  value
}
tax_ui_public_payload_v1 <- function(value) {
  forbidden <- c("tenant_id", "user_id", "data_space_id", "actor_id", "database_path", "plugin_path", "entry_path", "rules_fingerprint", "manifest_fingerprint", "preview_fingerprint", "context_fingerprint", "internal_id", "sql", "secret")
  visit <- function(item) {
    if (!is.list(item)) return(invisible(TRUE))
    item_names <- names(item); if (!is.null(item_names) && any(item_names %in% forbidden)) tax_ui_view_abort_v1("tax_ui_browser_model_invalid")
    for (child in item) visit(child); invisible(TRUE)
  }
  visit(value); value
}
tax_ui_catalog_view_model_v1 <- function(payload) {
  tax_ui_public_payload_v1(payload)
  if (!is.list(payload) || !identical(payload$status, "completed") || !is.list(payload$catalog) || !is.list(payload$plugin_catalog) || !is.list(payload$definition_catalog)) tax_ui_view_abort_v1("tax_ui_catalog_invalid")
  portfolios <- lapply(payload$catalog$portfolios, function(row) list(ref = tax_ui_safe_text_v1(row$exchange_ref), label = tax_ui_safe_text_v1(row$display_name), status = row$status))
  assets <- lapply(payload$catalog$assets, function(row) list(ref = tax_ui_safe_text_v1(row$exchange_ref), label = tax_ui_safe_text_v1(row$display_name), asset_type = row$asset_type, status = row$status))
  plugins <- lapply(payload$plugin_catalog, function(row) list(plugin_id = row$plugin_id, plugin_version = row$plugin_version, jurisdiction_code = row$jurisdiction_code, model_scope = row$model_scope, supported_projection_modes = unlist(row$supported_projection_modes, use.names = FALSE), effective_from = row$effective_from, effective_to = row$effective_to, recommended = isTRUE(row$recommended), disclaimer_codes = unlist(row$disclaimer_codes, use.names = FALSE)))
  list(portfolios = portfolios, assets = assets, plugins = plugins, classification_definitions = payload$definition_catalog$classifications, parameter_definitions = payload$definition_catalog$parameters, browser_context_exposed = FALSE, filesystem_paths_exposed = FALSE, fingerprints_exposed = FALSE)
}
tax_ui_overview_view_model_v1 <- function(payload, catalog) {
  tax_ui_public_payload_v1(payload)
  # inherited_partial_exemption_assets: Fonds, die nur den Satz ihrer Typ-Vorgabe erben (#466).
  required <- c("contract_version", "portfolio_ref", "tax_year", "plugin_catalog", "selections", "classifications", "parameters", "readiness", "asset_type_classifications", "resolved_classification_count", "asset_classification_count",
                "inherited_partial_exemption_assets", "invalidations_pending", "module_values", "module_coverage", "module_updates", "assessment", "portfolio_counts", "disclaimer_codes", "provider_access", "calculation", "canonical_write", "browser_context_exposed", "filesystem_paths_exposed", "fingerprints_exposed", "internal_ids_exposed")
  if (!is.list(payload) || !setequal(names(payload), required) || !identical(payload$contract_version, "tax_ui_browser_model_v1") || !is.numeric(payload$tax_year) || payload$provider_access || payload$calculation || payload$canonical_write || payload$browser_context_exposed || payload$filesystem_paths_exposed || payload$fingerprints_exposed || payload$internal_ids_exposed) tax_ui_view_abort_v1("tax_ui_browser_model_invalid")
  asset_labels <- stats::setNames(vapply(catalog$assets, `[[`, character(1), "label"), vapply(catalog$assets, `[[`, character(1), "ref"))
  readiness <- lapply(payload$readiness, function(row) {
    status <- tax_ui_safe_text_v1(row$status); list(projection_mode = row$projection_mode, status = status, missing_assets = vapply(unlist(row$missing_asset_refs, use.names = FALSE), function(ref) if (ref %in% names(asset_labels)) asset_labels[[ref]] else ref, character(1)), missing_parameters = unlist(row$missing_parameter_codes, use.names = FALSE), tone = if (identical(status, "ready")) "positive" else if (identical(status, "stale")) "warning" else "negative")
  })
  selections <- lapply(payload$selections, function(row) list(projection_mode = row$projection_mode, plugin_id = row$plugin_id, plugin_version = row$plugin_version, effective_from = row$effective_from, status = row$status, revision_no = row$revision_no))
  classifications <- lapply(payload$classifications, function(row) list(asset = if (row$asset_ref %in% names(asset_labels)) asset_labels[[row$asset_ref]] else row$asset_ref, classification_code = row$classification_code, tax_bucket = row$tax_bucket, partial_exemption_rate = row$partial_exemption_rate_decimal, effective_years = if (is.null(row$effective_to_year)) paste0(row$effective_from_year, "–") else paste0(row$effective_from_year, "–", row$effective_to_year), status = row$status))
  parameters <- lapply(payload$parameters, function(row) list(tax_year = row$tax_year, parameter_code = row$parameter_code, currency = if (is.null(row$currency)) "—" else row$currency, value = if (identical(row$value_kind, "applicability")) row$applicability_value else if (identical(row$value_kind, "rate")) row$rate_decimal else row$amount_decimal, value_kind = row$value_kind, status = row$status))
  list(state = "completed", portfolio_ref = payload$portfolio_ref, tax_year = as.character(payload$tax_year), readiness = readiness, selections = selections, classifications = classifications, parameters = parameters, invalidations_pending = unlist(payload$invalidations_pending, use.names = FALSE), disclaimer = "Non-binding model projection only · no tax advice, tax return, filing evidence or automatic legal update.", provider_access = FALSE, calculation = FALSE, canonical_write = FALSE)
}
tax_ui_state_v1 <- function(kind = "empty", title = "Tax configuration not loaded", copy = "Initialize and read the server-bound Tax policy store explicitly.", code = NULL, view_model = NULL) list(kind = kind, title = title, copy = copy, code = code, view_model = view_model)
tax_ui_error_state_v1 <- function(code) { if (!is.character(code) || length(code) != 1L || !grepl("^[a-z][a-z0-9_]{2,80}$", code)) code <- "tax_ui_boundary_failed"; tax_ui_state_v1("error", "Tax configuration unavailable", paste("Safe failure code:", code), code) }
