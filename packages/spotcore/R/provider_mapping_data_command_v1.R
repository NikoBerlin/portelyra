provider_mapping_data_command_error_codes_v1 <- function() {
  c(
    "provider_mapping_context_invalid",
    "provider_mapping_role_not_authorized",
    "provider_mapping_repository_invalid",
    "provider_mapping_input_invalid",
    "provider_mapping_asset_invalid",
    "provider_mapping_not_found",
    "provider_mapping_state_invalid",
    "provider_mapping_revision_conflict",
    "provider_mapping_duplicate_conflict",
    "provider_mapping_idempotency_conflict",
    "provider_mapping_integrity_invalid",
    "provider_mapping_lock_unavailable",
    "provider_mapping_transaction_failed",
    "provider_mapping_boundary_failed"
  )
}

.provider_mapping_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% provider_mapping_data_command_error_codes_v1()) {
    stop("provider_mapping_error_code_unregistered", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_provider_mapping_error_v1", "error", "condition")
  )
}

.provider_mapping_abort_v1 <- function(code) stop(.provider_mapping_condition_v1(code))

.provider_mapping_boundary_v1 <- function(expression, fallback = "provider_mapping_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_provider_mapping_error_v1 = function(error) error,
    spot_catalog_data_command_error = function(error) .provider_mapping_condition_v1("provider_mapping_repository_invalid"),
    spot_canonical_repository_error = function(error) .provider_mapping_condition_v1("provider_mapping_repository_invalid"),
    spot_runtime_error = function(error) .provider_mapping_condition_v1("provider_mapping_context_invalid"),
    error = function(error) .provider_mapping_condition_v1(fallback)
  )
  if (inherits(result, "spot_provider_mapping_error_v1")) stop(result)
  result
}

.provider_mapping_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .provider_mapping_abort_v1("provider_mapping_context_invalid")
  }
  if (!identical(context$role, "desktop_owner")) {
    .provider_mapping_abort_v1("provider_mapping_role_not_authorized")
  }
  invisible(TRUE)
}

.provider_mapping_columns_v1 <- c(
  "mapping_id", "asset_id", "capability", "provider_id", "provider_symbol",
  "exchange_code", "mic_code", "provider_currency", "verification_status",
  "expert_only", "enabled", "verified_at_utc", "created_at_utc", "updated_at_utc", "revision"
)

.provider_mapping_row_v1 <- function(frame) {
  if (!is.data.frame(frame) || nrow(frame) != 1L) .provider_mapping_abort_v1("provider_mapping_integrity_invalid")
  row <- vector("list", length(.provider_mapping_columns_v1))
  names(row) <- .provider_mapping_columns_v1
  for (column in .provider_mapping_columns_v1) {
    value <- frame[[column]][[1L]]
    if (length(value) != 1L || is.na(value)) {
      row[column] <- list(NULL)
    } else if (column %in% c("expert_only", "enabled", "revision")) {
      row[[column]] <- as.integer(value)
    } else {
      row[[column]] <- as.character(value)
    }
  }
  row
}

.provider_mapping_fetch_v1 <- function(connection, mapping_id, required = TRUE) {
  frame <- DBI::dbGetQuery(
    connection,
    paste0(
      "SELECT ", paste(.provider_mapping_columns_v1, collapse = ", "),
      " FROM provider_mapping WHERE mapping_id=?"
    ),
    params = list(mapping_id)
  )
  if (!nrow(frame)) {
    if (isTRUE(required)) .provider_mapping_abort_v1("provider_mapping_not_found")
    return(NULL)
  }
  .provider_mapping_row_v1(frame)
}

.provider_mapping_entity_fingerprint_v1 <- function(row) {
  .catalog_fingerprint(list(
    provider_mapping_state_version = 1L,
    provider_mapping = row
  ))
}

.provider_mapping_text_v1 <- function(value, maximum, optional = FALSE) {
  if (isTRUE(optional) && is.null(value)) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !nzchar(value) || !identical(value, trimws(value)) ||
      nchar(value, type = "bytes") > maximum || grepl("[\r\n\t]", value)) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  value
}

.provider_mapping_id_valid_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^map_[a-z0-9_]{4,60}$", value) && nchar(value, type = "bytes") <= 64L
}

.provider_mapping_provider_v1 <- function(value) {
  value <- .provider_mapping_text_v1(value, 64L)
  if (!grepl("^[a-z0-9_]{2,64}$", value) ||
      value %in% c("fmp", "financial_modeling_prep", "financialmodelingprep")) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  value
}

