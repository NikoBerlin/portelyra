import_data_command_error_codes <- function() {
  c(
    "fingerprint_float_forbidden",
    "fingerprint_unicode_not_nfc",
    "fingerprint_control_character_forbidden",
    "fingerprint_key_invalid",
    "fingerprint_value_type_invalid",
    "runtime_role_not_authorized",
    "runtime_context_invalid",
    "staging_connection_in_transaction",
    "staging_query_only_not_enforced",
    "staging_schema_version_mismatch",
    "staging_contract_schema_mismatch",
    "staging_contract_catalog_mismatch",
    "staging_foreign_key_invalid",
    "staging_integrity_invalid",
    "staging_run_count_invalid",
    "staging_seal_count_invalid",
    "productive_import_not_enabled",
    "staging_runtime_context_mismatch",
    "staging_not_ready",
    "staging_gate_missing",
    "staging_gate_closed",
    "staging_fingerprint_mismatch",
    "transaction_semantics_invalid",
    "canonical_schema_version_mismatch",
    "canonical_contract_schema_mismatch",
    "canonical_store_binding_missing",
    "canonical_runtime_context_mismatch",
    "canonical_foreign_keys_disabled",
    "canonical_connection_query_only",
    "canonical_foreign_key_invalid",
    "idempotency_conflict",
    "target_sandbox_not_empty",
    "confirmation_missing",
    "confirmation_invalid",
    "confirmation_challenge_duplicate",
    "confirmation_not_authorized",
    "confirmation_already_consumed",
    "confirmation_time_invalid",
    "confirmation_fingerprint_mismatch",
    "confirmation_scope_mismatch",
    "confirmation_expired_or_time_invalid",
    "confirmation_validity_window_exceeded",
    "canonical_connection_already_in_transaction",
    "command_preflight_failed",
    "candidate_portfolio_count_invalid",
    "canonical_integrity_invalid",
    "canonical_transaction_failed",
    "synthetic_failpoint"
  )
}

.import_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% import_data_command_error_codes()) {
    stop("unregistered_import_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_import_data_command_error", "error", "condition")
  )
}

.import_abort <- function(code) stop(.import_condition(code))

.import_boundary_eval <- function(expression, fallback = "command_preflight_failed") {
  result <- tryCatch(
    expression,
    spot_import_data_command_error = function(error) error,
    spot_runtime_error = function(error) .import_condition("runtime_context_invalid"),
    spot_canonical_repository_error = function(error) .import_condition(fallback),
    error = function(error) .import_condition(fallback)
  )
  if (inherits(result, "spot_import_data_command_error")) stop(result)
  result
}

.import_staging_schema_fingerprint <- "faee80169fdd043972ef1058c311ca4203794e534f79869934b5f13dee30fc86"
.import_staging_catalog_fingerprint <- "0b1849fdc38c01685afa543263240ac8691084847e15197b13af731fbe64ce5d"
.import_canonical_schema_fingerprint <- "092c8af40530258df6c4bc9760612b843ffc7fa86bb2a9854bfd16b157bab7c0"
.import_staging_schema_version <- 1001L
.import_canonical_schema_version <- 201L
.import_contract_version <- 1L

.import_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .import_abort("runtime_context_invalid")
  }
  if (!identical(context$role, "desktop_owner")) .import_abort("runtime_role_not_authorized")
  invisible(TRUE)
}

.import_ascii_string <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) {
    .import_abort("fingerprint_value_type_invalid")
  }
  codepoints <- utf8ToInt(enc2utf8(value))
  if (any(codepoints > 127L)) .import_abort("fingerprint_unicode_not_nfc")
  if (any(codepoints < 32L | codepoints == 127L)) .import_abort("fingerprint_control_character_forbidden")
  enc2utf8(value)
}

.import_sort_json_value <- function(value) {
  if (is.null(value)) return(NULL)
  if (is.logical(value)) {
    if (length(value) != 1L || is.na(value)) .import_abort("fingerprint_value_type_invalid")
    return(value)
  }
  if (is.integer(value)) {
    if (length(value) != 1L || is.na(value)) .import_abort("fingerprint_value_type_invalid")
    return(value)
  }
  if (is.double(value)) .import_abort("fingerprint_float_forbidden")
  if (is.character(value)) return(.import_ascii_string(value))
  if (!is.list(value)) .import_abort("fingerprint_value_type_invalid")
  value_names <- names(value)
  if (!is.null(value_names)) {
    if (length(value_names) != length(value) || anyNA(value_names) || any(!nzchar(value_names))) {
      .import_abort("fingerprint_key_invalid")
    }
    if (any(vapply(value_names, function(name) any(utf8ToInt(name) > 127L), logical(1)))) {
      .import_abort("fingerprint_key_invalid")
    }
    value <- value[order(value_names, method = "radix")]
  }
  lapply(value, .import_sort_json_value)
}

.import_canonical_json_bytes <- function(value) {
  normalized <- .import_sort_json_value(value)
  text <- jsonlite::toJSON(
    normalized,
    auto_unbox = TRUE,
    null = "null",
    na = "null",
    digits = NA,
    POSIXt = "ISO8601",
    UTC = TRUE,
    pretty = FALSE
  )
  charToRaw(enc2utf8(as.character(text)))
}

.import_fingerprint <- function(value) {
  digest::digest(.import_canonical_json_bytes(value), algo = "sha256", serialize = FALSE)
}

.import_nul_material <- function(parts) {
  if (!is.character(parts) || anyNA(parts)) .import_abort("fingerprint_value_type_invalid")
  output <- raw()
  for (index in seq_along(parts)) {
    if (index > 1L) output <- c(output, as.raw(0L))
    output <- c(output, charToRaw(enc2utf8(parts[[index]])))
  }
  output
}

.import_hash_parts <- function(parts) {
  digest::digest(.import_nul_material(parts), algo = "sha256", serialize = FALSE)
}

.import_frame_rows <- function(frame) {
  if (!is.data.frame(frame)) .import_abort("command_preflight_failed")
  if (nrow(frame) == 0L) return(list())
  lapply(seq_len(nrow(frame)), function(index) {
    row <- vector("list", ncol(frame))
    names(row) <- names(frame)
    for (column in names(frame)) {
      value <- frame[[column]][[index]]
      if (length(value) != 1L || (length(value) && is.na(value))) {
        row[column] <- list(NULL)
      } else if (is.integer(value)) {
        row[column] <- list(as.integer(value))
      } else if (is.logical(value)) {
        row[column] <- list(as.logical(value))
      } else if (is.character(value)) {
        row[column] <- list(as.character(value))
      } else {
        .import_abort("fingerprint_value_type_invalid")
      }
    }
    row
  })
}

