data_portfolio_snapshot_service_error_codes_v1 <- function() c(
  "data_portfolio_snapshot_service_invalid",
  "data_portfolio_snapshot_confirmation_required",
  "data_portfolio_snapshot_boundary_failed"
)

.data_portfolio_snapshot_abort_v1 <- function(code) {
  allowed <- c(data_portfolio_snapshot_service_error_codes_v1(),
               "portfolio_snapshot_publication_context_invalid",
               "portfolio_snapshot_publication_input_invalid",
               "portfolio_snapshot_publication_evidence_invalid",
               "portfolio_snapshot_publication_plan_stale",
               "portfolio_snapshot_publication_confirmation_required",
               "portfolio_snapshot_publication_failed",
               "portfolio_snapshot_publication_boundary_failed",
               "portfolio_snapshot_freshness_context_invalid",
               "portfolio_snapshot_freshness_evidence_invalid",
               "portfolio_snapshot_freshness_input_invalid",
               "portfolio_snapshot_freshness_boundary_failed",
               # Tageshistorie (#473)
               "portfolio_history_context_invalid", "portfolio_history_input_invalid", "portfolio_history_fifo_stale",
               "portfolio_history_evidence_invalid", "portfolio_history_store_invalid",
               # Staende je Datenart (#463)
               "data_stands_context_invalid", "data_stands_input_invalid", "data_stands_evidence_invalid",
               # Veroeffentlichte Tageshistorie (#473)
               "portfolio_history_publication_context_invalid", "portfolio_history_publication_input_invalid",
               "portfolio_history_publication_evidence_invalid", "portfolio_history_publication_failed",
               "portfolio_history_publication_boundary_failed",
               # Datenbasis (rc.314, #478)
               "data_basis_publication_context_invalid", "data_basis_publication_input_invalid", "data_basis_publication_failed")
  if (!is.character(code) || length(code) != 1L || !(code %in% allowed)) {
    code <- "data_portfolio_snapshot_boundary_failed"
  }
  stop(structure(list(message = code, call = NULL, code = code),
                 class = c("spot_data_portfolio_snapshot_error_v1", "error", "condition")))
}

