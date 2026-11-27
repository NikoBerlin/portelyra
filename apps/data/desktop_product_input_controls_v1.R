desktop_product_empty_date_input_v1 <- function(input_id, label) {
  if (!is.character(input_id) || length(input_id) != 1L || is.na(input_id) || !nzchar(input_id) ||
      !is.character(label) || length(label) != 1L || is.na(label) || !nzchar(label)) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  # Shiny turns value=NULL into the browser's current date during initialization.
  # An explicit empty initial value keeps optional and required dates user-authored.
  # Anzeige deutsch (0.3.4, #578): TT.MM.JJJJ, Kalender ab Montag. Bis 0.3.3 stand hier yyyy-mm-dd mit englischem Kalender; ein deutsch
  # getipptes Datum lehnte der Kern ohne genauen Grund ab. Der Server bekommt das Datum weiter als Date (Shiny wandelt).
  control <- suppressWarnings(shiny::dateInput(input_id, label, value = "", format = "dd.mm.yyyy", language = "de", weekstart = 1))
  input_tag <- control$children[[2L]]
  if (!inherits(input_tag, "shiny.tag") || !identical(input_tag$name, "input") ||
      !identical(input_tag$attribs[["data-initial-date"]], "")) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  control
}

desktop_product_manual_decimal_v1 <- function(value) {
  if (is.null(value) || length(value) == 0L) return("")
  if (!is.character(value) || length(value) != 1L || is.na(value)) return(value)
  normalized <- trimws(value)
  if (!grepl("^(0|[1-9][0-9]*)([.,][0-9]+)?$", normalized)) return(normalized)
  normalized <- sub(",", ".", normalized, fixed = TRUE)
  if (grepl(".", normalized, fixed = TRUE)) {
    normalized <- sub("0+$", "", normalized)
    normalized <- sub("\\.$", "", normalized)
  }
  normalized
}

desktop_product_activity_event_policy_v1 <- function(event_type) {
  policies <- list(
    buy = list(amount_modes=c("quantity_unit_price"), basis_modes=c("derived_trade"), default_amount_mode="quantity_unit_price", default_basis_mode="derived_trade"),
    sell = list(amount_modes=c("quantity_unit_price"), basis_modes=c("not_applicable"), default_amount_mode="quantity_unit_price", default_basis_mode="not_applicable"),
    dividend = list(amount_modes=c("quantity_unit_price","gross_total"), basis_modes=c("not_applicable"), default_amount_mode="quantity_unit_price", default_basis_mode="not_applicable"),
    stock_dividend = list(amount_modes=c("quantity_unit_price"), basis_modes=c("valuation_confirmed_as_basis","provided_basis","basis_missing"), default_amount_mode="quantity_unit_price", default_basis_mode="valuation_confirmed_as_basis"),
    # Der Kern nimmt einen Reward auch mit Brutto-Gesamtbetrag an, und die Importer
    # buchen ihn so. Solange die Maske diese Betragsart fuer Rewards nicht kannte,
    # stimmte eine so gebuchte Buchung nie mit dem Formular ueberein: Sie galt nie
    # als geladen und liess sich nur stornieren, nicht
    # bearbeiten.
    reward = list(amount_modes=c("quantity_unit_price","gross_total"), basis_modes=c("valuation_confirmed_as_basis","provided_basis","basis_missing"), default_amount_mode="quantity_unit_price", default_basis_mode="valuation_confirmed_as_basis"),
    deposit = list(amount_modes=c("quantity_unit_price","gross_total","not_applicable"), basis_modes=c("provided_basis","basis_missing"), default_amount_mode="quantity_unit_price", default_basis_mode="provided_basis"),
    withdrawal = list(amount_modes=c("not_applicable"), basis_modes=c("not_applicable"), default_amount_mode="not_applicable", default_basis_mode="not_applicable"),
    transfer = list(amount_modes=c("not_applicable"), basis_modes=c("not_applicable"), default_amount_mode="not_applicable", default_basis_mode="not_applicable")
  )
  if (!is.character(event_type) || length(event_type) != 1L || is.na(event_type) || is.null(policies[[event_type]])) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  policies[[event_type]]
}

