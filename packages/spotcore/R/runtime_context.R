runtime_error_codes <- function() {
  c(
    "runtime_context_invalid",
    "runtime_role_invalid",
    "runtime_data_root_invalid",
    "runtime_symlink_rejected",
    "runtime_path_invalid",
    "runtime_boundary_failed"
  )
}

.runtime_condition <- function(code) {
  if (!identical(length(code), 1L) || !code %in% runtime_error_codes()) {
    stop("unregistered_runtime_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_runtime_error", "error", "condition")
  )
}

.runtime_abort <- function(code) {
  stop(.runtime_condition(code))
}

.runtime_boundary_eval <- function(expression) {
  result <- tryCatch(
    expression,
    spot_runtime_error = function(error) error,
    error = function(error) .runtime_condition("runtime_boundary_failed")
  )
  if (inherits(result, "spot_runtime_error")) stop(result)
  result
}

.runtime_symlink <- function(path) {
  target <- suppressWarnings(Sys.readlink(path))
  length(target) == 1L && !is.na(target) && nzchar(target)
}

.runtime_id_valid <- function(value, lower_only = FALSE, maximum = 64L) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || nchar(value, type = "bytes") < 3L || nchar(value, type = "bytes") > maximum) {
    return(FALSE)
  }
  pattern <- if (lower_only) "^[a-z0-9_]+$" else "^[A-Za-z0-9_-]+$"
  grepl(pattern, value, perl = TRUE)
}

.runtime_role_actor <- function(role, runtime_mode = "desktop_demo") {
  actors <- if (runtime_mode %in% c("desktop_private", "desktop_product")) c(
    desktop_owner = "desktop_owner"
  ) else c(
    desktop_owner = "desktop_demo_user",
    viewer = "cockpit_demo_reader",
    tax_viewer = "tax_demo_reader",
    market_worker = "market_demo_worker",
    portfolio_worker = "portfolio_demo_worker",
    tax_worker = "tax_demo_worker"
  )
  if (!is.character(role) || length(role) != 1L || is.na(role) || !role %in% names(actors)) {
    .runtime_abort("runtime_role_invalid")
  }
  unname(actors[[role]])
}

