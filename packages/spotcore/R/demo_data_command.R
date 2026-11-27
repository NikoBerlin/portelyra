demo_data_command_error_codes <- function() {
  c(
    "demo_command_context_invalid",
    "demo_command_role_not_authorized",
    "demo_command_repository_invalid",
    "demo_command_candidate_invalid",
    "demo_command_idempotency_conflict",
    "demo_command_confirmation_missing",
    "demo_command_confirmation_invalid",
    "demo_command_confirmation_scope_mismatch",
    "demo_command_confirmation_time_invalid",
    "demo_command_confirmation_consumed",
    "demo_command_lock_unavailable",
    "demo_command_transaction_failed",
    "demo_command_boundary_failed"
  )
}

.demo_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% demo_data_command_error_codes()) {
    stop("unregistered_demo_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_demo_data_command_error", "error", "condition")
  )
}

.demo_abort <- function(code) stop(.demo_condition(code))

.demo_boundary_eval <- function(expression, fallback = "demo_command_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_demo_data_command_error = function(error) error,
    spot_canonical_repository_error = function(error) .demo_condition("demo_command_repository_invalid"),
    spot_runtime_error = function(error) .demo_condition("demo_command_context_invalid"),
    error = function(error) .demo_condition(fallback)
  )
  if (inherits(result, "spot_demo_data_command_error")) stop(result)
  result
}

.demo_sort_json_value <- function(value) {
  if (!is.list(value)) return(value)
  value <- lapply(value, .demo_sort_json_value)
  value_names <- names(value)
  if (!is.null(value_names) && length(value_names) && all(nzchar(value_names))) {
    value <- value[order(value_names, method = "radix")]
  }
  value
}

