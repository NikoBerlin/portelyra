guided_demo_workflow_error_codes <- function() {
  c(
    "guided_demo_context_invalid",
    "guided_demo_role_not_authorized",
    "guided_demo_repository_invalid",
    "guided_demo_state_conflict",
    "guided_demo_preview_required",
    "guided_demo_confirmation_required",
    "guided_demo_confirmation_invalid",
    "guided_demo_confirmation_scope_mismatch",
    "guided_demo_confirmation_time_invalid",
    "guided_demo_confirmation_consumed",
    "guided_demo_command_failed",
    "guided_demo_worker_source_invalid",
    "guided_demo_boundary_failed"
  )
}

.guided_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% guided_demo_workflow_error_codes()) {
    stop("unregistered_guided_demo_workflow_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_guided_demo_workflow_error", "error", "condition")
  )
}

.guided_abort <- function(code) stop(.guided_condition(code))

.guided_boundary <- function(expression, fallback = "guided_demo_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_guided_demo_workflow_error = function(error) error,
    spot_canonical_repository_error = function(error) .guided_condition("guided_demo_repository_invalid"),
    spot_runtime_error = function(error) .guided_condition("guided_demo_context_invalid"),
    spot_catalog_data_command_error = function(error) .guided_condition("guided_demo_command_failed"),
    spot_transaction_data_command_error = function(error) .guided_condition("guided_demo_command_failed"),
    error = function(error) .guided_condition(fallback)
  )
  if (inherits(result, "spot_guided_demo_workflow_error")) stop(result)
  result
}

.guided_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .guided_abort("guided_demo_context_invalid")
  }
  if (context$role != "desktop_owner") .guided_abort("guided_demo_role_not_authorized")
  invisible(TRUE)
}

.guided_demo_commands_v11 <- function(context) {
  .guided_context_check(context)
  portfolio <- .catalog_build_create_portfolio_v1(
    context, "tok_guided_portfolio01", "Demo Portfolio", "EUR", "2026-08-13T09:01:00Z"
  )
  cash_account <- .catalog_build_create_account_v1(
    context, "tok_guided_cashacct001", portfolio$entity_id, "Demo Cash", "cash", NULL,
    "2026-08-13T09:02:00Z"
  )
  depot_account <- .catalog_build_create_account_v1(
    context, "tok_guided_depotacct01", portfolio$entity_id, "Demo Depot", "securities", NULL,
    "2026-08-13T09:03:00Z"
  )
  cash_asset <- .catalog_build_create_asset_v1(
    context, "tok_guided_cashasset01", "Demo EUR Cash", "cash", "EUR", 2L,
    "unit_value", NULL, "2026-08-13T09:04:00Z"
  )
  etf_asset <- .catalog_build_create_asset_v1(
    context, "tok_guided_etfasset001", "Demo World ETF", "etf", "EUR", 8L,
    "external_market", NULL, "2026-08-13T09:05:00Z"
  )
  buy_postings <- list(
    new_transaction_posting_v1(
      1L, depot_account$entity_id, etf_asset$entity_id, "asset", "10", "100", "EUR", "1000", "EUR", NULL
    ),
    new_transaction_posting_v1(
      2L, cash_account$entity_id, cash_asset$entity_id, "cash", "-1000", NULL, NULL, "-1000", "EUR", NULL
    ),
    new_transaction_posting_v1(
      3L, cash_account$entity_id, cash_asset$entity_id, "fee", "-1", NULL, NULL, "-1", "EUR", NULL
    )
  )
  buy <- .transaction_build_command(
    context, "create", "tok_guided_buytrans001", portfolio$entity_id, "buy",
    "2026-01-02T12:00:00Z", "2026-01-02", "2026-08-13T09:06:00Z", buy_postings, NULL
  )
  sell_postings <- list(
    new_transaction_posting_v1(
      1L, depot_account$entity_id, etf_asset$entity_id, "asset", "-4", "120", "EUR", "-480", "EUR", NULL
    ),
    new_transaction_posting_v1(
      2L, cash_account$entity_id, cash_asset$entity_id, "cash", "480", NULL, NULL, "480", "EUR", NULL
    ),
    new_transaction_posting_v1(
      3L, cash_account$entity_id, cash_asset$entity_id, "fee", "-1", NULL, NULL, "-1", "EUR", NULL
    ),
    new_transaction_posting_v1(
      4L, cash_account$entity_id, cash_asset$entity_id, "tax", "-5", NULL, NULL, "-5", "EUR", NULL
    )
  )
  sell <- .transaction_build_command(
    context, "create", "tok_guided_selltrans01", portfolio$entity_id, "sell",
    "2026-02-02T12:00:00Z", "2026-02-02", "2026-08-13T09:07:00Z", sell_postings, NULL
  )
  list(
    list(step_no = 1L, entity_kind = "portfolio", command = portfolio),
    list(step_no = 2L, entity_kind = "account", command = cash_account),
    list(step_no = 3L, entity_kind = "account", command = depot_account),
    list(step_no = 4L, entity_kind = "asset", command = cash_asset),
    list(step_no = 5L, entity_kind = "asset", command = etf_asset),
    list(step_no = 6L, entity_kind = "transaction", command = buy),
    list(step_no = 7L, entity_kind = "transaction", command = sell)
  )
}