.runtime_context_new <- function(
  data_root, tenant_id, user_id, data_space_id, role,
  runtime_mode = "desktop_demo", trusted_source = "desktop_adapter"
) {
  if (!is.character(data_root) || length(data_root) != 1L || is.na(data_root) || !nzchar(data_root)) {
    .runtime_abort("runtime_data_root_invalid")
  }
  expanded <- path.expand(data_root)
  if (!dir.exists(expanded)) {
    .runtime_abort("runtime_data_root_invalid")
  }
  if (.runtime_symlink(expanded)) {
    .runtime_abort("runtime_symlink_rejected")
  }
  normalized <- tryCatch(normalizePath(expanded, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || !dir.exists(normalized) || .runtime_symlink(normalized)) {
    .runtime_abort("runtime_data_root_invalid")
  }
  if (!.runtime_id_valid(tenant_id) || !.runtime_id_valid(user_id)) {
    .runtime_abort("runtime_context_invalid")
  }
  if (!.runtime_id_valid(data_space_id, lower_only = TRUE) || !startsWith(data_space_id, "sbx_") || nchar(data_space_id, type = "bytes") < 8L) {
    .runtime_abort("runtime_context_invalid")
  }
  valid_mode_source <-
    (identical(runtime_mode, "desktop_demo") && identical(trusted_source, "desktop_adapter")) ||
    (identical(runtime_mode, "desktop_private") && identical(trusted_source, "locally_confirmed_private_context")) ||
    (identical(runtime_mode, "desktop_product") && identical(trusted_source, "owner_only_desktop_registry"))
  if (!valid_mode_source) .runtime_abort("runtime_context_invalid")
  actor_id <- .runtime_role_actor(role, runtime_mode)
  context <- structure(
    list(
      contract_version = 1L,
      runtime_mode = runtime_mode,
      tenant_id = tenant_id,
      user_id = user_id,
      data_space_id = data_space_id,
      actor_id = actor_id,
      role = role,
      trusted_source = trusted_source,
      data_root = normalized
    ),
    class = "spot_runtime_context_v1"
  )
  if (!runtime_context_valid(context)) {
    .runtime_abort("runtime_context_invalid")
  }
  context
}

new_desktop_demo_runtime <- function(
  data_root,
  data_space_id = "sbx_demo01",
  role = "desktop_owner"
) {
  .runtime_boundary_eval(
    .runtime_context_new(
      data_root = data_root,
      tenant_id = "local",
      user_id = "demo_user",
      data_space_id = data_space_id,
      role = role
    )
  )
}

new_private_desktop_runtime_v1 <- function(
  data_root, tenant_id, user_id, data_space_id, role = "desktop_owner"
) {
  .runtime_boundary_eval(
    .runtime_context_new(
      data_root = data_root,
      tenant_id = tenant_id,
      user_id = user_id,
      data_space_id = data_space_id,
      role = role,
      runtime_mode = "desktop_private",
      trusted_source = "locally_confirmed_private_context"
    )
  )
}

new_desktop_product_runtime_v1 <- function(data_root, tenant_id, user_id, data_space_id) {
  .runtime_boundary_eval(
    .runtime_context_new(
      data_root = data_root,
      tenant_id = tenant_id,
      user_id = user_id,
      data_space_id = data_space_id,
      role = "desktop_owner",
      runtime_mode = "desktop_product",
      trusted_source = "owner_only_desktop_registry"
    )
  )
}

runtime_context_valid <- function(context) {
  required <- c(
    "contract_version", "runtime_mode", "tenant_id", "user_id", "data_space_id",
    "actor_id", "role", "trusted_source", "data_root"
  )
  inherits(context, "spot_runtime_context_v1") &&
    identical(names(context), required) &&
    identical(context$contract_version, 1L) &&
    (
      (identical(context$runtime_mode, "desktop_demo") && identical(context$trusted_source, "desktop_adapter")) ||
      (identical(context$runtime_mode, "desktop_private") && identical(context$trusted_source, "locally_confirmed_private_context")) ||
      (identical(context$runtime_mode, "desktop_product") && identical(context$trusted_source, "owner_only_desktop_registry")) ||
      (identical(context$runtime_mode, "server") && identical(context$trusted_source, "verified_server_session"))
    ) &&
    .runtime_id_valid(context$tenant_id) &&
    .runtime_id_valid(context$user_id) &&
    .runtime_id_valid(context$data_space_id, lower_only = TRUE) &&
    startsWith(context$data_space_id, "sbx_") &&
    nchar(context$data_space_id, type = "bytes") >= 8L &&
    (
      (identical(context$runtime_mode, "server") && .runtime_id_valid(context$actor_id, maximum = 80L) && context$role %in% c("desktop_owner", "viewer", "tax_viewer")) ||
      (!identical(context$runtime_mode, "server") && isTRUE(tryCatch(
        identical(context$actor_id, .runtime_role_actor(context$role, context$runtime_mode)),
        error = function(error) FALSE
      )))
    ) &&
    is.character(context$data_root) &&
    length(context$data_root) == 1L &&
    dir.exists(context$data_root) &&
    !.runtime_symlink(context$data_root) &&
    identical(
      tryCatch(normalizePath(context$data_root, winslash = "/", mustWork = TRUE), error = function(error) NA_character_),
      context$data_root
    )
}

runtime_context_as <- function(context, role) {
  .runtime_boundary_eval({
    if (!runtime_context_valid(context)) {
      .runtime_abort("runtime_context_invalid")
    }
    if (identical(context$runtime_mode, "server")) .runtime_abort("runtime_role_invalid")
    .runtime_context_new(
      data_root = context$data_root,
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      role = role,
      runtime_mode = context$runtime_mode,
      trusted_source = context$trusted_source
    )
  })
}

.runtime_safe_child <- function(context, segments) {
  if (!runtime_context_valid(context)) {
    .runtime_abort("runtime_context_invalid")
  }
  if (!is.character(segments) || anyNA(segments) || any(!grepl("^[a-z0-9_]+$", segments, perl = TRUE))) {
    .runtime_abort("runtime_path_invalid")
  }
  current <- context$data_root
  for (segment in segments) {
    current <- file.path(current, segment)
    if (file.exists(current) || dir.exists(current)) {
      if (.runtime_symlink(current)) {
        .runtime_abort("runtime_symlink_rejected")
      }
      normalized <- tryCatch(normalizePath(current, winslash = "/", mustWork = TRUE), error = function(error) NULL)
      if (is.null(normalized) || !startsWith(paste0(normalized, "/"), paste0(context$data_root, "/"))) {
        .runtime_abort("runtime_path_invalid")
      }
    }
  }
  current
}

runtime_data_space_path <- function(context) {
  .runtime_boundary_eval(
    .runtime_safe_child(context, c(context$tenant_id, context$user_id, context$data_space_id))
  )
}

runtime_canonical_path <- function(context) {
  file.path(runtime_data_space_path(context), "canonical.sqlite")
}

runtime_artifact_area_path <- function(context, area_id) {
  allowed <- c("portfolio_snapshot", "tax_report")
  if (!is.character(area_id) || length(area_id) != 1L || is.na(area_id) || !area_id %in% allowed) {
    .runtime_abort("runtime_path_invalid")
  }
  .runtime_safe_child(
    context,
    c(context$tenant_id, context$user_id, context$data_space_id, "artifacts", area_id)
  )
}

runtime_context_fingerprint <- function(context) {
  .runtime_boundary_eval({
    if (!runtime_context_valid(context)) {
      .runtime_abort("runtime_context_invalid")
    }
    parts <- lapply(
      c(
        "runtime-context-v1", context$runtime_mode, context$tenant_id,
        context$user_id, context$data_space_id, context$actor_id, context$role
      ),
      function(value) charToRaw(enc2utf8(value))
    )
    material <- raw()
    for (index in seq_along(parts)) {
      if (index > 1L) material <- c(material, as.raw(0L))
      material <- c(material, parts[[index]])
    }
    digest::digest(material, algo = "sha256", serialize = FALSE)
  })
}
