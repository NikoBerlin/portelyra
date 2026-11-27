REALIZED_FIFO_ALGORITHM_VERSION_V1 <- "realized_fifo_v1.0.0"

realized_fifo_error_codes_v1 <- function() {
  c(
    "realized_fifo_input_invalid",
    "realized_fifo_ledger_invalid",
    "realized_fifo_context_mismatch",
    "realized_fifo_schema_unsupported",
    "realized_fifo_portfolio_missing",
    "realized_fifo_transaction_state_invalid",
    "realized_fifo_decimal_invalid",
    "realized_fifo_event_unsupported",
    "realized_fifo_derivative_unsupported",
    "realized_fifo_cash_event_invalid",
    "realized_fifo_reward_asset_invalid",
    "realized_fifo_currency_mismatch",
    "realized_fifo_inventory_insufficient",
    "realized_fifo_rounding_policy_required",
    "realized_fifo_boundary_failed"
  )
}

.realized_fifo_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !code %in% realized_fifo_error_codes_v1()) {
    stop("realized_fifo_error_code_unregistered", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_realized_fifo_error_v1", "error", "condition")
  )
}

.realized_fifo_abort_v1 <- function(code) stop(.realized_fifo_condition_v1(code))

.realized_fifo_boundary_eval_v1 <- function(expression) {
  result <- tryCatch(
    force(expression),
    spot_realized_fifo_error_v1 = function(error) error,
    error = function(error) .realized_fifo_condition_v1("realized_fifo_boundary_failed")
  )
  if (inherits(result, "spot_realized_fifo_error_v1")) stop(result)
  result
}

.fifo_scalar_v1 <- function(value, pattern, minimum = 1L, maximum = 80L) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= minimum && nchar(value, type = "bytes") <= maximum &&
    grepl(pattern, value, perl = TRUE)
}

.fifo_utc_valid_v1 <- function(value) {
  .fifo_scalar_v1(value, "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", 20L, 20L) &&
    !is.na(as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))
}

.fifo_context_valid_v1 <- function(context) {
  is.list(context) && identical(names(context), c("tenant_id", "user_id", "data_space_id")) &&
    all(vapply(context, .fifo_scalar_v1, logical(1L), pattern = "^[A-Za-z0-9_-]+$", minimum = 3L, maximum = 64L))
}

.fifo_context_fingerprint_v1 <- function(context) {
  digest::digest(
    charToRaw(enc2utf8(paste(
      "realized-fifo-context-v1", context$tenant_id, context$user_id,
      context$data_space_id, sep = "|"
    ))),
    algo = "sha256", serialize = FALSE
  )
}

.fifo_public_ref_v1 <- function(prefix, context_fingerprint, internal_value) {
  fingerprint <- digest::digest(
    charToRaw(enc2utf8(paste("realized-fifo-public-ref-v1", context_fingerprint, prefix, internal_value, sep = "|"))),
    algo = "sha256", serialize = FALSE
  )
  paste0(prefix, substr(fingerprint, 1L, 32L))
}

.fifo_data_frame_rows_v1 <- function(frame) {
  if (!is.data.frame(frame) || !nrow(frame)) return(list())
  lapply(seq_len(nrow(frame)), function(index) {
    values <- lapply(frame, function(column) {
      value <- column[[index]]
      if (length(value) == 0L || is.na(value)) NULL else as.character(value)
    })
    names(values) <- names(frame)
    values
  })
}

.fifo_fingerprint_v1 <- function(value) {
  raw_value <- charToRaw(enc2utf8(jsonlite::toJSON(
    value, auto_unbox = TRUE, null = "null", na = "null", digits = NA,
    pretty = FALSE, dataframe = "rows"
  )))
  digest::digest(raw_value, algo = "sha256", serialize = FALSE)
}

.fifo_read_only_connection_v1 <- function(database_path) {
  if (!is.character(database_path) || length(database_path) != 1L || is.na(database_path) ||
      !file.exists(database_path) || dir.exists(database_path) || nzchar(Sys.readlink(database_path))) {
    .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
  }
  normalized <- tryCatch(normalizePath(database_path, winslash = "/", mustWork = TRUE), error = function(error) NULL)
  if (is.null(normalized) || !file.exists(normalized) || dir.exists(normalized) || nzchar(Sys.readlink(normalized))) {
    .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
  }
  connection <- tryCatch(
    DBI::dbConnect(RSQLite::SQLite(), normalized, flags = RSQLite::SQLITE_RO),
    error = function(error) NULL
  )
  if (is.null(connection)) .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
  tryCatch(
    DBI::dbExecute(connection, "PRAGMA query_only=ON"),
    error = function(error) {
      DBI::dbDisconnect(connection)
      .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
    }
  )
  connection
}

