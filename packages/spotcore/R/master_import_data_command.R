master_import_data_command_error_codes <- function() {
  c(
    "master_dependency_missing",
    "master_runtime_context_invalid",
    "master_runtime_role_not_authorized",
    "master_contract_source_invalid",
    "master_sandbox_bootstrap_failed",
    "master_staging_path_invalid",
    "master_staging_query_only_not_enforced",
    "master_staging_connection_in_transaction",
    "master_staging_schema_version_mismatch",
    "master_staging_schema_fingerprint_mismatch",
    "master_staging_integrity_invalid",
    "master_staging_context_mismatch",
    "master_productive_candidate_not_enabled",
    "master_staging_seal_invalid",
    "master_staging_payload_invalid",
    "master_candidate_invalid",
    "master_canonical_schema_mismatch",
    "master_canonical_binding_mismatch",
    "master_canonical_settings_invalid",
    "master_canonical_integrity_invalid",
    "master_canonical_connection_in_transaction",
    "master_target_sandbox_not_empty",
    "master_idempotency_conflict",
    "master_confirmation_missing",
    "master_confirmation_invalid",
    "master_confirmation_challenge_duplicate",
    "master_confirmation_not_authorized",
    "master_confirmation_already_consumed",
    "master_confirmation_fingerprint_mismatch",
    "master_confirmation_scope_mismatch",
    "master_confirmation_expired_or_time_invalid",
    "master_confirmation_validity_window_exceeded",
    "master_synthetic_failpoint",
    "master_canonical_transaction_failed",
    "master_command_boundary_failed"
  )
}

.master_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% master_import_data_command_error_codes()) {
    stop("unregistered_master_import_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_master_import_data_command_error", "error", "condition")
  )
}

.master_abort <- function(code) stop(.master_condition(code))

.master_boundary_eval <- function(expression, fallback = "master_command_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_master_import_data_command_error = function(error) error,
    spot_runtime_error = function(error) .master_condition("master_runtime_context_invalid"),
    spot_canonical_repository_error = function(error) .master_condition(fallback),
    error = function(error) .master_condition(fallback)
  )
  if (inherits(result, "spot_master_import_data_command_error")) stop(result)
  result
}

.master_contract_version <- 1L
.master_staging_schema_version <- 1402L
.master_canonical_schema_version <- 202L
.master_staging_schema_fingerprint <- "43235f5efc242dc253cef1d1b9fb52f53b5a3a74d3b27107ff2c0e056b7c3651"
.master_canonical_schema_fingerprint <- "1d46be68f51afdf27315c9466f9c23440893ff666f1c0bf90ab7015fd94c1524"
.master_projection_contract_fingerprint <- "86506ab8f51b57a52197c0c452e1bdf0fa9c5a5bd45a53a541cdb1b146bb7079"
.master_v22_source_fingerprint <- "c3e09e59d254fa40d641bdcadbf44a9ee22b742fa98087252ed0e86b470103af"

.master_dependencies_valid <- function() {
  all(vapply(c("DBI", "RSQLite", "digest", "jsonlite"), requireNamespace, logical(1), quietly = TRUE))
}

.master_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .master_abort("master_runtime_context_invalid")
  }
  if (!identical(context$role, "desktop_owner")) {
    .master_abort("master_runtime_role_not_authorized")
  }
  invisible(TRUE)
}

.master_sha_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[a-f0-9]{64}$", value)
}

.master_id_valid <- function(value, prefix) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    startsWith(value, prefix) && grepl("^[a-z][a-z0-9_]{2,63}$", value)
}

.master_text_fingerprint <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) {
    .master_abort("master_staging_payload_invalid")
  }
  digest::digest(charToRaw(enc2utf8(value)), algo = "sha256", serialize = FALSE)
}

.master_contract_sources <- function(contract_root) {
  base <- tryCatch(
    .canonical_contract_sources(contract_root),
    error = function(error) .master_abort("master_contract_source_invalid")
  )
  path <- file.path(normalizePath(contract_root, winslash = "/", mustWork = TRUE), "v2.2", "migrate-from-v2.1.sql")
  if (!file.exists(path) || dir.exists(path) || .canonical_symlink(path) ||
      !identical(.canonical_sha256_file(path), .master_v22_source_fingerprint)) {
    .master_abort("master_contract_source_invalid")
  }
  c(base, v2_2 = path)
}

.master_connection_in_transaction <- function(connection) {
  began <- tryCatch({
    DBI::dbExecute(connection, "BEGIN")
    TRUE
  }, error = function(error) FALSE)
  if (began) {
    DBI::dbExecute(connection, "ROLLBACK")
    return(FALSE)
  }
  TRUE
}

.master_validate_canonical <- function(connection, context, expected_query_only = 0L) {
  version <- DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]
  if (!identical(as.integer(version), .master_canonical_schema_version) ||
      !identical(canonical_repository_schema_fingerprint_v1(connection), .master_canonical_schema_fingerprint)) {
    .master_abort("master_canonical_schema_mismatch")
  }
  binding <- DBI::dbGetQuery(
    connection,
    "SELECT singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc FROM store_binding"
  )
  if (nrow(binding) != 1L || as.integer(binding$singleton_id[[1]]) != 1L ||
      as.integer(binding$schema_version[[1]]) != .master_canonical_schema_version ||
      !identical(binding$tenant_id[[1]], context$tenant_id) ||
      !identical(binding$user_id[[1]], context$user_id) ||
      !identical(binding$data_space_id[[1]], context$data_space_id) ||
      !.canonical_utc_valid(binding$created_at_utc[[1]])) {
    .master_abort("master_canonical_binding_mismatch")
  }
  foreign_keys <- as.integer(DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]])
  query_only <- as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]])
  if (foreign_keys != 1L || query_only != expected_query_only) {
    .master_abort("master_canonical_settings_invalid")
  }
  if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .master_abort("master_canonical_integrity_invalid")
  }
  invisible(TRUE)
}

