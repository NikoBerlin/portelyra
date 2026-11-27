# Die Steuerprojektion des letzten Portfolioabschlusses in der Tax-App: deutsch, auf Cent, mit erklärtem Stand.
#
# Festlegung (#428): Die Jahresprojektion zeigte fuer Jahre ohne Einordnung eine 0 mit dem Stand "completed", Rewards
# trugen "tax_classification_invalid" - englische Kennungen, Betraege mit bis zu 21 Nachkommastellen, und nirgends stand,
# dass die Tabellen einen aelteren Abschluss zeigten, gerechnet vor den Jahresregeln. Hier wird gesagt, was ein Stand
# bedeutet und wo nachzutragen ist. Die Zeilen selbst kommen unveraendert aus dem veroeffentlichten Abschluss.
tax_projection_status_labels_v1 <- function() c(completed = "gerechnet", blocked = "ohne Steuerzahl", partial = "teilweise", stale = "veraltet",
  partial_blocked = "teilweise ohne Steuerzahl", not_applicable = "nicht steuerrelevant",
  # Gewaehlter Umfang ist kein Mangel (#564, rc.406): Der Abschluss lief bewusst ohne Steuermodul.
  not_selected = "ohne Steuer (wie gewählt)")
tax_projection_event_type_labels_v1 <- function() c(sell = "Verkauf", withdrawal = "Abgang", reward = "Reward", dividend = "Dividende",
  interest = "Zins", buy = "Kauf", deposit = "Zugang", transfer = "Umschichtung", stock_dividend = "Stockdividende", advance_lump_sum = "Vorabpauschale")
