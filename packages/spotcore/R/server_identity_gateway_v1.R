server_identity_error_codes_v1 <- function() {
  c(
    "server_claims_invalid", "server_context_mismatch", "server_capability_denied",
    "server_cross_user_access_blocked", "server_path_scope_invalid",
    "server_default_user_forbidden", "server_auth_provider_required",
    "server_mail_capability_required", "server_principal_deactivated",
    "server_session_stale", "server_session_expired", "server_session_revoked",
    "server_job_binding_invalid", "server_job_signature_invalid", "server_job_expired",
    "server_job_replay", "server_identity_assertion_invalid",
    "server_identity_not_provisioned", "server_identity_conflict",
    "server_identity_store_invalid", "server_data_space_denied",
    "server_lifecycle_conflict", "server_auth_audit_invalid",
    "server_email_storage_forbidden", "server_raw_token_forbidden",
    "server_bootstrap_capability_invalid", "server_bootstrap_consumed"
  )
}

.server_identity_abort_v1 <- function(code) {
  if (!code %in% server_identity_error_codes_v1()) stop("unregistered_server_identity_error", call. = FALSE)
  condition <- structure(list(message = code, call = NULL, code = code), class = c("portelyra_server_identity_error_v1", "error", "condition"))
  stop(condition)
}

.server_identity_id_valid_v1 <- function(value, maximum = 64L) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 3L && nchar(value, type = "bytes") <= maximum &&
    grepl("^[A-Za-z0-9_-]+$", value, perl = TRUE)
}

.server_identity_fingerprint_valid_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[a-f0-9]{64}$", value, perl = TRUE)
}

.server_identity_data_space_valid_v1 <- function(value, control_allowed = FALSE) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    ((isTRUE(control_allowed) && identical(value, "control_plane")) || grepl("^sbx_[a-z0-9_]{4,59}$", value, perl = TRUE))
}

.server_identity_utc_seconds_v1 <- function(value, code = "server_claims_invalid") {
  valid <- is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value, perl = TRUE)
  parsed <- if (valid) suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) else as.POSIXct(NA)
  if (!valid || is.na(parsed) || !identical(format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), value)) .server_identity_abort_v1(code)
  as.numeric(parsed)
}

.server_identity_random_ref_v1 <- function(prefix) {
  bytes <- openssl::rand_bytes(16L)
  paste0(prefix, paste(sprintf("%02x", as.integer(bytes)), collapse = ""))
}

.server_identity_canonical_bytes_v1 <- function(value) {
  charToRaw(enc2utf8(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA)))
}

.server_identity_fingerprint_v1 <- function(value) {
  digest::digest(.server_identity_canonical_bytes_v1(value), algo = "sha256", serialize = FALSE)
}

server_identity_role_capabilities_v1 <- function(role) {
  policy <- list(
    server_user = c("backup_export", "csv_apply", "csv_export", "csv_inbox", "manage_preferences", "plugin_run", "read_display", "restore_preflight", "submit_job"),
    server_admin = c("manage_users", "read_auth_audit"),
    server_support = "read_auth_audit",
    worker = "execute_bound_job",
    desktop_owner = c("csv_apply", "csv_export", "csv_inbox", "manage_preferences", "plugin_run", "read_display")
  )
  if (!is.character(role) || length(role) != 1L || is.na(role) || !role %in% names(policy)) .server_identity_abort_v1("server_claims_invalid")
  sort(unname(policy[[role]]))
}

server_identity_job_capabilities_v1 <- function() {
  c(
    "fifo_projection_run", "realized_tax_projection_run", "market_history_sync_run",
    "fx_conversion_run", "unrealized_valuation_run", "trade_analysis_run",
    "market_analysis_run", "backup_export_run", "restore_preflight_run"
  )
}

new_verified_oidc_identity_v1 <- function(
  issuer_fingerprint, subject_fingerprint, audience_id,
  authentication_time_utc, expires_at_utc,
  assurance_level = "oidc_single_factor", email_verified = TRUE,
  verification_source = "approved_oidc_gateway",
  provider_protocol = "oidc_authorization_code_pkce_v1"
) {
  authentication_seconds <- .server_identity_utc_seconds_v1(authentication_time_utc, "server_identity_assertion_invalid")
  expiration_seconds <- .server_identity_utc_seconds_v1(expires_at_utc, "server_identity_assertion_invalid")
  valid <- .server_identity_fingerprint_valid_v1(issuer_fingerprint) &&
    .server_identity_fingerprint_valid_v1(subject_fingerprint) &&
    .server_identity_id_valid_v1(audience_id) &&
    identical(verification_source, "approved_oidc_gateway") &&
    identical(provider_protocol, "oidc_authorization_code_pkce_v1") &&
    identical(email_verified, TRUE) &&
    assurance_level %in% c("oidc_single_factor", "oidc_mfa") &&
    expiration_seconds > authentication_seconds
  if (!isTRUE(valid)) .server_identity_abort_v1("server_identity_assertion_invalid")
  body <- list(
    contract_version = "verified_oidc_identity_v1",
    verification_source = verification_source,
    provider_protocol = provider_protocol,
    issuer_fingerprint = issuer_fingerprint,
    subject_fingerprint = subject_fingerprint,
    audience_id = audience_id,
    authentication_time_utc = authentication_time_utc,
    expires_at_utc = expires_at_utc,
    email_verified = TRUE,
    email_policy = "identity_provider_verified_unique_normalized",
    assurance_level = assurance_level
  )
  body$identity_fingerprint <- .server_identity_fingerprint_v1(body)
  class(body) <- c("portelyra_verified_oidc_identity_v1", "list")
  body
}

verified_oidc_identity_valid_v1 <- function(identity, at_utc = NULL) {
  if (!inherits(identity, "portelyra_verified_oidc_identity_v1")) return(FALSE)
  isTRUE(tryCatch({
    rebuilt <- new_verified_oidc_identity_v1(
      identity$issuer_fingerprint, identity$subject_fingerprint, identity$audience_id,
      identity$authentication_time_utc, identity$expires_at_utc,
      identity$assurance_level, identity$email_verified,
      identity$verification_source, identity$provider_protocol
    )
    if (!identical(rebuilt$identity_fingerprint, identity$identity_fingerprint)) return(FALSE)
    if (!is.null(at_utc)) {
      at_seconds <- .server_identity_utc_seconds_v1(at_utc, "server_identity_assertion_invalid")
      auth_seconds <- .server_identity_utc_seconds_v1(identity$authentication_time_utc, "server_identity_assertion_invalid")
      expiration_seconds <- .server_identity_utc_seconds_v1(identity$expires_at_utc, "server_identity_assertion_invalid")
      if (at_seconds < auth_seconds || at_seconds >= expiration_seconds) return(FALSE)
    }
    TRUE
  }, error = function(error) FALSE))
}

