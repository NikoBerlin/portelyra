minimal_bootstrap_completion_error_codes_v1 <- function() {
  c(
    "bootstrap_completion_dependency_missing",
    "bootstrap_completion_context_invalid",
    "bootstrap_completion_base_unavailable",
    "bootstrap_completion_base_invalid",
    "bootstrap_completion_store_invalid",
    "bootstrap_completion_command_invalid",
    "bootstrap_completion_preview_invalid",
    "bootstrap_completion_confirmation_missing",
    "bootstrap_completion_confirmation_invalid",
    "bootstrap_completion_confirmation_consumed",
    "bootstrap_completion_confirmation_expired",
    "bootstrap_completion_target_invalid",
    "bootstrap_completion_lock_unavailable",
    "bootstrap_completion_synthetic_failpoint",
    "bootstrap_completion_transaction_failed",
    "bootstrap_completion_boundary_failed"
  )
}

.bootstrap_completion_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% minimal_bootstrap_completion_error_codes_v1()) {
    stop("unregistered_bootstrap_completion_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_bootstrap_completion_error", "error", "condition")
  )
}

.bootstrap_completion_abort <- function(code) stop(.bootstrap_completion_condition(code))

.bootstrap_completion_boundary <- function(expression, fallback = "bootstrap_completion_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_bootstrap_completion_error = function(error) error,
    error = function(error) .bootstrap_completion_condition(fallback)
  )
  if (inherits(result, "spot_bootstrap_completion_error")) stop(result)
  result
}

.bootstrap_completion_dependencies <- function() {
  if (!all(vapply(c("DBI", "RSQLite", "digest", "jsonlite"), requireNamespace, logical(1), quietly = TRUE))) {
    .bootstrap_completion_abort("bootstrap_completion_dependency_missing")
  }
  invisible(TRUE)
}

.bootstrap_completion_fp <- function(value) {
  payload <- jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE)
  digest::digest(charToRaw(enc2utf8(payload)), algo = "sha256", serialize = FALSE)
}

.bootstrap_completion_file_fp <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

.bootstrap_completion_utc <- function(value, code = "bootstrap_completion_command_invalid") {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) {
    .bootstrap_completion_abort(code)
  }
  parsed <- as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (is.na(parsed) || format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") != value) {
    .bootstrap_completion_abort(code)
  }
  value
}

.bootstrap_completion_context <- function(context) {
  required <- c("tenant_id", "user_id", "data_space_id")
  if (!is.list(context) || !all(required %in% names(context)) ||
      !all(vapply(context[required], function(value) {
        is.character(value) && length(value) == 1L && !is.na(value) &&
          grepl("^[A-Za-z0-9_-]{3,64}$", value)
      }, logical(1))) || !grepl("^sbx_[a-z0-9_]{4,60}$", context$data_space_id)) {
    .bootstrap_completion_abort("bootstrap_completion_context_invalid")
  }
  context[required]
}

