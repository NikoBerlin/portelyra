# Karte "Jahresrechnung" der Tax-App: Steuer eines Jahres mit Verrechnung, Freigrenzen, Freistellung und Verlusttoepfen.
#
# Festlegung (12./13.10.2026, #429): Neben dem Rechenblatt je Ereignis die Jahresrechnung - Ergebnis brutto,
# voraussichtliche Gesamtsteuer, Netto, Verbrauch und Verrechnung der Verlusttoepfe, Vortraege; abgleichbar mit der
# Abrechnung eines Instituts. Kapitalertraege je Institut, private Veraeusserungsgeschaefte und sonstige Einkuenfte ueber
# alle Institute (14.10.2026). Die Karte rechnet nichts selbst; sie setzt, was der Rechenkern liefert.
# Braucht tax_projection_cents_v1 und tax_projection_failure_text_v1 aus tax_projection_view_v1.R.
tax_annual_statement_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  # Ab 2016 (#496); 2016-2019 nur in Grundzuegen, die Ansicht sagt es dann ausdruecklich.
  years <- rev(seq.int(2016L, max(2020L, as.integer(current_year))))
  shiny::tagList(
    shiny::p(class = "pl-section-copy", "Die voraussichtliche Steuer eines Jahres, nach dem Regelmodul des Jahres."),
    portelyra_note_v1(title = "So rechnet die Jahresrechnung", id = "tax-annual-statement",
      "Kapitalerträge je Institut – mit Verrechnung, Verlusttopf, Freistellungsauftrag und Quellensteuer des Instituts –, private Veräußerungsgeschäfte und sonstige Einkünfte über alle Institute, mit Freigrenze und Verlustvortrag.",
      "Grundlage sind dieselben Ereignisse wie in den Rechenblättern: alle Assetklassen und die Zinsen der Cash-Konten. Modellrechnung, keine Rechtsberatung.",
      "Für die Verlusttöpfe rechnet sie alle Jahre ab 2020 nacheinander; das dauert bis zu anderthalb Minuten. Freistellungsaufträge, Quellensteuer und Verlusttöpfe je Institut stehen in Daten → „4. Steuer“.",
      "2016 bis 2019 führt das Regelmodul nur in Grundzügen (Jahreswerte, Jahresfrist, Rewards; Fonds vor 2018 nicht): Eine Jahresrechnung für diese Jahre rechnet ab 2016 und ist ausdrücklich nicht vollständig."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("annual_statement_year", "Steuerjahr", choices = as.character(years),
        selected = as.character(if (length(years) > 1L) years[[2L]] else years[[1L]]))),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("annual_statement_build", "Jahresrechnung erstellen", class = "btn-primary")),
    shiny::uiOutput("annual_statement_state"),
    shiny::uiOutput("annual_statement_view"))
}
tax_annual_statement_error_text_v1 <- function(code) switch(as.character(code),
  tax_annual_statement_input_invalid = "Bitte ein Steuerjahr ab 2016 wählen.",
  "Die Jahresrechnung ließ sich nicht erstellen: Buchungsbestand, FIFO-Stand, Steuereinstellungen, Angaben je Institut oder Regelmodul waren nicht lesbar.")
# Beträge mit Einheit (#529 Punkt 8); die Jahresrechnung führt Euro.
.tax_annual_money_v1 <- function(value) { shown <- tax_projection_cents_v1(value); if (is.na(shown)) "–" else paste(shown, "€") }
.tax_annual_origin_v1 <- function(code) switch(as.character(code), entered = "eingetragen", carried = "aus dem Vorjahr", "")
.tax_annual_pair_v1 <- function(equity, general) paste(.tax_annual_money_v1(equity), "/", .tax_annual_money_v1(general))
tax_annual_statement_overview_frame_v1 <- function(statement) data.frame(check.names = FALSE, stringsAsFactors = FALSE,
  Posten = c("Ergebnis brutto (Gewinne und Erträge abzüglich Verluste)", "Voraussichtliche Steuer", "Voraussichtlich netto",
    "Angerechnete Quellensteuer", "Freistellungsaufträge (genutzt / eingetragen)", "Ereignisse in der Rechnung", "Ereignisse ohne Steuerzahl (nicht enthalten)"),
  Wert = c(.tax_annual_money_v1(statement$economic_amount), .tax_annual_money_v1(statement$projected_annual_tax), .tax_annual_money_v1(statement$projected_net),
    .tax_annual_money_v1(statement$withholding_credit), paste(.tax_annual_money_v1(statement$allowance_used), "/", .tax_annual_money_v1(statement$allowance_available)),
    as.character(statement$event_count), as.character(statement$open_count)))