.server_identity_reject_sensitive_v1 <- function(values) {
  values <- as.character(values)
  if (any(grepl("@", values, fixed = TRUE)) || any(grepl("^(eyJ|Bearer |Basic )", values, perl = TRUE, ignore.case = TRUE))) {
    code <- if (any(grepl("@", values, fixed = TRUE))) "server_email_storage_forbidden" else "server_raw_token_forbidden"
    .server_identity_abort_v1(code)
  }
  invisible(TRUE)
}

.server_identity_path_component_symlink_v1 <- function(path) {
  expanded <- path.expand(path)
  if (!startsWith(expanded, "/")) expanded <- file.path(getwd(), expanded)
  segments <- strsplit(sub("^/", "", expanded), "/", fixed = TRUE)[[1L]]
  current <- "/"
  for (segment in segments[nzchar(segments)]) {
    current <- file.path(current, segment)
    if ((file.exists(current) || dir.exists(current)) && nzchar(Sys.readlink(current))) return(TRUE)
  }
  FALSE
}

.server_identity_owner_only_v1 <- function(path) {
  information <- file.info(path)
  nrow(information) == 1L && !is.na(information$mode[[1L]]) && bitwAnd(as.integer(information$mode[[1L]]), 63L) == 0L
}

.server_identity_store_path_v1 <- function(database_path, must_exist = TRUE) {
  if (!is.character(database_path) || length(database_path) != 1L || is.na(database_path) || !nzchar(database_path)) .server_identity_abort_v1("server_identity_store_invalid")
  expanded <- path.expand(database_path)
  parent <- dirname(expanded)
  if (!dir.exists(parent) || .server_identity_path_component_symlink_v1(parent) || !.server_identity_owner_only_v1(parent)) .server_identity_abort_v1("server_identity_store_invalid")
  parent <- tryCatch(normalizePath(parent, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(parent)) .server_identity_abort_v1("server_identity_store_invalid")
  path <- file.path(parent, basename(database_path))
  if (isTRUE(must_exist) && (!file.exists(path) || dir.exists(path) || .server_identity_path_component_symlink_v1(path) || !.server_identity_owner_only_v1(path))) .server_identity_abort_v1("server_identity_store_invalid")
  if (file.exists(path) && (.server_identity_path_component_symlink_v1(path) || !.server_identity_owner_only_v1(path))) .server_identity_abort_v1("server_identity_store_invalid")
  path
}

.server_identity_default_schema_path_v1 <- function() {
  installed <- system.file("sql", "server_identity_v1.sql", package = "spotcore")
  path <- if (nzchar(installed)) installed else file.path("contracts", "server-multi-user", "v1", "schema.sql")
  if (!file.exists(path) || dir.exists(path)) .server_identity_abort_v1("server_identity_store_invalid")
  path
}

.server_identity_connect_v1 <- function(database_path, write = FALSE, validate = TRUE) {
  path <- .server_identity_store_path_v1(database_path, must_exist = TRUE)
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = if (isTRUE(write)) RSQLite::SQLITE_RW else RSQLite::SQLITE_RO),
    error = function(error) .server_identity_abort_v1("server_identity_store_invalid")
  )
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
    DBI::dbExecute(connection, "PRAGMA busy_timeout=5000")
    DBI::dbExecute(connection, paste0("PRAGMA query_only=", if (isTRUE(write)) "OFF" else "ON"))
    if (isTRUE(validate)) {
      meta <- DBI::dbGetQuery(connection, "SELECT schema_version, writer_role, schema_fingerprint FROM identity_meta WHERE singleton=1")
      tables <- DBI::dbGetQuery(connection, "SELECT name FROM sqlite_master WHERE type='table'")$name
      required <- c("identity_meta", "auth_provider_policy", "auth_principal", "auth_data_space_access", "auth_session", "auth_job_nonce", "auth_audit")
      expected_schema_fingerprint <- digest::digest(file = .server_identity_default_schema_path_v1(), algo = "sha256", serialize = FALSE)
      if (nrow(meta) != 1L || meta$schema_version[[1L]] != 2800L || meta$writer_role[[1L]] != "identity_gateway" || meta$schema_fingerprint[[1L]] != expected_schema_fingerprint || !all(required %in% tables)) {
        .server_identity_abort_v1("server_identity_store_invalid")
      }
    }
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    .server_identity_abort_v1("server_identity_store_invalid")
  })
  connection
}

.server_identity_execute_schema_v1 <- function(connection, schema_path) {
  sql <- paste(readLines(schema_path, warn = FALSE), collapse = "\n")
  statements <- trimws(unlist(strsplit(sql, ";", fixed = TRUE)))
  for (statement in statements[nzchar(statements)]) DBI::dbExecute(connection, statement)
}

server_identity_bootstrap_store_v1 <- function(database_path, schema_path = NULL) {
  previous_umask <- Sys.umask("0077")
  on.exit(Sys.umask(previous_umask), add = TRUE)
  if (is.null(schema_path)) schema_path <- .server_identity_default_schema_path_v1()
  if (file.exists(database_path)) {
    connection <- .server_identity_connect_v1(database_path, write = FALSE)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    return(invisible(list(status = "existing", schema_version = 2800L)))
  }
  path <- .server_identity_store_path_v1(database_path, must_exist = FALSE)
  if (!file.exists(schema_path) || dir.exists(schema_path)) .server_identity_abort_v1("server_identity_store_invalid")
  lock <- paste0(path, ".bootstrap-lock")
  if (!dir.create(lock, mode = "0700", showWarnings = FALSE)) .server_identity_abort_v1("server_identity_store_invalid")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  if (file.exists(path)) .server_identity_abort_v1("server_identity_store_invalid")
  temporary <- file.path(dirname(path), paste0(".", basename(path), ".", .server_identity_random_ref_v1("tmp_")))
  on.exit(unlink(temporary, force = TRUE), add = TRUE)
  connection <- tryCatch(DBI::dbConnect(RSQLite::SQLite(), dbname = temporary), error = function(error) .server_identity_abort_v1("server_identity_store_invalid"))
  committed <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys=ON")
    DBI::dbExecute(connection, "PRAGMA journal_mode=DELETE")
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    .server_identity_execute_schema_v1(connection, schema_path)
    schema_fingerprint <- digest::digest(file = schema_path, algo = "sha256", serialize = FALSE)
    DBI::dbExecute(connection, "INSERT INTO identity_meta(singleton,schema_version,writer_role,schema_fingerprint) VALUES(1,2800,'identity_gateway',?)", params = list(schema_fingerprint))
    DBI::dbExecute(connection, "COMMIT")
    committed <- TRUE
  }, error = function(error) {
    if (!committed) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    try(DBI::dbDisconnect(connection), silent = TRUE)
    .server_identity_abort_v1("server_identity_store_invalid")
  })
  DBI::dbDisconnect(connection)
  if (!isTRUE(Sys.chmod(temporary, mode = "0600"))) .server_identity_abort_v1("server_identity_store_invalid")
  if (!file.link(temporary, path)) .server_identity_abort_v1("server_identity_store_invalid")
  unlink(temporary, force = TRUE)
  if (!isTRUE(Sys.chmod(path, mode = "0600"))) .server_identity_abort_v1("server_identity_store_invalid")
  validation <- .server_identity_connect_v1(path, write = FALSE)
  DBI::dbDisconnect(validation)
  invisible(list(status = "created", schema_version = 2800L))
}

