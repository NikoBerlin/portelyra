# Steuerpflichtige Betraege laut Beleg (#459) und Bruttozinsen (#465): die Ertraegnisaufstellung eines Instituts mit Leser, in Data ->
# "4. Steuer" unter den Vorabpauschalen.
#
# Festlegung (04.11.2026): Uebernommen wird der Kapitalertrag je Posten (nach Teilfreistellung, vor Freistellungsauftrag und
# Verlustverrechnung), nur bis 1 Euro Abweichung zur eigenen Rechnung; groessere Abweichungen sind ein Befund. Die Steuer
# rechnet Portelyra weiter selbst - der Freibetrag verwaessert die Projektion nicht. Zinsen hebt die Karte auf brutto, wo sie
# netto gebucht sind; Bewegungen bucht sie nicht. Vorschau -> Haekchen -> Uebernehmen, gebunden an genau diese Vorschau.
data_tax_document_abort_v1 <- function(code) {
  # Codes des Leser-Plugins (rc.377) bleiben erhalten, damit die Meldung den genauen Grund nennt.
  if (!is.character(code) || length(code) != 1L || !grepl("^(tax_document|statement_reader)_[a-z_]+$", code)) code <- "tax_document_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_tax_document_error_v1", "error", "condition")))
}
data_tax_document_error_text_v1 <- function(code) {
  reader <- if (exists("data_statement_reader_message_v1", mode = "function"))
    data_statement_reader_message_v1(as.character(code), "Erträgnisaufstellung", "Es wurde nichts übernommen.") else NULL
  if (!is.null(reader)) return(paste0(reader$title, ": ", reader$copy))
  data_tax_document_error_text_fixed_v1(code)
}
data_tax_document_error_text_fixed_v1 <- function(code) switch(as.character(code),
  tax_document_source_invalid = "Das Dokument ist keine Erträgnisaufstellung, die ein Leser kennt (oder ihr Einzelnachweis fehlt).",
  tax_document_unreadable = "Das PDF ließ sich nicht lesen (pdftotext).",
  tax_document_preview_stale = "Seit der Prüfung hat sich etwas geändert – bitte erneut prüfen.",
  tax_document_confirmation_required = "Bitte zuerst das Häkchen setzen.",
  tax_document_input_invalid = "Bitte ein Dokument aus der Ablage wählen.",
  "Buchungsbestand, Rechenblätter oder der Speicher der Belegangaben ließen sich nicht lesen. Buchungen sind davon nicht berührt.")
