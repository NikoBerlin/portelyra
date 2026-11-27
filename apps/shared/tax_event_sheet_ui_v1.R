# Karte "Rechenblatt je Ereignis": Jahr waehlen, Blaetter erstellen, ein Ereignis ansehen.
#
# Ein Blatt zeigt den Vorgang, die Anschaffungsseite (jedes verbrauchte Lot mit Menge, Preis, Gebuehr, Datum, Konto,
# Kennung und Haltefrist), die angewandte Regel mit Fundstelle und Topf und die Steuer in ihren Schritten - jeden Satz
# mit seiner Herkunft. Die Karte rechnet nichts; sie setzt, was der Rechenkern liefert.
# Ueber der Liste der Ereignisse stehen deren Summen: insgesamt, je Institut und Konto, je Topf (Festlegung 13.10.2026).
# Braucht die Formatierer aus simple_tax_report_pdf_v1.R (Betrag, Zahl, Text, Art, Wertquelle).
tax_event_sheet_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- rev(seq.int(2020L, max(2020L, as.integer(current_year))))
  shiny::tagList(
    shiny::p(class = "pl-section-copy",
      "Je steuerlich relevantem Ereignis eine Rechnung: Vorgang, verbrauchte Lots mit Haltefrist, angewandte Regel mit Fundstelle und Topf, Steuer in Schritten und Netto."),
    portelyra_note_v1(title = "So lesen Sie die Rechenblätter", id = "tax-event-sheet",
      "Konservativ je Ereignis – ohne Freigrenze, ohne Freibetrag, ohne Verlustverrechnung; ein Verlust trägt die Steuer null.",
      "Zinsen der Cash-Konten kommen mit dem Häkchen „Cash (Zinsen)“ dazu. Über der Liste stehen die Summen: insgesamt, je Institut und Konto, je Topf.",
      "Modellrechnung nach dem Regelmodul des Jahres, keine Rechtsberatung."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("event_sheet_year", "Steuerjahr", choices = as.character(years),
        selected = as.character(if (length(years) > 1L) years[[2L]] else years[[1L]])),
      shiny::checkboxGroupInput("event_sheet_kinds", "Assetklassen und Erträge", choices = tax_event_sheet_asset_types_v1(), selected = "crypto", inline = TRUE)),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("event_sheet_build", "Rechenblätter erstellen", class = "btn-primary")),
    shiny::uiOutput("event_sheet_state"),
    shiny::uiOutput("event_sheet_overview"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("event_sheet_list")),
    shiny::uiOutput("event_sheet_chooser"),
    shiny::uiOutput("event_sheet_view"))
}
tax_event_sheet_error_text_v1 <- function(code) switch(as.character(code),
  tax_event_sheet_input_invalid = "Bitte ein Steuerjahr und mindestens eine Assetklasse oder die Zinsen wählen.",
  "Die Rechenblätter ließen sich nicht erstellen: Buchungsbestand, FIFO-Stand, Steuereinstellungen oder Regelmodul waren nicht lesbar.")
# Betrag auf Cent; wo die exakte Zahl mehr Stellen hat, steht sie dahinter.
# Fuer die App: Betrag mit Einheit, der exakte Wert in Klammern wie bisher (#529 Punkt 8). Das PDF nimmt weiter die Fassung ohne Einheit.
tax_event_sheet_money_ui_v1 <- function(value) { shown <- simple_tax_report_money_v1(value); if (identical(shown, "–")) shown else paste(shown, "€") }
tax_event_sheet_amount_ui_v1 <- function(exact, rounded = NULL) {
  shown <- tax_event_sheet_amount_v1(exact, rounded)
  if (identical(shown, "–")) shown else sub("^(\\S+)", "\\1 €", shown)
}
tax_event_sheet_amount_v1 <- function(exact, rounded = NULL) {
  if (is.null(exact)) return("–")
  shown <- simple_tax_report_money_v1(if (is.null(rounded)) exact else rounded)
  text <- as.character(exact)
  decimals <- if (grepl(".", text, fixed = TRUE)) nchar(sub("^[^.]*\\.", "", text)) else 0L
  if (decimals > 2L) paste0(shown, " (exakt ", gsub(".", ",", text, fixed = TRUE), ")") else shown
}
tax_event_sheet_status_label_v1 <- function(status) switch(as.character(status),
  calculated = "gerechnet", not_taxable = "nicht steuerpflichtig", not_calculated = "keine Steuerzahl", as.character(status))