.bootstrap_completion_path <- function(path, must_exist, code) {
  link <- if (is.character(path) && length(path) == 1L && !is.na(path)) Sys.readlink(path) else NA_character_
  if (!is.character(path) || length(path) != 1L || is.na(path) || !nzchar(path) ||
      (must_exist && !file.exists(path)) || dir.exists(path) || (!is.na(link) && nzchar(link))) {
    .bootstrap_completion_abort(code)
  }
  if (must_exist) {
    normalized <- tryCatch(normalizePath(path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
    normalized_link <- if (is.null(normalized)) NA_character_ else Sys.readlink(normalized)
    info <- if (is.null(normalized)) NULL else file.info(normalized)
    if (is.null(normalized) || (!is.na(normalized_link) && nzchar(normalized_link)) ||
        is.null(info) || is.na(info$mode[[1]]) || as.integer(info$mode[[1]]) != 384L) {
      .bootstrap_completion_abort(code)
    }
    return(normalized)
  }
  parent <- tryCatch(normalizePath(dirname(path), winslash = "/", mustWork = TRUE), error = function(error) NULL)
  info <- if (is.null(parent)) NULL else file.info(parent)
  if (is.null(parent) || is.null(info) || !isTRUE(info$isdir[[1]]) ||
      is.na(info$mode[[1]]) || as.integer(info$mode[[1]]) != 448L) {
    .bootstrap_completion_abort(code)
  }
  file.path(parent, basename(path))
}

.bootstrap_completion_base <- function(base_path, context) {
  path <- .bootstrap_completion_path(base_path, TRUE, "bootstrap_completion_base_unavailable")
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RO),
    error = function(error) .bootstrap_completion_abort("bootstrap_completion_base_unavailable")
  )
  valid <- FALSE
  on.exit(if (!valid) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  DBI::dbExecute(connection, "PRAGMA query_only=ON")
  binding <- DBI::dbGetQuery(connection, "SELECT schema_version,tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1")
  receipt <- DBI::dbGetQuery(connection, "SELECT bundle_fingerprint FROM bootstrap_import_receipt")
  if (nrow(binding) != 1L || nrow(receipt) != 1L || as.integer(binding$schema_version[[1]]) != 300L ||
      !identical(binding$tenant_id[[1]], context$tenant_id) ||
      !identical(binding$user_id[[1]], context$user_id) ||
      !identical(binding$data_space_id[[1]], context$data_space_id) ||
      !grepl("^[a-f0-9]{64}$", receipt$bundle_fingerprint[[1]]) ||
      !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .bootstrap_completion_abort("bootstrap_completion_base_invalid")
  }
  valid <- TRUE
  list(path = path, connection = connection, bundle_fingerprint = receipt$bundle_fingerprint[[1]])
}

.bootstrap_completion_store <- function(completion_path, context, bundle_fingerprint, read_only = TRUE, allow_absent = TRUE) {
  if (!file.exists(completion_path)) {
    if (allow_absent) return(NULL)
    .bootstrap_completion_abort("bootstrap_completion_store_invalid")
  }
  path <- .bootstrap_completion_path(completion_path, TRUE, "bootstrap_completion_store_invalid")
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = if (read_only) RSQLite::SQLITE_RO else RSQLite::SQLITE_RW),
    error = function(error) .bootstrap_completion_abort("bootstrap_completion_store_invalid")
  )
  valid <- FALSE
  on.exit(if (!valid) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  DBI::dbExecute(connection, paste0("PRAGMA query_only=", if (read_only) "ON" else "OFF"))
  DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
  DBI::dbExecute(connection, "PRAGMA busy_timeout=0")
  binding <- DBI::dbGetQuery(connection, "SELECT schema_version,tenant_id,user_id,data_space_id,base_bundle_fingerprint FROM completion_store_binding WHERE singleton_id=1")
  if (nrow(binding) != 1L || as.integer(binding$schema_version[[1]]) != 310L ||
      !identical(binding$tenant_id[[1]], context$tenant_id) ||
      !identical(binding$user_id[[1]], context$user_id) ||
      !identical(binding$data_space_id[[1]], context$data_space_id) ||
      !identical(binding$base_bundle_fingerprint[[1]], bundle_fingerprint) ||
      !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .bootstrap_completion_abort("bootstrap_completion_store_invalid")
  }
  valid <- TRUE
  list(path = path, connection = connection)
}

.bootstrap_completion_nullable <- function(value, maximum, trim = TRUE) {
  if (is.null(value) || (is.character(value) && length(value) == 1L && !is.na(value) && !nzchar(value))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) || nchar(value, type = "chars") > maximum) {
    .bootstrap_completion_abort("bootstrap_completion_command_invalid")
  }
  if (trim && value != trimws(value)) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
  value
}

.bootstrap_completion_decimal <- function(value, positive = FALSE, allow_zero = FALSE) {
  value <- .bootstrap_completion_nullable(value, 80L)
  if (is.null(value)) return(NULL)
  pattern <- if (positive) "^(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$" else "^-?(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$"
  if (!grepl(pattern, value) || (!allow_zero && value %in% c("0", "-0"))) {
    .bootstrap_completion_abort("bootstrap_completion_command_invalid")
  }
  value
}

.bootstrap_completion_latest <- function(connection, table, id_column, entity_id) {
  if (is.null(connection)) return(NULL)
  query <- paste0(
    "SELECT * FROM ", table, " WHERE ", id_column, "=? ORDER BY revision_no DESC LIMIT 1"
  )
  row <- DBI::dbGetQuery(connection, query, params = list(entity_id))
  if (!nrow(row)) NULL else row[1L, , drop = FALSE]
}

