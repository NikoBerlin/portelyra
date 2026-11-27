desktop_derivative_capability_error_codes_v1 <- function() c(
  "desktop_derivative_capability_context_invalid",
  "desktop_derivative_capability_source_invalid",
  "desktop_derivative_capability_preview_required",
  "desktop_derivative_capability_confirmation_required",
  "desktop_derivative_capability_confirmation_consumed",
  "desktop_derivative_capability_confirmation_expired",
  "desktop_derivative_capability_source_changed",
  "desktop_derivative_capability_lock_unavailable",
  "desktop_derivative_capability_migration_failed",
  "desktop_derivative_capability_recovery_required",
  "desktop_derivative_capability_storage_invalid",
  "synthetic_desktop_derivative_capability_failpoint",
  "desktop_derivative_capability_boundary_failed"
)

.derivative_capability_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% desktop_derivative_capability_error_codes_v1()) {
    stop("desktop_derivative_capability_unregistered_error", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_desktop_derivative_capability_error_v1", "error", "condition")
  )
}

.derivative_capability_abort_v1 <- function(code) stop(.derivative_capability_condition_v1(code))

.derivative_capability_boundary_v1 <- function(expression) {
  result <- tryCatch(
    expression,
    spot_desktop_derivative_capability_error_v1 = function(error) error,
    spot_runtime_error = function(error) .derivative_capability_condition_v1("desktop_derivative_capability_context_invalid"),
    spot_canonical_repository_error = function(error) .derivative_capability_condition_v1("desktop_derivative_capability_source_invalid"),
    spot_catalog_data_command_error = function(error) .derivative_capability_condition_v1("desktop_derivative_capability_source_invalid"),
    error = function(error) .derivative_capability_condition_v1("desktop_derivative_capability_boundary_failed")
  )
  if (inherits(result, "spot_desktop_derivative_capability_error_v1")) stop(result)
  result
}

.derivative_capability_v202_schema_fingerprint_v1 <- "1d46be68f51afdf27315c9466f9c23440893ff666f1c0bf90ab7015fd94c1524"
.derivative_capability_v202_source_fingerprint_v1 <- "c3e09e59d254fa40d641bdcadbf44a9ee22b742fa98087252ed0e86b470103af"
.derivative_capability_confirmation_code_v1 <- "DERIVAT_AKTIVIEREN"

.derivative_capability_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .derivative_capability_abort_v1("desktop_derivative_capability_context_invalid")
  }
  invisible(context)
}

.derivative_capability_sha_v1 <- function(value) {
  digest::digest(charToRaw(enc2utf8(value)), algo = "sha256", serialize = FALSE)
}

.derivative_capability_fingerprint_v1 <- function(value) {
  payload <- jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE)
  .derivative_capability_sha_v1(payload)
}

.derivative_capability_migration_path_v1 <- function(contract_root) {
  if (!is.character(contract_root) || length(contract_root) != 1L || is.na(contract_root)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  root <- tryCatch(normalizePath(contract_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(root)) .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  path <- file.path(root, "v2.2", "migrate-from-v2.1.sql")
  if (!file.exists(path) || dir.exists(path) || .canonical_symlink(path) ||
      !identical(.canonical_sha256_file(path), .derivative_capability_v202_source_fingerprint_v1)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  path
}

.derivative_capability_native_v202_v1 <- function(connection, context, expected_query_only) {
  if (as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]) != 202L ||
      !identical(canonical_repository_schema_fingerprint_v1(connection), .derivative_capability_v202_schema_fingerprint_v1)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  binding <- DBI::dbGetQuery(
    connection,
    "SELECT singleton_id,schema_version,tenant_id,user_id,data_space_id,created_at_utc FROM store_binding"
  )
  if (nrow(binding) != 1L || as.integer(binding$singleton_id[[1]]) != 1L ||
      as.integer(binding$schema_version[[1]]) != 202L ||
      !identical(binding$tenant_id[[1]], context$tenant_id) ||
      !identical(binding$user_id[[1]], context$user_id) ||
      !identical(binding$data_space_id[[1]], context$data_space_id) ||
      !.canonical_utc_valid(binding$created_at_utc[[1]]) ||
      as.integer(DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]]) != 1L ||
      as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]) != expected_query_only ||
      !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  legacy <- sum(vapply(
    c("portfolio", "account", "asset", "transaction_record", "data_command_audit"),
    function(table) DBI::dbGetQuery(
      connection,
      paste0("SELECT count(*) AS n FROM ", table, " WHERE origin_type!='native' OR origin_ref IS NOT NULL")
    )$n[[1]], numeric(1L)
  ))
  master_receipts <- DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM canonical_master_import_receipt")$n[[1]]
  if (legacy != 0L || master_receipts != 0L) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  invisible(TRUE)
}

