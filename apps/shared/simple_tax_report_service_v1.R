# Der einfache Steuerreport: Modell, Methode in Worten und Tabelle aus einem Aufruf,
# dazu die festen Hinweise, die auf jedem Report stehen sollen.
# Liest nur - kein Providerzugriff, kein Netzzugriff, kein Write.
simple_tax_report_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^simple_tax_report_[a-z_]+$", code)) code <- "simple_tax_report_source_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_simple_tax_report_error_v1", "error", "condition")))
}
# "cash" ist keine Assetklasse des Buchungsbestands: Das Haekchen holt die Zinsgutschriften der Cash-Konten aus dem Cash-Speicher dazu.
simple_tax_report_asset_types_v1 <- function() c(Krypto = "crypto", Aktien = "equity", Fonds = "fund", Rohstoffe = "commodity", Derivate = "derivative", Devisen = "fx",
  `Cash (Zinsen)` = "cash")
# Anmerkungen aus dem Eingabefeld: eine je Zeile, leere Zeilen fallen weg.
simple_tax_report_notes_v1 <- function(text) {
  if (is.null(text) || !is.character(text) || length(text) != 1L || is.na(text)) return(character())
  lines <- trimws(strsplit(text, "\n", fixed = TRUE)[[1L]])
  lines[nzchar(lines)]
}
new_simple_tax_report_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) || !valid_context ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) simple_tax_report_abort_v1("simple_tax_report_input_invalid")
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_simple_tax_report.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    simple_tax_report_abort_v1("simple_tax_report_source_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(paste(output, collapse = "\n"), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      simple_tax_report_abort_v1(if (is.null(parsed$code)) "simple_tax_report_source_invalid" else parsed$code)
    parsed$result
  }
  kinds <- unname(simple_tax_report_asset_types_v1())
  structure(list(
    contract_version = "simple_tax_report_service_v1",
    # `selection`: list(accounts = Marken, assets = Marken) aus `choices` oder NULL fuer alles (#433).
    build = function(tax_year, asset_types, notes, generated_at_utc, selection = NULL) {
      year <- suppressWarnings(as.integer(tax_year))
      if (length(year) != 1L || is.na(year) || year < 2000L || year > 2100L || !is.character(asset_types) || !length(asset_types) ||
          anyNA(asset_types) || anyDuplicated(asset_types) || !all(asset_types %in% kinds) || !is.character(notes) || anyNA(notes) ||
          length(notes) > 20L || any(nchar(notes) > 2000L) || !is.character(generated_at_utc) || length(generated_at_utc) != 1L ||
          !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", generated_at_utc))
        simple_tax_report_abort_v1("simple_tax_report_input_invalid")
      chosen <- simple_tax_report_selection_v1(selection)
      if (identical(chosen, FALSE)) simple_tax_report_abort_v1("simple_tax_report_input_invalid")
      result <- run("build", c(list(tax_year = year, asset_types = as.list(asset_types), notes = as.list(notes), generated_at_utc = generated_at_utc),
        if (!is.null(chosen)) list(selection = chosen)))
      model <- result$model
      if (!is.list(result) || !is.list(model) || !identical(model$contract_version, "simple_tax_report_v1") ||
          !identical(as.integer(model$tax_year), year) || !model$status %in% c("ready", "fifo_state_absent", "fifo_state_stale") ||
          !is.character(result$csv) || length(result$csv) != 1L || !is.list(result$method_lines) || isTRUE(model$canonical_write) ||
          !identical(model$method$tax_calculated, FALSE)) simple_tax_report_abort_v1("simple_tax_report_source_invalid")
      list(model = model, method_lines = vapply(result$method_lines, as.character, character(1L)), csv = result$csv,
        notes = notes, generated_at_utc = generated_at_utc)
    },
    # Was sich fuer einen Report auswaehlen laesst: Konten und Vermoegenswerte der Klassen, je mit Marke und Namen.
    choices = function(asset_types) {
      if (!is.character(asset_types) || !length(asset_types) || anyNA(asset_types) || anyDuplicated(asset_types) || !all(asset_types %in% kinds))
        simple_tax_report_abort_v1("simple_tax_report_input_invalid")
      result <- run("choices", list(asset_types = as.list(asset_types)))
      token <- function(rows, prefix) is.list(rows) && all(vapply(rows, function(row) is.character(row$token) && grepl(paste0("^", prefix, "_[a-f0-9]{24}$"), row$token) &&
        is.character(row$label), logical(1L)))
      if (!is.list(result) || !token(result$accounts, "kto") || !token(result$assets, "vmw") || isTRUE(result$canonical_write))
        simple_tax_report_abort_v1("simple_tax_report_source_invalid")
      result
    },
    # Die festen Hinweise des Datenraums, eine Zeile je Hinweis. Ohne Speicher gibt es keine.
    read_notes = function() {
      result <- run("notes-read", list())
      if (!is.list(result) || !identical(result$status, "ready") || !is.list(result$notes) || isTRUE(result$canonical_write) ||
          !all(vapply(result$notes, function(note) is.character(note) && length(note) == 1L && !is.na(note) && nzchar(note), logical(1L))))
        simple_tax_report_abort_v1("simple_tax_report_source_invalid")
      vapply(result$notes, as.character, character(1L))
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_simple_tax_report_service_v1", "list"))
}
# Eine Auswahl fuer den Rechenkern: NULL ohne Auswahl, FALSE bei unzulaessiger Eingabe.
simple_tax_report_selection_v1 <- function(selection) {
  if (is.null(selection)) return(NULL)
  if (!is.list(selection) || !all(names(selection) %in% c("accounts", "assets"))) return(FALSE)
  clean <- list()
  for (kind in names(selection)) {
    value <- selection[[kind]]
    if (is.null(value) || !length(value)) next
    if (!is.character(value) || anyNA(value) || anyDuplicated(value) || !all(grepl(paste0("^", if (kind == "accounts") "kto" else "vmw", "_[a-f0-9]{24}$"), value))) return(FALSE)
    clean[[kind]] <- as.list(value)
  }
  if (length(clean)) clean else NULL
}
# Kurze Auskunft zur Karte: was der erstellte Report enthaelt.
simple_tax_report_summary_v1 <- function(model) {
  if (!is.list(model) || !identical(model$contract_version, "simple_tax_report_v1")) return(NULL)
  lots <- sum(vapply(model$disposals, function(item) length(item$lots), integer(1L)))
  list(
    status = model$status,
    disposal_count = length(model$disposals), lot_row_count = lots,
    without_value_count = sum(vapply(model$disposals, function(item) !isTRUE(item$value_recorded), logical(1L))),
    daily_value_count = sum(vapply(model$disposals, function(item) identical(item$value_source, "daily_value"), logical(1L))),
    owner_value_count = sum(vapply(model$disposals, function(item) identical(item$value_source, "owner_entered"), logical(1L))),
    # Abgaenge nach Zweck: unentgeltliche zaehlen nicht als Veraeusserung; ohne Einordnung wird vorsorglich veraeussert.
    gratuitous_count = length(model$gratuitous_transfers),
    unclassified_count = sum(vapply(model$disposals, function(item) identical(item$treatment_code, "purpose_unclassified"), logical(1L))),
    income_count = length(model$income), transfer_count = length(model$transfers), asset_fee_event_count = length(model$asset_fees),
    # Zinsen der Cash-Konten: Zahl der Gutschriften und der Konten, auf denen sie stehen.
    interest_count = length(model$interest), interest_account_count = length(model$interest_totals),
    ledger_kinds = any(unlist(model$asset_types) != "cash"),
    holding_rows = vapply(model$holdings, length, integer(1L)), missing_identifier_count = length(model$missing_identifiers))
}
