transaction_import_data_command_error_codes <- function() {
  c(
    "transaction_import_dependency_missing",
    "transaction_import_context_invalid",
    "transaction_import_role_not_authorized",
    "transaction_import_staging_path_invalid",
    "transaction_import_staging_not_read_only",
    "transaction_import_staging_schema_invalid",
    "transaction_import_staging_integrity_invalid",
    "transaction_import_staging_seal_invalid",
    "transaction_import_staging_context_invalid",
    "transaction_import_staging_payload_invalid",
    "transaction_import_route_unsupported",
    "transaction_import_master_receipt_invalid",
    "transaction_import_target_not_empty",
    "transaction_import_idempotency_conflict",
    "transaction_import_confirmation_missing",
    "transaction_import_confirmation_invalid",
    "transaction_import_confirmation_duplicate",
    "transaction_import_confirmation_not_authorized",
    "transaction_import_confirmation_consumed",
    "transaction_import_confirmation_scope_mismatch",
    "transaction_import_confirmation_expired",
    "transaction_import_lock_unavailable",
    "transaction_import_synthetic_failpoint",
    "transaction_import_canonical_transaction_failed",
    "transaction_import_boundary_failed"
  )
}

.transaction_import_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% transaction_import_data_command_error_codes()) {
    stop("unregistered_transaction_import_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_transaction_import_data_command_error", "error", "condition")
  )
}

.transaction_import_abort <- function(code) stop(.transaction_import_condition(code))

.transaction_import_boundary <- function(expression, fallback = "transaction_import_boundary_failed") {
  value <- tryCatch(
    expression,
    spot_transaction_import_data_command_error = function(error) error,
    spot_transaction_data_command_error = function(error) .transaction_import_condition(fallback),
    spot_catalog_data_command_error = function(error) .transaction_import_condition(fallback),
    spot_runtime_error = function(error) .transaction_import_condition("transaction_import_context_invalid"),
    error = function(error) .transaction_import_condition(fallback)
  )
  if (inherits(value, "spot_transaction_import_data_command_error")) stop(value)
  value
}

.transaction_import_staging_schema_version <- 1101L
.transaction_import_staging_schema_fingerprint <- "293012c473659f5b1594c4958165db03636ef9597569d8fb9a10fb6482f0b557"

.transaction_import_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .transaction_import_abort("transaction_import_context_invalid")
  }
  if (!identical(context$role, "desktop_owner")) {
    .transaction_import_abort("transaction_import_role_not_authorized")
  }
  invisible(TRUE)
}