new_data_tax_document_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_tax_document_import.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else NULL
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_tax_document_abort_v1("tax_document_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_tax_document_abort_v1(if (is.null(parsed$code)) "tax_document_store_invalid" else parsed$code)
    parsed$result
  }
  token_valid <- function(token) is.character(token) && length(token) == 1L && grepl("^txf_[a-f0-9]{24}$", token)
  structure(list(
    contract_version = "data_tax_document_service_v1",
    documents = function() {
      result <- run("documents", list())
      if (!is.list(result) || !identical(result$contract_version, "tax_document_documents_v1") || isTRUE(result$canonical_write) ||
          !all(vapply(result$documents, function(row) token_valid(row$token), logical(1L))))
        data_tax_document_abort_v1("tax_document_store_invalid")
      result$documents
    },
    preview = function(token) {
      if (!token_valid(token)) data_tax_document_abort_v1("tax_document_input_invalid")
      result <- run("preview", list(token = token))
      if (!is.list(result) || !identical(result$contract_version, "tax_document_import_v1") || isTRUE(result$canonical_write) || !is.null(result[["_internal"]]))
        data_tax_document_abort_v1("tax_document_store_invalid")
      result
    },
    # reader_check_acknowledged (rc.380): Bestaetigung fuer den Leser, solange er in diesem Portfolio nicht an Ihren Belegen geprueft ist.
    apply = function(token, preview_fingerprint, recorded_at_utc, confirmed, reader_check_acknowledged = FALSE) {
      if (!isTRUE(confirmed)) data_tax_document_abort_v1("tax_document_confirmation_required")
      if (!token_valid(token) || !is.character(preview_fingerprint) || !grepl("^[a-f0-9]{64}$", preview_fingerprint)) data_tax_document_abort_v1("tax_document_input_invalid")
      result <- run("apply", list(token = token, preview_fingerprint = preview_fingerprint, recorded_at_utc = recorded_at_utc, confirmed = TRUE,
                                  reader_check_acknowledged = isTRUE(reader_check_acknowledged)))
      if (!is.list(result) || !identical(result$status, "recorded") || isTRUE(result$canonical_write)) data_tax_document_abort_v1("tax_document_store_invalid")
      result
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_tax_document_service_v1", "list"))
}

DATA_TAX_DOCUMENT_STATUS_V1 <- c(take = "übernehmen", already = "schon übernommen", finding = "Befund – über 1 € Abweichung, nicht übernommen",
  replacement_base = "Ersatzbemessungsgrundlage – nicht übernommen", unmatched = "keine passende Buchung", unclear = "Zeile nicht eindeutig",
  own_missing = "eigene Rechnung fehlt")
DATA_TAX_DOCUMENT_KINDS_V1 <- c(sale = "Verkauf", fund = "Fondsverkauf", dividend = "Dividende")

data_tax_document_card_ui_v1 <- function() {
  portelyra_card("Steuerpflichtige Beträge aus der Erträgnisaufstellung", help = "app-data#steuer", class = "pl-write-boundary",
    copy = "Die Erträgnisaufstellung der Bank nennt je Verkauf und Dividende den Kapitalertrag auf den Cent. Portelyra übernimmt ihn statt der eigenen Rechnung und hebt netto gebuchte Zinsen auf brutto.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-tax-document", paste(
      "Übernommen wird der Kapitalertrag vor Freistellungsauftrag und Verlustverrechnung (nach Teilfreistellung); die Steuer rechnet Portelyra weiter selbst.",
      "Weicht ein Posten um mehr als 1 € von der eigenen Rechnung ab, bleibt die eigene Rechnung – die Vorschau nennt ihn als Befund, etwa bei einer Ersatzbemessungsgrundlage nach einem Übertrag ohne Anschaffungsdaten.",
      "Die Summe der Posten muss Zeile 7 des Summennachweises ergeben, sonst übernimmt die Karte nichts. Die Erträgnisaufstellung liegt in der Ablage bei den Konten des Instituts; lesbar sind die Aufstellungen, die ein Leser-Plugin kennt.",
      "Angeboten werden nur Dokumente der Art „Erträgnisaufstellung“. Liegt sie unter einer anderen Art, in 2. Stammdaten → Ablage mit „Art ändern“ umstellen.")),
    shiny::div(class = "pl-field-row",
      shiny::selectInput("data_tax_document_file", "Erträgnisaufstellung aus der Ablage", choices = c("Bitte lesen" = ""), width = "420px"),
      shiny::actionButton("data_tax_document_read", "Ablage lesen", class = "btn-default"),
      shiny::actionButton("data_tax_document_preview", "Prüfen", class = "btn-default")),
    shiny::uiOutput("data_tax_document_state"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("data_tax_document_rows")),
    shiny::checkboxInput("data_tax_document_confirm", "Ja, die Beträge mit „übernehmen“ übernehmen und netto gebuchte Zinsen auf brutto heben", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_tax_document_apply", "Übernehmen", class = "btn-primary")),
    shiny::uiOutput("data_tax_document_notice"))
}

# Die Vorschau als Tabelle: je Posten Bank, eigene Rechnung, Abweichung und was geschieht.
data_tax_document_frame_v1 <- function(preview) {
  rows <- if (is.list(preview)) preview$rows else list()
  if (!length(rows)) return(data.frame())
  money <- function(value) if (is.null(value)) "–" else pl_amount_v1(value, "EUR", 2L)
  data.frame(
    Zufluss = vapply(rows, function(row) pl_day_v1(row$inflow_date), character(1L)),
    Art = vapply(rows, function(row) { kind <- DATA_TAX_DOCUMENT_KINDS_V1[as.character(row$kind)]; if (is.na(kind)) "Posten" else unname(kind) }, character(1L)),
    Wertpapier = vapply(rows, function(row) if (is.null(row$security_name)) "–" else as.character(row$security_name), character(1L)),
    Konto = vapply(rows, function(row) if (is.null(row$account_label)) "–" else as.character(row$account_label), character(1L)),
    `laut Bank` = vapply(rows, function(row) money(row$bank_taxable_decimal), character(1L)),
    `eigene Rechnung` = vapply(rows, function(row) money(row$own_taxable_decimal), character(1L)),
    Abweichung = vapply(rows, function(row) money(row$difference_decimal), character(1L)),
    Ergebnis = vapply(rows, function(row) { label <- DATA_TAX_DOCUMENT_STATUS_V1[as.character(row$status)]; if (is.na(label)) as.character(row$status) else unname(label) }, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_tax_document_summary_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  if (!identical(preview$status, "ready"))
    return(list(tone = "warning", title = "Nichts zu übernehmen", copy = paste0("Erträgnisaufstellung ", if (is.null(preview$tax_year)) "" else preview$tax_year,
      ": Die Summe der Posten ergibt nicht Zeile 7 des Summennachweises – die Karte übernimmt nichts.")))
  counts <- preview$counts; n <- function(name) if (is.null(counts[[name]])) 0L else as.integer(counts[[name]])
  interest <- preview$interest
  zinsen <- if (is.null(interest$posting_count) || !as.integer(interest$posting_count)) "" else sprintf(" · Zinsen: %d Gutschriften, %d schon brutto gebucht, %d auf brutto zu heben%s",
    as.integer(interest$posting_count), as.integer(interest$gross_booked_count), as.integer(interest$correction_count),
    if (as.integer(interest$unmatched_count)) sprintf(", %d ohne gebuchten Zins", as.integer(interest$unmatched_count)) else "")
  list(tone = if (n("finding") + n("replacement_base") + n("unmatched") + n("unclear") + n("own_missing")) "warning" else "neutral",
       title = sprintf("Erträgnisaufstellung %s – Gegenprobe Zeile 7 stimmt", preview$tax_year),
       copy = sprintf("%d zu übernehmen, %d schon übernommen, %d Befunde über 1 €, %d ohne passende Buchung%s.", n("take"), n("already"),
                      n("finding") + n("replacement_base"), n("unmatched") + n("unclear") + n("own_missing"), zinsen))
}

data_tax_document_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  preview <- shiny::reactiveVal(NULL); notice <- shiny::reactiveVal(NULL)
  read <- function() {
    if (is.null(service)) { notice(list(tone = "warning", title = "Nicht verfügbar", copy = data_tax_document_error_text_v1("tax_document_store_invalid"))); return(invisible(NULL)) }
    documents <- tryCatch(service$documents(), error = function(error) { notice(list(tone = "warning", title = "Ablage nicht lesbar", copy = data_tax_document_error_text_v1(error$code))); NULL })
    if (is.null(documents)) return(invisible(NULL))
    choices <- if (!length(documents)) c("Keine Erträgnisaufstellung in der Ablage (nur Institute mit passendem Leser)" = "") else
      stats::setNames(vapply(documents, function(row) row$token, character(1L)),
                      vapply(documents, function(row) paste0(if (is.null(row$year)) "–" else row$year, " · ", row$name), character(1L)))
    # Die gewaehlte Aufstellung bleibt gewaehlt, solange es sie gibt (#536): Die Liste liest sich bei jedem Oeffnen des Reiters neu.
    current <- shiny::isolate(input$data_tax_document_file)
    shiny::updateSelectInput(session, "data_tax_document_file", choices = choices,
                             selected = if (is.character(current) && length(current) == 1L && current %in% choices) current else unname(choices[[1L]]))
    invisible(documents)
  }
  shiny::observeEvent(input$data_tax_document_read, { notice(NULL); read() }, ignoreInit = TRUE)
  # Eine andere Datei gilt als neue Pruefung: die alte Vorschau und das Haekchen fallen weg.
  shiny::observeEvent(input$data_tax_document_file, { preview(NULL); notice(NULL); shiny::updateCheckboxInput(session, "data_tax_document_confirm", value = FALSE) }, ignoreInit = TRUE)
  shiny::observeEvent(input$data_tax_document_preview, {
    notice(NULL); shiny::updateCheckboxInput(session, "data_tax_document_confirm", value = FALSE)
    token <- input$data_tax_document_file
    result <- tryCatch(service$preview(token), error = function(error) { notice(list(tone = "warning", title = "Nicht geprüft", copy = data_tax_document_error_text_v1(error$code))); NULL })
    preview(result)
  }, ignoreInit = TRUE)
  output$data_tax_document_state <- shiny::renderUI({
    current <- preview(); summary <- data_tax_document_summary_v1(current)
    if (is.null(summary)) return(NULL)
    # Pruefstand (rc.380): Hinweis und eigenes Haekchen, solange der Leser in diesem Portfolio nicht an Ihren Belegen geprueft ist.
    check <- if (is.list(current)) current$reader_check else NULL
    shiny::tagList(portelyra_status_panel(summary$title, summary$copy, tone = summary$tone),
      if (exists("data_statement_reader_check_panel_v1", mode = "function")) data_statement_reader_check_panel_v1(check),
      if (exists("data_statement_reader_check_ack_v1", mode = "function")) data_statement_reader_check_ack_v1("data_tax_document_reader_ack", check, "der Erträgnisaufstellung"))
  })
  output$data_tax_document_rows <- shiny::renderTable(data_tax_document_frame_v1(preview()), striped = TRUE, spacing = "xs")
  shiny::observeEvent(input$data_tax_document_apply, {
    current <- preview()
    if (is.null(current) || !identical(current$status, "ready")) { notice(list(tone = "warning", title = "Nicht übernommen", copy = "Bitte zuerst prüfen.")); return() }
    if (!isTRUE(input$data_tax_document_confirm)) { notice(list(tone = "warning", title = "Nicht übernommen", copy = data_tax_document_error_text_v1("tax_document_confirmation_required"))); return() }
    if (isTRUE(current$reader_check$acknowledgment_required) && !isTRUE(input$data_tax_document_reader_ack)) {
      notice(list(tone = "warning", title = "Nicht übernommen", copy = data_tax_document_error_text_v1("statement_reader_unchecked"))); return() }
    result <- tryCatch(service$apply(input$data_tax_document_file, current$preview_fingerprint, now_utc(), TRUE, isTRUE(input$data_tax_document_reader_ack)),
                       error = function(error) { notice(list(tone = "error", title = "Nicht übernommen", copy = data_tax_document_error_text_v1(error$code))); NULL })
    if (is.null(result)) return()
    preview(NULL); shiny::updateCheckboxInput(session, "data_tax_document_confirm", value = FALSE)
    notice(list(tone = "positive", title = "Übernommen", copy = sprintf(
      paste("%d Beträge laut Beleg übernommen, %d Zinsen auf brutto gehoben. Rechenblätter, Jahresrechnung und der ausführliche Steuerreport rechnen damit.",
            "Die Steuerprojektion je Ereignis aus dem Abschluss und die Netto-Sicht der Analyse ziehen beim nächsten „Alles aktualisieren“ nach.%s"),
      as.integer(result$taken_count), as.integer(result$corrected_interest_count),
      paste0(if (exists("data_statement_provenance_note_v1", mode = "function") && nzchar(note <- data_statement_provenance_note_v1(result$provenance_status))) paste0(" ", note) else "",
             if (exists("data_statement_reader_check_note_v1", mode = "function") && nzchar(note <- data_statement_reader_check_note_v1(result$reader_check_recorded))) paste0(" ", note) else ""))))
  }, ignoreInit = TRUE)
  output$data_tax_document_notice <- shiny::renderUI({ value <- notice(); if (is.null(value)) NULL else portelyra_status_panel(value$title, value$copy, tone = value$tone) })
  invisible(list(read = read, preview = preview, notice = notice))
}
