# Das Institut als eigenes Stammdatum (#430): Art und Konten je Institut, in "2. Stammdaten".
#
# Festlegung (12./13.10.2026): Das Institut ist die Oberklasse, Konten sind Unterinstanzen; es entsteht mit seinem ersten
# Konto. Hier steht je Institut, welche Konten dazugehoeren und welcher Art es ist; Freistellungsauftrag, Verlusttoepfe
# und Quellensteuer stehen in "4. Steuer". Umbenannt wird im Kontoformular ("Institut umbenennen"). Die Angaben liegen
# neben den Stammdaten (institution-master-v1). Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_institution_master_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^institution_master_[a-z_]+$", code)) code <- "institution_master_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_institution_master_error_v1", "error", "condition")))
}
data_institution_master_kinds_v1 <- function() c(`bitte wählen` = "", Bank = "bank", `Broker / Depotbank` = "broker", `Krypto-Börse` = "crypto_exchange",
  `Wallet / eigene Verwahrung` = "wallet", `Edelmetall-Verwahrung` = "metal_custody", Sonstiges = "other")
data_institution_master_error_text_v1 <- function(code) switch(as.character(code),
  institution_master_institution_unknown = "Ein Institut steht an keinem Konto mehr. Bitte den Bereich neu öffnen.",
  institution_master_input_invalid = "Die Art eines Instituts wurde nicht erkannt.",
  "Der Speicher der Institute ließ sich nicht lesen oder schreiben. Konten und Buchungen sind davon nicht berührt.")
new_data_institution_master_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_institution_master.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_institution_master_abort_v1("institution_master_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_institution_master_abort_v1(if (is.null(parsed$code)) "institution_master_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "institution_master_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_institution_master_abort_v1("institution_master_store_invalid")
    result
  }
  stamp_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)
  structure(list(
    contract_version = "data_institution_master_service_v1",
    read = function() checked(run("read", list()), "ready"),
    # `entries`: Liste aus list(institution_label, kind); kind NULL leert die Angabe.
    record = function(entries, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_institution_master_abort_v1("institution_master_confirmation_required")
      if (!is.list(entries) || !length(entries) || !stamp_valid(recorded_at_utc)) data_institution_master_abort_v1("institution_master_input_invalid")
      checked(run("record", list(entries = unname(entries), recorded_at_utc = recorded_at_utc, confirmed = TRUE)), "recorded")
    },
    rename = function(old_label, new_label, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_institution_master_abort_v1("institution_master_confirmation_required")
      if (!stamp_valid(recorded_at_utc)) data_institution_master_abort_v1("institution_master_input_invalid")
      checked(run("rename", list(old_label = old_label, new_label = new_label, recorded_at_utc = recorded_at_utc, confirmed = TRUE)), c("renamed", "unchanged"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_institution_master_service_v1", "list"))
}
data_institution_master_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "institution_master_details",
    shiny::tags$summary("Institute · Art und Konten"),
    shiny::p(class = "pl-section-copy",
      "Je Institut seine Konten und seine Art. Ein Institut entsteht mit seinem ersten Konto; umbenannt wird es im Kontoformular („Institut umbenennen“).",
      " Freistellungsauftrag, Verlusttöpfe und Quellensteuer je Institut stehen in „4. Steuer“."),
    shiny::uiOutput("institution_master_form"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("institution_master_save", "Arten speichern", class = "btn-primary")),
    shiny::uiOutput("institution_master_notice"))
}
data_institution_master_form_v1 <- function(model) {
  rows <- if (is.list(model)) model$institutions else list()
  if (!length(rows)) return(shiny::p(class = "pl-field-hint", "Noch kein Institut – es entsteht mit dem ersten Konto, das eines trägt."))
  open <- sum(vapply(rows, function(row) is.null(row$kind), logical(1L)))
  shiny::tagList(
    shiny::p(class = "pl-field-hint", sprintf("%d Institut(e) · %d ohne Art", length(rows), open)),
    shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Institut", "Art", "Konten"), shiny::tags$th))),
      shiny::tags$tbody(lapply(seq_along(rows), function(index) {
        row <- rows[[index]]
        shiny::tags$tr(shiny::tags$td(shiny::tags$strong(row$institution_label)),
          shiny::tags$td(shiny::selectInput(sprintf("institution_master_kind_%d", index), NULL, choices = data_institution_master_kinds_v1(),
            selected = if (is.null(row$kind)) "" else row$kind, selectize = FALSE, width = "220px")),
          shiny::tags$td(sprintf("%d: %s", as.integer(row$active_account_count), paste(unlist(row$account_labels), collapse = " · "))))
      })))))
}
# Was zu speichern ist: je geaenderter Art ein Eintrag; leer heisst "keine Angabe".
data_institution_master_plan_v1 <- function(model, values) {
  entries <- list()
  rows <- if (is.list(model)) model$institutions else list()
  for (index in seq_along(rows)) {
    row <- rows[[index]]
    entered <- values(index)
    entered <- if (is.character(entered) && length(entered) == 1L && !is.na(entered) && nzchar(entered)) entered else NULL
    if (!is.null(entered) && !entered %in% data_institution_master_kinds_v1()) return(list(error = sprintf("%s: Art nicht erkannt.", row$institution_label)))
    if (identical(entered, row$kind) || (is.null(entered) && is.null(row$kind))) next
    entries[[length(entries) + 1L]] <- list(institution_label = row$institution_label, kind = entered)
  }
  list(entries = entries)
}
# `on_saved`: nach gespeicherten Arten aufgerufen (die Steuerkarte je Institut liest dann neu).
data_institution_master_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    on_saved = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$institution_master_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "institution_master_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "institution_master_store_invalid" else error$code))
  })
  output$institution_master_form <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!is.null(attr(current, "code"))) return(portelyra_status_panel("Institute nicht lesbar", data_institution_master_error_text_v1(attr(current, "code")), tone = "warning"))
    data_institution_master_form_v1(current)
  })
  output$institution_master_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  shiny::observeEvent(input$institution_master_save, {
    current <- shiny::isolate(model())
    if (is.null(current) || !is.null(attr(current, "code"))) { notice(list(tone = "warning", title = "Nichts gelesen", copy = "Bitte den Bereich öffnen.")); return() }
    plan <- data_institution_master_plan_v1(current, function(index) input[[sprintf("institution_master_kind_%d", index)]])
    if (!is.null(plan$error)) { notice(list(tone = "error", title = "Nicht gespeichert", copy = plan$error)); return() }
    if (!length(plan$entries)) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Die Arten stimmen mit dem gespeicherten Stand überein.")); return() }
    result <- tryCatch(service$record(plan$entries, now_utc(), TRUE), error = function(error) structure(list(), code = if (is.null(error$code)) "institution_master_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_institution_master_error_text_v1(attr(result, "code")))); return() }
    tick(shiny::isolate(tick()) + 1L)
    if (is.function(on_saved)) tryCatch(on_saved(), error = function(error) NULL)
    notice(list(tone = "positive", title = sprintf("%d Art(en) gespeichert", as.integer(result$written_count)), copy = "Konten und Buchungen sind davon nicht berührt."))
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L)))
}
