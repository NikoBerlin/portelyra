# Stichtag und Momentaufnahme in der Analyse (rc.313, #478).
#
# Festlegung 20.10.2026: Werte und GuV gehoeren in die Analyse, das Cockpit wird zur Datenbasis. Festlegung 24.10.2026:
# „Handeln in Data, Lesen in der Analyse“. Diese Reiter zeigen nur Veroeffentlichtes: die Stichtags-Snapshots (verbindlich, jeder
# Stand bleibt liegen) und die Momentaufnahme, die „Alles aktualisieren“ zum Schluss veroeffentlicht. Planen, veroeffentlichen und
# Kurse abrufen gibt es hier nicht - der Leser kennt nur `published`, `show` und `intraday_read`.

analysis_stichtag_ui_v1 <- function() shiny::tagList(
  shiny::p(class = "pl-section-copy", paste(
    "Der verbindliche Stand eines Tages: Bestand, Einstand, Marktwert und unrealisierte GuV je Position, Cash je Konto.",
    "„Alles aktualisieren“ in der App „Daten“ veröffentlicht ihn zum jüngsten vollständig bewerteten Tag; jeder Stand bleibt liegen.")),
  portelyra_card("Stichtags-Snapshot (verbindlich)", help = "app-analyse#stichtag",
    shiny::selectInput("analysis_snapshot_shown", "Angezeigter Stand", choices = c("Zuletzt veröffentlicht" = ""), width = "100%"),
    shiny::uiOutput("analysis_snapshot_state"),
    shiny::tags$h4("Überblick"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("analysis_snapshot_summary")),
    shiny::tags$h4("Frische je Ebene"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("analysis_snapshot_freshness")),
    shiny::div(class = "pl-table-wrap", style = "max-height:420px;overflow:auto", shiny::tableOutput("analysis_snapshot_positions")),
    shiny::uiOutput("analysis_snapshot_series_note"),
    shiny::tags$details(shiny::tags$summary("Nicht im Marktwert enthalten"),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("analysis_snapshot_excluded"))),
    shiny::tags$h4("Cash je Konto"),
    shiny::checkboxInput("analysis_snapshot_show_small", "Kleinstbestände zeigen", FALSE),
    shiny::uiOutput("analysis_snapshot_small"),
    shiny::div(class = "pl-table-wrap", style = "max-height:420px;overflow:auto", shiny::tableOutput("analysis_snapshot_cash"))))

analysis_moment_ui_v1 <- function() shiny::tagList(
  shiny::p(class = "pl-section-copy", paste(
    "Das Bild von jetzt: dieselbe Rechnung wie der Stichtags-Snapshot, mit den aktuellen Kursen vom Ende des letzten",
    "„Alles aktualisieren“. Tagesfrisch, aber kein Tagesschluss.")),
  portelyra_card("Momentaufnahme", help = "app-analyse#momentaufnahme",
    shiny::uiOutput("analysis_moment_state"),
    shiny::tags$h4("Überblick"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("analysis_moment_summary")),
    shiny::div(class = "pl-table-wrap", style = "max-height:420px;overflow:auto", shiny::tableOutput("analysis_moment_positions")),
    shiny::uiOutput("analysis_moment_series_note"),
    shiny::tags$details(shiny::tags$summary("Nicht im Marktwert enthalten"),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("analysis_moment_excluded"))),
    shiny::tags$details(shiny::tags$summary("Cash je Konto"),
      shiny::checkboxInput("analysis_moment_show_small", "Kleinstbestände zeigen", FALSE),
      shiny::uiOutput("analysis_moment_small"),
      shiny::div(class = "pl-table-wrap", style = "max-height:420px;overflow:auto", shiny::tableOutput("analysis_moment_cash")))))