.derivative_capability_open_v1 <- function(context, read_only) {
  path <- runtime_canonical_path(context)
  if (!file.exists(path) || dir.exists(path) || .canonical_symlink(path)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  }
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = if (read_only) RSQLite::SQLITE_RO else RSQLite::SQLITE_RW),
    error = function(error) .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  )
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
    DBI::dbExecute(connection, paste0("PRAGMA query_only=", if (read_only) "ON" else "OFF"))
    DBI::dbExecute(connection, "PRAGMA busy_timeout=0")
    version <- as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]])
    if (version == 201L) .canonical_validate_connection(connection, context)
    else if (version == 202L) .derivative_capability_native_v202_v1(connection, context, if (read_only) 1L else 0L)
    else .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    stop(error)
  })
  if (!valid) .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
  connection
}

.derivative_capability_counts_v1 <- function(connection) list(
  portfolio_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM portfolio")$n[[1]]),
  account_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM account")$n[[1]]),
  asset_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM asset")$n[[1]]),
  transaction_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM transaction_record")$n[[1]]),
  posting_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM transaction_posting")$n[[1]]),
  audit_count = as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM data_command_audit")$n[[1]])
)

.derivative_capability_data_fingerprint_v1 <- function(connection) {
  orders <- list(
    portfolio = "portfolio_id", account = "account_id", asset = "asset_id",
    transaction_record = "transaction_id", transaction_posting = "posting_id",
    data_command_audit = "command_id"
  )
  rows <- lapply(names(orders), function(table) {
    frame <- DBI::dbGetQuery(connection, paste0("SELECT * FROM ", table, " ORDER BY ", orders[[table]]))
    lapply(seq_len(nrow(frame)), function(index) {
      values <- lapply(frame[index, , drop = FALSE], function(value) {
        item <- value[[1]]
        if (length(item) != 1L || is.na(item)) NULL else if (is.integer(item)) as.integer(item) else as.character(item)
      })
      names(values) <- names(frame)
      values
    })
  })
  names(rows) <- names(orders)
  .derivative_capability_fingerprint_v1(rows)
}

.derivative_capability_preview_shape_v1 <- function(value) {
  required <- c(
    "contract_version", "status", "source_schema_version", "target_schema_version",
    "source_fingerprint", "source_data_fingerprint", "migration_source_fingerprint",
    "counts", "confirmation_required", "product_write", "activity_write", "cash_write",
    "provider_access", "network_access", "preview_fingerprint"
  )
  is.list(value) && identical(names(value), required) && identical(value$contract_version, 1L) &&
    value$status %in% c("ready_for_confirmation", "already_enabled") &&
    value$source_schema_version %in% c(201L, 202L) && identical(value$target_schema_version, 202L) &&
    all(vapply(value[c("source_fingerprint", "source_data_fingerprint", "migration_source_fingerprint", "preview_fingerprint")], function(item) {
      is.character(item) && length(item) == 1L && !is.na(item) && grepl("^[a-f0-9]{64}$", item)
    }, logical(1L))) && is.list(value$counts) &&
    identical(value$confirmation_required, identical(value$status, "ready_for_confirmation")) &&
    all(vapply(value[c("product_write", "activity_write", "cash_write", "provider_access", "network_access")], identical, logical(1L), FALSE))
}