.guided_command_descriptor <- function(step) {
  command <- step$command
  if (inherits(command, "spot_catalog_command_v1")) {
    payload <- list(
      action = command$action,
      entity_type = command$entity_type,
      command_type = command$command_type,
      command_id = command$command_id,
      entity_id = command$entity_id,
      committed_at_utc = command$committed_at_utc,
      fields = command$fields
    )
  } else {
    payload <- list(
      action = command$action,
      command_type = command$command_type,
      command_id = command$command_id,
      transaction_id = command$transaction_id,
      portfolio_id = command$portfolio_id,
      transaction_profile = command$transaction_profile,
      effective_at_utc = command$effective_at_utc,
      local_date = command$local_date,
      committed_at_utc = command$committed_at_utc,
      postings = command$postings,
      memo = command$memo,
      supersedes_transaction_id = command$supersedes_transaction_id
    )
  }
  list(step_no = step$step_no, entity_kind = step$entity_kind, command = payload)
}

.guided_entity_id <- function(step) {
  command <- step$command
  if (inherits(command, "spot_catalog_command_v1")) command$entity_id else command$transaction_id
}

.guided_demo_plan_v11 <- function(context) {
  commands <- .guided_demo_commands_v11(context)
  manifest <- list(
    guided_demo_plan_version = 11L,
    profile = "guided_native_buy_sell_v1",
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    steps = lapply(commands, .guided_command_descriptor)
  )
  fingerprint <- .catalog_fingerprint(manifest)
  list(
    commands = commands,
    manifest = manifest,
    plan_fingerprint = fingerprint,
    workflow_id = paste0("gwd_", substr(.catalog_hash_parts(c("guided-native-demo-v11", fingerprint)), 1L, 24L))
  )
}

.guided_exact_set <- function(actual, expected) {
  identical(sort(as.character(actual), method = "radix"), sort(as.character(expected), method = "radix"))
}