.transaction_import_stage_path <- function(path) {
  if (!is.character(path) || length(path) != 1L || is.na(path) || !nzchar(path) ||
      !file.exists(path) || dir.exists(path) || .canonical_symlink(path)) {
    .transaction_import_abort("transaction_import_staging_path_invalid")
  }
  normalized <- tryCatch(normalizePath(path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || .canonical_symlink(normalized)) {
    .transaction_import_abort("transaction_import_staging_path_invalid")
  }
  mode <- file.info(normalized)$mode[[1L]]
  if (is.na(mode) || bitwAnd(as.integer(mode), 146L) != 0L) {
    .transaction_import_abort("transaction_import_staging_not_read_only")
  }
  normalized
}

new_transaction_import_staging_capability_v1 <- function(staging_path) {
  .transaction_import_boundary(structure(
    list(path = .transaction_import_stage_path(staging_path), execution_mode = "synthetic_only"),
    class = "spot_transaction_import_staging_capability_v1"
  ))
}

.transaction_import_capability <- function(capability) {
  if (!inherits(capability, "spot_transaction_import_staging_capability_v1") ||
      !is.list(capability) || !identical(names(capability), c("path", "execution_mode")) ||
      !identical(capability$execution_mode, "synthetic_only")) {
    .transaction_import_abort("transaction_import_staging_path_invalid")
  }
  path <- .transaction_import_stage_path(capability$path)
  if (!identical(path, capability$path)) {
    .transaction_import_abort("transaction_import_staging_path_invalid")
  }
  capability
}

.transaction_import_rows <- function(frame, logical_columns = character(), integer_columns = character()) {
  if (!is.data.frame(frame)) .transaction_import_abort("transaction_import_staging_payload_invalid")
  if (!nrow(frame)) return(list())
  lapply(seq_len(nrow(frame)), function(index) {
    row <- vector("list", ncol(frame))
    names(row) <- names(frame)
    for (column in names(frame)) {
      value <- frame[[column]][[index]]
      if (length(value) != 1L || is.na(value)) {
        row[column] <- list(NULL)
      } else if (column %in% logical_columns) {
        row[[column]] <- identical(as.integer(value), 1L)
      } else if (column %in% integer_columns) {
        row[[column]] <- as.integer(value)
      } else {
        row[[column]] <- as.character(value)
      }
    }
    row
  })
}

.transaction_import_stage_artifact <- function(connection, binding) {
  facts <- .transaction_import_rows(
    DBI::dbGetQuery(connection, "SELECT * FROM staged_transaction_fact ORDER BY rowid"),
    logical_columns = c(
      "source_transaction_reference_present", "memo_present", "display_evidence_present"
    )
  )
  route_frames <- DBI::dbGetQuery(connection, "SELECT * FROM staged_event_route ORDER BY rowid")
  routes <- lapply(seq_len(nrow(route_frames)), function(index) {
    source_ref <- route_frames$source_row_ref[[index]]
    fact <- Filter(function(row) identical(row$source_row_ref, source_ref), facts)
    if (length(fact) != 1L) .transaction_import_abort("transaction_import_staging_payload_invalid")
    codes <- tryCatch(
      jsonlite::fromJSON(route_frames$route_codes_json[[index]], simplifyVector = FALSE),
      error = function(error) .transaction_import_abort("transaction_import_staging_payload_invalid")
    )
    list(
      source_row_ref = source_ref,
      transaction_type = fact[[1L]]$transaction_type,
      semantic_contract = route_frames$semantic_contract[[index]],
      semantic_status = route_frames$semantic_status[[index]],
      settlement_cash_asset_id = if (is.na(route_frames$settlement_cash_asset_id[[index]])) NULL else route_frames$settlement_cash_asset_id[[index]],
      route_codes = codes
    )
  })
  reference_frame <- DBI::dbGetQuery(
    connection,
    "SELECT entity_kind, entity_id FROM referenced_master_entity ORDER BY entity_kind, entity_id"
  )
  references <- lapply(seq_len(nrow(reference_frame)), function(index) {
    list(reference_frame$entity_kind[[index]], reference_frame$entity_id[[index]])
  })
  body <- list(
    staging_schema_version = 1101L,
    execution_mode = binding$execution_mode,
    master_candidate_fingerprint = binding$master_candidate_fingerprint,
    adapter_review_fingerprint = binding$adapter_review_fingerprint,
    routing_fingerprint = binding$routing_fingerprint,
    facts = facts,
    routes = routes,
    references = references
  )
  list(
    body = body,
    fingerprint = .import_fingerprint(body),
    facts = facts,
    routes = routes,
    references = references
  )
}

.transaction_import_expected_route_codes <- function(transaction_type) {
  switch(
    transaction_type,
    buy =, sell = list(
      "split_cash_trade_canonical_adapter_required",
      "split_cash_trade_fifo_context_required",
      "transaction_only_import_command_required"
    ),
    deposit =, withdrawal =, transfer = list("movement_v2_canonical_adapter_required"),
    reward = list("reward_event_canonical_adapter_required"),
    dividend =, interest = list("income_event_canonical_adapter_required"),
    NULL
  )
}

.transaction_import_expected_contract <- function(transaction_type) {
  if (transaction_type %in% c("buy", "sell")) return("split_cash_trade_semantics_v2")
  if (transaction_type %in% c("deposit", "withdrawal", "transfer")) return("movement_semantics_v2")
  if (transaction_type %in% c("dividend", "interest", "reward")) return("income_reward_semantics_v1")
  NULL
}

.transaction_import_decimal <- function(value, positive = FALSE) {
  tryCatch(
    .transaction_decimal_parse(value, allow_zero = FALSE, positive_only = positive),
    spot_transaction_data_command_error = function(error) {
      .transaction_import_abort("transaction_import_staging_payload_invalid")
    }
  )
}

.transaction_import_master_ids <- function(connection, receipt) {
  list(
    portfolio = receipt$target_portfolio_id,
    account = .catalog_master_reference_ids(connection, "account", receipt),
    asset = .catalog_master_reference_ids(connection, "asset", receipt)
  )
}

.transaction_import_account_asset_compatible <- function(account, asset) {
  if (identical(asset$asset_type, "cash")) {
    return(account$account_type %in% c("cash", "bank", "securities", "other"))
  }
  if (identical(asset$asset_type, "crypto")) {
    return(account$account_type %in% c("crypto_wallet", "securities", "other"))
  }
  account$account_type %in% c("securities", "other")
}

.transaction_import_validate_fact <- function(
  fact, route, master_ids, portfolio_currency, account, asset, related_account = NULL
) {
  required_fact <- c(
    "source_row_ref", "transaction_type", "portfolio_id", "asset_id", "account_id",
    "related_account_id", "settlement_account_id", "local_date", "local_time",
    "effective_at_utc", "price_currency", "quantity_decimal", "unit_price_decimal",
    "gross_amount_decimal", "fee_quantity_decimal", "reported_amount_decimal",
    "source_transaction_reference", "source_transaction_reference_origin",
    "source_transaction_reference_present", "memo_present", "display_evidence_present"
  )
  transaction_type <- fact$transaction_type
  expected_codes <- .transaction_import_expected_route_codes(transaction_type)
  expected_contract <- .transaction_import_expected_contract(transaction_type)
  if (!identical(names(fact), required_fact) || is.null(expected_codes) ||
      transaction_type %in% c("dividend", "interest") ||
      !identical(fact$portfolio_id, master_ids$portfolio) ||
      !fact$account_id %in% master_ids$account || !fact$asset_id %in% master_ids$asset ||
      !is.null(fact$settlement_account_id) ||
      !.canonical_utc_valid(fact$effective_at_utc) || !.transaction_date_valid(fact$local_date) ||
      !identical(fact$price_currency, portfolio_currency) ||
      !identical(route$source_row_ref, fact$source_row_ref) ||
      !identical(route$transaction_type, transaction_type) ||
      !identical(route$semantic_contract, expected_contract) ||
      !identical(route$semantic_status, "semantic_contract_available_persistence_required") ||
      !is.null(route$settlement_cash_asset_id) || !identical(route$route_codes, expected_codes) ||
      !identical(account$portfolio_id, master_ids$portfolio) ||
      !identical(account$status, "active") || !identical(asset$status, "active") ||
      identical(asset$asset_type, "derivative") ||
      !identical(asset$price_currency, portfolio_currency) ||
      !.transaction_import_account_asset_compatible(account, asset)) {
    .transaction_import_abort("transaction_import_route_unsupported")
  }
  if (!is.null(fact$reported_amount_decimal)) {
    invisible(.transaction_import_decimal(fact$reported_amount_decimal))
  }
  if (transaction_type %in% c("buy", "sell", "reward")) {
    if (!is.null(fact$related_account_id)) {
      .transaction_import_abort("transaction_import_route_unsupported")
    }
    quantity <- .transaction_import_decimal(fact$quantity_decimal, positive = TRUE)
    price <- .transaction_import_decimal(fact$unit_price_decimal, positive = TRUE)
    gross <- .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
    if (quantity$scale > asset$quantity_scale ||
        !.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), gross)) {
      .transaction_import_abort("transaction_import_staging_payload_invalid")
    }
    if (transaction_type %in% c("buy", "sell")) {
      if (identical(asset$asset_type, "cash") ||
          !account$account_type %in% c("securities", "crypto_wallet") ||
          !is.null(fact$fee_quantity_decimal)) {
        .transaction_import_abort("transaction_import_route_unsupported")
      }
    } else {
      if (!identical(asset$asset_type, "crypto") ||
          !account$account_type %in% c("crypto_wallet", "securities", "other")) {
        .transaction_import_abort("transaction_import_route_unsupported")
      }
      if (!is.null(fact$fee_quantity_decimal)) {
        fee <- .transaction_import_decimal(fact$fee_quantity_decimal, positive = TRUE)
        if (fee$scale > asset$quantity_scale || .transaction_decimal_compare(fee, quantity) > 0L) {
          .transaction_import_abort("transaction_import_staging_payload_invalid")
        }
      }
    }
    return(invisible(TRUE))
  }
  if (transaction_type %in% c("deposit", "withdrawal")) {
    if (!is.null(fact$related_account_id) || !is.null(related_account)) {
      .transaction_import_abort("transaction_import_route_unsupported")
    }
  } else if (transaction_type == "transfer") {
    if (is.null(fact$related_account_id) || is.null(related_account) ||
        !fact$related_account_id %in% master_ids$account ||
        identical(fact$account_id, fact$related_account_id) ||
        !identical(related_account$portfolio_id, master_ids$portfolio) ||
        !identical(related_account$status, "active") ||
        !.transaction_import_account_asset_compatible(related_account, asset)) {
      .transaction_import_abort("transaction_import_route_unsupported")
    }
  }
  if (transaction_type == "deposit" && !identical(asset$asset_type, "cash")) {
    .transaction_import_abort("transaction_import_route_unsupported")
  }
  quantity <- if (is.null(fact$quantity_decimal)) {
    if (!identical(asset$asset_type, "cash")) {
      .transaction_import_abort("transaction_import_route_unsupported")
    }
    .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
  } else {
    .transaction_import_decimal(fact$quantity_decimal, positive = TRUE)
  }
  if (quantity$scale > asset$quantity_scale) {
    .transaction_import_abort("transaction_import_staging_payload_invalid")
  }
  if (is.null(fact$unit_price_decimal)) {
    gross <- .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
    if (!identical(asset$asset_type, "cash") || !.transaction_decimal_equal(quantity, gross)) {
      .transaction_import_abort("transaction_import_staging_payload_invalid")
    }
  } else {
    price <- .transaction_import_decimal(fact$unit_price_decimal, positive = TRUE)
    gross <- .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
    if (!.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), gross)) {
      .transaction_import_abort("transaction_import_staging_payload_invalid")
    }
  }
  if (!is.null(fact$fee_quantity_decimal)) {
    fee <- .transaction_import_decimal(fact$fee_quantity_decimal, positive = TRUE)
    if (fee$scale > asset$quantity_scale ||
        (!identical(asset$asset_type, "cash") && is.null(fact$unit_price_decimal))) {
      .transaction_import_abort("transaction_import_staging_payload_invalid")
    }
  }
  invisible(TRUE)
}

