display_reader_error_codes <- function() {
  c(
    "display_context_invalid",
    "display_data_root_invalid",
    "display_project_root_invalid",
    "display_symlink_rejected",
    "display_no_latest",
    "display_reader_failed",
    "display_artifact_shape_invalid",
    "display_artifact_fingerprint_invalid",
    "display_artifact_time_invalid",
    "display_boundary_failed"
  )
}

.display_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% display_reader_error_codes()) {
    stop("unregistered_display_reader_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_display_reader_error", "error", "condition")
  )
}

.display_abort <- function(code) stop(.display_condition(code))

.display_boundary <- function(expression) {
  result <- tryCatch(
    expression,
    spot_display_reader_error = function(error) error,
    error = function(error) .display_condition("display_boundary_failed")
  )
  if (inherits(result, "spot_display_reader_error")) stop(result)
  result
}

.display_symlink <- function(path) {
  target <- suppressWarnings(Sys.readlink(path))
  length(target) == 1L && !is.na(target) && nzchar(target)
}

new_desktop_display_context <- function(data_root, role) {
  .display_boundary({
    if (!is.character(data_root) || length(data_root) != 1L || is.na(data_root) ||
        !dir.exists(data_root) || .display_symlink(data_root)) {
      .display_abort("display_data_root_invalid")
    }
    normalized <- tryCatch(normalizePath(data_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
    if (is.null(normalized) || .display_symlink(normalized)) .display_abort("display_data_root_invalid")
    if (!is.character(role) || length(role) != 1L || is.na(role) || !role %in% c("viewer", "tax_viewer", "analysis_viewer")) {
      .display_abort("display_context_invalid")
    }
    structure(
      list(
        contract_version = 1L,
        runtime_mode = "desktop_demo",
        tenant_id = "local",
        user_id = "demo_user",
        data_space_id = "sbx_demo01",
        role = role,
        trusted_source = "desktop_display_adapter",
        data_root = normalized
      ),
      class = "spot_display_context_v1"
    )
  })
}

new_desktop_product_display_context_v1 <- function(
  data_root, role, tenant_id, user_id, data_space_id
) {
  .display_boundary({
    valid <- function(value, minimum = 3L, maximum = 80L) {
      is.character(value) && length(value) == 1L && !is.na(value) &&
        nchar(value, type = "bytes") >= minimum && nchar(value, type = "bytes") <= maximum &&
        grepl("^[A-Za-z0-9_-]+$", value)
    }
    if (!is.character(data_root) || length(data_root) != 1L || !dir.exists(data_root) || .display_symlink(data_root) ||
        !role %in% c("viewer", "tax_viewer", "analysis_viewer") || !valid(tenant_id) || !valid(user_id) ||
        !valid(data_space_id, 8L, 64L) || !startsWith(data_space_id, "sbx_")) .display_abort("display_context_invalid")
    normalized <- tryCatch(normalizePath(data_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
    if (is.null(normalized) || .display_symlink(normalized)) .display_abort("display_data_root_invalid")
    structure(list(
      contract_version = 3L, runtime_mode = "desktop_product", tenant_id = tenant_id,
      user_id = user_id, data_space_id = data_space_id, role = role,
      trusted_source = "desktop_product_registry", data_root = normalized
    ), class = c("spot_display_context_v3", "spot_display_context_v1"))
  })
}

new_sandbox_display_context_v2 <- function(
  data_root, role, tenant_id, user_id, data_space_id
) {
  .display_boundary({
    valid_context_value <- function(value, minimum = 3L, maximum = 80L) {
      is.character(value) && length(value) == 1L && !is.na(value) &&
        nchar(value, type = "bytes") >= minimum && nchar(value, type = "bytes") <= maximum &&
        grepl("^[A-Za-z0-9_-]+$", value)
    }
    if (!is.character(data_root) || length(data_root) != 1L || is.na(data_root) ||
        !dir.exists(data_root) || .display_symlink(data_root) ||
        !role %in% c("viewer", "tax_viewer", "analysis_viewer") ||
        !valid_context_value(tenant_id) || !valid_context_value(user_id) ||
        !valid_context_value(data_space_id, 8L, 64L) || !startsWith(data_space_id, "sbx_")) {
      .display_abort("display_context_invalid")
    }
    normalized <- tryCatch(
      normalizePath(data_root, winslash = "/", mustWork = TRUE),
      error = function(error) NULL
    )
    if (is.null(normalized) || .display_symlink(normalized)) .display_abort("display_data_root_invalid")
    structure(
      list(
        contract_version = 2L,
        runtime_mode = "local_sandbox",
        tenant_id = tenant_id,
        user_id = user_id,
        data_space_id = data_space_id,
        role = role,
        trusted_source = "server_owned_display_context",
        data_root = normalized
      ),
      class = c("spot_display_context_v2", "spot_display_context_v1")
    )
  })
}

display_context_from_environment_v1 <- function(data_root, role) {
  values <- Sys.getenv(
    c("SPOTTRADING_NEXT_TENANT_ID", "SPOTTRADING_NEXT_USER_ID", "SPOTTRADING_NEXT_DATA_SPACE_ID"),
    unset = ""
  )
  if (!any(nzchar(values))) return(new_desktop_display_context(data_root, role))
  if (!all(nzchar(values))) .display_abort("display_context_invalid")
  new_sandbox_display_context_v2(data_root, role, values[[1L]], values[[2L]], values[[3L]])
}

display_context_valid <- function(context) {
  required <- c(
    "contract_version", "runtime_mode", "tenant_id", "user_id", "data_space_id",
    "role", "trusted_source", "data_root"
  )
  common <- inherits(context, "spot_display_context_v1") && identical(names(context), required) &&
    context$role %in% c("viewer", "tax_viewer", "analysis_viewer") && dir.exists(context$data_root) &&
    !.display_symlink(context$data_root) &&
    identical(tryCatch(normalizePath(context$data_root, winslash = "/", mustWork = TRUE), error = function(error) NA_character_), context$data_root)
  if (!common) return(FALSE)
  if (identical(context$contract_version, 1L)) {
    return(
      identical(context$runtime_mode, "desktop_demo") && identical(context$tenant_id, "local") &&
        identical(context$user_id, "demo_user") && identical(context$data_space_id, "sbx_demo01") &&
        identical(context$trusted_source, "desktop_display_adapter")
    )
  }
  valid <- function(value, minimum = 3L, maximum = 80L) {
    is.character(value) && length(value) == 1L && !is.na(value) &&
      nchar(value, type = "bytes") >= minimum && nchar(value, type = "bytes") <= maximum &&
      grepl("^[A-Za-z0-9_-]+$", value)
  }
  if (identical(context$contract_version, 2L)) {
    return(identical(context$runtime_mode, "local_sandbox") &&
      identical(context$trusted_source, "server_owned_display_context") &&
      valid(context$tenant_id) && valid(context$user_id) &&
      valid(context$data_space_id, 8L, 64L) && startsWith(context$data_space_id, "sbx_"))
  }
  identical(context$contract_version, 3L) && identical(context$runtime_mode, "desktop_product") &&
    identical(context$trusted_source, "desktop_product_registry") &&
    valid(context$tenant_id) && valid(context$user_id) &&
    valid(context$data_space_id, 8L, 64L) && startsWith(context$data_space_id, "sbx_")
}

display_artifact_area_path <- function(context, area_id) {
  .display_boundary({
    if (!display_context_valid(context) || !is.character(area_id) || length(area_id) != 1L ||
        is.na(area_id) || !area_id %in% c("portfolio_snapshot", "group_projection", "tax_report", "analysis_snapshot", "trade_analysis", "market_analysis", "desktop_workflow", "portfolio_history", "portfolio_history_parts", "display_settings", "data_basis")) {
      .display_abort("display_context_invalid")
    }
    if ((area_id %in% c("portfolio_snapshot", "group_projection") && context$role != "viewer") ||
        (area_id == "tax_report" && context$role != "tax_viewer") ||
        (area_id == "analysis_snapshot" && context$role != "analysis_viewer") ||
        (area_id == "trade_analysis" && !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) ||
        (area_id == "market_analysis" && !context$role %in% c("viewer", "analysis_viewer")) ||
        (area_id == "desktop_workflow" && !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) ||
        (area_id %in% c("portfolio_history", "portfolio_history_parts") && !identical(context$role, "analysis_viewer")) ||
        (area_id == "display_settings" && !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) ||
        (area_id == "data_basis" && !identical(context$role, "viewer"))) {
      .display_abort("display_context_invalid")
    }
    segments <- c(context$tenant_id, context$user_id, context$data_space_id, "artifacts", area_id)
    current <- context$data_root
    for (segment in segments) {
      current <- file.path(current, segment)
      if (.display_symlink(current)) .display_abort("display_symlink_rejected")
      if (!dir.exists(current)) .display_abort("display_no_latest")
      normalized <- tryCatch(normalizePath(current, winslash = "/", mustWork = TRUE), error = function(error) NULL)
      if (is.null(normalized) || !startsWith(paste0(normalized, "/"), paste0(context$data_root, "/"))) {
        .display_abort("display_data_root_invalid")
      }
    }
    current
  })
}

.display_project_reader <- function(project_root) {
  if (!is.character(project_root) || length(project_root) != 1L || is.na(project_root) ||
      !dir.exists(project_root) || .display_symlink(project_root)) {
    .display_abort("display_project_root_invalid")
  }
  normalized <- tryCatch(normalizePath(project_root, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized)) .display_abort("display_project_root_invalid")
  reader <- file.path(normalized, "apps", "desktop_demo", "read_latest_artifact_v1.py")
  if (!file.exists(reader) || dir.exists(reader) || .display_symlink(reader)) {
    .display_abort("display_project_root_invalid")
  }
  connection <- file(reader, open = "rb")
  on.exit(close(connection), add = TRUE)
  bytes <- readBin(connection, what = "raw", n = file.info(reader)$size)
  if (digest::digest(bytes, algo = "sha256", serialize = FALSE) != "e3ecbdf6596756972e2a082ff05c042c4dced83a873bdf011bacee6136436de8") {
    .display_abort("display_project_root_invalid")
  }
  reader
}

.display_sorted_value <- function(value) {
  if (!is.list(value)) return(value)
  value <- lapply(value, .display_sorted_value)
  value_names <- names(value)
  if (!is.null(value_names) && length(value_names) && all(nzchar(value_names))) {
    value <- value[order(value_names, method = "radix")]
  }
  value
}

.display_fingerprint <- function(value) {
  bytes <- charToRaw(enc2utf8(as.character(jsonlite::toJSON(
    .display_sorted_value(value), auto_unbox = TRUE, null = "null", na = "null",
    digits = NA, pretty = FALSE
  ))))
  digest::digest(bytes, algo = "sha256", serialize = FALSE)
}

.display_utc_valid <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", value)) return(FALSE)
  parsed <- suppressWarnings(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
  !is.na(parsed) && format(parsed, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") == value
}

.display_decimal_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && value != "-0" &&
    nchar(value, type = "bytes") <= 80L &&
    grepl("^-?(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value)
}

.display_read_latest <- function(context, project_root, area_id, with_text = FALSE) {
  area_root <- display_artifact_area_path(context, area_id)
  reader <- .display_project_reader(project_root)
  python <- Sys.which("python3")
  if (!nzchar(python)) .display_abort("display_project_root_invalid")
  output <- suppressWarnings(system2(
    python,
    args = c(
      shQuote(reader), "--area-root", shQuote(area_root), "--area-id", area_id,
      "--tenant-id", context$tenant_id, "--user-id", context$user_id,
      "--data-space-id", context$data_space_id, "--role", context$role
    ),
    stdout = TRUE,
    stderr = FALSE
  ))
  status <- attr(output, "status")
  if (is.null(status)) status <- 0L
  if (!identical(as.integer(status), 0L) || length(output) != 1L) {
    error_payload <- tryCatch(jsonlite::fromJSON(output[[1]], simplifyVector = FALSE), error = function(error) NULL)
    if (is.list(error_payload) && identical(error_payload$code, "run_publication_no_latest")) {
      .display_abort("display_no_latest")
    }
    .display_abort("display_reader_failed")
  }
  artifact <- tryCatch(jsonlite::fromJSON(output[[1]], simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(artifact)) .display_abort("display_reader_failed")
  if (isTRUE(with_text)) return(list(artifact = artifact, text = output[[1]]))
  artifact
}

# Abdruck aus den gelieferten Bytes (rc.298): Der Leser gibt das Artefakt in kanonischer Form aus (Schluessel sortiert, ohne
# Leerzeichen). Ohne seinen ersten Schluessel "artifact_fingerprint" ist das genau die Form, ueber die der Abdruck gerechnet ist.
# Das erspart das erneute Serialisieren in R (bei einer grossen Tageshistorie mehrere Sekunden); gelesen wird dasselbe, was gehasht wurde.
.display_fingerprint_from_text <- function(text) {
  if (!is.character(text) || length(text) != 1L || is.na(text)) return(NA_character_)
  prefix <- regmatches(text, regexpr('^\\{"artifact_fingerprint":"[a-f0-9]{64}",', text))
  if (length(prefix) != 1L) return(NA_character_)
  payload <- paste0("{", substr(text, nchar(prefix) + 1L, nchar(text)))
  digest::digest(charToRaw(enc2utf8(payload)), algo = "sha256", serialize = FALSE)
}

.display_source_valid <- function(source, include_market) {
  keys <- c(
    "canonical_schema_version", "provenance_type", "data_command_type",
    "candidate_fingerprint", "audit_set_fingerprint", "transaction_set_fingerprint",
    "transaction_semantics_evidence_fingerprint"
  )
  if (include_market) keys <- c(keys, "market_snapshot_id", "market_fingerprint")
  is.list(source) && setequal(names(source), keys) && source$canonical_schema_version == 201L &&
    source$provenance_type == "native_data_command" &&
    source$data_command_type %in% c("desktop_demo_seed_v1", "guided_native_demo_v1") &&
    all(vapply(source[c("candidate_fingerprint", "audit_set_fingerprint", "transaction_set_fingerprint", "transaction_semantics_evidence_fingerprint")], function(value) {
      is.character(value) && length(value) == 1L && grepl("^[a-f0-9]{64}$", value)
    }, logical(1))) &&
    (!include_market || (grepl("^mkt_[a-z0-9_]+$", source$market_snapshot_id) && grepl("^[a-f0-9]{64}$", source$market_fingerprint)))
}

read_cockpit_group_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "group_projection")
    required <- c(
      "cockpit_group_artifact_version", "cockpit_group_artifact_id", "status",
      "tenant_id", "user_id", "data_space_id", "portfolio_ref", "portfolio_label",
      "projection_status", "completed_at_utc", "schemes", "selected_scheme_ref",
      "nodes", "drilldown", "reconciliation", "annual_tax", "currency_status",
      "coverage_status", "market_status", "provider_access", "calculation_started",
      "canonical_write", "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$cockpit_group_artifact_version != 1L ||
        artifact$status != "completed" || artifact$tenant_id != context$tenant_id ||
        artifact$user_id != context$user_id || artifact$data_space_id != context$data_space_id ||
        !artifact$projection_status %in% c("completed", "stale") ||
        !artifact$currency_status %in% c("single_currency", "native_currency_slices", "empty") ||
        !artifact$coverage_status %in% c("complete", "unassigned", "not_applicable") ||
        artifact$market_status != "unavailable_m4_required" ||
        !identical(artifact$provider_access, FALSE) ||
        !identical(artifact$calculation_started, FALSE) ||
        !identical(artifact$canonical_write, FALSE) || !length(artifact$schemes) ||
        !is.list(artifact$nodes) || !is.list(artifact$drilldown) ||
        !is.list(artifact$reconciliation) || !is.list(artifact$annual_tax)) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) {
      .display_abort("display_artifact_fingerprint_invalid")
    }
    if (!.display_utc_valid(artifact$completed_at_utc)) .display_abort("display_artifact_time_invalid")
    scheme_refs <- vapply(artifact$schemes, function(scheme) {
      if (!is.list(scheme) || !setequal(names(scheme), c(
        "scheme_ref", "display_name", "scheme_type", "revision_no",
        "effective_from", "status", "projection_status", "currency_status",
        "coverage_status"
      )) || !scheme$scheme_type %in% c("none", "exclusive_hierarchy", "tag_set") ||
          !scheme$status %in% c("active", "archived", "none") ||
          !scheme$projection_status %in% c("completed", "stale") ||
          !scheme$currency_status %in% c("single_currency", "native_currency_slices", "empty") ||
          !scheme$coverage_status %in% c("complete", "unassigned", "not_applicable") ||
          !is.character(scheme$display_name) || length(scheme$display_name) != 1L ||
          is.na(scheme$display_name) || grepl("[[:cntrl:]]", scheme$display_name)) {
        .display_abort("display_artifact_shape_invalid")
      }
      if (is.null(scheme$scheme_ref)) "" else scheme$scheme_ref
    }, character(1L))
    selected_ref <- if (is.null(artifact$selected_scheme_ref)) "" else artifact$selected_scheme_ref
    if (!selected_ref %in% scheme_refs) .display_abort("display_artifact_shape_invalid")
    decimal_fields <- c(
      "remaining_fifo_cost_decimal", "realized_gross_proceeds_decimal",
      "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
      "cash_balance_decimal"
    )
    node_fields <- c(
      "node_ref", "node_kind", "parent_node_ref", "display_name", "scheme_ref",
      "scheme_type", "currency", "asset_count", "position_count", decimal_fields,
      "event_tax_status", "projected_event_tax_decimal", "projected_net_gain_decimal",
      "annual_tax_status", "currency_aggregation_status", "coverage_status"
    )
    for (node in artifact$nodes) {
      if (!is.list(node) || !setequal(names(node), node_fields) ||
          !all(vapply(node[decimal_fields], .display_decimal_valid, logical(1)))) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    drilldown_fields <- c(
      "node_ref", "source_kind", "source_ref", "asset_ref", "account_ref",
      "event_ref", "currency", "remaining_fifo_cost_decimal",
      "realized_gross_gain_decimal", "projected_event_tax_decimal",
      "projected_net_gain_decimal"
    )
    for (row in artifact$drilldown) {
      nullable_decimals <- row[c(
        "remaining_fifo_cost_decimal", "realized_gross_gain_decimal",
        "projected_event_tax_decimal", "projected_net_gain_decimal"
      )]
      if (!is.list(row) || !setequal(names(row), drilldown_fields) ||
          !all(vapply(nullable_decimals, function(value) is.null(value) || .display_decimal_valid(value), logical(1)))) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    reconciliation_fields <- c(
      "parent_node_ref", "currency", "metric_code", "parent_decimal",
      "child_decimal", "reconciliation_status"
    )
    for (row in artifact$reconciliation) {
      if (!is.list(row) || !setequal(names(row), reconciliation_fields)) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    annual_fields <- c(
      "node_ref", "tax_year", "tax_bucket", "currency",
      "taxable_contribution_decimal", "projected_annual_tax_decimal",
      "annual_tax_scope", "projection_status"
    )
    for (row in artifact$annual_tax) {
      if (!is.list(row) || !setequal(names(row), annual_fields) ||
          !.display_decimal_valid(row$taxable_contribution_decimal) ||
          !(is.null(row$projected_annual_tax_decimal) || .display_decimal_valid(row$projected_annual_tax_decimal))) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    forbidden_names <- c(
      "tenant_id", "user_id", "data_space_id", "context_binding_fingerprint",
      "grouping_revision_fingerprint", "row_set_fingerprint", "rules_fingerprint",
      "plugin_input_fingerprint", "plugin_output_fingerprint", "database_path", "internal_id"
    )
    browser_model <- list(
      view_version = 1L, status = "completed",
      projection_status = artifact$projection_status,
      portfolio_ref = artifact$portfolio_ref, portfolio_label = artifact$portfolio_label,
      completed_at_utc = artifact$completed_at_utc, schemes = artifact$schemes,
      selected_scheme_ref = artifact$selected_scheme_ref, nodes = artifact$nodes,
      drilldown = artifact$drilldown, reconciliation = artifact$reconciliation,
      annual_tax = artifact$annual_tax, currency_status = artifact$currency_status,
      coverage_status = artifact$coverage_status, market_status = artifact$market_status,
      provider_access = FALSE, calculation_started = FALSE, canonical_write = FALSE,
      context_authority_from_browser = FALSE
    )
    collect_names <- function(value) {
      if (!is.list(value)) return(character())
      c(names(value), unlist(lapply(value, collect_names), use.names = FALSE))
    }
    if (any(collect_names(browser_model) %in% forbidden_names)) {
      .display_abort("display_artifact_shape_invalid")
    }
    browser_model
  })
}

read_demo_cockpit_latest_v101 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "portfolio_snapshot")
    required <- c(
      "portfolio_snapshot_version", "snapshot_id", "status", "tenant_id", "user_id", "data_space_id",
      "portfolio_id", "portfolio_label", "base_currency", "snapshot_as_of_utc", "completed_at_utc",
      "source", "positions", "cash_balances", "totals", "worker_id", "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$portfolio_snapshot_version != 101L || artifact$status != "completed" ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id || artifact$data_space_id != context$data_space_id ||
        !.display_source_valid(artifact$source, TRUE) || length(artifact$positions) < 1L || length(artifact$cash_balances) < 1L) {
      .display_abort("display_artifact_shape_invalid")
    }
    total_keys <- c(
      "market_value_decimal", "cash_balance_decimal", "net_liquidation_decimal", "fifo_cost_decimal",
      "unrealized_gain_decimal", "realized_gain_pre_tax_decimal", "realized_gain_after_tax_cash_decimal",
      "total_gain_pre_tax_decimal", "total_gain_after_tax_cash_decimal", "fee_cashflow_decimal", "tax_cashflow_decimal"
    )
    if (!is.list(artifact$totals) || !setequal(names(artifact$totals), total_keys) ||
        !all(vapply(artifact$totals, .display_decimal_valid, logical(1)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$snapshot_as_of_utc) || !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$snapshot_as_of_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    list(
      view_version = 101L,
      status = artifact$status,
      portfolio_label = artifact$portfolio_label,
      base_currency = artifact$base_currency,
      snapshot_as_of_utc = artifact$snapshot_as_of_utc,
      completed_at_utc = artifact$completed_at_utc,
      totals = artifact$totals,
      positions = artifact$positions,
      cash_balances = artifact$cash_balances,
      price_status = artifact$positions[[1]]$price_status
    )
  })
}

read_demo_tax_latest_v101 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "tax_viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "tax_report")
    required <- c(
      "tax_report_version", "tax_report_id", "status", "scope_status", "tenant_id", "user_id", "data_space_id",
      "portfolio_id", "portfolio_label", "tax_year", "currency", "method", "report_as_of_utc", "completed_at_utc",
      "source", "disposals", "totals", "worker_id", "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$tax_report_version != 101L || artifact$status != "completed" ||
        artifact$scope_status != "recorded_cash_only_not_a_tax_filing" || artifact$tax_year != 2026L ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id || artifact$data_space_id != context$data_space_id ||
        !.display_source_valid(artifact$source, FALSE) || length(artifact$disposals) < 1L) {
      .display_abort("display_artifact_shape_invalid")
    }
    decimal_keys <- c(
      "disposed_quantity_decimal", "gross_proceeds_decimal", "disposal_fee_paid_decimal",
      "fifo_cost_decimal", "realized_gain_pre_tax_decimal", "recorded_tax_cash_paid_decimal",
      "realized_gain_after_recorded_tax_cash_decimal"
    )
    if (!is.list(artifact$totals) || !setequal(names(artifact$totals), c("disposal_count", decimal_keys)) ||
        artifact$totals$disposal_count != length(artifact$disposals) ||
        !all(vapply(artifact$totals[decimal_keys], .display_decimal_valid, logical(1)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$report_as_of_utc) || !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$report_as_of_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    list(
      view_version = 101L,
      status = artifact$status,
      scope_status = artifact$scope_status,
      portfolio_label = artifact$portfolio_label,
      tax_year = artifact$tax_year,
      currency = artifact$currency,
      method = artifact$method,
      report_as_of_utc = artifact$report_as_of_utc,
      completed_at_utc = artifact$completed_at_utc,
      totals = artifact$totals,
      disposals = artifact$disposals
    )
  })
}

.display_sha_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[a-f0-9]{64}$", value)
}

.display_public_ref_valid <- function(value, nullable = FALSE) {
  if (is.null(value) && nullable) return(TRUE)
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^[a-z][a-z0-9]{2}_[a-f0-9]{24,32}$", value)
}

.display_v2_source_valid <- function(source, include_market) {
  keys <- c(
    "canonical_schema_version", "provenance_type", "candidate_fingerprint",
    "audit_set_fingerprint", "transaction_set_fingerprint",
    "transaction_semantics_evidence_fingerprint"
  )
  if (include_market) keys <- c(keys, "market_snapshot_id", "market_fingerprint", "input_fingerprint")
  is.list(source) && setequal(names(source), keys) &&
    source$canonical_schema_version %in% c(201L, 202L) &&
    source$provenance_type %in% c("native_data_command", "legacy_import") &&
    all(vapply(source[c(
      "candidate_fingerprint", "audit_set_fingerprint", "transaction_set_fingerprint",
      "transaction_semantics_evidence_fingerprint"
    )], .display_sha_valid, logical(1))) &&
    (!include_market || (
      is.character(source$market_snapshot_id) && grepl("^mkt_manual_[a-f0-9]{24}$", source$market_snapshot_id) &&
      .display_sha_valid(source$market_fingerprint) && .display_sha_valid(source$input_fingerprint)
    ))
}

# Stichtagsbild mit Frische je Ebene. Anders als v1/v2 verlangt v3 kein Cash:
# Ein nicht erklaerter Bestand ist nicht null, sondern eine offene Ebene der
# Frischematrix (#373, 26.09.2026).
# Die Fassungen 3 und 4 des Stichtags-Snapshots unterscheiden sich nur im
# Cash-Block und zwei Summen. Ein vor dem Umstieg veroeffentlichter Stand der
# Fassung 3 bleibt der juengste, bis ein neuer entsteht - der Leser der Fassung 4
# nimmt deshalb beide an und liefert fuer Fassung 3 keinen Cash-Block.
# Fassung 5 fuehrt zusaetzlich aus Bewegungen abgeleitete Salden: zwei weitere
# Saldo-Arten, den Zaehler der abgeleiteten Konten und ihren Anteil an der Summe.
.display_portfolio_snapshot_latest <- function(context, project_root, versions) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "portfolio_snapshot")
    version <- if (is.list(artifact)) artifact$portfolio_snapshot_version else NULL
    if (!is.integer(version) || length(version) != 1L || !version %in% versions) .display_abort("display_artifact_shape_invalid")
    with_cash <- version >= 4L
    with_derived <- version >= 5L
    required <- c(
      "portfolio_snapshot_version", "snapshot_id", "status", "snapshot_status", "tenant_id",
      "user_id", "data_space_id", "portfolio_id", "portfolio_label", "base_currency",
      "as_of_date", "completed_at_utc", "freshness", "positions", "excluded_positions",
      "totals", "counts", "market_value_complete", "unrealised_before_fees_and_tax",
      "worker_id", "artifact_fingerprint", if (with_cash) "cash"
    )
    statuses <- c("not_requested", "source_gap", "stale_market", "stale_fifo",
                  "valuation_pending", "complete")
    total_keys <- c("market_value_decimal", "cost_basis_decimal", "unrealised_decimal",
                    "trade_derived_value_decimal", if (with_cash) c("cash_balance_decimal", "net_worth_decimal"),
                    if (with_derived) "cash_derived_balance_decimal")
    # Vorlaeufiger Cash-Stand (#539, seit rc.362): optional, und nur beide Summen zusammen.
    provisional_keys <- if (with_derived) c("cash_provisional_balance_decimal", "net_worth_provisional_decimal") else character()
    if (!is.list(artifact) || !setequal(names(artifact), required) ||
        !identical(artifact$status, "completed") ||
        !artifact$snapshot_status %in% c("complete", "partial") ||
        !identical(artifact$tenant_id, context$tenant_id) ||
        !identical(artifact$user_id, context$user_id) ||
        !identical(artifact$data_space_id, context$data_space_id) ||
        !grepl("^psn_[a-z0-9_]{4,72}$", artifact$snapshot_id) ||
        !grepl("^[A-Z]{3}$", artifact$base_currency) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", artifact$as_of_date) ||
        !is.list(artifact$freshness) || !is.list(artifact$freshness$levels) ||
        !length(artifact$freshness$levels) ||
        !artifact$freshness$overall_status %in% statuses ||
        !is.list(artifact$totals) || !all(total_keys %in% names(artifact$totals)) ||
        !all(names(artifact$totals) %in% c(total_keys, provisional_keys)) ||
        !sum(provisional_keys %in% names(artifact$totals)) %in% c(0L, length(provisional_keys))) {
      .display_abort("display_artifact_shape_invalid")
    }
    for (level in artifact$freshness$levels) {
      if (!is.list(level) || !all(c("level_code", "status", "reason_code") %in% names(level)) ||
          !level$status %in% statuses) .display_abort("display_artifact_shape_invalid")
    }
    # Ein teilweiser Lauf darf sich nicht als vollstaendig ausgeben - und
    # umgekehrt muss ein vollstaendiger es auf jeder Ebene sein.
    if (identical(artifact$snapshot_status, "complete") &&
        (!isTRUE(artifact$market_value_complete) ||
         !identical(artifact$freshness$overall_status, "complete"))) {
      .display_abort("display_artifact_shape_invalid")
    }
    if (with_cash) {
      cash <- artifact$cash
      if (!is.list(cash) || !cash$status %in% c("available", "absent") || !is.list(cash$accounts) ||
          !is.logical(cash$dated_before_as_of) || length(cash$dated_before_as_of) != 1L ||
          (with_derived && (!is.integer(cash$derived_account_count) || length(cash$derived_account_count) != 1L ||
                            cash$derived_account_count < 0L || cash$derived_account_count > cash$counted_account_count ||
                            # Ein abgeleiteter Anteil ohne abgeleitetes Konto - oder umgekehrt - ist kein gueltiger Stand.
                            (cash$derived_account_count > 0L) == is.null(artifact$totals$cash_derived_balance_decimal)))) {
        .display_abort("display_artifact_shape_invalid")
      }
      for (account in cash$accounts) {
        if (!is.list(account) || !all(c("account_label", "currency", "balance_status", "in_total") %in% names(account)) ||
            !is.logical(account$in_total) || length(account$in_total) != 1L ||
            (isTRUE(account$in_total) && (is.null(account$balance_target_decimal) || is.null(account$balance_date))) ||
            # Ein abgeleiteter Saldo nennt den Tag, ab dem summiert ist - und nur er.
            (with_derived && (account$balance_status %in% c("derived_at_as_of", "derived_before_as_of")) == is.null(account$derived_from_date))) {
          .display_abort("display_artifact_shape_invalid")
        }
      }
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$completed_at_utc)) .display_abort("display_artifact_time_invalid")
    list(
      view_version = version,
      snapshot_status = artifact$snapshot_status,
      portfolio_label = artifact$portfolio_label,
      base_currency = artifact$base_currency,
      as_of_date = artifact$as_of_date,
      completed_at_utc = artifact$completed_at_utc,
      freshness = artifact$freshness,
      totals = artifact$totals,
      counts = artifact$counts,
      positions = artifact$positions,
      excluded_positions = artifact$excluded_positions,
      market_value_complete = isTRUE(artifact$market_value_complete),
      cash = if (with_cash) artifact$cash else NULL
    )
  })
}