# Was ein Grund bedeutet - und wo nachzutragen ist.
tax_projection_failure_text_v1 <- function(code) {
  text <- if (is.null(code) || length(code) != 1L || is.na(code)) "" else as.character(code)
  if (!nzchar(text)) return("")
  switch(text,
    tax_rate_required = "Persönlicher Steuersatz fehlt – Daten → „4. Steuer“ → „Steuerangaben je Jahr“.",
    church_tax_applicability_required = "Angabe zur Kirchensteuer fehlt – Daten → „4. Steuer“ → „Steuerangaben je Jahr“.",
    church_tax_rate_required = "Kirchensteuer fällt an, der Satz fehlt – Daten → „4. Steuer“ → „Steuerangaben je Jahr“.",
    tax_year_rules_missing = "Das Regelmodul führt dieses Steuerjahr nicht.",
    tax_fund_old_investment_tax_act = "Fonds vor 2018 oder Altanteile von vor 2018: altes Investmentsteuergesetz und fiktiver Verkauf zum 31.12.2017 – nicht berechnet.",
    tax_classification_required = "Keine Einordnung für dieses Asset – Daten → „4. Steuer“ → „Vorgabe je Asset-Typ“.",
    tax_classification_invalid = "Die Einordnung passte nicht zum Vorgang. Bei Rewards war das vor rc.253 so; ein neuer Abschluss rechnet sie.",
    tax_holding_evidence_required = "Für die Haltedauer fehlt das Anschaffungsdatum eines Lots.",
    tax_currency_conflict = "Beträge in mehreren Währungen ohne geprüften Wechselkurs.",
    reference_tax_rounding_policy_required = "Das exakte Ergebnis endet nicht; es fehlt eine Rundungsregel.",
    tax_plugin_not_selected = "Kein Regelmodul gewählt – Daten → „4. Steuer“ → „Regelmodul wählen“.",
    paste0("Grund: ", text))
}
# Ein exakter Dezimalbetrag auf Cent, kaufmaennisch gerundet - am Text, nicht ueber Gleitkomma.
tax_projection_cents_v1 <- function(value) {
  text <- if (is.null(value) || length(value) != 1L || is.na(value)) "" else trimws(as.character(value))
  if (!grepl("^-?[0-9]+(\\.[0-9]+)?$", text)) return(NA_character_)
  negative <- startsWith(text, "-"); text <- sub("^-", "", text)
  whole <- sub("\\..*$", "", text); fraction <- if (grepl(".", text, fixed = TRUE)) sub("^[^.]*\\.", "", text) else ""
  fraction <- substr(paste0(fraction, "000"), 1L, max(3L, nchar(fraction)))
  cents <- as.numeric(paste0(whole, substr(fraction, 1L, 2L)))
  if (as.integer(substr(fraction, 3L, 3L)) >= 5L) cents <- cents + 1
  if (cents == 0) negative <- FALSE
  body <- formatC(cents, format = "f", digits = 0, width = 3, flag = "0")
  euros <- substr(body, 1L, nchar(body) - 2L); rest <- substr(body, nchar(body) - 1L, nchar(body))
  euros <- formatC(as.numeric(euros), format = "f", digits = 0, big.mark = ".", decimal.mark = ",")
  paste0(if (negative) "-" else "", euros, ",", rest)
}
# Betrag mit Einheit (#529 Punkt 8): „12,34 €“; ohne Währung bleibt es bei der Zahl.
.tax_projection_money_v1 <- function(value, currency = "EUR") {
  shown <- tax_projection_cents_v1(value)
  if (is.na(shown)) return("–")
  unit <- pl_currency_unit_v1(if (is.null(currency) || !length(currency) || is.na(currency[[1L]])) "" else as.character(currency[[1L]]))
  if (nzchar(unit)) paste(shown, unit) else shown
}
.tax_projection_label_v1 <- function(labels, code) {
  text <- if (is.null(code) || length(code) != 1L || is.na(code)) "" else as.character(code)
  if (!nzchar(text)) "–" else if (text %in% names(labels)) unname(labels[[text]]) else text
}
# Betrag eines Ereignisses: der Ertrag bei Zinsen, Dividenden, Rewards und Vorabpauschalen, sonst der Gewinn. Der Abschluss
# traegt bei jeder Zeile beide Felder; bei Ertraegen steht im Gewinn eine 0 (Zinsen zeigten sonst 0,00).
.tax_projection_amount_v1 <- function(row) {
  income <- row$gross_income_decimal
  present <- function(value) !is.null(value) && length(value) == 1L && !is.na(value) && nzchar(as.character(value))
  if (present(income) && !isTRUE(suppressWarnings(as.numeric(income)) == 0)) return(income)
  if (present(row$realized_gross_gain_decimal)) row$realized_gross_gain_decimal else income
}
# Steuerneutral (#530): Kauf, Transfer und Zugang, dazu ein Abgang ohne Gewinn und ohne Steuer. Sie stehen nur auf Wunsch in
# der Tabelle; ohne Wunsch zeigt sie Verkaeufe und Ertraege. Eine Zeile mit Grund oder ohne Steuerzahl bleibt immer sichtbar.
tax_projection_event_neutral_v1 <- function(row) {
  zero <- function(value) is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value)) || isTRUE(suppressWarnings(as.numeric(value)) == 0)
  type <- if (is.null(row$event_type)) "" else as.character(row$event_type)
  explained <- !is.null(row$failure_code) && length(row$failure_code) == 1L && !is.na(row$failure_code) && nzchar(as.character(row$failure_code))
  if (explained || !identical(row$projection_status, "completed")) return(FALSE)
  type %in% c("buy", "transfer", "deposit") ||
    (identical(type, "withdrawal") && zero(row$realized_gross_gain_decimal) && zero(row$gross_income_decimal) && zero(row$projected_event_tax_decimal))
}
tax_projection_event_rows_v1 <- function(rows, include_neutral = FALSE) {
  if (!is.list(rows) || !length(rows) || isTRUE(include_neutral)) return(rows)
  Filter(function(row) !tax_projection_event_neutral_v1(row), rows)
}
# Datum deutsch (TT.MM.JJJJ); ein unlesbarer Wert bleibt, wie er ist.
.tax_projection_date_v1 <- function(value) {
  text <- if (is.null(value) || length(value) != 1L || is.na(value)) "" else as.character(value)
  day <- suppressWarnings(as.Date(text, format = "%Y-%m-%d"))
  if (is.na(day)) text else format(day, "%d.%m.%Y")
}
# Je Ereignis: Datum, Art, Vermoegenswert, Betrag, Steuer, Netto, Stand und Grund.
tax_projection_event_frame_v1 <- function(rows) {
  if (!is.list(rows) || !length(rows)) return(data.frame())
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Nr. = vapply(rows, function(row) as.character(if (is.null(row$event_ordinal)) "" else row$event_ordinal), character(1L)),
    Datum = vapply(rows, function(row) .tax_projection_date_v1(row$local_date), character(1L)),
    Art = vapply(rows, function(row) .tax_projection_label_v1(tax_projection_event_type_labels_v1(), row$event_type), character(1L)),
    `Vermögenswert` = vapply(rows, function(row) as.character(row$asset_label), character(1L)),
    `Gewinn bzw. Ertrag` = vapply(rows, function(row) .tax_projection_money_v1(.tax_projection_amount_v1(row), row$currency), character(1L)),
    Steuer = vapply(rows, function(row) .tax_projection_money_v1(row$projected_event_tax_decimal, row$currency), character(1L)),
    Netto = vapply(rows, function(row) .tax_projection_money_v1(row$projected_net_gain_decimal, row$currency), character(1L)),
    Stand = vapply(rows, function(row) .tax_projection_label_v1(tax_projection_status_labels_v1(), row$projection_status), character(1L)),
    Grund = vapply(rows, function(row) tax_projection_failure_text_v1(row$failure_code), character(1L)))
}
# Je Jahr: die Summen des Abschlusses und daneben, wie viele Ereignisse des Jahres ohne Steuerzahl blieben. Eine 0 neben
# fehlenden Ereignissen ist keine "keine Steuer" - sie steht dann als unvollstaendig da.
tax_projection_annual_frame_v1 <- function(annual_rows, event_rows = list()) {
  if (!is.list(annual_rows) || !length(annual_rows)) return(data.frame())
  event_year <- vapply(event_rows, function(row) substr(as.character(row$local_date), 1L, 4L), character(1L))
  event_open <- vapply(event_rows, function(row) !identical(row$projection_status, "completed"), logical(1L))
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Steuerjahr = vapply(annual_rows, function(row) as.character(row$tax_year), character(1L)),
    `Ereignisse gerechnet` = vapply(annual_rows, function(row) as.character(sum(event_year == as.character(row$tax_year) & !event_open)), character(1L)),
    `ohne Steuerzahl` = vapply(annual_rows, function(row) as.character(sum(event_year == as.character(row$tax_year) & event_open)), character(1L)),
    `Beitrag zum Jahr` = vapply(annual_rows, function(row) .tax_projection_money_v1(row$net_contribution_decimal, row$currency), character(1L)),
    `Steuer im Jahr` = vapply(annual_rows, function(row) .tax_projection_money_v1(row$projected_annual_tax_decimal, row$currency), character(1L)),
    Netto = vapply(annual_rows, function(row) .tax_projection_money_v1(row$projected_net_gain_decimal, row$currency), character(1L)),
    Stand = vapply(annual_rows, function(row) {
      open <- sum(event_year == as.character(row$tax_year) & event_open)
      if (!identical(row$projection_status, "completed")) paste(.tax_projection_label_v1(tax_projection_status_labels_v1(), row$projection_status), tax_projection_failure_text_v1(row$failure_code))
      else if (open > 0L) sprintf("unvollständig – %d Ereignis(se) ohne Steuerzahl", open) else "gerechnet"
    }, character(1L)))
}
# Der Abschluss, den die Tabellen zeigen: Stichtag, Zeitpunkt, Stand - und ob die Steuereinstellungen seither geaendert wurden.
tax_projection_status_ui_v1 <- function(state, settings_changed = NA) {
  # Ohne veroeffentlichten Abschluss meldet der Leser "display_no_latest" - das ist kein Fehler, sondern noch kein Abschluss.
  if (identical(state$kind, "empty") || (identical(state$kind, "error") && identical(state$code, "display_no_latest"))) return(portelyra_status_panel("Noch kein Portfolioabschluss",
    "Die Tabellen zeigen einen abgeschlossenen Portfolioabschluss. Er entsteht in der App „Daten“ mit „Alles aktualisieren“ (oben rechts); die App „Steuer“ rechnet nicht selbst.", tone = "warning"))
  if (identical(state$kind, "error")) return(portelyra_status_panel("Abschluss nicht lesbar", pl_error_text_v1(state$code), tone = "error"))
  model <- state$model
  when <- tryCatch(format(as.POSIXct(model$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y %H:%M", tz = ""),
    error = function(error) as.character(model$completed_at_utc))
  day <- tryCatch(format(as.Date(model$as_of_date), "%d.%m.%Y"), error = function(error) as.character(model$as_of_date))
  readiness <- if (is.list(model$tax)) .tax_projection_label_v1(tax_projection_status_labels_v1(), model$tax$readiness_status) else "–"
  shiny::tagList(
    portelyra_status_panel(sprintf("Portfolioabschluss zum %s", day), paste0(
      "Gerechnet am ", when, " · Portfolio ", model$portfolio_label, " · Steuerprojektion: ", readiness,
      " · Ereignis- und Jahresprojektion unten zeigen genau diesen Stand."),
      tone = if (identical(model$status, "completed")) "neutral" else "warning"),
    if (isTRUE(settings_changed)) portelyra_status_panel("Steuereinstellungen seither geändert",
      "Seit diesem Abschluss wurden Steuerangaben oder Einordnungen geändert. Die Tabellen zeigen noch den alten Stand – bitte in der App „Daten“ oben rechts „Alles aktualisieren“ starten.",
      tone = "warning"))
}
# Ob seit dem Abschluss Steuereinstellungen geaendert wurden: Der Steuerspeicher fuehrt dann die Projektion als neu zu rechnen.
# NA heisst: nicht lesbar - dann sagt die Karte nichts dazu.
tax_projection_settings_changed_v1 <- function(service, year = as.integer(format(Sys.Date(), "%Y"))) {
  if (is.null(service) || !isTRUE(tryCatch(service$initialized(), error = function(error) FALSE))) return(NA)
  catalog <- tryCatch(service$catalog(), error = function(error) NULL)
  portfolios <- if (is.list(catalog) && is.list(catalog$catalog)) catalog$catalog$portfolios else list()
  if (!length(portfolios)) return(NA)
  states <- unlist(lapply(portfolios, function(portfolio) {
    overview <- tryCatch(service$overview(portfolio$exchange_ref, year), error = function(error) NULL)
    if (is.list(overview)) vapply(overview$readiness, function(row) as.character(row$status), character(1L)) else character()
  }))
  if (!length(states)) NA else any(states == "stale")
}

# Umfang je Portfolio (#542, Festlegung 06.11. und 10.11.2026): Ohne den Baustein Steuerbericht gibt es keine Inhalte der Steuer-App,
# ohne Steuerprojektion keine Karten der Projektion des Abschlusses. `scope` ist der veroeffentlichte Umfang oder NULL - dann bleibt
# alles stehen. Abschalten loescht nichts; die Flaeche sagt, wo zugeschaltet wird.
.tax_scope_off_v1 <- function(scope, module) is.list(scope) && isFALSE(scope$modules[[module]])
tax_scope_state_ui_v1 <- function(scope) {
  if (!.tax_scope_off_v1(scope, "tax_report")) return(NULL)
  portelyra_status_panel("Steuerbericht ist im Umfang nicht eingeschaltet", paste(
    "Steuerreport, Jahresrechnung, Rechenblätter, Unterlagen des Jahres und die Steuerprojektion gibt es nur mit dem Baustein Steuerbericht.",
    "Zuschalten unter Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“; gelöscht wurde nichts."), tone = "neutral")
}
tax_scope_projection_state_ui_v1 <- function(scope) {
  if (.tax_scope_off_v1(scope, "tax_report") || !.tax_scope_off_v1(scope, "tax_projection")) return(NULL)
  portelyra_status_panel("Steuerprojektion ist im Umfang nicht eingeschaltet", paste(
    "Die Karten der Steuerprojektion des Abschlusses sind ausgeblendet; Steuerreport, Jahresrechnung, Rechenblätter und Unterlagen gelten weiter.",
    "Zuschalten unter Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“."), tone = "neutral")
}
