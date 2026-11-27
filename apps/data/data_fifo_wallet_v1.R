# FIFO-Wallet aus mehreren Konten (#508) - in "2. Stammdaten", Unterreiter "FIFO-Wallet".
#
# Festlegung (23.10.2026): Ein Unterkonto einer Boerse oder eines Hardware-Wallets (Staking, Earn, weitere Konten auf dem Geraet)
# laesst sich einem Hauptkonto desselben Instituts zuordnen; beide bilden dann eine FIFO-Wallet. Nur Kryptowerte, eine Stufe, fuer
# die ganze Historie. Der Hinweis auf Verkaeufe mit Bestand auf einem anderen Konto desselben Instituts steht nur ohne Zuordnung.
# Vorschau zeigt, welche Verkaeufe sich je Jahr aendern; gespeichert wird nur genau die gezeigte Vorschau. Danach schreibt die App
# den FIFO-Stand fort und veroeffentlicht die Tageshistorie neu. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
# R vor 4.4 (Ubuntu 24.04 bringt 4.3.3) kennt `%||%` nicht in base, Shiny liefert ihn nicht (Endabnahme 19.11.2026).
if (!exists("%||%", mode = "function")) `%||%` <- function(x, y) if (is.null(x)) y else x
data_fifo_wallet_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^fifo_wallet_[a-z_]+$", code)) code <- "fifo_wallet_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code), class = c("spot_data_fifo_wallet_error_v1", "error", "condition")))
}
data_fifo_wallet_error_text_v1 <- function(code) switch(as.character(code),
  fifo_wallet_account_not_crypto = "Zuordnen lassen sich nur Krypto-Konten (Börse oder Wallet); Wertpapierdepots bleiben je Depot getrennt.",
  fifo_wallet_account_unknown = "Ein Konto steht nicht mehr in den Stammdaten. Bitte den Bereich neu öffnen.",
  fifo_wallet_institution_mismatch = "Beide Konten müssen zum selben Institut und Portfolio gehören.",
  fifo_wallet_chain_invalid = "Eine Stufe: Ein Hauptkonto ist selbst keinem Konto zugeordnet, und ein zugeordnetes Konto hat keine eigenen Unterkonten.",
  fifo_wallet_entry_unknown = "Für dieses Konto ist keine Zuordnung gespeichert, die sich lösen ließe.",
  fifo_wallet_preview_failed = "Die Vorschau ließ sich nicht rechnen. Der FIFO-Stand bleibt, wie er ist.",
  fifo_wallet_input_invalid = "Bitte ein Konto und ein Hauptkonto wählen.",
  "Der Speicher der FIFO-Wallet ließ sich nicht lesen oder schreiben. Stammdaten und Buchungen sind davon nicht berührt.")
