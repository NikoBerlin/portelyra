# Bewertung ueber die Zeit (rc.393, #495): die Bewertungs-Zeitleiste je Asset im Asset-Center, "3. Marktdaten" -> "1. Kursquelle".
# Festlegung vom 10.11.2026: bis Tag X eigene oder Trade-Kurse, ab X Yahoo, spaeter ein anderer Anbieter; Wechsel "ab Datum"
# (Vorgabe heute) und "ganze Historie neu". Kern und Pruefung: migrations/reference/asset_valuation_timeline_v1.py, CLI
# scripts/desktop_asset_valuation_timeline.py, Vertrag contracts/asset-valuation-timeline/v1/. Die Oberflaeche baut nur die Abschnitte,
# zeigt die Vorschau des Kerns und schreibt erst nach dem Haekchen. Muss die Bewertungsart der Stammdaten mit umgestellt werden, laeuft
# zuerst der Katalogbefehl (wie "Bewertungsart aendern"), danach die Zeitleiste; der Kern prueft die Reihenfolge.

# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
DATA_ASSET_VALUATION_TIMELINE_METHODS_V1 <- c(external_market = "Marktdaten", manual = "eigene Kurse bzw. Trade-Kurse",
                                              transaction_only = "nur Transaktionen")

data_asset_valuation_timeline_abort_v1 <- function(code) {
  stop(structure(class = c("spot_asset_valuation_timeline_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
}

data_asset_valuation_timeline_error_text_v1 <- function(code) switch(as.character(code),
  asset_valuation_timeline_asset_invalid = paste("Für dieses Asset gibt es keine Bewertung über die Zeit: Es ist nicht aktiv, ein Cash-Asset oder",
    "hat eine Bewertungsart, die die Zeitleiste nicht kennt (etwa Einheitswert)."),
  asset_valuation_timeline_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.",
  asset_valuation_timeline_future_date = "Ein Abschnitt beginnt nach heute. Ein Wechsel gilt höchstens ab heute (Tagesgrenze UTC).",
  asset_valuation_timeline_input_invalid = paste("Die Abschnitte passen nicht zusammen: Der erste gilt seit Beginn, die Tage steigen auf, ein",
    "Marktabschnitt braucht Anbieter und Symbol, und zwei gleiche Abschnitte folgen nicht aufeinander."),
  asset_valuation_timeline_method_mismatch = "Die Bewertungsart in den Stammdaten ist noch nicht auf die Art des letzten Abschnitts umgestellt.",
  asset_valuation_timeline_preview_stale = "Die Zeitleiste hat sich seit der Vorschau geändert. Bitte die Vorschau neu erstellen.",
  asset_valuation_timeline_series_not_ready = paste("Die Kursreihe des laufenden Abschnitts ist nicht geprüft und aktiv. Sie wird bei der",
    "Bewertungsart Marktdaten eingerichtet: Zuordnung speichern, dann „2. Einrichten“."),
  asset_valuation_timeline_series_unknown = paste("Das Symbol eines Marktabschnitts passt nicht zur heutigen Kurszuordnung seines Anbieters, oder es",
    "gibt weder eine Zuordnung noch Kurse dieser Reihe im Bewertungsstand. Bitte das Asset neu wählen und die Vorschau wiederholen."),
  asset_valuation_timeline_store_invalid = paste("Die Zeitleiste ist nicht lesbar: Ihr Speicher gehört zu einem anderen Datenraum oder ist",
    "beschädigt. Bitte das Backup prüfen."),
  "Die Bewertung über die Zeit ist gerade nicht lesbar.")

data_asset_valuation_timeline_error_copy_v1 <- function(code) sprintf("%s (%s)", data_asset_valuation_timeline_error_text_v1(code), as.character(code))

# Gruende des Katalogbefehls, wenn die Bewertungsart der Stammdaten nicht umgestellt werden konnte.
data_asset_valuation_timeline_catalog_copy_v1 <- function(code) {
  code <- if (is.character(code) && length(code) == 1L && !is.na(code)) code else "desktop_catalog_boundary_failed"
  text <- switch(code,
    desktop_catalog_preview_required = "Die Stammdaten haben sich zwischenzeitlich geändert.",
    desktop_catalog_confirmation_consumed = "Die Bestätigung war schon verbraucht.",
    desktop_catalog_input_invalid = "Der Katalog hat die Umstellung abgewiesen (Asset archiviert oder Art schon eingestellt).",
    "Der Katalogbefehl wurde abgewiesen.")
  sprintf("%s (%s)", text, code)
}

data_asset_valuation_timeline_method_label_v1 <- function(method) {
  # Ein Einheitswert (bis rc.392 bei Nicht-Cash-Assets waehlbar) wird angezeigt, ist aber keine waehlbare Art eines Abschnitts.
  if (identical(method, "unit_value")) return("Einheitswert (1 je Mengeneinheit)")
  method <- as.character(method)
  if (length(method) == 1L && !is.na(method) && method %in% names(DATA_ASSET_VALUATION_TIMELINE_METHODS_V1))
    DATA_ASSET_VALUATION_TIMELINE_METHODS_V1[[method]] else if (length(method) == 1L && !is.na(method) && nzchar(method)) method else "–"
}

new_data_asset_valuation_timeline_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_asset_valuation_timeline.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_asset_valuation_timeline_abort_v1("asset_valuation_timeline_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id,
                  role = "desktop_owner")
  request <- function(extra) as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE,
                                                           null = "null", digits = NA))
  parse <- function(output, status = 0L) {
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(status), 0L))
      data_asset_valuation_timeline_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "asset_valuation_timeline_store_invalid")
    parsed$result
  }
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = request(extra)))
    status <- attr(output, "status"); parse(output, if (is.null(status)) 0L else status)
  }
  list(
    overview = function() run("overview", list()),
    read = function(asset_id) run("read", list(asset_id = asset_id)),
    # Eine leere Liste hebt die Zeitleiste auf.
    preview = function(asset_id, segments) run("preview", list(asset_id = asset_id, segments = if (length(segments)) segments else list())),
    apply = function(preview, confirmed) run("apply", list(preview = preview, confirmed = isTRUE(confirmed))))
}

