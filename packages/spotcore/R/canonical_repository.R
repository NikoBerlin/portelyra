canonical_repository_error_codes <- function() {
  c(
    "canonical_repository_dependency_missing",
    "canonical_repository_context_invalid",
    "canonical_repository_role_not_authorized",
    "canonical_repository_contract_source_invalid",
    "canonical_repository_path_invalid",
    "canonical_repository_symlink_rejected",
    "canonical_repository_lock_unavailable",
    "canonical_repository_schema_mismatch",
    "canonical_repository_binding_mismatch",
    "canonical_repository_settings_invalid",
    "canonical_repository_integrity_invalid",
    "canonical_repository_bootstrap_failed",
    "canonical_repository_read_failed",
    "canonical_repository_boundary_failed"
  )
}

.canonical_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% canonical_repository_error_codes()) {
    stop("unregistered_canonical_repository_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_canonical_repository_error", "error", "condition")
  )
}

.canonical_abort <- function(code) stop(.canonical_condition(code))

.canonical_boundary_eval <- function(expression, fallback = "canonical_repository_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_canonical_repository_error = function(error) error,
    error = function(error) .canonical_condition(fallback)
  )
  if (inherits(result, "spot_canonical_repository_error")) stop(result)
  result
}

.canonical_dependencies_valid <- function() {
  all(vapply(c("DBI", "RSQLite", "digest"), requireNamespace, logical(1), quietly = TRUE))
}

.canonical_context_check <- function(context, allowed_roles) {
  valid <- tryCatch(runtime_context_valid(context), error = function(error) FALSE)
  if (!isTRUE(valid)) .canonical_abort("canonical_repository_context_invalid")
  if (!context$role %in% allowed_roles) .canonical_abort("canonical_repository_role_not_authorized")
  invisible(TRUE)
}

.canonical_symlink <- function(path) {
  target <- suppressWarnings(Sys.readlink(path))
  length(target) == 1L && !is.na(target) && nzchar(target)
}

.canonical_utc_valid <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) {
    return(FALSE)
  }
  parsed <- suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  !is.na(parsed) && identical(format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), value)
}

.canonical_sha256_file <- function(path) {
  connection <- file(path, open = "rb")
  on.exit(close(connection), add = TRUE)
  bytes <- readBin(connection, what = "raw", n = file.info(path)$size)
  digest::digest(bytes, algo = "sha256", serialize = FALSE)
}

.canonical_contract_sources <- function(contract_root) {
  if (!is.character(contract_root) || length(contract_root) != 1L || is.na(contract_root) || !dir.exists(contract_root) || .canonical_symlink(contract_root)) {
    .canonical_abort("canonical_repository_contract_source_invalid")
  }
  normalized <- tryCatch(normalizePath(contract_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized)) .canonical_abort("canonical_repository_contract_source_invalid")
  paths <- c(
    v2 = file.path(normalized, "v2", "schema.sql"),
    v2_1 = file.path(normalized, "v2.1", "migrate-from-v2.sql")
  )
  expected <- c(
    v2 = "87330714406d1d022fffe2d05262ddf944d1a29aa8694b435e034a85bb6868f4",
    v2_1 = "d229de5e2e58e1ff7fd2846c2d44aeea64935dd1212a9072b54c8263e60817d8"
  )
  for (name in names(paths)) {
    path <- paths[[name]]
    if (!file.exists(path) || dir.exists(path) || .canonical_symlink(path) || !identical(.canonical_sha256_file(path), expected[[name]])) {
      .canonical_abort("canonical_repository_contract_source_invalid")
    }
  }
  paths
}

