catalog_data_command_error_codes <- function() {
  c(
    "catalog_command_context_invalid",
    "catalog_command_role_not_authorized",
    "catalog_command_repository_invalid",
    "catalog_command_input_invalid",
    "catalog_command_entity_not_found",
    "catalog_command_entity_state_invalid",
    "catalog_command_revision_conflict",
    "catalog_command_duplicate_conflict",
    "catalog_command_idempotency_conflict",
    "catalog_command_provenance_invalid",
    "catalog_command_integrity_invalid",
    "catalog_command_dependency_active",
    "catalog_command_lock_unavailable",
    "catalog_command_transaction_failed",
    "catalog_command_boundary_failed"
  )
}

.catalog_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% catalog_data_command_error_codes()) {
    stop("unregistered_catalog_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_catalog_data_command_error", "error", "condition")
  )
}

.catalog_abort <- function(code) stop(.catalog_condition(code))

.catalog_boundary_eval <- function(expression, fallback = "catalog_command_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_catalog_data_command_error = function(error) error,
    spot_canonical_repository_error = function(error) .catalog_condition("catalog_command_repository_invalid"),
    spot_runtime_error = function(error) .catalog_condition("catalog_command_context_invalid"),
    error = function(error) .catalog_condition(fallback)
  )
  if (inherits(result, "spot_catalog_data_command_error")) stop(result)
  result
}

.catalog_specifications <- function() {
  list(
    portfolio = list(
      table = "portfolio",
      id_column = "portfolio_id",
      prefix = "ptf_",
      area = "portfolio_catalog",
      columns = c(
        "portfolio_id", "display_name", "base_currency", "status", "origin_type", "origin_ref",
        "created_at_utc", "updated_at_utc", "revision"
      ),
      integer_columns = "revision"
    ),
    account = list(
      table = "account",
      id_column = "account_id",
      prefix = "acc_",
      area = "account_catalog",
      columns = c(
        "account_id", "portfolio_id", "display_name", "account_type", "institution_label", "status",
        "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"
      ),
      integer_columns = "revision"
    ),
    asset = list(
      table = "asset",
      id_column = "asset_id",
      prefix = "ast_",
      area = "asset_catalog",
      columns = c(
        "asset_id", "display_name", "asset_type", "price_currency", "quantity_scale", "valuation_method",
        "isin", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"
      ),
      integer_columns = c("quantity_scale", "revision")
    )
  )
}

.catalog_sort_json_value <- function(value) {
  if (!is.list(value)) return(value)
  value <- lapply(value, .catalog_sort_json_value)
  value_names <- names(value)
  if (!is.null(value_names) && length(value_names) && all(nzchar(value_names))) {
    value <- value[order(value_names, method = "radix")]
  }
  value
}

.catalog_canonical_json_bytes <- function(value) {
  text <- jsonlite::toJSON(
    .catalog_sort_json_value(value),
    auto_unbox = TRUE,
    null = "null",
    na = "null",
    digits = NA,
    POSIXt = "ISO8601",
    UTC = TRUE,
    pretty = FALSE
  )
  charToRaw(enc2utf8(as.character(text)))
}

.catalog_fingerprint <- function(value) {
  digest::digest(.catalog_canonical_json_bytes(value), algo = "sha256", serialize = FALSE)
}

.catalog_hash_parts <- function(parts) {
  if (!is.character(parts) || anyNA(parts)) .catalog_abort("catalog_command_input_invalid")
  material <- raw()
  for (index in seq_along(parts)) {
    if (index > 1L) material <- c(material, as.raw(0L))
    material <- c(material, charToRaw(enc2utf8(parts[[index]])))
  }
  digest::digest(material, algo = "sha256", serialize = FALSE)
}

.catalog_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .catalog_abort("catalog_command_context_invalid")
  }
  if (context$role != "desktop_owner") .catalog_abort("catalog_command_role_not_authorized")
  invisible(TRUE)
}

.catalog_token_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    grepl("^tok_[a-z0-9_]+$", value)
}

.catalog_id_valid <- function(value, entity_type) {
  specifications <- .catalog_specifications()
  if (!entity_type %in% names(specifications)) return(FALSE)
  prefix <- specifications[[entity_type]]$prefix
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    startsWith(value, prefix) && grepl("^[a-z0-9_]+$", value)
}

.catalog_text_valid <- function(value, maximum) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 1L && nchar(value, type = "bytes") <= maximum &&
    identical(trimws(value), value) && !grepl("[\r\n\t]", value)
}

.catalog_optional_text_valid <- function(value, maximum) {
  is.null(value) || .catalog_text_valid(value, maximum)
}

.catalog_currency_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[A-Z]{3}$", value)
}

.catalog_revision_valid <- function(value) {
  is.integer(value) && length(value) == 1L && !is.na(value) && value >= 1L
}

.catalog_isin_valid <- function(value) {
  is.null(value) || (
    is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[A-Z0-9]{12}$", value)
  )
}

# ISO 6166: zwei Buchstaben Land, neun Zeichen, Pruefziffer nach Luhn ueber die Ziffernfolge (A=10 ... Z=35).
.catalog_isin_checksum_valid <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !grepl("^[A-Z]{2}[A-Z0-9]{9}[0-9]$", value)) return(FALSE)
  characters <- strsplit(value, "", fixed = TRUE)[[1L]]
  digits <- paste(vapply(characters, function(character) {
    if (grepl("[A-Z]", character)) as.character(utf8ToInt(character) - 55L) else character
  }, character(1)), collapse = "")
  numbers <- rev(as.integer(strsplit(digits, "", fixed = TRUE)[[1L]]))
  doubled <- seq_along(numbers) %% 2L == 0L
  numbers[doubled] <- numbers[doubled] * 2L
  numbers <- ifelse(numbers > 9L, numbers - 9L, numbers)
  sum(numbers) %% 10L == 0L
}