read_portfolio_snapshot_latest_v3 <- function(context, project_root) {
  value <- .display_portfolio_snapshot_latest(context, project_root, 3L)
  value[setdiff(names(value), "cash")]
}

read_portfolio_snapshot_latest_v4 <- function(context, project_root) {
  .display_portfolio_snapshot_latest(context, project_root, c(3L, 4L))
}

read_portfolio_snapshot_latest_v5 <- function(context, project_root) {
  .display_portfolio_snapshot_latest(context, project_root, c(3L, 4L, 5L))
}


read_cockpit_latest_v2 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "portfolio_snapshot")
    required <- c(
      "portfolio_snapshot_version", "profile", "snapshot_id", "status", "tenant_id", "user_id",
      "data_space_id", "portfolio_id", "portfolio_label", "base_currency", "snapshot_as_of_utc",
      "completed_at_utc", "source", "profiles", "positions", "cash_balances", "totals",
      "worker_id", "artifact_fingerprint"
    )
    allowed_profiles <- c(
      "buy_sell_fee_tax_base_currency_v1", "cash_movement_base_currency_v1",
      "reward_noncash_movement_base_currency_v1"
    )
    total_keys <- c(
      "market_value_decimal", "cash_balance_decimal", "net_liquidation_decimal", "fifo_cost_decimal",
      "unrealized_gain_decimal", "realized_gain_pre_tax_decimal", "realized_gain_after_tax_cash_decimal",
      "total_gain_pre_tax_decimal", "total_gain_after_tax_cash_decimal", "fee_cashflow_decimal", "tax_cashflow_decimal"
    )
    profile_values <- unlist(artifact$profiles, use.names = FALSE)
    if (!setequal(names(artifact), required) || artifact$portfolio_snapshot_version != 2L ||
        artifact$profile != "supported_canonical_portfolio_v1" || artifact$status != "completed" ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id ||
        artifact$data_space_id != context$data_space_id || !grepl("^psn_[a-f0-9]{32}$", artifact$snapshot_id) ||
        !grepl("^[A-Z]{3}$", artifact$base_currency) || !.display_v2_source_valid(artifact$source, TRUE) ||
        !length(profile_values) || anyDuplicated(profile_values) || !all(profile_values %in% allowed_profiles) ||
        !"buy_sell_fee_tax_base_currency_v1" %in% profile_values ||
        !is.list(artifact$positions) || !length(artifact$positions) ||
        !is.list(artifact$cash_balances) || !length(artifact$cash_balances) ||
        !is.list(artifact$totals) || !setequal(names(artifact$totals), total_keys) ||
        !all(vapply(artifact$totals, .display_decimal_valid, logical(1)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    position_decimals <- c(
      "quantity_decimal", "fifo_cost_decimal", "price_decimal", "market_value_decimal",
      "unrealized_gain_decimal", "realized_gain_pre_tax_decimal", "realized_gain_after_tax_cash_decimal",
      "fee_cashflow_decimal", "tax_cashflow_decimal"
    )
    for (position in artifact$positions) {
      if (!is.list(position) || !all(position_decimals %in% names(position)) ||
          !all(vapply(position[position_decimals], .display_decimal_valid, logical(1))) ||
          position$price_status != "manual_completed") .display_abort("display_artifact_shape_invalid")
    }
    for (cash in artifact$cash_balances) {
      if (!is.list(cash) || !setequal(names(cash), c(
        "account_id", "account_label", "cash_asset_id", "currency", "balance_decimal"
      )) || !.display_decimal_valid(cash$balance_decimal)) .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$snapshot_as_of_utc) || !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$snapshot_as_of_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    list(
      view_version = 101L,
      status = artifact$status,
      portfolio_label = artifact$portfolio_label,
      base_currency = artifact$base_currency,
      snapshot_as_of_utc = artifact$snapshot_as_of_utc,
      completed_at_utc = artifact$completed_at_utc,
      totals = artifact$totals,
      positions = artifact$positions,
      cash_balances = artifact$cash_balances,
      price_status = artifact$positions[[1L]]$price_status
    )
  })
}

