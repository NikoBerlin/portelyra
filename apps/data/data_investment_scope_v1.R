# Gehoert ein Cash-Konto zur Anlage? (#481) - in "2. Stammdaten", neben "Institute · Art und Konten".
#
# Festlegung (20.10.2026): Girokonten, auf die Gehalt und sonstige Einnahmen fliessen, liegen ausserhalb der Anlage;
# Tagesgeld-, Verrechnungs- und Depotkonten und Wallets innerhalb. Festgelegt wird je Konto, nicht je Umsatz. Die Angabe
# liegt neben den Stammdaten (investment-scope-v1); Konten und Buchungen beruehrt sie nicht. Nach dem Speichern wird die
# Tageshistorie neu veroeffentlicht, damit die Analyse mit dem neuen Stand rechnet. Kein Providerzugriff, kein Netzzugriff,
# kein kanonischer Write.
data_investment_scope_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^investment_scope_[a-z_]+$", code)) code <- "investment_scope_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_investment_scope_error_v1", "error", "condition")))
}
data_investment_scope_choices_v1 <- function() c(`gehört zur Anlage` = "in", `außerhalb (Giro, Alltag)` = "out")
data_investment_scope_error_text_v1 <- function(code) switch(as.character(code),
  investment_scope_account_unknown = "Ein Konto steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  investment_scope_input_invalid = "Eine Zugehörigkeit wurde nicht erkannt.",
  "Der Speicher der Zugehörigkeit ließ sich nicht lesen oder schreiben. Konten und Buchungen sind davon nicht berührt.")
