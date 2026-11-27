# Owner-lokale Kursangaben: lesen und ausdruecklich bestaetigt eintragen.
# Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write (#283 Punkt 2).
data_manual_price_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^manual_price_[a-z_]+$", code)) code <- "manual_price_store_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_data_manual_price_error_v1", "error", "condition")))
}
new_data_manual_price_service_v1 <- function(project_root, context) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_manual_price.py")
  space <- runtime_data_space_path(context)
  if (!nzchar(python) || !file.exists(cli) || !dir.exists(space)) data_manual_price_abort_v1("manual_price_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id)
  run <- function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = TRUE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      data_manual_price_abort_v1(if (is.null(parsed$code)) "manual_price_store_invalid" else parsed$code)
    parsed$result
  }
  structure(list(
    contract_version = "data_manual_price_service_v1",
    read = function(asset_id) run("read", list(asset_id = asset_id)),
    append = function(asset_id, price_date, value, currency, recorded_at_utc, confirmed)
      run("append", list(asset_id = asset_id, price_date = price_date, value = value,
        currency = currency, recorded_at_utc = recorded_at_utc, confirmed = isTRUE(confirmed))),
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_data_manual_price_service_v1", "list"))
}