.transaction_import_open_stage <- function(context, capability) {
  capability <- .transaction_import_capability(capability)
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), dbname = capability$path, flags = RSQLite::SQLITE_RO),
    error = function(error) .transaction_import_abort("transaction_import_staging_not_read_only")
  )
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
  DBI::dbExecute(connection, "PRAGMA query_only = ON")
  DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
  if (as.integer(DBI::dbGetQuery(connection, "PRAGMA query_only")[[1]][[1]]) != 1L ||
      as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1]][[1]]) != 1101L ||
      !identical(canonical_repository_schema_fingerprint_v1(connection), .transaction_import_staging_schema_fingerprint)) {
    .transaction_import_abort("transaction_import_staging_schema_invalid")
  }
  DBI::dbExecute(connection, "BEGIN")
  open_transaction <- TRUE
  on.exit(if (open_transaction && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
  if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
      nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
    .transaction_import_abort("transaction_import_staging_integrity_invalid")
  }
  bindings <- .transaction_import_rows(DBI::dbGetQuery(connection, "SELECT * FROM transaction_stage_binding"))
  seals <- .transaction_import_rows(
    DBI::dbGetQuery(connection, "SELECT * FROM transaction_stage_seal"),
    integer_columns = c("singleton_id", "fact_count", "route_count", "reference_count")
  )
  if (length(bindings) != 1L || length(seals) != 1L) {
    .transaction_import_abort("transaction_import_staging_seal_invalid")
  }
  binding <- bindings[[1L]]
  seal <- seals[[1L]]
  if (!identical(binding$execution_mode, "synthetic_only") ||
      !identical(binding$outcome, "routed_staging_complete_persistence_pending") ||
      !identical(binding$canonical_confirmation_created, "0") ||
      !identical(binding$canonical_write, "0") ||
      !identical(seal$outcome, "routed_staging_complete_persistence_pending") ||
      !.canonical_utc_valid(seal$sealed_at_utc)) {
    .transaction_import_abort("transaction_import_staging_seal_invalid")
  }
  artifact <- .transaction_import_stage_artifact(connection, binding)
  if (!identical(artifact$fingerprint, binding$artifact_fingerprint) ||
      !identical(artifact$fingerprint, seal$artifact_fingerprint) ||
      seal$fact_count != length(artifact$facts) || seal$route_count != length(artifact$routes) ||
      seal$reference_count != length(artifact$references) || !length(artifact$facts)) {
    .transaction_import_abort("transaction_import_staging_seal_invalid")
  }
  DBI::dbExecute(connection, "ROLLBACK")
  open_transaction <- FALSE
  list(binding = binding, seal = seal, artifact = artifact, path = capability$path)
}