# Vorschlag fuer ein Konto ohne Angabe: Ein Girokonto liegt ausserhalb, alles andere zaehlt zur Anlage. Gespeichert wird
# erst, was der Eigentuemer speichert.
data_investment_scope_proposal_v1 <- function(label) if (grepl("giro", label, ignore.case = TRUE)) "out" else "in"
new_data_investment_scope_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_investment_scope.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_investment_scope_abort_v1("investment_scope_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_investment_scope_abort_v1(if (is.null(parsed$code)) "investment_scope_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "investment_scope_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_investment_scope_abort_v1("investment_scope_store_invalid")
    result
  }
  stamp_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  structure(list(
    contract_version = "data_investment_scope_service_v1",
    read = function() checked(run("read", list()), "ready"),
    # `entries`: Liste aus list(account_id, in_investment); in_investment NULL leert die Angabe.
    record = function(entries, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_investment_scope_abort_v1("investment_scope_confirmation_required")
      if (!is.list(entries) || !length(entries) || !stamp_valid(recorded_at_utc)) data_investment_scope_abort_v1("investment_scope_input_invalid")
      checked(run("record", list(entries = unname(entries), recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "recorded")
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_investment_scope_service_v1", "list"))
}
data_investment_scope_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "investment_scope_details",
    shiny::tags$summary("Cash-Konten · Anlage und Rendite"),
    shiny::p(class = "pl-section-copy",
      "Welche Cash-Konten zur Anlage gehören. Die Rendite in der Analyse misst nur die Anlage: Was vom Girokonto aufs Tagesgeld oder ins Depot geht, ist dort eine Einlage, was zurückfließt, eine Entnahme.",
      " Girokonten, auf die Gehalt und sonstige Einnahmen fließen, liegen außerhalb; Tagesgeld-, Verrechnungs- und Depotkonten gehören dazu. Ein Konto ohne Angabe zählt zur Anlage.",
      # Grenze des Portfolios (#481), nicht "erzeugt Ertrag" (#529 Punkt 2, Korrektur 31.10.2026).
      " Ein Verrechnungskonto gehört auch ohne Zins dazu: Ein Kauf bucht dort keine Gegenbuchung, außerhalb zählte jeder Kauf als Einzahlung von außen und jeder Verkauf als Auszahlung."),
    shiny::uiOutput("investment_scope_form"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("investment_scope_save", "Zugehörigkeit speichern", class = "btn-primary")),
    shiny::uiOutput("investment_scope_notice"))
}
data_investment_scope_form_v1 <- function(model) {
  rows <- if (is.list(model)) model$cash_accounts else list()
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Noch kein Cash-Konto in den Stammdaten."))
  open <- sum(vapply(rows, function(row) is.null(row$in_investment), logical(1L)))
  outside <- sum(vapply(rows, function(row) isFALSE(row$in_investment), logical(1L)))
  shiny::tagList(
    shiny::p(class = "pl-field-hint", sprintf("%d Cash-Konten · %d außerhalb der Anlage · %d noch ohne Angabe (vorgeschlagen, erst mit „Speichern“ festgelegt)",
      length(rows), outside, open)),
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Konto", "Institut", "Zugehörigkeit", "Stand"), shiny::tags$th))),
      shiny::tags$tbody(lapply(seq_along(rows), function(index) {
        row <- rows[[index]]
        stored <- if (is.null(row$in_investment)) NULL else if (isTRUE(row$in_investment)) "in" else "out"
        shiny::tags$tr(shiny::tags$td(shiny::tags$strong(row$label)), shiny::tags$td(if (is.null(row$institution)) "—" else row$institution),
          shiny::tags$td(shiny::selectInput(sprintf("investment_scope_value_%d", index), NULL, choices = data_investment_scope_choices_v1(),
            selected = if (is.null(stored)) data_investment_scope_proposal_v1(row$label) else stored, selectize = FALSE, width = "230px")),
          shiny::tags$td(if (is.null(stored)) "Vorschlag, noch nicht gespeichert"
            else paste("festgelegt am", format(as.POSIXct(row$recorded_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y", tz = "Europe/Berlin"))))
      })))))
}
# Was zu speichern ist: je Konto, dessen Wahl vom gespeicherten Stand abweicht - auch ein Vorschlag, der noch nie
# gespeichert wurde.
data_investment_scope_plan_v1 <- function(model, values) {
  entries <- list()
  rows <- if (is.list(model)) model$cash_accounts else list()
  for (index in seq_along(rows)) {
    row <- rows[[index]]
    entered <- values(index)
    if (!is.character(entered) || length(entered) != 1L || !entered %in% data_investment_scope_choices_v1())
      return(list(error = sprintf("%s: Zugehörigkeit nicht erkannt.", row$label)))
    wanted <- identical(entered, "in")
    if (!is.null(row$in_investment) && identical(isTRUE(row$in_investment), wanted)) next
    entries[[length(entries) + 1L]] <- list(account_id = row$account_id, in_investment = wanted)
  }
  list(entries = entries)
}
# `publish`: veroeffentlicht nach dem Speichern die Tageshistorie neu (gibt den Status zurueck oder wirft).
data_investment_scope_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    publish = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$investment_scope_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "investment_scope_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "investment_scope_store_invalid" else error$code))
  })
  output$investment_scope_form <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!is.null(attr(current, "code"))) return(portelyra_status_panel("Zugehörigkeit nicht lesbar", data_investment_scope_error_text_v1(attr(current, "code")), tone = "warning"))
    data_investment_scope_form_v1(current)
  })
  output$investment_scope_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  shiny::observeEvent(input$investment_scope_save, {
    current <- shiny::isolate(model())
    if (is.null(current) || !is.null(attr(current, "code"))) { notice(list(tone = "warning", title = "Nichts gelesen", copy = "Bitte den Bereich öffnen.")); return() }
    plan <- data_investment_scope_plan_v1(current, function(index) input[[sprintf("investment_scope_value_%d", index)]])
    if (!is.null(plan$error)) { notice(list(tone = "error", title = "Nicht gespeichert", copy = plan$error)); return() }
    if (!length(plan$entries)) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Die Zugehörigkeit stimmt mit dem gespeicherten Stand überein.")); return() }
    result <- tryCatch(service$record(plan$entries, now_utc(), TRUE), error = function(error) structure(list(), code = if (is.null(error$code)) "investment_scope_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_investment_scope_error_text_v1(attr(result, "code")))); return() }
    tick(shiny::isolate(tick()) + 1L)
    published <- if (is.function(publish)) tryCatch(publish(), error = function(error) NULL) else NULL
    status <- if (is.list(published)) published$status else NULL
    copy <- if (identical(status, "published")) "Die Analyse rechnet ab jetzt mit dem neuen Stand (Seite der Analyse neu laden)."
      else if (identical(status, "already_published")) "Die Analyse hatte diesen Stand schon."
      else "Die Tageshistorie ließ sich nicht neu veröffentlichen; „Alles aktualisieren“ oder „Tageshistorie fortschreiben“ holt das nach."
    notice(list(tone = if (is.null(status)) "warning" else "positive", title = sprintf("%d Zugehörigkeit(en) gespeichert", as.integer(result$written_count)),
      copy = paste("Konten und Buchungen sind davon nicht berührt.", copy)))
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L)))
}