# `reader`: data_portfolio_snapshot_reader_v1 (nur lesend) oder NULL. `tab`: der gewaehlte Reiter - gelesen wird erst, wenn
# einer der beiden Reiter offen ist, und erneut mit „Neu lesen“ (`refresh`). `threshold`: die Grenze fuer Kleinstbestaende aus
# den Einstellungen (#534), gelesen mit jedem Laden. `modules`: die Bausteine eines veroeffentlichten Umfangs (#542) oder NULL - ohne
# Marktdaten heisst der Wert, wie er entsteht, ohne Cash die Summe „ohne Cash“; ohne Umfang alles wie bisher.
analysis_snapshots_server_v1 <- function(input, output, session, reader, tab, refresh, threshold = function() "1", modules = function() NULL) {
  scope_modules <- shiny::reactive(tryCatch(modules(), error = function(error) NULL))
  # Ohne Cash im Umfang ist eine leere Cash-Tabelle kein Fehlen, sondern „nicht geführt“ - nur bei einem gezeigten Stand.
  cash_table <- function(value, frame) {
    current <- scope_modules()
    if (is.list(value) && !nrow(frame) && is.list(current) && isFALSE(current[["cash"]])) data.frame(Hinweis = "Cash nicht geführt, wie gewählt (Umfang).", check.names = FALSE) else frame
  }
  limit <- shiny::reactiveVal("1")
  read_limit <- function() limit(tryCatch({ value <- threshold(); if (is.character(value) && length(value) == 1L) value else "1" }, error = function(error) "1"))
  snapshot <- shiny::reactiveVal(NULL); snapshot_notice <- shiny::reactiveVal(NULL); refs <- shiny::reactiveVal(character())
  library_rows <- shiny::reactiveVal(list())
  moment <- shiny::reactiveVal(NULL); moment_notice <- shiny::reactiveVal(NULL)
  loaded <- shiny::reactiveValues(stichtag = FALSE, moment = FALSE)
  unavailable <- list(tone = "warning", title = "Nicht lesbar", copy = "Der veröffentlichte Stand ließ sich nicht lesen. „Neu lesen“ versucht es erneut.")
  load_stichtag <- function(selected = shiny::isolate(input$analysis_snapshot_shown)) {
    loaded$stichtag <- TRUE; read_limit()
    if (is.null(reader)) { snapshot_notice(unavailable); return(invisible(NULL)) }
    library <- tryCatch(reader$published(), error = function(error) NULL)
    library_rows(if (is.list(library) && is.list(library$snapshots)) library$snapshots else list())
    refs(desktop_snapshot_library_refs_v1(library))
    # Ohne Auswahl der juengste Stichtag (die Liste steht juengster zuerst).
    choices <- desktop_snapshot_library_choices_v1(library); names(choices)[[1L]] <- "Jüngster Stichtag"
    keep <- is.character(selected) && length(selected) == 1L && selected %in% names(shiny::isolate(refs()))
    shiny::updateSelectInput(session, "analysis_snapshot_shown", choices = choices, selected = if (keep) selected else "")
    show(if (keep) selected else "")
  }
  show <- function(ref) {
    snapshots <- shiny::isolate(library_rows())
    id <- if (is.character(ref) && length(ref) == 1L && nzchar(ref)) unname(shiny::isolate(refs())[ref])
          else if (length(snapshots)) snapshots[[1L]]$snapshot_id else NA_character_
    if (length(id) != 1L || is.na(id)) { snapshot(NULL); snapshot_notice(NULL); return(invisible(NULL)) }
    value <- tryCatch(reader$show(id), error = function(error) NULL)
    snapshot(value); snapshot_notice(if (is.null(value)) unavailable else NULL)
  }
  load_moment <- function() {
    loaded$moment <- TRUE; read_limit()
    if (is.null(reader)) { moment_notice(unavailable); return(invisible(NULL)) }
    value <- tryCatch(reader$intraday_read(), error = function(error) NULL)
    moment(value); moment_notice(if (is.null(value)) unavailable else NULL)
  }
  shiny::observeEvent(tab(), {
    if (identical(tab(), "stichtag") && !loaded$stichtag) load_stichtag()
    if (identical(tab(), "moment") && !loaded$moment) load_moment()
  }, ignoreNULL = TRUE)
  shiny::observeEvent(refresh(), {
    if (loaded$stichtag) load_stichtag()
    if (loaded$moment) load_moment()
  }, ignoreInit = TRUE)
  shiny::observeEvent(input$analysis_snapshot_shown, if (loaded$stichtag) show(input$analysis_snapshot_shown), ignoreInit = TRUE)
  output$analysis_snapshot_state <- shiny::renderUI(desktop_snapshot_state_ui_v1(snapshot(), snapshot_notice(), scope_modules()))
  output$analysis_snapshot_summary <- shiny::renderTable(desktop_snapshot_summary_frame_v1(snapshot(), scope_modules()), striped = TRUE, bordered = TRUE, align = "lrl")
  output$analysis_snapshot_freshness <- shiny::renderTable(desktop_snapshot_freshness_frame_v1(snapshot()), striped = TRUE, spacing = "xs", width = "100%")
  snapshot_small <- shiny::reactive(desktop_snapshot_small_holdings_v1(snapshot(), limit()))
  moment_small <- shiny::reactive(desktop_snapshot_small_holdings_v1(moment(), limit()))
  snapshot_view <- shiny::reactive({ small <- snapshot_small(); if (isTRUE(input$analysis_snapshot_show_small)) snapshot() else small$model })
  moment_view <- shiny::reactive({ small <- moment_small(); if (isTRUE(input$analysis_moment_show_small)) moment() else small$model })
  output$analysis_snapshot_small <- shiny::renderUI({ text <- desktop_snapshot_small_holdings_note_v1(snapshot_small(), input$analysis_snapshot_show_small)
    if (!is.null(text)) shiny::p(class = "pl-field-hint", text) })
  output$analysis_moment_small <- shiny::renderUI({ text <- desktop_snapshot_small_holdings_note_v1(moment_small(), input$analysis_moment_show_small)
    if (!is.null(text)) shiny::p(class = "pl-field-hint", text) })
  output$analysis_snapshot_positions <- shiny::renderTable(desktop_snapshot_positions_frame_v1(snapshot_view(), scope_modules()), striped = TRUE, spacing = "xs", width = "100%")
  output$analysis_snapshot_series_note <- shiny::renderUI(desktop_snapshot_series_note_v1(snapshot_view()))
  output$analysis_snapshot_excluded <- shiny::renderTable(desktop_snapshot_excluded_frame_v1(snapshot()), striped = TRUE, spacing = "xs", width = "100%")
  output$analysis_snapshot_cash <- shiny::renderTable(cash_table(snapshot_view(), desktop_snapshot_cash_frame_v1(snapshot_view())), striped = TRUE, bordered = TRUE)
  output$analysis_moment_state <- shiny::renderUI(desktop_intraday_state_ui_v1(moment(), moment_notice(), scope_modules()))
  output$analysis_moment_summary <- shiny::renderTable(desktop_snapshot_summary_frame_v1(moment(), scope_modules()), striped = TRUE, bordered = TRUE, align = "lrl")
  output$analysis_moment_positions <- shiny::renderTable(desktop_snapshot_positions_frame_v1(moment_view(), scope_modules()), striped = TRUE, spacing = "xs", width = "100%")
  output$analysis_moment_series_note <- shiny::renderUI(desktop_snapshot_series_note_v1(moment_view()))
  output$analysis_moment_excluded <- shiny::renderTable(desktop_snapshot_excluded_frame_v1(moment()), striped = TRUE, spacing = "xs", width = "100%")
  output$analysis_moment_cash <- shiny::renderTable(cash_table(moment_view(), desktop_snapshot_cash_frame_v1(moment_view())), striped = TRUE, bordered = TRUE)
  invisible(list(snapshot = snapshot, moment = moment, load_stichtag = load_stichtag, load_moment = load_moment))
}
