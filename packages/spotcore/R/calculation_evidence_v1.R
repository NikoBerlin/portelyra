calculation_evidence_error_codes_v1 <- function() {
  c(
    "calculation_evidence_input_invalid",
    "calculation_evidence_output_invalid",
    "calculation_evidence_output_exists",
    "calculation_evidence_symlink_forbidden",
    "calculation_evidence_serialization_invalid",
    "calculation_evidence_publication_failed"
  )
}

.calculation_evidence_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !code %in% calculation_evidence_error_codes_v1()) {
    stop("calculation_evidence_error_code_unregistered", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_calculation_evidence_error_v1", "error", "condition")
  )
}

.calculation_evidence_abort_v1 <- function(code) stop(.calculation_evidence_condition_v1(code))

.calculation_evidence_fingerprint_v1 <- function(raw_value) {
  digest::digest(raw_value, algo = "sha256", serialize = FALSE)
}

.calculation_evidence_json_raw_v1 <- function(value) {
  text <- jsonlite::toJSON(
    value, auto_unbox = TRUE, null = "null", na = "null", digits = NA,
    pretty = FALSE, dataframe = "rows", POSIXt = "ISO8601", UTC = TRUE
  )
  charToRaw(enc2utf8(paste0(text, "\n")))
}

.calculation_evidence_escape_csv_v1 <- function(value, field_name) {
  if (length(value) != 1L) .calculation_evidence_abort_v1("calculation_evidence_serialization_invalid")
  if (is.na(value)) return("")
  value <- enc2utf8(as.character(value))
  if (grepl("[\r\n]", value, perl = TRUE)) {
    .calculation_evidence_abort_v1("calculation_evidence_serialization_invalid")
  }
  if (!grepl("_decimal$", field_name, perl = TRUE) && grepl("^[=+@]", value, perl = TRUE)) {
    .calculation_evidence_abort_v1("calculation_evidence_serialization_invalid")
  }
  if (!grepl("_decimal$", field_name, perl = TRUE) && grepl("^-", value, perl = TRUE) &&
      !grepl("^-?[0-9]+$", value, perl = TRUE)) {
    .calculation_evidence_abort_v1("calculation_evidence_serialization_invalid")
  }
  if (grepl('[,\"]', value, perl = TRUE)) {
    value <- paste0('"', gsub('"', '""', value, fixed = TRUE), '"')
  }
  value
}

.calculation_evidence_csv_raw_v1 <- function(table) {
  if (!is.data.frame(table) || !length(names(table)) || anyDuplicated(names(table)) ||
      any(!grepl("^[a-z][a-z0-9_]{1,79}$", names(table), perl = TRUE))) {
    .calculation_evidence_abort_v1("calculation_evidence_input_invalid")
  }
  header <- paste(names(table), collapse = ",")
  lines <- character(nrow(table) + 1L)
  lines[[1L]] <- header
  if (nrow(table)) {
    for (row_index in seq_len(nrow(table))) {
      values <- vapply(seq_along(table), function(column_index) {
        .calculation_evidence_escape_csv_v1(
          table[[column_index]][[row_index]], names(table)[[column_index]]
        )
      }, character(1L))
      lines[[row_index + 1L]] <- paste(values, collapse = ",")
    }
  }
  charToRaw(enc2utf8(paste0(paste(lines, collapse = "\n"), "\n")))
}

.calculation_evidence_regular_parent_v1 <- function(output_path) {
  if (!is.character(output_path) || length(output_path) != 1L || is.na(output_path) || !nzchar(output_path)) {
    .calculation_evidence_abort_v1("calculation_evidence_output_invalid")
  }
  expanded <- path.expand(output_path)
  if (file.exists(expanded) || dir.exists(expanded)) {
    if (nzchar(Sys.readlink(expanded))) .calculation_evidence_abort_v1("calculation_evidence_symlink_forbidden")
    .calculation_evidence_abort_v1("calculation_evidence_output_exists")
  }
  parent <- dirname(expanded)
  if (!dir.exists(parent) || nzchar(Sys.readlink(parent))) {
    .calculation_evidence_abort_v1("calculation_evidence_output_invalid")
  }
  normalized_parent <- tryCatch(
    normalizePath(parent, winslash = "/", mustWork = TRUE),
    error = function(error) NULL
  )
  if (is.null(normalized_parent) || !dir.exists(normalized_parent)) {
    .calculation_evidence_abort_v1("calculation_evidence_output_invalid")
  }
  file.path(normalized_parent, basename(expanded))
}

