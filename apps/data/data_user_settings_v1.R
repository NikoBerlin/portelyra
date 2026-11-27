# Reiter "Einstellungen" der Data-App (#500): Anzeige fuer alle Apps und Aufbewahrung der Tageshistorie.
#
# Festlegung (21./22.10.2026): ein eigener Reiter, der fuer alle Apps gilt. Gespeichert wird neben den Stammdaten
# (user-settings-v1, nur anhaengend); die anzeigenden Apps lesen die Anzeige-Einstellungen als veroeffentlichtes Artefakt
# (display_settings_v1). Die Rechnung beruehren sie nicht: Maschinendaten bleiben exakt, Steuer und Belege centgenau.
# Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_user_settings_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^user_settings_[a-z_]+$", code)) code <- "user_settings_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_user_settings_error_v1", "error", "condition")))
}

new_data_user_settings_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_user_settings.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else NULL
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_user_settings_abort_v1("user_settings_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_user_settings_abort_v1(if (is.null(parsed$code)) "user_settings_store_invalid" else parsed$code)
    parsed$result
  }
  stamp_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  structure(list(
    contract_version = "data_user_settings_service_v1",
    read = function() {
      result <- run("read", list())
      if (!is.list(result) || !identical(result$contract_version, "user_settings_v1") || !is.list(result$settings)) data_user_settings_abort_v1("user_settings_store_invalid")
      result
    },
    record = function(values, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_user_settings_abort_v1("user_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc) || !is.list(values) || !length(values)) data_user_settings_abort_v1("user_settings_input_invalid")
      run("record", list(values = values, recorded_at_utc = recorded_at_utc, confirmed = TRUE))
    },
    durations_read = function() {
      result <- run("durations-read", list())
      if (!is.list(result) || !is.list(result$durations)) data_user_settings_abort_v1("user_settings_store_invalid")
      result$durations
    },
    durations_record = function(durations, recorded_at_utc) {
      if (!stamp_valid(recorded_at_utc) || !is.list(durations) || !length(durations)) data_user_settings_abort_v1("user_settings_input_invalid")
      run("durations-record", list(durations = durations, recorded_at_utc = recorded_at_utc))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_user_settings_service_v1", "list"))
}

# Rueckgangszonen der Analyse (#506): "30, 50", "30;50" oder "-30 %" ergeben "30,50"; leer heisst keine. NA bei ungueltiger Eingabe:
# bis zu drei ganze Zahlen von 5 bis 95.
# Grenze fuer Kleinstbestaende (#534): "1", "0,5" oder "1.50" -> Dezimaltext mit Punkt; leer heisst die Vorgabe 1 Euro,
# ungueltig NA. Hoechstens 1000 Euro mit zwei Nachkommastellen.
data_user_settings_small_threshold_v1 <- function(text) {
  if (is.null(text) || !is.character(text) || length(text) != 1L || is.na(text)) return(NA_character_)
  value <- gsub("[[:space:]\u20ac]", "", text)
  if (!nzchar(value)) return("1")
  value <- sub(",", ".", value, fixed = TRUE)
  if (!grepl("^(0|[1-9][0-9]{0,3})([.][0-9]{1,2})?$", value) || as.numeric(value) > 1000) return(NA_character_)
  number <- as.numeric(value)
  if (number == 0) "0" else sub("[.]$", "", sub("0+$", "", if (grepl("[.]", value)) value else paste0(value, ".")))
}
data_user_settings_small_label_v1 <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) sub(".", ",", value, fixed = TRUE) else "1"
data_user_settings_zones_v1 <- function(text) {
  if (is.null(text) || !is.character(text) || length(text) != 1L || is.na(text)) return(NA_character_)
  parts <- strsplit(gsub("[%\u2212-]", "", trimws(text)), "[[:space:],;]+")[[1L]]; parts <- parts[nzchar(parts)]
  if (!length(parts)) return("")
  if (length(parts) > 3L || !all(grepl("^[0-9]{1,2}$", parts))) return(NA_character_)
  values <- sort(unique(as.integer(parts)))
  if (any(values < 5L | values > 95L)) return(NA_character_)
  paste(values, collapse = ",")
}
data_user_settings_zones_label_v1 <- function(value) if (is.null(value) || !nzchar(value)) "" else gsub(",", ", ", value, fixed = TRUE)

data_user_settings_error_text_v1 <- function(code) switch(as.character(code),
  user_settings_input_invalid = "Ein Wert liegt außerhalb des Erlaubten (Nachkommastellen 0 oder 2, Läufe 2 bis 50, Rückgangszonen bis zu drei ganze Zahlen von 5 bis 95).",
  user_settings_confirmation_required = "Speichern bitte über den Knopf bestätigen.",
  "Der Speicher der Einstellungen ließ sich nicht lesen oder schreiben. Daten und Buchungen sind davon nicht berührt.")

# Groesse der veroeffentlichten Tageshistorie: Kern des geltenden Laufs und alle Teildateien (#503). Liest nur Dateigroessen.
data_user_settings_history_size_v1 <- function(space) {
  area <- file.path(space, "artifacts", "portfolio_history")
  latest <- tryCatch(jsonlite::fromJSON(file.path(area, "latest.json"), simplifyVector = FALSE), error = function(error) NULL)
  core <- if (is.list(latest) && is.character(latest$run_id) && grepl("^run_[a-z0-9_]+$", latest$run_id))
    file.info(file.path(area, "runs", latest$run_id, "artifact.json"))$size else NA_real_
  runs <- if (dir.exists(file.path(area, "runs"))) length(list.dirs(file.path(area, "runs"), recursive = FALSE)) else 0L
  parts_dir <- file.path(space, "artifacts", "portfolio_history_parts")
  parts <- if (dir.exists(parts_dir)) file.info(list.files(parts_dir, pattern = "\\.json$", full.names = TRUE))$size else numeric()
  list(core_bytes = core, runs = runs, part_count = length(parts), part_bytes = sum(parts))
}

data_user_settings_size_text_v1 <- function(size) {
  if (!is.list(size) || is.na(size$core_bytes)) return("Noch keine Tageshistorie veröffentlicht.")
  mb <- function(bytes) formatC(bytes / 1e6, format = "f", digits = 1, decimal.mark = ",")
  sprintf("Heute: Kern %s MB (Grenze 50 MB), dazu %d Teildateien mit %s MB; %d Läufe liegen vor.", mb(size$core_bytes), size$part_count,
          mb(size$part_bytes), size$runs)
}

# Standard-Zeitraum der Analyse (Festlegung 23.10.2026): dieselbe Reihenfolge wie die Wahl in den Reitern der Analyse.
DATA_USER_SETTINGS_PERIODS_V1 <- c("1 Monat" = "1m", "3 Monate" = "3m", "Laufendes Quartal" = "qtd", "Laufendes Jahr" = "ytd",
  "1 Jahr" = "1y", "3 Jahre" = "3y", "5 Jahre" = "5y", "Alles" = "all")

# Linien und Kennwerte des Portfolio-Verlaufs der Analyse (#531 Punkt 2): dieselbe Folge wie dort.
DATA_USER_SETTINGS_LINES_V1 <- c("Gesamtvermögen" = "net_worth", "Marktwert" = "market_value", "Einstand" = "cost_basis", "Cash belegt" = "cash_documented",
  "Cash gesamt (mit abgeleiteten Salden)" = "cash", "Extern zugeflossen" = "contributed", "Unrealisierte GuV" = "unrealised")

data_user_settings_ui_v1 <- function() shiny::tagList(
  shiny::p(class = "pl-section-copy", "Diese Einstellungen gelten für alle Apps. Sie ändern die Anzeige, die Aufbewahrung und den Zeitpunkt des Kursabrufs, nie eine Rechnung."),
  portelyra_card("Anzeige", help = "app-data#anzeige-und-berechnung",
    copy = "Euro-Beträge in Übersichten ohne oder mit zwei Nachkommastellen; Erfolgskennzahlen in Tabellen leicht farbig hinterlegt (Gewinn blau, Verlust rot) oder schlicht.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-settings-display", paste(
      "Steuerangaben, Belege und Rechenblätter bleiben immer centgenau. Die Analyse zeigt die Wahl nach „Neu lesen“.",
      "Die Linien des Portfolio-Verlaufs gelten beim Öffnen der Analyse; dort lassen sie sich jederzeit umschalten.",
      "Kleinstbestände: Cash-Salden über 0 und unter der Grenze auf geschlossenen oder ruhenden Konten blenden Analyse und Cockpit aus und zählen sie; ein Schalter zeigt sie.",
      "Gerechnet wird weiter mit dem exakten Wert. 0 heißt: nichts ausblenden.")),
    shiny::div(class = "pl-form-grid",
      shiny::radioButtons("user_settings_decimals", "Nachkommastellen bei Euro-Beträgen", c("keine (1.234 €)" = "0", "zwei (1.234,56 €)" = "2"), selected = "0"),
      shiny::radioButtons("user_settings_tint", "Erfolgskennzahlen farbig hinterlegen", c("ja" = "on", "nein" = "off"), selected = "on")),
    shiny::checkboxGroupInput("user_settings_lines", "Linien und Kennwerte im Portfolio-Verlauf der Analyse", DATA_USER_SETTINGS_LINES_V1,
                              selected = unname(DATA_USER_SETTINGS_LINES_V1), inline = TRUE),
    shiny::div(class = "pl-form-grid",
      shiny::textInput("user_settings_small", "Kleinstbestände ausblenden unter (€)", "1", placeholder = "z. B. 1 oder 0,50"))),
  portelyra_card("Expertenwerkzeuge", help = "app-data#anzeige-und-berechnung",
    copy = "Seltene Werkzeuge in allen Reitern zeigen; ausgeblendet bleibt alles erhalten.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-settings-expert", paste(
      "Dazu gehören Rechenfelder und Korrekturhistorie, die Buchungsliste als CSV, Prüf- und Sammelwerkzeuge für Kurse,",
      "den Abschluss mit anderem Stichtag und weitere Steuerparameter sowie ältere Importwege. Im Cockpit zeigt der Schalter den Reiter „Abschluss im Detail“.",
      "Karten für Störungen erscheinen ohne Schalter von selbst, sobald etwas hängt.")),
    shiny::radioButtons("user_settings_expert", "Expertenwerkzeuge zeigen", c("nein" = "off", "ja" = "on"), selected = "off", inline = TRUE)),
  portelyra_card("Analyse", help = "app-data#anzeige-und-berechnung",
    copy = "Mit welchem Zeitraum die Analyse öffnet; umschalten lässt er sich dort jederzeit.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-settings-analysis", paste(
      "Der Zeitraum gilt für alle Bilder und Tabellen der Analyse; Tabellen zeigen die Zeiträume darin, für Monat und Quartal das laufende Jahr.",
      "Rückgangszonen für das Bild „Abstand vom Hoch“: bis zu drei Schwellen in Prozent unter dem bisherigen Hoch, etwa 30 und 50.",
      "Die Analyse zeigt sie als Bänder und zählt beim einzelnen Asset, wie viele Käufe darin lagen. Leer heißt keine Zonen.")),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("user_settings_period", "Zeitraum beim Öffnen", DATA_USER_SETTINGS_PERIODS_V1, selected = "all", selectize = FALSE),
      shiny::textInput("user_settings_zones", "Rückgangszonen in Prozent", "", placeholder = "z. B. 30, 50"))),
  portelyra_card("Kursabruf", help = "app-data#anzeige-und-berechnung",
    copy = "Ab wann der Kurs eines Tages als Schlusskurs gilt. Erst danach holt ein Abruf ihn als Tageswert.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-settings-market-day", paste(
      "Handelsschluss: Börsen gelten eine Stunde nach ihrem Schluss als abgeschlossen – XETRA ab 18:35, Frankfurt und Stuttgart ab 23:00,",
      "New York ab 23:00 deutscher Zeit. Ein Lauf nach Mitternacht holt so die Schlusskurse des Vortags; bisher galten sie erst ab 1 Uhr (New York ab 7 Uhr).",
      "Abgerufen wird wie bisher bis gestern; die Werte von heute zeigt die Momentaufnahme.",
      "Krypto, Wechselkurse und Börsen ohne bekannte Schlusszeit gelten immer erst nach dem Ende ihres Kalendertags, gegen 2 Uhr nachts.",
      "Assets in Fremdwährung werden für einen Tag erst bewertet, wenn auch der Wechselkurs dieses Tages abgeschlossen ist.",
      "Ein früher geholter Kurs bleibt vorläufig und wird erneut angefordert, bis ein späterer Abruf ihn bestätigt. Die Wahl gilt ab dem nächsten Abruf.")),
    shiny::radioButtons("user_settings_market_day", "Tageskurse abrufen ab",
      c("Handelsschluss + 1 Stunde" = "session_close", "Ende des Kalendertags + 1 Stunde" = "calendar_day_end"), selected = "session_close")),
  portelyra_card("Tageshistorie", help = "app-data#anzeige-und-berechnung",
    copy = "Nach jedem Veröffentlichen bleiben die jüngsten Läufe; ältere und nicht mehr gebrauchte Teildateien werden gelöscht.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-settings-history", paste(
      "Die Reihe lässt sich jederzeit aus den Daten neu erzeugen, ältere Läufe braucht man nur zum Vergleichen.")),
    shiny::div(class = "pl-form-grid",
      shiny::numericInput("user_settings_keep_runs", "Läufe aufbewahren", value = 5L, min = 2L, max = 50L, step = 1L)),
    shiny::uiOutput("user_settings_size")),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton("user_settings_save", "Einstellungen speichern", class = "btn-primary")),
  shiny::uiOutput("user_settings_state"))