.import_fetch_rows <- function(connection, sql, params = NULL) {
  frame <- if (is.null(params)) DBI::dbGetQuery(connection, sql) else DBI::dbGetQuery(connection, sql, params = params)
  .import_frame_rows(frame)
}

.import_fetch_one <- function(connection, sql, code, params = NULL) {
  rows <- .import_fetch_rows(connection, sql, params)
  if (length(rows) != 1L) .import_abort(code)
  rows[[1L]]
}

.import_schema_fingerprint <- function(connection) {
  tryCatch(
    canonical_repository_schema_fingerprint_v1(connection),
    spot_canonical_repository_error = function(error) .import_abort("command_preflight_failed"),
    error = function(error) .import_abort("command_preflight_failed")
  )
}

.import_staging_catalogs <- function(connection) {
  list(
    schema_contract = .import_fetch_rows(
      connection,
      paste(
        "SELECT schema_id, source_kind, header_fingerprint, status, projection_id,",
        "fixture_only, legacy_read_only_enabled, provenance",
        "FROM schema_contract ORDER BY schema_id"
      )
    ),
    diagnostic_catalog = .import_fetch_rows(
      connection,
      paste(
        "SELECT diagnostic_code, default_severity, scope, publish_blocking, safe_description",
        "FROM diagnostic_catalog ORDER BY diagnostic_code"
      )
    ),
    reconciliation_requirements = .import_fetch_rows(
      connection,
      paste(
        "SELECT requirement_id, applicability, gate_level, dimension_contract, safe_description",
        "FROM reconciliation_requirement ORDER BY requirement_id"
      )
    )
  )
}

.import_candidate_manifest <- function(connection) {
  run <- .import_fetch_one(connection, "SELECT * FROM import_run", "staging_run_count_invalid")
  run_id <- run$import_run_id
  portfolios <- .import_fetch_rows(
    connection,
    "SELECT staged_portfolio_id, display_name, base_currency FROM staged_portfolio WHERE import_run_id=? ORDER BY staged_portfolio_id",
    list(run_id)
  )
  accounts <- .import_fetch_rows(
    connection,
    paste(
      "SELECT staged_account_id, staged_portfolio_id, display_name, account_type",
      "FROM staged_account WHERE import_run_id=? ORDER BY staged_account_id"
    ),
    list(run_id)
  )
  assets <- .import_fetch_rows(
    connection,
    paste(
      "SELECT staged_asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method, isin",
      "FROM staged_asset WHERE import_run_id=? ORDER BY staged_asset_id"
    ),
    list(run_id)
  )
  transactions <- .import_fetch_rows(
    connection,
    paste(
      "SELECT staged_transaction_id, staged_portfolio_id, transaction_type, effective_at_utc, local_date",
      "FROM staged_transaction WHERE import_run_id=? ORDER BY staged_transaction_id"
    ),
    list(run_id)
  )
  postings <- .import_fetch_rows(
    connection,
    paste(
      "SELECT staged_posting_id, staged_transaction_id, sequence_no, staged_account_id, staged_asset_id,",
      "posting_role, quantity_decimal, unit_price_decimal, price_currency, valuation_amount_decimal, valuation_currency",
      "FROM staged_posting WHERE import_run_id=?",
      "ORDER BY staged_transaction_id, sequence_no, staged_posting_id"
    ),
    list(run_id)
  )
  counts <- list(
    portfolio_count = as.integer(length(portfolios)),
    account_count = as.integer(length(accounts)),
    asset_count = as.integer(length(assets)),
    transaction_count = as.integer(length(transactions)),
    posting_count = as.integer(length(postings))
  )
  manifest <- list(
    candidate_contract_version = .import_contract_version,
    source_contract_version = run$contract_version,
    staging_schema_version = .import_staging_schema_version,
    source_import_run_id = run_id,
    source_set_fingerprint = run$source_set_fingerprint,
    parser_bundle_fingerprint = run$parser_bundle_fingerprint,
    tenant_id = run$tenant_id,
    user_id = run$user_id,
    sandbox_id = run$sandbox_id,
    counts = counts,
    portfolios = portfolios,
    accounts = accounts,
    assets = assets,
    transactions = transactions,
    postings = postings
  )
  .import_canonical_json_bytes(manifest)
  manifest
}

.import_artifact_manifest <- function(connection, candidate_fingerprint) {
  run <- .import_fetch_one(connection, "SELECT * FROM import_run", "staging_run_count_invalid")
  run_id <- run$import_run_id
  run_keys <- c(
    "import_run_id", "contract_version", "import_profile", "execution_mode", "tenant_id", "user_id",
    "sandbox_id", "source_root_token", "source_set_fingerprint", "parser_bundle_fingerprint", "file_limit",
    "total_byte_limit", "total_row_limit", "started_at_utc"
  )
  catalogs <- .import_staging_catalogs(connection)
  manifest <- list(
    artifact_contract_version = .import_contract_version,
    candidate_fingerprint = candidate_fingerprint,
    staging_contract_schema_fingerprint = .import_schema_fingerprint(connection),
    staging_contract_catalog_fingerprint = .import_fingerprint(catalogs),
    run = run[run_keys],
    schema_contract = catalogs$schema_contract,
    diagnostic_catalog = catalogs$diagnostic_catalog,
    reconciliation_requirements = catalogs$reconciliation_requirements,
    source_files = .import_fetch_rows(
      connection,
      paste(
        "SELECT source_file_id, source_alias, source_kind, schema_id, parser_status, byte_size, data_row_count,",
        "header_fingerprint, content_fingerprint_before, content_fingerprint_after",
        "FROM source_file WHERE import_run_id=? ORDER BY source_file_id"
      ),
      list(run_id)
    ),
    source_rows = .import_fetch_rows(
      connection,
      paste(
        "SELECT source_row_id, source_file_id, data_row_ordinal, source_row_fingerprint, disposition",
        "FROM source_row WHERE import_run_id=? ORDER BY source_file_id, data_row_ordinal"
      ),
      list(run_id)
    ),
    source_row_mappings = .import_fetch_rows(
      connection,
      paste(
        "SELECT source_row_mapping_id, source_row_id, entity_kind, staged_portfolio_id, staged_account_id,",
        "staged_asset_id, staged_transaction_id",
        "FROM source_row_mapping WHERE import_run_id=? ORDER BY source_row_mapping_id"
      ),
      list(run_id)
    ),
    diagnostics = .import_fetch_rows(
      connection,
      paste(
        "SELECT diagnostic_id, diagnostic_code, source_file_id, source_row_id, entity_kind, entity_ref,",
        "field_key, safe_detail_code, evidence_fingerprint",
        "FROM import_diagnostic WHERE import_run_id=? ORDER BY diagnostic_id"
      ),
      list(run_id)
    ),
    reconciliation_results = .import_fetch_rows(
      connection,
      paste(
        "SELECT reconciliation_result_id, requirement_id, is_summary, dimension_kind, dimension_ref,",
        "applicable, status, reason_code, evidence_fingerprint",
        "FROM reconciliation_result WHERE import_run_id=?",
        "ORDER BY requirement_id, is_summary DESC, dimension_kind, dimension_ref, reconciliation_result_id"
      ),
      list(run_id)
    ),
    reconciliation_metrics = .import_fetch_rows(
      connection,
      paste(
        "SELECT metric.reconciliation_metric_id, metric.reconciliation_result_id, metric.metric_kind,",
        "metric.expected_value, metric.actual_value, metric.difference_decimal, metric.tolerance_decimal",
        "FROM reconciliation_metric metric",
        "JOIN reconciliation_result result ON result.reconciliation_result_id=metric.reconciliation_result_id",
        "WHERE result.import_run_id=?",
        "ORDER BY metric.reconciliation_result_id, metric.reconciliation_metric_id"
      ),
      list(run_id)
    ),
    gate = .import_fetch_one(
      connection,
      "SELECT * FROM reconciliation_gate WHERE import_run_id=?",
      "staging_gate_missing",
      list(run_id)
    )
  )
  .import_canonical_json_bytes(manifest)
  manifest
}

