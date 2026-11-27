desktop_run_center_error_codes_v1 <- function() {
  c(
    "desktop_run_center_state_invalid", "desktop_run_center_context_invalid",
    "desktop_run_center_catalog_unavailable", "desktop_run_center_input_invalid",
    "desktop_run_center_preview_invalid", "desktop_run_center_confirmation_invalid",
    "desktop_run_center_confirmation_expired", "desktop_run_center_confirmation_consumed",
    "desktop_run_center_catalog_changed", "desktop_run_center_market_valuation_changed", "desktop_run_center_job_conflict",
    "desktop_run_center_no_resumable_job", "desktop_run_center_worker_unavailable",
    "desktop_run_center_last_run_unreadable", "desktop_run_center_boundary_failed"
  )
}

.desktop_run_center_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !code %in% desktop_run_center_error_codes_v1()) {
    stop("unregistered_desktop_run_center_error_code", call. = FALSE)
  }
  structure(list(message = code, call = NULL, code = code), class = c("spot_desktop_run_center_error_v1", "error", "condition"))
}
.desktop_run_center_abort_v1 <- function(code) stop(.desktop_run_center_condition_v1(code))
.desktop_run_center_boundary_v1 <- function(expression) {
  result <- tryCatch(expression, spot_desktop_run_center_error_v1 = function(error) error, error = function(error) .desktop_run_center_condition_v1("desktop_run_center_boundary_failed"))
  if (inherits(result, "spot_desktop_run_center_error_v1")) stop(result)
  result
}
.desktop_run_center_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .desktop_run_center_abort_v1("desktop_run_center_context_invalid")
  }
  invisible(TRUE)
}
.desktop_run_center_check_v1 <- function(center) {
  if (!inherits(center, "spot_desktop_run_center_v1") || !is.environment(center) ||
      !is.environment(center$previews) || !is.environment(center$confirmations)) {
    .desktop_run_center_abort_v1("desktop_run_center_state_invalid")
  }
  invisible(TRUE)
}
new_desktop_run_center_v1 <- function() {
  center <- new.env(hash = FALSE, parent = emptyenv())
  center$catalog <- NULL; center$previews <- new.env(hash = TRUE, parent = emptyenv())
  center$confirmations <- new.env(hash = TRUE, parent = emptyenv())
  class(center) <- "spot_desktop_run_center_v1"; center
}
.desktop_run_center_utc_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value) &&
    !is.na(suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")))
}
.desktop_run_center_date_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value) &&
    !is.na(suppressWarnings(as.Date(value, format = "%Y-%m-%d")))
}
.desktop_run_center_text_v1 <- function(value, optional = FALSE, maximum = 160L) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) || value != trimws(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  value
}
.desktop_run_center_currency_v1 <- function(value, optional = FALSE) {
  value <- .desktop_run_center_text_v1(value, optional = optional, maximum = 3L)
  if (!is.null(value) && !grepl("^[A-Z]{3}$", value)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  value
}
.desktop_run_center_decimal_v1 <- function(value, optional = FALSE, positive = FALSE, nonnegative = FALSE) {
  value <- .desktop_run_center_text_v1(value, optional = optional, maximum = 80L)
  if (is.null(value)) return(NULL)
  if (!grepl("^-?(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value) || identical(value, "-0")) {
    .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  }
  parsed <- tryCatch(.transaction_decimal_parse(value, allow_zero = !positive, positive_only = positive), error = function(error) NULL)
  if (is.null(parsed) || (nonnegative && startsWith(value, "-"))) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  value
}
.desktop_run_center_ref_v1 <- function(prefix, index) sprintf("%s%04d", prefix, as.integer(index))

desktop_run_center_catalog_v1 <- function(center, context) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
    catalog <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    if (is.null(catalog) || !length(catalog$portfolios)) .desktop_run_center_abort_v1("desktop_run_center_catalog_unavailable")
    portfolio_refs <- vapply(seq_along(catalog$portfolios), function(index) .desktop_run_center_ref_v1("portfolio_ref_", index), character(1L))
    asset_refs <- vapply(seq_along(catalog$assets), function(index) .desktop_run_center_ref_v1("asset_ref_", index), character(1L))
    portfolios <- lapply(seq_along(catalog$portfolios), function(index) {
      row <- catalog$portfolios[[index]]
      list(ref = portfolio_refs[[index]], label = row$display_name, base_currency = row$base_currency, status = row$status)
    })
    assets <- lapply(seq_along(catalog$assets), function(index) {
      row <- catalog$assets[[index]]
      list(ref = asset_refs[[index]], label = row$display_name, asset_type = row$asset_type, price_currency = row$price_currency, status = row$status)
    })
    center$catalog <- list(
      context_fingerprint = runtime_context_fingerprint(context), catalog_fingerprint = catalog$catalog_fingerprint,
      portfolio_by_ref = setNames(catalog$portfolios, portfolio_refs), asset_by_ref = setNames(catalog$assets, asset_refs),
      public = list(contract_version = 1L, status = "ready", portfolios = portfolios, assets = assets,
                    tax_classifications = c("not_configured", "de_equity_share", "de_capital_instrument", "de_cash_interest", "de_fund", "de_private_disposal_asset", "de_other_income_asset"),
                    run_modes = c("full", "incremental"), grouping_modes = "none", canonical_ids_exposed = FALSE)
    )
    center$catalog$public
  })
}
.desktop_run_center_catalog_state_v1 <- function(center, context) {
  .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
  if (is.null(center$catalog) || !identical(center$catalog$context_fingerprint, runtime_context_fingerprint(context))) {
    .desktop_run_center_abort_v1("desktop_run_center_catalog_unavailable")
  }
  center$catalog
}
.desktop_run_center_form_v1 <- function(value) {
  names_expected <- c("portfolio_ref", "run_mode", "as_of_date", "cutoff_at_utc", "tax_mode", "capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_applicable", "church_tax_rate", "fee_source", "fee_fixed_decimal", "fee_percentage_rate_decimal", "asset_inputs", "grouping_mode")
  if (!is.list(value) || !identical(names(value), names_expected)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  value
}
.desktop_run_center_asset_input_v1 <- function(value, catalog, base_currency) {
  fields <- c("asset_ref", "listing_code", "market_currency", "close_decimal", "observed_at_utc", "tax_classification", "partial_exemption_rate_decimal", "fixed_fee_decimal", "percentage_fee_rate_decimal", "fx_base_currency", "fx_quote_currency", "fx_direction", "fx_rate_decimal", "fx_observed_at_utc")
  if (!is.list(value) || !identical(names(value), fields)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  ref <- .desktop_run_center_text_v1(value$asset_ref, maximum = 40L); asset <- catalog$asset_by_ref[[ref]]
  if (is.null(asset) || identical(asset$asset_type, "cash")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  listing <- .desktop_run_center_text_v1(value$listing_code, optional = TRUE, maximum = 80L)
  currency <- .desktop_run_center_currency_v1(value$market_currency, optional = TRUE)
  close <- .desktop_run_center_decimal_v1(value$close_decimal, optional = TRUE, positive = TRUE)
  observed <- .desktop_run_center_text_v1(value$observed_at_utc, optional = TRUE, maximum = 20L)
  if (!is.null(observed) && !.desktop_run_center_utc_v1(observed)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  if (!is.null(close) && (is.null(listing) || is.null(currency) || is.null(observed))) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  classification <- .desktop_run_center_text_v1(value$tax_classification, maximum = 60L)
  allowed <- c("not_configured", "de_equity_share", "de_capital_instrument", "de_cash_interest", "de_fund", "de_private_disposal_asset", "de_other_income_asset")
  if (!classification %in% allowed) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  partial <- .desktop_run_center_decimal_v1(value$partial_exemption_rate_decimal, optional = TRUE, nonnegative = TRUE)
  fixed <- .desktop_run_center_decimal_v1(value$fixed_fee_decimal, optional = TRUE, nonnegative = TRUE)
  percentage <- .desktop_run_center_decimal_v1(value$percentage_fee_rate_decimal, optional = TRUE, nonnegative = TRUE)
  direction <- .desktop_run_center_text_v1(value$fx_direction, maximum = 10L)
  if (!direction %in% c("none", "direct", "inverse")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  fx_base <- .desktop_run_center_currency_v1(value$fx_base_currency, optional = TRUE); fx_quote <- .desktop_run_center_currency_v1(value$fx_quote_currency, optional = TRUE)
  fx_rate <- .desktop_run_center_decimal_v1(value$fx_rate_decimal, optional = TRUE, positive = TRUE)
  fx_observed <- .desktop_run_center_text_v1(value$fx_observed_at_utc, optional = TRUE, maximum = 20L)
  if (!is.null(fx_observed) && !.desktop_run_center_utc_v1(fx_observed)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  if (direction != "none" && (is.null(fx_base) || is.null(fx_quote) || is.null(fx_rate) || is.null(fx_observed))) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  if (direction == "direct" && !identical(c(fx_base, fx_quote), c(currency, base_currency)) ||
      direction == "inverse" && !identical(c(fx_base, fx_quote), c(base_currency, currency))) {
    .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
  }
  list(
    asset_id = asset$asset_id, display_name = asset$display_name, asset_type = asset$asset_type,
    listing_code = listing, market_currency = currency, close_decimal = close, observed_at_utc = observed,
    tax_classification = classification, partial_exemption_rate_decimal = partial,
    fixed_fee_decimal = fixed, percentage_fee_rate_decimal = percentage,
    fx_base_currency = fx_base, fx_quote_currency = fx_quote, fx_direction = direction,
    fx_rate_decimal = fx_rate, fx_observed_at_utc = fx_observed
  )
}

.desktop_run_center_market_check_v1 <- function(context, project_root, binding) {
  if (is.null(binding)) return(invisible(NULL))
  if (!is.character(project_root) || length(project_root)!=1L) .desktop_run_center_abort_v1("desktop_run_center_market_valuation_changed")
  cli<-file.path(project_root,"scripts","desktop_market_valuation.py")
  mask<-Sys.umask("0077");errors<-tempfile("run-market-stderr-")
  on.exit({Sys.umask(mask);unlink(errors)},add=TRUE)
  payload<-list(context=list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id),
    data_space_path=runtime_data_space_path(context),payload=list(preview_ref=binding$preview_ref,as_of_date=binding$as_of_date))
  text<-suppressWarnings(system2(Sys.which("python3"),c("-B","-E","-s",shQuote(cli),"portfolio-input"),stdout=TRUE,stderr=errors,
    input=as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,null="null",digits=NA))))
  result<-tryCatch(if(length(text)==1L)jsonlite::fromJSON(text,simplifyVector=FALSE)else NULL,error=function(e)NULL)
  if (!is.null(attr(text,"status")) || !is.list(result) || !identical(result$status,"completed") ||
      (file.exists(errors)&&length(readLines(errors,warn=FALSE))) ||
      !identical(.catalog_sort_json_value(result$value$binding),.catalog_sort_json_value(binding)))
    .desktop_run_center_abort_v1("desktop_run_center_market_valuation_changed")
  invisible(NULL)
}

desktop_run_center_prepare_v1 <- function(center, context, form, prepared_at_utc, data_space_label, semantic_ledger_binding = NULL, market_valuation_binding = NULL) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
    catalog <- .desktop_run_center_catalog_state_v1(center, context); form <- .desktop_run_center_form_v1(form)
    if (!.desktop_run_center_utc_v1(prepared_at_utc) || !.desktop_run_center_date_v1(form$as_of_date) || !.desktop_run_center_utc_v1(form$cutoff_at_utc)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    portfolio <- catalog$portfolio_by_ref[[.desktop_run_center_text_v1(form$portfolio_ref, maximum = 40L)]]
    if (is.null(portfolio) || !identical(portfolio$status, "active")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    run_mode <- .desktop_run_center_text_v1(form$run_mode, maximum = 20L); if (!run_mode %in% c("full", "incremental")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    tax_mode <- .desktop_run_center_text_v1(form$tax_mode, maximum = 30L); if (!tax_mode %in% c("disabled", "de_reference_v1", "de_reference_v2")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    rates <- lapply(form[c("capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_rate")], .desktop_run_center_decimal_v1, optional = TRUE, nonnegative = TRUE)
    church_tax_applicable <- .desktop_run_center_text_v1(form$church_tax_applicable, optional = TRUE, maximum = 20L)
    church_tax_selection_valid <- if (identical(tax_mode, "de_reference_v2")) {
      !is.null(church_tax_applicable) && church_tax_applicable %in% c("applicable", "not_applicable") &&
        (identical(church_tax_applicable, "applicable") == !is.null(rates$church_tax_rate))
    } else is.null(church_tax_applicable) && is.null(rates$church_tax_rate)
    if (!church_tax_selection_valid) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    # Die Liquidationsgebuehr je Asset zu tippen ist bei vielen Assets kein Weg. Der
    # Lauf waehlt deshalb eine Quelle fuer alle: ein fester Betrag je Trade, ein
    # fester Prozentsatz vom Umsatz, oder der aus den bisherigen Transaktionen
    # abgeleitete Satz (Vorgabe). Eine Asset-Karte darf das ueberschreiben, wie
    # bei der Steuer (Festlegung 28.09.2026, #367).
    fee_source <- .desktop_run_center_text_v1(form$fee_source, maximum = 40L)
    if (!fee_source %in% c("derived_from_transactions", "fixed_per_trade", "percentage_of_turnover")) {
      .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    }
    fee_fixed <- .desktop_run_center_decimal_v1(form$fee_fixed_decimal, optional = TRUE, nonnegative = TRUE)
    fee_percentage <- .desktop_run_center_decimal_v1(form$fee_percentage_rate_decimal, optional = TRUE, nonnegative = TRUE)
    fee_selection_valid <- switch(fee_source,
      fixed_per_trade = !is.null(fee_fixed) && is.null(fee_percentage),
      percentage_of_turnover = is.null(fee_fixed) && !is.null(fee_percentage),
      derived_from_transactions = is.null(fee_fixed) && is.null(fee_percentage))
    if (!fee_selection_valid) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    grouping <- .desktop_run_center_text_v1(form$grouping_mode, maximum = 20L); if (!identical(grouping, "none")) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    noncash <- names(catalog$asset_by_ref)[vapply(catalog$asset_by_ref, function(row) !identical(row$asset_type, "cash") && identical(row$status, "active"), logical(1L))]
    if (!is.list(form$asset_inputs) || length(form$asset_inputs) != length(noncash) || anyDuplicated(vapply(form$asset_inputs, `[[`, character(1L), "asset_ref")) || !setequal(vapply(form$asset_inputs, `[[`, character(1L), "asset_ref"), noncash)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    asset_inputs <- lapply(form$asset_inputs, .desktop_run_center_asset_input_v1, catalog = catalog, base_currency = portfolio$base_currency)
    canonical_path <- runtime_canonical_path(context)
    canonical_fingerprint <- digest::digest(file = canonical_path, algo = "sha256", serialize = FALSE)
    semantic_ledger <- list(
      status = "absent", ledger_path = NULL, ledger_fingerprint = NULL,
      canonical_fingerprint = canonical_fingerprint, semantic_contracts = list("portfolio_ledger_v1_transaction_fact")
    )
    if (!is.null(semantic_ledger_binding)) {
      expected_names <- c("status", "ledger_path", "ledger_fingerprint", "canonical_fingerprint", "semantic_contracts")
      if (!is.list(semantic_ledger_binding) || !identical(names(semantic_ledger_binding), expected_names) ||
          !identical(semantic_ledger_binding$status, "available") || !is.character(semantic_ledger_binding$ledger_path) ||
          length(semantic_ledger_binding$ledger_path) != 1L || !startsWith(semantic_ledger_binding$ledger_path, "/") ||
          !file.exists(semantic_ledger_binding$ledger_path) || nzchar(Sys.readlink(semantic_ledger_binding$ledger_path)) ||
          !.desktop_product_owner_mode_v1(semantic_ledger_binding$ledger_path) || as.integer(file.info(semantic_ledger_binding$ledger_path)$mode) != 384L ||
          !identical(normalizePath(semantic_ledger_binding$ledger_path, winslash = "/", mustWork = TRUE), semantic_ledger_binding$ledger_path) ||
          !startsWith(semantic_ledger_binding$ledger_path, paste0(runtime_data_space_path(context), "/asset-activity-ledger-v1/generations/")) ||
          !is.character(semantic_ledger_binding$ledger_fingerprint) || !grepl("^[a-f0-9]{64}$", semantic_ledger_binding$ledger_fingerprint) ||
          !identical(digest::digest(file = semantic_ledger_binding$ledger_path, algo = "sha256", serialize = FALSE), semantic_ledger_binding$ledger_fingerprint) ||
          !identical(semantic_ledger_binding$canonical_fingerprint, canonical_fingerprint) ||
          !identical(unlist(semantic_ledger_binding$semantic_contracts, use.names = FALSE), c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1"))) {
        .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
      }
      semantic_ledger <- semantic_ledger_binding
    }
    payload_seed <- list(
      runtime = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, data_root = context$data_root, canonical_path = canonical_path, ledger_path = semantic_ledger$ledger_path, ledger_schema_version = if (identical(semantic_ledger$status, "available")) 401L else 201L, ledger_fingerprint = semantic_ledger$ledger_fingerprint, semantic_contracts = semantic_ledger$semantic_contracts),
      portfolio = list(portfolio_id = portfolio$portfolio_id, display_name = portfolio$display_name, base_currency = portfolio$base_currency),
      data_space_label = .desktop_run_center_text_v1(data_space_label, maximum = 100L), run_mode = run_mode,
      as_of_date = form$as_of_date, cutoff_at_utc = form$cutoff_at_utc, prepared_at_utc = prepared_at_utc,
      tax_policy = c(list(mode = tax_mode), rates[c("capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate")], list(church_tax_applicable = church_tax_applicable, church_tax_rate = rates$church_tax_rate)), asset_inputs = asset_inputs,
      fee_policy = list(source = fee_source, fixed_decimal = fee_fixed, percentage_rate_decimal = fee_percentage),
      grouping_policy = list(mode = grouping), catalog_fingerprint = catalog$catalog_fingerprint,
      canonical_fingerprint = canonical_fingerprint
    )
    if (!is.null(market_valuation_binding)) {
      fields<-c("preview_ref","valuation_fingerprint","receipt_fingerprint","as_of_date","bridge_fingerprint")
      if (!is.list(market_valuation_binding) || !setequal(names(market_valuation_binding),fields) ||
          !all(vapply(market_valuation_binding,function(v)is.character(v)&&length(v)==1L&&!is.na(v),logical(1L))) ||
          !grepl("^mvp_[a-f0-9]{32}$",market_valuation_binding$preview_ref) ||
          !all(vapply(market_valuation_binding[c("valuation_fingerprint","receipt_fingerprint","bridge_fingerprint")],function(v)grepl("^[a-f0-9]{64}$",v),logical(1L))) ||
          !identical(portfolio$base_currency,"EUR") || !identical(market_valuation_binding$as_of_date,form$as_of_date) ||
          !identical(form$cutoff_at_utc,paste0(form$as_of_date,"T23:59:59Z")) ||
          any(vapply(asset_inputs,function(v)!is.null(v$close_decimal)||!is.null(v$fx_rate_decimal)||v$fx_direction!="none",logical(1L))))
        .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
      payload_seed$market_valuation_binding<-market_valuation_binding
    }
    run_id <- paste0("run_drw_", substr(.catalog_fingerprint(payload_seed), 1L, 32L))
    plan <- c(list(contract_version = 1L, run_id = run_id), payload_seed)
    preview_ref <- paste0("drp_", substr(.catalog_fingerprint(list(plan = plan, context = runtime_context_fingerprint(context))), 1L, 32L))
    public_assets <- lapply(asset_inputs, function(row) row[c("display_name", "asset_type", "listing_code", "market_currency", "close_decimal", "observed_at_utc", "tax_classification", "partial_exemption_rate_decimal", "fixed_fee_decimal", "percentage_fee_rate_decimal", "fx_base_currency", "fx_quote_currency", "fx_direction", "fx_rate_decimal", "fx_observed_at_utc")])
    public <- list(
      contract_version = 1L, status = "pending_confirmation", preview_ref = preview_ref,
      portfolio_label = portfolio$display_name, reporting_currency = portfolio$base_currency,
      data_space_label = payload_seed$data_space_label, run_mode = run_mode, as_of_date = form$as_of_date,
      cutoff_at_utc = form$cutoff_at_utc, tax_mode = tax_mode, grouping_mode = grouping,
      fee_source = fee_source, fee_fixed_decimal = fee_fixed, fee_percentage_rate_decimal = fee_percentage,
      asset_inputs = public_assets,
      stages = c("canonical", "fifo", "tax", "grouping", "market", "fx", "valuation", "trade_analysis", "market_analysis", "publication"),
      semantic_ledger_status = if (identical(semantic_ledger$status, "available")) "schema_401" else "schema_201_projection",
      confirmation_required = TRUE, canonical_write = FALSE, provider_access = FALSE, network_access = FALSE,
      context_exposed = FALSE, internal_ids_exposed = FALSE, paths_exposed = FALSE
    )
    if (!is.null(market_valuation_binding)) public$market_snapshot_source<-list(kind="completed_valuation_projection",as_of_date=form$as_of_date,portfolio_completion=FALSE)
    assign(preview_ref, list(consumed = FALSE, context_fingerprint = runtime_context_fingerprint(context), catalog_fingerprint = catalog$catalog_fingerprint, plan = plan, public = public), envir = center$previews)
    public
  })
}

desktop_run_center_build_confirmation_v1 <- function(center, context, preview, issued_at_utc, expires_at_utc, project_root = NULL) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
    if (!is.list(preview) || is.null(preview$preview_ref) || !exists(preview$preview_ref, envir = center$previews, inherits = FALSE) ||
        !.desktop_run_center_utc_v1(issued_at_utc) || !.desktop_run_center_utc_v1(expires_at_utc)) .desktop_run_center_abort_v1("desktop_run_center_preview_invalid")
    state <- get(preview$preview_ref, envir = center$previews, inherits = FALSE)
    if (!identical(state$public, preview) || !identical(state$context_fingerprint, runtime_context_fingerprint(context))) .desktop_run_center_abort_v1("desktop_run_center_preview_invalid")
    issued <- as.POSIXct(issued_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"); expires <- as.POSIXct(expires_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    if (is.na(issued) || is.na(expires) || expires <= issued || as.numeric(difftime(expires, issued, units = "secs")) > 600) .desktop_run_center_abort_v1("desktop_run_center_confirmation_invalid")
    .desktop_run_center_market_check_v1(context,project_root,state$plan$market_valuation_binding)
    challenge <- paste0("drc_", substr(.catalog_fingerprint(list(preview_ref = preview$preview_ref, issued = issued_at_utc, expires = expires_at_utc, plan = state$plan)), 1L, 32L))
    assign(challenge, list(consumed = FALSE, preview_ref = preview$preview_ref, issued_at_utc = issued_at_utc, expires_at_utc = expires_at_utc, context_fingerprint = state$context_fingerprint), envir = center$confirmations)
    list(contract_version = 1L, challenge_ref = challenge, preview_ref = preview$preview_ref, issued_at_utc = issued_at_utc, expires_at_utc = expires_at_utc, decision = "confirm_once")
  })
}
.desktop_run_center_job_root_v1 <- function(context) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  root <- file.path(runtime_data_space_path(context), "run-center")
  if (!dir.exists(root) && !dir.create(root, recursive = TRUE, mode = "0700")) .desktop_run_center_abort_v1("desktop_run_center_job_conflict")
  Sys.chmod(root, "0700"); jobs <- file.path(root, "jobs")
  if (!dir.exists(jobs) && !dir.create(jobs, mode = "0700")) .desktop_run_center_abort_v1("desktop_run_center_job_conflict")
  Sys.chmod(jobs, "0700"); jobs
}
.desktop_run_center_existing_jobs_v1 <- function(context) {
  root <- file.path(runtime_data_space_path(context), "run-center", "jobs")
  if (!dir.exists(root)) return(NULL)
  if (.desktop_product_symlink_v1(root) || !.desktop_product_owner_mode_v1(root, directory = TRUE)) {
    .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
  }
  normalizePath(root, winslash = "/", mustWork = TRUE)
}
.desktop_run_center_worker_v1 <- function(project_root, job_path) {
  script <- file.path(project_root, "scripts", "desktop_workflow.py")
  python <- Sys.which("python3")
  if (!nzchar(python) || !file.exists(script) || nzchar(Sys.readlink(script))) .desktop_run_center_abort_v1("desktop_run_center_worker_unavailable")
  output <- suppressWarnings(system2(python, c(shQuote(script), "--job", shQuote(job_path)), stdout = TRUE, stderr = TRUE))
  if (length(output) != 1L) .desktop_run_center_abort_v1("desktop_run_center_worker_unavailable")
  result <- tryCatch(jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(result) || !result$status %in% c("completed", "blocked")) .desktop_run_center_abort_v1("desktop_run_center_worker_unavailable")
  list(status = result$status, run_label = if (is.null(result$run_label)) "Desktop run" else result$run_label,
       failure_code = result$failure_code, replayed = isTRUE(result$replayed), safe_output = TRUE)
}

desktop_run_center_execute_v1 <- function(center, context, preview, confirmation, executed_at_utc, project_root) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
    if (!is.list(preview) || is.null(preview$preview_ref) || !exists(preview$preview_ref, envir = center$previews, inherits = FALSE) ||
        !is.list(confirmation) || !identical(confirmation$preview_ref, preview$preview_ref) ||
        !is.character(confirmation$challenge_ref) || !exists(confirmation$challenge_ref, envir = center$confirmations, inherits = FALSE) ||
        !.desktop_run_center_utc_v1(executed_at_utc)) .desktop_run_center_abort_v1("desktop_run_center_confirmation_invalid")
    preview_state <- get(preview$preview_ref, envir = center$previews, inherits = FALSE); challenge <- get(confirmation$challenge_ref, envir = center$confirmations, inherits = FALSE)
    if (isTRUE(challenge$consumed) || isTRUE(preview_state$consumed)) .desktop_run_center_abort_v1("desktop_run_center_confirmation_consumed")
    now <- as.POSIXct(executed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    if (is.na(now) || now < as.POSIXct(challenge$issued_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") || now > as.POSIXct(challenge$expires_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") ||
        !identical(challenge$context_fingerprint, runtime_context_fingerprint(context)) || !identical(preview_state$public, preview) || !identical(confirmation[c("contract_version", "challenge_ref", "preview_ref", "issued_at_utc", "expires_at_utc", "decision")], list(contract_version = 1L, challenge_ref = confirmation$challenge_ref, preview_ref = preview$preview_ref, issued_at_utc = challenge$issued_at_utc, expires_at_utc = challenge$expires_at_utc, decision = "confirm_once"))) .desktop_run_center_abort_v1("desktop_run_center_confirmation_expired")
    current <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
    if (is.null(current) || !identical(current$catalog_fingerprint, preview_state$catalog_fingerprint) ||
        !identical(digest::digest(file = runtime_canonical_path(context), algo = "sha256", serialize = FALSE), preview_state$plan$canonical_fingerprint) ||
        (!is.null(preview_state$plan$runtime$ledger_path) &&
         (!file.exists(preview_state$plan$runtime$ledger_path) || nzchar(Sys.readlink(preview_state$plan$runtime$ledger_path)) ||
          !.desktop_product_owner_mode_v1(preview_state$plan$runtime$ledger_path) || as.integer(file.info(preview_state$plan$runtime$ledger_path)$mode) != 384L ||
          !identical(normalizePath(preview_state$plan$runtime$ledger_path, winslash = "/", mustWork = TRUE), preview_state$plan$runtime$ledger_path) ||
          !startsWith(preview_state$plan$runtime$ledger_path, paste0(runtime_data_space_path(context), "/asset-activity-ledger-v1/generations/")) ||
          !identical(digest::digest(file = preview_state$plan$runtime$ledger_path, algo = "sha256", serialize = FALSE), preview_state$plan$runtime$ledger_fingerprint)))) {
      .desktop_run_center_abort_v1("desktop_run_center_catalog_changed")
    }
    .desktop_run_center_market_check_v1(context,project_root,preview_state$plan$market_valuation_binding)
    challenge$consumed <- TRUE; preview_state$consumed <- TRUE
    assign(confirmation$challenge_ref, challenge, envir = center$confirmations); assign(preview$preview_ref, preview_state, envir = center$previews)
    payload <- preview_state$plan; payload$executed_at_utc <- executed_at_utc
    fields <- c("contract_version", "run_id", "runtime", "portfolio", "data_space_label", "run_mode", "as_of_date", "cutoff_at_utc", "prepared_at_utc", "executed_at_utc", "tax_policy", "asset_inputs", "grouping_policy", "fee_policy", "catalog_fingerprint", "canonical_fingerprint")
    if (!is.null(payload$market_valuation_binding)) fields<-c(fields,"market_valuation_binding")
    payload <- payload[fields]
    payload_json <- as.character(jsonlite::toJSON(.catalog_sort_json_value(payload), auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE))
    envelope <- list(contract_version = 1L, payload_json = payload_json, payload_fingerprint = digest::digest(charToRaw(enc2utf8(payload_json)), algo = "sha256", serialize = FALSE))
    job_path <- file.path(.desktop_run_center_job_root_v1(context), paste0(payload$run_id, ".json"))
    if (file.exists(job_path) || .desktop_product_symlink_v1(job_path)) .desktop_run_center_abort_v1("desktop_run_center_job_conflict")
    .desktop_product_json_write_atomic_v1(job_path, envelope)
    .desktop_run_center_worker_v1(project_root, job_path)
  })
}