read_realized_fifo_snapshot_v1 <- function(
  database_path, context, portfolio_id, evidence_cutoff_at_utc
) {
  .realized_fifo_boundary_eval_v1({
    if (!.fifo_context_valid_v1(context) ||
        !.fifo_scalar_v1(portfolio_id, "^ptf_[A-Za-z0-9_-]{4,60}$", 8L, 64L) ||
        !.fifo_utc_valid_v1(evidence_cutoff_at_utc)) {
      .realized_fifo_abort_v1("realized_fifo_input_invalid")
    }
    connection <- .fifo_read_only_connection_v1(database_path)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)

    schema_version <- tryCatch(
      as.integer(DBI::dbGetQuery(connection, "PRAGMA user_version")[[1L]][[1L]]),
      error = function(error) NA_integer_
    )
    if (!identical(schema_version, 400L)) {
      .realized_fifo_abort_v1("realized_fifo_schema_unsupported")
    }
    required_objects <- c(
      "ledger_store_binding", "portfolio_entity", "current_portfolio_revision",
      "account_entity", "current_account_revision", "asset_entity",
      "current_asset_revision", "transaction_fact", "transaction_void",
      "current_transaction_fact"
    )
    objects <- tryCatch(
      DBI::dbGetQuery(connection, "SELECT name FROM sqlite_master WHERE type IN ('table','view')")$name,
      error = function(error) character()
    )
    if (!all(required_objects %in% objects)) .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
    integrity <- tryCatch(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1L]], error = function(error) NULL)
    foreign_keys <- tryCatch(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check"), error = function(error) NULL)
    if (!identical(integrity, "ok") || is.null(foreign_keys) || nrow(foreign_keys) != 0L) {
      .realized_fifo_abort_v1("realized_fifo_ledger_invalid")
    }

    binding <- DBI::dbGetQuery(
      connection,
      "SELECT tenant_id,user_id,data_space_id FROM ledger_store_binding WHERE singleton_id=1"
    )
    if (nrow(binding) != 1L ||
        !identical(
          unname(as.character(unlist(binding[1L, c("tenant_id", "user_id", "data_space_id")], use.names = FALSE))),
          unname(as.character(unlist(context, use.names = FALSE)))
        )) {
      .realized_fifo_abort_v1("realized_fifo_context_mismatch")
    }

    portfolio <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT entity.portfolio_id,revision.base_currency,revision.status",
        "FROM portfolio_entity entity JOIN current_portfolio_revision revision",
        "ON revision.portfolio_id=entity.portfolio_id WHERE entity.portfolio_id=?"
      ),
      params = list(portfolio_id)
    )
    if (nrow(portfolio) != 1L) .realized_fifo_abort_v1("realized_fifo_portfolio_missing")

    accounts <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT entity.account_id,revision.account_type,revision.status",
        "FROM account_entity entity JOIN current_account_revision revision",
        "ON revision.account_id=entity.account_id WHERE entity.portfolio_id=?",
        "ORDER BY entity.account_id"
      ),
      params = list(portfolio_id)
    )
    assets <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT DISTINCT entity.asset_id,revision.asset_type,revision.status",
        "FROM asset_entity entity JOIN current_asset_revision revision",
        "ON revision.asset_id=entity.asset_id JOIN transaction_fact tx ON tx.asset_id=entity.asset_id",
        "WHERE tx.portfolio_id=? ORDER BY entity.asset_id"
      ),
      params = list(portfolio_id)
    )
    all_transactions <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT transaction_id,account_id,related_account_id,asset_id,event_type,effective_at_utc,",
        "local_date,quantity_decimal,unit_price_decimal,gross_amount_decimal,fee_decimal,",
        "transaction_currency,supersedes_transaction_id,created_at_utc",
        "FROM transaction_fact WHERE portfolio_id=? ORDER BY created_at_utc,transaction_id"
      ),
      params = list(portfolio_id)
    )
    voids <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT void.transaction_id,void.created_at_utc FROM transaction_void void",
        "JOIN transaction_fact tx ON tx.transaction_id=void.transaction_id",
        "WHERE tx.portfolio_id=? ORDER BY void.transaction_id"
      ),
      params = list(portfolio_id)
    )
    current_transactions <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT transaction_id,account_id,related_account_id,asset_id,event_type,effective_at_utc,",
        "local_date,quantity_decimal,unit_price_decimal,gross_amount_decimal,fee_decimal,transaction_currency",
        "FROM current_transaction_fact WHERE portfolio_id=?",
        "ORDER BY effective_at_utc,transaction_id"
      ),
      params = list(portfolio_id)
    )

    account_ids <- as.character(accounts$account_id)
    asset_ids <- as.character(assets$asset_id)
    current_valid <- !anyDuplicated(current_transactions$transaction_id) &&
      all(current_transactions$account_id %in% account_ids) &&
      all(current_transactions$asset_id %in% asset_ids) &&
      all(is.na(current_transactions$related_account_id) | current_transactions$related_account_id %in% account_ids)
    if (!isTRUE(current_valid)) .realized_fifo_abort_v1("realized_fifo_transaction_state_invalid")

    projected <- current_transactions[current_transactions$effective_at_utc <= evidence_cutoff_at_utc, , drop = FALSE]
    context_fingerprint <- .fifo_context_fingerprint_v1(context)
    fingerprint_payload <- list(
      snapshot_contract = "realized_fifo_input_snapshot_v1",
      schema_version = 400L,
      context_binding_fingerprint = context_fingerprint,
      portfolio = .fifo_data_frame_rows_v1(portfolio[, c("portfolio_id", "base_currency", "status"), drop = FALSE]),
      accounts = .fifo_data_frame_rows_v1(accounts),
      assets = .fifo_data_frame_rows_v1(assets),
      all_transactions = .fifo_data_frame_rows_v1(all_transactions),
      voids = .fifo_data_frame_rows_v1(voids),
      projected_transaction_ids = as.character(projected$transaction_id),
      evidence_cutoff_at_utc = evidence_cutoff_at_utc
    )
    structure(
      list(
        schema_version = 400L,
        context_binding_fingerprint = context_fingerprint,
        portfolio_id = portfolio_id,
        portfolio_ref = .fifo_public_ref_v1("pfr_", context_fingerprint, portfolio_id),
        base_currency = as.character(portfolio$base_currency[[1L]]),
        evidence_cutoff_at_utc = evidence_cutoff_at_utc,
        input_fingerprint = .fifo_fingerprint_v1(fingerprint_payload),
        accounts = accounts,
        assets = assets,
        transactions = projected,
        source_current_transaction_count = as.integer(nrow(current_transactions)),
        excluded_after_cutoff_count = as.integer(nrow(current_transactions) - nrow(projected))
      ),
      class = c("spot_realized_fifo_snapshot_v1", "list")
    )
  })
}