.guided_state_v11 <- function(connection, plan, context) {
  command_ids <- vapply(plan$commands, function(step) step$command$command_id, character(1))
  audit_ids <- DBI::dbGetQuery(connection, "SELECT command_id FROM data_command_audit ORDER BY command_id")$command_id
  if (any(!audit_ids %in% command_ids)) .guided_abort("guided_demo_state_conflict")
  present <- command_ids %in% audit_ids
  completed <- sum(present)
  if (completed > 0L && !identical(present, c(rep(TRUE, completed), rep(FALSE, length(present) - completed)))) {
    .guided_abort("guided_demo_state_conflict")
  }
  for (index in seq_along(plan$commands)) {
    step <- plan$commands[[index]]
    command <- step$command
    entity_id <- .guided_entity_id(step)
    if (present[[index]]) {
      exact <- tryCatch(
        if (inherits(command, "spot_catalog_command_v1")) {
          .catalog_existing_command(connection, command, context)
        } else {
          .transaction_existing_command(connection, command, context)
        },
        error = function(error) NULL
      )
      if (is.null(exact)) .guided_abort("guided_demo_state_conflict")
    } else {
      exists <- if (step$entity_kind == "portfolio") {
        DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM portfolio WHERE portfolio_id=?", params = list(entity_id))$n[[1]]
      } else if (step$entity_kind == "account") {
        DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM account WHERE account_id=?", params = list(entity_id))$n[[1]]
      } else if (step$entity_kind == "asset") {
        DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM asset WHERE asset_id=?", params = list(entity_id))$n[[1]]
      } else {
        DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM transaction_record WHERE transaction_id=?", params = list(entity_id))$n[[1]]
      }
      if (exists != 0L) .guided_abort("guided_demo_state_conflict")
    }
  }
  completed_steps <- plan$commands[present]
  expected_portfolios <- vapply(Filter(function(step) step$entity_kind == "portfolio", completed_steps), .guided_entity_id, character(1))
  expected_accounts <- vapply(Filter(function(step) step$entity_kind == "account", completed_steps), .guided_entity_id, character(1))
  expected_assets <- vapply(Filter(function(step) step$entity_kind == "asset", completed_steps), .guided_entity_id, character(1))
  expected_transactions <- vapply(Filter(function(step) step$entity_kind == "transaction", completed_steps), .guided_entity_id, character(1))
  expected_postings <- unlist(lapply(
    Filter(function(step) step$entity_kind == "transaction", completed_steps),
    function(step) vapply(step$command$postings, function(posting) {
      .transaction_posting_identity(step$command$transaction_id, posting$sequence_no)
    }, character(1))
  ), use.names = FALSE)
  actual <- list(
    portfolios = DBI::dbGetQuery(connection, "SELECT portfolio_id FROM portfolio")$portfolio_id,
    accounts = DBI::dbGetQuery(connection, "SELECT account_id FROM account")$account_id,
    assets = DBI::dbGetQuery(connection, "SELECT asset_id FROM asset")$asset_id,
    transactions = DBI::dbGetQuery(connection, "SELECT transaction_id FROM transaction_record")$transaction_id,
    postings = DBI::dbGetQuery(connection, "SELECT posting_id FROM transaction_posting")$posting_id,
    seals = DBI::dbGetQuery(connection, "SELECT transaction_id FROM transaction_seal")$transaction_id
  )
  if (!.guided_exact_set(actual$portfolios, expected_portfolios) ||
      !.guided_exact_set(actual$accounts, expected_accounts) ||
      !.guided_exact_set(actual$assets, expected_assets) ||
      !.guided_exact_set(actual$transactions, expected_transactions) ||
      !.guided_exact_set(actual$postings, expected_postings) ||
      !.guided_exact_set(actual$seals, expected_transactions) ||
      !.guided_exact_set(audit_ids, command_ids[present]) ||
      DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM provider_mapping")$n[[1]] != 0L ||
      DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM canonical_import_receipt")$n[[1]] != 0L ||
      DBI::dbGetQuery(connection, "SELECT count(*) AS n FROM current_transaction")$n[[1]] != length(expected_transactions)) {
    .guided_abort("guided_demo_state_conflict")
  }
  list(completed = as.integer(completed), present = present)
}

.guided_preview_from_state <- function(plan, state) {
  steps <- lapply(seq_along(plan$commands), function(index) {
    step <- plan$commands[[index]]
    list(
      step_no = step$step_no,
      command_type = step$command$command_type,
      entity_kind = step$entity_kind,
      entity_id = .guided_entity_id(step),
      status = if (state$present[[index]]) "committed" else "pending"
    )
  })
  list(
    guided_demo_contract_version = 11L,
    status = if (state$completed == 0L) "ready_for_confirmation" else if (state$completed == 7L) "already_committed" else "ready_to_resume",
    workflow_id = plan$workflow_id,
    plan_fingerprint = plan$plan_fingerprint,
    counts = list(
      step_count = 7L,
      completed_step_count = state$completed,
      pending_step_count = 7L - state$completed,
      portfolio_count = 1L,
      account_count = 2L,
      asset_count = 2L,
      transaction_count = 2L,
      posting_count = 7L
    ),
    display_summary = list(
      portfolio = "Demo Portfolio",
      accounts = c("Demo Cash", "Demo Depot"),
      assets = c("Demo EUR Cash", "Demo World ETF"),
      workflow = "Native Catalog + Buy/Sell Commands"
    ),
    semantics_summary = list(
      acquired_quantity_decimal = "10",
      disposed_quantity_decimal = "4",
      remaining_quantity_decimal = "6",
      fifo_cost_remaining_decimal = "600.6",
      realized_gain_pre_tax_decimal = "78.6",
      recorded_tax_cash_paid_decimal = "5",
      signed_cash_balance_decimal = "-527"
    ),
    steps = steps
  )
}

