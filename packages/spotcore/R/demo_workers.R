demo_portfolio_worker_error_codes <- function() {
  c(
    "demo_portfolio_worker_context_invalid",
    "demo_portfolio_worker_repository_invalid",
    "demo_portfolio_worker_source_invalid",
    "demo_portfolio_worker_market_invalid",
    "demo_portfolio_worker_time_invalid",
    "demo_portfolio_worker_calculation_invalid",
    "demo_portfolio_worker_boundary_failed"
  )
}

demo_tax_worker_error_codes <- function() {
  c(
    "demo_tax_worker_context_invalid",
    "demo_tax_worker_repository_invalid",
    "demo_tax_worker_source_invalid",
    "demo_tax_worker_time_invalid",
    "demo_tax_worker_calculation_invalid",
    "demo_tax_worker_boundary_failed"
  )
}

.demo_worker_condition <- function(code, type) {
  allowed <- if (type == "portfolio") demo_portfolio_worker_error_codes() else demo_tax_worker_error_codes()
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% allowed) {
    stop("unregistered_demo_worker_error_code", call. = FALSE)
  }
  class_name <- if (type == "portfolio") "spot_demo_portfolio_worker_error" else "spot_demo_tax_worker_error"
  structure(list(message = code, call = NULL, code = code), class = c(class_name, "error", "condition"))
}

.demo_portfolio_abort <- function(code) stop(.demo_worker_condition(code, "portfolio"))
.demo_tax_abort <- function(code) stop(.demo_worker_condition(code, "tax"))

.demo_portfolio_boundary <- function(expression, fallback = "demo_portfolio_worker_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_demo_portfolio_worker_error = function(error) error,
    spot_canonical_repository_error = function(error) .demo_worker_condition("demo_portfolio_worker_repository_invalid", "portfolio"),
    spot_demo_data_command_error = function(error) .demo_worker_condition("demo_portfolio_worker_source_invalid", "portfolio"),
    error = function(error) .demo_worker_condition(fallback, "portfolio")
  )
  if (inherits(result, "spot_demo_portfolio_worker_error")) stop(result)
  result
}

.demo_tax_boundary <- function(expression, fallback = "demo_tax_worker_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_demo_tax_worker_error = function(error) error,
    spot_canonical_repository_error = function(error) .demo_worker_condition("demo_tax_worker_repository_invalid", "tax"),
    spot_demo_data_command_error = function(error) .demo_worker_condition("demo_tax_worker_source_invalid", "tax"),
    error = function(error) .demo_worker_condition(fallback, "tax")
  )
  if (inherits(result, "spot_demo_tax_worker_error")) stop(result)
  result
}

.demo_frame_rows <- function(frame) {
  rows <- vector("list", nrow(frame))
  for (row_index in seq_len(nrow(frame))) {
    row <- vector("list", ncol(frame))
    names(row) <- names(frame)
    for (column_index in seq_along(frame)) {
      value <- frame[[column_index]][[row_index]]
      if (length(value) != 1L || is.na(value)) {
        row[column_index] <- list(NULL)
      } else if (is.integer(frame[[column_index]])) {
        row[[column_index]] <- as.integer(value)
      } else {
        row[[column_index]] <- as.character(value)
      }
    }
    rows[[row_index]] <- row
  }
  rows
}