new_server_identity_bootstrap_authorizer_v1 <- function(capability_path, expected_fingerprint) {
  if (is.character(capability_path) && length(capability_path) == 1L && !is.na(capability_path) && (file.exists(paste0(path.expand(capability_path), ".consumed")) || file.exists(paste0(path.expand(capability_path), ".consumed.used")))) .server_identity_abort_v1("server_bootstrap_consumed")
  if (!.server_identity_fingerprint_valid_v1(expected_fingerprint) || !is.character(capability_path) || length(capability_path) != 1L || !file.exists(capability_path) || dir.exists(capability_path) || .server_identity_path_component_symlink_v1(capability_path) || !.server_identity_owner_only_v1(capability_path)) .server_identity_abort_v1("server_bootstrap_capability_invalid")
  path <- normalizePath(capability_path, winslash = "/", mustWork = TRUE)
  consumed_receipt <- paste0(path, ".consumed")
  consuming <- paste0(path, ".consuming")
  if (file.exists(consumed_receipt) || file.exists(consuming)) .server_identity_abort_v1("server_bootstrap_consumed")
  if (!file.rename(path, consuming)) .server_identity_abort_v1("server_bootstrap_capability_invalid")
  on.exit(unlink(consuming, force = TRUE), add = TRUE)
  token <- tryCatch(readLines(consuming, warn = FALSE, encoding = "UTF-8"), error = function(error) character())
  valid <- length(token) == 1L && nchar(token, type = "bytes") >= 32L && nchar(token, type = "bytes") <= 256L && !grepl("[[:cntrl:]]", token) && identical(digest::digest(charToRaw(enc2utf8(token)), algo = "sha256", serialize = FALSE), expected_fingerprint)
  if (!valid) .server_identity_abort_v1("server_bootstrap_capability_invalid")
  temporary <- paste0(consumed_receipt, ".", .server_identity_random_ref_v1("tmp_"))
  writeLines(expected_fingerprint, temporary, useBytes = TRUE)
  on.exit(unlink(temporary, force = TRUE), add = TRUE)
  if (!isTRUE(Sys.chmod(temporary, mode = "0600")) || !file.link(temporary, consumed_receipt)) .server_identity_abort_v1("server_bootstrap_consumed")
  unlink(temporary, force = TRUE); unlink(consuming, force = TRUE)
  value <- new.env(parent = emptyenv())
  value$capability_fingerprint <- expected_fingerprint
  value$receipt_path <- consumed_receipt
  value$authorizer_fingerprint <- digest::digest(charToRaw(enc2utf8(paste("server_identity_bootstrap_authorizer_v1", expected_fingerprint, consumed_receipt, sep = "|"))), algo = "sha256", serialize = FALSE)
  value$consumed <- FALSE
  class(value) <- c("portelyra_server_identity_bootstrap_authorizer_v1", "environment")
  value
}

