# Wertermittlung je Wallet und Coin (rc.294) - in "2. Stammdaten", neben den Analyse-Einstellungen.
#
# BMF 06.03.2025 Rn. 61/62 und Festlegung (21.10.2026): Vorgabe ist FIFO walletbezogen. Fuer Kryptowerte laesst sich je Coin
# und Wallet die Durchschnittsmethode waehlen; die Haltefrist bleibt FIFO. Eine Wahl wirkt erst, wenn die Wallet leer war und
# wieder befuellt wird, und gilt bis zur vollstaendigen Veraeusserung - nicht je Jahr. Vorschau zeigt, welche Verkaeufe der
# Wallet sich je Jahr aendern; gespeichert wird nur genau die gezeigte Vorschau. Danach schreibt die App den FIFO-Stand fort
# und veroeffentlicht die Tageshistorie neu. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
data_crypto_method_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^crypto_valuation_method_[a-z_]+$", code)) code <- "crypto_valuation_method_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_crypto_method_error_v1", "error", "condition")))
}
data_crypto_method_error_text_v1 <- function(code) switch(as.character(code),
  crypto_valuation_method_asset_not_crypto = "Die Wahl gibt es nur für Kryptowerte.",
  crypto_valuation_method_asset_unknown = "Das Asset steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  crypto_valuation_method_account_unknown = "Das Konto steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  crypto_valuation_method_entry_unknown = "Für diesen Tag ist keine Wahl gespeichert, die sich zurücknehmen ließe.",
  crypto_valuation_method_preview_failed = "Die Vorschau ließ sich nicht rechnen. Der FIFO-Stand bleibt, wie er ist.",
  crypto_valuation_method_input_invalid = "Bitte Coin, Wallet, Methode und ein gültiges Datum angeben.",
  "Der Speicher der Wertermittlung ließ sich nicht lesen oder schreiben. Stammdaten und Buchungen sind davon nicht berührt.")
