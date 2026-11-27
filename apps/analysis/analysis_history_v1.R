# Verlaeufe aus der veroeffentlichten Tageshistorie (#473) - Portfolio und je Asset. Nur Anzeige: Die Analyse liest das
# Artefakt "portfolio_history" und zeichnet es; sie rechnet nichts nach und ruft nichts ab.
#
# Festlegungen (20.10.2026): oben Gesamtvermoegen, Marktwert, Einstand und Cash, darunter eine eigene
# Flaeche fuer die unrealisierte GuV (eine zweite Groessenordnung, deshalb keine zweite Achse). Abgeleitetes Cash wird
# getrennt gezeichnet: das belegte durchgezogen, die Summe einschliesslich der abgeleiteten Konten gestrichelt - die Summe
# erscheint weiter, mit ihrer Einschraenkung vermerkt (Festlegung 20.10.2026). Je Asset Wert und Einstand, Kurs und Menge,
# Kaeufe und Verkaeufe als Punkte.
#
# Zahlungsfluesse und Zusammensetzung (#480, Festlegungen 20.10.2026): Der externe Netto-Fluss je Tag ueber alle Konten ist
# eine Rechnung, die die Anzeige offenlegt (Kontoaenderung, was Kaeufe/Verkaeufe und Ertraege erklaeren, Lieferungen zum
# Tageswert). "Extern zugeflossen, kumuliert" steht als Linie neben dem Gesamtvermoegen, grosse Fluesse als Punkte darauf;
# der Abstand ist der Anlageerfolg vor Steuern. Die Zusammensetzung stapelt Cash und Assetklassen zum Gesamtvermoegen.
#
# Rendite der Anlage (#481): ohne die Cash-Konten, die ausserhalb der Anlage gefuehrt werden (etwa Giro). Zeitgewichtet
# (TWR, vergleichbar mit Fonds) als Verlauf und je Zeitraum, geldgewichtet (IZF) je Zeitraum; alles vor Steuern. Dazu die
# Zinsrendite je Cash-Konto und die externen Fluesse je Institut zum Abgleich mit den Auszuegen. Gerechnet ist alles in
# der Veroeffentlichung; hier wird nur gezeigt.

ANALYSIS_HISTORY_COLORS_V1 <- c(net_worth = "#2a78d6", market_value = "#eb6834", cost_basis = "#1baf7a", cash_documented = "#eda100", cash = "#eda100",
                                contributed = "#e87ba4")
ANALYSIS_HISTORY_INK_V1 <- c(primary = "#0b0b0b", secondary = "#52514e", muted = "#898781", grid = "#e1e0d9",
                             baseline = "#c3c2b7", surface = "#fcfcfb", positive = "#2a78d6", negative = "#e34948")
ANALYSIS_HISTORY_LABELS_V1 <- c(net_worth = "Gesamtvermögen", market_value = "Marktwert", cost_basis = "Einstand", cash_documented = "Cash belegt",
                                cash = "Cash gesamt", contributed = "Extern zugeflossen")
# Zusammensetzung: feste Stapelfolge von unten nach oben, Farbe folgt der Klasse (Nachbarpaare geprueft, auch ohne Farbe
# getrennt durch Luecke, Legende und Werte im Zeiger). Cash traegt dieselbe Farbe wie im Portfolio-Verlauf.
ANALYSIS_HISTORY_CLASSES_V1 <- list(
  cash = list(label = "Cash", col = "#eda100"), transit = list(label = "Cash unterwegs (Umbuchung)", col = "#eda100", hatch = TRUE),
  fund = list(label = "Fonds und ETF", col = "#2a78d6"),
  equity = list(label = "Aktien", col = "#eb6834"), crypto = list(label = "Krypto", col = "#1baf7a"),
  fx = list(label = "Devisen", col = "#6250d6"), derivative = list(label = "Derivate", col = "#e87ba4"),
  other = list(label = "Rohstoffe und Sonstige", col = "#008300"))
# Zeitraeume (#485): feste Spannen, Kalenderjahre von-bis und ein freier Bereich. Grosse Fluesse werden nicht mehr als Punkt
# markiert - eine feste Schwelle wirkt bei kleinem und grossem Vermoegen verschieden (Festlegung 20.10.2026).
# Laufendes Quartal und laufendes Jahr seit rc.309 (Festlegung 23.10.2026: oft interessiert die Jahres- oder Quartalssicht).
ANALYSIS_HISTORY_PERIODS_V1 <- c("1 Monat" = "1m", "3 Monate" = "3m", "Laufendes Quartal" = "qtd", "Laufendes Jahr" = "ytd",
                                 "1 Jahr" = "1y", "3 Jahre" = "3y", "5 Jahre" = "5y", "Alles" = "all",
                                 "Kalenderjahre" = "years", "Von – bis" = "range")
ANALYSIS_HISTORY_EVENT_LABELS_V1 <- c(buy = "Kauf", sell = "Verkauf", reward = "Reward", stock_dividend = "Stockdividende",
  deposit = "Einlieferung", withdrawal = "Auslieferung", transfer = "Übertrag", dividend = "Dividende", other = "sonstige Buchung")

# Exakte Dezimal- oder Bruchtexte als Zahl - erst die Anzeige rundet.
analysis_history_number_v1 <- function(values) {
  vapply(values, function(value) {
    if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(value)) return(NA_real_)
    text <- as.character(value)
    if (grepl("/", text, fixed = TRUE)) { parts <- strsplit(text, "/", fixed = TRUE)[[1L]]; return(as.numeric(parts[[1L]]) / as.numeric(parts[[2L]])) }
    as.numeric(text)
  }, numeric(1L), USE.NAMES = FALSE)
}

# Anzeige-Einstellungen (#500) aus dem Reiter "Einstellungen" der Data-App: Nachkommastellen in Uebersichten und farbige
# Hinterlegung. Sie gelten fuer diesen App-Prozess (ein Nutzer, lokal) und werden beim Lesen der Tageshistorie gesetzt; Stellen,
# die ausdruecklich Cent zeigen (Buchungen, Lose, Projektion), geben ihre Stellen selbst an.
ANALYSIS_DISPLAY_V1 <- new.env(parent = emptyenv())
ANALYSIS_DISPLAY_V1$digits <- 0L
ANALYSIS_DISPLAY_V1$tint <- TRUE
# Rueckgangszonen (#506): Schwellen in ganzen Prozent unter dem Hoch, festgelegt in Data -> Einstellungen.
ANALYSIS_DISPLAY_V1$zones <- integer()
# Zeitraum, mit dem die Reiter oeffnen (Data -> Einstellungen, seit rc.309).
ANALYSIS_DISPLAY_V1$period <- "all"
# Linien und Kennwerte des Portfolio-Verlaufs (#531 Punkt 2): Wahl im Bild, Vorgabe in Data -> Einstellungen -> Anzeige.
ANALYSIS_HISTORY_LINES_V1 <- c("Gesamtvermögen" = "net_worth", "Marktwert" = "market_value", "Einstand" = "cost_basis", "Cash belegt" = "cash_documented",
                               "Cash gesamt (mit abgeleiteten Salden)" = "cash", "Extern zugeflossen" = "contributed", "Unrealisierte GuV" = "unrealised")
ANALYSIS_DISPLAY_V1$lines <- unname(ANALYSIS_HISTORY_LINES_V1)
# Umfang je Portfolio (#542): die Bausteine eines veroeffentlichten Umfangs (leer = alles an, wie bisher) und der Name der Summe -
# ohne Cash heisst sie ausdruecklich „ohne Cash“, sobald die Reihe kein Cash traegt (Abschalten loescht nichts).
ANALYSIS_DISPLAY_V1$modules <- list()
ANALYSIS_DISPLAY_V1$total_label <- "Gesamtvermögen"
ANALYSIS_HISTORY_CASH_LINES_V1 <- c("cash_documented", "cash")
analysis_scope_off_v1 <- function(module, modules = ANALYSIS_DISPLAY_V1$modules) is.list(modules) && isFALSE(modules[[module]])
analysis_history_labels_v1 <- function() { labels <- ANALYSIS_HISTORY_LABELS_V1; labels[["net_worth"]] <- ANALYSIS_DISPLAY_V1$total_label; labels }
analysis_history_has_cash_v1 <- function(history) {
  series <- if (is.list(history)) history$portfolio else NULL
  cash <- analysis_history_number_v1(series$cash); transit <- analysis_history_number_v1(series$in_transit)
  any(!is.na(cash)) || any(!is.na(transit) & transit > 0)
}
analysis_history_apply_display_v1 <- function(settings) {
  if (!is.list(settings)) return(invisible(FALSE))
  period <- settings$analysis_period
  ANALYSIS_DISPLAY_V1$period <- if (is.character(period) && length(period) == 1L && period %in% ANALYSIS_HISTORY_PERIODS_V1 &&
    !period %in% c("years", "range")) period else "all"
  zones <- suppressWarnings(as.integer(unlist(settings$drawdown_zones)))
  ANALYSIS_DISPLAY_V1$zones <- sort(unique(zones[!is.na(zones) & zones >= 5L & zones <= 95L]))
  digits <- suppressWarnings(as.integer(settings$amount_decimals))
  ANALYSIS_DISPLAY_V1$digits <- if (length(digits) == 1L && !is.na(digits) && digits %in% c(0L, 2L)) digits else 0L
  ANALYSIS_DISPLAY_V1$tint <- !identical(settings$tint, FALSE)
  scope <- settings$portfolio_scope
  ANALYSIS_DISPLAY_V1$modules <- if (is.list(scope) && identical(scope$source, "published") && is.list(scope$modules)) scope$modules else list()
  lines <- intersect(unname(ANALYSIS_HISTORY_LINES_V1), unlist(settings$history_lines))
  ANALYSIS_DISPLAY_V1$lines <- if (length(lines)) lines else unname(ANALYSIS_HISTORY_LINES_V1)
  # Ohne Cash im Umfang stehen die Cash-Linien nicht in der Vorgabe; waehlbar bleiben sie.
  if (analysis_scope_off_v1("cash")) {
    kept <- setdiff(ANALYSIS_DISPLAY_V1$lines, ANALYSIS_HISTORY_CASH_LINES_V1)
    ANALYSIS_DISPLAY_V1$lines <- if (length(kept)) kept else setdiff(unname(ANALYSIS_HISTORY_LINES_V1), ANALYSIS_HISTORY_CASH_LINES_V1)
  }
  invisible(TRUE)
}

analysis_history_eur_v1 <- function(value, digits = ANALYSIS_DISPLAY_V1$digits) {
  # Erst runden, dann formatieren - sonst erschiene ein Rest wie -0,4 als "-0 €".
  rounded <- round(value, digits); rounded[!is.na(rounded) & rounded == 0] <- 0
  ifelse(is.na(value), "–", paste(formatC(rounded, format = "f", digits = digits, big.mark = ".", decimal.mark = ","), "€"))
}

# Raten als Prozent mit Vorzeichen, eine Nachkommastelle.
analysis_history_pct_v1 <- function(value, digits = 1L) {
  ifelse(is.na(value), "–", paste0(ifelse(value < 0, "\u2212", "+"), formatC(abs(value) * 100, format = "f", digits = digits, decimal.mark = ","), " %"))
}

# Erfolgsspalten in Tabellen unaufdringlich hinterlegt (#499): Gewinn blau, Verlust rot - derselbe Farbmodus wie in den Flaechen.
# Gilt fuer Spalten, deren Name hier steht oder mit einem davon beginnt; die Zellen werden zuerst maskiert, dann ausgezeichnet.
ANALYSIS_HISTORY_TINT_COLUMNS_V1 <- c("Anlageerfolg", "realisiert", "Änderung unrealisiert", "Erträge", "Zinsen", "GuV", "TWR", "IZF",
                                      "Mehr-/Minderrendite", "Rendite", "Erfolg", "Wertänderung", "Timing-Effekt", "Wirkung des Cash")
ANALYSIS_HISTORY_TINT_STYLE_V1 <- paste(
  ".pl-tint-gain{background:rgba(42,120,214,.13);border-radius:4px;padding:0 4px;white-space:nowrap}",
  ".pl-tint-loss{background:rgba(227,73,72,.13);border-radius:4px;padding:0 4px;white-space:nowrap}")

.analysis_history_text_sign_v1 <- function(values) {
  text <- trimws(as.character(values)); text[is.na(text)] <- ""
  digits <- gsub("[^0-9]", "", sub("\\s[¹²³⁴⁵⁶⁷⁸⁹]+$", "", text))
  zero <- !nzchar(digits) | !grepl("[1-9]", digits)
  ifelse(zero, 0L, ifelse(grepl("^[\u2212-]", text), -1L, ifelse(grepl("^[+0-9]", text), 1L, 0L)))
}

analysis_history_tint_v1 <- function(table, columns = ANALYSIS_HISTORY_TINT_COLUMNS_V1, tint = ANALYSIS_DISPLAY_V1$tint) {
  if (!is.data.frame(table) || !nrow(table)) return(table)
  # Ohne Hinterlegung (#500) werden die Zellen nur maskiert - die Ausgaben bleiben dieselben HTML-Tabellen.
  tinted <- vapply(names(table), function(name) isTRUE(tint) && any(startsWith(name, columns)), logical(1L))
  for (name in names(table)) {
    values <- as.character(table[[name]])
    cells <- htmltools::htmlEscape(ifelse(is.na(values), "", values))
    if (tinted[[name]]) {
      sign <- .analysis_history_text_sign_v1(values)
      cells <- ifelse(sign > 0, paste0('<span class="pl-tint-gain">', cells, "</span>"),
                      ifelse(sign < 0, paste0('<span class="pl-tint-loss">', cells, "</span>"), cells))
    }
    table[[name]] <- cells
  }
  table
}
.analysis_history_html_v1 <- function(x) x

# Abstand zweier Renditen in Prozentpunkten mit Vorzeichen; "–" ohne Wert.
analysis_history_points_v1 <- function(value) {
  ifelse(is.na(value), "–", paste0(ifelse(value < 0, "\u2212", "+"), formatC(abs(value) * 100, format = "f", digits = 1, decimal.mark = ","), " Pp."))
}

# Satz zu den Renditen (#502): Was TWR und IZF enthalten - Dividenden und Rewards zaehlen mit, wie bei einem thesaurierenden Fonds.
ANALYSIS_HISTORY_RETURNS_INCLUDE_V1 <- paste(
  "TWR und IZF enthalten Dividenden und Rewards (brutto, vor Steuern); die TWR rechnet eine Ausschüttung, als würde sie am Zahltag wieder angelegt –",
  "wie bei einem thesaurierenden Fonds. Order- und Stückgebühren mindern sie.")
# Timing-Effekt (#502): IZF minus TWR je Zeitraum - beide ueber dieselbe Spanne, nicht aufs Jahr gerechnet.
ANALYSIS_HISTORY_TIMING_TEXT_V1 <- paste(
  "„Timing-Effekt“ ist IZF minus TWR über denselben Zeitraum, in Prozentpunkten: Positiv heißt, es war mehr Geld in guten Phasen angelegt,",
  "negativ, mehr in schlechten. Beim Gesamtvermögen stecken darin auch Einzahlungen und Entnahmen ohne Timing-Absicht; je Asset ist es das eigene Kauf- und Verkaufs-Timing.")

# Mit Vorzeichen, fuer die Bestandteile einer Rechnung; das Minus als echtes Minuszeichen.
analysis_history_eur_signed_v1 <- function(value, digits = ANALYSIS_DISPLAY_V1$digits) {
  rounded <- round(value, digits)
  text <- analysis_history_eur_v1(abs(rounded), digits)
  ifelse(is.na(value), "–", paste0(ifelse(rounded < 0, "\u2212", "+"), text))
}

# Welche Tage im Zeitraum liegen. 'range' (zwei Daten) gilt fuer Kalenderjahre, den freien Bereich und den Zoom; fehlt er,
# gilt alles.
analysis_history_window_v1 <- function(days, period, range = NULL) {
  if (!length(days)) return(logical())
  if (as.character(period) %in% c("years", "range")) {
    if (is.null(range) || length(range) != 2L || any(is.na(range))) return(rep(TRUE, length(days)))
    return(days >= min(range) & days <= max(range))
  }
  last <- max(days)
  # Jahre wie in der Veroeffentlichung (#499): ab demselben Kalendertag vor n Jahren (29. Februar -> 28.), dieser Tag zaehlt
  # mit. Bis rc.295 zaehlte die Anzeige 365 Tage zurueck und begann einen Tag spaeter; Linie und Tabelle wichen so ab.
  years <- switch(as.character(period), "1y" = 1L, "3y" = 3L, "5y" = 5L, NA_integer_)
  if (!is.na(years)) {
    start <- as.Date(sprintf("%04d-%s", as.integer(format(last, "%Y")) - years, format(last, "%m-%d")), optional = TRUE)
    if (is.na(start)) start <- as.Date(sprintf("%04d-%s-28", as.integer(format(last, "%Y")) - years, format(last, "%m")))
    return(days >= start)
  }
  # Laufendes Jahr und Quartal: ab dem ersten Tag des Jahres bzw. Quartals, in dem der juengste Tag liegt.
  if (as.character(period) %in% c("ytd", "qtd")) {
    month <- if (identical(as.character(period), "ytd")) 1L else (as.integer(format(last, "%m")) - 1L) %/% 3L * 3L + 1L
    return(days >= as.Date(sprintf("%s-%02d-01", format(last, "%Y"), month)))
  }
  span <- switch(as.character(period), "1m" = 30L, "3m" = 91L, NA_integer_)
  if (is.na(span)) rep(TRUE, length(days)) else days > last - span
}

# --- Ein Zeitraum fuer die ganze Seite (#531 Punkt 1) ------------------------------------------------------------------------
# Die Auswahl oben grenzt alle Bilder und Tabellen ein. Tabellen zeigen nur die veroeffentlichten Zeitraeume, die in ihr liegen:
# bei 2023–2025 diese Jahre, bei „3 Jahre“ die drei Jahre und die Kalenderjahre darin. Ein Zeitraum beginnt mit dem Tag vor
# seinem ersten Tag (Anfangswert), das Kalenderjahr 2024 also mit dem 31.12.2023; das erste Jahr der Historie mit ihrem ersten Tag.

# Erster und letzter Tag der Auswahl in der Tageshistorie; NULL ohne Historie oder ohne Tag darin.
analysis_history_bounds_v1 <- function(history, window) {
  if (is.null(history) || is.null(window) || is.null(history$first_day) || is.null(history$last_day)) return(NULL)
  days <- seq(as.Date(history$first_day), as.Date(history$last_day), by = "day")
  inside <- days[analysis_history_window_v1(days, window$period, window$range)]
  if (!length(inside)) NULL else as.Date(as.numeric(range(inside)))
}

# Welche Spannen in den Grenzen liegen. Liegt keine darin (1 oder 3 Monate, laufendes Quartal, ein kurzer Bereich), gilt die
# kuerzeste, die die Auswahl enthaelt - Attribut "cover". Ohne Grenzen gilt alles.
.analysis_history_select_v1 <- function(start, end, bounds) {
  every <- seq_along(start)
  if (is.null(bounds) || !length(start)) return(structure(every, cover = FALSE))
  inside <- which(start >= bounds[[1L]] - 1 & end <= bounds[[2L]])
  if (length(inside)) return(structure(inside, cover = FALSE))
  around <- which(start <= bounds[[1L]] & end >= bounds[[2L]])
  if (!length(around)) return(structure(integer(), cover = FALSE))
  structure(around[[which.min(as.numeric(end[around] - start[around]))]], cover = TRUE)
}

# Veroeffentlichte Zeitraeume (mit start_day, end_day, label) in der Auswahl. Ein enthaltender statt eines enthaltenen traegt den
# Zusatz im Namen - so steht der Hinweis in der Tabelle selbst.
analysis_history_rows_in_v1 <- function(rows, bounds) {
  if (!length(rows)) return(rows)
  start <- as.Date(vapply(rows, function(row) row$start_day, character(1L)))
  end <- as.Date(vapply(rows, function(row) row$end_day, character(1L)))
  keep <- .analysis_history_select_v1(start, end, bounds)
  cover <- isTRUE(attr(keep, "cover"))
  picked <- rows[keep]
  if (cover) picked <- lapply(picked, function(row) { row$label <- paste(row$label, "– enthält die Auswahl"); row })
  structure(picked, cover = cover)
}

