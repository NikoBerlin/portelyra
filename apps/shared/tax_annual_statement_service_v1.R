# Jahresrechnung: die voraussichtliche Steuer eines Jahres mit Verrechnung, Freigrenzen, Freistellung und Verlusttoepfen.
# Liest nur - kein Providerzugriff, kein Netzzugriff, kein Write.
tax_annual_statement_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^tax_annual_statement_[a-z_]+$", code)) code <- "tax_annual_statement_source_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_tax_annual_statement_error_v1", "error", "condition")))
}
new_tax_annual_statement_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) || !valid_context ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) tax_annual_statement_abort_v1("tax_annual_statement_input_invalid")
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_tax_annual_statement.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    tax_annual_statement_abort_v1("tax_annual_statement_source_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(paste(output, collapse = "\n"), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      tax_annual_statement_abort_v1(if (is.null(parsed$code)) "tax_annual_statement_source_invalid" else parsed$code)
    parsed$result
  }
  structure(list(
    contract_version = "tax_annual_statement_service_v1",
    build = function(tax_year, generated_at_utc) {
      year <- suppressWarnings(as.integer(tax_year))
      if (length(year) != 1L || is.na(year) || year < 2020L || year > 2100L || !is.character(generated_at_utc) ||
          length(generated_at_utc) != 1L || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", generated_at_utc))
        tax_annual_statement_abort_v1("tax_annual_statement_input_invalid")
      result <- run("build", list(tax_year = year, generated_at_utc = generated_at_utc))
      model <- if (is.list(result)) result$model else NULL
      ready <- is.list(model) && identical(model$status, "ready") && is.list(model$statement)
      # Eine Antwort, die nicht zur Anfrage passt, einen Write behauptet oder sich als Rechtsberatung ausgibt, wird nicht durchgereicht.
      if (!is.list(model) || !identical(model$contract_version, "tax_annual_statement_v1") || !identical(as.integer(model$tax_year), year) ||
          !model$status %in% c("ready", "fifo_state_absent", "fifo_state_stale", "settings_absent", "settings_unreadable", "settings_differ_between_portfolios") ||
          isTRUE(model$canonical_write) || !identical(model$legal_advice, FALSE) || !is.list(model$years) ||
          (ready && (!is.character(result$csv) || length(result$csv) != 1L)))
        tax_annual_statement_abort_v1("tax_annual_statement_source_invalid")
      list(model = model, csv = if (ready) result$csv else NULL, generated_at_utc = generated_at_utc)
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_tax_annual_statement_service_v1", "list"))
}