.master_connect_canonical <- function(context, read_only = FALSE) {
  path <- runtime_canonical_path(context)
  if (!file.exists(path) || dir.exists(path) || .canonical_symlink(path)) {
    .master_abort("master_canonical_schema_mismatch")
  }
  flags <- if (isTRUE(read_only)) RSQLite::SQLITE_RO else RSQLite::SQLITE_RW
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = flags),
    error = function(error) .master_abort("master_canonical_schema_mismatch")
  )
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, paste0("PRAGMA query_only = ", if (isTRUE(read_only)) "ON" else "OFF"))
    DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
    .master_validate_canonical(connection, context, if (isTRUE(read_only)) 1L else 0L)
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    stop(error)
  })
  if (!valid) .master_abort("master_canonical_schema_mismatch")
  connection
}

.master_repository_status <- function(context, status) {
  connection <- .master_connect_canonical(context, read_only = TRUE)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tables <- c(
    portfolios = "portfolio", accounts = "account", assets = "asset",
    provider_mappings = "provider_mapping", transactions = "transaction_record",
    postings = "transaction_posting", audits = "data_command_audit",
    master_receipts = "canonical_master_import_receipt"
  )
  counts <- vapply(tables, function(table) {
    as.integer(DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1]])
  }, integer(1))
  list(
    contract_version = .master_contract_version,
    status = status,
    schema_version = .master_canonical_schema_version,
    schema_fingerprint = canonical_repository_schema_fingerprint_v1(connection),
    query_only = 1L,
    foreign_keys = 1L,
    counts = as.list(counts)
  )
}

.master_import_sandbox_bootstrap_impl <- function(context, contract_root, created_at_utc, execution_mode) {
  .master_boundary_eval({
    if (!.master_dependencies_valid()) .master_abort("master_dependency_missing")
    .master_context_check(context)
    if (!execution_mode %in% c("synthetic_fixture", "authorized_private_candidate")) {
      .master_abort("master_productive_candidate_not_enabled")
    }
    if (!.canonical_utc_valid(created_at_utc)) .master_abort("master_runtime_context_invalid")
    sources <- .master_contract_sources(contract_root)
    data_space <- tryCatch(.canonical_create_data_space(context), error = function(error) {
      .master_abort("master_sandbox_bootstrap_failed")
    })
    lock <- tryCatch(.canonical_acquire_lock(data_space), error = function(error) {
      .master_abort("master_sandbox_bootstrap_failed")
    })
    on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
    target <- runtime_canonical_path(context)
    if (.canonical_symlink(target)) .master_abort("master_sandbox_bootstrap_failed")
    if (file.exists(target)) return(.master_repository_status(context, "already_initialized"))
    temporary <- tempfile(pattern = ".master-bootstrap-", tmpdir = data_space, fileext = ".sqlite.tmp")
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
      .canonical_execute_contract_script(connection, .canonical_read_script(sources[["v2_2"]]))
      DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
      DBI::dbExecute(connection, "BEGIN IMMEDIATE")
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO store_binding",
          "(singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc)",
          "VALUES (1, 202, ?, ?, ?, ?)"
        ),
        params = list(context$tenant_id, context$user_id, context$data_space_id, created_at_utc)
      )
      DBI::dbExecute(connection, "COMMIT")
      .master_validate_canonical(connection, context, 0L)
    }, error = function(error) {
      if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
      if (inherits(error, "spot_master_import_data_command_error")) stop(error)
      .master_abort("master_sandbox_bootstrap_failed")
    })
    DBI::dbDisconnect(connection)
    connected <- FALSE
    suppressWarnings(Sys.chmod(temporary, mode = "0600"))
    if (file.exists(target) || !file.rename(temporary, target)) {
      .master_abort("master_sandbox_bootstrap_failed")
    }
    temporary_owned <- FALSE
    suppressWarnings(Sys.chmod(target, mode = "0600"))
    .master_repository_status(context, "created")
  }, fallback = "master_sandbox_bootstrap_failed")
}

master_import_sandbox_bootstrap_v1 <- function(context, contract_root, created_at_utc, execution_mode) {
  if (!identical(execution_mode, "synthetic_fixture")) {
    .master_abort("master_productive_candidate_not_enabled")
  }
  .master_import_sandbox_bootstrap_impl(
    context, contract_root, created_at_utc, execution_mode
  )
}