.provider_mapping_fields_v1 <- function(
  provider_symbol, exchange_code, mic_code, provider_currency, expert_only
) {
  symbol <- .provider_mapping_text_v1(provider_symbol, 120L)
  exchange <- if (is.null(exchange_code)) NULL else .provider_mapping_text_v1(exchange_code, 80L)
  mic <- if (is.null(mic_code)) NULL else .provider_mapping_text_v1(mic_code, 4L)
  currency <- .provider_mapping_text_v1(provider_currency, 3L)
  if (!is.null(mic) && !grepl("^[A-Z0-9]{4}$", mic) || !grepl("^[A-Z]{3}$", currency) ||
      !is.logical(expert_only) || length(expert_only) != 1L || is.na(expert_only)) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  list(
    provider_symbol = symbol,
    exchange_code = exchange,
    mic_code = mic,
    provider_currency = currency,
    expert_only = as.integer(expert_only)
  )
}

.provider_mapping_command_id_v1 <- function(context, command_type, command_token, mapping_id = NULL) {
  parts <- c(
    "provider-mapping-command-v1", context$tenant_id, context$user_id,
    context$data_space_id, command_type, command_token
  )
  if (!is.null(mapping_id)) parts <- c(parts, mapping_id)
  paste0("cmd_provider_", substr(.catalog_hash_parts(parts), 1L, 51L))
}

.provider_mapping_created_id_v1 <- function(context, command_token) {
  paste0("map_", substr(.catalog_hash_parts(c(
    "provider-mapping-entity-v1", context$tenant_id, context$user_id,
    context$data_space_id, command_token
  )), 1L, 24L))
}

.provider_mapping_build_command_v1 <- function(
  context, action, command_token, committed_at_utc, fields,
  mapping_id = NULL, expected_revision = NULL
) {
  .provider_mapping_context_v1(context)
  if (!action %in% c("create", "revise", "verify", "disable") ||
      !.catalog_token_valid(command_token) || !.canonical_utc_valid(committed_at_utc) ||
      !is.list(fields)) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  if (identical(action, "create")) {
    if (!is.null(mapping_id) || !is.null(expected_revision)) {
      .provider_mapping_abort_v1("provider_mapping_input_invalid")
    }
    mapping_id <- .provider_mapping_created_id_v1(context, command_token)
  } else if (!.provider_mapping_id_valid_v1(mapping_id) || !.catalog_revision_valid(expected_revision)) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  command_id_type <- paste0("provider_mapping_", action, "_v1")
  command_type <- command_id_type
  if (identical(action, "verify")) {
    evidence <- fields$probe_evidence_fingerprint
    if (!is.character(evidence) || length(evidence) != 1L || is.na(evidence) ||
        !grepl("^[a-f0-9]{64}$", evidence)) {
      .provider_mapping_abort_v1("provider_mapping_input_invalid")
    }
    command_type <- paste0(command_type, "_", substr(evidence, 1L, 48L))
  }
  structure(list(
    provider_mapping_command_contract_version = 1L,
    action = action,
    command_type = command_type,
    command_token = command_token,
    command_id = .provider_mapping_command_id_v1(
      context, command_id_type, command_token, if (identical(action, "create")) NULL else mapping_id
    ),
    mapping_id = mapping_id,
    expected_revision = expected_revision,
    committed_at_utc = committed_at_utc,
    fields = fields
  ), class = "spot_provider_mapping_command_v1")
}

.provider_mapping_build_create_v1 <- function(
  context, command_token, asset_id, capability, provider_id, provider_symbol,
  exchange_code, mic_code, provider_currency, expert_only, committed_at_utc
) {
  provider <- .provider_mapping_provider_v1(provider_id)
  if (!.catalog_id_valid(asset_id, "asset") ||
      !is.character(capability) || length(capability) != 1L || is.na(capability) ||
      !capability %in% c("daily_history", "quote", "intraday", "fundamentals", "fx")) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  mapping_fields <- .provider_mapping_fields_v1(
    provider_symbol, exchange_code, mic_code, provider_currency, expert_only
  )
  if (identical(provider, "twelve_data") && mapping_fields$expert_only != 1L) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  .provider_mapping_build_command_v1(
    context, "create", command_token, committed_at_utc,
    c(list(asset_id = asset_id, capability = capability, provider_id = provider), mapping_fields)
  )
}