# Neue Ordner festschreiben (#568): Liegt der Datenraum in gocryptfs (Passwortschutz), schreibt gocryptfs die gocryptfs.diriv eines neuen
# Ordners nicht sofort fest; nach einem harten Ausschalten waere der Ordner unlesbar. `sync -f <verschluesselter Quellordner>` (syncfs nur
# dieses Dateisystems), wie settle_new_directory_v1 in workers/reference/durable_storage_v1.py. Scheitert es, geht es ohne weiter.
.canonical_settle_new_directory <- function(path, mountinfo = NULL, runner = NULL) {
  tool <- Sys.which("sync")
  lines <- if (is.null(mountinfo)) tryCatch(readLines("/proc/self/mountinfo", warn = FALSE), error = function(error) character()) else mountinfo
  if (!nzchar(tool) || !length(lines)) return(invisible(FALSE))
  unescape <- function(value) {
    for (code in c("040", "011", "012")) value <- gsub(paste0("\\", code), intToUtf8(strtoi(code, 8L)), value, fixed = TRUE)
    gsub("\\134", "\\", value, fixed = TRUE)
  }
  target <- normalizePath(path, winslash = "/", mustWork = FALSE)
  best <- NULL
  for (line in lines) {
    parts <- strsplit(line, " ", fixed = TRUE)[[1L]]
    separator <- match("-", parts)
    if (is.na(separator) || separator < 6L || length(parts) < separator + 2L) next
    mount <- unescape(parts[[5L]])
    inside <- identical(mount, "/") || identical(target, mount) || startsWith(target, paste0(sub("/+$", "", mount), "/"))
    if (inside && (is.null(best) || nchar(mount) > nchar(best$mount)))
      best <- list(mount = mount, type = parts[[separator + 1L]], source = unescape(parts[[separator + 2L]]))
  }
  if (is.null(best) || !identical(best$type, "fuse.gocryptfs") || !startsWith(best$source, "/")) return(invisible(FALSE))
  run <- if (is.null(runner)) function(source) suppressWarnings(tryCatch(
    system2(tool, c("-f", shQuote(source)), stdout = FALSE, stderr = FALSE), error = function(error) 1L)) else runner
  invisible(identical(as.integer(run(best$source)), 0L))
}

.canonical_create_data_space <- function(context) {
  target <- runtime_data_space_path(context)
  segments <- c(context$tenant_id, context$user_id, context$data_space_id)
  current <- context$data_root
  created_any <- FALSE
  for (segment in segments) {
    current <- file.path(current, segment)
    if (file.exists(current) && !dir.exists(current)) .canonical_abort("canonical_repository_path_invalid")
    if (!dir.exists(current)) {
      created <- dir.create(current, mode = "0700", showWarnings = FALSE)
      if (!created) .canonical_abort("canonical_repository_path_invalid")
      created_any <- TRUE
    }
    if (.canonical_symlink(current) || !dir.exists(current)) .canonical_abort("canonical_repository_symlink_rejected")
    suppressWarnings(Sys.chmod(current, mode = "0700"))
  }
  if (created_any) .canonical_settle_new_directory(current)
  if (!identical(normalizePath(target, winslash = "/", mustWork = TRUE), normalizePath(current, winslash = "/", mustWork = TRUE))) {
    .canonical_abort("canonical_repository_path_invalid")
  }
  target
}

.canonical_acquire_lock <- function(data_space_path) {
  lock <- file.path(data_space_path, "canonical.writer.lock")
  if (.canonical_symlink(lock)) .canonical_abort("canonical_repository_symlink_rejected")
  if (!dir.create(lock, mode = "0700", showWarnings = FALSE)) {
    .canonical_abort("canonical_repository_lock_unavailable")
  }
  lock
}

.canonical_read_script <- function(path) {
  connection <- file(path, open = "rb")
  on.exit(close(connection), add = TRUE)
  raw <- readBin(connection, what = "raw", n = file.info(path)$size)
  if (any(raw == as.raw(0L))) .canonical_abort("canonical_repository_contract_source_invalid")
  enc2utf8(rawToChar(raw))
}

