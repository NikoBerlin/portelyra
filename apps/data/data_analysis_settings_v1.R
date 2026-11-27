# Vergleichsindizes (#482, #502) und eigene Asset-Gruppen (#483 Stufe 2) - in "2. Stammdaten", neben "Cash-Konten · Anlage und
# Rendite".
#
# Festlegung (20.-22.10.2026): Ein Vergleichsindex besteht aus einem oder mehreren Assets des Katalogs mit Kurshistorie und
# Gewichten (zusammen 100 %), auch wenn sie nicht gehalten werden; die Gewichte gelten taeglich fest. Gruppen gibt es frei (mit Ueberschneidung) und als Teil einer lueckenlosen Aufteilung (ohne Ueberschneidung, zusammen
# das ganze Portfolio). Assets, die nach dem Speichern dazukamen, nennt die Anzeige als Warnung. Die Angaben liegen neben den
# Stammdaten (analysis-settings-v1); Buchungen beruehren sie nicht. Nach dem Speichern wird die Tageshistorie neu
# veroeffentlicht. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_analysis_settings_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^analysis_settings_[a-z_]+$", code)) code <- "analysis_settings_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_analysis_settings_error_v1", "error", "condition")))
}
data_analysis_settings_error_text_v1 <- function(code) switch(as.character(code),
  analysis_settings_asset_unknown = "Ein Asset steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  analysis_settings_group_unknown = "Die Gruppe gibt es nicht mehr. Bitte den Bereich neu öffnen.",
  analysis_settings_index_unknown = "Den Index gibt es nicht mehr. Bitte den Bereich neu öffnen.",
  analysis_settings_label_taken = "Der Name ist schon vergeben – je Index und je Gruppe muss er eindeutig sein.",
  analysis_settings_weights_invalid = "Jedes Gewicht muss größer als 0 sein und höchstens zwei Nachkommastellen haben; zusammen genau 100 %.",
  analysis_settings_partition_overlap = "Ein gewähltes Asset steht schon in einer anderen Gruppe derselben Aufteilung. Eine Aufteilung überschneidet sich nicht.",
  analysis_settings_input_invalid = "Bitte Name und mindestens ein Asset angeben (je Index höchstens 10 Bestandteile, höchstens 10 Indizes).",
  "Der Speicher der Analyse-Einstellungen ließ sich nicht lesen oder schreiben. Stammdaten und Buchungen sind davon nicht berührt.")