.demo_canonical_json_bytes <- function(value) {
  sorted <- .demo_sort_json_value(value)
  text <- jsonlite::toJSON(
    sorted,
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

.demo_fingerprint <- function(value) {
  digest::digest(.demo_canonical_json_bytes(value), algo = "sha256", serialize = FALSE)
}

.demo_nul_material <- function(parts) {
  if (!is.character(parts) || anyNA(parts)) .demo_abort("demo_command_candidate_invalid")
  material <- raw()
  for (index in seq_along(parts)) {
    if (index > 1L) material <- c(material, as.raw(0L))
    material <- c(material, charToRaw(enc2utf8(parts[[index]])))
  }
  material
}

.demo_hash_parts <- function(parts) {
  digest::digest(.demo_nul_material(parts), algo = "sha256", serialize = FALSE)
}

.demo_domain_v1 <- function() {
  list(
    profile = "desktop_demo_buy_sell_v1",
    portfolios = list(
      list(staged_portfolio_id = "sptf_demo_portfolio01", display_name = "Demo Portfolio", base_currency = "EUR")
    ),
    accounts = list(
      list(
        staged_account_id = "sacc_demo_cash0001",
        staged_portfolio_id = "sptf_demo_portfolio01",
        display_name = "Demo Cash",
        account_type = "cash"
      ),
      list(
        staged_account_id = "sacc_demo_depot001",
        staged_portfolio_id = "sptf_demo_portfolio01",
        display_name = "Demo Depot",
        account_type = "securities"
      )
    ),
    assets = list(
      list(
        staged_asset_id = "sast_demo_cash_eur01",
        display_name = "Demo EUR Cash",
        asset_type = "cash",
        price_currency = "EUR",
        quantity_scale = 2L,
        valuation_method = "unit_value",
        isin = NULL
      ),
      list(
        staged_asset_id = "sast_demo_etf00001",
        display_name = "Demo World ETF",
        asset_type = "etf",
        price_currency = "EUR",
        quantity_scale = 8L,
        valuation_method = "external_market",
        isin = NULL
      )
    ),
    transactions = list(
      list(
        staged_transaction_id = "stx_demo_buy000001",
        staged_portfolio_id = "sptf_demo_portfolio01",
        transaction_type = "buy",
        effective_at_utc = "2026-01-02T12:00:00Z",
        local_date = "2026-01-02"
      ),
      list(
        staged_transaction_id = "stx_demo_sell00001",
        staged_portfolio_id = "sptf_demo_portfolio01",
        transaction_type = "sell",
        effective_at_utc = "2026-02-02T12:00:00Z",
        local_date = "2026-02-02"
      )
    ),
    postings = list(
      list(
        staged_posting_id = "spst_demo_buy_asset1",
        staged_transaction_id = "stx_demo_buy000001",
        sequence_no = 1L,
        staged_account_id = "sacc_demo_depot001",
        staged_asset_id = "sast_demo_etf00001",
        posting_role = "asset",
        quantity_decimal = "10",
        unit_price_decimal = "100",
        price_currency = "EUR",
        valuation_amount_decimal = "1000",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_buy_cash01",
        staged_transaction_id = "stx_demo_buy000001",
        sequence_no = 2L,
        staged_account_id = "sacc_demo_cash0001",
        staged_asset_id = "sast_demo_cash_eur01",
        posting_role = "cash",
        quantity_decimal = "-1000",
        unit_price_decimal = NULL,
        price_currency = NULL,
        valuation_amount_decimal = "-1000",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_buy_fee001",
        staged_transaction_id = "stx_demo_buy000001",
        sequence_no = 3L,
        staged_account_id = "sacc_demo_cash0001",
        staged_asset_id = "sast_demo_cash_eur01",
        posting_role = "fee",
        quantity_decimal = "-1",
        unit_price_decimal = NULL,
        price_currency = NULL,
        valuation_amount_decimal = "-1",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_sell_asset",
        staged_transaction_id = "stx_demo_sell00001",
        sequence_no = 1L,
        staged_account_id = "sacc_demo_depot001",
        staged_asset_id = "sast_demo_etf00001",
        posting_role = "asset",
        quantity_decimal = "-4",
        unit_price_decimal = "120",
        price_currency = "EUR",
        valuation_amount_decimal = "-480",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_sell_cash1",
        staged_transaction_id = "stx_demo_sell00001",
        sequence_no = 2L,
        staged_account_id = "sacc_demo_cash0001",
        staged_asset_id = "sast_demo_cash_eur01",
        posting_role = "cash",
        quantity_decimal = "480",
        unit_price_decimal = NULL,
        price_currency = NULL,
        valuation_amount_decimal = "480",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_sell_fee01",
        staged_transaction_id = "stx_demo_sell00001",
        sequence_no = 3L,
        staged_account_id = "sacc_demo_cash0001",
        staged_asset_id = "sast_demo_cash_eur01",
        posting_role = "fee",
        quantity_decimal = "-1",
        unit_price_decimal = NULL,
        price_currency = NULL,
        valuation_amount_decimal = "-1",
        valuation_currency = "EUR"
      ),
      list(
        staged_posting_id = "spst_demo_sell_tax01",
        staged_transaction_id = "stx_demo_sell00001",
        sequence_no = 4L,
        staged_account_id = "sacc_demo_cash0001",
        staged_asset_id = "sast_demo_cash_eur01",
        posting_role = "tax",
        quantity_decimal = "-5",
        unit_price_decimal = NULL,
        price_currency = NULL,
        valuation_amount_decimal = "-5",
        valuation_currency = "EUR"
      )
    ),
    semantics_summary = list(
      acquired_quantity_decimal = "10",
      disposed_quantity_decimal = "4",
      remaining_quantity_decimal = "6",
      acquisition_cost_including_fees_decimal = "1001",
      fifo_cost_consumed_decimal = "400.4",
      fifo_cost_remaining_decimal = "600.6",
      realized_gain_pre_tax_decimal = "78.6",
      recorded_fee_cash_paid_decimal = "2",
      recorded_tax_cash_paid_decimal = "5"
    )
  )
}

.demo_expected_domain_fingerprint <- "203cd75e92b7892b5b6dfd6919378c0cabc0e0c7a96c952a4e391a24d5eb4559"

.demo_candidate_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .demo_abort("demo_command_context_invalid")
  }
  domain <- .demo_domain_v1()
  domain_fingerprint <- .demo_fingerprint(domain)
  if (!identical(domain_fingerprint, .demo_expected_domain_fingerprint)) {
    .demo_abort("demo_command_candidate_invalid")
  }
  counts <- list(
    portfolio_count = length(domain$portfolios),
    account_count = length(domain$accounts),
    asset_count = length(domain$assets),
    transaction_count = length(domain$transactions),
    posting_count = length(domain$postings)
  )
  candidate <- list(
    demo_candidate_contract_version = 1L,
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    domain_fingerprint = domain_fingerprint,
    counts = counts,
    domain = domain
  )
  list(
    manifest = candidate,
    candidate_fingerprint = .demo_fingerprint(candidate),
    counts = counts,
    domain = domain
  )
}

.demo_deterministic_id <- function(prefix, candidate_fingerprint, kind, staged_id) {
  paste0(prefix, substr(.demo_hash_parts(c(candidate_fingerprint, kind, staged_id)), 1L, 24L))
}

