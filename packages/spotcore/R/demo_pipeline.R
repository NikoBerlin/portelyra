demo_pipeline_error_codes <- function() {
  c(
    "demo_pipeline_context_invalid",
    "demo_pipeline_project_root_invalid",
    "demo_pipeline_worker_failed",
    "demo_pipeline_publication_failed",
    "demo_pipeline_boundary_failed"
  )
}

.demo_pipeline_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% demo_pipeline_error_codes()) {
    stop("unregistered_demo_pipeline_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_demo_pipeline_error", "error", "condition")
  )
}

.demo_pipeline_abort <- function(code) stop(.demo_pipeline_condition(code))

.demo_pipeline_boundary <- function(expression) {
  result <- tryCatch(
    expression,
    spot_demo_pipeline_error = function(error) error,
    spot_demo_portfolio_worker_error = function(error) .demo_pipeline_condition("demo_pipeline_worker_failed"),
    spot_demo_tax_worker_error = function(error) .demo_pipeline_condition("demo_pipeline_worker_failed"),
    error = function(error) .demo_pipeline_condition("demo_pipeline_boundary_failed")
  )
  if (inherits(result, "spot_demo_pipeline_error")) stop(result)
  result
}

.demo_pipeline_project <- function(project_root) {
  if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root) ||
      !dir.exists(project_root) || .canonical_symlink(project_root)) {
    .demo_pipeline_abort("demo_pipeline_project_root_invalid")
  }
  normalized <- tryCatch(normalizePath(project_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized)) .demo_pipeline_abort("demo_pipeline_project_root_invalid")
  cli <- file.path(normalized, "workers", "desktop_demo", "publish_completed_artifact_v1.py")
  if (!file.exists(cli) || dir.exists(cli) || .canonical_symlink(cli) ||
      .canonical_sha256_file(cli) != "f6c20bbc97fad3de9e4401c3fbba839065e3d9a56c4d235b307a9b0b67ea3089") {
    .demo_pipeline_abort("demo_pipeline_project_root_invalid")
  }
  list(root = normalized, publisher = cli)
}

.demo_pipeline_create_area <- function(context, area_id) {
  area_path <- runtime_artifact_area_path(context, area_id)
  segments <- c("artifacts", area_id)
  current <- runtime_data_space_path(context)
  for (segment in segments) {
    current <- file.path(current, segment)
    if (file.exists(current) && !dir.exists(current)) .demo_pipeline_abort("demo_pipeline_publication_failed")
    if (!dir.exists(current) && !dir.create(current, mode = "0700", showWarnings = FALSE)) {
      .demo_pipeline_abort("demo_pipeline_publication_failed")
    }
    if (.canonical_symlink(current) || !dir.exists(current)) .demo_pipeline_abort("demo_pipeline_publication_failed")
    suppressWarnings(Sys.chmod(current, mode = "0700"))
  }
  if (normalizePath(area_path, winslash = "/", mustWork = TRUE) != normalizePath(current, winslash = "/", mustWork = TRUE)) {
    .demo_pipeline_abort("demo_pipeline_publication_failed")
  }
  area_path
}

.demo_pipeline_write_artifact <- function(path, artifact) {
  if (file.exists(path) || .canonical_symlink(path)) .demo_pipeline_abort("demo_pipeline_publication_failed")
  connection <- file(path, open = "wb")
  on.exit(close(connection), add = TRUE)
  writeBin(c(.demo_canonical_json_bytes(artifact), charToRaw("\n")), connection)
  flush(connection)
  suppressWarnings(Sys.chmod(path, mode = "0600"))
  invisible(path)
}

.demo_pipeline_publish_one <- function(
  python,
  publisher,
  artifact_file,
  area_root,
  area_id,
  run_id,
  context,
  artifact_fingerprint,
  published_at_utc
) {
  output <- suppressWarnings(system2(
    python,
    args = c(
      shQuote(publisher),
      "--artifact-file", shQuote(artifact_file),
      "--area-root", shQuote(area_root),
      "--area-id", area_id,
      "--run-id", run_id,
      "--tenant-id", context$tenant_id,
      "--user-id", context$user_id,
      "--data-space-id", context$data_space_id,
      "--writer-id", context$actor_id,
      "--writer-role", context$role,
      "--published-at-utc", published_at_utc
    ),
    stdout = TRUE,
    stderr = FALSE
  ))
  status <- attr(output, "status")
  if (is.null(status)) status <- 0L
  if (length(output) != 1L) .demo_pipeline_abort("demo_pipeline_publication_failed")
  result <- tryCatch(jsonlite::fromJSON(output[[1]], simplifyVector = FALSE), error = function(error) NULL)
  if (!identical(as.integer(status), 0L) || !is.list(result) || !result$status %in% c("published", "already_published")) {
    .demo_pipeline_abort("demo_pipeline_publication_failed")
  }
  required <- c("status", "run_id", "area_id", "artifact_fingerprint", "manifest_fingerprint")
  if (!setequal(names(result), required) || result$run_id != run_id || result$area_id != area_id ||
      result$artifact_fingerprint != artifact_fingerprint ||
      !grepl("^[a-f0-9]{64}$", result$manifest_fingerprint)) {
    .demo_pipeline_abort("demo_pipeline_publication_failed")
  }
  result
}

