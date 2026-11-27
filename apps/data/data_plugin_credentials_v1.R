# Zugaenge fuer Plugins in Data -> Einstellungen (#546, rc.390). Festlegungen vom 09.11.2026: eine Liste fuer alle
# Plugin-Arten; Geheimes nur im Schluesselbund des Systems, im Datenraum nur Verweis, Bezeichnung, letzte vier Zeichen und die bestaetigten
# Adressen. Eintragen, pruefen, ersetzen, Adressen bestaetigen und loeschen, jeweils mit Vorschau und Bestaetigung; die Anzeige ist immer
# maskiert. Werte gehen ueber eine Pipe an das Skript (nie als Argument, nie ueber den Eingabeweg von system2, der eine Temp-Datei schreibt) und
# werden nach dem Uebernehmen aus den Feldern geloescht.

DATA_PLUGIN_CREDENTIALS_ACTIONS_V1 <- c("Neuer Zugang" = "create", "Werte ersetzen" = "replace", "Adressen bestätigen" = "hosts",
  "Für Kursanbieter wählen" = "choice", "Zugang prüfen" = "check", "Zugang löschen" = "delete")

data_plugin_credentials_abort_v1 <- function(code) {
  stop(structure(class = c("spot_plugin_credentials_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
}

data_plugin_credentials_error_text_v1 <- function(code) switch(as.character(code),
  plugin_credentials_value_invalid = "Bitte jedes Feld ausfüllen; geheime Werte haben mindestens sechs Zeichen und keine Zeilenumbrüche.",
  plugin_credentials_preview_stale = "Die Eingabe oder der Stand hat sich seit der Vorschau geändert. Bitte erneut prüfen.",
  plugin_credentials_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau und die Adressen geprüft haben.",
  plugin_credentials_keyring_unavailable = "Der Schlüsselbund des Systems ist nicht erreichbar.",
  plugin_credentials_keyring_failed = "Der Schlüsselbund hat das Ablegen oder Entfernen abgelehnt (gesperrt oder abgebrochen?).",
  plugin_credentials_plugin_unavailable = "Für dieses Plugin ist kein gültiges Plugin mit Zugang geladen.",
  plugin_credentials_not_found = "Diesen Zugang gibt es nicht mehr. Bitte „Neu lesen“.",
  plugin_credentials_missing = "Der Wert fehlt im Schlüsselbund. Bitte „Werte ersetzen“.",
  plugin_credentials_hosts_unconfirmed = "Das Plugin nennt neue Adressen. Bitte „Adressen bestätigen“.",
  plugin_credentials_fields_changed = "Das Plugin verlangt andere Angaben. Bitte den Zugang neu eintragen.",
  plugin_credentials_check_unsupported = "Dieses Plugin kann einen Zugang nicht prüfen.",
  plugin_credentials_other_location = "Dieser Zugang wurde am Datenraum an einem anderen Ort eingetragen (Kopie oder Umzug); hier ist er gesperrt. Nach einem Umzug: „Werte ersetzen“.",
  plugin_credentials_store_invalid = "Die Zugänge dieses Datenraums sind nicht lesbar. Bitte das Backup prüfen.",
  price_provider_transport_failed = "Der Dienst war nicht erreichbar.",
  "Die Zugänge sind gerade nicht lesbar.")

data_plugin_credentials_error_copy_v1 <- function(code) sprintf("%s (%s)", data_plugin_credentials_error_text_v1(code), as.character(code))

# Ruft das Skript ueber eine Pipe auf: die Anfrage (mit Werten) geht ueber stdin, die Antwort (ohne Werte) in eine Datei.
.data_plugin_credentials_pipe_v1 <- function(python, cli, command, json) {
  out <- tempfile("pl-credentials-", fileext = ".json")
  on.exit(unlink(out), add = TRUE)
  line <- paste(shQuote(python), "-B -E -s", shQuote(cli), shQuote(command), ">", shQuote(out), "2>/dev/null")
  connection <- pipe(line, open = "wb")
  status <- tryCatch({ writeBin(charToRaw(enc2utf8(json)), connection); close(connection) },
    error = function(error) { try(close(connection), silent = TRUE); 1L })
  list(output = if (file.exists(out)) readLines(out, warn = FALSE, encoding = "UTF-8") else character(), status = if (is.null(status)) 0L else status)
}

new_data_plugin_credentials_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_plugin_credentials.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_plugin_credentials_abort_v1("plugin_credentials_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  request <- function(extra) as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE, null = "null", digits = NA))
  parse <- function(output, status) {
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(status), 0L))
      data_plugin_credentials_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "plugin_credentials_store_invalid")
    parsed$result
  }
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    result <- .data_plugin_credentials_pipe_v1(python, cli, command, request(extra)); parse(result$output, result$status)
  }
  values <- function(value) if (length(value)) value else structure(list(), names = character())
  list(
    overview = function() run("overview", list()),
    preview_create = function(plugin_id, label, value) run("create-preview", list(plugin_kind = "price_provider", plugin_id = plugin_id, label = label, values = values(value))),
    apply_create = function(preview, value, confirmed) run("create-apply", list(preview = preview, values = values(value), confirmed = isTRUE(confirmed))),
    preview_replace = function(ref, value) run("replace-preview", list(credential_ref = ref, values = values(value))),
    apply_replace = function(preview, value, confirmed) run("replace-apply", list(preview = preview, values = values(value), confirmed = isTRUE(confirmed))),
    preview_hosts = function(ref) run("hosts-preview", list(credential_ref = ref)),
    apply_hosts = function(preview, confirmed) run("hosts-apply", list(preview = preview, confirmed = isTRUE(confirmed))),
    preview_delete = function(ref) run("delete-preview", list(credential_ref = ref)),
    apply_delete = function(preview, confirmed) run("delete-apply", list(preview = preview, confirmed = isTRUE(confirmed))),
    preview_choice = function(provider_id, ref) run("choice-preview", list(provider_id = provider_id, credential_ref = ref)),
    apply_choice = function(preview, confirmed) run("choice-apply", list(preview = preview, confirmed = isTRUE(confirmed))),
    check = function(ref) run("check", list(credential_ref = ref)))
}