.catalog_time_later <- function(new_value, old_value) {
  if (!.canonical_utc_valid(new_value) || !.canonical_utc_valid(old_value)) return(FALSE)
  new_time <- as.POSIXct(new_value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  old_time <- as.POSIXct(old_value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  new_time > old_time
}

.catalog_command_id <- function(context, command_type, command_token, entity_id = NULL) {
  parts <- c(
    "native-catalog-command-v1", context$tenant_id, context$user_id, context$data_space_id,
    command_type, command_token
  )
  if (!is.null(entity_id)) parts <- c(parts, entity_id)
  paste0("cmd_catalog_", substr(.catalog_hash_parts(parts), 1L, 52L))
}

.catalog_created_entity_id <- function(context, entity_type, command_token) {
  specification <- .catalog_specifications()[[entity_type]]
  paste0(
    specification$prefix,
    substr(
      .catalog_hash_parts(c(
        "native-catalog-entity-v1", context$tenant_id, context$user_id,
        context$data_space_id, entity_type, command_token
      )),
      1L,
      24L
    )
  )
}

.catalog_build_command <- function(
  context,
  entity_type,
  action,
  command_token,
  committed_at_utc,
  fields,
  entity_id = NULL,
  expected_revision = NULL
) {
  .catalog_context_check(context)
  if (!entity_type %in% names(.catalog_specifications()) ||
      !action %in% c("create", "update", "archive", "rescale", "revise_price_currency", "revise_valuation_method", "set_isin", "revise_asset_type") ||
      (action %in% c("rescale", "revise_price_currency", "revise_valuation_method", "set_isin", "revise_asset_type") && !identical(entity_type, "asset")) ||
      !.catalog_token_valid(command_token) || !.canonical_utc_valid(committed_at_utc) || !is.list(fields)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  if (action == "create") {
    if (!is.null(entity_id) || !is.null(expected_revision)) .catalog_abort("catalog_command_input_invalid")
    entity_id <- .catalog_created_entity_id(context, entity_type, command_token)
  } else {
    if (!.catalog_id_valid(entity_id, entity_type) || !.catalog_revision_valid(expected_revision)) {
      .catalog_abort("catalog_command_input_invalid")
    }
  }
  command_type <- if (identical(action, "revise_price_currency")) {
    "catalog_revise_asset_price_currency_v1"
  } else if (identical(action, "revise_asset_type")) {
    "catalog_revise_asset_type_v1"
  } else {
    paste0("catalog_", action, "_", entity_type, "_v1")
  }
  structure(
    list(
      catalog_command_contract_version = 1L,
      entity_type = entity_type,
      action = action,
      command_type = command_type,
      command_token = command_token,
      command_id = .catalog_command_id(
        context, command_type, command_token, if (action == "create") NULL else entity_id
      ),
      entity_id = entity_id,
      expected_revision = expected_revision,
      committed_at_utc = committed_at_utc,
      fields = fields
    ),
    class = "spot_catalog_command_v1"
  )
}

.catalog_build_create_portfolio_v1 <- function(context, command_token, display_name, base_currency, committed_at_utc) {
  if (!.catalog_text_valid(display_name, 120L) || !.catalog_currency_valid(base_currency)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "portfolio", "create", command_token, committed_at_utc,
    list(display_name = display_name, base_currency = base_currency)
  )
}

.catalog_build_update_portfolio_v1 <- function(context, command_token, portfolio_id, expected_revision, display_name, committed_at_utc) {
  if (!.catalog_text_valid(display_name, 120L)) .catalog_abort("catalog_command_input_invalid")
  .catalog_build_command(
    context, "portfolio", "update", command_token, committed_at_utc,
    list(display_name = display_name), portfolio_id, expected_revision
  )
}

.catalog_build_archive_portfolio_v1 <- function(context, command_token, portfolio_id, expected_revision, committed_at_utc) {
  .catalog_build_command(
    context, "portfolio", "archive", command_token, committed_at_utc,
    list(), portfolio_id, expected_revision
  )
}

.catalog_build_create_account_v1 <- function(
  context, command_token, portfolio_id, display_name, account_type, institution_label, committed_at_utc
) {
  if (!.catalog_id_valid(portfolio_id, "portfolio") || !.catalog_text_valid(display_name, 120L) ||
      !is.character(account_type) || length(account_type) != 1L || is.na(account_type) ||
      !account_type %in% c("securities", "cash", "bank", "crypto_wallet", "external", "other") ||
      !.catalog_optional_text_valid(institution_label, 120L)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "account", "create", command_token, committed_at_utc,
    list(
      portfolio_id = portfolio_id,
      display_name = display_name,
      account_type = account_type,
      institution_label = institution_label
    )
  )
}

.catalog_build_update_account_v1 <- function(
  context, command_token, account_id, expected_revision, display_name, institution_label, committed_at_utc
) {
  if (!.catalog_text_valid(display_name, 120L) || !.catalog_optional_text_valid(institution_label, 120L)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "account", "update", command_token, committed_at_utc,
    list(display_name = display_name, institution_label = institution_label),
    account_id, expected_revision
  )
}

.catalog_build_archive_account_v1 <- function(context, command_token, account_id, expected_revision, committed_at_utc) {
  .catalog_build_command(
    context, "account", "archive", command_token, committed_at_utc,
    list(), account_id, expected_revision
  )
}

.catalog_build_create_asset_v1 <- function(
  context,
  command_token,
  display_name,
  asset_type,
  price_currency,
  quantity_scale,
  valuation_method,
  isin,
  committed_at_utc
) {
  if (!.catalog_text_valid(display_name, 160L) ||
      !is.character(asset_type) || length(asset_type) != 1L || is.na(asset_type) ||
      !asset_type %in% c("equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "cash", "fx", "index", "other") ||
      !.catalog_currency_valid(price_currency) || !is.integer(quantity_scale) || length(quantity_scale) != 1L ||
      is.na(quantity_scale) || quantity_scale < 0L || quantity_scale > 24L ||
      !is.character(valuation_method) || length(valuation_method) != 1L || is.na(valuation_method) ||
      !valuation_method %in% c("external_market", "manual", "unit_value", "transaction_only") ||
      (identical(asset_type, "cash") && !identical(valuation_method, "unit_value")) ||
      !.catalog_isin_valid(isin)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "asset", "create", command_token, committed_at_utc,
    list(
      display_name = display_name,
      asset_type = asset_type,
      price_currency = price_currency,
      quantity_scale = quantity_scale,
      valuation_method = valuation_method,
      isin = isin
    )
  )
}

.catalog_build_update_asset_v1 <- function(
  context, command_token, asset_id, expected_revision, display_name, isin, committed_at_utc
) {
  if (!.catalog_text_valid(display_name, 160L) || !.catalog_isin_valid(isin)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "asset", "update", command_token, committed_at_utc,
    list(display_name = display_name, isin = isin), asset_id, expected_revision
  )
}

.catalog_build_revise_asset_valuation_method_v1 <- function(context, command_token, asset_id, expected_revision, valuation_method, committed_at_utc) {
  if (!is.character(valuation_method) || length(valuation_method) != 1L || is.na(valuation_method) ||
      !valuation_method %in% c("external_market", "manual", "unit_value", "transaction_only")) .catalog_abort("catalog_command_input_invalid")
  .catalog_build_command(context, "asset", "revise_valuation_method", command_token, committed_at_utc,
    list(valuation_method = valuation_method), asset_id, expected_revision)
}

.catalog_build_revise_asset_price_currency_v1 <- function(
  context, command_token, asset_id, expected_revision, price_currency, committed_at_utc
) {
  if (!.catalog_currency_valid(price_currency)) .catalog_abort("catalog_command_input_invalid")
  .catalog_build_command(
    context, "asset", "revise_price_currency", command_token, committed_at_utc,
    list(price_currency = price_currency), asset_id, expected_revision
  )
}

# Ein Investmentfonds steht im Katalog als "ETF" oder "Fonds" (#447: steuerlich dasselbe). Der Wechsel geht nur zwischen
# diesen beiden: Konten, Mengenskala und Kurse bleiben, deshalb entwertet er keine Kursfreigabe.
.catalog_fund_types <- function() c("etf", "fund")
.catalog_build_revise_asset_type_v1 <- function(
  context, command_token, asset_id, expected_revision, asset_type, committed_at_utc
) {
  if (!is.character(asset_type) || length(asset_type) != 1L || is.na(asset_type) || !asset_type %in% .catalog_fund_types()) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "asset", "revise_asset_type", command_token, committed_at_utc,
    list(asset_type = asset_type), asset_id, expected_revision
  )
}

.catalog_build_archive_asset_v1 <- function(context, command_token, asset_id, expected_revision, committed_at_utc) {
  .catalog_build_command(
    context, "asset", "archive", command_token, committed_at_utc,
    list(), asset_id, expected_revision
  )
}

.catalog_build_rescale_asset_v1 <- function(
  context, command_token, asset_id, expected_revision, quantity_scale, committed_at_utc
) {
  if (!is.integer(quantity_scale) || length(quantity_scale) != 1L || is.na(quantity_scale) ||
      quantity_scale < 0L || quantity_scale > 24L) {
    .catalog_abort("catalog_command_input_invalid")
  }
  .catalog_build_command(
    context, "asset", "rescale", command_token, committed_at_utc,
    list(quantity_scale = quantity_scale), asset_id, expected_revision
  )
}

# Traegt eine ISIN nach, wo noch keine steht - und aendert sonst nichts an der Zeile. Anders als
# catalog_update_asset_v1 entwertet das keine Kursfreigabe: Die Freigabe galt dem Papier unter seinem
# Namen und Kurssymbol, und die bleiben. Eine schon gesetzte ISIN korrigiert weiter nur das Update.
.catalog_build_set_asset_isin_v1 <- function(
  context, command_token, asset_id, expected_revision, isin, committed_at_utc
) {
  if (!.catalog_isin_checksum_valid(isin)) .catalog_abort("catalog_command_input_invalid")
  .catalog_build_command(
    context, "asset", "set_isin", command_token, committed_at_utc,
    list(isin = isin), asset_id, expected_revision
  )
}

.catalog_v202_schema_fingerprint <- "1d46be68f51afdf27315c9466f9c23440893ff666f1c0bf90ab7015fd94c1524"
.catalog_master_projection_contract_fingerprint <- "86506ab8f51b57a52197c0c452e1bdf0fa9c5a5bd45a53a541cdb1b146bb7079"

.catalog_validate_supported_connection <- function(connection, context, expected_query_only) {
  version <- as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]])
  if (version == 201L) {
    .canonical_validate_connection(connection, context)
  } else if (version == 202L) {
    if (!identical(canonical_repository_schema_fingerprint_v1(connection), .catalog_v202_schema_fingerprint)) {
      .catalog_abort("catalog_command_repository_invalid")
    }
    binding <- DBI::dbGetQuery(
      connection,
      "SELECT singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc FROM store_binding"
    )
    if (nrow(binding) != 1L || as.integer(binding$singleton_id[[1]]) != 1L ||
        as.integer(binding$schema_version[[1]]) != 202L ||
        !identical(binding$tenant_id[[1]], context$tenant_id) ||
        !identical(binding$user_id[[1]], context$user_id) ||
        !identical(binding$data_space_id[[1]], context$data_space_id) ||
        !.canonical_utc_valid(binding$created_at_utc[[1]])) {
      .catalog_abort("catalog_command_repository_invalid")
    }
  } else {
    .catalog_abort("catalog_command_repository_invalid")
  }
  foreign_keys <- as.integer(DBI::dbGetQuery(connection, "PRAGMA foreign_keys")[[1]][[1]])
  query_only <- as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]])
  if (foreign_keys != 1L || query_only != expected_query_only ||
      !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .catalog_abort("catalog_command_repository_invalid")
  }
  if (version == 202L) {
    master_receipt <- .catalog_master_receipt_v1(connection, context)
    if (is.null(master_receipt)) {
      native_only <- sum(vapply(
        c("portfolio", "account", "asset", "transaction_record", "data_command_audit"),
        function(table) DBI::dbGetQuery(
          connection,
          paste0("SELECT count(*) AS n FROM ", table, " WHERE origin_type!='native' OR origin_ref IS NOT NULL")
        )$n[[1]], numeric(1L)
      )) == 0L
      if (!native_only || DBI::dbGetQuery(
        connection, "SELECT count(*) AS n FROM canonical_master_import_receipt"
      )$n[[1]] != 0L) .catalog_abort("catalog_command_repository_invalid")
    }
  }
  version
}