.transaction_import_posting <- function(
  transaction_id, sequence_no, fact, account_id, role, quantity,
  unit_price = NULL, valuation
) {
  list(
    posting_id = paste0("pst_", substr(.catalog_hash_parts(c(
      "legacy-transaction-posting-v1", transaction_id, as.character(sequence_no)
    )), 1L, 24L)),
    transaction_id = transaction_id,
    sequence_no = as.integer(sequence_no),
    account_id = account_id,
    asset_id = fact$asset_id,
    posting_role = role,
    quantity_decimal = .transaction_decimal_string(quantity),
    unit_price_decimal = if (is.null(unit_price)) NULL else .transaction_decimal_string(unit_price),
    price_currency = if (is.null(unit_price)) NULL else fact$price_currency,
    valuation_amount_decimal = .transaction_decimal_string(valuation),
    valuation_currency = fact$price_currency,
    memo = NULL
  )
}

.transaction_import_fact_postings <- function(transaction_id, fact) {
  transaction_type <- fact$transaction_type
  quantity <- if (is.null(fact$quantity_decimal)) {
    .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
  } else {
    .transaction_import_decimal(fact$quantity_decimal, positive = TRUE)
  }
  price <- if (is.null(fact$unit_price_decimal)) NULL else {
    .transaction_import_decimal(fact$unit_price_decimal, positive = TRUE)
  }
  gross <- .transaction_import_decimal(fact$gross_amount_decimal, positive = TRUE)
  if (transaction_type %in% c("buy", "sell")) {
    direction <- if (transaction_type == "buy") 1L else -1L
    return(list(.transaction_import_posting(
      transaction_id, 1L, fact, fact$account_id, "asset",
      if (direction == 1L) quantity else .transaction_decimal_negate(quantity),
      price, if (direction == 1L) gross else .transaction_decimal_negate(gross)
    )))
  }
  if (transaction_type == "reward") {
    postings <- list(.transaction_import_posting(
      transaction_id, 1L, fact, fact$account_id, "income", quantity, price, gross
    ))
    if (!is.null(fact$fee_quantity_decimal)) {
      fee <- .transaction_import_decimal(fact$fee_quantity_decimal, positive = TRUE)
      postings[[2L]] <- .transaction_import_posting(
        transaction_id, 2L, fact, fact$account_id, "fee",
        .transaction_decimal_negate(fee), price,
        .transaction_decimal_negate(.transaction_decimal_multiply(fee, price))
      )
    }
    return(postings)
  }
  principal_value <- if (is.null(price)) quantity else gross
  direction <- if (transaction_type == "deposit") 1L else -1L
  postings <- list(.transaction_import_posting(
    transaction_id, 1L, fact, fact$account_id, "transfer",
    if (direction == 1L) quantity else .transaction_decimal_negate(quantity), price,
    if (direction == 1L) principal_value else .transaction_decimal_negate(principal_value)
  ))
  if (transaction_type == "transfer") {
    postings[[2L]] <- .transaction_import_posting(
      transaction_id, 2L, fact, fact$related_account_id, "transfer",
      quantity, price, principal_value
    )
  }
  if (!is.null(fact$fee_quantity_decimal)) {
    fee <- .transaction_import_decimal(fact$fee_quantity_decimal, positive = TRUE)
    fee_value <- if (is.null(price)) fee else .transaction_decimal_multiply(fee, price)
    sequence_no <- length(postings) + 1L
    postings[[sequence_no]] <- .transaction_import_posting(
      transaction_id, sequence_no, fact, fact$account_id, "fee",
      .transaction_decimal_negate(fee), price, .transaction_decimal_negate(fee_value)
    )
  }
  postings
}

