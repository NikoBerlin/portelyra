# Aktiensplit (#451, rc.370) - in "2. Stammdaten", bei Portfolio und Assets.
#
# Ein Split ist ein eigenes Ereignis. Er ist keine Veraeusserung:
# Am Stichtag (Ex-Tag) wird jedes offene Lot im Verhaeltnis neu : alt geteilt, Einstand und Anschaffungsdatum bleiben. Buchungen
# davor stehen in alten Stuecken wie im Beleg, Buchungen ab dem Stichtag in neuen. Ein Spitzenausgleich in Geld ist ein Verkauf
# des Bruchteils und wird als solcher gebucht. Die Karte bietet nur Splits fuer alle Konten an: Ein Split auf einem Konto allein
# hiesse zwei Stueckelungen eines Assets zugleich, fuer die es keinen gemeinsamen Kurs gibt.
# Vorschau zeigt den Bestand vor und nach dem Split; gespeichert wird nur genau die gezeigte Vorschau. Danach schreibt die App den
# FIFO-Stand fort und veroeffentlicht die Tageshistorie neu. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
data_stock_split_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^stock_split_[a-z_]+$", code)) code <- "stock_split_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_stock_split_error_v1", "error", "condition")))
}
data_stock_split_error_text_v1 <- function(code) switch(as.character(code),
  stock_split_asset_unknown = "Das Asset steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  stock_split_account_unknown = "Das Konto steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  stock_split_entry_unknown = "Für dieses Asset und diesen Tag ist kein Split gespeichert, der sich zurücknehmen ließe.",
  stock_split_input_invalid = "Bitte Asset, Stichtag und das Verhältnis neu : alt als ganze Zahlen angeben (nicht 1 : 1).",
  stock_split_confirmation_required = "Bitte zuerst die Vorschau rechnen.",
  "Der Speicher der Splits ließ sich nicht lesen oder schreiben. Stammdaten und Buchungen sind davon nicht berührt.")
data_stock_split_reason_text_v1 <- function(reason) switch(as.character(reason),
  split_inexact = "Mit diesem Verhältnis ergäbe sich keine endliche Stückzahl (etwa 10 Stück bei 1 : 3). Bitte das Verhältnis prüfen; ein Spitzenausgleich wird als Verkauf gebucht.",
  inventory_insufficient = "Mit diesem Split wäre eine spätere Buchung nicht mehr gedeckt. Bitte Stichtag und Verhältnis prüfen.",
  "Der Split passt nicht zu den Buchungen dieses Assets.")
# Darstellung wie in allen Apps (rc.349): Tag und Menge ueber die Formatierer der Huelle; Mengen exakt aus dem Dezimaltext.
data_stock_split_day_v1 <- function(day) pl_day_v1(day)
data_stock_split_quantity_v1 <- function(text) pl_quantity_v1(text)

