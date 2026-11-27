# Deutsch seit rc.309 (Festlegung 23.10.2026: englische Begriffe nach deutsch); die Werte kommen unveraendert aus dem Abschluss.
DESKTOP_WORKFLOW_STATE_LABELS_V1 <- c(completed = "abgeschlossen", partial = "teilweise", stale = "veraltet", blocked = "blockiert",
  failed = "fehlgeschlagen", ready = "bereit", not_applicable = "nicht anwendbar", skipped = "übersprungen", fresh = "aktuell",
  current = "aktuell", pending = "offen", running = "läuft", unavailable = "nicht verfügbar", missing = "fehlt",
  # Stand je Position (#490): Kurs, Steuer, Wechselkurs.
  stale_price = "Kurs nicht vom Stichtag", missing_price = "Kurs fehlt", source_gap = "Lücke in der Kursquelle",
  corporate_action_review_required = "Kapitalmaßnahme prüfen", negative_gain_no_tax = "Verlust, keine Steuer",
  # Gewaehlter Umfang ist kein Mangel (#564, rc.406): "not_selected" = bewusst ohne Steuer; "no_plugin" ist seitdem nur noch eine Luecke
  # bei gewaehlter Steuer (Modul ohne Projektion, Einordnung fehlt) - bis rc.405 stand es auch fuer "nicht gewaehlt".
  not_selected = "ohne Steuer (wie gewählt)", no_plugin = "Steuerprojektion nicht verfügbar", classification_required = "Steuer-Einordnung fehlt", parameter_required = "Steuerangabe fehlt",
  plugin_blocked = "Steuermodul angehalten", not_calculated = "nicht berechnet", native = "ohne Umrechnung",
  conversion_unavailable = "Umrechnung nicht verfügbar")
.desktop_workflow_state_label_v1 <- function(value) {
  text <- if (is.null(value) || length(value) != 1L || is.na(value)) "" else as.character(value)
  if (!nzchar(text)) "—" else if (text %in% names(DESKTOP_WORKFLOW_STATE_LABELS_V1)) unname(DESKTOP_WORKFLOW_STATE_LABELS_V1[[text]]) else text
}
# Noch keine Buchungen (#555 c): Der erste Lauf aus der Einrichtung haelt ohne Assets an der Bewertung an. Statt "blockiert" sagt die
# Anzeige, worauf er wartet - nur in genau diesem Fall: FIFO und Steuer durch, angehalten an der Bewertung, keine Positionen, keine
# Steuerereignisse. Ein Anhalten mit Buchungen bleibt "blockiert".
desktop_workflow_awaiting_bookings_v1 <- function(model) {
  if (!is.list(model) || !identical(model$status, "blocked") || !is.null(model$cockpit)) return(FALSE)
  stage <- function(code) Filter(function(row) identical(row$stage_code, code), model$stages)
  valuation <- stage("valuation"); fifo <- stage("fifo")
  length(valuation) == 1L && identical(valuation[[1L]]$failure_code, "desktop_workflow_valuation_blocked") &&
    length(fifo) == 1L && identical(fifo[[1L]]$status, "completed") && (is.null(model$tax) || !length(model$tax$event_rows))
}
DESKTOP_WORKFLOW_AWAITING_BOOKINGS_TEXT_V1 <- paste("Die Vorgaben für den Abschluss stehen. Der erste Abschluss entsteht mit „Alles aktualisieren“, sobald",
  "Buchungen erfasst oder eingelesen sind.")
