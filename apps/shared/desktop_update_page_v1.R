# Fortschrittsseite des Updates (#562 Paket 4, 0.3.3): Wer „Update jetzt einspielen“ klickt, sieht danach eine eigene Seite mit den
# Schritten von `update` (wie im Terminal: pruefen, beenden, entsperren, Backup, einspielen, pruefen, ausduennen, starten), mit dem Grund,
# falls etwas scheitert, und dem Rueckweg. Sie laeuft in einem Kindprozess des Updates auf einem eigenen Port (Data-Port + 4), damit der
# Neustart den Data-Port frei hat und die Seite auch einen Fehler noch zeigt, wenn das bisherige Portelyra schon wieder laeuft. Das Update
# schreibt seinen Stand in eine Datei (0600); die Seite liest sie jede Sekunde. Wie die Entsperrseite nur mit Start-Token.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base.
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DESKTOP_UPDATE_PROGRESS_CONTRACT_V1 <- "desktop_update_progress_v1"
DESKTOP_UPDATE_PAGE_CSS_V1 <- ".pl-steps li.pl-step-failed::before{content:'\\2715';color:var(--pl-danger,#9a3f3f)}.pl-steps li.pl-step-failed .pl-step-label{font-weight:600}"
DESKTOP_UPDATE_STEPS_V1 <- c(check = "Archiv und Signatur prüfen", stop = "Portelyra beenden", unlock = "Bestand entsperren",
                             backup = "Backup anlegen und prüfen", upgrade = "Neue Version einspielen", preflight = "Neue Version prüfen",
                             prune = "Ältere Backups ausdünnen", start = "Portelyra neu starten")

# Stand schreiben (das Update) und lesen (die Seite). Ein symbolischer Link wird weder geschrieben noch gelesen.
desktop_update_progress_write_v1 <- function(path, value) {
  link <- Sys.readlink(path)
  if (isTRUE(!is.na(link) && nzchar(link))) return(invisible(FALSE))
  temporary <- paste0(path, ".tmp-", Sys.getpid())
  old_umask <- Sys.umask("0077"); on.exit(Sys.umask(old_umask), add = TRUE)
  written <- tryCatch({
    writeLines(enc2utf8(as.character(jsonlite::toJSON(c(list(contract_version = DESKTOP_UPDATE_PROGRESS_CONTRACT_V1), value),
                                                      auto_unbox = TRUE, null = "null", digits = NA))), temporary, useBytes = TRUE)
    Sys.chmod(temporary, mode = "0600")
    file.rename(temporary, path)
  }, error = function(error) FALSE)
  if (!isTRUE(written)) unlink(temporary)
  invisible(isTRUE(written))
}
desktop_update_progress_read_v1 <- function(path) {
  link <- Sys.readlink(path)
  if (!is.character(path) || !file.exists(path) || isTRUE(!is.na(link) && nzchar(link))) return(NULL)
  value <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
  if (is.list(value) && identical(value$contract_version, DESKTOP_UPDATE_PROGRESS_CONTRACT_V1)) value else NULL
}

# Was die Seite zeigt: je Schritt erledigt, laeuft, angehalten oder offen; darunter das Ergebnis mit Grund und Rueckweg.
desktop_update_page_view_v1 <- function(progress) {
  if (!is.list(progress)) return(shiny::p(class = "pl-field-hint", "Das Update startet …"))
  done <- vapply(progress$steps %||% list(), function(step) if (is.character(step$step)) step$step else "", character(1L))
  outcome <- progress$outcome
  failed_at <- if (is.list(outcome) && identical(outcome$status, "blocked") && is.character(outcome$step)) outcome$step else ""
  current <- if (is.character(progress$current)) progress$current else ""
  rows <- lapply(names(DESKTOP_UPDATE_STEPS_V1), function(key) {
    state <- if (identical(key, failed_at)) "failed" else if (key %in% done) "done" else if (identical(key, current) && is.null(outcome)) "running" else "open"
    word <- switch(state, done = "erledigt", failed = "angehalten", running = "läuft …", "")
    shiny::tags$li(class = paste0("pl-step-", state),
                   shiny::span(class = "pl-step-label", DESKTOP_UPDATE_STEPS_V1[[key]]), shiny::span(class = "pl-step-state", word))
  })
  share <- round(100 * length(intersect(done, names(DESKTOP_UPDATE_STEPS_V1))) / length(DESKTOP_UPDATE_STEPS_V1))
  versions <- if (is.character(progress$from_version) && is.character(progress$to_version)) paste0("Von Version ", progress$from_version, " auf ", progress$to_version, ".") else NULL
  result <- if (!is.list(outcome)) shiny::p(class = "pl-field-hint", "Bitte dieses Fenster offen lassen; Portelyra startet danach von selbst neu.")
    else desktop_update_outcome_ui_v1(outcome, progress)
  shiny::tagList(
    if (!is.null(versions)) shiny::p(versions),
    shiny::div(class = "pl-steps", shiny::div(class = "pl-steps-bar", shiny::div(class = "pl-steps-fill", style = paste0("width:", share, "%"))),
               shiny::tags$ol(rows)),
    result)
}