.desktop_run_center_stage_states_v1 <- function(value) {
  codes <- c("canonical", "fifo", "tax", "grouping", "market", "fx", "valuation", "trade_analysis", "market_analysis", "publication")
  if (!is.list(value) || length(value) != length(codes)) .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
  for (index in seq_along(codes)) {
    row <- value[[index]]
    if (!is.list(row) || !setequal(names(row), c("stage_code", "status", "failure_code")) ||
        !identical(row$stage_code, codes[[index]]) ||
        !row$status %in% c("completed", "partial", "stale", "blocked", if (identical(codes[[index]], "tax")) "not_selected") ||
        (!is.null(row$failure_code) && (!is.character(row$failure_code) || length(row$failure_code) != 1L || !grepl("^[a-z][a-z0-9_]{2,80}$", row$failure_code)))) {
      .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    }
  }
  value
}

desktop_run_center_status_v1 <- function(context) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_context_v1(context); jobs <- .desktop_run_center_existing_jobs_v1(context)
    if (is.null(jobs)) return(list(contract_version = 1L, status = "empty", resumable = FALSE, failure_code = NULL, run_label = NULL, stage_states = list()))
    files <- list.files(jobs, pattern = "^run_drw_[a-f0-9]{32}\\.json$", full.names = TRUE)
    if (!length(files)) return(list(contract_version = 1L, status = "empty", resumable = FALSE, failure_code = NULL, run_label = NULL, stage_states = list()))
    files <- files[order(file.info(files)$mtime, decreasing = TRUE)]
    job <- tryCatch(.desktop_product_json_read_v1(files[[1L]]), error = function(error) NULL)
    if (is.null(job) || !is.character(job$payload_json)) .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    payload <- jsonlite::fromJSON(job$payload_json, simplifyVector = FALSE); state_path <- file.path(runtime_data_space_path(context), "run-center", "runs", payload$run_id, "state.json")
    if (!file.exists(state_path)) return(list(contract_version = 1L, status = "confirmed", resumable = TRUE, failure_code = NULL, run_label = paste(payload$run_mode, "run"), stage_states = list()))
    state <- tryCatch(.desktop_product_json_read_v1(state_path), error = function(error) NULL)
    if (is.null(state)) .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    if (!state$status %in% c("running", "completed", "blocked") || (!is.null(state$failure_code) && (!is.character(state$failure_code) || length(state$failure_code) != 1L || !grepl("^[a-z][a-z0-9_]{2,80}$", state$failure_code)))) {
      .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    }
    stages <- .desktop_run_center_stage_states_v1(state$stage_states)
    list(contract_version = 1L, status = state$status, resumable = identical(state$status, "running"), failure_code = state$failure_code, run_label = paste(payload$run_mode, "run"), stage_states = stages)
  })
}