run_guided_demo_pipeline_v11 <- function(context, project_root) {
  .demo_pipeline_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "desktop_owner") {
      .demo_pipeline_abort("demo_pipeline_context_invalid")
    }
    project <- .demo_pipeline_project(project_root)
    python <- Sys.which("python3")
    if (!nzchar(python)) .demo_pipeline_abort("demo_pipeline_project_root_invalid")
    market <- build_completed_guided_demo_market_v101(
      runtime_context_as(context, "market_worker"),
      "2026-08-04T17:59:00Z",
      "2026-08-04T18:00:00Z"
    )
    portfolio <- build_guided_demo_portfolio_snapshot_v101(
      runtime_context_as(context, "portfolio_worker"),
      market,
      "2026-08-04T18:00:00Z",
      "2026-08-04T18:00:05Z"
    )
    tax <- build_guided_demo_tax_report_v101(
      runtime_context_as(context, "tax_worker"),
      2026L,
      "2026-12-31T23:59:59Z",
      "2027-01-01T00:00:05Z"
    )
    temporary_root <- tempfile(pattern = ".guided-demo-pipeline-", tmpdir = runtime_data_space_path(context))
    if (!dir.create(temporary_root, mode = "0700", showWarnings = FALSE)) {
      .demo_pipeline_abort("demo_pipeline_publication_failed")
    }
    on.exit(unlink(temporary_root, recursive = TRUE, force = TRUE), add = TRUE)
    portfolio_file <- file.path(temporary_root, "portfolio.json")
    tax_file <- file.path(temporary_root, "tax.json")
    .demo_pipeline_write_artifact(portfolio_file, portfolio)
    .demo_pipeline_write_artifact(tax_file, tax)
    portfolio_result <- .demo_pipeline_publish_one(
      python, project$publisher, portfolio_file,
      .demo_pipeline_create_area(context, "portfolio_snapshot"),
      "portfolio_snapshot", paste0("run_guided_", substr(portfolio$artifact_fingerprint, 1L, 24L)),
      runtime_context_as(context, "portfolio_worker"),
      portfolio$artifact_fingerprint, "2026-08-04T18:00:06Z"
    )
    tax_result <- .demo_pipeline_publish_one(
      python, project$publisher, tax_file,
      .demo_pipeline_create_area(context, "tax_report"),
      "tax_report", paste0("run_guided_", substr(tax$artifact_fingerprint, 1L, 24L)),
      runtime_context_as(context, "tax_worker"),
      tax$artifact_fingerprint, "2027-01-01T00:00:06Z"
    )
    list(
      contract_version = 11L,
      status = if (portfolio_result$status == "already_published" && tax_result$status == "already_published") "already_published" else "published",
      source_profile = "guided_native_demo_v1",
      portfolio = portfolio_result,
      tax = tax_result
    )
  })
}

run_desktop_demo_pipeline_v1 <- function(context, project_root) {
  .demo_pipeline_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "desktop_owner") {
      .demo_pipeline_abort("demo_pipeline_context_invalid")
    }
    project <- .demo_pipeline_project(project_root)
    python <- Sys.which("python3")
    if (!nzchar(python)) .demo_pipeline_abort("demo_pipeline_project_root_invalid")
    market <- build_completed_demo_market_v101(
      runtime_context_as(context, "market_worker"),
      "2026-08-04T17:59:00Z",
      "2026-08-04T18:00:00Z"
    )
    portfolio <- build_demo_portfolio_snapshot_v101(
      runtime_context_as(context, "portfolio_worker"),
      market,
      "2026-08-04T18:00:00Z",
      "2026-08-04T18:00:05Z"
    )
    tax <- build_demo_tax_report_v101(
      runtime_context_as(context, "tax_worker"),
      2026L,
      "2026-12-31T23:59:59Z",
      "2027-01-01T00:00:05Z"
    )
    temporary_root <- tempfile(pattern = ".demo-pipeline-", tmpdir = runtime_data_space_path(context))
    if (!dir.create(temporary_root, mode = "0700", showWarnings = FALSE)) {
      .demo_pipeline_abort("demo_pipeline_publication_failed")
    }
    on.exit(unlink(temporary_root, recursive = TRUE, force = TRUE), add = TRUE)
    portfolio_file <- file.path(temporary_root, "portfolio.json")
    tax_file <- file.path(temporary_root, "tax.json")
    .demo_pipeline_write_artifact(portfolio_file, portfolio)
    .demo_pipeline_write_artifact(tax_file, tax)
    portfolio_context <- runtime_context_as(context, "portfolio_worker")
    tax_context <- runtime_context_as(context, "tax_worker")
    portfolio_run_id <- paste0("run_demo_", substr(portfolio$artifact_fingerprint, 1L, 24L))
    tax_run_id <- paste0("run_demo_", substr(tax$artifact_fingerprint, 1L, 24L))
    portfolio_result <- .demo_pipeline_publish_one(
      python, project$publisher, portfolio_file,
      .demo_pipeline_create_area(context, "portfolio_snapshot"),
      "portfolio_snapshot", portfolio_run_id, portfolio_context,
      portfolio$artifact_fingerprint, "2026-08-04T18:00:06Z"
    )
    tax_result <- .demo_pipeline_publish_one(
      python, project$publisher, tax_file,
      .demo_pipeline_create_area(context, "tax_report"),
      "tax_report", tax_run_id, tax_context,
      tax$artifact_fingerprint, "2027-01-01T00:00:06Z"
    )
    list(
      contract_version = 1L,
      status = if (portfolio_result$status == "already_published" && tax_result$status == "already_published") "already_published" else "published",
      portfolio = portfolio_result,
      tax = tax_result
    )
  })
}