.demo_mapping_v1 <- function(candidate) {
  mappings <- list(portfolio = list(), account = list(), asset = list(), transaction = list(), posting = list())
  specifications <- list(
    portfolio = list(rows = candidate$domain$portfolios, staged = "staged_portfolio_id", prefix = "ptf_"),
    account = list(rows = candidate$domain$accounts, staged = "staged_account_id", prefix = "acc_"),
    asset = list(rows = candidate$domain$assets, staged = "staged_asset_id", prefix = "ast_"),
    transaction = list(rows = candidate$domain$transactions, staged = "staged_transaction_id", prefix = "txn_"),
    posting = list(rows = candidate$domain$postings, staged = "staged_posting_id", prefix = "pst_")
  )
  for (kind in names(specifications)) {
    specification <- specifications[[kind]]
    for (row in specification$rows) {
      staged_id <- row[[specification$staged]]
      mappings[[kind]][[staged_id]] <- .demo_deterministic_id(
        specification$prefix,
        candidate$candidate_fingerprint,
        kind,
        staged_id
      )
    }
  }
  mappings
}

.demo_parent_command_id <- function(context, candidate_fingerprint) {
  paste0(
    "cmd_demo_",
    substr(
      .demo_hash_parts(c(
        "desktop-demo-seed-command-v1", context$tenant_id, context$user_id,
        context$data_space_id, candidate_fingerprint
      )),
      1L,
      52L
    )
  )
}

.demo_audit_command_id <- function(context, candidate_fingerprint, area_id, entity_id) {
  paste0(
    "cmd_demo_",
    substr(
      .demo_hash_parts(c(
        "desktop-demo-seed-audit-v1", context$tenant_id, context$user_id,
        context$data_space_id, candidate_fingerprint, area_id, entity_id
      )),
      1L,
      52L
    )
  )
}

new_demo_confirmation_authorizer_v1 <- function() {
  structure(
    list(entries = new.env(hash = TRUE, parent = emptyenv())),
    class = "spot_demo_confirmation_authorizer_v1"
  )
}

.demo_authorizer_valid <- function(authorizer) {
  inherits(authorizer, "spot_demo_confirmation_authorizer_v1") &&
    is.list(authorizer) && identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

.demo_confirmation_payload <- function(preflight, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc) {
  list(
    confirmation_contract_version = 1L,
    challenge_id = challenge_id,
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    candidate_fingerprint = preflight$candidate_fingerprint,
    counts = preflight$counts,
    issued_at_utc = issued_at_utc,
    confirmed_at_utc = confirmed_at_utc,
    expires_at_utc = expires_at_utc
  )
}

.demo_challenge_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    grepl("^cfm_[a-z0-9_]+$", value) && nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L
}

.demo_time_value <- function(value) {
  if (!.canonical_utc_valid(value)) .demo_abort("demo_command_confirmation_time_invalid")
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

demo_seed_build_confirmation_v1 <- function(
  preflight,
  context,
  authorizer,
  challenge_id,
  issued_at_utc,
  confirmed_at_utc,
  expires_at_utc
) {
  .demo_boundary_eval({
    if (!is.list(preflight) || !identical(preflight$status, "ready_for_confirmation")) {
      .demo_abort("demo_command_confirmation_invalid")
    }
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "desktop_owner") {
      .demo_abort("demo_command_context_invalid")
    }
    if (!.demo_authorizer_valid(authorizer) || !.demo_challenge_valid(challenge_id)) {
      .demo_abort("demo_command_confirmation_invalid")
    }
    issued <- .demo_time_value(issued_at_utc)
    confirmed <- .demo_time_value(confirmed_at_utc)
    expires <- .demo_time_value(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires) || as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .demo_abort("demo_command_confirmation_time_invalid")
    }
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .demo_abort("demo_command_confirmation_invalid")
    }
    candidate <- .demo_candidate_v1(context)
    if (!identical(preflight$candidate_fingerprint, candidate$candidate_fingerprint) || !identical(preflight$counts, candidate$counts)) {
      .demo_abort("demo_command_confirmation_scope_mismatch")
    }
    payload <- .demo_confirmation_payload(
      preflight, context, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .demo_fingerprint(payload)
    assign(
      challenge_id,
      list(fingerprint = confirmation$confirmation_fingerprint, consumed = FALSE),
      envir = authorizer$entries
    )
    confirmation
  })
}