# Der zuletzt bestaetigte Lauf: sein versiegelter Auftrag und wie weit er kam. NULL, wenn es noch keinen gab.
.desktop_run_center_last_job_v1 <- function(context) {
  jobs <- tryCatch(.desktop_run_center_existing_jobs_v1(context), spot_desktop_run_center_error_v1 = function(error)
    .desktop_run_center_abort_v1("desktop_run_center_last_run_unreadable"))
  if (is.null(jobs)) return(NULL)
  files <- list.files(jobs, pattern = "^run_drw_[a-f0-9]{32}\\.json$", full.names = TRUE)
  if (!length(files)) return(NULL)
  path <- files[order(file.info(files)$mtime, decreasing = TRUE)][[1L]]
  job <- tryCatch(.desktop_product_json_read_v1(path), error = function(error) NULL)
  payload <- if (is.list(job) && is.character(job$payload_json) && length(job$payload_json) == 1L &&
                 identical(digest::digest(charToRaw(enc2utf8(job$payload_json)), algo = "sha256", serialize = FALSE), job$payload_fingerprint))
    tryCatch(jsonlite::fromJSON(job$payload_json, simplifyVector = FALSE), error = function(error) NULL) else NULL
  if (!is.list(payload) || !is.character(payload$run_id) || !grepl("^run_drw_[a-f0-9]{32}$", payload$run_id) ||
      !is.list(payload$portfolio) || !is.list(payload$tax_policy) || !is.list(payload$fee_policy) || !is.list(payload$asset_inputs) ||
      !.desktop_run_center_date_v1(payload$as_of_date)) {
    .desktop_run_center_abort_v1("desktop_run_center_last_run_unreadable")
  }
  state_path <- file.path(runtime_data_space_path(context), "run-center", "runs", payload$run_id, "state.json")
  # Ohne Zustandsdatei ist der Auftrag bestaetigt, aber nie angelaufen.
  status <- "confirmed"; failure_code <- NULL
  if (file.exists(state_path)) {
    state <- tryCatch(.desktop_product_json_read_v1(state_path), error = function(error) NULL)
    if (!is.list(state) || !is.character(state$status) || length(state$status) != 1L || !state$status %in% c("running", "completed", "blocked"))
      .desktop_run_center_abort_v1("desktop_run_center_last_run_unreadable")
    status <- state$status; failure_code <- state$failure_code
  }
  list(path = path, payload = payload, status = status, failure_code = failure_code)
}