.provider_mapping_build_revise_v1 <- function(
  context, command_token, mapping_id, expected_revision, provider_symbol,
  exchange_code, mic_code, provider_currency, expert_only, committed_at_utc
) {
  .provider_mapping_build_command_v1(
    context, "revise", command_token, committed_at_utc,
    .provider_mapping_fields_v1(
      provider_symbol, exchange_code, mic_code, provider_currency, expert_only
    ),
    mapping_id, expected_revision
  )
}

.provider_mapping_build_verify_v1 <- function(
  context, command_token, mapping_id, expected_revision,
  probe_evidence_fingerprint, committed_at_utc
) {
  .provider_mapping_build_command_v1(
    context, "verify", command_token, committed_at_utc,
    list(probe_evidence_fingerprint = probe_evidence_fingerprint),
    mapping_id, expected_revision
  )
}

.provider_mapping_build_disable_v1 <- function(
  context, command_token, mapping_id, expected_revision, committed_at_utc
) {
  .provider_mapping_build_command_v1(
    context, "disable", command_token, committed_at_utc, list(),
    mapping_id, expected_revision
  )
}

.provider_mapping_expected_row_v1 <- function(connection, command) {
  fields <- command$fields
  if (identical(command$action, "create")) {
    return(list(
      mapping_id = command$mapping_id,
      asset_id = fields$asset_id,
      capability = fields$capability,
      provider_id = fields$provider_id,
      provider_symbol = fields$provider_symbol,
      exchange_code = fields$exchange_code,
      mic_code = fields$mic_code,
      provider_currency = fields$provider_currency,
      verification_status = "unverified",
      expert_only = fields$expert_only,
      enabled = 0L,
      verified_at_utc = NULL,
      created_at_utc = command$committed_at_utc,
      updated_at_utc = command$committed_at_utc,
      revision = 1L
    ))
  }
  row <- .provider_mapping_fetch_v1(connection, command$mapping_id)
  row$updated_at_utc <- command$committed_at_utc
  row$revision <- command$expected_revision + 1L
  if (identical(command$action, "revise")) {
    row$provider_symbol <- fields$provider_symbol
    row$exchange_code <- fields$exchange_code
    row$mic_code <- fields$mic_code
    row$provider_currency <- fields$provider_currency
    row$expert_only <- fields$expert_only
    row$verification_status <- "unverified"
    row$enabled <- 0L
    row$verified_at_utc <- NULL
  } else if (identical(command$action, "verify")) {
    row$verification_status <- "verified"
    row$enabled <- if (identical(row$provider_id, "twelve_data")) 0L else 1L
    row$verified_at_utc <- command$committed_at_utc
  } else {
    row$verification_status <- "disabled"
    row$enabled <- 0L
  }
  row
}

.provider_mapping_latest_audit_v1 <- function(connection, mapping_id) {
  DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id,area_id,command_type,entity_id,actor_id,committed_at_utc,",
      "payload_fingerprint,origin_type,origin_ref FROM data_command_audit",
      "WHERE area_id='provider_mapping' AND entity_id=?",
      "ORDER BY committed_at_utc DESC,command_id DESC LIMIT 2"
    ),
    params = list(mapping_id)
  )
}

.provider_mapping_validate_entity_v1 <- function(connection, mapping_id, context) {
  row <- .provider_mapping_fetch_v1(connection, mapping_id)
  asset <- tryCatch(
    .catalog_validate_reference_entity(connection, "asset", row$asset_id, context),
    spot_catalog_data_command_error = function(error) NULL
  )
  if (is.null(asset)) .provider_mapping_abort_v1("provider_mapping_asset_invalid")
  audit <- .provider_mapping_latest_audit_v1(connection, mapping_id)
  allowed <- c(
    "provider_mapping_create_v1", "provider_mapping_revise_v1", "provider_mapping_disable_v1"
  )
  valid_command <- nrow(audit) >= 1L && (
    audit$command_type[[1L]] %in% allowed ||
      grepl("^provider_mapping_verify_v1_[a-f0-9]{48}$", audit$command_type[[1L]])
  )
  if (!valid_command || nrow(audit) > 1L && identical(audit$committed_at_utc[[1L]], audit$committed_at_utc[[2L]]) ||
      !identical(audit$entity_id[[1L]], mapping_id) ||
      !identical(audit$actor_id[[1L]], context$actor_id) ||
      !identical(audit$committed_at_utc[[1L]], row$updated_at_utc) ||
      !identical(audit$payload_fingerprint[[1L]], .provider_mapping_entity_fingerprint_v1(row)) ||
      !identical(audit$origin_type[[1L]], "native") || !is.na(audit$origin_ref[[1L]])) {
    .provider_mapping_abort_v1("provider_mapping_integrity_invalid")
  }
  if (identical(row$verification_status, "verified") &&
      !grepl("^provider_mapping_verify_v1_[a-f0-9]{48}$", audit$command_type[[1L]])) {
    .provider_mapping_abort_v1("provider_mapping_integrity_invalid")
  }
  row
}