# Betragsarten, die nur das Formular kennt: Eine Dividende kann netto eingetragen
# werden, mit dem Steuersatz, der darin schon abgezogen ist. Das Formular rechnet
# daraus den Bruttobetrag; der Kern bekommt ihn als "gross_total" und erfaehrt von
# Netto und Steuersatz nichts (Festlegung vom 09.10.2026).
desktop_product_activity_net_amount_modes_v1 <- function() c("net_total", "net_quantity_unit_price")

desktop_product_activity_amount_mode_choices_v1 <- function(event_type) {
  modes <- desktop_product_activity_event_policy_v1(event_type)$amount_modes
  if (identical(event_type, "dividend")) c(modes, desktop_product_activity_net_amount_modes_v1()) else modes
}

desktop_product_activity_core_amount_mode_v1 <- function(event_type, amount_input_mode) {
  if (identical(event_type, "dividend") && is.character(amount_input_mode) && length(amount_input_mode) == 1L &&
      !is.na(amount_input_mode) && amount_input_mode %in% desktop_product_activity_net_amount_modes_v1()) "gross_total" else amount_input_mode
}

desktop_product_activity_event_form_v1 <- function(event_type, amount_input_mode, basis_evidence_mode) {
  policy <- desktop_product_activity_event_policy_v1(event_type)
  list(
    amount_input_mode = if (is.character(amount_input_mode) && length(amount_input_mode) == 1L && !is.na(amount_input_mode) && amount_input_mode %in% policy$amount_modes) amount_input_mode else policy$default_amount_mode,
    basis_evidence_mode = if (is.character(basis_evidence_mode) && length(basis_evidence_mode) == 1L && !is.na(basis_evidence_mode) && basis_evidence_mode %in% policy$basis_modes) basis_evidence_mode else policy$default_basis_mode
  )
}

# Zur Betragsart gehoert genau ein Betragsfeld: der Stueckpreis oder der
# Brutto-Gesamtbetrag. Die Oberflaeche blendet das andere nur aus; sein Wert blieb
# stehen und ging mit ins Formular. Der Kern lehnt beide Angaben zugleich ab
# (asset_activity_amount_invalid), und wer eine als "Menge x Stueckpreis" gebuchte
# Dividende auf den Brutto-Gesamtbetrag umstellen wollte, bekam nur "Aktion
# blockiert" - das stoerende Feld war nicht mehr zu sehen und damit auch nicht zu
# leeren. Ein Feld, das
# zur gewaehlten Betragsart nicht gehoert, zaehlt deshalb nicht.
desktop_product_activity_amount_fields_v1 <- function(amount_input_mode, unit_price_decimal, gross_amount_decimal) {
  list(
    unit_price_decimal = if (identical(amount_input_mode, "quantity_unit_price")) unit_price_decimal else "",
    gross_amount_decimal = if (identical(amount_input_mode, "gross_total")) gross_amount_decimal else ""
  )
}

# Welche dieser Felder der Kern je Buchungsart ueberhaupt annimmt
# (migrations/reference/asset_activity_v1.py): eine Geldgebuehr nur bei Kauf und
# Verkauf, eine dividendenberechtigte Menge nur bei der Bardividende. Das Formular
# bot die Geldgebuehr auch bei Dividende, Reward und Einlieferung an und die
# berechtigte Menge auch bei der Stockdividende - jede Eingabe dort endete in
# "Aktion blockiert". Was der Kern nie annimmt, wird nicht
# angeboten und zaehlt nicht. (Beim Transfer naehme der Kern eine Geldgebuehr an;
# das Formular hat sie dort nie angeboten, und dabei bleibt es hier.)
# tests/contracts/test_asset_activity_v1.py haelt die Kernseite dieser Tabelle fest.
desktop_product_activity_field_applies_v1 <- function(event_type, field) {
  if (!is.character(field) || length(field) != 1L || !field %in% c("monetary_fee", "eligible_quantity")) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  known <- is.character(event_type) && length(event_type) == 1L && !is.na(event_type) && event_type %in% DESKTOP_ACTIVITY_EVENT_TYPES
  known && field %in% desktop_product_activity_relevant_fields_v1(event_type)
}