# Die Eingaben des letzten bestaetigten Laufs fuer einen neuen Stichtag (#463, Stufe 2). Das Run Center uebernimmt sie: Portfolio, Steuermodul, Kirchensteuer, Gebuehrenquelle,
# Modus und die Angaben je Asset; neu sind nur Stichtag und Cutoff. Eigene Kurse und Wechselkurse gelten nur fuer ihren
# Stichtag: Ein Lauf damit wird nicht uebernommen ("not_reusable"), sonst stuende ein alter Kurs unter einem neuen Datum. Eine
# eingebundene abgeschlossene Bewertung wird nicht uebernommen; die Marktwerte kommen wie bei jedem Plan ohne Bindung aus dem
# Bewertungsstand (Festlegung 20.10.2026). Ein Asset, das seit dem letzten Lauf hinzukam, bekommt die Vorgaben des Formulars.
desktop_run_center_last_form_v1 <- function(center, context, as_of_date, cutoff_at_utc) {
  .desktop_run_center_boundary_v1({
    catalog <- .desktop_run_center_catalog_state_v1(center, context)
    if (!.desktop_run_center_date_v1(as_of_date) || !.desktop_run_center_utc_v1(cutoff_at_utc)) .desktop_run_center_abort_v1("desktop_run_center_input_invalid")
    last <- .desktop_run_center_last_job_v1(context)
    answer <- function(status, reason = NULL, form = NULL, extra = list()) c(list(contract_version = 1L, status = status, reason = reason, form = form,
      last_as_of_date = if (is.null(last)) NULL else last$payload$as_of_date, last_status = if (is.null(last)) NULL else last$status), extra)
    if (is.null(last)) return(answer("absent"))
    payload <- last$payload
    if (last$status %in% c("confirmed", "running")) return(answer("not_reusable", "last_run_unfinished"))
    manual <- vapply(payload$asset_inputs, function(row) !is.list(row) || !is.null(row$close_decimal) || !identical(row$fx_direction, "none"), logical(1L))
    if (any(manual)) return(answer("not_reusable", "manual_market_inputs"))
    portfolio_ref <- names(catalog$portfolio_by_ref)[vapply(catalog$portfolio_by_ref, function(row)
      identical(row$portfolio_id, payload$portfolio$portfolio_id) && identical(row$status, "active"), logical(1L))]
    if (length(portfolio_ref) != 1L) return(answer("not_reusable", "portfolio_unavailable"))
    previous <- stats::setNames(payload$asset_inputs, vapply(payload$asset_inputs, function(row) as.character(row$asset_id), character(1L)))
    noncash <- names(catalog$asset_by_ref)[vapply(catalog$asset_by_ref, function(row) !identical(row$asset_type, "cash") && identical(row$status, "active"), logical(1L))]
    asset_inputs <- lapply(noncash, function(ref) {
      row <- previous[[catalog$asset_by_ref[[ref]]$asset_id]]
      if (is.null(row)) row <- list(tax_classification = "not_configured", fx_direction = "none")
      list(asset_ref = ref, listing_code = row$listing_code, market_currency = row$market_currency, close_decimal = NULL, observed_at_utc = NULL,
           tax_classification = row$tax_classification, partial_exemption_rate_decimal = row$partial_exemption_rate_decimal,
           fixed_fee_decimal = row$fixed_fee_decimal, percentage_fee_rate_decimal = row$percentage_fee_rate_decimal,
           fx_base_currency = NULL, fx_quote_currency = NULL, fx_direction = "none", fx_rate_decimal = NULL, fx_observed_at_utc = NULL)
    })
    tax <- payload$tax_policy; fee <- payload$fee_policy
    form <- list(portfolio_ref = portfolio_ref, run_mode = payload$run_mode, as_of_date = as_of_date, cutoff_at_utc = cutoff_at_utc,
                 tax_mode = tax$mode, capital_income_tax_rate = tax$capital_income_tax_rate, personal_income_tax_rate = tax$personal_income_tax_rate,
                 solidarity_surcharge_rate = tax$solidarity_surcharge_rate, church_tax_applicable = tax$church_tax_applicable,
                 church_tax_rate = tax$church_tax_rate, fee_source = fee$source, fee_fixed_decimal = fee$fixed_decimal,
                 fee_percentage_rate_decimal = fee$percentage_rate_decimal, asset_inputs = asset_inputs,
                 grouping_mode = if (is.list(payload$grouping_policy)) payload$grouping_policy$mode else NULL)
    answer("ready", form = form, extra = list(
      # portfolio_id (rc.410): Die Steuer des Abschlusses folgt dem Umfang genau dieses Portfolios, nicht dem des ganzen Datenraums.
      portfolio_label = catalog$portfolio_by_ref[[portfolio_ref]]$display_name, portfolio_id = payload$portfolio$portfolio_id,
      run_mode = payload$run_mode, tax_mode = tax$mode,
      church_tax_applicable = tax$church_tax_applicable, fee_source = fee$source,
      new_asset_count = sum(!vapply(noncash, function(ref) catalog$asset_by_ref[[ref]]$asset_id %in% names(previous), logical(1L)))))
  })
}

