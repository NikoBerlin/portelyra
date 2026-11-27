.guided_demo_entities_v11 <- function(plan) {
  list(
    portfolio_id = .guided_entity_id(plan$commands[[1]]),
    cash_account_id = .guided_entity_id(plan$commands[[2]]),
    depot_account_id = .guided_entity_id(plan$commands[[3]]),
    cash_asset_id = .guided_entity_id(plan$commands[[4]]),
    etf_asset_id = .guided_entity_id(plan$commands[[5]]),
    buy_transaction_id = .guided_entity_id(plan$commands[[6]]),
    sell_transaction_id = .guided_entity_id(plan$commands[[7]])
  )
}

.guided_semantics_evidence_v11 <- function(plan) {
  entities <- .guided_demo_entities_v11(plan)
  evidence <- list(
    transaction_semantics_version = 1L,
    profile = "buy_sell_fee_tax_base_currency_v1",
    transaction_count = 2L,
    posting_count = 7L,
    transactions = list(
      list(
        transaction_id = entities$buy_transaction_id,
        transaction_type = "buy",
        account_id = entities$depot_account_id,
        asset_id = entities$etf_asset_id,
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
        transaction_id = entities$sell_transaction_id,
        transaction_type = "sell",
        account_id = entities$depot_account_id,
        asset_id = entities$etf_asset_id,
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
    positions = list(list(
      portfolio_id = entities$portfolio_id,
      account_id = entities$depot_account_id,
      asset_id = entities$etf_asset_id,
      remaining_quantity_decimal = "6",
      remaining_fifo_cost_decimal = "600.6"
    )),
    totals_by_currency = list(list(
      currency = "EUR",
      gross_cashflow_decimal = "-520",
      fee_cashflow_decimal = "-2",
      tax_cashflow_decimal = "-5",
      net_cashflow_decimal = "-527",
      acquisition_cost_added_decimal = "1001",
      fifo_cost_consumed_decimal = "400.4",
      realized_gain_pre_tax_decimal = "78.6",
      realized_gain_after_tax_cash_decimal = "73.6"
    ))
  )
  evidence$evidence_fingerprint <- .catalog_fingerprint(evidence)
  evidence
}

.guided_native_source_v11 <- function(connection, plan, context) {
  state <- tryCatch(
    .guided_state_v11(connection, plan, runtime_context_as(context, "desktop_owner")),
    spot_guided_demo_workflow_error = function(error) .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  )
  if (state$completed != 7L) .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  owner <- runtime_context_as(context, "desktop_owner")
  transaction_steps <- plan$commands[6:7]
  bundles <- lapply(transaction_steps, function(step) {
    .transaction_validate_managed_transaction(connection, step$command$transaction_id, owner)
  })
  audits <- DBI::dbGetQuery(
    connection,
    "SELECT * FROM data_command_audit ORDER BY command_id"
  )
  if (nrow(audits) != 7L) .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
  semantics <- .guided_semantics_evidence_v11(plan)
  list(
    canonical_schema_version = 201L,
    provenance_type = "native_data_command",
    data_command_type = "guided_native_demo_v1",
    candidate_fingerprint = plan$plan_fingerprint,
    audit_set_fingerprint = .catalog_fingerprint(.demo_frame_rows(audits)),
    transaction_set_fingerprint = .catalog_fingerprint(lapply(bundles, function(bundle) {
      bundle[c("record", "postings", "seal", "audit")]
    })),
    transaction_semantics_evidence_fingerprint = semantics$evidence_fingerprint
  )
}

build_completed_guided_demo_market_v101 <- function(context, as_of_utc, completed_at_utc) {
  .demo_portfolio_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
        context$role != "market_worker") {
      .demo_portfolio_abort("demo_portfolio_worker_context_invalid")
    }
    as_of <- .demo_worker_time(as_of_utc, "portfolio")
    completed <- .demo_worker_time(completed_at_utc, "portfolio")
    if (completed < as_of) .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
    owner <- runtime_context_as(context, "desktop_owner")
    plan <- .guided_demo_plan_v11(owner)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    state <- tryCatch(
      .guided_state_v11(connection, plan, owner),
      spot_guided_demo_workflow_error = function(error) NULL
    )
    if (is.null(state) || state$completed != 7L) .demo_portfolio_abort("demo_portfolio_worker_source_invalid")
    entities <- .guided_demo_entities_v11(plan)
    market_id <- paste0(
      "mkt_guided_",
      substr(.catalog_hash_parts(c(
        "guided-demo-market-v101", context$tenant_id, context$user_id,
        context$data_space_id, entities$etf_asset_id, as_of_utc, "130", plan$plan_fingerprint
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
        asset_id = entities$etf_asset_id,
        price_decimal = "130",
        currency = "EUR",
        observed_at_utc = as_of_utc,
        price_status = "synthetic_completed"
      ))
    )
    result <- payload
    result$market_fingerprint <- .catalog_fingerprint(payload)
    result
  }, fallback = "demo_portfolio_worker_market_invalid")
}