.master_staging_path <- function(path) {
  if (!is.character(path) || length(path) != 1L || is.na(path) || !nzchar(path) ||
      !file.exists(path) || dir.exists(path) || .canonical_symlink(path)) {
    .master_abort("master_staging_path_invalid")
  }
  normalized <- tryCatch(normalizePath(path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || .canonical_symlink(normalized)) .master_abort("master_staging_path_invalid")
  mode <- file.info(normalized)$mode[[1]]
  if (is.na(mode) || bitwAnd(as.integer(mode), 146L) != 0L) {
    .master_abort("master_staging_query_only_not_enforced")
  }
  normalized
}

new_master_import_staging_capability_v1 <- function(staging_path) {
  .master_boundary_eval(structure(
    list(
      path = .master_staging_path(staging_path),
      execution_mode = "synthetic_fixture"
    ),
    class = "spot_master_import_staging_capability_v1"
  ))
}

new_private_master_import_staging_capability_v1 <- function(staging_path) {
  .master_boundary_eval(structure(
    list(
      path = .master_staging_path(staging_path),
      execution_mode = "authorized_private_candidate"
    ),
    class = "spot_master_import_staging_capability_v1"
  ))
}

.master_staging_capability_value <- function(capability) {
  if (!inherits(capability, "spot_master_import_staging_capability_v1") || !is.list(capability) ||
      !identical(names(capability), c("path", "execution_mode")) ||
      !capability$execution_mode %in% c("synthetic_fixture", "authorized_private_candidate")) {
    .master_abort("master_staging_path_invalid")
  }
  path <- .master_staging_path(capability$path)
  if (!identical(path, capability$path)) .master_abort("master_staging_path_invalid")
  list(path = path, execution_mode = capability$execution_mode)
}

.master_json <- function(text) {
  tryCatch(
    jsonlite::fromJSON(text, simplifyVector = FALSE),
    error = function(error) .master_abort("master_staging_payload_invalid")
  )
}

.master_exact_names <- function(value, expected, code = "master_candidate_invalid") {
  if (!is.list(value) || !setequal(names(value), expected)) .master_abort(code)
  value
}

.master_integer <- function(value, code = "master_candidate_invalid") {
  if (length(value) != 1L || is.na(value) || !is.numeric(value) || value != as.integer(value)) {
    .master_abort(code)
  }
  as.integer(value)
}

.master_rows <- function(connection, sql) .import_frame_rows(DBI::dbGetQuery(connection, sql))

.master_compare_value <- function(left, right) {
  if (is.null(left) || is.null(right)) return(is.null(left) && is.null(right))
  if (is.numeric(left) && is.numeric(right)) return(identical(as.integer(left), as.integer(right)))
  identical(left, right)
}

.master_compare_row <- function(json_row, sql_row, fields) {
  is.list(json_row) && setequal(names(json_row), fields) &&
    all(vapply(fields, function(field) .master_compare_value(json_row[[field]], sql_row[[field]]), logical(1)))
}

.master_validate_candidate <- function(candidate, binding, connection) {
  fields <- c(
    "master_candidate_contract_version", "projection_input_fingerprint", "canonical_schema_version",
    "master_staging_schema_version", "tenant_id", "user_id", "sandbox_id",
    "source_content_fingerprint", "source_header_fingerprint", "projection_fingerprint",
    "counts", "portfolio", "accounts", "assets"
  )
  .master_exact_names(candidate, fields)
  if (.master_integer(candidate$master_candidate_contract_version) != 1L ||
      .master_integer(candidate$canonical_schema_version) != .master_canonical_schema_version ||
      .master_integer(candidate$master_staging_schema_version) != .master_staging_schema_version ||
      !identical(candidate$tenant_id, binding$tenant_id) || !identical(candidate$user_id, binding$user_id) ||
      !identical(candidate$sandbox_id, binding$sandbox_id)) {
    .master_abort("master_candidate_invalid")
  }
  for (field in c(
    "projection_input_fingerprint", "source_content_fingerprint",
    "source_header_fingerprint", "projection_fingerprint"
  )) {
    if (!.master_sha_valid(candidate[[field]]) || !identical(candidate[[field]], binding[[field]])) {
      .master_abort("master_candidate_invalid")
    }
  }
  count_fields <- c(
    "portfolio_count", "account_count", "asset_count", "provider_mapping_count",
    "transaction_count", "posting_count"
  )
  .master_exact_names(candidate$counts, count_fields)
  counts <- lapply(candidate$counts, .master_integer)
  if (!identical(unname(unlist(counts[count_fields], use.names = FALSE)),
                 c(1L, length(candidate$accounts), length(candidate$assets), 0L, 0L, 0L))) {
    .master_abort("master_candidate_invalid")
  }
  portfolio_fields <- c("staged_portfolio_id", "display_name", "base_currency", "status", "origin_type")
  account_fields <- c(
    "staged_account_id", "staged_portfolio_id", "display_name", "account_type",
    "institution_label", "status", "origin_type"
  )
  asset_fields <- c(
    "staged_asset_id", "source_row_ordinal", "source_row_fingerprint",
    "legacy_asset_match_key_fingerprint", "currency_evidence_fingerprint", "display_name",
    "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin", "status",
    "operational_support_status", "origin_type"
  )
  portfolios <- .master_rows(connection, "SELECT * FROM staged_master_portfolio")
  accounts <- .master_rows(connection, "SELECT * FROM staged_master_account ORDER BY account_type, display_name, staged_account_id")
  assets <- .master_rows(connection, "SELECT * FROM staged_master_asset ORDER BY source_row_ordinal")
  if (length(portfolios) != 1L || !.master_compare_row(candidate$portfolio, portfolios[[1L]], portfolio_fields) ||
      !is.list(candidate$accounts) || length(candidate$accounts) != length(accounts) ||
      !is.list(candidate$assets) || length(candidate$assets) != length(assets)) {
    .master_abort("master_candidate_invalid")
  }
  if (length(accounts) && !all(vapply(seq_along(accounts), function(index) {
    .master_compare_row(candidate$accounts[[index]], accounts[[index]], account_fields)
  }, logical(1)))) .master_abort("master_candidate_invalid")
  if (length(assets) && !all(vapply(seq_along(assets), function(index) {
    .master_compare_row(candidate$assets[[index]], assets[[index]], asset_fields)
  }, logical(1)))) .master_abort("master_candidate_invalid")
  account_types <- if (length(candidate$accounts)) vapply(candidate$accounts, `[[`, character(1), "account_type") else character()
  asset_ordinals <- if (length(candidate$assets)) vapply(candidate$assets, function(asset) {
    .master_integer(asset$source_row_ordinal)
  }, integer(1)) else integer()
  identifiers_valid <- .master_id_valid(candidate$portfolio$staged_portfolio_id, "sptf_") &&
    all(vapply(candidate$accounts, function(account) {
      .master_id_valid(account$staged_account_id, "sacc_") &&
        identical(account$staged_portfolio_id, candidate$portfolio$staged_portfolio_id)
    }, logical(1))) &&
    all(vapply(candidate$assets, function(asset) {
      .master_id_valid(asset$staged_asset_id, "sast_") &&
        .master_sha_valid(asset$source_row_fingerprint) &&
        .master_sha_valid(asset$legacy_asset_match_key_fingerprint) &&
        .master_sha_valid(asset$currency_evidence_fingerprint) &&
        identical(
          asset$operational_support_status,
          if (identical(asset$asset_type, "derivative")) "blocked_derivative_contract_required" else "master_classification_reviewed"
        )
    }, logical(1)))
  display_names <- tolower(vapply(candidate$accounts, `[[`, character(1), "display_name"))
  if (!identifiers_valid || !any(account_types %in% c("securities", "crypto_wallet")) ||
      !any(account_types %in% c("cash", "bank")) || anyDuplicated(display_names) ||
      !identical(asset_ordinals, seq_along(candidate$assets))) {
    .master_abort("master_candidate_invalid")
  }
  candidate
}

.master_validate_stage_payload <- function(connection, binding, payload, expected_execution_mode) {
  candidate_fingerprint <- .master_text_fingerprint(payload$candidate_body_json)
  decision_fingerprint <- .master_text_fingerprint(payload$decision_body_json)
  artifact_fingerprint <- .master_text_fingerprint(payload$artifact_body_json)
  if (!identical(candidate_fingerprint, binding$candidate_fingerprint) ||
      !identical(decision_fingerprint, binding$decision_fingerprint) ||
      !identical(artifact_fingerprint, binding$artifact_fingerprint)) {
    .master_abort("master_staging_seal_invalid")
  }
  candidate <- .master_json(payload$candidate_body_json)
  candidate <- .master_validate_candidate(candidate, binding, connection)
  decision <- .master_json(payload$decision_body_json)
  decision_fields <- c(
    "contract_version", "slice_id", "execution_mode", "outcome", "projection_input_fingerprint",
    "blocker_codes", "operational_blocker_codes", "next_gate", "candidate", "canonical_write",
    "provider_mapping_activation", "transaction_import", "automatic_retry"
  )
  .master_exact_names(decision, decision_fields, "master_staging_payload_invalid")
  full_candidate <- decision$candidate
  if (!is.list(full_candidate) || !identical(full_candidate$candidate_fingerprint, candidate_fingerprint)) {
    .master_abort("master_staging_payload_invalid")
  }
  full_candidate$candidate_fingerprint <- NULL
  expected_operational_blockers <- if (any(vapply(candidate$assets, function(asset) {
    identical(asset$asset_type, "derivative")
  }, logical(1)))) list("derivative_operational_contract_missing") else list()
  if (!identical(full_candidate, candidate) || .master_integer(decision$contract_version, "master_staging_payload_invalid") != 1L ||
      !identical(decision$slice_id, "legacy_master_projection_v1") ||
      !identical(
        decision$execution_mode,
        if (identical(expected_execution_mode, "authorized_private_candidate")) "authorized_private_review" else "synthetic_fixture"
      ) ||
      !identical(decision$outcome, "ready_for_confirmation") || length(decision$blocker_codes) != 0L ||
      !identical(decision$operational_blocker_codes, expected_operational_blockers) ||
      !identical(decision$next_gate, "separate_one_use_canonical_confirmation_required") ||
      !identical(decision$projection_input_fingerprint, candidate$projection_input_fingerprint) ||
      !identical(decision$canonical_write, FALSE) || !identical(decision$provider_mapping_activation, FALSE) ||
      !identical(decision$transaction_import, FALSE) || !identical(decision$automatic_retry, FALSE)) {
    .master_abort("master_staging_payload_invalid")
  }
  artifact <- .master_json(payload$artifact_body_json)
  artifact_fields <- c(
    "artifact_contract_version", "master_staging_schema_version", "staging_schema_fingerprint",
    "candidate_fingerprint", "decision_fingerprint", "source_content_fingerprint",
    "projection_input_fingerprint"
  )
  .master_exact_names(artifact, artifact_fields, "master_staging_payload_invalid")
  if (.master_integer(artifact$artifact_contract_version, "master_staging_payload_invalid") != 1L ||
      .master_integer(artifact$master_staging_schema_version, "master_staging_payload_invalid") != .master_staging_schema_version ||
      !identical(artifact$staging_schema_fingerprint, .master_staging_schema_fingerprint) ||
      !identical(artifact$candidate_fingerprint, candidate_fingerprint) ||
      !identical(artifact$decision_fingerprint, decision_fingerprint) ||
      !identical(artifact$source_content_fingerprint, candidate$source_content_fingerprint) ||
      !identical(artifact$projection_input_fingerprint, candidate$projection_input_fingerprint)) {
    .master_abort("master_staging_payload_invalid")
  }
  list(
    binding = binding,
    candidate = candidate,
    candidate_fingerprint = candidate_fingerprint,
    decision_fingerprint = decision_fingerprint,
    artifact_fingerprint = artifact_fingerprint,
    counts = lapply(candidate$counts, as.integer)
  )
}

.master_open_validated_staging <- function(context, capability) {
  capability_value <- .master_staging_capability_value(capability)
  path <- capability_value$path
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RO),
    error = function(error) .master_abort("master_staging_query_only_not_enforced")
  )
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  if (.master_connection_in_transaction(connection)) .master_abort("master_staging_connection_in_transaction")
  DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
  DBI::dbExecute(connection, "PRAGMA query_only = ON")
  DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
  if (as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]) != 1L) {
    .master_abort("master_staging_query_only_not_enforced")
  }
  DBI::dbExecute(connection, "BEGIN")
  transaction_open <- TRUE
  on.exit(if (transaction_open && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
  version <- as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]])
  if (version != .master_staging_schema_version) .master_abort("master_staging_schema_version_mismatch")
  if (!identical(canonical_repository_schema_fingerprint_v1(connection), .master_staging_schema_fingerprint)) {
    .master_abort("master_staging_schema_fingerprint_mismatch")
  }
  if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .master_abort("master_staging_integrity_invalid")
  }
  bindings <- .master_rows(connection, "SELECT * FROM master_stage_binding")
  payloads <- .master_rows(connection, "SELECT * FROM master_stage_payload")
  if (length(bindings) != 1L || length(payloads) != 1L) .master_abort("master_staging_seal_invalid")
  binding <- bindings[[1L]]
  if (as.integer(binding$contract_version) != 1L || as.integer(binding$staging_schema_version) != .master_staging_schema_version ||
      !identical(binding$outcome, "ready_for_confirmation") || !.canonical_utc_valid(binding$sealed_at_utc)) {
    .master_abort("master_staging_seal_invalid")
  }
  if (!identical(binding$execution_mode, capability_value$execution_mode)) {
    if (identical(binding$execution_mode, "authorized_private_candidate")) {
      .master_abort("master_productive_candidate_not_enabled")
    }
    .master_abort("master_staging_seal_invalid")
  }
  if (!identical(binding$tenant_id, context$tenant_id) || !identical(binding$user_id, context$user_id) ||
      !identical(binding$sandbox_id, context$data_space_id)) {
    .master_abort("master_staging_context_mismatch")
  }
  validated <- .master_validate_stage_payload(
    connection, binding, payloads[[1L]], capability_value$execution_mode
  )
  DBI::dbExecute(connection, "ROLLBACK")
  transaction_open <- FALSE
  validated
}

