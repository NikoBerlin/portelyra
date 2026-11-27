data_transaction_editor_error_codes_v1 <- function() {
  c(
    "data_transaction_editor_state_invalid",
    "data_transaction_editor_context_invalid",
    "data_transaction_editor_catalog_unavailable",
    "data_transaction_editor_selection_invalid",
    "data_transaction_editor_input_invalid",
    "data_transaction_editor_decimal_invalid",
    "data_transaction_editor_preview_required",
    "data_transaction_editor_confirmation_required",
    "data_transaction_editor_confirmation_consumed",
    "data_transaction_editor_confirmation_expired",
    "data_transaction_editor_command_failed"
  )
}

.data_transaction_editor_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% data_transaction_editor_error_codes_v1()) {
    stop("unregistered_data_transaction_editor_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_data_transaction_editor_error", "error", "condition")
  )
}

.data_transaction_editor_abort <- function(code) stop(.data_transaction_editor_condition(code))

.data_transaction_editor_check <- function(editor) {
  if (!inherits(editor, "spot_data_transaction_editor_v1") || !is.environment(editor) ||
      !is.environment(editor$previews) || !is.integer(editor$sequence) || length(editor$sequence) != 1L) {
    .data_transaction_editor_abort("data_transaction_editor_state_invalid")
  }
  invisible(TRUE)
}

.data_transaction_editor_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE)) ||
      !identical(context$role, "desktop_owner")) {
    .data_transaction_editor_abort("data_transaction_editor_context_invalid")
  }
  invisible(TRUE)
}

new_data_transaction_editor_v1 <- function() {
  editor <- new.env(hash = FALSE, parent = emptyenv())
  editor$sequence <- 0L
  editor$selection <- NULL
  editor$previews <- new.env(hash = TRUE, parent = emptyenv())
  class(editor) <- "spot_data_transaction_editor_v1"
  editor
}

.data_transaction_editor_ref <- function(prefix, index) sprintf("%s%04d", prefix, as.integer(index))

.data_transaction_editor_safe_label <- function(value, maximum = 160L) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      value != trimws(value) || nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) {
    .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
  }
  value
}

.data_transaction_editor_index <- function(rows, prefix, id_field) {
  refs <- vapply(seq_along(rows), function(index) .data_transaction_editor_ref(prefix, index), character(1))
  identifiers <- vapply(rows, function(row) row[[id_field]], character(1))
  if (anyDuplicated(identifiers)) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
  list(by_ref = setNames(rows, refs), ref_by_id = setNames(refs, identifiers))
}

.data_transaction_editor_choice <- function(index, ref, label, fields = list()) {
  c(list(ref = ref, label = .data_transaction_editor_safe_label(label)), fields)
}

.data_transaction_editor_imported_lineage <- function(entry) {
  identical(entry$record$origin_type, "legacy_import") ||
    startsWith(entry$audit$command_type, "transaction_import_")
}

.data_transaction_editor_type_label <- function(value) {
  labels <- c(
    buy = "Kauf", sell = "Verkauf", deposit = "Einzahlung",
    withdrawal = "Auszahlung", transfer = "Interner Transfer", reward = "Reward"
  )
  label <- unname(labels[[value]])
  if (is.null(label)) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
  label
}