.import_compute_staging <- function(connection) {
  candidate_manifest <- .import_candidate_manifest(connection)
  candidate_fingerprint <- .import_fingerprint(candidate_manifest)
  artifact_manifest <- .import_artifact_manifest(connection, candidate_fingerprint)
  artifact_fingerprint <- .import_fingerprint(artifact_manifest)
  list(
    candidate_manifest = candidate_manifest,
    artifact_manifest = artifact_manifest,
    candidate_fingerprint = candidate_fingerprint,
    artifact_fingerprint = artifact_fingerprint
  )
}

.import_connection_in_transaction <- function(connection) {
  began <- tryCatch({
    DBI::dbExecute(connection, "BEGIN")
    TRUE
  }, error = function(error) FALSE)
  if (began) {
    try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    return(FALSE)
  }
  TRUE
}

.import_staging_path <- function(staging_path) {
  if (!is.character(staging_path) || length(staging_path) != 1L || is.na(staging_path) || !nzchar(staging_path)) {
    .import_abort("staging_query_only_not_enforced")
  }
  if (!file.exists(staging_path) || dir.exists(staging_path) || .canonical_symlink(staging_path)) {
    .import_abort("staging_query_only_not_enforced")
  }
  normalized <- tryCatch(normalizePath(staging_path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || .canonical_symlink(normalized)) .import_abort("staging_query_only_not_enforced")
  info <- file.info(normalized)
  if (nrow(info) != 1L || is.na(info$mode[[1]]) || bitwAnd(as.integer(info$mode[[1]]), 146L) != 0L) {
    .import_abort("staging_query_only_not_enforced")
  }
  normalized
}

new_import_staging_capability_v1 <- function(staging_path) {
  .import_boundary_eval({
    structure(
      list(path = .import_staging_path(staging_path)),
      class = "spot_import_staging_capability_v1"
    )
  })
}

.import_staging_capability_path <- function(capability) {
  if (!inherits(capability, "spot_import_staging_capability_v1") || !is.list(capability) ||
      !identical(names(capability), "path")) {
    .import_abort("staging_query_only_not_enforced")
  }
  path <- .import_staging_path(capability$path)
  if (!identical(path, capability$path)) .import_abort("staging_query_only_not_enforced")
  path
}

.import_validate_staging_connection <- function(connection, context) {
  version <- DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]
  if (!identical(as.integer(version), .import_staging_schema_version)) .import_abort("staging_schema_version_mismatch")
  if (!identical(.import_schema_fingerprint(connection), .import_staging_schema_fingerprint)) {
    .import_abort("staging_contract_schema_mismatch")
  }
  catalogs <- .import_staging_catalogs(connection)
  if (!identical(.import_fingerprint(catalogs), .import_staging_catalog_fingerprint)) {
    .import_abort("staging_contract_catalog_mismatch")
  }
  if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .import_abort("staging_foreign_key_invalid")
  }
  if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
    .import_abort("staging_integrity_invalid")
  }
  run <- .import_fetch_one(connection, "SELECT * FROM import_run", "staging_run_count_invalid")
  seal <- .import_fetch_one(connection, "SELECT * FROM import_seal", "staging_seal_count_invalid")
  if (!identical(run$execution_mode, "fixture")) .import_abort("productive_import_not_enabled")
  if (!identical(run$tenant_id, context$tenant_id) || !identical(run$user_id, context$user_id) ||
      !identical(run$sandbox_id, context$data_space_id)) {
    .import_abort("staging_runtime_context_mismatch")
  }
  if (!identical(seal$import_run_id, run$import_run_id) || !identical(seal$outcome, "ready_for_confirmation")) {
    .import_abort("staging_not_ready")
  }
  gate <- .import_fetch_one(
    connection,
    "SELECT * FROM reconciliation_gate WHERE import_run_id=?",
    "staging_gate_missing",
    list(run$import_run_id)
  )
  if (!identical(as.integer(gate$ready_for_confirmation), 1L)) .import_abort("staging_gate_closed")
  computed <- .import_compute_staging(connection)
  if (!identical(seal$candidate_fingerprint, computed$candidate_fingerprint) ||
      !identical(seal$artifact_fingerprint, computed$artifact_fingerprint)) {
    .import_abort("staging_fingerprint_mismatch")
  }
  structure(
    c(
      list(run = run, seal = seal, counts = computed$candidate_manifest$counts),
      computed
    ),
    class = "spot_validated_import_staging_v1"
  )
}

