# Experimenteller generischer Leser (#514): Zuordnung vorschlagen, pruefen und als Profil je Format speichern. Gebucht wird danach
# ueber die Karte des Wertpapier- bzw. Krypto-Imports ("Belege pruefen", Vorschau, Bestaetigung). Die Erkennung liegt in
# migrations/reference/generic_statement_import_v1.py; hier stehen nur Auswahl und Anzeige.

DATA_GENERIC_ADAPTERS_V1 <- c("generic_securities_v1", "generic_crypto_v1")
DATA_GENERIC_ZONES_V1 <- c("Europe/Berlin", "UTC", "Europe/London", "America/New_York")
DATA_GENERIC_MAX_ACTIONS_V1 <- 40L

data_generic_statement_ui_v1 <- function() shiny::conditionalPanel(
  sprintf("['%s'].indexOf(input.securities_import_adapter) >= 0", paste(DATA_GENERIC_ADAPTERS_V1, collapse = "','")),
  shiny::div(class = "pl-card", style = "border-left:4px solid #eda100;padding:10px 14px",
    shiny::strong("Zuordnung des generischen Lesers · experimentell, ohne Gewähr"),
    shiny::p(class = "pl-field-hint", paste("Der Leser schlägt aus typischen Spaltennamen und Vorgangsbezeichnungen eine Zuordnung vor. Bitte prüfen, ändern und speichern:",
      "Gespeichert gilt sie für jede Datei desselben Formats (gleiche Spalten). Unklare Zeilen bleiben beim Prüfen offen mit Grund; geraten wird nichts.",
      "Bei gängigen CSV-Exporten trifft er die Spalten oft, bei Exporten ohne Zeitzone nicht;",
      "PDF-Belege liest er nicht. Für Institute mit eigenem Leser hat dieser Vorrang.")),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("generic_statement_propose", "Zuordnung vorschlagen", class = "btn-default")),
    shiny::uiOutput("generic_statement_editor"),
    shiny::uiOutput("generic_statement_state")))

# Die Felder als Auswahl je Feld; die Vorgaenge als Auswahl je Bezeichnung (hoechstens 40 je Format).
data_generic_statement_editor_ui_v1 <- function(format, fields, kinds) {
  if (is.null(format)) return(NULL)
  columns <- unlist(format$columns)
  source <- if (is.null(format$saved)) format else format$saved
  mapping <- source$mapping; actions <- if (is.null(source$actions)) list() else source$actions
  column_choices <- c("— keine —" = "", stats::setNames(columns, columns))
  kind_choices <- c("nicht zugeordnet (bleibt offen)" = "", stats::setNames(vapply(kinds, function(kind) kind$kind, character(1L)), vapply(kinds, function(kind) kind$label, character(1L))))
  values <- utils::head(names(format$actions), DATA_GENERIC_MAX_ACTIONS_V1)
  shiny::tagList(
    shiny::p(class = "pl-field-hint", sprintf("Format mit %d Spalten, %d Zeilen in %d Datei(en)%s.", length(columns), as.integer(format$row_count), as.integer(format$file_count),
      if (!is.null(format$saved)) paste0(" · gespeichertes Profil „", format$saved$label, "“") else " · noch kein Profil gespeichert")),
    shiny::div(class = "pl-form-grid",
      lapply(fields, function(field) shiny::selectInput(paste0("generic_map_", field$field), field$label, column_choices,
        selected = if (is.null(mapping[[field$field]])) "" else mapping[[field$field]], selectize = FALSE))),
    if (length(values)) shiny::tagList(shiny::h4(class = "pl-section-title", "Vorgänge"),
      shiny::div(class = "pl-form-grid", lapply(seq_along(values), function(index) shiny::selectInput(paste0("generic_action_", index), values[[index]], kind_choices,
        selected = { chosen <- actions[[values[[index]]]]; if (is.null(chosen)) { proposed <- format$actions[[values[[index]]]]; if (is.null(proposed)) "" else proposed } else chosen },
        selectize = FALSE)))),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("generic_time_zone", "Zeitzone der Zeiten ohne Angabe", DATA_GENERIC_ZONES_V1, selected = if (is.null(source$time_zone)) "Europe/Berlin" else source$time_zone, selectize = FALSE),
      shiny::textInput("generic_profile_label", "Name des Profils", value = if (!is.null(format$saved)) format$saved$label else sub("\\.[A-Za-z0-9]+$", "", format$file_name))),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("generic_statement_sample")),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("generic_statement_save", "Zuordnung als Profil speichern", class = "btn-primary")))
}

