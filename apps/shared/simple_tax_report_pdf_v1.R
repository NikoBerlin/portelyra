# Der einfache Steuerreport als PDF - aus demselben Modell wie die Tabelle.
#
# Das Blatt soll sich von oben nach unten nachrechnen lassen: je Veraeusserung
# der Vorgang, die verbrauchten Lots, ihre Kennungen und ihr Weg ueber
# Umschichtungen. Gezeichnet wird mit grid aus der R-Grundausstattung; es wird
# nichts gerechnet, nur gesetzt. Zu lange Zellen werden gekuerzt und mit "…"
# gekennzeichnet - Kennungen stehen deshalb zusaetzlich ungekuerzt in eigenen
# Zeilen, die vollstaendige Tabelle ist die CSV-Fassung.
#
# Seit #532 (rc.356) wie in den Apps: Datum TT.MM.JJJJ, Betraege mit Einheit, Stueckzahlen ohne Nullen am Ende, Kurse mit
# mindestens zwei Stellen. Braucht dafuer die Formatierer pl_*_v1 aus portelyra_ui_shell.R. Die CSV bleibt maschinenlesbar,
# Behoerdentexte und Methodenzeilen bleiben im Wortlaut.
simple_tax_report_money_v1 <- function(value) {
  if (is.null(value) || !nzchar(as.character(value))) return("–")
  formatC(as.numeric(value), format = "f", digits = 2, big.mark = ".", decimal.mark = ",")
}
simple_tax_report_number_v1 <- function(value) {
  if (is.null(value) || !nzchar(as.character(value))) return("–")
  gsub(".", ",", as.character(value), fixed = TRUE)
}
simple_tax_report_text_v1 <- function(value) if (is.null(value) || !nzchar(as.character(value))) "–" else as.character(value)
# Die Formatierer des PDFs (#532): mit Einheit, deutsch; leer heisst "–". Die App haengt ihre Einheit selbst an
# (tax_event_sheet_money_ui_v1) und nimmt deshalb weiter simple_tax_report_money_v1.
.simple_tax_report_empty_v1 <- function(value) is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))
simple_tax_report_pdf_money_v1 <- function(value, currency = "EUR") {
  if (.simple_tax_report_empty_v1(value)) return("–")
  pl_amount_v1(as.character(value), if (.simple_tax_report_empty_v1(currency)) "EUR" else as.character(currency), 2L)
}
simple_tax_report_pdf_quantity_v1 <- function(value) if (.simple_tax_report_empty_v1(value)) "–" else pl_quantity_v1(as.character(value))
simple_tax_report_pdf_price_v1 <- function(value) if (.simple_tax_report_empty_v1(value)) "–" else pl_price_v1(as.character(value))
simple_tax_report_pdf_day_v1 <- function(value) if (.simple_tax_report_empty_v1(value)) "–" else pl_day_v1(as.character(value))
# Der Zeitpunkt der Erstellung in der Fusszeile: TT.MM.JJJJ HH:MM, weiter in UTC.
simple_tax_report_pdf_stamp_v1 <- function(value) {
  at <- suppressWarnings(as.POSIXct(as.character(value), format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  if (is.na(at)) as.character(value) else format(at, "%d.%m.%Y %H:%M", tz = "UTC")
}
# Woher der Erloes einer Veraeusserung stammt - wortgleich mit der Tabelle des Rechenkerns.
simple_tax_report_value_source_label_v1 <- function(item) {
  source <- if (is.null(item$value_source)) "" else as.character(item$value_source)
  if (identical(source, "booked")) return("gebucht")
  if (identical(source, "owner_entered")) return("am Abgang eingetragen")
  if (identical(source, "daily_value")) return(paste0("Tageswert der Kursquelle vom ",
    simple_tax_report_pdf_day_v1(if (is.null(item$value_price_date)) item$local_date else item$value_price_date),
    if (identical(item$value_price_basis, "observed")) "" else " (fortgeschrieben)"))
  if (identical(item$value_missing_reason, "valuation_state_unreadable")) "kein Wert – Bewertungsstand nicht lesbar" else "kein Wert – kein Kurs für den Tag"
}
# Die Wertermittlung einer Wallet in Worten - wortgleich mit der Tabelle des Rechenkerns (Rn. 61/62).
simple_tax_report_wallet_valuation_text_v1 <- function(item) {
  average <- item$average
  if (!length(average)) return("FiFo")
  paste0("Durchschnittsmethode für ", paste(vapply(average, function(row) paste(row$asset_label, "ab", format(as.Date(row$since), "%d.%m.%Y")), character(1L)),
    collapse = "; "), "; übrige Coins FiFo")
}
# Ein Split zwischen Kauf und Abgang (#451, rc.371): Stueckzahl und Kaufpreis des Lots stehen in Stuecken nach dem Split, der
# Kaufbeleg in alten. Der Hinweis nennt Verhaeltnis, Stichtag und Menge und Kurs des Belegs; ohne Split NULL.
simple_tax_report_split_note_v1 <- function(lot) {
  split <- lot$acquisition_split
  if (!is.list(split) || !length(split)) return(NULL)
  days <- paste(vapply(unlist(split$effective_local_dates), simple_tax_report_pdf_day_v1, character(1L)), collapse = ", ")
  paste0("Split ", split$ratio_numerator, " : ", split$ratio_denominator, " am ", days,
    " – Stückzahl und Kaufpreis in Stücken nach dem Split; im Kaufbeleg ", simple_tax_report_pdf_quantity_v1(split$document_quantity), " Stück",
    if (.simple_tax_report_empty_v1(split$document_unit_price)) "" else paste0(" à ", simple_tax_report_pdf_price_v1(split$document_unit_price)))
}
simple_tax_report_type_label_v1 <- function(value) {
  labels <- c(sell = "Verkauf", withdrawal = "Abgang", buy = "Kauf", reward = "Reward", dividend = "Dividende",
    deposit = "Zugang", stock_dividend = "Stockdividende", transfer = "Transfer")
  if (is.character(value) && length(value) == 1L && value %in% names(labels)) unname(labels[[value]]) else simple_tax_report_text_v1(value)
}
simple_tax_report_role_label_v1 <- function(roles) {
  labels <- c(disposal = "Veräußerung", gratuitous_transfer = "Unentgeltlicher Abgang", acquisition_of_consumed_lot = "Anschaffung eines verbrauchten Lots", income = "Ertrag",
    transfer_in_year = "Umschichtung im Jahr", transfer_in_lot_path = "Umschichtung im Weg eines Lots",
    event_with_asset_fee = "Vorgang mit Gebühr in Stück", acquisition_of_fee_lot = "Anschaffung eines Gebühren-Lots")
  paste(vapply(unlist(roles), function(role) if (role %in% names(labels)) unname(labels[[role]]) else role, character(1L)), collapse = " / ")
}
simple_tax_report_status_text_v1 <- function(model) if (identical(model$status, "ready") && length(model$asset_types) && all(unlist(model$asset_types) == "cash"))
  "nicht benötigt – der Report enthält nur Zinsen" else switch(as.character(model$status),
  ready = "aktuell",
  fifo_state_stale = "nicht aktuell – seit der letzten Fortschreibung wurden Buchungen geändert; der Report enthält deshalb keine Vorgänge",
  "nicht vorhanden – der Report enthält keine Vorgänge")

# `title` und `extra` fuer die ausfuehrliche Fassung (#433): `extra` bekommt die Zeichenwerkzeuge und setzt weitere Abschnitte
# hinter die des Reports - in dasselbe Dokument.
simple_tax_report_pdf_v1 <- function(model, file, generated_at_utc, method_lines, notes = character(), compress = TRUE, title = NULL, extra = NULL) {
  if (!is.list(model) || !identical(model$contract_version, "simple_tax_report_v1") || !is.character(file) || length(file) != 1L ||
      !is.character(generated_at_utc) || length(generated_at_utc) != 1L || !is.character(method_lines) || !is.character(notes))
    stop("simple_tax_report_pdf_input_invalid", call. = FALSE)
  width <- 297; height <- 210; margin <- 12; inner <- width - 2 * margin
  if (is.null(title)) title <- sprintf("Steuerreport %s – einfache Fassung (Dokumentation ohne Steuerberechnung)", model$tax_year)
  # WinAnsi kennt Umlaute, Gedankenstrich, Auslassungspunkte und Aufzaehlungspunkt; was es nicht kennt,
  # wird vor dem Setzen durch "?" ersetzt, statt beim Zeichnen still zu einem Punkt zu werden.
  grDevices::pdf(file, width = width / 25.4, height = height / 25.4, onefile = TRUE, compress = isTRUE(compress),
    title = sprintf("Steuerreport %s", model$tax_year), encoding = "WinAnsi.enc")
  finished <- FALSE
  on.exit({ grDevices::dev.off(); if (!finished) unlink(file, force = TRUE) }, add = TRUE)
  page <- 0L; y <- margin
  line_height <- function(size) size * 0.3528 * 1.3
  printable <- function(text) {
    chars <- strsplit(enc2utf8(as.character(text)), "", fixed = TRUE)[[1L]]
    if (!length(chars)) return("")
    chars[is.na(iconv(chars, "UTF-8", "CP1252"))] <- "?"
    value <- paste(chars, collapse = "")
    # Das PDF-Geraet setzt "-" als Minuszeichen. In Kennungen und Datumsangaben soll ein Bindestrich stehen,
    # der sich als "-" herauskopieren laesst (Zeichen 173 der Kodierung); ein Vorzeichen bleibt ein Minus.
    gsub("-(?![0-9])|(?<=[^ ])-(?=[0-9])", "\u00ad", value, perl = TRUE)
  }
  measure <- function(text, size, bold = FALSE) grid::convertWidth(grid::grobWidth(grid::textGrob(text,
    gp = grid::gpar(fontsize = size, fontface = if (bold) "bold" else "plain"))), "mm", valueOnly = TRUE)
  put <- function(text, x, size = 7, bold = FALSE, right = FALSE, col = "black") grid::grid.text(printable(text),
    x = grid::unit(x, "mm"), y = grid::unit(height - y, "mm"), just = c(if (right) "right" else "left", "top"),
    gp = grid::gpar(fontsize = size, fontface = if (bold) "bold" else "plain", col = col))
  new_page <- function() {
    grid::grid.newpage(); page <<- page + 1L; y <<- margin
    grid::grid.text(printable(sprintf("%s · erstellt %s (UTC) · Seite %d", title, simple_tax_report_pdf_stamp_v1(generated_at_utc), page)), x = grid::unit(margin, "mm"),
      y = grid::unit(5, "mm"), just = c("left", "bottom"), gp = grid::gpar(fontsize = 6, col = "grey35"))
  }
  need <- function(space) if (y + space > height - margin - 3) new_page()
  # Umbruch nach Woertern; ein Wort, das breiter ist als die Zeile (ein Hash), wird nach Zeichen geteilt.
  wrap <- function(text, limit, size, bold = FALSE) {
    words <- strsplit(printable(text), " ", fixed = TRUE)[[1L]]
    lines <- character(); current <- ""
    for (word in words) {
      while (measure(word, size, bold) > limit) {
        cut <- nchar(word)
        while (cut > 1L && measure(substr(word, 1L, cut), size, bold) > limit) cut <- cut - 1L
        if (nzchar(current)) { lines <- c(lines, current); current <- "" }
        lines <- c(lines, substr(word, 1L, cut)); word <- substr(word, cut + 1L, nchar(word))
      }
      candidate <- if (nzchar(current)) paste(current, word) else word
      if (nzchar(current) && measure(candidate, size, bold) > limit) { lines <- c(lines, current); current <- word } else current <- candidate
    }
    if (nzchar(current) || !length(lines)) lines <- c(lines, current)
    lines
  }
  paragraph <- function(text, size = 7, bold = FALSE, indent = 0, col = "black", after = 0) {
    for (line in wrap(text, inner - indent, size, bold)) { need(line_height(size)); put(line, margin + indent, size, bold, col = col); y <<- y + line_height(size) }
    y <<- y + after
  }
  heading <- function(text) { need(14); y <<- y + 2; paragraph(text, size = 10, bold = TRUE, after = 1.5) }
  fit <- function(text, limit, size, bold = FALSE) {
    text <- printable(text)
    if (nchar(text) * size * 0.14 <= limit || measure(text, size, bold) <= limit) return(text)
    cut <- nchar(text)
    while (cut > 1L && measure(paste0(substr(text, 1L, cut), "…"), size, bold) > limit) cut <- cut - 1L
    paste0(substr(text, 1L, cut), "…")
  }
  # Eine Tabelle: Spaltenbreiten in mm, rechtsbuendige Spalten fuer Zahlen; der Kopf wiederholt sich je Seite. Eine lange Zelle bricht in
  # der Zelle um, statt in die Nachbarspalte zu laufen oder gekuerzt zu werden (etwa „Europe/BerlinReward“); die Zeile wird
  # so hoch wie ihre hoechste Zelle.
  table <- function(header, rows, widths, right = rep(FALSE, length(header)), size = 6.5, indent = 0, empty = "Keine Einträge.") {
    scale <- min(1, (inner - indent) / sum(widths)); widths <- widths * scale
    left <- margin + indent + c(0, cumsum(widths))[seq_along(widths)]
    lines_of <- function(cells, bold) lapply(seq_along(cells), function(index) wrap(cells[[index]], widths[[index]] - 1.2, size, bold))
    draw <- function(lines, bold) {
      top <- y; height_of <- max(1L, max(lengths(lines)))
      for (index in seq_along(lines)) for (k in seq_along(lines[[index]])) {
        y <<- top + (k - 1L) * line_height(size)
        put(lines[[index]][[k]], if (right[[index]]) left[[index]] + widths[[index]] - 1.2 else left[[index]], size, bold, right = right[[index]])
      }
      y <<- top + height_of * line_height(size)
    }
    header_lines <- lines_of(header, TRUE)
    head <- function() {
      draw(header_lines, TRUE)
      grid::grid.lines(x = grid::unit(c(margin + indent, margin + indent + sum(widths)), "mm"), y = grid::unit(height - y + 0.2, "mm"),
        gp = grid::gpar(col = "grey55", lwd = 0.4))
      y <<- y + 0.6
    }
    need(line_height(size) * (max(lengths(header_lines)) + 2) + 1); head()
    if (!length(rows)) { put(empty, margin + indent, size, col = "grey35"); y <<- y + line_height(size) }
    for (cells in rows) {
      lines <- lines_of(cells, FALSE)
      if (y + max(1L, max(lengths(lines))) * line_height(size) > height - margin - 3) { new_page(); head() }
      draw(lines, FALSE)
    }
    y <<- y + 1.5
  }
  money <- simple_tax_report_pdf_money_v1; number <- simple_tax_report_pdf_quantity_v1; text <- simple_tax_report_text_v1
  price <- simple_tax_report_pdf_price_v1; day <- simple_tax_report_pdf_day_v1
  when <- function(item) paste(day(item$local_date), if (is.null(item$local_time)) "ohne Uhrzeit" else substr(item$local_time, 1L, 5L),
    if (is.null(item$time_zone)) "" else paste0("(", item$time_zone, ")"))

  new_page()
  paragraph(title, size = 13, bold = TRUE, after = 2)
  kinds <- c(crypto = "Krypto", equity = "Aktien", fund = "Fonds", commodity = "Rohstoffe", derivative = "Derivate", fx = "Devisen", cash = "Cash (Zinsen)")
  # Ein Report nur ueber Zinsen belegt keine Lots: Die Abschnitte A bis G gehoeren dort nicht hin.
  with_ledger <- any(unlist(model$asset_types) != "cash"); with_cash <- "cash" %in% unlist(model$asset_types)
  paragraph(sprintf("Assetklassen: %s · FIFO-Stand: %s", paste(unname(kinds[unlist(model$asset_types)]), collapse = ", "),
    simple_tax_report_status_text_v1(model)), size = 8, after = 2)
  paragraph("Methode", size = 9, bold = TRUE, after = 0.5)
  for (line in method_lines) paragraph(paste("•", line), size = 7.5, indent = 2, after = 0.4)
  if (length(notes)) { y <- y + 1.5; paragraph("Anmerkungen", size = 9, bold = TRUE, after = 0.5); for (note in notes) paragraph(paste("•", note), size = 7.5, indent = 2, after = 0.4) }
  if (!is.null(model$wallets)) {
    # Verwendungsreihenfolge je Wallet (BMF 06.03.2025 Rn. 103); eine FIFO-Wallet aus mehreren Konten nennt alle Konten (#508).
    heading("Verwendungsreihenfolge je Wallet")
    table(c("Wallet", "Konten", "Verbrauchsfolge (Haltefrist)", "Wertermittlung"),
      lapply(model$wallets, function(item) c(text(item$wallet_label), paste(unlist(item$account_labels), collapse = ", "), "FiFo",
        simple_tax_report_wallet_valuation_text_v1(item))),
      c(70, 90, 40, 77), right = rep(FALSE, 4), empty = "Keine Wallet mit Vorgang oder Bestand in diesem Jahr.")
  }

  if (with_ledger) {
    heading("Summen je Vermögenswert")
    table(c("Vermögenswert", "Veräußerungen", "ohne Wert", "mit Tageswert", "Erlöse nach Gebühr", "Anschaffungskosten", "GuV Brutto", "innerhalb Jahresfrist", "außerhalb Jahresfrist", "Erträge", "Erträge Brutto", "unentgeltlich"),
      lapply(model$totals, function(item) c(text(item$asset_label), as.character(item$disposal_count), as.character(item$disposals_without_value),
        as.character(if (is.null(item$disposals_at_daily_value)) 0L else item$disposals_at_daily_value),
        money(item$proceeds_rounded), money(item$basis_rounded), money(item$gain_rounded), money(item$gain_within_period_rounded),
        money(item$gain_outside_period_rounded), as.character(item$income_count), money(item$income_rounded),
        as.character(if (is.null(item$gratuitous_transfer_count)) 0L else item$gratuitous_transfer_count))),
      c(36, 20, 15, 19, 27, 27, 24, 27, 27, 13, 19, 19), right = c(FALSE, rep(TRUE, 11)), empty = "Keine Veräußerungen, keine unentgeltlichen Abgänge und keine Erträge in diesem Jahr.")

    # Ein Abgang traegt seine Einordnung nach dem Zweck im Titel; ein Verkauf ist ein Verkauf.
    event_title <- function(item) sprintf("%s · %s · %s · Konto %s%s", when(item),
      if (identical(item$disposal_type, "withdrawal") && !is.null(item$treatment_label)) paste("Abgang ·", item$treatment_label)
      else simple_tax_report_type_label_v1(item$disposal_type),
      text(item$asset_label), text(item$account_label), if (is.null(item$institution_label)) "" else paste0(" (", item$institution_label, ")"))
    lot_identifiers <- function(lots) for (lot in lots) {
      paragraph(sprintf("Lot vom %s (%s Stück): Kauf-ID %s%s", day(lot$acquisition_local_date), number(lot$quantity), text(lot$acquisition_identifier$transaction_id),
        if (is.null(lot$acquisition_identifier$note)) "" else paste0(" · Notiz: ", lot$acquisition_identifier$note)), size = 6, indent = 4, col = "grey20")
      split <- simple_tax_report_split_note_v1(lot)
      if (!is.null(split)) paragraph(split, size = 6, indent = 8, col = "grey20")
      for (step in lot$path) paragraph(sprintf("Weg: %s von %s nach %s · Transaktions-ID %s", day(step$local_date), step$from_account_label, step$to_account_label,
        text(step$transaction_id)), size = 6, indent = 8, col = "grey20")
    }

    heading("A. Veräußerungen – je Vorgang mit den verbrauchten Lots")
    if (!length(model$disposals)) paragraph("Keine Veräußerungen in diesem Jahr.", col = "grey35", after = 1)
    for (item in model$disposals) {
      need(26)
      paragraph(event_title(item), size = 8, bold = TRUE, after = 0.3)
      paragraph(if (isTRUE(item$value_recorded)) sprintf(
          "Stückzahl %s · Stückpreis %s · Bruttoerlös %s · Gebühr %s · Erlös nach Gebühr %s · Anschaffungskosten %s · GuV Brutto %s · davon innerhalb der Jahresfrist %s, außerhalb %s",
          number(item$quantity), price(item$unit_price), money(item$gross_amount_rounded), money(item$monetary_fee_rounded), money(item$net_proceeds_rounded),
          money(item$basis_rounded), money(item$gain_rounded), money(item$gain_within_holding_period_rounded), money(item$gain_outside_holding_period_rounded))
        else sprintf("Stückzahl %s · Anschaffungskosten %s · Wert des Abgangs: %s · kein Gewinn ausgewiesen", number(item$quantity), money(item$basis_rounded),
          simple_tax_report_value_source_label_v1(item)),
        size = 7, indent = 2, after = 0.3)
      # Ein Verkauf traegt seinen gebuchten Erloes; genannt wird die Quelle, wo der Wert nicht aus der Buchung stammt.
      if (isTRUE(item$value_recorded) && !is.null(item$value_source) && !identical(item$value_source, "booked"))
        paragraph(paste0("Wert des Abgangs: ", simple_tax_report_value_source_label_v1(item)), size = 7, indent = 2, after = 0.3)
      paragraph(sprintf("Transaktions-ID: %s · Adresse der Gegenseite: %s · Notiz: %s", text(item$transaction_id), text(item$counterparty_address), text(item$note)),
        size = 6.5, indent = 2, col = "grey20", after = 0.6)
      table(c("Kaufdatum", "Art", "Konto der Anschaffung", "Stückzahl", "Kauf: Stückpreis", "Gebühr ant.", "Anschaffungskosten", "Erlös ant.", "GuV Brutto", "Tage", "Fristende", "in Frist"),
        lapply(item$lots, function(lot) c(day(lot$acquisition_local_date), simple_tax_report_type_label_v1(lot$acquisition_type), text(lot$acquisition_account_label),
          number(lot$quantity), price(lot$acquisition_unit_price), money(lot$acquisition_fee_share_rounded), money(lot$basis_rounded),
          money(lot$proceeds_share_rounded), money(lot$gain_rounded), as.character(lot$holding_days), day(lot$holding_period_end_date),
          if (isTRUE(lot$within_holding_period)) "ja" else "nein")),
        c(20, 16, 40, 28, 26, 18, 28, 24, 24, 10, 20, 12), right = c(FALSE, FALSE, FALSE, rep(TRUE, 7), FALSE, FALSE), indent = 2)
      lot_identifiers(item$lots)
      y <- y + 2
    }

    # Spende, Schenkung, Erbschaft: Die Lots verlassen den Bestand ohne Gegenleistung. Dokumentiert werden Menge, Lots und
    # der Wert am Tag - ein Gewinn steht hier nicht, es ist keine Veraeusserung (Festlegung 13.10.2026).
    heading("B. Unentgeltliche Abgänge (Spende, Schenkung, Erbschaft) – keine Veräußerung, nicht steuerpflichtig")
    if (!length(model$gratuitous_transfers)) paragraph("Keine unentgeltlichen Abgänge in diesem Jahr.", col = "grey35", after = 1)
    for (item in model$gratuitous_transfers) {
      need(24)
      paragraph(event_title(item), size = 8, bold = TRUE, after = 0.3)
      paragraph(sprintf("Stückzahl %s · Anschaffungskosten der abgegangenen Lots %s · Wert am Tag des Abgangs: %s", number(item$quantity), money(item$basis_rounded),
        if (isTRUE(item$value_recorded)) sprintf("%s (%s)", money(item$net_proceeds_rounded), simple_tax_report_value_source_label_v1(item))
        else simple_tax_report_value_source_label_v1(item)), size = 7, indent = 2, after = 0.3)
      paragraph(sprintf("Transaktions-ID: %s · Adresse der Gegenseite: %s · Notiz: %s", text(item$transaction_id), text(item$counterparty_address), text(item$note)),
        size = 6.5, indent = 2, col = "grey20", after = 0.6)
      table(c("Kaufdatum", "Art", "Konto der Anschaffung", "Stückzahl", "Kauf: Stückpreis", "Gebühr ant.", "Anschaffungskosten", "Tage gehalten"),
        lapply(item$lots, function(lot) c(day(lot$acquisition_local_date), simple_tax_report_type_label_v1(lot$acquisition_type), text(lot$acquisition_account_label),
          number(lot$quantity), price(lot$acquisition_unit_price), money(lot$acquisition_fee_share_rounded), money(lot$basis_rounded), as.character(lot$holding_days))),
        c(22, 18, 60, 36, 34, 26, 36, 26), right = c(FALSE, FALSE, FALSE, rep(TRUE, 5)), indent = 2)
      lot_identifiers(item$lots)
      y <- y + 2
    }

    heading("C. Erträge")
    table(c("Datum", "Uhrzeit", "Art", "Vermögenswert", "Konto", "Stückzahl", "Gebühr Stück", "nach Gebühr", "Wert je Stück", "Bruttoertrag", "Transaktions-ID"),
      lapply(model$income, function(item) c(day(item$local_date), if (is.null(item$local_time)) "–" else paste(substr(item$local_time, 1L, 5L), text(item$time_zone)),
        simple_tax_report_type_label_v1(item$income_type), text(item$asset_label), text(item$account_label), number(item$quantity), number(item$fee_quantity),
        number(item$net_quantity), price(item$value_per_unit), money(item$gross_income_rounded), text(item$transaction_id))),
      c(19, 20, 16, 30, 30, 32, 24, 32, 24, 22, 24), right = c(rep(FALSE, 5), rep(TRUE, 5), FALSE), empty = "Keine Erträge in diesem Jahr.")

    heading("D. Umschichtungen zwischen eigenen Konten – keine Veräußerung")
    if (!length(model$transfers)) paragraph("Keine Umschichtungen in diesem Jahr.", col = "grey35", after = 1)
    for (item in model$transfers) {
      need(12)
      paragraph(sprintf("%s · %s · von %s nach %s · Stückzahl %s · Gebühr in Stück %s", when(item), text(item$asset_label), text(item$from_account_label),
        text(item$to_account_label), number(item$quantity), number(item$fee_quantity)), size = 7, bold = TRUE, after = 0.2)
      paragraph(sprintf("Transaktions-ID: %s · Adresse der Gegenseite: %s · Notiz: %s", text(item$transaction_id), text(item$counterparty_address), text(item$note)),
        size = 6, indent = 2, col = "grey20", after = 0.2)
      if (isTRUE(item$within_wallet)) {
        # Innerhalb einer FIFO-Wallet (#508) bleibt jedes Lot in der Wallet.
        paragraph(sprintf("Innerhalb der Wallet %s – keine Lots bewegt; die Lots gehören der Wallet.", text(item$wallet_label)), size = 6, indent = 2, after = 1)
      } else
      paragraph(paste("Mitgenommene Lots:", paste(vapply(item$moved_lots, function(lot) sprintf("%s Stück vom %s (%s, Anschaffungskosten %s)", number(lot$quantity),
        day(lot$acquisition_local_date), text(lot$acquisition_account_label), money(lot$basis_rounded)), character(1L)), collapse = "; ")), size = 6, indent = 2, after = 1)
    }

    heading("E. Gebühren in Stück – am Vorgang ausgewiesen, keine Veräußerung")
    table(c("Datum", "Vorgang", "Vermögenswert", "Konto", "Gegenkonto", "Gebühr in Stück", "aus Lots vom", "Anschaffungskosten", "Transaktions-ID des Vorgangs", "Notiz"),
      lapply(model$asset_fees, function(item) c(day(item$local_date), simple_tax_report_type_label_v1(item$event_type), text(item$asset_label), text(item$account_label),
        text(item$related_account_label), number(item$fee_quantity), paste(unique(vapply(item$lots, function(lot) day(lot$acquisition_local_date), character(1L))), collapse = ", "),
        money(item$basis_rounded), text(item$transaction_id), text(item$note))),
      c(19, 18, 30, 30, 30, 24, 24, 32, 40, 36), right = c(rep(FALSE, 5), TRUE, FALSE, TRUE, FALSE, FALSE), empty = "Keine Gebühren in Stück in diesem Jahr.")

    for (stand in sort(names(model$holdings))) {
      heading(sprintf("F. Bestände je Konto und Lot zum %s", day(stand)))
      table(c("Vermögenswert", "Konto", "Stückzahl", "Kaufdatum", "Anschaffungskosten", "Haltedauer [Tage]"),
        lapply(model$holdings[[stand]], function(lot) c(text(lot$asset_label), text(lot$account_label), number(lot$quantity), day(lot$acquisition_local_date),
          money(lot$basis_rounded), as.character(lot$holding_days))),
        c(60, 60, 48, 28, 40, 30), right = c(FALSE, FALSE, TRUE, FALSE, TRUE, TRUE), empty = "Kein Bestand an diesem Stichtag.")
    }

    heading("G. Buchungen dieses Reports ohne Transaktions-ID")
    table(c("Datum", "Uhrzeit", "Art", "Vermögenswert", "Konto", "Gegenkonto", "Stückzahl", "Rolle im Report", "vorhandene Notiz"),
      lapply(model$missing_identifiers, function(item) c(day(item$local_date), if (is.null(item$local_time)) "–" else substr(item$local_time, 1L, 5L),
        simple_tax_report_type_label_v1(item$event_type), text(item$asset_label), text(item$account_label), text(item$related_account_label),
        number(item$quantity), simple_tax_report_role_label_v1(item$roles), text(item$note))),
      c(19, 13, 16, 30, 30, 30, 32, 62, 41), right = c(rep(FALSE, 6), TRUE, FALSE, FALSE), empty = "Jede gezeigte Buchung trägt eine Transaktions-ID.")
  }

  if (with_cash) {
    # Zinsen stehen nur im Report, wenn sie gewaehlt sind; ein Report ohne sie bleibt, wie er war.
    heading(if (with_ledger) "H. Zinsen der Cash-Konten" else "Zinsen der Cash-Konten")
    paragraph("Summe je Konto", size = 8, bold = TRUE, after = 0.5)
    table(c("Institut", "Konto", "Währung", "Gutschriften", "Zinsertrag"),
      lapply(model$interest_totals, function(item) c(if (is.null(item$institution_label)) "ohne Institutsangabe" else item$institution_label,
        text(item$account_label), text(item$currency), as.character(item$interest_count), money(item$income_rounded, item$currency))),
      c(70, 90, 22, 28, 36), right = c(FALSE, FALSE, FALSE, TRUE, TRUE), empty = "Keine Zinsgutschriften in diesem Jahr.")
    paragraph("Je Gutschrift", size = 8, bold = TRUE, after = 0.5)
    table(c("Datum", "Institut", "Konto", "Währung", "Zinsertrag"),
      lapply(model$interest, function(item) c(day(item$local_date), if (is.null(item$institution_label)) "ohne Institutsangabe" else item$institution_label,
        text(item$account_label), text(item$currency), money(item$gross_income_rounded, item$currency))),
      c(24, 70, 90, 22, 36), right = c(FALSE, FALSE, FALSE, FALSE, TRUE), empty = "Keine Zinsgutschriften in diesem Jahr.")
  }
  if (any(unlist(model$asset_types) %in% c("equity", "fund", "cash"))) {
    # Die Quellensteuer steht nur bei Klassen mit Kapitalertraegen; ein Krypto-Report bleibt, wie er war (#432).
    heading(if (with_ledger) "I. Anrechenbare ausländische Quellensteuer" else "Anrechenbare ausländische Quellensteuer")
    table(c("Institut", "Währung", "Betrag"),
      lapply(model$withholding, function(item) c(if (is.null(item$institution_label)) "ohne Institutsangabe" else item$institution_label,
        text(item$currency), money(item$withholding_amount_rounded, item$currency))),
      c(110, 22, 36), right = c(FALSE, FALSE, TRUE), empty = "Für dieses Jahr ist keine Quellensteuer eingetragen.")
  }
  if ("fund" %in% unlist(model$asset_types) && identical(model$status, "ready")) {
    # Vorabpauschalen nur bei Fonds (#431): Zufluss im Jahr und Minderung der Gewinne beim Verkauf.
    heading("J. Vorabpauschalen")
    paragraph("Zufluss in diesem Jahr (berechnet für das Vorjahr, § 18 Abs. 3 InvStG)", size = 8, bold = TRUE, after = 0.5)
    table(c("Fonds", "Konto", "Jahr der Berechnung", "Zufluss am", "Betrag laut Bank", "Anteilen zum 31.12. zugeordnet"),
      lapply(model$advance_lump_sums, function(item) c(text(item$asset_label), text(item$account_label), as.character(item$calculation_year), day(item$local_date),
        money(item$advance_lump_sum_amount_rounded), if (isTRUE(item$allocated_to_lots)) "ja" else "nein – kein Bestand zum 31.12.")),
      c(70, 60, 26, 22, 28, 50), right = c(FALSE, FALSE, FALSE, FALSE, TRUE, FALSE), empty = "Keine Vorabpauschale fließt in diesem Jahr zu.")
    reduced <- Filter(function(item) !is.null(item$advance_lump_sum_deduction) && !identical(item$advance_lump_sum_deduction, "0"), model$disposals)
    paragraph("Minderung des Veräußerungsgewinns (§ 19 Abs. 1 Satz 3 InvStG)", size = 8, bold = TRUE, after = 0.5)
    table(c("Datum", "Fonds", "Konto", "Gewinn", "angesetzte Vorabpauschalen", "Gewinn nach Vorabpauschalen"),
      lapply(reduced, function(item) c(day(item$local_date), text(item$asset_label), text(item$account_label), money(item$gain_rounded),
        money(item$advance_lump_sum_deduction_rounded), money(item$gain_after_advance_lump_sum_rounded))),
      c(22, 70, 60, 30, 36, 36), right = c(FALSE, FALSE, FALSE, TRUE, TRUE, TRUE), empty = "Kein Verkauf in diesem Jahr trägt angesetzte Vorabpauschalen.")
  }
  if (is.function(extra)) extra(list(heading = heading, paragraph = paragraph, table = table, need = need, new_page = new_page,
    money = money, number = number, text = text, price = price, day = day))
  finished <- TRUE
  invisible(list(file = file, page_count = page))
}
