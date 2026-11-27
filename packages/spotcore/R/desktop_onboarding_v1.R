desktop_onboarding_error_codes_v1 <- function() {
  c(
    "desktop_onboarding_context_invalid",
    "desktop_onboarding_input_invalid",
    "desktop_onboarding_repository_uninitialized",
    "desktop_onboarding_repository_not_empty",
    "desktop_onboarding_plan_conflict",
    "desktop_onboarding_preview_required",
    "desktop_onboarding_confirmation_required",
    "desktop_onboarding_confirmation_invalid",
    "desktop_onboarding_confirmation_expired",
    "desktop_onboarding_confirmation_consumed",
    "desktop_onboarding_restart_unavailable",
    "desktop_onboarding_storage_invalid",
    "desktop_onboarding_command_failed",
    "desktop_onboarding_simulated_interruption",
    "desktop_onboarding_boundary_failed"
  )
}

.desktop_onboarding_condition_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) || !code %in% desktop_onboarding_error_codes_v1()) {
    stop("unregistered_desktop_onboarding_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_desktop_onboarding_error_v1", "error", "condition")
  )
}

.desktop_onboarding_abort_v1 <- function(code) stop(.desktop_onboarding_condition_v1(code))

.desktop_onboarding_boundary_v1 <- function(expression, fallback = "desktop_onboarding_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_desktop_onboarding_error_v1 = function(error) error,
    spot_desktop_product_error_v1 = function(error) .desktop_onboarding_condition_v1("desktop_onboarding_storage_invalid"),
    spot_runtime_error = function(error) .desktop_onboarding_condition_v1("desktop_onboarding_context_invalid"),
    spot_canonical_repository_error = function(error) .desktop_onboarding_condition_v1("desktop_onboarding_repository_uninitialized"),
    spot_catalog_data_command_error = function(error) .desktop_onboarding_condition_v1("desktop_onboarding_command_failed"),
    spot_transaction_data_command_error = function(error) .desktop_onboarding_condition_v1("desktop_onboarding_command_failed"),
    error = function(error) .desktop_onboarding_condition_v1(fallback)
  )
  if (inherits(result, "spot_desktop_onboarding_error_v1")) stop(result)
  result
}

.desktop_onboarding_context_v1 <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$runtime_mode, "desktop_product") || !identical(context$role, "desktop_owner") ||
      !identical(context$trusted_source, "owner_only_desktop_registry")) {
    .desktop_onboarding_abort_v1("desktop_onboarding_context_invalid")
  }
  invisible(TRUE)
}

.desktop_onboarding_input_names_v1 <- function() {
  c(
    "portfolio_name", "base_currency", "cash_account_name", "securities_account_name",
    "external_account_name", "cash_asset_name", "investment_asset_name", "investment_asset_type",
    "price_currency", "quantity_scale", "valuation_method", "isin", "deposit_effective_at_utc",
    "deposit_local_date", "deposit_amount_decimal", "buy_effective_at_utc", "buy_local_date",
    "buy_quantity_decimal", "buy_unit_price_decimal", "buy_total_cash_amount_decimal", "buy_fee_decimal"
  )
}

.desktop_onboarding_input_shape_v1 <- function(input) {
  expected <- .desktop_onboarding_input_names_v1()
  legacy <- expected[expected != "buy_total_cash_amount_decimal"]
  if (!is.list(input) || (!identical(names(input), expected) && !identical(names(input), legacy))) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  if (identical(names(input), legacy)) {
    position <- match("buy_unit_price_decimal", names(input))
    input <- c(input[seq_len(position)], list(buy_total_cash_amount_decimal = NULL), input[-seq_len(position)])
  }
  input
}

.desktop_onboarding_text_v1 <- function(value, maximum = 120L) {
  is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value) &&
    identical(value, trimws(value)) && nchar(value, type = "bytes") <= maximum && !grepl("[[:cntrl:]]", value)
}

.desktop_onboarding_currency_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[A-Z]{3}$", value)
}

.desktop_onboarding_date_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value)) return(FALSE)
  parsed <- suppressWarnings(as.Date(value, format = "%Y-%m-%d"))
  !is.na(parsed) && identical(format(parsed, "%Y-%m-%d"), value)
}

.desktop_onboarding_decimal_v1 <- function(value, optional = FALSE) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value)) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  parsed <- tryCatch(
    .transaction_decimal_parse(value, allow_zero = FALSE, positive_only = TRUE),
    error = function(error) NULL
  )
  if (is.null(parsed)) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  .transaction_decimal_string(parsed)
}