.fifo_key_v1 <- function(account_id, asset_id, currency) paste(account_id, asset_id, currency, sep = "\x1f")
.fifo_inventory_key_v1 <- function(account_id, asset_id) paste(account_id, asset_id, sep = "\x1f")

.fifo_env_get_v1 <- function(environment, key, default) {
  if (exists(key, envir = environment, inherits = FALSE)) get(key, envir = environment, inherits = FALSE) else default
}

.fifo_metric_new_v1 <- function(account_id, asset_id, currency) {
  list(
    account_id = account_id, asset_id = asset_id, currency = currency,
    realized = .ed_rat_zero_v1(), proceeds = .ed_rat_zero_v1(),
    basis_consumed = .ed_rat_zero_v1(), fees = .ed_rat_zero_v1(),
    income = .ed_rat_zero_v1(), cash_balance = .ed_rat_zero_v1()
  )
}

.fifo_metric_get_v1 <- function(metrics, account_id, asset_id, currency) {
  key <- .fifo_key_v1(account_id, asset_id, currency)
  value <- .fifo_env_get_v1(metrics, key, .fifo_metric_new_v1(account_id, asset_id, currency))
  list(key = key, value = value)
}

.fifo_rows_frame_v1 <- function(rows, columns) {
  if (!length(rows)) {
    output <- as.data.frame(setNames(replicate(length(columns), character(), simplify = FALSE), columns), stringsAsFactors = FALSE)
    return(output)
  }
  output <- lapply(columns, function(column) {
    vapply(rows, function(row) {
      value <- row[[column]]
      if (is.null(value) || length(value) == 0L || is.na(value)) NA_character_ else as.character(value)
    }, character(1L))
  })
  names(output) <- columns
  as.data.frame(output, stringsAsFactors = FALSE, check.names = FALSE)
}

.fifo_amount_v1 <- function(transaction) {
  quantity <- .ed_rat_from_decimal_v1(transaction$quantity_decimal, positive = TRUE)
  price <- .ed_rat_from_decimal_v1(transaction$unit_price_decimal, positive = TRUE)
  amount <- .ed_rat_mul_v1(quantity, price)
  gross <- transaction$gross_amount_decimal
  if (!is.null(gross) && length(gross) && !is.na(gross) && nzchar(gross)) {
    gross_value <- .ed_rat_from_decimal_v1(gross, positive = TRUE)
    if (!.ed_rat_equal_v1(amount, gross_value)) .realized_fifo_abort_v1("realized_fifo_decimal_invalid")
  }
  amount
}

.fifo_fee_v1 <- function(transaction) {
  value <- transaction$fee_decimal
  if (is.null(value) || length(value) == 0L || is.na(value) || !nzchar(value)) return(.ed_rat_zero_v1())
  .ed_rat_from_decimal_v1(value, positive = TRUE)
}

.fifo_inventory_currency_v1 <- function(inventory_currencies, account_id, asset_id, currency, set_if_missing = TRUE) {
  key <- .fifo_inventory_key_v1(account_id, asset_id)
  existing <- .fifo_env_get_v1(inventory_currencies, key, NULL)
  if (!is.null(existing) && !identical(existing, currency)) {
    .realized_fifo_abort_v1("realized_fifo_currency_mismatch")
  }
  if (is.null(existing) && set_if_missing) assign(key, currency, envir = inventory_currencies)
  invisible(currency)
}

.fifo_cash_currency_v1 <- function(cash_currencies, asset_id, currency) {
  existing <- .fifo_env_get_v1(cash_currencies, asset_id, NULL)
  if (!is.null(existing) && !identical(existing, currency)) {
    .realized_fifo_abort_v1("realized_fifo_currency_mismatch")
  }
  if (is.null(existing)) assign(asset_id, currency, envir = cash_currencies)
  invisible(currency)
}

.fifo_lot_quantity_cost_v1 <- function(lots) {
  quantity <- .ed_rat_zero_v1()
  cost <- .ed_rat_zero_v1()
  for (lot in lots) {
    quantity <- .ed_rat_add_v1(quantity, lot$quantity)
    cost <- .ed_rat_add_v1(cost, lot$cost)
  }
  list(quantity = quantity, cost = cost)
}

.fifo_consume_lots_v1 <- function(lots_environment, account_id, asset_id, quantity) {
  key <- .fifo_inventory_key_v1(account_id, asset_id)
  lots <- .fifo_env_get_v1(lots_environment, key, list())
  remaining <- quantity
  chunks <- list()
  while (!.ed_rat_is_zero_v1(remaining)) {
    if (!length(lots)) .realized_fifo_abort_v1("realized_fifo_inventory_insufficient")
    lot <- lots[[1L]]
    take <- .ed_rat_min_v1(remaining, lot$quantity)
    cost <- .ed_rat_mul_v1(lot$cost, .ed_rat_div_v1(take, lot$quantity))
    chunks[[length(chunks) + 1L]] <- list(lot = lot, quantity = take, cost = cost)
    lot$quantity <- .ed_rat_sub_v1(lot$quantity, take)
    lot$cost <- .ed_rat_sub_v1(lot$cost, cost)
    remaining <- .ed_rat_sub_v1(remaining, take)
    if (.ed_rat_is_zero_v1(lot$quantity)) {
      lots <- lots[-1L]
    } else {
      lots[[1L]] <- lot
    }
  }
  assign(key, lots, envir = lots_environment)
  chunks
}

