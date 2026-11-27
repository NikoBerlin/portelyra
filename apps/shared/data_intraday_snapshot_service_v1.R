data_intraday_snapshot_service_error_codes_v1 <- function() c(
  "data_intraday_snapshot_service_invalid",
  "data_intraday_snapshot_confirmation_required",
  "data_intraday_snapshot_boundary_failed"
)

.data_intraday_snapshot_abort_v1 <- function(code) {
  allowed <- c(data_intraday_snapshot_service_error_codes_v1(),
               "desktop_intraday_snapshot_input_invalid",
               "desktop_intraday_snapshot_state_required",
               "desktop_intraday_snapshot_confirmation_required",
               "desktop_intraday_snapshot_provider_inactive",
               "desktop_intraday_snapshot_provider_state_invalid",
               "market_valuation_state_store_invalid",
               "portfolio_snapshot_projection_context_invalid",
               "portfolio_snapshot_projection_input_invalid",
               "portfolio_snapshot_projection_evidence_invalid",
               "portfolio_snapshot_projection_boundary_failed",
               "market_valuation_state_schema_changed",
               "market_valuation_state_algorithm_changed",
               # Seit #554 liegen parallele Abrufe und "Sperre steckt Folgetage an" in den Nutzereinstellungen.
               "user_settings_store_invalid")
  if (!is.character(code) || length(code) != 1L || !(code %in% allowed)) {
    code <- "data_intraday_snapshot_boundary_failed"
  }
  stop(structure(list(message = code, call = NULL, code = code),
                 class = c("spot_data_intraday_snapshot_error_v1", "error", "condition")))
}