# `modules`: der Umfang des Portfolios dieses Abschlusses oder NULL (unbekannt). "wie gewaehlt" steht, wenn der Steuerbericht abgewaehlt
# oder der Umfang unbekannt ist - ohne Steuermodul rechnet der Abschluss nur nach einer Bestaetigung im Run Center oder in der
# Einrichtung. Ist der Steuerbericht gewaehlt und der Abschluss trotzdem ohne Steuer, passen zwei Angaben nicht zusammen: Hinweis mit
# beiden Wegen (#564; seit rc.410 ohne die Behauptung, ein Regelmodul fehle).
desktop_workflow_status_ui_v1 <- function(state, modules = NULL) {
  if (identical(state$kind, "empty")) return(portelyra_status_panel("Noch kein abgeschlossener Lauf",
    "Der erste Abschluss entsteht in der App „Daten“ mit „Alles aktualisieren“. Der Start einer App rechnet nichts.", tone = "warning"))
  if (identical(state$kind, "error")) return(portelyra_status_panel("Abschluss nicht lesbar", pl_error_text_v1(state$code), tone = "error"))
  model <- state$model
  if (isTRUE(desktop_workflow_awaiting_bookings_v1(model))) return(portelyra_status_panel(
    paste("Portfolio", model$portfolio_label, "· wartet auf die ersten Buchungen"), DESKTOP_WORKFLOW_AWAITING_BOOKINGS_TEXT_V1, tone = "neutral"))
  tone <- if (model$status == "completed") "neutral" else if (model$status %in% c("partial", "stale")) "warning" else "error"
  tax <- Filter(function(row) identical(row$stage_code, "tax"), model$stages)
  untaxed <- length(tax) == 1L && identical(tax[[1L]]$status, "not_selected")
  tax_wanted <- untaxed && is.list(modules) && isTRUE(modules[["tax_report"]])
  if (tax_wanted && identical(tone, "neutral")) tone <- "warning"
  portelyra_status_panel(
    paste("Portfolio", model$portfolio_label, "· Datenraum", model$data_space_label),
    paste("Fassung", model$revision_label, "· Stand", .desktop_workflow_state_label_v1(model$status), if (tax_wanted) paste("· ohne Steuermodul, obwohl „Steuerbericht“ im Umfang gewählt ist. Mit Steuer: Daten → „4. Steuer“ einrichten und im Bereich „Abschluss“",
                "das Steuermodul wählen. Ohne Steuer: im Umfang „Steuerbericht“ abwählen") else if (untaxed) "· ohne Steuer (wie gewählt)" else if (isTRUE(desktop_workflow_projection_deselected_v1(model))) "· ohne Steuerprojektion (wie gewählt)",
          "· Versuch", .desktop_workflow_state_label_v1(model$attempt_status), "· Stichtag", pl_day_v1(model$as_of_date),
          "· abgeschlossen", pl_moment_v1(model$completed_at_utc), "· Aktualität", .desktop_workflow_state_label_v1(model$freshness_status)), tone = tone
  )
}

# Stufen und Gruende des Abschlusses in Worten (rc.314, #478; bis dahin standen die Kuerzel da). Unbekannte bleiben als Kuerzel.
DESKTOP_WORKFLOW_STAGE_LABELS_V1 <- c(canonical = "Stammdaten", fifo = "FIFO-Stand", tax = "Steuer", grouping = "Gruppierung",
  market = "Marktkurse", fx = "Wechselkurse", valuation = "Bewertung", trade_analysis = "Trade-Analyse", market_analysis = "Marktanalyse",
  publication = "Veröffentlichung")
