# Kontonummer zu einem Konto: IBAN, Depot- oder Kundennummer, bei einem Wallet die eigene Adresse.
# Festlegung (13.10.2026): ein Attribut am Konto - nicht am Institut -, das sich eintragen und durchsuchen laesst.
# Die Angabe liegt neben den Stammdaten: Buchungsbestand, FIFO und Bewertung bleiben unberuehrt.
# Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
data_account_reference_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^account_reference_[a-z_]+$", code)) code <- "account_reference_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_data_account_reference_error_v1", "error", "condition")))
}
# Ein Eingabefeld: Leerraum am Rand faellt weg, Leerraum innen wird zusammengezogen, ein leeres Feld heisst "keine Angabe".
data_account_reference_text_v1 <- function(value) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return(NULL)
  text <- gsub("[ \t]+", " ", trimws(value))
  if (nzchar(text)) text else NULL
}
data_account_reference_number_valid_v1 <- function(value) is.null(value) || (nchar(value) <= 120L && !grepl("[[:cntrl:]]", value))
# Suchschluessel: Gross-/Kleinschreibung und Leerzeichen zaehlen nicht - eine IBAN findet sich mit und ohne Gruppen.
data_account_reference_search_key_v1 <- function(value) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return("")
  tolower(gsub("[[:space:]]+", "", value))
}
data_account_reference_type_label_v1 <- function(type) {
  labels <- c(securities = "Wertpapierdepot", crypto_wallet = "Krypto-Wallet / -Depot", bank = "Bankkonto", cash = "Cash", external = "Extern", other = "Sonstiges")
  if (is.character(type) && length(type) == 1L && type %in% names(labels)) unname(labels[[type]]) else "—"
}
# Die Konten der Stammdaten mit ihrer Kontonummer. `resolve_id` nennt zur Auswahl der Oberflaeche die Kennung des Kontos;
# sie bleibt im Prozess. Archivierte Konten stehen nicht in der Liste.
# `wallets` (#508): je Konto einer FIFO-Wallet aus mehreren Konten der Vermerk, mit wem es FIFO rechnet.
data_account_reference_rows_v1 <- function(accounts, references, resolve_id, wallets = list()) {
  rows <- list()
  for (account in accounts) {
    if (!is.list(account) || identical(account$status, "archived")) next
    id <- tryCatch(resolve_id(account$ref), error = function(error) NULL)
    number <- if (is.character(id) && length(id) == 1L && is.list(references[[id]])) data_account_reference_text_v1(references[[id]]$account_number) else NULL
    institution <- data_account_reference_text_v1(account$institution_label)
    wallet <- if (is.character(id) && length(id) == 1L && is.character(wallets[[id]])) wallets[[id]] else ""
    rows[[length(rows) + 1L]] <- list(ref = account$ref, name = as.character(account$display_name), type = data_account_reference_type_label_v1(account$account_type),
      institution = if (is.null(institution)) "" else institution, number = if (is.null(number)) "" else number, wallet = wallet)
  }
  rows[order(vapply(rows, function(row) tolower(row$name), character(1L)))]
}
# Gefunden ist ein Konto, wenn der Suchtext in Name, Institut, Kontoart oder Kontonummer vorkommt.
data_account_reference_filter_v1 <- function(rows, query) {
  key <- data_account_reference_search_key_v1(query)
  if (!nzchar(key)) return(rows)
  Filter(function(row) any(vapply(c(row$name, row$institution, row$type, row$number),
    function(text) grepl(key, data_account_reference_search_key_v1(text), fixed = TRUE), logical(1L))), rows)
}
data_account_reference_frame_v1 <- function(rows) {
  text <- function(value) if (nzchar(value)) value else "—"
  frame <- data.frame(
    `Konto / Wallet` = vapply(rows, function(row) row$name, character(1L)),
    Kontoart = vapply(rows, function(row) row$type, character(1L)),
    `Institut / Börse` = vapply(rows, function(row) text(row$institution), character(1L)),
    Kontonummer = vapply(rows, function(row) text(row$number), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
  # Die Spalte nur, wenn es eine FIFO-Wallet aus mehreren Konten gibt (#508).
  wallet <- vapply(rows, function(row) if (is.null(row$wallet)) "" else row$wallet, character(1L))
  if (any(nzchar(wallet))) frame$`FIFO-Wallet` <- vapply(wallet, text, character(1L), USE.NAMES = FALSE)
  frame
}
# Aus den Zuordnungen der FIFO-Wallet (#508) je Konto der Vermerk: "gemeinsam mit Hauptkonto" oder "Hauptkonto mit Unterkonto, ...".
data_account_reference_wallets_v1 <- function(entries) {
  result <- list()
  for (entry in entries) {
    if (!is.list(entry) || !is.character(entry$account_id) || !is.character(entry$wallet_account_id)) next
    result[[entry$account_id]] <- paste("FIFO gemeinsam mit", entry$wallet_account_label)
    main <- entry$wallet_account_id
    result[[main]] <- c(result[[main]], entry$account_label)
  }
  for (main in unique(vapply(Filter(function(entry) is.list(entry) && is.character(entry$wallet_account_id), entries),
                             function(entry) entry$wallet_account_id, character(1L))))
    result[[main]] <- paste("Hauptkonto, FIFO gemeinsam mit", paste(sort(result[[main]]), collapse = ", "))
  result
}
new_data_account_reference_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_account_reference.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_account_reference_abort_v1("account_reference_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_account_reference_abort_v1(if (is.null(parsed$code)) "account_reference_store_invalid" else parsed$code)
    parsed$result
  }
  account_id_valid <- function(value) is.character(value) && length(value) == 1L && !is.na(value) && grepl("^acc_[a-z0-9_]{4,60}$", value)
  structure(list(
    contract_version = "data_account_reference_service_v1",
    # Gueltiger Stand je Konto als benannte Liste Kontokennung -> Angaben.
    read = function() {
      result <- run("read", list())
      if (!is.list(result) || !identical(result$status, "ready") || !is.list(result$references) || isTRUE(result$canonical_write))
        data_account_reference_abort_v1("account_reference_store_invalid")
      result
    },
    record = function(account_id, account_number, recorded_at_utc, confirmed) {
      number <- data_account_reference_text_v1(account_number)
      if (!account_id_valid(account_id) || !data_account_reference_number_valid_v1(number)) data_account_reference_abort_v1("account_reference_input_invalid")
      if (!isTRUE(confirmed)) data_account_reference_abort_v1("account_reference_confirmation_required")
      result <- run("record", list(entries = list(list(account_id = account_id, account_number = number)), recorded_at_utc = recorded_at_utc, confirmed = TRUE))
      if (!is.list(result) || !identical(result$status, "recorded") || isTRUE(result$canonical_write))
        data_account_reference_abort_v1("account_reference_store_invalid")
      result
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_account_reference_service_v1", "list"))
}
# Der Bereich selbst (`data_account_reference_ui_v1`) steht bei der Oberflaeche des Asset-Centers, zu der er gehoert.
# Er liest nur: Eingetragen wird die Kontonummer im Kontoformular (#426, 14.10.2026), das dafuer `refresh` aufruft.
# `accounts` liefert die Konten des Katalogs, `resolve_id` die Kennung zu einer Auswahl der Oberflaeche.
data_account_reference_server_v1 <- function(input, output, session, service, accounts, resolve_id, wallet_entries = NULL) {
  tick <- shiny::reactiveVal(0L)
  open <- shiny::reactive(isTRUE(input$account_reference_details_open))
  model <- shiny::reactive({
    tick()
    if (!open()) return(list())
    if (is.null(service)) return(structure(list(), unreadable = TRUE))
    tryCatch(service$read()$references, error = function(error) structure(list(), unreadable = TRUE))
  })
  # Zuordnungen der FIFO-Wallet (#508): Ist der Speicher nicht lesbar, fehlt nur der Vermerk.
  wallets <- shiny::reactive({
    tick()
    if (!open() || !is.function(wallet_entries)) return(list())
    tryCatch(data_account_reference_wallets_v1(wallet_entries()), error = function(error) list())
  })
  rows <- shiny::reactive({ if (!open()) list() else data_account_reference_rows_v1(accounts(), model(), resolve_id, wallets()) })
  output$account_reference_state <- shiny::renderUI({
    if (open() && isTRUE(attr(model(), "unreadable"))) portelyra_status_panel("Kontonummern nicht lesbar",
      "Der Speicher der Kontonummern ließ sich nicht lesen. Konten und Buchungen sind davon nicht berührt.", tone = "warning")
  })
  shown <- shiny::reactive(data_account_reference_filter_v1(rows(), input$account_reference_search))
  output$account_reference_list_hint <- shiny::renderUI({
    if (!open()) return(NULL)
    all_rows <- rows(); found <- shown()
    shiny::p(class = "pl-field-hint", sprintf("%d von %d Konten · %d mit Kontonummer", length(found), length(all_rows),
      sum(vapply(all_rows, function(row) nzchar(row$number), logical(1L)))))
  })
  output$account_reference_list <- shiny::renderTable({
    if (!open()) return(NULL)
    found <- shown()
    if (!length(found)) return(NULL)
    data_account_reference_frame_v1(found)
  }, striped = TRUE, bordered = TRUE)
  invisible(list(rows = rows, refresh = function() tick(shiny::isolate(tick()) + 1L)))
}
# Was eine abgewiesene Kontonummer bedeutet - fuer jede Stelle, die sie schreibt.
data_account_reference_error_text_v1 <- function(code) switch(as.character(code),
  account_reference_input_invalid = "Die Kontonummer ist eine Zeile mit höchstens 120 Zeichen.",
  account_reference_account_unknown = "Dieses Konto gibt es in den Stammdaten nicht mehr. Bitte oben „Stammdaten neu lesen“.",
  "Der Speicher der Kontonummern ließ sich nicht schreiben.")