.provider_mapping_existing_command_v1 <- function(connection, command, context) {
  audit <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id,area_id,command_type,entity_id,actor_id,committed_at_utc,",
      "payload_fingerprint,origin_type,origin_ref FROM data_command_audit WHERE command_id=?"
    ),
    params = list(command$command_id)
  )
  if (!nrow(audit)) return(NULL)
  if (nrow(audit) != 1L) .provider_mapping_abort_v1("provider_mapping_integrity_invalid")
  expected <- .provider_mapping_expected_row_v1(connection, command)
  fingerprint <- .provider_mapping_entity_fingerprint_v1(expected)
  if (!identical(audit$area_id[[1L]], "provider_mapping") ||
      !identical(audit$command_type[[1L]], command$command_type) ||
      !identical(audit$entity_id[[1L]], command$mapping_id) ||
      !identical(audit$actor_id[[1L]], context$actor_id) ||
      !identical(audit$committed_at_utc[[1L]], command$committed_at_utc) ||
      !identical(audit$payload_fingerprint[[1L]], fingerprint) ||
      !identical(audit$origin_type[[1L]], "native") || !is.na(audit$origin_ref[[1L]])) {
    .provider_mapping_abort_v1("provider_mapping_idempotency_conflict")
  }
  list(row = expected, fingerprint = fingerprint)
}

.provider_mapping_precondition_v1 <- function(row, command) {
  if (!identical(row$revision, command$expected_revision)) {
    .provider_mapping_abort_v1("provider_mapping_revision_conflict")
  }
  if (!.catalog_time_later(command$committed_at_utc, row$updated_at_utc)) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  if (identical(command$action, "verify") && !row$verification_status %in% c("unverified", "verified")) {
    .provider_mapping_abort_v1("provider_mapping_state_invalid")
  }
  invisible(TRUE)
}