.catalog_connect <- function(context, read_only) {
  path <- runtime_canonical_path(context)
  if (.canonical_symlink(path) || !file.exists(path) || dir.exists(path)) {
    .catalog_abort("catalog_command_repository_invalid")
  }
  flags <- if (isTRUE(read_only)) RSQLite::SQLITE_RO else RSQLite::SQLITE_RW
  connection <- DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = flags)
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, paste0("PRAGMA query_only = ", if (isTRUE(read_only)) "ON" else "OFF"))
    DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
    .catalog_validate_supported_connection(connection, context, if (isTRUE(read_only)) 1L else 0L)
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    if (inherits(error, "spot_catalog_data_command_error")) stop(error)
    .catalog_abort("catalog_command_repository_invalid")
  })
  if (!valid) .catalog_abort("catalog_command_repository_invalid")
  connection
}

.catalog_connect_write <- function(context) .catalog_connect(context, read_only = FALSE)
.catalog_connect_read <- function(context) .catalog_connect(context, read_only = TRUE)

.catalog_frame_row <- function(frame, specification) {
  if (nrow(frame) != 1L) .catalog_abort("catalog_command_entity_not_found")
  row <- vector("list", length(specification$columns))
  names(row) <- specification$columns
  for (column in specification$columns) {
    value <- frame[[column]][[1]]
    if (length(value) != 1L || is.na(value)) {
      row[column] <- list(NULL)
    } else if (column %in% specification$integer_columns) {
      row[[column]] <- as.integer(value)
    } else {
      row[[column]] <- as.character(value)
    }
  }
  row
}