# Das Profil aus den Eingaben der Karte; NULL, wenn kein Format gewaehlt ist.
data_generic_statement_profile_v1 <- function(input, format, fields, saved_at_utc) {
  if (is.null(format)) return(NULL)
  mapping <- stats::setNames(lapply(fields, function(field) { value <- input[[paste0("generic_map_", field$field)]]
    if (is.character(value) && length(value) == 1L && nzchar(value)) value else NULL }), vapply(fields, function(field) field$field, character(1L)))
  values <- utils::head(names(format$actions), DATA_GENERIC_MAX_ACTIONS_V1)
  actions <- stats::setNames(lapply(seq_along(values), function(index) { value <- input[[paste0("generic_action_", index)]]
    if (is.character(value) && length(value) == 1L && nzchar(value)) value else NULL }), values)
  label <- trimws(if (is.character(input$generic_profile_label)) input$generic_profile_label else "")
  list(label = if (nzchar(label)) substr(label, 1L, 120L) else "Profil", mapping = mapping, actions = actions,
       time_zone = if (isTRUE(input$generic_time_zone %in% DATA_GENERIC_ZONES_V1)) input$generic_time_zone else "Europe/Berlin", saved_at_utc = saved_at_utc)
}

# 'service' traegt propose(paths, names) und save(signature, profile); 'files' liefert die gewaehlten Dateien der Importkarte.
data_generic_statement_server_v1 <- function(input, output, session, service, files,
    now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
  proposal <- shiny::reactiveVal(NULL); state <- shiny::reactiveVal(NULL)
  failed <- function(title, error) state(list(tone = "error", title = title, copy = pl_error_text_v1(if (is.character(error$code)) error$code else "generic_failed")))
  shiny::observeEvent(input$securities_import_adapter, { proposal(NULL); state(NULL) }, ignoreInit = TRUE)
  shiny::observeEvent(input$generic_statement_propose, {
    chosen <- files()
    if (is.null(chosen) || !nrow(chosen)) return(state(list(tone = "error", title = "Keine Dateien gewählt", copy = "Bitte zuerst oben die CSV-Exporte wählen.")))
    result <- tryCatch(service$propose(chosen$datapath, chosen$name), error = function(error) error)
    if (inherits(result, "error")) { proposal(NULL); return(failed("Kein Vorschlag", result)) }
    if (!length(result$formats)) { proposal(NULL); return(state(list(tone = "warning", title = "Keine Tabelle erkannt",
      copy = "Der generische Leser liest CSV-Exporte mit Kopfzeile. PDF-Belege brauchen einen eigenen Leser."))) }
    proposal(result)
    state(list(tone = "neutral", title = sprintf("%d Format(e) erkannt", length(result$formats)),
      copy = paste0("Bitte die Zuordnung prüfen und speichern; danach „Belege prüfen“.", if (as.integer(result$unreadable_count) > 0L)
        sprintf(" %d Datei(en) ohne Tabelle.", as.integer(result$unreadable_count)) else "")))
  })
  current <- shiny::reactive({ value <- proposal(); if (is.null(value) || !length(value$formats)) NULL else value$formats[[1L]] })
  output$generic_statement_editor <- shiny::renderUI({ value <- proposal(); if (is.null(value)) return(NULL)
    data_generic_statement_editor_ui_v1(current(), value$fields, value$kinds) })
  output$generic_statement_sample <- shiny::renderTable({
    format <- current(); if (is.null(format) || !length(format$sample)) return(NULL)
    columns <- unlist(format$columns)
    frame <- as.data.frame(do.call(rbind, lapply(format$sample, function(row) vapply(columns, function(column) { value <- row[[column]]; if (is.null(value)) "" else as.character(value) }, character(1L)))),
                           stringsAsFactors = FALSE, check.names = FALSE)
    names(frame) <- columns; frame
  }, striped = TRUE, bordered = TRUE)
  shiny::observeEvent(input$generic_statement_save, {
    format <- current(); value <- proposal(); if (is.null(format)) return()
    profile <- data_generic_statement_profile_v1(input, format, value$fields, now_utc())
    if (is.null(profile$mapping$date) || (is.null(profile$mapping$quantity) && is.null(profile$mapping$amount)))
      return(state(list(tone = "error", title = "Nicht gespeichert", copy = "Mindestens Datum und Menge (oder Betrag) brauchen eine Spalte.")))
    result <- tryCatch(service$save(format$signature, profile), error = function(error) error)
    if (inherits(result, "error")) return(failed("Nicht gespeichert", result))
    format$saved <- profile; value$formats[[1L]] <- format; proposal(value)
    state(list(tone = "positive", title = sprintf("Profil „%s“ gespeichert", profile$label),
      copy = "Es gilt ab jetzt für jede Datei dieses Formats. Jetzt „Belege prüfen“ – unklare Zeilen bleiben offen mit Grund."))
  })
  output$generic_statement_state <- shiny::renderUI({ value <- state(); if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) })
  invisible(list(proposal = proposal, state = state, current = current))
}

# Der Dienst ueber die Grenze der Pruef-CLI.
new_data_generic_statement_service_v1 <- function(project_root, context) {
  payload_context <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                          actor_id = context$actor_id, role = "desktop_owner")
  run <- function(command, payload) .per_asset_review_adapter_run(project_root, command, payload)
  list(
    propose = function(paths, names) run("generic-statement-propose", list(context = payload_context, data_space_path = runtime_data_space_path(context),
      source_path = as.list(paths), file_name = as.list(names))),
    save = function(signature, profile) run("generic-statement-profile-save", list(context = payload_context, data_space_path = runtime_data_space_path(context),
      signature = signature, profile = profile, confirmed = TRUE)))
}