# Der Zeitraum, der genau der Auswahl entspricht ("Alles", 1/3/5 Jahre, laufendes Jahr, Kalenderjahre); NULL, wenn keiner.
analysis_history_exact_v1 <- function(rows, bounds) {
  if (is.null(bounds)) return(NULL)
  for (row in rows) {
    start <- as.Date(row$start_day); end <- as.Date(row$end_day)
    if (end == bounds[[2L]] && start >= bounds[[1L]] - 1 && start <= bounds[[1L]]) return(row)
  }
  NULL
}

# Ein einzelner Zeitraum fuer Bild oder Tabelle: der genaue, sonst der kuerzeste enthaltende (mit Zusatz im Namen).
analysis_history_single_v1 <- function(rows, bounds) {
  exact <- analysis_history_exact_v1(rows, bounds)
  if (!is.null(exact)) return(exact)
  if (is.null(bounds) || !length(rows)) return(NULL)
  start <- as.Date(vapply(rows, function(row) row$start_day, character(1L))); end <- as.Date(vapply(rows, function(row) row$end_day, character(1L)))
  around <- which(start <= bounds[[1L]] & end >= bounds[[2L]])
  if (!length(around)) return(NULL)
  row <- rows[[around[[which.min(as.numeric(end[around] - start[around]))]]]]
  row$label <- paste(row$label, "– enthält die Auswahl")
  row
}

# Zeitraeume zur Wahl, wo es keinen genauen gibt (je Asset sind Kalenderjahre von–bis nicht veroeffentlicht): die in der Auswahl,
# vorgewaehlt der juengste, bei gleichem Ende der laengste. 'exact' ist der Schluessel des genauen Zeitraums oder NULL.
analysis_history_offer_v1 <- function(rows, bounds) {
  exact <- analysis_history_exact_v1(rows, bounds)
  if (!is.null(exact)) return(list(exact = exact$period, choices = stats::setNames(exact$period, exact$label), selected = exact$period))
  picked <- analysis_history_rows_in_v1(rows, bounds)
  if (!length(picked)) return(list(exact = NULL, choices = character(), selected = NULL))
  start <- as.Date(vapply(picked, function(row) row$start_day, character(1L))); end <- as.Date(vapply(picked, function(row) row$end_day, character(1L)))
  best <- order(-as.numeric(end), -as.numeric(end - start))[[1L]]
  keys <- vapply(picked, function(row) row$period, character(1L))
  list(exact = NULL, cover = isTRUE(attr(picked, "cover")), choices = stats::setNames(keys, vapply(picked, function(row) row$label, character(1L))),
       selected = keys[[best]])
}

# Die Wahl dazu: ohne genau passenden Zeitraum ein Feld mit den Zeitraeumen in der Auswahl, sonst nur der Satz, welcher gilt.
analysis_history_offer_ui_v1 <- function(id, offer, typed, window_label) {
  if (!is.null(offer$exact)) return(shiny::p(class = "pl-field-hint", paste0("Zeitraum: ", names(offer$choices)[[1L]], " – wie oben gewählt.")))
  if (!length(offer$choices)) return(shiny::p(class = "pl-field-hint", "Für den gewählten Zeitraum gibt es hier keine Auswertung."))
  shiny::tagList(
    shiny::selectInput(id, if (isTRUE(offer$cover)) "Zeitraum" else "Zeitraum innerhalb der Auswahl", offer$choices,
                       selected = analysis_history_offer_key_v1(offer, typed), selectize = FALSE),
    shiny::p(class = "pl-field-hint", if (isTRUE(offer$cover))
      sprintf("Für „%s“ gibt es hier keine eigene Auswertung; gezeigt ist der kürzeste Zeitraum, der ihn enthält.", window_label) else
      sprintf("Für „%s“ gibt es hier keine eigene Auswertung; zur Wahl stehen die Zeiträume darin.", window_label)))
}

# Der Schluessel, mit dem eine Tabelle rechnet: der genaue Zeitraum, sonst die eigene Wahl, wenn sie zur Auswahl gehoert.
analysis_history_offer_key_v1 <- function(offer, typed) {
  if (!is.null(offer$exact)) return(offer$exact)
  if (is.character(typed) && length(typed) == 1L && typed %in% offer$choices) typed else offer$selected
}

# Die Zeitraeume einer Tabelle der Anlage: die in der Auswahl, bei mehreren Kalenderjahren zuoberst deren Spanne (2023–2025).
analysis_history_periods_in_v1 <- function(periods, spans, bounds) {
  picked <- analysis_history_rows_in_v1(periods, bounds)
  # Nur ohne genau passenden Zeitraum: Bei „Alles“ stuende die Spanne aller Jahre sonst neben „Seit Beginn“.
  if (!is.null(analysis_history_exact_v1(periods, bounds))) return(picked)
  span <- analysis_history_exact_v1(Filter(function(row) grepl("^([0-9]{4})-(?!\\1$)[0-9]{4}$", row$period, perl = TRUE), spans), bounds)
  if (!is.null(span) && !span$period %in% vapply(picked, function(row) row$period, character(1L))) picked <- c(list(span), picked)
  picked
}

# Kalenderjahre in der Auswahl (Zinsen je Jahr); liegt keines darin, das juengste, das sie enthaelt - als Zeichen, Attribut "cover".
analysis_history_years_in_v1 <- function(history, years, bounds) {
  years <- sort(unique(suppressWarnings(as.integer(unlist(years)))))
  if (!length(years) || is.null(bounds)) return(structure(as.character(years), cover = FALSE))
  first <- as.Date(history$first_day); last <- as.Date(history$last_day)
  start <- pmax(as.Date(sprintf("%d-01-01", years)) - 1, first); end <- pmin(as.Date(sprintf("%d-12-31", years)), last)
  keep <- .analysis_history_select_v1(start, end, bounds)
  structure(as.character(years[keep]), cover = isTRUE(attr(keep, "cover")))
}

# Monate in der Auswahl (Fluesse je Konto), als "JJJJ-MM".
analysis_history_months_in_v1 <- function(history, months, bounds) {
  months <- unique(unlist(months))
  if (!length(months) || is.null(bounds)) return(months)
  first <- as.Date(history$first_day); last <- as.Date(history$last_day)
  begin <- as.Date(paste0(months, "-01"))
  year <- as.integer(format(begin, "%Y")); month <- as.integer(format(begin, "%m"))
  finish <- as.Date(sprintf("%d-%02d-01", year + (month == 12L), ifelse(month == 12L, 1L, month + 1L))) - 1
  months[.analysis_history_select_v1(pmax(begin - 1, first), pmin(finish, last), bounds)]
}

# Die Auswahl in Worten, fuer Hinweise.
analysis_history_window_label_v1 <- function(window, bounds = NULL) {
  if (is.null(window)) return("")
  if (identical(window$period, "years") && length(window$range) == 2L) {
    years <- unique(format(window$range, "%Y")); return(paste(years, collapse = "–"))
  }
  if (identical(window$period, "range") || is.null(window$period) || !window$period %in% ANALYSIS_HISTORY_PERIODS_V1) {
    if (is.null(bounds)) return("der gewählte Bereich")
    return(paste(format(bounds[[1L]], "%d.%m.%Y"), "bis", format(bounds[[2L]], "%d.%m.%Y")))
  }
  names(ANALYSIS_HISTORY_PERIODS_V1)[match(window$period, ANALYSIS_HISTORY_PERIODS_V1)]
}

analysis_history_portfolio_frame_v1 <- function(history, period = "all", range = NULL) {
  series <- history$portfolio
  days <- as.Date(unlist(series$day))
  frame <- data.frame(day = days, stringsAsFactors = FALSE)
  for (field in c("net_worth", "market_value", "cost_basis", "unrealised", "cash", "cash_derived")) {
    frame[[field]] <- analysis_history_number_v1(series[[field]])
  }
  frame$complete <- as.logical(unlist(series$complete))
  # Geld zwischen zwei eigenen Konten unterwegs (#481) gehoert zum Vermoegen; die Veroeffentlichung weist es eigens aus.
  transit <- if (is.null(series$in_transit)) rep(NA_real_, nrow(frame)) else analysis_history_number_v1(series$in_transit)
  frame$in_transit <- ifelse(is.na(transit), 0, transit)
  frame$net_worth <- frame$net_worth + frame$in_transit
  frame$cash <- ifelse(is.na(frame$cash), ifelse(frame$in_transit > 0, frame$in_transit, NA_real_), frame$cash + frame$in_transit)
  frame$contributed <- analysis_history_number_v1(series$contributed)
  frame$net_flow <- analysis_history_number_v1(series$net_flow)
  frame$flow_complete <- as.logical(unlist(series$flow_complete))
  for (part in c("cash_change", "trades", "income", "deliveries")) frame[[paste0("flow_", part)]] <- analysis_history_number_v1(series$flow_parts[[part]])
  # Belegt ist, was ein Auszug bestaetigt; die Summe enthaelt zusaetzlich die aus Bewegungen abgeleiteten Salden.
  frame$cash_documented <- ifelse(is.na(frame$cash), NA_real_, frame$cash - ifelse(is.na(frame$cash_derived), 0, frame$cash_derived))
  frame[analysis_history_window_v1(days, period, range), , drop = FALSE]
}

# Bezeichnung und Farbe einer Ebene: aus der Aufteilung, wenn der Rahmen sie traegt, sonst die feste Klasse.
.analysis_history_layer_meta_v1 <- function(frame, key) {
  meta <- attr(frame, "meta")
  if (!is.null(meta) && !is.null(meta[[key]])) meta[[key]] else ANALYSIS_HISTORY_CLASSES_V1[[key]]
}

# Farben eigener Gruppen in fester Folge (dieselben wie die Klassen); was keiner Gruppe gehoert, grau.
ANALYSIS_HISTORY_GROUP_COLORS_V1 <- c("#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#008300")

# Zusammensetzung nach einer Aufteilung eigener Gruppen (#483 Stufe 2): Cash, je Gruppe, nicht zugeordnet.
analysis_history_partition_frame_v1 <- function(history, partition, period = "all", range = NULL) {
  series <- history$portfolio
  days <- as.Date(unlist(series$day))
  frame <- data.frame(day = days, stringsAsFactors = FALSE)
  meta <- list()
  for (key in intersect(c("cash", "transit"), unlist(series$composition$classes))) {
    frame[[key]] <- analysis_history_number_v1(series$composition$values[[key]]); meta[[key]] <- ANALYSIS_HISTORY_CLASSES_V1[[key]]
  }
  groups <- Filter(function(group) group$ordinal %in% unlist(partition$groups), history$groups)
  for (index in seq_along(groups)) {
    key <- paste0("g", groups[[index]]$ordinal)
    frame[[key]] <- analysis_history_number_v1(groups[[index]]$value)
    meta[[key]] <- list(label = groups[[index]]$label,
                        col = if (index <= length(ANALYSIS_HISTORY_GROUP_COLORS_V1)) ANALYSIS_HISTORY_GROUP_COLORS_V1[[index]] else ANALYSIS_HISTORY_INK_V1[["muted"]])
  }
  frame$unassigned <- analysis_history_number_v1(partition$unassigned); meta$unassigned <- list(label = "keiner Gruppe zugeordnet", col = "#c3c2b7")
  layers <- c(intersect(c("cash", "transit"), names(frame)), paste0("g", vapply(groups, function(group) group$ordinal, numeric(1L))), "unassigned")
  frame <- frame[analysis_history_window_v1(days, period, range), , drop = FALSE]
  attr(frame, "classes") <- layers; attr(frame, "meta") <- meta
  frame
}

analysis_history_composition_choices_v1 <- function(history) {
  partitions <- history$partitions
  # Ohne Aufteilung nur die Klassen: paste0("partition:", integer(0)) ergaebe in R einen Wert, die Auswahl zeigte "NA" (bis rc.295).
  if (!length(partitions)) return(c("Assetklassen" = "classes"))
  c("Assetklassen" = "classes", stats::setNames(paste0("partition:", seq_along(partitions)),
    vapply(partitions, function(row) paste("Aufteilung", row$label), character(1L))))
}

analysis_history_composition_frame_v1 <- function(history, period = "all", range = NULL) {
  series <- history$portfolio
  days <- as.Date(unlist(series$day))
  classes <- intersect(names(ANALYSIS_HISTORY_CLASSES_V1), unlist(series$composition$classes))
  frame <- data.frame(day = days, stringsAsFactors = FALSE)
  for (group in classes) frame[[group]] <- analysis_history_number_v1(series$composition$values[[group]])
  frame <- frame[analysis_history_window_v1(days, period, range), , drop = FALSE]
  attr(frame, "classes") <- classes
  frame
}

analysis_history_asset_frame_v1 <- function(asset, period = "all", range = NULL) {
  days <- as.Date(unlist(asset$days$day))
  frame <- data.frame(day = days, quantity = analysis_history_number_v1(asset$days$quantity),
                      unit_value = analysis_history_number_v1(asset$days$unit_value),
                      market_value = analysis_history_number_v1(asset$days$market_value), stringsAsFactors = FALSE)
  # Der Einstand als Stufe: an jedem Tag der Stand nach dem letzten Ereignis bis zu diesem Tag.
  steps <- asset$basis
  step_days <- as.Date(vapply(steps, function(step) step$day, character(1L)))
  step_values <- analysis_history_number_v1(lapply(steps, function(step) step$cost_basis))
  index <- findInterval(as.numeric(frame$day), as.numeric(step_days))
  frame$cost_basis <- ifelse(index > 0L, step_values[pmax(index, 1L)], NA_real_)
  frame$cost_basis[frame$quantity == 0] <- NA_real_
  # Der durchschnittliche Einstandskurs je Einheit: die Gewinnschwelle im Kurs-Panel (#480).
  frame$cost_average <- ifelse(!is.na(frame$cost_basis) & frame$quantity > 0, frame$cost_basis / frame$quantity, NA_real_)
  frame[analysis_history_window_v1(days, period, range), , drop = FALSE]
}

.analysis_history_axis_dates_v1 <- function(days) {
  span <- as.numeric(diff(range(days)))
  if (span > 1460) { at <- seq(as.Date(format(min(days), "%Y-01-01")), max(days), by = "year"); format <- "%Y" }
  else if (span > 120) { at <- seq(as.Date(format(min(days), "%Y-%m-01")), max(days), by = "3 months"); format <- "%m.%Y" }
  else { at <- seq(min(days), max(days), by = "week"); format <- "%d.%m." }
  at <- at[at >= min(days)]
  graphics::axis(1, at = at, labels = format(at, format), col = NA,
                 col.ticks = ANALYSIS_HISTORY_INK_V1[["baseline"]], col.axis = ANALYSIS_HISTORY_INK_V1[["secondary"]], cex.axis = 0.85)
}

.analysis_history_axis_values_v1 <- function(range, side = 2L) {
  at <- pretty(range, n = 5L)
  graphics::abline(h = at, col = ANALYSIS_HISTORY_INK_V1[["grid"]], lwd = 1)
  graphics::axis(side, at = at, labels = analysis_history_axis_eur_v1(at), las = 1, col = NA, col.axis = ANALYSIS_HISTORY_INK_V1[["secondary"]], cex.axis = 0.8)
}

# Beschriftung einer Euro-Achse: mit den eingestellten Stellen, solange die Teilstriche darauf unterscheidbar bleiben. Bei kleinen
# Betraegen (Teilstriche unter einem Euro) stand sonst an jeder Linie "0 €" (#541); dann so viele Nachkommastellen wie noetig.
analysis_history_axis_eur_v1 <- function(at, digits = ANALYSIS_DISPLAY_V1$digits) {
  digits <- as.integer(digits)
  steps <- diff(sort(unique(at)))
  if (length(steps) && min(steps) > 0 && min(steps) < 10^-digits) digits <- min(4L, max(2L, as.integer(ceiling(-log10(min(steps)) - 1e-9))))
  analysis_history_eur_v1(at, digits)
}

# Eine Linie, gestrichelt, wo 'dashed' gilt - je zusammenhaengendem Abschnitt eine eigene Strichart.
.analysis_history_line_v1 <- function(days, values, color, dashed = rep(FALSE, length(values))) {
  ok <- !is.na(values)
  if (!any(ok)) return(invisible(NULL))
  runs <- rle(paste(ok, dashed))
  ends <- cumsum(runs$lengths); starts <- ends - runs$lengths + 1L
  for (index in seq_along(starts)) {
    range <- seq(max(1L, starts[[index]] - 1L), ends[[index]])
    if (!ok[[starts[[index]]]]) next
    graphics::lines(days[range], values[range], col = color, lwd = 2, lty = if (dashed[[starts[[index]]]]) 2L else 1L, lend = "round", ljoin = "round")
  }
}

# Beschriftung am Linienende in Textfarbe, mit kurzem Linienschluessel in Serienfarbe; Kollisionen werden gestreckt.
.analysis_history_end_labels_v1 <- function(x, values, labels, colors) {
  keep <- !is.na(values)
  if (!any(keep)) return(invisible(NULL))
  values <- values[keep]; labels <- labels[keep]; colors <- colors[keep]
  # Auf logarithmischer Skala (Vergleich, #502) liegen die Grenzen des Bilds als log10 vor: dort stapeln, dann zurueckrechnen.
  ylog <- isTRUE(graphics::par("ylog"))
  if (ylog) values <- log10(values)
  order <- order(values); gap <- diff(graphics::par("usr")[3:4]) * 0.07
  placed <- values[order]
  for (index in seq_along(placed)[-1L]) placed[[index]] <- max(placed[[index]], placed[[index - 1L]] + gap)
  if (ylog) placed <- 10^placed
  span <- diff(graphics::par("usr")[1:2])
  for (index in seq_along(order)) {
    position <- order[[index]]
    graphics::segments(x + span * 0.01, placed[[index]], x + span * 0.03, placed[[index]], col = colors[[position]], lwd = 2, xpd = NA)
    graphics::text(x + span * 0.035, placed[[index]], labels[[position]], pos = 4, offset = 0.1, cex = 0.8,
                   col = ANALYSIS_HISTORY_INK_V1[["primary"]], xpd = NA)
  }
}

.analysis_history_text_v1 <- function(value, fallback = "") {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) fallback else as.character(value)
}

