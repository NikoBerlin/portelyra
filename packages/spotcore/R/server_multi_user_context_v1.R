server_multi_user_error_codes_v1 <- function() {
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

.server_claim_value_valid_v1 <- function(value, maximum = 64L) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 3L && nchar(value, type = "bytes") <= maximum &&
    grepl("^[A-Za-z0-9_-]+$", value, perl = TRUE)
}

new_verified_server_claims_v1 <- function(
  tenant_id, user_id, data_space_id, actor_id, role,
  capabilities = character()
) {
  capabilities <- sort(unique(as.character(capabilities)))
  allowed_capabilities <- list(
    desktop_owner = c("csv_apply", "csv_export", "csv_inbox", "manage_preferences", "plugin_run", "read_display"),
    server_user = c("backup_export", "csv_apply", "csv_export", "csv_inbox", "manage_preferences", "plugin_run", "read_display", "restore_preflight", "submit_job"),
    server_admin = c("manage_users", "read_auth_audit"),
    worker = c("execute_bound_job", "plugin_run")
  )
  valid <- .server_claim_value_valid_v1(tenant_id) &&
    .server_claim_value_valid_v1(user_id) &&
    .server_claim_value_valid_v1(data_space_id) &&
    .server_claim_value_valid_v1(actor_id, 80L) &&
    role %in% names(allowed_capabilities) &&
    all(grepl("^[a-z][a-z0-9_]*$", capabilities)) &&
    all(capabilities %in% allowed_capabilities[[role]])
  if (!isTRUE(valid)) stop("server_claims_invalid", call. = FALSE)
  body <- list(
    contract_version = "server_multi_user_claims_v1",
    tenant_id = tenant_id, user_id = user_id, data_space_id = data_space_id,
    actor_id = actor_id, role = role, capabilities = capabilities
  )
  body$claims_fingerprint <- digest::digest(
    charToRaw(enc2utf8(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))),
    algo = "sha256", serialize = FALSE
  )
  class(body) <- c("portelyra_verified_server_claims_v1", "list")
  body
}

verified_server_claims_valid_v1 <- function(claims) {
  if (!inherits(claims, "portelyra_verified_server_claims_v1")) return(FALSE)
  isTRUE(tryCatch({
    rebuilt <- new_verified_server_claims_v1(
      claims$tenant_id, claims$user_id, claims$data_space_id,
      claims$actor_id, claims$role, claims$capabilities
    )
    identical(rebuilt$claims_fingerprint, claims$claims_fingerprint)
  }, error = function(error) FALSE))
}

server_claims_require_capability_v1 <- function(claims, capability) {
  if (!verified_server_claims_valid_v1(claims)) stop("server_claims_invalid", call. = FALSE)
  capability <- as.character(capability)[1]
  if (!capability %in% claims$capabilities) stop("server_capability_denied", call. = FALSE)
  invisible(TRUE)
}

server_claims_context_fingerprint_v1 <- function(claims) {
  if (!verified_server_claims_valid_v1(claims)) stop("server_claims_invalid", call. = FALSE)
  digest::digest(
    charToRaw(enc2utf8(paste(
      "server_multi_user_context_v1", claims$tenant_id,
      claims$user_id, claims$data_space_id, sep = "|"
    ))),
    algo = "sha256", serialize = FALSE
  )
}

server_context_data_space_path_v1 <- function(data_root, claims) {
  if (!verified_server_claims_valid_v1(claims)) stop("server_claims_invalid", call. = FALSE)
  root <- normalizePath(data_root, winslash = "/", mustWork = TRUE)
  if (file.info(root)$isdir %in% FALSE || Sys.readlink(root) != "") stop("server_path_scope_invalid", call. = FALSE)
  segments <- c(claims$tenant_id, claims$user_id, claims$data_space_id)
  if (any(segments %in% c(".", "..")) || any(grepl("[/\\\\]", segments))) {
    stop("server_path_scope_invalid", call. = FALSE)
  }
  file.path(root, segments)
}

server_context_assert_same_v1 <- function(claims, tenant_id, user_id, data_space_id) {
  if (!verified_server_claims_valid_v1(claims)) stop("server_claims_invalid", call. = FALSE)
  if (!identical(c(claims$tenant_id, claims$user_id, claims$data_space_id), c(tenant_id, user_id, data_space_id))) {
    stop("server_context_mismatch", call. = FALSE)
  }
  invisible(TRUE)
}

new_server_principal_state_v1 <- function(
  tenant_id, user_id, status = "active", session_revision = 1L
) {
  if (!.server_claim_value_valid_v1(tenant_id) ||
      !.server_claim_value_valid_v1(user_id) ||
      !status %in% c("active", "deactivated") ||
      !is.numeric(session_revision) || length(session_revision) != 1L ||
      is.na(session_revision) || session_revision < 1L ||
      session_revision != as.integer(session_revision)) {
    stop("server_claims_invalid", call. = FALSE)
  }
  structure(list(
    contract_version = "server_principal_state_v1",
    tenant_id = tenant_id,
    user_id = user_id,
    status = status,
    session_revision = as.integer(session_revision)
  ), class = c("portelyra_server_principal_state_v1", "list"))
}

server_authorize_request_v1 <- function(
  claims, principal_state, request_session_revision, required_capability
) {
  if (!verified_server_claims_valid_v1(claims) ||
      !inherits(principal_state, "portelyra_server_principal_state_v1") ||
      !identical(claims$tenant_id, principal_state$tenant_id) ||
      !identical(claims$user_id, principal_state$user_id)) {
    stop("server_context_mismatch", call. = FALSE)
  }
  if (!identical(principal_state$status, "active")) {
    stop("server_principal_deactivated", call. = FALSE)
  }
  if (!identical(as.integer(request_session_revision), principal_state$session_revision)) {
    stop("server_session_stale", call. = FALSE)
  }
  server_claims_require_capability_v1(claims, required_capability)
  invisible(TRUE)
}

new_server_job_binding_v1 <- function(claims, capability, input_fingerprint) {
  server_claims_require_capability_v1(claims, capability)
  if (!is.character(input_fingerprint) || length(input_fingerprint) != 1L ||
      !grepl("^[a-f0-9]{64}$", input_fingerprint)) {
    stop("server_job_binding_invalid", call. = FALSE)
  }
  body <- list(
    contract_version = "server_job_binding_v1",
    claims_fingerprint = claims$claims_fingerprint,
    context_fingerprint = server_claims_context_fingerprint_v1(claims),
    capability = capability,
    input_fingerprint = input_fingerprint
  )
  body$binding_fingerprint <- digest::digest(
    charToRaw(enc2utf8(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))),
    algo = "sha256", serialize = FALSE
  )
  class(body) <- c("portelyra_server_job_binding_v1", "list")
  body
}

server_job_binding_valid_v1 <- function(binding, claims, capability, input_fingerprint) {
  if (!inherits(binding, "portelyra_server_job_binding_v1")) return(FALSE)
  isTRUE(tryCatch({
    rebuilt <- new_server_job_binding_v1(claims, capability, input_fingerprint)
    identical(rebuilt, binding)
  }, error = function(error) FALSE))
}