.demo_transaction_set_fingerprint <- function(connection, portfolio_id) {
  transactions_frame <- DBI::dbGetQuery(
    connection,
    "SELECT * FROM transaction_record WHERE portfolio_id=? ORDER BY transaction_id",
    params = list(portfolio_id)
  )
  current_count <- DBI::dbGetQuery(
    connection,
    "SELECT count(*) AS n FROM current_transaction WHERE portfolio_id=?",
    params = list(portfolio_id)
  )$n[[1]]
  if (nrow(transactions_frame) != current_count || any(transactions_frame$record_action != "book")) {
    .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  }
  transactions <- .demo_frame_rows(transactions_frame)
  manifest <- list()
  for (transaction in transactions) {
    postings_frame <- DBI::dbGetQuery(
      connection,
      "SELECT * FROM transaction_posting WHERE transaction_id=? ORDER BY sequence_no, posting_id",
      params = list(transaction$transaction_id)
    )
    seal_frame <- DBI::dbGetQuery(
      connection,
      "SELECT * FROM transaction_seal WHERE transaction_id=?",
      params = list(transaction$transaction_id)
    )
    if (nrow(seal_frame) != 1L) .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
    postings <- .demo_frame_rows(postings_frame)
    seal <- .demo_frame_rows(seal_frame)[[1]]
    seal_postings <- lapply(postings, function(posting) posting[c(
      "posting_id", "sequence_no", "account_id", "asset_id", "posting_role",
      "quantity_decimal", "unit_price_decimal", "price_currency",
      "valuation_amount_decimal", "valuation_currency"
    )])
    content <- list(
      transaction_id = transaction$transaction_id,
      portfolio_id = transaction$portfolio_id,
      transaction_type = transaction$transaction_type,
      effective_at_utc = transaction$effective_at_utc,
      local_date = transaction$local_date,
      postings = seal_postings
    )
    if (seal$posting_count != length(postings) || seal$content_fingerprint != .demo_fingerprint(content)) {
      .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
    }
    manifest[[length(manifest) + 1L]] <- list(transaction = transaction, postings = postings, seal = seal)
  }
  .demo_fingerprint(manifest)
}

.demo_semantics_evidence_v1 <- function(candidate) {
  mappings <- .demo_mapping_v1(candidate)
  portfolio_id <- mappings$portfolio[["sptf_demo_portfolio01"]]
  account_id <- mappings$account[["sacc_demo_depot001"]]
  asset_id <- mappings$asset[["sast_demo_etf00001"]]
  buy_id <- mappings$transaction[["stx_demo_buy000001"]]
  sell_id <- mappings$transaction[["stx_demo_sell00001"]]
  evidence <- list(
    transaction_semantics_version = 1L,
    profile = "buy_sell_fee_tax_base_currency_v1",
    transaction_count = 2L,
    posting_count = 7L,
    transactions = list(
      list(
        transaction_id = buy_id,
        transaction_type = "buy",
        account_id = account_id,
        asset_id = asset_id,
        settlement_currency = "EUR",
        asset_quantity_decimal = "10",
        gross_trade_amount_decimal = "1000",
        gross_cashflow_decimal = "-1000",
        fee_cashflow_decimal = "-1",
        tax_cashflow_decimal = "0",
        net_cashflow_decimal = "-1001",
        acquisition_cost_added_decimal = "1001",
        fifo_cost_consumed_decimal = NULL,
        realized_gain_pre_tax_decimal = NULL,
        realized_gain_after_tax_cash_decimal = NULL
      ),
      list(
        transaction_id = sell_id,
        transaction_type = "sell",
        account_id = account_id,
        asset_id = asset_id,
        settlement_currency = "EUR",
        asset_quantity_decimal = "-4",
        gross_trade_amount_decimal = "480",
        gross_cashflow_decimal = "480",
        fee_cashflow_decimal = "-1",
        tax_cashflow_decimal = "-5",
        net_cashflow_decimal = "474",
        acquisition_cost_added_decimal = NULL,
        fifo_cost_consumed_decimal = "400.4",
        realized_gain_pre_tax_decimal = "78.6",
        realized_gain_after_tax_cash_decimal = "73.6"
      )
    ),
    positions = list(
      list(
        portfolio_id = portfolio_id,
        account_id = account_id,
        asset_id = asset_id,
        remaining_quantity_decimal = "6",
        remaining_fifo_cost_decimal = "600.6"
      )
    ),
    totals_by_currency = list(
      list(
        currency = "EUR",
        gross_cashflow_decimal = "-520",
        fee_cashflow_decimal = "-2",
        tax_cashflow_decimal = "-5",
        net_cashflow_decimal = "-527",
        acquisition_cost_added_decimal = "1001",
        fifo_cost_consumed_decimal = "400.4",
        realized_gain_pre_tax_decimal = "78.6",
        realized_gain_after_tax_cash_decimal = "73.6"
      )
    )
  )
  evidence$evidence_fingerprint <- .demo_fingerprint(evidence)
  if (evidence$evidence_fingerprint != "7dd302e7305df125a7b2a9b4b17c108297bd85626e5d47076702b3e333bff106") {
    .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  }
  evidence
}