data_transaction_editor_refresh_v1 <- function(editor, context) {
  .data_transaction_editor_check(editor)
  .data_transaction_editor_context_check(context)
  catalog <- tryCatch(
    catalog_read_v1(context),
    error = function(error) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
  )
  portfolios <- .data_transaction_editor_index(catalog$portfolios, "portfolio_ref_", "portfolio_id")
  accounts <- .data_transaction_editor_index(catalog$accounts, "account_ref_", "account_id")
  assets <- .data_transaction_editor_index(catalog$assets, "asset_ref_", "asset_id")
  current_entries <- list()
  for (portfolio in catalog$portfolios) {
    history <- tryCatch(
      transaction_read_history_v1(context, portfolio$portfolio_id),
      error = function(error) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
    )
    for (entry in history$entries) {
      if (isTRUE(entry$is_current)) current_entries[[length(current_entries) + 1L]] <- entry
    }
  }
  if (length(current_entries)) {
    transaction_refs <- vapply(seq_along(current_entries), function(index) {
      .data_transaction_editor_ref("transaction_ref_", index)
    }, character(1))
    transaction_ids <- vapply(current_entries, function(entry) entry$record$transaction_id, character(1))
    if (anyDuplicated(transaction_ids)) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
    transactions <- list(
      by_ref = setNames(current_entries, transaction_refs),
      ref_by_id = setNames(transaction_refs, transaction_ids)
    )
  } else {
    transactions <- list(
      by_ref = setNames(list(), character()),
      ref_by_id = setNames(character(), character())
    )
  }
  context_fingerprint <- runtime_context_fingerprint(context)
  selection_fingerprint <- .catalog_fingerprint(list(
    data_transaction_editor_selection_version = 1L,
    context_fingerprint = context_fingerprint,
    catalog_fingerprint = catalog$catalog_fingerprint,
    current_transaction_fingerprints = lapply(current_entries, function(entry) entry$seal$content_fingerprint)
  ))
  editor$selection <- list(
    context_fingerprint = context_fingerprint,
    selection_fingerprint = selection_fingerprint,
    portfolios = portfolios,
    accounts = accounts,
    assets = assets,
    transactions = transactions
  )
  portfolio_choices <- lapply(names(portfolios$by_ref), function(ref) {
    row <- portfolios$by_ref[[ref]]
    .data_transaction_editor_choice(portfolios, ref, row$display_name, list(currency = row$base_currency))
  })
  account_choices <- lapply(names(accounts$by_ref), function(ref) {
    row <- accounts$by_ref[[ref]]
    portfolio_ref <- unname(portfolios$ref_by_id[[row$portfolio_id]])
    if (is.null(portfolio_ref)) .data_transaction_editor_abort("data_transaction_editor_catalog_unavailable")
    .data_transaction_editor_choice(accounts, ref, row$display_name, list(
      portfolio_ref = portfolio_ref,
      account_type = row$account_type,
      status = row$status
    ))
  })
  asset_choices <- lapply(names(assets$by_ref), function(ref) {
    row <- assets$by_ref[[ref]]
    .data_transaction_editor_choice(assets, ref, row$display_name, list(
      asset_type = row$asset_type,
      currency = row$price_currency,
      status = row$status
    ))
  })
  transaction_choices <- lapply(names(transactions$by_ref), function(ref) {
    entry <- transactions$by_ref[[ref]]
    record <- entry$record
    portfolio_ref <- unname(portfolios$ref_by_id[[record$portfolio_id]])
    label <- paste(record$local_date, .data_transaction_editor_type_label(record$transaction_type))
    .data_transaction_editor_choice(transactions, ref, label, list(
      portfolio_ref = portfolio_ref,
      profile = if (record$transaction_type == "transfer") "internal_transfer" else record$transaction_type,
      cash_flow_mode = if (.data_transaction_editor_imported_lineage(entry) &&
                           record$transaction_type %in% c("buy", "sell")) {
        "separate_cash_movement"
      } else if (.data_transaction_editor_imported_lineage(entry) &&
                 identical(record$transaction_type, "reward")) {
        "asset_income_no_cash_posting"
      } else if (.data_transaction_editor_imported_lineage(entry) &&
                 record$transaction_type %in% c("deposit", "withdrawal", "transfer")) {
        "movement_no_guv"
      } else {
        "embedded_cash_posting"
      }
    ))
  })
  list(
    editor_selection_contract_version = 1L,
    status = "ready",
    selection_fingerprint = selection_fingerprint,
    portfolios = portfolio_choices,
    accounts = account_choices,
    assets = asset_choices,
    current_transactions = transaction_choices,
    canonical_ids_exposed = FALSE,
    provider_access = FALSE,
    canonical_write = FALSE
  )
}

.data_transaction_editor_selection <- function(editor, context) {
  .data_transaction_editor_check(editor)
  .data_transaction_editor_context_check(context)
  selection <- editor$selection
  if (is.null(selection) || !identical(selection$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_transaction_editor_abort("data_transaction_editor_selection_invalid")
  }
  selection
}

.data_transaction_editor_resolve <- function(selection, area, ref) {
  if (!is.character(ref) || length(ref) != 1L || is.na(ref) || !nzchar(ref)) {
    .data_transaction_editor_abort("data_transaction_editor_selection_invalid")
  }
  row <- selection[[area]]$by_ref[[ref]]
  if (is.null(row)) .data_transaction_editor_abort("data_transaction_editor_selection_invalid")
  row
}

.data_transaction_editor_reverse_ref <- function(selection, area, identifier) {
  ref <- unname(selection[[area]]$ref_by_id[[identifier]])
  if (is.null(ref)) .data_transaction_editor_abort("data_transaction_editor_selection_invalid")
  ref
}

.data_transaction_editor_scalar <- function(value, allowed = NULL, optional = FALSE, maximum = 500L) {
  if (optional && (is.null(value) || identical(value, ""))) return(NULL)
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) {
    .data_transaction_editor_abort("data_transaction_editor_input_invalid")
  }
  if (!is.null(allowed) && !value %in% allowed) {
    .data_transaction_editor_abort("data_transaction_editor_input_invalid")
  }
  value
}