.import_open_validated_staging <- function(context, staging_capability) {
  path <- .import_staging_capability_path(staging_capability)
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RO),
    error = function(error) .import_abort("staging_query_only_not_enforced")
  )
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  if (.import_connection_in_transaction(connection)) .import_abort("staging_connection_in_transaction")
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, "PRAGMA query_only = ON")
    DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
  }, error = function(error) .import_abort("staging_query_only_not_enforced"))
  if (!identical(as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]), 1L)) {
    .import_abort("staging_query_only_not_enforced")
  }
  DBI::dbExecute(connection, "BEGIN")
  transaction_open <- TRUE
  on.exit(if (transaction_open && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
  validated <- .import_validate_staging_connection(connection, context)
  DBI::dbExecute(connection, "ROLLBACK")
  transaction_open <- FALSE
  validated
}

.import_decimal <- function(value, allow_zero = TRUE, positive_only = FALSE) {
  tryCatch(
    .transaction_decimal_parse(value, allow_zero = allow_zero, positive_only = positive_only),
    error = function(error) .import_abort("transaction_semantics_invalid")
  )
}

.import_decimal_scale <- function(value) {
  pieces <- strsplit(value, ".", fixed = TRUE)[[1]]
  if (length(pieces) == 2L) nchar(pieces[[2]], type = "bytes") else 0L
}

.import_decimal_equal <- function(left, right) {
  isTRUE(tryCatch(.transaction_decimal_equal(left, right), error = function(error) FALSE))
}

.import_index_rows <- function(rows, key) {
  if (!is.list(rows) || !length(rows)) .import_abort("transaction_semantics_invalid")
  identifiers <- vapply(rows, function(row) {
    value <- row[[key]]
    if (!is.character(value) || length(value) != 1L || is.na(value)) .import_abort("transaction_semantics_invalid")
    value
  }, character(1))
  if (anyDuplicated(identifiers)) .import_abort("transaction_semantics_invalid")
  result <- rows
  names(result) <- identifiers
  result
}

.import_cash_value <- function(posting, account, asset, currency) {
  if (!account$account_type %in% c("cash", "bank") || !identical(asset$asset_type, "cash") ||
      !identical(asset$valuation_method, "unit_value") || !identical(asset$price_currency, currency)) {
    .import_abort("transaction_semantics_invalid")
  }
  if (!is.null(posting$unit_price_decimal) || !is.null(posting$price_currency) ||
      !identical(posting$valuation_currency, currency)) {
    .import_abort("transaction_semantics_invalid")
  }
  quantity <- .import_decimal(posting$quantity_decimal, allow_zero = FALSE)
  valuation <- .import_decimal(posting$valuation_amount_decimal)
  if (!.import_decimal_equal(quantity, valuation) || .import_decimal_scale(posting$quantity_decimal) > asset$quantity_scale) {
    .import_abort("transaction_semantics_invalid")
  }
  quantity
}

.import_validate_transaction_semantics <- function(candidate) {
  tryCatch({
    portfolios <- .import_index_rows(candidate$portfolios, "staged_portfolio_id")
    accounts <- .import_index_rows(candidate$accounts, "staged_account_id")
    assets <- .import_index_rows(candidate$assets, "staged_asset_id")
    transactions <- .import_index_rows(candidate$transactions, "staged_transaction_id")
    postings <- .import_index_rows(candidate$postings, "staged_posting_id")
    if (length(portfolios) != 1L || !length(transactions) || any(vapply(postings, function(posting) {
      !posting$staged_transaction_id %in% names(transactions)
    }, logical(1)))) .import_abort("transaction_semantics_invalid")
    transaction_order <- order(
      vapply(transactions, `[[`, character(1), "effective_at_utc"),
      vapply(transactions, `[[`, character(1), "staged_transaction_id"),
      method = "radix"
    )
    fifo <- list()
    zero <- .transaction_decimal_zero()
    for (transaction in transactions[transaction_order]) {
      if (!transaction$transaction_type %in% c("buy", "sell") ||
          !.canonical_utc_valid(transaction$effective_at_utc) || !.transaction_date_valid(transaction$local_date)) {
        .import_abort("transaction_semantics_invalid")
      }
      portfolio <- portfolios[[transaction$staged_portfolio_id]]
      if (is.null(portfolio) || !grepl("^[A-Z]{3}$", portfolio$base_currency)) {
        .import_abort("transaction_semantics_invalid")
      }
      currency <- portfolio$base_currency
      tx_postings <- Filter(
        function(posting) identical(posting$staged_transaction_id, transaction$staged_transaction_id),
        postings
      )
      if (!length(tx_postings)) .import_abort("transaction_semantics_invalid")
      tx_postings <- tx_postings[order(vapply(tx_postings, `[[`, integer(1), "sequence_no"))]
      sequences <- unname(vapply(tx_postings, `[[`, integer(1), "sequence_no"))
      if (!identical(sequences, seq_along(tx_postings))) .import_abort("transaction_semantics_invalid")
      roles <- unname(vapply(tx_postings, `[[`, character(1), "posting_role"))
      if (any(!roles %in% c("asset", "cash", "fee", "tax")) ||
          sum(roles == "asset") != 1L || sum(roles == "cash") != 1L ||
          sum(roles == "fee") > 1L || sum(roles == "tax") > 1L ||
          (transaction$transaction_type == "buy" && any(roles == "tax"))) {
        .import_abort("transaction_semantics_invalid")
      }
      expected_roles <- c("asset", "cash", if (any(roles == "fee")) "fee", if (any(roles == "tax")) "tax")
      if (!identical(roles, expected_roles)) .import_abort("transaction_semantics_invalid")
      asset_posting <- tx_postings[[which(roles == "asset")]]
      cash_posting <- tx_postings[[which(roles == "cash")]]
      account <- accounts[[asset_posting$staged_account_id]]
      traded_asset <- assets[[asset_posting$staged_asset_id]]
      cash_account <- accounts[[cash_posting$staged_account_id]]
      cash_asset <- assets[[cash_posting$staged_asset_id]]
      if (any(vapply(list(account, traded_asset, cash_account, cash_asset), is.null, logical(1))) ||
          !identical(account$staged_portfolio_id, transaction$staged_portfolio_id) ||
          !identical(cash_account$staged_portfolio_id, transaction$staged_portfolio_id) ||
          !account$account_type %in% c("securities", "crypto_wallet") ||
          identical(traded_asset$asset_type, "cash") || !identical(traded_asset$price_currency, currency)) {
        .import_abort("transaction_semantics_invalid")
      }
      quantity <- .import_decimal(asset_posting$quantity_decimal, allow_zero = FALSE)
      if (.import_decimal_scale(asset_posting$quantity_decimal) > traded_asset$quantity_scale ||
          (transaction$transaction_type == "buy" && quantity$sign != 1L) ||
          (transaction$transaction_type == "sell" && quantity$sign != -1L)) {
        .import_abort("transaction_semantics_invalid")
      }
      price <- .import_decimal(asset_posting$unit_price_decimal, positive_only = TRUE)
      if (!identical(asset_posting$price_currency, currency) || !identical(asset_posting$valuation_currency, currency)) {
        .import_abort("transaction_semantics_invalid")
      }
      valuation <- .import_decimal(asset_posting$valuation_amount_decimal)
      if (!.import_decimal_equal(valuation, .transaction_decimal_multiply(quantity, price))) {
        .import_abort("transaction_semantics_invalid")
      }
      gross <- .import_cash_value(cash_posting, cash_account, cash_asset, currency)
      if (!.import_decimal_equal(gross, .transaction_decimal_negate(valuation))) {
        .import_abort("transaction_semantics_invalid")
      }
      optional_cash <- zero
      for (role in c("fee", "tax")) {
        rows <- tx_postings[roles == role]
        if (!length(rows)) next
        posting <- rows[[1L]]
        if (!identical(posting$staged_account_id, cash_posting$staged_account_id) ||
            !identical(posting$staged_asset_id, cash_posting$staged_asset_id)) {
          .import_abort("transaction_semantics_invalid")
        }
        value <- .import_cash_value(posting, accounts[[posting$staged_account_id]], assets[[posting$staged_asset_id]], currency)
        if (value$sign >= 0L) .import_abort("transaction_semantics_invalid")
        optional_cash <- .transaction_decimal_add(optional_cash, value)
      }
      key <- paste(transaction$staged_portfolio_id, asset_posting$staged_account_id, asset_posting$staged_asset_id, sep = "|")
      lots <- fifo[[key]]
      if (is.null(lots)) lots <- list()
      if (transaction$transaction_type == "buy") {
        lots[[length(lots) + 1L]] <- quantity
      } else {
        remaining <- .transaction_decimal_abs(quantity)
        while (remaining$sign > 0L) {
          if (!length(lots)) .import_abort("transaction_semantics_invalid")
          comparison <- .transaction_decimal_compare(lots[[1L]], remaining)
          if (comparison <= 0L) {
            remaining <- .transaction_decimal_subtract(remaining, lots[[1L]])
            lots <- lots[-1L]
          } else {
            lots[[1L]] <- .transaction_decimal_subtract(lots[[1L]], remaining)
            remaining <- zero
          }
        }
      }
      fifo[[key]] <- lots
    }
    invisible(TRUE)
  }, spot_import_data_command_error = function(error) stop(error), error = function(error) {
    .import_abort("transaction_semantics_invalid")
  })
}

.import_validate_canonical_connection <- function(connection, context) {
  version <- DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]
  if (!identical(as.integer(version), .import_canonical_schema_version)) {
    .import_abort("canonical_schema_version_mismatch")
  }
  if (!identical(.import_schema_fingerprint(connection), .import_canonical_schema_fingerprint)) {
    .import_abort("canonical_contract_schema_mismatch")
  }
  binding <- .import_fetch_rows(connection, "SELECT * FROM store_binding")
  if (length(binding) != 1L) .import_abort("canonical_store_binding_missing")
  binding <- binding[[1L]]
  if (!identical(as.integer(binding$schema_version), .import_canonical_schema_version) ||
      !identical(binding$tenant_id, context$tenant_id) || !identical(binding$user_id, context$user_id) ||
      !identical(binding$data_space_id, context$data_space_id)) {
    .import_abort("canonical_runtime_context_mismatch")
  }
  if (!identical(as.integer(DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]]), 1L)) {
    .import_abort("canonical_foreign_keys_disabled")
  }
  if (!identical(as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]), 0L)) {
    .import_abort("canonical_connection_query_only")
  }
  if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .import_abort("canonical_foreign_key_invalid")
  }
  invisible(TRUE)
}