.fifo_position_state_v1 <- function(lots_environment, metrics, account_id, asset_id, currency, asset_type) {
  metric <- .fifo_metric_get_v1(metrics, account_id, asset_id, currency)$value
  if (identical(asset_type, "cash")) {
    return(list(quantity = metric$cash_balance, cost = .ed_rat_zero_v1(), metric = metric))
  }
  lots <- .fifo_env_get_v1(lots_environment, .fifo_inventory_key_v1(account_id, asset_id), list())
  lots <- Filter(function(lot) identical(lot$currency, currency), lots)
  totals <- .fifo_lot_quantity_cost_v1(lots)
  list(quantity = totals$quantity, cost = totals$cost, metric = metric)
}

build_realized_fifo_projection_v1 <- function(snapshot) {
  .realized_fifo_boundary_eval_v1({
    if (!inherits(snapshot, "spot_realized_fifo_snapshot_v1") ||
        !identical(snapshot$schema_version, 400L) ||
        !grepl("^[a-f0-9]{64}$", snapshot$input_fingerprint, perl = TRUE)) {
      .realized_fifo_abort_v1("realized_fifo_input_invalid")
    }
    context_fingerprint <- snapshot$context_binding_fingerprint
    account_by_id <- setNames(lapply(seq_len(nrow(snapshot$accounts)), function(index) {
      as.list(snapshot$accounts[index, , drop = FALSE])
    }), snapshot$accounts$account_id)
    asset_by_id <- setNames(lapply(seq_len(nrow(snapshot$assets)), function(index) {
      as.list(snapshot$assets[index, , drop = FALSE])
    }), snapshot$assets$asset_id)

    lots <- new.env(hash = TRUE, parent = emptyenv())
    metrics <- new.env(hash = TRUE, parent = emptyenv())
    inventory_currencies <- new.env(hash = TRUE, parent = emptyenv())
    cash_currencies <- new.env(hash = TRUE, parent = emptyenv())
    segment_counters <- new.env(hash = TRUE, parent = emptyenv())
    event_rows <- list()
    movement_rows <- list()
    history_rows <- list()
    movement_sequence <- 0L
    history_sequence <- 0L

    add_metric <- function(account_id, asset_id, currency, field, value) {
      wrapped <- .fifo_metric_get_v1(metrics, account_id, asset_id, currency)
      wrapped$value[[field]] <- .ed_rat_add_v1(wrapped$value[[field]], value)
      assign(wrapped$key, wrapped$value, envir = metrics)
      invisible(wrapped$value)
    }
    next_segment_ref <- function(origin_lot_ref, account_id) {
      current <- .fifo_env_get_v1(segment_counters, origin_lot_ref, 0L) + 1L
      assign(origin_lot_ref, current, envir = segment_counters)
      .fifo_public_ref_v1("lsg_", context_fingerprint, paste(origin_lot_ref, account_id, current, sep = "|"))
    }
    add_movement <- function(event_ref, movement_type, lot, quantity, cost, source_account_id = NULL, destination_account_id = NULL) {
      movement_sequence <<- movement_sequence + 1L
      movement_rows[[length(movement_rows) + 1L]] <<- list(
        movement_sequence = as.character(movement_sequence),
        event_ref = event_ref,
        movement_type = movement_type,
        origin_lot_ref = lot$origin_lot_ref,
        lot_segment_ref = lot$segment_ref,
        source_account_ref = if (is.null(source_account_id)) NULL else .fifo_public_ref_v1("afr_", context_fingerprint, source_account_id),
        destination_account_ref = if (is.null(destination_account_id)) NULL else .fifo_public_ref_v1("afr_", context_fingerprint, destination_account_id),
        asset_ref = .fifo_public_ref_v1("asf_", context_fingerprint, lot$asset_id),
        currency = lot$currency,
        quantity_decimal = .ed_rat_to_decimal_v1(quantity),
        fifo_cost_decimal = .ed_rat_to_decimal_v1(cost),
        acquisition_event_ref = lot$acquisition_event_ref,
        acquisition_effective_at_utc = lot$acquisition_effective_at_utc,
        acquisition_local_date = lot$acquisition_local_date
      )
    }
    add_history <- function(event_ref, effective_at_utc, account_id, asset_id, currency, asset_type) {
      history_sequence <<- history_sequence + 1L
      state <- .fifo_position_state_v1(lots, metrics, account_id, asset_id, currency, asset_type)
      history_rows[[length(history_rows) + 1L]] <<- list(
        history_sequence = as.character(history_sequence),
        event_ref = event_ref,
        effective_at_utc = effective_at_utc,
        account_ref = .fifo_public_ref_v1("afr_", context_fingerprint, account_id),
        asset_ref = .fifo_public_ref_v1("asf_", context_fingerprint, asset_id),
        currency = currency,
        position_quantity_decimal = .ed_rat_to_decimal_v1(state$quantity),
        fifo_cost_balance_decimal = .ed_rat_to_decimal_v1(state$cost),
        cumulative_realized_gross_gain_decimal = .ed_rat_to_decimal_v1(state$metric$realized),
        cumulative_gross_income_decimal = .ed_rat_to_decimal_v1(state$metric$income),
        cash_balance_decimal = .ed_rat_to_decimal_v1(state$metric$cash_balance)
      )
    }

    if (nrow(snapshot$transactions)) for (event_index in seq_len(nrow(snapshot$transactions))) {
      transaction <- as.list(snapshot$transactions[event_index, , drop = FALSE])
      transaction <- lapply(transaction, function(value) {
        if (length(value) == 0L || is.na(value)) NULL else as.character(value)
      })
      transaction_id <- transaction$transaction_id
      event_ref <- .fifo_public_ref_v1("evr_", context_fingerprint, transaction_id)
      account_id <- transaction$account_id
      related_account_id <- transaction$related_account_id
      asset_id <- transaction$asset_id
      event_type <- transaction$event_type
      currency <- transaction$transaction_currency
      asset <- asset_by_id[[asset_id]]
      if (is.null(asset)) .realized_fifo_abort_v1("realized_fifo_transaction_state_invalid")
      asset_type <- as.character(asset$asset_type[[1L]])
      if (identical(asset_type, "derivative")) .realized_fifo_abort_v1("realized_fifo_derivative_unsupported")
      if (event_type %in% c("adjustment", "other")) .realized_fifo_abort_v1("realized_fifo_event_unsupported")
      if (!event_type %in% c("buy", "sell", "deposit", "withdrawal", "transfer", "dividend", "interest", "reward", "fee")) {
        .realized_fifo_abort_v1("realized_fifo_event_unsupported")
      }
      quantity <- .ed_rat_from_decimal_v1(transaction$quantity_decimal, positive = TRUE)
      amount <- .fifo_amount_v1(transaction)
      fee <- .fifo_fee_v1(transaction)
      basis_added <- .ed_rat_zero_v1()
      basis_consumed <- .ed_rat_zero_v1()
      proceeds <- .ed_rat_zero_v1()
      realized <- .ed_rat_zero_v1()
      income <- .ed_rat_zero_v1()
      cash_delta <- .ed_rat_zero_v1()
      holding_effect <- "no_holding_change"
      history_accounts <- account_id
      add_metric(account_id, asset_id, currency, "fees", .ed_rat_zero_v1())
      if (identical(event_type, "transfer") && !is.null(related_account_id)) {
        add_metric(related_account_id, asset_id, currency, "fees", .ed_rat_zero_v1())
      }

      if (identical(asset_type, "cash")) {
        .fifo_cash_currency_v1(cash_currencies, asset_id, currency)
        if (!event_type %in% c("deposit", "withdrawal", "transfer", "interest", "fee")) {
          .realized_fifo_abort_v1("realized_fifo_cash_event_invalid")
        }
        if (identical(event_type, "deposit")) {
          cash_delta <- .ed_rat_sub_v1(amount, fee)
          add_metric(account_id, asset_id, currency, "cash_balance", cash_delta)
          holding_effect <- "cash_balance_change"
        } else if (identical(event_type, "withdrawal")) {
          cash_delta <- .ed_rat_neg_v1(.ed_rat_add_v1(amount, fee))
          add_metric(account_id, asset_id, currency, "cash_balance", cash_delta)
          holding_effect <- "cash_balance_change"
        } else if (identical(event_type, "transfer")) {
          if (is.null(related_account_id) || identical(related_account_id, account_id)) {
            .realized_fifo_abort_v1("realized_fifo_transaction_state_invalid")
          }
          source_delta <- .ed_rat_neg_v1(.ed_rat_add_v1(amount, fee))
          add_metric(account_id, asset_id, currency, "cash_balance", source_delta)
          add_metric(related_account_id, asset_id, currency, "cash_balance", amount)
          cash_delta <- .ed_rat_neg_v1(fee)
          holding_effect <- "transferred"
          history_accounts <- c(account_id, related_account_id)
        } else if (identical(event_type, "interest")) {
          income <- amount
          add_metric(account_id, asset_id, currency, "income", income)
        } else {
          if (!.ed_rat_is_zero_v1(fee)) .realized_fifo_abort_v1("realized_fifo_decimal_invalid")
          fee <- amount
          cash_delta <- .ed_rat_neg_v1(amount)
          add_metric(account_id, asset_id, currency, "cash_balance", cash_delta)
          holding_effect <- "cash_balance_change"
        }
        if (!.ed_rat_is_zero_v1(fee)) add_metric(account_id, asset_id, currency, "fees", fee)
      } else {
        if (identical(event_type, "interest")) .realized_fifo_abort_v1("realized_fifo_cash_event_invalid")
        if (identical(event_type, "reward") && !identical(asset_type, "crypto")) {
          .realized_fifo_abort_v1("realized_fifo_reward_asset_invalid")
        }
        if (event_type %in% c("buy", "sell", "deposit", "withdrawal", "transfer", "reward", "fee")) {
          .fifo_inventory_currency_v1(inventory_currencies, account_id, asset_id, currency)
        }
        if (identical(event_type, "transfer") && !is.null(related_account_id)) {
          .fifo_inventory_currency_v1(inventory_currencies, related_account_id, asset_id, currency)
        }
        if (event_type %in% c("buy", "deposit", "reward")) {
          basis_added <- if (identical(event_type, "buy")) .ed_rat_add_v1(amount, fee) else amount
          origin_lot_ref <- .fifo_public_ref_v1("lot_", context_fingerprint, transaction_id)
          lot <- list(
            origin_lot_ref = origin_lot_ref,
            segment_ref = next_segment_ref(origin_lot_ref, account_id),
            acquisition_event_ref = event_ref,
            acquisition_effective_at_utc = transaction$effective_at_utc,
            acquisition_local_date = transaction$local_date,
            asset_id = asset_id, currency = currency,
            quantity = quantity, cost = basis_added
          )
          key <- .fifo_inventory_key_v1(account_id, asset_id)
          current <- .fifo_env_get_v1(lots, key, list())
          assign(key, c(current, list(lot)), envir = lots)
          add_movement(
            event_ref,
            if (identical(event_type, "reward")) "reward_acquisition" else if (identical(event_type, "deposit")) "provided_basis_deposit" else "buy_acquisition",
            lot, quantity, basis_added, destination_account_id = account_id
          )
          if (identical(event_type, "reward")) {
            income <- amount
            add_metric(account_id, asset_id, currency, "income", income)
          }
          holding_effect <- "acquired"
        } else if (event_type %in% c("sell", "withdrawal", "fee")) {
          if (identical(event_type, "fee") && !.ed_rat_is_zero_v1(fee)) {
            .realized_fifo_abort_v1("realized_fifo_decimal_invalid")
          }
          chunks <- .fifo_consume_lots_v1(lots, account_id, asset_id, quantity)
          for (chunk in chunks) {
            basis_consumed <- .ed_rat_add_v1(basis_consumed, chunk$cost)
            add_movement(
              event_ref,
              if (identical(event_type, "sell")) "sell_consumption" else if (identical(event_type, "withdrawal")) "withdrawal_consumption" else "asset_fee_consumption",
              chunk$lot, chunk$quantity, chunk$cost, source_account_id = account_id
            )
          }
          if (identical(event_type, "sell")) {
            proceeds <- .ed_rat_sub_v1(amount, fee)
            realized <- .ed_rat_sub_v1(proceeds, basis_consumed)
            add_metric(account_id, asset_id, currency, "proceeds", proceeds)
            add_metric(account_id, asset_id, currency, "basis_consumed", basis_consumed)
            add_metric(account_id, asset_id, currency, "realized", realized)
          } else if (identical(event_type, "fee")) {
            fee <- amount
          }
          holding_effect <- "consumed"
        } else if (identical(event_type, "transfer")) {
          if (is.null(related_account_id) || identical(related_account_id, account_id)) {
            .realized_fifo_abort_v1("realized_fifo_transaction_state_invalid")
          }
          chunks <- .fifo_consume_lots_v1(lots, account_id, asset_id, quantity)
          destination_key <- .fifo_inventory_key_v1(related_account_id, asset_id)
          destination_lots <- .fifo_env_get_v1(lots, destination_key, list())
          for (chunk in chunks) {
            moved_lot <- chunk$lot
            moved_lot$quantity <- chunk$quantity
            moved_lot$cost <- chunk$cost
            moved_lot$segment_ref <- next_segment_ref(moved_lot$origin_lot_ref, related_account_id)
            destination_lots <- c(destination_lots, list(moved_lot))
            add_movement(
              event_ref, "internal_transfer", moved_lot, chunk$quantity, chunk$cost,
              source_account_id = account_id, destination_account_id = related_account_id
            )
          }
          assign(destination_key, destination_lots, envir = lots)
          holding_effect <- "transferred"
          history_accounts <- c(account_id, related_account_id)
        } else if (identical(event_type, "dividend")) {
          income <- amount
          add_metric(account_id, asset_id, currency, "income", income)
        } else {
          .realized_fifo_abort_v1("realized_fifo_event_unsupported")
        }
        if (!.ed_rat_is_zero_v1(fee)) add_metric(account_id, asset_id, currency, "fees", fee)
      }

      event_rows[[length(event_rows) + 1L]] <- list(
        event_sequence = as.character(event_index),
        event_ref = event_ref,
        effective_at_utc = transaction$effective_at_utc,
        local_date = transaction$local_date,
        event_type = event_type,
        account_ref = .fifo_public_ref_v1("afr_", context_fingerprint, account_id),
        related_account_ref = if (is.null(related_account_id)) NULL else .fifo_public_ref_v1("afr_", context_fingerprint, related_account_id),
        asset_ref = .fifo_public_ref_v1("asf_", context_fingerprint, asset_id),
        asset_type = asset_type,
        currency = currency,
        quantity_decimal = .ed_rat_to_decimal_v1(quantity),
        amount_decimal = .ed_rat_to_decimal_v1(amount),
        fee_decimal = if (.ed_rat_is_zero_v1(fee)) NULL else .ed_rat_to_decimal_v1(fee),
        basis_added_decimal = .ed_rat_to_decimal_v1(basis_added),
        basis_consumed_decimal = .ed_rat_to_decimal_v1(basis_consumed),
        gross_proceeds_decimal = .ed_rat_to_decimal_v1(proceeds),
        realized_gross_gain_decimal = .ed_rat_to_decimal_v1(realized),
        gross_income_decimal = .ed_rat_to_decimal_v1(income),
        cash_balance_delta_decimal = .ed_rat_to_decimal_v1(cash_delta),
        holding_effect = holding_effect,
        projection_status = "completed"
      )
      for (history_account_id in history_accounts) {
        add_history(event_ref, transaction$effective_at_utc, history_account_id, asset_id, currency, asset_type)
      }
    }

    remaining_rows <- list()
    inventory_keys <- sort(ls(lots, all.names = TRUE))
    for (key in inventory_keys) {
      entries <- get(key, envir = lots, inherits = FALSE)
      if (!length(entries)) next
      parts <- strsplit(key, "\x1f", fixed = TRUE)[[1L]]
      account_id <- parts[[1L]]
      asset_id <- parts[[2L]]
      asset_type <- as.character(asset_by_id[[asset_id]]$asset_type[[1L]])
      for (lot in entries) {
        if (lot$quantity$sign <= 0L || lot$cost$sign < 0L) {
          .realized_fifo_abort_v1("realized_fifo_transaction_state_invalid")
        }
        remaining_rows[[length(remaining_rows) + 1L]] <- list(
          position_ref = .fifo_public_ref_v1("pos_", context_fingerprint, paste(account_id, asset_id, lot$currency, sep = "|")),
          account_ref = .fifo_public_ref_v1("afr_", context_fingerprint, account_id),
          asset_ref = .fifo_public_ref_v1("asf_", context_fingerprint, asset_id),
          asset_type = asset_type,
          currency = lot$currency,
          origin_lot_ref = lot$origin_lot_ref,
          lot_segment_ref = lot$segment_ref,
          acquisition_event_ref = lot$acquisition_event_ref,
          acquisition_effective_at_utc = lot$acquisition_effective_at_utc,
          acquisition_local_date = lot$acquisition_local_date,
          remaining_quantity_decimal = .ed_rat_to_decimal_v1(lot$quantity),
          remaining_fifo_cost_decimal = .ed_rat_to_decimal_v1(lot$cost)
        )
      }
    }

    summary_rows <- list()
    metric_keys <- sort(ls(metrics, all.names = TRUE))
    for (key in metric_keys) {
      metric <- get(key, envir = metrics, inherits = FALSE)
      asset_type <- as.character(asset_by_id[[metric$asset_id]]$asset_type[[1L]])
      state <- .fifo_position_state_v1(lots, metrics, metric$account_id, metric$asset_id, metric$currency, asset_type)
      summary_rows[[length(summary_rows) + 1L]] <- list(
        position_ref = .fifo_public_ref_v1("pos_", context_fingerprint, paste(metric$account_id, metric$asset_id, metric$currency, sep = "|")),
        account_ref = .fifo_public_ref_v1("afr_", context_fingerprint, metric$account_id),
        asset_ref = .fifo_public_ref_v1("asf_", context_fingerprint, metric$asset_id),
        asset_type = asset_type,
        currency = metric$currency,
        remaining_quantity_decimal = .ed_rat_to_decimal_v1(state$quantity),
        remaining_fifo_cost_decimal = .ed_rat_to_decimal_v1(state$cost),
        realized_gross_proceeds_decimal = .ed_rat_to_decimal_v1(metric$proceeds),
        realized_fifo_cost_decimal = .ed_rat_to_decimal_v1(metric$basis_consumed),
        realized_gross_gain_decimal = .ed_rat_to_decimal_v1(metric$realized),
        gross_income_decimal = .ed_rat_to_decimal_v1(metric$income),
        fee_total_decimal = .ed_rat_to_decimal_v1(metric$fees),
        cash_balance_decimal = .ed_rat_to_decimal_v1(metric$cash_balance)
      )
    }

    currency_values <- new.env(hash = TRUE, parent = emptyenv())
    for (key in metric_keys) {
      metric <- get(key, envir = metrics, inherits = FALSE)
      current <- .fifo_env_get_v1(currency_values, metric$currency, list(
        proceeds = .ed_rat_zero_v1(), basis = .ed_rat_zero_v1(), realized = .ed_rat_zero_v1(),
        income = .ed_rat_zero_v1(), fees = .ed_rat_zero_v1(), cash = .ed_rat_zero_v1()
      ))
      current$proceeds <- .ed_rat_add_v1(current$proceeds, metric$proceeds)
      current$basis <- .ed_rat_add_v1(current$basis, metric$basis_consumed)
      current$realized <- .ed_rat_add_v1(current$realized, metric$realized)
      current$income <- .ed_rat_add_v1(current$income, metric$income)
      current$fees <- .ed_rat_add_v1(current$fees, metric$fees)
      current$cash <- .ed_rat_add_v1(current$cash, metric$cash_balance)
      assign(metric$currency, current, envir = currency_values)
    }
    currency_rows <- lapply(sort(ls(currency_values, all.names = TRUE)), function(currency) {
      value <- get(currency, envir = currency_values, inherits = FALSE)
      list(
        currency = currency,
        realized_gross_proceeds_decimal = .ed_rat_to_decimal_v1(value$proceeds),
        realized_fifo_cost_decimal = .ed_rat_to_decimal_v1(value$basis),
        realized_gross_gain_decimal = .ed_rat_to_decimal_v1(value$realized),
        gross_income_decimal = .ed_rat_to_decimal_v1(value$income),
        fee_total_decimal = .ed_rat_to_decimal_v1(value$fees),
        cash_balance_decimal = .ed_rat_to_decimal_v1(value$cash),
        cross_currency_aggregation = "not_applied"
      )
    })

    tables <- list(
      "event-results.csv" = .fifo_rows_frame_v1(event_rows, c(
        "event_sequence", "event_ref", "effective_at_utc", "local_date", "event_type",
        "account_ref", "related_account_ref", "asset_ref", "asset_type", "currency",
        "quantity_decimal", "amount_decimal", "fee_decimal", "basis_added_decimal",
        "basis_consumed_decimal", "gross_proceeds_decimal", "realized_gross_gain_decimal",
        "gross_income_decimal", "cash_balance_delta_decimal", "holding_effect", "projection_status"
      )),
      "lot-movements.csv" = .fifo_rows_frame_v1(movement_rows, c(
        "movement_sequence", "event_ref", "movement_type", "origin_lot_ref", "lot_segment_ref",
        "source_account_ref", "destination_account_ref", "asset_ref", "currency",
        "quantity_decimal", "fifo_cost_decimal", "acquisition_event_ref",
        "acquisition_effective_at_utc", "acquisition_local_date"
      )),
      "remaining-lots.csv" = .fifo_rows_frame_v1(remaining_rows, c(
        "position_ref", "account_ref", "asset_ref", "asset_type", "currency", "origin_lot_ref",
        "lot_segment_ref", "acquisition_event_ref", "acquisition_effective_at_utc",
        "acquisition_local_date", "remaining_quantity_decimal", "remaining_fifo_cost_decimal"
      )),
      "position-history.csv" = .fifo_rows_frame_v1(history_rows, c(
        "history_sequence", "event_ref", "effective_at_utc", "account_ref", "asset_ref", "currency",
        "position_quantity_decimal", "fifo_cost_balance_decimal",
        "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal",
        "cash_balance_decimal"
      )),
      "position-summary.csv" = .fifo_rows_frame_v1(summary_rows, c(
        "position_ref", "account_ref", "asset_ref", "asset_type", "currency",
        "remaining_quantity_decimal", "remaining_fifo_cost_decimal",
        "realized_gross_proceeds_decimal", "realized_fifo_cost_decimal",
        "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
        "cash_balance_decimal"
      )),
      "currency-summary.csv" = .fifo_rows_frame_v1(currency_rows, c(
        "currency", "realized_gross_proceeds_decimal", "realized_fifo_cost_decimal",
        "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
        "cash_balance_decimal", "cross_currency_aggregation"
      ))
    )
    structure(
      list(
        profile_id = "realized_fifo_v1",
        algorithm_version = REALIZED_FIFO_ALGORITHM_VERSION_V1,
        portfolio_ref = snapshot$portfolio_ref,
        context_binding_fingerprint = context_fingerprint,
        input_fingerprint = snapshot$input_fingerprint,
        evidence_cutoff_at_utc = snapshot$evidence_cutoff_at_utc,
        tables = tables,
        table_roles = list(
          "event-results.csv" = "normative_event_results",
          "lot-movements.csv" = "normative_fifo_lot_movements",
          "remaining-lots.csv" = "normative_remaining_fifo_lots",
          "position-history.csv" = "normative_position_history",
          "position-summary.csv" = "normative_position_summary",
          "currency-summary.csv" = "normative_currency_summary"
        ),
        reconciliation = list(
          source_current_transaction_count = snapshot$source_current_transaction_count,
          projected_transaction_count = as.integer(nrow(snapshot$transactions)),
          excluded_after_cutoff_count = snapshot$excluded_after_cutoff_count,
          event_result_count = as.integer(nrow(tables[["event-results.csv"]])),
          lot_movement_count = as.integer(nrow(tables[["lot-movements.csv"]])),
          remaining_lot_count = as.integer(nrow(tables[["remaining-lots.csv"]])),
          position_summary_count = as.integer(nrow(tables[["position-summary.csv"]])),
          projection_reconciliation_status = "full_oracle_not_persisted"
        ),
        boundaries = list(
          canonical_write = FALSE,
          provider_access = FALSE,
          network_access = FALSE,
          app_side_calculation = FALSE,
          tax_calculation = FALSE,
          market_calculation = FALSE,
          automatic_retry = FALSE,
          grouping_dependency = FALSE
        )
      ),
      class = c("spot_realized_fifo_projection_v1", "list")
    )
  })
}