.demo_audit_set_fingerprint <- function(connection) {
  audits <- DBI::dbGetQuery(connection, "SELECT * FROM data_command_audit ORDER BY command_id")
  if (nrow(audits) != 7L || any(audits$command_type != "desktop_demo_seed_v1")) {
    .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  }
  .demo_fingerprint(.demo_frame_rows(audits))
}

.demo_native_source <- function(connection, candidate, context) {
  if (!.demo_existing_exact(connection, candidate, runtime_context_as(context, "desktop_owner"))) {
    .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  }
  mappings <- .demo_mapping_v1(candidate)
  portfolio_id <- mappings$portfolio[["sptf_demo_portfolio01"]]
  semantics <- .demo_semantics_evidence_v1(candidate)
  list(
    canonical_schema_version = 201L,
    provenance_type = "native_data_command",
    data_command_type = "desktop_demo_seed_v1",
    candidate_fingerprint = candidate$candidate_fingerprint,
    audit_set_fingerprint = .demo_audit_set_fingerprint(connection),
    transaction_set_fingerprint = .demo_transaction_set_fingerprint(connection, portfolio_id),
    transaction_semantics_evidence_fingerprint = semantics$evidence_fingerprint
  )
}

.demo_worker_time <- function(value, type) {
  if (!.canonical_utc_valid(value)) {
    if (type == "portfolio") .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
    .demo_tax_abort("demo_tax_worker_time_invalid")
  }
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

build_completed_demo_market_v101 <- function(context, as_of_utc, completed_at_utc) {
  .demo_portfolio_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "market_worker") {
      .demo_portfolio_abort("demo_portfolio_worker_context_invalid")
    }
    as_of <- .demo_worker_time(as_of_utc, "portfolio")
    completed <- .demo_worker_time(completed_at_utc, "portfolio")
    if (completed < as_of) .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
    candidate <- .demo_candidate_v1(context)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    DBI::dbExecute(connection, "BEGIN")
    on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
    source_context <- runtime_context_as(context, "desktop_owner")
    if (!.demo_existing_exact(connection, candidate, source_context)) {
      .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
    }
    mappings <- .demo_mapping_v1(candidate)
    asset_id <- mappings$asset[["sast_demo_etf00001"]]
    market_id <- paste0(
      "mkt_demo_",
      substr(.demo_hash_parts(c(
        "desktop-demo-market-v101", context$tenant_id, context$user_id,
        context$data_space_id, asset_id, as_of_utc, "130", candidate$candidate_fingerprint
      )), 1L, 24L)
    )
    payload <- list(
      market_snapshot_version = 101L,
      market_snapshot_id = market_id,
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      status = "completed",
      as_of_utc = as_of_utc,
      completed_at_utc = completed_at_utc,
      source_kind = "synthetic_desktop_demo",
      observations = list(list(
        asset_id = asset_id,
        price_decimal = "130",
        currency = "EUR",
        observed_at_utc = as_of_utc,
        price_status = "synthetic_completed"
      ))
    )
    result <- payload
    result$market_fingerprint <- .demo_fingerprint(payload)
    DBI::dbExecute(connection, "ROLLBACK")
    result
  }, fallback = "demo_portfolio_worker_market_invalid")
}

.demo_validate_market_v101 <- function(market, context, snapshot_as_of_utc, candidate) {
  required <- c(
    "market_snapshot_version", "market_snapshot_id", "tenant_id", "user_id", "data_space_id",
    "status", "as_of_utc", "completed_at_utc", "source_kind", "observations", "market_fingerprint"
  )
  if (!is.list(market) || !setequal(names(market), required) || market$market_snapshot_version != 101L ||
      market$status != "completed" || market$source_kind != "synthetic_desktop_demo" ||
      market$tenant_id != context$tenant_id || market$user_id != context$user_id ||
      market$data_space_id != context$data_space_id) {
    .demo_portfolio_abort("demo_portfolio_worker_market_invalid")
  }
  payload <- market[setdiff(names(market), "market_fingerprint")]
  if (market$market_fingerprint != .demo_fingerprint(payload) || length(market$observations) != 1L) {
    .demo_portfolio_abort("demo_portfolio_worker_market_invalid")
  }
  mappings <- .demo_mapping_v1(candidate)
  observation <- market$observations[[1]]
  expected <- list(
    asset_id = mappings$asset[["sast_demo_etf00001"]],
    price_decimal = "130",
    currency = "EUR",
    observed_at_utc = market$as_of_utc,
    price_status = "synthetic_completed"
  )
  if (!identical(observation, expected)) .demo_portfolio_abort("demo_portfolio_worker_market_invalid")
  market_as_of <- .demo_worker_time(market$as_of_utc, "portfolio")
  market_completed <- .demo_worker_time(market$completed_at_utc, "portfolio")
  snapshot_as_of <- .demo_worker_time(snapshot_as_of_utc, "portfolio")
  if (!(market_as_of <= market_completed && market_completed <= snapshot_as_of)) {
    .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
  }
  invisible(TRUE)
}

