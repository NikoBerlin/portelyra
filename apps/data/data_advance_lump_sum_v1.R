# Vorabpauschale je Fonds, Konto und Jahr - als Buchung mit dem Betrag der Bank (#431), in Data -> "4. Steuer".
#
# Die Karte geht nach Steuerjahr, dem Jahr des Zuflusses.
# Eingetragen wird im Januar 2026 die Vorabpauschale, die fuer 2025 berechnet ist und am 2.1.2026 zufliesst. Der
# Speicher fuehrt weiter das Jahr der Berechnung; die Karte rechnet um (Steuerjahr - 1).
#
# Festlegung (13.10.2026): je Fonds und Konto als eigene Buchung mit dem Betrag der Bank; sie laeuft an den Lots mit und
# mindert den Gewinn beim Verkauf. Die Karte listet je Jahr die Fonds mit Bestand zum 31.12. und nimmt den Betrag der
# Bank auf; was er steuerlich bewirkt, rechnen Report, Rechenblatt, Jahresrechnung und Abschluss. Die Buchung liegt neben
# dem Buchungsbestand (advance-lump-sum-v1). Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_advance_lump_sum_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^advance_lump_sum_[a-z_]+$", code)) code <- "advance_lump_sum_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_advance_lump_sum_error_v1", "error", "condition")))
}
data_advance_lump_sum_error_text_v1 <- function(code) switch(as.character(code),
  advance_lump_sum_input_invalid = , advance_lump_sum_overview_input_invalid = "Ein Betrag ist nicht gültig: nicht negativ, höchstens zwei Nachkommastellen.",
  advance_lump_sum_not_a_fund = "Eine Vorabpauschale gibt es nur bei Fonds.",
  "Buchungsbestand, FIFO-Stand oder der Speicher der Vorabpauschalen ließen sich nicht lesen. Konten und Buchungen sind davon nicht berührt.")
