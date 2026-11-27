# Unterlagen eines Steuerjahres als ein Archiv: Report, Rechenblaetter, hinterlegte Auszuege, Lueckenliste.
# Der Dienst liest den Datenraum und schreibt genau eine Datei - das Archiv an dem Ort, den der Aufrufer nennt,
# ausserhalb des Datenraums. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
tax_year_documents_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^tax_year_documents_[a-z_]+$", code)) code <- "tax_year_documents_source_invalid"
  stop(structure(list(message = code, call = NULL, code = code),
    class = c("spot_tax_year_documents_error_v1", "error", "condition")))
}
tax_year_documents_scopes_v1 <- function() c(`Konten des Steuerreports` = "report_accounts", `Alle Konten mit Bewegung oder Beleg im Jahr` = "all_accounts")
# Die Auswahl gleicht der des Steuerreports - einschliesslich der Zinsen der Cash-Konten.
tax_year_documents_asset_types_v1 <- function() c(Krypto = "crypto", Aktien = "equity", Fonds = "fund", Rohstoffe = "commodity", Derivate = "derivative", Devisen = "fx",
  `Cash (Zinsen)` = "cash")
new_tax_year_documents_service_v1 <- function(project_root, context, cli_runner = NULL) {
  valid_context <- isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))
  if (!is.character(project_root) || length(project_root) != 1L || !dir.exists(project_root) || !valid_context ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      (!is.null(cli_runner) && !is.function(cli_runner))) tax_year_documents_abort_v1("tax_year_documents_input_invalid")
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_tax_year_documents.py")
  space <- runtime_data_space_path(context)
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    tax_year_documents_abort_v1("tax_year_documents_source_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
    actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command),
      stdout = TRUE, stderr = FALSE, input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(paste(output, collapse = "\n"), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || status != 0L || !identical(parsed$status, "completed"))
      tax_year_documents_abort_v1(if (is.null(parsed$code)) "tax_year_documents_source_invalid" else parsed$code)
    parsed$result
  }
  kinds <- unname(tax_year_documents_asset_types_v1()); scopes <- unname(tax_year_documents_scopes_v1())
  structure(list(
    contract_version = "tax_year_documents_service_v1",
    # `attachments`: Liste aus list(section = "report" | "sheets", name = Dateiname im Archiv, path = fertige Datei).
    build = function(tax_year, asset_types, scope, attachments, target_path, generated_at_utc) {
      year <- suppressWarnings(as.integer(tax_year))
      attachment_valid <- function(item) is.list(item) && setequal(names(item), c("section", "name", "path")) &&
        all(vapply(item, function(value) is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value), logical(1L))) &&
        item$section %in% c("report", "sheets") && grepl("^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$", item$name)
      if (length(year) != 1L || is.na(year) || year < 2000L || year > 2100L || !is.character(asset_types) || !length(asset_types) ||
          anyNA(asset_types) || anyDuplicated(asset_types) || !all(asset_types %in% kinds) || !is.character(scope) || length(scope) != 1L ||
          !scope %in% scopes || !is.list(attachments) || !all(vapply(attachments, attachment_valid, logical(1L))) ||
          !is.character(target_path) || length(target_path) != 1L || is.na(target_path) || !grepl("\\.zip$", target_path) ||
          !is.character(generated_at_utc) || length(generated_at_utc) != 1L ||
          !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", generated_at_utc))
        tax_year_documents_abort_v1("tax_year_documents_input_invalid")
      result <- run("build", list(tax_year = year, asset_types = as.list(asset_types), scope = scope, attachments = unname(attachments),
        target_path = target_path, generated_at_utc = generated_at_utc))
      # Eine Antwort, die nicht zur Anfrage passt, einen Write in den Bestand behauptet oder ein Archiv meldet, das es nicht gibt, wird nicht durchgereicht.
      if (!is.list(result) || !identical(result$contract_version, "tax_year_documents_v1") || !identical(as.integer(result$tax_year), year) ||
          !identical(result$scope, scope) || !result$status %in% c("ready", "fifo_state_absent", "fifo_state_stale") || isTRUE(result$canonical_write) ||
          !identical(isTRUE(result$archive_written), identical(result$status, "ready")) ||
          (isTRUE(result$archive_written) && !file.exists(target_path)))
        tax_year_documents_abort_v1("tax_year_documents_source_invalid")
      result
    },
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE),
    class = c("spot_tax_year_documents_service_v1", "list"))
}
