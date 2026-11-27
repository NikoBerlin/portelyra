# Der Steuerreport in ausfuehrlicher Fassung als ein Dokument (#433): der einfache Report, dahinter die Jahresrechnung und
# je Ereignis das Rechenblatt mit Regel, Fundstelle, Topf und den Schritten der Steuer.
#
# Den Steuerreport gibt es einfach und ausfuehrlich. Die einfache Fassung dokumentiert, die ausfuehrliche
# zeigt dazu die eigene Modellrechnung - deutlich als solche gekennzeichnet, keine Steuerfestsetzung. Die Seiten rechnen
# nichts; sie setzen, was Report, Rechenblaetter und Jahresrechnung liefern.
# Braucht simple_tax_report_pdf_v1.R, tax_event_sheet_ui_v1.R (Betraege), tax_projection_view_v1.R und
# tax_annual_statement_view_v1.R (Tabellen der Jahresrechnung).
tax_detailed_report_title_v1 <- function(year) sprintf("Steuerreport %s – ausführliche Fassung (Dokumentation mit eigener Modellrechnung)", year)
tax_detailed_report_method_lines_v1 <- function() c(
  "Ausführliche Fassung: Hinter dem Report stehen die Jahresrechnung und je Ereignis das Rechenblatt. Beides ist eine eigene Modellrechnung nach dem Regelmodul des Jahres – keine Steuerfestsetzung und keine Rechtsberatung.")

# `report`: Ergebnis des Report-Dienstes (model, method_lines, notes). `sheets`: Modell der Rechenblaetter oder NULL.
# `statement`: Modell der Jahresrechnung oder NULL. Fehlt eins, sagt das Dokument es an seiner Stelle.
tax_detailed_report_pdf_v1 <- function(report, sheets, statement, file, generated_at_utc, compress = TRUE) {
  if (!is.list(report) || !is.list(report$model)) stop("tax_detailed_report_input_invalid", call. = FALSE)
  model <- report$model
  simple_tax_report_pdf_v1(model, file, generated_at_utc, c(as.character(report$method_lines), tax_detailed_report_method_lines_v1()),
    as.character(report$notes), compress = compress, title = tax_detailed_report_title_v1(model$tax_year),
    extra = function(h) tax_detailed_report_sections_v1(h, model, sheets, statement))
}

# Die Abschnitte hinter dem Report: Jahresrechnung, dann je Ereignis das Rechenblatt. `h` sind die Zeichenwerkzeuge des PDFs.
tax_detailed_report_sections_v1 <- function(h, model, sheets, statement) {
  h$new_page()
  h$heading(if (any(unlist(model$asset_types) != "cash")) "M. Jahresrechnung (eigene Modellrechnung)" else "Jahresrechnung (eigene Modellrechnung)")
  if (!is.list(statement) || !identical(statement$status, "ready") || !is.list(statement$statement)) {
    h$paragraph("Die Jahresrechnung ließ sich für dieses Dokument nicht erstellen; sie steht nicht darin.", col = "grey35", after = 1)
  } else {
    st <- statement$statement
    h$paragraph(paste("Stand:", if (identical(st$projection_status, "completed")) "gerechnet" else paste("ohne Steuerzahl –", tax_projection_failure_text_v1(st$failure_code))),
      size = 7.5, after = 0.5)
    h$paragraph(tax_annual_statement_rates_text_v1(st), size = 7.5, after = 1)
    overview <- tax_annual_statement_overview_frame_v1(st)
    h$table(names(overview), lapply(seq_len(nrow(overview)), function(index) unname(unlist(overview[index, ]))), c(120, 50), right = c(FALSE, TRUE))
    h$paragraph("Kapitalerträge je Institut (Beträge „Aktien / allgemein“)", size = 8, bold = TRUE, after = 0.5)
    institutions <- tax_annual_statement_institution_frame_v1(st)
    if (nrow(institutions)) h$table(names(institutions), lapply(seq_len(nrow(institutions)), function(index) unname(unlist(institutions[index, ]))),
      c(34, 14, 26, 26, 30, 26, 30, 20, 20, 16, 26), right = c(FALSE, rep(TRUE, 10)), size = 5.8)
    else h$paragraph("Keine Kapitalerträge in diesem Jahr.", col = "grey35", after = 1)
    h$paragraph("Über alle Institute", size = 8, bold = TRUE, after = 0.5)
    personal <- tax_annual_statement_personal_frame_v1(st)
    h$table(names(personal), lapply(seq_len(nrow(personal)), function(index) unname(unlist(personal[index, ]))),
      c(50, 20, 20, 20, 26, 30, 22, 22, 18, 24), right = c(FALSE, rep(TRUE, 9)), size = 5.8)
    h$paragraph("Wie gerechnet wird", size = 8, bold = TRUE, after = 0.5)
    for (line in unlist(statement$method_lines)) h$paragraph(paste("•", line), size = 7, indent = 2, after = 0.3)
  }
  h$new_page()
  h$heading(if (any(unlist(model$asset_types) != "cash")) "N. Rechenblätter je Ereignis (eigene Modellrechnung)" else "Rechenblätter je Ereignis (eigene Modellrechnung)")
  if (!is.list(sheets) || !identical(sheets$status, "ready")) {
    h$paragraph("Die Rechenblätter ließen sich für dieses Dokument nicht erstellen; sie stehen nicht darin.", col = "grey35")
    return(invisible(NULL))
  }
  h$paragraph(paste("Je Ereignis konservativ gerechnet – ohne Freigrenze, ohne Freibetrag, ohne Verlustverrechnung; ein Verlust trägt die Steuer null.",
    "Die Summe der Ereignissteuern ist keine Jahressteuer; die steht in der Jahresrechnung."), size = 7, col = "grey25", after = 1)
  if (!length(sheets$sheets)) h$paragraph("Keine Ereignisse in diesem Jahr.", col = "grey35")
  for (sheet in sheets$sheets) tax_detailed_report_sheet_v1(h, sheet)
  invisible(NULL)
}