.catalog_fetch_entity <- function(connection, entity_type, entity_id, required = TRUE) {
  specification <- .catalog_specifications()[[entity_type]]
  frame <- DBI::dbGetQuery(
    connection,
    paste0(
      "SELECT ", paste(specification$columns, collapse = ", "), " FROM ", specification$table,
      " WHERE ", specification$id_column, "=?"
    ),
    params = list(entity_id)
  )
  if (!nrow(frame)) {
    if (required) .catalog_abort("catalog_command_entity_not_found")
    return(NULL)
  }
  if (nrow(frame) != 1L) .catalog_abort("catalog_command_integrity_invalid")
  .catalog_frame_row(frame, specification)
}

.catalog_entity_fingerprint <- function(entity_type, row) {
  .catalog_fingerprint(list(catalog_entity_state_version = 1L, entity_type = entity_type, entity = row))
}

.catalog_latest_audit <- function(connection, entity_type, entity_id) {
  specification <- .catalog_specifications()[[entity_type]]
  DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref FROM data_command_audit",
      "WHERE area_id=? AND entity_id=? AND command_type GLOB 'catalog_*'",
      "ORDER BY committed_at_utc DESC, command_id DESC LIMIT 2"
    ),
    params = list(specification$area, entity_id)
  )
}

.catalog_validate_managed_entity <- function(connection, entity_type, entity_id, context) {
  row <- .catalog_fetch_entity(connection, entity_type, entity_id)
  if (!identical(row$origin_type, "native") || !is.null(row$origin_ref)) {
    .catalog_abort("catalog_command_provenance_invalid")
  }
  audit <- .catalog_latest_audit(connection, entity_type, entity_id)
  if (!nrow(audit)) .catalog_abort("catalog_command_provenance_invalid")
  if (nrow(audit) > 1L && identical(audit$committed_at_utc[[1]], audit$committed_at_utc[[2]])) {
    .catalog_abort("catalog_command_integrity_invalid")
  }
  allowed_command_types <- paste0("catalog_", c("create", "update", "archive"), "_", entity_type, "_v1")
  if (identical(entity_type, "asset")) {
    allowed_command_types <- c(
      allowed_command_types, "catalog_rescale_asset_v1", "catalog_revise_asset_price_currency_v1", "catalog_revise_valuation_method_asset_v1",
      "catalog_set_isin_asset_v1", "catalog_revise_asset_type_v1"
    )
  }
  if (!audit$command_type[[1]] %in% allowed_command_types ||
      !identical(audit$actor_id[[1]], context$actor_id) || !identical(audit$origin_type[[1]], "native") ||
      !is.na(audit$origin_ref[[1]]) || !identical(audit$committed_at_utc[[1]], row$updated_at_utc) ||
      !identical(audit$payload_fingerprint[[1]], .catalog_entity_fingerprint(entity_type, row))) {
    .catalog_abort("catalog_command_integrity_invalid")
  }
  row
}

.catalog_master_receipt_payload <- function(receipt) {
  receipt[c(
    "command_id", "tenant_id", "user_id", "target_sandbox_id", "target_portfolio_id",
    "source_contract_version", "master_staging_schema_version", "canonical_schema_version",
    "source_import_run_id", "source_set_fingerprint", "projection_contract_fingerprint",
    "staging_artifact_fingerprint", "candidate_fingerprint", "confirmation_fingerprint",
    "origin_ref_namespace", "portfolio_count", "account_count", "asset_count",
    "provider_mapping_count", "actor_id", "committed_at_utc"
  )]
}