.import_connect_canonical_write <- function(context) {
  path <- runtime_canonical_path(context)
  if (.canonical_symlink(path) || !file.exists(path) || dir.exists(path)) {
    .import_abort("canonical_contract_schema_mismatch")
  }
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RW),
    error = function(error) .import_abort("canonical_contract_schema_mismatch")
  )
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, "PRAGMA query_only = OFF")
    DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
    .import_validate_canonical_connection(connection, context)
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    stop(error)
  })
  if (!valid) .import_abort("canonical_contract_schema_mismatch")
  connection
}

.import_command_id <- function(context, source_set_fingerprint, candidate_fingerprint) {
  paste0(
    "cmd_import_",
    substr(
      .import_hash_parts(c(
        "legacy-import-command-v1", context$tenant_id, context$user_id, context$data_space_id,
        source_set_fingerprint, candidate_fingerprint
      )),
      1L,
      52L
    )
  )
}

.import_target_empty <- function(connection) {
  tables <- c(
    "portfolio", "account", "asset", "provider_mapping", "transaction_record",
    "transaction_posting", "transaction_seal", "data_command_audit", "canonical_import_receipt"
  )
  all(vapply(tables, function(table) {
    identical(as.integer(DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1]]), 0L)
  }, logical(1)))
}

.import_receipt_fingerprint_valid <- function(receipt, context) {
  keys <- c(
    "command_id", "tenant_id", "user_id", "target_sandbox_id", "target_portfolio_id",
    "source_contract_version", "staging_schema_version", "canonical_schema_version",
    "source_import_run_id", "source_set_fingerprint", "parser_bundle_fingerprint",
    "staging_artifact_fingerprint", "candidate_fingerprint", "confirmation_fingerprint",
    "origin_ref_namespace", "portfolio_count", "account_count", "asset_count", "transaction_count",
    "posting_count", "actor_id", "committed_at_utc"
  )
  payload <- receipt[keys]
  expected <- .import_fingerprint(payload)
  identical(receipt$receipt_fingerprint, expected) &&
    identical(receipt$import_receipt_id, paste0("irc_", substr(expected, 1L, 32L))) &&
    identical(receipt$command_id, .import_command_id(context, receipt$source_set_fingerprint, receipt$candidate_fingerprint)) &&
    identical(receipt$origin_ref_namespace, paste0("lir_", substr(receipt$candidate_fingerprint, 1L, 24L), "_"))
}

.import_preflight_connection <- function(connection, validated, context) {
  rows <- .import_fetch_rows(
    connection,
    paste(
      "SELECT * FROM canonical_import_receipt",
      "WHERE source_set_fingerprint=? OR candidate_fingerprint=?",
      "ORDER BY import_receipt_id"
    ),
    list(validated$run$source_set_fingerprint, validated$candidate_fingerprint)
  )
  if (!length(rows)) return(list(status = "new_candidate", import_receipt_id = NULL))
  if (length(rows) == 1L) {
    receipt <- rows[[1L]]
    exact <- identical(receipt$source_import_run_id, validated$run$import_run_id) &&
      identical(receipt$source_set_fingerprint, validated$run$source_set_fingerprint) &&
      identical(receipt$parser_bundle_fingerprint, validated$run$parser_bundle_fingerprint) &&
      identical(receipt$staging_artifact_fingerprint, validated$artifact_fingerprint) &&
      identical(receipt$candidate_fingerprint, validated$candidate_fingerprint) &&
      identical(receipt$tenant_id, context$tenant_id) && identical(receipt$user_id, context$user_id) &&
      identical(receipt$target_sandbox_id, context$data_space_id) &&
      identical(as.integer(receipt$source_contract_version), as.integer(validated$run$contract_version)) &&
      identical(as.integer(receipt$staging_schema_version), .import_staging_schema_version) &&
      identical(as.integer(receipt$canonical_schema_version), .import_canonical_schema_version) &&
      all(vapply(names(validated$counts), function(name) {
        identical(as.integer(receipt[[name]]), as.integer(validated$counts[[name]]))
      }, logical(1))) && .import_receipt_fingerprint_valid(receipt, context)
    audit_count <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT count(*) AS n FROM data_command_audit",
        "WHERE command_id=? AND area_id='canonical_import_receipt'",
        "AND command_type='legacy_import_commit_v1' AND entity_id=? AND actor_id=?",
        "AND committed_at_utc=? AND payload_fingerprint=?",
        "AND origin_type='legacy_import' AND origin_ref=?"
      ),
      params = list(
        receipt$command_id, receipt$target_portfolio_id, receipt$actor_id, receipt$committed_at_utc,
        receipt$candidate_fingerprint, receipt$source_import_run_id
      )
    )$n[[1]]
    if (exact && identical(as.integer(audit_count), 1L)) {
      return(list(status = "already_imported", import_receipt_id = receipt$import_receipt_id))
    }
  }
  list(status = "idempotency_conflict", import_receipt_id = NULL)
}