.master_command_id <- function(context, candidate_fingerprint) {
  paste0("cmd_master_", substr(.import_hash_parts(c(
    "legacy-master-bootstrap-v1", context$tenant_id, context$user_id,
    context$data_space_id, candidate_fingerprint
  )), 1L, 52L))
}

.master_target_empty <- function(connection) {
  tables <- c(
    "portfolio", "account", "asset", "provider_mapping", "transaction_record",
    "transaction_posting", "transaction_seal", "data_command_audit",
    "canonical_import_receipt", "canonical_master_import_receipt"
  )
  all(vapply(tables, function(table) {
    as.integer(DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1]]) == 0L
  }, logical(1)))
}

.master_receipt_payload <- function(receipt) {
  keys <- c(
    "command_id", "tenant_id", "user_id", "target_sandbox_id", "target_portfolio_id",
    "source_contract_version", "master_staging_schema_version", "canonical_schema_version",
    "source_import_run_id", "source_set_fingerprint", "projection_contract_fingerprint",
    "staging_artifact_fingerprint", "candidate_fingerprint", "confirmation_fingerprint",
    "origin_ref_namespace", "portfolio_count", "account_count", "asset_count",
    "provider_mapping_count", "actor_id", "committed_at_utc"
  )
  receipt[keys]
}

