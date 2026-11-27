# Private CLI payloads remain in this server-side closure, never in browser models.
data_market_fx_batch_abort_v1 <- function(code = "data_market_fx_batch_boundary_failed") {
  allowed <- c("data_market_fx_batch_boundary_failed", "data_market_fx_batch_service_invalid",
    "data_market_fx_batch_confirmation_required", "data_market_fx_batch_preview_required",
    paste0("desktop_market_fx_batch_", c("input_invalid", "context_invalid", "time_invalid",
      "confirmation_invalid", "store_invalid", "executor_invalid", "provider_call_failed",
      "recovery_required", "busy", "result_invalid", "selection_invalid", "selection_blocked", "binding_invalid", "binding_confirmation_required")),
    paste0("desktop_market_fx_batch_calendar_", c("input_invalid", "stale", "saved_profile_required", "staged_not_published")),
    paste0("desktop_market_fx_batch_publication_", c("input_invalid", "confirmation_required", "stale", "store_invalid", "recovery_required")))
  if (!is.character(code) || length(code) != 1L || !code %in% allowed) code <- "data_market_fx_batch_boundary_failed"
  stop(structure(list(message = code, code = code, call = NULL),
    class = c("spot_data_market_fx_batch_error_v1", "error", "condition")))
}

new_data_market_fx_batch_service_v1 <- function(project_root, context, cli_runner = NULL) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(e) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) data_market_fx_batch_abort_v1("data_market_fx_batch_service_invalid")
  python <- Sys.which("python3")
  cli <- file.path(normalizePath(project_root, mustWork = TRUE), "scripts", "desktop_market_fx_batch.py")
  space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(space) || nzchar(Sys.readlink(space)) || nzchar(Sys.readlink(cli)))
    data_market_fx_batch_abort_v1("data_market_fx_batch_service_invalid")
  base <- list(context = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id), data_space_path = space)
  trusted <- public <- progress <- grant <- review_slot <- NULL
  run <- function(command, fields = list()) {
    payload <- c(base, fields)
    if (!is.null(cli_runner)) {
      result <- tryCatch(cli_runner(command, payload), error = function(e) NULL)
    } else {
      old_umask <- Sys.umask("0077")
      stderr_path <- tempfile("market-fx-batch-stderr-")
      on.exit({Sys.umask(old_umask); unlink(stderr_path)}, add = TRUE)
      output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
        stdout = TRUE, stderr = stderr_path,
        input = as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA)))),
        error = function(e) character())
      result <- tryCatch(if (length(output) == 1L) jsonlite::fromJSON(output, simplifyVector = FALSE) else NULL,
        error = function(e) NULL)
      stderr <- if (file.exists(stderr_path)) readLines(stderr_path, warn = FALSE) else character()
      exit_status <- attr(output, "status")
      if (length(stderr) || (!is.null(exit_status) && exit_status != 0L &&
          is.list(result) && identical(result$status, "completed"))) result <- NULL
    }
    if (!is.list(result) || !identical(result$status, "completed"))
      data_market_fx_batch_abort_v1(if (is.list(result)) result$code else NULL)
    result
  }
  accept <- function(result) {
    if (!is.list(result$trusted_batch) || !is.list(result$public_review) || !is.list(result$progress) ||
        !identical(result$progress$contract_version, "desktop_market_fx_batch_progress_v1") ||
        !identical(result$progress$silent_drop_count, 0L)) data_market_fx_batch_abort_v1()
    trusted <<- result$trusted_batch; public <<- result$public_review; progress <<- result$progress
    grant <<- NULL; review_slot <<- NULL
    progress
  }
  prepare <- function(batch, server_targets, now) {
    trusted <<- public <<- progress <<- grant <<- review_slot <<- NULL
    result <- run("prepare", list(batch = batch, targets = server_targets, created_at_utc = now))
    if (!is.list(result$trusted_batch) || !is.list(result$public_review)) data_market_fx_batch_abort_v1()
    trusted <<- result$trusted_batch; public <<- result$public_review
    public
  }
  prepare_calendar <- function(preview_ref, now) {
    trusted <<- public <<- progress <<- grant <<- review_slot <<- NULL
    result <- run("prepare-calendar", list(preview_ref=preview_ref, created_at_utc=now))
    if (!is.list(result$public_review) || (!is.list(result$trusted_batch) &&
        !(is.null(result$trusted_batch) && identical(result$public_review$item_count,0L) &&
          identical(result$public_review$confirmation_required,FALSE)))) data_market_fx_batch_abort_v1()
    trusted <<- result$trusted_batch; public <<- result$public_review
    public
  }
  confirm_fetch <- function(preview, confirmed, issued_at, expires_at, ordinals = NULL) {
    grant <<- NULL
    if (!isTRUE(confirmed) || is.null(trusted) || !identical(preview, public) ||
        !is.numeric(ordinals) || !length(ordinals) || anyNA(ordinals) || anyDuplicated(ordinals) ||
        any(!is.finite(ordinals) | ordinals < 1 | ordinals > length(public$items) | ordinals != trunc(ordinals)))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    ordinals <- sort(as.integer(ordinals))
    if (!is.null(progress) && !all(ordinals %in% vapply(Filter(function(row) identical(row$status,"pending"),
        progress$items), `[[`, integer(1L), "ordinal")))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    result <- run("confirm-selected", list(trusted_batch = trusted, public_review = public, confirmed = TRUE,
      ordinals = as.list(ordinals), issued_at_utc = issued_at, expires_at_utc = expires_at))
    if (!is.list(result$confirmation) || !identical(result$confirmation$confirmation_version,3L) ||
        !identical(result$confirmation$selected_ordinals, as.list(ordinals))) data_market_fx_batch_abort_v1()
    grant <<- result$confirmation
    invisible(TRUE)
  }
  execute <- function(now, resume = FALSE, ordinals = NULL) {
    confirmation <- grant; grant <<- NULL; review_slot <<- NULL
    if (is.null(confirmation) || (isTRUE(resume) && is.null(progress)) ||
        !is.numeric(ordinals) || anyNA(ordinals) || anyDuplicated(ordinals) ||
        any(!is.finite(ordinals) | ordinals < 1 | ordinals > length(public$items) | ordinals != trunc(ordinals)) ||
        !identical(as.list(sort(as.integer(ordinals))), confirmation$selected_ordinals))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    fields <- if (isTRUE(resume)) list(execution_ref = progress$execution_ref) else list(trusted_batch = trusted)
    accept(run(if (isTRUE(resume)) "resume" else "stage", c(fields, list(confirmation = confirmation, executed_at_utc = now))))
  }
  read_execution <- function(execution_ref) {
    grant <<- NULL; review_slot <<- NULL
    accept(run("read", list(execution_ref = execution_ref)))
  }
  review <- function(ordinals) {
    review_slot <<- NULL
    if (is.null(progress)) data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    if (!is.numeric(ordinals) || !length(ordinals) || anyNA(ordinals) ||
        any(!is.finite(ordinals) | ordinals < 1 | ordinals > .Machine$integer.max | ordinals != trunc(ordinals)))
      data_market_fx_batch_abort_v1("data_market_fx_batch_preview_required")
    result <- run("review", list(execution_ref = progress$execution_ref, ordinals = as.list(as.integer(ordinals))))
    if (!is.list(result$preview)) data_market_fx_batch_abort_v1()
    review_slot <<- result$preview
    review_slot
  }
  publish <- function(preview, confirmed, now, expires_at) {
    if (!isTRUE(confirmed) || is.null(review_slot) || !identical(preview, review_slot))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    review_slot <<- NULL; grant <<- NULL
    confirmation <- run("confirm-publication", list(preview = preview, confirmed = TRUE,
      issued_at_utc = now, expires_at_utc = expires_at))$confirmation
    accept(run("publish", list(execution_ref = progress$execution_ref, preview = preview,
      confirmation = confirmation, completed_at_utc = now)))
  }
  recover <- function(ordinal, domain, confirmed) {
    if (!isTRUE(confirmed) || is.null(progress) || !is.character(domain) || length(domain) != 1L ||
        is.na(domain) || !domain %in% c("staging", "publication") ||
        !is.numeric(ordinal) || length(ordinal) != 1L || is.na(ordinal) || !is.finite(ordinal) ||
        ordinal < 1 || ordinal > .Machine$integer.max || ordinal != trunc(ordinal))
      data_market_fx_batch_abort_v1("data_market_fx_batch_confirmation_required")
    grant <<- NULL; review_slot <<- NULL
    accept(run(paste0("recover-", domain), list(execution_ref = progress$execution_ref,
      ordinal = as.integer(ordinal), confirmed = TRUE)))
  }
  list_executions <- function() run("list")$executions
  # An unchecked fetch box revokes only fetch authority, never an unrelated review.
  invalidate_fetch <- function() { grant <<- NULL; invisible(TRUE) }
  invalidate <- function() { invalidate_fetch(); review_slot <<- NULL; invisible(TRUE) }
  structure(list(invalidate = invalidate, invalidate_fetch = invalidate_fetch, prepare = prepare, prepare_calendar = prepare_calendar, confirm_fetch = confirm_fetch, execute = execute, read = read_execution,
    review = review, publish = publish, recover = recover, list_executions = list_executions,
    fetch_preview = function() public, progress = function() progress,
    automatic_provider_access = FALSE, provider_refetch_on_publish = FALSE, startup_write = FALSE),
    class = c("spot_data_market_fx_batch_service_v1", "list"))
}
