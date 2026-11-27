# Speicher aufraeumen (#438). Festlegung (23.10.2026): nur Zwischenstaende entfernen, die nachweislich nichts
# mehr tragen, mit Vorschau und Bestaetigung; was eine Korrektur belegt, bleibt vollstaendig.
#
# Zwei Regeln des Kerns, beide seit #283 vorhanden und hier erstmals bedienbar:
# - Buchungsbestand: Generationen, deren Inhalt vollstaendig in der aktiven steht. Es bleiben die aktive, jede mit einer
#   Korrekturquittung und jeder darin benannte Vorgaenger (dort steht die wegkorrigierte Buchung im Wortlaut).
# - Bewertungen: ueberholte Laeufe; je Asset bleibt der juengste Beleg und der juengste Lauf ueberhaupt.
# Beide Plaene werden beim Ausfuehren unter der jeweiligen Schreibsperre neu erhoben und muessen dem gezeigten gleichen.

data_storage_retention_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^storage_retention_[a-z_]+$", code)) code <- "storage_retention_failed"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_storage_retention_error_v1", "error", "condition")))
}

new_data_storage_retention_service_v1 <- function(project_root, context, ledger_runner = NULL, valuation_runner = NULL) {
  space <- runtime_data_space_path(context)
  product <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  ledger <- if (is.function(ledger_runner)) ledger_runner else function(command, extra)
    .per_asset_review_adapter_run(project_root, command, c(list(context = product, data_space_path = space), extra))
  valuation <- if (is.function(valuation_runner)) valuation_runner else {
    python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_market_valuation.py")
    function(command, payload) {
      if (!nzchar(python) || !file.exists(cli)) data_storage_retention_abort_v1("storage_retention_failed")
      body <- list(context = list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id),
        data_space_path = space, payload = payload)
      text <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE,
        input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
      value <- tryCatch(jsonlite::fromJSON(tail(text, 1L), simplifyVector = FALSE), error = function(error) NULL)
      if (!is.list(value) || !identical(value$status, "completed"))
        data_storage_retention_abort_v1(if (identical(value$code, "desktop_market_valuation_stale")) "storage_retention_stale" else "storage_retention_failed")
      value$value
    }
  }
  count <- function(value) if (is.numeric(value) && length(value) == 1L && !is.na(value)) as.numeric(value) else 0
  list(
    contract_version = "data_storage_retention_service_v1",
    # Ein Bereich, der sich nicht lesen laesst, bleibt unberuehrt und wird als solcher gezeigt; der andere geht trotzdem.
    plan = function() {
      generations <- tryCatch(ledger("generation-retention-plan", list())$plan, error = function(error) NULL)
      runs <- tryCatch(valuation("retain-plan", list(read_only = TRUE)), error = function(error) NULL)
      if (!is.list(generations) && !is.list(runs)) data_storage_retention_abort_v1("storage_retention_failed")
      list(ledger = if (is.list(generations)) generations else NULL, valuation = if (is.list(runs)) runs else NULL,
        removed_byte_count = count(generations$removed_byte_count) + count(runs$removed_byte_count))
    },
    apply = function(plan, applied_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_storage_retention_abort_v1("storage_retention_confirmation_required")
      if (!is.list(plan) || (!is.list(plan$ledger) && !is.list(plan$valuation))) data_storage_retention_abort_v1("storage_retention_failed")
      done <- list(ledger = NULL, valuation = NULL)
      if (is.list(plan$ledger) && count(plan$ledger$removed_generation_count) > 0) done$ledger <- tryCatch(
        ledger("generation-retention-apply", list(plan_fingerprint = plan$ledger$plan_fingerprint, confirmed = TRUE, applied_at_utc = applied_at_utc))$receipt,
        error = function(error) data_storage_retention_abort_v1(if (grepl("stale", conditionMessage(error))) "storage_retention_stale" else "storage_retention_failed"))
      if (is.list(plan$valuation) && count(plan$valuation$removed_file_count) > 0)
        done$valuation <- valuation("retain-apply", list(plan_fingerprint = plan$valuation$plan_fingerprint, confirmed = TRUE))
      done
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE)
}

data_storage_bytes_label_v1 <- function(bytes) {
  bytes <- if (is.numeric(bytes) && length(bytes) == 1L && !is.na(bytes)) bytes else 0
  if (bytes >= 1e9) return(paste(format(round(bytes / 1e9, 1), nsmall = 1, decimal.mark = ","), "GB"))
  if (bytes >= 1e6) return(paste(format(round(bytes / 1e6), big.mark = ".", decimal.mark = ","), "MB"))
  paste(format(round(bytes / 1e3), big.mark = ".", decimal.mark = ","), "kB")
}

data_storage_retention_ui_v1 <- function() portelyra_card("Speicher aufräumen", help = "app-data#sicherheit-und-speicher",
  copy = "Entfernt Zwischenstände, die nichts mehr tragen. Was eine Korrektur belegt, bleibt vollständig.",
  note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-storage-retention", paste(
    "Entfernt werden ältere Generationen des Buchungsbestands, deren Inhalt vollständig in der aktuellen steht, und überholte",
    "Bewertungsläufe (je Asset bleibt der jüngste). Danach sind auch die Backups kleiner.")),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("storage_retention_plan", "Aufräumen prüfen", class = "btn-default")),
  shiny::uiOutput("storage_retention_state"))

