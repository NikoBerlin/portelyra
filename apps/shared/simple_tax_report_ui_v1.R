# Karte "Steuerreport - einfache Fassung": Jahr und Assetklassen waehlen, Report erstellen, als Tabelle und PDF laden.
# Die Karte rechnet nichts; sie zeigt, was der Report enthaelt und was ihm fehlt.
simple_tax_report_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- rev(seq.int(2020L, max(2020L, as.integer(current_year))))
  shiny::tagList(
    shiny::p(class = "pl-section-copy",
      "Dokumentiert Veräußerungen je verbrauchtem Lot, unentgeltliche Abgänge, Erträge, Umschichtungen und Bestände je Konto – mit Kennungen, Haltedauer und Jahresfrist."),
    # Lesart und Bedienung im Kaestchen (#507, Variante A).
    portelyra_note_v1(title = "So lesen Sie den Report", id = "tax-simple-report",
      "Mit dem Häkchen „Cash (Zinsen)“ kommen die Zinsgutschriften der Cash-Konten dazu, je Gutschrift und als Summe je Konto. Es wird keine Steuer berechnet und keine Freigrenze angewandt.",
      "Ausführliche Fassung: der Report, dahinter die Jahresrechnung und je Ereignis das Rechenblatt – ein PDF. Sie rechnet dafür alle Jahre ab 2020; das dauert bis zu drei Minuten. Die Jahresrechnung gilt für das ganze Jahr, auch bei einer Auswahl."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("simple_report_year", "Steuerjahr", choices = as.character(years),
        selected = as.character(if (length(years) > 1L) years[[2L]] else years[[1L]])),
      # Alle Klassen vorausgewaehlt (Endabnahme 19.11.2026): mit nur „Krypto“ fehlten Dividenden und Zinsen scheinbar.
      shiny::checkboxGroupInput("simple_report_kinds", "Assetklassen", choices = simple_tax_report_asset_types_v1(),
                                selected = unname(simple_tax_report_asset_types_v1()), inline = TRUE),
      shiny::p(class = "pl-field-hint", paste("Für das Finanzamt nur die Klassen wählen, die der Report belegen soll. Kapitalerträge belegt die",
                                              "Jahressteuerbescheinigung Ihrer Bank."))),
    # Ein Report fuer eine Auswahl einzelner Konten oder Vermoegenswerte (#433); leer heisst: alle.
    shiny::div(class = "pl-form-grid",
      shiny::selectizeInput("simple_report_accounts", "Nur diese Konten (leer = alle)", choices = NULL, multiple = TRUE,
        options = list(placeholder = "alle Konten")),
      shiny::selectizeInput("simple_report_assets", "Nur diese Vermögenswerte (leer = alle)", choices = NULL, multiple = TRUE,
        options = list(placeholder = "alle Vermögenswerte der gewählten Klassen"))),
    # Das Feld ist eine Ausgabe des Servers: Es kommt mit den festen Hinweisen des Datenraums vorbelegt.
    shiny::uiOutput("simple_report_notes_field"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("simple_report_build", "Report erstellen", class = "btn-primary"),
      shiny::actionButton("simple_report_detailed", "Ausführliche Fassung erstellen", class = "btn-default")),
    shiny::uiOutput("simple_report_state"),
    shiny::uiOutput("simple_report_detailed_state"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("simple_report_totals")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("simple_report_interest")))
}
simple_tax_report_error_text_v1 <- function(code) switch(as.character(code),
  simple_tax_report_input_invalid = "Bitte ein Steuerjahr und mindestens eine Assetklasse wählen.",
  "Der Report ließ sich nicht erstellen: Buchungsbestand, FIFO-Stand oder Belegangaben waren nicht lesbar.")