new_data_advance_lump_sum_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_advance_lump_sum.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_advance_lump_sum_abort_v1("advance_lump_sum_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_advance_lump_sum_abort_v1(if (is.null(parsed$code)) "advance_lump_sum_store_invalid" else parsed$code)
    parsed$result
  }
  year_valid <- function(year) { value <- suppressWarnings(as.integer(year)); length(value) == 1L && !is.na(value) && value >= 2018L && value <= 2100L }
  structure(list(
    contract_version = "data_advance_lump_sum_service_v1",
    overview = function(calculation_year) {
      if (!year_valid(calculation_year)) data_advance_lump_sum_abort_v1("advance_lump_sum_input_invalid")
      result <- run("overview", list(calculation_year = as.integer(calculation_year)))
      if (!is.list(result) || !identical(result$contract_version, "advance_lump_sum_overview_v1") || !is.list(result$rows) || isTRUE(result$canonical_write) ||
          !all(vapply(result$rows, function(row) is.character(row$token) && grepl("^vpf_[a-f0-9]{24}$", row$token), logical(1L))))
        data_advance_lump_sum_abort_v1("advance_lump_sum_store_invalid")
      result
    },
    # Je Berechnungsjahr: Fonds am 31.12. und wie viele ohne Angabe sind (#472).
    gaps = function(last_calculation_year) {
      if (!year_valid(last_calculation_year)) data_advance_lump_sum_abort_v1("advance_lump_sum_input_invalid")
      result <- run("gaps", list(last_calculation_year = as.integer(last_calculation_year)))
      if (!is.list(result) || !identical(result$contract_version, "advance_lump_sum_gaps_v1") || !is.list(result$years) || isTRUE(result$canonical_write))
        data_advance_lump_sum_abort_v1("advance_lump_sum_store_invalid")
      result
    },
    # `entries`: Liste aus list(token, amount_decimal); amount_decimal NULL leert die Buchung.
    record = function(calculation_year, entries, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_advance_lump_sum_abort_v1("advance_lump_sum_confirmation_required")
      if (!year_valid(calculation_year) || !is.list(entries) || !length(entries)) data_advance_lump_sum_abort_v1("advance_lump_sum_input_invalid")
      result <- run("record", list(calculation_year = as.integer(calculation_year), entries = unname(entries), recorded_at_utc = recorded_at_utc, confirmed = TRUE))
      if (!is.list(result) || !identical(result$status, "recorded") || isTRUE(result$canonical_write)) data_advance_lump_sum_abort_v1("advance_lump_sum_store_invalid")
      result
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_advance_lump_sum_service_v1", "list"))
}
# Die Steuerjahre der Karte: Zufluss ab 2019 (berechnet ab 2018) bis zum laufenden Jahr.
data_advance_lump_sum_tax_years_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) rev(seq.int(2019L, max(2019L, as.integer(current_year))))
# Woher die Werte kommen. Haengt an den Lesern des
# Wertpapier-Imports: Belege mit Betrag (ING, Scalable) uebernimmt er, Trade Republic prueft er nur.
DATA_ADVANCE_LUMP_SUM_SOURCES_V1 <- c(
  automatic = "Automatisch aus dem Beleg – ING und Scalable Capital: Der Wertpapier-Import liest die Vorabpauschale und trägt fehlende nach der Bestätigung ein; einen abweichenden Wert ersetzt er nur mit Häkchen.",
  checked = "Nur geprüft – Trade Republic: Der Export nennt nur die einbehaltene Steuer; der Import warnt, wenn der Wert hier nicht dazu passt. Den Betrag hier eintragen.",
  manual = "Von Hand – alle anderen Institute: hier eintragen.")
data_advance_lump_sum_card_ui_v1 <- function(current_year = as.integer(format(Sys.Date(), "%Y"))) {
  years <- data_advance_lump_sum_tax_years_v1(current_year)
  portelyra_card("Vorabpauschalen je Fonds und Konto", help = "app-data#steuer", class = "pl-write-boundary",
    copy = "Je Fonds und Konto die Vorabpauschale aus der Abrechnung der Bank – der Betrag vor Teilfreistellung; die Teilfreistellung rechnet Portelyra selbst.",
    note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-advance-lump-sum", paste(
      "Sie ist für das Vorjahr berechnet, gilt am ersten Werktag des Steuerjahres als zugeflossen und mindert beim späteren Verkauf den Gewinn (§§ 18, 19 InvStG).")),
    shiny::tags$ul(class = "pl-field-hint", lapply(unname(DATA_ADVANCE_LUMP_SUM_SOURCES_V1), shiny::tags$li)),
    shiny::div(class = "pl-field-row",
      shiny::selectInput("data_advance_lump_sum_year", "Steuerjahr (Zufluss)", choices = as.character(years), selected = as.character(years[[1L]]), width = "180px")),
    shiny::uiOutput("data_advance_lump_sum_gaps"),
    shiny::uiOutput("data_advance_lump_sum_form"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_advance_lump_sum_save", "Vorabpauschalen speichern", class = "btn-primary")),
    shiny::uiOutput("data_advance_lump_sum_notice"),
    shiny::p(class = "pl-field-hint", paste(
      "Auf der Abrechnung der Bank steht oft das Vorjahr: „Vorabpauschale 2025“ zum Beispiel fließt am 2.1.2026 zu und wird im Steuerjahr 2026 eingetragen.",
      "Die Liste zeigt die Fonds mit Bestand am 31.12. des Vorjahres; der Betrag verteilt sich auf deren Lots, im Erwerbsjahr um ein Zwölftel je vollem Monat vor dem Kauf gekürzt.",
      "Leer heißt: noch keine Angabe – hat die Bank keine Vorabpauschale berechnet (etwa bei negativem Basiszins), 0 eintragen. Gespeichert wird nur, was geändert ist.")))
}
# Wo fehlt eine Angabe (#472)? Je Steuerjahr die Fonds mit Bestand am 31.12. des Vorjahres ohne Betrag und ohne 0.
data_advance_lump_sum_gaps_v1 <- function(gaps) {
  if (!is.list(gaps) || !identical(gaps$status, "ready")) return(NULL)
  open <- Filter(function(row) as.integer(row$missing_count) > 0L, gaps$years)
  if (!length(open)) return(portelyra_status_panel("Für jedes Steuerjahr ist eine Angabe da",
    "Für alle Fonds, die an einem 31.12. im Bestand lagen, ist eine Vorabpauschale oder 0 eingetragen.", tone = "positive"))
  parts <- vapply(rev(open), function(row) sprintf("%d: %d von %d", as.integer(row$tax_year), as.integer(row$missing_count), as.integer(row$held_count)), character(1L))
  portelyra_status_panel(sprintf("Vorabpauschale fehlt in %d Steuerjahr(en)", length(open)),
    paste0("Fonds je Konto mit Bestand am 31.12. des Vorjahres, aber ohne eingetragenen Betrag (Steuerjahr: fehlend von gehalten) – ", paste(parts, collapse = " · "),
           ". Betrag laut Bank eintragen; hat die Bank keine berechnet, 0."), tone = "warning")
}
data_advance_lump_sum_number_v1 <- function(text) if (is.null(text)) "–" else gsub(".", ",", as.character(text), fixed = TRUE)
data_advance_lump_sum_form_v1 <- function(model) {
  if (!is.list(model)) return(shiny::p(class = "pl-field-hint", "Zuerst oben „Einstellungen lesen“ drücken."))
  if (!identical(model$status, "ready")) return(portelyra_status_panel(if (identical(model$status, "fifo_state_stale")) "FIFO-Stand nicht aktuell" else "Kein FIFO-Stand vorhanden",
    "Welche Fonds am 31.12. im Bestand lagen, sagt der Lot-Nachweis des Buchungsbestands. Bitte den Bestand fortschreiben und danach neu öffnen.", tone = "warning"))
  rows <- model$rows
  year <- as.integer(model$calculation_year)
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", sprintf("Am 31.12.%d lag kein Fonds im Bestand – für das Steuerjahr %d gibt es keine Vorabpauschale.", year, year + 1L)))
  shiny::tagList(
    shiny::p(class = "pl-field-hint", sprintf("Steuerjahr %d · berechnet für %d aus dem Bestand zum 31.12.%d · Zufluss %s · %d Fonds je Konto",
      year + 1L, year, year, format(as.Date(model$inflow_date), "%d.%m.%Y"), length(rows))),
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Fonds", "Konto", sprintf("Stück am 31.12.%d", year), "Vorabpauschale vor Teilfreistellung in €"), shiny::tags$th))),
      shiny::tags$tbody(lapply(seq_along(rows), function(index) {
        row <- rows[[index]]
        value <- suppressWarnings(as.numeric(row$amount_decimal)); if (length(value) != 1L) value <- NA_real_
        shiny::tags$tr(shiny::tags$td(shiny::tags$strong(row$fund_label)),
          shiny::tags$td(paste0(row$account_label, if (is.null(row$institution_label)) "" else paste0(" (", row$institution_label, ")"))),
          shiny::tags$td(data_advance_lump_sum_number_v1(row$quantity_decimal)),
          shiny::tags$td(shiny::numericInput(sprintf("data_advance_lump_sum_amount_%d", index), NULL, value = value, min = 0, step = 0.01, width = "150px")))
      })))))
}
data_advance_lump_sum_plan_v1 <- function(model, values) {
  entries <- list()
  for (index in seq_along(model$rows)) {
    row <- model$rows[[index]]
    entered <- values(index)
    entered <- if (is.null(entered) || length(entered) != 1L || !is.numeric(entered) || is.na(entered)) NA_real_ else as.numeric(entered)
    if (!is.na(entered) && entered < 0) return(list(error = sprintf("%s · %s: Der Betrag darf nicht negativ sein.", row$fund_label, row$account_label)))
    if (!is.na(entered) && abs(entered * 100 - round(entered * 100)) > 1e-6) return(list(error = sprintf("%s · %s: höchstens zwei Nachkommastellen.", row$fund_label, row$account_label)))
    before <- suppressWarnings(as.numeric(row$amount_decimal)); if (length(before) != 1L) before <- NA_real_
    if ((is.na(entered) && is.na(before)) || (!is.na(entered) && !is.na(before) && abs(entered - before) < 0.005)) next
    entries[[length(entries) + 1L]] <- list(token = row$token, amount_decimal = if (is.na(entered)) NULL else formatC(round(entered, 2), format = "f", digits = 2))
  }
  list(entries = entries)
}
data_advance_lump_sum_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  model <- shiny::reactiveVal(NULL); failure <- shiny::reactiveVal(NULL); notice <- shiny::reactiveVal(NULL); active <- shiny::reactiveVal(FALSE)
  gaps <- shiny::reactiveVal(NULL)
  read_gaps <- function(today = Sys.Date()) {
    if (is.null(service) || !is.function(service$gaps)) return(invisible(NULL))
    gaps(tryCatch(service$gaps(as.integer(format(today, "%Y")) - 1L), error = function(error) NULL))
    invisible(NULL)
  }
  read <- function() {
    active(TRUE)
    if (is.null(service)) { failure("advance_lump_sum_store_invalid"); return(invisible(NULL)) }
    if (is.null(shiny::isolate(gaps()))) read_gaps()
    # Die Karte waehlt das Steuerjahr; gerechnet und gespeichert wird mit dem Jahr der Berechnung davor.
    tax_year <- suppressWarnings(as.integer(shiny::isolate(input$data_advance_lump_sum_year)))
    value <- tryCatch(service$overview(tax_year - 1L), error = function(error) structure(list(), code = if (is.null(error$code)) "advance_lump_sum_store_invalid" else error$code))
    if (!is.null(attr(value, "code"))) { failure(attr(value, "code")); model(NULL) } else { failure(NULL); model(value) }
    invisible(NULL)
  }
  shiny::observeEvent(input$data_advance_lump_sum_year, { notice(NULL); if (isTRUE(active())) read() }, ignoreInit = TRUE)
  output$data_advance_lump_sum_form <- shiny::renderUI({
    if (!is.null(failure())) return(portelyra_status_panel("Vorabpauschalen nicht lesbar", data_advance_lump_sum_error_text_v1(failure()), tone = "warning"))
    data_advance_lump_sum_form_v1(model())
  })
  output$data_advance_lump_sum_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  output$data_advance_lump_sum_gaps <- shiny::renderUI(data_advance_lump_sum_gaps_v1(gaps()))
  shiny::observeEvent(input$data_advance_lump_sum_save, {
    current <- shiny::isolate(model())
    if (!is.list(current) || !identical(current$status, "ready")) { notice(list(tone = "warning", title = "Noch nichts gelesen", copy = "Zuerst oben „Einstellungen lesen“ drücken.")); return() }
    plan <- data_advance_lump_sum_plan_v1(current, function(index) input[[sprintf("data_advance_lump_sum_amount_%d", index)]])
    if (!is.null(plan$error)) { notice(list(tone = "error", title = "Nicht gespeichert", copy = plan$error)); return() }
    if (!length(plan$entries)) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Die Beträge stimmen mit dem gespeicherten Stand überein.")); return() }
    result <- tryCatch(service$record(current$calculation_year, plan$entries, now_utc(), TRUE), error = function(error) structure(list(), code = if (is.null(error$code)) "advance_lump_sum_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_advance_lump_sum_error_text_v1(attr(result, "code")))); return() }
    read(); read_gaps()
    notice(list(tone = "positive", title = sprintf("%d Vorabpauschale(n) für das Steuerjahr %d gespeichert", as.integer(result$written_count), as.integer(current$calculation_year) + 1L),
      copy = sprintf("Zufluss am %s. Report, Rechenblätter, Jahresrechnung und der nächste Portfolioabschluss rechnen damit.", format(as.Date(current$inflow_date), "%d.%m.%Y"))))
  })
  invisible(list(read = read, model = model))
}