.catalog_master_receipt_v1 <- function(connection, context) {
  version <- as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]])
  if (version != 202L) return(NULL)
  frame <- DBI::dbGetQuery(connection, "SELECT * FROM canonical_master_import_receipt")
  if (!nrow(frame)) return(NULL)
  if (nrow(frame) != 1L) .catalog_abort("catalog_command_integrity_invalid")
  integer_columns <- c(
    "source_contract_version", "master_staging_schema_version", "canonical_schema_version",
    "portfolio_count", "account_count", "asset_count", "provider_mapping_count"
  )
  receipt <- lapply(names(frame), function(column) {
    value <- frame[[column]][[1]]
    if (column %in% integer_columns) as.integer(value) else as.character(value)
  })
  names(receipt) <- names(frame)
  expected_fingerprint <- .catalog_fingerprint(.catalog_master_receipt_payload(receipt))
  expected_command <- paste0("cmd_master_", substr(.catalog_hash_parts(c(
    "legacy-master-bootstrap-v1", context$tenant_id, context$user_id,
    context$data_space_id, receipt$candidate_fingerprint
  )), 1L, 52L))
  if (!identical(receipt$tenant_id, context$tenant_id) ||
      !identical(receipt$user_id, context$user_id) ||
      !identical(receipt$target_sandbox_id, context$data_space_id) ||
      receipt$source_contract_version != 1L || receipt$master_staging_schema_version != 1402L ||
      receipt$canonical_schema_version != 202L || receipt$portfolio_count != 1L ||
      receipt$account_count < 1L || receipt$asset_count < 1L || receipt$provider_mapping_count != 0L ||
      !identical(receipt$projection_contract_fingerprint, .catalog_master_projection_contract_fingerprint) ||
      !identical(receipt$origin_ref_namespace, paste0("lmr_", substr(receipt$candidate_fingerprint, 1L, 24L), "_")) ||
      !identical(receipt$command_id, expected_command) ||
      !identical(receipt$receipt_fingerprint, expected_fingerprint) ||
      !identical(receipt$master_import_receipt_id, paste0("mrc_", substr(expected_fingerprint, 1L, 32L)))) {
    .catalog_abort("catalog_command_integrity_invalid")
  }
  audit <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT count(*) AS n FROM data_command_audit",
      "WHERE command_id=? AND area_id='canonical_import_receipt'",
      "AND command_type='legacy_master_bootstrap_v1' AND entity_id=?",
      "AND actor_id=? AND committed_at_utc=? AND payload_fingerprint=?",
      "AND origin_type='legacy_import' AND origin_ref=?"
    ),
    params = list(
      receipt$command_id, receipt$target_portfolio_id, receipt$actor_id,
      receipt$committed_at_utc, receipt$candidate_fingerprint, receipt$source_import_run_id
    )
  )$n[[1]]
  portfolio_count <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT count(*) AS n FROM portfolio WHERE portfolio_id=? AND origin_type='native'",
      "AND origin_ref IS NULL AND created_at_utc=? AND updated_at_utc=? AND revision=1"
    ),
    params = list(receipt$target_portfolio_id, receipt$committed_at_utc, receipt$committed_at_utc)
  )$n[[1]]
  account_count <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT count(*) AS n FROM account WHERE portfolio_id=? AND origin_type='native'",
      "AND origin_ref IS NULL AND created_at_utc=? AND updated_at_utc=? AND revision=1"
    ),
    params = list(receipt$target_portfolio_id, receipt$committed_at_utc, receipt$committed_at_utc)
  )$n[[1]]
  asset_count <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT count(*) AS n FROM asset WHERE origin_type='legacy_import'",
      "AND substr(origin_ref, 1, length(?))=?",
      "AND created_at_utc=? AND updated_at_utc=? AND revision=1"
    ),
    params = list(
      receipt$origin_ref_namespace, receipt$origin_ref_namespace,
      receipt$committed_at_utc, receipt$committed_at_utc
    )
  )$n[[1]]
  if (as.integer(audit) != 1L || as.integer(portfolio_count) != receipt$portfolio_count ||
      as.integer(account_count) != receipt$account_count || as.integer(asset_count) != receipt$asset_count) {
    .catalog_abort("catalog_command_integrity_invalid")
  }
  receipt
}

.catalog_master_reference_ids <- function(connection, entity_type, receipt) {
  if (is.null(receipt)) return(character())
  if (entity_type == "portfolio") return(receipt$target_portfolio_id)
  if (entity_type == "account") {
    return(DBI::dbGetQuery(
      connection,
      paste(
        "SELECT account_id FROM account WHERE portfolio_id=? AND origin_type='native'",
        "AND origin_ref IS NULL AND created_at_utc=? AND updated_at_utc=? AND revision=1 ORDER BY account_id"
      ),
      params = list(receipt$target_portfolio_id, receipt$committed_at_utc, receipt$committed_at_utc)
    )$account_id)
  }
  DBI::dbGetQuery(
    connection,
    paste(
      "SELECT asset_id FROM asset WHERE origin_type='legacy_import'",
      "AND substr(origin_ref, 1, length(?))=?",
      "AND created_at_utc=? AND updated_at_utc=? AND revision=1 ORDER BY asset_id"
    ),
    params = list(
      receipt$origin_ref_namespace, receipt$origin_ref_namespace,
      receipt$committed_at_utc, receipt$committed_at_utc
    )
  )$asset_id
}

.catalog_validate_reference_entity <- function(connection, entity_type, entity_id, context) {
  row <- .catalog_fetch_entity(connection, entity_type, entity_id)
  audit <- .catalog_latest_audit(connection, entity_type, entity_id)
  if (nrow(audit)) return(.catalog_validate_managed_entity(connection, entity_type, entity_id, context))
  receipt <- .catalog_master_receipt_v1(connection, context)
  if (is.null(receipt) || !entity_id %in% .catalog_master_reference_ids(connection, entity_type, receipt)) {
    .catalog_abort("catalog_command_provenance_invalid")
  }
  if (entity_type == "portfolio") {
    valid <- identical(row$portfolio_id, receipt$target_portfolio_id) &&
      identical(row$origin_type, "native") && is.null(row$origin_ref)
  } else if (entity_type == "account") {
    valid <- identical(row$portfolio_id, receipt$target_portfolio_id) &&
      identical(row$origin_type, "native") && is.null(row$origin_ref)
  } else {
    valid <- identical(row$origin_type, "legacy_import") && !is.null(row$origin_ref) &&
      startsWith(row$origin_ref, receipt$origin_ref_namespace)
  }
  if (!valid || !identical(row$created_at_utc, receipt$committed_at_utc) ||
      !identical(row$updated_at_utc, receipt$committed_at_utc) || row$revision != 1L) {
    .catalog_abort("catalog_command_integrity_invalid")
  }
  row
}

