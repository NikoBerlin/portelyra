data_provider_search_service_error_codes_v1 <- function() c(
  "data_provider_search_service_invalid", "data_provider_search_preview_required",
  "data_provider_search_confirmation_required", "data_provider_search_confirmation_consumed",
  "data_provider_search_boundary_failed"
)

.data_provider_search_abort_v1 <- function(code) {
  if (!code %in% data_provider_search_service_error_codes_v1() && !grepl("^desktop_provider_search_[a-z_]+$", code)) code <- "data_provider_search_boundary_failed"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_provider_search_error_v1", "error", "condition")))
}

new_data_provider_search_service_v1 <- function(project_root, context) {
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) ||
      !isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner")) {
    .data_provider_search_abort_v1("data_provider_search_service_invalid")
  }
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_provider_search.py")
  data_space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(data_space) || nzchar(Sys.readlink(cli)) || nzchar(Sys.readlink(data_space))) {
    .data_provider_search_abort_v1("data_provider_search_service_invalid")
  }
  previews <- new.env(hash = TRUE, parent = emptyenv())
  candidates <- new.env(hash = TRUE, parent = emptyenv())
  context_payload <- list(
    tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = "market_worker", role = "market_worker"
  )
  run_cli <- function(command, payload) {
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))
    output <- tryCatch(
      suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), shQuote(command)), stdout = TRUE, stderr = TRUE, input = encoded)),
      error = function(error) structure(character(), status = 1L)
    )
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed)) .data_provider_search_abort_v1("data_provider_search_boundary_failed")
    if (as.integer(status) != 0L || isTRUE(parsed$status %in% c("blocked", "failed"))) {
      .data_provider_search_abort_v1(if (is.null(parsed$code)) "data_provider_search_boundary_failed" else parsed$code)
    }
    parsed
  }
  preview <- function(provider_id, query, search_mode, created_at_utc) {
    result <- run_cli("preview", list(
      context = context_payload, provider_id = provider_id, query = query,
      search_mode = search_mode, created_at_utc = created_at_utc
    ))
    trusted <- result$trusted_preview; public <- result$public_preview
    if (!is.list(trusted) || !is.list(public) || !identical(public$status, "pending_confirmation")) {
      .data_provider_search_abort_v1("data_provider_search_boundary_failed")
    }
    preview_ref <- paste0("srchp_", substr(digest::digest(
      as.character(jsonlite::toJSON(trusted, auto_unbox = TRUE, null = "null", digits = NA)),
      algo = "sha256", serialize = FALSE
    ), 1L, 32L))
    public$preview_ref <- preview_ref
    assign(preview_ref, list(consumed = FALSE, public = public, trusted = trusted), envir = previews)
    public
  }
  execute <- function(public_preview, confirmed) {
    if (!isTRUE(confirmed)) .data_provider_search_abort_v1("data_provider_search_confirmation_required")
    if (!is.list(public_preview) || !is.character(public_preview$preview_ref) || length(public_preview$preview_ref) != 1L ||
        !exists(public_preview$preview_ref, envir = previews, inherits = FALSE)) {
      .data_provider_search_abort_v1("data_provider_search_preview_required")
    }
    stored <- get(public_preview$preview_ref, envir = previews, inherits = FALSE)
    if (isTRUE(stored$consumed)) .data_provider_search_abort_v1("data_provider_search_confirmation_consumed")
    if (!identical(stored$public, public_preview)) .data_provider_search_abort_v1("data_provider_search_preview_required")
    stored$consumed <- TRUE; assign(public_preview$preview_ref, stored, envir = previews)
    python_public <- stored$public; python_public$preview_ref <- NULL
    result <- run_cli("apply", list(
      context = context_payload, data_space_path = data_space,
      trusted_preview = stored$trusted, public_preview = python_public, confirmed = TRUE
    ))$result
    if (!is.list(result) || !identical(result$status, "completed") || !is.list(result$candidates)) {
      .data_provider_search_abort_v1("data_provider_search_boundary_failed")
    }
    rows <- lapply(seq_along(result$candidates), function(index) {
      row <- result$candidates[[index]]; handle <- paste0("candidate_", public_preview$preview_ref, "_", index)
      assign(handle, row, envir = candidates)
      list(
        ref = handle, symbol = row$symbol, display_name = row$display_name,
        exchange = row$exchange, quote_type = row$quote_type,
        quote_currency = row$quote_currency, isin = row$isin
      )
    })
    list(
      contract_version = 1L, status = "completed", provider_id = result$provider_id,
      candidate_count = as.integer(length(rows)), candidates = rows,
      provider_access = TRUE, network_access = TRUE, canonical_write = FALSE,
      market_history_write = FALSE, automatic_retry = FALSE,
      context_exposed = FALSE, paths_exposed = FALSE, fingerprints_exposed = FALSE
    )
  }
  resolve_candidate <- function(handle) {
    if (!is.character(handle) || length(handle) != 1L || !exists(handle, envir = candidates, inherits = FALSE)) {
      .data_provider_search_abort_v1("data_provider_search_preview_required")
    }
    get(handle, envir = candidates, inherits = FALSE)
  }
  structure(list(
    contract_version = "data_provider_search_service_v1", preview = preview,
    execute = execute, resolve_candidate = resolve_candidate,
    browser_paths_exposed = FALSE, browser_context_exposed = FALSE,
    automatic_provider_access = FALSE, automatic_retry = FALSE
  ), class = c("spot_data_provider_search_service_v1", "list"))
}