guided_demo_preview_v11 <- function(context) {
  .guided_boundary({
    .guided_context_check(context)
    plan <- .guided_demo_plan_v11(context)
    connection <- .canonical_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    state <- .guided_state_v11(connection, plan, context)
    .guided_preview_from_state(plan, state)
  }, fallback = "guided_demo_repository_invalid")
}

new_guided_demo_confirmation_authorizer_v11 <- function() {
  structure(
    list(entries = new.env(hash = TRUE, parent = emptyenv())),
    class = "spot_guided_demo_confirmation_authorizer_v11"
  )
}

.guided_authorizer_valid <- function(authorizer) {
  inherits(authorizer, "spot_guided_demo_confirmation_authorizer_v11") &&
    is.list(authorizer) && identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

.guided_challenge_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    grepl("^gcf_[a-z0-9_]+$", value)
}

.guided_time <- function(value) {
  if (!.canonical_utc_valid(value)) .guided_abort("guided_demo_confirmation_time_invalid")
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

guided_demo_build_confirmation_v11 <- function(
  preview,
  context,
  authorizer,
  challenge_id,
  issued_at_utc,
  confirmed_at_utc,
  expires_at_utc
) {
  .guided_boundary({
    .guided_context_check(context)
    if (!is.list(preview) || !preview$status %in% c("ready_for_confirmation", "ready_to_resume")) {
      .guided_abort("guided_demo_preview_required")
    }
    if (!.guided_authorizer_valid(authorizer) || !.guided_challenge_valid(challenge_id)) {
      .guided_abort("guided_demo_confirmation_invalid")
    }
    issued <- .guided_time(issued_at_utc)
    confirmed <- .guided_time(confirmed_at_utc)
    expires <- .guided_time(expires_at_utc)
    if (!(issued <= confirmed && confirmed <= expires) ||
        as.numeric(difftime(expires, issued, units = "secs")) > 600) {
      .guided_abort("guided_demo_confirmation_time_invalid")
    }
    current <- guided_demo_preview_v11(context)
    if (!identical(preview, current)) .guided_abort("guided_demo_confirmation_scope_mismatch")
    if (exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .guided_abort("guided_demo_confirmation_invalid")
    }
    payload <- list(
      guided_demo_confirmation_version = 11L,
      challenge_id = challenge_id,
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      actor_id = context$actor_id,
      role = context$role,
      workflow_id = preview$workflow_id,
      plan_fingerprint = preview$plan_fingerprint,
      completed_step_count = preview$counts$completed_step_count,
      pending_step_count = preview$counts$pending_step_count,
      issued_at_utc = issued_at_utc,
      confirmed_at_utc = confirmed_at_utc,
      expires_at_utc = expires_at_utc
    )
    confirmation <- payload
    confirmation$confirmation_fingerprint <- .catalog_fingerprint(payload)
    assign(
      challenge_id,
      list(fingerprint = confirmation$confirmation_fingerprint, consumed = FALSE),
      envir = authorizer$entries
    )
    confirmation
  })
}

.guided_validate_confirmation <- function(confirmation, preview, context, now_utc) {
  if (!is.list(confirmation)) .guided_abort("guided_demo_confirmation_required")
  required <- c(
    "guided_demo_confirmation_version", "challenge_id", "tenant_id", "user_id", "data_space_id",
    "actor_id", "role", "workflow_id", "plan_fingerprint", "completed_step_count",
    "pending_step_count", "issued_at_utc", "confirmed_at_utc", "expires_at_utc",
    "confirmation_fingerprint"
  )
  if (!setequal(names(confirmation), required) ||
      !identical(confirmation$guided_demo_confirmation_version, 11L) ||
      !.guided_challenge_valid(confirmation$challenge_id)) {
    .guided_abort("guided_demo_confirmation_invalid")
  }
  payload <- confirmation[setdiff(names(confirmation), "confirmation_fingerprint")]
  if (!identical(.catalog_fingerprint(payload), confirmation$confirmation_fingerprint)) {
    .guided_abort("guided_demo_confirmation_invalid")
  }
  expected <- list(
    tenant_id = context$tenant_id,
    user_id = context$user_id,
    data_space_id = context$data_space_id,
    actor_id = context$actor_id,
    role = context$role,
    workflow_id = preview$workflow_id,
    plan_fingerprint = preview$plan_fingerprint,
    completed_step_count = preview$counts$completed_step_count,
    pending_step_count = preview$counts$pending_step_count
  )
  for (name in names(expected)) {
    if (!identical(confirmation[[name]], expected[[name]])) {
      .guided_abort("guided_demo_confirmation_scope_mismatch")
    }
  }
  issued <- .guided_time(confirmation$issued_at_utc)
  confirmed <- .guided_time(confirmation$confirmed_at_utc)
  expires <- .guided_time(confirmation$expires_at_utc)
  now <- .guided_time(now_utc)
  if (!(issued <= confirmed && confirmed <= now && now <= expires) ||
      as.numeric(difftime(expires, issued, units = "secs")) > 600) {
    .guided_abort("guided_demo_confirmation_time_invalid")
  }
  invisible(TRUE)
}

.guided_consume_confirmation <- function(authorizer, confirmation) {
  if (!.guided_authorizer_valid(authorizer) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .guided_abort("guided_demo_confirmation_invalid")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$fingerprint, confirmation$confirmation_fingerprint)) {
    .guided_abort("guided_demo_confirmation_invalid")
  }
  if (isTRUE(entry$consumed)) .guided_abort("guided_demo_confirmation_consumed")
  entry$consumed <- TRUE
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  invisible(TRUE)
}