.data_plugin_credentials_text_v1 <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) value else "–"
data_plugin_credentials_field_id_v1 <- function(name) paste0("data_plugin_credentials_field_", name)

data_plugin_credentials_masked_v1 <- function(fields) paste(vapply(fields, function(field) {
  value <- if (isTRUE(field$secret)) paste0("••••", if (is.character(field$last4)) field$last4 else "") else .data_plugin_credentials_text_v1(field$value)
  sprintf("%s %s", .data_plugin_credentials_text_v1(field$label), value)
}, character(1L)), collapse = " · ")

data_plugin_credentials_ui_v1 <- function() portelyra_card("Zugänge", help = "app-data#plugins-und-zugänge",
  copy = "Schlüssel und Passwörter für Plugins, die einen Zugang brauchen. Sie liegen im Schlüsselbund des Systems – nicht im Datenraum und nicht im Backup.",
  note = portelyra_note_v1(title = "So schützt Portelyra einen Zugang", id = "data-plugin-credentials",
    "Portelyra setzt den Wert selbst in die Anfrage ein, nur an die Adressen, die Sie beim Eintragen bestätigen. Das Plugin sieht ihn nie.",
    "Im Datenraum stehen nur Bezeichnung, die letzten vier Zeichen und die bestätigten Adressen. Nach einer Wiederherstellung oder auf einem neuen Rechner tragen Sie den Wert neu ein.",
    "Ein Zugang gilt nur für diesen Datenraum an diesem Ort. Eine Kopie an anderem Ort kommt nicht an ihn heran; nach einem Umzug tragen Sie die Werte neu ein.",
    "Der Schlüsselbund ist mit Ihrer Anmeldung entsperrt. Programme in Ihrer Sitzung können ihn lesen, wie Ihre übrigen privaten Dateien.",
    "Kosten und die Bedingungen des Anbieters verantworten Sie; Portelyra ist kostenlos und ohne Gewähr."),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("data_plugin_credentials_refresh", "Neu lesen", class = "btn-default")),
  shiny::uiOutput("data_plugin_credentials_state"),
  shiny::uiOutput("data_plugin_credentials_table"),
  shiny::uiOutput("data_plugin_credentials_form"),
  shiny::uiOutput("data_plugin_credentials_fields"),
  shiny::uiOutput("data_plugin_credentials_preview_panel"))