.calculation_evidence_write_file_v1 <- function(path, raw_value) {
  connection <- file(path, open = "wb")
  on.exit(close(connection), add = TRUE)
  writeBin(raw_value, connection, useBytes = TRUE)
  close(connection)
  on.exit(NULL, add = FALSE)
  if (!isTRUE(Sys.chmod(path, mode = "0600"))) {
    .calculation_evidence_abort_v1("calculation_evidence_publication_failed")
  }
  invisible(TRUE)
}

publish_calculation_evidence_v1 <- function(projection, output_path) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  required <- c(
    "profile_id", "algorithm_version", "portfolio_ref", "context_binding_fingerprint",
    "input_fingerprint", "evidence_cutoff_at_utc", "tables", "table_roles",
    "reconciliation", "boundaries"
  )
  valid <- is.list(projection) && all(required %in% names(projection)) &&
    identical(projection$profile_id, "realized_fifo_v1") &&
    is.character(projection$algorithm_version) && length(projection$algorithm_version) == 1L &&
    grepl("^[a-z][a-z0-9_.-]{2,39}$", projection$algorithm_version, perl = TRUE) &&
    is.character(projection$portfolio_ref) && length(projection$portfolio_ref) == 1L &&
    grepl("^pfr_[a-f0-9]{32}$", projection$portfolio_ref, perl = TRUE) &&
    is.character(projection$context_binding_fingerprint) &&
    grepl("^[a-f0-9]{64}$", projection$context_binding_fingerprint, perl = TRUE) &&
    is.character(projection$input_fingerprint) &&
    grepl("^[a-f0-9]{64}$", projection$input_fingerprint, perl = TRUE) &&
    is.character(projection$evidence_cutoff_at_utc) &&
    grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", projection$evidence_cutoff_at_utc, perl = TRUE) &&
    is.list(projection$tables) && length(projection$tables) > 0L &&
    identical(names(projection$tables), names(projection$table_roles)) &&
    all(grepl("^[a-z][a-z0-9-]{1,78}\\.csv$", names(projection$tables), perl = TRUE)) &&
    is.list(projection$reconciliation) && is.list(projection$boundaries)
  if (!isTRUE(valid)) .calculation_evidence_abort_v1("calculation_evidence_input_invalid")

  target <- .calculation_evidence_regular_parent_v1(output_path)
  if (!dir.create(target, recursive = FALSE, mode = "0700", showWarnings = FALSE)) {
    if (file.exists(target) || dir.exists(target)) {
      .calculation_evidence_abort_v1("calculation_evidence_output_exists")
    }
    .calculation_evidence_abort_v1("calculation_evidence_publication_failed")
  }
  completed <- FALSE
  on.exit({
    if (!completed && dir.exists(target) && !nzchar(Sys.readlink(target))) {
      unlink(target, recursive = TRUE, force = TRUE)
    }
  }, add = TRUE)
  if (!isTRUE(Sys.chmod(target, mode = "0700"))) {
    .calculation_evidence_abort_v1("calculation_evidence_publication_failed")
  }

  file_entries <- vector("list", length(projection$tables))
  for (index in seq_along(projection$tables)) {
    file_name <- names(projection$tables)[[index]]
    table <- projection$tables[[index]]
    raw_value <- .calculation_evidence_csv_raw_v1(table)
    .calculation_evidence_write_file_v1(file.path(target, file_name), raw_value)
    file_entries[[index]] <- list(
      file_name = file_name,
      content_role = unname(projection$table_roles[[index]]),
      row_count = as.integer(nrow(table)),
      sha256 = .calculation_evidence_fingerprint_v1(raw_value)
    )
  }

  manifest_body <- list(
    calculation_evidence_version = 1L,
    profile_id = projection$profile_id,
    status = "completed",
    algorithm_version = projection$algorithm_version,
    portfolio_ref = projection$portfolio_ref,
    context_binding_fingerprint = projection$context_binding_fingerprint,
    input_fingerprint = projection$input_fingerprint,
    evidence_cutoff_at_utc = projection$evidence_cutoff_at_utc,
    files = file_entries,
    reconciliation = projection$reconciliation,
    boundaries = projection$boundaries
  )
  manifest_body$artifact_fingerprint <- .calculation_evidence_fingerprint_v1(
    .calculation_evidence_json_raw_v1(manifest_body)
  )
  manifest_raw <- .calculation_evidence_json_raw_v1(manifest_body)
  .calculation_evidence_write_file_v1(file.path(target, "evidence-manifest.json"), manifest_raw)
  completed <- TRUE
  structure(
    list(
      status = "evidence_published",
      artifact_fingerprint = manifest_body$artifact_fingerprint,
      file_count = as.integer(length(file_entries)),
      row_count = as.integer(sum(vapply(file_entries, function(item) item$row_count, integer(1L))))
    ),
    class = c("spot_calculation_evidence_result_v1", "list")
  )
}