new_data_stock_split_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_stock_split.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else NULL
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_stock_split_abort_v1("stock_split_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_stock_split_abort_v1(if (is.null(parsed$code)) "stock_split_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "stock_split_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_stock_split_abort_v1("stock_split_store_invalid")
    result
  }
  entry <- function(asset_id, effective_local_date, ratio_numerator, ratio_denominator) {
    day_ok <- is.character(effective_local_date) && length(effective_local_date) == 1L && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", effective_local_date)
    ratio_ok <- function(value) is.character(value) && length(value) == 1L && grepl("^[1-9][0-9]{0,11}$", value)
    if (!is.character(asset_id) || length(asset_id) != 1L || !grepl("^ast_[a-z0-9_]{4,60}$", asset_id) || !day_ok ||
        !(is.null(ratio_numerator) || ratio_ok(ratio_numerator)) || !(is.null(ratio_denominator) || ratio_ok(ratio_denominator)))
      data_stock_split_abort_v1("stock_split_input_invalid")
    list(asset_id = asset_id, account_id = NULL, effective_local_date = effective_local_date, ratio_numerator = ratio_numerator,
         ratio_denominator = ratio_denominator)
  }
  stamp_ok <- function(value) is.character(value) && length(value) == 1L && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  structure(list(
    contract_version = "data_stock_split_service_v1",
    read = function() checked(run("read", list()), "ready"),
    preview = function(asset_id, effective_local_date, ratio_numerator, ratio_denominator, remove = FALSE)
      checked(run("preview", c(entry(asset_id, effective_local_date, ratio_numerator, ratio_denominator), list(remove = isTRUE(remove)))),
              c("previewed", "blocked")),
    record = function(asset_id, effective_local_date, ratio_numerator, ratio_denominator, note, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_stock_split_abort_v1("stock_split_confirmation_required")
      if (!stamp_ok(recorded_at_utc) || is.null(ratio_numerator) || is.null(ratio_denominator)) data_stock_split_abort_v1("stock_split_input_invalid")
      checked(run("record", c(entry(asset_id, effective_local_date, ratio_numerator, ratio_denominator),
                              list(note = if (is.character(note) && nzchar(trimws(note))) trimws(note) else NULL, recorded_at_utc = recorded_at_utc, confirmed = TRUE))),
              c("recorded", "unchanged"))
    },
    remove = function(asset_id, effective_local_date, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_stock_split_abort_v1("stock_split_confirmation_required")
      if (!stamp_ok(recorded_at_utc)) data_stock_split_abort_v1("stock_split_input_invalid")
      value <- entry(asset_id, effective_local_date, NULL, NULL)
      checked(run("remove", list(asset_id = value$asset_id, account_id = NULL, effective_local_date = value$effective_local_date,
                                 recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "removed")
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_stock_split_service_v1", "list"))
}

data_stock_split_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "stock_split_details",
    shiny::tags$summary("Kapitalmaßnahme · Aktiensplit"),
    shiny::p(class = "pl-section-copy", "Ein Split teilt jedes offene Lot am Stichtag im Verhältnis neu : alt. Einstand und Anschaffungsdatum bleiben, es entsteht kein Gewinn."),
    portelyra_note_v1(title = "So wirkt ein Split", id = "data-stock-split",
      paste("Buchungen vor dem Stichtag stehen in alten Stücken wie im Beleg, Buchungen ab dem Stichtag in neuen. Ein Split 3 : 1 macht aus 10 Stück 30,",
            "eine Zusammenlegung 1 : 10 aus 100 Stück 10. Der Einstand je Stück teilt sich, der Einstand gesamt bleibt."),
      paste("Stichtag ist der Ex-Tag: der erste Handelstag in neuen Stücken. Ein Spitzenausgleich in Geld für Bruchstücke ist ein Verkauf des Bruchteils",
            "und wird als Verkauf gebucht. Der Split gilt für alle Konten des Assets. Kurse der Anbieter vor dem Stichtag rechnet die Bewertung",
            "auf die damaligen Stücke um, wenn sie nach dem Split abgerufen wurden.")),
    shiny::uiOutput("stock_split_table"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("stock_split_asset", "Asset", c("Asset wählen" = ""), selectize = TRUE),
      shiny::dateInput("stock_split_date", "Stichtag (Ex-Tag)", value = NULL, format = "dd.mm.yyyy", language = "de", weekstart = 1),
      shiny::numericInput("stock_split_new", "neue Stücke", value = NA, min = 1, step = 1),
      shiny::numericInput("stock_split_old", "für alte Stücke", value = NA, min = 1, step = 1),
      shiny::textInput("stock_split_note", "Notiz (optional)", "", placeholder = "z. B. Mitteilung der Bank vom …")),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("stock_split_preview", "Vorschau", class = "btn-default"),
      shiny::actionButton("stock_split_save", "Split speichern", class = "btn-primary"),
      shiny::actionButton("stock_split_remove_preview", "Vorschau: Split zurücknehmen", class = "btn-default")),
    shiny::uiOutput("stock_split_preview_block"),
    shiny::uiOutput("stock_split_notice"))
}

data_stock_split_asset_choices_v1 <- function(model) {
  assets <- if (is.list(model)) model$assets else list()
  c(stats::setNames("", "Asset wählen"),
    stats::setNames(vapply(assets, function(row) row$asset_id, character(1L)), vapply(assets, function(row) row$label, character(1L))))
}

data_stock_split_table_v1 <- function(model) {
  entries <- if (is.list(model)) model$entries else list()
  if (!length(entries)) return(shiny::p(class = "pl-field-hint", "Noch kein Split gespeichert."))
  rows <- lapply(entries, function(row) shiny::tags$tr(
    shiny::tags$td(row$asset_label %||% "–"), shiny::tags$td(data_stock_split_day_v1(row$effective_local_date)),
    shiny::tags$td(paste(row$ratio_numerator, ":", row$ratio_denominator)), shiny::tags$td(row$note %||% "")))
  shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
    shiny::tags$thead(shiny::tags$tr(lapply(c("Asset", "Stichtag", "neu : alt", "Notiz"), shiny::tags$th))), shiny::tags$tbody(rows)))
}

data_stock_split_preview_ui_v1 <- function(preview, remove = FALSE) {
  if (identical(preview$status, "blocked"))
    return(portelyra_status_panel("Dieser Split lässt sich nicht speichern", data_stock_split_reason_text_v1(preview$reason), tone = "warning"))
  worlds <- if (is.list(preview$worlds)) preview$worlds else list()
  if (!length(worlds)) return(shiny::p(class = "pl-field-hint", "Für dieses Asset gibt es keine Buchungen; der Split wirkt erst auf künftige."))
  rows <- lapply(worlds, function(row) shiny::tags$tr(
    shiny::tags$td(data_stock_split_quantity_v1(row$quantity_before_split)), shiny::tags$td(data_stock_split_quantity_v1(row$quantity_after_split)),
    shiny::tags$td(data_stock_split_quantity_v1(row$quantity_now)), shiny::tags$td(data_stock_split_quantity_v1(row$quantity_after))))
  shiny::div(class = "pl-preview",
    shiny::p(shiny::tags$strong(if (isTRUE(remove)) "Ohne diesen Split rechnet der FIFO-Stand so:" else "Mit diesem Split rechnet der FIFO-Stand so:")),
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Bestand vor dem Split", "am Stichtag danach", "Bestand heute bisher", "Bestand heute danach"), shiny::tags$th))),
      shiny::tags$tbody(rows))),
    shiny::p(class = "pl-field-hint", "Einstand und Anschaffungsdaten bleiben. Gewinne aus späteren Verkäufen ändern sich nur, wenn bisher in alten Stücken gebucht war."))
}