.provider_mapping_apply_v1 <- function(connection, command, context) {
  fields <- command$fields
  if (identical(command$action, "create")) {
    if (!is.null(.provider_mapping_fetch_v1(connection, command$mapping_id, required = FALSE))) {
      .provider_mapping_abort_v1("provider_mapping_duplicate_conflict")
    }
    asset <- tryCatch(
      .catalog_validate_reference_entity(connection, "asset", fields$asset_id, context),
      spot_catalog_data_command_error = function(error) NULL
    )
    if (is.null(asset) || !identical(asset$status, "active")) {
      .provider_mapping_abort_v1("provider_mapping_asset_invalid")
    }
    duplicate <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT count(*) AS n FROM provider_mapping",
        "WHERE asset_id=? AND capability=? AND provider_id=?"
      ),
      params = list(fields$asset_id, fields$capability, fields$provider_id)
    )$n[[1L]]
    if (as.integer(duplicate) != 0L) .provider_mapping_abort_v1("provider_mapping_duplicate_conflict")
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO provider_mapping",
        "(mapping_id,asset_id,capability,provider_id,provider_symbol,exchange_code,mic_code,provider_currency,",
        "verification_status,expert_only,enabled,verified_at_utc,created_at_utc,updated_at_utc,revision)",
        "VALUES (?,?,?,?,?,?,?,?,'unverified',?,0,NULL,?,?,1)"
      ),
      params = list(
        command$mapping_id, fields$asset_id, fields$capability, fields$provider_id,
        fields$provider_symbol,
        if (is.null(fields$exchange_code)) NA_character_ else fields$exchange_code,
        if (is.null(fields$mic_code)) NA_character_ else fields$mic_code,
        fields$provider_currency, fields$expert_only,
        command$committed_at_utc, command$committed_at_utc
      )
    )
    return(invisible(TRUE))
  }
  row <- .provider_mapping_validate_entity_v1(connection, command$mapping_id, context)
  .provider_mapping_precondition_v1(row, command)
  asset <- tryCatch(
    .catalog_validate_reference_entity(connection, "asset", row$asset_id, context),
    spot_catalog_data_command_error = function(error) NULL
  )
  if (!identical(command$action, "disable") && (is.null(asset) || !identical(asset$status, "active"))) {
    .provider_mapping_abort_v1("provider_mapping_asset_invalid")
  }
  if (identical(command$action, "revise")) {
    if (identical(row$provider_id, "twelve_data") && fields$expert_only != 1L) {
      .provider_mapping_abort_v1("provider_mapping_input_invalid")
    }
    DBI::dbExecute(
      connection,
      paste(
        "UPDATE provider_mapping SET provider_symbol=?,exchange_code=?,mic_code=?,provider_currency=?,",
        "verification_status='unverified',expert_only=?,enabled=0,verified_at_utc=NULL,",
        "updated_at_utc=?,revision=revision+1 WHERE mapping_id=?"
      ),
      params = list(
        fields$provider_symbol,
        if (is.null(fields$exchange_code)) NA_character_ else fields$exchange_code,
        if (is.null(fields$mic_code)) NA_character_ else fields$mic_code,
        fields$provider_currency, fields$expert_only, command$committed_at_utc, command$mapping_id
      )
    )
  } else if (identical(command$action, "verify")) {
    enabled <- if (identical(row$provider_id, "twelve_data")) 0L else 1L
    DBI::dbExecute(
      connection,
      paste(
        "UPDATE provider_mapping SET verification_status='verified',enabled=?,verified_at_utc=?,",
        "updated_at_utc=?,revision=revision+1 WHERE mapping_id=?"
      ),
      params = list(enabled, command$committed_at_utc, command$committed_at_utc, command$mapping_id)
    )
  } else {
    DBI::dbExecute(
      connection,
      paste(
        "UPDATE provider_mapping SET verification_status='disabled',enabled=0,",
        "updated_at_utc=?,revision=revision+1 WHERE mapping_id=?"
      ),
      params = list(command$committed_at_utc, command$mapping_id)
    )
  }
  invisible(TRUE)
}

.provider_mapping_result_v1 <- function(command, status, row, fingerprint) {
  list(
    provider_mapping_command_contract_version = 1L,
    status = status,
    command_type = command$command_type,
    command_id = command$command_id,
    mapping_id = command$mapping_id,
    entity_fingerprint = fingerprint,
    revision = row$revision,
    verification_status = row$verification_status,
    enabled = as.logical(row$enabled),
    committed_at_utc = command$committed_at_utc
  )
}

.provider_mapping_execute_impl_v1 <- function(context, command, failpoint = "none") {
  .provider_mapping_context_v1(context)
  if (!inherits(command, "spot_provider_mapping_command_v1") ||
      !identical(command$provider_mapping_command_contract_version, 1L) ||
      !failpoint %in% c("none", "after_mapping", "before_commit")) {
    .provider_mapping_abort_v1("provider_mapping_input_invalid")
  }
  data_space <- runtime_data_space_path(context)
  lock <- tryCatch(.canonical_acquire_lock(data_space), spot_canonical_repository_error = function(error) NULL)
  if (is.null(lock)) .provider_mapping_abort_v1("provider_mapping_lock_unavailable")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- tryCatch(
    .catalog_connect_write(context),
    spot_catalog_data_command_error = function(error) NULL
  )
  if (is.null(connection)) .provider_mapping_abort_v1("provider_mapping_repository_invalid")
  on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
  replay <- .provider_mapping_existing_command_v1(connection, command, context)
  if (!is.null(replay)) {
    return(.provider_mapping_result_v1(command, "already_committed", replay$row, replay$fingerprint))
  }
  tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    replay <- .provider_mapping_existing_command_v1(connection, command, context)
    if (!is.null(replay)) {
      DBI::dbExecute(connection, "ROLLBACK")
      return(.provider_mapping_result_v1(command, "already_committed", replay$row, replay$fingerprint))
    }
    .provider_mapping_apply_v1(connection, command, context)
    row <- .provider_mapping_fetch_v1(connection, command$mapping_id)
    fingerprint <- .provider_mapping_entity_fingerprint_v1(row)
    if (identical(failpoint, "after_mapping")) stop("synthetic_provider_mapping_failpoint", call. = FALSE)
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id,area_id,command_type,entity_id,actor_id,committed_at_utc,payload_fingerprint,origin_type,origin_ref)",
        "VALUES (?,'provider_mapping',?,?,?,?,?,'native',NULL)"
      ),
      params = list(
        command$command_id, command$command_type, command$mapping_id,
        context$actor_id, command$committed_at_utc, fingerprint
      )
    )
    .provider_mapping_validate_entity_v1(connection, command$mapping_id, context)
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L ||
        !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1L]], "ok")) {
      .provider_mapping_abort_v1("provider_mapping_integrity_invalid")
    }
    if (identical(failpoint, "before_commit")) stop("synthetic_provider_mapping_failpoint", call. = FALSE)
    DBI::dbExecute(connection, "COMMIT")
    .provider_mapping_result_v1(command, "committed", row, fingerprint)
  }, error = function(error) {
    if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_provider_mapping_error_v1")) stop(error)
    .provider_mapping_abort_v1("provider_mapping_transaction_failed")
  })
}

