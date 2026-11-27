desktop_csv_import_error_codes_v1 <- function() c(
  "desktop_csv_context_invalid", "desktop_csv_source_invalid", "desktop_csv_header_invalid",
  "desktop_csv_input_invalid", "desktop_csv_catalog_unavailable", "desktop_csv_plan_conflict",
  "desktop_csv_preview_required", "desktop_csv_confirmation_required",
  "desktop_csv_confirmation_consumed", "desktop_csv_catalog_changed",
  "desktop_csv_restart_unavailable", "desktop_csv_storage_invalid",
  "desktop_csv_command_failed", "desktop_csv_simulated_interruption", "desktop_csv_boundary_failed"
)
.desktop_csv_condition_v1 <- function(code) {
  if (!code %in% desktop_csv_import_error_codes_v1()) stop("desktop_csv_unregistered_error", call. = FALSE)
  structure(list(message = code, call = NULL, code = code), class = c("spot_desktop_csv_error_v1", "error", "condition"))
}
.desktop_csv_abort_v1 <- function(code) stop(.desktop_csv_condition_v1(code))
.desktop_csv_boundary_v1 <- function(expression) {
  result <- tryCatch(expression, spot_desktop_csv_error_v1 = function(error) error, error = function(error) .desktop_csv_condition_v1("desktop_csv_boundary_failed"))
  if (inherits(result, "spot_desktop_csv_error_v1")) stop(result)
  result
}
.desktop_csv_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .desktop_csv_abort_v1("desktop_csv_context_invalid")
  }
}
.desktop_csv_fields_v1 <- function() c(
  "row_ref", "entity_type", "portfolio_ref", "display_name", "base_currency", "account_type",
  "institution_label", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin"
)
.desktop_csv_text_v1 <- function(value, optional = FALSE, maximum = 120L) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) || value != trimws(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) .desktop_csv_abort_v1("desktop_csv_input_invalid")
  value
}
.desktop_csv_paths_v1 <- function(context) {
  root <- .runtime_safe_child(context, c(context$tenant_id, context$user_id, context$data_space_id, "catalog_import"))
  list(root = root, plans = file.path(root, "plans"), receipts = file.path(root, "receipts"), lock = file.path(root, "writer.lock"))
}
.desktop_csv_prepare_dirs_v1 <- function(context) {
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  paths <- .desktop_csv_paths_v1(context)
  for (path in paths[c("root", "plans", "receipts")]) {
    value <- path[[1L]]
    if (file.exists(value) && !dir.exists(value)) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
    if (!dir.exists(value) && !dir.create(value, mode = "0700", showWarnings = FALSE)) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
    if (.desktop_product_symlink_v1(value)) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
    suppressWarnings(Sys.chmod(value, "0700"))
    if (!.desktop_product_owner_mode_v1(value, directory = TRUE)) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
  }
  paths
}
.desktop_csv_catalog_v1 <- function(context) {
  catalog <- tryCatch(catalog_read_v1(context), error = function(error) NULL)
  if (is.null(catalog)) .desktop_csv_abort_v1("desktop_csv_catalog_unavailable")
  refs <- vapply(seq_along(catalog$portfolios), function(index) sprintf("portfolio_ref_%04d", index), character(1L))
  list(
    model = catalog,
    portfolios = stats::setNames(catalog$portfolios, refs),
    public = list(
      contract_version = 1L, status = "ready",
      portfolios = lapply(seq_along(catalog$portfolios), function(index) list(
        portfolio_ref = refs[[index]], display_name = catalog$portfolios[[index]]$display_name,
        base_currency = catalog$portfolios[[index]]$base_currency, status = catalog$portfolios[[index]]$status
      )),
      accepted_file = "desktop-catalog.csv", create_only = TRUE, context_exposed = FALSE,
      internal_ids_exposed = FALSE, canonical_write = FALSE
    )
  )
}
desktop_csv_import_catalog_v1 <- function(context) .desktop_csv_boundary_v1({
  .desktop_csv_context_v1(context); .desktop_csv_catalog_v1(context)$public
})