.server_identity_transaction_v1 <- function(connection, expression) {
  DBI::dbExecute(connection, "BEGIN IMMEDIATE")
  committed <- FALSE
  on.exit(if (!committed) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
  result <- force(expression)
  DBI::dbExecute(connection, "COMMIT")
  committed <- TRUE
  result
}

.server_identity_audit_v1 <- function(connection, event_code, tenant_id, user_id, data_space_id, actor_id, event_at_utc) {
  allowed <- c("identity_store_bootstrapped", "auth_provider_registered", "principal_provisioned", "principal_reactivated", "principal_deactivated", "principal_deletion_requested", "data_spaces_replaced", "session_opened", "session_logged_out", "sessions_rotated", "signed_job_consumed")
  if (!event_code %in% allowed || !.server_identity_id_valid_v1(tenant_id) || !.server_identity_id_valid_v1(user_id) || !.server_identity_id_valid_v1(actor_id, 80L) || (!is.null(data_space_id) && !.server_identity_id_valid_v1(data_space_id))) .server_identity_abort_v1("server_auth_audit_invalid")
  .server_identity_utc_seconds_v1(event_at_utc, "server_auth_audit_invalid")
  DBI::dbExecute(connection, "INSERT INTO auth_audit(audit_ref,event_code,tenant_id,user_id,data_space_id,actor_id,event_at_utc) VALUES(?,?,?,?,?,?,?)", params = list(.server_identity_random_ref_v1("aud_"), event_code, tenant_id, user_id, if (is.null(data_space_id)) NA_character_ else data_space_id, actor_id, event_at_utc))
}

.server_identity_principal_values_v1 <- function(identity, tenant_id, user_id, actor_id, role, data_space_ids, at_utc) {
  if (!verified_oidc_identity_valid_v1(identity, at_utc)) .server_identity_abort_v1("server_identity_assertion_invalid")
  values <- c(tenant_id, user_id, actor_id, role, data_space_ids)
  .server_identity_reject_sensitive_v1(values)
  valid <- .server_identity_id_valid_v1(tenant_id) && .server_identity_id_valid_v1(user_id) &&
    .server_identity_id_valid_v1(actor_id, 80L) && role %in% c("server_user", "server_admin", "server_support") &&
    is.character(data_space_ids) && length(data_space_ids) >= 1L && !anyNA(data_space_ids) &&
    all(vapply(data_space_ids, .server_identity_data_space_valid_v1, logical(1L), control_allowed = role != "server_user")) && length(unique(data_space_ids)) == length(data_space_ids)
  if (!valid) .server_identity_abort_v1("server_claims_invalid")
  if (role == "server_user" && any(data_space_ids == "control_plane")) .server_identity_abort_v1("server_data_space_denied")
  if (role != "server_user" && !identical(sort(data_space_ids), "control_plane")) .server_identity_abort_v1("server_data_space_denied")
  invisible(TRUE)
}

server_identity_bootstrap_admin_v1 <- function(database_path, authorizer, identity, tenant_id, user_id, actor_id, at_utc) {
  valid_authorizer <- inherits(authorizer, "portelyra_server_identity_bootstrap_authorizer_v1") && !isTRUE(authorizer$consumed) && .server_identity_fingerprint_valid_v1(authorizer$capability_fingerprint) && is.character(authorizer$receipt_path) && length(authorizer$receipt_path) == 1L && is.character(authorizer$authorizer_fingerprint) && length(authorizer$authorizer_fingerprint) == 1L && identical(authorizer$authorizer_fingerprint, digest::digest(charToRaw(enc2utf8(paste("server_identity_bootstrap_authorizer_v1", authorizer$capability_fingerprint, authorizer$receipt_path, sep = "|"))), algo = "sha256", serialize = FALSE))
  if (!valid_authorizer) .server_identity_abort_v1("server_bootstrap_consumed")
  used_receipt <- paste0(authorizer$receipt_path, ".used")
  if (!file.exists(authorizer$receipt_path) || file.exists(used_receipt) || .server_identity_path_component_symlink_v1(authorizer$receipt_path) || !.server_identity_owner_only_v1(authorizer$receipt_path) || !file.rename(authorizer$receipt_path, used_receipt)) .server_identity_abort_v1("server_bootstrap_consumed")
  authorizer$consumed <- TRUE
  receipt <- tryCatch(readLines(used_receipt, warn = FALSE, encoding = "UTF-8"), error = function(error) character())
  if (length(receipt) != 1L || !identical(receipt[[1L]], authorizer$capability_fingerprint)) .server_identity_abort_v1("server_bootstrap_capability_invalid")
  .server_identity_principal_values_v1(identity, tenant_id, user_id, actor_id, "server_admin", "control_plane", at_utc)
  connection <- .server_identity_connect_v1(database_path, write = TRUE)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tryCatch(.server_identity_transaction_v1(connection, {
    if (DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM auth_principal")$n[[1L]] != 0L) .server_identity_abort_v1("server_identity_conflict")
    DBI::dbExecute(connection, "INSERT INTO auth_provider_policy(issuer_fingerprint,audience_id,status,registered_at_utc) VALUES(?,?,'active',?)", params = list(identity$issuer_fingerprint, identity$audience_id, at_utc))
    DBI::dbExecute(connection, "INSERT INTO auth_principal(tenant_id,user_id,actor_id,issuer_fingerprint,subject_fingerprint,audience_id,role,status,principal_revision,session_revision,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active',1,1,?,?)", params = list(tenant_id, user_id, actor_id, identity$issuer_fingerprint, identity$subject_fingerprint, identity$audience_id, "server_admin", at_utc, at_utc))
    DBI::dbExecute(connection, "INSERT INTO auth_data_space_access(tenant_id,user_id,data_space_id,granted_at_utc) VALUES(?,?,?,?)", params = list(tenant_id, user_id, "control_plane", at_utc))
    .server_identity_audit_v1(connection, "identity_store_bootstrapped", tenant_id, user_id, "control_plane", actor_id, at_utc)
    invisible(TRUE)
  }), error = function(error) {
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    .server_identity_abort_v1("server_identity_conflict")
  })
}

.server_identity_session_claims_v1 <- function(principal, data_space_id, session_ref, issued_at_utc, expires_at_utc, identity_fingerprint) {
  body <- list(
    contract_version = "server_session_claims_v1",
    tenant_id = principal$tenant_id[[1L]], user_id = principal$user_id[[1L]],
    data_space_id = data_space_id, actor_id = principal$actor_id[[1L]], role = principal$role[[1L]],
    capabilities = server_identity_role_capabilities_v1(principal$role[[1L]]),
    session_ref = session_ref, session_revision = as.integer(principal$session_revision[[1L]]),
    principal_revision = as.integer(principal$principal_revision[[1L]]),
    issued_at_utc = issued_at_utc, expires_at_utc = expires_at_utc,
    issuer_fingerprint = principal$issuer_fingerprint[[1L]], audience_id = principal$audience_id[[1L]], identity_fingerprint = identity_fingerprint
  )
  body$claims_fingerprint <- .server_identity_fingerprint_v1(body)
  class(body) <- c("portelyra_server_session_claims_v1", "list")
  body
}

server_session_claims_valid_v1 <- function(claims) {
  if (!inherits(claims, "portelyra_server_session_claims_v1")) return(FALSE)
  isTRUE(tryCatch({
    required <- c("contract_version", "tenant_id", "user_id", "data_space_id", "actor_id", "role", "capabilities", "session_ref", "session_revision", "principal_revision", "issued_at_utc", "expires_at_utc", "issuer_fingerprint", "audience_id", "identity_fingerprint", "claims_fingerprint")
    if (!identical(names(claims), required) || claims$contract_version != "server_session_claims_v1") return(FALSE)
    if (!.server_identity_id_valid_v1(claims$tenant_id) || !.server_identity_id_valid_v1(claims$user_id) || !.server_identity_data_space_valid_v1(claims$data_space_id, control_allowed = claims$role %in% c("server_admin", "server_support")) || !.server_identity_id_valid_v1(claims$actor_id, 80L)) return(FALSE)
    if (!grepl("^ses_[a-f0-9]{32}$", claims$session_ref) || !.server_identity_fingerprint_valid_v1(claims$issuer_fingerprint) || !.server_identity_id_valid_v1(claims$audience_id) || !.server_identity_fingerprint_valid_v1(claims$identity_fingerprint)) return(FALSE)
    if (!identical(sort(claims$capabilities), server_identity_role_capabilities_v1(claims$role))) return(FALSE)
    fingerprint <- claims$claims_fingerprint
    unclassed <- unclass(claims); unclassed$claims_fingerprint <- NULL
    identical(fingerprint, .server_identity_fingerprint_v1(unclassed))
  }, error = function(error) FALSE))
}

server_identity_open_session_v1 <- function(database_path, identity, data_space_id, issued_at_utc, expires_at_utc) {
  if (!verified_oidc_identity_valid_v1(identity, issued_at_utc)) .server_identity_abort_v1("server_identity_assertion_invalid")
  issued <- .server_identity_utc_seconds_v1(issued_at_utc, "server_identity_assertion_invalid")
  expires <- .server_identity_utc_seconds_v1(expires_at_utc, "server_identity_assertion_invalid")
  identity_expires <- .server_identity_utc_seconds_v1(identity$expires_at_utc, "server_identity_assertion_invalid")
  if (expires <= issued || expires > identity_expires || expires - issued > 43200) .server_identity_abort_v1("server_identity_assertion_invalid")
  if (!.server_identity_data_space_valid_v1(data_space_id, control_allowed = TRUE)) .server_identity_abort_v1("server_data_space_denied")
  session_ref <- .server_identity_random_ref_v1("ses_")
  connection <- .server_identity_connect_v1(database_path, write = TRUE)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tryCatch(.server_identity_transaction_v1(connection, {
    provider <- DBI::dbGetQuery(connection, "SELECT 1 AS allowed FROM auth_provider_policy WHERE issuer_fingerprint=? AND audience_id=? AND status='active'", params = list(identity$issuer_fingerprint, identity$audience_id))
    if (nrow(provider) != 1L) .server_identity_abort_v1("server_auth_provider_required")
    principal <- DBI::dbGetQuery(connection, "SELECT * FROM auth_principal WHERE issuer_fingerprint=? AND subject_fingerprint=? AND audience_id=?", params = list(identity$issuer_fingerprint, identity$subject_fingerprint, identity$audience_id))
    if (nrow(principal) != 1L) .server_identity_abort_v1("server_identity_not_provisioned")
    if (principal$status[[1L]] != "active") .server_identity_abort_v1("server_principal_deactivated")
    access <- DBI::dbGetQuery(connection, "SELECT 1 AS allowed FROM auth_data_space_access WHERE tenant_id=? AND user_id=? AND data_space_id=? AND status='active'", params = list(principal$tenant_id[[1L]], principal$user_id[[1L]], data_space_id))
    if (nrow(access) != 1L) .server_identity_abort_v1("server_data_space_denied")
    claims <- .server_identity_session_claims_v1(principal, data_space_id, session_ref, issued_at_utc, expires_at_utc, identity$identity_fingerprint)
    DBI::dbExecute(connection, "INSERT INTO auth_session(session_ref,tenant_id,user_id,data_space_id,session_revision,principal_revision,claims_fingerprint,identity_fingerprint,status,issued_at_utc,expires_at_utc) VALUES(?,?,?,?,?,?,?,?, 'active',?,?)", params = list(session_ref, claims$tenant_id, claims$user_id, data_space_id, claims$session_revision, claims$principal_revision, claims$claims_fingerprint, identity$identity_fingerprint, issued_at_utc, expires_at_utc))
    .server_identity_audit_v1(connection, "session_opened", claims$tenant_id, claims$user_id, data_space_id, claims$actor_id, issued_at_utc)
    claims
  }), error = function(error) {
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    .server_identity_abort_v1("server_identity_conflict")
  })
}

.server_identity_authorize_connection_v1 <- function(connection, claims, required_capability = NULL, at_utc) {
  if (!server_session_claims_valid_v1(claims)) .server_identity_abort_v1("server_claims_invalid")
  now <- .server_identity_utc_seconds_v1(at_utc, "server_claims_invalid")
  principal <- DBI::dbGetQuery(connection, "SELECT * FROM auth_principal WHERE tenant_id=? AND user_id=?", params = list(claims$tenant_id, claims$user_id))
  if (nrow(principal) != 1L) .server_identity_abort_v1("server_context_mismatch")
  if (principal$status[[1L]] != "active") .server_identity_abort_v1("server_principal_deactivated")
  if (principal$actor_id[[1L]] != claims$actor_id || principal$role[[1L]] != claims$role || principal$issuer_fingerprint[[1L]] != claims$issuer_fingerprint || principal$audience_id[[1L]] != claims$audience_id) .server_identity_abort_v1("server_context_mismatch")
  if (principal$principal_revision[[1L]] != claims$principal_revision || principal$session_revision[[1L]] != claims$session_revision) .server_identity_abort_v1("server_session_stale")
  session <- DBI::dbGetQuery(connection, "SELECT * FROM auth_session WHERE session_ref=?", params = list(claims$session_ref))
  if (nrow(session) != 1L || session$tenant_id[[1L]] != claims$tenant_id || session$user_id[[1L]] != claims$user_id || session$data_space_id[[1L]] != claims$data_space_id || session$claims_fingerprint[[1L]] != claims$claims_fingerprint || session$identity_fingerprint[[1L]] != claims$identity_fingerprint) .server_identity_abort_v1("server_context_mismatch")
  if (session$status[[1L]] != "active") .server_identity_abort_v1("server_session_revoked")
  if (now < .server_identity_utc_seconds_v1(session$issued_at_utc[[1L]], "server_claims_invalid")) .server_identity_abort_v1("server_session_stale")
  if (now >= .server_identity_utc_seconds_v1(session$expires_at_utc[[1L]], "server_claims_invalid")) .server_identity_abort_v1("server_session_expired")
  if (!is.null(required_capability) && !required_capability %in% claims$capabilities) .server_identity_abort_v1("server_capability_denied")
  invisible(TRUE)
}

server_identity_authorize_request_v1 <- function(database_path, claims, required_capability = NULL, at_utc) {
  connection <- .server_identity_connect_v1(database_path, write = FALSE)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_authorize_connection_v1(connection, claims, required_capability, at_utc)
}

server_identity_register_auth_provider_v1 <- function(database_path, admin_claims, issuer_fingerprint, audience_id, at_utc) {
  if (!.server_identity_fingerprint_valid_v1(issuer_fingerprint) || !.server_identity_id_valid_v1(audience_id)) .server_identity_abort_v1("server_auth_provider_required")
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tryCatch(.server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, admin_claims, "manage_users", at_utc)
    DBI::dbExecute(connection, "INSERT INTO auth_provider_policy(issuer_fingerprint,audience_id,status,registered_at_utc) VALUES(?,?,'active',?)", params = list(issuer_fingerprint, audience_id, at_utc))
    .server_identity_audit_v1(connection, "auth_provider_registered", admin_claims$tenant_id, admin_claims$user_id, "control_plane", admin_claims$actor_id, at_utc)
    invisible(TRUE)
  }), error = function(error) {
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    .server_identity_abort_v1("server_identity_conflict")
  })
}