new_data_analysis_settings_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_analysis_settings.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_analysis_settings_abort_v1("analysis_settings_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_analysis_settings_abort_v1(if (is.null(parsed$code)) "analysis_settings_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "analysis_settings_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_analysis_settings_abort_v1("analysis_settings_store_invalid")
    result
  }
  stamp_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  scalar <- function(value) if (is.null(value) || (is.character(value) && length(value) == 1L && !nzchar(value))) NULL else value
  structure(list(
    contract_version = "data_analysis_settings_service_v1",
    read = function() checked(run("read", list()), "ready"),
    record_index = function(index_key, label, components, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_analysis_settings_abort_v1("analysis_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc) || !is.list(components) || !length(components)) data_analysis_settings_abort_v1("analysis_settings_input_invalid")
      checked(run("record-index", list(index_key = scalar(index_key), label = label, components = unname(components),
                                       recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    remove_index = function(index_key, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_analysis_settings_abort_v1("analysis_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc)) data_analysis_settings_abort_v1("analysis_settings_input_invalid")
      checked(run("remove-index", list(index_key = index_key, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "removed")
    },
    record_group = function(group_key, label, partition, members, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_analysis_settings_abort_v1("analysis_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc) || !is.character(members) || !length(members)) data_analysis_settings_abort_v1("analysis_settings_input_invalid")
      checked(run("record-group", list(group_key = scalar(group_key), label = label, partition = scalar(partition), members = I(unname(members)),
                                       recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("recorded", "unchanged"))
    },
    remove_group = function(group_key, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_analysis_settings_abort_v1("analysis_settings_confirmation_required")
      if (!stamp_valid(recorded_at_utc)) data_analysis_settings_abort_v1("analysis_settings_input_invalid")
      checked(run("remove-group", list(group_key = group_key, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "removed")
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_analysis_settings_service_v1", "list"))
}
data_analysis_settings_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "analysis_settings_details",
    shiny::tags$summary("Analyse · Vergleichsindizes und Asset-Gruppen"),
    shiny::h4(class = "pl-section-title", "Vergleichsindizes"),
    shiny::p(class = "pl-section-copy",
      "Ein Vergleichsindex besteht aus einem oder mehreren Assets mit Kurshistorie, auch wenn sie nicht gehalten werden – etwa ein MSCI-World-ETF oder 50 % Gold und 50 % BTC.",
      " Die Analyse stellt Anlage, Klassen, Gruppen und Assets daneben; je Asset läuft der Index nur an den Tagen mit Bestand. Damit ein Bestandteil Kurse hat, braucht er eine",
      " Kurszuordnung und einen Marktdatenlauf („3. Marktdaten“). Der erste Index ist in der Analyse vorgewählt."),
    shiny::p(class = "pl-section-copy", DATA_ANALYSIS_INDEX_WEIGHTS_TEXT_V1,
      " Ausschüttungen zählen mit, wo die Kursquelle bereinigte Kurse liefert; sonst rechnet ein Bestandteil nur mit dem Kurs. Die Analyse sagt das je Index."),
    shiny::uiOutput("analysis_indices_table"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("analysis_index_target", "Index", c("Neuer Index" = ""), selectize = FALSE),
      shiny::textInput("analysis_index_label", "Name", "")),
    shiny::selectizeInput("analysis_index_members", "Bestandteile", choices = character(), multiple = TRUE, width = "100%",
                          options = list(plugins = list("remove_button"), placeholder = "Assets wählen", maxItems = 10)),
    shiny::uiOutput("analysis_index_weights"),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("analysis_index_save", "Index speichern", class = "btn-primary"),
      shiny::checkboxInput("analysis_index_remove_confirm", "Entfernen bestätigen", FALSE),
      shiny::actionButton("analysis_index_remove", "Index entfernen", class = "btn-default")),
    shiny::h4(class = "pl-section-title", style = "margin-top:16px", "Eigene Asset-Gruppen"),
    shiny::p(class = "pl-section-copy",
      "Frei zusammengestellt darf ein Asset in mehreren Gruppen stehen. Als Teil einer Aufteilung schneiden sich die Gruppen nicht und ergeben zusammen das Portfolio – die Analyse zeigt sie dann wie die Zusammensetzung nach Klassen.",
      " Assets, die nach dem Speichern einer Gruppe dazukommen, zählen nicht automatisch mit; die Liste nennt sie, bis die Gruppe neu gespeichert wird."),
    shiny::uiOutput("analysis_groups_table"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("analysis_group_target", "Gruppe", c("Neue Gruppe" = ""), selectize = FALSE),
      shiny::textInput("analysis_group_label", "Name", ""),
      shiny::radioButtons("analysis_group_kind", "Art", c("frei" = "free", "Teil einer Aufteilung" = "partition"), selected = "free", inline = TRUE),
      shiny::conditionalPanel("input.analysis_group_kind == 'partition'",
        shiny::selectizeInput("analysis_group_partition", "Aufteilung", choices = character(), options = list(create = TRUE, placeholder = "Name der Aufteilung")))),
    shiny::selectizeInput("analysis_group_members", "Assets der Gruppe", choices = character(), multiple = TRUE, width = "100%",
                          options = list(plugins = list("remove_button"), placeholder = "Assets wählen")),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("analysis_group_save", "Gruppe speichern", class = "btn-primary"),
      shiny::checkboxInput("analysis_group_remove_confirm", "Entfernen bestätigen", FALSE),
      shiny::actionButton("analysis_group_remove", "Gruppe entfernen", class = "btn-default")),
    shiny::uiOutput("analysis_settings_notice"))
}
# Erklaerung der taeglich festen Gewichte (#502, Text vom 22.10.2026) - in Data bei den Gewichten und in der Analyse.
DATA_ANALYSIS_INDEX_WEIGHTS_TEXT_V1 <- paste(
  "Ein Index aus mehreren Assets wird jeden Tag auf seine festen Gewichte zurückgesetzt. Er verhält sich, als würde man täglich verkaufen, was gestiegen ist,",
  "und nachkaufen, was gefallen ist, ohne Gebühren und ohne Steuern. Nur so ergibt jeder Zeitraum und jede Haltedauer dieselbe Indexreihe.",
  "Läuft ein Bestandteil lange in eine Richtung (etwa BTC stark aufwärts), liegt dieser Index unter einem einmal gekauften und gehaltenen Mix;",
  "schwanken die Kurse hin und her, liegt er darüber.")

# Gleiche Gewichte als Vorschlag: zwei Nachkommastellen, der Rest beim letzten Bestandteil, zusammen genau 100.
data_analysis_settings_equal_weights_v1 <- function(count) {
  if (count < 1L) return(numeric())
  cents <- rep(10000L %/% count, count); cents[[count]] <- 10000L - sum(cents[-count])
  cents / 100
}

# Gewicht als Text fuer den Speicher: hoechstens zwei Nachkommastellen, ohne Nullen am Ende; NA bei ungueltiger Eingabe.
data_analysis_settings_weight_text_v1 <- function(value) {
  number <- suppressWarnings(as.numeric(value))
  if (length(number) != 1L || is.na(number) || number <= 0 || number > 100 || abs(number * 100 - round(number * 100)) > 1e-6) return(NA_character_)
  text <- formatC(round(number, 2), format = "f", digits = 2)
  sub("\\.$", "", sub("0+$", "", text))
}

data_analysis_settings_indices_table_v1 <- function(model) {
  indices <- if (is.list(model)) model$indices else list()
  if (!length(indices)) return(shiny::p(class = "pl-field-hint", "Noch kein Vergleichsindex."))
  rows <- lapply(indices, function(index) {
    parts <- vapply(index$components, function(part) sprintf("%s %s %%", part$label, sub(".", ",", part$weight_percent, fixed = TRUE)), character(1L))
    note <- c(if (isTRUE(index$legacy)) "bis rc.298 der einzige Vergleichsindex" else NULL,
              if (isTRUE(index$missing_count > 0L)) sprintf("%d Bestandteil(e) nicht mehr in den Stammdaten – bitte neu speichern", index$missing_count) else NULL)
    shiny::tags$tr(shiny::tags$td(shiny::tags$strong(index$label)), shiny::tags$td(paste(parts, collapse = " · ")),
                   shiny::tags$td(format(as.POSIXct(index$recorded_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y", tz = "Europe/Berlin")),
                   shiny::tags$td(if (length(note)) paste(note, collapse = " · ") else "—"))
  })
  shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
    shiny::tags$thead(shiny::tags$tr(lapply(c("Index", "Bestandteile", "Gespeichert", "Hinweis"), shiny::tags$th))), shiny::tags$tbody(rows)))
}

data_analysis_settings_asset_choices_v1 <- function(model, empty = NULL) {
  assets <- if (is.list(model)) model$assets else list()
  choices <- stats::setNames(vapply(assets, function(row) row$asset_id, character(1L)), vapply(assets, function(row) row$label, character(1L)))
  if (is.null(empty)) choices else c(stats::setNames("", empty), choices)
}
data_analysis_settings_label_of_v1 <- function(model, asset_id) {
  hit <- Filter(function(row) identical(row$asset_id, asset_id), model$assets)
  if (length(hit)) hit[[1L]]$label else "–"
}
data_analysis_settings_groups_table_v1 <- function(model) {
  groups <- if (is.list(model)) model$groups else list()
  if (!length(groups)) return(shiny::p(class = "pl-field-hint", "Noch keine eigene Gruppe."))
  rows <- lapply(groups, function(group) {
    new <- vapply(group$new_assets, function(asset) data_analysis_settings_label_of_v1(model, asset), character(1L))
    warning <- c(if (length(new)) sprintf("seit dem Speichern neu: %s", paste(utils::head(new, 6L), collapse = ", ")) else NULL,
                 if (length(new) > 6L) sprintf("und %d weitere", length(new) - 6L) else NULL,
                 if (group$missing_count > 0L) sprintf("%d Mitglied(er) nicht mehr in den Stammdaten", group$missing_count) else NULL)
    shiny::tags$tr(shiny::tags$td(shiny::tags$strong(group$label)), shiny::tags$td(if (is.null(group$partition)) "frei" else paste("Aufteilung", group$partition)),
                   shiny::tags$td(length(group$members)), shiny::tags$td(if (length(warning)) paste(warning, collapse = " · ") else "—"))
  })
  partitions <- if (is.list(model)) model$partitions else list()
  shiny::tagList(
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Gruppe", "Art", "Assets", "Hinweis"), shiny::tags$th))), shiny::tags$tbody(rows))),
    lapply(partitions, function(partition) if (length(partition$uncovered)) shiny::p(class = "pl-field-hint", sprintf(
      "Aufteilung „%s“: %d Asset(s) in keiner ihrer Gruppen – %s", partition$label, length(partition$uncovered),
      paste(utils::head(vapply(partition$uncovered, function(asset) data_analysis_settings_label_of_v1(model, asset), character(1L)), 8L), collapse = ", ")))))
}
# `publish`: veroeffentlicht nach dem Speichern die Tageshistorie neu (gibt den Status zurueck oder wirft).
data_analysis_settings_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    publish = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$analysis_settings_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "analysis_settings_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "analysis_settings_store_invalid" else error$code))
  })
  readable <- function(current) is.list(current) && is.null(attr(current, "code"))
  # Nach dem Speichern oder Entfernen bleibt der Eintrag gewaehlt, den die Aktion nennt. Das Neulesen der Liste setzt die Auswahl
  # sonst auf den Stand vor der Aktion zurueck ("Neuer Index") und leert das Formular (rc.299).
  pending <- list(index = shiny::reactiveVal(NULL), group = shiny::reactiveVal(NULL))
  keep <- function(kind, current) { value <- shiny::isolate(pending[[kind]]()); pending[[kind]](NULL); if (is.null(value)) current else value }
  shiny::observeEvent(model(), {
    current <- model(); if (!readable(current)) return()
    shiny::updateSelectInput(session, "analysis_index_target", choices = c("Neuer Index" = "", stats::setNames(
      vapply(current$indices, function(index) index$index_key, character(1L)), vapply(current$indices, function(index) index$label, character(1L)))),
      selected = keep("index", shiny::isolate(input$analysis_index_target)))
    shiny::updateSelectizeInput(session, "analysis_index_members", choices = data_analysis_settings_asset_choices_v1(current),
                                selected = shiny::isolate(input$analysis_index_members), server = FALSE)
    shiny::updateSelectInput(session, "analysis_group_target", choices = c("Neue Gruppe" = "", stats::setNames(
      vapply(current$groups, function(group) group$group_key, character(1L)), vapply(current$groups, function(group) group$label, character(1L)))),
      selected = keep("group", shiny::isolate(input$analysis_group_target)))
    shiny::updateSelectizeInput(session, "analysis_group_members", choices = data_analysis_settings_asset_choices_v1(current),
                                selected = shiny::isolate(input$analysis_group_members), server = FALSE)
    shiny::updateSelectizeInput(session, "analysis_group_partition", choices = unique(vapply(current$partitions, function(row) row$label, character(1L))),
                                selected = shiny::isolate(input$analysis_group_partition))
  }, ignoreNULL = TRUE)
  # Eine gewaehlte Gruppe fuellt das Formular; "Neue Gruppe" leert es.
  shiny::observeEvent(input$analysis_group_target, {
    current <- model(); if (!readable(current)) return()
    group <- Filter(function(row) identical(row$group_key, input$analysis_group_target), current$groups)
    if (!length(group)) {
      shiny::updateTextInput(session, "analysis_group_label", value = ""); shiny::updateRadioButtons(session, "analysis_group_kind", selected = "free")
      shiny::updateSelectizeInput(session, "analysis_group_members", selected = character())
      return()
    }
    group <- group[[1L]]
    shiny::updateTextInput(session, "analysis_group_label", value = group$label)
    shiny::updateRadioButtons(session, "analysis_group_kind", selected = if (is.null(group$partition)) "free" else "partition")
    if (!is.null(group$partition)) shiny::updateSelectizeInput(session, "analysis_group_partition", selected = group$partition)
    shiny::updateSelectizeInput(session, "analysis_group_members", selected = unlist(group$members))
  }, ignoreInit = TRUE)
  # Ein gewaehlter Index fuellt Name und Bestandteile; "Neuer Index" leert sie.
  shiny::observeEvent(input$analysis_index_target, {
    current <- model(); if (!readable(current)) return()
    index <- Filter(function(row) identical(row$index_key, input$analysis_index_target), current$indices)
    if (!length(index)) {
      shiny::updateTextInput(session, "analysis_index_label", value = "")
      shiny::updateSelectizeInput(session, "analysis_index_members", selected = character())
      return()
    }
    shiny::updateTextInput(session, "analysis_index_label", value = index[[1L]]$label)
    shiny::updateSelectizeInput(session, "analysis_index_members", selected = vapply(index[[1L]]$components, function(part) part$asset_id, character(1L)))
  }, ignoreInit = TRUE)
  # Je Bestandteil ein Gewicht in Prozent: gespeicherte Gewichte des gewaehlten Index, sonst gleiche Teile.
  output$analysis_index_weights <- shiny::renderUI({
    current <- model(); members <- input$analysis_index_members
    if (!readable(current) || !length(members)) return(NULL)
    # Auch auf die Auswahl hoeren: Nach dem Speichern kommt der gespeicherte Index erst nach dem Neulesen als Auswahl an.
    index <- Filter(function(row) identical(row$index_key, input$analysis_index_target), current$indices)
    stored <- if (length(index)) stats::setNames(vapply(index[[1L]]$components, function(part) as.numeric(part$weight_percent), numeric(1L)),
                                                 vapply(index[[1L]]$components, function(part) part$asset_id, character(1L))) else numeric()
    equal <- data_analysis_settings_equal_weights_v1(length(members))
    values <- if (length(stored) && all(members %in% names(stored)) && length(stored) == length(members)) unname(stored[members]) else equal
    shiny::div(class = "pl-form-grid", lapply(seq_along(members), function(position)
      shiny::numericInput(paste0("analysis_index_weight_", position), paste0(data_analysis_settings_label_of_v1(current, members[[position]]), " (%)"),
                          value = values[[position]], min = 0.01, max = 100, step = 0.01)))
  })
  output$analysis_groups_table <- shiny::renderUI({ current <- model(); if (readable(current)) data_analysis_settings_groups_table_v1(current) })
  output$analysis_indices_table <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!readable(current)) return(portelyra_status_panel("Einstellungen nicht lesbar", data_analysis_settings_error_text_v1(attr(current, "code")), tone = "warning"))
    data_analysis_settings_indices_table_v1(current)
  })
  output$analysis_settings_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  attempt <- function(write, title) {
    result <- tryCatch(write(), error = function(error) structure(list(), code = if (is.null(error$code)) "analysis_settings_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_analysis_settings_error_text_v1(attr(result, "code")))); return(NULL) }
    if (identical(result$status, "unchanged")) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Der Stand stimmt mit dem gespeicherten überein.")); return(result) }
    tick(shiny::isolate(tick()) + 1L)
    published <- if (is.function(publish)) tryCatch(publish(), error = function(error) NULL) else NULL
    status <- if (is.list(published)) published$status else NULL
    copy <- if (identical(status, "published")) "Die Analyse zeigt den neuen Stand nach dem Neuladen ihrer Seite."
      else if (identical(status, "already_published")) "Die Analyse hatte diesen Stand schon."
      else "Die Tageshistorie ließ sich nicht neu veröffentlichen; „Alles aktualisieren“ oder „Tageshistorie fortschreiben“ holt das nach."
    notice(list(tone = if (is.null(status)) "warning" else "positive", title = title, copy = paste("Stammdaten und Buchungen sind davon nicht berührt.", copy)))
    result
  }
  shiny::observeEvent(input$analysis_index_save, {
    current <- shiny::isolate(model()); if (!readable(current)) return()
    members <- input$analysis_index_members; label <- input$analysis_index_label
    if (!is.character(label) || !nzchar(trimws(label)) || !length(members)) {
      notice(list(tone = "error", title = "Nicht gespeichert", copy = data_analysis_settings_error_text_v1("analysis_settings_input_invalid"))); return()
    }
    weights <- vapply(seq_along(members), function(position) data_analysis_settings_weight_text_v1(input[[paste0("analysis_index_weight_", position)]]), character(1L))
    if (anyNA(weights) || sum(round(as.numeric(weights) * 100)) != 10000L) {
      total <- sum(suppressWarnings(as.numeric(vapply(seq_along(members), function(position) {
        value <- input[[paste0("analysis_index_weight_", position)]]; if (is.null(value)) NA_real_ else as.numeric(value) }, numeric(1L)))), na.rm = TRUE)
      notice(list(tone = "error", title = "Nicht gespeichert", copy = paste(data_analysis_settings_error_text_v1("analysis_settings_weights_invalid"),
        sprintf("Eingegeben: zusammen %s %%.", formatC(total, format = "f", digits = 2, decimal.mark = ",")))))
      return()
    }
    components <- lapply(seq_along(members), function(position) list(asset_id = members[[position]], weight_percent = weights[[position]]))
    target <- input$analysis_index_target
    result <- attempt(function() service$record_index(if (is.character(target) && nzchar(target)) target else NULL, label, components, now_utc(), TRUE),
                      sprintf("Index „%s“ gespeichert", trimws(label)))
    if (is.list(result) && !is.null(result$index_key)) {
      pending$index(result$index_key); shiny::updateSelectInput(session, "analysis_index_target", selected = result$index_key)
    }
  })
  shiny::observeEvent(input$analysis_index_remove, {
    target <- input$analysis_index_target
    if (!is.character(target) || !nzchar(target)) { notice(list(tone = "error", title = "Nichts entfernt", copy = "Bitte zuerst einen Index wählen.")); return() }
    if (!isTRUE(input$analysis_index_remove_confirm)) { notice(list(tone = "warning", title = "Nichts entfernt", copy = "Bitte „Entfernen bestätigen“ anhaken.")); return() }
    if (!is.null(attempt(function() service$remove_index(target, now_utc(), TRUE), "Index entfernt"))) {
      shiny::updateCheckboxInput(session, "analysis_index_remove_confirm", value = FALSE)
      pending$index(""); shiny::updateSelectInput(session, "analysis_index_target", selected = "")
    }
  })
  shiny::observeEvent(input$analysis_group_save, {
    current <- shiny::isolate(model()); if (!readable(current)) return()
    members <- input$analysis_group_members; label <- input$analysis_group_label
    if (!is.character(label) || !nzchar(trimws(label)) || !length(members)) {
      notice(list(tone = "error", title = "Nicht gespeichert", copy = data_analysis_settings_error_text_v1("analysis_settings_input_invalid"))); return()
    }
    partition <- if (identical(input$analysis_group_kind, "partition")) input$analysis_group_partition else NULL
    if (identical(input$analysis_group_kind, "partition") && (!is.character(partition) || !nzchar(trimws(partition)))) {
      notice(list(tone = "error", title = "Nicht gespeichert", copy = "Bitte den Namen der Aufteilung angeben.")); return()
    }
    target <- input$analysis_group_target
    result <- attempt(function() service$record_group(if (is.character(target) && nzchar(target)) target else NULL, label, partition, members, now_utc(), TRUE),
                      sprintf("Gruppe „%s“ gespeichert", trimws(label)))
    if (is.list(result) && !is.null(result$group_key)) {
      pending$group(result$group_key); shiny::updateSelectInput(session, "analysis_group_target", selected = result$group_key)
    }
  })
  shiny::observeEvent(input$analysis_group_remove, {
    target <- input$analysis_group_target
    if (!is.character(target) || !nzchar(target)) { notice(list(tone = "error", title = "Nichts entfernt", copy = "Bitte zuerst eine Gruppe wählen.")); return() }
    if (!isTRUE(input$analysis_group_remove_confirm)) { notice(list(tone = "warning", title = "Nichts entfernt", copy = "Bitte „Entfernen bestätigen“ anhaken.")); return() }
    if (!is.null(attempt(function() service$remove_group(target, now_utc(), TRUE), "Gruppe entfernt"))) {
      shiny::updateCheckboxInput(session, "analysis_group_remove_confirm", value = FALSE)
      pending$group(""); shiny::updateSelectInput(session, "analysis_group_target", selected = "")
    }
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L), model = model))
}