.data_avt_text_v1 <- function(value) if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) value else NULL
.data_avt_segment_v1 <- function(valid_from, method, provider_id = NULL, provider_symbol = NULL) {
  market <- identical(method, "external_market")
  list(valid_from = .data_avt_text_v1(valid_from), method = method, provider_id = if (market) .data_avt_text_v1(provider_id) else NULL,
       provider_symbol = if (market) .data_avt_text_v1(provider_symbol) else NULL)
}
.data_avt_same_v1 <- function(left, right) identical(left$method, right$method) && identical(left$provider_id, right$provider_id) &&
  identical(left$provider_symbol, right$provider_symbol)

# Wert der Auswahl "Kursreihe": Anbieter und Symbol. Die Anbieterkennung kennt keinen Doppelpunkt, getrennt wird am ersten.
data_asset_valuation_timeline_series_value_v1 <- function(provider_id, provider_symbol) paste0(provider_id, ":", provider_symbol)
data_asset_valuation_timeline_series_parse_v1 <- function(value) {
  value <- .data_avt_text_v1(value); if (is.null(value) || !grepl(":", value, fixed = TRUE)) return(NULL)
  at <- regexpr(":", value, fixed = TRUE)[[1L]]
  list(provider_id = substr(value, 1L, at - 1L), provider_symbol = substr(value, at + 1L, nchar(value)))
}

# Nur gepruefte, aktive Zuordnungen kommen als Kursreihe eines neuen Abschnitts in Frage (der Kern verlangt das fuer den laufenden).
data_asset_valuation_timeline_ready_series_v1 <- function(timeline) {
  rows <- if (is.list(timeline) && is.list(timeline$mappings)) timeline$mappings else list()
  Filter(function(row) identical(row$verification_status, "verified") && isTRUE(row$enabled) && !is.null(.data_avt_text_v1(row$provider_id)) &&
           !is.null(.data_avt_text_v1(row$provider_symbol)), rows)
}

# Ohne eigene Zeitleiste traegt die Kursreihe der Zuordnung (Regel aus #474): ein Symbol; sonst das eine aktive; sonst das mit dem
# spaetesten bewerteten Tag. Laesst sie sich nicht bestimmen, kann ein Wechsel "ab Datum" den Zeitraum davor nicht beschreiben.
data_asset_valuation_timeline_implicit_series_v1 <- function(timeline) {
  rows <- Filter(function(row) !is.null(.data_avt_text_v1(row$provider_id)) && !is.null(.data_avt_text_v1(row$provider_symbol)),
                 if (is.list(timeline$mappings)) timeline$mappings else list())
  if (!length(rows)) return(NULL)
  symbol_of <- function(items) unique(vapply(items, function(row) row$provider_symbol, character(1L)))
  symbols <- symbol_of(rows)
  enabled <- Filter(function(row) isTRUE(row$enabled), rows)
  symbol <- if (length(symbols) == 1L) symbols else if (length(symbol_of(enabled)) == 1L) symbol_of(enabled) else {
    last <- vapply(symbols, function(item) { cover <- timeline$coverage[[item]]; text <- if (is.list(cover)) .data_avt_text_v1(cover$last) else NULL
      if (is.null(text)) "" else text }, character(1L))
    if (!any(nzchar(last)) || sum(last == max(last)) != 1L) return(NULL)
    symbols[[which(last == max(last))[[1L]]]]
  }
  candidates <- Filter(function(row) identical(row$provider_symbol, symbol), rows)
  ranked <- c(Filter(function(row) identical(row$verification_status, "verified") && isTRUE(row$enabled), candidates),
              Filter(function(row) isTRUE(row$enabled), candidates), candidates)
  list(provider_id = ranked[[1L]]$provider_id, provider_symbol = ranked[[1L]]$provider_symbol)
}

# Die geltenden Abschnitte, wie der Kern sie erwartet; ohne eigene Zeitleiste mit der Kursreihe der Zuordnung.
data_asset_valuation_timeline_current_v1 <- function(timeline) {
  rows <- lapply(if (is.list(timeline$segments)) timeline$segments else list(), function(row)
    .data_avt_segment_v1(row$valid_from, row$method, row$provider_id, row$provider_symbol))
  derived <- FALSE; unresolved <- FALSE
  if (!isTRUE(timeline$explicit) && length(rows) == 1L && identical(rows[[1L]]$method, "external_market") && is.null(rows[[1L]]$provider_id)) {
    series <- data_asset_valuation_timeline_implicit_series_v1(timeline)
    if (is.null(series)) unresolved <- TRUE else {
      rows[[1L]]$provider_id <- series$provider_id; rows[[1L]]$provider_symbol <- series$provider_symbol; derived <- TRUE
    }
  }
  list(rows = rows, derived = derived, unresolved = unresolved)
}