# Ein Rechenblatt auf der Seite: Vorgang, Lots, Regel, Schritte, Ergebnis - oder der Grund, warum es keine Steuerzahl gibt.
tax_detailed_report_sheet_v1 <- function(h, sheet) {
  event <- sheet$event; calculation <- sheet$calculation; text <- h$text; number <- h$number; money <- h$money
  # Seit #532 mit Einheit und Datum TT.MM.JJJJ wie in der App.
  day <- if (is.function(h$day)) h$day else function(value) value
  amount <- function(exact, rounded) tax_event_sheet_amount_ui_v1(exact, rounded)
  h$need(16)
  h$paragraph(sprintf("Blatt %s · %s · %s · %s · %s%s", sheet$sheet_no, day(event$local_date), sheet$event_type_label, text(event$asset_label), text(event$account_label),
    if (is.null(event$institution_label)) "" else paste0(" (", event$institution_label, ")")), size = 8, bold = TRUE, after = 0.3)
  income <- identical(sheet$event_kind, "income")
  facts <- c(
    if (!is.null(sheet$treatment_label)) paste("Einordnung:", sheet$treatment_label),
    if (!identical(sheet$event_type, "interest")) paste("Stückzahl:", number(event$quantity)),
    if (income) paste(if (identical(sheet$event_type, "interest")) "Zinsertrag brutto:" else "Bruttoertrag:", amount(event$gross_income, event$gross_income_rounded)),
    if (!income) paste("Erlös bzw. Wert:", amount(event$net_proceeds, event$net_proceeds_rounded), "·", "Anschaffungskosten:", amount(event$basis, event$basis_rounded)),
    if (!income && !identical(sheet$event_kind, "gratuitous_transfer")) paste("Gewinn:", amount(event$gain, event$gain_rounded)),
    if (!is.null(event$transaction_id)) paste("Transaktions-ID:", event$transaction_id))
  h$paragraph(paste(facts, collapse = " · "), size = 7, indent = 2, after = 0.3)
  if (!income && length(event$lots)) h$table(c("Kaufdatum", "Konto der Anschaffung", "Stückzahl", "Anschaffungskosten", "Erlös anteilig", "Gewinn", "Haltedauer [Tage]", "in der Frist", "Kauf-ID"),
    lapply(event$lots, function(lot) c(day(lot$acquisition_local_date), text(lot$acquisition_account_label), number(lot$quantity), money(lot$basis_rounded),
      money(lot$proceeds_share_rounded), money(lot$gain_rounded), as.character(lot$holding_days), if (isTRUE(lot$within_holding_period)) "ja" else "nein",
      text(lot$acquisition_identifier$transaction_id))),
    c(20, 40, 26, 26, 26, 24, 18, 14, 40), right = c(FALSE, FALSE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, FALSE), indent = 2, size = 6)
  if (identical(calculation$status, "calculated")) {
    h$paragraph(sprintf("Regel: %s · %s · Topf: %s · Einordnung: %s", text(calculation$legal_citation), text(calculation$rule_code), text(calculation$tax_bucket_label),
      text(calculation$classification_code)), size = 7, indent = 2, after = 0.2)
    h$paragraph(paste0("Steuerpflichtig: ", amount(calculation$taxable_amount, calculation$taxable_amount_rounded), " – ", text(calculation$taxable_explanation)),
      size = 7, indent = 2, after = 0.2)
    if (length(calculation$steps)) h$table(c("Schritt", "Bemessungsgrundlage", "Satz in %", "Herkunft des Satzes", "Betrag"),
      lapply(calculation$steps, function(step) c(step$label, if (is.null(step$base)) "–" else paste0(step$base_label, ": ", amount(step$base, step$base_rounded)),
        number(step$rate_percent), text(step$rate_origin), amount(step$amount, step$amount_rounded))),
      c(32, 60, 16, 70, 36), right = c(FALSE, FALSE, TRUE, FALSE, TRUE), indent = 2, size = 6)
    h$paragraph(sprintf("Steuer je Ereignis: %s · Netto nach Steuer: %s", amount(calculation$tax_total, calculation$tax_total_rounded),
      amount(calculation$net_after_tax, calculation$net_after_tax_rounded)), size = 7, bold = TRUE, indent = 2, after = 1.2)
  } else {
    h$paragraph(paste("Keine Steuerzahl:", text(calculation$reason_text)), size = 7, indent = 2, col = "grey25", after = 1.2)
  }
}