build_demo_portfolio_snapshot_v101 <- function(context, market, snapshot_as_of_utc, completed_at_utc) {
  .demo_portfolio_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "portfolio_worker") {
      .demo_portfolio_abort("demo_portfolio_worker_context_invalid")
    }
    snapshot_as_of <- .demo_worker_time(snapshot_as_of_utc, "portfolio")
    completed <- .demo_worker_time(completed_at_utc, "portfolio")
    if (completed < snapshot_as_of) .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
    candidate <- .demo_candidate_v1(context)
    .demo_validate_market_v101(market, context, snapshot_as_of_utc, candidate)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    DBI::dbExecute(connection, "BEGIN")
    on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
    source <- .demo_native_source(connection, candidate, context)
    source$market_snapshot_id <- market$market_snapshot_id
    source$market_fingerprint <- market$market_fingerprint
    mappings <- .demo_mapping_v1(candidate)
    portfolio_id <- mappings$portfolio[["sptf_demo_portfolio01"]]
    depot_id <- mappings$account[["sacc_demo_depot001"]]
    cash_id <- mappings$account[["sacc_demo_cash0001"]]
    etf_id <- mappings$asset[["sast_demo_etf00001"]]
    cash_asset_id <- mappings$asset[["sast_demo_cash_eur01"]]
    snapshot_id <- paste0(
      "psn_",
      substr(.demo_hash_parts(c(
        "portfolio-snapshot-v101", context$tenant_id, context$user_id, context$data_space_id,
        portfolio_id, snapshot_as_of_utc, source$candidate_fingerprint,
        source$transaction_set_fingerprint, market$market_fingerprint
      )), 1L, 32L)
    )
    payload <- list(
      portfolio_snapshot_version = 101L,
      snapshot_id = snapshot_id,
      status = "completed",
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      portfolio_id = portfolio_id,
      portfolio_label = "Demo Portfolio",
      base_currency = "EUR",
      snapshot_as_of_utc = snapshot_as_of_utc,
      completed_at_utc = completed_at_utc,
      source = source,
      positions = list(list(
        account_id = depot_id,
        account_label = "Demo Depot",
        asset_id = etf_id,
        asset_label = "Demo World ETF",
        currency = "EUR",
        quantity_decimal = "6",
        fifo_cost_decimal = "600.6",
        price_decimal = "130",
        price_observed_at_utc = market$as_of_utc,
        price_status = "synthetic_completed",
        market_value_decimal = "780",
        unrealized_gain_decimal = "179.4",
        realized_gain_pre_tax_decimal = "78.6",
        realized_gain_after_tax_cash_decimal = "73.6",
        fee_cashflow_decimal = "-2",
        tax_cashflow_decimal = "-5"
      )),
      cash_balances = list(list(
        account_id = cash_id,
        account_label = "Demo Cash",
        cash_asset_id = cash_asset_id,
        currency = "EUR",
        balance_decimal = "-527"
      )),
      totals = list(
        market_value_decimal = "780",
        cash_balance_decimal = "-527",
        net_liquidation_decimal = "253",
        fifo_cost_decimal = "600.6",
        unrealized_gain_decimal = "179.4",
        realized_gain_pre_tax_decimal = "78.6",
        realized_gain_after_tax_cash_decimal = "73.6",
        total_gain_pre_tax_decimal = "258",
        total_gain_after_tax_cash_decimal = "253",
        fee_cashflow_decimal = "-2",
        tax_cashflow_decimal = "-5"
      ),
      worker_id = context$actor_id
    )
    result <- payload
    result$artifact_fingerprint <- .demo_fingerprint(payload)
    DBI::dbExecute(connection, "ROLLBACK")
    result
  }, fallback = "demo_portfolio_worker_calculation_invalid")
}