# Plan und Veroeffentlichung getrennt: Der Plan zeigt, was entstuende, ohne
# etwas zu schreiben; veroeffentlicht wird nur genau der bestaetigte Inhalt
# (#373, 26.09.2026).
new_data_portfolio_snapshot_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) ||
      !valid_context || !identical(context$runtime_mode, "desktop_product") ||
      !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) {
    .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_service_invalid")
  }
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3")
  cli <- file.path(project_root, "scripts", "desktop_portfolio_snapshot.py")
  data_space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(data_space) ||
      nzchar(Sys.readlink(cli)) || nzchar(Sys.readlink(data_space))) {
    .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_service_invalid")
  }
  context_payload <- list(tenant_id = context$tenant_id, user_id = context$user_id,
                          data_space_id = context$data_space_id)
  run_cli_process <- function(command, payload) {
    encoded <- as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))
    stderr_path <- tempfile("portfolio-snapshot-stderr-")
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
        parsed$code else "data_portfolio_snapshot_boundary_failed"
      .data_portfolio_snapshot_abort_v1(code)
    }
    parsed
  }
  run_cli <- function(command, payload) {
    if (is.null(cli_runner)) return(run_cli_process(command, payload))
    parsed <- tryCatch(cli_runner(command, payload), error = function(error) NULL)
    if (is.null(parsed) || !is.list(parsed) || isTRUE(parsed$status %in% c("blocked", "failed"))) {
      code <- if (is.list(parsed) && is.character(parsed$code) && length(parsed$code) == 1L)
        parsed$code else "data_portfolio_snapshot_boundary_failed"
      .data_portfolio_snapshot_abort_v1(code)
    }
    parsed
  }
  structure(list(
    freshness = function(as_of_date) run_cli("freshness", list(
      context = context_payload, data_space_path = data_space, as_of_date = as_of_date)),
    plan = function(as_of_date, planned_at_utc) run_cli("plan", list(
      context = context_payload, data_space_path = data_space,
      as_of_date = as_of_date, planned_at_utc = planned_at_utc)),
    publish = function(as_of_date, plan_fingerprint, confirmed, published_at_utc) {
      if (!isTRUE(confirmed)) .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_confirmation_required")
      run_cli("publish", list(
        context = context_payload, data_space_path = data_space, as_of_date = as_of_date,
        plan_fingerprint = plan_fingerprint, confirmed = TRUE, published_at_utc = published_at_utc))
    },
    # Alle veroeffentlichten Staende und das Lesen eines bestimmten. Bis rc.242
    # zeigte die Karte nur den zuletzt veroeffentlichten; wer einen frueheren
    # Stichtag erneut veroeffentlichte, bekam "bereits veroeffentlicht" und sah
    # weiter den anderen Stand (Befund 12.10.2026).
    published = function() {
      value <- run_cli("list", list(context = context_payload, data_space_path = data_space))
      if (!is.list(value) || !value$status %in% c("absent", "available") || !is.list(value$snapshots)) {
        .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      }
      for (row in value$snapshots) {
        if (!is.list(row) || !is.character(row$snapshot_id) || length(row$snapshot_id) != 1L ||
            !grepl("^psn_[a-z0-9_]{4,72}$", row$snapshot_id) ||
            !is.character(row$as_of_date) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$as_of_date) ||
            !row$snapshot_status %in% c("complete", "partial")) {
          .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
        }
      }
      value
    },
    # Tageshistorie (#473): fortschreiben schreibt nur in ihren eigenen Speicher im Datenraum; lesen liefert Tagessummen.
    # `through_date` (#567): Ohne den Baustein „Marktdaten“ bestimmt kein Kursabruf den letzten Tag; die Reihe reicht dann bis zu
    # diesem Tag - dem gestrigen, wie der Snapshot ohne Verlauf (#542). Mit Marktdaten wertet der Kern ihn nicht aus.
    history_update = function(requested_at_utc, rebuild = FALSE, through_date = NULL) run_cli("history-update", list(
      context = context_payload, data_space_path = data_space, requested_at_utc = requested_at_utc, rebuild = isTRUE(rebuild),
      through_date = if (is.null(through_date)) format(Sys.Date() - 1L, "%Y-%m-%d") else as.character(through_date))),
    history_read = function(start = "", end = "") run_cli("history-read", list(
      context = context_payload, data_space_path = data_space,
      start = if (is.null(start) || is.na(start)) "" else as.character(start), end = if (is.null(end) || is.na(end)) "" else as.character(end))),
    # Staende je Datenart (#463): bis wann Buchungen, Rewards, Cash und Kurse reichen. Nur lesend.
    stands = function(as_of_date) run_cli("stands", list(
      context = context_payload, data_space_path = data_space, as_of_date = as_of_date)),
    # Die Tageshistorie fuer die Analyse veroeffentlichen (#473); unveraendert bleibt es bei "already_published".
    history_publish = function(published_at_utc) run_cli("history-publish", list(
      context = context_payload, data_space_path = data_space, published_at_utc = published_at_utc)),
    # Quellluecken gehaltener Assets im Zeitraum (#477), fuer den optionalen Nachabruf. Nur lesend.
    recent_gaps = function(start, end) run_cli("recent-gaps", list(
      context = context_payload, data_space_path = data_space, start = start, end = end)),
    show = function(snapshot_id) {
      if (!is.character(snapshot_id) || length(snapshot_id) != 1L || is.na(snapshot_id) ||
          !grepl("^psn_[a-z0-9_]{4,72}$", snapshot_id)) {
        .data_portfolio_snapshot_abort_v1("portfolio_snapshot_publication_input_invalid")
      }
      value <- run_cli("show", list(context = context_payload, data_space_path = data_space, snapshot_id = snapshot_id))
      if (!is.list(value) || !identical(value$snapshot_id, snapshot_id) ||
          !value$snapshot_status %in% c("complete", "partial") || !is.list(value$positions) ||
          !is.list(value$excluded_positions) || !is.list(value$totals) || !is.list(value$freshness)) {
        .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      }
      value
    },
    # Momentaufnahme (rc.313): nach dem Kursabruf veroeffentlichen - nur die Data-App ruft das, als letzten Schritt von
    # „Alles aktualisieren“ - und den juengsten Stand lesen (Analyse).
    intraday_publish = function(as_of_date, published_at_utc) {
      value <- run_cli("intraday-publish", list(context = context_payload, data_space_path = data_space,
                                                 as_of_date = as_of_date, published_at_utc = published_at_utc))
      if (!is.list(value) || !value$status %in% c("published", "already_published", "no_quotes"))
        .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      value
    },
    # Die Datenbasis veroeffentlichen (rc.314, #478): zum Schluss von "Alles aktualisieren". `run_center` sind die Eingaben des
    # letzten Abschlusses (data_basis_run_center_v1) oder NULL, wenn der Lauf sie nicht gelesen hat.
    basis_publish = function(as_of_date, published_at_utc, run_center = NULL) {
      value <- run_cli("basis-publish", list(context = context_payload, data_space_path = data_space, as_of_date = as_of_date,
                                              published_at_utc = published_at_utc, run_center = run_center))
      if (!is.list(value) || !value$status %in% c("published", "already_published") || !is.list(value$section_status))
        .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      value
    },
    # Nach Stammdatenpflege (rc.332, #422): Der Kern prueft und veroeffentlicht in einem Schritt, aber nur, wenn sich nichts
    # geaendert hat, womit Steuer und Analyse rechnen. Sonst "blocked_calculation" (oder _never_published, _unreadable).
    basis_publish_names = function(published_at_utc) {
      value <- run_cli("basis-publish-names", list(context = context_payload, data_space_path = data_space, published_at_utc = published_at_utc))
      known <- c("published", "already_published", "blocked_calculation", "blocked_never_published", "blocked_unreadable")
      if (!is.list(value) || !isTRUE(value$status %in% known)) .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      value
    },
    intraday_read = function() {
      value <- run_cli("intraday-read", list(context = context_payload, data_space_path = data_space))
      if (!is.list(value) || !value$status %in% c("absent", "available") ||
          (identical(value$status, "available") && (!is.list(value$positions) || !is.list(value$totals) || !is.list(value$quotes))))
        .data_portfolio_snapshot_abort_v1("data_portfolio_snapshot_boundary_failed")
      value
    }
  ), class = "spot_data_portfolio_snapshot_service_v1")
}

# Nur die lesenden Teile (rc.313, #478): Die Analyse zeigt veroeffentlichte Stichtags-Snapshots und die Momentaufnahme; planen,
# veroeffentlichen und Kurse abrufen bleiben bei der Data-App.
data_portfolio_snapshot_reader_v1 <- function(service) {
  if (!inherits(service, "spot_data_portfolio_snapshot_service_v1")) return(NULL)
  structure(list(published = service$published, show = service$show, intraday_read = service$intraday_read),
            class = "spot_data_portfolio_snapshot_reader_v1")
}