.catalog_expected_row <- function(connection, command) {
  action <- command$action
  entity_type <- command$entity_type
  fields <- command$fields
  if (action == "create") {
    if (entity_type == "portfolio") {
      return(list(
        portfolio_id = command$entity_id,
        display_name = fields$display_name,
        base_currency = fields$base_currency,
        status = "active",
        origin_type = "native",
        origin_ref = NULL,
        created_at_utc = command$committed_at_utc,
        updated_at_utc = command$committed_at_utc,
        revision = 1L
      ))
    }
    if (entity_type == "account") {
      return(list(
        account_id = command$entity_id,
        portfolio_id = fields$portfolio_id,
        display_name = fields$display_name,
        account_type = fields$account_type,
        institution_label = fields$institution_label,
        status = "active",
        origin_type = "native",
        origin_ref = NULL,
        created_at_utc = command$committed_at_utc,
        updated_at_utc = command$committed_at_utc,
        revision = 1L
      ))
    }
    return(list(
      asset_id = command$entity_id,
      display_name = fields$display_name,
      asset_type = fields$asset_type,
      price_currency = fields$price_currency,
      quantity_scale = fields$quantity_scale,
      valuation_method = fields$valuation_method,
      isin = fields$isin,
      status = "active",
      origin_type = "native",
      origin_ref = NULL,
      created_at_utc = command$committed_at_utc,
      updated_at_utc = command$committed_at_utc,
      revision = 1L
    ))
  }
  row <- .catalog_fetch_entity(connection, entity_type, command$entity_id)
  row$updated_at_utc <- command$committed_at_utc
  row$revision <- command$expected_revision + 1L
  if (action == "rescale") {
    row$quantity_scale <- fields$quantity_scale
    return(row)
  }
  if (action == "set_isin") {
    row$isin <- fields$isin
    return(row)
  }
  if (action == "revise_valuation_method") {
    row$valuation_method <- fields$valuation_method
    return(row)
  }
  if (action == "revise_price_currency") {
    row$price_currency <- fields$price_currency
    return(row)
  }
  if (action == "revise_asset_type") {
    row$asset_type <- fields$asset_type
    return(row)
  }
  if (action == "archive") {
    row$status <- "archived"
    return(row)
  }
  row$status <- "active"
  if (entity_type == "portfolio") {
    row$display_name <- fields$display_name
  } else if (entity_type == "account") {
    row$display_name <- fields$display_name
    row$institution_label <- fields$institution_label
  } else {
    row$display_name <- fields$display_name
    row$isin <- fields$isin
  }
  row
}

.catalog_existing_command <- function(connection, command, context) {
  audit <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref FROM data_command_audit WHERE command_id=?"
    ),
    params = list(command$command_id)
  )
  if (!nrow(audit)) return(NULL)
  if (nrow(audit) != 1L) .catalog_abort("catalog_command_integrity_invalid")
  expected_row <- .catalog_expected_row(connection, command)
  expected_fingerprint <- .catalog_entity_fingerprint(command$entity_type, expected_row)
  specification <- .catalog_specifications()[[command$entity_type]]
  valid <-
    identical(audit$area_id[[1]], specification$area) &&
    identical(audit$command_type[[1]], command$command_type) &&
    identical(audit$entity_id[[1]], command$entity_id) &&
    identical(audit$actor_id[[1]], context$actor_id) &&
    identical(audit$committed_at_utc[[1]], command$committed_at_utc) &&
    identical(audit$payload_fingerprint[[1]], expected_fingerprint) &&
    identical(audit$origin_type[[1]], "native") && is.na(audit$origin_ref[[1]])
  if (!valid) .catalog_abort("catalog_command_idempotency_conflict")
  list(row = expected_row, fingerprint = expected_fingerprint)
}

.catalog_duplicate_exists <- function(connection, sql, params) {
  as.integer(DBI::dbGetQuery(connection, sql, params = params)$n[[1]]) > 0L
}

.catalog_precondition_active <- function(row, command) {
  if (!identical(row$status, "active")) .catalog_abort("catalog_command_entity_state_invalid")
  if (!identical(row$revision, command$expected_revision)) .catalog_abort("catalog_command_revision_conflict")
  if (!.catalog_time_later(command$committed_at_utc, row$updated_at_utc)) {
    .catalog_abort("catalog_command_input_invalid")
  }
  invisible(TRUE)
}