.data_transaction_editor_positive_decimal <- function(value, optional = FALSE) {
  value <- .data_transaction_editor_scalar(value, optional = optional, maximum = 80L)
  if (is.null(value)) return(NULL)
  tryCatch(
    .transaction_decimal_parse(value, allow_zero = FALSE, positive_only = TRUE),
    error = function(error) .data_transaction_editor_abort("data_transaction_editor_decimal_invalid")
  )
  value
}

.data_transaction_editor_negate <- function(value) {
  .transaction_decimal_string(.transaction_decimal_negate(.transaction_decimal_parse(value, allow_zero = FALSE)))
}

.data_transaction_editor_abs <- function(value) {
  .transaction_decimal_string(.transaction_decimal_abs(.transaction_decimal_parse(value, allow_zero = FALSE)))
}

.data_transaction_editor_multiply <- function(left, right) {
  .transaction_decimal_string(.transaction_decimal_multiply(
    .transaction_decimal_parse(left, allow_zero = FALSE, positive_only = TRUE),
    .transaction_decimal_parse(right, allow_zero = FALSE, positive_only = TRUE)
  ))
}

.data_transaction_editor_posting <- function(sequence, account, asset, role, quantity, valuation, currency, price = NULL, memo = NULL) {
  new_transaction_posting_v1(
    as.integer(sequence), account$account_id, asset$asset_id, role, quantity,
    price, if (is.null(price)) NULL else currency, valuation, currency, memo
  )
}

.data_transaction_editor_form_shape <- function(form) {
  required <- c(
    "action", "profile", "portfolio_ref", "transaction_ref", "effective_at_utc", "local_date",
    "account_ref", "asset_ref", "cash_account_ref", "cash_asset_ref",
    "counterparty_account_ref", "destination_account_ref", "quantity_decimal",
    "unit_price_decimal", "amount_decimal", "fee_decimal", "tax_decimal", "memo"
  )
  if (!is.list(form) || !identical(names(form), required)) {
    .data_transaction_editor_abort("data_transaction_editor_input_invalid")
  }
  form
}