simple_tax_report_totals_frame_v1 <- function(model) {
  rows <- if (is.list(model)) model$totals else list()
  money <- simple_tax_report_money_v1
  data.frame(
    `Vermögenswert` = vapply(rows, function(item) as.character(item$asset_label), character(1L)),
    `Veräußerungen` = vapply(rows, function(item) as.integer(item$disposal_count), integer(1L)),
    `ohne Wert` = vapply(rows, function(item) as.integer(item$disposals_without_value), integer(1L)),
    `mit Tageswert` = vapply(rows, function(item) if (is.null(item$disposals_at_daily_value)) 0L else as.integer(item$disposals_at_daily_value), integer(1L)),
    `Erlöse nach Gebühr` = vapply(rows, function(item) money(item$proceeds_rounded), character(1L)),
    `Anschaffungskosten` = vapply(rows, function(item) money(item$basis_rounded), character(1L)),
    `GuV Brutto` = vapply(rows, function(item) money(item$gain_rounded), character(1L)),
    `innerhalb Jahresfrist` = vapply(rows, function(item) money(item$gain_within_period_rounded), character(1L)),
    `außerhalb Jahresfrist` = vapply(rows, function(item) money(item$gain_outside_period_rounded), character(1L)),
    `Erträge` = vapply(rows, function(item) as.integer(item$income_count), integer(1L)),
    `Erträge Brutto` = vapply(rows, function(item) money(item$income_rounded), character(1L)),
    `unentgeltlich` = vapply(rows, function(item) if (is.null(item$gratuitous_transfer_count)) 0L else as.integer(item$gratuitous_transfer_count), integer(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}
# Zinsen der Cash-Konten als Summe je Konto.
simple_tax_report_interest_frame_v1 <- function(model) {
  rows <- if (is.list(model)) model$interest_totals else list()
  data.frame(
    Institut = vapply(rows, function(item) if (is.null(item$institution_label)) "ohne Institutsangabe" else as.character(item$institution_label), character(1L)),
    Konto = vapply(rows, function(item) as.character(item$account_label), character(1L)),
    `Währung` = vapply(rows, function(item) as.character(item$currency), character(1L)),
    `Zinsgutschriften` = vapply(rows, function(item) as.integer(item$interest_count), integer(1L)),
    `Zinsertrag` = vapply(rows, function(item) simple_tax_report_money_v1(item$income_rounded), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}
# `detailed`: list(sheets = Rechenblatt-Dienst, statement = Dienst der Jahresrechnung, render = function(report, sheets, statement,
# file, at)) fuer die ausfuehrliche Fassung, oder NULL.
simple_tax_report_card_server_v1 <- function(input, output, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    detailed = NULL) {
  report <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL)
  detailed_built <- shiny::reactiveVal(NULL); detailed_failure <- shiny::reactiveVal(NULL)
  session <- shiny::getDefaultReactiveDomain()
  # Die Auswahl laedt von selbst, wenn sich die Klassen aendern: Konten mit Institut, Vermoegenswerte der Klassen.
  shiny::observeEvent(input$simple_report_kinds, {
    if (is.null(service) || !is.function(service$choices) || is.null(session)) return()
    kinds <- as.character(input$simple_report_kinds)
    choices <- if (length(kinds)) tryCatch(service$choices(kinds), error = function(error) NULL) else NULL
    if (is.null(choices)) return()
    named <- function(rows, describe) stats::setNames(vapply(rows, function(row) row$token, character(1L)), vapply(rows, describe, character(1L)))
    accounts <- named(choices$accounts, function(row) if (is.null(row$institution_label)) row$label else sprintf("%s (%s)", row$label, row$institution_label))
    assets <- named(choices$assets, function(row) row$label)
    shiny::updateSelectizeInput(session, "simple_report_accounts", choices = accounts, selected = intersect(as.character(input$simple_report_accounts), accounts))
    shiny::updateSelectizeInput(session, "simple_report_assets", choices = assets, selected = intersect(as.character(input$simple_report_assets), assets))
  }, ignoreNULL = FALSE)
  selection <- function() {
    chosen <- list(accounts = as.character(input$simple_report_accounts), assets = as.character(input$simple_report_assets))
    chosen <- chosen[lengths(chosen) > 0L]
    if (length(chosen)) chosen else NULL
  }
  build_report <- function(notes, at) {
    chosen <- selection()
    arguments <- c(list(input$simple_report_year, as.character(input$simple_report_kinds), notes, at), if (!is.null(chosen)) list(selection = chosen))
    if (is.null(service)) "simple_tax_report_source_invalid" else tryCatch(do.call(service$build, arguments),
      spot_simple_tax_report_error_v1 = function(error) error$code, error = function(error) "simple_tax_report_source_invalid")
  }
  # Feste Hinweise: einmal je Sitzung gelesen. Lassen sie sich nicht lesen, bleibt das Feld leer und sagt es.
  stored_notes <- shiny::reactive({
    if (is.null(service) || !is.function(service$read_notes)) return(character())
    tryCatch(service$read_notes(), error = function(error) structure(character(), unreadable = TRUE))
  })
  output$simple_report_notes_field <- shiny::renderUI({
    notes <- stored_notes()
    shiny::tagList(
      shiny::textAreaInput("simple_report_notes", "Anmerkungen – eine je Zeile, sie erscheinen im Report", value = paste(notes, collapse = "\n"),
        rows = max(3L, length(notes) + 1L), width = "100%"),
      shiny::p(class = "pl-field-hint", if (isTRUE(attr(notes, "unreadable"))) "Die festen Hinweise ließen sich nicht lesen; das Feld ist leer."
        else if (length(notes)) sprintf("%d fester Hinweis/feste Hinweise vorbelegt. Änderungen hier gelten nur für diesen Report.", length(notes))
        else "Keine festen Hinweise hinterlegt."))
  })
  shiny::observeEvent(input$simple_report_build, {
    failure(NULL)
    # Ist das Feld noch nicht im Browser angekommen, gelten die festen Hinweise - sie sollen auf keinem Report fehlen.
    notes <- if (is.null(input$simple_report_notes)) as.character(stored_notes()) else simple_tax_report_notes_v1(input$simple_report_notes)
    built <- build_report(notes, now_utc())
    if (is.character(built)) { report(NULL); failure(built) } else report(built)
  })
  # Ausfuehrliche Fassung: derselbe Report, dazu Rechenblaetter (mit derselben Auswahl) und die Jahresrechnung des Jahres.
  shiny::observeEvent(input$simple_report_detailed, {
    detailed_failure(NULL); detailed_built(NULL)
    if (is.null(detailed) || !is.function(detailed$render)) { detailed_failure("simple_tax_report_source_invalid"); return() }
    notes <- if (is.null(input$simple_report_notes)) as.character(stored_notes()) else simple_tax_report_notes_v1(input$simple_report_notes)
    at <- now_utc()
    built <- build_report(notes, at)
    if (is.character(built)) { detailed_failure(built); return() }
    chosen <- selection()
    sheets <- if (is.null(detailed$sheets)) NULL else tryCatch(do.call(detailed$sheets$build, c(list(input$simple_report_year, as.character(input$simple_report_kinds), at),
      if (!is.null(chosen)) list(selection = chosen)))$model, error = function(error) NULL)
    statement <- if (is.null(detailed$statement)) NULL else tryCatch(detailed$statement$build(input$simple_report_year, at)$model, error = function(error) NULL)
    detailed_built(list(report = built, sheets = sheets, statement = statement, at = at))
  })
  output$simple_report_detailed_state <- shiny::renderUI({
    if (!is.null(detailed_failure())) return(portelyra_status_panel("Ausführliche Fassung nicht erstellt", simple_tax_report_error_text_v1(detailed_failure()), tone = "error"))
    built <- detailed_built()
    if (is.null(built)) return(NULL)
    missing <- c(if (!is.list(built$statement) || !identical(built$statement$status, "ready")) "die Jahresrechnung",
      if (!is.list(built$sheets) || !identical(built$sheets$status, "ready")) "die Rechenblätter")
    shiny::tagList(
      portelyra_status_panel(sprintf("Ausführliche Fassung %s erstellt", built$report$model$tax_year),
        if (length(missing)) paste("Ohne", paste(missing, collapse = " und "), "– sie ließen sich nicht erstellen; das Dokument sagt es an ihrer Stelle.")
        else sprintf("Report, Jahresrechnung und %d Rechenblätter in einem PDF.", length(built$sheets$sheets)), tone = if (length(missing)) "warning" else "positive"),
      shiny::div(class = "pl-editor-actions", shiny::downloadButton("simple_report_detailed_pdf", "Ausführliche Fassung laden (PDF)", class = "btn-default")))
  })
  output$simple_report_detailed_pdf <- shiny::downloadHandler(
    filename = function() { built <- detailed_built(); sprintf("steuerreport-%s-ausfuehrlich-%s.pdf", if (is.null(built)) "leer" else built$report$model$tax_year,
      if (is.null(built)) "x" else paste(unlist(built$report$model$asset_types), collapse = "-")) },
    contentType = "application/pdf",
    content = function(file) {
      built <- detailed_built(); if (is.null(built)) stop("simple_tax_report_not_built", call. = FALSE)
      detailed$render(built$report, built$sheets, built$statement, file, built$at)
    })
  output$simple_report_state <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Report nicht erstellt", simple_tax_report_error_text_v1(failure()), tone = "error"))
    built <- report()
    if (is.null(built)) return(shiny::p(class = "pl-field-hint", "Noch kein Report erstellt."))
    model <- built$model; summary <- simple_tax_report_summary_v1(model)
    if (!identical(model$status, "ready")) return(portelyra_status_panel(
      if (identical(model$status, "fifo_state_stale")) "FIFO-Stand nicht aktuell" else "Kein FIFO-Stand vorhanden",
      paste("Der Lot-Nachweis gehört zum Buchungsbestand, wie er zuletzt fortgeschrieben wurde.",
        "Bitte in der App „Daten“ den Bestand fortschreiben und den Report danach neu erstellen – bis dahin bleibt er leer."), tone = "warning"))
    days <- sort(names(summary$holding_rows))
    interest <- if (summary$interest_count > 0L || "cash" %in% unlist(model$asset_types)) sprintf("%d Zinsgutschriften auf %d Konten",
      summary$interest_count, summary$interest_account_count) else NULL
    # Ein Report nur ueber Zinsen kennt weder Lots noch Bestaende; dort steht nur, was er enthaelt.
    if (!isTRUE(summary$ledger_kinds)) return(shiny::tagList(
      portelyra_status_panel(sprintf("Report %s erstellt", model$tax_year), interest, tone = "positive"),
      shiny::div(class = "pl-editor-actions",
        shiny::downloadButton("simple_report_csv", "Tabelle laden (CSV)", class = "btn-default"),
        shiny::downloadButton("simple_report_pdf", "PDF laden", class = "btn-default"))))
    gaps <- c(
      if (summary$without_value_count > 0L) sprintf("%d Abgang/Abgänge ohne Wert – weder am Abgang eingetragen noch ein Kurs für den Tag vorhanden; dort ist kein Gewinn ausgewiesen", summary$without_value_count),
      if (summary$missing_identifier_count > 0L) sprintf("%d gezeigte Buchung(en) ohne Transaktions-ID – aufgelistet im letzten Abschnitt des Reports", summary$missing_identifier_count))
    shiny::tagList(
      portelyra_status_panel(sprintf("Report %s erstellt", model$tax_year), sprintf(
        "%d Veräußerungen (%d Lot-Zeilen) · %d unentgeltliche Abgänge (keine Veräußerung) · %d Erträge · %d Umschichtungen · %d Vorgänge mit Gebühr in Stück · Bestände: %s",
        summary$disposal_count, summary$lot_row_count, summary$gratuitous_count, summary$income_count, summary$transfer_count, summary$asset_fee_event_count,
        paste(c(paste(sprintf("%d Lots zum %s", summary$holding_rows[days], if (exists("pl_day_v1", mode = "function")) pl_day_v1(days) else days),
                  collapse = ", "), interest), collapse = " · ")), tone = "positive"),
      if (summary$daily_value_count > 0L) portelyra_status_panel("Abgänge mit Tageswert angesetzt", sprintf(
        "%d Abgang/Abgänge tragen Stückzahl mal Tageswert der Kursquelle als Erlös. Ein in der App „Daten“ am Abgang eingetragener Wert geht vor (Buchung wählen, Bereich „Beleg“).",
        summary$daily_value_count)),
      # Ohne Zweck laesst sich ein Abgang nicht einordnen; der Report fuehrt ihn dann vorsorglich als Veraeusserung.
      if (summary$unclassified_count > 0L) portelyra_status_panel("Abgänge ohne eingeordneten Zweck", sprintf(
        "%d Abgang/Abgänge tragen keinen Zweck und stehen vorsorglich als Veräußerung im Report. Den Zweck in der App „Daten“ an der Buchung eintragen (Feld „Anlass“): Zahlung und Schuldentilgung sind Veräußerungen, Spende, Schenkung und Erbschaft nicht.",
        summary$unclassified_count), tone = "warning"),
      if (length(gaps)) portelyra_status_panel("Was dem Report fehlt", paste(gaps, collapse = " · "), tone = "warning"),
      shiny::div(class = "pl-editor-actions",
        shiny::downloadButton("simple_report_csv", "Tabelle laden (CSV)", class = "btn-default"),
        shiny::downloadButton("simple_report_pdf", "PDF laden", class = "btn-default")))
  })
  output$simple_report_totals <- shiny::renderTable({
    built <- report()
    # Ein Report nur ueber Zinsen hat keine Summen je Vermoegenswert; eine leere Tabelle saehe aus wie ein Fehler.
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$totals)) return(NULL)
    simple_tax_report_totals_frame_v1(built$model)
  }, striped = TRUE, bordered = TRUE)
  output$simple_report_interest <- shiny::renderTable({
    built <- report()
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$interest_totals)) return(NULL)
    simple_tax_report_interest_frame_v1(built$model)
  }, striped = TRUE, bordered = TRUE)
  file_name <- function(extension) {
    built <- report()
    sprintf("steuerreport-%s-einfach-%s.%s", if (is.null(built)) "leer" else built$model$tax_year,
      if (is.null(built)) "x" else paste(unlist(built$model$asset_types), collapse = "-"), extension)
  }
  output$simple_report_csv <- shiny::downloadHandler(filename = function() file_name("csv"), contentType = "text/csv; charset=utf-8",
    content = function(file) {
      built <- report(); if (is.null(built)) stop("simple_tax_report_not_built", call. = FALSE)
      writeBin(charToRaw(enc2utf8(built$csv)), file)
    })
  output$simple_report_pdf <- shiny::downloadHandler(filename = function() file_name("pdf"), contentType = "application/pdf",
    content = function(file) {
      built <- report(); if (is.null(built)) stop("simple_tax_report_not_built", call. = FALSE)
      simple_tax_report_pdf_v1(built$model, file, built$generated_at_utc, built$method_lines, built$notes)
    })
  # `notes` nennt die Anmerkungen, wie sie gerade im Feld stehen - fuer Karten, die denselben Report ein zweites Mal brauchen.
  invisible(list(report = report, failure = failure,
    notes = function() if (is.null(input$simple_report_notes)) as.character(stored_notes()) else simple_tax_report_notes_v1(input$simple_report_notes)))
}
