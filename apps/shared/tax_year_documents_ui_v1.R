# Karte "Unterlagen des Jahres": Report, Rechenblaetter und die hinterlegten Auszuege als ein Archiv laden.
#
# Festlegung (13.10.2026): Die Dokumente fuer die Steuer sollen sich zusammen mit dem Report laden lassen; ins Archiv
# gehoert alles Relevante - auch Lueckenliste und Rechenblaetter -, getrennt in Ordnern. Die Karte erstellt Report und
# Rechenblaetter selbst (mit den Anmerkungen der Reportkarte), laesst das Archiv bauen und sagt, was darin liegt und
# was fehlt. Sie schreibt nichts in den Datenraum: Das Archiv entsteht in einem Zwischenverzeichnis der Sitzung.
# Braucht simple_tax_report_pdf_v1.R (PDF des Reports).
tax_year_documents_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- rev(seq.int(2020L, max(2020L, as.integer(current_year))))
  shiny::tagList(
    shiny::p(class = "pl-section-copy",
      "Ein Archiv (ZIP) mit getrennten Ordnern: Steuerreport · Rechenblätter (eigene Modellrechnung) · hinterlegte Original-Auszüge und Belege mit Inhaltsverzeichnis · Lückenliste zur eigenen Kontrolle."),
    portelyra_note_v1(title = "Was im Archiv liegt", id = "tax-year-documents",
      "Bei den Auszügen liegen die der Konten des Reports und die Belege zur Anschaffung der im Jahr verbrauchten Lots, auch aus früheren Jahren. Zur Modellrechnung gehören die Jahresrechnung und der Steuerreport in ausführlicher Fassung. Was Sie weitergeben, entscheiden Sie je Ordner.",
      "Report, Rechenblätter und Jahresrechnung werden dafür neu erstellt; das dauert je nach Bestand bis zu drei Minuten. Die Anmerkungen kommen aus dem Feld der Karte „Steuerreport“."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("year_documents_year", "Steuerjahr", choices = as.character(years),
        selected = as.character(if (length(years) > 1L) years[[2L]] else years[[1L]])),
      shiny::checkboxGroupInput("year_documents_kinds", "Assetklassen und Erträge", choices = tax_year_documents_asset_types_v1(), selected = "crypto", inline = TRUE),
      shiny::radioButtons("year_documents_scope", "Auszüge welcher Konten", choices = tax_year_documents_scopes_v1(), selected = "report_accounts")),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("year_documents_build", "Unterlagen zusammenstellen", class = "btn-primary")),
    shiny::uiOutput("year_documents_state"))
}
tax_year_documents_error_text_v1 <- function(code) switch(as.character(code),
  tax_year_documents_input_invalid = "Bitte ein Steuerjahr und mindestens eine Assetklasse oder die Zinsen wählen.",
  tax_year_documents_report_failed = "Der Steuerreport ließ sich nicht erstellen: Buchungsbestand, FIFO-Stand oder Belegangaben waren nicht lesbar.",
  tax_year_documents_target_invalid = "Das Archiv ließ sich nicht schreiben.",
  "Die Unterlagen ließen sich nicht zusammenstellen: Auszugsablage oder Buchungsbestand waren nicht lesbar, oder eine hinterlegte Datei gleicht ihrem Prüfwert nicht mehr.")
tax_year_documents_size_text_v1 <- function(bytes) {
  value <- suppressWarnings(as.numeric(bytes))
  if (length(value) != 1L || is.na(value)) return("–")
  if (value < 1024 * 1024) sprintf("%s KB", format(max(1, round(value / 1024)), big.mark = ".", decimal.mark = ","))
  else sprintf("%s MB", format(round(value / 1024 / 1024, 1), nsmall = 1, big.mark = ".", decimal.mark = ","))
}
# Was im Archiv liegt, in einem Satz; und was fehlt, je Art einmal.
tax_year_documents_content_text_v1 <- function(result, sheets_included, statement_included = FALSE, detailed_included = FALSE) paste0(
  "Steuerreport (PDF und Tabelle) · ", if (isTRUE(sheets_included)) "Rechenblätter (Tabelle)" else "keine Rechenblätter",
  if (isTRUE(statement_included)) " · Jahresrechnung (Tabelle)" else "", if (isTRUE(detailed_included)) " · ausführliche Fassung (PDF)" else "",
  sprintf(" · %d hinterlegte Datei(en) aus %d Dokument(en) für %d Konto/Konten · Archiv %s", as.integer(result$statement_file_count),
    as.integer(result$statement_document_count), as.integer(result$account_count), tax_year_documents_size_text_v1(result$archive_bytes)))