.desktop_onboarding_validate_input_v1 <- function(input) {
  input <- .desktop_onboarding_input_shape_v1(input)
  for (field in c(
    "portfolio_name", "cash_account_name", "securities_account_name", "external_account_name",
    "cash_asset_name", "investment_asset_name"
  )) if (!.desktop_onboarding_text_v1(input[[field]])) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  if (!.desktop_onboarding_currency_v1(input$base_currency) || !identical(input$price_currency, input$base_currency)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  if (!input$investment_asset_type %in% c("equity", "etf", "fund", "bond", "crypto", "commodity", "other") ||
      !is.integer(input$quantity_scale) || length(input$quantity_scale) != 1L || is.na(input$quantity_scale) ||
      input$quantity_scale < 0L || input$quantity_scale > 24L ||
      !input$valuation_method %in% c("external_market", "manual", "transaction_only")) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  if (!is.null(input$isin) && (!is.character(input$isin) || length(input$isin) != 1L ||
      is.na(input$isin) || !grepl("^[A-Z0-9]{12}$", input$isin))) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  if (!.desktop_product_utc_valid_v1(input$deposit_effective_at_utc) ||
      !.desktop_product_utc_valid_v1(input$buy_effective_at_utc) ||
      !.desktop_onboarding_date_v1(input$deposit_local_date) || !.desktop_onboarding_date_v1(input$buy_local_date)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  deposit_time <- as.POSIXct(input$deposit_effective_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  buy_time <- as.POSIXct(input$buy_effective_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (deposit_time > buy_time || input$deposit_local_date > input$buy_local_date) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  deposit <- .desktop_onboarding_decimal_v1(input$deposit_amount_decimal)
  quantity <- .desktop_onboarding_decimal_v1(input$buy_quantity_decimal)
  price <- .desktop_onboarding_decimal_v1(input$buy_unit_price_decimal)
  total <- .desktop_onboarding_decimal_v1(input$buy_total_cash_amount_decimal, optional = TRUE)
  fee <- .desktop_onboarding_decimal_v1(input$buy_fee_decimal, optional = TRUE)
  deposit_parsed <- .transaction_decimal_parse(deposit, allow_zero = FALSE, positive_only = TRUE)
  quantity_parsed <- .transaction_decimal_parse(quantity, allow_zero = FALSE, positive_only = TRUE)
  price_parsed <- .transaction_decimal_parse(price, allow_zero = FALSE, positive_only = TRUE)
  total_parsed <- if (is.null(total)) NULL else .transaction_decimal_parse(total, allow_zero = FALSE, positive_only = TRUE)
  fee_parsed <- if (is.null(fee)) .transaction_decimal_zero() else {
    .transaction_decimal_parse(fee, allow_zero = FALSE, positive_only = TRUE)
  }
  internal_gross <- tryCatch(
    .transaction_decimal_multiply(quantity_parsed, price_parsed),
    spot_transaction_data_command_error = function(error) NULL
  )
  internal_gross_text <- if (is.null(internal_gross)) NULL else tryCatch(
    .transaction_decimal_string(internal_gross),
    spot_transaction_data_command_error = function(error) NULL
  )
  if (is.null(internal_gross_text)) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  booked_gross <- if (is.null(total_parsed)) internal_gross else {
    .transaction_decimal_subtract(total_parsed, fee_parsed)
  }
  if (booked_gross$sign != 1L) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  booked_gross_text <- tryCatch(
    .transaction_decimal_string(booked_gross),
    spot_transaction_data_command_error = function(error) NULL
  )
  cash_scales <- c(
    deposit_parsed$scale, booked_gross$scale,
    if (is.null(total_parsed)) integer() else total_parsed$scale,
    if (is.null(fee)) integer() else fee_parsed$scale
  )
  if (is.null(booked_gross_text) || quantity_parsed$scale > input$quantity_scale || any(cash_scales > 2L)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  }
  normalized <- input
  normalized$deposit_amount_decimal <- deposit
  normalized$buy_quantity_decimal <- quantity
  normalized$buy_unit_price_decimal <- price
  normalized["buy_total_cash_amount_decimal"] <- list(total)
  normalized["buy_fee_decimal"] <- list(fee)
  normalized
}

.desktop_onboarding_now_add_v1 <- function(value, seconds) {
  parsed <- as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (is.na(parsed)) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
  format(parsed + seconds, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

.desktop_onboarding_paths_v1 <- function(context) {
  base <- .runtime_safe_child(context, c(context$tenant_id, context$user_id, context$data_space_id, "onboarding"))
  list(
    directory = base,
    plan = file.path(base, "active-plan.json"),
    receipt = file.path(base, "completed-receipt.json"),
    lock = file.path(base, "writer.lock")
  )
}

.desktop_onboarding_prepare_directory_v1 <- function(context) {
  old_umask <- Sys.umask("0077")
  on.exit(Sys.umask(old_umask), add = TRUE)
  data_space <- runtime_data_space_path(context)
  if (!dir.exists(data_space)) .desktop_onboarding_abort_v1("desktop_onboarding_repository_uninitialized")
  paths <- .desktop_onboarding_paths_v1(context)
  if (file.exists(paths$directory) && !dir.exists(paths$directory)) .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  if (!dir.exists(paths$directory) && !dir.create(paths$directory, mode = "0700", showWarnings = FALSE)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  if (.desktop_product_symlink_v1(paths$directory)) .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  suppressWarnings(Sys.chmod(paths$directory, mode = "0700"))
  if (!.desktop_product_owner_mode_v1(paths$directory, directory = TRUE)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  paths
}

.desktop_onboarding_plan_fingerprint_v1 <- function(plan) .catalog_fingerprint(plan)

.desktop_onboarding_plan_valid_v1 <- function(plan, context) {
  is.list(plan) && identical(names(plan), c(
    "contract_version", "plan_id", "tenant_id", "user_id", "data_space_id", "prepared_at_utc", "input", "tokens"
  )) && identical(plan$contract_version, 1L) &&
    is.character(plan$plan_id) && length(plan$plan_id) == 1L && grepl("^onb_[a-f0-9]{32}$", plan$plan_id) &&
    identical(plan$tenant_id, context$tenant_id) && identical(plan$user_id, context$user_id) &&
    identical(plan$data_space_id, context$data_space_id) && .desktop_product_utc_valid_v1(plan$prepared_at_utc) &&
    is.list(plan$tokens) && identical(names(plan$tokens), c(
      "portfolio", "cash_account", "securities_account", "external_account", "cash_asset", "investment_asset", "deposit", "buy"
    )) && all(vapply(plan$tokens, function(token) {
      is.character(token) && length(token) == 1L && grepl("^tok_onb_[a-f0-9]{32}$", token)
    }, logical(1))) && is.list(tryCatch(.desktop_onboarding_validate_input_v1(plan$input), error = function(error) NULL))
}

.desktop_onboarding_plan_envelope_v1 <- function(plan) {
  list(contract_version = 1L, plan_fingerprint = .desktop_onboarding_plan_fingerprint_v1(plan), plan = plan)
}

.desktop_onboarding_read_plan_v1 <- function(context) {
  paths <- .desktop_onboarding_paths_v1(context)
  if (!file.exists(paths$plan) || dir.exists(paths$plan) || .desktop_product_symlink_v1(paths$plan) ||
      !.desktop_product_owner_mode_v1(paths$plan)) .desktop_onboarding_abort_v1("desktop_onboarding_restart_unavailable")
  size <- suppressWarnings(file.info(paths$plan)$size)
  if (length(size) != 1L || is.na(size) || size < 2 || size > 1048576) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  envelope <- tryCatch(jsonlite::fromJSON(paths$plan, simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(envelope) || !identical(names(envelope), c("contract_version", "plan_fingerprint", "plan")) ||
      !identical(envelope$contract_version, 1L) || !.desktop_onboarding_plan_valid_v1(envelope$plan, context) ||
      !identical(envelope$plan_fingerprint, .desktop_onboarding_plan_fingerprint_v1(envelope$plan))) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  envelope$plan
}

.desktop_onboarding_read_receipt_v1 <- function(context) {
  paths <- .desktop_onboarding_paths_v1(context)
  if (!file.exists(paths$receipt) || dir.exists(paths$receipt) || .desktop_product_symlink_v1(paths$receipt) ||
      !.desktop_product_owner_mode_v1(paths$receipt)) .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  size <- suppressWarnings(file.info(paths$receipt)$size)
  if (length(size) != 1L || is.na(size) || size < 2 || size > 65536) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  receipt <- tryCatch(jsonlite::fromJSON(paths$receipt, simplifyVector = FALSE), error = function(error) NULL)
  plan <- .desktop_onboarding_read_plan_v1(context)
  if (!is.list(receipt) || !identical(names(receipt), c(
    "contract_version", "plan_id", "plan_fingerprint", "status", "completed_at_utc", "step_count"
  )) || !identical(receipt$contract_version, 1L) || !identical(receipt$plan_id, plan$plan_id) ||
      !identical(receipt$plan_fingerprint, .desktop_onboarding_plan_fingerprint_v1(plan)) ||
      !identical(receipt$status, "completed") || !.desktop_product_utc_valid_v1(receipt$completed_at_utc) ||
      !identical(receipt$step_count, 8L)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_storage_invalid")
  }
  receipt
}

.desktop_onboarding_negate_v1 <- function(value) {
  .transaction_decimal_string(.transaction_decimal_negate(.transaction_decimal_parse(value, allow_zero = FALSE)))
}

.desktop_onboarding_commands_v1 <- function(plan, context) {
  input <- .desktop_onboarding_input_shape_v1(plan$input)
  committed <- function(offset) .desktop_onboarding_now_add_v1(plan$prepared_at_utc, offset)
  portfolio <- .catalog_build_create_portfolio_v1(
    context, plan$tokens$portfolio, input$portfolio_name, input$base_currency, committed(1L)
  )
  cash_account <- .catalog_build_create_account_v1(
    context, plan$tokens$cash_account, portfolio$entity_id, input$cash_account_name, "cash", NULL, committed(2L)
  )
  securities_account <- .catalog_build_create_account_v1(
    context, plan$tokens$securities_account, portfolio$entity_id, input$securities_account_name, "securities", NULL, committed(3L)
  )
  external_account <- .catalog_build_create_account_v1(
    context, plan$tokens$external_account, portfolio$entity_id, input$external_account_name, "external", NULL, committed(4L)
  )
  cash_asset <- .catalog_build_create_asset_v1(
    context, plan$tokens$cash_asset, input$cash_asset_name, "cash", input$base_currency, 2L, "unit_value", NULL, committed(5L)
  )
  investment_asset <- .catalog_build_create_asset_v1(
    context, plan$tokens$investment_asset, input$investment_asset_name, input$investment_asset_type,
    input$price_currency, input$quantity_scale, input$valuation_method, input$isin, committed(6L)
  )
  deposit_amount <- input$deposit_amount_decimal
  deposit <- .transaction_build_command(
    context, "create", plan$tokens$deposit, portfolio$entity_id, "deposit",
    input$deposit_effective_at_utc, input$deposit_local_date, committed(7L),
    list(
      new_transaction_posting_v1(
        1L, cash_account$entity_id, cash_asset$entity_id, "cash", deposit_amount,
        NULL, NULL, deposit_amount, input$base_currency, NULL
      ),
      new_transaction_posting_v1(
        2L, external_account$entity_id, cash_asset$entity_id, "transfer", .desktop_onboarding_negate_v1(deposit_amount),
        NULL, NULL, .desktop_onboarding_negate_v1(deposit_amount), input$base_currency, NULL
      )
    ),
    NULL
  )
  quantity <- input$buy_quantity_decimal
  price <- input$buy_unit_price_decimal
  internal_gross <- .transaction_decimal_multiply(
    .transaction_decimal_parse(quantity, allow_zero = FALSE, positive_only = TRUE),
    .transaction_decimal_parse(price, allow_zero = FALSE, positive_only = TRUE)
  )
  gross <- .transaction_decimal_string(internal_gross)
  fee_value <- if (is.null(input$buy_fee_decimal)) .transaction_decimal_zero() else {
    .transaction_decimal_parse(input$buy_fee_decimal, allow_zero = FALSE, positive_only = TRUE)
  }
  booked_gross <- if (is.null(input$buy_total_cash_amount_decimal)) internal_gross else {
    .transaction_decimal_subtract(
      .transaction_decimal_parse(input$buy_total_cash_amount_decimal, allow_zero = FALSE, positive_only = TRUE),
      fee_value
    )
  }
  booked_gross_text <- .transaction_decimal_string(booked_gross)
  buy_postings <- list(
    new_transaction_posting_v1(
      1L, securities_account$entity_id, investment_asset$entity_id, "asset", quantity,
      price, input$price_currency, gross, input$base_currency, NULL
    ),
    new_transaction_posting_v1(
      2L, cash_account$entity_id, cash_asset$entity_id, "cash", .desktop_onboarding_negate_v1(booked_gross_text),
      NULL, NULL, .desktop_onboarding_negate_v1(booked_gross_text), input$base_currency, NULL
    )
  )
  if (!is.null(input$buy_fee_decimal)) buy_postings[[3L]] <- new_transaction_posting_v1(
    3L, cash_account$entity_id, cash_asset$entity_id, "fee", .desktop_onboarding_negate_v1(input$buy_fee_decimal),
    NULL, NULL, .desktop_onboarding_negate_v1(input$buy_fee_decimal), input$base_currency, NULL
  )
  buy <- .transaction_build_command(
    context, "create", plan$tokens$buy, portfolio$entity_id, "buy",
    input$buy_effective_at_utc, input$buy_local_date, committed(8L), buy_postings, NULL,
    settlement_mode = if (is.null(input$buy_total_cash_amount_decimal)) NULL else "explicit_cash"
  )
  list(
    list(step_no = 1L, area = "portfolio", label = input$portfolio_name, command = portfolio),
    list(step_no = 2L, area = "account", label = input$cash_account_name, command = cash_account),
    list(step_no = 3L, area = "account", label = input$securities_account_name, command = securities_account),
    list(step_no = 4L, area = "account", label = input$external_account_name, command = external_account),
    list(step_no = 5L, area = "asset", label = input$cash_asset_name, command = cash_asset),
    list(step_no = 6L, area = "asset", label = input$investment_asset_name, command = investment_asset),
    list(step_no = 7L, area = "transaction", label = "deposit", command = deposit),
    list(step_no = 8L, area = "transaction", label = "buy", command = buy)
  )
}

.desktop_onboarding_command_id_v1 <- function(step) step$command$command_id

.desktop_onboarding_state_v1 <- function(plan, context) {
  commands <- .desktop_onboarding_commands_v1(plan, context)
  connection <- .canonical_connect_read(context)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  expected <- vapply(commands, .desktop_onboarding_command_id_v1, character(1))
  actual <- DBI::dbGetQuery(connection, "SELECT command_id FROM data_command_audit ORDER BY committed_at_utc, command_id")$command_id
  if (any(!actual %in% expected)) .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
  present <- expected %in% actual
  completed <- sum(present)
  if (!identical(present, c(rep(TRUE, completed), rep(FALSE, length(present) - completed)))) {
    .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
  }
  for (index in which(present)) {
    command <- commands[[index]]$command
    exact <- tryCatch(
      if (inherits(command, "spot_catalog_command_v1")) .catalog_existing_command(connection, command, context)
      else .transaction_existing_command(connection, command, context),
      error = function(error) NULL
    )
    if (is.null(exact)) .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
  }
  list(commands = commands, present = present, completed = as.integer(completed))
}

.desktop_onboarding_public_preview_v1 <- function(plan, state) {
  input <- .desktop_onboarding_input_shape_v1(plan$input)
  buy_postings <- state$commands[[8L]]$command$postings
  list(
    contract_version = 1L,
    status = if (state$completed == 8L) "ready_to_finalize" else if (state$completed > 0L) "ready_to_resume" else "ready_for_confirmation",
    counts = list(step_count = 8L, completed_step_count = state$completed, pending_step_count = 8L - state$completed),
    summary = list(
      portfolio_name = input$portfolio_name,
      base_currency = input$base_currency,
      cash_account_name = input$cash_account_name,
      securities_account_name = input$securities_account_name,
      investment_asset_name = input$investment_asset_name,
      investment_asset_type = input$investment_asset_type,
      deposit_amount_decimal = input$deposit_amount_decimal,
      buy_quantity_decimal = input$buy_quantity_decimal,
      buy_unit_price_decimal = input$buy_unit_price_decimal,
      buy_settlement_mode = state$commands[[8L]]$command$settlement_mode,
      buy_internal_gross_decimal = buy_postings[[1L]]$valuation_amount_decimal,
      buy_booked_gross_decimal = .transaction_decimal_string(.transaction_decimal_abs(
        .transaction_decimal_parse(buy_postings[[2L]]$valuation_amount_decimal, allow_zero = FALSE)
      )),
      buy_total_cash_amount_decimal = input$buy_total_cash_amount_decimal,
      buy_fee_decimal = input$buy_fee_decimal
    ),
    steps = lapply(seq_along(state$commands), function(index) list(
      step_no = as.integer(index), area = state$commands[[index]]$area,
      label = state$commands[[index]]$label,
      status = if (state$present[[index]]) "completed" else "pending"
    )),
    context_authority = FALSE,
    canonical_write = FALSE,
    provider_access = FALSE
  )
}

.desktop_onboarding_preview_object_v1 <- function(plan, state) {
  structure(
    list(
      contract_version = 1L,
      plan = plan,
      plan_fingerprint = .desktop_onboarding_plan_fingerprint_v1(plan),
      public = .desktop_onboarding_public_preview_v1(plan, state)
    ),
    class = "spot_desktop_onboarding_preview_v1"
  )
}

.desktop_onboarding_preview_valid_v1 <- function(preview, context) {
  inherits(preview, "spot_desktop_onboarding_preview_v1") && is.list(preview) &&
    identical(names(preview), c("contract_version", "plan", "plan_fingerprint", "public")) &&
    identical(preview$contract_version, 1L) && .desktop_onboarding_plan_valid_v1(preview$plan, context) &&
    identical(preview$plan_fingerprint, .desktop_onboarding_plan_fingerprint_v1(preview$plan)) &&
    is.list(preview$public)
}

.desktop_onboarding_current_state_v1 <- function(preview, context) {
  if (!.desktop_onboarding_preview_valid_v1(preview, context)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_preview_required")
  }
  paths <- .desktop_onboarding_paths_v1(context)
  if (file.exists(paths$plan)) {
    persisted <- .desktop_onboarding_read_plan_v1(context)
    if (!identical(.desktop_onboarding_plan_fingerprint_v1(persisted), preview$plan_fingerprint)) {
      .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
    }
  } else if (file.exists(paths$receipt)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
  }
  state <- .desktop_onboarding_state_v1(preview$plan, context)
  if (!identical(preview$public, .desktop_onboarding_public_preview_v1(preview$plan, state))) {
    .desktop_onboarding_abort_v1("desktop_onboarding_preview_required")
  }
  state
}

desktop_onboarding_public_preview_v1 <- function(preview) {
  if (!inherits(preview, "spot_desktop_onboarding_preview_v1") || !is.list(preview$public)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_preview_required")
  }
  preview$public
}

.desktop_onboarding_repository_empty_v1 <- function(context) {
  connection <- .canonical_connect_read(context)
  on.exit(DBI::dbDisconnect(connection), add = TRUE)
  tables <- c(
    "portfolio", "account", "asset", "provider_mapping", "transaction_record", "transaction_posting",
    "transaction_seal", "data_command_audit", "canonical_import_receipt"
  )
  all(vapply(tables, function(table) {
    DBI::dbGetQuery(connection, paste0("SELECT count(*) AS n FROM ", table))$n[[1L]] == 0
  }, logical(1)))
}

desktop_onboarding_prepare_v1 <- function(context, input, prepared_at_utc) {
  .desktop_onboarding_boundary_v1({
    .desktop_onboarding_context_v1(context)
    if (!file.exists(runtime_canonical_path(context))) .desktop_onboarding_abort_v1("desktop_onboarding_repository_uninitialized")
    paths <- .desktop_onboarding_paths_v1(context)
    if (file.exists(paths$plan) || file.exists(paths$receipt)) .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
    if (!.desktop_onboarding_repository_empty_v1(context)) .desktop_onboarding_abort_v1("desktop_onboarding_repository_not_empty")
    normalized <- .desktop_onboarding_validate_input_v1(input)
    if (!.desktop_product_utc_valid_v1(prepared_at_utc)) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
    token_names <- c(
      "portfolio", "cash_account", "securities_account", "external_account", "cash_asset", "investment_asset", "deposit", "buy"
    )
    tokens <- setNames(lapply(token_names, function(name) .desktop_product_random_id_v1("tok_onb_")), token_names)
    plan <- list(
      contract_version = 1L,
      plan_id = .desktop_product_random_id_v1("onb_"),
      tenant_id = context$tenant_id,
      user_id = context$user_id,
      data_space_id = context$data_space_id,
      prepared_at_utc = prepared_at_utc,
      input = normalized,
      tokens = tokens
    )
    state <- list(commands = .desktop_onboarding_commands_v1(plan, context), present = rep(FALSE, 8L), completed = 0L)
    .desktop_onboarding_preview_object_v1(plan, state)
  })
}

desktop_onboarding_restart_preview_v1 <- function(context) {
  .desktop_onboarding_boundary_v1({
    .desktop_onboarding_context_v1(context)
    plan <- .desktop_onboarding_read_plan_v1(context)
    state <- .desktop_onboarding_state_v1(plan, context)
    .desktop_onboarding_preview_object_v1(plan, state)
  })
}

new_desktop_onboarding_authorizer_v1 <- function() {
  structure(list(entries = new.env(hash = TRUE, parent = emptyenv())), class = "spot_desktop_onboarding_authorizer_v1")
}

.desktop_onboarding_authorizer_valid_v1 <- function(authorizer) {
  inherits(authorizer, "spot_desktop_onboarding_authorizer_v1") && is.list(authorizer) &&
    identical(names(authorizer), "entries") && is.environment(authorizer$entries)
}

desktop_onboarding_build_confirmation_v1 <- function(
  preview, context, authorizer, challenge_id, issued_at_utc, confirmed_at_utc, expires_at_utc
) {
  .desktop_onboarding_boundary_v1({
    .desktop_onboarding_context_v1(context)
    if (!.desktop_onboarding_preview_valid_v1(preview, context) ||
        !preview$public$status %in% c("ready_for_confirmation", "ready_to_resume", "ready_to_finalize")) {
      .desktop_onboarding_abort_v1("desktop_onboarding_preview_required")
    }
    invisible(.desktop_onboarding_current_state_v1(preview, context))
    if (!.desktop_onboarding_authorizer_valid_v1(authorizer) || !is.character(challenge_id) ||
        length(challenge_id) != 1L || !grepl("^ocf_[a-f0-9]{32}$", challenge_id) ||
        exists(challenge_id, envir = authorizer$entries, inherits = FALSE)) {
      .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_invalid")
    }
    values <- c(issued_at_utc, confirmed_at_utc, expires_at_utc)
    if (!all(vapply(values, .desktop_product_utc_valid_v1, logical(1)))) {
      .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_expired")
    }
    times <- as.POSIXct(values, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    if (!(times[[1L]] <= times[[2L]] && times[[2L]] <= times[[3L]]) ||
        as.numeric(difftime(times[[3L]], times[[1L]], units = "secs")) > 600) {
      .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_expired")
    }
    entry <- list(
      status = "issued", plan_fingerprint = preview$plan_fingerprint,
      context_fingerprint = runtime_context_fingerprint(context), issued_at_utc = issued_at_utc,
      confirmed_at_utc = confirmed_at_utc, expires_at_utc = expires_at_utc
    )
    assign(challenge_id, entry, envir = authorizer$entries)
    structure(
      list(
        contract_version = 1L, challenge_id = challenge_id, plan_fingerprint = preview$plan_fingerprint,
        context_fingerprint = entry$context_fingerprint, issued_at_utc = issued_at_utc,
        confirmed_at_utc = confirmed_at_utc, expires_at_utc = expires_at_utc
      ),
      class = "spot_desktop_onboarding_confirmation_v1"
    )
  })
}

.desktop_onboarding_consume_confirmation_v1 <- function(preview, context, confirmation, authorizer, now_utc) {
  if (!.desktop_onboarding_authorizer_valid_v1(authorizer) ||
      !inherits(confirmation, "spot_desktop_onboarding_confirmation_v1") ||
      !is.list(confirmation) || !identical(names(confirmation), c(
        "contract_version", "challenge_id", "plan_fingerprint", "context_fingerprint",
        "issued_at_utc", "confirmed_at_utc", "expires_at_utc"
      )) || !identical(confirmation$contract_version, 1L) ||
      !exists(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_invalid")
  }
  entry <- get(confirmation$challenge_id, envir = authorizer$entries, inherits = FALSE)
  if (!identical(entry$status, "issued")) .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_consumed")
  entry$status <- "consumed"
  assign(confirmation$challenge_id, entry, envir = authorizer$entries)
  now <- if (.desktop_product_utc_valid_v1(now_utc)) {
    as.POSIXct(now_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  } else as.POSIXct(NA)
  confirmed <- as.POSIXct(entry$confirmed_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  expires <- as.POSIXct(entry$expires_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  if (is.na(now) || now < confirmed || now > expires) {
    .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_expired")
  }
  if (!identical(entry$plan_fingerprint, preview$plan_fingerprint) ||
      !identical(entry$context_fingerprint, runtime_context_fingerprint(context)) ||
      !identical(confirmation$plan_fingerprint, preview$plan_fingerprint) ||
      !identical(confirmation$context_fingerprint, entry$context_fingerprint) ||
      !identical(confirmation$issued_at_utc, entry$issued_at_utc) ||
      !identical(confirmation$confirmed_at_utc, entry$confirmed_at_utc) ||
      !identical(confirmation$expires_at_utc, entry$expires_at_utc)) {
    .desktop_onboarding_abort_v1("desktop_onboarding_confirmation_invalid")
  }
  invisible(TRUE)
}

.desktop_onboarding_execute_command_v1 <- function(context, command) {
  if (inherits(command, "spot_catalog_command_v1")) .catalog_execute_public(context, command)
  else .transaction_execute_public(context, command)
}

.desktop_onboarding_execute_impl_v1 <- function(
  context, preview, confirmation, authorizer, executed_at_utc, fail_after_step
) {
  .desktop_onboarding_boundary_v1({
    old_umask <- Sys.umask("0077")
    on.exit(Sys.umask(old_umask), add = TRUE)
    .desktop_onboarding_context_v1(context)
    if (!.desktop_onboarding_preview_valid_v1(preview, context) ||
        !preview$public$status %in% c("ready_for_confirmation", "ready_to_resume", "ready_to_finalize")) {
      .desktop_onboarding_abort_v1("desktop_onboarding_preview_required")
    }
    if (!is.integer(fail_after_step) || length(fail_after_step) != 1L || is.na(fail_after_step) ||
        fail_after_step < 0L || fail_after_step > 8L) .desktop_onboarding_abort_v1("desktop_onboarding_input_invalid")
    .desktop_onboarding_consume_confirmation_v1(preview, context, confirmation, authorizer, executed_at_utc)
    paths <- .desktop_onboarding_prepare_directory_v1(context)
    lock_owner <- .desktop_product_acquire_lock_v1(paths$lock, "desktop_product_registry_conflict")
    on.exit(if (dir.exists(paths$lock)) .desktop_product_release_lock_v1(paths$lock, lock_owner), add = TRUE)
    if (!file.exists(paths$plan)) {
      .desktop_product_json_write_atomic_v1(paths$plan, .desktop_onboarding_plan_envelope_v1(preview$plan))
    } else {
      persisted <- .desktop_onboarding_read_plan_v1(context)
      if (!identical(.desktop_onboarding_plan_fingerprint_v1(persisted), preview$plan_fingerprint)) {
        .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
      }
    }
    state <- .desktop_onboarding_state_v1(preview$plan, context)
    if (!identical(preview$public, .desktop_onboarding_public_preview_v1(preview$plan, state))) {
      .desktop_onboarding_abort_v1("desktop_onboarding_plan_conflict")
    }
    executed <- 0L
    for (index in seq_along(state$commands)) if (!state$present[[index]]) {
      invisible(.desktop_onboarding_execute_command_v1(context, state$commands[[index]]$command))
      executed <- executed + 1L
      if (fail_after_step > 0L && index == fail_after_step) {
        .desktop_onboarding_abort_v1("desktop_onboarding_simulated_interruption")
      }
    }
    final <- .desktop_onboarding_state_v1(preview$plan, context)
    if (final$completed != 8L) .desktop_onboarding_abort_v1("desktop_onboarding_command_failed")
    if (!file.exists(paths$receipt)) {
      receipt <- list(
        contract_version = 1L, plan_id = preview$plan$plan_id,
        plan_fingerprint = preview$plan_fingerprint, status = "completed",
        completed_at_utc = executed_at_utc, step_count = 8L
      )
      .desktop_product_json_write_atomic_v1(paths$receipt, receipt)
    }
    invisible(.desktop_onboarding_read_receipt_v1(context))
    list(status = "completed", executed_step_count = as.integer(executed), completed_step_count = 8L)
  })
}

desktop_onboarding_execute_v1 <- function(context, preview, confirmation, authorizer, executed_at_utc) {
  .desktop_onboarding_execute_impl_v1(
    context, preview, confirmation, authorizer, executed_at_utc, fail_after_step = 0L
  )
}

desktop_onboarding_status_v1 <- function(context) {
  .desktop_onboarding_boundary_v1({
    .desktop_onboarding_context_v1(context)
    if (!file.exists(runtime_canonical_path(context))) return(list(status = "uninitialized", completed_step_count = 0L))
    paths <- .desktop_onboarding_paths_v1(context)
    if (file.exists(paths$receipt)) {
      invisible(.desktop_onboarding_read_receipt_v1(context))
      return(list(status = "completed", completed_step_count = 8L))
    }
    if (file.exists(paths$plan)) {
      preview <- desktop_onboarding_restart_preview_v1(context)
      return(list(status = preview$public$status, completed_step_count = preview$public$counts$completed_step_count))
    }
    if (!.desktop_onboarding_repository_empty_v1(context)) return(list(status = "not_available_nonempty", completed_step_count = 0L))
    list(status = "ready", completed_step_count = 0L)
  })
}