.transaction_import_bundle <- function(context, validated, fact, committed_at_utc) {
  batch_command_id <- .transaction_import_batch_command_id(
    context, validated$binding$master_candidate_fingerprint,
    validated$artifact$fingerprint
  )
  transaction_id <- .transaction_import_transaction_id(
    context, batch_command_id, fact$source_row_ref
  )
  origin_ref <- paste0(
    .transaction_import_origin_namespace(validated$artifact$fingerprint),
    substr(.catalog_hash_parts(c("legacy-source-row", fact$source_row_ref)), 1L, 24L)
  )
  record <- list(
    transaction_id = transaction_id,
    portfolio_id = fact$portfolio_id,
    transaction_type = fact$transaction_type,
    record_action = "book",
    effective_at_utc = fact$effective_at_utc,
    local_date = fact$local_date,
    memo = fact$source_transaction_reference,
    supersedes_transaction_id = NULL,
    origin_type = "legacy_import",
    origin_ref = origin_ref,
    created_at_utc = committed_at_utc,
    created_by_actor = context$actor_id
  )
  postings <- .transaction_import_fact_postings(transaction_id, fact)
  list(
    record = record,
    postings = postings,
    fingerprint = .transaction_content_fingerprint(record, postings),
    command_id = .transaction_import_row_command_id(context, batch_command_id, transaction_id),
    batch_command_id = batch_command_id
  )
}

.transaction_import_validate_fifo_context <- function(context, validated, assets) {
  batch_command_id <- .transaction_import_batch_command_id(
    context, validated$binding$master_candidate_fingerprint, validated$artifact$fingerprint
  )
  facts <- validated$artifact$facts
  order_keys <- vapply(facts, function(fact) paste0(
    fact$effective_at_utc, "|",
    .transaction_import_transaction_id(context, batch_command_id, fact$source_row_ref)
  ), character(1))
  facts <- facts[order(order_keys)]
  lots <- new.env(hash = TRUE, parent = emptyenv())
  consume <- function(key, quantity) {
    tryCatch(
      .transaction_fifo_consume_quantities(lots, key, quantity),
      spot_transaction_data_command_error = function(error) {
        .transaction_import_abort("transaction_import_staging_payload_invalid")
      }
    )
  }
  for (fact in facts) {
    asset <- assets[[fact$asset_id]]
    if (identical(asset$asset_type, "cash")) next
    quantity <- .transaction_import_decimal(fact$quantity_decimal, positive = TRUE)
    key <- paste(fact$portfolio_id, fact$account_id, fact$asset_id, sep = "|")
    if (fact$transaction_type %in% c("buy", "reward")) {
      existing <- if (exists(key, envir = lots, inherits = FALSE)) get(key, envir = lots) else list()
      existing[[length(existing) + 1L]] <- quantity
      assign(key, existing, envir = lots)
    } else if (fact$transaction_type %in% c("sell", "withdrawal")) {
      invisible(consume(key, quantity))
    } else if (fact$transaction_type == "transfer") {
      chunks <- consume(key, quantity)
      destination_key <- paste(
        fact$portfolio_id, fact$related_account_id, fact$asset_id, sep = "|"
      )
      destination <- if (exists(destination_key, envir = lots, inherits = FALSE)) {
        get(destination_key, envir = lots)
      } else list()
      assign(destination_key, c(destination, chunks), envir = lots)
    }
    if (!is.null(fact$fee_quantity_decimal)) {
      fee <- .transaction_import_decimal(fact$fee_quantity_decimal, positive = TRUE)
      invisible(consume(key, fee))
    }
  }
  invisible(TRUE)
}