data_crypto_method_label_v1 <- function(method) switch(as.character(method), average = "Durchschnitt", fifo = "FIFO", "–")
data_crypto_method_day_v1 <- function(day) if (is.character(day) && length(day) == 1L && !is.na(day)) format(as.Date(day), "%d.%m.%Y") else "–"
new_data_crypto_method_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_crypto_valuation_method.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_crypto_method_abort_v1("crypto_valuation_method_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_crypto_method_abort_v1(if (is.null(parsed$code)) "crypto_valuation_method_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "crypto_valuation_method_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_crypto_method_abort_v1("crypto_valuation_method_store_invalid")
    result
  }
  entry <- function(asset_id, account_id, method, valid_from) {
    ok <- function(value, pattern) is.character(value) && length(value) == 1L && !is.na(value) && grepl(pattern, value)
    if (!ok(asset_id, "^ast_[a-z0-9_]{4,60}$") || !ok(account_id, "^acc_[a-z0-9_]{4,60}$") || !ok(valid_from, "^[0-9]{4}-[0-9]{2}-[0-9]{2}$") ||
        !(is.null(method) || identical(method, "average") || identical(method, "fifo")))
      data_crypto_method_abort_v1("crypto_valuation_method_input_invalid")
    list(asset_id = asset_id, account_id = account_id, method = method, valid_from_local_date = valid_from)
  }
  structure(list(
    contract_version = "data_crypto_method_service_v1",
    read = function() checked(run("read", list()), "ready"),
    preview = function(asset_id, account_id, method, valid_from) checked(run("preview", entry(asset_id, account_id, method, valid_from)), "previewed"),
    record = function(asset_id, account_id, method, valid_from, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_crypto_method_abort_v1("crypto_valuation_method_confirmation_required")
      if (!is.character(recorded_at_utc) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", recorded_at_utc))
        data_crypto_method_abort_v1("crypto_valuation_method_input_invalid")
      checked(run("record", c(entry(asset_id, account_id, method, valid_from), list(recorded_at_utc = recorded_at_utc, confirmed = TRUE))),
              c("recorded", "removed", "unchanged"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_crypto_method_service_v1", "list"))
}
data_crypto_method_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "crypto_method_details",
    shiny::tags$summary("Krypto · Wertermittlung je Wallet"),
    shiny::p(class = "pl-section-copy",
      "Vorgabe ist FIFO je Wallet. Für einen Coin in einer Wallet lässt sich die Durchschnittsmethode wählen: Die Haltefrist folgt weiter FIFO, die Kosten eines Verkaufs aber dem Durchschnitt der Wallet (BMF 06.03.2025, Rn. 61/62)."),
    shiny::p(class = "pl-field-hint",
      "Eine Wahl wirkt, sobald die Wallet leer war und wieder befüllt wird, und gilt bis zur vollständigen Veräußerung – nicht je Jahr. Ein Datum vor dem ersten Kauf gilt von Anfang an."),
    shiny::uiOutput("crypto_method_table"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("crypto_method_asset", "Coin", c("Coin wählen" = ""), selectize = FALSE),
      shiny::selectInput("crypto_method_account", "Wallet", c("Wallet wählen" = ""), selectize = FALSE),
      shiny::radioButtons("crypto_method_choice", "Methode", c("Durchschnitt" = "average", "FIFO" = "fifo", "Wahl dieses Tages zurücknehmen" = "remove"),
                          selected = "average", inline = TRUE),
      shiny::dateInput("crypto_method_valid_from", "Gültig ab", value = Sys.Date(), format = "dd.mm.yyyy", language = "de", weekstart = 1)),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("crypto_method_preview", "Vorschau", class = "btn-default"),
      shiny::actionButton("crypto_method_save", "Wahl speichern", class = "btn-primary")),
    shiny::uiOutput("crypto_method_preview_block"),
    shiny::uiOutput("crypto_method_notice"))
}
# Die Konten, auf denen ein Coin je lag (aus den Abschnitten des FIFO-Stands); ohne Coin oder ohne FIFO-Stand alle Konten.
data_crypto_method_wallet_choices_v1 <- function(model, asset_id) {
  accounts <- if (is.list(model)) model$accounts else list()
  held <- vapply(Filter(function(row) identical(row$asset_id, asset_id), if (is.list(model$wallets)) model$wallets else list()),
                 function(row) row$account_id, character(1L))
  if (length(held)) accounts <- Filter(function(row) row$account_id %in% held, accounts)
  c(stats::setNames("", "Wallet wählen"), stats::setNames(vapply(accounts, function(row) row$account_id, character(1L)),
                                                          vapply(accounts, function(row) row$label, character(1L))))
}
data_crypto_method_table_v1 <- function(model) {
  entries <- if (is.list(model)) model$entries else list()
  if (!length(entries)) return(shiny::p(class = "pl-field-hint", "Noch keine Wahl – alle Wallets rechnen mit FIFO."))
  segments <- if (is.list(model$segments)) model$segments else list()
  rows <- lapply(entries, function(row) {
    own <- Filter(function(segment) identical(segment$asset_id, row$asset_id) && identical(segment$account_id, row$account_id), segments)
    since <- Filter(function(segment) segment$start_local_date >= row$valid_from_local_date, own)
    state <- if (!identical(model$fifo_freshness, "fresh")) "FIFO-Stand noch nicht fortgeschrieben"
      else if (length(since)) sprintf("wirkt ab %s", data_crypto_method_day_v1(since[[1L]]$start_local_date))
      else "wartet auf vollständige Veräußerung und Neuerwerb"
    shiny::tags$tr(shiny::tags$td(row$asset_label %||% "–"), shiny::tags$td(row$account_label %||% "–"),
                   shiny::tags$td(data_crypto_method_label_v1(row$method)), shiny::tags$td(data_crypto_method_day_v1(row$valid_from_local_date)),
                   shiny::tags$td(state))
  })
  shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
    shiny::tags$thead(shiny::tags$tr(lapply(c("Coin", "Wallet", "Methode", "Gültig ab", "Stand"), shiny::tags$th))), shiny::tags$tbody(rows)))
}
data_crypto_method_preview_ui_v1 <- function(preview, valid_from, today = Sys.Date()) {
  segments <- function(rows) if (!length(rows)) "keine Befüllung" else paste(vapply(rows, function(row)
    sprintf("ab %s %s", data_crypto_method_day_v1(row$start_local_date), data_crypto_method_label_v1(row$method)), character(1L)), collapse = " · ")
  years <- Filter(function(row) row$sales > 0L, preview$years)
  # Exakter Text, dezimal oder als Bruch ("-1234/7"); erst die Anzeige rundet auf Cent.
  amount <- function(text) {
    parts <- if (is.character(text) && length(text) == 1L) strsplit(text, "/", fixed = TRUE)[[1L]] else character()
    value <- suppressWarnings(if (length(parts) == 2L) as.numeric(parts[[1L]]) / as.numeric(parts[[2L]]) else if (length(parts) == 1L) as.numeric(parts[[1L]]) else NA_real_)
    if (is.na(value)) "–" else paste(formatC(value, format = "f", digits = 2, big.mark = ".", decimal.mark = ","), "€")
  }
  past <- as.Date(valid_from) < as.Date(sprintf("%s-01-01", format(today, "%Y")))
  shiny::div(class = "pl-preview",
    shiny::p(shiny::tags$strong("Abschnitte der Wallet bisher: "), segments(preview$segments_current)),
    shiny::p(shiny::tags$strong("mit dieser Wahl: "), segments(preview$segments_candidate)),
    if (!length(years)) shiny::p(class = "pl-field-hint", "Die Wallet hat keine Verkäufe – die Wahl ändert nur künftige Rechnungen.")
    else shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Jahr", "Verkäufe der Wallet", "davon geändert", "Änderung realisierte GuV"), shiny::tags$th))),
      shiny::tags$tbody(lapply(years, function(row) shiny::tags$tr(shiny::tags$td(row$year), shiny::tags$td(row$sales), shiny::tags$td(row$changed),
                                                                  shiny::tags$td(amount(row$realized_delta))))))),
    if (identical(preview$changed_sales, 0L) && identical(segments(preview$segments_current), segments(preview$segments_candidate)))
      shiny::p(class = "pl-field-hint", "Ändert nichts: Die Wallet ist in diesem Abschnitt ununterbrochen befüllt; die Wahl wirkt erst nach vollständiger Veräußerung und Neuerwerb."),
    if (past && preview$changed_sales > 0L)
      shiny::p(class = "pl-field-hint", "Die Wahl ändert Ergebnisse abgelaufener Jahre. Bereits abgegebene Erklärungen bleiben davon unberührt; Steuerreports dieser Jahre rechnen danach anders."))
}
# `after_write`: schreibt nach dem Speichern den FIFO-Stand fort und veroeffentlicht die Tageshistorie (gibt Status oder NULL).
data_crypto_method_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    after_write = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$crypto_method_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "crypto_valuation_method_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "crypto_valuation_method_store_invalid" else error$code))
  })
  readable <- function(current) is.list(current) && is.null(attr(current, "code"))
  shiny::observeEvent(model(), {
    current <- model(); if (!readable(current)) return()
    choices <- function(rows, id, empty) c(stats::setNames("", empty), stats::setNames(vapply(rows, function(row) row[[id]], character(1L)),
                                                                                 vapply(rows, function(row) row$label, character(1L))))
    shiny::updateSelectInput(session, "crypto_method_asset", choices = choices(current$assets, "asset_id", "Coin wählen"),
                             selected = shiny::isolate(input$crypto_method_asset))
    shiny::updateSelectInput(session, "crypto_method_account", choices = data_crypto_method_wallet_choices_v1(current, shiny::isolate(input$crypto_method_asset)),
                             selected = shiny::isolate(input$crypto_method_account))
  }, ignoreNULL = TRUE)
  # Zur Wahl stehen die Konten, auf denen der gewaehlte Coin je lag.
  shiny::observeEvent(input$crypto_method_asset, {
    current <- model(); if (!readable(current)) return()
    shiny::updateSelectInput(session, "crypto_method_account", choices = data_crypto_method_wallet_choices_v1(current, input$crypto_method_asset),
                             selected = shiny::isolate(input$crypto_method_account))
  }, ignoreInit = TRUE)
  key <- shiny::reactive(list(asset = input$crypto_method_asset, account = input$crypto_method_account, method = input$crypto_method_choice,
                              day = if (length(input$crypto_method_valid_from)) as.character(input$crypto_method_valid_from) else NA_character_))
  # Die Vorschau gilt nur fuer genau die Eingaben, mit denen sie gerechnet wurde.
  shiny::observeEvent(key(), { current <- shiny::isolate(preview()); if (is.list(current) && !identical(current$key, key())) preview(NULL) }, ignoreInit = TRUE)
  method_of <- function(choice) if (identical(choice, "remove")) NULL else choice
  complete <- function(value) all(vapply(value[c("asset", "account", "method", "day")], function(item) is.character(item) && length(item) == 1L && !is.na(item) && nzchar(item), logical(1L)))
  shiny::observeEvent(input$crypto_method_preview, {
    value <- key(); notice(NULL)
    if (!complete(value)) { preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_crypto_method_error_text_v1("crypto_valuation_method_input_invalid"))); return() }
    result <- tryCatch(service$preview(value$asset, value$account, method_of(value$method), value$day),
                       error = function(error) structure(list(), code = if (is.null(error$code)) "crypto_valuation_method_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_crypto_method_error_text_v1(attr(result, "code")))); return() }
    preview(list(key = value, result = result))
  })
  output$crypto_method_table <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!readable(current)) return(portelyra_status_panel("Wertermittlung nicht lesbar", data_crypto_method_error_text_v1(attr(current, "code")), tone = "warning"))
    data_crypto_method_table_v1(current)
  })
  output$crypto_method_preview_block <- shiny::renderUI({ current <- preview(); if (is.list(current)) data_crypto_method_preview_ui_v1(current$result, current$key$day) })
  output$crypto_method_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  shiny::observeEvent(input$crypto_method_save, {
    current <- preview(); value <- key()
    if (!is.list(current) || !identical(current$key, value)) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = "Bitte zuerst die Vorschau zu genau diesen Angaben rechnen.")); return()
    }
    result <- tryCatch(service$record(value$asset, value$account, method_of(value$method), value$day, now_utc(), TRUE),
                       error = function(error) structure(list(), code = if (is.null(error$code)) "crypto_valuation_method_store_invalid" else error$code))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_crypto_method_error_text_v1(attr(result, "code")))); return() }
    preview(NULL)
    if (identical(result$status, "unchanged")) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Diese Wahl ist schon gespeichert.")); return() }
    status <- if (is.function(after_write)) tryCatch(after_write(), error = function(error) NULL) else NULL
    copy <- if (identical(status, "published")) "FIFO-Stand fortgeschrieben, Tageshistorie neu veröffentlicht. Steuerergebnisse folgen mit dem nächsten Abschluss."
      else "Der FIFO-Stand ließ sich nicht sofort fortschreiben; „Alles aktualisieren“ holt das nach."
    tick(shiny::isolate(tick()) + 1L)
    notice(list(tone = if (identical(status, "published")) "positive" else "warning",
                title = if (identical(result$status, "removed")) "Wahl zurückgenommen" else "Wahl gespeichert", copy = copy))
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L), model = model))
}