tax_event_sheet_list_frame_v1 <- function(model) {
  rows <- if (is.list(model)) model$sheets else list()
  money <- tax_event_sheet_money_ui_v1; text <- simple_tax_report_text_v1
  data.frame(
    Blatt = vapply(rows, function(sheet) as.integer(sheet$sheet_no), integer(1L)),
    Datum = vapply(rows, function(sheet) pl_day_v1(sheet$event$local_date), character(1L)),
    Art = vapply(rows, function(sheet) as.character(sheet$event_type_label), character(1L)),
    `Vermögenswert` = vapply(rows, function(sheet) text(sheet$event$asset_label), character(1L)),
    Konto = vapply(rows, function(sheet) text(sheet$event$account_label), character(1L)),
    Institut = vapply(rows, function(sheet) text(sheet$event$institution_label), character(1L)),
    # Gewinn bzw. Ertrag steht am Vorgang - auch dort, wo dem Blatt die Steuerzahl fehlt.
    `Gewinn bzw. Ertrag` = vapply(rows, function(sheet) money(sheet$economic_amount_rounded), character(1L)),
    `steuerpflichtig` = vapply(rows, function(sheet) money(sheet$calculation$taxable_amount_rounded), character(1L)),
    Steuer = vapply(rows, function(sheet) money(sheet$calculation$tax_total_rounded), character(1L)),
    `Netto nach Steuer` = vapply(rows, function(sheet) money(sheet$calculation$net_after_tax_rounded), character(1L)),
    Stand = vapply(rows, function(sheet) tax_event_sheet_status_label_v1(sheet$calculation$status), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}
tax_event_sheet_choices_v1 <- function(model) {
  rows <- if (is.list(model)) model$sheets else list()
  stats::setNames(vapply(rows, function(sheet) as.character(sheet$sheet_no), character(1L)),
    vapply(rows, function(sheet) sprintf("%d · %s · %s · %s · %s", as.integer(sheet$sheet_no), pl_day_v1(sheet$event$local_date), sheet$event_type_label,
      simple_tax_report_text_v1(sheet$event$asset_label), simple_tax_report_text_v1(sheet$event$account_label)), character(1L)))
}
# Die Tabellen eines Blatts stehen in voller Hoehe da. Der uebliche Tabellenrahmen (pl-table-wrap) begrenzt die Hoehe und
# rollt den Rest weg - im Browser gemessen fehlten so am Vorgang Erloes, Anschaffungskosten, Gewinn und Kennung.
# Ein Blatt liest man von oben nach unten; nur zur Seite darf es rollen.
.tax_event_sheet_table_v1 <- function(header, rows) shiny::div(style = "overflow-x:auto;margin-bottom:12px", shiny::tags$table(class = "table shiny-table table-striped table-bordered",
  shiny::tags$thead(shiny::tags$tr(lapply(header, shiny::tags$th))),
  shiny::tags$tbody(lapply(rows, function(cells) shiny::tags$tr(lapply(cells, shiny::tags$td))))))
.tax_event_sheet_pairs_v1 <- function(pairs) .tax_event_sheet_table_v1(c("Angabe", "Wert"),
  lapply(Filter(function(pair) !is.null(pair), pairs), function(pair) list(pair[[1L]], pair[[2L]])))
# Die Summen der Ereignisse als Tabellen: insgesamt, je Institut und Konto, je Topf. Zellen einer Summenzeile.
.tax_event_sheet_sum_cells_v1 <- function(row) {
  money <- simple_tax_report_money_v1
  open <- as.integer(row$not_calculated_count)
  list(as.character(as.integer(row$sheet_count)), money(row$economic_amount_rounded), money(row$taxable_amount_rounded), money(row$tax_total_rounded),
    # Ohne Steuerzahl an einem Blatt der Gruppe gibt es kein Netto der Gruppe - eine Teilsumme saehe aus wie das Ganze.
    if (is.null(row$net_after_tax_rounded)) "–" else money(row$net_after_tax_rounded), if (open > 0L) as.character(open) else "–")
}
tax_event_sheet_institution_label_v1 <- function(label) if (is.null(label) || !nzchar(label)) "ohne Institutsangabe" else as.character(label)
# Zeilen der Aufschluesselung: je Konto eine Zeile; hat ein Institut mehrere Konten, folgt seine Summe.
tax_event_sheet_account_rows_v1 <- function(model) {
  breakdown <- if (is.list(model)) model$breakdown else NULL
  if (!is.list(breakdown) || !length(breakdown$by_account)) return(list())
  rows <- list()
  for (group in breakdown$by_institution) {
    name <- tax_event_sheet_institution_label_v1(group$institution_label)
    members <- Filter(function(row) identical(tax_event_sheet_institution_label_v1(row$institution_label), name), breakdown$by_account)
    for (row in members) rows[[length(rows) + 1L]] <- c(list(name, simple_tax_report_text_v1(row$account_label)), .tax_event_sheet_sum_cells_v1(row))
    if (length(members) > 1L) rows[[length(rows) + 1L]] <- c(list(shiny::tags$strong(paste("Summe", name)),
      sprintf("%d Konten", as.integer(group$account_count))), lapply(.tax_event_sheet_sum_cells_v1(group), shiny::tags$strong))
  }
  rows
}
tax_event_sheet_overview_html_v1 <- function(model) {
  breakdown <- if (is.list(model)) model$breakdown else NULL
  if (!is.list(breakdown) || !is.list(breakdown$total) || !length(model$sheets)) return(NULL)
  money <- simple_tax_report_money_v1
  sums <- c("Ereignisse", "Gewinn bzw. Ertrag", "steuerpflichtig", "Steuer je Ereignis", "Netto nach Steuer", "ohne Steuerzahl")
  open <- as.integer(breakdown$total$not_calculated_count)
  shiny::tagList(
    shiny::tags$h4(sprintf("Gesamt %s", model$tax_year)),
    .tax_event_sheet_table_v1(sums, list(.tax_event_sheet_sum_cells_v1(breakdown$total))),
    shiny::p(class = "pl-field-hint", paste0(
      "Summen der Ereignisse: Gewinn bzw. Ertrag vor Steuer, die Steuer je Ereignis zusammengezählt und was danach bliebe.",
      " Verluste sind nicht verrechnet, Freigrenzen, Freistellungsauftrag und Verlustvorträge nicht angesetzt – das ist nicht die Jahressteuer.",
      if (open > 0L) sprintf(" %d Blatt/Blätter tragen keine Steuerzahl; solange fehlt das Netto.", open) else "")),
    shiny::tags$h4("Nach Institut und Konto"),
    .tax_event_sheet_table_v1(c("Institut", "Konto", sums), tax_event_sheet_account_rows_v1(model)),
    shiny::p(class = "pl-field-hint", "Institut ist die Angabe „Institut / Börse“ am Konto (Daten → „Stammdaten → Konten und Institute“ → „Konto / Wallet anlegen oder umbenennen“); Konten mit derselben Angabe bilden ein Institut."),
    if (length(breakdown$by_bucket) || length(breakdown$by_untaxed)) shiny::tagList(
      shiny::tags$h4("Nach Topf"),
      .tax_event_sheet_table_v1(c("Topf", "Ereignisse", "positive Beträge", "negative Beträge", "Saldo", "Steuer je Ereignis"), c(
        lapply(breakdown$by_bucket, function(row) list(simple_tax_report_text_v1(row$tax_bucket_label), as.character(as.integer(row$sheet_count)),
          money(row$positive_taxable_amount_rounded), money(row$negative_taxable_amount_rounded), money(row$taxable_amount_rounded), money(row$tax_total_rounded))),
        # Was nicht besteuert wird, nach Grund (#582). Die steuerfreien Anteile tragen die Steuer 0, Blaetter ohne Steuerzahl keine.
        lapply(breakdown$by_untaxed, function(row) list(simple_tax_report_text_v1(row$untaxed_label), as.character(as.integer(row$sheet_count)),
          money(row$positive_amount_rounded), money(row$negative_amount_rounded), money(row$amount_rounded),
          if (identical(row$untaxed_code, "not_calculated")) "–" else money("0.00"))),
        # Toepfe und Zeilen zusammen: der Gewinn bzw. Ertrag der Gesamtzeile.
        list(list(shiny::tags$strong("Gewinn bzw. Ertrag"), "", "", "", shiny::tags$strong(money(breakdown$total$economic_amount_rounded)),
          shiny::tags$strong(money(breakdown$total$tax_total_rounded)))))),
      shiny::p(class = "pl-field-hint", paste(
        "Steuerpflichtige Beträge der gerechneten Ereignisse je Topf, darunter, was davon nicht besteuert wird: Lots nach Ablauf der Jahresfrist",
        "(nur bei privaten Veräußerungsgeschäften), die Teilfreistellung bei Fonds, schon versteuerte Vorabpauschalen und die Rundung auf Cent,",
        "dazu Blätter ohne Steuerzahl. Zusammen ergeben sie den Gewinn bzw. Ertrag der Gesamtzeile. Ein Verkauf mit Lots in und nach der Frist",
        "zählt in beiden Zeilen. Der Saldo zeigt, was eine Verrechnung innerhalb des Topfs ergäbe; angewandt ist sie hier nicht."))),
    shiny::tags$h4("Ereignisse"))
}
# Ein Blatt als Seite: Vorgang, Anschaffungsseite, Regel, Rechnung.
tax_event_sheet_html_v1 <- function(sheet) {
  if (!is.list(sheet) || !is.list(sheet$event) || !is.list(sheet$calculation)) return(NULL)
  event <- sheet$event; calculation <- sheet$calculation
  # In der App mit Einheit, Stück ohne Nullen am Ende, Datum TT.MM.JJJJ (#529 Punkt 8); das PDF bleibt, wie es ist.
  money <- tax_event_sheet_money_ui_v1; number <- simple_tax_report_number_v1; text <- simple_tax_report_text_v1
  quantity <- function(value) pl_quantity_v1(value, "–"); price <- function(value) pl_price_v1(value, "EUR", "–")
  amount <- tax_event_sheet_amount_ui_v1
  when <- paste(pl_day_v1(event$local_date), if (is.null(event$local_time)) "ohne Uhrzeit" else event$local_time, if (is.null(event$time_zone)) "" else paste0("(", event$time_zone, ")"))
  income <- identical(sheet$event_kind, "income")
  # Ein Zins traegt einen Betrag und einen Tag - keine Stueckzahl, keinen Kurs, keine Kennung.
  interest <- identical(sheet$event_type, "interest"); reward <- income && !interest
  facts <- list(
    list("Datum und Uhrzeit", when),
    # Die Einordnung nennt die Art schon, wo sie mit ihr beginnt ("Verkauf – Veräußerung").
    list("Vorgang", if (is.null(sheet$treatment_label)) sheet$event_type_label
      else if (startsWith(sheet$treatment_label, sheet$event_type_label)) sheet$treatment_label
      else paste0(sheet$event_type_label, " · ", sheet$treatment_label)),
    list("Vermögenswert", text(event$asset_label)),
    list("Konto", paste0(text(event$account_label), if (is.null(event$institution_label)) "" else paste0(" (", event$institution_label, ")"))),
    if (!interest) list("Stückzahl", quantity(event$quantity)),
    if (reward) list("Gebühr in Stück", quantity(event$fee_quantity)),
    if (reward) list("Stückzahl nach Gebühr", quantity(event$net_quantity)),
    if (reward) list("Wert je Stück bei Zufluss", price(event$value_per_unit)),
    if (income) list(if (interest) "Zinsertrag brutto" else "Bruttoertrag", amount(event$gross_income, event$gross_income_rounded)),
    if (!income) list("Stückpreis", price(event$unit_price)),
    if (!income) list(if (identical(sheet$event_type, "sell")) "Bruttoerlös" else "Wert des Abgangs", amount(event$gross_amount, event$gross_amount_rounded)),
    if (!income && identical(sheet$event_type, "sell")) list("Gebühr", amount(event$monetary_fee, event$monetary_fee_rounded)),
    if (!income && identical(sheet$event_type, "sell")) list("Erlös nach Gebühr", amount(event$net_proceeds, event$net_proceeds_rounded)),
    if (!income && !identical(sheet$event_type, "sell")) list("Quelle des Werts", text(sheet$value_source_label)),
    if (!income) list("Anschaffungskosten der verbrauchten Lots", amount(event$basis, event$basis_rounded)),
    if (!income && !identical(sheet$event_kind, "gratuitous_transfer")) list("Gewinn (Erlös abzüglich Anschaffungskosten)", amount(event$gain, event$gain_rounded)),
    if (!interest) list("Transaktions-ID", text(event$transaction_id)),
    if (!income) list("Adresse der Gegenseite", text(event$counterparty_address)),
    if (!interest) list("Notiz", text(event$note)))
  lots <- if (income || !length(event$lots)) NULL else shiny::tagList(
    shiny::tags$h4("Anschaffungsseite – die verbrauchten Lots"),
    .tax_event_sheet_table_v1(c("Kaufdatum", "Art", "Konto der Anschaffung", "Stückzahl", "Kauf: Stückpreis", "Gebühr anteilig", "Anschaffungskosten",
        "Erlös anteilig", "Gewinn", "Haltedauer [Tage]", "Ende der Jahresfrist", "in der Frist", "Kauf-ID", "Weg über Umschichtungen"),
      lapply(event$lots, function(lot) list(pl_day_v1(lot$acquisition_local_date), simple_tax_report_type_label_v1(lot$acquisition_type), text(lot$acquisition_account_label),
        quantity(lot$quantity), price(lot$acquisition_unit_price), money(lot$acquisition_fee_share_rounded), money(lot$basis_rounded),
        money(lot$proceeds_share_rounded), money(lot$gain_rounded), as.character(lot$holding_days), pl_day_v1(lot$holding_period_end_date),
        if (isTRUE(lot$within_holding_period)) "ja" else "nein", text(lot$acquisition_identifier$transaction_id),
        if (!length(lot$path)) "–" else paste(vapply(lot$path, function(step) sprintf("%s %s → %s [%s]", pl_day_v1(step$local_date), step$from_account_label,
          step$to_account_label, text(step$transaction_id)), character(1L)), collapse = " | ")))),
    # Split zwischen Kauf und Abgang (#451): je betroffenem Lot ein Hinweis unter der Tabelle.
    lapply(Filter(Negate(is.null), lapply(event$lots, function(lot) {
      note <- simple_tax_report_split_note_v1(lot)
      if (is.null(note)) NULL else paste0("Lot vom ", pl_day_v1(lot$acquisition_local_date), ": ", note, ".")
    })), function(note) shiny::p(class = "pl-field-hint", note)))
  result <- if (identical(calculation$status, "calculated")) shiny::tagList(
    shiny::tags$h4("Regel"),
    .tax_event_sheet_pairs_v1(list(
      list("Steuerjahr und Rechtsstand", as.character(calculation$tax_year)),
      list("Angewandte Regel", paste0(text(calculation$legal_citation), " · ", text(calculation$rule_code))),
      list("Topf", text(calculation$tax_bucket_label)),
      list("Einordnung des Assets", text(calculation$classification_code)),
      list("Regelmodul", paste(text(calculation$plugin_id), text(calculation$plugin_version))))),
    shiny::tags$h4("Rechnung"),
    shiny::p(class = "pl-field-hint", paste0("Steuerpflichtiger Betrag: ", amount(calculation$taxable_amount, calculation$taxable_amount_rounded),
      " – ", text(calculation$taxable_explanation))),
    if (length(calculation$steps)) .tax_event_sheet_table_v1(c("Schritt", "Bemessungsgrundlage", "Satz in %", "Herkunft des Satzes", "Fundstelle", "Betrag"),
      lapply(calculation$steps, function(step) list(step$label,
        if (is.null(step$base)) "–" else paste0(step$base_label, ": ", amount(step$base, step$base_rounded)),
        number(step$rate_percent), text(step$rate_origin), text(step$legal_citation), amount(step$amount, step$amount_rounded))))
    else shiny::p(class = "pl-field-hint", "Kein positiver steuerpflichtiger Betrag – es fällt je Ereignis keine Steuer an, ein Satz wird nicht gebraucht."),
    .tax_event_sheet_pairs_v1(list(
      list(if (interest) "Zinsertrag brutto" else if (income) "Bruttoertrag" else "Gewinn", amount(calculation$economic_amount, calculation$economic_amount_rounded)),
      list("Steuer gesamt", amount(calculation$tax_total, calculation$tax_total_rounded)),
      list("Netto nach Steuer", amount(calculation$net_after_tax, calculation$net_after_tax_rounded)))))
  else portelyra_status_panel(
    if (identical(calculation$status, "not_taxable")) "Nicht steuerpflichtig" else "Keine Steuerzahl",
    text(calculation$reason_text), tone = if (identical(calculation$status, "not_taxable")) "neutral" else "warning")
  shiny::tagList(
    shiny::tags$h3(sprintf("Blatt %d · %s · %s · %s", as.integer(sheet$sheet_no), pl_day_v1(event$local_date), sheet$event_type_label, text(event$asset_label))),
    shiny::tags$h4("Vorgang"), .tax_event_sheet_pairs_v1(facts), lots, result)
}
tax_event_sheet_card_server_v1 <- function(input, output, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  sheets <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL)
  shiny::observeEvent(input$event_sheet_build, {
    failure(NULL)
    built <- if (is.null(service)) "tax_event_sheet_source_invalid" else tryCatch(
      service$build(input$event_sheet_year, as.character(input$event_sheet_kinds), now_utc()),
      spot_tax_event_sheet_error_v1 = function(error) error$code, error = function(error) "tax_event_sheet_source_invalid")
    if (is.character(built)) { sheets(NULL); failure(built) } else sheets(built)
  })
  output$event_sheet_state <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Rechenblätter nicht erstellt", tax_event_sheet_error_text_v1(failure()), tone = "error"))
    built <- sheets()
    if (is.null(built)) return(shiny::p(class = "pl-field-hint", "Noch keine Rechenblätter erstellt."))
    model <- built$model; summary <- model$summary
    if (!identical(model$status, "ready")) return(portelyra_status_panel(
      if (identical(model$status, "fifo_state_stale")) "FIFO-Stand nicht aktuell" else "Kein FIFO-Stand vorhanden",
      "Die Rechenblätter stehen auf dem Lot-Nachweis des Buchungsbestands. Bitte in der App „Daten“ den Bestand fortschreiben und danach neu erstellen.", tone = "warning"))
    if (!length(model$sheets)) return(portelyra_status_panel(sprintf("Keine Ereignisse in %s", model$tax_year),
      "In diesem Jahr gibt es für die Auswahl keine Veräußerung, keinen Abgang und keinen Ertrag.", tone = "neutral"))
    # Je Grund einmal der Satz, der sagt, was fehlt und wo es einzutragen ist.
    reasons <- unique(vapply(Filter(function(sheet) identical(sheet$calculation$status, "not_calculated"), model$sheets),
      function(sheet) simple_tax_report_text_v1(sheet$calculation$reason_text), character(1L)))
    shiny::tagList(
      portelyra_status_panel(sprintf("Rechenblätter %s erstellt", model$tax_year), sprintf(
        "%d Blätter · %d gerechnet (%d mit Steuerbetrag) · %d nicht steuerpflichtig · %d ohne Steuerzahl · Summe der Ereignissteuern %s EUR",
        as.integer(summary$sheet_count), as.integer(summary$calculated_count), as.integer(summary$with_tax_count), as.integer(summary$not_taxable_count),
        as.integer(summary$not_calculated_count), simple_tax_report_money_v1(summary$event_tax_sum_rounded)), tone = "positive"),
      shiny::p(class = "pl-field-hint", "Die Summe der Ereignissteuern ist keine Jahressteuer: Je Ereignis gelten weder Freigrenzen noch Verlustverrechnung."),
      if (length(reasons)) portelyra_status_panel(sprintf("%d Blatt/Blätter ohne Steuerzahl", as.integer(summary$not_calculated_count)),
        paste(reasons, collapse = " · "), tone = "warning"),
      shiny::div(class = "pl-editor-actions", shiny::downloadButton("event_sheet_csv", "Übersicht laden (CSV)", class = "btn-default")))
  })
  output$event_sheet_overview <- shiny::renderUI({
    built <- sheets()
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$sheets)) return(NULL)
    tax_event_sheet_overview_html_v1(built$model)
  })
  output$event_sheet_list <- shiny::renderTable({
    built <- sheets()
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$sheets)) return(NULL)
    tax_event_sheet_list_frame_v1(built$model)
  }, striped = TRUE, bordered = TRUE)
  output$event_sheet_chooser <- shiny::renderUI({
    built <- sheets()
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$sheets)) return(NULL)
    shiny::selectInput("event_sheet_choice", "Blatt ansehen", choices = tax_event_sheet_choices_v1(built$model), width = "100%")
  })
  output$event_sheet_view <- shiny::renderUI({
    built <- sheets()
    if (is.null(built) || !identical(built$model$status, "ready") || !length(built$model$sheets)) return(NULL)
    wanted <- suppressWarnings(as.integer(if (is.null(input$event_sheet_choice)) 1L else input$event_sheet_choice))
    found <- Filter(function(sheet) identical(as.integer(sheet$sheet_no), wanted), built$model$sheets)
    tax_event_sheet_html_v1(if (length(found)) found[[1L]] else built$model$sheets[[1L]])
  })
  output$event_sheet_csv <- shiny::downloadHandler(
    filename = function() { built <- sheets(); sprintf("rechenblaetter-%s-%s.csv", if (is.null(built)) "leer" else built$model$tax_year,
      if (is.null(built)) "x" else paste(unlist(built$model$asset_types), collapse = "-")) },
    contentType = "text/csv; charset=utf-8",
    content = function(file) { built <- sheets(); if (is.null(built)) stop("tax_event_sheet_not_built", call. = FALSE); writeBin(charToRaw(enc2utf8(built$csv)), file) })
  invisible(sheets)
}
