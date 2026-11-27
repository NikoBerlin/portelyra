# Rechenblaetter je Ereignis: Modell und Uebersichtstabelle aus einem Aufruf.
# Liest nur - kein Providerzugriff, kein Netzzugriff, kein Write.
tax_event_sheet_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^tax_event_sheet_[a-z_]+$", code)) code <- "tax_event_sheet_source_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_tax_event_sheet_error_v1", "error", "condition")))
}
# "cash" ist keine Assetklasse des Buchungsbestands: Das Haekchen holt die Zinsertraege der Cash-Konten aus dem Cash-Speicher dazu.
tax_event_sheet_asset_types_v1 <- function() c(Krypto = "crypto", Aktien = "equity", Fonds = "fund", Rohstoffe = "commodity", Derivate = "derivative", Devisen = "fx",
  `Cash (Zinsen)` = "cash")
new_tax_event_sheet_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) || !valid_context ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) tax_event_sheet_abort_v1("tax_event_sheet_input_invalid")
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_tax_event_sheet.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    tax_event_sheet_abort_v1("tax_event_sheet_source_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(paste(output, collapse = "\n"), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      tax_event_sheet_abort_v1(if (is.null(parsed$code)) "tax_event_sheet_source_invalid" else parsed$code)
    parsed$result
  }
  kinds <- unname(tax_event_sheet_asset_types_v1())
  structure(list(
    contract_version = "tax_event_sheet_service_v1",
    build = function(tax_year, asset_types, generated_at_utc, selection = NULL) {
      year <- suppressWarnings(as.integer(tax_year))
      if (length(year) != 1L || is.na(year) || year < 2000L || year > 2100L || !is.character(asset_types) || !length(asset_types) ||
          anyNA(asset_types) || anyDuplicated(asset_types) || !all(asset_types %in% kinds) || !is.character(generated_at_utc) ||
          length(generated_at_utc) != 1L || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", generated_at_utc))
        tax_event_sheet_abort_v1("tax_event_sheet_input_invalid")
      # Dieselbe Auswahl wie im Report (#433); die Pruefung der Marken teilt sich der Dienst mit dem Report.
      chosen <- if (exists("simple_tax_report_selection_v1", mode = "function")) simple_tax_report_selection_v1(selection) else if (is.null(selection)) NULL else FALSE
      if (identical(chosen, FALSE)) tax_event_sheet_abort_v1("tax_event_sheet_input_invalid")
      result <- run("build", c(list(tax_year = year, asset_types = as.list(asset_types), generated_at_utc = generated_at_utc),
        if (!is.null(chosen)) list(selection = chosen)))
      model <- result$model
      # Eine Antwort, die nicht zur Anfrage passt, einen Write behauptet oder sich als Jahressteuer ausgibt, wird nicht durchgereicht.
      if (!is.list(result) || !is.list(model) || !identical(model$contract_version, "tax_event_sheet_v1") ||
          !identical(as.integer(model$tax_year), year) || !model$status %in% c("ready", "fifo_state_absent", "fifo_state_stale") ||
          !is.character(result$csv) || length(result$csv) != 1L || !is.list(model$sheets) || !is.list(model$summary) ||
          !is.list(model$breakdown) || !is.list(model$breakdown$total) || !identical(model$breakdown$offsetting_applied, FALSE) ||
          isTRUE(model$canonical_write) || !identical(model$method$event_tax_is_annual_tax, FALSE) || !identical(model$method$legal_advice, FALSE))
        tax_event_sheet_abort_v1("tax_event_sheet_source_invalid")
      list(model = model, csv = result$csv, generated_at_utc = generated_at_utc)
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_tax_event_sheet_service_v1", "list"))
}