data_plugin_credentials_state_ui_v1 <- function(overview) {
  if (is.null(overview)) return(NULL)
  if (!is.null(attr(overview, "code"))) return(portelyra_status_panel("Zugänge nicht lesbar", data_plugin_credentials_error_copy_v1(attr(overview, "code")), tone = "warning"))
  panels <- list()
  if (!identical(overview$keyring$status, "available"))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Schlüsselbund nicht verfügbar", .data_plugin_credentials_text_v1(overview$keyring$hint), tone = "warning")
  open <- Filter(function(row) !identical(row$state, "ready"), overview$credentials)
  if (length(open))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Zugang braucht Ihre Hilfe", paste(vapply(open, function(row)
      sprintf("%s (%s): %s", .data_plugin_credentials_text_v1(row$label), .data_plugin_credentials_text_v1(row$plugin_label), .data_plugin_credentials_text_v1(row$state_text)),
      character(1L)), collapse = "; "), tone = "warning")
  if (!length(overview$plugins))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Kein Plugin braucht einen Zugang",
      "Die geladenen Plugins laufen ohne Schlüssel, etwa Yahoo Finance. Ein Plugin mit Zugang erscheint hier, sobald es installiert ist.", tone = "neutral")
  if (length(panels)) shiny::tagList(panels) else NULL
}

data_plugin_credentials_table_ui_v1 <- function(overview) {
  if (is.null(overview) || !is.null(attr(overview, "code")) || !length(overview$credentials)) return(NULL)
  text <- .data_plugin_credentials_text_v1
  cells <- lapply(overview$credentials, function(row) list(text(row$label), text(row$plugin_label), data_plugin_credentials_masked_v1(row$fields),
    paste(unlist(row$hosts), collapse = ", "), text(row$state_text), if (is.character(row$last_success_at_utc)) pl_day_v1(row$last_success_at_utc) else "noch nie"))
  shiny::div(class = "pl-table-wrap", pl_table_v1(c("Zugang", "Plugin", "Werte", "Nur an", "Zustand", "Zuletzt erfolgreich"), cells))
}

# Aktion, Plugin bzw. Zugang: Felder je Aktion (nur anbieten, was die Aktion braucht).
data_plugin_credentials_form_ui_v1 <- function(overview, action, selected = NULL, plugin = NULL) {
  if (is.null(overview) || !is.null(attr(overview, "code")) || !length(overview$plugins)) return(NULL)
  credentials <- overview$credentials
  actions <- if (length(credentials)) DATA_PLUGIN_CREDENTIALS_ACTIONS_V1 else DATA_PLUGIN_CREDENTIALS_ACTIONS_V1["Neuer Zugang"]
  counts <- table(vapply(credentials, function(row) row$plugin_id, character(1L)))
  if (!any(counts > 1L)) actions <- actions[actions != "choice"]
  action <- if (is.character(action) && action %in% actions) action else "create"
  refs <- stats::setNames(vapply(credentials, function(row) row$credential_ref, character(1L)),
                          vapply(credentials, function(row) sprintf("%s (%s)", .data_plugin_credentials_text_v1(row$label), .data_plugin_credentials_text_v1(row$plugin_label)), character(1L)))
  plugins <- stats::setNames(vapply(overview$plugins, function(row) row$plugin_id, character(1L)), vapply(overview$plugins, function(row) .data_plugin_credentials_text_v1(row$label), character(1L)))
  shiny::tagList(
    shiny::h4(class = "pl-section-title", "Zugang eintragen oder ändern"),
    shiny::radioButtons("data_plugin_credentials_action", "Aktion", choices = actions, selected = action, inline = TRUE),
    if (identical(action, "create")) shiny::tagList(
      shiny::selectInput("data_plugin_credentials_plugin", "Plugin", choices = plugins, selected = if (isTRUE(plugin %in% plugins)) plugin else plugins[[1L]], width = "100%"),
      shiny::textInput("data_plugin_credentials_label", "Bezeichnung", placeholder = "z. B. Hauptkonto", width = "100%"))
    else shiny::selectInput("data_plugin_credentials_selected", "Zugang", choices = refs, selected = if (isTRUE(selected %in% refs)) selected else refs[[1L]], width = "100%"))
}