DESKTOP_WORKFLOW_FAILURE_LABELS_V1 <- c(run_in_progress = "Lauf läuft noch", tax_plugin_not_selected = "kein Steuermodul gewählt",
  no_plugin = "kein Steuermodul gewählt", market_price_source_missing = "Kursquelle fehlt",
  desktop_workflow_fifo_blocked = "an der FIFO-Stufe angehalten", desktop_workflow_tax_blocked = "an der Steuer angehalten",
  desktop_workflow_grouping_blocked = "an der Gruppierung angehalten", desktop_workflow_market_blocked = "an den Marktkursen angehalten",
  desktop_workflow_fx_blocked = "an den Wechselkursen angehalten", desktop_workflow_valuation_blocked = "an der Bewertung angehalten",
  desktop_workflow_analysis_blocked = "an der Analyse angehalten", desktop_workflow_publication_blocked = "an der Veröffentlichung angehalten",
  market_price_carried_forward = "nicht jeder Kurs ist vom Stichtag",
  # Gruende je Position (#490).
  market_price_stale = "Kurs nicht vom Stichtag", market_price_missing = "Kurs fehlt", market_source_gap = "Lücke in der Kursquelle",
  market_corporate_action_review_required = "Kapitalmaßnahme prüfen", market_basis_fx_unavailable = "Wechselkurs fehlt",
  display_fx_unavailable = "Wechselkurs für die Anzeige fehlt", fifo_basis_unavailable = "FIFO-Basis fehlt",
  tax_projection_unavailable = "Steuerprojektion fehlt")
DESKTOP_WORKFLOW_FX_DIRECTION_LABELS_V1 <- c(none = "keine", direct = "direkt", inverse = "umgekehrt")
.desktop_workflow_label_of_v1 <- function(labels, value) {
  text <- if (is.null(value) || length(value) != 1L || is.na(value)) "" else as.character(value)
  if (!nzchar(text)) "—" else if (text %in% names(labels)) unname(labels[[text]]) else text
}
desktop_workflow_stage_frame_v1 <- function(model) {
  if (is.null(model)) return(data.frame())
  do.call(rbind, lapply(model$stages, function(row) data.frame(
    Stufe = .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_STAGE_LABELS_V1, row$stage_code), Stand = .desktop_workflow_state_label_v1(row$status),
    Grund = .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_FAILURE_LABELS_V1, row$failure_code),
    stringsAsFactors = FALSE, check.names = FALSE
  )))
}

# Spaltennamen der Abschluss-Tabellen (Cockpit "Abschluss im Detail", Analyse "Abschluss"). Unbekannte Felder behalten ihren
# Namen, damit nichts verschwindet.
DESKTOP_WORKFLOW_FIELD_LABELS_V1 <- c(
  currency = "Währung", target_currency = "Zielwährung", cash_balance_decimal = "Cash-Saldo",
  cross_currency_aggregation = "Währungen zusammengefasst", fee_total_decimal = "Gebühren", gross_income_decimal = "Erträge brutto",
  realized_fifo_cost_decimal = "Einstand des Verkauften (FIFO)", realized_gross_gain_decimal = "realisiert brutto",
  realized_gross_proceeds_decimal = "Umsatz (Verkaufserlöse)", asset_label = "Asset", asset_ordinal = "Asset Nr.",
  account_ordinal = "Konto Nr.", position_ordinal = "Position Nr.", listing_code = "Notierung", quantity_decimal = "Menge",
  fifo_cost_decimal = "Einstand (FIFO)", market_price_decimal = "Kurs", market_currency = "Kurswährung",
  market_observed_at_utc = "Kurs vom", market_value_decimal = "Marktwert", unrealized_gross_gain_decimal = "unrealisiert brutto",
  projected_tax_decimal = "Steuer (Projektion)", liquidation_fee_decimal = "Verkaufsgebühr (gedacht)",
  net_liquidation_decimal = "netto nach Verkauf (gedacht)", fx_rate_decimal = "Wechselkurs", fx_base_currency = "FX-Basis",
  fx_quote_currency = "FX-Notiz", fx_direction = "FX-Richtung", fx_observed_at_utc = "Wechselkurs vom", fx_status = "Stand FX",
  price_status = "Stand Kurs", tax_status = "Stand Steuer", position_status = "Stand", failure_codes = "Gründe",
  aggregation_status = "Zusammenfassung", position_count = "Positionen", completed_position_count = "vollständig bewertet",
  partial_position_count = "teilweise bewertet", blocked_position_count = "ohne Wert", valued_position_count = "bewertet",
  valued_fifo_cost_decimal = "Einstand (bewertete)", valued_market_value_decimal = "Marktwert (bewertete)",
  valued_unrealized_gross_gain_decimal = "unrealisiert (bewertete)", valued_projected_tax_decimal = "Steuer (bewertete)",
  valued_liquidation_fee_decimal = "Verkaufsgebühr (bewertete)", valued_net_liquidation_decimal = "netto nach Verkauf (bewertete)",
  period_start = "von", period_end = "bis", event_count = "Ereignisse", event_tax_status = "Stand Steuer",
  projected_event_tax_decimal = "Steuer (Projektion)", projected_event_net_gain_decimal = "netto (Projektion)",
  deposit_decimal = "Einlagen", withdrawal_decimal = "Entnahmen", as_of_date = "Stichtag", snapshot_status = "Stand",
  source_status = "Stand Quelle", last_covered_market_date = "letzter Kurstag", max_price_age_days = "ältester Kurs (Tage)",
  # Eingaben des Run Centers (#490).
  display_name = "Asset", asset_type = "Klasse", close_decimal = "Schlusskurs", observed_at_utc = "Kurs vom",
  tax_classification = "Steuer-Einordnung", partial_exemption_rate_decimal = "Teilfreistellung", fixed_fee_decimal = "feste Gebühr",
  percentage_fee_rate_decimal = "Gebühr in Prozent")