# Zeitpunkt der Momentaufnahme in Ortszeit, z. B. "24.10.2026, 14:05 Uhr".
analysis_history_moment_time_v1 <- function(point) {
  at <- suppressWarnings(as.POSIXct(point$at, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  if (is.na(at)) format(point$day, "%d.%m.%Y") else paste0(format(at, "%d.%m.%Y, %H:%M", tz = "Europe/Berlin"), " Uhr")
}

analysis_history_moment_rows_v1 <- function(point, model = NULL) {
  colors <- ANALYSIS_HISTORY_COLORS_V1
  rows <- list(list(label = ANALYSIS_DISPLAY_V1$total_label, value = analysis_history_eur_v1(point$net_worth), color = colors[["net_worth"]]),
               list(label = "Marktwert", value = analysis_history_eur_v1(point$market_value), color = colors[["market_value"]]),
               list(label = "Cash", value = analysis_history_eur_v1(point$cash)),
               list(label = "Unrealisierte GuV", value = analysis_history_eur_signed_v1(point$unrealised)))
  if (!is.null(point$delta) && !is.na(point$delta)) rows <- c(rows, list(list(label = "Kursänderung seit dem letzten Tagesschluss", value = analysis_history_eur_signed_v1(point$delta))))
  notes <- analysis_moment_caveats_v1(model)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = paste0("jetzt · Momentaufnahme ", analysis_history_moment_time_v1(point), " (kein Tagesschluss)"), rows = rows)
}

analysis_history_moment_note_v1 <- function(point, model = NULL) {
  if (is.null(point)) return(NULL)
  analysis_moment_note_v1(if (is.null(model)) point else model, paste0(
    ANALYSIS_DISPLAY_V1$total_label, " ", analysis_history_eur_v1(point$net_worth), " · Marktwert ", analysis_history_eur_v1(point$market_value),
    " · unrealisierte GuV ", analysis_history_eur_signed_v1(point$unrealised),
    if (!is.null(point$delta) && !is.na(point$delta)) paste0(" · seit dem letzten Tagesschluss ", analysis_history_eur_signed_v1(point$delta)) else "", "."))
}

# 'lines' (#531 Punkt 2): welche Linien oben und ob das Feld der unrealisierten GuV darunter erscheint.
analysis_history_plot_portfolio_v1 <- function(frame, now = NULL, lines = unname(ANALYSIS_HISTORY_LINES_V1)) {
  ink <- ANALYSIS_HISTORY_INK_V1; colors <- ANALYSIS_HISTORY_COLORS_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  series <- intersect(c("net_worth", "market_value", "cost_basis", "cash_documented", "contributed"), lines)
  with_cash <- "cash" %in% lines; with_gain <- "unrealised" %in% lines; upper <- length(series) > 0L || with_cash
  if (upper && with_gain) graphics::layout(matrix(1:2), heights = c(3, 1.3))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(if (with_gain) 1.2 else 2.2, 7, 3.6, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2)
  # Beide Teilbilder teilen dieselbe Zeitachse - mit dem Punkt „jetzt“ reicht sie bis zu seinem Tag.
  xlim <- range(c(frame$day, if (!is.null(now)) now$day))
  last <- nrow(frame)
  if (upper) {
    moment_fields <- intersect(c("market_value", "net_worth"), series)
    moment_values <- vapply(moment_fields, function(field) { value <- if (is.null(now)) NULL else now[[field]]
      if (is.null(value) || !length(value)) NA_real_ else as.numeric(value[[1L]]) }, numeric(1L))
    range <- range(c(unlist(frame[c(series, if (with_cash) "cash")]), moment_values), na.rm = TRUE)
    if (!all(is.finite(range))) range <- c(0, 1)
    graphics::plot(frame$day, frame$net_worth, type = "n", xlim = xlim, ylim = range, axes = FALSE, xlab = "", ylab = "")
    .analysis_history_axis_values_v1(range)
    graphics::abline(v = frame$day[!frame$complete], col = grDevices::adjustcolor(ink[["muted"]], 0.18), lwd = 1)
    derived <- !is.na(frame$cash_derived) & frame$cash_derived != 0
    if ("cost_basis" %in% series) .analysis_history_line_v1(frame$day, frame$cost_basis, colors[["cost_basis"]])
    if ("cash_documented" %in% series) .analysis_history_line_v1(frame$day, frame$cash_documented, colors[["cash_documented"]])
    # Die Summe nur dort eigens, wo sie vom belegten Cash abweicht; sonst liegt sie auf derselben Linie. Ohne das belegte Cash ganz.
    cash_shown <- if ("cash_documented" %in% series) derived else rep(TRUE, nrow(frame))
    if (with_cash) .analysis_history_line_v1(frame$day, ifelse(cash_shown, frame$cash, NA_real_), colors[["cash"]], rep(TRUE, nrow(frame)))
    if ("market_value" %in% series) .analysis_history_line_v1(frame$day, frame$market_value, colors[["market_value"]])
    if ("contributed" %in% series) .analysis_history_line_v1(frame$day, frame$contributed, colors[["contributed"]])
    if ("net_worth" %in% series) .analysis_history_line_v1(frame$day, frame$net_worth, colors[["net_worth"]])
    moment_marks <- function(fields, values) for (index in seq_along(fields)) if (!is.na(values[[index]])) {
      graphics::segments(frame$day[[last]], frame[[fields[[index]]]][[last]], now$day, values[[index]], col = colors[[fields[[index]]]], lwd = 1.5, lty = 3)
      graphics::points(now$day, values[[index]], pch = 21, cex = 1.5, lwd = 2, col = colors[[fields[[index]]]], bg = ink[["surface"]])
    }
    if (!is.null(now) && length(moment_fields)) moment_marks(moment_fields, moment_values)
    labelled <- if (with_cash && isTRUE(cash_shown[[last]])) c(series, "cash") else series
    if (length(labelled)) .analysis_history_end_labels_v1(xlim[[2L]], unlist(frame[last, labelled]), analysis_history_labels_v1()[labelled], colors[labelled])
    # Zwei Zeilen: die Reihen, darunter, was Strichart und graue Tage bedeuten.
    top <- graphics::par("usr")[[4]]; step <- diff(graphics::par("usr")[3:4])
    if (length(series)) graphics::legend(graphics::par("usr")[[1]], top + step * 0.17, horiz = TRUE, bty = "n", cex = 0.8, text.col = ink[["secondary"]], xpd = NA,
                                         legend = analysis_history_labels_v1()[series], col = colors[series], lty = 1, lwd = 2, seg.len = 1.6)
    graphics::legend(graphics::par("usr")[[1]], top + step * 0.09, horiz = TRUE, bty = "n", cex = 0.8, text.col = ink[["secondary"]], xpd = NA,
                     legend = c(if (with_cash) "Cash gesamt, mit abgeleiteten Salden (gestrichelt)", "nicht vollständig bewertet", if (!is.null(now)) ANALYSIS_MOMENT_LEGEND_V1),
                     col = c(if (with_cash) colors[["cash"]], grDevices::adjustcolor(ink[["muted"]], 0.5), if (!is.null(now)) ink[["secondary"]]),
                     lty = c(if (with_cash) 2, 1, if (!is.null(now)) NA), lwd = c(if (with_cash) 2, 6, if (!is.null(now)) 2), pch = c(if (with_cash) NA, NA, if (!is.null(now)) 21),
                     pt.bg = ink[["surface"]], pt.cex = 1.2, seg.len = 1.6)
    if (!with_gain) {
      .analysis_history_axis_dates_v1(frame$day)
      return(invisible(.analysis_history_geometry_v1()))
    }
  }
  # Unrealisierte GuV: eigene Flaeche, eigene Skala, Nulllinie; ueber null blau, darunter rot (divergierend).
  graphics::par(mar = c(2.2, 7, if (upper) 1.2 else 3.6, 9.5))
  gain <- frame$unrealised
  span <- range(c(0, gain), na.rm = TRUE)
  if (!is.null(now) && !is.na(now$unrealised)) span <- range(c(span, now$unrealised))
  graphics::plot(frame$day, gain, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  .analysis_history_axis_values_v1(span)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  ok <- !is.na(gain)
  if (any(ok)) {
    positive <- ifelse(ok, pmax(gain, 0), 0); negative <- ifelse(ok, pmin(gain, 0), 0)
    graphics::polygon(c(frame$day, rev(frame$day)), c(positive, rep(0, nrow(frame))), col = grDevices::adjustcolor(ink[["positive"]], 0.12), border = NA)
    graphics::polygon(c(frame$day, rev(frame$day)), c(negative, rep(0, nrow(frame))), col = grDevices::adjustcolor(ink[["negative"]], 0.12), border = NA)
    # Die Linie in Textfarbe ohne Unterbrechung; das Vorzeichen traegt die Flaeche.
    .analysis_history_line_v1(frame$day, gain, ink[["secondary"]])
  }
  if (!is.null(now) && !is.na(now$unrealised)) {
    if (!is.na(gain[[last]])) graphics::segments(frame$day[[last]], gain[[last]], now$day, now$unrealised, col = ink[["secondary"]], lwd = 1.5, lty = 3)
    graphics::points(now$day, now$unrealised, pch = 21, cex = 1.4, lwd = 2, col = ink[["secondary"]], bg = ink[["surface"]])
  }
  .analysis_history_axis_dates_v1(frame$day)
  graphics::mtext("Unrealisierte GuV", side = 3, line = 0.1, adj = 0, cex = 0.8, col = ink[["secondary"]])
  # Am rechten Rand steht der Wert dessen, was dort gezeichnet ist: mit Punkt „jetzt“ dessen Wert, sonst der letzte Tag.
  if (!is.null(now) && !is.na(now$unrealised)) graphics::text(xlim[[2L]], now$unrealised, analysis_history_eur_v1(now$unrealised), pos = 4, cex = 0.8, col = ink[["primary"]], xpd = NA)
  else if (any(ok)) graphics::text(xlim[[2L]], gain[[last]], analysis_history_eur_v1(gain[[last]]), pos = 4, cex = 0.8, col = ink[["primary"]], xpd = NA)
  invisible(.analysis_history_geometry_v1())
}

# Zusammensetzung als gestapelte Flaechen in fester Klassenfolge; 'share' zeigt Anteile statt Euro. Eine schmale Luecke in
# Flaechenfarbe trennt die Schichten.
analysis_history_composition_matrix_v1 <- function(frame, share = FALSE) {
  classes <- attr(frame, "classes")
  values <- vapply(classes, function(group) pmax(ifelse(is.na(frame[[group]]), 0, frame[[group]]), 0), numeric(nrow(frame)))
  if (!is.matrix(values)) values <- matrix(values, nrow = nrow(frame), dimnames = list(NULL, classes))
  if (isTRUE(share)) { total <- rowSums(values); values <- values / ifelse(total > 0, total, 1) * 100 }
  values
}

# Wo der schmale Balken „jetzt“ rechts vom letzten Tag steht (#512): eine Luecke, dann ein Balken von gut einem Prozent der Zeitachse.
analysis_history_moment_bar_v1 <- function(days) {
  width <- max(as.numeric(diff(range(days))) * 0.012, 0.8)
  start <- as.numeric(max(days)) + 0.5 + width * 0.4
  c(start, start + width)
}

analysis_history_plot_composition_v1 <- function(frame, share = FALSE, now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.6, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2)
  classes <- attr(frame, "classes")
  values <- analysis_history_composition_matrix_v1(frame, share)
  top <- t(apply(values, 1L, cumsum)); if (length(classes) == 1L) top <- t(top)
  layers_now <- if (is.null(now)) NULL else unname(now$values[classes])
  if (!is.null(layers_now) && isTRUE(share)) layers_now <- layers_now / ifelse(sum(layers_now) > 0, sum(layers_now), 1) * 100
  at <- pretty(c(0, if (isTRUE(share)) 100 else max(top[, ncol(top)], sum(layers_now), 1)), n = 5L)
  span <- c(0, if (isTRUE(share)) 100 else max(at))
  at <- at[at <= span[[2L]]]
  bar <- if (is.null(now)) NULL else analysis_history_moment_bar_v1(frame$day)
  xlim <- range(c(as.numeric(frame$day), bar))
  graphics::plot(frame$day, top[, ncol(top)], type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "", yaxs = "i")
  graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = if (isTRUE(share)) paste0(at, " %") else analysis_history_axis_eur_v1(at), las = 1, col = NA,
                 col.axis = ink[["secondary"]], cex.axis = 0.8)
  bottom <- rep(0, nrow(frame))
  for (index in seq_along(classes)) {
    upper <- top[, index]
    meta <- .analysis_history_layer_meta_v1(frame, classes[[index]])
    if (isTRUE(meta$hatch)) {
      # Unterwegs: dieselbe Farbe wie Cash, aufgehellt und schraffiert - Teil des Cash, auf keinem Konto gebucht.
      graphics::polygon(c(frame$day, rev(frame$day)), c(upper, rev(bottom)), col = grDevices::adjustcolor(meta$col, 0.35), border = ink[["surface"]], lwd = 1.5)
      graphics::polygon(c(frame$day, rev(frame$day)), c(upper, rev(bottom)), col = meta$col, density = 18, angle = 45, border = NA)
    } else graphics::polygon(c(frame$day, rev(frame$day)), c(upper, rev(bottom)), col = meta$col, border = ink[["surface"]], lwd = 1.5)
    bottom <- upper
  }
  if (!is.null(bar)) {
    # Der Balken „jetzt“: dieselben Schichten in derselben Folge, gepunktet umrandet - kein Tagesschluss.
    lower <- 0
    for (index in seq_along(classes)) {
      meta <- .analysis_history_layer_meta_v1(frame, classes[[index]]); upper <- lower + layers_now[[index]]
      if (upper > lower) graphics::rect(bar[[1L]], lower, bar[[2L]], upper, col = meta$col, border = ink[["surface"]], lwd = 1.5,
                                        density = if (isTRUE(meta$hatch)) 18 else NULL, angle = 45)
      lower <- upper
    }
    graphics::rect(bar[[1L]], 0, bar[[2L]], lower, border = ink[["secondary"]], lty = 3, lwd = 1.2)
    graphics::text(mean(bar), lower, "jetzt", pos = 3, cex = 0.75, col = ink[["secondary"]], xpd = NA)
  }
  .analysis_history_axis_dates_v1(frame$day)
  last <- nrow(frame)
  # Beschriftet wird, was am letzten Tag sichtbar Platz hat; alles traegt die Legende und der Zeiger.
  middle <- top[last, ] - values[last, ] / 2
  visible <- values[last, ] >= diff(span) * 0.04
  .analysis_history_end_labels_v1(xlim[[2L]], ifelse(visible, middle, NA_real_),
                                  vapply(classes, function(group) .analysis_history_layer_meta_v1(frame, group)$label, character(1L)),
                                  vapply(classes, function(group) .analysis_history_layer_meta_v1(frame, group)$col, character(1L)))
  graphics::legend(graphics::par("usr")[[1]], graphics::par("usr")[[4]] + diff(graphics::par("usr")[3:4]) * 0.1, horiz = TRUE, bty = "n",
                   cex = 0.8, text.col = ink[["secondary"]], xpd = NA, pch = 22, pt.cex = 1.6, col = c(rep(ink[["surface"]], length(classes)), if (!is.null(bar)) ink[["secondary"]]),
                   pt.bg = c(vapply(classes, function(group) .analysis_history_layer_meta_v1(frame, group)$col, character(1L)), if (!is.null(bar)) ink[["surface"]]),
                   legend = c(vapply(classes, function(group) .analysis_history_layer_meta_v1(frame, group)$label, character(1L)), if (!is.null(bar)) ANALYSIS_MOMENT_LEGEND_V1))
  geometry <- .analysis_history_geometry_v1(); geometry$bar <- bar
  invisible(geometry)
}

# Zeiger am Balken „jetzt“: je Schicht Wert und Anteil wie an einem Tag.
analysis_history_composition_moment_rows_v1 <- function(frame, now, model = NULL) {
  classes <- attr(frame, "classes"); values <- now$values[classes]; total <- sum(values)
  shown <- rev(classes[values > 0])
  rows <- lapply(shown, function(group) list(label = .analysis_history_layer_meta_v1(frame, group)$label, color = .analysis_history_layer_meta_v1(frame, group)$col,
    value = paste0(analysis_history_eur_v1(values[[group]]), if (total > 0) paste0(" · ", formatC(values[[group]] / total * 100, format = "f", digits = 1, decimal.mark = ","), " %") else "")))
  rows <- c(rows, list(list(label = ANALYSIS_DISPLAY_V1$total_label, value = analysis_history_eur_v1(total)),
                       list(label = "seit dem letzten Tagesschluss", value = analysis_history_eur_signed_v1(total - sum(now$before[classes])))))
  notes <- analysis_moment_caveats_v1(model)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = analysis_moment_title_v1(now), rows = rows)
}

analysis_history_composition_rows_v1 <- function(frame, x) {
  index <- which.min(abs(as.numeric(frame$day) - x))
  classes <- attr(frame, "classes")
  values <- analysis_history_composition_matrix_v1(frame)[index, , drop = FALSE]
  total <- sum(values)
  # Von oben nach unten, wie die Schichten im Bild liegen; Klassen ohne Wert an dem Tag entfallen.
  shown <- rev(classes[values[1L, classes] > 0])
  rows <- lapply(shown, function(group) list(label = .analysis_history_layer_meta_v1(frame, group)$label, color = .analysis_history_layer_meta_v1(frame, group)$col,
    value = paste0(analysis_history_eur_v1(values[1L, group]), if (total > 0) paste0(" · ", formatC(values[1L, group] / total * 100, format = "f", digits = 1, decimal.mark = ","), " %") else "")))
  list(title = format(frame$day[[index]], "%d.%m.%Y"), rows = c(rows, list(list(label = ANALYSIS_DISPLAY_V1$total_label, value = analysis_history_eur_v1(total)))))
}

analysis_history_composition_table_v1 <- function(frame) {
  if (!nrow(frame)) return(data.frame())
  months <- format(frame$day, "%Y-%m")
  keep <- rev(which(!duplicated(months, fromLast = TRUE)))
  classes <- attr(frame, "classes")
  values <- analysis_history_composition_matrix_v1(frame)[keep, , drop = FALSE]
  table <- data.frame(Tag = format(frame$day[keep], "%d.%m.%Y"), check.names = FALSE, stringsAsFactors = FALSE)
  for (group in classes) table[[.analysis_history_layer_meta_v1(frame, group)$label]] <- analysis_history_eur_v1(values[, group])
  table[[ANALYSIS_DISPLAY_V1$total_label]] <- analysis_history_eur_v1(rowSums(values))
  table
}

# Rendite der Anlage (#481): Index, Wert und Zufluss je Tag im Fenster; die Rendite ab Fensterbeginn.
analysis_history_investment_frame_v1 <- function(history, period = "all", range = NULL) {
  series <- history$investment
  days <- as.Date(unlist(history$portfolio$day))
  frame <- data.frame(day = days, value = analysis_history_number_v1(series$value), contributed = analysis_history_number_v1(series$contributed),
                      index = analysis_history_number_v1(series$twr_index), net_flow = analysis_history_number_v1(series$net_flow),
                      valuation_flow = if (is.null(series$valuation_flow)) 0 else analysis_history_number_v1(series$valuation_flow), stringsAsFactors = FALSE)
  frame <- frame[analysis_history_window_v1(days, period, range), , drop = FALSE]
  if (nrow(frame)) frame$twr <- frame$index / frame$index[[1L]] - 1
  if (nrow(frame)) frame$mwr <- analysis_history_mwr_series_v1(frame)
  frame
}

# Geldgewichtete Rendite (IZF) wie in der Veroeffentlichung: der Satz je 'scale' Tage, bei dem der Barwert aller Zahlungen null
# ist; Halbierung, NA ohne Vorzeichenwechsel.
.analysis_history_xirr_v1 <- function(times, amounts, scale) {
  if (!any(amounts > 0) || !any(amounts < 0)) return(NA_real_)
  present <- function(rate) sum(amounts / (1 + rate)^(times / scale))
  low <- -0.9999; high <- 10; value_low <- present(low); value_high <- present(high)
  if (!is.finite(value_low) || !is.finite(value_high) || value_low * value_high > 0) return(NA_real_)
  for (step in seq_len(120L)) {
    middle <- (low + high) / 2; value <- present(middle)
    if ((value > 0) == (value_low > 0)) { low <- middle; value_low <- value } else high <- middle
  }
  (low + high) / 2
}

# IZF seit Beginn des Zeitraums je Stichtag (#499): Anfangswert als Einzahlung, jeder Fluss, Wert am Stichtag als Auszahlung,
# als Rendite ueber die Spanne bis dahin - vergleichbar mit der TWR seit Beginn. Gerechnet an hoechstens 'points' Tagen und am
# letzten Tag; dazwischen NA. Wo TWR und IZF auseinanderlaufen, kam oder ging Geld zu guenstigen oder unguenstigen Zeiten.
analysis_history_mwr_series_v1 <- function(frame, points = 360L) {
  count <- nrow(frame); result <- rep(NA_real_, count)
  if (count < 2L || is.na(frame$value[[1L]])) return(result)
  times <- as.numeric(frame$day - frame$day[[1L]])
  # Fluss wie in der Veroeffentlichung: externer Fluss und Bewertungsuebergang des Tages.
  neutral <- if (is.null(frame$valuation_flow)) 0 else ifelse(is.na(frame$valuation_flow), 0, frame$valuation_flow)
  flows <- ifelse(is.na(frame$net_flow), 0, frame$net_flow) + neutral; flows[[1L]] <- 0
  for (index in unique(c(round(seq(2L, count, length.out = min(points, count - 1L))), count))) {
    if (is.na(frame$value[[index]]) || times[[index]] <= 0) next
    used <- which(flows[seq_len(index)] != 0)
    amounts <- c(-frame$value[[1L]], -flows[used], frame$value[[index]]); at <- c(0, times[used], times[[index]])
    keep <- amounts != 0
    result[[index]] <- .analysis_history_xirr_v1(at[keep], amounts[keep], max(times[[index]], 1))
  }
  result
}

