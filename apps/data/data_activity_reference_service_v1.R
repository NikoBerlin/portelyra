# Belegangaben zu Buchungen: Transaktions-ID, Adresse der Gegenseite, Notiz -
# und der Wert eines Abgangs in EUR, wie ihn der Eigentuemer angibt.
# Lesen und ausdruecklich bestaetigt eintragen. Die Angaben liegen neben dem
# Buchungsbestand; Bestand, FIFO und Bewertung bleiben unberuehrt. Kein
# Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_activity_reference_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^activity_reference_[a-z_]+$", code)) code <- "activity_reference_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_data_activity_reference_error_v1", "error", "condition")))
}
# Ein Eingabefeld: Leerraum am Rand faellt weg, ein leeres Feld heisst "keine Angabe".
data_activity_reference_text_v1 <- function(value) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return(NULL)
  text <- trimws(value)
  if (nzchar(text)) text else NULL
}
# Wert eines Abgangs in EUR: Dezimalkomma oder Dezimalpunkt, kein Vorzeichen, kein
# Tausendertrenner. Ein leeres Feld heisst "kein Wert" (NULL), eine andere Eingabe NA.
data_activity_reference_value_v1 <- function(value) {
  text <- data_activity_reference_text_v1(value)
  if (is.null(text)) return(NULL)
  text <- sub(",", ".", text, fixed = TRUE)
  if (grepl("^(0|[1-9][0-9]{0,11})(\\.[0-9]{1,8})?$", text)) text else NA_character_
}
data_activity_reference_value_label_v1 <- function(value) {
  text <- data_activity_reference_text_v1(value)
  if (is.null(text)) "" else sub(".", ",", text, fixed = TRUE)
}
# Kennung und Adresse sind eine zusammenhaengende Zeichenfolge; Freitext gehoert in die Notiz.
data_activity_reference_token_valid_v1 <- function(value) is.null(value) || grepl("^[!-~]{1,200}$", value, perl = TRUE)
data_activity_reference_note_valid_v1 <- function(value) is.null(value) || (nchar(value) <= 4000L && !grepl("[[:cntrl:]]", value))
# Kurzform fuer die Tabellenspalte: die Kennung, sonst ein Hinweis, was hinterlegt ist.
data_activity_reference_label_v1 <- function(reference) {
  if (!is.list(reference)) return("—")
  id <- data_activity_reference_text_v1(reference$transaction_id)
  if (!is.null(id)) return(if (nchar(id) > 18L) paste0(substr(id, 1L, 8L), "…", substr(id, nchar(id) - 5L, nchar(id))) else id)
  if (!is.null(data_activity_reference_text_v1(reference$counterparty_address))) return("Adresse")
  if (!is.null(data_activity_reference_text_v1(reference$note))) return("Notiz")
  "—"
}
data_activity_reference_origin_label_v1 <- function(origin) {
  labels <- c(owner_entered = "von Hand erfasst", legacy_comment = "aus dem Kommentar des Altbestands übernommen",
    statement_source = "aus dem Auszug übernommen", carried_from_correction = "von der korrigierten Buchung übernommen")
  if (is.character(origin) && length(origin) == 1L && origin %in% names(labels)) unname(labels[[origin]]) else "Herkunft unbekannt"
}
new_data_activity_reference_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_activity_reference.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_activity_reference_abort_v1("activity_reference_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_activity_reference_abort_v1(if (is.null(parsed$code)) "activity_reference_store_invalid" else parsed$code)
    parsed$result
  }
  event_ref_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^evt_[a-z0-9_]{4,60}$", value)
  structure(list(
    contract_version = "data_activity_reference_service_v1",
    # Gueltiger Stand je Buchung als benannte Liste event_ref -> Angaben.
    read = function(event_refs = NULL) {
      if (!is.null(event_refs) && (!is.character(event_refs) || anyNA(event_refs) || !all(vapply(event_refs, event_ref_valid, logical(1L)))))
        data_activity_reference_abort_v1("activity_reference_input_invalid")
      result <- run("read", list(event_refs = if (is.null(event_refs)) NULL else as.list(unname(event_refs))))
      if (!is.list(result) || !identical(result$status, "ready") || !is.list(result$references) || isTRUE(result$canonical_write))
        data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    record = function(event_ref, transaction_id, counterparty_address, note, recorded_at_utc, confirmed) {
      id <- data_activity_reference_text_v1(transaction_id); address <- data_activity_reference_text_v1(counterparty_address)
      text <- data_activity_reference_text_v1(note)
      if (!event_ref_valid(event_ref) || !data_activity_reference_token_valid_v1(id) || !data_activity_reference_token_valid_v1(address) ||
          !data_activity_reference_note_valid_v1(text)) data_activity_reference_abort_v1("activity_reference_input_invalid")
      if (!isTRUE(confirmed)) data_activity_reference_abort_v1("activity_reference_confirmation_required")
      result <- run("record", list(
        entries = list(list(event_ref = event_ref, transaction_id = id, counterparty_address = address, note = text)),
        recorded_at_utc = recorded_at_utc, confirmed = TRUE))
      if (!is.list(result) || !identical(result$status, "recorded") || isTRUE(result$canonical_write))
        data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    # Eingetragene Werte der Abgaenge als benannte Liste event_ref -> Angaben.
    read_values = function() {
      result <- run("value-read", list())
      if (!is.list(result) || !identical(result$status, "ready") || !is.list(result$values) || isTRUE(result$canonical_write))
        data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    record_value = function(event_ref, value, recorded_at_utc, confirmed) {
      betrag <- data_activity_reference_value_v1(value)
      if (!event_ref_valid(event_ref) || (!is.null(betrag) && is.na(betrag))) data_activity_reference_abort_v1("activity_reference_input_invalid")
      if (!isTRUE(confirmed)) data_activity_reference_abort_v1("activity_reference_confirmation_required")
      result <- run("value-record", list(event_ref = event_ref, value_eur_decimal = betrag, recorded_at_utc = recorded_at_utc, confirmed = TRUE))
      if (!is.list(result) || !identical(result$status, "recorded") || isTRUE(result$canonical_write))
        data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    # Kennungen der Krypto-Buchungen aus Boersen- und Wallet-Exporten (#439): Plan (nur Zaehler) und Anwenden. Die Dateien als
    # Pfad und Originalname - der Name zaehlt fuer die Endung und fuer Leser, die aus ihm lesen.
    statement_plan = function(paths, names) {
      if (!is.character(paths) || !is.character(names) || length(paths) != length(names) || !length(paths)) data_activity_reference_abort_v1("activity_reference_input_invalid")
      result <- run("statement-plan", list(statement_root = lapply(seq_along(paths), function(index) list(paths[[index]], names[[index]]))))
      if (!is.list(result) || !identical(result$status, "planned") || isTRUE(result$canonical_write)) data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    statement_apply = function(paths, names, recorded_at_utc, confirmed) {
      if (!is.character(paths) || !is.character(names) || length(paths) != length(names) || !length(paths)) data_activity_reference_abort_v1("activity_reference_input_invalid")
      if (!isTRUE(confirmed)) data_activity_reference_abort_v1("activity_reference_confirmation_required")
      result <- run("statement-apply", list(statement_root = lapply(seq_along(paths), function(index) list(paths[[index]], names[[index]])),
        recorded_at_utc = recorded_at_utc, confirmed = TRUE))
      if (!is.list(result) || !identical(result$status, "applied")) data_activity_reference_abort_v1("activity_reference_store_invalid")
      result
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_activity_reference_service_v1", "list"))
}

# Karte "Kennungen aus Exporten nachtragen" (#439): Transaktions-ID und Adresse der Krypto-Buchungen, auch der Rewards, aus den
# CSV-Exporten der Boersen und Wallets - aus einem Ordner oder aus der Ablage (#434). Nur in leere Felder; was abweicht, bleibt.
data_reference_backfill_card_ui_v1 <- function() portelyra_card("Kennungen aus Börsen- und Wallet-Exporten nachtragen",
  copy = "Transaktions-ID und Adresse der Krypto-Buchungen – auch der Rewards – aus den CSV-Exporten.",
  note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-reference-backfill", paste(
    "Zugeordnet wird streng: dasselbe Kürzel, eine passende Art, dieselbe Menge und ein Zeitpunkt in der Nähe.",
    "Übernommen wird nur in leere Felder; was schon eingetragen ist oder abweicht, bleibt.")),
  class = "pl-write-boundary",
  htmltools::tagQuery(shiny::fileInput("reference_backfill_folder", "CSV-Exporte: einen Ordner samt Unterordnern", multiple = TRUE, buttonLabel = "Ordner wählen …"))$
    find("#reference_backfill_folder")$addAttrs(webkitdirectory = NA, directory = NA)$allTags(),
  data_statement_archive_source_ui_v1("reference_backfill"),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("reference_backfill_plan", "Kennungen prüfen", class = "btn-default")),
  shiny::uiOutput("reference_backfill_state"))
data_reference_backfill_summary_v1 <- function(plan) {
  counts <- if (is.list(plan$counts)) plan$counts else list()
  total <- function(outcomes) sum(vapply(Filter(function(item) item$outcome %in% outcomes, counts), function(item) as.integer(item$count), integer(1L)))
  files <- if (is.list(plan$file_counts)) plan$file_counts else list()
  read <- sum(vapply(names(files), function(name) if (name %in% c("unrecognized", "skipped")) 0L else as.integer(files[[name]]), integer(1L)))
  list(entries = as.integer(plan$entry_count), new = total(c("new", "new_among_alike_bookings")), ambiguous = total("ambiguous"),
    differs = total("differs_from_statement"), files_read = read, files_unrecognized = if (is.null(files$unrecognized)) 0L else as.integer(files$unrecognized))
}
data_reference_backfill_server_v1 <- function(input, output, session, service, now_utc, archive_service = NULL, accounts = NULL, resolve_id = NULL) {
  chosen <- shiny::reactiveVal(NULL); plan <- shiny::reactiveVal(NULL); notice <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$reference_backfill_folder, { chosen(input$reference_backfill_folder); plan(NULL); notice(NULL) }, ignoreInit = TRUE)
  data_statement_archive_source_server_v1(input, output, session, "reference_backfill", archive_service,
    on_take = function(frame) { chosen(frame); plan(NULL); notice(NULL) }, accounts = accounts, resolve_id = resolve_id)
  # Der Name aus der Ablage beginnt mit dem Pruefwert; fuer die Leser zaehlt der Originalname dahinter.
  original <- function(names) sub("^[0-9a-f]{8} · ", "", names)
  shiny::observeEvent(input$reference_backfill_plan, {
    files <- chosen()
    if (is.null(service) || is.null(files) || !nrow(files)) return(notice(list(tone = "error", title = "Keine Dateien gewählt", copy = "Bitte einen Ordner oder Dateien aus der Ablage wählen.")))
    result <- tryCatch(shiny::withProgress(message = "Exporte werden gelesen", value = 0.3, service$statement_plan(files$datapath, original(files$name))),
      error = function(error) structure(list(), code = if (is.null(error$code)) "activity_reference_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) return(notice(list(tone = "error", title = "Nicht geprüft", copy = "Die Exporte ließen sich nicht lesen.")))
    plan(result); notice(NULL)
  })
  shiny::observeEvent(input$reference_backfill_apply, {
    files <- chosen(); current <- plan()
    if (is.null(current) || is.null(files)) return()
    if (!isTRUE(input$reference_backfill_confirm)) return(notice(list(tone = "error", title = "Nicht bestätigt", copy = "Bitte zuerst bestätigen, dass die Kennungen übernommen werden sollen.")))
    result <- tryCatch(service$statement_apply(files$datapath, original(files$name), now_utc(), TRUE), error = function(error) NULL)
    if (is.null(result)) return(notice(list(tone = "error", title = "Nicht übernommen", copy = "Die Kennungen ließen sich nicht schreiben; es wurde nichts geändert.")))
    plan(NULL); shiny::updateCheckboxInput(session, "reference_backfill_confirm", value = FALSE)
    notice(list(tone = "positive", title = "Kennungen übernommen", copy = sprintf("%d Buchung(en) ergänzt, %d unverändert.", as.integer(result$written_count), as.integer(result$unchanged_count))))
  })
  output$reference_backfill_state <- shiny::renderUI({
    message <- notice(); current <- plan()
    if (is.list(message)) return(portelyra_status_panel(message$title, message$copy, tone = message$tone))
    if (is.null(current)) return(NULL)
    summary <- data_reference_backfill_summary_v1(current)
    shiny::tagList(
      portelyra_status_panel(if (summary$entries > 0L) sprintf("%d Buchung(en) bekommen eine Kennung oder Adresse", summary$entries) else "Nichts nachzutragen",
        sprintf("%d Datei(en) gelesen, %d nicht erkannt · neu: %d · mehrdeutig, bleibt offen: %d · weicht ab, bleibt wie eingetragen: %d.",
          summary$files_read, summary$files_unrecognized, summary$new, summary$ambiguous, summary$differs), tone = if (summary$entries > 0L) "warning" else "positive"),
      if (summary$entries > 0L) shiny::tagList(
        shiny::checkboxInput("reference_backfill_confirm", "Diese Kennungen und Adressen übernehmen", FALSE),
        shiny::actionButton("reference_backfill_apply", "Kennungen übernehmen", class = "btn-primary")))
  })
  invisible(list(chosen = chosen, plan = plan, notice = notice))
}