# Beträge mit Einheit, Mengen ohne Nullen am Ende, Daten als TT.MM.JJJJ (#529 Punkt 8). Die Einheit kommt aus der Zeile
# (Zielwährung, sonst Währung; beim Kurs die Kurswährung), sonst aus `currency`.
DESKTOP_WORKFLOW_DAY_FIELDS_V1 <- c("as_of_date", "period_start", "period_end", "last_covered_market_date")
# exact = FALSE: Beträge auf Cent, Mengen und Wechselkurse mit allen Stellen ohne Nullen am Ende; exact = TRUE zeigt die
# Werte so, wie der Abschluss sie führt (Festlegung 23.10.2026: Transparenz für die Rechnung).
# `untaxed`: Der Abschluss lief ohne gewaehlte Steuer (#564, rc.406). Dann zeigt die Tabelle keine Spalten fuer Steuer und Netto -
# angezeigt wird nur, was als Baustein gewaehlt ist (Festlegung 13.11.2026); leer waeren sie ohnehin, Brutto wird nie als Netto gezeigt.
DESKTOP_WORKFLOW_TAX_COLUMN_PATTERN_V1 <- "(^|_)(projected_tax|net_liquidation|projected_unrealized_tax|tax_status)(_|$)"
desktop_workflow_untaxed_v1 <- function(model) {
  if (!is.list(model)) return(FALSE)
  tax <- Filter(function(row) identical(row$stage_code, "tax"), model$stages)
  length(tax) == 1L && identical(tax[[1L]]$status, "not_selected") || isTRUE(desktop_workflow_projection_deselected_v1(model))
}
# Steuerbericht gewaehlt, Steuerprojektion nicht: Jede bewertete Position traegt "not_selected" (#564).
desktop_workflow_projection_deselected_v1 <- function(model) {
  positions <- if (is.list(model) && is.list(model$cockpit)) model$cockpit$positions else NULL
  is.list(positions) && length(positions) > 0L &&
    all(vapply(positions, function(row) identical(row$tax_status, "not_selected"), logical(1L)))
}
desktop_workflow_labeled_frame_v1 <- function(rows, exact = FALSE, currency = NULL, untaxed = FALSE) {
  frame <- desktop_workflow_rows_frame_v1(rows)
  if (!nrow(frame)) return(frame)
  if (isTRUE(untaxed)) frame <- frame[, !grepl(DESKTOP_WORKFLOW_TAX_COLUMN_PATTERN_V1, names(frame)), drop = FALSE]
  column <- function(name) if (name %in% names(frame)) frame[[name]] else NULL
  fallback <- if (is.null(currency)) "" else as.character(currency)[1L]
  unit <- column("target_currency"); if (is.null(unit)) unit <- column("currency"); if (is.null(unit)) unit <- rep(fallback, nrow(frame))
  unit[unit %in% c("—", "")] <- fallback
  price_unit <- column("market_currency"); if (is.null(price_unit)) price_unit <- unit
  dash <- function(values) { values[values == "—"] <- ""; values }
  for (name in names(frame)) {
    if (identical(name, "failure_codes")) frame[[name]] <- vapply(strsplit(frame[[name]], " | ", fixed = TRUE), function(codes)
      if (!length(codes) || identical(codes, "—")) "—" else paste(vapply(codes, function(code) .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_FAILURE_LABELS_V1, code), character(1L)), collapse = ", "),
      character(1L))
    else if (identical(name, "fx_direction")) frame[[name]] <- vapply(frame[[name]], function(value) .desktop_workflow_label_of_v1(DESKTOP_WORKFLOW_FX_DIRECTION_LABELS_V1, value), character(1L))
    else if (grepl("_status$", name)) frame[[name]] <- vapply(frame[[name]], .desktop_workflow_state_label_v1, character(1L))
    else if (identical(name, "cross_currency_aggregation")) {
      known <- c(not_applied = "nein", applied = "ja")
      frame[[name]] <- ifelse(frame[[name]] %in% names(known), unname(known[frame[[name]]]), frame[[name]])
    }
    else if (identical(name, "asset_type")) frame[[name]] <- pl_label_v1(PL_ASSET_TYPE_LABELS_V1, dash(frame[[name]]), "—")
    else if (name %in% DESKTOP_WORKFLOW_DAY_FIELDS_V1) frame[[name]] <- pl_day_v1(dash(frame[[name]]), "—")
    else if (grepl("_utc$", name)) frame[[name]] <- pl_moment_v1(dash(frame[[name]]), "—")
    else if (!isTRUE(exact) && grepl("_decimal$", name)) {
      values <- dash(frame[[name]])
      frame[[name]] <- if (name %in% c("quantity_decimal", "fx_rate_decimal")) pl_quantity_v1(values, "—")
        else if (name %in% c("market_price_decimal", "close_decimal")) pl_price_v1(values, price_unit, "—")
        else if (grepl("_rate_decimal$", name)) pl_percent_v1(values, 2L, "fraction", "—")
        else pl_amount_v1(values, unit, 2L, "—")
    }
  }
  labels <- DESKTOP_WORKFLOW_FIELD_LABELS_V1[names(frame)]
  names(frame) <- ifelse(is.na(labels), names(frame), labels)
  frame
}