# Waere ein Lauf aus dieser Vorschau eine Wiederholung des letzten? Ja, wenn der letzte vollstaendig lief, nach dem Einspielen
# des jetzigen Programmstands (eine neue Version kann anders rechnen) und mit genau denselben Eingaben und Datenstaenden -
# Stichtag, Cutoff, Stammdaten-, Buchungs- und Bestandsabdruck eingeschlossen. Nur Zeitstempel und die Laufkennung zaehlen nicht.
# Steuer-Eingaben ausserhalb des Plans (#536): Betraege laut Beleg, Vorabpauschalen, Steuerangaben je Portfolio und Institut,
# Cash-Zinsen. Dieselben wie im Abdruck der Netto-Sicht. Ist eine Datei darin juenger als der letzte Lauf, rechnet der Abschluss
# neu - bis rc.358 blieb ein uebernommener Bankwert bis zum naechsten Stichtag unbeachtet.
# Seit rc.406 auch der Umfang je Portfolio: Die Steuerprojektion folgt ihrem Baustein (#564).
DESKTOP_RUN_CENTER_TAX_INPUTS_V1 <- c("asset-activity-reference-v1/activity-taxable-document.sqlite", "advance-lump-sum-v1", "tax-ui",
                                      "institution-tax-settings-v1", "cash-coverage-v1", "portfolio-configuration-v1")