# Die Felder der Maske, die nur je Buchungsart erscheinen (#422). Datum, Uhrzeit, Zeitzone und Konto gelten fuer alle.
DESKTOP_ACTIVITY_EVENT_TYPES <- c("buy", "sell", "dividend", "stock_dividend", "reward", "deposit", "withdrawal", "transfer")
DESKTOP_ACTIVITY_TYPED_FIELDS <- c("related_account", "source_asset", "quantity", "eligible_quantity", "amount_mode", "unit_price",
  "gross_total", "net_total", "net_unit_price", "net_tax_rate", "monetary_fee", "asset_fee", "basis_mode", "provided_basis",
  "movement_context", "acquisition")

# Welche dieser Felder der Kern bei Buchungsart, Betragsart und Basis liest (migrations/reference/asset_activity_v1.py,
# _normalize_event). Die Maske zeigte bis rc.329 Felder, die der Kern dort ablehnt - die Stueck-Gebuehr bei Kauf und
# Verkauf, die Menge bei der Bardividende -, und versteckte zwei Pflichtangaben der Einlieferung im Aufklapper. Eine Liste
# fuer beides: Was hier fehlt, zeigt die Maske nicht, und das Formular schickt es leer bzw. als "nicht anwendbar".
# tests/contracts/test_data_activity_relevant_fields_v1.R prueft sie gegen den Kern.
desktop_product_activity_relevant_fields_v1 <- function(event_type, amount_input_mode = NULL, basis_evidence_mode = NULL) {
  policy <- desktop_product_activity_event_policy_v1(event_type)
  choices <- desktop_product_activity_amount_mode_choices_v1(event_type)
  pick <- function(value, allowed, default) if (is.character(value) && length(value) == 1L && !is.na(value) && value %in% allowed) value else default
  amount <- pick(amount_input_mode, choices, policy$default_amount_mode)
  core_amount <- desktop_product_activity_core_amount_mode_v1(event_type, amount)
  basis <- pick(basis_evidence_mode, policy$basis_modes, policy$default_basis_mode)
  net <- desktop_product_activity_net_amount_modes_v1()
  c(if (identical(event_type, "transfer")) "related_account",
    if (identical(event_type, "stock_dividend")) "source_asset",
    # Die Bardividende rechnet mit der dividendenberechtigten Menge; eine Menge nimmt der Kern dort nicht an.
    if (!identical(event_type, "dividend")) "quantity" else "eligible_quantity",
    if (length(choices) > 1L) "amount_mode",
    if (identical(amount, "quantity_unit_price")) "unit_price",
    if (identical(amount, "gross_total")) "gross_total",
    if (identical(amount, "net_total")) "net_total",
    if (identical(amount, "net_quantity_unit_price")) "net_unit_price",
    if (amount %in% net) "net_tax_rate",
    if (event_type %in% c("buy", "sell")) "monetary_fee",
    if (event_type %in% c("reward", "withdrawal", "transfer")) "asset_fee",
    if (length(policy$basis_modes) > 1L) "basis_mode",
    # Bei der Einlieferung ist die belegte Basis nur ohne Betrag eine eigene Angabe; sonst ist der Betrag die Basis.
    if (identical(basis, "provided_basis") && (!identical(event_type, "deposit") || identical(core_amount, "not_applicable"))) "provided_basis",
    if (event_type %in% c("deposit", "withdrawal")) "movement_context",
    if (identical(event_type, "deposit")) "acquisition")
}