desktop_workflow_rows_frame_v1 <- function(rows) {
  if (is.null(rows) || !length(rows)) return(data.frame())
  keys <- unique(unlist(lapply(rows, names), use.names = FALSE))
  text <- function(value) if (is.null(value)) "—" else if (is.list(value)) paste(unlist(value), collapse = " | ") else as.character(value)
  # Spaltenweise statt zeilenweise. Je Zeile einen eigenen einzeiligen
  # Datenrahmen zu bilden und alle mit rbind zu verbinden kostet rund ein
  # Viertel Millisekunde je Zeile und Aufbau; grosse Cash-Tabellen
# brauchten so viele Sekunden. Der schnelle Weg gilt nur fuer den Normalfall - Listenzeilen mit
  # eindeutigen Namen und genau einem Wert je Feld. Alles andere nimmt weiter den
  # bisherigen Weg, damit sich fuer keinen Sonderfall das Ergebnis aendert.
  regular <- length(keys) > 0L && all(vapply(rows, function(row) {
    labels <- names(row)
    is.list(row) && !is.data.frame(row) && length(labels) == length(row) && !anyNA(labels) &&
      all(nzchar(labels)) && !anyDuplicated(labels)
  }, logical(1L)))
  if (regular) {
    # Spaltenfolge wie bisher: die Felder der ersten Zeile, danach die uebrigen.
    ordered <- c(names(rows[[1L]]), setdiff(keys, names(rows[[1L]])))
    columns <- lapply(ordered, function(key) lapply(rows, function(row) text(row[[key]])))
    if (all(vapply(columns, function(column) all(lengths(column) == 1L), logical(1L)))) {
      names(columns) <- ordered
      return(as.data.frame(lapply(columns, function(column) unlist(column, use.names = FALSE)),
                           stringsAsFactors = FALSE, check.names = FALSE))
    }
  }
  values <- lapply(rows, function(row) {
    row[keys] <- lapply(row[keys], text)
    as.data.frame(row, stringsAsFactors = FALSE, check.names = FALSE)
  })
  do.call(rbind, values)
}