.derivative_capability_evidence_state_v1 <- function(context) {
  root <- file.path(runtime_data_space_path(context), "derivative-capability-v1")
  if (!file.exists(root)) return("absent")
  if (!dir.exists(root) || .canonical_symlink(root) || !.desktop_product_owner_mode_v1(root, directory = TRUE)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  attempts <- file.path(root, "attempts"); receipts <- file.path(root, "receipts")
  if (!dir.exists(attempts) || !dir.exists(receipts) || .canonical_symlink(attempts) || .canonical_symlink(receipts) ||
      !.desktop_product_owner_mode_v1(attempts, directory = TRUE) || !.desktop_product_owner_mode_v1(receipts, directory = TRUE)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  attempt_names <- list.files(attempts, all.files = TRUE, no.. = TRUE)
  receipt_names <- list.files(receipts, all.files = TRUE, no.. = TRUE)
  if (any(!grepl("^dca_[a-f0-9]{32}[.]json$", attempt_names)) ||
      any(!grepl("^dcr_[a-f0-9]{32}[.]json$", receipt_names))) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  attempt_paths <- file.path(attempts, attempt_names); receipt_paths <- file.path(receipts, receipt_names)
  if (any(vapply(c(attempt_paths, receipt_paths), function(path) {
    .canonical_symlink(path) || !file.exists(path) || dir.exists(path) || !.desktop_product_owner_mode_v1(path)
  }, logical(1L)))) .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  attempt_suffixes <- sub("^dca_([a-f0-9]{32})[.]json$", "\\1", attempt_names)
  receipt_suffixes <- sub("^dcr_([a-f0-9]{32})[.]json$", "\\1", receipt_names)
  if (!length(attempt_suffixes) || !setequal(attempt_suffixes, receipt_suffixes)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_recovery_required")
  }
  "completed"
}

desktop_derivative_capability_preview_v1 <- function(context, contract_root) {
  .derivative_capability_boundary_v1({
    .derivative_capability_context_v1(context)
    evidence_state <- .derivative_capability_evidence_state_v1(context)
    migration <- .derivative_capability_migration_path_v1(contract_root)
    connection <- .derivative_capability_open_v1(context, TRUE)
    on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
    version <- as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]])
    if (version == 201L && identical(evidence_state, "completed")) {
      .derivative_capability_abort_v1("desktop_derivative_capability_recovery_required")
    }
    base <- list(
      contract_version = 1L,
      status = if (version == 201L) "ready_for_confirmation" else "already_enabled",
      source_schema_version = version,
      target_schema_version = 202L,
      source_fingerprint = .canonical_sha256_file(runtime_canonical_path(context)),
      source_data_fingerprint = .derivative_capability_data_fingerprint_v1(connection),
      migration_source_fingerprint = .canonical_sha256_file(migration),
      counts = .derivative_capability_counts_v1(connection),
      confirmation_required = version == 201L,
      product_write = FALSE,
      activity_write = FALSE,
      cash_write = FALSE,
      provider_access = FALSE,
      network_access = FALSE
    )
    preview <- c(base, list(preview_fingerprint = .derivative_capability_fingerprint_v1(base)))
    if (!.derivative_capability_preview_shape_v1(preview)) .derivative_capability_abort_v1("desktop_derivative_capability_source_invalid")
    preview
  })
}

new_desktop_derivative_capability_authorizer_v1 <- function() {
  value <- new.env(hash = TRUE, parent = emptyenv())
  value$consumed <- new.env(hash = TRUE, parent = emptyenv())
  class(value) <- "spot_desktop_derivative_capability_authorizer_v1"
  value
}

.derivative_capability_time_v1 <- function(value) {
  if (!.canonical_utc_valid(value)) .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_required")
  parsed <- suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  if (is.na(parsed)) .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_required")
  parsed
}

desktop_derivative_capability_confirmation_v1 <- function(
  preview, confirmation_code, confirmed_at_utc, expires_at_utc
) {
  .derivative_capability_boundary_v1({
    if (!.derivative_capability_preview_shape_v1(preview) ||
        !identical(preview$status, "ready_for_confirmation") ||
        !identical(confirmation_code, .derivative_capability_confirmation_code_v1)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_required")
    }
    confirmed <- .derivative_capability_time_v1(confirmed_at_utc)
    expires <- .derivative_capability_time_v1(expires_at_utc)
    if (expires <= confirmed) .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_required")
    base <- list(
      contract_version = 1L,
      preview_fingerprint = preview$preview_fingerprint,
      source_fingerprint = preview$source_fingerprint,
      source_data_fingerprint = preview$source_data_fingerprint,
      migration_source_fingerprint = preview$migration_source_fingerprint,
      confirmation_code_fingerprint = .derivative_capability_sha_v1(confirmation_code),
      confirmed_at_utc = confirmed_at_utc,
      expires_at_utc = expires_at_utc
    )
    c(base, list(confirmation_fingerprint = .derivative_capability_fingerprint_v1(base)))
  })
}