.import_safe_preflight <- function(validated, context, state) {
  list(
    contract_version = .import_contract_version,
    status = if (identical(state$status, "new_candidate")) "ready_for_confirmation" else state$status,
    command_id = .import_command_id(context, validated$run$source_set_fingerprint, validated$candidate_fingerprint),
    source_import_run_id = validated$run$import_run_id,
    source_set_fingerprint = validated$run$source_set_fingerprint,
    parser_bundle_fingerprint = validated$run$parser_bundle_fingerprint,
    staging_artifact_fingerprint = validated$artifact_fingerprint,
    candidate_fingerprint = validated$candidate_fingerprint,
    counts = validated$counts,
    import_receipt_id = state$import_receipt_id
  )
}

legacy_import_preflight_v1 <- function(context, staging_capability) {
  .import_boundary_eval({
    .import_context_check(context)
    validated <- .import_open_validated_staging(context, staging_capability)
    .import_validate_transaction_semantics(validated$candidate_manifest)
    connection <- .import_connect_canonical_write(context)
    on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
    if (.import_connection_in_transaction(connection)) .import_abort("canonical_connection_already_in_transaction")
    state <- .import_preflight_connection(connection, validated, context)
    if (identical(state$status, "idempotency_conflict")) .import_abort("idempotency_conflict")
    if (identical(state$status, "new_candidate") && !.import_target_empty(connection)) {
      .import_abort("target_sandbox_not_empty")
    }
    .import_safe_preflight(validated, context, state)
  })
}

new_import_confirmation_authorizer_v1 <- function() {
  structure(
    list(entries = new.env(hash = TRUE, parent = emptyenv())),
    class = "spot_import_confirmation_authorizer_v1"
  )
}

.import_authorizer_valid <- function(authorizer) {
  inherits(authorizer, "spot_import_confirmation_authorizer_v1") && is.list(authorizer) &&
    identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

.import_challenge_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    grepl("^cfm_[a-z0-9_]+$", value)
}

.import_time <- function(value) {
  if (!.canonical_utc_valid(value)) .import_abort("confirmation_time_invalid")
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

.import_confirmation_payload <- function(current, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc) {
  list(
    confirmation_contract_version = .import_contract_version,
    challenge_id = challenge_id,
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    source_import_run_id = current$source_import_run_id,
    source_set_fingerprint = current$source_set_fingerprint,
    parser_bundle_fingerprint = current$parser_bundle_fingerprint,
    staging_artifact_fingerprint = current$staging_artifact_fingerprint,
    candidate_fingerprint = current$candidate_fingerprint,
    counts = current$counts,
    issued_at_utc = issued_at_utc,
    confirmed_at_utc = confirmed_at_utc,
    expires_at_utc = expires_at_utc
  )
}

legacy_import_build_confirmation_v1 <- function(
  preflight,
  context,
  staging_capability,
  authorizer,
  challenge_id,
  issued_at_utc,
  confirmed_at_utc,
  expires_at_utc
) {
  .import_boundary_eval({
    .import_context_check(context)
    if (!.import_authorizer_valid(authorizer) || !.import_challenge_valid(challenge_id)) {
      .import_abort("confirmation_invalid")
    }
    current <- legacy_import_preflight_v1(context, staging_capability)
    if (!is.list(preflight) || !identical(preflight, current) || !identical(current$status, "ready_for_confirmation")) {
      .import_abort("confirmation_scope_mismatch")
    }
    issued <- .import_time(issued_at_utc)
    confirmed <- .import_time(confirmed_at_utc)
    expires <- .import_time(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires)) .import_abort("confirmation_expired_or_time_invalid")
    if (as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .import_abort("confirmation_validity_window_exceeded")
    }
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .import_abort("confirmation_challenge_duplicate")
    }
    payload <- .import_confirmation_payload(
      current, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .import_fingerprint(payload)
    assign(
      challenge_id,
      list(fingerprint = confirmation$confirmation_fingerprint, consumed = FALSE),
      envir = authorizer$entries
    )
    confirmation
  })
}

.import_validate_confirmation <- function(confirmation, validated, context, now_utc) {
  if (!is.list(confirmation)) .import_abort("confirmation_missing")
  required <- c(
    "confirmation_contract_version", "challenge_id", "tenant_id", "user_id", "data_space_id", "actor_id",
    "role", "source_import_run_id", "source_set_fingerprint", "parser_bundle_fingerprint",
    "staging_artifact_fingerprint", "candidate_fingerprint", "counts", "issued_at_utc", "confirmed_at_utc",
    "expires_at_utc", "confirmation_fingerprint"
  )
  if (!setequal(names(confirmation), required) || !identical(confirmation$confirmation_contract_version, 1L) ||
      !.import_challenge_valid(confirmation$challenge_id)) {
    .import_abort("confirmation_invalid")
  }
  payload <- confirmation[setdiff(names(confirmation), "confirmation_fingerprint")]
  if (!identical(.import_fingerprint(payload), confirmation$confirmation_fingerprint)) {
    .import_abort("confirmation_fingerprint_mismatch")
  }
  expected <- list(
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    source_import_run_id = validated$run$import_run_id,
    source_set_fingerprint = validated$run$source_set_fingerprint,
    parser_bundle_fingerprint = validated$run$parser_bundle_fingerprint,
    staging_artifact_fingerprint = validated$artifact_fingerprint,
    candidate_fingerprint = validated$candidate_fingerprint,
    counts = validated$counts
  )
  for (name in names(expected)) {
    if (!identical(confirmation[[name]], expected[[name]])) .import_abort("confirmation_scope_mismatch")
  }
  issued <- .import_time(confirmation$issued_at_utc)
  confirmed <- .import_time(confirmation$confirmed_at_utc)
  expires <- .import_time(confirmation$expires_at_utc)
  now <- .import_time(now_utc)
  if (!(issued <= confirmed && confirmed <= now && now <= expires)) {
    .import_abort("confirmation_expired_or_time_invalid")
  }
  if (as.numeric(difftime(expires, issued, units = "secs")) > 600) {
    .import_abort("confirmation_validity_window_exceeded")
  }
  invisible(TRUE)
}

