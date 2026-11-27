# Gemeinsamer Plugin-Verwalter (#486 Schritt 3, Festlegung 16.11.2026: Daten -> Einstellungen -> "Plugins").
# Eine Liste ueber Leser, Kursanbieter und Steuermodule und ein gemeinsames "Paket installieren": Es erkennt am Paket, welche Art Plugin
# es ist, und zeigt die Pruefung dieser Art (Leser: Selbsttest, Signatur, Update eines mitgelieferten; Steuermodul: Signatur, Testfaelle,
# Jahreswerte). Die Einzelheiten bleiben in ihren Reitern: Pruefstand und Aktivierung der Leser, Aktivieren der Kursanbieter, Fassung des
# Steuermoduls im Kasten "Regelmodul".

data_plugin_manager_abort_v1 <- function(code) stop(structure(class = c("data_plugin_manager_error_v1", "error", "condition"),
  list(message = code, call = NULL, code = code)))

new_data_plugin_manager_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_plugin_manager.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_plugin_manager_abort_v1("plugin_manager_input_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE, null = "null", digits = NA))
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = body))
    status <- attr(output, "status")
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(if (is.null(status)) 0L else status), 0L))
      data_plugin_manager_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "plugin_manager_input_invalid")
    parsed$result
  }
  list(contract_version = "data_plugin_manager_service_v1",
    overview = function() {
      result <- run("overview", list())
      if (!is.list(result) || !identical(result$contract_version, "plugin_manager_overview_v1") || !is.list(result$plugins))
        data_plugin_manager_abort_v1("plugin_manager_input_invalid")
      result
    },
    kind = function(zip_path) {
      result <- run("kind", list(zip_path = zip_path))
      if (!is.list(result) || !is.character(result$kind)) data_plugin_manager_abort_v1("plugin_package_unreadable")
      result
    })
}

DATA_PLUGIN_MANAGER_KINDS_V1 <- c(statement_reader = "Leser", price_provider = "Kursanbieter", tax_model = "Steuermodul")
DATA_PLUGIN_MANAGER_SIGNATURES_V1 <- c(shipped = "mitgeliefert", signed = "von Portelyra signiert", unchecked = "ungeprüft")

data_plugin_manager_rows_v1 <- function(overview) {
  rows <- if (is.list(overview) && is.list(overview$plugins)) overview$plugins else list()
  text <- function(value) if (is.null(value) || !length(value) || is.na(value[[1L]]) || !nzchar(as.character(value[[1L]]))) "–" else as.character(value[[1L]])
  lapply(rows, function(row) {
    origin <- switch(text(row$origin), shipped = "mitgeliefert", installed = "installiert",
      update = sprintf("Update der mitgelieferten %s", text(row$replaces_shipped)), preserved = "aus einem früheren Release gesichert", text(row$origin))
    state <- switch(text(row$kind),
      statement_reader = if (is.numeric(row$active_count) && is.numeric(row$portfolio_count)) sprintf("aktiv in %d von %d Portfolios",
        as.integer(row$active_count), as.integer(row$portfolio_count)) else "–",
      price_provider = if (isTRUE(row$active)) "aktiv" else if (identical(row$state, "new")) "neu – noch nicht eingestellt" else "nicht aktiv",
      tax_model = "Fassung wählen: Kasten „Regelmodul“",
      "–")
    list(kind = unname(.data_plugin_manager_or_v1(DATA_PLUGIN_MANAGER_KINDS_V1[text(row$kind)], text(row$kind))), label = text(row$label), version = text(row$plugin_version),
         origin = origin, signature = unname(.data_plugin_manager_or_v1(DATA_PLUGIN_MANAGER_SIGNATURES_V1[text(row$signature)], text(row$signature))), state = state)
  })
}

.data_plugin_manager_or_v1 <- function(left, right) if (is.null(left) || (length(left) == 1L && is.na(left))) right else left

data_plugin_manager_list_ui_v1 <- function(overview) {
  if (is.null(overview)) return(shiny::p(class = "pl-field-hint", "Die Liste wird gelesen, sobald die Einstellungen offen sind."))
  if (!is.null(attr(overview, "code"))) return(portelyra_status_panel("Plugins nicht lesbar", sprintf("Grund: %s", attr(overview, "code")), tone = "warning"))
  rows <- data_plugin_manager_rows_v1(overview)
  problems <- if (is.list(overview$problems)) overview$problems else list()
  shiny::tagList(
    if (length(rows)) shiny::div(class = "pl-table-wrap", pl_table_v1(c("Art", "Plugin", "Version", "Herkunft", "Signatur", "Zustand"),
      lapply(rows, function(row) list(row$kind, row$label, row$version, row$origin, row$signature, row$state)))) else
      shiny::p(class = "pl-field-hint", "Keine Plugins gefunden."),
    if (length(problems)) portelyra_status_panel("Nicht alles lesbar", shiny::tags$ul(lapply(problems, function(item) shiny::tags$li(sprintf("%s: %s",
      unname(.data_plugin_manager_or_v1(DATA_PLUGIN_MANAGER_KINDS_V1[as.character(item$kind)], as.character(item$kind))), as.character(item$code))))), tone = "warning"))
}