# Die neue Zeitleiste fuer "Ab Datum wechseln": Die bisherigen Abschnitte enden am Vortag, spaetere entfallen. "Ganze Historie neu"
# ersetzt alles durch einen Abschnitt seit Beginn. Ergebnis: list(segments) oder list(problem) oder list(unchanged = TRUE).
# `today`: heutiger UTC-Tag (Text) fuer die Pruefung der Tiefe bei Anbietern, die nur "ab Datum" eingesetzt werden (rc.394).
data_asset_valuation_timeline_plan_v1 <- function(timeline, whole_history, from_day, method, series = NULL, today = NULL) {
  if (!is.character(method) || length(method) != 1L || !method %in% names(DATA_ASSET_VALUATION_TIMELINE_METHODS_V1))
    return(list(problem = "Bitte eine Bewertung wählen."))
  chosen <- if (identical(method, "external_market")) data_asset_valuation_timeline_series_parse_v1(series) else NULL
  if (identical(method, "external_market") && is.null(chosen))
    return(list(problem = "Bitte eine Kursreihe wählen. Zur Wahl stehen die geprüften, aktiven Zuordnungen dieses Assets."))
  current <- data_asset_valuation_timeline_current_v1(timeline)
  whole <- isTRUE(whole_history)
  day <- if (whole) NULL else .data_avt_text_v1(if (length(from_day) == 1L && !is.na(from_day)) as.character(from_day) else NULL)
  if (!whole && (is.null(day) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", day))) return(list(problem = "Bitte den Tag wählen, ab dem der Wechsel gilt."))
  if (!whole && isTRUE(current$unresolved))
    return(list(problem = paste("Die bisherige Kursreihe dieses Assets ist nicht eindeutig: keine Zuordnung oder mehrere ohne klaren Vorrang.",
      "Bitte „Ganze Historie neu“ wählen, um die Zeitleiste ab dem ersten Tag festzulegen.")))
  limits <- if (exists("PL_PRICE_PROVIDERS_FROM_DATE_ONLY_V1")) PL_PRICE_PROVIDERS_FROM_DATE_ONLY_V1 else integer()
  limited <- identical(method, "external_market") && isTRUE(chosen$provider_id %in% names(limits))
  label <- if (limited && exists("pl_price_provider_label_v1", mode = "function")) pl_price_provider_label_v1(chosen$provider_id, chosen$provider_id) else chosen$provider_id
  if (limited && whole) return(list(problem = sprintf(paste("%s wird nur ab einem Datum eingesetzt: Kostenlos liefert es etwa %d Tage Kurse,",
    "mit „Ganze Historie neu“ blieben alle älteren Tage ohne Kurs. Bitte „Ab Datum wechseln“ wählen; die Kurse davor bleiben beim",
    "bisherigen Anbieter."), label, as.integer(limits[[chosen$provider_id]]))))
  warning <- NULL
  if (limited && !is.null(.data_avt_text_v1(today)) && as.integer(as.Date(today) - as.Date(day)) > as.integer(limits[[chosen$provider_id]]))
    warning <- sprintf(paste("Der Tag liegt mehr als %d Tage zurück. Kostenlos liefert %s nur etwa so viel Historie; ältere Tage dieses",
      "Abschnitts bleiben dann ohne Kurs. Ein späterer Tag vermeidet das."), as.integer(limits[[chosen$provider_id]]), label)
  new <- .data_avt_segment_v1(day, method, chosen$provider_id, chosen$provider_symbol)
  segments <- if (whole) list(new) else {
    kept <- Filter(function(row) is.null(row$valid_from) || row$valid_from < day, current$rows)
    if (length(kept) && .data_avt_same_v1(kept[[length(kept)]], new)) kept else c(kept, list(new))
  }
  same_rows <- length(segments) == length(current$rows) && all(vapply(seq_along(segments), function(index)
    .data_avt_same_v1(segments[[index]], current$rows[[index]]) && identical(segments[[index]]$valid_from, current$rows[[index]]$valid_from), logical(1L)))
  if (same_rows) return(list(unchanged = TRUE))
  list(segments = segments, warning = warning)
}

.data_avt_count_v1 <- function(value) {
  number <- suppressWarnings(as.numeric(value))
  if (length(number) != 1L || is.na(number)) "0" else formatC(number, format = "d", big.mark = ".", decimal.mark = ",")
}

data_asset_valuation_timeline_coverage_text_v1 <- function(timeline, row) {
  if (identical(row$method, "transaction_only")) return("nicht nötig")
  if (identical(row$method, "manual")) return("eigene Angaben bzw. Trade-Kurse")
  symbol <- .data_avt_text_v1(row$provider_symbol); if (is.null(symbol)) return("–")
  cover <- if (is.list(timeline$coverage)) timeline$coverage[[symbol]] else NULL
  days <- suppressWarnings(as.numeric(if (is.list(cover)) cover$days else 0))
  if (!length(days) || is.na(days) || days <= 0) return("keine bewerteten Tage")
  sprintf("%s Tage (%s – %s)", .data_avt_count_v1(days), pl_day_v1(cover$first), pl_day_v1(cover$last))
}

data_asset_valuation_timeline_period_text_v1 <- function(row) {
  start <- if (is.null(.data_avt_text_v1(row$valid_from))) "seit Beginn" else pl_day_v1(row$valid_from)
  end <- if (is.null(.data_avt_text_v1(row$valid_until))) "bis heute" else pl_day_v1(row$valid_until)
  sprintf("%s – %s", start, end)
}

data_asset_valuation_timeline_ui_v1 <- function(today = as.Date(format(Sys.time(), "%Y-%m-%d", tz = "UTC"))) portelyra_card("Bewertung über die Zeit", help = "app-data#bewerten",
  copy = "Welche Bewertung für welchen Zeitraum gilt – etwa bis zu einem Tag eigene Kurse, danach die Kurse eines Anbieters.",
  note = portelyra_note_v1(title = "So lesen Sie die Tabelle", id = "data-asset-valuation-timeline",
    "Jeder Abschnitt gilt bis zum Tag vor dem nächsten; die Tagesgrenze ist UTC.",
    "Fehlt der Kursreihe eines Marktabschnitts ein Tag, bleibt er offen. Portelyra nimmt nicht still eine andere Reihe.",
    "Ein Marktabschnitt folgt der Kurszuordnung seines Anbieters: Ändert sich dort das Symbol, gilt das neue für den ganzen Abschnitt.",
    "Bei Marktdaten ist Yahoo Finance der Standardanbieter und liefert auch Wechselkurse und Momentkurse; weitere Anbieter wie EODHD liefern nur Tageskurse.",
    "In einem Abschnitt „eigene Kurse bzw. Trade-Kurse“ gilt der jüngste eigene Kurs weiter, auch einer von davor; sein Alter wird angezeigt.",
    "„Kurse vorhanden“ zählt die bewerteten Tage der ganzen Kursreihe, nicht nur die des Abschnitts."),
  shiny::uiOutput("asset_valuation_timeline_state"),
  shiny::uiOutput("asset_valuation_timeline_table"),
  shiny::tags$details(class = "pl-disclosure", id = "asset-valuation-timeline-change",
    shiny::tags$summary("Ab Datum wechseln"),
    shiny::checkboxInput("asset_valuation_timeline_whole", "Ganze Historie neu (ab dem ersten Tag)", FALSE),
    shiny::conditionalPanel("!input.asset_valuation_timeline_whole",
      shiny::dateInput("asset_valuation_timeline_from", "Ab Tag", value = today, max = today, format = "dd.mm.yyyy", language = "de", weekstart = 1),
      shiny::p(class = "pl-field-hint", "Die bisherigen Abschnitte enden am Vortag; Abschnitte ab diesem Tag entfallen.")),
    shiny::conditionalPanel("input.asset_valuation_timeline_whole",
      shiny::p(class = "pl-field-hint", "Ersetzt die ganze Zeitleiste durch einen Abschnitt seit Beginn.")),
    shiny::selectInput("asset_valuation_timeline_method", "Bewertung", stats::setNames(names(DATA_ASSET_VALUATION_TIMELINE_METHODS_V1),
      unname(DATA_ASSET_VALUATION_TIMELINE_METHODS_V1)), selectize = FALSE),
    shiny::conditionalPanel("input.asset_valuation_timeline_method == 'external_market'", shiny::uiOutput("asset_valuation_timeline_series_choice")),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("asset_valuation_timeline_preview", "Vorschau", class = "btn-default")),
    shiny::uiOutput("asset_valuation_timeline_preview_panel")),
  data_expert_only_v1(shiny::tags$details(class = "pl-disclosure", id = "asset-valuation-timeline-clear",
    shiny::tags$summary("Zeitleiste aufheben"),
    shiny::uiOutput("asset_valuation_timeline_clear_body"),
    shiny::uiOutput("asset_valuation_timeline_clear_panel"))))

data_asset_valuation_timeline_state_ui_v1 <- function(timeline) {
  if (is.null(timeline)) return(shiny::p(class = "pl-field-hint", "Zuerst ein bestehendes Asset wählen."))
  if (!is.null(attr(timeline, "code")))
    return(portelyra_status_panel("Bewertung über die Zeit nicht lesbar", data_asset_valuation_timeline_error_copy_v1(attr(timeline, "code")), tone = "warning"))
  panels <- list()
  if (isTRUE(timeline$explicit)) {
    panels[[1L]] <- shiny::p(class = "pl-field-hint", sprintf("%s · eigene Zeitleiste, zuletzt geändert am %s.", .data_avt_text_v1(timeline$asset_name) %||% "–",
                                                                 pl_day_v1(timeline$updated_at_utc)))
    rows <- timeline$segments; last <- if (length(rows)) rows[[length(rows)]]$method else NULL
    if (!identical(last, timeline$valuation_method))
      panels[[2L]] <- portelyra_status_panel("Stammdaten und Zeitleiste weichen ab", sprintf(paste(
        "Heute gilt laut Zeitleiste „%s“, in den Stammdaten steht „%s“. Für die Bewertung zählt die Zeitleiste, neue Abrufe richten sich",
        "nach den Stammdaten. Angleichen mit „Ab Datum wechseln“."),
        data_asset_valuation_timeline_method_label_v1(last), data_asset_valuation_timeline_method_label_v1(timeline$valuation_method)), tone = "warning")
  } else {
    panels[[1L]] <- shiny::p(class = "pl-field-hint", sprintf("%s · keine eigene Zeitleiste: Es gilt die Bewertungsart aus den Stammdaten für die ganze Zeit.",
                                                                 .data_avt_text_v1(timeline$asset_name) %||% "–"))
  }
  shiny::tagList(panels)
}

data_asset_valuation_timeline_table_ui_v1 <- function(timeline) {
  if (!is.list(timeline) || !is.null(attr(timeline, "code"))) return(NULL)
  current <- data_asset_valuation_timeline_current_v1(timeline)
  rows <- if (is.list(timeline$segments)) timeline$segments else list()
  futures <- vapply(current$rows, function(row) identical(row$method, "external_market") && !is.null(row$provider_id) &&
                      isTRUE(pl_price_series_is_future_v1(row$provider_id, row$provider_symbol)), logical(1L))
  cells <- lapply(seq_along(rows), function(index) {
    row <- rows[[index]]; effective <- current$rows[[index]]
    recorded <- .data_avt_text_v1(row$recorded_symbol)
    series <- if (!identical(row$method, "external_market")) "–" else if (is.null(effective$provider_id)) "nicht eindeutig" else
      paste0(pl_price_provider_series_label_v1(effective$provider_id, effective$provider_symbol), " · ", effective$provider_symbol,
             if (isTRUE(current$derived)) " (aus der Zuordnung)" else "",
             if (!is.null(recorded) && !identical(recorded, effective$provider_symbol))
               sprintf(" (Symbol seit Anlage geändert: %s → %s)", recorded, effective$provider_symbol) else "")
    list(data_asset_valuation_timeline_period_text_v1(row), data_asset_valuation_timeline_method_label_v1(row$method), series,
         data_asset_valuation_timeline_coverage_text_v1(timeline, effective))
  })
  shiny::tagList(shiny::div(class = "pl-table-wrap", pl_table_v1(c("Zeitraum", "Bewertung", "Anbieter und Symbol", "Kurse vorhanden"), cells)),
                 pl_price_series_future_note_v1(futures))
}

data_asset_valuation_timeline_series_ui_v1 <- function(timeline) {
  if (!is.list(timeline) || !is.null(attr(timeline, "code"))) return(NULL)
  ready <- data_asset_valuation_timeline_ready_series_v1(timeline)
  if (!length(ready)) return(shiny::p(class = "pl-field-hint", paste("Für dieses Asset gibt es keine geprüfte, aktive Kursreihe. Sie wird bei der",
    "Bewertungsart Marktdaten eingerichtet: Zuordnung speichern, dann „2. Einrichten“.")))
  values <- vapply(ready, function(row) data_asset_valuation_timeline_series_value_v1(row$provider_id, row$provider_symbol), character(1L))
  labels <- vapply(ready, function(row) paste0(pl_price_provider_series_label_v1(row$provider_id, row$provider_symbol), " · ", row$provider_symbol), character(1L))
  current <- data_asset_valuation_timeline_current_v1(timeline)$rows
  last <- if (length(current)) current[[length(current)]] else NULL
  selected <- if (identical(last$method, "external_market") && !is.null(last$provider_id))
    data_asset_valuation_timeline_series_value_v1(last$provider_id, last$provider_symbol) else values[[1L]]
  shiny::selectInput("asset_valuation_timeline_series", "Kursreihe", stats::setNames(values, labels),
                     selected = if (selected %in% values) selected else values[[1L]], selectize = FALSE)
}

.data_avt_deviation_v1 <- function(before, after) {
  old <- suppressWarnings(as.numeric(before)); new <- suppressWarnings(as.numeric(after))
  if (length(old) != 1L || length(new) != 1L || is.na(old) || is.na(new) || old == 0) return("–")
  pl_percent_v1(sprintf("%.8f", (new - old) / old), digits = 2L)
}

# Vergleich an jedem Wechsel zwischen zwei Marktreihen: die letzten gemeinsamen Tage, Wert je Stueck in EUR.
data_asset_valuation_timeline_comparison_ui_v1 <- function(comparisons) {
  if (!length(comparisons)) return(NULL)
  shiny::tagList(lapply(comparisons, function(item) {
    title <- sprintf("Vergleich am Wechsel ab %s: %s → %s (Wert je Stück in EUR)", pl_day_v1(item$valid_from), .data_avt_text_v1(item$before) %||% "–",
                     .data_avt_text_v1(item$after) %||% "–")
    days <- if (is.list(item$days)) item$days else list()
    shiny::div(class = "pl-field-group", shiny::strong(title),
      if (!length(days)) shiny::p(class = "pl-field-hint", "Beide Reihen haben vor dem Wechsel keinen gemeinsamen bewerteten Tag; ein Vergleich ist nicht möglich.")
      else shiny::div(class = "pl-table-wrap", pl_table_v1(c("Tag", "bisher", "neu", "Abweichung in %"), lapply(days, function(day)
        list(pl_day_v1(day$day), pl_price_v1(day$before, "EUR"), pl_price_v1(day$after, "EUR"), .data_avt_deviation_v1(day$before, day$after))))))
  }))
}

# Was ein gewaehlter Anbieter nicht leistet (rc.394; bei EODHD: keine Splits), steht in der Vorschau, bevor uebernommen wird.
data_asset_valuation_timeline_provider_notes_ui_v1 <- function(segments) {
  if (!exists("pl_price_provider_note_v1", mode = "function")) return(NULL)
  providers <- unique(unlist(lapply(if (is.list(segments)) segments else list(), function(row)
    if (identical(row$method, "external_market") && is.character(row$provider_id)) row$provider_id else NULL)))
  notes <- Filter(Negate(is.null), lapply(providers, pl_price_provider_note_v1))
  if (!length(notes)) NULL else shiny::tagList(lapply(notes, function(note) portelyra_status_panel("Hinweis zum Kursanbieter", note, tone = "warning")))
}

data_asset_valuation_timeline_preview_ui_v1 <- function(result, confirm_id, apply_id) {
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: %s", .data_avt_text_v1(result$asset_name) %||% "–")),
    if (isTRUE(result$catalog_method_change)) portelyra_status_panel("Stammdaten werden mit umgestellt", sprintf(paste(
      "Bewertungsart der Stammdaten: %s → %s. „Übernehmen“ stellt zuerst die Stammdaten um und speichert danach die Zeitleiste."),
      data_asset_valuation_timeline_method_label_v1(result$catalog_method_before), data_asset_valuation_timeline_method_label_v1(result$catalog_method_after)), tone = "warning"),
    shiny::tags$ul(class = "pl-plain-list", lapply(unlist(result$notes), function(note) shiny::tags$li(note))),
    if (!is.null(.data_avt_text_v1(result$history_warning))) portelyra_status_panel("Historie des Anbieters", result$history_warning, tone = "warning"),
    data_asset_valuation_timeline_provider_notes_ui_v1(result$segments),
    data_asset_valuation_timeline_comparison_ui_v1(result$comparisons),
    shiny::checkboxInput(confirm_id, "Ich habe die Vorschau geprüft.", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton(apply_id, "Übernehmen", class = "btn-primary")))
}