server_identity_provision_principal_v1 <- function(database_path, admin_claims, identity, tenant_id, user_id, actor_id, role, data_space_ids, at_utc) {
  .server_identity_principal_values_v1(identity, tenant_id, user_id, actor_id, role, data_space_ids, at_utc)
  connection <- .server_identity_connect_v1(database_path, write = TRUE)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tryCatch(.server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, admin_claims, "manage_users", at_utc)
    provider <- DBI::dbGetQuery(connection, "SELECT 1 AS allowed FROM auth_provider_policy WHERE issuer_fingerprint=? AND audience_id=? AND status='active'", params = list(identity$issuer_fingerprint, identity$audience_id))
    if (nrow(provider) != 1L) .server_identity_abort_v1("server_auth_provider_required")
    DBI::dbExecute(connection, "INSERT INTO auth_principal(tenant_id,user_id,actor_id,issuer_fingerprint,subject_fingerprint,audience_id,role,status,principal_revision,session_revision,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'active',1,1,?,?)", params = list(tenant_id, user_id, actor_id, identity$issuer_fingerprint, identity$subject_fingerprint, identity$audience_id, role, at_utc, at_utc))
    for (data_space_id in sort(data_space_ids)) DBI::dbExecute(connection, "INSERT INTO auth_data_space_access(tenant_id,user_id,data_space_id,granted_at_utc) VALUES(?,?,?,?)", params = list(tenant_id, user_id, data_space_id, at_utc))
    .server_identity_audit_v1(connection, "principal_provisioned", tenant_id, user_id, sort(data_space_ids)[[1L]], admin_claims$actor_id, at_utc)
    invisible(TRUE)
  }), error = function(error) {
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    .server_identity_abort_v1("server_identity_conflict")
  })
}

.server_identity_revoke_sessions_v1 <- function(connection, tenant_id, user_id, at_utc) {
  DBI::dbExecute(connection, "UPDATE auth_session SET status='revoked', revoked_at_utc=? WHERE tenant_id=? AND user_id=? AND status='active'", params = list(at_utc, tenant_id, user_id))
}

server_identity_rotate_sessions_v1 <- function(database_path, admin_claims, tenant_id, user_id, at_utc) {
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, admin_claims, "manage_users", at_utc)
    target <- DBI::dbGetQuery(connection, "SELECT actor_id FROM auth_principal WHERE tenant_id=? AND user_id=?", params = list(tenant_id, user_id))
    if (nrow(target) != 1L) .server_identity_abort_v1("server_identity_not_provisioned")
    DBI::dbExecute(connection, "UPDATE auth_principal SET session_revision=session_revision+1, updated_at_utc=? WHERE tenant_id=? AND user_id=?", params = list(at_utc, tenant_id, user_id))
    .server_identity_revoke_sessions_v1(connection, tenant_id, user_id, at_utc)
    .server_identity_audit_v1(connection, "sessions_rotated", tenant_id, user_id, NULL, admin_claims$actor_id, at_utc)
    invisible(TRUE)
  })
}