# Kombinationen, die der Kern unabhaengig von den Feldern ablehnt: Eine Einlieferung ohne Basis hat keinen Wert, also nur
# "Nicht anwendbar" als Betragsart. Die Maske nennt das, statt den Sammelcode des Kerns zu zeigen.
desktop_product_activity_combination_complaint_v1 <- function(event_type, amount_input_mode, basis_evidence_mode) {
  if (identical(event_type, "deposit") && identical(basis_evidence_mode, "basis_missing") && !identical(amount_input_mode, "not_applicable"))
    return("Bei „Basis fehlt“ hat die Einlieferung keinen Wert: unter „Wert eingeben als“ „Nicht anwendbar“ wählen.")
  NULL
}

# Sichtbarkeitsbedingung eines Feldes, abgeleitet aus der Liste darueber - nicht je Feld von Hand gepflegt, damit Maske und
# Kern nicht wieder auseinanderlaufen. Haengt ein Feld nur an der Buchungsart, prueft die Bedingung nur sie.
desktop_product_activity_field_condition_v1 <- function(field) {
  if (!is.character(field) || length(field) != 1L || !field %in% DESKTOP_ACTIVITY_TYPED_FIELDS) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  quoted <- function(values) paste(sprintf("'%s'", values), collapse = ",")
  whole <- character(); parts <- character()
  for (type in DESKTOP_ACTIVITY_EVENT_TYPES) {
    amounts <- desktop_product_activity_amount_mode_choices_v1(type)
    bases <- desktop_product_activity_event_policy_v1(type)$basis_modes
    hit <- matrix(vapply(seq_len(length(amounts) * length(bases)), function(index) {
      field %in% desktop_product_activity_relevant_fields_v1(type, amounts[(index - 1L) %% length(amounts) + 1L],
        bases[(index - 1L) %/% length(amounts) + 1L])
    }, logical(1L)), nrow = length(amounts), dimnames = list(amounts, bases))
    if (all(hit)) { whole <- c(whole, type); next }
    if (!any(hit)) next
    by_amount <- apply(hit, 1L, all); by_basis <- apply(hit, 2L, all)
    if (all(by_amount | !apply(hit, 1L, any))) {
      parts <- c(parts, sprintf("(input.activity_type=='%s' && [%s].indexOf(input.activity_amount_mode)>=0)", type, quoted(amounts[by_amount])))
    } else if (all(by_basis | !apply(hit, 2L, any))) {
      parts <- c(parts, sprintf("(input.activity_type=='%s' && [%s].indexOf(input.activity_basis_mode)>=0)", type, quoted(bases[by_basis])))
    } else {
      pairs <- which(hit, arr.ind = TRUE)
      parts <- c(parts, sprintf("(input.activity_type=='%s' && input.activity_amount_mode=='%s' && input.activity_basis_mode=='%s')",
        type, amounts[pairs[, 1L]], bases[pairs[, 2L]]))
    }
  }
  condition <- c(if (length(whole)) sprintf("[%s].indexOf(input.activity_type)>=0", quoted(whole)), parts)
  if (!length(condition)) "false" else paste(condition, collapse = " || ")
}

# Ein Feld der Transaktionsmaske, das nur erscheint, wenn der Kern es bei der gewaehlten Buchungsart liest.
desktop_product_activity_field_v1 <- function(field, ...) shiny::conditionalPanel(desktop_product_activity_field_condition_v1(field), ...)