.data_avt_feedback_ui_v1 <- function(value) if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) else NULL

# `asset`: reaktiv das gewaehlte, bestehende Asset als list(asset_id (intern), ref, display_name, valuation_method) oder NULL.
# `active`: gelesen wird erst, wenn die Karte sichtbar ist. `catalog_revise(method, ref)`: der Katalogbefehl "Bewertungsart aendern"
# fuer genau dieses Asset (Vorschau und Ausfuehrung). `on_changed()`: nach jedem Schreiben (Stammdaten neu lesen).
data_asset_valuation_timeline_server_v1 <- function(input, output, session, service, asset = shiny::reactive(NULL), active = shiny::reactive(TRUE),
    catalog_revise = NULL, on_changed = NULL, today = function() as.Date(format(Sys.time(), "%Y-%m-%d", tz = "UTC"))) {
  loaded <- shiny::reactiveVal(NULL)    # list(key, asset, value): die gelesene Zeitleiste und fuer welches Asset
  preview <- shiny::reactiveVal(NULL)   # list(kind = "change" | "clear", key, result)
  feedback <- shiny::reactiveVal(NULL)  # list(kind, tone, title, copy)
  own_choice <- new.env(parent = emptyenv()) # eigene Wahl (#579): method = Schluessel, from = Asset; method_preset = zuletzt vorbelegte Art
  failed <- function(error) structure(list(), code = if (is.character(error$code) && length(error$code) == 1L) error$code else "asset_valuation_timeline_store_invalid")
  readable <- function(value) is.list(value) && is.null(attr(value, "code"))
  key_of <- function(current) if (is.list(current) && !is.null(.data_avt_text_v1(current$asset_id)))
    paste(current$asset_id, .data_avt_text_v1(current$valuation_method) %||% "", sep = "|") else NULL
  read <- function(current) {
    value <- if (is.null(service)) structure(list(), code = "asset_valuation_timeline_store_invalid") else tryCatch(service$read(current$asset_id), error = failed)
    loaded(list(key = key_of(current), asset = current, value = value))
  }
  # Gelesen wird beim Oeffnen und bei jedem Wechsel des Assets oder seiner Bewertungsart; zugeklappt bleibt alles still.
  shiny::observe({
    if (!isTRUE(active())) return()
    current <- asset(); key <- key_of(current); previous <- shiny::isolate(loaded())
    if (is.null(key)) { if (!is.null(previous)) { loaded(NULL); preview(NULL); feedback(NULL) }; return() }
    if (is.list(previous) && identical(previous$key, key)) return()
    # Eine eigene Wahl gilt dem Asset, fuer das sie getroffen wurde (#579): Beim Wechsel verfaellt sie wie die Vorschau, und wer zurueckkehrt,
    # sieht wieder, was fuer dieses Asset gilt. Bleiben darf nur eine Wahl fuer das neue Asset selbst - getroffen, waehrend es noch lud.
    if (!identical(own_choice$method, key)) own_choice$method <- NULL
    if (!is.list(previous) || !identical(previous$asset$asset_id, current$asset_id)) {
      preview(NULL); feedback(NULL)
      # Ein neues Asset beginnt bei heute, ausser man hat fuer genau dieses schon einen Tag gewaehlt.
      own_day <- identical(own_choice$from, current$asset_id); if (!own_day) own_choice$from <- NULL
      shiny::updateDateInput(session, "asset_valuation_timeline_from", value = if (!own_day) today(), max = today())
    }
    read(current)
  })
  timeline <- shiny::reactive({ state <- loaded(); if (is.list(state)) state$value else NULL })
  # Fuer die eigenen Kursangaben (rc.393): auch anbieten, wenn die Zeitleiste einen Abschnitt "eigene Kurse" fuehrt.
  has_manual <- function(ref) {
    state <- loaded()
    is.list(state) && identical(state$asset$ref, ref) && readable(state$value) && isTRUE(state$value$explicit) &&
      any(vapply(state$value$segments, function(row) identical(row$method, "manual"), logical(1L)))
  }
  output$asset_valuation_timeline_state <- shiny::renderUI(data_asset_valuation_timeline_state_ui_v1(timeline()))
  output$asset_valuation_timeline_table <- shiny::renderUI(data_asset_valuation_timeline_table_ui_v1(timeline()))
  output$asset_valuation_timeline_series_choice <- shiny::renderUI(data_asset_valuation_timeline_series_ui_v1(timeline()))
  # Die Art des laufenden Abschnitts vorbelegen: Man sieht, was gilt, und aendert nur, was sich aendern soll.
  # Eine eigene Wahl geht vor (#579): Die Zeitleiste wird erst gelesen, wenn die Karte offen ist; auf einem langsamen Rechner hat man dann
  # womoeglich schon gewaehlt. Gemerkt wird, fuer welches Asset man Art bzw. Tag selbst gesetzt hat; ein Echo der eigenen Vorbelegung zaehlt
  # nicht (die Merker laufen vor der Vorbelegung, Prioritaet). Im Browser setzt die Vorbelegung nur, wenn das Feld noch auf dem Wert steht,
  # den der Server kannte - eine Wahl kann gerade unterwegs sein (pl_set_if_unchanged, Handler im Asset-Center).
  shiny::observeEvent(input$asset_valuation_timeline_method, {
    if (!identical(input$asset_valuation_timeline_method, own_choice$method_preset)) own_choice$method <- key_of(shiny::isolate(asset()))
  }, ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(input$asset_valuation_timeline_from, {
    day <- if (length(input$asset_valuation_timeline_from) == 1L) as.character(input$asset_valuation_timeline_from) else NA_character_
    if (!identical(day, format(today(), "%Y-%m-%d"))) own_choice$from <- .data_avt_text_v1(shiny::isolate(asset())$asset_id)
  }, ignoreInit = TRUE, priority = 10)
  shiny::observeEvent(timeline(), {
    value <- timeline(); if (!readable(value)) return()
    rows <- value$segments; last <- if (length(rows)) rows[[length(rows)]]$method else NULL
    if (!is.character(last) || !last %in% names(DATA_ASSET_VALUATION_TIMELINE_METHODS_V1)) return()
    if (identical(own_choice$method, shiny::isolate(loaded())$key)) return()
    current <- shiny::isolate(input$asset_valuation_timeline_method)
    own_choice$method_preset <- last
    if (!identical(current, last)) session$sendCustomMessage("pl_set_if_unchanged",
      list(id = "asset_valuation_timeline_method", value = last, expected = if (is.character(current) && length(current) == 1L) current else ""))
  })
  change_key <- shiny::reactive({
    state <- loaded()
    list(asset = if (is.list(state)) state$key else NULL, whole = isTRUE(input$asset_valuation_timeline_whole),
         day = if (length(input$asset_valuation_timeline_from) == 1L) as.character(input$asset_valuation_timeline_from) else NA_character_,
         method = input$asset_valuation_timeline_method, series = input$asset_valuation_timeline_series)
  })
  # Die Vorschau gilt nur fuer genau die Angaben, mit denen sie erstellt wurde.
  shiny::observeEvent(change_key(), {
    current <- shiny::isolate(preview())
    if (is.list(current) && identical(current$kind, "change") && !identical(current$key, change_key())) preview(NULL)
    if (is.list(current) && identical(current$kind, "clear") && !identical(current$key$asset, change_key()$asset)) preview(NULL)
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$asset_valuation_timeline_preview, {
    preview(NULL); feedback(NULL)
    state <- loaded(); value <- if (is.list(state)) state$value else NULL
    if (!readable(value)) return(feedback(list(kind = "change", tone = "warning", title = "Keine Vorschau",
      copy = if (is.list(state)) data_asset_valuation_timeline_error_copy_v1(attr(value, "code")) else "Zuerst ein bestehendes Asset wählen.")))
    key <- change_key()
    plan <- data_asset_valuation_timeline_plan_v1(value, key$whole, key$day, key$method, key$series, format(today(), "%Y-%m-%d"))
    if (!is.null(plan$problem)) return(feedback(list(kind = "change", tone = "warning", title = "Keine Vorschau", copy = plan$problem)))
    if (isTRUE(plan$unchanged)) return(feedback(list(kind = "change", tone = "neutral", title = "Nichts zu ändern",
      copy = "Die Angaben entsprechen der geltenden Bewertung über die Zeit.")))
    result <- tryCatch(service$preview(state$asset$asset_id, plan$segments), error = failed)
    if (!readable(result)) return(feedback(list(kind = "change", tone = "warning", title = "Keine Vorschau",
      copy = data_asset_valuation_timeline_error_copy_v1(attr(result, "code")))))
    if (!is.null(plan$warning)) result$history_warning <- plan$warning
    preview(list(kind = "change", key = key, result = result))
  })
  output$asset_valuation_timeline_clear_body <- shiny::renderUI({
    value <- timeline(); if (!readable(value)) return(NULL)
    if (!isTRUE(value$explicit)) return(shiny::p(class = "pl-field-hint",
      "Für dieses Asset ist keine eigene Zeitleiste eingetragen; es gilt die Bewertungsart aus den Stammdaten."))
    shiny::tagList(
      shiny::p(class = "pl-field-hint", sprintf(paste("Danach gilt wieder die eine Bewertungsart aus den Stammdaten („%s“) für die ganze Zeit.",
        "Die bisherigen Fassungen der Zeitleiste bleiben gespeichert."), data_asset_valuation_timeline_method_label_v1(value$valuation_method))),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("asset_valuation_timeline_clear_preview", "Vorschau", class = "btn-default")))
  })
  shiny::observeEvent(input$asset_valuation_timeline_clear_preview, {
    preview(NULL); feedback(NULL)
    state <- loaded(); value <- if (is.list(state)) state$value else NULL
    if (!readable(value) || !isTRUE(value$explicit)) return()
    result <- tryCatch(service$preview(state$asset$asset_id, list()), error = failed)
    if (!readable(result)) return(feedback(list(kind = "clear", tone = "warning", title = "Keine Vorschau",
      copy = data_asset_valuation_timeline_error_copy_v1(attr(result, "code")))))
    preview(list(kind = "clear", key = list(asset = state$key), result = result))
  })
  panel <- function(kind, confirm_id, apply_id) shiny::renderUI({
    current <- preview(); note <- feedback()
    shiny::tagList(
      if (is.list(current) && identical(current$kind, kind)) data_asset_valuation_timeline_preview_ui_v1(current$result, confirm_id, apply_id),
      if (is.list(note) && identical(note$kind, kind)) .data_avt_feedback_ui_v1(note))
  })
  output$asset_valuation_timeline_preview_panel <- panel("change", "asset_valuation_timeline_confirm", "asset_valuation_timeline_apply")
  output$asset_valuation_timeline_clear_panel <- panel("clear", "asset_valuation_timeline_clear_confirm", "asset_valuation_timeline_clear_apply")
  changed <- function() {
    if (is.function(on_changed)) tryCatch(on_changed(), error = function(error) NULL)
    fresh <- shiny::isolate(asset())
    if (!is.null(key_of(fresh))) read(fresh)
  }
  apply_preview <- function(kind, confirmed) {
    current <- preview(); state <- loaded()
    if (!is.list(current) || !identical(current$kind, kind) || !is.list(state)) return()
    result <- current$result
    if (!isTRUE(confirmed)) return(feedback(list(kind = kind, tone = "warning", title = "Nicht gespeichert",
      copy = data_asset_valuation_timeline_error_copy_v1("asset_valuation_timeline_confirmation_required"))))
    after <- data_asset_valuation_timeline_method_label_v1(result$catalog_method_after)
    revised <- FALSE
    # Erst die Stammdaten, dann die Zeitleiste: apply prueft, dass die heutige Art zum letzten Abschnitt passt.
    if (isTRUE(result$catalog_method_change)) {
      outcome <- if (!is.function(catalog_revise)) structure(list(), code = "desktop_catalog_boundary_failed") else
        tryCatch({ catalog_revise(result$catalog_method_after, state$asset$ref); TRUE }, error = function(error)
          structure(list(), code = if (is.character(error$code) && length(error$code) == 1L) error$code else "desktop_catalog_boundary_failed"))
      if (!isTRUE(outcome)) {
        preview(NULL)
        return(feedback(list(kind = kind, tone = "error", title = "Nicht gespeichert", copy = sprintf(paste(
          "Die Bewertungsart der Stammdaten ließ sich nicht auf „%s“ umstellen; die Zeitleiste ist deshalb unverändert. %s"),
          after, data_asset_valuation_timeline_catalog_copy_v1(attr(outcome, "code"))))))
      }
      revised <- TRUE
    }
    applied <- if (is.null(service)) structure(list(), code = "asset_valuation_timeline_store_invalid") else tryCatch(service$apply(result, TRUE), error = failed)
    preview(NULL)
    if (!readable(applied)) {
      if (revised) {
        changed()
        return(feedback(list(kind = kind, tone = "error", title = "Nur die Stammdaten umgestellt", copy = sprintf(paste(
          "Die Bewertungsart der Stammdaten ist jetzt „%s“, die Zeitleiste wurde aber nicht gespeichert: %s",
          "Bitte die Vorschau neu erstellen und erneut übernehmen; die Stammdaten müssen dann nicht mehr umgestellt werden."),
          after, data_asset_valuation_timeline_error_copy_v1(attr(applied, "code"))))))
      }
      return(feedback(list(kind = kind, tone = "error", title = "Nicht gespeichert", copy = data_asset_valuation_timeline_error_copy_v1(attr(applied, "code")))))
    }
    changed()
    title <- if (identical(kind, "clear")) "Zeitleiste aufgehoben" else "Zeitleiste gespeichert"
    feedback(list(kind = kind, tone = "positive", title = title, copy = paste0(
      if (revised) sprintf("Die Bewertungsart der Stammdaten ist jetzt „%s“. ", after) else "",
      "Snapshot, Tageshistorie und Steuer-Tageswerte lesen die neue Fassung; die Tageshistorie rechnet beim nächsten Fortschreiben ab dem ",
      "ersten geänderten Tag neu. Versiegelte Snapshots bleiben, wie sie sind.")))
  }
  shiny::observeEvent(input$asset_valuation_timeline_apply, apply_preview("change", input$asset_valuation_timeline_confirm))
  shiny::observeEvent(input$asset_valuation_timeline_clear_apply, apply_preview("clear", input$asset_valuation_timeline_clear_confirm))
  invisible(list(timeline = timeline, has_manual = has_manual, read = function() { current <- shiny::isolate(asset()); if (!is.null(key_of(current))) read(current) }))
}