read_tax_latest_v2 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "tax_viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "tax_report")
    required <- c(
      "tax_report_version", "profile", "tax_report_id", "status", "scope_status", "tenant_id",
      "user_id", "data_space_id", "portfolio_id", "portfolio_label", "tax_year", "currency",
      "method", "profiles", "report_as_of_utc", "completed_at_utc", "source", "disposals",
      "totals", "worker_id", "artifact_fingerprint"
    )
    decimal_keys <- c(
      "disposed_quantity_decimal", "gross_proceeds_decimal", "disposal_fee_paid_decimal",
      "fifo_cost_decimal", "realized_gain_pre_tax_decimal", "recorded_tax_cash_paid_decimal",
      "realized_gain_after_recorded_tax_cash_decimal"
    )
    allowed_profiles <- c(
      "buy_sell_fee_tax_base_currency_v1", "cash_movement_base_currency_v1",
      "reward_noncash_movement_base_currency_v1"
    )
    profile_values <- unlist(artifact$profiles, use.names = FALSE)
    if (!setequal(names(artifact), required) || artifact$tax_report_version != 2L ||
        artifact$profile != "recorded_cash_tax_documentation_v1" || artifact$status != "completed" ||
        artifact$scope_status != "recorded_cash_only_not_a_tax_filing" ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id ||
        artifact$data_space_id != context$data_space_id || !grepl("^txr_[a-f0-9]{32}$", artifact$tax_report_id) ||
        !is.integer(artifact$tax_year) || artifact$method != "fifo_account_asset_v1" ||
        !grepl("^[A-Z]{3}$", artifact$currency) || !.display_v2_source_valid(artifact$source, FALSE) ||
        !length(profile_values) || anyDuplicated(profile_values) || !all(profile_values %in% allowed_profiles) ||
        !"buy_sell_fee_tax_base_currency_v1" %in% profile_values ||
        !is.list(artifact$disposals) || !length(artifact$disposals) ||
        !is.list(artifact$totals) || !setequal(names(artifact$totals), c("disposal_count", decimal_keys)) ||
        artifact$totals$disposal_count != length(artifact$disposals) ||
        !all(vapply(artifact$totals[decimal_keys], .display_decimal_valid, logical(1)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    for (disposal in artifact$disposals) {
      if (!is.list(disposal) || !all(decimal_keys %in% names(disposal)) ||
          !all(vapply(disposal[decimal_keys], .display_decimal_valid, logical(1))) ||
          !is.list(disposal$fifo_allocations) || !length(disposal$fifo_allocations)) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$report_as_of_utc) || !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$report_as_of_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    list(
      view_version = 101L,
      status = artifact$status,
      scope_status = artifact$scope_status,
      portfolio_label = artifact$portfolio_label,
      tax_year = artifact$tax_year,
      currency = artifact$currency,
      method = artifact$method,
      report_as_of_utc = artifact$report_as_of_utc,
      completed_at_utc = artifact$completed_at_utc,
      totals = artifact$totals,
      disposals = artifact$disposals
    )
  })
}