.transaction_import_validate_target <- function(context, validated) {
  connection <- .catalog_connect_read(context)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  receipt <- .catalog_master_receipt_v1(connection, context)
  if (is.null(receipt) || !identical(
    receipt$candidate_fingerprint, validated$binding$master_candidate_fingerprint
  )) .transaction_import_abort("transaction_import_master_receipt_invalid")
  master_ids <- .transaction_import_master_ids(connection, receipt)
  portfolio <- .catalog_fetch_entity(connection, "portfolio", receipt$target_portfolio_id)
  routes <- setNames(validated$artifact$routes, vapply(
    validated$artifact$routes, `[[`, character(1), "source_row_ref"
  ))
  if (length(routes) != length(validated$artifact$facts) || anyDuplicated(names(routes))) {
    .transaction_import_abort("transaction_import_staging_payload_invalid")
  }
  account_ids <- unique(c(
    vapply(validated$artifact$facts, `[[`, character(1), "account_id"),
    vapply(validated$artifact$facts, function(fact) {
      if (is.null(fact$related_account_id)) "" else fact$related_account_id
    }, character(1))
  ))
  account_ids <- account_ids[nzchar(account_ids)]
  asset_ids <- unique(vapply(validated$artifact$facts, `[[`, character(1), "asset_id"))
  accounts <- setNames(lapply(account_ids, function(id) {
    .catalog_fetch_entity(connection, "account", id)
  }), account_ids)
  assets <- setNames(lapply(asset_ids, function(id) {
    .catalog_fetch_entity(connection, "asset", id)
  }), asset_ids)
  for (fact in validated$artifact$facts) {
    route <- routes[[fact$source_row_ref]]
    if (is.null(route)) .transaction_import_abort("transaction_import_staging_payload_invalid")
    .transaction_import_validate_fact(
      fact, route, master_ids, portfolio$base_currency,
      accounts[[fact$account_id]], assets[[fact$asset_id]],
      if (is.null(fact$related_account_id)) NULL else accounts[[fact$related_account_id]]
    )
  }
  .transaction_import_validate_fifo_context(context, validated, assets)
  expected_references <- unique(c(
    list(list("portfolio", receipt$target_portfolio_id)),
    lapply(account_ids, function(id) list("account", id)),
    lapply(asset_ids, function(id) list("asset", id))
  ))
  reference_key <- function(value) paste(unlist(value, use.names = FALSE), collapse = "|")
  if (!setequal(vapply(validated$artifact$references, reference_key, character(1)),
                vapply(expected_references, reference_key, character(1)))) {
    .transaction_import_abort("transaction_import_staging_context_invalid")
  }
  batch_command_id <- .transaction_import_batch_command_id(
    context, receipt$candidate_fingerprint, validated$artifact$fingerprint
  )
  posting_count <- sum(vapply(validated$artifact$facts, function(fact) {
    transaction_id <- .transaction_import_transaction_id(
      context, batch_command_id, fact$source_row_ref
    )
    length(.transaction_import_fact_postings(transaction_id, fact))
  }, integer(1)))
  batch <- DBI::dbGetQuery(
    connection,
    "SELECT * FROM data_command_audit WHERE command_id=?",
    params = list(batch_command_id)
  )
  if (nrow(batch)) {
    if (nrow(batch) != 1L || !identical(batch$command_type[[1]], "legacy_transaction_import_v1") ||
        !identical(batch$entity_id[[1]], receipt$target_portfolio_id) ||
        !identical(batch$payload_fingerprint[[1]], validated$artifact$fingerprint) ||
        !identical(batch$origin_ref[[1]], .transaction_import_run_id(validated$artifact$fingerprint))) {
      .transaction_import_abort("transaction_import_idempotency_conflict")
    }
    expected <- lapply(validated$artifact$facts, function(fact) {
      .transaction_import_bundle(context, validated, fact, batch$committed_at_utc[[1]])
    })
    for (bundle in expected) {
      actual <- tryCatch(
        .transaction_validate_managed_transaction(connection, bundle$record$transaction_id, context),
        error = function(error) .transaction_import_abort("transaction_import_idempotency_conflict")
      )
      if (!identical(actual$record, bundle$record) || !identical(actual$postings, bundle$postings) ||
          !identical(actual$fingerprint, bundle$fingerprint)) {
        .transaction_import_abort("transaction_import_idempotency_conflict")
      }
    }
    imported_count <- as.integer(DBI::dbGetQuery(
      connection,
      "SELECT count(*) AS n FROM transaction_record WHERE origin_type='legacy_import' AND origin_ref LIKE ?",
      params = list(paste0(.transaction_import_origin_namespace(validated$artifact$fingerprint), "%"))
    )$n[[1]])
    if (imported_count != length(expected)) {
      .transaction_import_abort("transaction_import_idempotency_conflict")
    }
    return(list(
      status = "already_imported", receipt = receipt,
      batch_command_id = batch_command_id, posting_count = posting_count
    ))
  }
  transaction_count <- as.integer(DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM transaction_record")$n[[1]])
  transaction_audits <- as.integer(DBI::dbGetQuery(
    connection, "SELECT count(*) AS n FROM data_command_audit WHERE area_id='transaction_ledger'"
  )$n[[1]])
  if (transaction_count != 0L || transaction_audits != 0L) {
    .transaction_import_abort("transaction_import_target_not_empty")
  }
  list(
    status = "ready_for_confirmation", receipt = receipt,
    batch_command_id = batch_command_id, posting_count = posting_count
  )
}

.transaction_import_preflight_value <- function(validated, target) {
  list(
    transaction_import_contract_version = 1L,
    status = target$status,
    batch_command_id = target$batch_command_id,
    master_candidate_fingerprint = validated$binding$master_candidate_fingerprint,
    adapter_review_fingerprint = validated$binding$adapter_review_fingerprint,
    routing_fingerprint = validated$binding$routing_fingerprint,
    artifact_fingerprint = validated$artifact$fingerprint,
    transaction_count = length(validated$artifact$facts),
    posting_count = target$posting_count
  )
}

transaction_import_preflight_v1 <- function(context, staging_capability) {
  .transaction_import_boundary({
    .transaction_import_context_check(context)
    validated <- .transaction_import_open_stage(context, staging_capability)
    target <- .transaction_import_validate_target(context, validated)
    .transaction_import_preflight_value(validated, target)
  })
}

new_transaction_import_confirmation_authorizer_v1 <- function() {
  structure(
    list(entries = new.env(hash = TRUE, parent = emptyenv())),
    class = "spot_transaction_import_confirmation_authorizer_v1"
  )
}

.transaction_import_authorizer_valid <- function(authorizer) {
  inherits(authorizer, "spot_transaction_import_confirmation_authorizer_v1") &&
    is.list(authorizer) && identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

.transaction_import_time <- function(value) {
  if (!.canonical_utc_valid(value)) .transaction_import_abort("transaction_import_confirmation_invalid")
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

transaction_import_build_confirmation_v1 <- function(
  preflight, context, staging_capability, authorizer, challenge_id,
  issued_at_utc, confirmed_at_utc, expires_at_utc
) {
  .transaction_import_boundary({
    .transaction_import_context_check(context)
    if (!.transaction_import_authorizer_valid(authorizer) ||
        !is.character(challenge_id) || length(challenge_id) != 1L || is.na(challenge_id) ||
        !grepl("^tic_[a-z0-9_]{4,56}$", challenge_id)) {
      .transaction_import_abort("transaction_import_confirmation_invalid")
    }
    current <- transaction_import_preflight_v1(context, staging_capability)
    if (!is.list(preflight) || !identical(preflight, current) ||
        !identical(current$status, "ready_for_confirmation")) {
      .transaction_import_abort("transaction_import_confirmation_scope_mismatch")
    }
    issued <- .transaction_import_time(issued_at_utc)
    confirmed <- .transaction_import_time(confirmed_at_utc)
    expires <- .transaction_import_time(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires) ||
        as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .transaction_import_abort("transaction_import_confirmation_expired")
    }
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .transaction_import_abort("transaction_import_confirmation_duplicate")
    }
    payload <- list(
      transaction_import_confirmation_contract_version = 1L,
      challenge_id = challenge_id,
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      actor_id = context$actor_id,
      batch_command_id = current$batch_command_id,
      master_candidate_fingerprint = current$master_candidate_fingerprint,
      artifact_fingerprint = current$artifact_fingerprint,
      transaction_count = current$transaction_count,
      posting_count = current$posting_count,
      issued_at_utc = issued_at_utc,
      confirmed_at_utc = confirmed_at_utc,
      expires_at_utc = expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .import_fingerprint(payload)
    assign(challenge_id, list(
      fingerprint = confirmation$confirmation_fingerprint,
      consumed = FALSE
    ), envir = authorizer$entries)
    confirmation
  })
}

.transaction_import_validate_confirmation <- function(
  confirmation, preflight, context, authorizer, now_utc
) {
  if (!is.list(confirmation)) .transaction_import_abort("transaction_import_confirmation_missing")
  fingerprint <- confirmation$confirmation_fingerprint
  body <- confirmation[setdiff(names(confirmation), "confirmation_fingerprint")]
  if (!is.character(fingerprint) || length(fingerprint) != 1L ||
      !identical(.import_fingerprint(body), fingerprint) ||
      !identical(confirmation$tenant_id, context$tenant_id) ||
      !identical(confirmation$user_id, context$user_id) ||
      !identical(confirmation$data_space_id, context$data_space_id) ||
      !identical(confirmation$actor_id, context$actor_id) ||
      !identical(confirmation$batch_command_id, preflight$batch_command_id) ||
      !identical(confirmation$master_candidate_fingerprint, preflight$master_candidate_fingerprint) ||
      !identical(confirmation$artifact_fingerprint, preflight$artifact_fingerprint) ||
      !identical(confirmation$transaction_count, preflight$transaction_count) ||
      !identical(confirmation$posting_count, preflight$posting_count)) {
    .transaction_import_abort("transaction_import_confirmation_scope_mismatch")
  }
  issued <- .transaction_import_time(confirmation$issued_at_utc)
  confirmed <- .transaction_import_time(confirmation$confirmed_at_utc)
  expires <- .transaction_import_time(confirmation$expires_at_utc)
  now <- .transaction_import_time(now_utc)
  if (!(issued <= confirmed && confirmed <= now && now <= expires) ||
      as.numeric(difftime(expires, issued, units = "secs")) > 600) {
    .transaction_import_abort("transaction_import_confirmation_expired")
  }
  if (!.transaction_import_authorizer_valid(authorizer) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .transaction_import_abort("transaction_import_confirmation_not_authorized")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, fingerprint)) {
    .transaction_import_abort("transaction_import_confirmation_not_authorized")
  }
  if (isTRUE(entry$consumed)) .transaction_import_abort("transaction_import_confirmation_consumed")
  invisible(TRUE)
}

.transaction_import_consume_confirmation <- function(authorizer, confirmation) {
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  entry$consumed <- TRUE
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  invisible(TRUE)
}

.transaction_import_insert_bundle <- function(connection, bundle, context, committed_at_utc) {
  record <- bundle$record
  DBI::dbExecute(
    connection,
    paste(
      "INSERT INTO transaction_record",
      "(transaction_id, portfolio_id, transaction_type, record_action, effective_at_utc, local_date, memo,",
      "supersedes_transaction_id, origin_type, origin_ref, created_at_utc, created_by_actor)",
      "VALUES (?, ?, ?, 'book', ?, ?, ?, NULL, 'legacy_import', ?, ?, ?)"
    ),
    params = list(
      record$transaction_id, record$portfolio_id, record$transaction_type,
      record$effective_at_utc, record$local_date,
      if (is.null(record$memo)) NA_character_ else record$memo,
      record$origin_ref, committed_at_utc, context$actor_id
    )
  )
  for (posting in bundle$postings) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO transaction_posting",
        "(posting_id, transaction_id, sequence_no, account_id, asset_id, posting_role, quantity_decimal,",
        "unit_price_decimal, price_currency, valuation_amount_decimal, valuation_currency, memo)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)"
      ),
      params = list(
        posting$posting_id, record$transaction_id, posting$sequence_no,
        posting$account_id, posting$asset_id, posting$posting_role,
        posting$quantity_decimal,
        if (is.null(posting$unit_price_decimal)) NA_character_ else posting$unit_price_decimal,
        if (is.null(posting$price_currency)) NA_character_ else posting$price_currency,
        posting$valuation_amount_decimal, posting$valuation_currency
      )
    )
  }
  DBI::dbExecute(
    connection,
    "INSERT INTO transaction_seal VALUES (?, ?, ?, ?)",
    params = list(
      record$transaction_id, committed_at_utc, length(bundle$postings), bundle$fingerprint
    )
  )
  DBI::dbExecute(
    connection,
    paste(
      "INSERT INTO data_command_audit",
      "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref)",
      "VALUES (?, 'transaction_ledger', 'legacy_transaction_import_row_v1', ?, ?, ?, ?, 'legacy_import', ?)"
    ),
    params = list(
      bundle$command_id, record$transaction_id, context$actor_id, committed_at_utc,
      bundle$fingerprint, bundle$batch_command_id
    )
  )
}