# Je Zeitraum: Werte, Erfolg, zeit- und geldgewichtete Rendite. Annualisiert nur, was laenger als ein Kalenderjahr ist.
analysis_history_periods_table_v1 <- function(history, bounds = NULL) {
  periods <- analysis_history_periods_in_v1(history$investment$periods, history$investment$year_spans, bounds)
  if (!length(periods)) return(data.frame())
  number <- function(field) analysis_history_number_v1(lapply(periods, function(row) row[[field]]))
  long <- vapply(periods, function(row) row$period %in% c("all", "3y", "5y") || grepl("^[0-9]{4}-[0-9]{4}$", row$period), logical(1L))
  # Alle Assets ohne Cash (#502): dieselben Zeitraeume; die Differenz zeigt, was das geparkte Cash kostete oder brachte.
  only <- c(history$investment$assets_only$periods, history$investment$assets_only$year_spans)
  only_twr <- analysis_history_number_v1(lapply(periods, function(row) {
    hit <- Filter(function(other) identical(other$period, row$period), only); if (length(hit) == 1L) hit[[1L]]$twr else NULL }))
  data.frame(Zeitraum = vapply(periods, function(row) paste0(row$label, if (isTRUE(row$complete)) "" else " *"), character(1L)),
             Von = format(as.Date(vapply(periods, function(row) row$start_day, character(1L))), "%d.%m.%Y"),
             Bis = format(as.Date(vapply(periods, function(row) row$end_day, character(1L))), "%d.%m.%Y"),
             Anfangswert = analysis_history_eur_v1(number("start_value")), Endwert = analysis_history_eur_v1(number("end_value")),
             `Zu- und Abflüsse` = analysis_history_eur_signed_v1(number("net_flow")), Anlageerfolg = analysis_history_eur_signed_v1(number("gain")),
             `zeitgewichtet (TWR)` = analysis_history_pct_v1(number("twr")), `geldgewichtet (IZF)` = analysis_history_pct_v1(number("mwr")),
             `TWR p. a.` = analysis_history_pct_v1(ifelse(long, number("twr_annualised"), NA_real_)),
             `IZF p. a.` = analysis_history_pct_v1(ifelse(long, number("mwr_annualised"), NA_real_)),
             `Timing-Effekt (IZF − TWR)` = analysis_history_points_v1(number("mwr") - number("twr")),
             `TWR ohne Cash` = analysis_history_pct_v1(only_twr), `Wirkung des Cash` = analysis_history_points_v1(number("twr") - only_twr),
             check.names = FALSE, stringsAsFactors = FALSE)
}

# Rendite fuer den gewaehlten Zeitraum des Verlaufs (#485): Kalenderjahre aus den vorab veroeffentlichten Spannen (TWR und
# IZF); ein freier Bereich oder Zoom nur mit der TWR aus dem Verlauf - den IZF dafuer muesste die Anzeige selbst rechnen.
analysis_history_span_text_v1 <- function(history, window, frame) {
  if (identical(window$period, "years") && length(window$range) == 2L) {
    key <- paste(format(window$range[[1L]], "%Y"), format(window$range[[2L]], "%Y"), sep = "-")
    hit <- Filter(function(row) identical(row$period, key), history$investment$year_spans)
    if (length(hit) != 1L) return(NULL)
    row <- hit[[1L]]; number <- function(field) analysis_history_number_v1(list(row[[field]]))
    yearly <- if (!is.null(row$twr_annualised)) sprintf(" · p. a.: TWR %s, IZF %s", analysis_history_pct_v1(number("twr_annualised")), analysis_history_pct_v1(number("mwr_annualised"))) else ""
    return(sprintf("%s: zeitgewichtet (TWR) %s · geldgewichtet (IZF) %s%s · Anlageerfolg %s%s", row$label, analysis_history_pct_v1(number("twr")),
                   analysis_history_pct_v1(number("mwr")), yearly, analysis_history_eur_signed_v1(number("gain")), if (isTRUE(row$complete)) "" else " · nicht vollständig bewertete Tage"))
  }
  if (identical(window$period, "range") && !is.null(frame) && nrow(frame) > 1L)
    return(sprintf("%s bis %s: zeitgewichtet (TWR) %s. Den IZF gibt es für ganze Kalenderjahre (Zeitraum „Kalenderjahre“).",
                   format(frame$day[[1L]], "%d.%m.%Y"), format(frame$day[[nrow(frame)]], "%d.%m.%Y"), analysis_history_pct_v1(frame$twr[[nrow(frame)]])))
  NULL
}

# Welche Konten ausserhalb liegen und wie viele noch keine Angabe tragen.
analysis_history_scope_text_v1 <- function(history) {
  accounts <- history$investment$cash_accounts
  outside <- vapply(Filter(function(row) isFALSE(row$in_investment), accounts), function(row) row$label, character(1L))
  unset <- sum(vapply(accounts, function(row) !isTRUE(row$scope_set), logical(1L)))
  paste0("Anlage: ", length(accounts) - length(outside), " von ", length(accounts), " Cash-Konten",
         if (length(outside)) paste0("; außerhalb: ", paste(outside, collapse = ", ")) else "; keines außerhalb", ".",
         if (unset) sprintf(" %d Konto/Konten ohne Festlegung zählen zur Anlage – festlegen in der App „Daten“ unter „2. Stammdaten · Cash-Konten · Anlage und Rendite“.", unset) else "")
}

# `hide_zero` (#531 Punkt 3, Haekchen „Null-Renditen ausblenden“): ohne Konto-Jahre ohne Zinsen, etwa Verrechnungskonten.
analysis_history_interest_table_v1 <- function(history, hide_zero = FALSE, bounds = NULL) {
  rows <- list()
  years <- analysis_history_years_in_v1(history, unique(unlist(lapply(history$investment$cash_accounts, function(account) lapply(account$years, function(year) year$year)))), bounds)
  for (account in history$investment$cash_accounts) for (year in account$years) {
    if (!as.character(year$year) %in% years) next
    interest <- analysis_history_number_v1(list(year$interest)); average <- analysis_history_number_v1(list(year$average_balance))
    if ((is.na(interest) || interest == 0) && (is.na(average) || average == 0)) next
    if (isTRUE(hide_zero) && (is.na(interest) || interest == 0)) next
    rows[[length(rows) + 1L]] <- data.frame(Konto = account$label, Institut = account$institution, Anlage = if (isTRUE(account$in_investment)) "ja" else "nein",
      Jahr = as.character(year$year), Zinsen = analysis_history_eur_v1(interest, 2L), `Ø Saldo` = analysis_history_eur_v1(average),
      `Tage gezählt` = as.character(year$counted_days), `Zinsrendite p. a.` = sub("^\\+", "", analysis_history_pct_v1(analysis_history_number_v1(list(year$yield_annualised)), 2L)),
      check.names = FALSE, stringsAsFactors = FALSE)
  }
  if (!length(rows)) data.frame() else do.call(rbind, rows)
}

