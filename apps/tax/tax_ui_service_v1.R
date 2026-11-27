tax_ui_service_abort_v1 <- function(code) stop(code, call. = FALSE)
tax_ui_timestamp_v1 <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
tax_ui_context_valid_v1 <- function(context) {
  is.list(context) && all(c("tenant_id", "user_id", "data_space_id") %in% names(context)) &&
    all(vapply(context[c("tenant_id", "user_id", "data_space_id")], function(value) {
      is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[A-Za-z0-9_-]{3,80}$", value)
    }, logical(1)))
}
new_tax_ui_service_v1 <- function(project_root, data_root, context) {
  if (!dir.exists(project_root) || !dir.exists(data_root) || !tax_ui_context_valid_v1(context) ||
      !grepl("^sbx_[a-f0-9]{32}$", context$data_space_id)) tax_ui_service_abort_v1("tax_ui_service_invalid")
  project_root <- normalizePath(project_root, winslash = "/", mustWork = TRUE); data_root <- normalizePath(data_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "tax_ui_workspace.py")
  if (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(data_root))) tax_ui_service_abort_v1("tax_ui_service_invalid")
  data_space <- file.path(data_root, context$tenant_id, context$user_id, context$data_space_id)
  policy_root <- file.path(data_space, "tax-ui")
  store <- file.path(policy_root, "tax-policy.sqlite")
  catalog_args <- c("--activity-data-space", data_space)
  context_args <- c("--tenant-id", context$tenant_id, "--user-id", context$user_id, "--data-space-id", context$data_space_id, "--actor-id", "tax_app")
  run_cli <- function(command, arguments = character(), input = NULL) {
    result <- tryCatch(suppressWarnings(system2(python, vapply(c(cli, command, arguments, context_args), shQuote, character(1)), stdout = TRUE, stderr = TRUE, input = input)), error = function(error) structure(character(), status = 1L))
    status <- attr(result, "status"); if (is.null(status) || length(status) != 1L || is.na(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(result, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed)) tax_ui_service_abort_v1("tax_ui_boundary_failed")
    if (!identical(as.integer(status), 0L) || isTRUE(parsed$status %in% c("blocked", "failed"))) tax_ui_service_abort_v1(if (is.null(parsed$code)) "tax_ui_boundary_failed" else parsed$code)
    parsed
  }
  require_initialized <- function() if (!file.exists(store)) tax_ui_service_abort_v1("tax_ui_not_initialized")
  initialize <- function() {
    current <- data_root
    for (segment in c(context$tenant_id, context$user_id, context$data_space_id, "tax-ui")) {
      current <- file.path(current, segment)
      if (!dir.exists(current)) dir.create(current, recursive = FALSE, mode = "0700")
      if (nzchar(Sys.readlink(current))) tax_ui_service_abort_v1("tax_ui_service_invalid")
      Sys.chmod(current, mode = "0700", use_umask = FALSE)
    }
    if (nzchar(Sys.readlink(policy_root))) tax_ui_service_abort_v1("tax_ui_service_invalid")
    run_cli("init", c("--store", store, "--created-at-utc", tax_ui_timestamp_v1())); invisible(TRUE)
  }
  catalog <- function() { require_initialized(); run_cli("catalog", catalog_args) }
  overview <- function(portfolio_ref, tax_year) { require_initialized(); run_cli("overview", c("--store", store, catalog_args, "--portfolio-ref", portfolio_ref, "--tax-year", as.character(as.integer(tax_year)))) }
  preview <- function(command_type, payload) { require_initialized(); run_cli("preview", c("--store", store, "--command-type", command_type, "--payload-json-stdin", "--created-at-utc", tax_ui_timestamp_v1()), input = as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA))) }
  confirm_apply <- function(preview_ref, confirmed) {
    require_initialized(); if (!isTRUE(confirmed)) tax_ui_service_abort_v1("tax_ui_confirmation_required")
    at <- tax_ui_timestamp_v1(); confirmation <- run_cli("confirm", c("--store", store, "--preview-ref", preview_ref, "--confirmed", "yes", "--confirmed-at-utc", at))
    request_ref <- paste0("req_", substr(digest::digest(paste(confirmation$confirmation_ref, at, context$user_id, sep = "|"), algo = "sha256", serialize = FALSE), 1L, 24L))
    run_cli("apply", c("--store", store, "--confirmation-ref", confirmation$confirmation_ref, "--request-ref", request_ref, "--applied-at-utc", at))
  }
  # Veranlagungsart je Jahr (#498): einzeln oder zusammen, gespeichert neben dem Steuerspeicher.
  assessment_record <- function(tax_year, assessment) {
    require_initialized()
    if (!assessment %in% c("single", "joint")) tax_ui_service_abort_v1("tax_assessment_input_invalid")
    run_cli("assessment-record", c("--store", store, "--tax-year", as.character(as.integer(tax_year)), "--assessment", assessment, "--recorded-at-utc", tax_ui_timestamp_v1()))$result
  }
  # Zaehlt das Portfolio im Jahr zur Veranlagung (#501)? Im selben Speicher wie die Veranlagungsart.
  scope_record <- function(tax_year, counts) {
    require_initialized()
    if (!is.logical(counts) || length(counts) != 1L || is.na(counts)) tax_ui_service_abort_v1("tax_assessment_input_invalid")
    run_cli("assessment-scope-record", c("--store", store, "--tax-year", as.character(as.integer(tax_year)), "--counts", if (counts) "yes" else "no",
                                         "--recorded-at-utc", tax_ui_timestamp_v1()))$result
  }
  # Steuermodul aus ZIP (#486 Schritt 2c): Vorschau schreibt nichts; installiert wird nur bestaetigt und genau die gezeigte Vorschau.
  module_install_preview <- function(zip_path) {
    require_initialized()
    if (!is.character(zip_path) || length(zip_path) != 1L || !file.exists(zip_path)) tax_ui_service_abort_v1("tax_module_install_input_invalid")
    run_cli("module-install-preview", c("--store", store, "--zip", zip_path))$preview
  }
  module_install_apply <- function(zip_path, preview_fingerprint) {
    require_initialized()
    if (!is.character(zip_path) || length(zip_path) != 1L || !file.exists(zip_path) || !is.character(preview_fingerprint) || !nzchar(preview_fingerprint))
      tax_ui_service_abort_v1("tax_module_install_input_invalid")
    run_cli("module-install-apply", c("--store", store, "--zip", zip_path, "--preview-fingerprint", preview_fingerprint, "--installed-at-utc", tax_ui_timestamp_v1(),
                                      "--confirmed", "yes"))$result
  }
  structure(list(contract_version = "tax_ui_service_v1", initialized = function() file.exists(store), initialize = initialize, catalog = catalog, overview = overview, preview = preview, confirm_apply = confirm_apply,
    assessment_record = assessment_record, scope_record = scope_record, module_install_preview = module_install_preview, module_install_apply = module_install_apply, browser_paths_exposed = FALSE, browser_context_exposed = FALSE, fingerprints_exposed = FALSE, provider_access = FALSE, calculation = FALSE), class = c("portelyra_tax_ui_service_v1", "list"))
}