data_user_settings_server_v1 <- function(input, output, session, service, now_utc, space = NULL) {
  notice <- shiny::reactiveVal(NULL); tick <- shiny::reactiveVal(0L)
  # Die Data-App braucht den Schalter schon beim Start, nicht erst beim Aufklappen der Einstellungen (#452; Kopfzeile seit rc.332).
  expert_read <- function() tryCatch(identical(service$read()$settings$expert_tools, "on"), error = function(error) FALSE)
  expert <- shiny::reactiveVal(if (is.null(service)) FALSE else expert_read())
  current <- shiny::reactive({
    tick()
    if (!isTRUE(input$settings_panel_open)) return(NULL)
    if (is.null(service)) return(structure(list(), code = "user_settings_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "user_settings_store_invalid" else error$code))
  })
  shiny::observeEvent(current(), {
    value <- current(); if (!is.null(attr(value, "code"))) return()
    shiny::updateRadioButtons(session, "user_settings_decimals", selected = value$settings$amount_decimals)
    shiny::updateRadioButtons(session, "user_settings_tint", selected = value$settings$tint)
    shiny::updateNumericInput(session, "user_settings_keep_runs", value = as.integer(value$settings$history_keep_runs))
    if (!is.null(value$settings$expert_tools)) shiny::updateRadioButtons(session, "user_settings_expert", selected = value$settings$expert_tools)
    if (!is.null(value$settings$analysis_period)) shiny::updateSelectInput(session, "user_settings_period", selected = value$settings$analysis_period)
    if (!is.null(value$settings$market_day_completion)) shiny::updateRadioButtons(session, "user_settings_market_day", selected = value$settings$market_day_completion)
    if (!is.null(value$settings$drawdown_zones)) shiny::updateTextInput(session, "user_settings_zones", value = data_user_settings_zones_label_v1(value$settings$drawdown_zones))
    if (!is.null(value$settings$history_lines))
      shiny::updateCheckboxGroupInput(session, "user_settings_lines", selected = strsplit(value$settings$history_lines, ",", fixed = TRUE)[[1L]])
    if (!is.null(value$settings$small_holdings_threshold))
      shiny::updateTextInput(session, "user_settings_small", value = data_user_settings_small_label_v1(value$settings$small_holdings_threshold))
  }, ignoreNULL = TRUE)
  output$user_settings_size <- shiny::renderUI({
    if (!isTRUE(input$settings_panel_open) || is.null(space)) return(NULL)
    tick()
    shiny::p(class = "pl-field-hint", data_user_settings_size_text_v1(tryCatch(data_user_settings_history_size_v1(space), error = function(error) NULL)))
  })
  lines_touched <- shiny::reactiveVal(FALSE)
  shiny::observeEvent(input$user_settings_lines, lines_touched(TRUE), ignoreInit = TRUE)
  shiny::observeEvent(input$user_settings_save, {
    keep <- suppressWarnings(as.integer(input$user_settings_keep_runs))
    zones <- data_user_settings_zones_v1(if (is.null(input$user_settings_zones)) "" else input$user_settings_zones)
    small <- data_user_settings_small_threshold_v1(if (is.null(input$user_settings_small)) "" else input$user_settings_small)
    if (is.na(small)) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = "Die Grenze für Kleinstbestände ist ein Betrag in Euro von 0 bis 1.000, z. B. 1 oder 0,50.")); return()
    }
    if (length(keep) != 1L || is.na(keep) || keep < 2L || keep > 50L || is.na(zones)) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = data_user_settings_error_text_v1("user_settings_input_invalid"))); return()
    }
    # Hat sich das Feld noch nicht gemeldet, bleibt die Wahl, wie sie ist; leer gewaehlt wird abgewiesen.
    lines <- intersect(unname(DATA_USER_SETTINGS_LINES_V1), input$user_settings_lines)
    if (!length(lines) && isTRUE(lines_touched())) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = "Für den Portfolio-Verlauf mindestens eine Linie wählen.")); return()
    }
    values <- list(amount_decimals = as.character(input$user_settings_decimals), tint = as.character(input$user_settings_tint),
                   history_keep_runs = as.character(keep),
                   expert_tools = if (identical(input$user_settings_expert, "on")) "on" else "off", drawdown_zones = zones,
                   analysis_period = if (isTRUE(input$user_settings_period %in% DATA_USER_SETTINGS_PERIODS_V1)) input$user_settings_period else "all",
                   history_lines = if (length(lines)) paste(lines, collapse = ",") else NULL, small_holdings_threshold = small,
                   market_day_completion = if (identical(input$user_settings_market_day, "calendar_day_end")) "calendar_day_end" else "session_close")
    values <- Filter(Negate(is.null), values)
    result <- tryCatch(service$record(values, now_utc(), TRUE), error = function(error) structure(list(), code = if (is.null(error$code)) "user_settings_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) {
      notice(list(tone = "error", title = "Nicht gespeichert", copy = data_user_settings_error_text_v1(attr(result, "code")))); return()
    }
    tick(tick() + 1L); expert(identical(values$expert_tools, "on"))
    # Gespeichert oder nichts zu speichern: Der Bereich in der Kopfzeile klappt zu, die Rueckmeldung steht neben dem Knopf
    # (rc.333). Bei Warnung oder Fehler bleibt er offen, damit sie gelesen wird.
    done <- function(text) session$sendCustomMessage("pl_settings_done", list(text = text))
    if (identical(result$status, "unchanged")) {
      notice(list(tone = "neutral", title = "Nichts geändert", copy = "Die gewählten Werte gelten bereits.")); done("Nichts geändert"); return()
    }
    published <- !identical(result$publication, "failed")
    notice(list(tone = if (published) "positive" else "warning", title = "Gespeichert",
      copy = if (published) "Die Analyse zeigt die neue Anzeige nach „Neu lesen“. Die Aufbewahrung gilt ab dem nächsten Veröffentlichen der Tageshistorie, der Kursabruf ab dem nächsten Abruf."
             else "Gespeichert, aber für die anzeigenden Apps nicht veröffentlicht. Erneut speichern versucht es noch einmal."))
    if (published) done("Einstellungen gespeichert")
  })
  output$user_settings_state <- shiny::renderUI({
    value <- notice()
    if (is.null(value)) {
      read <- current(); code <- attr(read, "code")
      if (is.null(code)) return(NULL)
      return(portelyra_status_panel("Einstellungen nicht lesbar", data_user_settings_error_text_v1(code), tone = "warning"))
    }
    portelyra_status_panel(value$title, value$copy, tone = value$tone)
  })
  invisible(list(current = current, notice = notice, expert = expert))
}