# Je Jahr ein Bereich, das neueste offen, darin die Konten (#531 Punkt 3, wie die Steuerangaben je Institut in der Datenbasis).
analysis_history_interest_ui_v1 <- function(history, hide_zero = TRUE, bounds = NULL) {
  frame <- analysis_history_interest_table_v1(history, hide_zero, bounds)
  hidden <- nrow(analysis_history_interest_table_v1(history, FALSE, bounds)) - nrow(frame)
  note <- if (hidden > 0L) shiny::p(class = "pl-field-hint", sprintf("%d %s ohne Zinsen ausgeblendet.", hidden, if (hidden == 1L) "Konto-Jahr" else "Konto-Jahre")) else NULL
  if (!nrow(frame)) return(shiny::tagList(note, shiny::p(class = "pl-field-hint", "Keine Zinsen in der Tageshistorie.")))
  totals <- list()
  for (account in history$investment$cash_accounts) for (year in account$years) {
    value <- analysis_history_number_v1(list(year$interest))
    if (!is.na(value)) totals[[as.character(year$year)]] <- c(totals[[as.character(year$year)]], value)
  }
  years <- sort(unique(as.integer(frame$Jahr)), decreasing = TRUE)
  shown <- analysis_history_years_in_v1(history, lapply(history$investment$cash_accounts, function(account) lapply(account$years, function(year) year$year)), bounds)
  if (isTRUE(attr(shown, "cover"))) note <- shiny::tagList(note, shiny::p(class = "pl-field-hint",
    sprintf("Kein Kalenderjahr liegt ganz im gewählten Zeitraum; gezeigt ist %s, das ihn enthält.", paste(shown, collapse = ", "))))
  shiny::tagList(note, pl_year_groups_v1(lapply(years, function(year) {
    mine <- frame[as.integer(frame$Jahr) == year, setdiff(names(frame), "Jahr"), drop = FALSE]
    list(title = as.character(year),
         summary = paste0(if (nrow(mine) == 1L) "1 Konto" else paste(nrow(mine), "Konten"), " · Zinsen ",
                          analysis_history_eur_v1(sum(totals[[as.character(year)]]), 2L)),
         body = shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", pl_frame_table_v1(mine)))
  })))
}

# Externe Fluesse je Konto (#481): die Konten mit Bewegung, Giro zuerst, dann nach Bezeichnung.
analysis_history_flow_account_choices_v1 <- function(history) {
  rows <- history$investment$accounts_flows
  if (!length(rows)) return(c("Keine Flüsse" = ""))
  labels <- vapply(rows, function(row) row$account, character(1L))
  outside <- vapply(rows, function(row) isFALSE(row$in_investment), logical(1L))
  order <- order(!outside, labels)
  stats::setNames(labels[order], paste0(labels[order], ifelse(outside[order], " · außerhalb der Anlage", "")))
}

# Je Konto die Summen: extern hinein und hinaus, Umbuchungen zwischen eigenen Konten.
analysis_history_flow_accounts_table_v1 <- function(history, bounds = NULL) {
  rows <- history$investment$accounts_flows
  if (!length(rows)) return(data.frame())
  # Im Zeitraum (#531 Punkt 1): die Summen der Monate darin; ueber die ganze Historie die veroeffentlichten Summen.
  whole <- is.null(bounds) || (bounds[[1L]] <= as.Date(history$first_day) && bounds[[2L]] >= as.Date(history$last_day))
  if (!whole) {
    shown <- analysis_history_months_in_v1(history, lapply(rows, function(row) lapply(row$months, function(month) month$month)), bounds)
    rows <- lapply(rows, function(row) {
      months <- Filter(function(month) month$month %in% shown, row$months)
      total <- function(field) { values <- analysis_history_number_v1(lapply(months, function(month) month[[field]])); as.character(sum(values, na.rm = TRUE)) }
      row$months <- months
      for (field in c("inflow", "outflow", "transfer_in", "transfer_out")) row[[field]] <- total(field)
      row
    })
    rows <- Filter(function(row) length(row$months) > 0L, rows)
    if (!length(rows)) return(data.frame())
  }
  number <- function(field) analysis_history_number_v1(lapply(rows, function(row) row[[field]]))
  inflow <- number("inflow"); outflow <- number("outflow")
  data.frame(Konto = vapply(rows, function(row) row$account, character(1L)),
             Anlage = vapply(rows, function(row) if (isTRUE(row$without_cash_account)) "kein Cash-Konto" else if (isTRUE(row$in_investment)) "ja" else "nein", character(1L)),
             `extern hinein` = analysis_history_eur_v1(inflow), `extern hinaus` = analysis_history_eur_v1(outflow),
             `extern netto` = analysis_history_eur_signed_v1(inflow + outflow),
             `Umbuchungen hinein` = analysis_history_eur_v1(number("transfer_in")), `Umbuchungen hinaus` = analysis_history_eur_v1(number("transfer_out")),
             `Monate mit Bewegung` = vapply(rows, function(row) as.character(length(row$months)), character(1L)),
             check.names = FALSE, stringsAsFactors = FALSE)
}

analysis_history_flow_account_table_v1 <- function(history, account, bounds = NULL) {
  hit <- Filter(function(row) identical(row$account, account), history$investment$accounts_flows)
  if (length(hit) != 1L || !length(hit[[1L]]$months)) return(data.frame())
  shown <- analysis_history_months_in_v1(history, lapply(hit[[1L]]$months, function(month) month$month), bounds)
  months <- rev(Filter(function(month) month$month %in% shown, hit[[1L]]$months))
  if (!length(months)) return(data.frame())
  number <- function(field) analysis_history_number_v1(lapply(months, function(row) row[[field]]))
  inflow <- number("inflow"); outflow <- number("outflow")
  data.frame(Monat = format(as.Date(paste0(vapply(months, function(row) row$month, character(1L)), "-01")), "%m.%Y"),
             `extern hinein` = analysis_history_eur_v1(inflow, 2L), `extern hinaus` = analysis_history_eur_v1(outflow, 2L),
             `extern netto` = analysis_history_eur_signed_v1(inflow + outflow, 2L),
             `Umbuchungen hinein` = analysis_history_eur_v1(number("transfer_in"), 2L), `Umbuchungen hinaus` = analysis_history_eur_v1(number("transfer_out"), 2L),
             `Valuta erkannt` = vapply(months, function(row) as.character(row$valuta_count), character(1L)), check.names = FALSE, stringsAsFactors = FALSE)
}

analysis_history_plot_returns_v1 <- function(frame, now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1; colors <- ANALYSIS_HISTORY_COLORS_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  # Oben TWR und IZF, darunter der Timing-Effekt auf eigener Skala mit derselben Zeitachse (#502) - keine zweite Skala im selben Bild.
  graphics::layout(matrix(1:2), heights = c(3, 1.3))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(1.2, 7, 1.6, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2)
  values <- frame$twr * 100
  mwr <- if (is.null(frame$mwr)) rep(NA_real_, nrow(frame)) else frame$mwr * 100
  span <- range(c(0, values, mwr, if (!is.null(now)) now$twr * 100), na.rm = TRUE)
  xlim <- range(c(frame$day, if (!is.null(now)) now$day))
  graphics::plot(frame$day, values, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = paste0(formatC(at, format = "fg", decimal.mark = ","), " %"), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  .analysis_history_line_v1(frame$day, values, colors[["net_worth"]])
  # Geldgewichtet (IZF) daneben, an Stichtagen gerechnet und verbunden (#499).
  sampled <- !is.na(mwr)
  if (sum(sampled) >= 2L) graphics::lines(frame$day[sampled], mwr[sampled], col = colors[["market_value"]], lwd = 2, lend = "round", ljoin = "round")
  last <- nrow(frame)
  if (!is.null(now)) .analysis_moment_mark_v1(frame$day[[last]], values[[last]], now$day, now$twr * 100, colors[["net_worth"]])
  ends <- c(if (!is.null(now)) now$twr * 100 else values[[last]], mwr[[last]])
  labels <- c(paste(if (!is.null(now)) "TWR jetzt" else "TWR", analysis_history_pct_v1(ends[[1L]] / 100)), paste("IZF", analysis_history_pct_v1(mwr[[last]] / 100)))
  shown <- !is.na(ends)
  if (any(shown)) .analysis_history_end_labels_v1(xlim[[2L]], ends[shown], labels[shown], c(colors[["net_worth"]], colors[["market_value"]])[shown])
  if (!is.null(now)) .analysis_moment_legend_v1()
  graphics::mtext("Rendite der Anlage seit Beginn des Zeitraums (vor Steuern): zeitgewichtet (TWR, blau) und geldgewichtet (IZF, orange)", side = 3, line = 0.2,
                  adj = 0, cex = 0.8, col = ink[["secondary"]])
  # Timing-Effekt: IZF minus TWR an den Stichtagen des IZF, ueber null blau, darunter rot.
  graphics::par(mar = c(2.2, 7, 1.2, 9.5))
  timing <- ifelse(sampled, mwr - values, NA_real_)
  known <- which(!is.na(timing))
  limits <- range(c(0, timing), na.rm = TRUE); if (diff(limits) == 0) limits <- limits + c(-1, 1)
  graphics::plot(frame$day, values, type = "n", xlim = xlim, ylim = limits, axes = FALSE, xlab = "", ylab = "")
  at <- pretty(limits, n = 3L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = paste0(formatC(at, format = "fg", decimal.mark = ","), " Pp."), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  if (length(known) >= 2L) {
    days <- frame$day[known]; points <- timing[known]
    graphics::polygon(c(days, rev(days)), c(pmax(points, 0), rep(0, length(days))), col = grDevices::adjustcolor(ink[["positive"]], 0.12), border = NA)
    graphics::polygon(c(days, rev(days)), c(pmin(points, 0), rep(0, length(days))), col = grDevices::adjustcolor(ink[["negative"]], 0.12), border = NA)
    graphics::lines(days, points, col = ink[["secondary"]], lwd = 2, lend = "round", ljoin = "round")
    graphics::text(days[[length(days)]], points[[length(points)]], analysis_history_points_v1(points[[length(points)]] / 100), pos = 4, cex = 0.8,
                   col = ink[["primary"]], xpd = NA)
  }
  .analysis_history_axis_dates_v1(frame$day)
  graphics::mtext("Timing-Effekt (IZF − TWR) seit Beginn des Zeitraums: über null blau, darunter rot", side = 3, line = 0.1, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

analysis_history_returns_moment_rows_v1 <- function(now, model = NULL) {
  rows <- list(list(label = "Rendite seit Beginn des Zeitraums (TWR, jetzt)", value = analysis_history_pct_v1(now$twr), color = ANALYSIS_HISTORY_COLORS_V1[["net_worth"]]),
               list(label = "seit dem letzten Tagesschluss", value = paste0(analysis_history_pct_v1(now$rate, 2L), " · ", analysis_history_eur_signed_v1(now$delta))),
               list(label = "Wert der Anlage (jetzt)", value = analysis_history_eur_v1(now$value)))
  notes <- analysis_moment_caveats_v1(model)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = analysis_moment_title_v1(now), rows = rows)
}

analysis_history_returns_rows_v1 <- function(frame, x) {
  row <- frame[which.min(abs(as.numeric(frame$day) - x)), , drop = FALSE]
  list(title = format(row$day, "%d.%m.%Y"), rows = list(
    list(label = "Rendite seit Beginn des Zeitraums (TWR)", value = analysis_history_pct_v1(row$twr), color = ANALYSIS_HISTORY_COLORS_V1[["net_worth"]]),
    list(label = "geldgewichtet seit Beginn (IZF, letzter Stichtag)", value = {
      known <- which(!is.na(frame$mwr) & frame$day <= row$day); if (length(known)) analysis_history_pct_v1(frame$mwr[[max(known)]]) else "–" },
      color = ANALYSIS_HISTORY_COLORS_V1[["market_value"]]),
    list(label = "Timing-Effekt (IZF − TWR, letzter Stichtag)", value = {
      known <- which(!is.na(frame$mwr) & frame$day <= row$day); if (length(known)) analysis_history_points_v1(frame$mwr[[max(known)]] - frame$twr[[max(known)]]) else "–" }),
    list(label = "Wert der Anlage", value = analysis_history_eur_v1(row$value)),
    list(label = "Extern zugeflossen, kumuliert (Anlage)", value = analysis_history_eur_v1(row$contributed))))
}

# Netto-Sicht (#481, Festlegungen 21.10.2026): projizierte Verkaufsgebuehr und Steuer nach dem Steuermodul des Jahres, in der
# Veroeffentlichung gerechnet und am letzten Tag gegen das Modul geprueft. Renditen (TWR, IZF) bleiben vor Steuern.
# Zwei Netto-Sichten (#501, Festlegung 22.10.2026): je Topf im Jahr (Vorgabe, wie die Jahresrechnung) und je Asset ohne
# Verrechnung (die vorsichtige Obergrenze). "net" ist die Sicht je Topf; "net_asset" die bisherige.
ANALYSIS_HISTORY_VIEWS_V1 <- c("brutto (vor Steuern)" = "gross", "netto, je Topf im Jahr" = "net", "netto, je Asset ohne Verrechnung" = "net_asset")

# Ob eine Sicht netto rechnet - gleich welche.
analysis_history_net_kind_v1 <- function(view) identical(view, "net") || identical(view, "net_asset")

# Die Sicht je Topf in die Felder der Netto-Sicht legen: Bruecke, Liquidationskosten, Netto-Stufen und Steuer je Ereignis.
# Fehlt ein Feld je Topf (nicht verfuegbar), steht das Netto-Feld danach leer - nie still die Sicht je Asset.
analysis_history_pooled_v1 <- function(x) {
  if (!is.list(x)) return(x)
  if (!is.null(names(x))) {
    if (is.list(x$bridge) && !is.null(x$bridge$net)) x$bridge$net <- x$bridge$net_pooled
    if (is.list(x$net) && !is.null(x$net$cost)) { x$net$cost <- x$net$cost_pooled; x$net$realized_net_steps <- x$net$realized_net_steps_pooled }
    if ("net_cost" %in% names(x)) { x["net_cost"] <- list(x$net_cost_pooled); x["net_realized_steps"] <- list(x$net_realized_steps_pooled) }
    if ("tax_pooled" %in% names(x)) x["tax"] <- list(x$tax_pooled)
  }
  for (index in seq_along(x)) if (is.list(x[[index]])) x[[index]] <- analysis_history_pooled_v1(x[[index]])
  x
}

# Die Daten einer Netto-Sicht: je Topf getauscht, je Asset unveraendert.
analysis_history_net_view_v1 <- function(x, view) if (identical(view, "net")) analysis_history_pooled_v1(x) else x
ANALYSIS_HISTORY_NET_REASONS_V1 <- c(
  tax_settings_absent = "In der App „Daten“ sind noch keine Steuereinstellungen gepflegt („4. Steuer“).",
  tax_settings_unreadable = "Die Steuereinstellungen ließen sich nicht lesen.",
  portfolio_ambiguous = "Es gibt mehr als ein Portfolio; die Netto-Sicht kennt nur eines.",
  tax_module_mismatch = "Die Gegenprobe mit dem Steuermodul am letzten Tag wich ab; Netto wird deshalb nicht gezeigt.",
  tax_module_unavailable = "Das Steuermodul ließ sich für die Gegenprobe nicht ausführen.",
  net_failed = "Die Netto-Sicht ließ sich nicht rechnen.", net_setup_failed = "Die Netto-Sicht ließ sich nicht vorbereiten.",
  tax_classification_required = "Für dieses Asset fehlt an manchen Tagen die steuerliche Einordnung („4. Steuer“).",
  tax_classification_invalid = "Die steuerliche Einordnung dieses Assets passt nicht zu einem Verkauf.",
  tax_rate_required = "Für ein Jahr fehlt ein Steuersatz (etwa der persönliche Satz für private Veräußerungen).",
  church_tax_applicability_required = "Für ein Jahr fehlt die Angabe, ob Kirchensteuer anfällt.",
  church_tax_rate_required = "Für ein Jahr fehlt der Kirchensteuersatz.",
  tax_holding_evidence_required = "Für die Haltefrist fehlen die Lose.",
  pool_failed = "Die Rechnung je Topf ließ sich nicht ausführen.", tax_events_unavailable = "Die Rechenblätter eines Jahres ließen sich nicht lesen.",
  net_unavailable = "Die Netto-Sicht ist nicht verfügbar.")

analysis_history_net_note_v1 <- function(history, asset = NULL, view = "net") {
  net <- history$net
  if (is.null(net)) return("Diese Tageshistorie trägt noch keine Netto-Sicht; sie erscheint nach der nächsten Veröffentlichung.")
  reason <- function(code) { text <- ANALYSIS_HISTORY_NET_REASONS_V1[code]; if (is.na(text)) paste("Grund:", code) else unname(text) }
  if (!isTRUE(net$available)) return(paste("Netto nicht verfügbar:", reason(if (is.null(net$reason)) net$status else net$reason)))
  pool <- net$pool
  if (identical(view, "net") && !isTRUE(pool$available))
    return(paste("Netto je Topf nicht verfügbar:", reason(if (is.null(pool$reason)) (if (is.null(pool$status)) "net_unavailable" else pool$status) else pool$reason),
                 "Die Sicht „netto, je Asset ohne Verrechnung“ bleibt wählbar."))
  module <- net$module
  method <- if (identical(view, "net"))
    paste("je Topf im Jahr wie die Jahresrechnung: Gewinne und Verluste eines Topfs verrechnet (Kapitalerträge je Institut, private Veräußerungen,",
          "sonstige Einkünfte), mit Freistellungsauftrag, Freigrenzen und Verlustvorträgen. Jedes Ereignis und jede Position trägt Betrag mal Satz –",
          "ein Verlust zeigt, was er anderswo spart –, Freistellung, Freigrenze und Vorträge anteilig; ein gedachter Verkauf am Tag kostet, was er zum",
          "bereits Realisierten des Jahres hinzufügt.")
  else "je Ereignis konservativ: ohne Freibetrag, ohne Verlustverrechnung – die vorsichtige Obergrenze."
  text <- paste0("Netto = Brutto minus projizierte Verkaufsgebühr und Steuer, ", method, " Nach ",
                 module$plugin_id, " ", if (is.null(module$plugin_version)) "" else module$plugin_version,
                 if (is.null(net$checked_day)) "" else sprintf(", am %s gegen das Modul geprüft (%s Positionen)", format(as.Date(net$checked_day), "%d.%m.%Y"), net$checked_positions),
                 if (identical(view, "net") && !is.null(pool$checked_day)) sprintf("; die Rechnung je Topf jedes Jahr gegen die Jahresrechnung des Moduls und am %s samt gedachtem Verkauf", format(as.Date(pool$checked_day), "%d.%m.%Y")) else "",
                 ". Projektion, keine Steuerberechnung. Renditen (TWR, IZF) bleiben vor Steuern.")
  outside <- unlist(net$not_assessed_years)
  years <- setdiff(unlist(net$warning_years), outside)
  # Seit #496 fuehrt das Modul 2016-2019 in Grundzuegen; die Netto-Sicht rechnet ihre Jahreskette aber weiter ab 2020.
  if (length(years)) text <- paste0(text, " ¹ Für ", paste(range(years), collapse = "–"), " rechnet die Netto-Sicht ohne Steuer (netto = brutto): Ihre Jahreskette beginnt 2020; Jahre davor führt das Steuermodul nur in Grundzügen.")
  if (length(outside)) text <- paste0(text, " ¹ ", paste(outside, collapse = ", "), ": Das Portfolio zählt nicht zur Veranlagung (Daten → „4. Steuer“); dort ist ohne Steuer gerechnet.")
  if (!is.null(asset)) {
    if (is.null(asset$net)) return(text)
    if (!is.null(asset$net$reason)) text <- paste0(text, " Dieses Asset: ", reason(asset$net$reason), " An ", asset$net$blocked_days, " Tagen fehlt deshalb der Netto-Wert.")
    if (!is.null(asset$net$fee_rate)) text <- paste0(text, " Verkaufsgebühr ", formatC(analysis_history_number_v1(list(asset$net$fee_rate)), format = "f", digits = 3, decimal.mark = ","),
                                                   " % vom Wert (", if (identical(asset$net$fee_source, "asset")) "aus den eigenen Käufen und Verkäufen" else "Durchschnitt des Portfolios", ").")
  }
  text
}

# Erfolgsbruecke (#481), vor Steuern: Woraus sich der Anlageerfolg eines Zeitraums zusammensetzt. Einlieferungen bringen
# eine Wertaenderung mit, die nicht hier entstand (abgezogen); Auslieferungen nehmen die bis dahin entstandene mit (zugerechnet);
# Stueckgebuehren bei Uebertraegen mindern den Einstand. Der Rest ist, was die Teile nicht erklaeren.
ANALYSIS_HISTORY_BRIDGE_V1 <- list(
  list(field = "realized", label = "realisiert", sign = 1), list(field = "unrealised_change", label = "Änderung unrealisiert", sign = 1),
  list(field = "income", label = "Dividenden und Rewards", sign = 1), list(field = "interest", label = "Zinsen", sign = 1),
  list(field = "disposal_change", label = "Wertänderung der Auslieferungen", sign = 1),
  list(field = "delivery_change", label = "mitgebrachte Wertänderung der Einlieferungen", sign = -1),
  list(field = "fee_basis", label = "Stückgebühren bei Überträgen", sign = -1), list(field = "rest", label = "Rest", sign = 1))

.analysis_history_bridge_values_v1 <- function(row) {
  vapply(ANALYSIS_HISTORY_BRIDGE_V1, function(part) part$sign * analysis_history_number_v1(list(row$bridge[[part$field]])), numeric(1L))
}

analysis_history_bridge_table_v1 <- function(periods, view = "gross") {
  periods <- Filter(function(row) !is.null(row$bridge), analysis_history_net_view_v1(periods, view))
  if (!length(periods)) return(data.frame())
  values <- do.call(rbind, lapply(periods, .analysis_history_bridge_values_v1))
  frame <- data.frame(Zeitraum = vapply(periods, function(row) paste0(row$label, if (isTRUE(row$complete)) "" else " *"), character(1L)),
                      Anlageerfolg = analysis_history_eur_signed_v1(analysis_history_number_v1(lapply(periods, function(row) row$gain))),
                      check.names = FALSE, stringsAsFactors = FALSE)
  for (index in seq_along(ANALYSIS_HISTORY_BRIDGE_V1)) {
    column <- values[, index]
    # Teile, die in keinem Zeitraum vorkommen, bleiben weg; der Rest steht immer.
    if (!identical(ANALYSIS_HISTORY_BRIDGE_V1[[index]]$field, "rest") && all(is.na(column) | round(column, 2) == 0)) next
    frame[[ANALYSIS_HISTORY_BRIDGE_V1[[index]]$label]] <- analysis_history_eur_signed_v1(column)
  }
  if (analysis_history_net_kind_v1(view)) {
    net <- function(field) analysis_history_number_v1(lapply(periods, function(row) row$bridge$net[[field]]))
    warning <- vapply(periods, function(row) !is.null(row$bridge$net$warning), logical(1L))
    frame[["Steuer auf Realisiertes (Projektion)"]] <- analysis_history_eur_signed_v1(-net("tax_realized"))
    frame[["Steuer auf Erträge (Projektion)"]] <- analysis_history_eur_signed_v1(-net("tax_income"))
    frame[["Änderung Liquidationskosten"]] <- analysis_history_eur_signed_v1(-net("cost_change"))
    frame[["Anlageerfolg netto"]] <- paste0(analysis_history_eur_signed_v1(net("gain")), ifelse(warning, " ¹", ""))
  }
  frame
}

# Zeitraum einer Tabelle beim Oeffnen (Festlegung 23.10.2026: die Voreinstellung gilt fuer alle Zeitraum-Auswahlen). Die
# Tabellen kennen "Seit Beginn", 1/3/5 Jahre und Kalenderjahre: Laufendes Jahr, Quartal und 1 oder 3 Monate werden zum
# juengsten Kalenderjahr - dem kuerzesten Zeitraum, der sie enthaelt.
analysis_history_table_period_v1 <- function(choices, period = ANALYSIS_DISPLAY_V1$period) {
  codes <- unname(as.character(choices))
  if (is.character(period) && length(period) == 1L && period %in% codes) return(period)
  years <- codes[grepl("^[0-9]{4}$", codes)]
  if (isTRUE(period %in% c("ytd", "qtd", "1m", "3m")) && length(years)) return(max(years))
  if ("all" %in% codes) "all" else if (length(codes)) codes[[1L]] else "all"
}

analysis_history_bridge_choices_v1 <- function(history) {
  periods <- Filter(function(row) !is.null(row$bridge), history$investment$periods)
  stats::setNames(vapply(periods, function(row) row$period, character(1L)), vapply(periods, function(row) row$label, character(1L)))
}

# Als Wasserfall: jeder Teil ein Balken ab dem Stand davor, unten der Anlageerfolg ab null. Gewinn blau, Verlust rot. Netto (#481)
# kommen Steuer und die Aenderung der Liquidationskosten als Abzuege dazu, unten steht der Anlageerfolg netto.
analysis_history_plot_bridge_v1 <- function(row, view = "gross") {
  ink <- ANALYSIS_HISTORY_INK_V1
  row <- analysis_history_net_view_v1(row, view)
  values <- .analysis_history_bridge_values_v1(row); values[is.na(values)] <- 0
  keep <- round(values, 2) != 0 | vapply(ANALYSIS_HISTORY_BRIDGE_V1, function(part) part$field %in% c("realized", "unrealised_change", "income"), logical(1L))
  net <- analysis_history_net_kind_v1(view) && !is.null(row$bridge$net) && !is.null(row$bridge$net$gain)
  labels <- c(vapply(ANALYSIS_HISTORY_BRIDGE_V1[keep], function(part) part$label, character(1L)),
              if (net) c("Steuer auf Realisiertes (Projektion)", "Steuer auf Erträge (Projektion)", "Änderung Liquidationskosten"),
              if (net) "Anlageerfolg netto" else "Anlageerfolg")
  values <- values[keep]
  if (net) values <- c(values, -analysis_history_number_v1(list(row$bridge$net$tax_realized)), -analysis_history_number_v1(list(row$bridge$net$tax_income)),
                       -analysis_history_number_v1(list(row$bridge$net$cost_change)))
  gain <- analysis_history_number_v1(list(if (net) row$bridge$net$gain else row$gain)); if (is.na(gain)) gain <- sum(values)
  ends <- cumsum(values); starts <- c(0, utils::head(ends, -1L))
  starts <- c(starts, 0); ends <- c(ends, gain)
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.4, 19, 2.2, 6), mgp = c(3, 0.6, 0), tcl = -0.2)
  span <- range(c(0, starts, ends)); span <- span + c(-1, 1) * diff(span) * 0.08; if (!all(is.finite(span)) || diff(span) == 0) span <- c(-1, 1)
  count <- length(labels); y <- rev(seq_len(count))
  graphics::plot(NA, xlim = span, ylim = c(0.4, count + 0.6), axes = FALSE, xlab = "", ylab = "")
  at <- pretty(span, n = 5L); graphics::abline(v = at, col = ink[["grid"]], lwd = 1); graphics::abline(v = 0, col = ink[["baseline"]], lwd = 1)
  graphics::axis(1, at = at, labels = analysis_history_axis_eur_v1(at), col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::axis(2, at = y, labels = labels, las = 1, col = NA, col.axis = ink[["primary"]], cex.axis = 0.85)
  for (index in seq_len(count)) {
    total <- index == count; value <- ends[[index]] - starts[[index]]
    # Der Anlageerfolg farbig nach Vorzeichen und kraeftig, die Teile heller (#499).
    color <- if (total) (if (isTRUE(gain >= 0)) ink[["positive"]] else ink[["negative"]])
      else grDevices::adjustcolor(if (value >= 0) ink[["positive"]] else ink[["negative"]], 0.6)
    graphics::rect(min(starts[[index]], ends[[index]]), y[[index]] - 0.32, max(starts[[index]], ends[[index]]), y[[index]] + 0.32, col = color, border = ink[["surface"]], lwd = 2)
    if (index < count) graphics::segments(ends[[index]], y[[index]] - 0.32, ends[[index]], y[[index + 1L]] + 0.32, col = ink[["muted"]], lty = 3)
    graphics::text(max(starts[[index]], ends[[index]]), y[[index]], analysis_history_eur_signed_v1(if (total) gain else value), pos = 4, cex = 0.8, col = ink[["primary"]], xpd = NA)
  }
  graphics::mtext(paste0("Erfolgsbrücke · ", row$label, if (net) " · netto (Projektion)" else " · vor Steuern",
                         if (net && !is.null(row$bridge$net$warning)) " · ¹ ohne Steuer gerechnet: netto = brutto" else ""),
                  side = 3, line = 0.6, adj = 0, cex = 0.85, col = ink[["secondary"]])
  invisible(NULL)
}

# Kennzahlen je Intervall (#485): Tag, Woche, Monat oder Quartal im gewaehlten Zeitraum der Seite, dazu Durchschnitt, Median, bestes und
# schlechtestes Intervall und Anteil positiver - fuer die festen Zeitraeume und Kalenderjahre vorab veroeffentlicht.
ANALYSIS_HISTORY_GRANULARITIES_V1 <- c("Tag" = "day", "Woche" = "week", "Monat" = "month", "Quartal" = "quarter")
# Balken waehlbar (Festlegung 06.11.2026): auch GuV realisiert, Ertraege und beides zusammen. Alle vor Steuern (brutto); die Wahl
# brutto/netto kommt mit #543, weil netto je Intervall noch nicht veroeffentlicht ist.
ANALYSIS_HISTORY_INTERVAL_METRICS_V1 <- c(gain = "Anlageerfolg", realized = "GuV realisiert", unrealised_change = "Änderung unrealisiert",
                                          income = "Erträge (mit Zinsen)", realized_income = "GuV realisiert + Erträge", net_flow = "Zu- und Abflüsse",
                                          twr = "zeitgewichtet (TWR)", mwr = "geldgewichtet (IZF)")
ANALYSIS_HISTORY_INTERVAL_BARS_V1 <- c("Anlageerfolg" = "gain", "GuV realisiert" = "realized", "Erträge" = "income", "GuV realisiert + Erträge" = "realized_income",
                                       "zeitgewichtet (TWR)" = "twr", "geldgewichtet (IZF)" = "mwr")

analysis_history_interval_frame_v1 <- function(history, granularity = "month", period = "all", range = NULL) {
  rows <- history$investment$intervals[[granularity]]$rows
  if (!length(rows)) return(NULL)
  frame <- data.frame(key = vapply(rows, function(row) row$key, character(1L)), start = as.Date(vapply(rows, function(row) row$start_day, character(1L))),
                      end = as.Date(vapply(rows, function(row) row$end_day, character(1L))), stringsAsFactors = FALSE)
  for (field in setdiff(names(ANALYSIS_HISTORY_INTERVAL_METRICS_V1), "realized_income")) frame[[field]] <- analysis_history_number_v1(lapply(rows, function(row) row[[field]]))
  frame$realized_income <- frame$realized + frame$income
  days <- as.Date(unlist(history$portfolio$day)); inside <- days[analysis_history_window_v1(days, period, range)]
  if (!length(inside)) return(frame[0L, , drop = FALSE])
  frame[frame$start + 1 >= min(inside) & frame$end <= max(inside), , drop = FALSE]
}

# Welche veroeffentlichte Zusammenfassung zum Zeitraum gehoert; NULL fuer 1 und 3 Monate, das laufende Quartal, freie Bereiche
# und den Zoom. Das laufende Jahr ist das Kalenderjahr bis heute.
analysis_history_interval_window_v1 <- function(window) {
  if (window$period %in% c("all", "1y", "3y", "5y")) return(window$period)
  if (identical(window$period, "ytd")) { year <- format(Sys.Date(), "%Y"); return(paste(year, year, sep = "-")) }
  if (identical(window$period, "years") && length(window$range) == 2L) return(paste(format(window$range[[1L]], "%Y"), format(window$range[[2L]], "%Y"), sep = "-"))
  NULL
}

analysis_history_interval_summary_v1 <- function(history, granularity, key) {
  if (is.null(key)) return(data.frame())
  hit <- Filter(function(row) identical(row$window, key), history$investment$intervals[[granularity]]$summaries)
  if (length(hit) != 1L || !length(hit[[1L]]$metrics)) return(data.frame())
  metrics <- hit[[1L]]$metrics
  rows <- lapply(intersect(names(ANALYSIS_HISTORY_INTERVAL_METRICS_V1), names(metrics)), function(field) {
    item <- metrics[[field]]; rate <- field %in% c("twr", "mwr")
    show <- function(value) { number <- analysis_history_number_v1(list(value)); if (rate) analysis_history_pct_v1(number, 2L) else analysis_history_eur_signed_v1(number) }
    data.frame(Kennzahl = ANALYSIS_HISTORY_INTERVAL_METRICS_V1[[field]], Durchschnitt = show(item$mean), Median = show(item$median),
               `bestes` = show(item$best), `schlechtestes` = show(item$worst),
               `Anteil positiv` = paste0(formatC(analysis_history_number_v1(list(item$positive_share)) * 100, format = "f", digits = 0), " %"),
               Anzahl = as.character(item$count), check.names = FALSE, stringsAsFactors = FALSE)
  })
  do.call(rbind, rows)
}

analysis_history_plot_intervals_v1 <- function(frame, metric = "gain", now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1; rate <- metric %in% c("twr", "mwr")
  values <- frame[[metric]] * if (rate) 100 else 1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.2, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2)
  # Die Momentaufnahme kennt seit dem letzten Tagesschluss nur Anlageerfolg und Rendite; fuer GuV realisiert und Ertraege gibt es dort
  # keinen Wert und keinen Balken (bis rc.390 brach die Grafik daran ab: leerer Wert in der Pruefung).
  current <- if (is.null(now) || !is.numeric(now[[metric]]) || length(now[[metric]]) != 1L) NA_real_ else now[[metric]] * if (rate) 100 else 1
  span <- range(c(0, values, current), na.rm = TRUE); if (!all(is.finite(span)) || diff(span) == 0) span <- c(-1, 1)
  bar <- if (is.null(now) || is.na(current)) NULL else analysis_history_moment_bar_v1(c(frame$start, frame$end))
  graphics::plot(range(c(as.numeric(frame$start), as.numeric(frame$end), bar)), span, type = "n", axes = FALSE, xlab = "", ylab = "")
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = if (rate) paste0(formatC(at, format = "fg", decimal.mark = ","), " %") else analysis_history_axis_eur_v1(at),
                 las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  # Ein Balken je Intervall ueber seine Tage; zwischen den Balken bleibt eine schmale Luecke in Flaechenfarbe.
  left <- as.numeric(frame$start) + 0.5; right <- as.numeric(frame$end) + 0.5
  ok <- !is.na(values)
  # Ohne einen einzigen Wert (Kennzahl im Zeitraum nicht veroeffentlicht) steht ein Hinweis statt der Balken; rect() bricht sonst ab.
  if (any(ok)) graphics::rect(left[ok], 0, right[ok], values[ok], col = ifelse(values[ok] >= 0, ink[["positive"]], ink[["negative"]]),
                              border = if (nrow(frame) <= 120L) ink[["surface"]] else NA, lwd = 1)
  else graphics::text(mean(range(c(left, right))), mean(span), "Für diese Kennzahl gibt es im Zeitraum keine Werte.", cex = 0.85, col = ink[["secondary"]])
  if (!is.null(bar)) {
    # Seit dem letzten Tagesschluss: hell gefuellt, gepunktet umrandet - kein abgeschlossenes Intervall.
    color <- if (current >= 0) ink[["positive"]] else ink[["negative"]]
    graphics::rect(bar[[1L]], 0, bar[[2L]], current, col = grDevices::adjustcolor(color, 0.3), border = color, lty = 3, lwd = 1.4)
    graphics::text(mean(bar), max(current, 0), "jetzt", pos = 3, cex = 0.75, col = ink[["secondary"]], xpd = NA)
  }
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  .analysis_history_axis_dates_v1(c(frame$start, frame$end))
  graphics::mtext(paste(ANALYSIS_HISTORY_INTERVAL_METRICS_V1[[metric]], "je Intervall · brutto (vor Steuern) · Gewinn blau, Verlust rot",
                        if (!is.null(bar)) "· rechts gepunktet: seit dem letzten Tagesschluss (Momentaufnahme)" else ""), side = 3, line = 0.6,
                  adj = 0, cex = 0.8, col = ink[["secondary"]])
  geometry <- .analysis_history_geometry_v1(); geometry$bar <- bar
  invisible(geometry)
}

analysis_history_interval_moment_rows_v1 <- function(now, model = NULL) {
  rows <- list(list(label = "Anlageerfolg seit dem letzten Tagesschluss", value = analysis_history_eur_signed_v1(now$gain, 2L)),
               list(label = "Rendite seit dem letzten Tagesschluss", value = analysis_history_pct_v1(now$twr, 2L)))
  notes <- analysis_moment_caveats_v1(model)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = analysis_moment_title_v1(now), rows = rows)
}

analysis_history_interval_rows_v1 <- function(frame, x) {
  index <- which(as.numeric(frame$start) + 0.5 <= x & as.numeric(frame$end) + 0.5 >= x)
  if (!length(index)) index <- which.min(abs((as.numeric(frame$start) + as.numeric(frame$end)) / 2 - x))
  row <- frame[index[[1L]], , drop = FALSE]
  title <- if (identical(row$start + 1, row$end)) format(row$end, "%d.%m.%Y") else sprintf("%s bis %s", format(row$start + 1, "%d.%m.%Y"), format(row$end, "%d.%m.%Y"))
  rows <- lapply(names(ANALYSIS_HISTORY_INTERVAL_METRICS_V1), function(field) {
    value <- row[[field]]
    list(label = ANALYSIS_HISTORY_INTERVAL_METRICS_V1[[field]], value = if (field %in% c("twr", "mwr")) analysis_history_pct_v1(value, 2L) else analysis_history_eur_signed_v1(value, 2L))
  })
  list(title = title, rows = Filter(function(item) !identical(item$value, "–") || item$label == "Anlageerfolg", rows))
}

analysis_history_interval_table_v1 <- function(frame) {
  if (is.null(frame) || !nrow(frame)) return(data.frame())
  frame <- frame[rev(seq_len(nrow(frame))), , drop = FALSE]
  data.frame(Von = format(frame$start + 1, "%d.%m.%Y"), Bis = format(frame$end, "%d.%m.%Y"), Anlageerfolg = analysis_history_eur_signed_v1(frame$gain, 2L),
             `GuV realisiert` = analysis_history_eur_signed_v1(frame$realized, 2L), `Änderung unrealisiert` = analysis_history_eur_signed_v1(frame$unrealised_change, 2L),
             `Erträge (mit Zinsen)` = analysis_history_eur_signed_v1(frame$income, 2L),
             `GuV realisiert + Erträge` = analysis_history_eur_signed_v1(frame$realized_income, 2L), `Zu- und Abflüsse` = analysis_history_eur_signed_v1(frame$net_flow, 2L),
             `TWR` = analysis_history_pct_v1(frame$twr, 2L), `IZF` = analysis_history_pct_v1(frame$mwr, 2L), check.names = FALSE, stringsAsFactors = FALSE)
}

# Wo die Zeitachse im Bild liegt - fuer Zeiger und Klick. Shiny liefert bei mehreren Teilgrafiken mit R-Bordmitteln keine
# Achsenzuordnung, nur Pixel; alle Teilgrafiken teilen Zeitachse und Seitenraender, die letzte gilt deshalb fuer alle.
.analysis_history_geometry_v1 <- function() {
  usr <- graphics::par("usr")[1:2]
  list(usr = usr, px = graphics::grconvertX(usr, "user", "device"))
}

# Wie viele Tage 'pixels' Bildpunkte der Zeitachse umfassen.
analysis_history_pixel_days_v1 <- function(geometry, pixels) {
  if (is.null(geometry)) return(0)
  pixels * abs(diff(geometry$usr) / diff(geometry$px))
}

# Ein aufgezogener Bereich (Bildpunkte) als zwei Tage; NULL ohne Zuordnung oder fuer weniger als zwei Tage.
analysis_history_zoom_days_v1 <- function(geometry, x0, x1) {
  if (is.null(geometry) || !is.numeric(x0) || !is.numeric(x1)) return(NULL)
  at <- function(x) geometry$usr[[1L]] + (x - geometry$px[[1L]]) / diff(geometry$px) * diff(geometry$usr)
  days <- sort(as.Date(round(c(at(x0), at(x1))), origin = "1970-01-01"))
  if (as.numeric(diff(days)) < 2) NULL else days
}

# Ein Pixel im Bild als Tag (Zahl wie as.numeric(Date)); NULL ohne Zuordnung.
analysis_history_pixel_day_v1 <- function(geometry, event) {
  if (is.null(geometry) || is.null(event) || !is.list(event$coords_img) || !is.numeric(event$coords_img$x)) return(NULL)
  geometry$usr[[1L]] + (event$coords_img$x - geometry$px[[1L]]) / diff(geometry$px) * diff(geometry$usr)
}

# Werte direkt in der Grafik (#480): eine senkrechte Linie am Zeiger und ein Kasten mit den Tageswerten, als HTML ueber dem
# Bild - das Bild selbst wird dafuer nicht neu gezeichnet. 'rows' sind Bezeichnung, Wert und optional die Serienfarbe.
.analysis_history_quantity_v1 <- function(value) {
  if (is.null(value) || is.na(value)) return("–")
  trimws(formatC(value, format = "fg", digits = 10, big.mark = ".", decimal.mark = ","))
}

.analysis_history_box_v1 <- function(event, title, rows, line = TRUE, box = TRUE, geometry = NULL) {
  if (is.null(event) || is.null(event$coords_css)) return(NULL)
  x <- round(as.numeric(event$coords_css$x)); y <- round(as.numeric(event$coords_css$y))
  # Rechts im Bild klappt der Kasten nach links; die Grenze ist das Ende der Zeitachse in CSS-Pixeln.
  ratio <- if (is.list(event$coords_img) && is.numeric(event$coords_img$x) && x > 0) event$coords_img$x / x else 1
  width <- if (!is.null(geometry)) geometry$px[[2L]] / ratio else Inf
  side <- if (x > width * 0.6) sprintf("right:calc(100%% - %dpx + 14px)", x) else sprintf("left:%dpx", x + 14L)
  panel <- if (!box) NULL else shiny::div(style = paste0("position:absolute;top:", max(4L, y - 12L), "px;", side, ";background:rgba(252,252,251,.97);border:1px solid #c3c2b7;",
                                   "border-radius:8px;padding:6px 10px;font-size:12px;line-height:1.5;color:#0b0b0b;box-shadow:0 2px 10px rgba(0,0,0,.10);white-space:nowrap;z-index:2"),
    shiny::strong(title),
    lapply(rows, function(row) shiny::div(
      if (!is.null(row$color)) shiny::span(style = paste0("display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle;background:", row$color)),
      shiny::span(style = "color:#52514e", paste0(row$label, " ")), row$value)))
  shiny::tagList(if (line) shiny::div(style = paste0("position:absolute;left:", x, "px;top:0;bottom:0;width:1px;background:#52514e;opacity:.55")), panel)
}

# Der Zeiger zeigt die gewaehlten Linien und Kennwerte (#531 Punkt 2); der Zufluss bringt seine Rechnung des Tages mit.
analysis_history_portfolio_rows_v1 <- function(frame, x, lines = unname(ANALYSIS_HISTORY_LINES_V1)) {
  row <- frame[which.min(abs(as.numeric(frame$day) - x)), , drop = FALSE]
  colors <- ANALYSIS_HISTORY_COLORS_V1; labels <- analysis_history_labels_v1()
  rows <- lapply(intersect(c("net_worth", "market_value", "cost_basis", "cash_documented"), lines), function(field)
    list(label = labels[[field]], value = analysis_history_eur_v1(row[[field]]), color = colors[[field]]))
  if ("cash" %in% lines && (!"cash_documented" %in% lines || (!is.na(row$cash_derived) && row$cash_derived != 0)))
    rows <- c(rows, list(list(label = "Cash gesamt", value = paste0(analysis_history_eur_v1(row$cash), if (!is.na(row$cash_derived) && row$cash_derived != 0)
      paste0(" (davon abgeleitet ", analysis_history_eur_v1(row$cash_derived), ")") else ""), color = colors[["cash"]])))
  if (isTRUE(row$in_transit > 0) && any(c("net_worth", "cash") %in% lines)) rows <- c(rows, list(list(label = "davon unterwegs zwischen eigenen Konten", value = analysis_history_eur_v1(row$in_transit))))
  if ("unrealised" %in% lines) rows <- c(rows, list(list(label = "Unrealisierte GuV", value = analysis_history_eur_v1(row$unrealised))))
  flows <- "contributed" %in% lines
  if (flows && !is.na(row$contributed)) rows <- c(rows, list(
    list(label = "Extern zugeflossen, kumuliert", value = analysis_history_eur_v1(row$contributed), color = colors[["contributed"]]),
    list(label = "Anlageerfolg seit Beginn (vor Steuern)", value = analysis_history_eur_signed_v1(row$net_worth - row$contributed))))
  # Die Rechnung des Tages, sobald etwas floss oder eine Buchung Geld bewegte.
  parts <- c(row$flow_cash_change, row$flow_trades, row$flow_income, row$flow_deliveries)
  # Die Kontoaenderung steht immer, die uebrigen Teile nur, wo sie etwas beitragen - steht sie allein, haben keine Buchungen
  # das Geld bewegt (oft ein Kontostart oder das Ende einer Auszugsluecke).
  if (flows && !is.na(row$net_flow) && (row$net_flow != 0 || any(!is.na(parts) & parts != 0))) {
    rows <- c(rows, list(list(label = "Externer Fluss des Tages", value = analysis_history_eur_signed_v1(row$net_flow), color = colors[["contributed"]]),
                         list(label = "\u2003Kontoänderung", value = analysis_history_eur_signed_v1(row$flow_cash_change))))
    for (part in list(list("flow_trades", "\u2003davon erklärt durch Käufe und Verkäufe"), list("flow_income", "\u2003davon erklärt durch Erträge (Dividenden, Zinsen)"),
                      list("flow_deliveries", "\u2003dazu Ein- und Auslieferungen (Tageswert)")))
      if (!is.na(row[[part[[1L]]]]) && row[[part[[1L]]]] != 0) rows <- c(rows, list(list(label = part[[2L]], value = analysis_history_eur_signed_v1(row[[part[[1L]]]]))))
  }
  if (flows && isFALSE(row$flow_complete)) rows <- c(rows, list(list(label = "Hinweis", value = "Fluss unvollständig: Buchung in fremder Währung oder ohne Betrag")))
  if (!isTRUE(row$complete)) rows <- c(rows, list(list(label = "Hinweis", value = "nicht vollständig bewertet")))
  list(title = format(row$day, "%d.%m.%Y"), rows = rows)
}

# Die Werte als Tabelle, je Monatsende - fuer Leser, die nicht vom Bild ablesen wollen oder koennen.
analysis_history_month_table_v1 <- function(frame) {
  if (!nrow(frame)) return(data.frame())
  months <- format(frame$day, "%Y-%m")
  rows <- frame[!duplicated(months, fromLast = TRUE), , drop = FALSE]
  flows <- tapply(ifelse(is.na(frame$net_flow), 0, frame$net_flow), months, sum)
  rows$month_flow <- as.numeric(flows[format(rows$day, "%Y-%m")])
  rows <- rows[rev(seq_len(nrow(rows))), , drop = FALSE]
  table <- data.frame(Tag = format(rows$day, "%d.%m.%Y"), Gesamtvermögen = analysis_history_eur_v1(rows$net_worth),
             Marktwert = analysis_history_eur_v1(rows$market_value), Einstand = analysis_history_eur_v1(rows$cost_basis),
             `Cash belegt` = analysis_history_eur_v1(rows$cash_documented),
             `Cash gesamt` = paste0(analysis_history_eur_v1(rows$cash), ifelse(!is.na(rows$cash_derived) & rows$cash_derived != 0,
                                    paste0(" (davon abgeleitet ", analysis_history_eur_v1(rows$cash_derived), ")"), "")),
             `Unrealisierte GuV` = analysis_history_eur_v1(rows$unrealised),
             `Extern zugeflossen im Monat` = analysis_history_eur_signed_v1(rows$month_flow),
             `Extern zugeflossen, kumuliert` = analysis_history_eur_v1(rows$contributed),
             `Vollständig bewertet` = ifelse(rows$complete, "ja", "nein"), check.names = FALSE, stringsAsFactors = FALSE)
  names(table)[[2L]] <- ANALYSIS_DISPLAY_V1$total_label
  table
}

# Zeitraum (#485, seit #531 einer fuer die ganze Seite): feste Spannen, Kalenderjahre von-bis oder ein freier Bereich. Ein im
# Bild aufgezogener Bereich vergroessert darueber hinaus (Zoom), ein Doppelklick setzt ihn zurueck.
analysis_history_period_ui_v1 <- function(prefix, label = "Zeitraum", selected = "all") shiny::div(class = "pl-period",
  shiny::radioButtons(paste0(prefix, "_period"), label, ANALYSIS_HISTORY_PERIODS_V1, selected = selected, inline = TRUE),
  shiny::conditionalPanel(sprintf("input['%s_period'] == 'years'", prefix), shiny::div(class = "pl-form-grid",
    shiny::selectInput(paste0(prefix, "_year_from"), "von Jahr", c("Bitte warten" = ""), selectize = FALSE),
    shiny::selectInput(paste0(prefix, "_year_to"), "bis Jahr", c("Bitte warten" = ""), selectize = FALSE))),
  shiny::conditionalPanel(sprintf("input['%s_period'] == 'range'", prefix),
    shiny::dateRangeInput(paste0(prefix, "_range"), "von – bis", format = "dd.mm.yyyy", language = "de", separator = "bis", weekstart = 1)),
  shiny::p(class = "pl-field-hint", "Im Bild einen Bereich mit gedrückter Maustaste aufziehen vergrößert ihn; ein Doppelklick ins Bild setzt zurück."))

# Eine Grafik, in der sich ein Bereich aufziehen laesst. Shiny ordnet bei mehreren Teilgrafiken keinen Bereich zu; das
# Skript meldet deshalb die Bildpunkte, der Server rechnet sie wie beim Zeiger in Tage um.
analysis_history_zoomable_v1 <- function(prefix, plot, ...) shiny::div(class = "pl-zoomable", style = "position:relative",
  `data-zoom-input` = paste0(prefix, "_zoom"), `data-zoom-plot` = plot, ...)

analysis_history_zoom_script_v1 <- function() shiny::tagList(
  shiny::tags$style(shiny::HTML(".pl-zoomable img{user-select:none;-webkit-user-drag:none}.pl-zoom-band{position:absolute;top:0;bottom:0;background:rgba(42,120,214,.12);border-left:1px solid #2a78d6;border-right:1px solid #2a78d6;pointer-events:none;z-index:3}")),
  shiny::tags$script(shiny::HTML(paste0(
    "(function(){",
    "document.addEventListener('mousedown',function(ev){var img=ev.target;if(!img||img.tagName!=='IMG'||ev.button!==0)return;",
    "var box=img.closest('.pl-zoomable');if(!box)return;ev.preventDefault();var start=ev.clientX,rect=img.getBoundingClientRect(),band=null,moved=false;",
    "function move(e){if(!moved&&Math.abs(e.clientX-start)<6)return;moved=true;if(!band){band=document.createElement('div');band.className='pl-zoom-band';box.appendChild(band);}",
    "var a=Math.max(rect.left,Math.min(start,e.clientX)),b=Math.min(rect.right,Math.max(start,e.clientX)),off=box.getBoundingClientRect().left;",
    "band.style.left=(a-off)+'px';band.style.width=(b-a)+'px';}",
    "function up(e){document.removeEventListener('mousemove',move);document.removeEventListener('mouseup',up);if(band)band.remove();",
    "if(!moved||!window.Shiny)return;var ratio=img.naturalWidth/rect.width,a=Math.max(rect.left,Math.min(start,e.clientX)),b=Math.min(rect.right,Math.max(start,e.clientX));",
    "Shiny.setInputValue(box.dataset.zoomInput,{plot:box.dataset.zoomPlot,x0:(a-rect.left)*ratio,x1:(b-rect.left)*ratio,nonce:Math.random()},{priority:'event'});}",
    "document.addEventListener('mousemove',move);document.addEventListener('mouseup',up);});",
    "document.addEventListener('dblclick',function(ev){var box=ev.target&&ev.target.closest&&ev.target.closest('.pl-zoomable');",
    "if(box&&window.Shiny)Shiny.setInputValue(box.dataset.zoomInput,{reset:true,nonce:Math.random()},{priority:'event'});});",
    "})();"))))

# Der Zeitraum fuer die ganze Seite (#531 Punkt 1), ueber den Reitern mit Zeitachse; Projektion, Stichtag, Momentaufnahme und
# Abschluss kennen keinen Zeitraum, dort ist er ausgeblendet. Ein aufgezogener Bereich in einem Bild gilt ebenso fuer alle.
ANALYSIS_HISTORY_PERIOD_TABS_V1 <- c("verlauf", "rendite", "vergleich", "assets")
analysis_history_central_period_ui_v1 <- function() shiny::tagList(
  analysis_history_zoom_script_v1(),
  shiny::conditionalPanel(sprintf("!input.analysis_tab || ['%s'].indexOf(input.analysis_tab) >= 0", paste(ANALYSIS_HISTORY_PERIOD_TABS_V1, collapse = "','")),
    shiny::div(class = "pl-card", analysis_history_period_ui_v1("zeitraum", "Zeitraum für alle Bilder und Tabellen"), shiny::uiOutput("zeitraum_zoom_state"))))

# Reiter "Verlauf": Portfolio und Zusammensetzung - ein gemeinsamer Zeitraum. Je Asset und je Klasse zeigt der Reiter
# "Assets und Gruppen" (analysis_assets_v1.R).
analysis_history_verlauf_ui_v1 <- function() shiny::tagList(
  portelyra_card(
    "Portfolio-Verlauf",
    copy = "Gesamtvermögen, Marktwert, Einstand und Cash je Tag aus der veröffentlichten Tageshistorie, darunter die unrealisierte GuV.",
    note = portelyra_note_v1(title = "So lesen Sie den Verlauf", id = "analysis-portfolio",
      "Cash belegt ist durch Auszüge bestätigt; Cash gesamt enthält zusätzlich aus Bewegungen abgeleitete Salden (gestrichelt) – so wie das Gesamtvermögen. Geld, das zwischen zwei eigenen Konten unterwegs ist (Abgang und gleich hoher Eingang bis zu fünf Tage später), zählt weiter zum Cash.",
      "Extern zugeflossen beginnt beim Gesamtvermögen des ersten Tages und addiert, was über alle Konten von außen kam oder nach außen ging: die Kontoänderung, soweit Käufe, Verkäufe und Erträge sie nicht erklären, dazu Ein- und Auslieferungen zum Tageswert. Der Abstand zum Gesamtvermögen ist der Anlageerfolg vor Steuern; Steuern und Gebühren, die vom Konto abgehen, zählen als Abfluss.",
      "Der Zeiger zeigt die Rechnung jedes Tages. Nicht vollständig bewertete Tage sind grau hinterlegt.",
      "Welche Linien und Kennwerte erscheinen, wählen die Häkchen; die Vorgabe beim Öffnen steht in der App „Daten“ unter „Einstellungen · Anzeige“."),
    shiny::uiOutput("history_state"),
    shiny::checkboxGroupInput("history_portfolio_lines", "Linien und Kennwerte", ANALYSIS_HISTORY_LINES_V1, selected = unname(ANALYSIS_HISTORY_LINES_V1), inline = TRUE),
    analysis_history_zoomable_v1("zeitraum", "portfolio",
      shiny::plotOutput("history_portfolio_plot", height = "520px", hover = shiny::hoverOpts("history_portfolio_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      # Shiny ordnet bei mehreren Teilgrafiken nur die unterste zu; alle teilen dieselbe Zeitachse und dieselben Seitenraender,
      # deshalb gilt die Zuordnung auch ueber den oberen (nullOutside = FALSE).
      shiny::uiOutput("history_portfolio_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("history_moment_note"),
    shiny::tags$details(shiny::tags$summary("Werte je Monatsende als Tabelle"), shiny::div(class = "pl-table-wrap", shiny::tableOutput("history_portfolio_table")))),
  portelyra_card(
    "Zusammensetzung",
    copy = "Das Gesamtvermögen je Tag nach Cash und Assetklasse, in Euro oder als Anteil. Gezählt wird, was auch im Gesamtvermögen steht: bewertete Positionen und Cash.",
    shiny::div(class = "pl-form-grid",
      shiny::radioButtons("history_composition_view", "Darstellung", c("in Euro" = "eur", "Anteil in %" = "share"), selected = "eur", inline = TRUE),
      shiny::selectInput("history_composition_split", "Gliederung", c("Assetklassen" = "classes"), selectize = FALSE)),
    shiny::uiOutput("history_composition_note"),
    analysis_history_zoomable_v1("zeitraum", "composition",
      shiny::plotOutput("history_composition_plot", height = "380px", hover = shiny::hoverOpts("history_composition_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      shiny::uiOutput("history_composition_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("history_composition_moment_note"),
    shiny::tags$details(shiny::tags$summary("Zusammensetzung je Monatsende als Tabelle"), shiny::div(class = "pl-table-wrap", shiny::tableOutput("history_composition_table")))))

# Reiter "Rendite": die Rendite der Anlage mit eigenem Zeitraum fuer den Verlauf.
analysis_history_rendite_ui_v1 <- function() shiny::tagList(
  portelyra_card(
    "Rendite der Anlage",
    copy = "Zeitgewichtete (TWR) und geldgewichtete Rendite (IZF) der Anlage je Zeitraum, vor Steuern.",
    note = portelyra_note_v1(title = "So lesen Sie die Rendite", id = "analysis-returns",
      "Die Anlage ist alles ohne die Cash-Konten, die außerhalb geführt werden (Girokonten mit Gehalt und Alltag). Was von dort hinein- oder zurückfließt, ist eine Einlage oder Entnahme.",
      "Zeitgewichtet (TWR) blendet Einlagen und Entnahmen aus und ist mit Fonds und Indizes vergleichbar; geldgewichtet (IZF) berücksichtigt, wann Geld kam und ging.",
      "Alles vor Steuern: Steuern und Gebühren, die vom Konto abgehen, zählen als Abfluss; Order- und Stückgebühren mindern die Rendite. Ein * markiert Zeiträume mit nicht vollständig bewerteten Tagen.",
      paste(ANALYSIS_HISTORY_RETURNS_INCLUDE_V1, ANALYSIS_HISTORY_TIMING_TEXT_V1,
            "„TWR ohne Cash“ rechnet nur über die Assets; „Wirkung des Cash“ ist der Abstand der Anlage dazu – was das geparkte Cash gekostet (negativ) oder gebracht hat (positiv).")),
    shiny::uiOutput("history_scope_state"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_periods_table")),
    shiny::uiOutput("rendite_span_state"),
    analysis_history_zoomable_v1("zeitraum", "returns",
      shiny::plotOutput("history_returns_plot", height = "400px", hover = shiny::hoverOpts("history_returns_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      shiny::uiOutput("history_returns_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("history_returns_moment_note"),
    shiny::tags$details(shiny::tags$summary("Zinsrendite je Cash-Konto und Jahr"),
      shiny::p(class = "pl-field-hint", "Zinsen geteilt durch den durchschnittlichen Saldo der gezählten Tage, aufs Jahr gerechnet."),
      shiny::checkboxInput("history_interest_hide_zero", "Null-Renditen ausblenden", TRUE),
      shiny::uiOutput("history_interest_table")),
    shiny::tags$details(shiny::tags$summary("Externe Flüsse je Konto · Abgleich mit den Auszügen"),
      shiny::p(class = "pl-field-hint", paste("Je Cash-Konto die Kontoänderung, soweit Käufe, Verkäufe, Dividenden und Zinsen sie nicht erklären. Ein Kauf oder Verkauf zählt auf dem Konto, auf dem sein Betrag gebucht ist – auch einige Tage später (Valuta erkannt) oder bei einem anderen Institut bezahlt.",
        "Umbuchungen sind Abgang und gleich hoher Eingang auf zwei eigenen Konten innerhalb von fünf Tagen. Extern bleibt, was dann übrig ist: Gehalt, Ausgaben, Steuern, Zahlungen von und an nicht geführte Konten, ein Kontostart oder das Ende einer Auszugslücke.")),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_flow_accounts_table")),
      shiny::selectInput("history_flow_account", "Konto je Monat", c("Bitte warten" = "")),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_flow_account_table")))),
  portelyra_card(
    "Erfolgsbrücke",
    copy = "Woraus sich der Anlageerfolg eines Zeitraums zusammensetzt, vor Steuern.",
    note = portelyra_note_v1(title = "So lesen Sie die Brücke", id = "analysis-bridge",
      "Realisiert bei Verkäufen (Erlös nach Gebühren minus Einstand je Lot), die Änderung des unrealisierten, Dividenden (brutto), Rewards zum Zuflusswert und Zinsen.",
      "Einlieferungen bringen eine Wertänderung mit, die anderswo entstand – sie wird abgezogen; Auslieferungen nehmen die bis dahin entstandene mit – sie wird zugerechnet. Stückgebühren bei Überträgen mindern den Einstand. Der Rest ist, was die Teile nicht erklären."),
    shiny::div(class = "pl-form-grid",
      shiny::radioButtons("history_bridge_view", "Sicht", ANALYSIS_HISTORY_VIEWS_V1, selected = "gross")),
    shiny::uiOutput("history_bridge_state"),
    shiny::uiOutput("history_bridge_net_state"),
    shiny::plotOutput("history_bridge_plot", height = "380px"),
    shiny::tags$details(shiny::tags$summary("Erfolgsbrücke je Zeitraum als Tabelle"),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_bridge_table")))),
  portelyra_card(
    "Kennzahlen je Intervall",
    copy = "Die Anlage je Tag, Woche, Monat oder Quartal im gewählten Zeitraum.",
    note = portelyra_note_v1(title = "So lesen Sie die Intervalle", id = "analysis-intervals",
      "Je Intervall Anlageerfolg und seine Teile, zeit- und geldgewichtete Rendite (IZF ab der Woche). Für die festen Zeiträume und für Kalenderjahre dazu Durchschnitt, Median, bestes und schlechtestes Intervall und der Anteil positiver Intervalle.",
      "Ein Intervall zählt, wenn sein erster und sein letzter Tag bewertet sind; angebrochene Intervalle am Rand zählen mit ihren Tagen."),
    shiny::div(class = "pl-form-grid",
      shiny::radioButtons("history_interval_granularity", "Intervall", ANALYSIS_HISTORY_GRANULARITIES_V1, selected = "month", inline = TRUE),
      shiny::radioButtons("history_interval_metric", "Balken (brutto, vor Steuern)", ANALYSIS_HISTORY_INTERVAL_BARS_V1, selected = "gain", inline = TRUE)),
    analysis_history_zoomable_v1("zeitraum", "intervals",
      shiny::plotOutput("history_intervals_plot", height = "300px", hover = shiny::hoverOpts("history_intervals_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      shiny::uiOutput("history_intervals_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("history_intervals_moment_note"),
    shiny::uiOutput("history_interval_summary_state"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_interval_summary")),
    shiny::tags$details(shiny::tags$summary("Alle Intervalle als Tabelle"),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_interval_table")))))

# Beide Reiter in einem - fuer Stellen, die alles auf einer Seite zeigen.
analysis_history_cards_ui_v1 <- function() shiny::tagList(analysis_history_central_period_ui_v1(), analysis_history_verlauf_ui_v1(), analysis_history_rendite_ui_v1(), analysis_compare_ui_v1(),
                                                         analysis_assets_ui_v1(), analysis_projection_ui_v1())

# Teildateien (#503): Der Kern traegt je Asset, Klasse und Gruppe nur den Verweis 'part'; die Tagesreihen kommen beim Auswaehlen
# dazu. Ohne Verweis (oder ohne Leser) bleibt der Eintrag, wie er ist.
analysis_history_hydrate_v1 <- function(entry, read_part) {
  if (is.null(entry) || is.null(entry$part) || is.null(read_part)) return(entry)
  fields <- read_part(entry$part)
  out <- entry[setdiff(names(entry), "part")]
  for (name in names(fields)) {
    if (identical(name, "performance") && is.list(out$performance)) out$performance <- c(out$performance, fields$performance)
    else out[name] <- list(fields[[name]])
  }
  out
}

analysis_history_hydrate_all_v1 <- function(history, read_part) {
  for (key in c("assets", "watched", "classes", "groups")) history[[key]] <- lapply(history[[key]], analysis_history_hydrate_v1, read_part = read_part)
  history
}

analysis_history_server_v1 <- function(input, output, session, read, read_part = NULL, read_display = NULL, read_moment = NULL) {
  state <- shiny::reactiveVal(list(kind = "loading"))
  # Die gelesenen Anzeige-Einstellungen, samt Umfang je Portfolio (#542); NULL, bis sie gelesen sind oder ohne Leser.
  display <- shiny::reactiveVal(NULL)
  shown_total <- "Gesamtvermögen"
  # Die juengste Momentaufnahme fuer den Punkt „jetzt“ (rc.314); ohne Leser oder Stand bleibt das Bild wie bisher.
  moment <- shiny::reactiveVal(NULL)
  # Gelesene Teildateien bleiben fuer die Sitzung: Sie sind nach ihrem Abdruck benannt und aendern sich nie.
  parts <- new.env(parent = emptyenv())
  cached <- if (is.null(read_part)) NULL else function(part) {
    if (!exists(part, envir = parts, inherits = FALSE)) assign(part, read_part(part), envir = parts)
    get(part, envir = parts, inherits = FALSE)
  }
  hydrate <- function(entry) analysis_history_hydrate_v1(entry, cached)
  first <- TRUE
  load <- function() {
    # Erst die Anzeige-Einstellungen (#500): Die Ausgaben danach rechnen mit ihnen. Ohne lesbare Einstellungen gelten die Vorgaben.
    if (is.function(read_display)) {
      settings <- tryCatch(read_display(), error = function(error) list(amount_decimals = 0L, tint = TRUE))
      analysis_history_apply_display_v1(settings)
      display(settings)
    }
    # Beim ersten Lesen der Sitzung oeffnet die Seite mit dem eingestellten Zeitraum; "Neu lesen" laesst die eigene Wahl stehen.
    opening <- first
    if (first) {
      first <<- FALSE
      if (!identical(ANALYSIS_DISPLAY_V1$period, "all")) shiny::updateRadioButtons(session, "zeitraum_period", selected = ANALYSIS_DISPLAY_V1$period)
      if (!setequal(ANALYSIS_DISPLAY_V1$lines, ANALYSIS_HISTORY_LINES_V1))
        shiny::updateCheckboxGroupInput(session, "history_portfolio_lines", selected = ANALYSIS_DISPLAY_V1$lines)
    }
    # Ohne „Verlauf und Analyse“ im Umfang (#542) gibt es keine Tageshistorie: Sie wird nicht gelesen, auch eine aeltere nicht.
    if (analysis_scope_off_v1("history_analysis")) {
      state(list(kind = "off", loaded_at = Sys.time())); moment(NULL)
      return(invisible(NULL))
    }
    value <- tryCatch(list(kind = "ready", history = read()),
                      error = function(error) list(kind = "error", code = if (is.character(error$code)) error$code else conditionMessage(error)))
    # Ohne Cash im Umfang heisst die Summe „ohne Cash“, sofern die Reihe keines traegt; Linienwahl und Bilder nennen sie so.
    total <- if (analysis_scope_off_v1("cash") && identical(value$kind, "ready") && !analysis_history_has_cash_v1(value$history))
      "Gesamtvermögen ohne Cash" else "Gesamtvermögen"
    ANALYSIS_DISPLAY_V1$total_label <- total
    if (!identical(total, shown_total)) {
      shown_total <<- total
      choices <- ANALYSIS_HISTORY_LINES_V1; names(choices)[choices == "net_worth"] <- total
      chosen <- if (opening) ANALYSIS_DISPLAY_V1$lines else shiny::isolate(input$history_portfolio_lines)
      shiny::updateCheckboxGroupInput(session, "history_portfolio_lines", choices = choices, selected = chosen, inline = TRUE)
    }
    # Jedes Lesen gilt als neuer Stand: Ein reactiveVal meldet einen gleichen Wert nicht weiter. Sonst blieben nach "Neu lesen"
    # mit unveraenderter Reihe neue Anzeige-Einstellungen unsichtbar und der Hinweis auf einen neuen Stand stehen (rc.298).
    value$loaded_at <- Sys.time()
    state(value)
    if (is.function(read_moment)) moment(tryCatch(read_moment(), error = function(error) NULL))
  }
  # Erst die Seite, dann die Reihe: Das Lesen kostet einige Sekunden und soll den Seitenaufbau nicht aufhalten.
  session$onFlushed(function() load(), once = TRUE)
  shiny::observeEvent(input$refresh, load(), ignoreInit = TRUE)
  ready <- shiny::reactive({ value <- state(); if (identical(value$kind, "ready")) value$history else NULL })
  geometry <- new.env(parent = emptyenv())
  # Ein Zeitraum fuer die ganze Seite (#485, #531 Punkt 1): Auswahl oder - vorrangig - ein im Bild aufgezogener Bereich.
  zoom <- list(zeitraum = shiny::reactiveVal(NULL))
  spec_of <- function(prefix) shiny::reactive({
    zoomed <- zoom[[prefix]]()
    if (!is.null(zoomed)) return(list(period = "range", range = zoomed))
    mode <- input[[paste0(prefix, "_period")]]; if (is.null(mode) || !nzchar(mode)) mode <- "all"
    range <- if (identical(mode, "years")) {
      years <- suppressWarnings(as.integer(c(input[[paste0(prefix, "_year_from")]], input[[paste0(prefix, "_year_to")]])))
      if (length(years) == 2L && !anyNA(years)) as.Date(c(sprintf("%d-01-01", min(years)), sprintf("%d-12-31", max(years)))) else NULL
    } else if (identical(mode, "range")) {
      value <- input[[paste0(prefix, "_range")]]
      if (length(value) == 2L && !anyNA(value)) as.Date(value) else NULL
    } else NULL
    list(period = mode, range = range)
  })
  window_of <- spec_of("zeitraum")
  spec <- list(zeitraum = window_of)
  # Erster und letzter Tag der Auswahl - damit grenzen die Tabellen ihre Zeitraeume ein.
  bounds <- shiny::reactive(analysis_history_bounds_v1(ready(), window_of()))
  shiny::observeEvent(ready(), {
    history <- ready(); years <- as.character(seq(as.integer(substr(history$first_day, 1, 4)), as.integer(substr(history$last_day, 1, 4))))
    for (prefix in names(spec)) {
      shiny::updateSelectInput(session, paste0(prefix, "_year_from"), choices = years, selected = years[[1L]])
      shiny::updateSelectInput(session, paste0(prefix, "_year_to"), choices = years, selected = years[[length(years)]])
      shiny::updateDateRangeInput(session, paste0(prefix, "_range"), start = history$first_day, end = history$last_day, min = history$first_day, max = history$last_day)
    }
  }, ignoreNULL = TRUE)
  for (zoom_prefix in names(zoom)) local({
    prefix <- zoom_prefix
    # Eine neue Auswahl des Zeitraums hebt den Zoom auf.
    shiny::observeEvent(list(input[[paste0(prefix, "_period")]], input[[paste0(prefix, "_year_from")]], input[[paste0(prefix, "_year_to")]],
                             input[[paste0(prefix, "_range")]]), zoom[[prefix]](NULL), ignoreInit = TRUE)
    shiny::observeEvent(input[[paste0(prefix, "_zoom_reset")]], zoom[[prefix]](NULL), ignoreInit = TRUE)
    shiny::observeEvent(input[[paste0(prefix, "_zoom")]], {
      event <- input[[paste0(prefix, "_zoom")]]
      if (isTRUE(event$reset)) return(zoom[[prefix]](NULL))
      days <- analysis_history_zoom_days_v1(geometry[[event$plot]], event$x0, event$x1)
      if (!is.null(days)) zoom[[prefix]](days)
    }, ignoreInit = TRUE)
    output[[paste0(prefix, "_zoom_state")]] <- shiny::renderUI({
      zoomed <- zoom[[prefix]](); if (is.null(zoomed)) return(NULL)
      shiny::p(class = "pl-field-hint", sprintf("Vergrößert: %s bis %s · ", format(zoomed[[1L]], "%d.%m.%Y"), format(zoomed[[2L]], "%d.%m.%Y")),
               shiny::actionLink(paste0(prefix, "_zoom_reset"), "Zoom zurücksetzen"))
    })
  })
  portfolio <- shiny::reactive({ history <- ready(); window <- window_of(); if (is.null(history)) NULL else analysis_history_portfolio_frame_v1(history, window$period, window$range) })
  output$history_state <- shiny::renderUI({
    value <- state()
    if (identical(value$kind, "loading")) return(portelyra_status_panel("Tageshistorie wird gelesen", "Einen Moment.", tone = "neutral"))
    if (identical(value$kind, "off")) return(portelyra_status_panel("Verlauf und Analyse ist im Umfang nicht eingeschaltet", ANALYSIS_SCOPE_HISTORY_COPY_V1, tone = "neutral"))
    if (identical(value$kind, "error")) {
      copy <- if (identical(value$code, "display_no_latest")) "Noch keine Tageshistorie veröffentlicht. Sie entsteht in der App „Daten“ mit „Alles aktualisieren“ oder „Tageshistorie fortschreiben“."
        else paste("Die Tageshistorie ließ sich nicht lesen.", pl_error_text_v1(value$code))
      return(portelyra_status_panel("Kein Verlauf", copy, tone = "warning"))
    }
    history <- value$history
    portelyra_status_panel(paste0("Tageshistorie bis ", format(as.Date(history$last_day), "%d.%m.%Y")),
      paste0(history$day_count, " Tage ab dem ", format(as.Date(history$first_day), "%d.%m.%Y"), " · veröffentlicht ",
             format(as.POSIXct(history$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y %H:%M", tz = "Europe/Berlin")),
      tone = "neutral")
  })
  # Die Momentaufnahme je Asset fuer alle Bilder (#512): einmal je gelesenem Stand.
  moment_model <- shiny::reactive(analysis_moment_model_v1(moment(), ready()))
  now <- shiny::reactive(analysis_history_moment_point_v1(moment_model(), portfolio()))
  # Gewaehlte Linien (#531 Punkt 2). Bevor das Feld sich meldet, gilt die Vorgabe; danach heisst leer: keine.
  lines_touched <- shiny::reactiveVal(FALSE)
  shiny::observeEvent(input$history_portfolio_lines, lines_touched(TRUE), ignoreInit = TRUE)
  lines <- shiny::reactive({
    chosen <- input$history_portfolio_lines
    if (is.null(chosen) && !isTRUE(lines_touched())) ANALYSIS_DISPLAY_V1$lines else intersect(unname(ANALYSIS_HISTORY_LINES_V1), chosen)
  })
  output$history_portfolio_plot <- shiny::renderPlot({
    frame <- portfolio(); shiny::req(frame, nrow(frame) > 1L)
    shiny::validate(shiny::need(length(lines()) > 0L, "Keine Linie gewählt."))
    geometry$portfolio <- analysis_history_plot_portfolio_v1(frame, now(), lines())
  })
  output$history_moment_note <- shiny::renderUI(analysis_history_moment_note_v1(now(), moment_model()))
  output$history_portfolio_overlay <- shiny::renderUI({
    frame <- portfolio(); hover <- input$history_portfolio_hover
    day <- analysis_history_pixel_day_v1(geometry$portfolio, hover)
    if (is.null(frame) || !nrow(frame) || is.null(day)) return(NULL)
    point <- now()
    # Rechts vom letzten Tag, naeher am Punkt „jetzt“: dessen Werte statt des letzten Tagesschlusses.
    if (analysis_moment_hovered_v1(point, frame$day, day)) {
      content <- analysis_history_moment_rows_v1(point, moment_model())
      return(.analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$portfolio))
    }
    content <- analysis_history_portfolio_rows_v1(frame, day, lines())
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$portfolio)
  })
  output$history_portfolio_table <- shiny::renderTable(analysis_history_month_table_v1(shiny::req(portfolio())), striped = TRUE, spacing = "xs")
  # Gliederung nach Assetklassen oder nach einer Aufteilung eigener Gruppen (#483 Stufe 2).
  shiny::observeEvent(ready(), shiny::updateSelectInput(session, "history_composition_split", choices = analysis_history_composition_choices_v1(ready())), ignoreNULL = TRUE)
  partition_of <- function(history) {
    choice <- input$history_composition_split
    if (!is.character(choice) || !startsWith(choice, "partition:")) return(NULL)
    index <- suppressWarnings(as.integer(sub("partition:", "", choice, fixed = TRUE)))
    if (is.na(index) || index > length(history$partitions)) NULL else history$partitions[[index]]
  }
  composition <- shiny::reactive({
    history <- ready(); window <- window_of(); if (is.null(history)) return(NULL)
    partition <- partition_of(history)
    if (is.null(partition)) return(analysis_history_composition_frame_v1(history, window$period, window$range))
    # Die Gruppen dieser Aufteilung mit ihrem Wert je Tag aus den Teildateien (#503).
    history$groups <- lapply(history$groups, function(group) if (group$ordinal %in% unlist(partition$groups)) hydrate(group) else group)
    analysis_history_partition_frame_v1(history, partition, window$period, window$range)
  })
  output$history_composition_note <- shiny::renderUI({
    history <- ready(); if (is.null(history)) return(NULL)
    partition <- partition_of(history); if (is.null(partition) || !length(partition$uncovered_labels)) return(NULL)
    shiny::p(class = "pl-field-hint", sprintf("In keiner Gruppe der Aufteilung (grau): %s. In der App „Daten“ lässt sich die Aufteilung ergänzen.",
                                              paste(unlist(partition$uncovered_labels), collapse = ", ")))
  })
  composition_now <- shiny::reactive({
    frame <- composition(); model <- moment_model(); history <- ready()
    if (is.null(frame) || is.null(model) || !length(attr(frame, "classes"))) return(NULL)
    members <- if (is.null(partition_of(history))) NULL else analysis_moment_partition_members_v1(model, history, frame)
    analysis_moment_composition_v1(model, frame, members)
  })
  output$history_composition_plot <- shiny::renderPlot({
    frame <- composition(); shiny::req(frame, nrow(frame) > 1L, length(attr(frame, "classes")) > 0L)
    geometry$composition <- analysis_history_plot_composition_v1(frame, identical(input$history_composition_view, "share"), composition_now())
  })
  output$history_composition_moment_note <- shiny::renderUI({ current <- composition_now(); if (is.null(current)) NULL else analysis_moment_note_v1(moment_model()) })
  output$history_composition_overlay <- shiny::renderUI({
    frame <- composition(); hover <- input$history_composition_hover
    day <- analysis_history_pixel_day_v1(geometry$composition, hover)
    if (is.null(frame) || !nrow(frame) || is.null(day) || !length(attr(frame, "classes"))) return(NULL)
    current <- composition_now(); bar <- geometry$composition$bar
    if (!is.null(current) && !is.null(bar) && day > (as.numeric(max(frame$day)) + bar[[1L]]) / 2) {
      content <- analysis_history_composition_moment_rows_v1(frame, current, moment_model())
      return(.analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$composition))
    }
    content <- analysis_history_composition_rows_v1(frame, day)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$composition)
  })
  output$history_composition_table <- shiny::renderTable(analysis_history_composition_table_v1(shiny::req(composition())), striped = TRUE, spacing = "xs")
  # Rendite der Anlage (#481).
  output$history_scope_state <- shiny::renderUI({
    history <- ready(); if (is.null(history) || is.null(history$investment)) return(NULL)
    shiny::p(class = "pl-field-hint", analysis_history_scope_text_v1(history))
  })
  output$history_periods_table <- shiny::renderTable(analysis_history_tint_v1(analysis_history_periods_table_v1(shiny::req(ready()), bounds())), striped = TRUE, spacing = "xs",
                                                     sanitize.text.function = .analysis_history_html_v1)
  returns <- shiny::reactive({ history <- ready(); window <- window_of(); if (is.null(history)) NULL else analysis_history_investment_frame_v1(history, window$period, window$range) })
  output$rendite_span_state <- shiny::renderUI({
    history <- ready(); if (is.null(history)) return(NULL)
    text <- analysis_history_span_text_v1(history, window_of(), returns())
    if (!is.null(text)) portelyra_status_panel("Rendite im gewählten Zeitraum", text, tone = "neutral")
  })
  returns_now <- shiny::reactive(analysis_moment_returns_v1(moment_model(), returns()))
  output$history_returns_plot <- shiny::renderPlot({
    frame <- returns(); shiny::req(frame, nrow(frame) > 1L)
    geometry$returns <- analysis_history_plot_returns_v1(frame, returns_now())
  })
  output$history_returns_moment_note <- shiny::renderUI({
    current <- returns_now(); if (is.null(current)) return(NULL)
    analysis_moment_note_v1(moment_model(), sprintf("Zeitgewichtet jetzt %s, seit dem letzten Tagesschluss %s (Kursänderung, ohne Zu- und Abflüsse seither).",
                                                    analysis_history_pct_v1(current$twr), analysis_history_pct_v1(current$rate, 2L)))
  })
  output$history_returns_overlay <- shiny::renderUI({
    frame <- returns(); hover <- input$history_returns_hover
    day <- analysis_history_pixel_day_v1(geometry$returns, hover)
    if (is.null(frame) || !nrow(frame) || is.null(day)) return(NULL)
    current <- returns_now()
    if (analysis_moment_hovered_v1(current, frame$day, day)) {
      content <- analysis_history_returns_moment_rows_v1(current, moment_model())
      return(.analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$returns))
    }
    content <- analysis_history_returns_rows_v1(frame, day)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$returns)
  })
  output$history_interest_table <- shiny::renderUI(analysis_history_interest_ui_v1(shiny::req(ready()), !isFALSE(input$history_interest_hide_zero), bounds()))
  shiny::observeEvent(ready(), shiny::updateSelectInput(session, "history_flow_account", choices = analysis_history_flow_account_choices_v1(ready())), ignoreNULL = TRUE)
  output$history_flow_accounts_table <- shiny::renderTable(analysis_history_flow_accounts_table_v1(shiny::req(ready()), bounds()), striped = TRUE, spacing = "xs")
  output$history_flow_account_table <- shiny::renderTable({
    history <- shiny::req(ready()); analysis_history_flow_account_table_v1(history, input$history_flow_account, bounds())
  }, striped = TRUE, spacing = "xs")
  # Erfolgsbruecke und Kennzahlen je Intervall (#481, #485). Die Bruecke gilt fuer den gewaehlten Zeitraum (#531 Punkt 1): den
  # genau passenden veroeffentlichten, sonst den kuerzesten, der ihn enthaelt.
  bridge_row <- shiny::reactive({
    history <- ready(); if (is.null(history)) return(NULL)
    analysis_history_single_v1(Filter(function(row) !is.null(row$bridge), c(history$investment$periods, history$investment$year_spans)), bounds())
  })
  output$history_bridge_state <- shiny::renderUI({
    row <- bridge_row(); if (is.null(row)) return(if (is.null(ready())) NULL else shiny::p(class = "pl-field-hint", "Für den gewählten Zeitraum gibt es keine Brücke."))
    shiny::p(class = "pl-field-hint", paste0("Zeitraum: ", row$label, " (", format(as.Date(row$start_day), "%d.%m.%Y"), " bis ", format(as.Date(row$end_day), "%d.%m.%Y"), ")."))
  })
  output$history_bridge_plot <- shiny::renderPlot({
    row <- shiny::req(bridge_row())
    analysis_history_plot_bridge_v1(row, if (is.null(input$history_bridge_view)) "gross" else input$history_bridge_view)
  })
  output$history_bridge_table <- shiny::renderTable({
    history <- shiny::req(ready())
    rows <- analysis_history_periods_in_v1(history$investment$periods, Filter(function(row) !is.null(row$bridge), history$investment$year_spans), bounds())
    analysis_history_tint_v1(analysis_history_bridge_table_v1(rows, if (is.null(input$history_bridge_view)) "gross" else input$history_bridge_view))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$history_bridge_net_state <- shiny::renderUI({
    history <- ready(); if (is.null(history) || !analysis_history_net_kind_v1(input$history_bridge_view)) return(NULL)
    shiny::p(class = "pl-field-hint", analysis_history_net_note_v1(history, view = input$history_bridge_view))
  })
  intervals <- shiny::reactive({
    history <- ready(); window <- window_of(); if (is.null(history)) return(NULL)
    analysis_history_interval_frame_v1(history, if (is.null(input$history_interval_granularity)) "month" else input$history_interval_granularity, window$period, window$range)
  })
  intervals_now <- shiny::reactive({ history <- ready(); if (is.null(history)) NULL else analysis_moment_interval_v1(moment_model(), history, intervals()) })
  output$history_intervals_plot <- shiny::renderPlot({
    frame <- intervals(); shiny::req(frame, nrow(frame) > 0L)
    metric <- if (is.null(input$history_interval_metric)) "gain" else input$history_interval_metric
    if (identical(metric, "mwr") && identical(input$history_interval_granularity, "day")) metric <- "twr"
    geometry$intervals <- analysis_history_plot_intervals_v1(frame, metric, intervals_now())
  })
  output$history_intervals_moment_note <- shiny::renderUI({ current <- intervals_now()
    metric <- if (is.null(input$history_interval_metric)) "gain" else input$history_interval_metric
    if (is.null(current) || !is.numeric(current[[metric]])) NULL else analysis_moment_note_v1(moment_model(),
    sprintf("Der gepunktete Balken rechts: seit dem letzten Tagesschluss %s (%s).", analysis_history_eur_signed_v1(current$gain), analysis_history_pct_v1(current$twr, 2L))) })
  output$history_intervals_overlay <- shiny::renderUI({
    frame <- intervals(); hover <- input$history_intervals_hover
    day <- analysis_history_pixel_day_v1(geometry$intervals, hover)
    if (is.null(frame) || !nrow(frame) || is.null(day)) return(NULL)
    current <- intervals_now(); bar <- geometry$intervals$bar
    if (!is.null(current) && !is.null(bar) && day > (as.numeric(max(frame$end)) + 0.5 + bar[[1L]]) / 2) {
      content <- analysis_history_interval_moment_rows_v1(current, moment_model())
      return(.analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$intervals))
    }
    content <- analysis_history_interval_rows_v1(frame, day)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$intervals)
  })
  interval_key <- shiny::reactive(analysis_history_interval_window_v1(window_of()))
  output$history_interval_summary_state <- shiny::renderUI({
    history <- ready(); if (is.null(history)) return(NULL)
    if (is.null(interval_key())) return(shiny::p(class = "pl-field-hint", "Durchschnitt, Median und Anteil positiver Intervalle gibt es für „Alles“, 1, 3 und 5 Jahre und für Kalenderjahre; für den gewählten Zeitraum stehen nur die Intervalle im Bild."))
    shiny::p(class = "pl-field-hint", "Zusammenfassung der Intervalle im gewählten Zeitraum.")
  })
  output$history_interval_summary <- shiny::renderTable({
    history <- shiny::req(ready())
    analysis_history_tint_v1(analysis_history_interval_summary_v1(history, if (is.null(input$history_interval_granularity)) "month" else input$history_interval_granularity, interval_key()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$history_interval_table <- shiny::renderTable(analysis_history_tint_v1(analysis_history_interval_table_v1(intervals())), striped = TRUE, spacing = "xs",
                                                      sanitize.text.function = .analysis_history_html_v1)
  # Reiter "Assets und Gruppen" (#483).
  assets <- analysis_assets_server_v1(input, output, session, ready, window_of, geometry, hydrate, moment_model)
  # Reiter "Projektion" (#494) und "Vergleich" (#482).
  projection <- analysis_projection_server_v1(input, output, session, ready, geometry, moment_model, hydrate)
  compare <- analysis_compare_server_v1(input, output, session, ready, window_of, geometry, hydrate, moment_model)
  invisible(list(load = load, state = state, display = display, moment = moment, moment_model = moment_model, now = now, composition_now = composition_now,
                 returns_now = returns_now, intervals_now = intervals_now, clicked = assets$clicked, assets = assets, projection = projection, compare = compare, geometry = geometry, zoom = zoom,
                 spec = spec, bounds = bounds, intervals = intervals, lines = lines))
}

# Umfang je Portfolio (#542, Festlegung 06.11. und 10.11.2026). Ohne „Verlauf und Analyse“ gibt es keine Tageshistorie: Die Reiter, die
# sie zeigen (Verlauf, Rendite, Vergleich, Assets und Gruppen, Projektion), weichen einer Statusflaeche; Stichtag, Momentaufnahme und
# Abschluss bleiben. Ohne Steuerprojektion keine Netto-Sicht und kein Reiter „Projektion“ - gezeigt wird brutto. Ohne veroeffentlichten
# Umfang (oder mit allem an) bleibt die Seite, wie sie war: Es wird nichts versteckt und keine Auswahl angefasst.
ANALYSIS_SCOPE_HISTORY_TABS_V1 <- c("verlauf", "rendite", "vergleich", "assets", "projektion")
ANALYSIS_SCOPE_FALLBACK_TAB_V1 <- "stichtag"
# Die Wahl brutto/netto mit ihrer Beschriftung im Reiter.
ANALYSIS_SCOPE_VIEW_INPUTS_V1 <- c(history_bridge_view = "Sicht", history_asset_view = "GuV und Kennzahlen", history_overview_view = "Sicht")
ANALYSIS_SCOPE_HISTORY_COPY_V1 <- paste(
  "Zuschalten unter Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“; der nächste Lauf von „Alles aktualisieren“ rechnet die Tageshistorie dann einmal auf.",
  "Verlauf, Rendite, Vergleich, Assets und Gruppen und die Projektion brauchen sie; Stichtag, Momentaufnahme und Abschluss stehen weiter da.")
# scope: der veroeffentlichte Umfang (portfolio_scope mit source = "published") oder NULL.
analysis_scope_hidden_tabs_v1 <- function(scope) {
  modules <- if (is.list(scope)) scope$modules else NULL
  as.character(unique(c(if (analysis_scope_off_v1("history_analysis", modules)) ANALYSIS_SCOPE_HISTORY_TABS_V1,
                        if (analysis_scope_off_v1("tax_projection", modules)) "projektion")))
}
analysis_scope_net_allowed_v1 <- function(scope) !analysis_scope_off_v1("tax_projection", if (is.list(scope)) scope$modules else NULL)
analysis_scope_state_ui_v1 <- function(scope) {
  modules <- if (is.list(scope)) scope$modules else NULL
  if (analysis_scope_off_v1("history_analysis", modules))
    return(portelyra_status_panel("Verlauf und Analyse ist im Umfang nicht eingeschaltet", ANALYSIS_SCOPE_HISTORY_COPY_V1, tone = "neutral"))
  if (analysis_scope_off_v1("tax_projection", modules))
    return(portelyra_status_panel("Steuerprojektion ist im Umfang nicht eingeschaltet", paste(
      "Die Netto-Sicht und der Reiter „Projektion“ sind ausgeblendet; gezeigt wird brutto, vor Steuern.",
      "Zuschalten unter Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“."), tone = "neutral"))
  NULL
}
# `scope`: reaktiv, der veroeffentlichte Umfang oder NULL. Gibt die ausgeblendeten Reiter und ob netto waehlbar ist zurueck.
analysis_scope_server_v1 <- function(input, output, session, scope, tabset = "analysis_tab") {
  hidden <- shiny::reactiveVal(character()); net <- shiny::reactiveVal(TRUE)
  output$analysis_scope_state <- shiny::renderUI(analysis_scope_state_ui_v1(scope()))
  shiny::outputOptions(output, "analysis_scope_state", suspendWhenHidden = FALSE)   # leer ausgeblendet (.pl-scope-slot), sonst nie berechnet
  shiny::observeEvent(scope(), {
    current <- scope(); want <- analysis_scope_hidden_tabs_v1(current); before <- shiny::isolate(hidden())
    for (target in setdiff(want, before)) shiny::hideTab(tabset, target, session = session)
    for (target in setdiff(before, want)) shiny::showTab(tabset, target, session = session)
    if (!setequal(want, before)) hidden(want)
    selected <- shiny::isolate(input[[tabset]])
    if (length(want) && (is.null(selected) || selected %in% want)) shiny::updateTabsetPanel(session, tabset, selected = ANALYSIS_SCOPE_FALLBACK_TAB_V1)
    allowed <- analysis_scope_net_allowed_v1(current)
    if (!identical(allowed, shiny::isolate(net()))) {
      net(allowed)
      for (id in names(ANALYSIS_SCOPE_VIEW_INPUTS_V1)) shiny::updateRadioButtons(session, id,
        label = if (allowed) ANALYSIS_SCOPE_VIEW_INPUTS_V1[[id]] else paste0(ANALYSIS_SCOPE_VIEW_INPUTS_V1[[id]], " · netto nur mit Steuerprojektion im Umfang"),
        choices = if (allowed) ANALYSIS_HISTORY_VIEWS_V1 else ANALYSIS_HISTORY_VIEWS_V1[1L], selected = "gross")
    }
  }, ignoreNULL = FALSE)
  invisible(list(hidden = hidden, net = net))
}