.guided_execute_step <- function(context, step) {
  command <- step$command
  tryCatch(
    if (inherits(command, "spot_catalog_command_v1")) {
      .catalog_execute_public(context, command)
    } else {
      .transaction_execute_public(context, command)
    },
    spot_catalog_data_command_error = function(error) .guided_abort("guided_demo_command_failed"),
    spot_transaction_data_command_error = function(error) .guided_abort("guided_demo_command_failed")
  )
}

.guided_result <- function(plan, status, executed) {
  transaction_steps <- Filter(function(step) step$entity_kind == "transaction", plan$commands)
  list(
    guided_demo_contract_version = 11L,
    status = status,
    workflow_id = plan$workflow_id,
    plan_fingerprint = plan$plan_fingerprint,
    completed_step_count = 7L,
    executed_step_count = as.integer(executed),
    portfolio_id = .guided_entity_id(plan$commands[[1]]),
    transaction_ids = vapply(transaction_steps, .guided_entity_id, character(1))
  )
}

.guided_demo_execute_impl_v11 <- function(
  context,
  confirmation,
  authorizer,
  now_utc,
  failpoint = "none"
) {
  .guided_context_check(context)
  allowed_failpoints <- c("none", paste0("after_step_", 1:7))
  if (!failpoint %in% allowed_failpoints) .guided_abort("guided_demo_confirmation_invalid")
  plan <- .guided_demo_plan_v11(context)
  preview <- guided_demo_preview_v11(context)
  if (preview$status == "already_committed") return(.guided_result(plan, "already_committed", 0L))
  .guided_validate_confirmation(confirmation, preview, context, now_utc)
  .guided_consume_confirmation(authorizer, confirmation)
  start <- preview$counts$completed_step_count + 1L
  executed <- 0L
  for (index in start:7L) {
    .guided_execute_step(context, plan$commands[[index]])
    executed <- executed + 1L
    if (identical(failpoint, paste0("after_step_", index))) {
      .guided_abort("guided_demo_command_failed")
    }
  }
  completed <- guided_demo_preview_v11(context)
  if (completed$status != "already_committed") .guided_abort("guided_demo_state_conflict")
  .guided_result(plan, if (start == 1L) "committed" else "resumed", executed)
}

guided_demo_execute_v11 <- function(context, confirmation, authorizer, now_utc) {
  .guided_boundary(
    .guided_demo_execute_impl_v11(context, confirmation, authorizer, now_utc),
    fallback = "guided_demo_command_failed"
  )
}