read_trade_analysis_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) {
      .display_abort("display_context_invalid")
    }
    artifact <- .display_read_latest(context, project_root, "trade_analysis")
    required <- c(
      "trade_analysis_artifact_version", "trade_analysis_artifact_id", "status",
      "projection_status", "tenant_id", "user_id", "data_space_id", "portfolio_ref",
      "portfolio_label", "analysis_cutoff_at_utc", "completed_at_utc", "currency_status",
      "source", "metric_definitions", "currency_metrics", "event_timeline",
      "position_history", "period_series", "annual_tax", "plot_series", "disclaimers",
      "market_status", "boundaries", "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$trade_analysis_artifact_version != 1L ||
        artifact$status != "completed" || !artifact$projection_status %in% c("completed", "stale", "partial") ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id ||
        artifact$data_space_id != context$data_space_id ||
        !.display_public_ref_valid(artifact$portfolio_ref) ||
        !is.character(artifact$portfolio_label) || length(artifact$portfolio_label) != 1L ||
        is.na(artifact$portfolio_label) || !nzchar(artifact$portfolio_label) ||
        grepl("[[:cntrl:]]", artifact$portfolio_label) ||
        !artifact$currency_status %in% c("single_currency", "native_currency_slices", "empty") ||
        artifact$market_status != "unavailable_m4_required" ||
        !identical(sort(unlist(artifact$disclaimers, use.names = FALSE)), sort(c(
          "trade_based_no_market_values", "event_tax_is_not_annual_tax",
          "tax_projection_not_legal_advice_or_filing"
        )))) {
      .display_abort("display_artifact_shape_invalid")
    }
    if (!.display_utc_valid(artifact$analysis_cutoff_at_utc) ||
        !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$analysis_cutoff_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    semantic_binding_valid <- function(value) {
      if (!is.list(value) || !length(value)) return(FALSE)
      contracts <- vapply(value, function(row) if (is.list(row) && is.character(row$semantic_contract) && length(row$semantic_contract) == 1L) row$semantic_contract else "", character(1L))
      if (anyDuplicated(contracts) || !all(contracts %in% c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1"))) return(FALSE)
      all(vapply(value, function(row) {
        is.list(row) && setequal(names(row), c("semantic_contract", "source_event_count", "projected_event_count", "coupled_transaction_fact", "automatic_cash_posting_state")) &&
          is.numeric(row$source_event_count) && is.numeric(row$projected_event_count) && row$source_event_count >= row$projected_event_count && row$projected_event_count >= 0 &&
          ((identical(row$semantic_contract, "portfolio_ledger_v1_transaction_fact") && isTRUE(row$coupled_transaction_fact) && identical(row$automatic_cash_posting_state, "unknown")) ||
           (identical(row$semantic_contract, "asset_activity_v1") && identical(row$coupled_transaction_fact, FALSE) && identical(row$automatic_cash_posting_state, "none_created")))
      }, logical(1L)))
    }
    source_required <- c("realized", "event_tax", "annual_tax")
    realized_required <- c("status", "artifact_ref", "algorithm_version", "row_set_fingerprint", "evidence_cutoff_at_utc", "completed_at_utc", "semantic_source_bindings", "semantic_binding_fingerprint")
    if (!is.list(artifact$source) || !setequal(names(artifact$source), source_required) ||
        !is.list(artifact$source$realized) || !setequal(names(artifact$source$realized), realized_required) ||
        !semantic_binding_valid(artifact$source$realized$semantic_source_bindings) || !.display_sha_valid(artifact$source$realized$semantic_binding_fingerprint)) {
      .display_abort("display_artifact_shape_invalid")
    }
    tax_source_valid <- function(value, annual = FALSE) {
      if (!is.list(value) || !.display_sha_valid(value$semantic_binding_fingerprint) ||
          !identical(value$semantic_binding_fingerprint, artifact$source$realized$semantic_binding_fingerprint)) return(FALSE)
      required <- c("status", "artifact_ref", "source_artifact_ref", if (annual) "tax_year", "plugin_id", "plugin_version", "rules_fingerprint", "row_set_fingerprint", "semantic_binding_fingerprint", "readiness_status", "completed_at_utc")
      setequal(names(value), required)
    }
    if ((!is.null(artifact$source$event_tax) && !tax_source_valid(artifact$source$event_tax)) ||
        !all(vapply(artifact$source$annual_tax, tax_source_valid, logical(1L), annual = TRUE))) {
      .display_abort("display_artifact_shape_invalid")
    }
    boundary_names <- c(
      "provider_access", "network_access", "market_calculation", "unrealized_calculation",
      "forecasting", "technical_analysis", "ai_inference", "alarm_eligibility",
      "notification_eligibility", "app_side_calculation", "canonical_write"
    )
    if (!is.list(artifact$boundaries) || !setequal(names(artifact$boundaries), boundary_names) ||
        !all(vapply(artifact$boundaries, identical, logical(1L), FALSE))) {
      .display_abort("display_artifact_shape_invalid")
    }
    metric_fields <- c("metric_code", "domain", "formula_code", "value_semantics", "aggregation_policy", "tax_scope")
    if (!is.list(artifact$metric_definitions) || length(artifact$metric_definitions) != 18L ||
        !all(vapply(artifact$metric_definitions, function(row) is.list(row) && setequal(names(row), metric_fields), logical(1L)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    currency_fields <- c(
      "currency", "position_count", "event_count", "remaining_fifo_cost_decimal",
      "realized_gross_proceeds_decimal", "realized_fifo_cost_decimal",
      "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
      "cash_balance_decimal", "projected_event_tax_decimal",
      "projected_event_net_gain_decimal", "event_tax_status", "cross_currency_aggregation"
    )
    currency_decimals <- c(
      "remaining_fifo_cost_decimal", "realized_gross_proceeds_decimal",
      "realized_fifo_cost_decimal", "realized_gross_gain_decimal", "gross_income_decimal",
      "fee_total_decimal", "cash_balance_decimal"
    )
    nullable_decimal_valid <- function(value) is.null(value) || .display_decimal_valid(value)
    for (row in artifact$currency_metrics) {
      if (!is.list(row) || !setequal(names(row), currency_fields) ||
          !grepl("^[A-Z]{3}$", row$currency) ||
          !all(vapply(row[currency_decimals], .display_decimal_valid, logical(1L))) ||
          !nullable_decimal_valid(row$projected_event_tax_decimal) ||
          !nullable_decimal_valid(row$projected_event_net_gain_decimal) ||
          !row$event_tax_status %in% c("completed", "partial_blocked", "unavailable", "stale") ||
          row$cross_currency_aggregation != "not_performed_without_fx") {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    event_fields <- c(
      "event_ref", "effective_at_utc", "local_date", "event_type", "account_ref",
      "related_account_ref", "asset_ref", "asset_type", "currency", "quantity_decimal",
      "amount_decimal", "fee_decimal", "gross_proceeds_decimal",
      "realized_gross_gain_decimal", "gross_income_decimal", "cash_balance_delta_decimal",
      "fifo_projection_status", "semantic_contract", "coupled_transaction_fact",
      "automatic_cash_posting_created", "tax_bucket", "projected_event_tax_decimal",
      "projected_event_net_gain_decimal", "event_tax_status", "event_tax_failure_code"
    )
    event_decimals <- c(
      "quantity_decimal", "fee_decimal", "gross_proceeds_decimal",
      "realized_gross_gain_decimal", "gross_income_decimal", "cash_balance_delta_decimal"
    )
    for (row in artifact$event_timeline) {
      if (!is.list(row) || !setequal(names(row), event_fields) ||
          !.display_public_ref_valid(row$event_ref) || !.display_public_ref_valid(row$account_ref) ||
          !.display_public_ref_valid(row$related_account_ref, TRUE) || !.display_public_ref_valid(row$asset_ref) ||
          !(is.null(row$effective_at_utc) || .display_utc_valid(row$effective_at_utc)) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$local_date) ||
          !grepl("^[A-Z]{3}$", row$currency) ||
          !nullable_decimal_valid(row$quantity_decimal) ||
          !all(vapply(row[setdiff(event_decimals, "quantity_decimal")], .display_decimal_valid, logical(1L))) ||
          !row$semantic_contract %in% c("portfolio_ledger_v1_transaction_fact", "asset_activity_v1") ||
          !is.logical(row$coupled_transaction_fact) || length(row$coupled_transaction_fact) != 1L ||
          (identical(row$semantic_contract, "portfolio_ledger_v1_transaction_fact") && (!isTRUE(row$coupled_transaction_fact) || !is.null(row$automatic_cash_posting_created))) ||
          (identical(row$semantic_contract, "asset_activity_v1") && (!identical(row$coupled_transaction_fact, FALSE) || !identical(row$automatic_cash_posting_created, FALSE))) ||
          !nullable_decimal_valid(row$amount_decimal) ||
          !nullable_decimal_valid(row$projected_event_tax_decimal) ||
          !nullable_decimal_valid(row$projected_event_net_gain_decimal) ||
          !row$event_tax_status %in% c("completed", "blocked", "unavailable", "stale")) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    position_fields <- c(
      "history_sequence", "event_ref", "effective_at_utc", "position_ref", "account_ref",
      "asset_ref", "currency", "position_quantity_decimal", "fifo_cost_balance_decimal",
      "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal", "cash_balance_decimal"
    )
    position_decimals <- c(
      "position_quantity_decimal", "fifo_cost_balance_decimal",
      "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal", "cash_balance_decimal"
    )
    for (row in artifact$position_history) {
      if (!is.list(row) || !setequal(names(row), position_fields) ||
          !all(vapply(row[c("event_ref", "position_ref", "account_ref", "asset_ref")], .display_public_ref_valid, logical(1L))) ||
          !(is.null(row$effective_at_utc) || .display_utc_valid(row$effective_at_utc)) || !grepl("^[A-Z]{3}$", row$currency) ||
          !all(vapply(row[position_decimals], .display_decimal_valid, logical(1L)))) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    period_fields <- c(
      "period_start", "period_end", "period_granularity", "currency", "event_count",
      "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
      "deposit_decimal", "withdrawal_decimal", "transfer_decimal",
      "projected_event_tax_decimal", "projected_event_net_gain_decimal", "event_tax_status",
      "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal",
      "cumulative_fee_total_decimal", "cumulative_deposit_decimal",
      "cumulative_withdrawal_decimal", "cumulative_transfer_decimal",
      "cumulative_projected_event_tax_decimal", "cumulative_projected_event_net_gain_decimal",
      "source_event_refs"
    )
    period_decimals <- c(
      "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
      "deposit_decimal", "withdrawal_decimal", "transfer_decimal",
      "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal",
      "cumulative_fee_total_decimal", "cumulative_deposit_decimal",
      "cumulative_withdrawal_decimal", "cumulative_transfer_decimal"
    )
    for (row in artifact$period_series) {
      if (!is.list(row) || !setequal(names(row), period_fields) || row$period_granularity != "month" ||
          !grepl("^[A-Z]{3}$", row$currency) ||
          !all(vapply(row[period_decimals], .display_decimal_valid, logical(1L))) ||
          !all(vapply(row[c("projected_event_tax_decimal", "projected_event_net_gain_decimal", "cumulative_projected_event_tax_decimal", "cumulative_projected_event_net_gain_decimal")], nullable_decimal_valid, logical(1L))) ||
          !all(vapply(row$source_event_refs, .display_public_ref_valid, logical(1L)))) {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    annual_fields <- c(
      "tax_year", "row_type", "tax_bucket", "currency", "positive_contribution_decimal",
      "negative_contribution_decimal", "net_contribution_decimal",
      "closing_loss_carryforward_decimal", "allowance_used_decimal",
      "withholding_credit_decimal", "projected_annual_tax_decimal",
      "projected_annual_net_gain_decimal", "defaulted_parameter_codes",
      "projection_status", "failure_code", "disclaimer_code"
    )
    annual_decimals <- c(
      "positive_contribution_decimal", "negative_contribution_decimal",
      "net_contribution_decimal", "closing_loss_carryforward_decimal",
      "allowance_used_decimal", "withholding_credit_decimal"
    )
    for (row in artifact$annual_tax) {
      if (!is.list(row) || !setequal(names(row), annual_fields) ||
          !all(vapply(row[annual_decimals], .display_decimal_valid, logical(1L))) ||
          !nullable_decimal_valid(row$projected_annual_tax_decimal) ||
          !nullable_decimal_valid(row$projected_annual_net_gain_decimal) ||
          !row$projection_status %in% c("completed", "blocked", "stale") ||
          row$disclaimer_code != "model_projection_not_legal_advice") {
        .display_abort("display_artifact_shape_invalid")
      }
    }
    plot_fields <- c(
      "series_ref", "plot_code", "metric_code", "currency", "scope_ref", "tax_scope",
      "series_status", "zero_line_y_basis_points", "points"
    )
    point_fields <- c(
      "point_ref", "period_label", "x_basis_points", "y_basis_points", "value_decimal",
      "point_status", "source_refs"
    )
    coordinate_valid <- function(value) is.null(value) ||
      (is.integer(value) && length(value) == 1L && value >= 0L && value <= 10000L)
    for (series in artifact$plot_series) {
      if (!is.list(series) || !setequal(names(series), plot_fields) ||
          !.display_public_ref_valid(series$series_ref) || !.display_public_ref_valid(series$scope_ref) ||
          !grepl("^[A-Z]{3}$", series$currency) ||
          !series$tax_scope %in% c("none", "event", "annual") ||
          !series$series_status %in% c("completed", "partial_blocked", "unavailable", "stale") ||
          !coordinate_valid(series$zero_line_y_basis_points)) {
        .display_abort("display_artifact_shape_invalid")
      }
      for (point in series$points) {
        if (!is.list(point) || !setequal(names(point), point_fields) ||
            !.display_public_ref_valid(point$point_ref) ||
            !coordinate_valid(point$x_basis_points) || !coordinate_valid(point$y_basis_points) ||
            !nullable_decimal_valid(point$value_decimal) ||
            !point$point_status %in% c("completed", "blocked", "unavailable", "stale") ||
            !all(vapply(point$source_refs, .display_public_ref_valid, logical(1L)))) {
          .display_abort("display_artifact_shape_invalid")
        }
      }
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) {
      .display_abort("display_artifact_fingerprint_invalid")
    }
    annual_states <- if (!length(artifact$source$annual_tax)) character() else
      vapply(artifact$source$annual_tax, `[[`, character(1L), "status")
    source_states <- list(
      realized = artifact$source$realized$status,
      event_tax = if (is.null(artifact$source$event_tax)) "unavailable" else artifact$source$event_tax$status,
      annual_tax = if (!length(annual_states)) "unavailable" else if (any(annual_states == "stale")) "stale" else "completed",
      annual_years = if (!length(artifact$source$annual_tax)) integer() else
        vapply(artifact$source$annual_tax, `[[`, integer(1L), "tax_year")
    )
    browser_model <- list(
      view_version = 1L, status = "completed", projection_status = artifact$projection_status,
      portfolio_ref = artifact$portfolio_ref, portfolio_label = artifact$portfolio_label,
      analysis_cutoff_at_utc = artifact$analysis_cutoff_at_utc,
      completed_at_utc = artifact$completed_at_utc, currency_status = artifact$currency_status,
      source_states = source_states, metric_definitions = artifact$metric_definitions,
      currency_metrics = artifact$currency_metrics, event_timeline = artifact$event_timeline,
      position_history = artifact$position_history, period_series = artifact$period_series,
      annual_tax = artifact$annual_tax, plot_series = artifact$plot_series,
      disclaimers = artifact$disclaimers, market_status = artifact$market_status,
      provider_access = FALSE, calculation_started = FALSE, canonical_write = FALSE,
      context_authority_from_browser = FALSE, internal_id_exposure = FALSE,
      fingerprint_exposure = FALSE
    )
    forbidden_names <- c(
      "tenant_id", "user_id", "data_space_id", "source", "artifact_fingerprint",
      "row_set_fingerprint", "rules_fingerprint", "database_path", "internal_id"
    )
    collect_names <- function(value) {
      if (!is.list(value)) return(character())
      c(names(value), unlist(lapply(value, collect_names), use.names = FALSE))
    }
    if (any(collect_names(browser_model) %in% forbidden_names)) {
      .display_abort("display_artifact_shape_invalid")
    }
    browser_model
  })
}

read_market_analysis_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !context$role %in% c("viewer", "analysis_viewer")) {
      .display_abort("display_context_invalid")
    }
    artifact <- .display_read_latest(context, project_root, "market_analysis")
    required <- c(
      "market_analysis_artifact_version", "market_analysis_artifact_id", "status", "projection_status",
      "tenant_id", "user_id", "data_space_id", "portfolio_ref", "portfolio_label", "target_currency",
      "history_start_date", "analysis_cutoff_date", "completed_at_utc", "source_snapshots",
      "latest_snapshot_ref", "tax_plugin", "metric_definitions", "portfolio_history", "account_history",
      "position_history", "freshness", "allocation", "plot_series", "disclaimers", "boundaries",
      "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$market_analysis_artifact_version != 1L ||
        artifact$status != "completed" || !artifact$projection_status %in% c("completed", "stale", "partial") ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id ||
        artifact$data_space_id != context$data_space_id || !.display_public_ref_valid(artifact$portfolio_ref) ||
        !grepl("^[A-Z]{3}$", artifact$target_currency) || !is.character(artifact$portfolio_label) ||
        length(artifact$portfolio_label) != 1L || !nzchar(artifact$portfolio_label) ||
        grepl("[[:cntrl:]]", artifact$portfolio_label) || !is.list(artifact$source_snapshots) ||
        !length(artifact$source_snapshots) || !is.list(artifact$portfolio_history) ||
        !length(artifact$portfolio_history) || !is.list(artifact$account_history) ||
        !length(artifact$account_history) || !is.list(artifact$position_history) ||
        !length(artifact$position_history) || !is.list(artifact$freshness) ||
        !is.list(artifact$allocation) || !is.list(artifact$plot_series)) {
      .display_abort("display_artifact_shape_invalid")
    }
    if (!.display_utc_valid(artifact$completed_at_utc) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", artifact$history_start_date) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", artifact$analysis_cutoff_date)) {
      .display_abort("display_artifact_time_invalid")
    }
    boundary_names <- c(
      "provider_access", "network_access", "valuation_started", "tax_calculation_started",
      "fx_conversion_started", "trade_metric_composition", "forecasting", "technical_analysis",
      "alarm_eligibility", "notification_eligibility", "app_side_calculation", "canonical_write"
    )
    if (!is.list(artifact$boundaries) || !setequal(names(artifact$boundaries), boundary_names) ||
        !all(vapply(artifact$boundaries, identical, logical(1L), FALSE))) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) {
      .display_abort("display_artifact_fingerprint_invalid")
    }
    metric_fields <- c(
      "market_value_decimal", "fifo_cost_decimal", "unrealized_gross_gain_decimal",
      "projected_tax_decimal", "liquidation_fee_decimal", "net_liquidation_decimal"
    )
    nullable_decimal <- function(value) is.null(value) || .display_decimal_valid(value)
    if (length(artifact$metric_definitions) != 9L ||
        !all(vapply(artifact$portfolio_history, function(row) all(vapply(row[metric_fields], nullable_decimal, logical(1L))), logical(1L))) ||
        !all(vapply(artifact$account_history, function(row) all(vapply(row[metric_fields], nullable_decimal, logical(1L))), logical(1L))) ||
        !all(vapply(artifact$position_history, function(row) {
          all(vapply(row[c(metric_fields, "market_price_decimal")], nullable_decimal, logical(1L))) &&
            .display_decimal_valid(row$quantity_decimal)
        }, logical(1L)))) {
      .display_abort("display_artifact_shape_invalid")
    }
    coordinate <- function(value, nullable = FALSE) {
      if (is.null(value) && nullable) return(TRUE)
      is.integer(value) && length(value) == 1L && value >= 0L && value <= 10000L
    }
    for (series in artifact$plot_series) {
      if (!series$series_status %in% c("completed", "partial", "unavailable", "stale") ||
          !coordinate(series$zero_line_y_basis_points) || !is.list(series$points) || !length(series$points)) {
        .display_abort("display_artifact_shape_invalid")
      }
      for (point in series$points) {
        if (!coordinate(point$x_basis_points) || !coordinate(point$y_basis_points, TRUE) ||
            !nullable_decimal(point$value_decimal) ||
            !point$point_status %in% c("completed", "blocked", "unavailable", "stale")) {
          .display_abort("display_artifact_shape_invalid")
        }
      }
    }
    account_refs <- sort(unique(vapply(artifact$account_history, `[[`, character(1L), "account_ref")))
    position_refs <- sort(unique(vapply(artifact$position_history, `[[`, character(1L), "position_ref")))
    snapshot_refs <- vapply(artifact$source_snapshots, `[[`, character(1L), "snapshot_ref")
    account_ordinal <- stats::setNames(seq_along(account_refs), account_refs)
    position_ordinal <- stats::setNames(seq_along(position_refs), position_refs)
    snapshot_ordinal <- stats::setNames(seq_along(snapshot_refs), snapshot_refs)
    relations_valid <-
      all(vapply(artifact$position_history, function(row) row$account_ref %in% account_refs && row$position_ref %in% position_refs && row$snapshot_ref %in% snapshot_refs, logical(1L))) &&
      all(vapply(artifact$freshness, function(row) row$account_ref %in% account_refs && row$position_ref %in% position_refs, logical(1L))) &&
      all(vapply(artifact$allocation, function(row) row$account_ref %in% account_refs && ((row$scope_kind == "account" && row$scope_ref %in% account_refs) || (row$scope_kind == "position" && row$scope_ref %in% position_refs)), logical(1L))) &&
      all(vapply(artifact$plot_series, function(series) {
        scope_valid <- series$scope_kind == "portfolio" || (series$scope_kind == "account" && series$scope_ref %in% account_refs) || (series$scope_kind == "position" && series$scope_ref %in% position_refs)
        scope_valid && all(vapply(series$points, function(point) point$source_snapshot_ref %in% snapshot_refs, logical(1L)))
      }, logical(1L)))
    if (!relations_valid) .display_abort("display_artifact_shape_invalid")
    without <- function(row, fields) row[setdiff(names(row), fields)]
    sources <- lapply(artifact$source_snapshots, function(row) c(
      list(snapshot_ordinal = unname(snapshot_ordinal[[row$snapshot_ref]])),
      without(row, c("snapshot_ref", "artifact_fingerprint", "row_set_fingerprint", "tax_rules_fingerprint"))
    ))
    portfolio <- lapply(artifact$portfolio_history, function(row) c(
      list(snapshot_ordinal = unname(snapshot_ordinal[[row$snapshot_ref]])), without(row, "snapshot_ref")
    ))
    accounts <- lapply(artifact$account_history, function(row) c(
      list(account_ordinal = unname(account_ordinal[[row$account_ref]]), snapshot_ordinal = unname(snapshot_ordinal[[row$snapshot_ref]])),
      without(row, c("account_ref", "snapshot_ref"))
    ))
    positions <- lapply(artifact$position_history, function(row) c(
      list(position_ordinal = unname(position_ordinal[[row$position_ref]]), account_ordinal = unname(account_ordinal[[row$account_ref]]), snapshot_ordinal = unname(snapshot_ordinal[[row$snapshot_ref]])),
      without(row, c("position_ref", "account_ref", "asset_ref", "snapshot_ref"))
    ))
    freshness <- lapply(artifact$freshness, function(row) c(
      list(position_ordinal = unname(position_ordinal[[row$position_ref]]), account_ordinal = unname(account_ordinal[[row$account_ref]])),
      without(row, c("position_ref", "account_ref", "asset_ref"))
    ))
    allocation <- lapply(artifact$allocation, function(row) {
      scope_ordinal <- if (row$scope_kind == "account") unname(account_ordinal[[row$scope_ref]]) else unname(position_ordinal[[row$scope_ref]])
      c(list(scope_ordinal = scope_ordinal, account_ordinal = unname(account_ordinal[[row$account_ref]])), without(row, c("scope_ref", "account_ref", "position_ref")))
    })
    plots <- lapply(artifact$plot_series, function(series) {
      scope_ordinal <- if (series$scope_kind == "portfolio") 1L else if (series$scope_kind == "account") unname(account_ordinal[[series$scope_ref]]) else unname(position_ordinal[[series$scope_ref]])
      points <- lapply(series$points, function(point) c(
        list(snapshot_ordinal = unname(snapshot_ordinal[[point$source_snapshot_ref]])),
        without(point, c("point_ref", "source_snapshot_ref"))
      ))
      c(list(scope_ordinal = scope_ordinal), without(series, c("series_ref", "scope_ref", "points")), list(points = points))
    })
    plugin <- without(artifact$tax_plugin, c("rules_fingerprint", "manifest_fingerprint"))
    browser <- list(
      view_version = 1L, status = "completed", projection_status = artifact$projection_status,
      portfolio_label = artifact$portfolio_label, target_currency = artifact$target_currency,
      history_start_date = artifact$history_start_date, analysis_cutoff_date = artifact$analysis_cutoff_date,
      completed_at_utc = artifact$completed_at_utc, source_snapshots = sources,
      tax_plugin = plugin, metric_definitions = artifact$metric_definitions,
      portfolio_history = portfolio, account_history = accounts, position_history = positions,
      freshness = freshness, allocation = allocation, plot_series = plots,
      disclaimers = artifact$disclaimers, provider_access = FALSE, calculation_started = FALSE,
      canonical_write = FALSE, context_authority_from_browser = FALSE,
      internal_id_exposure = FALSE, fingerprint_exposure = FALSE
    )
    forbidden <- c(
      "tenant_id", "user_id", "data_space_id", "portfolio_ref", "snapshot_ref", "position_ref",
      "account_ref", "asset_ref", "scope_ref", "series_ref", "point_ref", "source_snapshot_ref",
      "artifact_fingerprint", "row_set_fingerprint", "tax_rules_fingerprint", "rules_fingerprint", "manifest_fingerprint",
      "database_path", "internal_id"
    )
    collect_names <- function(value) {
      if (!is.list(value)) return(character())
      c(names(value), unlist(lapply(value, collect_names), use.names = FALSE))
    }
    if (any(collect_names(browser) %in% forbidden)) .display_abort("display_artifact_shape_invalid")
    browser
  })
}

read_demo_analysis_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || context$role != "analysis_viewer") .display_abort("display_context_invalid")
    artifact <- .display_read_latest(context, project_root, "analysis_snapshot")
    required <- c(
      "analysis_snapshot_version", "analysis_snapshot_id", "status", "scope_status", "tenant_id",
      "user_id", "data_space_id", "portfolio_id", "portfolio_label", "currency",
      "analysis_as_of_utc", "completed_at_utc", "configuration", "source", "metric_definitions",
      "portfolio_metrics", "position_metrics", "boundaries", "worker_id", "artifact_fingerprint"
    )
    if (!setequal(names(artifact), required) || artifact$analysis_snapshot_version != 1L || artifact$status != "completed" ||
        artifact$scope_status != "portfolio_valuation_decomposition_only" ||
        artifact$tenant_id != context$tenant_id || artifact$user_id != context$user_id || artifact$data_space_id != context$data_space_id ||
        !grepl("^ans_[a-f0-9]{32}$", artifact$analysis_snapshot_id) ||
        !grepl("^ptf_[a-z0-9_]+$", artifact$portfolio_id) || !grepl("^[A-Z]{3}$", artifact$currency)) {
      .display_abort("display_artifact_shape_invalid")
    }
    config_keys <- c(
      "analysis_configuration_version", "configuration_id", "tenant_id", "user_id", "data_space_id",
      "portfolio_id", "configuration_status", "analysis_scope_id", "metric_set_version", "metric_ids",
      "revision", "created_at_utc", "created_by_actor", "configuration_fingerprint"
    )
    expected_metric_ids <- c(
      "cash_balance", "fifo_cost", "market_value", "net_liquidation", "position_allocation_fraction",
      "position_count", "realized_gain_pre_tax", "total_gain_pre_tax", "unrealized_gain"
    )
    configuration <- artifact$configuration
    if (!is.list(configuration) || !setequal(names(configuration), config_keys) ||
        configuration$analysis_configuration_version != 1L || configuration$metric_set_version != 1L ||
        configuration$configuration_status != "active" || configuration$analysis_scope_id != "portfolio_valuation_decomposition_v1" ||
        configuration$tenant_id != context$tenant_id || configuration$user_id != context$user_id ||
        configuration$data_space_id != context$data_space_id || configuration$portfolio_id != artifact$portfolio_id ||
        !identical(unlist(configuration$metric_ids, use.names = FALSE), expected_metric_ids) ||
        configuration$configuration_fingerprint != .display_fingerprint(configuration[setdiff(names(configuration), "configuration_fingerprint")])) {
      .display_abort("display_artifact_shape_invalid")
    }
    source_keys <- c("market_snapshot_id", "market_fingerprint", "portfolio_snapshot_id", "portfolio_artifact_fingerprint")
    if (!is.list(artifact$source) || !setequal(names(artifact$source), source_keys) ||
        !grepl("^mkt_[a-z0-9_]+$", artifact$source$market_snapshot_id) ||
        !grepl("^psn_[a-z0-9_]+$", artifact$source$portfolio_snapshot_id) ||
        !grepl("^[a-f0-9]{64}$", artifact$source$market_fingerprint) ||
        !grepl("^[a-f0-9]{64}$", artifact$source$portfolio_artifact_fingerprint)) {
      .display_abort("display_artifact_shape_invalid")
    }
    metric_keys <- c(
      "position_count", "market_value_decimal", "cash_balance_decimal", "net_liquidation_decimal",
      "fifo_cost_decimal", "unrealized_gain_decimal", "realized_gain_pre_tax_decimal", "total_gain_pre_tax_decimal"
    )
    decimal_metric_keys <- setdiff(metric_keys, "position_count")
    if (!is.list(artifact$portfolio_metrics) || !setequal(names(artifact$portfolio_metrics), metric_keys) ||
        !is.integer(artifact$portfolio_metrics$position_count) || artifact$portfolio_metrics$position_count < 1L ||
        !all(vapply(artifact$portfolio_metrics[decimal_metric_keys], .display_decimal_valid, logical(1))) ||
        length(artifact$position_metrics) != artifact$portfolio_metrics$position_count || length(artifact$metric_definitions) != 9L) {
      .display_abort("display_artifact_shape_invalid")
    }
    position_keys <- c(
      "account_id", "account_label", "asset_id", "asset_label", "currency", "market_value_decimal",
      "fifo_cost_decimal", "unrealized_gain_decimal", "allocation_numerator_decimal",
      "allocation_denominator_decimal", "allocation_status"
    )
    position_decimal_keys <- c(
      "market_value_decimal", "fifo_cost_decimal", "unrealized_gain_decimal",
      "allocation_numerator_decimal", "allocation_denominator_decimal"
    )
    if (!all(vapply(artifact$position_metrics, function(position) {
      is.list(position) && setequal(names(position), position_keys) &&
        grepl("^acc_[a-z0-9_]+$", position$account_id) && grepl("^ast_[a-z0-9_]+$", position$asset_id) &&
        grepl("^[A-Z]{3}$", position$currency) && position$allocation_status == "exact_unrounded_fraction" &&
        all(vapply(position[position_decimal_keys], .display_decimal_valid, logical(1))) &&
        !startsWith(position$market_value_decimal, "-") && position$market_value_decimal != "0" &&
        !startsWith(position$fifo_cost_decimal, "-") &&
        !startsWith(position$allocation_denominator_decimal, "-") && position$allocation_denominator_decimal != "0"
    }, logical(1)))) .display_abort("display_artifact_shape_invalid")
    definition_keys <- c("metric_id", "formula_id", "value_type", "opaque_score")
    expected_formula_ids <- c(
      "sum_signed_cash_balances", "sum_position_fifo_cost", "sum_position_market_value",
      "market_value_plus_signed_cash", "position_market_value_over_total_market_value",
      "count_open_valued_positions", "sum_position_realized_gain_pre_tax",
      "unrealized_gain_plus_realized_gain_pre_tax", "sum_market_value_minus_fifo_cost"
    )
    expected_value_types <- c(
      "exact_decimal", "exact_decimal", "exact_decimal", "exact_decimal", "exact_fraction",
      "integer", "exact_decimal", "exact_decimal", "exact_decimal"
    )
    if (!all(vapply(seq_along(artifact$metric_definitions), function(index) {
      definition <- artifact$metric_definitions[[index]]
      is.list(definition) && setequal(names(definition), definition_keys) &&
        definition$metric_id == expected_metric_ids[[index]] &&
        definition$formula_id == expected_formula_ids[[index]] &&
        definition$value_type == expected_value_types[[index]] && identical(definition$opaque_score, FALSE)
    }, logical(1)))) .display_abort("display_artifact_shape_invalid")
    boundary_keys <- c(
      "provider_access", "automatic_refresh", "forecasting", "ai_inference", "alarm_eligibility",
      "notification_eligibility", "app_side_recalculation"
    )
    if (!is.list(artifact$boundaries) || !setequal(names(artifact$boundaries), boundary_keys) ||
        !all(vapply(artifact$boundaries, identical, logical(1), FALSE))) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (artifact$artifact_fingerprint != .display_fingerprint(payload)) .display_abort("display_artifact_fingerprint_invalid")
    if (!.display_utc_valid(artifact$analysis_as_of_utc) || !.display_utc_valid(artifact$completed_at_utc) ||
        as.POSIXct(artifact$completed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") <
          as.POSIXct(artifact$analysis_as_of_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")) {
      .display_abort("display_artifact_time_invalid")
    }
    list(
      view_version = 1L,
      status = artifact$status,
      scope_status = artifact$scope_status,
      portfolio_label = artifact$portfolio_label,
      currency = artifact$currency,
      analysis_as_of_utc = artifact$analysis_as_of_utc,
      completed_at_utc = artifact$completed_at_utc,
      portfolio_metrics = artifact$portfolio_metrics,
      position_metrics = artifact$position_metrics,
      metric_definitions = artifact$metric_definitions
    )
  })
}