desktop_csv_import_template_v1 <- function(path) {
  .desktop_csv_boundary_v1({
    old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
    if (!is.character(path) || length(path) != 1L || is.na(path) || file.exists(path) || dir.exists(path) ||
        .desktop_product_symlink_v1(path)) .desktop_csv_abort_v1("desktop_csv_source_invalid")
    frame <- as.data.frame(stats::setNames(replicate(length(.desktop_csv_fields_v1()), character(), simplify = FALSE), .desktop_csv_fields_v1()), check.names = FALSE)
    utils::write.table(frame, path, sep = ",", row.names = FALSE, col.names = TRUE, quote = TRUE, na = "", eol = "\n", fileEncoding = "UTF-8")
    suppressWarnings(Sys.chmod(path, "0600"))
    if (!.desktop_product_owner_mode_v1(path)) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
    invisible(path)
  })
}
.desktop_csv_read_v1 <- function(path, catalog) {
  if (!is.character(path) || length(path) != 1L || is.na(path) || !file.exists(path) || dir.exists(path) || .desktop_product_symlink_v1(path)) .desktop_csv_abort_v1("desktop_csv_source_invalid")
  size <- suppressWarnings(file.info(path)$size)
  if (length(size) != 1L || is.na(size) || size < 2L || size > 1048576L) .desktop_csv_abort_v1("desktop_csv_source_invalid")
  raw <- readBin(path, what = "raw", n = size)
  if (any(raw == as.raw(0L)) || any(raw == as.raw(13L))) .desktop_csv_abort_v1("desktop_csv_source_invalid")
  text <- tryCatch(iconv(rawToChar(raw), from = "UTF-8", to = "UTF-8", sub = NA_character_), error = function(error) NA_character_)
  if (length(text) != 1L || is.na(text)) .desktop_csv_abort_v1("desktop_csv_source_invalid")
  frame <- tryCatch(utils::read.csv(text = text, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character", na.strings = character()), error = function(error) NULL)
  if (is.null(frame) || !identical(names(frame), .desktop_csv_fields_v1())) .desktop_csv_abort_v1("desktop_csv_header_invalid")
  if (nrow(frame) < 1L || nrow(frame) > 500L || anyDuplicated(frame$row_ref)) .desktop_csv_abort_v1("desktop_csv_input_invalid")
  rows <- vector("list", nrow(frame)); known <- names(catalog$portfolios); created_portfolios <- character()
  require_empty <- function(row, fields) if (any(vapply(fields, function(field) nzchar(row[[field]]), logical(1L)))) {
    .desktop_csv_abort_v1("desktop_csv_input_invalid")
  }
  for (index in seq_len(nrow(frame))) {
    row <- as.list(frame[index, , drop = FALSE]); row_ref <- .desktop_csv_text_v1(row$row_ref, maximum = 64L)
    if (!grepl("^usr_[a-z0-9_]{3,60}$", row_ref)) .desktop_csv_abort_v1("desktop_csv_input_invalid")
    kind <- .desktop_csv_text_v1(row$entity_type, maximum = 12L)
    if (!kind %in% c("portfolio", "account", "asset")) .desktop_csv_abort_v1("desktop_csv_input_invalid")
    display <- .desktop_csv_text_v1(row$display_name)
    normalized <- stats::setNames(as.list(rep(NA_character_, length(.desktop_csv_fields_v1()))), .desktop_csv_fields_v1())
    normalized$row_ref <- row_ref; normalized$entity_type <- kind; normalized$display_name <- display
    if (kind == "portfolio") {
      require_empty(row, c("portfolio_ref", "account_type", "institution_label", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin"))
      if (!grepl("^[A-Z]{3}$", row$base_currency)) .desktop_csv_abort_v1("desktop_csv_input_invalid")
      normalized$base_currency <- row$base_currency; created_portfolios <- c(created_portfolios, row_ref)
    } else if (kind == "account") {
      require_empty(row, c("base_currency", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin"))
      portfolio_ref <- .desktop_csv_text_v1(row$portfolio_ref, maximum = 64L)
      existing_active <- portfolio_ref %in% known && identical(catalog$portfolios[[portfolio_ref]]$status, "active")
      if (!(existing_active || portfolio_ref %in% created_portfolios) ||
          !row$account_type %in% c("securities", "cash", "bank", "crypto_wallet", "external", "other")) {
        .desktop_csv_abort_v1("desktop_csv_input_invalid")
      }
      normalized$portfolio_ref <- portfolio_ref; normalized$account_type <- row$account_type
      institution <- .desktop_csv_text_v1(row$institution_label, optional = TRUE)
      normalized["institution_label"] <- list(institution)
    } else {
      require_empty(row, c("portfolio_ref", "base_currency", "account_type", "institution_label"))
      scale <- suppressWarnings(as.integer(row$quantity_scale))
      isin <- .desktop_csv_text_v1(row$isin, optional = TRUE, maximum = 12L)
      if (!row$asset_type %in% c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "cash", "fx", "index", "other") ||
          !grepl("^[A-Z]{3}$", row$price_currency) || length(scale) != 1L || is.na(scale) || scale < 0L || scale > 24L ||
          !row$valuation_method %in% c("external_market", "manual", "unit_value", "transaction_only") ||
          (identical(row$asset_type, "cash") && !identical(row$valuation_method, "unit_value")) ||
          (!is.null(isin) && !grepl("^[A-Z0-9]{12}$", isin))) .desktop_csv_abort_v1("desktop_csv_input_invalid")
      normalized$asset_type <- row$asset_type; normalized$price_currency <- row$price_currency
      normalized$quantity_scale <- as.character(scale); normalized$valuation_method <- row$valuation_method
      normalized["isin"] <- list(isin)
    }
    rows[[index]] <- normalized
  }
  order <- order(match(vapply(rows, `[[`, character(1L), "entity_type"), c("portfolio", "account", "asset")), seq_along(rows))
  rows[order]
}
.desktop_csv_baseline_commands_v1 <- function(context) {
  connection <- .catalog_connect_read(context); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  sort(DBI::dbGetQuery(connection, "SELECT command_id FROM data_command_audit ORDER BY command_id")$command_id, method = "radix")
}
.desktop_csv_plan_valid_v1 <- function(plan, context) {
  base <- is.list(plan) && identical(names(plan), c(
    "contract_version", "plan_id", "tenant_id", "user_id", "data_space_id", "prepared_at_utc",
    "source_fingerprint", "baseline_catalog_fingerprint", "baseline_command_ids", "existing_portfolios", "rows", "tokens"
  )) && identical(plan$contract_version, 1L) && is.character(plan$plan_id) && length(plan$plan_id) == 1L && grepl("^dci_[a-f0-9]{32}$", plan$plan_id) &&
    identical(plan$tenant_id, context$tenant_id) && identical(plan$user_id, context$user_id) && identical(plan$data_space_id, context$data_space_id) &&
    .desktop_product_utc_valid_v1(plan$prepared_at_utc) && is.character(plan$source_fingerprint) && grepl("^[a-f0-9]{64}$", plan$source_fingerprint) &&
    is.character(plan$baseline_catalog_fingerprint) && grepl("^[a-f0-9]{64}$", plan$baseline_catalog_fingerprint) && is.list(plan$rows) && length(plan$rows) >= 1L &&
    is.list(plan$tokens) && length(plan$tokens) == length(plan$rows) && is.list(plan$existing_portfolios) &&
    is.list(plan$baseline_command_ids)
  if (!isTRUE(base)) return(FALSE)
  tokens <- unlist(plan$tokens, use.names = FALSE)
  baseline <- unlist(plan$baseline_command_ids, use.names = FALSE)
  existing <- unlist(plan$existing_portfolios, use.names = TRUE)
  if (length(tokens) != length(plan$rows) || anyDuplicated(tokens) || any(!grepl("^tok_csv_[a-f0-9]{32}$", tokens)) ||
      anyDuplicated(baseline) || any(!grepl("^[a-z][a-z0-9_]{7,80}$", baseline)) ||
      (length(existing) && (is.null(names(existing)) || anyDuplicated(names(existing)) ||
        any(!grepl("^portfolio_ref_[0-9]{4}$", names(existing))) || any(!grepl("^ptf_[a-f0-9]{24}$", existing))))) return(FALSE)
  row_refs <- character(); created_portfolios <- character(); seen_account <- FALSE; seen_asset <- FALSE
  text_valid <- function(value, maximum = 120L) is.character(value) && length(value) == 1L && !is.na(value) &&
    nzchar(value) && identical(value, trimws(value)) && nchar(value, type = "bytes") <= maximum && !grepl("[[:cntrl:]]", value)
  absent <- function(value) is.null(value)
  for (row in plan$rows) {
    if (!is.list(row) || !identical(names(row), .desktop_csv_fields_v1()) || !is.character(row$row_ref) ||
        !grepl("^usr_[a-z0-9_]{3,60}$", row$row_ref) || row$row_ref %in% row_refs ||
        !is.character(row$entity_type) || !row$entity_type %in% c("portfolio", "account", "asset") ||
        !text_valid(row$display_name)) return(FALSE)
    row_refs <- c(row_refs, row$row_ref)
    if (row$entity_type == "portfolio") {
      if (seen_account || seen_asset || !is.character(row$base_currency) || !grepl("^[A-Z]{3}$", row$base_currency) ||
          any(!vapply(row[c("portfolio_ref", "account_type", "institution_label", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin")], absent, logical(1L)))) return(FALSE)
      created_portfolios <- c(created_portfolios, row$row_ref)
    }
    if (row$entity_type == "account") {
      seen_account <- TRUE
      if (seen_asset || !is.character(row$portfolio_ref) || !row$portfolio_ref %in% c(names(existing), created_portfolios) ||
          !is.character(row$account_type) || !row$account_type %in% c("securities", "cash", "bank", "crypto_wallet", "external", "other") ||
          any(!vapply(row[c("base_currency", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin")], absent, logical(1L))) ||
          !(absent(row$institution_label) || text_valid(row$institution_label))) return(FALSE)
    }
    if (row$entity_type == "asset") {
      seen_asset <- TRUE
      if (!is.character(row$asset_type) || !row$asset_type %in% c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "cash", "fx", "index", "other") ||
          !is.character(row$price_currency) || !grepl("^[A-Z]{3}$", row$price_currency) ||
          !is.character(row$quantity_scale) || !grepl("^(0|[1-9]|1[0-9]|2[0-4])$", row$quantity_scale) ||
          !is.character(row$valuation_method) || !row$valuation_method %in% c("external_market", "manual", "unit_value", "transaction_only") ||
          (identical(row$asset_type, "cash") && !identical(row$valuation_method, "unit_value")) ||
          any(!vapply(row[c("portfolio_ref", "base_currency", "account_type", "institution_label")], absent, logical(1L))) ||
          !(absent(row$isin) || is.character(row$isin) && grepl("^[A-Z0-9]{12}$", row$isin))) return(FALSE)
    }
  }
  TRUE
}
.desktop_csv_commands_v1 <- function(plan, context) {
  portfolio_ids <- lapply(plan$existing_portfolios, identity); commands <- list()
  timestamp <- function() plan$prepared_at_utc
  for (index in seq_along(plan$rows)) {
    row <- plan$rows[[index]]; token <- plan$tokens[[index]]
    command <- if (row$entity_type == "portfolio") {
      value <- .catalog_build_create_portfolio_v1(context, token, row$display_name, row$base_currency, timestamp())
      portfolio_ids[[row$row_ref]] <- value$entity_id; value
    } else if (row$entity_type == "account") {
      id <- portfolio_ids[[row$portfolio_ref]]; if (is.null(id)) .desktop_csv_abort_v1("desktop_csv_plan_conflict")
      .catalog_build_create_account_v1(context, token, id, row$display_name, row$account_type, row$institution_label, timestamp())
    } else .catalog_build_create_asset_v1(
      context, token, row$display_name, row$asset_type, row$price_currency, as.integer(row$quantity_scale),
      row$valuation_method, row$isin, timestamp()
    )
    commands[[index]] <- command
  }
  commands
}
.desktop_csv_state_v1 <- function(plan, context) {
  commands <- .desktop_csv_commands_v1(plan, context); expected <- vapply(commands, `[[`, character(1L), "command_id")
  actual <- .desktop_csv_baseline_commands_v1(context)
  extras <- setdiff(actual, plan$baseline_command_ids); if (any(!extras %in% expected)) .desktop_csv_abort_v1("desktop_csv_plan_conflict")
  present <- expected %in% extras; completed <- sum(present)
  if (!identical(present, c(rep(TRUE, completed), rep(FALSE, length(present) - completed)))) .desktop_csv_abort_v1("desktop_csv_plan_conflict")
  list(commands = commands, present = present, completed = as.integer(completed))
}
.desktop_csv_public_v1 <- function(plan, state) list(
  contract_version = 1L,
  status = if (state$completed == length(state$commands)) "ready_to_finalize" else if (state$completed > 0L) "ready_to_resume" else "pending_confirmation",
  preview_ref = paste0("dcip_", substr(.catalog_fingerprint(list(plan = plan$plan_id, source = plan$source_fingerprint, completed = state$completed)), 1L, 32L)),
  counts = list(row_count = as.integer(length(plan$rows)), completed_row_count = state$completed, pending_row_count = as.integer(length(plan$rows) - state$completed)),
  rows = lapply(seq_along(plan$rows), function(index) list(
    row_ordinal = as.integer(index), entity_type = plan$rows[[index]]$entity_type,
    display_name = plan$rows[[index]]$display_name, status = if (state$present[[index]]) "completed" else "pending"
  )), confirmation_required = TRUE, canonical_write = FALSE, context_exposed = FALSE,
  internal_ids_exposed = FALSE, paths_exposed = FALSE
)
new_desktop_csv_import_v1 <- function() {
  center <- new.env(hash = FALSE, parent = emptyenv()); center$current <- NULL
  class(center) <- "spot_desktop_csv_import_v1"; center
}
.desktop_csv_center_v1 <- function(center) {
  if (!inherits(center, "spot_desktop_csv_import_v1") || !is.environment(center)) .desktop_csv_abort_v1("desktop_csv_preview_required")
}
.desktop_csv_incomplete_plans_v1 <- function(context) {
  paths <- .desktop_csv_paths_v1(context); if (!dir.exists(paths$plans)) return(character())
  plans <- list.files(paths$plans, pattern = "^dci_[a-f0-9]{32}[.]json$", full.names = TRUE)
  plans[!file.exists(file.path(paths$receipts, paste0(sub("[.]json$", "", basename(plans)), ".json")))]
}
desktop_csv_import_prepare_v1 <- function(center, context, source_path, prepared_at_utc) {
  .desktop_csv_boundary_v1({
    .desktop_csv_center_v1(center); .desktop_csv_context_v1(context)
    if (!.desktop_product_utc_valid_v1(prepared_at_utc) || length(.desktop_csv_incomplete_plans_v1(context))) .desktop_csv_abort_v1("desktop_csv_plan_conflict")
    catalog <- .desktop_csv_catalog_v1(context); rows <- .desktop_csv_read_v1(source_path, catalog)
    source_raw <- readBin(source_path, what = "raw", n = file.info(source_path)$size)
    source_fingerprint <- digest::digest(source_raw, algo = "sha256", serialize = FALSE)
    plan <- list(
      contract_version = 1L, plan_id = .desktop_product_random_id_v1("dci_"),
      tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
      prepared_at_utc = prepared_at_utc, source_fingerprint = source_fingerprint,
      baseline_catalog_fingerprint = catalog$model$catalog_fingerprint,
      baseline_command_ids = as.list(.desktop_csv_baseline_commands_v1(context)),
      existing_portfolios = lapply(catalog$portfolios, `[[`, "portfolio_id"), rows = rows,
      tokens = lapply(rows, function(row) .desktop_product_random_id_v1("tok_csv_"))
    )
    state <- .desktop_csv_state_v1(plan, context); public <- .desktop_csv_public_v1(plan, state)
    center$current <- list(plan = plan, public = public, consumed = FALSE)
    public
  })
}
.desktop_csv_read_plan_v1 <- function(path, context) {
  value <- .desktop_product_json_read_v1(path, "desktop_csv_storage_invalid")
  if (!is.list(value) || !identical(names(value), c("contract_version", "plan_fingerprint", "plan")) || value$contract_version != 1L ||
      !.desktop_csv_plan_valid_v1(value$plan, context) || !identical(value$plan_fingerprint, .catalog_fingerprint(value$plan))) .desktop_csv_abort_v1("desktop_csv_storage_invalid")
  value$plan
}
desktop_csv_import_restart_preview_v1 <- function(center, context) {
  .desktop_csv_boundary_v1({
    .desktop_csv_center_v1(center); .desktop_csv_context_v1(context)
    plans <- .desktop_csv_incomplete_plans_v1(context); if (length(plans) != 1L) .desktop_csv_abort_v1("desktop_csv_restart_unavailable")
    plan <- .desktop_csv_read_plan_v1(plans[[1L]], context); state <- .desktop_csv_state_v1(plan, context)
    public <- .desktop_csv_public_v1(plan, state); center$current <- list(plan = plan, public = public, consumed = FALSE); public
  })
}
.desktop_csv_execute_impl_v1 <- function(center, context, preview, confirmed, executed_at_utc, fail_after_step = 0L) {
  .desktop_csv_boundary_v1({
    .desktop_csv_center_v1(center); .desktop_csv_context_v1(context)
    if (!isTRUE(confirmed)) .desktop_csv_abort_v1("desktop_csv_confirmation_required")
    if (!is.list(preview) || is.null(center$current) || !identical(preview, center$current$public)) .desktop_csv_abort_v1("desktop_csv_preview_required")
    if (isTRUE(center$current$consumed)) .desktop_csv_abort_v1("desktop_csv_confirmation_consumed")
    if (!.desktop_product_utc_valid_v1(executed_at_utc) || !is.integer(fail_after_step) || fail_after_step < 0L || fail_after_step > length(center$current$plan$rows)) .desktop_csv_abort_v1("desktop_csv_input_invalid")
    plan <- center$current$plan
    if (as.POSIXct(executed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
        as.POSIXct(plan$prepared_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) .desktop_csv_abort_v1("desktop_csv_input_invalid")
    state <- .desktop_csv_state_v1(plan, context)
    if (state$completed == 0L) {
      catalog <- .desktop_csv_catalog_v1(context)
      if (!identical(catalog$model$catalog_fingerprint, plan$baseline_catalog_fingerprint)) .desktop_csv_abort_v1("desktop_csv_catalog_changed")
    }
    paths <- .desktop_csv_prepare_dirs_v1(context); lock_owner <- .desktop_product_acquire_lock_v1(paths$lock, "desktop_product_registry_conflict")
    on.exit(if (dir.exists(paths$lock)) .desktop_product_release_lock_v1(paths$lock, lock_owner), add = TRUE)
    plan_path <- file.path(paths$plans, paste0(plan$plan_id, ".json"))
    if (!file.exists(plan_path)) .desktop_product_json_write_atomic_v1(plan_path, list(contract_version = 1L, plan_fingerprint = .catalog_fingerprint(plan), plan = plan))
    else if (!identical(.desktop_csv_read_plan_v1(plan_path, context), plan)) .desktop_csv_abort_v1("desktop_csv_plan_conflict")
    center$current$consumed <- TRUE
    for (index in seq_along(state$commands)) if (!state$present[[index]]) {
      result <- tryCatch(.catalog_execute_public(context, state$commands[[index]]), error = function(error) NULL)
      if (is.null(result) || !result$status %in% c("committed", "already_committed")) .desktop_csv_abort_v1("desktop_csv_command_failed")
      if (fail_after_step > 0L && index == fail_after_step) .desktop_csv_abort_v1("desktop_csv_simulated_interruption")
    }
    final <- .desktop_csv_state_v1(plan, context); if (final$completed != length(final$commands)) .desktop_csv_abort_v1("desktop_csv_command_failed")
    receipt <- file.path(paths$receipts, paste0(plan$plan_id, ".json"))
    if (!file.exists(receipt)) .desktop_product_json_write_atomic_v1(receipt, list(
      contract_version = 1L, plan_id = plan$plan_id, plan_fingerprint = .catalog_fingerprint(plan),
      status = "completed", completed_at_utc = executed_at_utc, row_count = as.integer(length(plan$rows))
    ))
    list(contract_version = 1L, status = "completed", completed_row_count = final$completed, canonical_write = TRUE)
  })
}
desktop_csv_import_execute_v1 <- function(center, context, preview, confirmed, executed_at_utc) {
  .desktop_csv_execute_impl_v1(center, context, preview, confirmed, executed_at_utc, fail_after_step = 0L)
}