desktop_product_activity_time_form_v1 <- function(
  event_time_evidence, local_date, local_time, time_zone, effective_at_utc,
  original_acquired_time_evidence, original_acquired_local_date,
  original_acquired_local_time, original_acquired_time_zone, original_acquired_at_utc
) {
  value <- list(
    event_time_evidence = event_time_evidence,
    local_date = local_date,
    local_time = local_time,
    time_zone = time_zone,
    effective_at_utc = effective_at_utc,
    original_acquired_time_evidence = original_acquired_time_evidence,
    original_acquired_local_date = original_acquired_local_date,
    original_acquired_local_time = original_acquired_local_time,
    original_acquired_time_zone = original_acquired_time_zone,
    original_acquired_at_utc = original_acquired_at_utc
  )
  if (identical(event_time_evidence, "date_only")) {
    value$local_time <- ""
    value$effective_at_utc <- ""
  } else if (identical(event_time_evidence, "exact") &&
             is.character(value$local_time) && length(value$local_time)==1L) {
    if(grepl("^[0-9]{2}:[0-9]{2}$",value$local_time)){
      value$local_time<-paste0(value$local_time,":00")
    }else if(grepl("^[0-9]{2}:[0-9]{2}:[0-9]{2}\\.0+$",value$local_time)){
      value$local_time<-sub("\\.0+$","",value$local_time)
    }
  }
  if (identical(original_acquired_time_evidence, "not_applicable")) {
    value$original_acquired_local_date <- ""
    value$original_acquired_local_time <- ""
    value$original_acquired_time_zone <- ""
    value$original_acquired_at_utc <- ""
  } else if (identical(original_acquired_time_evidence, "date_only")) {
    value$original_acquired_local_time <- ""
    value$original_acquired_at_utc <- ""
  }
  value
}

# Sichtbarkeitsbedingung eines Cash-Coverage-Feldes, abgeleitet aus der
# Relevanzliste des Editors. Abgeleitet, nicht gepflegt: eine handgeschriebene
# Bedingung je Feld laeuft mit dem Kern auseinander, und genau daran scheiterte
# die Oberflaeche - sie zeigte alle zwanzig Felder immer, auch die sechs, die
# "Coverage-Zeitraum erklaeren" gar nicht liest (04.10.2026, #422).
desktop_product_cash_field_condition_v1 <- function(form_field) {
  if (!is.character(form_field) || length(form_field) != 1L || is.na(form_field) || !nzchar(form_field)) {
    stop("desktop_product_input_control_invalid", call. = FALSE)
  }
  aktionen <- c("declare_coverage", "record_cash_event", "record_interest_income",
                "record_reconciliation", "correct", "supersede", "void")
  liest <- function(action, mode) form_field %in% data_cash_coverage_editor_relevant_fields_v1(action, mode)
  immer <- Filter(function(action) liest(action, "not_tracked"), aktionen)
  # Der Eroeffnungssaldo und die Abstimmung einer Erklaerung haengen zusaetzlich
  # am Coverage-Modus: nur eine vollstaendig abgestimmte Erklaerung liest sie.
  nur_vollstaendig <- !"declare_coverage" %in% immer && liest("declare_coverage", "complete_reconciled")
  teile <- c(
    if (length(immer)) sprintf("[%s].indexOf(input.cash_action)>=0",
      paste(sprintf("'%s'", immer), collapse = ",")) else NULL,
    if (nur_vollstaendig) "(input.cash_action=='declare_coverage' && input.cash_coverage_mode=='complete_reconciled')" else NULL
  )
  if (!length(teile)) return("false")
  paste(teile, collapse = " || ")
}

# Ein Feld der Cash-Coverage-Karte, das nur erscheint, wenn die gewaehlte Aktion
# es liest.
desktop_product_cash_field_v1 <- function(form_field, control) {
  shiny::conditionalPanel(condition = desktop_product_cash_field_condition_v1(form_field), control)
}