read_desktop_workflow_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) {
      .display_abort("display_context_invalid")
    }
    artifact <- .display_read_latest(context, project_root, "desktop_workflow")
    required <- c(
      "desktop_workflow_artifact_version", "desktop_workflow_artifact_id", "status",
      "workflow_status", "attempt_status", "tenant_id", "user_id", "data_space_id",
      "completed_at_utc", "stage_states", "source_bindings", "browser_model", "artifact_fingerprint"
    )
    if (!is.list(artifact) || !setequal(names(artifact), required) ||
        !identical(artifact$desktop_workflow_artifact_version, 1L) || !identical(artifact$status, "completed") ||
        !artifact$workflow_status %in% c("completed", "partial", "stale", "blocked") ||
        !artifact$attempt_status %in% c("running", "completed", "blocked") ||
        !identical(artifact$tenant_id, context$tenant_id) || !identical(artifact$user_id, context$user_id) ||
        !identical(artifact$data_space_id, context$data_space_id) || !.display_utc_valid(artifact$completed_at_utc) ||
        !is.list(artifact$browser_model) || !identical(artifact$browser_model$status, artifact$workflow_status) ||
        !identical(artifact$browser_model$attempt_status, artifact$attempt_status)) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (!identical(artifact$artifact_fingerprint, .display_fingerprint(payload))) {
      .display_abort("display_artifact_fingerprint_invalid")
    }
    collect_names <- function(value) {
      if (!is.list(value)) return(character())
      c(names(value), unlist(lapply(value, collect_names), use.names = FALSE))
    }
    forbidden <- c(
      "tenant_id", "user_id", "data_space_id", "claims", "context", "database_path", "path", "sql",
      "portfolio_id", "account_id", "asset_id", "transaction_id", "run_id", "job_id",
      "portfolio_ref", "account_ref", "asset_ref", "position_ref", "event_ref", "listing_ref",
      "pair_ref", "selection_ref", "snapshot_ref", "artifact_ref", "source_ref", "fingerprint",
      "artifact_fingerprint", "input_fingerprint", "output_fingerprint", "row_set_fingerprint", "semantic_binding_fingerprint"
    )
    browser_names <- collect_names(artifact$browser_model)
    if (any(browser_names %in% forbidden) || !identical(artifact$browser_model$browser_model_version, 1L) ||
        !identical(artifact$browser_model$completed_at_utc, artifact$completed_at_utc)) {
      .display_abort("display_artifact_shape_invalid")
    }
    artifact$browser_model
  })
}