.data_plugin_credentials_plugin_v1 <- function(overview, plugin_id) {
  hits <- Filter(function(row) identical(row$plugin_id, plugin_id), overview$plugins)
  if (length(hits)) hits[[1L]] else NULL
}

.data_plugin_credentials_entry_v1 <- function(overview, ref) {
  hits <- Filter(function(row) identical(row$credential_ref, ref), overview$credentials)
  if (length(hits)) hits[[1L]] else NULL
}

# Welche Felder die Aktion braucht: beim Eintragen die des Plugins, beim Ersetzen die des Zugangs (laut heutigem Plugin).
data_plugin_credentials_action_fields_v1 <- function(overview, action, plugin_id, ref) {
  if (is.null(overview) || !is.null(attr(overview, "code"))) return(list())
  if (identical(action, "create")) return(if (is.null(plugin <- .data_plugin_credentials_plugin_v1(overview, plugin_id))) list() else plugin$fields)
  if (identical(action, "replace")) {
    entry <- .data_plugin_credentials_entry_v1(overview, ref)
    plugin <- if (is.null(entry)) NULL else .data_plugin_credentials_plugin_v1(overview, entry$plugin_id)
    return(if (is.null(plugin)) list() else plugin$fields)
  }
  list()
}

data_plugin_credentials_fields_ui_v1 <- function(fields, action) {
  if (!is.character(action) || !nzchar(action)) return(NULL)
  button <- switch(action, check = "Zugang prüfen", "Vorschau")
  shiny::tagList(
    lapply(fields, function(field) {
      id <- data_plugin_credentials_field_id_v1(field$name)
      input <- if (isTRUE(field$secret)) shiny::passwordInput(id, field$label, width = "100%") else shiny::textInput(id, field$label, width = "100%")
      shiny::div(input, shiny::div(class = "pl-field-hint", .data_plugin_credentials_text_v1(field$hint),
        if (is.character(field$url)) shiny::tagList(" ", shiny::tags$a(href = field$url, target = "_blank", rel = "noopener noreferrer", "Beim Anbieter"))))
    }),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_plugin_credentials_preview", button, class = "btn-default")))
}

data_plugin_credentials_preview_ui_v1 <- function(preview) {
  if (is.null(preview)) return(NULL)
  if (!is.null(attr(preview, "code"))) return(portelyra_status_panel("Nicht möglich", data_plugin_credentials_error_copy_v1(attr(preview, "code")), tone = "warning"))
  if (identical(preview$contract_version, "plugin_credential_check_v1")) {
    outcome <- as.character(preview$outcome)
    return(portelyra_status_panel(switch(outcome, accepted = "Zugang angenommen", rejected = "Zugang abgewiesen", "Antwort nicht lesbar"),
      sprintf("Ein Testabruf, Antwort des Dienstes: HTTP %s.", .data_plugin_credentials_text_v1(as.character(preview$http_status))),
      tone = switch(outcome, accepted = "positive", rejected = "error", "warning")))
  }
  text <- .data_plugin_credentials_text_v1
  title <- switch(as.character(preview$action), create = "Vorschau: neuer Zugang", replace = "Vorschau: Werte ersetzen", confirm_hosts = "Vorschau: Adressen bestätigen",
    delete = "Vorschau: Zugang löschen", choose = "Vorschau: Zugang für den Kursanbieter wählen", "Vorschau")
  confirm <- if (preview$action %in% c("create", "replace", "confirm_hosts"))
    sprintf("Ich habe die Vorschau geprüft und bestätige die Adressen: %s.", paste(unlist(preview$hosts), collapse = ", ")) else "Ich habe die Vorschau geprüft."
  shiny::tagList(
    shiny::h4(class = "pl-section-title", title),
    shiny::p(sprintf("%s · %s · %s", text(preview$label), text(preview$plugin_label), data_plugin_credentials_masked_v1(preview$fields))),
    shiny::tags$ul(class = "pl-plain-list", lapply(unlist(preview$notes), function(note) shiny::tags$li(note))),
    shiny::checkboxInput("data_plugin_credentials_confirm", confirm, FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_plugin_credentials_apply", "Übernehmen", class = "btn-primary")))
}

data_plugin_credentials_server_v1 <- function(input, output, session, service, active = shiny::reactive(TRUE)) {
  overview <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL)
  failed <- function(error) structure(list(), code = if (is.character(error$code)) error$code else "plugin_credentials_store_invalid")
  read <- function() {
    if (is.null(service)) return(overview(structure(list(), code = "plugin_credentials_store_invalid")))
    overview(tryCatch(service$overview(), error = failed))
  }
  shiny::observeEvent(active(), if (isTRUE(active()) && is.null(overview())) read(), ignoreInit = FALSE)
  shiny::observeEvent(input$data_plugin_credentials_refresh, { preview(NULL); read() })
  action <- shiny::reactive(if (is.character(input$data_plugin_credentials_action)) input$data_plugin_credentials_action else "create")
  fields <- shiny::reactive(data_plugin_credentials_action_fields_v1(overview(), action(), input$data_plugin_credentials_plugin, input$data_plugin_credentials_selected))
  values <- function() {
    current <- fields()
    stats::setNames(lapply(current, function(field) { value <- input[[data_plugin_credentials_field_id_v1(field$name)]]; if (is.character(value)) value else "" }),
                    vapply(current, function(field) field$name, character(1L)))
  }
  clear <- function() for (field in shiny::isolate(fields())) shiny::updateTextInput(session, data_plugin_credentials_field_id_v1(field$name), value = "")
  output$data_plugin_credentials_state <- shiny::renderUI(data_plugin_credentials_state_ui_v1(overview()))
  output$data_plugin_credentials_table <- shiny::renderUI(data_plugin_credentials_table_ui_v1(overview()))
  output$data_plugin_credentials_form <- shiny::renderUI(data_plugin_credentials_form_ui_v1(overview(), action(),
    shiny::isolate(input$data_plugin_credentials_selected), shiny::isolate(input$data_plugin_credentials_plugin)))
  output$data_plugin_credentials_fields <- shiny::renderUI({ current <- overview()
    if (is.null(current) || !is.null(attr(current, "code")) || !length(current$plugins)) return(NULL)
    data_plugin_credentials_fields_ui_v1(fields(), action()) })
  # Jede Aenderung der Eingabe verwirft die Vorschau (die Bestaetigung gilt genau dem Gezeigten).
  shiny::observeEvent(list(input$data_plugin_credentials_action, input$data_plugin_credentials_plugin, input$data_plugin_credentials_selected), preview(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$data_plugin_credentials_preview, {
    ref <- input$data_plugin_credentials_selected
    preview(tryCatch(switch(action(),
      create = service$preview_create(input$data_plugin_credentials_plugin, if (is.character(input$data_plugin_credentials_label)) input$data_plugin_credentials_label else "", values()),
      replace = service$preview_replace(ref, values()),
      hosts = service$preview_hosts(ref),
      delete = service$preview_delete(ref),
      choice = { entry <- .data_plugin_credentials_entry_v1(overview(), ref); service$preview_choice(if (is.null(entry)) "" else entry$plugin_id, ref) },
      check = service$check(ref)), error = failed))
    if (identical(action(), "check")) read()
  })
  output$data_plugin_credentials_preview_panel <- shiny::renderUI(data_plugin_credentials_preview_ui_v1(preview()))
  shiny::observeEvent(input$data_plugin_credentials_apply, {
    current <- preview()
    if (!is.list(current) || !is.null(attr(current, "code")) || !is.character(current$action)) return(NULL)
    confirmed <- isTRUE(input$data_plugin_credentials_confirm)
    result <- tryCatch(switch(current$action,
      create = service$apply_create(current, values(), confirmed), replace = service$apply_replace(current, values(), confirmed),
      confirm_hosts = service$apply_hosts(current, confirmed), delete = service$apply_delete(current, confirmed),
      choose = service$apply_choice(current, confirmed)), error = failed)
    if (!is.null(attr(result, "code"))) return(preview(result))
    clear(); preview(NULL); read()
    shiny::showNotification(switch(current$action, create = "Zugang eingetragen.", replace = "Werte ersetzt.", confirm_hosts = "Adressen bestätigt.",
      delete = if (isFALSE(result$keyring_cleared)) "Zugang gelöscht; der Schlüsselbund war nicht erreichbar, ein Eintrag dort bleibt stehen." else "Zugang gelöscht.",
      choose = "Zugang gewählt.", "Übernommen."), type = "message")
  })
  invisible(list(overview = overview, read = read))
}