.master_receipt_valid <- function(receipt, context, validated) {
  fingerprint <- .import_fingerprint(.master_receipt_payload(receipt))
  identical(receipt$receipt_fingerprint, fingerprint) &&
    identical(receipt$master_import_receipt_id, paste0("mrc_", substr(fingerprint, 1L, 32L))) &&
    identical(receipt$command_id, .master_command_id(context, validated$candidate_fingerprint)) &&
    identical(receipt$projection_contract_fingerprint, .master_projection_contract_fingerprint) &&
    identical(receipt$staging_artifact_fingerprint, validated$decision_fingerprint)
}

.master_idempotency <- function(connection, validated, context) {
  rows <- .import_fetch_rows(
    connection,
    paste(
      "SELECT * FROM canonical_master_import_receipt",
      "WHERE candidate_fingerprint=? OR source_set_fingerprint=?",
      "ORDER BY master_import_receipt_id"
    ),
    list(validated$candidate_fingerprint, validated$candidate$source_content_fingerprint)
  )
  if (!length(rows)) return(list(status = "new_candidate", receipt_id = NULL))
  if (length(rows) == 1L) {
    receipt <- rows[[1L]]
    counts <- validated$counts
    exact <- identical(receipt$candidate_fingerprint, validated$candidate_fingerprint) &&
      identical(receipt$source_set_fingerprint, validated$candidate$source_content_fingerprint) &&
      identical(receipt$tenant_id, context$tenant_id) && identical(receipt$user_id, context$user_id) &&
      identical(receipt$target_sandbox_id, context$data_space_id) &&
      as.integer(receipt$portfolio_count) == counts$portfolio_count &&
      as.integer(receipt$account_count) == counts$account_count &&
      as.integer(receipt$asset_count) == counts$asset_count &&
      as.integer(receipt$provider_mapping_count) == 0L && .master_receipt_valid(receipt, context, validated)
    audit <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT count(*) AS n FROM data_command_audit",
        "WHERE command_id=? AND area_id='canonical_import_receipt'",
        "AND command_type='legacy_master_bootstrap_v1' AND entity_id=?",
        "AND actor_id=? AND committed_at_utc=? AND payload_fingerprint=?",
        "AND origin_type='legacy_import' AND origin_ref=?"
      ),
      params = list(
        receipt$command_id, receipt$target_portfolio_id, receipt$actor_id,
        receipt$committed_at_utc, receipt$candidate_fingerprint, receipt$source_import_run_id
      )
    )$n[[1]]
    if (exact && as.integer(audit) == 1L) {
      return(list(status = "already_imported", receipt_id = receipt$master_import_receipt_id))
    }
  }
  list(status = "idempotency_conflict", receipt_id = NULL)
}

.master_preflight_value <- function(validated, context, state) {
  list(
    contract_version = .master_contract_version,
    status = if (identical(state$status, "new_candidate")) "ready_for_confirmation" else state$status,
    command_id = .master_command_id(context, validated$candidate_fingerprint),
    source_set_fingerprint = validated$candidate$source_content_fingerprint,
    projection_input_fingerprint = validated$candidate$projection_input_fingerprint,
    decision_fingerprint = validated$decision_fingerprint,
    staging_artifact_fingerprint = validated$artifact_fingerprint,
    candidate_fingerprint = validated$candidate_fingerprint,
    counts = validated$counts,
    master_import_receipt_id = state$receipt_id
  )
}

master_import_candidate_review_v1 <- function(context, staging_capability) {
  .master_boundary_eval({
    if (!.master_dependencies_valid()) .master_abort("master_dependency_missing")
    .master_context_check(context)
    validated <- .master_open_validated_staging(context, staging_capability)
    review <- .master_preflight_value(
      validated,
      context,
      list(status = "new_candidate", receipt_id = NULL)
    )
    review$status <- "ready_for_local_confirmation"
    review$execution_mode <- validated$binding$execution_mode
    review$canonical_target_access <- FALSE
    review$canonical_write <- FALSE
    review
  })
}