.demo_validate_confirmation <- function(confirmation, candidate, context, now_utc) {
  if (!is.list(confirmation)) .demo_abort("demo_command_confirmation_missing")
  required <- c(
    "confirmation_contract_version", "challenge_id", "tenant_id", "user_id", "data_space_id",
    "actor_id", "role", "candidate_fingerprint", "counts", "issued_at_utc",
    "confirmed_at_utc", "expires_at_utc", "confirmation_fingerprint"
  )
  if (!setequal(names(confirmation), required) || !identical(confirmation$confirmation_contract_version, 1L) || !.demo_challenge_valid(confirmation$challenge_id)) {
    .demo_abort("demo_command_confirmation_invalid")
  }
  payload <- confirmation[setdiff(names(confirmation), "confirmation_fingerprint")]
  if (!identical(.demo_fingerprint(payload), confirmation$confirmation_fingerprint)) {
    .demo_abort("demo_command_confirmation_invalid")
  }
  expected <- list(
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    candidate_fingerprint = candidate$candidate_fingerprint,
    counts = candidate$counts
  )
  for (name in names(expected)) {
    if (!identical(confirmation[[name]], expected[[name]])) .demo_abort("demo_command_confirmation_scope_mismatch")
  }
  issued <- .demo_time_value(confirmation$issued_at_utc)
  confirmed <- .demo_time_value(confirmation$confirmed_at_utc)
  expires <- .demo_time_value(confirmation$expires_at_utc)
  now <- .demo_time_value(now_utc)
  if (!(issued <= confirmed && confirmed <= now && now <= expires) || as.numeric(difftime(expires, issued, units = "secs")) > 600) {
    .demo_abort("demo_command_confirmation_time_invalid")
  }
  invisible(TRUE)
}

.demo_consume_confirmation <- function(authorizer, confirmation) {
  if (!.demo_authorizer_valid(authorizer) || !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .demo_abort("demo_command_confirmation_invalid")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, confirmation$confirmation_fingerprint)) {
    .demo_abort("demo_command_confirmation_invalid")
  }
  if (isTRUE(entry$consumed)) .demo_abort("demo_command_confirmation_consumed")
  entry$consumed <- TRUE
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  invisible(TRUE)
}

.demo_expected_entities <- function(candidate, context, committed_at_utc) {
  mappings <- .demo_mapping_v1(candidate)
  portfolio_id <- unname(unlist(mappings$portfolio, use.names = FALSE)[[1]])
  audit_entities <- list()
  for (row in candidate$domain$portfolios) {
    audit_entities[[length(audit_entities) + 1L]] <- list(area = "portfolio_catalog", entity = mappings$portfolio[[row$staged_portfolio_id]])
  }
  for (row in candidate$domain$accounts) {
    audit_entities[[length(audit_entities) + 1L]] <- list(area = "account_catalog", entity = mappings$account[[row$staged_account_id]])
  }
  for (row in candidate$domain$assets) {
    audit_entities[[length(audit_entities) + 1L]] <- list(area = "asset_catalog", entity = mappings$asset[[row$staged_asset_id]])
  }
  for (row in candidate$domain$transactions) {
    audit_entities[[length(audit_entities) + 1L]] <- list(area = "transaction_ledger", entity = mappings$transaction[[row$staged_transaction_id]])
  }
  audits <- lapply(audit_entities, function(item) {
    list(
      command_id = .demo_audit_command_id(context, candidate$candidate_fingerprint, item$area, item$entity),
      area_id = item$area,
      command_type = "desktop_demo_seed_v1",
      entity_id = item$entity,
      actor_id = context$actor_id,
      committed_at_utc = committed_at_utc,
      payload_fingerprint = candidate$candidate_fingerprint,
      origin_type = "native",
      origin_ref = NULL
    )
  })
  list(mappings = mappings, portfolio_id = portfolio_id, audits = audits)
}

.demo_core_counts <- function(connection) {
  tables <- c(
    portfolio_count = "portfolio",
    account_count = "account",
    asset_count = "asset",
    provider_mapping_count = "provider_mapping",
    transaction_count = "transaction_record",
    posting_count = "transaction_posting",
    seal_count = "transaction_seal",
    audit_count = "data_command_audit",
    receipt_count = "canonical_import_receipt"
  )
  as.list(vapply(tables, function(table) {
    as.integer(DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1]])
  }, integer(1)))
}

.demo_target_empty <- function(counts) all(unlist(counts, use.names = FALSE) == 0L)

