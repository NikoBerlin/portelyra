data_market_history_review_service_error_codes_v1 <- function() c(
  "data_market_history_review_service_invalid",
  "data_market_history_review_preview_required",
  "data_market_history_review_confirmation_required",
  "data_market_history_review_confirmation_consumed",
  "data_market_history_review_boundary_failed"
)

.data_market_history_review_service_abort_v1 <- function(code) {
  allowed <- c(
    data_market_history_review_service_error_codes_v1(),
    if (exists(".data_market_history_review_recovery_codes_v1", mode = "function"))
      .data_market_history_review_recovery_codes_v1() else character(),
    # Kursanbieter je Datenraum (rc.383): Sperre des Skripts mit genauem Grund.
    "desktop_market_history_review_provider_inactive", "desktop_market_history_review_provider_state_invalid"
  )
  if (!is.character(code) || length(code) != 1L || !(code %in% allowed)) {
    code <- "data_market_history_review_boundary_failed"
  }
  stop(structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_market_history_review_error_v1", "error", "condition")
  ))
}

.data_market_history_review_private_payload_v1 <- function(value) {
  private_keys <- c(
    "listing_ref", "stage_ref", "request_ref", "source_ref", "asset_ref",
    "candidate_fingerprint", "staged_candidate_fingerprint", "receipt_fingerprint",
    "preview_fingerprint", "mapping_fingerprint", "promotion_binding_fingerprint",
    "context", "context_fingerprint", "tenant_id", "user_id", "data_space_id",
    "data_space_path", "store_path"
  )
  if (is.character(value)) {
    return(any(grepl("^(lsr|mhs|mrq|msr|asf|ast|map)_[A-Za-z0-9_-]+$", value)))
  }
  if (!is.list(value)) return(FALSE)
  if (length(intersect(names(value), private_keys))) return(TRUE)
  any(vapply(value, .data_market_history_review_private_payload_v1, logical(1L)))
}