# Tageshistorie (#473): die veroeffentlichte Reihe fuer die Analyse - je Tag die Portfoliosummen, je Asset Menge, Kurs,
# Wert, Einstand und Zu- und Abgaenge. Das Schema prueft der Leser beim Lesen; hier nur Form, Zuordnung und Abdruck.
read_portfolio_history_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !identical(context$role, "analysis_viewer")) .display_abort("display_context_invalid")
    read <- .display_read_latest(context, project_root, "portfolio_history", with_text = TRUE)
    artifact <- read$artifact
    required <- c(
      "portfolio_history_version", "portfolio_history_id", "status", "tenant_id", "user_id", "data_space_id", "currency",
      "first_day", "last_day", "day_count", "portfolio", "investment", "assets", "classes", "net", "benchmarks", "groups", "partitions", "content_fingerprint", "completed_at_utc",
      "provider_access", "network_access", "canonical_write", "artifact_fingerprint"
    )
    # "watched" (seit rc.369, #526): beobachtete, nie gehaltene Assets mit Kursreihe; aeltere Staende haben das Feld nicht.
    if (!is.list(artifact) || !(setequal(names(artifact), required) || setequal(names(artifact), c(required, "watched"))) ||
        !identical(artifact$portfolio_history_version, 1L) ||
        !identical(artifact$status, "completed") || !identical(artifact$tenant_id, context$tenant_id) ||
        !identical(artifact$user_id, context$user_id) || !identical(artifact$data_space_id, context$data_space_id) ||
        !.display_utc_valid(artifact$completed_at_utc) || !is.list(artifact$portfolio) || !is.list(artifact$investment) || !is.list(artifact$assets) ||
        !identical(length(artifact$portfolio$day), as.integer(artifact$day_count)) ||
        !isFALSE(artifact$provider_access) || !isFALSE(artifact$network_access) || !isFALSE(artifact$canonical_write)) {
      .display_abort("display_artifact_shape_invalid")
    }
    if (!identical(artifact$artifact_fingerprint, .display_fingerprint_from_text(read$text))) .display_abort("display_artifact_fingerprint_invalid")
    shown <- artifact[c("first_day", "last_day", "day_count", "currency", "completed_at_utc", "portfolio", "investment", "assets", "classes", "net", "benchmarks", "groups", "partitions")]
    shown$watched <- if (is.list(artifact$watched)) artifact$watched else list()
    shown
  })
}