server_identity_set_principal_status_v1 <- function(database_path, admin_claims, tenant_id, user_id, status, at_utc) {
  if (!status %in% c("active", "deactivated")) .server_identity_abort_v1("server_lifecycle_conflict")
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, admin_claims, "manage_users", at_utc)
    target <- DBI::dbGetQuery(connection, "SELECT status FROM auth_principal WHERE tenant_id=? AND user_id=?", params = list(tenant_id, user_id))
    if (nrow(target) != 1L || target$status[[1L]] == "deletion_pending" || target$status[[1L]] == status || (tenant_id == admin_claims$tenant_id && user_id == admin_claims$user_id)) .server_identity_abort_v1("server_lifecycle_conflict")
    event <- if (status == "active") "principal_reactivated" else "principal_deactivated"
    DBI::dbExecute(connection, "UPDATE auth_principal SET status=?, principal_revision=principal_revision+1, session_revision=session_revision+1, updated_at_utc=? WHERE tenant_id=? AND user_id=?", params = list(status, at_utc, tenant_id, user_id))
    .server_identity_revoke_sessions_v1(connection, tenant_id, user_id, at_utc)
    .server_identity_audit_v1(connection, event, tenant_id, user_id, NULL, admin_claims$actor_id, at_utc)
    invisible(TRUE)
  })
}

server_identity_replace_data_spaces_v1 <- function(database_path, admin_claims, tenant_id, user_id, data_space_ids, at_utc) {
  if (!is.character(data_space_ids) || !length(data_space_ids) || anyNA(data_space_ids) || length(unique(data_space_ids)) != length(data_space_ids) || !all(vapply(data_space_ids, .server_identity_data_space_valid_v1, logical(1L), control_allowed = FALSE))) .server_identity_abort_v1("server_data_space_denied")
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, admin_claims, "manage_users", at_utc)
    target <- DBI::dbGetQuery(connection, "SELECT role FROM auth_principal WHERE tenant_id=? AND user_id=?", params = list(tenant_id, user_id))
    if (nrow(target) != 1L || target$role[[1L]] != "server_user" || any(data_space_ids == "control_plane")) .server_identity_abort_v1("server_data_space_denied")
    DBI::dbExecute(connection, "UPDATE auth_data_space_access SET status='revoked', revoked_at_utc=? WHERE tenant_id=? AND user_id=? AND status='active'", params = list(at_utc, tenant_id, user_id))
    for (data_space_id in sort(data_space_ids)) DBI::dbExecute(connection, "INSERT INTO auth_data_space_access(tenant_id,user_id,data_space_id,status,granted_at_utc,revoked_at_utc) VALUES(?,?,?,'active',?,NULL) ON CONFLICT(tenant_id,user_id,data_space_id) DO UPDATE SET status='active', granted_at_utc=excluded.granted_at_utc, revoked_at_utc=NULL", params = list(tenant_id, user_id, data_space_id, at_utc))
    DBI::dbExecute(connection, "UPDATE auth_principal SET session_revision=session_revision+1, updated_at_utc=? WHERE tenant_id=? AND user_id=?", params = list(at_utc, tenant_id, user_id))
    .server_identity_revoke_sessions_v1(connection, tenant_id, user_id, at_utc)
    .server_identity_audit_v1(connection, "data_spaces_replaced", tenant_id, user_id, sort(data_space_ids)[[1L]], admin_claims$actor_id, at_utc)
    invisible(TRUE)
  })
}

server_identity_request_deletion_v1 <- function(database_path, claims, requested_at_utc, retention_until_utc) {
  requested <- .server_identity_utc_seconds_v1(requested_at_utc, "server_lifecycle_conflict")
  retention <- .server_identity_utc_seconds_v1(retention_until_utc, "server_lifecycle_conflict")
  if (retention <= requested) .server_identity_abort_v1("server_lifecycle_conflict")
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, claims, "read_display", requested_at_utc)
    if (claims$role != "server_user") .server_identity_abort_v1("server_capability_denied")
    DBI::dbExecute(connection, "UPDATE auth_principal SET status='deletion_pending', principal_revision=principal_revision+1, session_revision=session_revision+1, updated_at_utc=?, deletion_requested_at_utc=?, retention_until_utc=? WHERE tenant_id=? AND user_id=?", params = list(requested_at_utc, requested_at_utc, retention_until_utc, claims$tenant_id, claims$user_id))
    .server_identity_revoke_sessions_v1(connection, claims$tenant_id, claims$user_id, requested_at_utc)
    .server_identity_audit_v1(connection, "principal_deletion_requested", claims$tenant_id, claims$user_id, claims$data_space_id, claims$actor_id, requested_at_utc)
    invisible(TRUE)
  })
}

server_identity_logout_v1 <- function(database_path, claims, at_utc) {
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_transaction_v1(connection, {
    .server_identity_authorize_connection_v1(connection, claims, NULL, at_utc)
    DBI::dbExecute(connection, "UPDATE auth_session SET status='revoked', revoked_at_utc=? WHERE session_ref=?", params = list(at_utc, claims$session_ref))
    .server_identity_audit_v1(connection, "session_logged_out", claims$tenant_id, claims$user_id, claims$data_space_id, claims$actor_id, at_utc)
    invisible(TRUE)
  })
}