# Bereitschaft und Frische im Klartext (#189). Die Matrix selbst bleibt
# abfragefrei; hier werden ihre Codes nur benannt, damit sichtbar wird, warum
# eine Bewertung noch nicht belastbar ist.
.portelyra_readiness_area <- c(
  canonical_activity = "Buchungen", fifo_basis = "FIFO-Basis", time_ordering = "Zeitliche Ordnung",
  migration_quarantine = "Übernahme aus Altbestand", derivative_activity = "Abgeleitete Buchungen",
  cash_coverage = "Cash-Abdeckung", market_history = "Marktpreise", fx_history = "Wechselkurse",
  tax_policy = "Steuerliche Einstellungen")
.portelyra_readiness_status <- c(
  complete = "vollständig", partial = "teilweise", stale = "veraltet", unavailable = "nicht vorhanden",
  blocked = "gesperrt", not_applicable = "nicht nötig")
.portelyra_readiness_reason <- c(
  active_schema401_generation = "Aktive Buchungsgeneration liegt vor.",
  active_schema401_absent = "Es sind noch keine Buchungen erfasst.",
  fifo_v2_fresh = "Bestand und realisierte GuV sind auf dem Stand der Buchungen.",
  fifo_v2_stale = "Seit der letzten Rechnung wurde gebucht oder korrigiert: in der App „Daten“ unter „Transaktionen → Bestand prüfen“ nachrechnen.",
  fifo_v2_unavailable = "Noch keine Berechnung vorhanden.",
  explicit_order_fresh = "Reihenfolge der Buchungen ist festgelegt.",
  explicit_order_stale = "Reihenfolge wird nach der nächsten Berechnung wieder verlässlich.",
  explicit_order_unavailable = "Noch keine Berechnung vorhanden.",
  all_declared_periods_reconciled = "Alle erfassten Zeiträume sind abgeglichen.",
  cash_coverage_partial_or_income_only = "Für mindestens ein Konto ist der Saldo nicht belegt.",
  cash_not_declared = "Für kein Konto ist eine Cash-Abdeckung erfasst.",
  no_completed_valuation = "Es wurde noch keine Marktbewertung abgeschlossen.",
  valuation_evidence_unreadable = "Der Bewertungsbeleg ist nicht lesbar; die Bewertung gilt als nicht vorhanden.",
  valuation_without_assets = "Die abgeschlossene Bewertung enthält kein Asset.",
  assets_without_valuation = "Für gehaltene Assets fehlt eine Bewertung.",
  valuation_days_incomplete = "Für einzelne Tage fehlen Preise.",
  valuation_complete = "Alle gehaltenen Assets sind durchgehend bewertet.",
  no_foreign_currency_demand = "Es werden keine Fremdwährungen benötigt.",
  fx_days_open = "Für einzelne Tage fehlen Wechselkurse.",
  fx_days_substituted = "Einzelne Kurse stammen aus einer Ersatzquelle.",
  fx_complete = "Alle benötigten Wechselkurse liegen vor.",
  tax_projection_not_requested = "Noch nicht eingerichtet.",
  quarantine_excluded = "Teile des Altbestands sind ausgenommen.", no_quarantine = "Nichts ausgenommen.",
  derivative_schema401_blocked = "Abgeleitete Buchungen sind gesperrt.", no_derivative_block = "Keine Sperre.",
  fresh_product_no_migration_receipt = "Keine Altdaten übernommen.", no_migration_derivative_scope = "Keine Altdaten übernommen.")