.bootstrap_completion_command <- function(base, store, command) {
  if (!is.list(command) || !identical(sort(names(command)), sort(c("action_type", "entity_id", "fields"))) ||
      !is.character(command$action_type) || length(command$action_type) != 1L ||
      !is.character(command$entity_id) || length(command$entity_id) != 1L || !is.list(command$fields)) {
    .bootstrap_completion_abort("bootstrap_completion_command_invalid")
  }
  base_connection <- base$connection
  store_connection <- if (is.null(store)) NULL else store$connection
  action <- command$action_type
  if (identical(action, "complete_asset_metadata")) {
    if (!identical(sort(names(command$fields)), sort(c("quantity_scale", "valuation_method", "isin")))) {
      .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    }
    row <- DBI::dbGetQuery(base_connection, "SELECT asset_id,display_name,quantity_scale,valuation_method,isin FROM bootstrap_asset WHERE asset_id=?", params = list(command$entity_id))
    if (nrow(row) != 1L) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    latest <- .bootstrap_completion_latest(store_connection, "asset_metadata_revision", "asset_id", command$entity_id)
    before <- list(
      quantity_scale = if (is.null(latest)) if (is.na(row$quantity_scale[[1]])) NULL else as.integer(row$quantity_scale[[1]]) else if (is.na(latest$quantity_scale[[1]])) NULL else as.integer(latest$quantity_scale[[1]]),
      valuation_method = if (is.null(latest)) if (is.na(row$valuation_method[[1]])) NULL else row$valuation_method[[1]] else if (is.na(latest$valuation_method[[1]])) NULL else latest$valuation_method[[1]],
      isin = if (is.null(latest)) if (is.na(row$isin[[1]])) NULL else row$isin[[1]] else if (is.na(latest$isin[[1]])) NULL else latest$isin[[1]]
    )
    scale <- command$fields$quantity_scale
    if (is.null(scale) || (is.character(scale) && length(scale) == 1L && !nzchar(scale))) {
      scale <- NULL
    } else {
      if (!is.character(scale) || length(scale) != 1L || !grepl("^[0-9]{1,2}$", scale) || as.integer(scale) > 24L) {
        .bootstrap_completion_abort("bootstrap_completion_command_invalid")
      }
      scale <- as.integer(scale)
    }
    valuation <- .bootstrap_completion_nullable(command$fields$valuation_method, 40L)
    if (!is.null(valuation) && !valuation %in% c("external_market", "manual", "unit_value", "transaction_only")) {
      .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    }
    isin <- .bootstrap_completion_nullable(command$fields$isin, 12L)
    if (!is.null(isin) && !grepl("^[A-Z0-9]{12}$", isin)) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    after <- list(quantity_scale = scale, valuation_method = valuation, isin = isin)
    revision_no <- if (is.null(latest)) 1L else as.integer(latest$revision_no[[1]]) + 1L
    return(list(action_type = action, entity_id = command$entity_id, label = row$display_name[[1]], before = before, after = after, revision_no = revision_no))
  }
  if (identical(action, "complete_account_metadata")) {
    if (!identical(names(command$fields), "institution_label")) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    row <- DBI::dbGetQuery(base_connection, "SELECT account_id,display_name,institution_label FROM bootstrap_account WHERE account_id=?", params = list(command$entity_id))
    if (nrow(row) != 1L) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    latest <- .bootstrap_completion_latest(store_connection, "account_metadata_revision", "account_id", command$entity_id)
    before_value <- if (is.null(latest)) row$institution_label[[1]] else latest$institution_label[[1]]
    before <- list(institution_label = if (is.na(before_value)) NULL else before_value)
    after <- list(institution_label = .bootstrap_completion_nullable(command$fields$institution_label, 120L))
    revision_no <- if (is.null(latest)) 1L else as.integer(latest$revision_no[[1]]) + 1L
    return(list(action_type = action, entity_id = command$entity_id, label = row$display_name[[1]], before = before, after = after, revision_no = revision_no))
  }
  if (identical(action, "complete_transaction_fields")) {
    expected <- c("related_account_id", "unit_price_decimal", "gross_amount_decimal", "fee_decimal", "tax_decimal", "memo")
    if (!identical(sort(names(command$fields)), sort(expected))) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    row <- DBI::dbGetQuery(base_connection, paste(
      "SELECT fact.*,asset.display_name AS asset_name,asset.asset_type,source.display_name AS account_name",
      "FROM bootstrap_transaction_fact fact JOIN bootstrap_asset asset ON asset.asset_id=fact.asset_id",
      "JOIN bootstrap_account source ON source.account_id=fact.account_id WHERE fact.transaction_id=?"
    ), params = list(command$entity_id))
    if (nrow(row) != 1L) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    latest <- .bootstrap_completion_latest(store_connection, "transaction_completion_revision", "transaction_id", command$entity_id)
    pick <- function(name) {
      value <- if (is.null(latest)) row[[name]][[1]] else latest[[name]][[1]]
      if (is.na(value)) NULL else as.character(value)
    }
    before <- list(
      related_account_id = pick("related_account_id"), unit_price_decimal = pick("unit_price_decimal"),
      gross_amount_decimal = pick("gross_amount_decimal"), fee_decimal = pick("fee_decimal"),
      tax_decimal = pick("tax_decimal"), memo = pick("memo")
    )
    related <- .bootstrap_completion_nullable(command$fields$related_account_id, 64L)
    if (identical(row$event_type[[1]], "transfer")) {
      if (!is.null(related)) {
        target <- DBI::dbGetQuery(base_connection, "SELECT account_id FROM bootstrap_account WHERE account_id=? AND portfolio_id=?", params = list(related, row$portfolio_id[[1]]))
        if (nrow(target) != 1L || identical(related, row$account_id[[1]])) .bootstrap_completion_abort("bootstrap_completion_command_invalid")
      }
    } else if (!is.null(related)) {
      .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    }
    after <- list(
      related_account_id = related,
      unit_price_decimal = .bootstrap_completion_decimal(command$fields$unit_price_decimal, positive = TRUE),
      gross_amount_decimal = .bootstrap_completion_decimal(command$fields$gross_amount_decimal, allow_zero = TRUE),
      fee_decimal = .bootstrap_completion_decimal(command$fields$fee_decimal, positive = TRUE, allow_zero = TRUE),
      tax_decimal = .bootstrap_completion_decimal(command$fields$tax_decimal, positive = TRUE, allow_zero = TRUE),
      memo = .bootstrap_completion_nullable(command$fields$memo, 4000L, trim = FALSE)
    )
    identity_status <- if (identical(row$event_type[[1]], "transfer") && is.null(related)) "related_account_pending" else "complete"
    basis_required <- row$asset_type[[1]] != "cash" && row$event_type[[1]] %in% c("buy", "sell", "reward")
    basis_status <- if (basis_required && is.null(after$unit_price_decimal) && is.null(after$gross_amount_decimal)) "basis_pending" else if (basis_required) "available" else "not_required"
    calculation_status <- if (identity_status == "related_account_pending") "identity_pending" else if (basis_status == "basis_pending") "basis_pending" else "facts_ready"
    after$identity_status <- identity_status
    after$basis_status <- basis_status
    after$calculation_status <- calculation_status
    revision_no <- if (is.null(latest)) 1L else as.integer(latest$revision_no[[1]]) + 1L
    label <- paste(row$local_date[[1]], row$event_type[[1]], row$account_name[[1]], row$asset_name[[1]], sep = " · ")
    return(list(action_type = action, entity_id = command$entity_id, label = label, before = before, after = after, revision_no = revision_no))
  }
  .bootstrap_completion_abort("bootstrap_completion_command_invalid")
}