.transaction_import_result <- function(status, preflight) {
  list(
    transaction_import_contract_version = 1L,
    status = status,
    batch_command_id = preflight$batch_command_id,
    artifact_fingerprint = preflight$artifact_fingerprint,
    transaction_count = preflight$transaction_count,
    posting_count = preflight$posting_count
  )
}

.transaction_import_execute_impl <- function(
  context, staging_capability, confirmation, authorizer, now_utc, failpoint = "none"
) {
  .transaction_import_context_check(context)
  if (!failpoint %in% c("none", "after_batch_audit", "after_records", "before_commit")) {
    .transaction_import_abort("transaction_import_boundary_failed")
  }
  validated <- .transaction_import_open_stage(context, staging_capability)
  target <- .transaction_import_validate_target(context, validated)
  preflight <- .transaction_import_preflight_value(validated, target)
  if (identical(preflight$status, "already_imported")) {
    return(.transaction_import_result("already_imported", preflight))
  }
  .transaction_import_validate_confirmation(confirmation, preflight, context, authorizer, now_utc)
  .transaction_import_consume_confirmation(authorizer, confirmation)
  lock <- tryCatch(
    .canonical_acquire_lock(runtime_data_space_path(context)),
    error = function(error) NULL
  )
  if (is.null(lock)) .transaction_import_abort("transaction_import_lock_unavailable")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .catalog_connect_write(context)
  on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbDisconnect(connection), silent = TRUE), add = TRUE)
  began <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    began <- TRUE
    locked_target <- .transaction_import_validate_target(context, validated)
    if (!identical(locked_target$status, "ready_for_confirmation")) {
      .transaction_import_abort("transaction_import_idempotency_conflict")
    }
    receipt <- locked_target$receipt
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
        "payload_fingerprint, origin_type, origin_ref)",
        "VALUES (?, 'canonical_import_receipt', 'legacy_transaction_import_v1', ?, ?, ?, ?, 'legacy_import', ?)"
      ),
      params = list(
        preflight$batch_command_id, receipt$target_portfolio_id, context$actor_id,
        now_utc, preflight$artifact_fingerprint,
        .transaction_import_run_id(preflight$artifact_fingerprint)
      )
    )
    if (identical(failpoint, "after_batch_audit")) {
      .transaction_import_abort("transaction_import_synthetic_failpoint")
    }
    bundles <- lapply(validated$artifact$facts, function(fact) {
      .transaction_import_bundle(context, validated, fact, now_utc)
    })
    for (bundle in bundles) .transaction_import_insert_bundle(connection, bundle, context, now_utc)
    if (identical(failpoint, "after_records")) {
      .transaction_import_abort("transaction_import_synthetic_failpoint")
    }
    for (bundle in bundles) {
      actual <- .transaction_validate_managed_transaction(
        connection, bundle$record$transaction_id, context
      )
      if (!identical(actual$fingerprint, bundle$fingerprint)) {
        .transaction_import_abort("transaction_import_canonical_transaction_failed")
      }
    }
    .transaction_validate_current_ledger(connection, receipt$target_portfolio_id, context)
    if (!identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok") ||
        nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L) {
      .transaction_import_abort("transaction_import_canonical_transaction_failed")
    }
    if (identical(failpoint, "before_commit")) {
      .transaction_import_abort("transaction_import_synthetic_failpoint")
    }
    DBI::dbExecute(connection, "COMMIT")
    began <- FALSE
    .transaction_import_result("committed", preflight)
  }, error = function(error) {
    if (began && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_transaction_import_data_command_error")) stop(error)
    .transaction_import_abort("transaction_import_canonical_transaction_failed")
  })
}

transaction_import_execute_v1 <- function(
  context, staging_capability, confirmation, authorizer, now_utc
) {
  .transaction_import_boundary(
    .transaction_import_execute_impl(
      context, staging_capability, confirmation, authorizer, now_utc, "none"
    ),
    fallback = "transaction_import_canonical_transaction_failed"
  )
}