.portelyra_readiness_detail <- function(row) {
  detail <- row$detail
  if (!is.list(detail)) return("")
  count <- function(value) if (is.null(value)) 0L else as.integer(value)
  parts <- character(0)
  plural <- function(value, one, many) sprintf(if (value == 1L) one else many, value)
  if (identical(row$dimension_code, "market_history")) {
    if (count(detail$asset_without_valuation_count) > 0L) parts <- c(parts, plural(count(detail$asset_without_valuation_count), "%d Asset ohne Bewertung", "%d Assets ohne Bewertung"))
    if (count(detail$incomplete_asset_count) > 0L) parts <- c(parts, plural(count(detail$incomplete_asset_count), "%d Asset mit Lücken", "%d Assets mit Lücken"))
    if (count(detail$valued_asset_count) > 0L) parts <- c(parts, sprintf("%d bewertet", count(detail$valued_asset_count)))
  }
  if (identical(row$dimension_code, "fx_history") && count(detail$open_fx_day_count) > 0L)
    parts <- c(parts, plural(count(detail$open_fx_day_count), "%d offener Kurstag", "%d offene Kurstage"))
  if (!is.null(detail$as_of_date)) parts <- c(parts, paste("Stand", format(as.Date(detail$as_of_date), "%d.%m.%Y")))
  paste(parts, collapse = " · ")
}

portelyra_readiness_frame_v1 <- function(model) {
  if (!is.list(model) || !length(model$dimensions)) return(data.frame())
  rows <- model$dimensions
  label <- function(map, key, fallback) { value <- unname(map[[key]]); if (is.null(value) || is.na(value)) fallback else value }
  data.frame(check.names = FALSE, stringsAsFactors = FALSE,
    Bereich = vapply(rows, function(row) label(.portelyra_readiness_area, row$dimension_code, row$dimension_code), character(1L)),
    Stand = vapply(rows, function(row) label(.portelyra_readiness_status, row$status, row$status), character(1L)),
    Bedeutung = vapply(rows, function(row) {
      text <- label(.portelyra_readiness_reason, row$reason_code, row$reason_code)
      detail <- .portelyra_readiness_detail(row)
      if (nzchar(detail)) paste0(text, " (", detail, ")") else text
    }, character(1L)))
}

# Eine Zeile, die sagt, ob eine Bewertung belastbar ist - und wenn nicht, woran es liegt.
portelyra_readiness_headline_v1 <- function(model) {
  if (!is.list(model) || !length(model$dimensions)) return("Bereitschaft noch nicht gelesen.")
  if (isTRUE(model$market_valuation_ready)) return("Bewertung belastbar: Buchungen, Bestand, Marktpreise und Wechselkurse sind vollständig.")
  # Nur was die Bewertung selbst traegt; Steuer und Altbestand haengen nicht daran.
  relevant <- c("canonical_activity", "fifo_basis", "time_ordering", "market_history", "fx_history")
  open <- Filter(function(row) row$dimension_code %in% relevant && !row$status %in% c("complete", "not_applicable"), model$dimensions)
  if (!length(open)) return("Bewertung noch nicht belastbar.")
  areas <- vapply(open, function(row) {
    area <- unname(.portelyra_readiness_area[[row$dimension_code]])
    if (is.null(area) || is.na(area)) row$dimension_code else area
  }, character(1L))
  paste0("Bewertung noch nicht belastbar — offen: ", paste(unique(areas), collapse = ", "), ".")
}