.guided_validate_market_v101 <- function(market, context, snapshot_as_of_utc, plan) {
  required <- c(
    "market_snapshot_version", "market_snapshot_id", "tenant_id", "user_id", "data_space_id",
    "status", "as_of_utc", "completed_at_utc", "source_kind", "observations", "market_fingerprint"
  )
  if (!is.list(market) || !setequal(names(market), required) || market$market_snapshot_version != 101L ||
      market$status != "completed" || market$source_kind != "synthetic_desktop_demo" ||
      market$tenant_id != context$tenant_id || market$user_id != context$user_id ||
      market$data_space_id != context$data_space_id ||
      market$market_fingerprint != .catalog_fingerprint(market[setdiff(names(market), "market_fingerprint")]) ||
      length(market$observations) != 1L) {
    .demo_portfolio_abort("demo_portfolio_worker_market_invalid")
  }
  entities <- .guided_demo_entities_v11(plan)
  expected <- list(
    asset_id = entities$etf_asset_id,
    price_decimal = "130",
    currency = "EUR",
    observed_at_utc = market$as_of_utc,
    price_status = "synthetic_completed"
  )
  if (!identical(market$observations[[1]], expected)) .demo_portfolio_abort("demo_portfolio_worker_market_invalid")
  market_as_of <- .demo_worker_time(market$as_of_utc, "portfolio")
  market_completed <- .demo_worker_time(market$completed_at_utc, "portfolio")
  snapshot_as_of <- .demo_worker_time(snapshot_as_of_utc, "portfolio")
  if (!(market_as_of <= market_completed && market_completed <= snapshot_as_of)) {
    .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
  }
  invisible(TRUE)
}

build_guided_demo_portfolio_snapshot_v101 <- function(context, market, snapshot_as_of_utc, completed_at_utc) {
  .demo_portfolio_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
        context$role != "portfolio_worker") {
      .demo_portfolio_abort("demo_portfolio_worker_context_invalid")
    }
    snapshot_as_of <- .demo_worker_time(snapshot_as_of_utc, "portfolio")
    completed <- .demo_worker_time(completed_at_utc, "portfolio")
    if (completed < snapshot_as_of) .demo_portfolio_abort("demo_portfolio_worker_time_invalid")
    owner <- runtime_context_as(context, "desktop_owner")
    plan <- .guided_demo_plan_v11(owner)
    .guided_validate_market_v101(market, context, snapshot_as_of_utc, plan)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    DBI::dbExecute(connection, "BEGIN")
    on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
    source <- .guided_native_source_v11(connection, plan, context)
    source$market_snapshot_id <- market$market_snapshot_id
    source$market_fingerprint <- market$market_fingerprint
    entities <- .guided_demo_entities_v11(plan)
    snapshot_id <- paste0(
      "psn_",
      substr(.catalog_hash_parts(c(
        "guided-portfolio-snapshot-v101", context$tenant_id, context$user_id,
        context$data_space_id, entities$portfolio_id, snapshot_as_of_utc,
        source$candidate_fingerprint, source$transaction_set_fingerprint, market$market_fingerprint
      )), 1L, 32L)
    )
    payload <- list(
      portfolio_snapshot_version = 101L,
      snapshot_id = snapshot_id,
      status = "completed",
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      portfolio_id = entities$portfolio_id,
      portfolio_label = "Demo Portfolio",
      base_currency = "EUR",
      snapshot_as_of_utc = snapshot_as_of_utc,
      completed_at_utc = completed_at_utc,
      source = source,
      positions = list(list(
        account_id = entities$depot_account_id,
        account_label = "Demo Depot",
        asset_id = entities$etf_asset_id,
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
        account_id = entities$cash_account_id,
        account_label = "Demo Cash",
        cash_asset_id = entities$cash_asset_id,
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
    result$artifact_fingerprint <- .catalog_fingerprint(payload)
    DBI::dbExecute(connection, "ROLLBACK")
    result
  }, fallback = "demo_portfolio_worker_calculation_invalid")
}

build_guided_demo_tax_report_v101 <- function(context, tax_year, report_as_of_utc, completed_at_utc) {
  .demo_tax_boundary({
    if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
        context$role != "tax_worker") {
      .demo_tax_abort("demo_tax_worker_context_invalid")
    }
    if (!identical(tax_year, 2026L)) .demo_tax_abort("demo_tax_worker_time_invalid")
    report_as_of <- .demo_worker_time(report_as_of_utc, "tax")
    completed <- .demo_worker_time(completed_at_utc, "tax")
    if (completed < report_as_of || format(report_as_of, "%Y", tz = "UTC") != "2026") {
      .demo_tax_abort("demo_tax_worker_time_invalid")
    }
    owner <- runtime_context_as(context, "desktop_owner")
    plan <- .guided_demo_plan_v11(owner)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    DBI::dbExecute(connection, "BEGIN")
    on.exit(if (DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE), add = TRUE)
    source <- tryCatch(
      .guided_native_source_v11(connection, plan, context),
      spot_demo_portfolio_worker_error = function(error) .demo_tax_abort("demo_tax_worker_source_invalid")
    )
    entities <- .guided_demo_entities_v11(plan)
    report_id <- paste0(
      "txr_",
      substr(.catalog_hash_parts(c(
        "guided-tax-report-v101", context$tenant_id, context$user_id, context$data_space_id,
        entities$portfolio_id, as.character(tax_year), source$transaction_set_fingerprint,
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
      portfolio_id = entities$portfolio_id,
      portfolio_label = "Demo Portfolio",
      tax_year = tax_year,
      currency = "EUR",
      method = "fifo_account_asset_v1",
      report_as_of_utc = report_as_of_utc,
      completed_at_utc = completed_at_utc,
      source = source,
      disposals = list(list(
        disposal_transaction_id = entities$sell_transaction_id,
        disposal_date = "2026-02-02",
        account_id = entities$depot_account_id,
        account_label = "Demo Depot",
        asset_id = entities$etf_asset_id,
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
          acquisition_transaction_id = entities$buy_transaction_id,
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
    result$artifact_fingerprint <- .catalog_fingerprint(payload)
    DBI::dbExecute(connection, "ROLLBACK")
    result
  }, fallback = "demo_tax_worker_calculation_invalid")
}