# Was die Karte zeigt: der Plan mit Bestaetigung, das Ergebnis oder ein Fehler. Reine Funktion, damit sie ohne Server pruefbar ist.
data_storage_retention_state_ui_v1 <- function(plan = NULL, result = NULL, failure = NULL) {
  if (identical(failure, "storage_retention_confirmation_required") && !is.null(plan)) return(shiny::tagList(
    data_storage_retention_state_ui_v1(plan), portelyra_status_panel("Noch nicht bestätigt", "Bitte den Plan prüfen und das Kästchen setzen.", tone = "warning")))
  if (!is.null(failure)) return(portelyra_status_panel("Nicht aufgeräumt", switch(failure,
    storage_retention_stale = "Der Bestand hat sich seit der Prüfung geändert. Es wurde nichts entfernt – bitte erneut prüfen.",
    storage_retention_confirmation_required = "Bitte zuerst bestätigen.",
    "Die Pläne ließen sich nicht lesen oder nicht ausführen. Es wurde nichts entfernt, was der Plan nicht nannte."), tone = "error"))
  if (!is.null(result)) {
    teile <- c(
      if (is.list(result$ledger)) sprintf("%d Generationen des Buchungsbestands (%s)", as.integer(result$ledger$removed_generation_count),
        data_storage_bytes_label_v1(result$ledger$removed_byte_count)),
      if (is.list(result$valuation)) sprintf("%d Dateien überholter Bewertungsläufe (%s)", as.integer(result$valuation$removed_file_count),
        data_storage_bytes_label_v1(result$valuation$removed_byte_count)))
    return(portelyra_status_panel(if (length(teile)) "Aufgeräumt" else "Nichts zu entfernen",
      if (length(teile)) paste0("Entfernt: ", paste(teile, collapse = " und "), ". Eine Quittung je Bereich liegt im Datenraum.")
      else "Es lagen keine Zwischenstände vor.", tone = "positive"))
  }
  if (is.null(plan)) return(NULL)
  ledger <- plan$ledger; runs <- plan$valuation
  generationen <- as.integer(if (is.null(ledger$removed_generation_count)) 0L else ledger$removed_generation_count)
  dateien <- as.integer(if (is.null(runs$removed_file_count)) 0L else runs$removed_file_count)
  unlesbar <- "nicht lesbar – bleibt unverändert."
  if (generationen == 0L && dateien == 0L) return(portelyra_status_panel("Nichts zu entfernen",
    paste("Es liegen keine Zwischenstände vor.", if (is.null(ledger)) paste("Buchungsbestand:", unlesbar) else "",
      if (is.null(runs)) paste("Bewertungen:", unlesbar) else ""), tone = "neutral"))
  shiny::tagList(
    shiny::tags$ul(class = "pl-plain-list",
      shiny::tags$li(if (is.null(ledger)) paste("Buchungsbestand:", unlesbar) else sprintf(
        "Buchungsbestand: %d von %d Generationen entfernen (%s); %d bleiben, davon %d mit Korrekturquittung.",
        generationen, as.integer(ledger$generation_count), data_storage_bytes_label_v1(ledger$removed_byte_count),
        as.integer(ledger$kept_generation_count), as.integer(ledger$receipt_generation_count))),
      shiny::tags$li(if (is.null(runs)) paste("Bewertungen:", unlesbar) else sprintf(
        "Bewertungen: %d überholte Läufe und %d abgebrochene Vorbereitungen, zusammen %d Dateien (%s); %d Läufe bleiben.",
        as.integer(runs$superseded_run_count), as.integer(runs$unfinished_preview_count), dateien,
        data_storage_bytes_label_v1(runs$removed_byte_count), as.integer(runs$kept_run_count)))),
    shiny::checkboxInput("storage_retention_confirm", sprintf("Ich habe den Plan geprüft: zusammen %s entfernen.", data_storage_bytes_label_v1(plan$removed_byte_count)), FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("storage_retention_apply", "Aufräumen", class = "btn-primary")))
}

data_storage_retention_server_v1 <- function(input, output, session, service, now_utc) {
  plan <- shiny::reactiveVal(NULL); result <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL)
  code_of <- function(error) if (inherits(error, "spot_data_storage_retention_error_v1")) error$code else "storage_retention_failed"
  shiny::observeEvent(input$storage_retention_plan, {
    result(NULL); failure(NULL); plan(NULL)
    value <- tryCatch(if (is.null(service)) data_storage_retention_abort_v1("storage_retention_failed") else service$plan(), error = function(error) code_of(error))
    if (is.character(value)) failure(value) else plan(value)
  })
  shiny::observeEvent(input$storage_retention_apply, {
    current <- plan()
    if (is.null(current)) return(invisible(NULL))
    if (!isTRUE(input$storage_retention_confirm)) { failure("storage_retention_confirmation_required"); return(invisible(NULL)) }
    failure(NULL)
    value <- tryCatch(service$apply(current, now_utc(), TRUE), error = function(error) code_of(error))
    plan(NULL)
    if (is.character(value)) failure(value) else { failure(NULL); result(value) }
  })
  output$storage_retention_state <- shiny::renderUI(data_storage_retention_state_ui_v1(plan(), result(), failure()))
  invisible(list(plan = plan, result = result, failure = failure))
}