# Teildatei der Tageshistorie (#503): die Tagesreihen eines Assets, einer Klasse oder einer Gruppe, erst bei Bedarf gelesen.
# 'part' ist der Verweis aus dem geprueften Kern (SHA-256 der Bytes). Der Schreiber hat die Datei gegen part.schema.json
# geprueft; hier zaehlen Abdruck, Zuordnung und Form. Fehlt die Datei, ist der gelesene Kern inzwischen ersetzt worden.
read_portfolio_history_part_v1 <- function(context, part) {
  .display_boundary({
    if (!display_context_valid(context) || !identical(context$role, "analysis_viewer") || !is.character(part) || length(part) != 1L ||
        is.na(part) || !grepl("^[a-f0-9]{64}$", part)) .display_abort("display_context_invalid")
    area <- tryCatch(display_artifact_area_path(context, "portfolio_history_parts"), spot_display_reader_error = function(error) {
      if (identical(error$code, "display_no_latest")) .display_abort("display_no_latest") else stop(error)
    })
    path <- file.path(area, paste0(part, ".json"))
    if (.display_symlink(path)) .display_abort("display_symlink_rejected")
    info <- file.info(path)
    if (is.na(info$size) || isTRUE(info$isdir)) .display_abort("display_no_latest")
    if (info$size > 20000000) .display_abort("display_artifact_shape_invalid")
    connection <- file(path, open = "rb")
    on.exit(close(connection), add = TRUE)
    bytes <- readBin(connection, what = "raw", n = info$size)
    if (!identical(digest::digest(bytes, algo = "sha256", serialize = FALSE), part)) .display_abort("display_artifact_fingerprint_invalid")
    text <- rawToChar(bytes); Encoding(text) <- "UTF-8"
    document <- tryCatch(jsonlite::fromJSON(text, simplifyVector = FALSE), error = function(error) NULL)
    if (!is.list(document) || !identical(document$portfolio_history_part_version, 1L) || !identical(document$tenant_id, context$tenant_id) ||
        !identical(document$user_id, context$user_id) || !identical(document$data_space_id, context$data_space_id) ||
        !is.character(document$kind) || !document$kind %in% c("asset", "class", "group", "watched") || !is.list(document$fields)) {
      .display_abort("display_artifact_shape_invalid")
    }
    document$fields
  })
}