.demo_rows_identical <- function(actual, expected, columns) {
  if (nrow(actual) != length(expected)) return(FALSE)
  actual <- actual[order(actual[[columns[[1]]]], method = "radix"), columns, drop = FALSE]
  expected_values <- lapply(expected, function(row) {
    value <- lapply(columns, function(column) row[[column]])
    names(value) <- columns
    value
  })
  expected_values <- expected_values[order(vapply(expected_values, function(row) row[[columns[[1]]]], character(1)), method = "radix")]
  for (index in seq_along(expected_values)) {
    for (column in columns) {
      actual_value <- actual[[column]][[index]]
      expected_value <- expected_values[[index]][[column]]
      if (is.null(expected_value)) {
        if (!is.na(actual_value)) return(FALSE)
      } else if (is.integer(expected_value)) {
        if (!identical(as.integer(actual_value), expected_value)) return(FALSE)
      } else if (!identical(as.character(actual_value), as.character(expected_value))) {
        return(FALSE)
      }
    }
  }
  TRUE
}

.demo_existing_exact <- function(connection, candidate, context) {
  counts <- .demo_core_counts(connection)
  expected_counts <- c(
    portfolio_count = candidate$counts$portfolio_count,
    account_count = candidate$counts$account_count,
    asset_count = candidate$counts$asset_count,
    provider_mapping_count = 0L,
    transaction_count = candidate$counts$transaction_count,
    posting_count = candidate$counts$posting_count,
    seal_count = candidate$counts$transaction_count,
    audit_count = 7L,
    receipt_count = 0L
  )
  if (!identical(unlist(counts, use.names = TRUE), expected_counts)) return(FALSE)
  mappings <- .demo_mapping_v1(candidate)
  portfolios <- DBI::dbGetQuery(connection, "SELECT * FROM portfolio ORDER BY portfolio_id")
  if (nrow(portfolios) != 1L || portfolios$portfolio_id[[1]] != mappings$portfolio[["sptf_demo_portfolio01"]] ||
      portfolios$display_name[[1]] != "Demo Portfolio" || portfolios$base_currency[[1]] != "EUR" ||
      portfolios$status[[1]] != "active" || portfolios$origin_type[[1]] != "native" ||
      !is.na(portfolios$origin_ref[[1]]) || as.integer(portfolios$revision[[1]]) != 1L) return(FALSE)
  committed_at <- portfolios$created_at_utc[[1]]
  if (!.canonical_utc_valid(committed_at) || portfolios$updated_at_utc[[1]] != committed_at) return(FALSE)
  accounts <- DBI::dbGetQuery(connection, "SELECT * FROM account ORDER BY account_id")
  expected_accounts <- lapply(candidate$domain$accounts, function(row) list(
    account_id = mappings$account[[row$staged_account_id]],
    portfolio_id = mappings$portfolio[[row$staged_portfolio_id]],
    display_name = row$display_name,
    account_type = row$account_type,
    institution_label = NULL,
    status = "active",
    origin_type = "native",
    origin_ref = NULL,
    created_at_utc = committed_at,
    updated_at_utc = committed_at,
    revision = 1L
  ))
  if (!.demo_rows_identical(accounts, expected_accounts, c("account_id", "portfolio_id", "display_name", "account_type", "institution_label", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"))) return(FALSE)
  assets <- DBI::dbGetQuery(connection, "SELECT * FROM asset ORDER BY asset_id")
  expected_assets <- lapply(candidate$domain$assets, function(row) list(
    asset_id = mappings$asset[[row$staged_asset_id]],
    display_name = row$display_name,
    asset_type = row$asset_type,
    price_currency = row$price_currency,
    quantity_scale = row$quantity_scale,
    valuation_method = row$valuation_method,
    isin = row$isin,
    status = "active",
    origin_type = "native",
    origin_ref = NULL,
    created_at_utc = committed_at,
    updated_at_utc = committed_at,
    revision = 1L
  ))
  if (!.demo_rows_identical(assets, expected_assets, c("asset_id", "display_name", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"))) return(FALSE)
  transactions <- DBI::dbGetQuery(connection, "SELECT * FROM transaction_record ORDER BY transaction_id")
  expected_transactions <- lapply(candidate$domain$transactions, function(row) list(
    transaction_id = mappings$transaction[[row$staged_transaction_id]],
    portfolio_id = mappings$portfolio[[row$staged_portfolio_id]],
    transaction_type = row$transaction_type,
    record_action = "book",
    effective_at_utc = row$effective_at_utc,
    local_date = row$local_date,
    memo = NULL,
    supersedes_transaction_id = NULL,
    origin_type = "native",
    origin_ref = NULL,
    created_at_utc = committed_at,
    created_by_actor = context$actor_id
  ))
  if (!.demo_rows_identical(transactions, expected_transactions, c("transaction_id", "portfolio_id", "transaction_type", "record_action", "effective_at_utc", "local_date", "memo", "supersedes_transaction_id", "origin_type", "origin_ref", "created_at_utc", "created_by_actor"))) return(FALSE)
  postings <- DBI::dbGetQuery(connection, "SELECT * FROM transaction_posting ORDER BY posting_id")
  expected_postings <- lapply(candidate$domain$postings, function(row) list(
    posting_id = mappings$posting[[row$staged_posting_id]],
    transaction_id = mappings$transaction[[row$staged_transaction_id]],
    sequence_no = row$sequence_no,
    account_id = mappings$account[[row$staged_account_id]],
    asset_id = mappings$asset[[row$staged_asset_id]],
    posting_role = row$posting_role,
    quantity_decimal = row$quantity_decimal,
    unit_price_decimal = row$unit_price_decimal,
    price_currency = row$price_currency,
    valuation_amount_decimal = row$valuation_amount_decimal,
    valuation_currency = row$valuation_currency,
    memo = NULL
  ))
  if (!.demo_rows_identical(postings, expected_postings, c("posting_id", "transaction_id", "sequence_no", "account_id", "asset_id", "posting_role", "quantity_decimal", "unit_price_decimal", "price_currency", "valuation_amount_decimal", "valuation_currency", "memo"))) return(FALSE)
  expected <- .demo_expected_entities(candidate, context, committed_at)
  audits <- DBI::dbGetQuery(connection, "SELECT * FROM data_command_audit ORDER BY command_id")
  if (!.demo_rows_identical(audits, expected$audits, c("command_id", "area_id", "command_type", "entity_id", "actor_id", "committed_at_utc", "payload_fingerprint", "origin_type", "origin_ref"))) return(FALSE)
  seals <- DBI::dbGetQuery(connection, "SELECT * FROM transaction_seal ORDER BY transaction_id")
  if (nrow(seals) != 2L || any(seals$sealed_at_utc != committed_at)) return(FALSE)
  if (DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM current_transaction")$n[[1]] != candidate$counts$transaction_count ||
      DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM current_transaction_posting")$n[[1]] != candidate$counts$posting_count) return(FALSE)
  for (transaction in candidate$domain$transactions) {
    transaction_id <- mappings$transaction[[transaction$staged_transaction_id]]
    transaction_postings <- Filter(
      function(posting) identical(posting$staged_transaction_id, transaction$staged_transaction_id),
      candidate$domain$postings
    )
    canonical_postings <- lapply(transaction_postings, function(posting) list(
      posting_id = mappings$posting[[posting$staged_posting_id]],
      sequence_no = posting$sequence_no,
      account_id = mappings$account[[posting$staged_account_id]],
      asset_id = mappings$asset[[posting$staged_asset_id]],
      posting_role = posting$posting_role,
      quantity_decimal = posting$quantity_decimal,
      unit_price_decimal = posting$unit_price_decimal,
      price_currency = posting$price_currency,
      valuation_amount_decimal = posting$valuation_amount_decimal,
      valuation_currency = posting$valuation_currency
    ))
    content <- list(
      transaction_id = transaction_id,
      portfolio_id = mappings$portfolio[[transaction$staged_portfolio_id]],
      transaction_type = transaction$transaction_type,
      effective_at_utc = transaction$effective_at_utc,
      local_date = transaction$local_date,
      postings = canonical_postings
    )
    seal <- seals[seals$transaction_id == transaction_id, , drop = FALSE]
    if (nrow(seal) != 1L || as.integer(seal$posting_count[[1]]) != length(canonical_postings) || seal$content_fingerprint[[1]] != .demo_fingerprint(content)) return(FALSE)
  }
  TRUE
}

.demo_state <- function(connection, candidate, context) {
  counts <- .demo_core_counts(connection)
  if (.demo_target_empty(counts)) return("new_candidate")
  if (.demo_existing_exact(connection, candidate, context)) return("already_seeded")
  "idempotency_conflict"
}

demo_seed_preflight_v1 <- function(context) {
  .demo_boundary_eval({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
      .demo_abort("demo_command_context_invalid")
    }
    if (context$role != "desktop_owner") .demo_abort("demo_command_role_not_authorized")
    candidate <- .demo_candidate_v1(context)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    state <- .demo_state(connection, candidate, context)
    if (state == "idempotency_conflict") .demo_abort("demo_command_idempotency_conflict")
    list(
      contract_version = 1L,
      status = if (state == "new_candidate") "ready_for_confirmation" else "already_seeded",
      parent_command_id = .demo_parent_command_id(context, candidate$candidate_fingerprint),
      candidate_fingerprint = candidate$candidate_fingerprint,
      domain_fingerprint = candidate$manifest$domain_fingerprint,
      counts = candidate$counts,
      semantics_summary = candidate$domain$semantics_summary,
      display_summary = list(
        portfolio = "Demo Portfolio",
        accounts = c("Demo Cash", "Demo Depot"),
        assets = c("Demo EUR Cash", "Demo World ETF")
      )
    )
  })
}

.demo_connect_write <- function(context) {
  path <- runtime_canonical_path(context)
  if (.canonical_symlink(path) || !file.exists(path) || dir.exists(path)) {
    .demo_abort("demo_command_repository_invalid")
  }
  connection <- DBI::dbConnect(RSQLite::SQLite(), dbname = path, flags = RSQLite::SQLITE_RW)
  valid <- FALSE
  tryCatch({
    DBI::dbExecute(connection, "PRAGMA foreign_keys = ON")
    DBI::dbExecute(connection, "PRAGMA query_only = OFF")
    DBI::dbExecute(connection, "PRAGMA busy_timeout = 0")
    .canonical_validate_connection(connection, context)
    valid <- TRUE
  }, error = function(error) {
    try(DBI::dbDisconnect(connection), silent = TRUE)
    if (inherits(error, "spot_demo_data_command_error")) stop(error)
    .demo_abort("demo_command_repository_invalid")
  })
  if (!valid) .demo_abort("demo_command_repository_invalid")
  connection
}

.demo_db_param <- function(value) {
  if (is.null(value)) NA_character_ else value
}

.demo_insert_candidate <- function(connection, candidate, context, committed_at_utc) {
  expected <- .demo_expected_entities(candidate, context, committed_at_utc)
  mappings <- expected$mappings
  for (row in candidate$domain$portfolios) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO portfolio",
        "(portfolio_id, display_name, base_currency, origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, 'native', NULL, ?, ?)"
      ),
      params = list(
        mappings$portfolio[[row$staged_portfolio_id]], row$display_name, row$base_currency,
        committed_at_utc, committed_at_utc
      )
    )
  }
  for (row in candidate$domain$accounts) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO account",
        "(account_id, portfolio_id, display_name, account_type, origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, ?, 'native', NULL, ?, ?)"
      ),
      params = list(
        mappings$account[[row$staged_account_id]], mappings$portfolio[[row$staged_portfolio_id]],
        row$display_name, row$account_type, committed_at_utc, committed_at_utc
      )
    )
  }
  for (row in candidate$domain$assets) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO asset",
        "(asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method, isin,",
        "origin_type, origin_ref, created_at_utc, updated_at_utc)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'native', NULL, ?, ?)"
      ),
      params = list(
        mappings$asset[[row$staged_asset_id]], row$display_name, row$asset_type,
        row$price_currency, row$quantity_scale, row$valuation_method, .demo_db_param(row$isin),
        committed_at_utc, committed_at_utc
      )
    )
  }
  for (transaction in candidate$domain$transactions) {
    transaction_id <- mappings$transaction[[transaction$staged_transaction_id]]
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO transaction_record",
        "(transaction_id, portfolio_id, transaction_type, record_action, effective_at_utc, local_date,",
        "origin_type, origin_ref, created_at_utc, created_by_actor)",
        "VALUES (?, ?, ?, 'book', ?, ?, 'native', NULL, ?, ?)"
      ),
      params = list(
        transaction_id, mappings$portfolio[[transaction$staged_portfolio_id]], transaction$transaction_type,
        transaction$effective_at_utc, transaction$local_date, committed_at_utc, context$actor_id
      )
    )
    transaction_postings <- Filter(
      function(posting) identical(posting$staged_transaction_id, transaction$staged_transaction_id),
      candidate$domain$postings
    )
    canonical_postings <- list()
    for (posting in transaction_postings) {
      posting_id <- mappings$posting[[posting$staged_posting_id]]
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO transaction_posting",
          "(posting_id, transaction_id, sequence_no, account_id, asset_id, posting_role, quantity_decimal,",
          "unit_price_decimal, price_currency, valuation_amount_decimal, valuation_currency)",
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        params = list(
          posting_id, transaction_id, posting$sequence_no,
          mappings$account[[posting$staged_account_id]], mappings$asset[[posting$staged_asset_id]],
          posting$posting_role, posting$quantity_decimal, .demo_db_param(posting$unit_price_decimal),
          .demo_db_param(posting$price_currency), posting$valuation_amount_decimal, posting$valuation_currency
        )
      )
      canonical_postings[[length(canonical_postings) + 1L]] <- list(
        posting_id = posting_id,
        sequence_no = posting$sequence_no,
        account_id = mappings$account[[posting$staged_account_id]],
        asset_id = mappings$asset[[posting$staged_asset_id]],
        posting_role = posting$posting_role,
        quantity_decimal = posting$quantity_decimal,
        unit_price_decimal = posting$unit_price_decimal,
        price_currency = posting$price_currency,
        valuation_amount_decimal = posting$valuation_amount_decimal,
        valuation_currency = posting$valuation_currency
      )
    }
    content <- list(
      transaction_id = transaction_id,
      portfolio_id = mappings$portfolio[[transaction$staged_portfolio_id]],
      transaction_type = transaction$transaction_type,
      effective_at_utc = transaction$effective_at_utc,
      local_date = transaction$local_date,
      postings = canonical_postings
    )
    DBI::dbExecute(
      connection,
      "INSERT INTO transaction_seal VALUES (?, ?, ?, ?)",
      params = list(transaction_id, committed_at_utc, length(canonical_postings), .demo_fingerprint(content))
    )
  }
  for (audit in expected$audits) {
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
        "payload_fingerprint, origin_type, origin_ref)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'native', NULL)"
      ),
      params = list(
        audit$command_id, audit$area_id, audit$command_type, audit$entity_id,
        audit$actor_id, audit$committed_at_utc, audit$payload_fingerprint
      )
    )
  }
  invisible(expected$portfolio_id)
}