.provider_mapping_execute_v1 <- function(context, command) {
  .provider_mapping_boundary_v1(
    .provider_mapping_execute_impl_v1(context, command, "none"),
    fallback = "provider_mapping_transaction_failed"
  )
}

provider_mapping_create_v1 <- function(
  context, command_token, asset_id, capability, provider_id, provider_symbol,
  exchange_code = NULL, mic_code = NULL, provider_currency,
  expert_only = FALSE, committed_at_utc
) {
  .provider_mapping_boundary_v1({
    command <- .provider_mapping_build_create_v1(
      context, command_token, asset_id, capability, provider_id, provider_symbol,
      exchange_code, mic_code, provider_currency, expert_only, committed_at_utc
    )
    .provider_mapping_execute_v1(context, command)
  })
}

provider_mapping_revise_v1 <- function(
  context, command_token, mapping_id, expected_revision, provider_symbol,
  exchange_code = NULL, mic_code = NULL, provider_currency,
  expert_only = FALSE, committed_at_utc
) {
  .provider_mapping_boundary_v1({
    command <- .provider_mapping_build_revise_v1(
      context, command_token, mapping_id, expected_revision, provider_symbol,
      exchange_code, mic_code, provider_currency, expert_only, committed_at_utc
    )
    .provider_mapping_execute_v1(context, command)
  })
}

provider_mapping_verify_v1 <- function(
  context, command_token, mapping_id, expected_revision,
  probe_evidence_fingerprint, committed_at_utc
) {
  .provider_mapping_boundary_v1({
    command <- .provider_mapping_build_verify_v1(
      context, command_token, mapping_id, expected_revision,
      probe_evidence_fingerprint, committed_at_utc
    )
    .provider_mapping_execute_v1(context, command)
  })
}

provider_mapping_disable_v1 <- function(
  context, command_token, mapping_id, expected_revision, committed_at_utc
) {
  .provider_mapping_boundary_v1({
    command <- .provider_mapping_build_disable_v1(
      context, command_token, mapping_id, expected_revision, committed_at_utc
    )
    .provider_mapping_execute_v1(context, command)
  })
}

provider_mapping_read_v1 <- function(context) {
  .provider_mapping_boundary_v1({
    .provider_mapping_context_v1(context)
    connection <- tryCatch(
      .catalog_connect_read(context),
      spot_catalog_data_command_error = function(error) NULL
    )
    if (is.null(connection)) .provider_mapping_abort_v1("provider_mapping_repository_invalid")
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    ids <- DBI::dbGetQuery(
      connection,
      "SELECT mapping_id FROM provider_mapping ORDER BY mapping_id"
    )$mapping_id
    rows <- lapply(ids, function(mapping_id) {
      row <- .provider_mapping_validate_entity_v1(connection, mapping_id, context)
      audit <- .provider_mapping_latest_audit_v1(connection, mapping_id)
      row$verification_evidence_ref <- if (
        identical(row$verification_status, "verified") &&
          grepl("^provider_mapping_verify_v1_[a-f0-9]{48}$", audit$command_type[[1L]])
      ) sub("^provider_mapping_verify_v1_", "evd_", audit$command_type[[1L]]) else NULL
      row
    })
    payload <- list(
      provider_mapping_read_contract_version = 1L,
      status = "ready",
      mappings = rows,
      count = as.integer(length(rows)),
      provider_access = FALSE,
      network_access = FALSE,
      canonical_write = FALSE
    )
    payload$provider_mapping_fingerprint <- .catalog_fingerprint(payload)
    payload
  }, fallback = "provider_mapping_repository_invalid")
}