.canonical_execute_contract_script <- function(connection, script) {
  lines <- strsplit(script, "\n", fixed = TRUE)[[1]]
  statement <- character()
  trigger <- FALSE
  executed <- 0L
  for (line in lines) {
    trimmed <- trimws(line)
    if (!length(statement) && (!nzchar(trimmed) || startsWith(trimmed, "--"))) next
    statement <- c(statement, line)
    if (length(statement) == 1L) {
      trigger <- grepl("^CREATE[[:space:]]+(TEMP[[:space:]]+|TEMPORARY[[:space:]]+)?TRIGGER[[:space:]]", trimmed, ignore.case = TRUE)
    }
    complete <- if (trigger) identical(trimmed, "END;") else endsWith(trimmed, ";")
    if (complete) {
      sql <- paste(statement, collapse = "\n")
      DBI::dbExecute(connection, sql)
      executed <- executed + 1L
      statement <- character()
      trigger <- FALSE
    }
  }
  if (length(statement) || executed < 1L) .canonical_abort("canonical_repository_contract_source_invalid")
  invisible(executed)
}

.canonical_length_prefix <- function(length_value) {
  if (!is.numeric(length_value) || length(length_value) != 1L || is.na(length_value) || length_value < 0 || length_value > 2^53) {
    .canonical_abort("canonical_repository_schema_mismatch")
  }
  value <- floor(length_value)
  output <- raw(8L)
  for (index in 8:1) {
    output[[index]] <- as.raw(value %% 256)
    value <- floor(value / 256)
  }
  output
}

canonical_repository_schema_fingerprint_v1 <- function(connection) {
  .canonical_boundary_eval({
    rows <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT type, name, tbl_name, sql FROM sqlite_master",
        "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL",
        "ORDER BY type, name"
      )
    )
    material <- raw()
    for (row_index in seq_len(nrow(rows))) {
      for (column in c("type", "name", "tbl_name", "sql")) {
        value <- rows[[column]][[row_index]]
        if (!is.character(value) || length(value) != 1L || is.na(value)) .canonical_abort("canonical_repository_schema_mismatch")
        bytes <- charToRaw(enc2utf8(value))
        material <- c(material, .canonical_length_prefix(length(bytes)), bytes)
      }
    }
    digest::digest(material, algo = "sha256", serialize = FALSE)
  })
}

.canonical_validate_connection <- function(connection, context, expected_fingerprint = "092c8af40530258df6c4bc9760612b843ffc7fa86bb2a9854bfd16b157bab7c0") {
  version <- DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]
  if (!identical(as.integer(version), 201L)) .canonical_abort("canonical_repository_schema_mismatch")
  if (!identical(canonical_repository_schema_fingerprint_v1(connection), expected_fingerprint)) {
    .canonical_abort("canonical_repository_schema_mismatch")
  }
  binding <- DBI::dbGetQuery(
    connection,
    "SELECT singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc FROM store_binding"
  )
  if (
    nrow(binding) != 1L ||
    !identical(as.integer(binding$singleton_id[[1]]), 1L) ||
    !identical(as.integer(binding$schema_version[[1]]), 201L) ||
    !identical(binding$tenant_id[[1]], context$tenant_id) ||
    !identical(binding$user_id[[1]], context$user_id) ||
    !identical(binding$data_space_id[[1]], context$data_space_id) ||
    !.canonical_utc_valid(binding$created_at_utc[[1]])
  ) {
    .canonical_abort("canonical_repository_binding_mismatch")
  }
  foreign_keys <- DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]]
  if (!identical(as.integer(foreign_keys), 1L)) .canonical_abort("canonical_repository_settings_invalid")
  integrity <- DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]]
  foreign_key_check <- DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")
  if (!identical(integrity, "ok") || nrow(foreign_key_check) != 0L) {
    .canonical_abort("canonical_repository_integrity_invalid")
  }
  invisible(binding)
}

.canonical_connect_read <- function(context) {
  path <- runtime_canonical_path(context)
  if (.canonical_symlink(path)) .canonical_abort("canonical_repository_symlink_rejected")
  if (!file.exists(path) || dir.exists(path)) .canonical_abort("canonical_repository_path_invalid")
  connection <- DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RO)
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, "PRAGMA query_only = ON")
    query_only <- DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]
    if (!identical(as.integer(query_only), 1L)) .canonical_abort("canonical_repository_settings_invalid")
    .canonical_validate_connection(connection, context)
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    stop(error)
  })
  if (!valid) .canonical_abort("canonical_repository_read_failed")
  connection
}