# Ein Vorgang statt einem je Asset: Der Snapshot liest die Bereiche aus dem Bewertungsstand,
# holt die Kurse parallel und schreibt je Asset eine Zeile. Er ruft ab, schreibt
# aber weder Kurshistorie noch Bewertung fort - ein Zwischenstand der laufenden
# Sitzung ist kein Tagesschluss (#283, 26.09.2026).
new_data_intraday_snapshot_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) ||
      !valid_context || !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) {
    .data_intraday_snapshot_abort_v1("data_intraday_snapshot_service_invalid")
  }
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3")
  cli <- file.path(project_root, "scripts", "desktop_intraday_snapshot.py")
  data_space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(data_space) ||
      nzchar(Sys.readlink(cli)) || nzchar(Sys.readlink(data_space))) {
    .data_intraday_snapshot_abort_v1("data_intraday_snapshot_service_invalid")
  }
  context_payload <- list(tenant_id = context$tenant_id, user_id = context$user_id,
                          data_space_id = context$data_space_id)
  run_cli_process <- function(command, payload) {
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))
    stderr_path <- tempfile("intraday-snapshot-stderr-")
    old_umask <- Sys.umask("0077")
    on.exit({ Sys.umask(old_umask); unlink(stderr_path, force = TRUE) }, add = TRUE)
    output <- tryCatch(
      suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), shQuote(command)),
                               stdout = TRUE, stderr = stderr_path, input = encoded)),
      error = function(error) structure(character(), status = 1L))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    stderr_output <- tryCatch(
      if (file.exists(stderr_path)) readLines(stderr_path, warn = FALSE) else character(),
      error = function(error) "boundary_error")
    parsed <- tryCatch(
      if (length(output) == 1L) jsonlite::fromJSON(output[[1L]], simplifyVector = FALSE) else NULL,
      error = function(error) NULL)
    if (length(stderr_output) || length(output) != 1L || is.null(parsed) || !is.list(parsed) ||
        as.integer(status) != 0L || isTRUE(parsed$status %in% c("blocked", "failed"))) {
      code <- if (is.list(parsed) && is.character(parsed$code) && length(parsed$code) == 1L)
        parsed$code else "data_intraday_snapshot_boundary_failed"
      .data_intraday_snapshot_abort_v1(code)
    }
    parsed
  }
  run_cli <- function(command, payload) {
    if (is.null(cli_runner)) return(run_cli_process(command, payload))
    parsed <- tryCatch(cli_runner(command, payload), error = function(error) NULL)
    if (is.null(parsed) || !is.list(parsed) || isTRUE(parsed$status %in% c("blocked", "failed"))) {
      code <- if (is.list(parsed) && is.character(parsed$code) && length(parsed$code) == 1L)
        parsed$code else "data_intraday_snapshot_boundary_failed"
      .data_intraday_snapshot_abort_v1(code)
    }
    parsed
  }
  validate <- function(value) {
    if (!is.list(value) || !identical(value$contract_version, "desktop_intraday_snapshot_v1") ||
        !value$status %in% c("absent", "available") || !is.list(value$rows) ||
        isTRUE(value$canonical_write) || isTRUE(value$market_history_write)) {
      .data_intraday_snapshot_abort_v1("data_intraday_snapshot_boundary_failed")
    }
    value
  }
  read <- function() validate(run_cli("read", list(context = context_payload, data_space_path = data_space)))
  # Das fluide Bild in der Gestalt des Stichtags-Snapshots: Bestand, eigene
  # Bewertung, Cash und Summen aus derselben Rechnung, die Kurse aus dem letzten
  # Abruf. Liest nur (Festlegung 12.10.2026).
  view <- function(as_of_date) {
    if (!is.character(as_of_date) || length(as_of_date) != 1L || is.na(as_of_date) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", as_of_date)) {
      .data_intraday_snapshot_abort_v1("desktop_intraday_snapshot_input_invalid")
    }
    value <- run_cli("view", list(context = context_payload, data_space_path = data_space, as_of_date = as_of_date))
    if (!is.list(value) || !identical(value$snapshot_kind, "intraday") || !identical(value$as_of_date, as_of_date) ||
        !value$status %in% c("absent", "available") || !value$snapshot_status %in% c("complete", "partial") ||
        !is.list(value$positions) || !is.list(value$excluded_positions) || !is.list(value$totals) ||
        !is.list(value$cash) || !is.list(value$quotes) || !is.list(value$freshness) ||
        isTRUE(value$published) || isTRUE(value$provider_access) || isTRUE(value$canonical_write) ||
        isTRUE(value$market_history_write)) {
      .data_intraday_snapshot_abort_v1("data_intraday_snapshot_boundary_failed")
    }
    value
  }
  snapshot <- function(confirmed, requested_at_utc) {
    if (!isTRUE(confirmed)) {
      .data_intraday_snapshot_abort_v1("data_intraday_snapshot_confirmation_required")
    }
    validate(run_cli("snapshot", list(context = context_payload, data_space_path = data_space,
                                      confirmed = TRUE, requested_at_utc = requested_at_utc)))
  }
  parallel_requests <- function() {
    parsed <- run_cli("setting", list(context = context_payload, data_space_path = data_space))
    value <- parsed$parallel_request_count
    if (is.null(value)) NA_integer_ else as.integer(value)
  }
  set_parallel_requests <- function(value, updated_at_utc) {
    parsed <- run_cli("set-parallel", list(context = context_payload, data_space_path = data_space,
                                           parallel_request_count = as.integer(value),
                                           updated_at_utc = updated_at_utc))
    as.integer(parsed$parallel_request_count)
  }
  # Ob eine Sperre im Bewertungsstand die Folgetage ansteckt. Der gesperrte Tag
  # selbst bleibt in jedem Fall ohne Wert (#368, 28.09.2026).
  carry_across_blocked <- function() {
    parsed <- run_cli("setting", list(context = context_payload, data_space_path = data_space))
    isTRUE(parsed$carry_across_blocked)
  }
  set_carry_across_blocked <- function(value, updated_at_utc) {
    parsed <- run_cli("set-carry", list(context = context_payload, data_space_path = data_space,
                                        carry_across_blocked = isTRUE(value),
                                        updated_at_utc = updated_at_utc))
    isTRUE(parsed$carry_across_blocked)
  }
  structure(list(contract_version = "data_intraday_snapshot_service_v1",
                 read = read, view = view, snapshot = snapshot,
                 parallel_requests = parallel_requests, set_parallel_requests = set_parallel_requests,
                 carry_across_blocked = carry_across_blocked, set_carry_across_blocked = set_carry_across_blocked,
                 browser_paths_exposed = FALSE, browser_context_exposed = FALSE,
                 canonical_write = FALSE, market_history_write = FALSE, automatic_retry = FALSE),
            class = c("spot_data_intraday_snapshot_service_v1", "list"))
}