# Je Institut eine Zeile; wo Aktien und allgemeiner Topf getrennt laufen, stehen beide als "Aktien / allgemein".
tax_annual_statement_institution_frame_v1 <- function(statement) {
  rows <- if (is.list(statement$institutions)) statement$institutions else list()
  if (!length(rows)) return(data.frame())
  pick <- function(field) function(row) .tax_annual_pair_v1(row$capital_equity[[field]], row$capital_general[[field]])
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Institut = vapply(rows, function(row) as.character(row$institution_label), character(1L)),
    Ereignisse = vapply(rows, function(row) as.character(row$event_count), character(1L)),
    `Gewinne und Erträge (Aktien / allgemein)` = vapply(rows, pick("positive_contribution_decimal"), character(1L)),
    `Verluste (Aktien / allgemein)` = vapply(rows, pick("negative_contribution_decimal"), character(1L)),
    `Verlusttopf zum 1.1. (Aktien / allgemein)` = vapply(rows, function(row) {
      origin <- unique(Filter(nzchar, c(.tax_annual_origin_v1(row$opening_origin$capital_equity), .tax_annual_origin_v1(row$opening_origin$capital_general))))
      paste0(pick("opening_loss_carryforward_decimal")(row), if (length(origin)) paste0(" (", paste(origin, collapse = ", "), ")") else "")
    }, character(1L)),
    `Verlust verrechnet (Aktien / allgemein)` = vapply(rows, pick("used_loss_decimal"), character(1L)),
    `Freistellungsauftrag (genutzt / eingetragen)` = vapply(rows, function(row) paste(
      .tax_annual_money_v1(row$allowance_used), "/",
      .tax_annual_money_v1(row$allowance_available)), character(1L)),
    steuerpflichtig = vapply(rows, function(row) .tax_annual_money_v1(row$taxable_base), character(1L)),
    `Quellensteuer angerechnet` = vapply(rows, function(row) .tax_annual_money_v1(row$withholding_credit), character(1L)),
    Steuer = vapply(rows, function(row) .tax_annual_money_v1(row$projected_tax), character(1L)),
    `Verlusttopf zum 31.12. (Aktien / allgemein)` = vapply(rows, pick("closing_loss_carryforward_decimal"), character(1L)))
}
tax_annual_statement_personal_frame_v1 <- function(statement) {
  rows <- if (is.list(statement$personal)) statement$personal else list()
  if (!length(rows)) return(data.frame())
  money <- function(field) function(row) .tax_annual_money_v1(row[[field]])
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Topf = vapply(rows, function(row) as.character(row$tax_bucket_label), character(1L)),
    Gewinne = vapply(rows, money("positive_contribution_decimal"), character(1L)),
    Verluste = vapply(rows, money("negative_contribution_decimal"), character(1L)),
    Saldo = vapply(rows, money("net_contribution_decimal"), character(1L)),
    `Freigrenze (frei bleibt, was darunter liegt)` = vapply(rows, money("exemption_threshold_decimal"), character(1L)),
    `Verlustvortrag zum 1.1.` = vapply(rows, function(row) { origin <- .tax_annual_origin_v1(row$opening_origin)
      paste0(.tax_annual_money_v1(row$opening_loss_carryforward_decimal), if (nzchar(origin)) paste0(" (", origin, ")") else "") }, character(1L)),
    `Verlust verrechnet` = vapply(rows, money("used_loss_decimal"), character(1L)),
    steuerpflichtig = vapply(rows, money("taxable_base_decimal"), character(1L)),
    Steuer = vapply(rows, money("projected_annual_tax_decimal"), character(1L)),
    `Verlustvortrag zum 31.12.` = vapply(rows, money("closing_loss_carryforward_decimal"), character(1L)))
}
tax_annual_statement_chain_frame_v1 <- function(years) {
  rows <- if (is.list(years)) years else list()
  if (!length(rows)) return(data.frame())
  status <- function(row) switch(as.character(row$status), completed = "gerechnet", no_events = "keine Ereignisse",
    blocked = paste("ohne Steuerzahl –", tax_projection_failure_text_v1(row$failure_code)), as.character(row$status))
  closing <- function(field) function(row) if (is.list(row$closing)) .tax_annual_money_v1(row$closing[[field]]) else "–"
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Steuerjahr = vapply(rows, function(row) as.character(row$tax_year), character(1L)),
    Stand = vapply(rows, status, character(1L)),
    Ereignisse = vapply(rows, function(row) as.character(row$event_count), character(1L)),
    `ohne Steuerzahl` = vapply(rows, function(row) as.character(row$open_count), character(1L)),
    Steuer = vapply(rows, function(row) .tax_annual_money_v1(row$projected_annual_tax), character(1L)),
    `Topf Aktien 31.12.` = vapply(rows, closing("capital_equity"), character(1L)),
    `Topf allgemein 31.12.` = vapply(rows, closing("capital_general"), character(1L)),
    `Private Veräußerungen 31.12.` = vapply(rows, closing("private_disposal"), character(1L)),
    `Sonstige Einkünfte 31.12.` = vapply(rows, closing("other_income"), character(1L)))
}
tax_annual_statement_rates_text_v1 <- function(statement) {
  rate <- function(code) { value <- statement$rates[[code]]; if (is.list(value) && !is.null(value$value)) paste0(gsub(".", ",", as.character(value$value), fixed = TRUE), " %") else "–" }
  church <- if (identical(statement$church_tax_applicability, "applicable")) paste("Kirchensteuer", rate("church_tax_rate")) else "keine Kirchensteuer"
  sprintf("Sätze %s: Abgeltungsteuer %s · persönlicher Steuersatz %s · Solidaritätszuschlag %s · %s.", statement$tax_year,
    rate("capital_income_tax_rate"), rate("personal_income_tax_rate"), rate("solidarity_surcharge_rate"), church)
}
tax_annual_statement_card_server_v1 <- function(input, output, service,
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  built <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$annual_statement_build, {
    failure(NULL); built(NULL)
    if (is.null(service)) { failure("tax_annual_statement_source_invalid"); return() }
    result <- tryCatch(service$build(input$annual_statement_year, now_utc()), spot_tax_annual_statement_error_v1 = function(error) error$code,
      error = function(error) "tax_annual_statement_source_invalid")
    if (is.character(result)) failure(result) else built(result)
  })
  output$annual_statement_state <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Jahresrechnung nicht erstellt", tax_annual_statement_error_text_v1(failure()), tone = "error"))
    result <- built()
    if (is.null(result)) return(shiny::p(class = "pl-field-hint", "Noch keine Jahresrechnung erstellt."))
    model <- result$model
    if (!identical(model$status, "ready")) return(portelyra_status_panel(
      switch(model$status, fifo_state_stale = "FIFO-Stand nicht aktuell", fifo_state_absent = "Kein FIFO-Stand vorhanden",
        settings_differ_between_portfolios = "Steuerangaben der Portfolios weichen ab",
        not_assessed = sprintf("Portfolio zählt %s nicht zur Veranlagung", model$failed_year), "Steuereinstellungen nicht lesbar"),
      switch(model$status,
        fifo_state_stale = , fifo_state_absent = "Die Ereignisse kommen aus dem Lot-Nachweis des Buchungsbestands. Bitte in der App „Daten“ den Bestand fortschreiben und danach neu erstellen.",
        settings_differ_between_portfolios = sprintf("Für %s tragen die Portfolios unterschiedliche Steuerangaben; die Jahresrechnung rechnet über alle Portfolios und bräuchte dieselben.", model$failed_year),
        not_assessed = sprintf("In Daten → „4. Steuer“ → „Steuerangaben je Jahr“ ist festgelegt, dass dieses Portfolio %s nicht zur Veranlagung zählt (etwa ein Muster- oder Fremdportfolio). Die Jahresrechnung rechnet es deshalb nicht; Verlustvorträge laufen unverändert weiter.", model$failed_year),
        sprintf("Für %s ließen sich die Steuereinstellungen nicht lesen (Daten → „4. Steuer“).", model$failed_year)), tone = "warning"))
    statement <- model$statement
    # Ein Jahr ohne Ereignisse rechnet der Kern nicht; er liefert nur den Eintrag „keine Ereignisse“ der Kette (Nachprobe rc.440: Demo 2020,
    # vorher brach die Karte mit „argument is of length zero“ ab). Hinweis statt Rechnung - fehlende Buchungen waeren sonst unsichtbar.
    if (!is.list(statement)) return(portelyra_status_panel(sprintf("Steuerjahr %s: keine Ereignisse", shiny::isolate(input$annual_statement_year)), paste(
      "Im Buchungsbestand gibt es für dieses Jahr keine steuerlich relevanten Ereignisse – keine Verkäufe, Dividenden, Zinsen oder Rewards.",
      "Gab es welche, fehlen sie noch im Bestand (App „Daten“). Verlusttöpfe und Vorträge gehen unverändert ins nächste Jahr."), tone = "warning"))
    blocked <- !identical(statement$projection_status, "completed")
    shiny::tagList(
      # 2016-2019 (#496): ausdruecklich nicht vollstaendig - vor der Zahl, damit sie nicht fuer eine vollstaendige gehalten wird.
      if (isTRUE(model$partial)) portelyra_status_panel(sprintf("Steuerjahr %s: nur in Grundzügen – nicht vollständig", statement$tax_year), paste(
        "Das Regelmodul führt Jahre vor 2020 nur mit den Jahreswerten, der Jahresfrist und den Rewards; Fonds vor 2018 rechnet es nicht.",
        "Die Kette dieser Jahresrechnung beginnt 2016 ohne Verlusttöpfe aus früheren Jahren. Freistellungsaufträge und Verlusttöpfe zählen nur, soweit sie in der App „Daten“ eingetragen sind."),
        tone = "warning"),
      if (blocked) portelyra_status_panel(sprintf("Jahresrechnung %s ohne Steuerzahl", statement$tax_year), tax_projection_failure_text_v1(statement$failure_code), tone = "warning")
      else portelyra_status_panel(sprintf("Jahresrechnung %s", statement$tax_year), paste0(
        "Voraussichtliche Steuer ", .tax_annual_money_v1(statement$projected_annual_tax), " · Ergebnis brutto ", .tax_annual_money_v1(statement$economic_amount),
        " · netto ", .tax_annual_money_v1(statement$projected_net), "."), tone = "positive"),
      if (isTRUE(as.integer(statement$open_count) > 0L)) portelyra_status_panel(sprintf("%d Ereignis(se) ohne Steuerzahl", as.integer(statement$open_count)),
        "Sie fehlen in der Rechnung; warum, steht je Ereignis in den Rechenblättern und in der Tabelle (CSV).", tone = "warning"))
  })
  output$annual_statement_view <- shiny::renderUI({
    result <- built()
    if (is.null(result) || !identical(result$model$status, "ready") || !is.list(result$model$statement)) return(NULL)
    statement <- result$model$statement
    shiny::tagList(
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("annual_statement_overview")),
      shiny::tags$h4("Kapitalerträge je Institut"),
      shiny::p(class = "pl-field-hint", "Je Institut: erst Verrechnung im Jahr, dann der Verlusttopf des Instituts, dann sein Freistellungsauftrag; die Quellensteuer mindert die Steuer des Instituts."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("annual_statement_institutions")),
      shiny::tags$h4("Über alle Institute"),
      shiny::p(class = "pl-field-hint", "Saldo des Jahres; unter der Freigrenze steuerfrei, der Vortrag bleibt. Ab der Freigrenze mindert der Vortrag, der Rest ist steuerpflichtig."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("annual_statement_personal")),
      shiny::p(class = "pl-field-hint", tax_annual_statement_rates_text_v1(statement)),
      shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Jahre der Kette · Steuer und Verlusttöpfe zum Jahresende"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("annual_statement_chain"))),
      shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Wie gerechnet wird"),
        shiny::tags$ul(lapply(result$model$method_lines, function(line) shiny::tags$li(line)))),
      shiny::div(class = "pl-editor-actions", shiny::downloadButton("annual_statement_csv", "Jahresrechnung als Tabelle (CSV)", class = "btn-default")))
  })
  statement <- shiny::reactive({ result <- built(); if (is.null(result) || !is.list(result$model$statement)) NULL else result$model$statement })
  output$annual_statement_overview <- shiny::renderTable({ value <- statement(); if (is.null(value)) NULL else tax_annual_statement_overview_frame_v1(value) }, striped = TRUE, bordered = TRUE)
  output$annual_statement_institutions <- shiny::renderTable({ value <- statement(); if (is.null(value)) NULL else tax_annual_statement_institution_frame_v1(value) }, striped = TRUE, bordered = TRUE)
  output$annual_statement_personal <- shiny::renderTable({ value <- statement(); if (is.null(value)) NULL else tax_annual_statement_personal_frame_v1(value) }, striped = TRUE, bordered = TRUE)
  output$annual_statement_chain <- shiny::renderTable({ result <- built(); if (is.null(result)) NULL else tax_annual_statement_chain_frame_v1(result$model$years) }, striped = TRUE, bordered = TRUE)
  output$annual_statement_csv <- shiny::downloadHandler(
    filename = function() { result <- built(); sprintf("jahresrechnung-%s.csv", if (is.null(result)) "leer" else result$model$tax_year) },
    contentType = "text/csv",
    content = function(file) {
      result <- built()
      if (is.null(result) || is.null(result$csv)) stop("tax_annual_statement_not_built", call. = FALSE)
      writeBin(charToRaw(enc2utf8(result$csv)), file)
    })
  invisible(list(built = built, failure = failure))
}