.catalog_apply_mutation <- function(connection, command, context) {
  entity_type <- command$entity_type
  action <- command$action
  fields <- command$fields
  entity_id <- command$entity_id
  if (action == "create") {
    if (!is.null(.catalog_fetch_entity(connection, entity_type, entity_id, required = FALSE))) {
      .catalog_abort("catalog_command_duplicate_conflict")
    }
    if (entity_type == "portfolio") {
      if (.catalog_duplicate_exists(connection, "SELECT count(*) AS n FROM portfolio WHERE display_name=?", list(fields$display_name))) {
        .catalog_abort("catalog_command_duplicate_conflict")
      }
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO portfolio",
          "(portfolio_id, display_name, base_currency, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
          "VALUES (?, ?, ?, 'active', 'native', NULL, ?, ?, 1)"
        ),
        params = list(entity_id, fields$display_name, fields$base_currency, command$committed_at_utc, command$committed_at_utc)
      )
    } else if (entity_type == "account") {
      portfolio <- .catalog_validate_reference_entity(connection, "portfolio", fields$portfolio_id, context)
      if (!identical(portfolio$status, "active")) .catalog_abort("catalog_command_entity_state_invalid")
      if (.catalog_duplicate_exists(
        connection,
        "SELECT count(*) AS n FROM account WHERE portfolio_id=? AND display_name=?",
        list(fields$portfolio_id, fields$display_name)
      )) .catalog_abort("catalog_command_duplicate_conflict")
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO account",
          "(account_id, portfolio_id, display_name, account_type, institution_label, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
          "VALUES (?, ?, ?, ?, ?, 'active', 'native', NULL, ?, ?, 1)"
        ),
        params = list(
          entity_id, fields$portfolio_id, fields$display_name, fields$account_type,
          if (is.null(fields$institution_label)) NA_character_ else fields$institution_label,
          command$committed_at_utc, command$committed_at_utc
        )
      )
    } else {
      if (!is.null(fields$isin) && .catalog_duplicate_exists(
        connection, "SELECT count(*) AS n FROM asset WHERE isin=?", list(fields$isin)
      )) .catalog_abort("catalog_command_duplicate_conflict")
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO asset",
          "(asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method, isin, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)",
          "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 'native', NULL, ?, ?, 1)"
        ),
        params = list(
          entity_id, fields$display_name, fields$asset_type, fields$price_currency,
          fields$quantity_scale, fields$valuation_method,
          if (is.null(fields$isin)) NA_character_ else fields$isin,
          command$committed_at_utc, command$committed_at_utc
        )
      )
    }
    return(invisible(TRUE))
  }

  row <- .catalog_validate_managed_entity(connection, entity_type, entity_id, context)
  .catalog_precondition_active(row, command)
  if (action == "rescale") {
    if (!identical(entity_type, "asset") || fields$quantity_scale <= row$quantity_scale) {
      .catalog_abort("catalog_command_input_invalid")
    }
    DBI::dbExecute(
      connection,
      "UPDATE asset SET quantity_scale=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(fields$quantity_scale, command$committed_at_utc, entity_id)
    )
    return(invisible(TRUE))
  }
  if (action == "set_isin") {
    if (!identical(entity_type, "asset")) .catalog_abort("catalog_command_input_invalid")
    if (!is.null(row$isin) && !is.na(row$isin)) .catalog_abort("catalog_command_entity_state_invalid")
    if (.catalog_duplicate_exists(
      connection, "SELECT count(*) AS n FROM asset WHERE isin=? AND asset_id!=?", list(fields$isin, entity_id)
    )) .catalog_abort("catalog_command_duplicate_conflict")
    DBI::dbExecute(
      connection,
      "UPDATE asset SET isin=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(fields$isin, command$committed_at_utc, entity_id)
    )
    return(invisible(TRUE))
  }
  if (action == "revise_valuation_method") {
    if (!identical(entity_type, "asset") || identical(fields$valuation_method, row$valuation_method) ||
        (identical(row$asset_type, "cash") && !identical(fields$valuation_method, "unit_value"))) .catalog_abort("catalog_command_input_invalid")
    DBI::dbExecute(connection,
      "UPDATE asset SET valuation_method=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(fields$valuation_method, command$committed_at_utc, entity_id))
    return(invisible(TRUE))
  }
  if (action == "revise_asset_type") {
    if (!identical(entity_type, "asset") || identical(fields$asset_type, row$asset_type) ||
        !row$asset_type %in% .catalog_fund_types() || !fields$asset_type %in% .catalog_fund_types()) {
      .catalog_abort("catalog_command_input_invalid")
    }
    DBI::dbExecute(
      connection,
      "UPDATE asset SET asset_type=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(fields$asset_type, command$committed_at_utc, entity_id)
    )
    return(invisible(TRUE))
  }
  if (action == "revise_price_currency") {
    if (!identical(entity_type, "asset") || identical(fields$price_currency, row$price_currency)) {
      .catalog_abort("catalog_command_input_invalid")
    }
    DBI::dbExecute(
      connection,
      "UPDATE asset SET price_currency=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(fields$price_currency, command$committed_at_utc, entity_id)
    )
    return(invisible(TRUE))
  }
  if (action == "archive") {
    if (entity_type == "portfolio" && .catalog_duplicate_exists(
      connection, "SELECT count(*) AS n FROM account WHERE portfolio_id=? AND status='active'", list(entity_id)
    )) .catalog_abort("catalog_command_dependency_active")
    specification <- .catalog_specifications()[[entity_type]]
    DBI::dbExecute(
      connection,
      paste0(
        "UPDATE ", specification$table,
        " SET status='archived', updated_at_utc=?, revision=revision+1 WHERE ", specification$id_column, "=?"
      ),
      params = list(command$committed_at_utc, entity_id)
    )
    return(invisible(TRUE))
  }

  if (entity_type == "portfolio") {
    if (.catalog_duplicate_exists(
      connection,
      "SELECT count(*) AS n FROM portfolio WHERE display_name=? AND portfolio_id!=?",
      list(fields$display_name, entity_id)
    )) .catalog_abort("catalog_command_duplicate_conflict")
    DBI::dbExecute(
      connection,
      "UPDATE portfolio SET display_name=?, updated_at_utc=?, revision=revision+1 WHERE portfolio_id=?",
      params = list(fields$display_name, command$committed_at_utc, entity_id)
    )
  } else if (entity_type == "account") {
    portfolio <- .catalog_validate_reference_entity(connection, "portfolio", row$portfolio_id, context)
    if (!identical(portfolio$status, "active")) .catalog_abort("catalog_command_entity_state_invalid")
    if (.catalog_duplicate_exists(
      connection,
      "SELECT count(*) AS n FROM account WHERE portfolio_id=? AND display_name=? AND account_id!=?",
      list(row$portfolio_id, fields$display_name, entity_id)
    )) .catalog_abort("catalog_command_duplicate_conflict")
    DBI::dbExecute(
      connection,
      "UPDATE account SET display_name=?, institution_label=?, updated_at_utc=?, revision=revision+1 WHERE account_id=?",
      params = list(
        fields$display_name,
        if (is.null(fields$institution_label)) NA_character_ else fields$institution_label,
        command$committed_at_utc,
        entity_id
      )
    )
  } else {
    if (!is.null(fields$isin) && .catalog_duplicate_exists(
      connection,
      "SELECT count(*) AS n FROM asset WHERE isin=? AND asset_id!=?",
      list(fields$isin, entity_id)
    )) .catalog_abort("catalog_command_duplicate_conflict")
    DBI::dbExecute(
      connection,
      "UPDATE asset SET display_name=?, isin=?, updated_at_utc=?, revision=revision+1 WHERE asset_id=?",
      params = list(
        fields$display_name,
        if (is.null(fields$isin)) NA_character_ else fields$isin,
        command$committed_at_utc,
        entity_id
      )
    )
  }
  invisible(TRUE)
}

.catalog_insert_audit <- function(connection, command, context, entity_fingerprint) {
  specification <- .catalog_specifications()[[command$entity_type]]
  DBI::dbExecute(
    connection,
    paste(
      "INSERT INTO data_command_audit",
      "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc, payload_fingerprint, origin_type, origin_ref)",
      "VALUES (?, ?, ?, ?, ?, ?, ?, 'native', NULL)"
    ),
    params = list(
      command$command_id,
      specification$area,
      command$command_type,
      command$entity_id,
      context$actor_id,
      command$committed_at_utc,
      entity_fingerprint
    )
  )
}

.catalog_result <- function(command, status, row, fingerprint) {
  list(
    catalog_command_contract_version = 1L,
    status = status,
    command_type = command$command_type,
    command_id = command$command_id,
    entity_type = command$entity_type,
    entity_id = command$entity_id,
    entity_fingerprint = fingerprint,
    revision = row$revision,
    committed_at_utc = command$committed_at_utc
  )
}