.data_transaction_editor_build <- function(editor, context, form, now_utc) {
  selection <- .data_transaction_editor_selection(editor, context)
  form <- .data_transaction_editor_form_shape(form)
  action <- .data_transaction_editor_scalar(form$action, c("create", "correct", "void"))
  effective_at_utc <- .data_transaction_editor_scalar(form$effective_at_utc, maximum = 20L)
  local_date <- .data_transaction_editor_scalar(form$local_date, maximum = 10L)
  memo <- .data_transaction_editor_scalar(form$memo, optional = TRUE)
  if (!.canonical_utc_valid(now_utc)) .data_transaction_editor_abort("data_transaction_editor_input_invalid")
  predecessor <- NULL
  if (action != "create") {
    predecessor <- .data_transaction_editor_resolve(selection, "transactions", form$transaction_ref)
    if (!.catalog_time_later(now_utc, predecessor$record$created_at_utc)) {
      .data_transaction_editor_abort("data_transaction_editor_input_invalid")
    }
  }
  editor$sequence <- editor$sequence + 1L
  token_material <- list(
    editor_command_token_version = 1L,
    context_fingerprint = selection$context_fingerprint,
    selection_fingerprint = selection$selection_fingerprint,
    sequence = editor$sequence,
    now_utc = now_utc,
    form = form
  )
  token <- paste0("tok_editor_", substr(.catalog_fingerprint(token_material), 1L, 32L))
  imported_lineage <- !is.null(predecessor) &&
    .data_transaction_editor_imported_lineage(predecessor)
  if (action == "void") {
    command <- .transaction_build_command(
      context, "void", token, NULL, NULL, effective_at_utc, local_date,
      now_utc, list(), memo, predecessor$record$transaction_id
    )
    if (imported_lineage) command$command_type <- "transaction_import_void_v1"
    return(list(
      command = command,
      action = action,
      profile = if (predecessor$record$transaction_type == "transfer") "internal_transfer" else predecessor$record$transaction_type,
      cash_flow_mode = if (imported_lineage && predecessor$record$transaction_type %in% c("buy", "sell")) {
        "separate_cash_movement"
      } else if (imported_lineage && identical(predecessor$record$transaction_type, "reward")) {
        "asset_income_no_cash_posting"
      } else if (imported_lineage) {
        "movement_no_guv"
      } else "embedded_cash_posting",
      postings = list(),
      selection = selection,
      predecessor = predecessor,
      form = form
    ))
  }
  profile <- .data_transaction_editor_scalar(
    form$profile, c("buy", "sell", "deposit", "withdrawal", "internal_transfer", "reward")
  )
  portfolio <- .data_transaction_editor_resolve(selection, "portfolios", form$portfolio_ref)
  currency <- portfolio$base_currency
  postings <- list()
  settlement_mode <- NULL
  if (profile %in% c("buy", "sell", "reward")) {
    account <- .data_transaction_editor_resolve(selection, "accounts", form$account_ref)
    asset <- .data_transaction_editor_resolve(selection, "assets", form$asset_ref)
    quantity <- .data_transaction_editor_positive_decimal(form$quantity_decimal)
    price <- .data_transaction_editor_positive_decimal(form$unit_price_decimal)
    fee <- .data_transaction_editor_positive_decimal(form$fee_decimal, optional = TRUE)
    tax <- .data_transaction_editor_positive_decimal(form$tax_decimal, optional = TRUE)
    gross <- .data_transaction_editor_multiply(quantity, price)
    booked_gross <- .data_transaction_editor_positive_decimal(form$amount_decimal, optional = TRUE)
    if (profile == "reward") {
      if (!imported_lineage || !is.null(tax) || !is.null(booked_gross)) {
        .data_transaction_editor_abort("data_transaction_editor_input_invalid")
      }
      postings <- list(
        .data_transaction_editor_posting(1L, account, asset, "income", quantity, gross, currency, price)
      )
      if (!is.null(fee)) postings[[2L]] <- .data_transaction_editor_posting(
        2L, account, asset, "fee", .data_transaction_editor_negate(fee),
        .data_transaction_editor_negate(.data_transaction_editor_multiply(fee, price)),
        currency, price
      )
    } else {
      if (profile == "buy" && !is.null(tax)) {
        .data_transaction_editor_abort("data_transaction_editor_input_invalid")
      }
      asset_quantity <- if (profile == "buy") quantity else .data_transaction_editor_negate(quantity)
      asset_value <- if (profile == "buy") gross else .data_transaction_editor_negate(gross)
      if (imported_lineage) {
        if (!is.null(fee) || !is.null(tax) || !is.null(booked_gross)) {
          .data_transaction_editor_abort("data_transaction_editor_input_invalid")
        }
        postings <- list(
          .data_transaction_editor_posting(1L, account, asset, "asset", asset_quantity, asset_value, currency, price)
        )
      } else {
        cash_account <- .data_transaction_editor_resolve(selection, "accounts", form$cash_account_ref)
        cash_asset <- .data_transaction_editor_resolve(selection, "assets", form$cash_asset_ref)
        settlement <- if (is.null(booked_gross)) gross else booked_gross
        settlement_mode <- if (is.null(booked_gross)) "derived_exact" else "explicit_cash"
        cash_value <- if (profile == "buy") .data_transaction_editor_negate(settlement) else settlement
        postings <- list(
          .data_transaction_editor_posting(1L, account, asset, "asset", asset_quantity, asset_value, currency, price),
          .data_transaction_editor_posting(2L, cash_account, cash_asset, "cash", cash_value, cash_value, currency)
        )
        if (!is.null(fee)) postings[[length(postings) + 1L]] <- .data_transaction_editor_posting(
          length(postings) + 1L, cash_account, cash_asset, "fee",
          .data_transaction_editor_negate(fee), .data_transaction_editor_negate(fee), currency
        )
        if (!is.null(tax)) postings[[length(postings) + 1L]] <- .data_transaction_editor_posting(
          length(postings) + 1L, cash_account, cash_asset, "tax",
          .data_transaction_editor_negate(tax), .data_transaction_editor_negate(tax), currency
        )
      }
    }
  } else {
    account <- .data_transaction_editor_resolve(selection, "accounts", form$cash_account_ref)
    cash_asset <- .data_transaction_editor_resolve(selection, "assets", form$cash_asset_ref)
    amount <- .data_transaction_editor_positive_decimal(form$amount_decimal)
    fee <- .data_transaction_editor_positive_decimal(form$fee_decimal, optional = TRUE)
    if (!is.null(.data_transaction_editor_positive_decimal(form$tax_decimal, optional = TRUE))) {
      .data_transaction_editor_abort("data_transaction_editor_input_invalid")
    }
    if (imported_lineage) {
      price <- .data_transaction_editor_positive_decimal(form$unit_price_decimal, optional = TRUE)
      value <- if (is.null(price)) amount else .data_transaction_editor_multiply(amount, price)
      first_value <- if (profile == "deposit") amount else .data_transaction_editor_negate(amount)
      first_valuation <- if (profile == "deposit") value else .data_transaction_editor_negate(value)
      postings <- list(
        .data_transaction_editor_posting(
          1L, account, cash_asset, "transfer", first_value, first_valuation, currency, price
        )
      )
      if (profile == "internal_transfer") {
        other <- .data_transaction_editor_resolve(selection, "accounts", form$destination_account_ref)
        postings[[2L]] <- .data_transaction_editor_posting(
          2L, other, cash_asset, "transfer", amount, value, currency, price
        )
      }
      if (!is.null(fee)) postings[[length(postings) + 1L]] <- .data_transaction_editor_posting(
        length(postings) + 1L, account, cash_asset, "fee",
        .data_transaction_editor_negate(fee),
        .data_transaction_editor_negate(if (is.null(price)) fee else .data_transaction_editor_multiply(fee, price)),
        currency, price
      )
    } else {
      if (profile == "internal_transfer") {
        other <- .data_transaction_editor_resolve(selection, "accounts", form$destination_account_ref)
        roles <- c("transfer", "transfer")
        values <- c(.data_transaction_editor_negate(amount), amount)
      } else {
        other <- .data_transaction_editor_resolve(selection, "accounts", form$counterparty_account_ref)
        roles <- c("cash", "transfer")
        values <- if (profile == "deposit") {
          c(amount, .data_transaction_editor_negate(amount))
        } else c(.data_transaction_editor_negate(amount), amount)
      }
      postings <- list(
        .data_transaction_editor_posting(1L, account, cash_asset, roles[[1]], values[[1]], values[[1]], currency),
        .data_transaction_editor_posting(2L, other, cash_asset, roles[[2]], values[[2]], values[[2]], currency)
      )
      if (!is.null(fee)) postings[[3L]] <- .data_transaction_editor_posting(
        3L, account, cash_asset, "fee", .data_transaction_editor_negate(fee),
        .data_transaction_editor_negate(fee), currency
      )
    }
  }
  command <- .transaction_build_command(
    context, action, token, portfolio$portfolio_id, profile, effective_at_utc, local_date,
    now_utc, postings, memo,
    if (action == "correct") predecessor$record$transaction_id else NULL,
    settlement_mode
  )
  if (imported_lineage && action == "correct") {
    command$command_type <- "transaction_import_correct_v1"
  }
  list(
    command = command,
    action = action,
    profile = profile,
    cash_flow_mode = if (imported_lineage && profile %in% c("buy", "sell")) {
      "separate_cash_movement"
    } else if (imported_lineage && identical(profile, "reward")) {
      "asset_income_no_cash_posting"
    } else if (imported_lineage) {
      "movement_no_guv"
    } else "embedded_cash_posting",
    postings = postings,
    selection = selection,
    predecessor = predecessor,
    form = form
  )
}