.canonical_status_from_connection <- function(connection, status) {
  tables <- c(
    portfolios = "portfolio",
    accounts = "account",
    assets = "asset",
    transactions = "transaction_record",
    postings = "transaction_posting",
    receipts = "canonical_import_receipt"
  )
  counts <- vapply(tables, function(table) {
    as.integer(DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1]])
  }, integer(1))
  list(
    contract_version = 1L,
    status = status,
    schema_version = 201L,
    schema_fingerprint = canonical_repository_schema_fingerprint_v1(connection),
    query_only = as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]),
    foreign_keys = as.integer(DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]]),
    counts = as.list(counts)
  )
}

canonical_repository_status_v1 <- function(context) {
  .canonical_boundary_eval({
    if (!.canonical_dependencies_valid()) .canonical_abort("canonical_repository_dependency_missing")
    .canonical_context_check(context, c("desktop_owner", "portfolio_worker", "tax_worker"))
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    .canonical_status_from_connection(connection, "ready")
  }, fallback = "canonical_repository_read_failed")
}

canonical_repository_bootstrap_v1 <- function(context, contract_root, created_at_utc) {
  .canonical_boundary_eval({
    if (!.canonical_dependencies_valid()) .canonical_abort("canonical_repository_dependency_missing")
    .canonical_context_check(context, "desktop_owner")
    if (!.canonical_utc_valid(created_at_utc)) .canonical_abort("canonical_repository_context_invalid")
    sources <- .canonical_contract_sources(contract_root)
    data_space <- .canonical_create_data_space(context)
    lock <- .canonical_acquire_lock(data_space)
    on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
    target <- runtime_canonical_path(context)
    if (.canonical_symlink(target)) .canonical_abort("canonical_repository_symlink_rejected")
    if (file.exists(target)) {
      status <- canonical_repository_status_v1(context)
      status$status <- "already_initialized"
      return(status)
    }
    temporary <- tempfile(pattern = ".canonical-bootstrap-", tmpdir = data_space, fileext = ".sqlite.tmp")
    temporary_owned <- TRUE
    on.exit(if (temporary_owned && file.exists(temporary)) unlink(temporary, force = TRUE), add = TRUE)
    connection <- DBI::dbConnect(RSQLite::SQLite(), dbname = temporary, flags = RSQLite::SQLITE_RWC)
    connected <- TRUE
    on.exit(if (connected && DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
    tryCatch({
      DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
      DBI::dbExecute(connection, "PRAGMA journal_mode = DELETE")
      DBI::dbExecute(connection, "PRAGMA synchronous = FULL")
      .canonical_execute_contract_script(connection, .canonical_read_script(sources[["v2"]]))
      .canonical_execute_contract_script(connection, .canonical_read_script(sources[["v2_1"]]))
      DBI::dbExecute(connection, "BEGIN IMMEDIATE")
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO store_binding",
          "(singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc)",
          "VALUES (1, 201, ?, ?, ?, ?)"
        ),
        params = list(context$tenant_id, context$user_id, context$data_space_id, created_at_utc)
      )
      DBI::dbExecute(connection, "COMMIT")
      DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
      .canonical_validate_connection(connection, context)
    }, error = function(error) {
      if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
      if (inherits(error, "spot_canonical_repository_error")) stop(error)
      .canonical_abort("canonical_repository_bootstrap_failed")
    })
    DBI::dbDisconnect(connection)
    connected <- FALSE
    suppressWarnings(Sys.chmod(temporary, mode = "0600"))
    if (file.exists(target) || !file.rename(temporary, target)) {
      .canonical_abort("canonical_repository_bootstrap_failed")
    }
    temporary_owned <- FALSE
    suppressWarnings(Sys.chmod(target, mode = "0600"))
    status <- canonical_repository_status_v1(context)
    status$status <- "created"
    status
  }, fallback = "canonical_repository_bootstrap_failed")
}