new_data_market_history_review_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  validator_names <- c(
    "data_market_history_fetch_preview_validate_v1",
    "data_market_history_review_validate_v1",
    "data_market_history_publication_result_validate_v1",
    "data_market_history_rejection_result_validate_v1",
    "data_market_history_recovery_result_validate_v1"
  )
  lookup_environment <- environment()
  validators_available <- all(vapply(
    validator_names,
    function(name) is.function(get0(name, envir = lookup_environment, inherits = TRUE)),
    logical(1L)
  ))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) ||
      !valid_context || !validators_available ||
      !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) {
    .data_market_history_review_service_abort_v1("data_market_history_review_service_invalid")
  }
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3")
  cli <- file.path(project_root, "scripts", "desktop_market_history_review.py")
  data_space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(data_space) ||
      nzchar(Sys.readlink(cli)) || nzchar(Sys.readlink(data_space))) {
    .data_market_history_review_service_abort_v1("data_market_history_review_service_invalid")
  }
  preview_slot <- new.env(parent = emptyenv())
  preview_slot$value <- NULL
  operation_state <- new.env(parent = emptyenv())
  operation_state$value <- "idle"
  reviews <- new.env(hash = TRUE, parent = emptyenv())
  context_payload <- list(
    tenant_id = context$tenant_id, user_id = context$user_id,
    data_space_id = context$data_space_id, actor_id = "market_worker", role = "market_worker"
  )
  validate_browser <- function(validator, value) {
    validated <- tryCatch(validator(value), error = function(error) NULL)
    if (is.null(validated)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    validated
  }
  run_cli_process <- function(command, payload) {
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))
    stderr_path <- tempfile("market-history-review-stderr-")
    old_umask <- Sys.umask("0077")
    on.exit({
      Sys.umask(old_umask)
      unlink(stderr_path, force = TRUE)
    }, add = TRUE)
    output <- tryCatch(
      suppressWarnings(system2(
        python, c("-B", "-E", "-s", shQuote(cli), shQuote(command)),
        stdout = TRUE, stderr = stderr_path, input = encoded
      )),
      error = function(error) structure(character(), status = 1L)
    )
    status <- attr(output, "status")
    if (is.null(status)) status <- 0L
    stderr_output <- tryCatch(
      if (file.exists(stderr_path)) readLines(stderr_path, warn = FALSE) else character(),
      error = function(error) "boundary_error"
    )
    parsed <- tryCatch(
      if (length(output) == 1L)
        jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE) else NULL,
      error = function(error) NULL
    )
    if (length(stderr_output) || length(output) != 1L || is.null(parsed) || !is.list(parsed) ||
        as.integer(status) != 0L ||
        isTRUE(parsed$status %in% c("blocked", "failed"))) {
      code <- if (is.list(parsed) && is.character(parsed$code) && length(parsed$code) == 1L)
        parsed$code else "data_market_history_review_boundary_failed"
      .data_market_history_review_service_abort_v1(code)
    }
    parsed
  }
  run_cli <- function(command, payload) {
    if (is.null(cli_runner)) return(run_cli_process(command, payload))
    parsed <- tryCatch(cli_runner(command, payload), error = function(error) NULL)
    if (is.null(parsed) || !is.list(parsed) || isTRUE(parsed$status %in% c("blocked", "failed"))) {
      code <- if (is.list(parsed) && is.character(parsed$code) && length(parsed$code) == 1L)
        parsed$code else "data_market_history_review_boundary_failed"
      .data_market_history_review_service_abort_v1(code)
    }
    parsed
  }
  preview <- function(listing_ref, mapping, promotion_binding, scope_start_date, scope_end_date, mode, created_at_utc) {
    if (operation_state$value %in% c("fetch_attempt_consumed", "staged_review", "publish_attempt_consumed", "recovery_required")) {
      .data_market_history_review_service_abort_v1("desktop_market_history_review_recovery_required")
    }
    result <- run_cli("preview", list(
      context = context_payload, data_space_path = data_space,
      listing_ref = listing_ref, mapping = mapping, promotion_binding = promotion_binding,
      scope_start_date = scope_start_date, scope_end_date = scope_end_date,
      mode = mode, created_at_utc = created_at_utc
    ))
    trusted <- result$trusted_preview
    public <- result$public_preview
    if (!is.list(trusted)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    public <- validate_browser(data_market_history_fetch_preview_validate_v1, public)
    preview_slot$value <- list(consumed = FALSE, public = public, trusted = trusted)
    operation_state$value <- "previewed"
    public
  }
  stage <- function(public_preview, confirmed) {
    if (!isTRUE(confirmed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_required")
    }
    stored <- preview_slot$value
    if (is.null(stored) || !is.list(public_preview)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_preview_required")
    }
    if (isTRUE(stored$consumed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_consumed")
    }
    if (!identical(stored$public, public_preview)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_preview_required")
    }
    stored$consumed <- TRUE
    preview_slot$value <- stored
    operation_state$value <- "fetch_attempt_consumed"
    result <- run_cli("stage", list(
      context = context_payload, data_space_path = data_space,
      trusted_preview = stored$trusted, public_preview = stored$public, confirmed = TRUE
    ))
    public_review <- validate_browser(
      data_market_history_review_validate_v1, result$public_review
    )
    if (!is.character(result$stage_ref) || length(result$stage_ref) != 1L ||
        !grepl("^mhs_[a-f0-9]{32}$", result$stage_ref)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    assign(
      public_review$review_ref,
      list(stage_ref = result$stage_ref, public = public_review, consumed = FALSE),
      envir = reviews
    )
    operation_state$value <- "staged_review"
    public_review
  }
  resolve_review <- function(public_review) {
    if (!is.list(public_review) || !is.character(public_review$review_ref) ||
        length(public_review$review_ref) != 1L ||
        !exists(public_review$review_ref, envir = reviews, inherits = FALSE)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_preview_required")
    }
    stored <- get(public_review$review_ref, envir = reviews, inherits = FALSE)
    if (!identical(stored$public, public_review)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_preview_required")
    }
    stored
  }
  publish <- function(public_review, confirmed, completed_at_utc) {
    if (!isTRUE(confirmed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_required")
    }
    stored <- resolve_review(public_review)
    if (isTRUE(stored$consumed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_consumed")
    }
    stored$consumed <- TRUE
    assign(public_review$review_ref, stored, envir = reviews)
    operation_state$value <- "publish_attempt_consumed"
    result <- run_cli("publish", list(
      context = context_payload, data_space_path = data_space,
      stage_ref = stored$stage_ref, public_review = stored$public,
      confirmed = TRUE, completed_at_utc = completed_at_utc
    ))$public_result
    result <- validate_browser(
      data_market_history_publication_result_validate_v1, result
    )
    operation_state$value <- "published"
    result
  }
  reject <- function(public_review, confirmed, rejected_at_utc) {
    if (!isTRUE(confirmed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_required")
    }
    stored <- resolve_review(public_review)
    if (isTRUE(stored$consumed)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_confirmation_consumed")
    }
    stored$consumed <- TRUE
    assign(public_review$review_ref, stored, envir = reviews)
    operation_state$value <- "publish_attempt_consumed"
    result <- run_cli("reject", list(
      context = context_payload, data_space_path = data_space,
      stage_ref = stored$stage_ref, public_review = stored$public,
      confirmed = TRUE, rejected_at_utc = rejected_at_utc
    ))$public_result
    result <- validate_browser(
      data_market_history_rejection_result_validate_v1, result
    )
    operation_state$value <- "rejected"
    result
  }
  # Ein begonnener, nie angekommener Schreibvorgang laesst sich weder erneut
  # veroeffentlichen noch verwerfen - das Asset bliebe dauerhaft gesperrt. Das
  # Verwerfen loest genau diesen Fall auf, und nur ihn: Die Quittung im
  # Kursspeicher muss fehlen (#283, 25.09.2026).
  discard <- function(listing_ref, discarded_at_utc) {
    parsed <- run_cli("discard", list(
      context = context_payload, data_space_path = data_space, listing_ref = listing_ref,
      confirmed = TRUE, discarded_at_utc = discarded_at_utc
    ))
    # Nichts zu verwerfen ist kein Fehler: Der Zustand ist dann schon in Ordnung.
    if (identical(parsed$status, "absent")) {
      operation_state$value <- "idle"
      return(NULL)
    }
    result <- parsed$public_result
    if (!is.list(result) || !identical(result$status, "discarded") ||
        isTRUE(result$provider_access) || isTRUE(result$network_access) ||
        isTRUE(result$market_history_write) || isTRUE(result$canonical_write)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    operation_state$value <- "idle"
    result
  }
  # Die Erstnotiz des Anbietersymbols: reine Auskunft aus dem eigenen Bestand,
  # ohne Abruf. Sie steht am Symbol, nicht an der Notierungsbindung, und
  # ueberlebt deshalb eine erneuerte Einrichtung (#283, 25.09.2026).
  notation <- function(provider_symbol) {
    parsed <- run_cli("notation", list(
      context = context_payload, data_space_path = data_space,
      provider_symbol = provider_symbol
    ))
    if (identical(parsed$status, "absent")) return(NULL)
    if (!identical(parsed$status, "known") || !is.character(parsed$first_trade_date) ||
        length(parsed$first_trade_date) != 1L ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", parsed$first_trade_date) ||
        isTRUE(parsed$provider_access) || isTRUE(parsed$network_access) ||
        isTRUE(parsed$market_history_write) || isTRUE(parsed$canonical_write)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    list(first_trade_date = parsed$first_trade_date, observed_at_utc = parsed$observed_at_utc)
  }
  # Alle Erstnotizen in einem Aufruf: Die Vorbereitung eines Sammellaufs braucht
  # sie fuer jedes Asset, und ein Prozessstart je Asset kostet mehr als das
  # Lesen selbst (26.09.2026, #283).
  notations <- function() {
    parsed <- run_cli("notations", list(context = context_payload, data_space_path = data_space))
    rows <- parsed$rows
    if (!identical(parsed$status, "known") || !is.list(rows)) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    known <- new.env(hash = TRUE, parent = emptyenv())
    for (row in rows) {
      if (!is.list(row) || !is.character(row$provider_symbol) || length(row$provider_symbol) != 1L ||
          !is.character(row$first_trade_date) || length(row$first_trade_date) != 1L ||
          !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$first_trade_date)) {
        .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
      }
      assign(row$provider_symbol, row$first_trade_date, envir = known)
    }
    known
  }
  recover <- function(listing_ref) {
    result <- run_cli("recover", list(
      context = context_payload, data_space_path = data_space, listing_ref = listing_ref,
      confirmed = TRUE
    ))
    if (identical(result$status, "absent")) {
      operation_state$value <- "idle"
      return(NULL)
    }
    if (!identical(result$status, "recovered") || !is.character(result$stage_ref) ||
        length(result$stage_ref) != 1L || !grepl("^mhs_[a-f0-9]{32}$", result$stage_ref) ||
        !is.character(result$state) || length(result$state) != 1L ||
        !result$state %in% c("staged_review", "published", "rejected", "fetch_failed", "recovery_required")) {
      .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
    }
    if (result$state %in% c("staged_review", "published", "rejected")) {
      result$public_review <- validate_browser(
        data_market_history_review_validate_v1, result$public_review
      )
      if (identical(result$state, "staged_review")) {
        if (!is.null(result$public_result)) {
          .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
        }
      } else if (identical(result$state, "published")) {
        result$public_result <- validate_browser(
          data_market_history_publication_result_validate_v1, result$public_result
        )
      } else {
        result$public_result <- validate_browser(
          data_market_history_rejection_result_validate_v1, result$public_result
        )
      }
      assign(
        result$public_review$review_ref,
        list(
          stage_ref = result$stage_ref, public = result$public_review,
          consumed = !identical(result$state, "staged_review")
        ),
        envir = reviews
      )
    } else {
      if (identical(result$state, "fetch_failed") && !is.null(result$public_review)) {
        .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
      }
      if (identical(result$state, "recovery_required") && !is.null(result$public_review)) {
        result$public_review <- validate_browser(
          data_market_history_review_validate_v1, result$public_review
        )
        assign(
          result$public_review$review_ref,
          list(stage_ref = result$stage_ref, public = result$public_review, consumed = TRUE),
          envir = reviews
        )
      }
      result$public_result <- validate_browser(
        data_market_history_recovery_result_validate_v1, result$public_result
      )
      if (!identical(result$public_result$status, result$state)) {
        .data_market_history_review_service_abort_v1("data_market_history_review_boundary_failed")
      }
    }
    operation_state$value <- result$state
    list(
      state = result$state,
      stage_ref = result$stage_ref,
      public_review = result$public_review,
      public_result = result$public_result
    )
  }
  structure(list(
    contract_version = "data_market_history_review_service_v1",
    preview = preview, stage = stage, publish = publish, reject = reject, recover = recover, discard = discard, notation = notation, notations = notations,
    automatic_provider_access = FALSE, automatic_retry = FALSE,
    provider_refetch_on_publish = FALSE, fetch_writes_market_history = FALSE,
    browser_paths_exposed = FALSE, browser_context_exposed = FALSE,
    browser_candidate_fingerprints_exposed = FALSE
  ), class = c("spot_data_market_history_review_service_v1", "list"))
}