# Anzeige-Einstellungen (#500): Nachkommastellen und farbige Hinterlegung aus dem Reiter "Einstellungen" der Data-App. Ohne
# Veroeffentlichung gelten die Vorgaben, ausdruecklich als solche gekennzeichnet (source = "default").
DISPLAY_SETTINGS_PERIODS_V1 <- c("1m", "3m", "qtd", "ytd", "1y", "3y", "5y", "all")
# Linien und Kennwerte des Portfolio-Verlaufs (#531 Punkt 2), in fester Folge.
DISPLAY_SETTINGS_LINES_V1 <- c("net_worth", "market_value", "cost_basis", "cash_documented", "cash", "contributed", "unrealised")
DISPLAY_SETTINGS_DEFAULTS_V1 <- list(amount_decimals = 0L, tint = TRUE, drawdown_zones = integer(), expert_tools = FALSE, analysis_period = "all",
                                     history_lines = DISPLAY_SETTINGS_LINES_V1, small_holdings_threshold = "1")
# Umfang je Portfolio (#542, rc.395): ohne veroeffentlichten Umfang alle Bausteine an, wie bis rc.394.
DISPLAY_SETTINGS_MODULES_V1 <- c("cash", "market_data", "history_analysis", "tax_report", "tax_projection", "documents")
DISPLAY_SETTINGS_SCOPE_DEFAULT_V1 <- list(effective_scope_text = NULL, modules = as.list(stats::setNames(rep(TRUE, 6L), DISPLAY_SETTINGS_MODULES_V1)),
                                          classes = list("equity_etf", "fund", "bond", "crypto", "commodity", "derivative", "other"),
                                          valuation_without_market = "manual", portfolios = list(), source = "default")
.display_portfolio_scope_valid_v1 <- function(scope) {
  text_ok <- function(value, limit) is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) && nchar(value) <= limit
  is.list(scope) && setequal(names(scope), c("effective_scope_text", "modules", "classes", "valuation_without_market", "portfolios")) &&
    text_ok(scope$effective_scope_text, 400L) && is.list(scope$modules) && setequal(names(scope$modules), DISPLAY_SETTINGS_MODULES_V1) &&
    all(vapply(scope$modules, function(value) is.logical(value) && length(value) == 1L && !is.na(value), logical(1L))) &&
    is.list(scope$classes) && length(scope$classes) <= 7L &&
    all(vapply(scope$classes, function(value) is.character(value) && length(value) == 1L &&
      value %in% c("equity_etf", "fund", "bond", "crypto", "commodity", "derivative", "other"), logical(1L))) &&
    is.character(scope$valuation_without_market) && length(scope$valuation_without_market) == 1L &&
    scope$valuation_without_market %in% c("manual", "transaction_only") &&
    is.list(scope$portfolios) && length(scope$portfolios) <= 50L && all(vapply(scope$portfolios, function(row)
      is.list(row) && setequal(names(row), c("label", "status", "configured", "scope_text")) && text_ok(row$label, 120L) &&
        is.character(row$status) && length(row$status) == 1L && row$status %in% c("active", "archived") &&
        is.logical(row$configured) && length(row$configured) == 1L && !is.na(row$configured) && text_ok(row$scope_text, 400L), logical(1L)))
}
read_display_settings_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !context$role %in% c("viewer", "tax_viewer", "analysis_viewer")) .display_abort("display_context_invalid")
    artifact <- tryCatch(.display_read_latest(context, project_root, "display_settings"), spot_display_reader_error = function(error) {
      if (identical(error$code, "display_no_latest")) NULL else stop(error)
    })
    if (is.null(artifact)) return(c(DISPLAY_SETTINGS_DEFAULTS_V1, list(portfolio_scope = DISPLAY_SETTINGS_SCOPE_DEFAULT_V1, source = "default")))
    required <- c("display_settings_version", "display_settings_id", "status", "tenant_id", "user_id", "data_space_id", "amount_decimals", "tint",
                  "content_fingerprint", "completed_at_utc", "provider_access", "network_access", "canonical_write", "artifact_fingerprint")
    # Seit rc.305 traegt das Artefakt die Rueckgangszonen der Analyse (#506); ein frueher veroeffentlichtes gilt ohne sie weiter.
    zones <- artifact$drawdown_zones
    zones_valid <- is.null(zones) || (is.list(zones) && length(zones) <= 3L && all(vapply(zones, function(zone)
      is.numeric(zone) && length(zone) == 1L && !is.na(zone) && zone == round(zone) && zone >= 5 && zone <= 95, logical(1L))))
    # Seit rc.309 dazu Expertenschalter und Standard-Zeitraum der Analyse (#492); fehlen sie, gelten die Vorgaben.
    expert <- artifact$expert_tools; period <- artifact$analysis_period
    extras_valid <- (is.null(expert) || (is.logical(expert) && length(expert) == 1L && !is.na(expert))) &&
      (is.null(period) || (is.character(period) && length(period) == 1L && period %in% DISPLAY_SETTINGS_PERIODS_V1))
    # Seit rc.353 die Linien des Portfolio-Verlaufs (#531 Punkt 2); fehlen sie, gelten alle.
    lines <- artifact$history_lines
    lines_valid <- is.null(lines) || (is.list(lines) && length(lines) >= 1L && length(lines) <= length(DISPLAY_SETTINGS_LINES_V1) &&
      all(vapply(lines, function(line) is.character(line) && length(line) == 1L && line %in% DISPLAY_SETTINGS_LINES_V1, logical(1L))) &&
      !anyDuplicated(unlist(lines)))
    # Seit rc.360 die Grenze fuer Kleinstbestaende (#534), exakter Dezimaltext in Euro; fehlt sie, gilt 1 Euro.
    small <- artifact$small_holdings_threshold_decimal
    small_valid <- is.null(small) || (is.character(small) && length(small) == 1L && !is.na(small) &&
      grepl("^(0|[1-9][0-9]{0,3})([.][0-9]{1,2})?$", small) && as.numeric(small) <= 1000)
    # Seit rc.395 der Umfang je Portfolio (#542); fehlt er, gilt alles wie bisher.
    scope <- artifact$portfolio_scope
    scope_valid <- is.null(scope) || .display_portfolio_scope_valid_v1(scope)
    optional <- c("drawdown_zones", "expert_tools", "analysis_period", "history_lines", "small_holdings_threshold_decimal", "portfolio_scope")
    if (!is.list(artifact) || !all(required %in% names(artifact)) || !all(setdiff(names(artifact), required) %in% optional) ||
        !zones_valid || !extras_valid || !lines_valid || !small_valid || !scope_valid ||
        !identical(artifact$display_settings_version, 1L) ||
        !identical(artifact$tenant_id, context$tenant_id) || !identical(artifact$user_id, context$user_id) ||
        !identical(artifact$data_space_id, context$data_space_id) || !as.integer(artifact$amount_decimals) %in% c(0L, 2L) ||
        !is.logical(artifact$tint) || length(artifact$tint) != 1L || is.na(artifact$tint) || !.display_utc_valid(artifact$completed_at_utc)) {
      .display_abort("display_artifact_shape_invalid")
    }
    payload <- artifact[setdiff(names(artifact), "artifact_fingerprint")]
    if (!identical(artifact$artifact_fingerprint, .display_fingerprint(payload))) .display_abort("display_artifact_fingerprint_invalid")
    list(amount_decimals = as.integer(artifact$amount_decimals), tint = isTRUE(artifact$tint),
         drawdown_zones = if (is.null(zones)) integer() else sort(as.integer(unlist(zones))),
         expert_tools = isTRUE(expert), analysis_period = if (is.null(period)) "all" else period,
         history_lines = if (is.null(lines)) DISPLAY_SETTINGS_LINES_V1 else intersect(DISPLAY_SETTINGS_LINES_V1, unlist(lines)),
         small_holdings_threshold = if (is.null(small)) "1" else small,
         portfolio_scope = if (is.null(scope)) DISPLAY_SETTINGS_SCOPE_DEFAULT_V1 else c(scope, list(source = "published")), source = "published")
  })
}

# Datenbasis (rc.314, #478): was hinterlegt und wie es eingestellt ist - Buchungen je Konto, Assets mit Kurszuordnung, Wechselkurse,
# Belege je Jahr, Einstellungen und Staende je Datenart. Veroeffentlicht von "Alles aktualisieren" in der Data-App. Das Schema
# prueft der Leser (read_latest_artifact_v1.py); hier zaehlen Zuordnung, Teile und der Abdruck aus den gelieferten Bytes.
DATA_BASIS_SECTIONS_V1 <- c("stands", "accounts", "assets", "fx", "statements", "settings")
read_data_basis_latest_v1 <- function(context, project_root) {
  .display_boundary({
    if (!display_context_valid(context) || !identical(context$role, "viewer")) .display_abort("display_context_invalid")
    read <- .display_read_latest(context, project_root, "data_basis", with_text = TRUE)
    artifact <- read$artifact
    required <- c("data_basis_version", "data_basis_id", "status", "tenant_id", "user_id", "data_space_id", "as_of_date", "sections",
                  "content_fingerprint", "completed_at_utc", "provider_access", "network_access", "canonical_write", "artifact_fingerprint")
    sections <- artifact$sections
    if (!is.list(artifact) || !setequal(names(artifact), required) || !identical(artifact$data_basis_version, 1L) ||
        !identical(artifact$status, "completed") || !identical(artifact$tenant_id, context$tenant_id) ||
        !identical(artifact$user_id, context$user_id) || !identical(artifact$data_space_id, context$data_space_id) ||
        !.display_utc_valid(artifact$completed_at_utc) || !is.list(sections) || !setequal(names(sections), DATA_BASIS_SECTIONS_V1) ||
        !all(vapply(sections, function(part) is.list(part) && isTRUE(part$status %in% c("available", "unavailable")), logical(1L))) ||
        !isFALSE(artifact$provider_access) || !isFALSE(artifact$network_access) || !isFALSE(artifact$canonical_write)) {
      .display_abort("display_artifact_shape_invalid")
    }
    if (!identical(artifact$artifact_fingerprint, .display_fingerprint_from_text(read$text))) .display_abort("display_artifact_fingerprint_invalid")
    artifact[c("as_of_date", "completed_at_utc", "sections")]
  })
}

# Zeiger auf den juengsten Lauf eines Bereichs (#457): nur der Abdruck aus latest.json, ohne das Artefakt zu lesen. Die
# anzeigenden Apps fragen ihn regelmaessig ab und bieten "Neu lesen" an, wenn er sich seit dem Laden geaendert hat. Ohne
# lesbaren Zeiger NA - das ist kein Fehler, die App zeigt dann einfach keinen Hinweis.
display_latest_marker_v1 <- function(context, area_id) {
  tryCatch({
    area <- display_artifact_area_path(context, area_id)
    path <- file.path(area, "latest.json")
    if (.display_symlink(path) || !file.exists(path) || isTRUE(file.info(path)$size > 1000000)) return(NA_character_)
    value <- jsonlite::fromJSON(paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = ""), simplifyVector = FALSE)
    marker <- value$latest_fingerprint
    if (is.character(marker) && length(marker) == 1L && grepl("^[a-f0-9]{64}$", marker)) marker else NA_character_
  }, error = function(error) NA_character_)
}
