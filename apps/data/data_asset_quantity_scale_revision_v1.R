data_asset_quantity_scale_error_codes_v1 <- function() c(
  "data_asset_quantity_scale_state_invalid",
  "data_asset_quantity_scale_context_invalid",
  "data_asset_quantity_scale_input_invalid",
  "data_asset_quantity_scale_preview_required",
  "data_asset_quantity_scale_confirmation_required",
  "data_asset_quantity_scale_confirmation_consumed",
  "data_asset_quantity_scale_confirmation_expired",
  "data_asset_quantity_scale_resume_invalid",
  "data_asset_quantity_scale_adapter_failed"
)

.data_asset_quantity_scale_abort <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% data_asset_quantity_scale_error_codes_v1()) {
    stop("unregistered_data_asset_quantity_scale_error", call. = FALSE)
  }
  stop(structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_asset_quantity_scale_error", "error", "condition")
  ))
}

.data_asset_quantity_scale_context <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner")) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_context_invalid")
  }
  context
}

.data_asset_quantity_scale_time <- function(value) {
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

new_data_asset_quantity_scale_product_adapter_v1 <- function(project_root, context) {
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  data_space <- runtime_data_space_path(context)
  canonical <- runtime_canonical_path(context)
  trusted <- function(bound) {
    .data_asset_quantity_scale_context(bound)
    if (!identical(runtime_context_fingerprint(bound), runtime_context_fingerprint(context))) {
      .data_asset_quantity_scale_abort("data_asset_quantity_scale_context_invalid")
    }
    list(
      tenant_id = context$tenant_id, user_id = context$user_id,
      data_space_id = context$data_space_id, actor_id = context$actor_id,
      role = "desktop_owner"
    )
  }
  run <- function(command, payload) {
    tryCatch(
      .per_asset_review_adapter_run(project_root, command, payload),
      error = function(error) {
        if (inherits(error, "spot_data_asset_quantity_scale_error")) stop(error)
        .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
      }
    )
  }
  list(
    preview = function(bound, asset_id, quantity_values, at) run(
      "quantity-scale-preview",
      list(
        context = trusted(bound), canonical_path = canonical,
        data_space_path = data_space, asset_id = asset_id,
        quantity_values = quantity_values, previewed_at_utc = at
      )
    )$preview,
    confirmation = function(bound, preview, challenge, issued, expires) run(
      "quantity-scale-confirmation",
      list(
        context = trusted(bound), trusted_preview = preview,
        challenge_ref = challenge, issued_at_utc = issued,
        confirmed_at_utc = issued, expires_at_utc = expires
      )
    )$confirmation,
    begin = function(bound, preview, confirmation, at) run(
      "quantity-scale-begin",
      list(
        context = trusted(bound), canonical_path = canonical,
        data_space_path = data_space, trusted_preview = preview,
        confirmation = confirmation, committed_at_utc = at
      )
    )$result,
    finalize = function(bound, plan_fingerprint) run(
      "quantity-scale-finalize",
      list(
        context = trusted(bound), canonical_path = canonical,
        data_space_path = data_space, plan_fingerprint = plan_fingerprint
      )
    )$result,
    pending = function(bound) run(
      "quantity-scale-pending",
      list(
        context = trusted(bound), canonical_path = canonical,
        data_space_path = data_space
      )
    )$pending
  )
}

new_data_asset_quantity_scale_center_v1 <- function(adapter) {
  required <- c("preview", "confirmation", "begin", "finalize", "pending")
  if (!is.list(adapter) || !identical(names(adapter), required) ||
      !all(vapply(adapter, is.function, logical(1L)))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_state_invalid")
  }
  center <- new.env(hash = FALSE, parent = emptyenv())
  center$adapter <- adapter
  center$previews <- new.env(hash = TRUE, parent = emptyenv())
  center$pending <- new.env(hash = TRUE, parent = emptyenv())
  center$sequence <- 0L
  class(center) <- "spot_data_asset_quantity_scale_center_v1"
  center
}

.data_asset_quantity_scale_check <- function(center) {
  if (!inherits(center, "spot_data_asset_quantity_scale_center_v1") ||
      !is.environment(center) || !is.environment(center$previews) ||
      !is.environment(center$pending) || !is.integer(center$sequence)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_state_invalid")
  }
  invisible(TRUE)
}

.data_asset_quantity_scale_values <- function(form) {
  required <- c("quantity_decimal", "eligible_quantity_decimal", "asset_fee_quantity_decimal")
  if (!is.list(form) || !all(required %in% names(form))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_input_invalid")
  }
  values <- form[required]
  if (!all(vapply(values, function(value) {
    is.null(value) || is.character(value) && length(value) == 1L && !is.na(value) &&
      nchar(value, type = "bytes") <= 100L && !grepl("[[:cntrl:]]", value)
  }, logical(1L)))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_input_invalid")
  }
  values
}

.data_asset_quantity_scale_public_valid <- function(value) {
  is.list(value) && value$status %in% c("within_current_scale", "ready_for_confirmation") &&
    is.character(value$asset_label) && length(value$asset_label) == 1L &&
    is.numeric(value$current_quantity_scale) && is.numeric(value$proposed_quantity_scale) &&
    value$current_quantity_scale >= 0L && value$proposed_quantity_scale <= 24L &&
    identical(value$rounding_performed, FALSE) &&
    identical(value$provider_access, FALSE) && identical(value$network_access, FALSE) &&
    identical(value$path_exposed, FALSE) && identical(value$internal_id_exposed, FALSE)
}

data_asset_quantity_scale_prepare_for_activity_v1 <- function(
  center, activity_editor, context, activity_form, now_utc
) {
  .data_asset_quantity_scale_check(center)
  .data_asset_quantity_scale_context(context)
  if (!is.character(now_utc) || length(now_utc) != 1L ||
      is.na(.data_asset_quantity_scale_time(now_utc)) ||
      !is.list(activity_form) || !is.character(activity_form$asset_ref) ||
      length(activity_form$asset_ref) != 1L) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_input_invalid")
  }
  selection <- .data_asset_activity_selection(activity_editor, context)
  asset <- .data_asset_activity_resolve(selection, "assets", activity_form$asset_ref)
  value <- center$adapter$preview(
    context, asset$asset_id, .data_asset_quantity_scale_values(activity_form), now_utc
  )
  if (!is.list(value) || !.data_asset_quantity_scale_public_valid(value$public_preview) ||
      (identical(value$public_preview$status, "within_current_scale") && !is.null(value$trusted_preview)) ||
      (identical(value$public_preview$status, "ready_for_confirmation") && !is.list(value$trusted_preview))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  if (identical(value$public_preview$status, "within_current_scale")) {
    return(value$public_preview)
  }
  center$sequence <- center$sequence + 1L
  preview_ref <- sprintf("quantity_scale_preview_%04d", center$sequence)
  expires <- format(
    .data_asset_quantity_scale_time(now_utc) + 600,
    "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"
  )
  assign(
    preview_ref,
    list(
      trusted = value$trusted_preview,
      context_fingerprint = runtime_context_fingerprint(context),
      expires_at_utc = expires, confirmed = FALSE, consumed = FALSE
    ),
    envir = center$previews
  )
  c(value$public_preview, list(preview_ref = preview_ref, expires_at_utc = expires))
}

data_asset_quantity_scale_confirm_v1 <- function(center, context, preview_ref) {
  .data_asset_quantity_scale_check(center)
  .data_asset_quantity_scale_context(context)
  if (!is.character(preview_ref) || length(preview_ref) != 1L ||
      !exists(preview_ref, envir = center$previews, inherits = FALSE)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_preview_required")
  }
  entry <- get(preview_ref, envir = center$previews, inherits = FALSE)
  if (isTRUE(entry$consumed)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_confirmation_consumed")
  }
  if (!identical(entry$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_confirmation_expired")
  }
  entry$confirmed <- TRUE
  assign(preview_ref, entry, envir = center$previews)
  list(status = "confirmed", one_use = TRUE, preview_ref = preview_ref)
}

.data_asset_quantity_scale_catalog_write <- function(context, command) {
  if (!is.list(command) || !identical(
    sort(names(command)),
    sort(c("command_token", "asset_id", "expected_revision", "quantity_scale", "committed_at_utc"))
  ) || !is.character(command$command_token) || length(command$command_token) != 1L ||
      !grepl("^tok_scale_[a-f0-9]{40}$", command$command_token) ||
      !is.character(command$asset_id) || length(command$asset_id) != 1L ||
      !startsWith(command$asset_id, "ast_") ||
      !is.numeric(command$expected_revision) || length(command$expected_revision) != 1L ||
      is.na(command$expected_revision) || command$expected_revision < 1 ||
      command$expected_revision != floor(command$expected_revision) ||
      !is.numeric(command$quantity_scale) || length(command$quantity_scale) != 1L ||
      is.na(command$quantity_scale) || command$quantity_scale < 0 || command$quantity_scale > 24 ||
      command$quantity_scale != floor(command$quantity_scale) ||
      !is.character(command$committed_at_utc) || length(command$committed_at_utc) != 1L ||
      is.na(.data_asset_quantity_scale_time(command$committed_at_utc))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  result <- tryCatch(
    catalog_rescale_asset_v1(
      context, command$command_token, command$asset_id,
      as.integer(command$expected_revision), as.integer(command$quantity_scale),
      command$committed_at_utc
    ),
    error = function(error) .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  )
  if (!is.list(result) || !result$status %in% c("committed", "already_committed") ||
      !identical(result$command_type, "catalog_rescale_asset_v1")) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  result
}

.data_asset_quantity_scale_result <- function(result) {
  required <- c(
    "status", "current_quantity_scale", "proposed_quantity_scale", "catalog_revision",
    "generation_updated", "affected_fifo_world_count", "catalog_write",
    "activity_fact_write", "rounding_performed", "fifo_rebuild_required",
    "provider_access", "network_access", "path_exposed", "internal_id_exposed"
  )
  if (!is.list(result) || !identical(sort(names(result)), sort(required)) ||
      !result$status %in% c("committed", "already_committed", "recovered_committed") ||
      !identical(result$activity_fact_write, FALSE) ||
      !identical(result$rounding_performed, FALSE) ||
      !identical(result$provider_access, FALSE) || !identical(result$network_access, FALSE) ||
      !identical(result$path_exposed, FALSE) || !identical(result$internal_id_exposed, FALSE)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  list(
    quantity_scale_result_version = 1L,
    status = result$status,
    current_quantity_scale = as.integer(result$current_quantity_scale),
    proposed_quantity_scale = as.integer(result$proposed_quantity_scale),
    catalog_revision = as.integer(result$catalog_revision),
    generation_updated = isTRUE(result$generation_updated),
    affected_fifo_world_count = as.integer(result$affected_fifo_world_count),
    catalog_write = isTRUE(result$catalog_write),
    activity_fact_write = FALSE,
    rounding_performed = FALSE,
    fifo_rebuild_required = isTRUE(result$fifo_rebuild_required),
    provider_access = FALSE, network_access = FALSE,
    path_exposed = FALSE, internal_id_exposed = FALSE
  )
}

data_asset_quantity_scale_execute_v1 <- function(center, context, preview_ref, now_utc) {
  .data_asset_quantity_scale_check(center)
  .data_asset_quantity_scale_context(context)
  if (!is.character(preview_ref) || length(preview_ref) != 1L ||
      !exists(preview_ref, envir = center$previews, inherits = FALSE)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_preview_required")
  }
  entry <- get(preview_ref, envir = center$previews, inherits = FALSE)
  if (isTRUE(entry$consumed)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_confirmation_consumed")
  }
  now <- .data_asset_quantity_scale_time(now_utc)
  if (!isTRUE(entry$confirmed)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_confirmation_required")
  }
  if (!is.character(now_utc) || length(now_utc) != 1L || is.na(now) ||
      now > .data_asset_quantity_scale_time(entry$expires_at_utc) ||
      !identical(entry$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_confirmation_expired")
  }
  entry$consumed <- TRUE
  entry$confirmed <- FALSE
  assign(preview_ref, entry, envir = center$previews)
  challenge <- paste0(
    "aqs_",
    substr(digest::digest(
      charToRaw(enc2utf8(paste(entry$trusted$plan_fingerprint, now_utc, sep = "|"))),
      algo = "sha256", serialize = FALSE
    ), 1L, 32L)
  )
  confirmation <- center$adapter$confirmation(
    context, entry$trusted, challenge, now_utc, entry$expires_at_utc
  )
  begun <- center$adapter$begin(context, entry$trusted, confirmation, now_utc)
  if (!is.list(begun) || !identical(begun$status, "pending_catalog_write") ||
      !is.list(begun$catalog_command) ||
      !identical(begun$plan_fingerprint, entry$trusted$plan_fingerprint)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  invisible(.data_asset_quantity_scale_catalog_write(context, begun$catalog_command))
  .data_asset_quantity_scale_result(
    center$adapter$finalize(context, begun$plan_fingerprint)
  )
}

data_asset_quantity_scale_pending_v1 <- function(center, context) {
  .data_asset_quantity_scale_check(center)
  .data_asset_quantity_scale_context(context)
  value <- center$adapter$pending(context)
  if (!is.list(value) || !identical(value$status, "available") ||
      !is.list(value$candidates) || !identical(value$path_exposed, FALSE) ||
      !identical(value$internal_id_exposed, FALSE)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
  }
  rm(list = ls(center$pending, all.names = TRUE), envir = center$pending)
  public <- lapply(value$candidates, function(item) {
    required <- c(
      "resume_ref", "status", "current_quantity_scale", "proposed_quantity_scale",
      "affected_fifo_world_count", "plan_fingerprint", "catalog_command"
    )
    if (!is.list(item) || !identical(sort(names(item)), sort(required)) ||
        !item$status %in% c("pending_catalog_write", "pending_generation_finalize")) {
      .data_asset_quantity_scale_abort("data_asset_quantity_scale_adapter_failed")
    }
    assign(item$resume_ref, item, envir = center$pending)
    list(
      resume_ref = item$resume_ref, status = item$status,
      current_quantity_scale = as.integer(item$current_quantity_scale),
      proposed_quantity_scale = as.integer(item$proposed_quantity_scale),
      affected_fifo_world_count = as.integer(item$affected_fifo_world_count)
    )
  })
  list(
    status = "available", candidates = public,
    path_exposed = FALSE, internal_id_exposed = FALSE
  )
}

data_asset_quantity_scale_resume_v1 <- function(center, context, resume_ref) {
  .data_asset_quantity_scale_check(center)
  .data_asset_quantity_scale_context(context)
  if (!is.character(resume_ref) || length(resume_ref) != 1L ||
      !exists(resume_ref, envir = center$pending, inherits = FALSE)) {
    .data_asset_quantity_scale_abort("data_asset_quantity_scale_resume_invalid")
  }
  item <- get(resume_ref, envir = center$pending, inherits = FALSE)
  if (identical(item$status, "pending_catalog_write")) {
    invisible(.data_asset_quantity_scale_catalog_write(context, item$catalog_command))
  }
  result <- .data_asset_quantity_scale_result(
    center$adapter$finalize(context, item$plan_fingerprint)
  )
  rm(list = resume_ref, envir = center$pending)
  result
}