build_demo_tax_report_v101 <- function(context, tax_year, report_as_of_utc, completed_at_utc) {
  .demo_tax_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) || context$role != "tax_worker") {
      .demo_tax_abort("demo_tax_worker_context_invalid")
    }
    if (!identical(tax_year, 2026L)) .demo_tax_abort("demo_tax_worker_time_invalid")
    report_as_of <- .demo_worker_time(report_as_of_utc, "tax")
    completed <- .demo_worker_time(completed_at_utc, "tax")
    if (completed < report_as_of || format(report_as_of, "%Y", tz = "UTC") != "2026") {
      .demo_tax_abort("demo_tax_worker_time_invalid")
    }
    candidate <- .demo_candidate_v1(context)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    DBI::dbExecute(connection, "BEGIN")
    on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
    source <- tryCatch(
      .demo_native_source(connection, candidate, context),
      spot_demo_portfolio_worker_error = function(error) .demo_tax_abort("demo_tax_worker_source_invalid")
    )
    mappings <- .demo_mapping_v1(candidate)
    portfolio_id <- mappings$portfolio[["sptf_demo_portfolio01"]]
    depot_id <- mappings$account[["sacc_demo_depot001"]]
    etf_id <- mappings$asset[["sast_demo_etf00001"]]
    buy_id <- mappings$transaction[["stx_demo_buy000001"]]
    sell_id <- mappings$transaction[["stx_demo_sell00001"]]
    report_id <- paste0(
      "txr_",
      substr(.demo_hash_parts(c(
        "tax-report-v101", context$tenant_id, context$user_id, context$data_space_id,
        portfolio_id, as.character(tax_year), source$transaction_set_fingerprint,
        "fifo_account_asset_v1"
      )), 1L, 32L)
    )
    payload <- list(
      tax_report_version = 101L,
      tax_report_id = report_id,
      status = "completed",
      scope_status = "recorded_cash_only_not_a_tax_filing",
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      portfolio_id = portfolio_id,
      portfolio_label = "Demo Portfolio",
      tax_year = tax_year,
      currency = "EUR",
      method = "fifo_account_asset_v1",
      report_as_of_utc = report_as_of_utc,
      completed_at_utc = completed_at_utc,
      source = source,
      disposals = list(list(
        disposal_transaction_id = sell_id,
        disposal_date = "2026-02-02",
        account_id = depot_id,
        account_label = "Demo Depot",
        asset_id = etf_id,
        asset_label = "Demo World ETF",
        currency = "EUR",
        disposed_quantity_decimal = "4",
        gross_proceeds_decimal = "480",
        disposal_fee_paid_decimal = "1",
        fifo_cost_decimal = "400.4",
        realized_gain_pre_tax_decimal = "78.6",
        recorded_tax_cash_paid_decimal = "5",
        realized_gain_after_recorded_tax_cash_decimal = "73.6",
        fifo_allocations = list(list(
          acquisition_transaction_id = buy_id,
          acquisition_date = "2026-01-02",
          quantity_decimal = "4",
          acquisition_cost_including_fees_decimal = "400.4"
        ))
      )),
      totals = list(
        disposal_count = 1L,
        disposed_quantity_decimal = "4",
        gross_proceeds_decimal = "480",
        disposal_fee_paid_decimal = "1",
        fifo_cost_decimal = "400.4",
        realized_gain_pre_tax_decimal = "78.6",
        recorded_tax_cash_paid_decimal = "5",
        realized_gain_after_recorded_tax_cash_decimal = "73.6"
      ),
      worker_id = context$actor_id
    )
    result <- payload
    result$artifact_fingerprint <- .demo_fingerprint(payload)
    DBI::dbExecute(connection, "ROLLBACK")
    result
  }, fallback = "demo_tax_worker_calculation_invalid")
}