master_import_preflight_v1 <- function(context, staging_capability) {
  .master_boundary_eval({
    if (!.master_dependencies_valid()) .master_abort("master_dependency_missing")
    .master_context_check(context)
    validated <- .master_open_validated_staging(context, staging_capability)
    connection <- .master_connect_canonical(context, read_only = FALSE)
    on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
    if (.master_connection_in_transaction(connection)) .master_abort("master_canonical_connection_in_transaction")
    state <- .master_idempotency(connection, validated, context)
    if (identical(state$status, "idempotency_conflict")) .master_abort("master_idempotency_conflict")
    if (identical(state$status, "new_candidate") && !.master_target_empty(connection)) {
      .master_abort("master_target_sandbox_not_empty")
    }
    .master_preflight_value(validated, context, state)
  })
}

new_master_import_confirmation_authorizer_v1 <- function() {
  structure(
    list(entries = new.env(hash = TRUE, parent = emptyenv())),
    class = "spot_master_import_confirmation_authorizer_v1"
  )
}

.master_authorizer_valid <- function(authorizer) {
  inherits(authorizer, "spot_master_import_confirmation_authorizer_v1") &&
    is.list(authorizer) && identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

.master_challenge_valid <- function(value) .master_id_valid(value, "mcf_")

.master_time <- function(value) {
  if (!.canonical_utc_valid(value)) .master_abort("master_confirmation_invalid")
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

.master_confirmation_payload <- function(preflight, context, challenge_id, issued, confirmed, expires) {
  list(
    confirmation_contract_version = 1L,
    challenge_id = challenge_id,
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    target_sandbox_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    projection_input_fingerprint = preflight$projection_input_fingerprint,
    candidate_fingerprint = preflight$candidate_fingerprint,
    displayed_counts = preflight$counts,
    issued_at_utc = issued,
    confirmed_at_utc = confirmed,
    expires_at_utc = expires
  )
}

master_import_build_confirmation_v1 <- function(
  preflight, context, staging_capability, authorizer, challenge_id,
  issued_at_utc, confirmed_at_utc, expires_at_utc
) {
  .master_boundary_eval({
    .master_context_check(context)
    if (!.master_authorizer_valid(authorizer) || !.master_challenge_valid(challenge_id)) {
      .master_abort("master_confirmation_invalid")
    }
    current <- master_import_preflight_v1(context, staging_capability)
    if (!is.list(preflight) || !identical(preflight, current) ||
        !identical(current$status, "ready_for_confirmation")) {
      .master_abort("master_confirmation_scope_mismatch")
    }
    issued <- .master_time(issued_at_utc)
    confirmed <- .master_time(confirmed_at_utc)
    expires <- .master_time(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires)) {
      .master_abort("master_confirmation_expired_or_time_invalid")
    }
    if (as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .master_abort("master_confirmation_validity_window_exceeded")
    }
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .master_abort("master_confirmation_challenge_duplicate")
    }
    payload <- .master_confirmation_payload(
      current, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .import_fingerprint(payload)
    assign(challenge_id, list(
      fingerprint = confirmation$confirmation_fingerprint,
      consumed = FALSE
    ), envir = authorizer$entries)
    confirmation
  })
}

master_import_build_private_confirmation_v1 <- function(
  review, context, staging_capability, authorizer, challenge_id,
  issued_at_utc, confirmed_at_utc, expires_at_utc
) {
  .master_boundary_eval({
    .master_context_check(context)
    capability_value <- .master_staging_capability_value(staging_capability)
    if (!identical(capability_value$execution_mode, "authorized_private_candidate") ||
        !.master_authorizer_valid(authorizer) || !.master_challenge_valid(challenge_id)) {
      .master_abort("master_confirmation_invalid")
    }
    current <- master_import_candidate_review_v1(context, staging_capability)
    if (!is.list(review) || !identical(review, current) ||
        !identical(current$status, "ready_for_local_confirmation") ||
        !identical(current$canonical_target_access, FALSE) ||
        !identical(current$canonical_write, FALSE)) {
      .master_abort("master_confirmation_scope_mismatch")
    }
    issued <- .master_time(issued_at_utc)
    confirmed <- .master_time(confirmed_at_utc)
    expires <- .master_time(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires)) {
      .master_abort("master_confirmation_expired_or_time_invalid")
    }
    if (as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .master_abort("master_confirmation_validity_window_exceeded")
    }
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .master_abort("master_confirmation_challenge_duplicate")
    }
    payload <- .master_confirmation_payload(
      current, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .import_fingerprint(payload)
    assign(challenge_id, list(
      fingerprint = confirmation$confirmation_fingerprint,
      consumed = FALSE
    ), envir = authorizer$entries)
    confirmation
  })
}