minimal_bootstrap_completion_preview_v1 <- function(base_path, completion_path, context, command) {
  .bootstrap_completion_boundary({
    .bootstrap_completion_dependencies()
    context <- .bootstrap_completion_context(context)
    base <- .bootstrap_completion_base(base_path, context)
    on.exit(DBI::dbDisconnect(base$connection), add = TRUE)
    store <- .bootstrap_completion_store(completion_path, context, base$bundle_fingerprint, read_only = TRUE, allow_absent = TRUE)
    if (!is.null(store)) on.exit(DBI::dbDisconnect(store$connection), add = TRUE)
    normalized <- .bootstrap_completion_command(base, store, command)
    body <- list(
      preview_contract_version = 1L,
      status = "ready_for_confirmation",
      context = context,
      base_bundle_fingerprint = base$bundle_fingerprint,
      action_type = normalized$action_type,
      entity_id = normalized$entity_id,
      entity_label = normalized$label,
      revision_no = normalized$revision_no,
      before = normalized$before,
      after = normalized$after,
      provider_access = FALSE,
      calculation_started = FALSE,
      base_store_write = FALSE
    )
    body$preview_fingerprint <- .bootstrap_completion_fp(body)
    body
  }, "bootstrap_completion_preview_invalid")
}

new_minimal_bootstrap_completion_authorizer_v1 <- function() {
  value <- new.env(hash = TRUE, parent = emptyenv())
  class(value) <- "spot_bootstrap_completion_authorizer_v1"
  value
}