# Was an den Eingaben des Run Centers nicht stimmt - in Worten und mit dem Feld.
# Der Vertrag (desktop_run_center_prepare_v1) prueft dasselbe und meldet fuer
# alles denselben Code, desktop_run_center_input_invalid. NULL heisst: Aus Sicht
# dieser Pruefung passt die Form; der Vertrag prueft weiterhin selbst.
desktop_product_run_form_complaint_v1 <- function(form, assets = list(), now = as.POSIXct(Sys.time(), tz = "UTC")) {
  missing <- function(value) is.null(value) || !is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value)
  if (missing(form$portfolio_ref)) return("Bitte zuerst ein Portfolio wählen.")
  if (missing(form$run_mode)) return("Bitte einen Modus wählen.")
  if (missing(form$as_of_date)) return("Bitte ein Bewertungsdatum wählen.")
  if (missing(form$cutoff_at_utc)) return("Der Stichzeitpunkt ist leer. Er folgt aus dem Bewertungsdatum \u2014 Datum einmal neu setzen.")
  utc <- function(value) grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value) &&
    !is.na(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  if (!utc(form$cutoff_at_utc)) return("Der Stichzeitpunkt hat nicht die Form 2026-10-10T00:00:00Z. Bewertungsdatum einmal neu setzen, dann wird er richtig vorbelegt.")
  # Der FIFO-Lauf weist einen Cutoff nach dem Ausfuehrungszeitpunkt ab (semantic_realized_fifo_input_invalid, im Run nur
  # "desktop_workflow_fifo_blocked"); zwischen Mitternacht und 2 Uhr lag die Tagesgrenze nach dem Bewertungsdatum noch vorn.
  if (as.POSIXct(form$cutoff_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") > now)
    return("Der Stichzeitpunkt liegt in der Zukunft. Ein früheres Bewertungsdatum wählen oder den Stichzeitpunkt auf die jetzige Zeit (UTC) setzen.")
  if (missing(form$tax_mode)) return("Bitte ein Steuermodul wählen.")
  # Dieselbe Form wie im Vertrag: Dezimalpunkt, keine angehaengten Nullen.
  decimal <- function(value, label, positive = FALSE) {
    if (missing(value)) return(NULL)
    if (!grepl("^(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value) || (positive && grepl("^0(\\.0*)?$", value)))
      return(paste0("„", label, "\u201c ist so nicht lesbar (\u201e", value, "\u201c): bitte mit Dezimalpunkt statt Komma, ohne angehängte Nullen",
        if (positive) " und größer als null" else " und nicht negativ", " \u2014 zum Beispiel 0.25 statt 0,25 oder 0.250."))
    NULL
  }
  for (field in list(
    list(form$capital_income_tax_rate, "Kapitalertragsteuersatz"), list(form$personal_income_tax_rate, "Persönlicher Satz"),
    list(form$solidarity_surcharge_rate, "Solidaritätszuschlag"), list(form$church_tax_rate, "Kirchensteuersatz"),
    list(form$fee_fixed_decimal, "Fester Betrag je Trade in EUR"), list(form$fee_percentage_rate_decimal, "Fester Prozentsatz vom Umsatz"))) {
    complaint <- decimal(field[[1L]], field[[2L]])
    if (!is.null(complaint)) return(complaint)
  }
  if (identical(form$tax_mode, "de_reference_v2")) {
    if (missing(form$church_tax_applicable)) {
      return("Das deutsche Referenzmodell v2 verlangt eine ausdrückliche Angabe zur Kirchensteuer: „Anwendbar\u201c oder „Nicht anwendbar\u201c.")
    }
    if (identical(form$church_tax_applicable, "applicable") && missing(form$church_tax_rate)) {
      return("Bei anwendbarer Kirchensteuer muss der Kirchensteuersatz gefüllt sein.")
    }
    if (!identical(form$church_tax_applicable, "applicable") && !missing(form$church_tax_rate)) {
      return("Bei „Nicht anwendbar\u201c muss der Kirchensteuersatz leer bleiben.")
    }
  } else if (!missing(form$church_tax_applicable) || !missing(form$church_tax_rate)) {
    return("Die Angaben zur Kirchensteuer gelten nur für das deutsche Referenzmodell v2. Bitte „Kirchensteuer anwendbar\u201c auf „Bitte wählen\u201c stellen und den Kirchensteuersatz leeren \u2014 oder das Modell v2 wählen.")
  }
  if (missing(form$fee_source)) {
    return("Die Auswahl „Liquidationsgebühr \u00b7 Quelle\u201c fehlt. Wahrscheinlich ist die Seite veraltet: bitte neu laden.")
  }
  if (identical(form$fee_source, "fixed_per_trade") && missing(form$fee_fixed_decimal)) {
    return("Bei fester Gebühr muss „Fester Betrag je Trade in EUR\u201c gefüllt sein.")
  }
  if (identical(form$fee_source, "percentage_of_turnover") && missing(form$fee_percentage_rate_decimal)) {
    return("Bei prozentualer Gebühr muss „Fester Prozentsatz vom Umsatz\u201c gefüllt sein.")
  }
  labels <- stats::setNames(
    vapply(assets, function(asset) if (missing(asset$label)) asset$ref else asset$label, character(1L)),
    vapply(assets, function(asset) asset$ref, character(1L)))
  if (!is.list(form$asset_inputs) || length(form$asset_inputs) != length(assets)) {
    return("Die Eingaben je Asset passen nicht zum Katalog. Bitte „Abschluss-Eingaben lesen\u201c erneut ausführen.")
  }
  for (row in form$asset_inputs) {
    card <- function(copy) paste0("Manueller Nachweis für „", if (missing(row$asset_ref) || is.na(labels[row$asset_ref])) "?" else labels[[row$asset_ref]], "\u201c: ", copy)
    # Fehlt das Pflichtfeld einer Karte ganz, ist die Karte im Browser noch nicht
    # aufgebaut - das ist keine Eingabe des Eigentuemers.
    if (missing(row$tax_classification) || missing(row$fx_direction)) {
      return(card("Die Felder sind noch nicht geladen. Bitte kurz warten oder „Abschluss-Eingaben lesen\u201c erneut ausführen, dann den Plan noch einmal prüfen."))
    }
    if (!missing(row$market_currency) && !grepl("^[A-Z]{3}$", row$market_currency)) {
      return(card("Die Kurswährung braucht drei Großbuchstaben, etwa EUR oder USD."))
    }
    for (field in list(list(row$close_decimal, "Schlusskurs", TRUE), list(row$partial_exemption_rate_decimal, "Teilfreistellung", FALSE),
                       list(row$fixed_fee_decimal, "Liquidationsgebühr fix", FALSE), list(row$percentage_fee_rate_decimal, "Liquidationsgebühr %", FALSE),
                       list(row$fx_rate_decimal, "Devisenkurs", TRUE))) {
      complaint <- decimal(field[[1L]], field[[2L]], field[[3L]])
      if (!is.null(complaint)) return(card(complaint))
    }
    for (field in list(list(row$observed_at_utc, "Kurszeitpunkt (UTC)"), list(row$fx_observed_at_utc, "Devisenkurszeitpunkt (UTC)"))) {
      if (!missing(field[[1L]]) && !utc(field[[1L]])) return(card(paste0("„", field[[2L]], "\u201c hat nicht die Form 2026-10-09T16:00:00Z.")))
    }
    if (!missing(row$close_decimal) && (missing(row$listing_code) || missing(row$market_currency) || missing(row$observed_at_utc))) {
      return(card("Ein eigener Schlusskurs braucht auch Notierungscode, Kurswährung und Kurszeitpunkt (UTC) \u2014 oder das Feld \u201eSchlusskurs\u201c bleibt leer."))
    }
    for (field in list(list(row$fx_base_currency, "FX Basiswährung"), list(row$fx_quote_currency, "FX Quotierungswährung"))) {
      if (!missing(field[[1L]]) && !grepl("^[A-Z]{3}$", field[[1L]])) return(card(paste0("„", field[[2L]], "\u201c braucht drei Großbuchstaben.")))
    }
    if (!identical(row$fx_direction, "none") &&
        (missing(row$fx_base_currency) || missing(row$fx_quote_currency) || missing(row$fx_rate_decimal) || missing(row$fx_observed_at_utc))) {
      return(card("Eine eigene Devisenroute braucht Basiswährung, Quotierungswährung, Devisenkurs und Devisenkurszeitpunkt (UTC) \u2014 oder die Route steht auf „Keine\u201c."))
    }
  }
  NULL
}

# Manuelle Evidenz je Asset im Run Center (#422, Festlegung 17.10.2026, Variante 1): eine Karte mit Suche statt einer Karte je
# Asset. Die Werte stehen serverseitig je Asset; der Lauf liest weiterhin fuer jedes aktive Asset alle Felder. Vorher baute das
# Oeffnen 13 Eingaben je Asset.
DESKTOP_RUN_EVIDENCE_FIELDS <- c(listing_code = "run_ev_listing", market_currency = "run_ev_currency", close_decimal = "run_ev_close",
  observed_at_utc = "run_ev_observed", tax_classification = "run_ev_tax", partial_exemption_rate_decimal = "run_ev_partial",
  fixed_fee_decimal = "run_ev_fixed_fee", percentage_fee_rate_decimal = "run_ev_percentage_fee", fx_base_currency = "run_ev_fx_base",
  fx_quote_currency = "run_ev_fx_quote", fx_direction = "run_ev_fx_direction", fx_rate_decimal = "run_ev_fx_rate",
  fx_observed_at_utc = "run_ev_fx_observed")
DESKTOP_RUN_EVIDENCE_LABELS <- c(listing_code = "Notierungscode", market_currency = "Kurswährung", close_decimal = "Schlusskurs",
  observed_at_utc = "Kurszeitpunkt (UTC)", tax_classification = "Steuerliche Einordnung", partial_exemption_rate_decimal = "Teilfreistellung",
  fixed_fee_decimal = "Liquidationsgebühr fix", percentage_fee_rate_decimal = "Liquidationsgebühr %", fx_direction = "FX-Route",
  fx_base_currency = "Basiswährung (Devisen)", fx_quote_currency = "Quotierungswährung (Devisen)", fx_rate_decimal = "Devisenkurs",
  fx_observed_at_utc = "Devisenkurszeitpunkt (UTC)")

# Die Vorgabe eines Assets: so, wie die Karte je Asset unberuehrt im Browser stand.
desktop_run_evidence_defaults_v1 <- function(asset) {
  currency <- if (is.null(asset$price_currency) || is.na(asset$price_currency)) "" else as.character(asset$price_currency)
  list(listing_code = "", market_currency = currency, close_decimal = "", observed_at_utc = "", tax_classification = "not_configured",
       partial_exemption_rate_decimal = "", fixed_fee_decimal = "", percentage_fee_rate_decimal = "", fx_base_currency = "",
       fx_quote_currency = "", fx_direction = "none", fx_rate_decimal = "", fx_observed_at_utc = "")
}

# Die Werte eines Assets fuer den Lauf: gespeichert oder Vorgabe; `live` (die Felder des gerade gewaehlten Assets) gilt zuletzt.
desktop_run_evidence_values_v1 <- function(store, asset, live = NULL) {
  values <- desktop_run_evidence_defaults_v1(asset)
  saved <- store[[as.character(asset$ref)]]
  if (is.list(saved)) values[names(saved)] <- saved
  if (is.list(live)) for (field in names(DESKTOP_RUN_EVIDENCE_FIELDS)) if (!is.null(live[[field]])) values[[field]] <- as.character(live[[field]])
  c(list(asset_ref = as.character(asset$ref)), values)
}

# Die Felder, die von der Vorgabe abweichen - fuer die Liste "Assets mit manuellem Nachweis".
desktop_run_evidence_changed_v1 <- function(asset, values) {
  defaults <- desktop_run_evidence_defaults_v1(asset)
  names(DESKTOP_RUN_EVIDENCE_FIELDS)[vapply(names(DESKTOP_RUN_EVIDENCE_FIELDS), function(field)
    !is.null(values[[field]]) && !identical(as.character(values[[field]]), defaults[[field]]), logical(1L))]
}

# Speichert die Werte eines Assets; stehen alle auf der Vorgabe, verschwindet der Eintrag.
desktop_run_evidence_store_v1 <- function(store, asset, values) {
  ref <- as.character(asset$ref)
  merged <- desktop_run_evidence_values_v1(store, asset, values)
  if (!length(desktop_run_evidence_changed_v1(asset, merged))) { store[[ref]] <- NULL; return(store) }
  store[[ref]] <- merged[names(DESKTOP_RUN_EVIDENCE_FIELDS)]
  store
}