.import_consume_confirmation <- function(authorizer, confirmation) {
  if (!.import_authorizer_valid(authorizer) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .import_abort("confirmation_not_authorized")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, confirmation$confirmation_fingerprint)) {
    .import_abort("confirmation_not_authorized")
  }
  if (isTRUE(entry$consumed)) .import_abort("confirmation_already_consumed")
  entry$consumed <- TRUE
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  invisible(TRUE)
}

.import_deterministic_id <- function(prefix, candidate_fingerprint, kind, staged_id) {
  paste0(prefix, substr(.import_hash_parts(c(candidate_fingerprint, kind, staged_id)), 1L, 24L))
}

.import_origin_ref <- function(namespace, kind, staged_id) {
  paste0(namespace, kind, "_", substr(.import_hash_parts(c(kind, staged_id)), 1L, 20L))
}

.import_db_value <- function(value) if (is.null(value)) NA_character_ else value

.import_failpoint <- function(selected, current) {
  if (identical(selected, current)) .import_abort("synthetic_failpoint")
}

.import_write_candidate <- function(connection, validated, context, committed_at_utc, failpoint) {
  manifest <- validated$candidate_manifest
  candidate_fingerprint <- validated$candidate_fingerprint
  namespace <- paste0("lir_", substr(candidate_fingerprint, 1L, 24L), "_")
  mappings <- list(portfolio = list(), account = list(), asset = list(), transaction = list(), posting = list())
  for (item in manifest$portfolios) {
    staged_id <- item$staged_portfolio_id
    canonical_id <- .import_deterministic_id("ptf_", candidate_fingerprint, "portfolio", staged_id)
    mappings$portfolio[[staged_id]] <- canonical_id
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO portfolio",
        "(portfolio_id, display_name, base_currency, origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, 'legacy_import', ?, ?, ?)"
      ),
      params = list(
        canonical_id, item$display_name, item$base_currency,
        .import_origin_ref(namespace, "ptf", staged_id), committed_at_utc, committed_at_utc
      )
    )
  }
  .import_failpoint(failpoint, "after_portfolios")
  for (item in manifest$accounts) {
    staged_id <- item$staged_account_id
    canonical_id <- .import_deterministic_id("acc_", candidate_fingerprint, "account", staged_id)
    mappings$account[[staged_id]] <- canonical_id
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO account",
        "(account_id, portfolio_id, display_name, account_type, origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, ?, 'legacy_import', ?, ?, ?)"
      ),
      params = list(
        canonical_id, mappings$portfolio[[item$staged_portfolio_id]], item$display_name, item$account_type,
        .import_origin_ref(namespace, "acc", staged_id), committed_at_utc, committed_at_utc
      )
    )
  }
  .import_failpoint(failpoint, "after_accounts")
  for (item in manifest$assets) {
    staged_id <- item$staged_asset_id
    canonical_id <- .import_deterministic_id("ast_", candidate_fingerprint, "asset", staged_id)
    mappings$asset[[staged_id]] <- canonical_id
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO asset",
        "(asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method, isin,",
        "origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'legacy_import', ?, ?, ?)"
      ),
      params = list(
        canonical_id, item$display_name, item$asset_type, item$price_currency, item$quantity_scale,
        item$valuation_method, .import_db_value(item$isin), .import_origin_ref(namespace, "ast", staged_id),
        committed_at_utc, committed_at_utc
      )
    )
  }
  .import_failpoint(failpoint, "after_assets")
  postings_by_transaction <- split(
    manifest$postings,
    vapply(manifest$postings, `[[`, character(1), "staged_transaction_id")
  )
  for (item in manifest$transactions) {
    staged_id <- item$staged_transaction_id
    canonical_id <- .import_deterministic_id("txn_", candidate_fingerprint, "transaction", staged_id)
    mappings$transaction[[staged_id]] <- canonical_id
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO transaction_record",
        "(transaction_id, portfolio_id, transaction_type, record_action, effective_at_utc, local_date,",
        "origin_type, origin_ref, created_at_utc, created_by_actor)",
        "VALUES (?, ?, ?, 'book', ?, ?, 'legacy_import', ?, ?, ?)"
      ),
      params = list(
        canonical_id, mappings$portfolio[[item$staged_portfolio_id]], item$transaction_type,
        item$effective_at_utc, item$local_date, .import_origin_ref(namespace, "txn", staged_id),
        committed_at_utc, context$actor_id
      )
    )
    canonical_postings <- list()
    transaction_postings <- postings_by_transaction[[staged_id]]
    if (is.null(transaction_postings)) transaction_postings <- list()
    for (posting in transaction_postings) {
      staged_posting_id <- posting$staged_posting_id
      posting_id <- .import_deterministic_id("pst_", candidate_fingerprint, "posting", staged_posting_id)
      mappings$posting[[staged_posting_id]] <- posting_id
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO transaction_posting",
          "(posting_id, transaction_id, sequence_no, account_id, asset_id, posting_role, quantity_decimal,",
          "unit_price_decimal, price_currency, valuation_amount_decimal, valuation_currency)",
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        params = list(
          posting_id, canonical_id, posting$sequence_no, mappings$account[[posting$staged_account_id]],
          mappings$asset[[posting$staged_asset_id]], posting$posting_role, posting$quantity_decimal,
          .import_db_value(posting$unit_price_decimal), .import_db_value(posting$price_currency),
          .import_db_value(posting$valuation_amount_decimal), .import_db_value(posting$valuation_currency)
        )
      )
      canonical_postings[[length(canonical_postings) + 1L]] <- list(
        posting_id = posting_id,
        sequence_no = posting$sequence_no,
        account_id = mappings$account[[posting$staged_account_id]],
        asset_id = mappings$asset[[posting$staged_asset_id]],
        posting_role = posting$posting_role,
        quantity_decimal = posting$quantity_decimal,
        unit_price_decimal = posting$unit_price_decimal,
        price_currency = posting$price_currency,
        valuation_amount_decimal = posting$valuation_amount_decimal,
        valuation_currency = posting$valuation_currency
      )
    }
    transaction_content <- list(
      transaction_id = canonical_id,
      portfolio_id = mappings$portfolio[[item$staged_portfolio_id]],
      transaction_type = item$transaction_type,
      effective_at_utc = item$effective_at_utc,
      local_date = item$local_date,
      postings = canonical_postings
    )
    DBI::dbExecute(
      connection,
      "INSERT INTO transaction_seal VALUES (?, ?, ?, ?)",
      params = list(canonical_id, committed_at_utc, length(canonical_postings), .import_fingerprint(transaction_content))
    )
  }
  .import_failpoint(failpoint, "after_transactions")
  if (length(mappings$portfolio) != 1L) .import_abort("candidate_portfolio_count_invalid")
  list(
    mappings = mappings,
    target_portfolio_id = unname(unlist(mappings$portfolio, use.names = FALSE)[[1L]]),
    origin_ref_namespace = namespace
  )
}