.catalog_execute_impl_v1 <- function(context, command, failpoint = "none") {
  .catalog_context_check(context)
  if (!inherits(command, "spot_catalog_command_v1") || !identical(command$catalog_command_contract_version, 1L) ||
      !failpoint %in% c("none", "after_entity", "before_commit")) {
    .catalog_abort("catalog_command_input_invalid")
  }
  data_space <- runtime_data_space_path(context)
  lock <- tryCatch(.canonical_acquire_lock(data_space), spot_canonical_repository_error = function(error) NULL)
  if (is.null(lock)) .catalog_abort("catalog_command_lock_unavailable")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .catalog_connect_write(context)
  on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)

  replay <- .catalog_existing_command(connection, command, context)
  if (!is.null(replay)) return(.catalog_result(command, "already_committed", replay$row, replay$fingerprint))

  result <- tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    replay_locked <- .catalog_existing_command(connection, command, context)
    if (!is.null(replay_locked)) {
      DBI::dbExecute(connection, "ROLLBACK")
      return(.catalog_result(command, "already_committed", replay_locked$row, replay_locked$fingerprint))
    }
    .catalog_apply_mutation(connection, command, context)
    row <- .catalog_fetch_entity(connection, command$entity_type, command$entity_id)
    fingerprint <- .catalog_entity_fingerprint(command$entity_type, row)
    if (failpoint == "after_entity") stop("synthetic_catalog_failpoint", call. = FALSE)
    .catalog_insert_audit(connection, command, context, fingerprint)
    .catalog_validate_managed_entity(connection, command$entity_type, command$entity_id, context)
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L ||
        !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
      .catalog_abort("catalog_command_integrity_invalid")
    }
    if (failpoint == "before_commit") stop("synthetic_catalog_failpoint", call. = FALSE)
    DBI::dbExecute(connection, "COMMIT")
    .catalog_result(command, "committed", row, fingerprint)
  }, error = function(error) {
    if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_catalog_data_command_error")) stop(error)
    .catalog_abort("catalog_command_transaction_failed")
  })
  result
}

.catalog_execute_public <- function(context, command) {
  .catalog_boundary_eval(
    .catalog_execute_impl_v1(context, command, failpoint = "none"),
    fallback = "catalog_command_transaction_failed"
  )
}

catalog_create_portfolio_v1 <- function(context, command_token, display_name, base_currency, committed_at_utc) {
  .catalog_boundary_eval({
    command <- .catalog_build_create_portfolio_v1(context, command_token, display_name, base_currency, committed_at_utc)
    .catalog_execute_public(context, command)
  })
}

catalog_update_portfolio_v1 <- function(context, command_token, portfolio_id, expected_revision, display_name, committed_at_utc) {
  .catalog_boundary_eval({
    command <- .catalog_build_update_portfolio_v1(
      context, command_token, portfolio_id, expected_revision, display_name, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_archive_portfolio_v1 <- function(context, command_token, portfolio_id, expected_revision, committed_at_utc) {
  .catalog_boundary_eval({
    command <- .catalog_build_archive_portfolio_v1(
      context, command_token, portfolio_id, expected_revision, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_create_account_v1 <- function(
  context, command_token, portfolio_id, display_name, account_type, institution_label = NULL, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_create_account_v1(
      context, command_token, portfolio_id, display_name, account_type, institution_label, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_update_account_v1 <- function(
  context, command_token, account_id, expected_revision, display_name, institution_label = NULL, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_update_account_v1(
      context, command_token, account_id, expected_revision, display_name, institution_label, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_archive_account_v1 <- function(context, command_token, account_id, expected_revision, committed_at_utc) {
  .catalog_boundary_eval({
    command <- .catalog_build_archive_account_v1(
      context, command_token, account_id, expected_revision, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_create_asset_v1 <- function(
  context,
  command_token,
  display_name,
  asset_type,
  price_currency,
  quantity_scale,
  valuation_method,
  isin = NULL,
  committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_create_asset_v1(
      context, command_token, display_name, asset_type, price_currency,
      quantity_scale, valuation_method, isin, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_update_asset_v1 <- function(
  context, command_token, asset_id, expected_revision, display_name, isin = NULL, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_update_asset_v1(
      context, command_token, asset_id, expected_revision, display_name, isin, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_revise_asset_price_currency_v1 <- function(
  context, command_token, asset_id, expected_revision, price_currency, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_revise_asset_price_currency_v1(
      context, command_token, asset_id, expected_revision, price_currency, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_revise_asset_type_v1 <- function(
  context, command_token, asset_id, expected_revision, asset_type, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_revise_asset_type_v1(
      context, command_token, asset_id, expected_revision, asset_type, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_archive_asset_v1 <- function(context, command_token, asset_id, expected_revision, committed_at_utc) {
  .catalog_boundary_eval({
    command <- .catalog_build_archive_asset_v1(
      context, command_token, asset_id, expected_revision, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_rescale_asset_v1 <- function(
  context, command_token, asset_id, expected_revision, quantity_scale, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_rescale_asset_v1(
      context, command_token, asset_id, expected_revision, quantity_scale, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_set_isin_asset_v1 <- function(
  context, command_token, asset_id, expected_revision, isin, committed_at_utc
) {
  .catalog_boundary_eval({
    command <- .catalog_build_set_asset_isin_v1(
      context, command_token, asset_id, expected_revision, isin, committed_at_utc
    )
    .catalog_execute_public(context, command)
  })
}

catalog_read_v1 <- function(context) {
  .catalog_boundary_eval({
    .catalog_context_check(context)
    connection <- .catalog_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    receipt <- .catalog_master_receipt_v1(connection, context)
    result <- list()
    counts <- list()
    for (entity_type in names(.catalog_specifications())) {
      specification <- .catalog_specifications()[[entity_type]]
      catalog_identifiers <- DBI::dbGetQuery(
        connection,
        paste(
          "SELECT DISTINCT entity_id FROM data_command_audit",
          "WHERE area_id=? AND command_type GLOB 'catalog_*' ORDER BY entity_id"
        ),
        params = list(specification$area)
      )$entity_id
      identifiers <- sort(unique(c(
        catalog_identifiers,
        .catalog_master_reference_ids(connection, entity_type, receipt)
      )), method = "radix")
      rows <- lapply(identifiers, function(entity_id) {
        .catalog_validate_reference_entity(connection, entity_type, entity_id, context)
      })
      result[[paste0(entity_type, "s")]] <- rows
      counts[[paste0(entity_type, "_count")]] <- length(rows)
    }
    payload <- list(
      catalog_read_contract_version = 1L,
      status = "ready",
      portfolios = result$portfolios,
      accounts = result$accounts,
      assets = result$assets,
      counts = counts
    )
    output <- payload
    output$catalog_fingerprint <- .catalog_fingerprint(payload)
    output
  }, fallback = "catalog_command_repository_invalid")
}