.derivative_capability_owner_directory_v1 <- function(path) {
  if (file.exists(path) && (!dir.exists(path) || .canonical_symlink(path))) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  if (!dir.exists(path) && !dir.create(path, mode = "0700", showWarnings = FALSE)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  suppressWarnings(Sys.chmod(path, mode = "0700"))
  normalized <- tryCatch(normalizePath(path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || .canonical_symlink(normalized)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  }
  normalized
}

.derivative_capability_write_json_new_v1 <- function(path, value) {
  if (file.exists(path) || dir.exists(path) || .canonical_symlink(path)) {
    .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_consumed")
  }
  parent <- .derivative_capability_owner_directory_v1(dirname(path))
  incoming <- tempfile(pattern = ".incoming-", tmpdir = parent)
  on.exit(if (file.exists(incoming)) unlink(incoming, force = TRUE), add = TRUE)
  payload <- paste0(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE), "\n")
  connection <- file(incoming, open = "wb")
  tryCatch({
    writeBin(charToRaw(enc2utf8(payload)), connection)
    close(connection)
  }, error = function(error) {
    try(close(connection), silent = TRUE)
    .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  })
  suppressWarnings(Sys.chmod(incoming, mode = "0600"))
  if (!file.rename(incoming, path)) .derivative_capability_abort_v1("desktop_derivative_capability_storage_invalid")
  suppressWarnings(Sys.chmod(path, mode = "0600"))
  invisible(path)
}

.derivative_capability_evidence_paths_v1 <- function(context, confirmation_fingerprint) {
  root <- .derivative_capability_owner_directory_v1(file.path(runtime_data_space_path(context), "derivative-capability-v1"))
  attempts <- .derivative_capability_owner_directory_v1(file.path(root, "attempts"))
  receipts <- .derivative_capability_owner_directory_v1(file.path(root, "receipts"))
  suffix <- substr(confirmation_fingerprint, 1L, 32L)
  list(
    attempt = file.path(attempts, paste0("dca_", suffix, ".json")),
    receipt = file.path(receipts, paste0("dcr_", suffix, ".json"))
  )
}

desktop_derivative_capability_apply_v1 <- function(
  context, contract_root, preview, confirmation, authorizer, applied_at_utc,
  failpoint = "none"
) {
  .derivative_capability_boundary_v1({
    .derivative_capability_context_v1(context)
    if (!.derivative_capability_preview_shape_v1(preview) || !identical(preview$status, "ready_for_confirmation") ||
        !inherits(authorizer, "spot_desktop_derivative_capability_authorizer_v1") || !is.environment(authorizer$consumed) ||
        !failpoint %in% c("none", "after_attempt") || !is.list(confirmation) ||
        !identical(confirmation$preview_fingerprint, preview$preview_fingerprint) ||
        !identical(confirmation$source_fingerprint, preview$source_fingerprint) ||
        !identical(confirmation$source_data_fingerprint, preview$source_data_fingerprint) ||
        !identical(confirmation$migration_source_fingerprint, preview$migration_source_fingerprint) ||
        !identical(confirmation$confirmation_code_fingerprint, .derivative_capability_sha_v1(.derivative_capability_confirmation_code_v1)) ||
        !is.character(confirmation$confirmation_fingerprint) || !grepl("^[a-f0-9]{64}$", confirmation$confirmation_fingerprint)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_preview_required")
    }
    expected_confirmation <- confirmation[names(confirmation) != "confirmation_fingerprint"]
    if (!identical(confirmation$confirmation_fingerprint, .derivative_capability_fingerprint_v1(expected_confirmation))) {
      .derivative_capability_abort_v1("desktop_derivative_capability_preview_required")
    }
    applied <- .derivative_capability_time_v1(applied_at_utc)
    confirmed <- .derivative_capability_time_v1(confirmation$confirmed_at_utc)
    expires <- .derivative_capability_time_v1(confirmation$expires_at_utc)
    if (applied < confirmed || applied > expires) .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_expired")
    key <- confirmation$confirmation_fingerprint
    if (exists(key, envir = authorizer$consumed, inherits = FALSE)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_consumed")
    }
    assign(key, TRUE, envir = authorizer$consumed)
    migration <- .derivative_capability_migration_path_v1(contract_root)
    paths <- .derivative_capability_evidence_paths_v1(context, key)
    if (file.exists(paths$attempt) || file.exists(paths$receipt)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_confirmation_consumed")
    }
    attempt <- list(
      contract_version = 1L,
      status = "consumed_before_domain_write",
      preview_fingerprint = preview$preview_fingerprint,
      confirmation_fingerprint = key,
      confirmation_code_fingerprint = confirmation$confirmation_code_fingerprint,
      source_fingerprint = preview$source_fingerprint,
      source_data_fingerprint = preview$source_data_fingerprint,
      migration_source_fingerprint = preview$migration_source_fingerprint,
      consumed_at_utc = applied_at_utc,
      product_write = FALSE,
      activity_write = FALSE,
      cash_write = FALSE,
      provider_access = FALSE,
      network_access = FALSE
    )
    .derivative_capability_write_json_new_v1(paths$attempt, attempt)
    if (failpoint == "after_attempt") .derivative_capability_abort_v1("synthetic_desktop_derivative_capability_failpoint")
    data_space <- runtime_data_space_path(context)
    lock <- tryCatch(.canonical_acquire_lock(data_space), error = function(error) NULL)
    if (is.null(lock)) .derivative_capability_abort_v1("desktop_derivative_capability_lock_unavailable")
    on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
    canonical_path <- runtime_canonical_path(context)
    if (!identical(.canonical_sha256_file(canonical_path), preview$source_fingerprint)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_source_changed")
    }
    connection <- .derivative_capability_open_v1(context, FALSE)
    on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
    if (as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]) != 201L ||
        !identical(.derivative_capability_data_fingerprint_v1(connection), preview$source_data_fingerprint)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_source_changed")
    }
    migration_error <- tryCatch({
      script <- .canonical_read_script(migration)
      .canonical_execute_contract_script(connection, script)
      NULL
    }, error = function(error) error)
    if (!is.null(migration_error)) {
      if (DBI::dbIsValid(connection) && DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]] != 201L) {
        .derivative_capability_abort_v1("desktop_derivative_capability_recovery_required")
      }
      .derivative_capability_abort_v1("desktop_derivative_capability_migration_failed")
    }
    DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
    .derivative_capability_native_v202_v1(connection, context, 0L)
    if (!identical(.derivative_capability_data_fingerprint_v1(connection), preview$source_data_fingerprint)) {
      .derivative_capability_abort_v1("desktop_derivative_capability_recovery_required")
    }
    counts <- .derivative_capability_counts_v1(connection)
    DBI::dbDisconnect(connection)
    receipt_base <- list(
      contract_version = 1L,
      status = "enabled",
      source_schema_version = 201L,
      target_schema_version = 202L,
      preview_fingerprint = preview$preview_fingerprint,
      confirmation_fingerprint = key,
      source_fingerprint = preview$source_fingerprint,
      source_data_fingerprint = preview$source_data_fingerprint,
      migration_source_fingerprint = preview$migration_source_fingerprint,
      target_fingerprint = .canonical_sha256_file(canonical_path),
      counts = counts,
      committed_at_utc = applied_at_utc,
      generic_derivative_catalog_enabled = TRUE,
      generic_derivative_activity_enabled_by_release_patch = TRUE,
      derivative_coupled_transaction_enabled = FALSE,
      lifecycle_metadata_inferred = FALSE,
      automatic_cash_posting_enabled = FALSE,
      provider_access = FALSE,
      network_access = FALSE
    )
    receipt <- c(receipt_base, list(receipt_fingerprint = .derivative_capability_fingerprint_v1(receipt_base)))
    receipt_error <- tryCatch({
      .derivative_capability_write_json_new_v1(paths$receipt, receipt)
      NULL
    }, spot_desktop_derivative_capability_error_v1 = function(error) error)
    if (!is.null(receipt_error)) .derivative_capability_abort_v1("desktop_derivative_capability_recovery_required")
    receipt
  })
}
