# Steuerliche Einstellungen im Datenbereich.
#
# Die Regel haengt am Asset-Typ: Aktien sind Aktien, Fonds sind Fonds. Deshalb
# steht die Vorgabe am Typ und deckt alle Assets dieses Typs ab; ein einzelnes
# Asset darf sie ueberschreiben, wenn es abweicht. Ohne diese Aufloesung waeren
# je Asset ein Einzeleintrag noetig gewesen (#367).
#
# Reine Darstellung: kein Abruf, keine Rechnung, keine Pfade und keine internen
# Kennungen im Browser. Geschrieben wird ausschliesslich ueber Vorschau,
# Bestaetigung und Anwenden.

.data_tax_text_v1 <- function(value, fallback = "—") {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value)))
    fallback else as.character(value)
}

# Kein Regelmodul unterstuetzt bislang 'unrealized_snapshot'. Als "kein Modul
# gewaehlt" sah das aus wie eine offene Aufgabe des Eigentuemers; es ist aber
# eine offene Aufgabe der App (#367, Schritt 2).
data_tax_status_label_v1 <- function(status, mode = NULL) {
  # "noch nicht verfuegbar" galt, solange kein Modul die unrealisierte
  # Projektion konnte. Seit v2 sie beherrscht, ist ein fehlendes Modul auch hier
  # schlicht ein fehlendes Modul (#367 Schritt 2, 28.09.2026).
  switch(.data_tax_text_v1(status, ""),
    ready = "bereit",
    no_plugin = "kein Regelmodul gewählt",
    plugin_version_stale = "Modulfassung überholt",
    # Gleiche Version, andere Regeln (#527): Die Rechnung haelt sonst am naechsten Steuerschritt an.
    plugin_rules_changed = "Regeln des Moduls geändert – neu übernehmen",
    unsupported_mode = "Modus vom Modul nicht unterstützt",
    # Das Modul fuehrt je Steuerjahr den Rechtsstand; fuer ein Jahr ohne Eintrag
    # rechnet es nicht. Das ist ein Hinweis, keine Sperre: Alles andere laeuft weiter.
    year_not_covered = "Regelmodul führt dieses Steuerjahr nicht – keine Steuerzahlen",
    classification_required = "Klassifikation fehlt",
    parameter_required = "Parameter fehlt",
    stale = "veraltet – neu zu rechnen",
    .data_tax_text_v1(status))
}

data_tax_mode_label_v1 <- function(mode) {
  switch(.data_tax_text_v1(mode, ""),
    realized_event = "Je Ereignis",
    realized_annual = "Je Jahr",
    unrealized_snapshot = "Unrealisiert (Stichtag)",
    .data_tax_text_v1(mode))
}