.data_transaction_editor_time <- function(value) {
  as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

.data_transaction_editor_posting_preview <- function(built, posting) {
  selection <- built$selection
  account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", posting$account_id)
  asset_ref <- .data_transaction_editor_reverse_ref(selection, "assets", posting$asset_id)
  account <- selection$accounts$by_ref[[account_ref]]
  asset <- selection$assets$by_ref[[asset_ref]]
  role_labels <- c(
    asset = "Asset", cash = "Cash", fee = "Gebühr", tax = "Steuer",
    income = "Ertrag", transfer = "Transfer"
  )
  list(
    sequence = as.character(posting$sequence_no),
    account = account$display_name,
    asset = asset$display_name,
    role = unname(role_labels[[posting$posting_role]]),
    quantity_decimal = posting$quantity_decimal,
    unit_price_decimal = if (is.null(posting$unit_price_decimal)) "—" else posting$unit_price_decimal,
    valuation_amount_decimal = posting$valuation_amount_decimal,
    currency = posting$valuation_currency
  )
}

data_transaction_editor_prepare_v1 <- function(editor, context, form, now_utc) {
  .data_transaction_editor_check(editor)
  built <- tryCatch(
    .data_transaction_editor_build(editor, context, form, now_utc),
    error = function(error) {
      if (inherits(error, "spot_data_transaction_editor_error")) stop(error)
      .data_transaction_editor_abort("data_transaction_editor_input_invalid")
    }
  )
  command_fingerprint <- .catalog_fingerprint(unclass(built$command))
  preview_ref <- paste0("editor_preview_", substr(.catalog_hash_parts(c(
    "data-transaction-editor-preview-v1", built$selection$context_fingerprint,
    command_fingerprint, as.character(editor$sequence)
  )), 1L, 24L))
  expires_at_utc <- format(.data_transaction_editor_time(now_utc) + 600, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  state <- list(
    consumed = FALSE,
    context_fingerprint = built$selection$context_fingerprint,
    command_fingerprint = command_fingerprint,
    expires_at_utc = expires_at_utc,
    built = built,
    result = NULL
  )
  assign(preview_ref, state, envir = editor$previews)
  profile_labels <- c(
    buy = "Kauf", sell = "Verkauf", deposit = "Einzahlung",
    withdrawal = "Auszahlung", internal_transfer = "Interner Transfer", reward = "Reward"
  )
  list(
    editor_preview_contract_version = 1L,
    status = "pending_confirmation",
    preview_ref = preview_ref,
    action = built$action,
    action_label = c(create = "Neu anlegen", correct = "Korrigieren", void = "Stornieren")[[built$action]],
    profile = built$profile,
    profile_label = unname(profile_labels[[built$profile]]),
    cash_flow_mode = built$cash_flow_mode,
    settlement_mode = built$command$settlement_mode,
    effective_at_utc = built$command$effective_at_utc,
    local_date = built$command$local_date,
    expires_at_utc = expires_at_utc,
    replaces = if (is.null(built$predecessor)) "—" else paste(
      built$predecessor$record$local_date,
      .data_transaction_editor_type_label(built$predecessor$record$transaction_type)
    ),
    before_postings = if (is.null(built$predecessor)) list() else lapply(
      built$predecessor$postings,
      function(posting) .data_transaction_editor_posting_preview(built, posting)
    ),
    after_postings = lapply(
      built$postings,
      function(posting) .data_transaction_editor_posting_preview(built, posting)
    ),
    postings = lapply(built$postings, function(posting) .data_transaction_editor_posting_preview(built, posting)),
    confirmation_required = TRUE,
    one_attempt_only = TRUE,
    canonical_ids_exposed = FALSE,
    provider_access = FALSE
  )
}

data_transaction_editor_execute_v1 <- function(editor, context, preview_ref, confirmed, now_utc) {
  .data_transaction_editor_check(editor)
  .data_transaction_editor_context_check(context)
  if (!isTRUE(confirmed)) .data_transaction_editor_abort("data_transaction_editor_confirmation_required")
  if (!is.character(preview_ref) || length(preview_ref) != 1L || is.na(preview_ref) ||
      !exists(preview_ref, envir = editor$previews, inherits = FALSE)) {
    .data_transaction_editor_abort("data_transaction_editor_preview_required")
  }
  state <- get(preview_ref, envir = editor$previews, inherits = FALSE)
  if (isTRUE(state$consumed)) .data_transaction_editor_abort("data_transaction_editor_confirmation_consumed")
  if (!.canonical_utc_valid(now_utc) ||
      .data_transaction_editor_time(now_utc) > .data_transaction_editor_time(state$expires_at_utc) ||
      !identical(state$context_fingerprint, runtime_context_fingerprint(context))) {
    .data_transaction_editor_abort("data_transaction_editor_confirmation_expired")
  }
  state$consumed <- TRUE
  assign(preview_ref, state, envir = editor$previews)
  result <- tryCatch(
    .transaction_execute_public(context, state$built$command),
    error = function(error) {
      if (inherits(error, "spot_transaction_data_command_error")) stop(error)
      .data_transaction_editor_abort("data_transaction_editor_command_failed")
    }
  )
  state$result <- result
  assign(preview_ref, state, envir = editor$previews)
  list(
    editor_result_contract_version = 1L,
    status = result$status,
    action = result$action,
    profile = state$built$profile,
    settlement_mode = state$built$command$settlement_mode,
    posting_count = result$posting_count,
    committed_at_utc = result$committed_at_utc,
    preview_consumed = TRUE,
    canonical_ids_exposed = FALSE,
    provider_access = FALSE
  )
}

.data_transaction_editor_entry_form <- function(selection, transaction_ref, entry) {
  record <- entry$record
  profile <- if (record$transaction_type == "transfer") "internal_transfer" else record$transaction_type
  form <- list(
    action = "correct",
    profile = profile,
    portfolio_ref = .data_transaction_editor_reverse_ref(selection, "portfolios", record$portfolio_id),
    transaction_ref = transaction_ref,
    effective_at_utc = record$effective_at_utc,
    local_date = record$local_date,
    account_ref = "",
    asset_ref = "",
    cash_account_ref = "",
    cash_asset_ref = "",
    counterparty_account_ref = "",
    destination_account_ref = "",
    quantity_decimal = "",
    unit_price_decimal = "",
    amount_decimal = "",
    fee_decimal = "",
    tax_decimal = "",
    memo = if (is.null(record$memo)) "" else record$memo
  )
  postings <- entry$postings
  role <- function(value) Filter(function(posting) posting$posting_role == value, postings)
  if (profile %in% c("buy", "sell", "reward")) {
    asset_posting <- if (profile == "reward") role("income")[[1L]] else role("asset")[[1L]]
    cash_postings <- role("cash")
    form$account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", asset_posting$account_id)
    form$asset_ref <- .data_transaction_editor_reverse_ref(selection, "assets", asset_posting$asset_id)
    if (length(cash_postings)) {
      form$cash_account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", cash_postings[[1L]]$account_id)
      form$cash_asset_ref <- .data_transaction_editor_reverse_ref(selection, "assets", cash_postings[[1L]]$asset_id)
    }
    form$quantity_decimal <- .data_transaction_editor_abs(asset_posting$quantity_decimal)
    form$unit_price_decimal <- asset_posting$unit_price_decimal
    if (length(cash_postings) && entry$audit$command_type %in% c(
      "transaction_create_explicit_settlement_v1", "transaction_correct_explicit_settlement_v1"
    )) {
      form$amount_decimal <- .data_transaction_editor_abs(cash_postings[[1L]]$quantity_decimal)
    }
    fees <- role("fee")
    taxes <- role("tax")
    if (length(fees)) form$fee_decimal <- .data_transaction_editor_abs(fees[[1L]]$quantity_decimal)
    if (length(taxes)) form$tax_decimal <- .data_transaction_editor_abs(taxes[[1L]]$quantity_decimal)
  } else {
    form$cash_account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", postings[[1L]]$account_id)
    form$cash_asset_ref <- .data_transaction_editor_reverse_ref(selection, "assets", postings[[1L]]$asset_id)
    form$amount_decimal <- .data_transaction_editor_abs(postings[[1L]]$quantity_decimal)
    form$unit_price_decimal <- if (is.null(postings[[1L]]$unit_price_decimal)) "" else postings[[1L]]$unit_price_decimal
    if (profile == "internal_transfer") {
      form$destination_account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", postings[[2L]]$account_id)
    } else if (length(postings) >= 2L && identical(postings[[2L]]$posting_role, "transfer") &&
               !.data_transaction_editor_imported_lineage(entry)) {
      form$counterparty_account_ref <- .data_transaction_editor_reverse_ref(selection, "accounts", postings[[2L]]$account_id)
    }
    fees <- role("fee")
    if (length(fees)) form$fee_decimal <- .data_transaction_editor_abs(fees[[1L]]$quantity_decimal)
  }
  form
}

data_transaction_editor_prefill_v1 <- function(editor, context, transaction_ref) {
  selection <- .data_transaction_editor_selection(editor, context)
  entry <- .data_transaction_editor_resolve(selection, "transactions", transaction_ref)
  .data_transaction_editor_entry_form(selection, transaction_ref, entry)
}