run_realized_fifo_projection_v1 <- function(
  database_path, output_path, context, portfolio_id, evidence_cutoff_at_utc
) {
  snapshot <- read_realized_fifo_snapshot_v1(
    database_path, context, portfolio_id, evidence_cutoff_at_utc
  )
  projection <- build_realized_fifo_projection_v1(snapshot)
  publish_calculation_evidence_v1(projection, output_path)
}

.realized_fifo_cli_arguments_v1 <- function(arguments) {
  keys <- c(
    "--ledger", "--output", "--tenant-id", "--user-id", "--data-space-id",
    "--portfolio-id", "--cutoff-at-utc"
  )
  if (length(arguments) != length(keys) * 2L) .realized_fifo_abort_v1("realized_fifo_input_invalid")
  values <- list()
  index <- 1L
  while (index <= length(arguments)) {
    key <- arguments[[index]]
    if (!key %in% keys || key %in% names(values) || index == length(arguments)) {
      .realized_fifo_abort_v1("realized_fifo_input_invalid")
    }
    values[[key]] <- arguments[[index + 1L]]
    index <- index + 2L
  }
  if (!setequal(names(values), keys)) .realized_fifo_abort_v1("realized_fifo_input_invalid")
  values
}

realized_fifo_cli_main_v1 <- function(arguments = commandArgs(trailingOnly = TRUE)) {
  tryCatch({
    values <- .realized_fifo_cli_arguments_v1(arguments)
    result <- run_realized_fifo_projection_v1(
      values[["--ledger"]], values[["--output"]],
      list(
        tenant_id = values[["--tenant-id"]], user_id = values[["--user-id"]],
        data_space_id = values[["--data-space-id"]]
      ),
      values[["--portfolio-id"]], values[["--cutoff-at-utc"]]
    )
    cat("realized_fifo_projection_completed\n")
    invisible(0L)
  }, spot_realized_fifo_error_v1 = function(error) {
    cat(paste0("realized_fifo_projection_blocked:", error$code, "\n"), file = stderr())
    invisible(2L)
  }, spot_calculation_evidence_error_v1 = function(error) {
    cat(paste0("realized_fifo_projection_blocked:", error$code, "\n"), file = stderr())
    invisible(2L)
  }, error = function(error) {
    cat("realized_fifo_projection_failed:realized_fifo_boundary_failed\n", file = stderr())
    invisible(1L)
  })
}