# `after_write`: schreibt nach dem Speichern den FIFO-Stand fort und veroeffentlicht die Tageshistorie (gibt Status oder NULL).
data_stock_split_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    after_write = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$stock_split_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "stock_split_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "stock_split_store_invalid" else error$code))
  })
  readable <- function(current) is.list(current) && is.null(attr(current, "code"))
  shiny::observeEvent(model(), {
    current <- model(); if (!readable(current)) return()
    shiny::updateSelectizeInput(session, "stock_split_asset", choices = data_stock_split_asset_choices_v1(current), selected = shiny::isolate(input$stock_split_asset))
  }, ignoreNULL = TRUE)
  ratio_text <- function(value) {
    number <- suppressWarnings(as.numeric(value))
    if (length(number) != 1L || is.na(number) || number < 1 || number != round(number) || number > 999999999999) NULL else format(number, scientific = FALSE)
  }
  key <- shiny::reactive(list(asset = input$stock_split_asset, day = if (length(input$stock_split_date) == 1L && !is.na(input$stock_split_date)) format(as.Date(input$stock_split_date)) else NULL,
                              new = ratio_text(input$stock_split_new), old = ratio_text(input$stock_split_old)))
  # Die Vorschau gilt nur fuer genau die Eingaben, mit denen sie gerechnet wurde.
  shiny::observeEvent(key(), { current <- shiny::isolate(preview()); if (is.list(current) && !identical(current$key, key())) preview(NULL) }, ignoreInit = TRUE)
  code_of <- function(error) if (is.null(error$code)) "stock_split_store_invalid" else error$code
  run_preview <- function(remove) {
    value <- key(); notice(NULL)
    if (!is.character(value$asset) || !nzchar(value$asset) || is.null(value$day) || (!remove && (is.null(value$new) || is.null(value$old) || identical(value$new, value$old)))) {
      preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_stock_split_error_text_v1("stock_split_input_invalid"))); return()
    }
    result <- tryCatch(service$preview(value$asset, value$day, if (remove) NULL else value$new, if (remove) NULL else value$old, remove = remove),
                       error = function(error) structure(list(), code = code_of(error)))
    if (!is.null(attr(result, "code"))) { preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_stock_split_error_text_v1(attr(result, "code")))); return() }
    preview(list(key = value, result = result, remove = remove))
  }
  shiny::observeEvent(input$stock_split_preview, run_preview(FALSE))
  shiny::observeEvent(input$stock_split_remove_preview, run_preview(TRUE))
  output$stock_split_table <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!readable(current)) return(portelyra_status_panel("Splits nicht lesbar", data_stock_split_error_text_v1(attr(current, "code")), tone = "warning"))
    data_stock_split_table_v1(current)
  })
  output$stock_split_preview_block <- shiny::renderUI({ current <- preview(); if (is.list(current)) data_stock_split_preview_ui_v1(current$result, current$remove) })
  output$stock_split_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  shiny::observeEvent(input$stock_split_save, {
    current <- preview(); value <- key()
    if (!is.list(current) || !identical(current$key, value)) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = "Bitte zuerst die Vorschau zu genau diesen Angaben rechnen.")); return()
    }
    if (identical(current$result$status, "blocked")) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = data_stock_split_reason_text_v1(current$result$reason))); return()
    }
    result <- tryCatch(
      if (isTRUE(current$remove)) service$remove(value$asset, value$day, now_utc(), TRUE)
      else service$record(value$asset, value$day, value$new, value$old, input$stock_split_note, now_utc(), TRUE),
      error = function(error) structure(list(), code = code_of(error)))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_stock_split_error_text_v1(attr(result, "code")))); return() }
    preview(NULL)
    if (identical(result$status, "unchanged")) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Dieser Split ist schon gespeichert.")); return() }
    status <- if (is.function(after_write)) tryCatch(after_write(), error = function(error) NULL) else NULL
    copy <- if (identical(status, "published")) "FIFO-Stand fortgeschrieben, Tageshistorie neu veröffentlicht. Steuerergebnisse folgen mit dem nächsten Abschluss."
      else "Der FIFO-Stand ließ sich nicht sofort fortschreiben; „Alles aktualisieren“ holt das nach."
    tick(shiny::isolate(tick()) + 1L)
    notice(list(tone = if (identical(status, "published")) "positive" else "warning",
                title = if (identical(result$status, "removed")) "Split zurückgenommen" else "Split gespeichert", copy = copy))
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L), model = model))
}