# `institution_card`: die Karte der Angaben je Institut (Data-App); sie steht unter "Steuerangaben je Jahr".
# `advance_card`: die Karte der Vorabpauschalen je Fonds und Konto (#431); sie steht darunter.
# `document_card`: die Karte der Ertraegnisaufstellung (#459, #465); sie steht unter den Vorabpauschalen.
data_tax_settings_ui_v1 <- function(institution_card = NULL, advance_card = NULL, document_card = NULL) {
  shiny::tagList(
    portelyra_card("Steuerliche Einstellungen", help = "app-data#steuer",
      copy = paste(
        "Die Regel gilt je Asset-Typ; ein einzelnes Asset kann abweichen.",
        "Keine Rechtsberatung und keine Zusicherung von Aktualität oder Vollständigkeit —",
        "die Berechnung ist eine Projektion nach einem gewählten Regelmodul."),
      shiny::div(class = "pl-editor-actions",
        # Eingerichtet wird oben in der Einzelasset-Maske; hier wird nur gelesen
        # und gepflegt. Ein zweiter Einrichtungsknopf legte nichts Zweites an,
        # verspraeche es aber (#367, 28.09.2026).
        shiny::actionButton("data_tax_refresh", "Einstellungen lesen", class = "btn-default"),
        shiny::selectInput("data_tax_portfolio", "Portfolio", choices = c("Bitte lesen" = "")),
        shiny::numericInput("data_tax_year", "Steuerjahr", value = as.integer(format(Sys.Date(), "%Y")), min = 1900L, max = 9999L, step = 1L)),
      shiny::uiOutput("data_tax_state"),
      shiny::tags$h4("Bereitschaft je Projektionsart"),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_readiness"))),

    # Festlegung (13.10.2026): Was der Rechnung je Jahr fehlt, soll sich an einer Stelle klar nachtragen lassen.
    # Meist fehlt je Jahr genau eine Angabe, der persoenliche Steuersatz, die sonst einzeln ueber die
    # allgemeine Parameterkarte einzutragen waere. Hier stehen alle Jahre nebeneinander; ein Knopf speichert, was geaendert ist.
    portelyra_card("Steuerangaben je Jahr", help = "app-data#steuer", class = "pl-write-boundary",
      copy = "Je Steuerjahr braucht die Rechnung zwei Angaben von Ihnen: den persönlichen Steuersatz und ob Kirchensteuer anfällt.",
      note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-tax-years", paste(
        "Sätze und Freigrenzen des Jahres bringt das Regelmodul mit.")),
      shiny::uiOutput("data_tax_years_form"),
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("data_tax_years_save", "Angaben speichern", class = "btn-primary")),
      shiny::uiOutput("data_tax_years_notice"),
      shiny::p(class = "pl-field-hint", paste(
        "Gespeichert wird nur, was geändert ist; ein leeres Feld ändert nichts.",
        "Ohne persönlichen Steuersatz rechnet das Modul Kapitalerträge trotzdem – Veräußerungen und Erträge, die ihm unterliegen (Krypto), bleiben ohne Steuerzahl.",
        "Die App „Steuer“ zeigt neue Zahlen erst nach einem neuen Portfolioabschluss („Alles aktualisieren“ oben rechts)."))),

    institution_card,
    advance_card,
    document_card,

    portelyra_card("Vorgabe je Asset-Typ", help = "app-data#steuer", class = "pl-write-boundary",
      copy = "Die Regel für alle Assets eines Typs – der Normalfall. Eine Zeile je Typ genügt.",
      note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-tax-type-default", paste(
        "Teilfreistellung gibt es nur bei Fonds; sonst 0. Ein einzelnes Asset, das abweicht, steht ganz unten im Reiter.")),
      shiny::div(class = "pl-field-row",
        shiny::selectInput("data_tax_type", "Asset-Typ", choices = c("Bitte lesen" = "")),
        shiny::selectInput("data_tax_type_code", "Klassifikation", choices = c("Bitte lesen" = "")),
        shiny::textInput("data_tax_type_partial", "Teilfreistellung in Prozent", value = "0"),
        shiny::numericInput("data_tax_type_from", "Gültig ab Jahr", value = as.integer(format(Sys.Date(), "%Y")), min = 1900L, max = 9999L, step = 1L)),
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("data_tax_type_apply", "Vorgabe setzen", class = "btn-primary"),
        shiny::actionButton("data_tax_type_retire", "Vorgabe zurückziehen", class = "btn-default")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_type_table")),
      # Nur zur Ansicht: Bearbeitet werden Abweichungen in der Maske darueber.
      data_expert_only_v1(shiny::tags$details(class = "pl-disclosure",
        shiny::tags$summary("Gespeicherte Abweichungen je Asset · gesetzt ganz unten im Reiter"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_asset_table")))),
      # Welche Fonds erben ihren Satz? Genau dort weist die Jahresrechnung sonst zu
      # niedrig aus - Anleihe-ETFs tragen 0 %, ETCs sind keine Fonds (#466).
      data_when_needed_v1("inherited_rates", shiny::tags$details(class = "pl-disclosure pl-lazy",
        shiny::tags$summary("Fonds mit geerbter Teilfreistellung · bitte je Asset prüfen"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_inherited_table"))))),

    # Die Modulwahl ist immer erreichbar (#527). Bis rc.337 erschien die Karte nur, solange ein Modul fehlte (#492) - aenderten sich nur seine Regeln,
    # blieb sie verborgen. Jetzt steht das gewaehlte Modul je Projektionsart in der Tabelle "Bereitschaft je Projektionsart";
    # die Auswahl ist eingeklappt und klappt von selbst auf, sobald ein Modul fehlt, ueberholt ist oder neu zu uebernehmen ist.
    portelyra_card("Regelmodul", help = "steuer-umfang",
      copy = "Das Regelmodul bringt Sätze, Freigrenzen und Fundstellen je Steuerjahr mit. Gewählt wird es einmal je Projektionsart; empfohlen ist die neueste Fassung. Welches gilt, steht oben unter „Bereitschaft je Projektionsart“.",
      shiny::conditionalPanel("output.data_need_tax_module == 'on'", shiny::p(class = "pl-field-hint",
        shiny::tags$strong("Für mindestens eine Projektionsart ist das Regelmodul zu wählen oder neu zu übernehmen"),
        " – je Projektionsart dasselbe Modul mit „Gültig ab“ heute. Bis dahin hält der Steuerschritt von „Alles aktualisieren“ an.")),
      # Neue Fassung verfuegbar (#486 Schritt 2): mit den Unterschieden; uebernommen wird sie ab "Gueltig ab" fuer alle Steuerjahre.
      shiny::uiOutput("data_tax_module_updates"),
      # Neue Fassung aus Datei (#486 Schritt 2c): seit Schritt 3 unter Einstellungen -> "Plugins" -> "Paket installieren" (eine Stelle fuer
      # alle Plugins, Festlegung 16.11.2026); danach steht sie hier unter "Neue Fassung verfügbar".
      shiny::p(class = "pl-field-hint", paste("Eine neue Fassung aus einer Datei installieren Sie unter Einstellungen → „Plugins und Zugänge“ → „Plugins“ → „Paket installieren“",
        "(nur mit Portelyra-Signatur). Danach steht sie hier unter „Neue Fassung verfügbar“ und gilt, sobald Sie sie übernehmen.")),
      shiny::tags$details(id = "data-tax-module-choice", class = "pl-disclosure",
      shiny::tags$summary("Regelmodul wählen"),
      shiny::div(class = "pl-field-row",
        # Die Bereitschaftstabelle fuehrte die dritte Projektionsart laengst, die
        # Auswahl nicht: Das Modul liess sich fuer sie gar nicht uebernehmen
        # (Befund 28.09.2026, #367 Schritt 2).
        shiny::selectInput("data_tax_mode", "Projektionsart", choices = c(
          "Je Ereignis" = "realized_event", "Je Jahr" = "realized_annual",
          "Unrealisiert (Stichtag)" = "unrealized_snapshot")),
        shiny::selectInput("data_tax_plugin", "Regelmodul", choices = c("Bitte lesen" = "")),
        # Die Fassungskette verlangt ein streng spaeteres Datum als die vorige
        # Auswahl. Der 1. Januar ist fachlich richtig, scheitert aber bei jeder
        # Wiederauswahl im selben Jahr - der Server schiebt das Feld dann auf den
        # frueheste zulaessigen Tag und sagt es (#368, 28.09.2026).
        shiny::dateInput("data_tax_plugin_from", "Gültig ab",
          value = as.Date(paste0(format(Sys.Date(), "%Y"), "-01-01")),
          min = as.Date("1900-01-01"), max = as.Date("9999-12-31"),
          format = "dd.mm.yyyy", language = "de", weekstart = 1L),
        shiny::actionButton("data_tax_plugin_apply", "Modul übernehmen", class = "btn-primary")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_plugins"))),
      # Aufklappen schickt der Server, sobald der Anlass entsteht; zuklappen bleibt Sache des Nutzers.
      shiny::tags$script(shiny::HTML(paste0(
        "$(document).on('shiny:connected',function(){Shiny.addCustomMessageHandler('pl_open_tax_module',function(m){",
        "var d=document.getElementById('data-tax-module-choice');if(d){d.open=true;}});});")))),

    data_expert_only_v1(portelyra_card("Weitere Steuerparameter je Jahr", help = "app-data#steuer",
      copy = paste(
        "Für alles Übrige eines Jahres: Verlustvorträge privater Veräußerungsgeschäfte und sonstiger Einkünfte – oder ein Wert des Regelmoduls, der für Sie abweicht.",
        "Freistellungsauftrag, anrechenbare Quellensteuer und die Verlusttöpfe der Kapitalerträge stehen je Institut in der Karte dafür.",
        "Die Tabelle zeigt je Jahr alle Werte, mit denen gerechnet wird – aus dem Regelmodul mit Fundstelle oder als eigene Angabe.",
        "Persönlicher Steuersatz, Kirchensteuer und Veranlagung stehen in „Steuerangaben je Jahr“."),
      shiny::div(class = "pl-field-row",
        # Ab 2016 (#496): Das Modul fuehrt 2016-2019 in Grundzuegen; Angaben fuer diese Jahre (etwa Kirchensteuer) muessen eintragbar sein.
        shiny::selectInput("data_tax_parameter_year", "Steuerjahr", choices = rev(as.character(2016:as.integer(format(Sys.Date(), "%Y")))),
                           selected = format(Sys.Date(), "%Y"), selectize = FALSE, width = "140px"),
        shiny::selectInput("data_tax_parameter", "Parameter", choices = c("Bitte lesen" = "")),
        shiny::textInput("data_tax_parameter_value", "Wert", value = ""),
        shiny::textInput("data_tax_parameter_currency", "Währung (nur bei Beträgen)", value = ""),
        shiny::actionButton("data_tax_parameter_apply", "Parameter setzen", class = "btn-primary"),
        # Eine eigene Angabe zurueckziehen (#529): Danach gilt wieder die Vorgabe des Regelmoduls; die alte Angabe bleibt als Fassung erhalten.
        shiny::actionButton("data_tax_parameter_retire", "Eigene Angabe zurücksetzen – Vorgabe des Moduls gilt", class = "btn-default")),
      shiny::uiOutput("data_tax_year_coverage"),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_tax_parameter_table")))),

    shiny::uiOutput("data_tax_plugin_from_note"),
    shiny::uiOutput("data_tax_action_feedback")
  )
}

# Wann zuletzt gerechnet, seit wann neu zu rechnen und warum (#497) - Zeitpunkte in Ortszeit.
.data_tax_when_v1 <- function(value) {
  text <- .data_tax_text_v1(value, "")
  if (!nzchar(text)) return("")
  stamp <- as.POSIXct(text, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (is.na(stamp)) "" else format(stamp, "%d.%m.%Y %H:%M", tz = "Europe/Berlin")
}
data_tax_reason_label_v1 <- function(code) switch(.data_tax_text_v1(code, ""),
  plugin_change = "Modulwahl", tax_classification_change = "Klassifikation", tax_parameter_change = "Parameter", .data_tax_text_v1(code, ""))
data_tax_readiness_text_v1 <- function(row) {
  label <- data_tax_status_label_v1(row$status, row$projection_mode)
  if (identical(row$status, "stale") && nzchar(.data_tax_when_v1(row$pending_since_utc)))
    return(sprintf("%s (geändert am %s: %s)", label, .data_tax_when_v1(row$pending_since_utc),
                   paste(vapply(unlist(row$pending_reasons), data_tax_reason_label_v1, character(1L)), collapse = ", ")))
  if (identical(row$status, "ready") && nzchar(.data_tax_when_v1(row$last_completed_at_utc)))
    return(sprintf("%s · zuletzt gerechnet am %s", label, .data_tax_when_v1(row$last_completed_at_utc)))
  label
}

data_tax_readiness_frame_v1 <- function(model) {
  if (!is.list(model) || !length(model$readiness)) return(data.frame())
  rows <- model$readiness
  selections <- if (is.list(model$selections)) model$selections else list()
  # Welches Modul je Projektionsart gilt (#527): bis rc.337 nur in der Auswahl selbst zu sehen.
  chosen <- function(mode) {
    hit <- Filter(function(s) identical(s$projection_mode, mode) && identical(.data_tax_text_v1(s$status, "active"), "active"), selections)
    if (!length(hit)) return("–")
    from <- suppressWarnings(as.Date(.data_tax_text_v1(hit[[1L]]$effective_from, "")))
    paste0(data_tax_plugin_label_v1(hit[[1L]]$plugin_id, hit[[1L]]$plugin_version), if (!is.na(from)) paste0(" · gewählt ab ", format(from, "%d.%m.%Y")) else "")
  }
  data.frame(
    Projektionsart = vapply(rows, function(r) data_tax_mode_label_v1(r$projection_mode), character(1L)),
    Regelmodul = vapply(rows, function(r) chosen(r$projection_mode), character(1L)),
    Stand = vapply(rows, data_tax_readiness_text_v1, character(1L)),
    `Fehlende Assets` = vapply(rows, function(r) as.character(length(r$missing_asset_refs)), character(1L)),
    `Fehlende Parameter` = vapply(rows, function(r) paste(vapply(unlist(r$missing_parameter_codes), function(code) data_tax_label_v1(data_tax_parameter_labels_v1(), code), character(1L)), collapse = ", "), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

data_tax_type_frame_v1 <- function(model) {
  if (!is.list(model) || !length(model$asset_type_classifications)) return(data.frame())
  rows <- model$asset_type_classifications
  data.frame(
    `Asset-Typ` = vapply(rows, function(r) data_tax_label_v1(data_tax_asset_type_labels_v1(), r$asset_type), character(1L)),
    Klassifikation = vapply(rows, function(r) data_tax_label_v1(data_tax_classification_labels_v1(), r$classification_code), character(1L)),
    Steuertopf = vapply(rows, function(r) data_tax_label_v1(data_tax_bucket_labels_v1(), r$tax_bucket), character(1L)),
    `Teilfreistellung %` = vapply(rows, function(r) .data_tax_text_v1(r$partial_exemption_rate_decimal, "0"), character(1L)),
    `Gültig ab` = vapply(rows, function(r) .data_tax_text_v1(r$effective_from_year), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

data_tax_asset_frame_v1 <- function(model, labels = list()) {
  if (!is.list(model) || !length(model$classifications)) return(data.frame())
  rows <- model$classifications
  data.frame(
    Asset = vapply(rows, function(r) .data_tax_text_v1(labels[[.data_tax_text_v1(r$asset_ref, "")]], .data_tax_text_v1(r$asset_ref)), character(1L)),
    Klassifikation = vapply(rows, function(r) data_tax_label_v1(data_tax_classification_labels_v1(), r$classification_code), character(1L)),
    Steuertopf = vapply(rows, function(r) data_tax_label_v1(data_tax_bucket_labels_v1(), r$tax_bucket), character(1L)),
    `Teilfreistellung %` = vapply(rows, function(r) .data_tax_text_v1(r$partial_exemption_rate_decimal, "0"), character(1L)),
    `Gültig ab` = vapply(rows, function(r) .data_tax_text_v1(r$effective_from_year), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

# Fonds, die nur die Vorgabe ihres Typs tragen (#466). Die Vorgabe gilt sonst
# unbemerkt auch fuer Anleihe-ETFs (0 %) und ETCs, die keine Fonds sind.
data_tax_inherited_frame_v1 <- function(model, labels = list()) {
  if (!is.list(model) || !length(model$inherited_partial_exemption_assets)) return(data.frame())
  rows <- model$inherited_partial_exemption_assets
  data.frame(
    Asset = vapply(rows, function(r) .data_tax_text_v1(labels[[.data_tax_text_v1(r$asset_ref, "")]], .data_tax_text_v1(r$asset_ref)), character(1L)),
    `Asset-Typ` = vapply(rows, function(r) data_tax_label_v1(data_tax_asset_type_labels_v1(), r$asset_type), character(1L)),
    `Geerbte Teilfreistellung %` = vapply(rows, function(r) .data_tax_text_v1(r$partial_exemption_rate_decimal, "0"), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

# Alle Werte eines Jahres, mit denen gerechnet wird (#498): die des Regelmoduls mit Fundstelle und die eigenen Angaben. Eine
# eigene Angabe ueberschreibt sichtbar den Modulwert. Der Sparer-Pauschbetrag folgt der Veranlagungsart; die Freigrenzen gelten
# je Person.
# Wie vollstaendig das Modul das gewaehlte Jahr fuehrt (#496, Festlegung 28.10.2026): 2016-2019 nur in Grundzuegen - das soll
# unuebersehbar dastehen; ab 2020 vollstaendig bis auf Fondsanteile von vor 2018.
data_tax_year_coverage_ui_v1 <- function(model) {
  coverage <- if (is.list(model) && is.list(model$module_coverage)) model$module_coverage else NULL
  if (is.null(coverage)) return(NULL)
  year <- .data_tax_text_v1(model$tax_year, "")
  if (identical(coverage$coverage, "partial"))
    return(portelyra_status_panel(paste0("Steuerjahr ", year, ": nur in Grundzügen – nicht vollständig"), paste(
      "Das Regelmodul führt dieses Jahr nur mit den Jahreswerten (Abgeltungsteuer, Solidaritätszuschlag, Sparer-Pauschbetrag, Freigrenzen),",
      "der Jahresfrist und den Rewards. Fonds rechnet es vor 2018 nicht (altes Investmentsteuergesetz). Die Berechnung für dieses Jahr ist",
      "ausdrücklich nicht vollständig; genauere Regeln für frühere Jahre kommen später als Plugin."), tone = "warning"))
  shiny::p(class = "pl-field-hint", paste(
    "Das Regelmodul führt dieses Jahr weitgehend vollständig für die Kapitalanlage – ausgenommen Fondsanteile, die vor 2018 angeschafft wurden",
    "(fiktive Veräußerung zum 31.12.2017; solche Verkäufe bekommen keine Zahl), und was das Handbuch unter „Bewusst nicht enthalten“ nennt."))
}
data_tax_parameter_values_frame_v1 <- function(model) {
  if (!is.list(model)) return(data.frame())
  module <- if (is.list(model$module_values)) model$module_values else list()
  own <- if (is.list(model$parameters)) model$parameters else list()
  module_of <- function(code) { hit <- Filter(function(row) identical(row$value_code, code), module); if (length(hit)) hit[[1L]] else NULL }
  own_of <- function(code) { hit <- Filter(function(row) identical(row$parameter_code, code), own); if (length(hit)) hit[[1L]] else NULL }
  number <- function(text, kind) {
    value <- suppressWarnings(as.numeric(.data_tax_text_v1(text, "")))
    if (is.na(value)) return("–")
    if (identical(kind, "rate")) paste(trimws(formatC(value, format = "fg", digits = 10, decimal.mark = ",")), "%") else paste(formatC(value, format = "f", digits = if (value == round(value)) 0L else 2L, big.mark = ".", decimal.mark = ","), "€")
  }
  own_value <- function(row) if (identical(row$value_kind, "applicability")) data_tax_label_v1(data_tax_applicability_labels_v1(), row$applicability_value)
    else number(if (is.null(row$rate_decimal)) row$amount_decimal else row$rate_decimal, row$value_kind)
  assessment <- .data_tax_text_v1(model$assessment, "")
  allowance_code <- if (identical(assessment, "joint")) "capital_income_allowance_joint" else "capital_income_allowance_single"
  rows <- list()
  add <- function(label, module_code, own_code, note = NULL) {
    m <- if (is.null(module_code)) NULL else module_of(module_code); o <- if (is.null(own_code)) NULL else own_of(own_code)
    if (is.null(m) && is.null(o)) return(invisible(NULL))
    value <- if (!is.null(o)) own_value(o) else number(m$value_decimal, m$value_kind)
    origin <- if (!is.null(o) && !is.null(m)) paste0("eigene Angabe (Modul: ", number(m$value_decimal, m$value_kind), ")")
      else if (!is.null(o)) "eigene Angabe" else "Regelmodul"
    rows[[length(rows) + 1L]] <<- data.frame(Parameter = label, Wert = value, Herkunft = paste(c(origin, note), collapse = " · "),
      Fundstelle = if (is.null(m) || is.null(m$citation)) "" else m$citation, check.names = FALSE, stringsAsFactors = FALSE)
  }
  add("Abgeltungsteuersatz", "capital_income_tax_rate", "capital_income_tax_rate")
  add("Solidaritätszuschlag", "solidarity_surcharge_rate", "solidarity_surcharge_rate")
  add("Sparer-Pauschbetrag", allowance_code, "capital_income_allowance",
      if (identical(assessment, "joint")) "Zusammenveranlagung" else if (identical(assessment, "single")) "Einzelveranlagung" else "Veranlagung nicht angegeben – einzeln angenommen")
  add("Freigrenze private Veräußerungsgeschäfte (§ 23)", "private_disposal_exemption_threshold", "private_disposal_exemption_threshold", "je Person")
  add("Freigrenze sonstige Einkünfte (§ 22 Nr. 3)", "other_income_exemption_threshold", "other_income_exemption_threshold", "je Person")
  shown <- c("capital_income_tax_rate", "solidarity_surcharge_rate", "capital_income_allowance", "private_disposal_exemption_threshold", "other_income_exemption_threshold")
  for (row in own) if (!row$parameter_code %in% shown) add(data_tax_label_v1(data_tax_parameter_labels_v1(), row$parameter_code), NULL, row$parameter_code)
  if (!length(rows)) return(data.frame())
  do.call(rbind, rows)
}

data_tax_parameter_frame_v1 <- function(model) {
  if (!is.list(model) || !length(model$parameters)) return(data.frame())
  rows <- model$parameters
  data.frame(
    Parameter = vapply(rows, function(r) data_tax_label_v1(data_tax_parameter_labels_v1(), r$parameter_code), character(1L)),
    Art = vapply(rows, function(r) data_tax_label_v1(data_tax_value_kind_labels_v1(), r$value_kind), character(1L)),
    Wert = vapply(rows, function(r) {
      if (identical(r$value_kind, "applicability")) data_tax_label_v1(data_tax_applicability_labels_v1(), r$applicability_value)
      else .data_tax_text_v1(if (is.null(r$rate_decimal)) r$amount_decimal else r$rate_decimal)
    }, character(1L)),
    Währung = vapply(rows, function(r) .data_tax_text_v1(r$currency, ""), character(1L)),
    Steuerjahr = vapply(rows, function(r) .data_tax_text_v1(r$tax_year), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

data_tax_state_ui_v1 <- function(model, notice = NULL) {
  panels <- list()
  if (is.list(notice)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      .data_tax_text_v1(notice$title, "Hinweis"), .data_tax_text_v1(notice$copy, ""),
      tone = .data_tax_text_v1(notice$tone, "neutral"))
  }
  if (!is.list(model)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      "Steuerbereich noch nicht gelesen",
      paste("Einrichten legt den Speicher an; Lesen zeigt Regelmodule, Klassifikationen und Parameter.",
            "Es wird nichts gerechnet und nichts veröffentlicht."),
      tone = "neutral")
    return(do.call(shiny::tagList, panels))
  }
  # Ein Zaehler sagt nicht, was sich bewegt hat. Nach dem Setzen eines Moduls
  # stand dort weiter "0 von 3 bereit" - richtig, aber unbrauchbar. Die Staende
  # stehen jetzt beim Namen (Festlegung 28.09.2026, #367).
  ready <- vapply(model$readiness, function(r) identical(r$status, "ready"), logical(1L))
  covered <- .data_tax_text_v1(model$resolved_classification_count, "0")
  detail <- paste(vapply(model$readiness, function(r) paste0(
    data_tax_mode_label_v1(r$projection_mode), ": ", data_tax_status_label_v1(r$status, r$projection_mode)), character(1L)),
    collapse = " · ")
  panels[[length(panels) + 1L]] <- portelyra_status_panel(
    paste0("Steuerjahr ", .data_tax_text_v1(model$tax_year), " · ", detail),
    paste0(length(model$asset_type_classifications), " Vorgaben je Typ · ",
           .data_tax_text_v1(model$asset_classification_count, "0"), " Abweichungen je Asset · ",
           covered, " Assets damit abgedeckt."),
    tone = if (all(ready)) "neutral" else "warning")
  # Ein geerbter Satz ueber 0 ist die Stelle, an der die Jahresrechnung zu niedrig
  # ausweist: Anleihe-ETFs sind sonstige Investmentfonds mit 0 %, ETCs sind keine
  # Fonds (#466).
  inherited <- model$inherited_partial_exemption_assets
  if (length(inherited)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      paste0(length(inherited), if (length(inherited) == 1L) " Fonds trägt nur die Vorgabe seines Typs" else " Fonds tragen nur die Vorgabe ihres Typs"),
      paste("Die Vorgabe setzt die Teilfreistellung für jeden Fonds dieses Typs.",
            "Anleihe- und Geldmarkt-ETFs sind sonstige Investmentfonds mit 0 %; ETCs sind keine Investmentfonds.",
            "Prüfen Sie je Asset und setzen Sie, wo nötig, eine eigene Einordnung."),
      tone = "warning")
  }
  panels[[length(panels) + 1L]] <- shiny::p(class = "pl-field-hint", paste(
    "Modellprojektion, keine Rechtsberatung. Regeln ändern sich; das gewählte Modul wird nicht automatisch aktualisiert.",
    "Die Kirchensteuer beruht ausschließlich auf Ihrer ausdrücklichen Angabe."))
  do.call(shiny::tagList, panels)
}

# --- Steuerangaben je Jahr ---------------------------------------------------------------------------------------
# Die beiden Angaben, die nur der Eigentuemer machen kann, fuer alle Jahre auf einer Karte.
data_tax_year_parameter_label_v1 <- function(code) switch(.data_tax_text_v1(code, ""),
  personal_income_tax_rate = "persönlicher Steuersatz",
  church_tax_applicable = "Angabe zur Kirchensteuer",
  church_tax_rate = "Kirchensteuersatz",
  .data_tax_text_v1(code))
# Eine Zahl als Dezimaltext fuer den Steuerspeicher: Punkt, keine Exponentialschreibweise, keine angehaengten Nullen.
data_tax_decimal_text_v1 <- function(value) {
  if (is.null(value) || length(value) != 1L || !is.numeric(value) || is.na(value) || !is.finite(value)) return(NULL)
  text <- formatC(value, format = "f", digits = 6)
  sub("\\.$", "", sub("0+$", "", text))
}
# Eine Zeile je Jahr aus dem Ueberblick des Steuerspeichers: was eingetragen ist und was der Jahresrechnung fehlt.
data_tax_year_row_v1 <- function(year, overview) {
  parameter <- function(code) {
    found <- Filter(function(row) identical(row$parameter_code, code), if (is.list(overview)) overview$parameters else list())
    if (length(found)) found[[1L]] else NULL
  }
  rate_of <- function(code) { row <- parameter(code); value <- if (is.null(row)) NA_real_ else suppressWarnings(as.numeric(row$rate_decimal)); if (length(value) == 1L) value else NA_real_ }
  church <- parameter("church_tax_applicable")
  annual <- Filter(function(row) identical(row$projection_mode, "realized_annual"), if (is.list(overview)) overview$readiness else list())
  status <- if (length(annual)) .data_tax_text_v1(annual[[1L]]$status, "") else ""
  missing <- if (length(annual)) vapply(annual[[1L]]$missing_parameter_codes, as.character, character(1L)) else character()
  rate <- rate_of("personal_income_tax_rate"); church_rate <- rate_of("church_tax_rate")
  church_value <- if (is.null(church)) "" else .data_tax_text_v1(church$applicability_value, "")
  # Was fehlt, sagen die Angaben selbst - nicht der Stand der Projektion: Ohne gewaehltes Regelmodul meldet der keinen
  # fehlenden Parameter, und die Karte nannte ein leeres Jahr "vollstaendig" (im Browser gesehen, 13.10.2026).
  absent <- c(if (is.na(rate)) "persönlicher Steuersatz", if (!nzchar(church_value)) "Angabe zur Kirchensteuer",
    if (identical(church_value, "applicable") && is.na(church_rate)) "Kirchensteuersatz")
  readable <- is.list(overview)
  other <- if (readable && nzchar(status) && !status %in% c("ready", "stale", "parameter_required")) data_tax_status_label_v1(status) else NULL
  list(year = as.integer(year), status = status, missing = missing, readable = readable, complete = readable && !length(absent),
    rate = rate, church = church_value, church_rate = church_rate,
    assessment = if (readable) .data_tax_text_v1(overview$assessment, "") else "",
    # Zaehlt das Portfolio im Jahr zur Veranlagung (#501)? Ohne Angabe ja.
    counts = !(readable && identical(overview$portfolio_counts, FALSE)),
    status_text = if (!readable) "nicht lesbar"
      else paste(c(if (length(absent)) paste("fehlt:", paste(absent, collapse = ", ")) else "vollständig", other), collapse = " · "))
}
data_tax_years_form_v1 <- function(rows) {
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Zuerst oben „Einstellungen lesen“ drücken und ein Portfolio wählen."))
  open <- sum(vapply(rows, function(row) isTRUE(row$readable) && !isTRUE(row$complete), logical(1L)))
  shiny::tagList(
    if (open > 0L) portelyra_status_panel(sprintf("%d Jahr(e) mit fehlender Angabe", open),
      "Die Zeilen nennen, was fehlt. Eintragen und unten speichern.", tone = "warning")
    else portelyra_status_panel("Alle Jahre vollständig", "Je Jahr sind persönlicher Steuersatz und Kirchensteuer eingetragen.", tone = "positive"),
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Steuerjahr", "Stand", "Persönlicher Steuersatz in %", "Kirchensteuer", "Kirchensteuersatz in %", "Veranlagung",
                                                "zählt zur Veranlagung"), shiny::tags$th))),
      shiny::tags$tbody(lapply(rows, function(row) shiny::tags$tr(
        shiny::tags$td(shiny::tags$strong(row$year)), shiny::tags$td(row$status_text),
        shiny::tags$td(shiny::numericInput(paste0("data_tax_years_rate_", row$year), NULL, value = row$rate, min = 0, max = 100, step = 0.01, width = "140px")),
        shiny::tags$td(shiny::selectInput(paste0("data_tax_years_church_", row$year), NULL, selected = row$church, width = "170px", selectize = FALSE,
          choices = c("bitte wählen" = "", "fällt nicht an" = "not_applicable", "fällt an" = "applicable"))),
        shiny::tags$td(shiny::numericInput(paste0("data_tax_years_church_rate_", row$year), NULL, value = row$church_rate, min = 0, max = 100, step = 0.01, width = "140px")),
        # Veranlagungsart (#498): bestimmt den Sparer-Pauschbetrag in der Anzeige und der Pruefung der Freistellungsauftraege.
        shiny::tags$td(shiny::selectInput(paste0("data_tax_years_assessment_", row$year), NULL, selected = .data_tax_text_v1(row$assessment, ""), width = "170px", selectize = FALSE,
          choices = c("nicht angegeben" = "", "einzeln" = "single", "zusammen" = "joint"))),
        # Muster- oder Fremdportfolio (#501): zaehlt es nicht, rechnen Jahresrechnung und Netto-Sicht keine Steuer.
        shiny::tags$td(shiny::selectInput(paste0("data_tax_years_counts_", row$year), NULL, selected = if (isFALSE(row$counts)) "no" else "yes", width = "130px",
          selectize = FALSE, choices = c("ja" = "yes", "nein" = "no")))))))),
    shiny::p(class = "pl-field-hint", paste(
      "„zählt zur Veranlagung“: Nein für ein Muster- oder Fremdportfolio – dann rechnen Jahresrechnung und Netto-Sicht der Analyse für das Jahr keine Steuer und sagen das;",
      "Verlustvorträge laufen unverändert weiter. Bei Zusammenveranlagung zählt der gemeinsame Sparer-Pauschbetrag über die eingetragenen Freistellungsaufträge.")))
}
# Welche Angaben "zaehlt zur Veranlagung" zu speichern sind: je Jahr, dessen Auswahl vom gespeicherten Stand abweicht.
data_tax_year_scope_changes_v1 <- function(rows, value_of) {
  changes <- list()
  for (row in rows) {
    chosen <- .data_tax_text_v1(value_of(row$year), "")
    if (chosen %in% c("yes", "no") && !identical(chosen == "yes", !isFALSE(row$counts))) changes[[length(changes) + 1L]] <- list(year = row$year, counts = chosen == "yes")
  }
  changes
}
# Welche Veranlagungsarten zu speichern sind: je Jahr, dessen Auswahl vom gespeicherten Stand abweicht. Leeren nimmt nichts zurueck.
data_tax_year_assessment_changes_v1 <- function(rows, value_of) {
  changes <- list()
  for (row in rows) {
    chosen <- .data_tax_text_v1(value_of(row$year), "")
    if (chosen %in% c("single", "joint") && !identical(chosen, .data_tax_text_v1(row$assessment, ""))) changes[[length(changes) + 1L]] <- list(year = row$year, assessment = chosen)
  }
  changes
}
# Was zu schreiben ist: je geaenderter Angabe ein Kommando. `values` liefert je Jahr die Eingaben der Karte.
# Eine unzulaessige Eingabe nennt Jahr und Feld; dann wird nichts geschrieben.
data_tax_year_commands_v1 <- function(rows, values, portfolio_ref) {
  commands <- list()
  same <- function(a, b) (is.na(a) && is.na(b)) || (!is.na(a) && !is.na(b) && isTRUE(all.equal(a, b, tolerance = 1e-9)))
  number <- function(value) if (is.null(value) || length(value) != 1L || !is.numeric(value)) NA_real_ else as.numeric(value)
  set <- function(year, code, value) list(command = "set_parameter", year = year, code = code,
    payload = list(portfolio_ref = portfolio_ref, tax_year = year, parameter_code = code, currency = NULL, value_decimal = value))
  for (row in rows) {
    entered <- values(row$year)
    rate <- number(entered$rate); church_rate <- number(entered$church_rate)
    church <- if (is.character(entered$church) && length(entered$church) == 1L && !is.na(entered$church)) entered$church else ""
    for (pair in list(list(rate, "Persönlicher Steuersatz"), list(church_rate, "Kirchensteuersatz")))
      if (!is.na(pair[[1L]]) && (pair[[1L]] < 0 || pair[[1L]] > 100))
        return(list(error = sprintf("%d: %s muss zwischen 0 und 100 Prozent liegen.", row$year, pair[[2L]])))
    if (!church %in% c("", "applicable", "not_applicable")) return(list(error = sprintf("%d: Angabe zur Kirchensteuer nicht erkannt.", row$year)))
    if (!is.na(rate) && !same(rate, row$rate)) commands[[length(commands) + 1L]] <- set(row$year, "personal_income_tax_rate", data_tax_decimal_text_v1(rate))
    if (nzchar(church) && !identical(church, row$church)) commands[[length(commands) + 1L]] <- set(row$year, "church_tax_applicable", church)
    applicable <- identical(if (nzchar(church)) church else row$church, "applicable")
    if (applicable && is.na(church_rate) && is.na(row$church_rate))
      return(list(error = sprintf("%d: Wenn Kirchensteuer anfällt, braucht es den Kirchensteuersatz.", row$year)))
    if (applicable && !is.na(church_rate) && !same(church_rate, row$church_rate))
      commands[[length(commands) + 1L]] <- set(row$year, "church_tax_rate", data_tax_decimal_text_v1(church_rate))
  }
  list(commands = commands)
}

# --- Deutsche Namen (Festlegung 14.10.2026, #427) ------------------------------------------------------------------
# Gerade beim deutschen Steuermodul sollen deutsche, verstaendliche Namen stehen; die Kennung bleibt der Wert dahinter.
data_tax_classification_labels_v1 <- function() c(
  de_equity_share = "Aktie", de_capital_instrument = "Allgemeines Kapitalinstrument", de_cash_interest = "Cash / Zinsen", de_fund = "Fonds",
  de_private_disposal_asset = "Privates Veräußerungsgut (Jahresfrist)", de_other_income_asset = "Sonstige Einkünfte")
data_tax_bucket_labels_v1 <- function() c(
  capital_equity = "Kapitalerträge – Aktien", capital_general = "Kapitalerträge – allgemein",
  private_disposal = "Private Veräußerungsgeschäfte (§ 23 EStG)", other_income = "Sonstige Einkünfte (§ 22 Nr. 3 EStG)")
data_tax_asset_type_labels_v1 <- function() c(
  crypto = "Krypto", equity = "Aktien", fund = "Fonds", etf = "ETF", commodity = "Rohstoffe", derivative = "Derivate", bond = "Anleihen", fx = "Devisen", cash = "Cash", other = "Sonstiges")
data_tax_parameter_labels_v1 <- function() c(
  personal_income_tax_rate = "Persönlicher Steuersatz", church_tax_applicable = "Kirchensteuer fällt an", church_tax_rate = "Kirchensteuersatz",
  capital_income_tax_rate = "Abgeltungsteuersatz (Wert des Moduls überschreiben)", solidarity_surcharge_rate = "Solidaritätszuschlag (Wert des Moduls überschreiben)",
  capital_income_allowance = "Sparer-Pauschbetrag / Freistellungsauftrag", externally_used_capital_income_allowance = "Anderweitig genutzter Sparer-Pauschbetrag",
  private_disposal_exemption_threshold = "Freigrenze private Veräußerungsgeschäfte (§ 23)", other_income_exemption_threshold = "Freigrenze sonstige Einkünfte (§ 22 Nr. 3)",
  creditable_foreign_withholding_tax = "Anrechenbare ausländische Quellensteuer",
  opening_equity_loss_carryforward = "Verlustvortrag zum Jahresbeginn – Aktien",
  opening_general_capital_loss_carryforward = "Verlustvortrag zum Jahresbeginn – Kapitalerträge allgemein",
  opening_private_disposal_loss_carryforward = "Verlustvortrag zum Jahresbeginn – private Veräußerungsgeschäfte",
  opening_other_income_loss_carryforward = "Verlustvortrag zum Jahresbeginn – sonstige Einkünfte")
data_tax_value_kind_labels_v1 <- function() c(rate = "Satz in %", amount = "Betrag", applicability = "Angabe")
data_tax_applicability_labels_v1 <- function() c(applicable = "fällt an", not_applicable = "fällt nicht an")
# Ein Name aus einer der Listen; was keine Liste kennt, bleibt die Kennung.
data_tax_label_v1 <- function(labels, code, fallback = "—") {
  text <- .data_tax_text_v1(code, "")
  if (!nzchar(text)) return(fallback)
  if (text %in% names(labels)) unname(labels[[text]]) else text
}
# Auswahl mit deutschen Namen, sortiert nach dem Namen; die Kennung ist der Wert.
data_tax_named_choices_v1 <- function(labels, codes) {
  codes <- unique(as.character(codes[!is.na(codes) & nzchar(codes)]))
  if (!length(codes)) return(c("Bitte lesen" = ""))
  shown <- vapply(codes, function(code) data_tax_label_v1(labels, code), character(1L))
  stats::setNames(codes, shown)[order(tolower(shown))]
}
# Neue Fassung verfuegbar (#486 Schritt 2): je Modul die hoehere Fassung, ihre geaenderten Jahreswerte mit Fundstelle und die Zahl
# geaenderter Regeln. Uebernommen wird sie fuer alle Projektionsarten zugleich (Festlegung 16.11.2026) mit einem "Gueltig ab" (Vorgabe
# heute) - ab dem Tag rechnet Portelyra alle Steuerjahre damit; die bisherige bleibt im Datenraum und gilt bis dahin.
DATA_TAX_MODE_LABELS_V1 <- c(realized_event = "Je Ereignis", realized_annual = "Je Jahr", unrealized_snapshot = "Unrealisiert (Stichtag)")
data_tax_module_updates_ui_v1 <- function(model) {
  updates <- if (is.list(model) && is.list(model$module_updates)) model$module_updates else list()
  if (!length(updates)) return(NULL)
  blocks <- lapply(seq_along(updates), function(index) {
    update <- updates[[index]]
    changes <- if (is.list(update$value_changes)) update$value_changes else list()
    rows <- lapply(changes, function(change) shiny::tags$tr(
      shiny::tags$td(.data_tax_text_v1(change$tax_year, "")), shiny::tags$td(.data_tax_text_v1(change$value_code, "")),
      shiny::tags$td(.data_tax_text_v1(change$old_value_decimal, "–")), shiny::tags$td(.data_tax_text_v1(change$new_value_decimal, "–")),
      shiny::tags$td(.data_tax_text_v1(change$citation, "–"))))
    rule_changes <- suppressWarnings(as.integer(update$rule_change_count))
    modes <- as.character(unlist(update$projection_modes, use.names = FALSE))
    mode_labels <- vapply(modes, function(mode) if (mode %in% names(DATA_TAX_MODE_LABELS_V1)) DATA_TAX_MODE_LABELS_V1[[mode]] else mode, character(1L))
    selected <- unique(as.character(unlist(update$selected_versions, use.names = FALSE)))
    shiny::div(class = "pl-section-copy",
      shiny::p(shiny::strong(paste0("Neue Fassung verfügbar · ", data_tax_plugin_label_v1(update$plugin_id))),
        paste0(" – bisher ", if (length(selected)) paste(selected, collapse = " / ") else "?", ", verfügbar ", .data_tax_text_v1(update$available_version, "?"),
          if (identical(update$origin, "data_space")) " (installiert)" else " (mitgeliefert)", ". ",
          if (length(changes)) sprintf("%d geänderte Jahreswerte", length(changes)) else "Keine geänderten Jahreswerte",
          if (!is.na(rule_changes) && rule_changes > 0L) sprintf(", %d geänderte Regeln", rule_changes) else "", ".")),
      if (length(rows)) shiny::div(class = "pl-table-wrap", shiny::tags$table(class = "table table-condensed",
        shiny::tags$thead(shiny::tags$tr(lapply(c("Jahr", "Wert", "bisher", "neu", "Fundstelle"), shiny::tags$th))), shiny::tags$tbody(rows))),
      shiny::p(class = "pl-field-hint", paste0("Gilt dann für: ", paste(mode_labels, collapse = ", "), ".")),
      shiny::actionButton(paste0("data_tax_module_adopt_", index), "Neue Fassung für alle Projektionsarten übernehmen", class = "btn-default"))
  })
  shiny::tagList(blocks,
    shiny::dateInput("data_tax_module_adopt_from", "Gültig ab", value = Sys.Date(), min = as.Date("1900-01-01"), max = as.Date("9999-12-31"),
      format = "dd.mm.yyyy", language = "de", weekstart = 1L),
    shiny::p(class = "pl-field-hint", "Ab diesem Tag rechnet Portelyra alle Steuerjahre mit der neuen Fassung; früher erstellte Berichte nennen ihre Fassung. Die bisherige bleibt im Datenraum erhalten."))
}
# Vorschau einer Installation (#486 Schritt 2c): Fassung, Signatur, Testfaelle, Unterschiede und - falls nicht installierbar - die Gruende.
DATA_TAX_SIGNATURE_LABELS_V1 <- c(valid = "Portelyra-Signatur gültig", plugin_signature_missing = "ohne Signatur",
  plugin_signature_untrusted = "Signatur nicht von Portelyra (oder Schlüssel noch nicht eingerichtet)", plugin_signature_invalid = "Signatur passt nicht zum Inhalt",
  plugin_signature_tool_missing = "Signatur nicht prüfbar (ssh-keygen fehlt)")
data_tax_module_install_preview_ui_v1 <- function(preview) {
  if (!is.list(preview)) return(NULL)
  signature <- .data_tax_text_v1(preview$signature$status, "missing")
  selftest <- preview$selftest
  test_text <- if (!is.list(selftest)) "Testfälle nicht gerechnet" else if (identical(selftest$status, "passed"))
    sprintf("alle %d Testfälle bestanden", as.integer(selftest$scenario_count)) else
    sprintf("Testfälle nicht bestanden: %s", paste(unlist(selftest$failed), collapse = ", "))
  problems <- as.character(unlist(preview$problems, use.names = FALSE))
  changes <- if (is.list(preview$value_changes)) preview$value_changes else list()
  rows <- lapply(changes, function(change) shiny::tags$tr(
    shiny::tags$td(.data_tax_text_v1(change$tax_year, "")), shiny::tags$td(.data_tax_text_v1(change$value_code, "")),
    shiny::tags$td(.data_tax_text_v1(change$old_value_decimal, "–")), shiny::tags$td(.data_tax_text_v1(change$new_value_decimal, "–")),
    shiny::tags$td(.data_tax_text_v1(change$citation, "–"))))
  shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(paste0(data_tax_plugin_label_v1(preview$plugin_id), " · Fassung ", .data_tax_text_v1(preview$plugin_version, "?"))),
      paste0(" – ", if (signature %in% names(DATA_TAX_SIGNATURE_LABELS_V1)) DATA_TAX_SIGNATURE_LABELS_V1[[signature]] else signature, "; ", test_text, ".")),
    if (length(rows)) shiny::div(class = "pl-table-wrap", shiny::tags$table(class = "table table-condensed",
      shiny::tags$caption(paste0("Geänderte Jahreswerte gegenüber der mitgelieferten Fassung ", .data_tax_text_v1(preview$compared_with_version, ""))),
      shiny::tags$thead(shiny::tags$tr(lapply(c("Jahr", "Wert", "bisher", "neu", "Fundstelle"), shiny::tags$th))), shiny::tags$tbody(rows))),
    if (length(problems)) shiny::tags$ul(lapply(problems, function(code) shiny::tags$li(pl_error_text_v1(code)))),
    if (isTRUE(preview$installable)) shiny::tagList(
      shiny::checkboxInput("data_tax_module_install_seen", "Ich habe Fassung und Unterschiede gesehen.", FALSE),
      shiny::actionButton("data_tax_module_install", "Fassung installieren", class = "btn-primary")))
}
data_tax_plugin_label_v1 <- function(plugin_id, plugin_version = NULL) {
  id <- .data_tax_text_v1(plugin_id, "")
  base <- switch(id,
    tax_de_personal_income_tax_projection_v2 = "Deutsches Steuerrecht für Kapitalanlagen – Fassung 2 (Rechtsstand je Jahr 2020–2026, 2016–2019 in Grundzügen)",
    tax_de_personal_income_tax_projection_v1 = "Deutsches Steuerrecht für Kapitalanlagen – Fassung 1 (Vergleichsmodell)",
    id)
  version <- .data_tax_text_v1(plugin_version, "")
  if (nzchar(version)) paste0(base, " · ", version) else base
}