.master_validate_confirmation <- function(confirmation, validated, context, now_utc) {
  if (!is.list(confirmation)) .master_abort("master_confirmation_missing")
  fields <- c(
    "confirmation_contract_version", "challenge_id", "tenant_id", "user_id",
    "target_sandbox_id", "actor_id", "role", "projection_input_fingerprint",
    "candidate_fingerprint", "displayed_counts", "issued_at_utc", "confirmed_at_utc",
    "expires_at_utc", "confirmation_fingerprint"
  )
  if (!setequal(names(confirmation), fields) ||
      .master_integer(confirmation$confirmation_contract_version, "master_confirmation_invalid") != 1L ||
      !.master_challenge_valid(confirmation$challenge_id) ||
      !.master_sha_valid(confirmation$confirmation_fingerprint)) {
    .master_abort("master_confirmation_invalid")
  }
  body <- confirmation[setdiff(names(confirmation), "confirmation_fingerprint")]
  if (!identical(.import_fingerprint(body), confirmation$confirmation_fingerprint)) {
    .master_abort("master_confirmation_fingerprint_mismatch")
  }
  expected <- list(
    tenant_id = context$tenant_id, user_id = context$user_id,
    target_sandbox_id = context$data_space_id, actor_id = context$actor_id, role = context$role,
    projection_input_fingerprint = validated$candidate$projection_input_fingerprint,
    candidate_fingerprint = validated$candidate_fingerprint,
    displayed_counts = validated$counts
  )
  for (name in names(expected)) {
    if (!identical(confirmation[[name]], expected[[name]])) {
      .master_abort("master_confirmation_scope_mismatch")
    }
  }
  issued <- .master_time(confirmation$issued_at_utc)
  confirmed <- .master_time(confirmation$confirmed_at_utc)
  expires <- .master_time(confirmation$expires_at_utc)
  now <- .master_time(now_utc)
  if (!(issued <= confirmed && confirmed <= now && now <= expires)) {
    .master_abort("master_confirmation_expired_or_time_invalid")
  }
  if (as.numeric(difftime(expires, issued, units = "secs")) > 600) {
    .master_abort("master_confirmation_validity_window_exceeded")
  }
  invisible(TRUE)
}

.master_consume_confirmation <- function(authorizer, confirmation) {
  if (!.master_authorizer_valid(authorizer) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .master_abort("master_confirmation_not_authorized")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, confirmation$confirmation_fingerprint)) {
    .master_abort("master_confirmation_not_authorized")
  }
  if (isTRUE(entry$consumed)) .master_abort("master_confirmation_already_consumed")
  entry$consumed <- TRUE
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  invisible(TRUE)
}

.master_assert_confirmation_consumed <- function(authorizer, confirmation) {
  if (!.master_authorizer_valid(authorizer) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .master_abort("master_confirmation_not_authorized")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, confirmation$confirmation_fingerprint) ||
      !isTRUE(entry$consumed)) {
    .master_abort("master_confirmation_not_authorized")
  }
  invisible(TRUE)
}

.master_id <- function(prefix, candidate_fingerprint, kind, staged_id) {
  paste0(prefix, substr(.import_hash_parts(c(candidate_fingerprint, kind, staged_id)), 1L, 24L))
}

.master_asset_origin_ref <- function(namespace, staged_id) {
  fingerprint <- digest::digest(charToRaw(staged_id), algo = "sha256", serialize = FALSE)
  paste0(namespace, "asset_", substr(fingerprint, 1L, 20L))
}

.master_source_run_id <- function(candidate) paste0("mimp_", substr(candidate$source_content_fingerprint, 1L, 24L))
.master_db_value <- function(value) if (is.null(value)) NA_character_ else value
.master_failpoint <- function(selected, current) if (identical(selected, current)) .master_abort("master_synthetic_failpoint")
.master_failpoints_v1 <- function() c("after_portfolio", "after_accounts", "after_assets", "after_audit", "after_receipt", "before_commit")

.master_write_entities <- function(connection, validated, context, committed_at_utc, failpoint) {
  candidate <- validated$candidate
  fingerprint <- validated$candidate_fingerprint
  portfolio <- candidate$portfolio
  portfolio_id <- .master_id("ptf_", fingerprint, "portfolio", portfolio$staged_portfolio_id)
  DBI::dbExecute(
    connection,
    paste(
      "INSERT INTO portfolio",
      "(portfolio_id, display_name, base_currency, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
      "VALUES (?, ?, ?, ?, 'native', NULL, ?, ?, 1)"
    ),
    params = list(portfolio_id, portfolio$display_name, portfolio$base_currency,
                  portfolio$status, committed_at_utc, committed_at_utc)
  )
  .master_failpoint(failpoint, "after_portfolio")
  for (account in candidate$accounts) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO account",
        "(account_id, portfolio_id, display_name, account_type, institution_label, status,",
        "origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
        "VALUES (?, ?, ?, ?, ?, ?, 'native', NULL, ?, ?, 1)"
      ),
      params = list(
        .master_id("acc_", fingerprint, "account", account$staged_account_id),
        portfolio_id, account$display_name, account$account_type,
        .master_db_value(account$institution_label), account$status,
        committed_at_utc, committed_at_utc
      )
    )
  }
  .master_failpoint(failpoint, "after_accounts")
  namespace <- paste0("lmr_", substr(fingerprint, 1L, 24L), "_")
  for (asset in candidate$assets) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO asset",
        "(asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method,",
        "isin, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'legacy_import', ?, ?, ?, 1)"
      ),
      params = list(
        .master_id("ast_", fingerprint, "asset", asset$staged_asset_id),
        asset$display_name, asset$asset_type, asset$price_currency,
        as.integer(asset$quantity_scale), asset$valuation_method, .master_db_value(asset$isin),
        asset$status, .master_asset_origin_ref(namespace, asset$staged_asset_id),
        committed_at_utc, committed_at_utc
      )
    )
  }
  .master_failpoint(failpoint, "after_assets")
  list(portfolio_id = portfolio_id, namespace = namespace)
}

.master_result <- function(status, command_id, validated, receipt_id) {
  list(
    status = status,
    command_id = command_id,
    candidate_fingerprint = validated$candidate_fingerprint,
    master_import_receipt_id = receipt_id,
    counts = validated$counts
  )
}