.demo_seed_execute_impl <- function(context, confirmation, authorizer, now_utc, failpoint = "none") {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .demo_abort("demo_command_context_invalid")
  }
  if (context$role != "desktop_owner") .demo_abort("demo_command_role_not_authorized")
  if (!failpoint %in% c("none", "after_entities", "before_commit")) {
    .demo_abort("demo_command_candidate_invalid")
  }
  candidate <- .demo_candidate_v1(context)
  preflight <- demo_seed_preflight_v1(context)
  if (preflight$status == "already_seeded") {
    return(list(
      contract_version = 1L,
      status = "already_seeded",
      parent_command_id = preflight$parent_command_id,
      candidate_fingerprint = candidate$candidate_fingerprint,
      counts = candidate$counts
    ))
  }
  .demo_validate_confirmation(confirmation, candidate, context, now_utc)
  data_space <- runtime_data_space_path(context)
  lock <- tryCatch(.canonical_acquire_lock(data_space), spot_canonical_repository_error = function(error) NULL)
  if (is.null(lock)) .demo_abort("demo_command_lock_unavailable")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .demo_connect_write(context)
  on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
  locked_state <- .demo_state(connection, candidate, context)
  if (locked_state == "already_seeded") {
    return(list(
      contract_version = 1L,
      status = "already_seeded",
      parent_command_id = preflight$parent_command_id,
      candidate_fingerprint = candidate$candidate_fingerprint,
      counts = candidate$counts
    ))
  }
  if (locked_state != "new_candidate") .demo_abort("demo_command_idempotency_conflict")
  .demo_consume_confirmation(authorizer, confirmation)
  tryCatch({
    DBI::dbExecute(connection, "BEGIN IMMEDIATE")
    if (.demo_state(connection, candidate, context) != "new_candidate") {
      .demo_abort("demo_command_idempotency_conflict")
    }
    .demo_insert_candidate(connection, candidate, context, now_utc)
    if (failpoint == "after_entities") stop("synthetic_failpoint", call. = FALSE)
    if (!.demo_existing_exact(connection, candidate, context)) {
      .demo_abort("demo_command_transaction_failed")
    }
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L ||
        !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
      .demo_abort("demo_command_transaction_failed")
    }
    if (failpoint == "before_commit") stop("synthetic_failpoint", call. = FALSE)
    DBI::dbExecute(connection, "COMMIT")
  }, error = function(error) {
    if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    if (inherits(error, "spot_demo_data_command_error")) stop(error)
    .demo_abort("demo_command_transaction_failed")
  })
  list(
    contract_version = 1L,
    status = "committed",
    parent_command_id = preflight$parent_command_id,
    candidate_fingerprint = candidate$candidate_fingerprint,
    counts = candidate$counts
  )
}

demo_seed_execute_v1 <- function(context, confirmation, authorizer, now_utc) {
  .demo_boundary_eval(
    .demo_seed_execute_impl(context, confirmation, authorizer, now_utc, failpoint = "none"),
    fallback = "demo_command_transaction_failed"
  )
}