data_fifo_wallet_day_v1 <- function(day) if (is.character(day) && length(day) == 1L && !is.na(day)) format(as.Date(day), "%d.%m.%Y") else "–"
new_data_fifo_wallet_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_fifo_wallet.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_fifo_wallet_abort_v1("fifo_wallet_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_fifo_wallet_abort_v1(if (is.null(parsed$code)) "fifo_wallet_store_invalid" else parsed$code)
    parsed$result
  }
  checked <- function(result, status) {
    if (!is.list(result) || !identical(result$contract_version, "fifo_wallet_v1") || !result$status %in% status || isTRUE(result$canonical_write))
      data_fifo_wallet_abort_v1("fifo_wallet_store_invalid")
    result
  }
  entry <- function(account_id, wallet_account_id) {
    ok <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^acc_[a-z0-9_]{4,60}$", value)
    if (!ok(account_id) || !(is.null(wallet_account_id) || ok(wallet_account_id))) data_fifo_wallet_abort_v1("fifo_wallet_input_invalid")
    list(account_id = account_id, wallet_account_id = wallet_account_id)
  }
  structure(list(
    contract_version = "data_fifo_wallet_service_v1",
    read = function() checked(run("read", list()), "ready"),
    # Nur die Zuordnungen - fuer "Konten durchsuchen", ohne die Lot-Spur des Hinweises.
    entries = function() checked(run("entries", list()), "ready")$entries,
    preview = function(account_id, wallet_account_id) checked(run("preview", entry(account_id, wallet_account_id)), "previewed"),
    record = function(account_id, wallet_account_id, recorded_at_utc, confirmed) {
      if (!isTRUE(confirmed)) data_fifo_wallet_abort_v1("fifo_wallet_confirmation_required")
      if (!is.character(recorded_at_utc) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", recorded_at_utc))
        data_fifo_wallet_abort_v1("fifo_wallet_input_invalid")
      checked(run("record", c(entry(account_id, wallet_account_id), list(recorded_at_utc = recorded_at_utc, confirmed = TRUE))),
              c("recorded", "removed", "unchanged"))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_fifo_wallet_service_v1", "list"))
}
# Speichern seit rc.311 (#508): In rc.310 fuehrten Tageshistorie (Einstand, Netto und Projektion je Konto) und Steuerreport die
# Lose noch je Buchungskonto. Der Schalter bleibt, falls ein Leser wieder nachziehen muss; dann zeigt die Karte nur die Vorschau.
DATA_FIFO_WALLET_SAVE_V1 <- TRUE
DATA_FIFO_WALLET_SAVE_LATER_V1 <- paste("Speichern folgt mit dem nächsten Release: Erst dann rechnen auch Einstand, Netto je Konto und der",
                                        "Krypto-Steuerreport mit der Wallet. Die Vorschau zeigt schon jetzt, was sich ändern würde.")
data_fifo_wallet_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "fifo_wallet_details",
    shiny::tags$summary("Krypto · FIFO-Wallet aus mehreren Konten"),
    shiny::p(class = "pl-section-copy", "Ein Staking- oder Unterkonto einem Hauptkonto desselben Instituts zuordnen: Beide rechnen dann als eine FIFO-Wallet."),
    portelyra_note_v1(title = "So wirkt die Zuordnung", id = "data-fifo-wallet",
      paste("Ohne Zuordnung ist jedes Konto eine eigene FIFO-Wallet. Eine Umbuchung aufs Staking-Konto nimmt dann die ältesten Lose mit,",
            "und ein Verkauf vom Hauptkonto verbraucht jüngere. Mit Zuordnung bleibt jedes Los in der Wallet, und ein Verkauf verbraucht die ältesten der ganzen Wallet."),
      paste("Die Zuordnung gilt für die ganze Historie des Kontos. Bestand und Buchungen bleiben je Konto; FIFO, Haltefrist und Steuer rechnen je Wallet.",
            "Nur Kryptowerte: Bei Brokern gilt FIFO je Depot (§ 20 Abs. 4 Satz 7 EStG). Ob Unterkonten eine Wallet sind, klärt verbindlich die Steuerberatung (BMF 06.03.2025, Rn. 62).")),
    shiny::uiOutput("fifo_wallet_hint"),
    shiny::uiOutput("fifo_wallet_table"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("fifo_wallet_account", "Konto", c("Konto wählen" = ""), selectize = FALSE),
      shiny::selectInput("fifo_wallet_main", "FIFO gemeinsam mit", c("Hauptkonto wählen" = ""), selectize = FALSE)),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("fifo_wallet_preview", "Vorschau", class = "btn-default"),
      if (isTRUE(DATA_FIFO_WALLET_SAVE_V1)) shiny::actionButton("fifo_wallet_save", "Zuordnung speichern", class = "btn-primary")),
    if (!isTRUE(DATA_FIFO_WALLET_SAVE_V1)) shiny::p(class = "pl-field-hint", DATA_FIFO_WALLET_SAVE_LATER_V1),
    shiny::uiOutput("fifo_wallet_preview_block"),
    shiny::uiOutput("fifo_wallet_notice"))
}
# Hauptkonten zur Wahl: Krypto-Konten desselben Instituts und Portfolios, nicht das Konto selbst und keines, das schon zugeordnet ist.
data_fifo_wallet_main_choices_v1 <- function(model, account_id) {
  accounts <- if (is.list(model)) model$accounts else list()
  own <- Filter(function(row) identical(row$account_id, account_id), accounts)
  assigned <- vapply(if (is.list(model$entries)) model$entries else list(), function(row) row$account_id, character(1L))
  current <- Filter(function(row) identical(row$account_id, account_id), if (is.list(model$entries)) model$entries else list())
  candidates <- if (!length(own)) list() else Filter(function(row) !identical(row$account_id, account_id) && !row$account_id %in% assigned &&
    identical(tolower(row$institution), tolower(own[[1L]]$institution)) && nzchar(row$institution) && identical(row$portfolio_id, own[[1L]]$portfolio_id), accounts)
  c(stats::setNames("", "Hauptkonto wählen"),
    if (length(current)) stats::setNames("__remove__", "Zuordnung lösen") else character(),
    stats::setNames(vapply(candidates, function(row) row$account_id, character(1L)), vapply(candidates, function(row) row$label, character(1L))))
}
data_fifo_wallet_account_choices_v1 <- function(model) {
  accounts <- if (is.list(model)) model$accounts else list()
  mains <- vapply(if (is.list(model$entries)) model$entries else list(), function(row) row$wallet_account_id, character(1L))
  shown <- Filter(function(row) nzchar(row$institution) && !row$account_id %in% mains, accounts)
  c(stats::setNames("", "Konto wählen"), stats::setNames(vapply(shown, function(row) row$account_id, character(1L)),
    vapply(shown, function(row) paste0(row$label, " · ", row$institution), character(1L))))
}
data_fifo_wallet_table_v1 <- function(model) {
  entries <- if (is.list(model)) model$entries else list()
  if (!length(entries)) return(shiny::p(class = "pl-field-hint", "Noch keine Zuordnung – jedes Krypto-Konto rechnet als eigene FIFO-Wallet."))
  rows <- lapply(entries, function(row) shiny::tags$tr(shiny::tags$td(row$account_label %||% "–"), shiny::tags$td(paste("FIFO gemeinsam mit", row$wallet_account_label %||% "–")),
                                                       shiny::tags$td(row$institution %||% "–")))
  shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
    shiny::tags$thead(shiny::tags$tr(lapply(c("Konto", "Zuordnung", "Institut"), shiny::tags$th))), shiny::tags$tbody(rows)))
}
# Hinweis (Festlegung 23.10.2026): Verkaeufe, waehrend derselbe Coin auf einem anderen, nicht zugeordneten Konto desselben Instituts lag.
data_fifo_wallet_hint_v1 <- function(model) {
  rows <- if (is.list(model)) model$shared_sales else list()
  if (!length(rows)) return(NULL)
  label <- function(id) { hit <- Filter(function(row) identical(row$account_id, id), model$accounts); if (length(hit)) hit[[1L]]$label else "–" }
  coin <- function(id) { value <- model$asset_labels[[id]]; if (is.null(value)) "–" else value }
  portelyra_status_panel(sprintf("%d %s mit Bestand auf einem anderen Konto desselben Instituts", length(rows), if (length(rows) == 1L) "Verkauf" else "Verkäufe"),
    shiny::tagList("Gehört dieses Konto zur selben Wallet, rechnet FIFO nach einer Zuordnung anders. Die Vorschau zeigt, um wie viel.",
      shiny::tags$ul(lapply(utils::head(rows, 12L), function(row) shiny::tags$li(sprintf("%s · %s · verkauft von %s, Bestand auch auf %s",
        data_fifo_wallet_day_v1(row$local_date), coin(row$asset_id), label(row$account_id),
        paste(vapply(row$other_account_ids, label, character(1L)), collapse = ", ")))))), tone = "warning")
}
data_fifo_wallet_preview_ui_v1 <- function(preview) {
  years <- Filter(function(row) row$sales > 0L, preview$years)
  amount <- function(text) {
    parts <- if (is.character(text) && length(text) == 1L) strsplit(text, "/", fixed = TRUE)[[1L]] else character()
    value <- suppressWarnings(if (length(parts) == 2L) as.numeric(parts[[1L]]) / as.numeric(parts[[2L]]) else if (length(parts) == 1L) as.numeric(parts[[1L]]) else NA_real_)
    if (is.na(value)) "–" else paste(formatC(value, format = "f", digits = 2, big.mark = ".", decimal.mark = ","), "€")
  }
  shiny::div(class = "pl-preview",
    shiny::p(shiny::tags$strong(sprintf("%d %s neu zu rechnen.", as.integer(preview$world_count), if (identical(as.integer(preview$world_count), 1L)) "Coin ist" else "Coins sind"))),
    if (!length(years)) shiny::p(class = "pl-field-hint", "Die betroffenen Coins haben keine Verkäufe – die Zuordnung ändert nur künftige Rechnungen.")
    else shiny::div(style = "overflow-x:auto", shiny::tags$table(class = "table shiny-table table-striped",
      shiny::tags$thead(shiny::tags$tr(lapply(c("Jahr", "Verkäufe", "davon geändert", "Änderung realisierte GuV"), shiny::tags$th))),
      shiny::tags$tbody(lapply(years, function(row) shiny::tags$tr(shiny::tags$td(row$year), shiny::tags$td(row$sales), shiny::tags$td(row$changed),
                                                                  shiny::tags$td(amount(row$realized_delta))))))),
    if (isTRUE(preview$changed_sales > 0L))
      shiny::p(class = "pl-field-hint", "Die Zuordnung ändert Ergebnisse vergangener Jahre. Bereits abgegebene Erklärungen bleiben davon unberührt; Steuerreports dieser Jahre rechnen danach anders."))
}
# `after_write`: schreibt nach dem Speichern den FIFO-Stand fort und veroeffentlicht die Tageshistorie (gibt Status oder NULL).
data_fifo_wallet_server_v1 <- function(input, output, session, service, now_utc = function() format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
    after_write = NULL) {
  tick <- shiny::reactiveVal(0L); notice <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL)
  open <- shiny::reactive(isTRUE(input$fifo_wallet_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(NULL)
    if (is.null(service)) return(structure(list(), code = "fifo_wallet_store_invalid"))
    tryCatch(service$read(), error = function(error) structure(list(), code = if (is.null(error$code)) "fifo_wallet_store_invalid" else error$code))
  })
  readable <- function(current) is.list(current) && is.null(attr(current, "code"))
  shiny::observeEvent(model(), {
    current <- model(); if (!readable(current)) return()
    shiny::updateSelectInput(session, "fifo_wallet_account", choices = data_fifo_wallet_account_choices_v1(current), selected = shiny::isolate(input$fifo_wallet_account))
    shiny::updateSelectInput(session, "fifo_wallet_main", choices = data_fifo_wallet_main_choices_v1(current, shiny::isolate(input$fifo_wallet_account)),
                             selected = shiny::isolate(input$fifo_wallet_main))
  }, ignoreNULL = TRUE)
  shiny::observeEvent(input$fifo_wallet_account, {
    current <- model(); if (!readable(current)) return()
    shiny::updateSelectInput(session, "fifo_wallet_main", choices = data_fifo_wallet_main_choices_v1(current, input$fifo_wallet_account), selected = "")
  }, ignoreInit = TRUE)
  key <- shiny::reactive(list(account = input$fifo_wallet_account, main = input$fifo_wallet_main))
  # Die Vorschau gilt nur fuer genau die Eingaben, mit denen sie gerechnet wurde.
  shiny::observeEvent(key(), { current <- shiny::isolate(preview()); if (is.list(current) && !identical(current$key, key())) preview(NULL) }, ignoreInit = TRUE)
  main_of <- function(choice) if (identical(choice, "__remove__")) NULL else choice
  complete <- function(value) all(vapply(value[c("account", "main")], function(item) is.character(item) && length(item) == 1L && !is.na(item) && nzchar(item), logical(1L)))
  code_of <- function(error) if (is.null(error$code)) "fifo_wallet_store_invalid" else error$code
  shiny::observeEvent(input$fifo_wallet_preview, {
    value <- key(); notice(NULL)
    if (!complete(value)) { preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_fifo_wallet_error_text_v1("fifo_wallet_input_invalid"))); return() }
    result <- tryCatch(service$preview(value$account, main_of(value$main)), error = function(error) structure(list(), code = code_of(error)))
    if (!is.null(attr(result, "code"))) { preview(NULL); notice(list(tone = "error", title = "Keine Vorschau", copy = data_fifo_wallet_error_text_v1(attr(result, "code")))); return() }
    preview(list(key = value, result = result))
  })
  output$fifo_wallet_hint <- shiny::renderUI({ current <- model(); if (readable(current)) data_fifo_wallet_hint_v1(current) })
  output$fifo_wallet_table <- shiny::renderUI({
    current <- model()
    if (is.null(current)) return(NULL)
    if (!readable(current)) return(portelyra_status_panel("FIFO-Wallet nicht lesbar", data_fifo_wallet_error_text_v1(attr(current, "code")), tone = "warning"))
    data_fifo_wallet_table_v1(current)
  })
  output$fifo_wallet_preview_block <- shiny::renderUI({ current <- preview(); if (is.list(current)) data_fifo_wallet_preview_ui_v1(current$result) })
  output$fifo_wallet_notice <- shiny::renderUI({ current <- notice(); if (is.list(current)) portelyra_status_panel(current$title, current$copy, tone = current$tone) })
  shiny::observeEvent(input$fifo_wallet_save, {
    if (!isTRUE(DATA_FIFO_WALLET_SAVE_V1)) { notice(list(tone = "neutral", title = "Nicht gespeichert", copy = DATA_FIFO_WALLET_SAVE_LATER_V1)); return() }
    current <- preview(); value <- key()
    if (!is.list(current) || !identical(current$key, value)) {
      notice(list(tone = "warning", title = "Nicht gespeichert", copy = "Bitte zuerst die Vorschau zu genau diesen Angaben rechnen.")); return()
    }
    result <- tryCatch(service$record(value$account, main_of(value$main), now_utc(), TRUE), error = function(error) structure(list(), code = code_of(error)))
    if (!is.null(attr(result, "code"))) { notice(list(tone = "error", title = "Nicht gespeichert", copy = data_fifo_wallet_error_text_v1(attr(result, "code")))); return() }
    preview(NULL)
    if (identical(result$status, "unchanged")) { notice(list(tone = "neutral", title = "Nichts geändert", copy = "Diese Zuordnung ist schon gespeichert.")); return() }
    status <- if (is.function(after_write)) tryCatch(after_write(), error = function(error) NULL) else NULL
    copy <- if (identical(status, "published")) "FIFO-Stand fortgeschrieben, Tageshistorie neu veröffentlicht. Steuerergebnisse folgen mit dem nächsten Abschluss."
      else "Der FIFO-Stand ließ sich nicht sofort fortschreiben; „Alles aktualisieren“ holt das nach."
    tick(shiny::isolate(tick()) + 1L)
    notice(list(tone = if (identical(status, "published")) "positive" else "warning",
                title = if (identical(result$status, "removed")) "Zuordnung gelöst" else "Zuordnung gespeichert", copy = copy))
  })
  invisible(list(refresh = function() tick(shiny::isolate(tick()) + 1L), model = model))
}