.desktop_run_center_tax_inputs_newer_v1 <- function(context, since, inputs = DESKTOP_RUN_CENTER_TAX_INPUTS_V1) {
  space <- runtime_data_space_path(context)
  paths <- file.path(space, inputs)
  files <- unlist(lapply(paths[file.exists(paths)], function(path)
    if (dir.exists(path)) list.files(path, recursive = TRUE, full.names = TRUE, all.files = TRUE, no.. = TRUE) else path), use.names = FALSE)
  if (!length(files)) return(FALSE)
  times <- file.info(files)$mtime
  any(!is.na(times) & times >= since)
}

# Kursspeicher (rc.385): Ein Abruf, der Kurse oder Wechselkurse anhaengt oder korrigiert (vorlaeufige Werte, Quellluecken), kann
# den Stichtag des letzten Abschlusses betreffen. Bis rc.384 galt der Abschluss dann trotzdem als aktuell - die Bewertungsbindung
# des Plans ist im Lauf "Alles aktualisieren" leer. Der Bewertungsstand selbst taugt nicht als Signal: Die Momentaufnahme schreibt
# alle zwei Stunden in dieselbe Datei. Die Kursspeicher aendern sich nur mit einem echten Abruf.
DESKTOP_RUN_CENTER_PRICE_INPUTS_V1 <- c("daily-market-history-v1", "fx-history-v1")