tax_year_documents_gap_lines_v1 <- function(result) {
  count <- function(name) { value <- suppressWarnings(as.integer(result[[name]])); if (length(value) != 1L || is.na(value)) 0L else value }
  c(
    if (count("open_month_count") > 0L) sprintf("%d Monat(e) des Jahres mit Bewegung ohne hinterlegten Auszug", count("open_month_count")),
    if (count("unconfirmed_month_count") > 0L) sprintf("%d Monat(e) des Jahres nur unbestätigt belegt", count("unconfirmed_month_count")),
    if (count("not_available_month_count") > 0L) sprintf("%d Monat(e) des Jahres als „nicht mehr vorhanden“ erklärt", count("not_available_month_count")),
    if (count("acquisition_open_month_count") > 0L) sprintf("%d Anschaffungsmonat(e) verbrauchter Lots ohne Auszug", count("acquisition_open_month_count")),
    if (count("acquisition_unconfirmed_month_count") > 0L) sprintf("%d Anschaffungsmonat(e) nur unbestätigt belegt", count("acquisition_unconfirmed_month_count")),
    if (count("acquisition_not_available_month_count") > 0L) sprintf("%d Anschaffungsmonat(e) als „nicht mehr vorhanden“ erklärt", count("acquisition_not_available_month_count")))
}
# `services`: list(documents, report, sheets, statement, detailed_render) - die Dienste der Tax-App; `statement` (Jahresrechnung) und
# `detailed_render` (ausfuehrliche Fassung als PDF) sind wahlweise. `notes`: die Anmerkungen der Reportkarte.
tax_year_documents_card_server_v1 <- function(input, output, services, notes = function() character(),
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  bundle <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL)
  work <- NULL
  discard <- function() { if (!is.null(work)) unlink(work, recursive = TRUE, force = TRUE); work <<- NULL }
  domain <- shiny::getDefaultReactiveDomain()
  if (!is.null(domain)) domain$onSessionEnded(discard)
  write_text <- function(path, text) { writeBin(charToRaw(enc2utf8(text)), path); path }
  shiny::observeEvent(input$year_documents_build, {
    failure(NULL); bundle(NULL); discard()
    year <- input$year_documents_year; kinds <- as.character(input$year_documents_kinds); scope <- input$year_documents_scope
    if (is.null(services$documents) || is.null(services$report)) { failure("tax_year_documents_source_invalid"); return() }
    if (!length(kinds)) { failure("tax_year_documents_input_invalid"); return() }
    at <- now_utc()
    remarks <- tryCatch(as.character(notes()), error = function(error) character())
    report <- tryCatch(services$report$build(year, kinds, remarks, at), error = function(error) NULL)
    if (is.null(report)) { failure("tax_year_documents_report_failed"); return() }
    if (!identical(report$model$status, "ready")) { bundle(list(status = report$model$status, tax_year = year)); return() }
    work <<- tempfile("unterlagen-"); dir.create(work, mode = "0700")
    label <- paste(unlist(report$model$asset_types), collapse = "-")
    built <- tryCatch({
      pdf <- file.path(work, sprintf("steuerreport-%s-einfach-%s.pdf", report$model$tax_year, label))
      simple_tax_report_pdf_v1(report$model, pdf, report$generated_at_utc, report$method_lines, report$notes)
      attachments <- list(list(section = "report", name = basename(pdf), path = pdf),
        list(section = "report", name = sprintf("steuerreport-%s-einfach-%s.csv", report$model$tax_year, label),
          path = write_text(file.path(work, sprintf("steuerreport-%s-einfach-%s.csv", report$model$tax_year, label)), report$csv)))
      # Die Rechenblaetter sind Beigabe: Lassen sie sich nicht erstellen, entsteht das Archiv ohne sie und sagt es.
      sheets <- if (is.null(services$sheets)) NULL else tryCatch(services$sheets$build(year, kinds, at), error = function(error) NULL)
      sheets_included <- is.list(sheets) && identical(sheets$model$status, "ready") && length(sheets$model$sheets) > 0L
      if (sheets_included) {
        name <- sprintf("rechenblaetter-%s-%s.csv", sheets$model$tax_year, paste(unlist(sheets$model$asset_types), collapse = "-"))
        attachments[[length(attachments) + 1L]] <- list(section = "sheets", name = name, path = write_text(file.path(work, name), sheets$csv))
      }
      # Die Jahresrechnung und die ausfuehrliche Fassung gehoeren zur Modellrechnung; wie die Rechenblaetter sind sie Beigabe.
      statement <- if (is.null(services$statement)) NULL else tryCatch(services$statement$build(year, at), error = function(error) NULL)
      statement_included <- is.list(statement) && identical(statement$model$status, "ready") && !is.null(statement$csv)
      if (statement_included) {
        name <- sprintf("jahresrechnung-%s.csv", statement$model$tax_year)
        attachments[[length(attachments) + 1L]] <- list(section = "sheets", name = name, path = write_text(file.path(work, name), statement$csv))
      }
      detailed_included <- FALSE
      if (is.function(services$detailed_render)) {
        name <- sprintf("steuerreport-%s-ausfuehrlich-%s.pdf", report$model$tax_year, label)
        detailed_included <- isTRUE(tryCatch({
          services$detailed_render(report, if (sheets_included) sheets$model else NULL, if (statement_included) statement$model else NULL, file.path(work, name), at)
          file.exists(file.path(work, name))
        }, error = function(error) FALSE))
        if (detailed_included) attachments[[length(attachments) + 1L]] <- list(section = "sheets", name = name, path = file.path(work, name))
      }
      target <- file.path(work, sprintf("unterlagen-%s.zip", report$model$tax_year))
      result <- services$documents$build(year, kinds, scope, attachments, target, at)
      list(status = result$status, tax_year = report$model$tax_year, result = result, path = target, sheets_included = sheets_included,
        sheet_count = if (sheets_included) length(sheets$model$sheets) else 0L, statement_included = statement_included, detailed_included = detailed_included)
    }, spot_tax_year_documents_error_v1 = function(error) error$code, error = function(error) "tax_year_documents_source_invalid")
    if (is.character(built)) { discard(); failure(built) } else bundle(built)
  })
  output$year_documents_state <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Unterlagen nicht zusammengestellt", tax_year_documents_error_text_v1(failure()), tone = "error"))
    built <- bundle()
    if (is.null(built)) return(shiny::p(class = "pl-field-hint", "Noch keine Unterlagen zusammengestellt."))
    if (!identical(built$status, "ready")) return(portelyra_status_panel(
      if (identical(built$status, "fifo_state_stale")) "FIFO-Stand nicht aktuell" else "Kein FIFO-Stand vorhanden",
      "Welche Auszüge dazugehören, sagt der Lot-Nachweis des Buchungsbestands. Bitte in der App „Daten“ den Bestand fortschreiben und danach neu zusammenstellen.", tone = "warning"))
    gaps <- tax_year_documents_gap_lines_v1(built$result)
    shiny::tagList(
      portelyra_status_panel(sprintf("Unterlagen %s zusammengestellt", built$tax_year),
        tax_year_documents_content_text_v1(built$result, built$sheets_included, built$statement_included, built$detailed_included), tone = "positive"),
      if (!isTRUE(built$sheets_included)) portelyra_status_panel("Ohne Rechenblätter",
        "Für die Auswahl gibt es keine Rechenblätter, oder sie ließen sich nicht erstellen. Das Archiv enthält keine Tabelle dazu.", tone = "neutral"),
      if (as.integer(built$result$statement_file_count) == 0L) portelyra_status_panel("Keine Auszüge hinterlegt",
        "Für die Konten der Auswahl liegt nichts in der Auszugsablage. Hinterlegen in Daten → „2. Stammdaten“ → „Auszüge und Belege je Konto“.", tone = "warning"),
      if (length(gaps)) portelyra_status_panel("Was den Unterlagen fehlt",
        paste0(paste(gaps, collapse = " · "), ". Die Monate stehen einzeln in 4_Eigene_Kontrolle/Lueckenliste.csv."), tone = "warning"),
      shiny::div(class = "pl-editor-actions", shiny::downloadButton("year_documents_zip", "Archiv laden (ZIP)", class = "btn-default")))
  })
  output$year_documents_zip <- shiny::downloadHandler(
    filename = function() { built <- bundle(); sprintf("unterlagen-%s.zip", if (is.null(built)) "leer" else built$tax_year) },
    contentType = "application/zip",
    content = function(file) {
      built <- bundle()
      if (is.null(built) || !identical(built$status, "ready") || !file.exists(built$path)) stop("tax_year_documents_not_built", call. = FALSE)
      if (!file.copy(built$path, file, overwrite = TRUE)) stop("tax_year_documents_not_built", call. = FALSE)
    })
  invisible(list(bundle = bundle, failure = failure))
}