.master_execute_impl <- function(
  context, staging_capability, confirmation, authorizer, now_utc, failpoint,
  confirmation_preconsumed = FALSE
) {
  .master_context_check(context)
  if (!identical(failpoint, "none") && !failpoint %in% .master_failpoints_v1()) {
    .master_abort("master_command_boundary_failed")
  }
  validated <- .master_open_validated_staging(context, staging_capability)
  data_space <- runtime_data_space_path(context)
  lock <- tryCatch(.canonical_acquire_lock(data_space), error = function(error) NULL)
  if (is.null(lock)) .master_abort("master_command_boundary_failed")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .master_connect_canonical(context, read_only = FALSE)
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  if (.master_connection_in_transaction(connection)) .master_abort("master_canonical_connection_in_transaction")
  command_id <- .master_command_id(context, validated$candidate_fingerprint)
  state <- .master_idempotency(connection, validated, context)
  if (identical(state$status, "already_imported")) {
    return(.master_result("already_imported", command_id, validated, state$receipt_id))
  }
  if (!identical(state$status, "new_candidate")) .master_abort("master_idempotency_conflict")
  if (!.master_target_empty(connection)) .master_abort("master_target_sandbox_not_empty")
  .master_validate_confirmation(confirmation, validated, context, now_utc)
  if (isTRUE(confirmation_preconsumed)) {
    .master_assert_confirmation_consumed(authorizer, confirmation)
  } else {
    .master_consume_confirmation(authorizer, confirmation)
  }
  transaction_open <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    transaction_open <- TRUE
    .master_validate_canonical(connection, context, 0L)
    locked <- .master_idempotency(connection, validated, context)
    if (identical(locked$status, "already_imported")) {
      DBI::dbExecute(connection, "ROLLBACK")
      transaction_open <- FALSE
      return(.master_result("already_imported", command_id, validated, locked$receipt_id))
    }
    if (!identical(locked$status, "new_candidate")) .master_abort("master_idempotency_conflict")
    if (!.master_target_empty(connection)) .master_abort("master_target_sandbox_not_empty")
    written <- .master_write_entities(connection, validated, context, now_utc, failpoint)
    source_run_id <- .master_source_run_id(validated$candidate)
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
        "payload_fingerprint, origin_type, origin_ref)",
        "VALUES (?, 'canonical_import_receipt', 'legacy_master_bootstrap_v1', ?, ?, ?, ?, 'legacy_import', ?)"
      ),
      params = list(
        command_id, written$portfolio_id, context$actor_id, now_utc,
        validated$candidate_fingerprint, source_run_id
      )
    )
    .master_failpoint(failpoint, "after_audit")
    counts <- validated$counts
    receipt_payload <- list(
      command_id = command_id,
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      target_sandbox_id = context$data_space_id,
      target_portfolio_id = written$portfolio_id,
      source_contract_version = 1L,
      master_staging_schema_version = .master_staging_schema_version,
      canonical_schema_version = .master_canonical_schema_version,
      source_import_run_id = source_run_id,
      source_set_fingerprint = validated$candidate$source_content_fingerprint,
      projection_contract_fingerprint = .master_projection_contract_fingerprint,
      staging_artifact_fingerprint = validated$decision_fingerprint,
      candidate_fingerprint = validated$candidate_fingerprint,
      confirmation_fingerprint = confirmation$confirmation_fingerprint,
      origin_ref_namespace = written$namespace,
      portfolio_count = counts$portfolio_count,
      account_count = counts$account_count,
      asset_count = counts$asset_count,
      provider_mapping_count = counts$provider_mapping_count,
      actor_id = context$actor_id,
      committed_at_utc = now_utc
    )
    receipt_fingerprint <- .import_fingerprint(receipt_payload)
    receipt_id <- paste0("mrc_", substr(receipt_fingerprint, 1L, 32L))
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO canonical_master_import_receipt",
        "(master_import_receipt_id, command_id, tenant_id, user_id, target_sandbox_id, target_portfolio_id,",
        "source_contract_version, master_staging_schema_version, canonical_schema_version, source_import_run_id,",
        "source_set_fingerprint, projection_contract_fingerprint, staging_artifact_fingerprint,",
        "candidate_fingerprint, confirmation_fingerprint, origin_ref_namespace, portfolio_count, account_count,",
        "asset_count, provider_mapping_count, actor_id, committed_at_utc, receipt_fingerprint)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ),
      params = unname(c(list(receipt_id), receipt_payload, list(receipt_fingerprint)))
    )
    .master_failpoint(failpoint, "after_receipt")
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L ||
        !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
      .master_abort("master_canonical_integrity_invalid")
    }
    .master_failpoint(failpoint, "before_commit")
    DBI::dbExecute(connection, "COMMIT")
    transaction_open <- FALSE
    .master_result("committed", command_id, validated, receipt_id)
  }, error = function(error) {
    if (transaction_open && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_master_import_data_command_error")) stop(error)
    .master_abort("master_canonical_transaction_failed")
  })
}

master_import_private_execute_v1 <- function(
  context, contract_root, staging_capability, confirmation, authorizer,
  created_at_utc, now_utc
) {
  .master_boundary_eval({
    .master_context_check(context)
    capability_value <- .master_staging_capability_value(staging_capability)
    if (!identical(capability_value$execution_mode, "authorized_private_candidate")) {
      .master_abort("master_productive_candidate_not_enabled")
    }
    target <- runtime_canonical_path(context)
    if (file.exists(target)) {
      return(.master_execute_impl(
        context, staging_capability, confirmation, authorizer, now_utc, "none"
      ))
    }
    validated <- .master_open_validated_staging(context, staging_capability)
    .master_validate_confirmation(confirmation, validated, context, now_utc)
    .master_consume_confirmation(authorizer, confirmation)
    status <- .master_import_sandbox_bootstrap_impl(
      context, contract_root, created_at_utc, "authorized_private_candidate"
    )
    if (!identical(status$status, "created")) {
      .master_abort("master_sandbox_bootstrap_failed")
    }
    .master_execute_impl(
      context, staging_capability, confirmation, authorizer, now_utc, "none",
      confirmation_preconsumed = TRUE
    )
  }, fallback = "master_canonical_transaction_failed")
}

master_import_execute_v1 <- function(context, staging_capability, confirmation, authorizer, now_utc) {
  capability_value <- .master_staging_capability_value(staging_capability)
  if (!identical(capability_value$execution_mode, "synthetic_fixture")) {
    .master_abort("master_productive_candidate_not_enabled")
  }
  .master_boundary_eval(
    .master_execute_impl(context, staging_capability, confirmation, authorizer, now_utc, "none"),
    fallback = "master_canonical_transaction_failed"
  )
}