.import_receipt_payload <- function(validated, context, command_id, target_portfolio_id, confirmation_fingerprint, committed_at_utc) {
  list(
    command_id = command_id,
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    target_sandbox_id = context$data_space_id,
    target_portfolio_id = target_portfolio_id,
    source_contract_version = validated$run$contract_version,
    staging_schema_version = .import_staging_schema_version,
    canonical_schema_version = .import_canonical_schema_version,
    source_import_run_id = validated$run$import_run_id,
    source_set_fingerprint = validated$run$source_set_fingerprint,
    parser_bundle_fingerprint = validated$run$parser_bundle_fingerprint,
    staging_artifact_fingerprint = validated$artifact_fingerprint,
    candidate_fingerprint = validated$candidate_fingerprint,
    confirmation_fingerprint = confirmation_fingerprint,
    origin_ref_namespace = paste0("lir_", substr(validated$candidate_fingerprint, 1L, 24L), "_"),
    portfolio_count = validated$counts$portfolio_count,
    account_count = validated$counts$account_count,
    asset_count = validated$counts$asset_count,
    transaction_count = validated$counts$transaction_count,
    posting_count = validated$counts$posting_count,
    actor_id = context$actor_id,
    committed_at_utc = committed_at_utc
  )
}

.import_result <- function(status, command_id, candidate_fingerprint, import_receipt_id, counts) {
  list(
    status = status,
    command_id = command_id,
    candidate_fingerprint = candidate_fingerprint,
    import_receipt_id = import_receipt_id,
    counts = counts
  )
}

.import_failpoints_v1 <- function() {
  c(
    "after_portfolios", "after_accounts", "after_assets", "after_transactions",
    "after_audit", "after_receipt", "before_commit"
  )
}

.import_execute_impl_v1 <- function(
  context,
  staging_capability,
  confirmation,
  authorizer,
  now_utc,
  failpoint = "none"
) {
  .import_context_check(context)
  if (!identical(failpoint, "none") && !failpoint %in% .import_failpoints_v1()) {
    .import_abort("command_preflight_failed")
  }
  validated <- .import_open_validated_staging(context, staging_capability)
  .import_validate_transaction_semantics(validated$candidate_manifest)
  data_space <- runtime_data_space_path(context)
  lock <- tryCatch(.canonical_acquire_lock(data_space), error = function(error) NULL)
  if (is.null(lock)) .import_abort("command_preflight_failed")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .import_connect_canonical_write(context)
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  if (.import_connection_in_transaction(connection)) .import_abort("canonical_connection_already_in_transaction")
  command_id <- .import_command_id(context, validated$run$source_set_fingerprint, validated$candidate_fingerprint)
  state <- .import_preflight_connection(connection, validated, context)
  if (identical(state$status, "already_imported")) {
    return(.import_result("already_imported", command_id, validated$candidate_fingerprint, state$import_receipt_id, validated$counts))
  }
  if (!identical(state$status, "new_candidate")) .import_abort("idempotency_conflict")
  if (!.import_target_empty(connection)) .import_abort("target_sandbox_not_empty")
  .import_validate_confirmation(confirmation, validated, context, now_utc)
  .import_consume_confirmation(authorizer, confirmation)
  transaction_open <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    transaction_open <- TRUE
    .import_validate_canonical_connection(connection, context)
    locked_state <- .import_preflight_connection(connection, validated, context)
    if (identical(locked_state$status, "already_imported")) {
      DBI::dbExecute(connection, "ROLLBACK")
      transaction_open <- FALSE
      return(.import_result(
        "already_imported", command_id, validated$candidate_fingerprint,
        locked_state$import_receipt_id, validated$counts
      ))
    }
    if (!identical(locked_state$status, "new_candidate")) .import_abort("idempotency_conflict")
    if (!.import_target_empty(connection)) .import_abort("target_sandbox_not_empty")
    written <- .import_write_candidate(connection, validated, context, now_utc, failpoint)
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
        "payload_fingerprint, origin_type, origin_ref)",
        "VALUES (?, 'canonical_import_receipt', 'legacy_import_commit_v1', ?, ?, ?, ?, 'legacy_import', ?)"
      ),
      params = list(
        command_id, written$target_portfolio_id, context$actor_id, now_utc,
        validated$candidate_fingerprint, validated$run$import_run_id
      )
    )
    .import_failpoint(failpoint, "after_audit")
    receipt_payload <- .import_receipt_payload(
      validated, context, command_id, written$target_portfolio_id,
      confirmation$confirmation_fingerprint, now_utc
    )
    receipt_fingerprint <- .import_fingerprint(receipt_payload)
    import_receipt_id <- paste0("irc_", substr(receipt_fingerprint, 1L, 32L))
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO canonical_import_receipt",
        "(import_receipt_id, command_id, tenant_id, user_id, target_sandbox_id, target_portfolio_id,",
        "source_contract_version, staging_schema_version, canonical_schema_version, source_import_run_id,",
        "source_set_fingerprint, parser_bundle_fingerprint, staging_artifact_fingerprint, candidate_fingerprint,",
        "confirmation_fingerprint, origin_ref_namespace, portfolio_count, account_count, asset_count,",
        "transaction_count, posting_count, actor_id, committed_at_utc, receipt_fingerprint)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ),
      params = unname(c(list(import_receipt_id), receipt_payload, list(receipt_fingerprint)))
    )
    .import_failpoint(failpoint, "after_receipt")
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
      .import_abort("canonical_foreign_key_invalid")
    }
    if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
      .import_abort("canonical_integrity_invalid")
    }
    .import_failpoint(failpoint, "before_commit")
    DBI::dbExecute(connection, "COMMIT")
    transaction_open <- FALSE
    .import_result("committed", command_id, validated$candidate_fingerprint, import_receipt_id, validated$counts)
  }, error = function(error) {
    if (transaction_open && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_import_data_command_error")) stop(error)
    .import_abort("canonical_transaction_failed")
  })
}

legacy_import_execute_v1 <- function(context, staging_capability, confirmation, authorizer, now_utc) {
  .import_boundary_eval(
    .import_execute_impl_v1(context, staging_capability, confirmation, authorizer, now_utc, failpoint = "none"),
    fallback = "canonical_transaction_failed"
  )
}