minimal_bootstrap_completion_confirmation_v1 <- function(preview, context, authorizer, challenge_id, issued_at_utc, expires_at_utc) {
  .bootstrap_completion_boundary({
    context <- .bootstrap_completion_context(context)
    if (!inherits(authorizer, "spot_bootstrap_completion_authorizer_v1") ||
        !is.list(preview) || !identical(preview$status, "ready_for_confirmation") ||
        !identical(preview$context, context) || !grepl("^[a-f0-9]{64}$", preview$preview_fingerprint) ||
        !is.character(challenge_id) || length(challenge_id) != 1L || !grepl("^bcf_[a-z0-9_]{8,60}$", challenge_id)) {
      .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
    }
    issued <- .bootstrap_completion_utc(issued_at_utc, "bootstrap_completion_confirmation_invalid")
    expires <- .bootstrap_completion_utc(expires_at_utc, "bootstrap_completion_confirmation_invalid")
    issued_time <- as.POSIXct(issued, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    expires_time <- as.POSIXct(expires, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    validity <- as.numeric(expires_time - issued_time, units = "secs")
    if (validity <= 0 || validity > 600) {
      .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
    }
    value <- list(
      confirmation_contract_version = 1L,
      authorization_scope = "minimal_bootstrap_completion_once",
      challenge_id = challenge_id,
      preview_fingerprint = preview$preview_fingerprint,
      base_bundle_fingerprint = preview$base_bundle_fingerprint,
      context = context,
      issued_at_utc = issued,
      expires_at_utc = expires,
      provider_access_authorized = FALSE,
      calculation_authorized = FALSE,
      confirmed = TRUE
    )
    value$confirmation_fingerprint <- .bootstrap_completion_fp(value)
    value
  }, "bootstrap_completion_confirmation_invalid")
}

.bootstrap_completion_consume <- function(authorizer, confirmation) {
  if (!inherits(authorizer, "spot_bootstrap_completion_authorizer_v1")) .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
  key <- confirmation$confirmation_fingerprint
  if (exists(key, envir = authorizer, inherits = FALSE)) .bootstrap_completion_abort("bootstrap_completion_confirmation_consumed")
  assign(key, TRUE, envir = authorizer)
  invisible(TRUE)
}

.bootstrap_completion_verify_confirmation <- function(confirmation, preview, context, now_utc) {
  if (is.null(confirmation)) .bootstrap_completion_abort("bootstrap_completion_confirmation_missing")
  if (!is.list(confirmation) || !identical(confirmation$authorization_scope, "minimal_bootstrap_completion_once") ||
      !identical(confirmation$preview_fingerprint, preview$preview_fingerprint) ||
      !identical(confirmation$base_bundle_fingerprint, preview$base_bundle_fingerprint) ||
      !identical(confirmation$context, context) || !identical(confirmation$provider_access_authorized, FALSE) ||
      !identical(confirmation$calculation_authorized, FALSE) || !identical(confirmation$confirmed, TRUE)) {
    .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
  }
  fingerprint <- confirmation$confirmation_fingerprint
  body <- confirmation[names(confirmation) != "confirmation_fingerprint"]
  if (!is.character(fingerprint) || length(fingerprint) != 1L || !identical(fingerprint, .bootstrap_completion_fp(body))) {
    .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
  }
  now <- as.POSIXct(.bootstrap_completion_utc(now_utc, "bootstrap_completion_confirmation_invalid"), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  issued <- as.POSIXct(.bootstrap_completion_utc(confirmation$issued_at_utc, "bootstrap_completion_confirmation_invalid"), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  expires <- as.POSIXct(.bootstrap_completion_utc(confirmation$expires_at_utc, "bootstrap_completion_confirmation_invalid"), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (now < issued || now > expires) .bootstrap_completion_abort("bootstrap_completion_confirmation_expired")
  confirmation
}

.bootstrap_completion_execute_schema <- function(connection, schema_sql) {
  lines <- strsplit(schema_sql, "\n", fixed = TRUE)[[1L]]
  buffer <- character()
  in_trigger <- FALSE
  for (line in lines) {
    trimmed <- trimws(line)
    if (!length(buffer) && !nzchar(trimmed)) next
    if (!length(buffer) && grepl("^CREATE TRIGGER ", trimmed)) in_trigger <- TRUE
    buffer <- c(buffer, line)
    complete <- if (in_trigger) endsWith(trimmed, "END;") else endsWith(trimmed, ";")
    if (complete) {
      DBI::dbExecute(connection, paste(buffer, collapse = "\n"))
      buffer <- character()
      in_trigger <- FALSE
    }
  }
  if (length(buffer) && nzchar(trimws(paste(buffer, collapse = "\n")))) {
    .bootstrap_completion_abort("bootstrap_completion_target_invalid")
  }
  invisible(TRUE)
}

.bootstrap_completion_sql_value <- function(value) {
  if (is.null(value)) NA else value
}

minimal_bootstrap_completion_failpoints_v1 <- function() c("after_binding", "after_receipt", "after_revision")

minimal_bootstrap_completion_execute_v1 <- function(
  base_path, completion_path, schema_sql, context, command, confirmation, authorizer, now_utc, failpoint = NULL
) {
  .bootstrap_completion_boundary({
    .bootstrap_completion_dependencies()
    context <- .bootstrap_completion_context(context)
    if (inherits(authorizer, "spot_bootstrap_completion_authorizer_v1") && is.list(confirmation) &&
        is.character(confirmation$confirmation_fingerprint) && length(confirmation$confirmation_fingerprint) == 1L &&
        exists(confirmation$confirmation_fingerprint, envir = authorizer, inherits = FALSE)) {
      .bootstrap_completion_abort("bootstrap_completion_confirmation_consumed")
    }
    preview <- minimal_bootstrap_completion_preview_v1(base_path, completion_path, context, command)
    confirmed <- .bootstrap_completion_verify_confirmation(confirmation, preview, context, now_utc)
    .bootstrap_completion_consume(authorizer, confirmed)
    if (!is.null(failpoint) && !failpoint %in% minimal_bootstrap_completion_failpoints_v1()) {
      .bootstrap_completion_abort("bootstrap_completion_command_invalid")
    }
    base <- .bootstrap_completion_base(base_path, context)
    on.exit(DBI::dbDisconnect(base$connection), add = TRUE)
    target <- .bootstrap_completion_path(completion_path, FALSE, "bootstrap_completion_target_invalid")
    fresh <- !file.exists(target)
    temporary <- if (fresh) file.path(dirname(target), paste0(".", basename(target), ".tmp-", Sys.getpid())) else NULL
    connection <- NULL
    committed <- FALSE
    on.exit({
      if (!is.null(connection) && DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE)
      if (!committed && fresh && !is.null(temporary) && file.exists(temporary)) unlink(temporary, force = TRUE)
    }, add = TRUE)
    if (fresh) {
      if (!is.character(schema_sql) || length(schema_sql) != 1L || !grepl("CREATE TABLE completion_store_binding", schema_sql, fixed = TRUE) || file.exists(temporary)) {
        .bootstrap_completion_abort("bootstrap_completion_target_invalid")
      }
      connection <- DBI::dbConnect(RSQLite::SQLite(), dbname = temporary, flags = RSQLite::SQLITE_RWC)
      DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
      DBI::dbExecute(connection, "PRAGMA busy_timeout=0")
      DBI::dbExecute(connection, "BEGIN IMMEDIATE")
      .bootstrap_completion_execute_schema(connection, schema_sql)
      DBI::dbExecute(
        connection,
        "INSERT INTO completion_store_binding VALUES (1,310,?,?,?,?,?)",
        params = list(context$tenant_id, context$user_id, context$data_space_id, base$bundle_fingerprint, now_utc)
      )
    } else {
      store <- .bootstrap_completion_store(target, context, base$bundle_fingerprint, read_only = FALSE, allow_absent = FALSE)
      connection <- store$connection
      DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    }
    if (identical(failpoint, "after_binding")) .bootstrap_completion_abort("bootstrap_completion_synthetic_failpoint")
    latest_store <- list(connection = connection)
    current <- .bootstrap_completion_command(base, latest_store, command)
    if (!identical(current$revision_no, preview$revision_no) || !identical(current$before, preview$before) || !identical(current$after, preview$after)) {
      .bootstrap_completion_abort("bootstrap_completion_confirmation_invalid")
    }
    payload <- list(action_type = current$action_type, entity_id = current$entity_id, revision_no = current$revision_no, after = current$after)
    payload_fp <- .bootstrap_completion_fp(payload)
    command_id <- paste0("bcm_", substr(.bootstrap_completion_fp(list(payload_fp, confirmed$confirmation_fingerprint)), 1L, 24L))
    DBI::dbExecute(
      connection,
      "INSERT INTO completion_command_receipt VALUES (?,?,?,?,?,?,?)",
      params = list(command_id, current$action_type, current$entity_id, current$revision_no, payload_fp, confirmed$confirmation_fingerprint, now_utc)
    )
    if (identical(failpoint, "after_receipt")) .bootstrap_completion_abort("bootstrap_completion_synthetic_failpoint")
    revision_fp <- .bootstrap_completion_fp(list(command_id, current$entity_id, current$revision_no))
    if (current$action_type == "complete_asset_metadata") {
      DBI::dbExecute(connection, "INSERT INTO asset_metadata_revision VALUES (?,?,?,?,?,?,?,?)", params = list(
        paste0("amr_", substr(revision_fp, 1L, 24L)), current$entity_id, current$revision_no,
        .bootstrap_completion_sql_value(current$after$quantity_scale),
        .bootstrap_completion_sql_value(current$after$valuation_method),
        .bootstrap_completion_sql_value(current$after$isin), command_id, now_utc
      ))
    } else if (current$action_type == "complete_account_metadata") {
      DBI::dbExecute(connection, "INSERT INTO account_metadata_revision VALUES (?,?,?,?,?,?)", params = list(
        paste0("acr_", substr(revision_fp, 1L, 24L)), current$entity_id, current$revision_no,
        .bootstrap_completion_sql_value(current$after$institution_label), command_id, now_utc
      ))
    } else {
      DBI::dbExecute(connection, "INSERT INTO transaction_completion_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", params = list(
        paste0("tcr_", substr(revision_fp, 1L, 24L)), current$entity_id, current$revision_no,
        .bootstrap_completion_sql_value(current$after$related_account_id),
        .bootstrap_completion_sql_value(current$after$unit_price_decimal),
        .bootstrap_completion_sql_value(current$after$gross_amount_decimal),
        .bootstrap_completion_sql_value(current$after$fee_decimal),
        .bootstrap_completion_sql_value(current$after$tax_decimal),
        .bootstrap_completion_sql_value(current$after$memo),
        current$after$identity_status, current$after$basis_status, current$after$calculation_status,
        command_id, now_utc
      ))
    }
    if (identical(failpoint, "after_revision")) .bootstrap_completion_abort("bootstrap_completion_synthetic_failpoint")
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) .bootstrap_completion_abort("bootstrap_completion_transaction_failed")
    DBI::dbCommit(connection)
    DBI::dbDisconnect(connection)
    connection <- NULL
    if (fresh) {
      Sys.chmod(temporary, mode = "0600")
      if (!file.rename(temporary, target)) .bootstrap_completion_abort("bootstrap_completion_transaction_failed")
    }
    committed <- TRUE
    list(
      result_contract_version = 1L,
      status = "bootstrap_completion_committed",
      action_type = current$action_type,
      revision_no = current$revision_no,
      command_fingerprint = payload_fp,
      provider_access = FALSE,
      calculation_started = FALSE,
      base_store_write = FALSE,
      automatic_retry = FALSE
    )
  }, "bootstrap_completion_transaction_failed")
}