server_identity_read_auth_audit_v1 <- function(database_path, claims, at_utc) {
  connection <- .server_identity_connect_v1(database_path, write = FALSE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  .server_identity_authorize_connection_v1(connection, claims, "read_auth_audit", at_utc)
  rows <- DBI::dbGetQuery(connection, "SELECT event_code,tenant_id,user_id,data_space_id,actor_id,event_at_utc FROM auth_audit ORDER BY event_at_utc,audit_ref")
  lapply(seq_len(nrow(rows)), function(index) as.list(rows[index, , drop = FALSE]))
}

.server_identity_operation_capability_v1 <- function(operation) {
  values <- c(read = "read_display", write = "csv_apply", export = "csv_export", plugin = "plugin_run", job = "submit_job", backup = "backup_export", restore_preflight = "restore_preflight", preferences = "manage_preferences")
  if (!is.character(operation) || length(operation) != 1L || !operation %in% names(values)) .server_identity_abort_v1("server_capability_denied")
  unname(values[[operation]])
}

server_identity_authorize_scope_v1 <- function(database_path, claims, operation, target_tenant_id, target_user_id, target_data_space_id, at_utc) {
  server_identity_authorize_request_v1(database_path, claims, .server_identity_operation_capability_v1(operation), at_utc)
  if (!identical(c(claims$tenant_id, claims$user_id, claims$data_space_id), c(target_tenant_id, target_user_id, target_data_space_id))) .server_identity_abort_v1("server_cross_user_access_blocked")
  invisible(TRUE)
}

server_identity_bind_untrusted_context_v1 <- function(database_path, claims, operation, untrusted_context = list(), at_utc) {
  server_identity_authorize_scope_v1(database_path, claims, operation, claims$tenant_id, claims$user_id, claims$data_space_id, at_utc)
  list(tenant_id = claims$tenant_id, user_id = claims$user_id, data_space_id = claims$data_space_id, untrusted_context_ignored = length(untrusted_context) > 0L)
}

.server_identity_path_has_symlink_v1 <- function(path, root) {
  relative <- substring(path, nchar(root) + 2L)
  segments <- if (nzchar(relative)) strsplit(relative, "/", fixed = TRUE)[[1L]] else character()
  current <- root
  for (segment in segments) {
    current <- file.path(current, segment)
    if ((file.exists(current) || dir.exists(current)) && (nzchar(Sys.readlink(current)) || !.server_identity_owner_only_v1(current))) return(TRUE)
  }
  FALSE
}

server_identity_runtime_context_v1 <- function(database_path, data_root, claims, runtime_role, at_utc) {
  operation <- if (identical(runtime_role, "desktop_owner")) "write" else if (runtime_role %in% c("viewer", "tax_viewer")) "read" else .server_identity_abort_v1("server_capability_denied")
  server_identity_authorize_scope_v1(database_path, claims, operation, claims$tenant_id, claims$user_id, claims$data_space_id, at_utc)
  if (!exists("runtime_context_valid", mode = "function") || !is.character(data_root) || length(data_root) != 1L || !dir.exists(data_root) || .server_identity_path_component_symlink_v1(data_root) || !.server_identity_owner_only_v1(data_root)) .server_identity_abort_v1("server_path_scope_invalid")
  root <- tryCatch(normalizePath(data_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(root)) .server_identity_abort_v1("server_path_scope_invalid")
  context <- structure(list(
    contract_version = 1L, runtime_mode = "server",
    tenant_id = claims$tenant_id, user_id = claims$user_id,
    data_space_id = claims$data_space_id, actor_id = claims$actor_id,
    role = runtime_role, trusted_source = "verified_server_session", data_root = root
  ), class = "spot_runtime_context_v1")
  if (!runtime_context_valid(context)) .server_identity_abort_v1("server_claims_invalid")
  context
}

server_identity_scoped_path_v1 <- function(database_path, data_root, claims, operation, area_id, at_utc) {
  allowed_areas <- c("canonical", "inbox", "exports", "plugins", "artifacts", "uploads", "backups", "preferences")
  if (!area_id %in% allowed_areas) .server_identity_abort_v1("server_path_scope_invalid")
  server_identity_authorize_scope_v1(database_path, claims, operation, claims$tenant_id, claims$user_id, claims$data_space_id, at_utc)
  if (!is.character(data_root) || length(data_root) != 1L || !dir.exists(data_root) || .server_identity_path_component_symlink_v1(data_root) || !.server_identity_owner_only_v1(data_root)) .server_identity_abort_v1("server_path_scope_invalid")
  root <- tryCatch(normalizePath(data_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(root)) .server_identity_abort_v1("server_path_scope_invalid")
  path <- file.path(root, claims$tenant_id, claims$user_id, claims$data_space_id, area_id)
  if (.server_identity_path_has_symlink_v1(path, root)) .server_identity_abort_v1("server_path_scope_invalid")
  path
}

.server_identity_job_payload_valid_v1 <- function(payload) {
  required <- c("contract_version", "tenant_id", "user_id", "data_space_id", "session_ref", "session_revision", "principal_revision", "claims_fingerprint", "job_capability", "input_fingerprint", "issued_at_utc", "expires_at_utc", "job_nonce")
  is.list(payload) && identical(names(payload), required) && payload$contract_version == "server_job_payload_v1" &&
    .server_identity_id_valid_v1(payload$tenant_id) && .server_identity_id_valid_v1(payload$user_id) && .server_identity_data_space_valid_v1(payload$data_space_id, control_allowed = FALSE) &&
    grepl("^ses_[a-f0-9]{32}$", payload$session_ref) &&
    is.integer(payload$session_revision) && payload$session_revision >= 1L && is.integer(payload$principal_revision) && payload$principal_revision >= 1L &&
    .server_identity_fingerprint_valid_v1(payload$claims_fingerprint) && payload$job_capability %in% server_identity_job_capabilities_v1() &&
    .server_identity_fingerprint_valid_v1(payload$input_fingerprint) && grepl("^jnonce_[a-f0-9]{32}$", payload$job_nonce)
}

server_identity_new_job_payload_v1 <- function(database_path, claims, job_capability, input_fingerprint, issued_at_utc, expires_at_utc) {
  server_identity_authorize_request_v1(database_path, claims, "submit_job", issued_at_utc)
  issued <- .server_identity_utc_seconds_v1(issued_at_utc, "server_job_binding_invalid")
  expires <- .server_identity_utc_seconds_v1(expires_at_utc, "server_job_binding_invalid")
  claims_expires <- .server_identity_utc_seconds_v1(claims$expires_at_utc, "server_job_binding_invalid")
  if (!job_capability %in% server_identity_job_capabilities_v1() || !.server_identity_fingerprint_valid_v1(input_fingerprint) || expires <= issued || expires - issued > 900 || expires > claims_expires) .server_identity_abort_v1("server_job_binding_invalid")
  job_nonce <- .server_identity_random_ref_v1("jnonce_")
  payload <- list(
    contract_version = "server_job_payload_v1", tenant_id = claims$tenant_id,
    user_id = claims$user_id, data_space_id = claims$data_space_id,
    session_ref = claims$session_ref, session_revision = as.integer(claims$session_revision),
    principal_revision = as.integer(claims$principal_revision), claims_fingerprint = claims$claims_fingerprint,
    job_capability = job_capability, input_fingerprint = input_fingerprint,
    issued_at_utc = issued_at_utc, expires_at_utc = expires_at_utc, job_nonce = job_nonce
  )
  if (!.server_identity_job_payload_valid_v1(payload)) .server_identity_abort_v1("server_job_binding_invalid")
  payload
}

server_job_signing_bytes_v1 <- function(payload) {
  if (!.server_identity_job_payload_valid_v1(payload)) .server_identity_abort_v1("server_job_binding_invalid")
  .server_identity_canonical_bytes_v1(payload)
}

new_server_signed_job_envelope_v1 <- function(payload, key_id, signature_base64) {
  if (!.server_identity_job_payload_valid_v1(payload) || !is.character(key_id) || length(key_id) != 1L || !grepl("^job_key_[a-z0-9_]{3,48}$", key_id) || !is.character(signature_base64) || length(signature_base64) != 1L || nchar(signature_base64) < 86L || !grepl("^[A-Za-z0-9+/]+={0,2}$", signature_base64)) .server_identity_abort_v1("server_job_binding_invalid")
  structure(list(contract_version = "server_signed_job_envelope_v1", key_id = key_id, signature_algorithm = "Ed25519", payload = payload, signature_base64 = signature_base64), class = c("portelyra_server_signed_job_envelope_v1", "list"))
}

server_identity_authorize_job_once_v1 <- function(database_path, envelope, trusted_public_keys, expected_tenant_id, expected_user_id, expected_data_space_id, expected_job_capability, expected_input_fingerprint, at_utc) {
  if (!inherits(envelope, "portelyra_server_signed_job_envelope_v1") || !identical(envelope$contract_version, "server_signed_job_envelope_v1") || !identical(envelope$signature_algorithm, "Ed25519") || !.server_identity_job_payload_valid_v1(envelope$payload)) .server_identity_abort_v1("server_job_binding_invalid")
  if (!is.list(trusted_public_keys) || is.null(names(trusted_public_keys)) || !envelope$key_id %in% names(trusted_public_keys)) .server_identity_abort_v1("server_job_signature_invalid")
  signature <- tryCatch(openssl::base64_decode(envelope$signature_base64), error = function(error) NULL)
  verified <- !is.null(signature) && isTRUE(tryCatch(openssl::ed25519_verify(server_job_signing_bytes_v1(envelope$payload), signature, trusted_public_keys[[envelope$key_id]]), error = function(error) FALSE))
  if (!verified) .server_identity_abort_v1("server_job_signature_invalid")
  payload <- envelope$payload
  if (!identical(c(payload$tenant_id, payload$user_id, payload$data_space_id), c(expected_tenant_id, expected_user_id, expected_data_space_id)) || payload$job_capability != expected_job_capability || payload$input_fingerprint != expected_input_fingerprint) .server_identity_abort_v1("server_cross_user_access_blocked")
  now <- .server_identity_utc_seconds_v1(at_utc, "server_job_expired")
  issued <- .server_identity_utc_seconds_v1(payload$issued_at_utc, "server_job_expired")
  expires <- .server_identity_utc_seconds_v1(payload$expires_at_utc, "server_job_expired")
  if (now < issued || now >= expires || expires - issued > 900) .server_identity_abort_v1("server_job_expired")
  connection <- .server_identity_connect_v1(database_path, write = TRUE); on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tryCatch(.server_identity_transaction_v1(connection, {
    principal <- DBI::dbGetQuery(connection, "SELECT * FROM auth_principal WHERE tenant_id=? AND user_id=?", params = list(payload$tenant_id, payload$user_id))
    if (nrow(principal) != 1L || principal$status[[1L]] != "active") .server_identity_abort_v1("server_principal_deactivated")
    if (principal$session_revision[[1L]] != payload$session_revision || principal$principal_revision[[1L]] != payload$principal_revision || !"submit_job" %in% server_identity_role_capabilities_v1(principal$role[[1L]])) .server_identity_abort_v1("server_session_stale")
    session <- DBI::dbGetQuery(connection, "SELECT * FROM auth_session WHERE session_ref=?", params = list(payload$session_ref))
    if (nrow(session) != 1L || session$status[[1L]] != "active" || session$claims_fingerprint[[1L]] != payload$claims_fingerprint || session$tenant_id[[1L]] != payload$tenant_id || session$user_id[[1L]] != payload$user_id || session$data_space_id[[1L]] != payload$data_space_id) .server_identity_abort_v1("server_session_revoked")
    if (issued < .server_identity_utc_seconds_v1(session$issued_at_utc[[1L]], "server_job_expired")) .server_identity_abort_v1("server_job_binding_invalid")
    if (now >= .server_identity_utc_seconds_v1(session$expires_at_utc[[1L]], "server_job_expired")) .server_identity_abort_v1("server_session_expired")
    existing <- DBI::dbGetQuery(connection, "SELECT 1 AS used FROM auth_job_nonce WHERE job_nonce=?", params = list(payload$job_nonce))
    if (nrow(existing)) .server_identity_abort_v1("server_job_replay")
    DBI::dbExecute(connection, "INSERT INTO auth_job_nonce(job_nonce,key_id,tenant_id,user_id,data_space_id,job_capability,input_fingerprint,consumed_at_utc) VALUES(?,?,?,?,?,?,?,?)", params = list(payload$job_nonce, envelope$key_id, payload$tenant_id, payload$user_id, payload$data_space_id, payload$job_capability, payload$input_fingerprint, at_utc))
    .server_identity_audit_v1(connection, "signed_job_consumed", payload$tenant_id, payload$user_id, payload$data_space_id, principal$actor_id[[1L]], at_utc)
    list(contract_version = "authorized_worker_job_v1", tenant_id = payload$tenant_id, user_id = payload$user_id, data_space_id = payload$data_space_id, role = "worker", capabilities = "execute_bound_job", capability = payload$job_capability, input_fingerprint = payload$input_fingerprint, execute_bound_job = TRUE)
  }), error = function(error) {
    if (inherits(error, "portelyra_server_identity_error_v1")) stop(error)
    if (grepl("UNIQUE constraint failed: auth_job_nonce", conditionMessage(error), fixed = TRUE)) .server_identity_abort_v1("server_job_replay")
    .server_identity_abort_v1("server_identity_store_invalid")
  })
}

server_identity_dispatch_signed_job_v1 <- function(database_path, envelope, trusted_public_keys, expected_tenant_id, expected_user_id, expected_data_space_id, expected_job_capability, data_root, job_path, at_utc, execute_callback) {
  if (!.server_identity_id_valid_v1(expected_tenant_id) || !.server_identity_id_valid_v1(expected_user_id) || !.server_identity_data_space_valid_v1(expected_data_space_id, control_allowed = FALSE) || !is.character(data_root) || length(data_root) != 1L || !dir.exists(data_root) || .server_identity_path_component_symlink_v1(data_root) || !.server_identity_owner_only_v1(data_root) || !is.character(job_path) || length(job_path) != 1L || !file.exists(job_path) || dir.exists(job_path) || .server_identity_path_component_symlink_v1(job_path) || !.server_identity_owner_only_v1(job_path) || !is.function(execute_callback)) .server_identity_abort_v1("server_job_binding_invalid")
  normalized_root <- normalizePath(data_root, winslash = "/", mustWork = TRUE)
  normalized_job <- normalizePath(job_path, winslash = "/", mustWork = TRUE)
  expected_job_root <- file.path(normalized_root, expected_tenant_id, expected_user_id, expected_data_space_id, "jobs")
  if (!startsWith(normalized_job, paste0(expected_job_root, "/")) || .server_identity_path_has_symlink_v1(normalized_job, normalized_root)) .server_identity_abort_v1("server_job_binding_invalid")
  input_fingerprint <- digest::digest(file = normalized_job, algo = "sha256", serialize = FALSE)
  if (!identical(input_fingerprint, envelope$payload$input_fingerprint)) .server_identity_abort_v1("server_job_binding_invalid")
  authorized_job <- server_identity_authorize_job_once_v1(
    database_path, envelope, trusted_public_keys,
    expected_tenant_id, expected_user_id, expected_data_space_id,
    expected_job_capability, input_fingerprint, at_utc
  )
  execute_callback(authorized_job, normalized_job)
}