desktop_update_outcome_ui_v1 <- function(outcome, progress = list()) {
  panel <- function(title, copy, tone) if (exists("portelyra_status_panel", mode = "function")) portelyra_status_panel(title, copy, tone = tone)
    else shiny::div(shiny::strong(title), shiny::p(copy))
  if (identical(outcome$status, "updated")) {
    started <- identical(outcome$start, "started")
    return(panel(paste0("Portelyra ", outcome$product_version, " ist eingespielt"),
                 if (started) "Portelyra hat sich in einem neuen Fenster geöffnet. Dieses Fenster können Sie schließen."
                 else "Portelyra antwortet noch nicht. Bitte über den Starter öffnen; das Update selbst ist abgeschlossen.", "positive"))
  }
  if (identical(outcome$status, "already_current")) return(panel("Schon aktuell", paste0("Version ", outcome$product_version, " ist bereits installiert."), "neutral"))
  code <- if (is.character(outcome$code)) outcome$code else "desktop_product_boundary_failed"
  text <- if (exists("pl_error_text_v1", mode = "function")) tryCatch(pl_error_text_v1(code), error = function(error) NULL) else NULL
  step <- if (is.character(outcome$step) && outcome$step %in% names(DESKTOP_UPDATE_STEPS_V1)) DESKTOP_UPDATE_STEPS_V1[[outcome$step]] else "einem Schritt"
  back <- if (identical(outcome$restarted, "started")) paste0("Portelyra läuft wieder mit Version ", progress$from_version %||% "der bisherigen Version", ".")
    else if (is.character(outcome$rollback)) "Die neue Version ist schon eingespielt, startet aber nicht. Zurück zur vorigen Version im Terminal: Rscript ~/.local/share/portelyra/library/.portelyra-source/scripts/portelyra_desktop.R rollback --confirm ROLLBACK_LOCAL_RUNTIME"
    else "Portelyra läuft noch mit der bisherigen Version oder startet über den Starter wie gewohnt."
  panel(paste0("Update angehalten bei „", step, "“"),
        paste0(if (is.character(text) && nzchar(text)) text else paste0("Portelyra meldet: ", code), " ", back,
               " Den Ablauf protokolliert ", progress$log %||% "die Datei update-<version>.log unter ~/.local/state/portelyra", "."), "warning")
}

desktop_update_page_ui_v1 <- function(css = "") shiny::fluidPage(
  shiny::tags$head(shiny::tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
                   shiny::tags$meta(name = "referrer", content = "no-referrer"), shiny::tags$title("Portelyra wird aktualisiert"),
                   shiny::tags$style(shiny::HTML(css)), shiny::tags$style(shiny::HTML(DESKTOP_UPDATE_PAGE_CSS_V1))),
  shiny::div(class = "pl-setup", style = "max-width:720px;margin:40px auto;padding:0 16px;",
    shiny::h2("Portelyra wird aktualisiert"),
    shiny::uiOutput("update_progress")))

# Die Seite liest den Stand jede Sekunde, solange ein Fenster offen ist.
desktop_update_page_server_v1 <- function(progress_path, poll_ms = 1000L) {
  function(input, output, session) {
    progress <- shiny::reactivePoll(poll_ms, session,
      checkFunc = function() { info <- file.info(progress_path); paste(info$mtime, info$size) },
      valueFunc = function() desktop_update_progress_read_v1(progress_path))
    output$update_progress <- shiny::renderUI(desktop_update_page_view_v1(progress()))
  }
}

# Fuer das Update (Kindprozess): die Seite auf `port`. Sie endet von selbst - unabhaengig davon, ob ein Fenster offen ist -, wenn nach dem
# Ergebnis `linger_ms` vergangen sind oder insgesamt `limit_ms` (90 Minuten; ein erstes verschluesseltes Backup kann mehrere Minuten dauern). Das
# Token prueft nur sie selbst: Eine geerbte Zugangsdatei des beendeten Portelyra (PORTELYRA_ACCESS_FILE_INTERNAL) gilt hier nicht.
desktop_update_page_blocking_v1 <- function(progress_path, port, open_browser = NULL, css = "", token = NULL, linger_ms = 600000, limit_ms = 5400000) {
  Sys.unsetenv("PORTELYRA_ACCESS_FILE_INTERNAL")
  started <- Sys.time()
  ended_at <- NULL
  elapsed_ms <- function(since) as.numeric(difftime(Sys.time(), since, units = "secs")) * 1000
  watch <- function() {
    value <- desktop_update_progress_read_v1(progress_path)
    if (is.list(value) && is.list(value$outcome) && is.null(ended_at)) ended_at <<- Sys.time()
    if ((!is.null(ended_at) && elapsed_ms(ended_at) >= linger_ms) || elapsed_ms(started) >= limit_ms) shiny::stopApp(TRUE)
    else later::later(watch, 2)
  }
  app <- shiny::shinyApp(desktop_update_page_ui_v1(css), desktop_page_guard_v1(desktop_update_page_server_v1(progress_path), token))
  if (is.function(open_browser)) later::later(function() open_browser(desktop_page_url_v1(port, token)), 0.5)
  later::later(watch, 2)
  shiny::runApp(app, host = "127.0.0.1", port = port, launch.browser = FALSE, quiet = TRUE)
  invisible(TRUE)
}