desktop_run_center_preview_repeats_last_v1 <- function(center, context, preview, project_root) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_check_v1(center); .desktop_run_center_context_v1(context)
    if (!is.list(preview) || !is.character(preview$preview_ref) || !exists(preview$preview_ref, envir = center$previews, inherits = FALSE))
      .desktop_run_center_abort_v1("desktop_run_center_preview_invalid")
    state <- get(preview$preview_ref, envir = center$previews, inherits = FALSE)
    if (!identical(state$public, preview) || !identical(state$context_fingerprint, runtime_context_fingerprint(context)))
      .desktop_run_center_abort_v1("desktop_run_center_preview_invalid")
    last <- .desktop_run_center_last_job_v1(context)
    if (is.null(last) || !identical(last$status, "completed")) return(FALSE)
    # Das Upgrade schreibt VERSION in der Installation neu; ihr Zeitstempel ist der Zeitpunkt des jetzigen Programmstands.
    version <- file.path(project_root, "VERSION")
    if (!file.exists(version) || file.info(version)$mtime >= file.info(last$path)$mtime) return(FALSE)
    if (.desktop_run_center_tax_inputs_newer_v1(context, file.info(last$path)$mtime)) return(FALSE)
    if (.desktop_run_center_tax_inputs_newer_v1(context, file.info(last$path)$mtime, DESKTOP_RUN_CENTER_PRICE_INPUTS_V1)) return(FALSE)
    fields <- c("runtime", "portfolio", "data_space_label", "run_mode", "as_of_date", "cutoff_at_utc", "tax_policy", "asset_inputs",
                "grouping_policy", "fee_policy", "catalog_fingerprint", "canonical_fingerprint", "market_valuation_binding")
    canonical <- function(value) as.character(jsonlite::toJSON(.catalog_sort_json_value(value[intersect(fields, names(value))]),
      auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = FALSE))
    identical(canonical(jsonlite::fromJSON(canonical(state$plan), simplifyVector = FALSE)), canonical(last$payload))
  })
}

desktop_run_center_resume_v1 <- function(context, project_root) {
  .desktop_run_center_boundary_v1({
    .desktop_run_center_context_v1(context); jobs <- .desktop_run_center_existing_jobs_v1(context)
    if (is.null(jobs)) .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    files <- list.files(jobs, pattern = "^run_drw_[a-f0-9]{32}\\.json$", full.names = TRUE)
    if (!length(files)) .desktop_run_center_abort_v1("desktop_run_center_no_resumable_job")
    files <- files[order(file.info(files)$mtime, decreasing = TRUE)]
    .desktop_run_center_worker_v1(project_root, files[[1L]])
  })
}