data_plugin_manager_ui_v1 <- function() portelyra_card("Plugins", help = "app-data#plugins-und-zugänge",
  copy = paste("Alle Leser, Kursanbieter und Steuermodule auf einen Blick: Version, ob mitgeliefert oder installiert, ob von Portelyra signiert",
               "und ob sie gerade wirken. Einstellen lassen sie sich in ihren Reitern – Leser unter Transaktionen → „Leser“ (mit dem Baustein",
               "„Import aus Belegen und Auszügen“), Kursanbieter unter „Kursanbieter“ (mit dem Baustein Marktdaten), die Fassung des Steuermoduls",
               "im Kasten „Regelmodul“."),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("data_plugin_manager_read", "Liste neu lesen", class = "btn-default")),
  shiny::uiOutput("data_plugin_manager_list"),
  shiny::h4(class = "pl-section-title", "Paket installieren"),
  shiny::p(class = "pl-field-hint", paste("Ein Plugin-Paket (ZIP) für einen Leser, einen Kursanbieter oder ein Steuermodul. Portelyra erkennt die Art am",
    "Paket und prüft es, bevor etwas installiert wird: Signatur, Prüfsummen und Selbsttest bzw. Testfälle. Steuermodule nur mit",
    "Portelyra-Signatur; Leser und Kursanbieter ohne Signatur nur unter eigener Kennung, als „ungeprüft“ und mit zusätzlicher Bestätigung.")),
  shiny::div(class = "pl-field-row",
    shiny::fileInput("data_plugin_package_file", "Paket (ZIP)", accept = ".zip", buttonLabel = "Datei wählen …", placeholder = "keine Datei"),
    shiny::actionButton("data_plugin_package_check", "Paket prüfen", class = "btn-default")),
  shiny::uiOutput("data_plugin_package_note"),
  shiny::uiOutput("data_statement_readers_install_preview"),
  shiny::uiOutput("data_statement_readers_install_outcome"),
  shiny::uiOutput("data_price_providers_install_preview"),
  shiny::uiOutput("data_tax_module_install_preview"))

# on_reader(request) startet die Pruefung eines Leser-Pakets im Leser-Server, on_provider(request) die eines Kursanbieter-Pakets, on_tax(path)
# die eines Steuermodul-Pakets; alle zeigen ihre Vorschau in den Ausgaben dieser Karte.
data_plugin_manager_server_v1 <- function(input, output, session, service, active = shiny::reactive(TRUE), on_reader = NULL, on_tax = NULL, on_provider = NULL) {
  overview <- shiny::reactiveVal(NULL); note <- shiny::reactiveVal(NULL)
  read <- function() overview(if (is.null(service)) structure(list(), code = "plugin_manager_input_invalid") else
    tryCatch(service$overview(), error = function(error) structure(list(), code = if (is.character(error$code)) error$code else "plugin_manager_input_invalid")))
  shiny::observeEvent(active(), if (isTRUE(active())) read())
  shiny::observeEvent(input$data_plugin_manager_read, read(), ignoreInit = TRUE)
  output$data_plugin_manager_list <- shiny::renderUI(data_plugin_manager_list_ui_v1(overview()))
  shiny::observeEvent(input$data_plugin_package_file, note(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$data_plugin_package_check, {
    file <- input$data_plugin_package_file
    if (is.null(file) || !length(file$datapath)) { note(list(tone = "warning", title = "Keine Datei gewählt", copy = "Bitte zuerst eine ZIP-Datei wählen.")); return(invisible(NULL)) }
    path <- as.character(file$datapath[[1L]]); name <- enc2utf8(as.character(file$name[[1L]]))
    found <- if (is.null(service)) NULL else tryCatch(service$kind(path), error = function(error) NULL)
    kind <- if (is.list(found)) found$kind else "unknown"
    if (identical(kind, "statement_reader") && is.function(on_reader)) {
      note(list(tone = "neutral", title = "Leser-Paket erkannt", copy = if (isTRUE(found$packaged)) "Prüfung mit Signatur und Selbsttest." else
        "Ein Leser-Plugin im bisherigen Format, ohne Signatur – es gilt als ungeprüft."))
      on_reader(list(zip_path = path, file_name = name))
    } else if (identical(kind, "tax_model") && is.function(on_tax)) {
      note(list(tone = "neutral", title = "Steuermodul-Paket erkannt", copy = "Prüfung mit Signatur, Prüfsummen, Jahreswerten und Testfällen."))
      on_tax(path)
    } else if (identical(kind, "price_provider") && is.function(on_provider)) {
      note(list(tone = "neutral", title = "Kursanbieter-Paket erkannt", copy = "Prüfung mit Signatur, Prüfsummen und Selbsttest ohne Netz."))
      on_provider(list(zip_path = path, file_name = name))
    } else note(list(tone = "error", title = "Kein Plugin-Paket", copy = "Die Datei ist kein lesbares Plugin-Paket (ZIP mit package.json oder manifest.json)."))
  }, ignoreInit = TRUE)
  output$data_plugin_package_note <- shiny::renderUI({
    value <- note(); if (is.null(value)) return(NULL)
    portelyra_status_panel(value$title, value$copy, tone = value$tone)
  })
  invisible(list(read = read))
}
