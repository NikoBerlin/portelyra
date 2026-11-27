transaction_data_command_error_codes <- function() {
  c(
    "transaction_command_context_invalid",
    "transaction_command_role_not_authorized",
    "transaction_command_repository_invalid",
    "transaction_command_input_invalid",
    "transaction_command_decimal_invalid",
    "transaction_command_date_invalid",
    "transaction_command_profile_unsupported",
    "transaction_command_entity_not_found",
    "transaction_command_entity_state_invalid",
    "transaction_command_entity_reference_invalid",
    "transaction_command_provenance_invalid",
    "transaction_command_integrity_invalid",
    "transaction_command_posting_sequence_invalid",
    "transaction_command_posting_role_invalid",
    "transaction_command_account_invalid",
    "transaction_command_asset_invalid",
    "transaction_command_currency_invalid",
    "transaction_command_valuation_invalid",
    "transaction_command_principal_conservation_invalid",
    "transaction_command_fifo_inventory_insufficient",
    "transaction_command_supersession_conflict",
    "transaction_command_duplicate_conflict",
    "transaction_command_idempotency_conflict",
    "transaction_command_caller_transaction_rejected",
    "transaction_command_lock_unavailable",
    "transaction_command_transaction_failed",
    "transaction_command_boundary_failed"
  )
}

.transaction_condition <- function(code) {
  if (!is.character(code) || length(code) != 1L || is.na(code) ||
      !code %in% transaction_data_command_error_codes()) {
    stop("unregistered_transaction_data_command_error_code", call. = FALSE)
  }
  structure(
    list(message = code, call = NULL, code = code),
    class = c("spot_transaction_data_command_error", "error", "condition")
  )
}

.transaction_abort <- function(code) stop(.transaction_condition(code))

.transaction_boundary_eval <- function(expression, fallback = "transaction_command_boundary_failed") {
  result <- tryCatch(
    expression,
    spot_transaction_data_command_error = function(error) error,
    spot_canonical_repository_error = function(error) .transaction_condition("transaction_command_repository_invalid"),
    spot_runtime_error = function(error) .transaction_condition("transaction_command_context_invalid"),
    spot_catalog_data_command_error = function(error) {
      mapping <- c(
        catalog_command_context_invalid = "transaction_command_context_invalid",
        catalog_command_role_not_authorized = "transaction_command_role_not_authorized",
        catalog_command_repository_invalid = "transaction_command_repository_invalid",
        catalog_command_entity_not_found = "transaction_command_entity_not_found",
        catalog_command_entity_state_invalid = "transaction_command_entity_state_invalid",
        catalog_command_provenance_invalid = "transaction_command_provenance_invalid",
        catalog_command_integrity_invalid = "transaction_command_integrity_invalid"
      )
      code <- unname(mapping[[error$code]])
      .transaction_condition(if (is.null(code)) fallback else code)
    },
    error = function(error) .transaction_condition(fallback)
  )
  if (inherits(result, "spot_transaction_data_command_error")) stop(result)
  result
}

.transaction_context_check <- function(context) {
  if (!isTRUE(tryCatch(runtime_context_valid(context), error = function(error) FALSE))) {
    .transaction_abort("transaction_command_context_invalid")
  }
  if (context$role != "desktop_owner") .transaction_abort("transaction_command_role_not_authorized")
  invisible(TRUE)
}

.transaction_unsigned_strip <- function(value) {
  result <- sub("^0+", "", value)
  if (!nzchar(result)) "0" else result
}

.transaction_unsigned_compare <- function(left, right) {
  left <- .transaction_unsigned_strip(left)
  right <- .transaction_unsigned_strip(right)
  if (nchar(left) < nchar(right)) return(-1L)
  if (nchar(left) > nchar(right)) return(1L)
  if (identical(left, right)) return(0L)
  left_digits <- utf8ToInt(left)
  right_digits <- utf8ToInt(right)
  first_difference <- which(left_digits != right_digits)[[1]]
  if (left_digits[[first_difference]] < right_digits[[first_difference]]) -1L else 1L
}

.transaction_unsigned_add <- function(left, right) {
  left_digits <- rev(utf8ToInt(left) - 48L)
  right_digits <- rev(utf8ToInt(right) - 48L)
  length_out <- max(length(left_digits), length(right_digits)) + 1L
  output <- integer(length_out)
  carry <- 0L
  for (index in seq_len(length_out - 1L)) {
    a <- if (index <= length(left_digits)) left_digits[[index]] else 0L
    b <- if (index <= length(right_digits)) right_digits[[index]] else 0L
    total <- a + b + carry
    output[[index]] <- total %% 10L
    carry <- total %/% 10L
  }
  output[[length_out]] <- carry
  .transaction_unsigned_strip(paste0(rev(output), collapse = ""))
}

.transaction_unsigned_subtract <- function(left, right) {
  if (.transaction_unsigned_compare(left, right) < 0L) {
    .transaction_abort("transaction_command_decimal_invalid")
  }
  left_digits <- rev(utf8ToInt(left) - 48L)
  right_digits <- rev(utf8ToInt(right) - 48L)
  output <- integer(length(left_digits))
  borrow <- 0L
  for (index in seq_along(left_digits)) {
    a <- left_digits[[index]] - borrow
    b <- if (index <= length(right_digits)) right_digits[[index]] else 0L
    if (a < b) {
      a <- a + 10L
      borrow <- 1L
    } else {
      borrow <- 0L
    }
    output[[index]] <- a - b
  }
  if (borrow != 0L) .transaction_abort("transaction_command_decimal_invalid")
  .transaction_unsigned_strip(paste0(rev(output), collapse = ""))
}

.transaction_unsigned_multiply <- function(left, right) {
  if (left == "0" || right == "0") return("0")
  left_digits <- rev(utf8ToInt(left) - 48L)
  right_digits <- rev(utf8ToInt(right) - 48L)
  output <- integer(length(left_digits) + length(right_digits) + 1L)
  for (left_index in seq_along(left_digits)) {
    for (right_index in seq_along(right_digits)) {
      output[[left_index + right_index - 1L]] <- output[[left_index + right_index - 1L]] +
        left_digits[[left_index]] * right_digits[[right_index]]
    }
  }
  for (index in seq_len(length(output) - 1L)) {
    carry <- output[[index]] %/% 10L
    output[[index]] <- output[[index]] %% 10L
    output[[index + 1L]] <- output[[index + 1L]] + carry
  }
  while (tail(output, 1L) >= 10L) {
    carry <- tail(output, 1L) %/% 10L
    output[[length(output)]] <- tail(output, 1L) %% 10L
    output <- c(output, carry)
  }
  .transaction_unsigned_strip(paste0(rev(output), collapse = ""))
}

.transaction_decimal_parse <- function(value, allow_zero = TRUE, positive_only = FALSE) {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      nchar(value, type = "bytes") > 80L || value == "-0" ||
      !grepl("^-?(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value)) {
    .transaction_abort("transaction_command_decimal_invalid")
  }
  negative <- startsWith(value, "-")
  unsigned <- if (negative) substring(value, 2L) else value
  pieces <- strsplit(unsigned, ".", fixed = TRUE)[[1]]
  fractional <- if (length(pieces) == 2L) pieces[[2]] else ""
  digits <- .transaction_unsigned_strip(paste0(pieces[[1]], fractional))
  sign <- if (digits == "0") 0L else if (negative) -1L else 1L
  if (!allow_zero && sign == 0L) .transaction_abort("transaction_command_decimal_invalid")
  if (positive_only && sign != 1L) .transaction_abort("transaction_command_decimal_invalid")
  structure(list(sign = sign, digits = digits, scale = nchar(fractional)), class = "spot_exact_decimal_v1")
}

.transaction_decimal_normalize <- function(sign, digits, scale) {
  digits <- .transaction_unsigned_strip(digits)
  if (digits == "0") return(structure(list(sign = 0L, digits = "0", scale = 0L), class = "spot_exact_decimal_v1"))
  while (scale > 0L && substr(digits, nchar(digits), nchar(digits)) == "0") {
    digits <- substr(digits, 1L, nchar(digits) - 1L)
    scale <- scale - 1L
  }
  structure(list(sign = as.integer(sign), digits = digits, scale = as.integer(scale)), class = "spot_exact_decimal_v1")
}

.transaction_decimal_align <- function(left, right) {
  scale <- max(left$scale, right$scale)
  list(
    left = paste0(left$digits, strrep("0", scale - left$scale)),
    right = paste0(right$digits, strrep("0", scale - right$scale)),
    scale = scale
  )
}

.transaction_decimal_add <- function(left, right) {
  if (left$sign == 0L) return(right)
  if (right$sign == 0L) return(left)
  aligned <- .transaction_decimal_align(left, right)
  if (left$sign == right$sign) {
    return(.transaction_decimal_normalize(
      left$sign, .transaction_unsigned_add(aligned$left, aligned$right), aligned$scale
    ))
  }
  comparison <- .transaction_unsigned_compare(aligned$left, aligned$right)
  if (comparison == 0L) return(.transaction_decimal_normalize(0L, "0", 0L))
  if (comparison > 0L) {
    .transaction_decimal_normalize(
      left$sign, .transaction_unsigned_subtract(aligned$left, aligned$right), aligned$scale
    )
  } else {
    .transaction_decimal_normalize(
      right$sign, .transaction_unsigned_subtract(aligned$right, aligned$left), aligned$scale
    )
  }
}

.transaction_decimal_negate <- function(value) {
  .transaction_decimal_normalize(-value$sign, value$digits, value$scale)
}

.transaction_decimal_subtract <- function(left, right) {
  .transaction_decimal_add(left, .transaction_decimal_negate(right))
}

.transaction_decimal_multiply <- function(left, right) {
  .transaction_decimal_normalize(
    left$sign * right$sign,
    .transaction_unsigned_multiply(left$digits, right$digits),
    left$scale + right$scale
  )
}

.transaction_decimal_compare <- function(left, right) {
  if (left$sign < right$sign) return(-1L)
  if (left$sign > right$sign) return(1L)
  if (left$sign == 0L) return(0L)
  aligned <- .transaction_decimal_align(left, right)
  comparison <- .transaction_unsigned_compare(aligned$left, aligned$right)
  if (left$sign < 0L) -comparison else comparison
}

.transaction_decimal_equal <- function(left, right) .transaction_decimal_compare(left, right) == 0L
.transaction_decimal_abs <- function(value) .transaction_decimal_normalize(abs(value$sign), value$digits, value$scale)
.transaction_decimal_zero <- function() .transaction_decimal_normalize(0L, "0", 0L)

.transaction_decimal_string <- function(value) {
  if (value$sign == 0L) return("0")
  digits <- value$digits
  if (value$scale > 0L) {
    digits <- paste0(strrep("0", max(0L, value$scale + 1L - nchar(digits))), digits)
    split <- nchar(digits) - value$scale
    digits <- paste0(substr(digits, 1L, split), ".", substr(digits, split + 1L, nchar(digits)))
  }
  result <- paste0(if (value$sign < 0L) "-" else "", digits)
  if (nchar(result, type = "bytes") > 80L) .transaction_abort("transaction_command_decimal_invalid")
  result
}

.transaction_date_valid <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value)) return(FALSE)
  parsed <- tryCatch(as.Date(value, format = "%Y-%m-%d"), error = function(error) as.Date(NA))
  !is.na(parsed) && format(parsed, "%Y-%m-%d") == value
}

.transaction_text_optional <- function(value, maximum) {
  is.null(value) || (
    is.character(value) && length(value) == 1L && !is.na(value) &&
      nchar(value, type = "bytes") <= maximum
  )
}

.transaction_id_valid <- function(value, prefix) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    startsWith(value, prefix) && grepl("^[a-z0-9_]+$", value)
}

.transaction_token_valid <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) &&
    nchar(value, type = "bytes") >= 8L && nchar(value, type = "bytes") <= 64L &&
    grepl("^tok_[a-z0-9_]+$", value)
}

new_transaction_posting_v1 <- function(
  sequence_no,
  account_id,
  asset_id,
  posting_role,
  quantity_decimal,
  unit_price_decimal = NULL,
  price_currency = NULL,
  valuation_amount_decimal,
  valuation_currency,
  memo = NULL
) {
  .transaction_boundary_eval({
    if (!is.integer(sequence_no) || length(sequence_no) != 1L || is.na(sequence_no) || sequence_no < 1L ||
        !.transaction_id_valid(account_id, "acc_") || !.transaction_id_valid(asset_id, "ast_") ||
        !is.character(posting_role) || length(posting_role) != 1L || is.na(posting_role) ||
        !posting_role %in% c("asset", "cash", "fee", "tax", "income", "transfer") ||
        !.transaction_text_optional(memo, 500L)) {
      .transaction_abort("transaction_command_input_invalid")
    }
    .transaction_decimal_parse(quantity_decimal, allow_zero = FALSE)
    .transaction_decimal_parse(valuation_amount_decimal, allow_zero = FALSE)
    if (is.null(unit_price_decimal) != is.null(price_currency)) {
      .transaction_abort("transaction_command_input_invalid")
    }
    if (!is.null(unit_price_decimal)) {
      .transaction_decimal_parse(unit_price_decimal, allow_zero = FALSE, positive_only = TRUE)
      if (!is.character(price_currency) || length(price_currency) != 1L || is.na(price_currency) ||
          !grepl("^[A-Z]{3}$", price_currency)) .transaction_abort("transaction_command_currency_invalid")
    }
    if (!is.character(valuation_currency) || length(valuation_currency) != 1L || is.na(valuation_currency) ||
        !grepl("^[A-Z]{3}$", valuation_currency)) .transaction_abort("transaction_command_currency_invalid")
    list(
      sequence_no = sequence_no,
      account_id = account_id,
      asset_id = asset_id,
      posting_role = posting_role,
      quantity_decimal = quantity_decimal,
      unit_price_decimal = unit_price_decimal,
      price_currency = price_currency,
      valuation_amount_decimal = valuation_amount_decimal,
      valuation_currency = valuation_currency,
      memo = memo
    )
  }, fallback = "transaction_command_input_invalid")
}

.transaction_profile_type <- function(profile) {
  mapping <- c(
    buy = "buy",
    sell = "sell",
    deposit = "deposit",
    withdrawal = "withdrawal",
    internal_transfer = "transfer",
    reward = "reward"
  )
  unname(mapping[[profile]])
}

.transaction_validate_posting_input <- function(postings) {
  required <- c(
    "sequence_no", "account_id", "asset_id", "posting_role", "quantity_decimal",
    "unit_price_decimal", "price_currency", "valuation_amount_decimal", "valuation_currency", "memo"
  )
  if (!is.list(postings) || !length(postings)) .transaction_abort("transaction_command_input_invalid")
  for (posting in postings) {
    if (!is.list(posting) || !identical(names(posting), required)) {
      .transaction_abort("transaction_command_input_invalid")
    }
    invisible(do.call(new_transaction_posting_v1, posting))
  }
  sequences <- vapply(postings, function(posting) posting$sequence_no, integer(1))
  if (!identical(sequences, seq_along(postings))) {
    .transaction_abort("transaction_command_posting_sequence_invalid")
  }
  invisible(TRUE)
}

.transaction_settlement_mode <- function(transaction_profile, requested_mode) {
  if (!transaction_profile %in% c("buy", "sell")) {
    if (!is.null(requested_mode)) .transaction_abort("transaction_command_input_invalid")
    return("not_applicable")
  }
  if (is.null(requested_mode)) return("derived_exact")
  if (!is.character(requested_mode) || length(requested_mode) != 1L || is.na(requested_mode) ||
      !requested_mode %in% c("derived_exact", "explicit_cash")) {
    .transaction_abort("transaction_command_input_invalid")
  }
  requested_mode
}

.transaction_command_identity <- function(context, action, command_token, supersedes_transaction_id = NULL) {
  parts <- c(
    "native-transaction-command-v1", context$tenant_id, context$user_id,
    context$data_space_id, action, command_token
  )
  if (!is.null(supersedes_transaction_id)) parts <- c(parts, supersedes_transaction_id)
  paste0("cmd_txn_", substr(.catalog_hash_parts(parts), 1L, 52L))
}

.transaction_entity_identity <- function(context, action, command_token, supersedes_transaction_id = NULL) {
  parts <- c(
    "native-transaction-entity-v1", context$tenant_id, context$user_id,
    context$data_space_id, action, command_token
  )
  if (!is.null(supersedes_transaction_id)) parts <- c(parts, supersedes_transaction_id)
  paste0("txn_", substr(.catalog_hash_parts(parts), 1L, 24L))
}

.transaction_build_command <- function(
  context,
  action,
  command_token,
  portfolio_id,
  transaction_profile,
  effective_at_utc,
  local_date,
  committed_at_utc,
  postings,
  memo,
  supersedes_transaction_id = NULL,
  settlement_mode = NULL
) {
  .transaction_context_check(context)
  if (!action %in% c("create", "correct", "void") || !.transaction_token_valid(command_token) ||
      !.transaction_text_optional(memo, 500L)) {
    .transaction_abort("transaction_command_input_invalid")
  }
  if (!.canonical_utc_valid(effective_at_utc) || !.transaction_date_valid(local_date) ||
      !.canonical_utc_valid(committed_at_utc)) {
    .transaction_abort("transaction_command_date_invalid")
  }
  if (action == "create") {
    if (!is.null(supersedes_transaction_id) || !.transaction_id_valid(portfolio_id, "ptf_")) {
      .transaction_abort("transaction_command_input_invalid")
    }
  } else if (!.transaction_id_valid(supersedes_transaction_id, "txn_")) {
    .transaction_abort("transaction_command_input_invalid")
  }
  if (action == "void") {
    if (!is.null(transaction_profile) || !is.null(portfolio_id) || length(postings)) {
      .transaction_abort("transaction_command_input_invalid")
    }
  } else {
    if (!is.character(transaction_profile) || length(transaction_profile) != 1L || is.na(transaction_profile) ||
        !transaction_profile %in% c("buy", "sell", "deposit", "withdrawal", "internal_transfer", "reward")) {
      .transaction_abort("transaction_command_profile_unsupported")
    }
    if (!.transaction_id_valid(portfolio_id, "ptf_")) .transaction_abort("transaction_command_input_invalid")
    .transaction_validate_posting_input(postings)
  }
  settlement_mode <- if (action == "void") {
    if (!is.null(settlement_mode)) .transaction_abort("transaction_command_input_invalid")
    "not_applicable"
  } else {
    .transaction_settlement_mode(transaction_profile, settlement_mode)
  }
  command_type <- if (identical(settlement_mode, "explicit_cash")) {
    paste0("transaction_", action, "_explicit_settlement_v1")
  } else {
    paste0("transaction_", action, "_v1")
  }
  structure(
    list(
      transaction_command_contract_version = 1L,
      action = action,
      command_type = command_type,
      settlement_mode = settlement_mode,
      command_token = command_token,
      command_id = .transaction_command_identity(context, action, command_token, supersedes_transaction_id),
      transaction_id = .transaction_entity_identity(context, action, command_token, supersedes_transaction_id),
      portfolio_id = portfolio_id,
      transaction_profile = transaction_profile,
      effective_at_utc = effective_at_utc,
      local_date = local_date,
      committed_at_utc = committed_at_utc,
      postings = postings,
      memo = memo,
      supersedes_transaction_id = supersedes_transaction_id
    ),
    class = "spot_transaction_command_v1"
  )
}

.transaction_posting_identity <- function(transaction_id, sequence_no) {
  paste0(
    "pst_",
    substr(.catalog_hash_parts(c("native-transaction-posting-v1", transaction_id, as.character(sequence_no))), 1L, 24L)
  )
}

.transaction_record_columns <- function() {
  c(
    "transaction_id", "portfolio_id", "transaction_type", "record_action", "effective_at_utc",
    "local_date", "memo", "supersedes_transaction_id", "origin_type", "origin_ref",
    "created_at_utc", "created_by_actor"
  )
}

.transaction_posting_columns <- function() {
  c(
    "posting_id", "transaction_id", "sequence_no", "account_id", "asset_id", "posting_role",
    "quantity_decimal", "unit_price_decimal", "price_currency", "valuation_amount_decimal",
    "valuation_currency", "memo"
  )
}

.transaction_frame_row <- function(frame, columns, integer_columns = character()) {
  if (nrow(frame) != 1L) .transaction_abort("transaction_command_entity_not_found")
  row <- vector("list", length(columns))
  names(row) <- columns
  for (column in columns) {
    value <- frame[[column]][[1]]
    if (length(value) != 1L || is.na(value)) {
      row[column] <- list(NULL)
    } else if (column %in% integer_columns) {
      row[[column]] <- as.integer(value)
    } else {
      row[[column]] <- as.character(value)
    }
  }
  row
}

.transaction_frame_rows <- function(frame, columns, integer_columns = character()) {
  if (!nrow(frame)) return(list())
  lapply(seq_len(nrow(frame)), function(index) {
    .transaction_frame_row(frame[index, , drop = FALSE], columns, integer_columns)
  })
}

.transaction_fetch_record <- function(connection, transaction_id, required = TRUE) {
  columns <- .transaction_record_columns()
  frame <- DBI::dbGetQuery(
    connection,
    paste0("SELECT ", paste(columns, collapse = ", "), " FROM transaction_record WHERE transaction_id=?"),
    params = list(transaction_id)
  )
  if (!nrow(frame)) {
    if (required) .transaction_abort("transaction_command_entity_not_found")
    return(NULL)
  }
  if (nrow(frame) != 1L) .transaction_abort("transaction_command_integrity_invalid")
  .transaction_frame_row(frame, columns)
}

.transaction_fetch_postings <- function(connection, transaction_id) {
  columns <- .transaction_posting_columns()
  frame <- DBI::dbGetQuery(
    connection,
    paste0(
      "SELECT ", paste(columns, collapse = ", "),
      " FROM transaction_posting WHERE transaction_id=? ORDER BY sequence_no, posting_id"
    ),
    params = list(transaction_id)
  )
  .transaction_frame_rows(frame, columns, "sequence_no")
}

.transaction_content <- function(record, postings) {
  list(transaction_content_version = 1L, record = record, postings = postings)
}

.transaction_content_fingerprint <- function(record, postings) {
  .catalog_fingerprint(.transaction_content(record, postings))
}

.transaction_expected_bundle <- function(connection, command, context) {
  predecessor <- NULL
  if (command$action != "create") {
    predecessor <- .transaction_fetch_record(connection, command$supersedes_transaction_id)
  }
  portfolio_id <- if (command$action == "void") predecessor$portfolio_id else command$portfolio_id
  transaction_type <- if (command$action == "void") predecessor$transaction_type else .transaction_profile_type(command$transaction_profile)
  record <- list(
    transaction_id = command$transaction_id,
    portfolio_id = portfolio_id,
    transaction_type = transaction_type,
    record_action = if (command$action == "void") "void" else "book",
    effective_at_utc = command$effective_at_utc,
    local_date = command$local_date,
    memo = command$memo,
    supersedes_transaction_id = command$supersedes_transaction_id,
    origin_type = "native",
    origin_ref = NULL,
    created_at_utc = command$committed_at_utc,
    created_by_actor = context$actor_id
  )
  postings <- if (command$action == "void") list() else lapply(command$postings, function(posting) {
    list(
      posting_id = .transaction_posting_identity(command$transaction_id, posting$sequence_no),
      transaction_id = command$transaction_id,
      sequence_no = posting$sequence_no,
      account_id = posting$account_id,
      asset_id = posting$asset_id,
      posting_role = posting$posting_role,
      quantity_decimal = posting$quantity_decimal,
      unit_price_decimal = posting$unit_price_decimal,
      price_currency = posting$price_currency,
      valuation_amount_decimal = posting$valuation_amount_decimal,
      valuation_currency = posting$valuation_currency,
      memo = posting$memo
    )
  })
  fingerprint <- .transaction_content_fingerprint(record, postings)
  list(record = record, postings = postings, fingerprint = fingerprint)
}

.transaction_fetch_bundle <- function(connection, transaction_id) {
  record <- .transaction_fetch_record(connection, transaction_id)
  postings <- .transaction_fetch_postings(connection, transaction_id)
  seal_frame <- DBI::dbGetQuery(
    connection,
    "SELECT transaction_id, sealed_at_utc, posting_count, content_fingerprint FROM transaction_seal WHERE transaction_id=?",
    params = list(transaction_id)
  )
  if (nrow(seal_frame) != 1L) .transaction_abort("transaction_command_integrity_invalid")
  seal <- .transaction_frame_row(
    seal_frame,
    c("transaction_id", "sealed_at_utc", "posting_count", "content_fingerprint"),
    "posting_count"
  )
  fingerprint <- .transaction_content_fingerprint(record, postings)
  if (!identical(seal$transaction_id, transaction_id) || seal$posting_count != length(postings) ||
      !identical(seal$content_fingerprint, fingerprint) ||
      !identical(seal$sealed_at_utc, record$created_at_utc) ||
      (record$record_action == "book" && !length(postings)) ||
      (record$record_action == "void" && length(postings))) {
    .transaction_abort("transaction_command_integrity_invalid")
  }
  list(record = record, postings = postings, seal = seal, fingerprint = fingerprint)
}

.transaction_audit_for_entity <- function(connection, transaction_id) {
  DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref FROM data_command_audit",
      "WHERE area_id='transaction_ledger' AND entity_id=?",
      "ORDER BY command_id"
    ),
    params = list(transaction_id)
  )
}

.transaction_import_batch_command_id <- function(context, master_candidate_fingerprint, artifact_fingerprint) {
  paste0("cmd_txn_batch_", substr(.catalog_hash_parts(c(
    "legacy-transaction-import-v1", context$tenant_id, context$user_id,
    context$data_space_id, master_candidate_fingerprint, artifact_fingerprint
  )), 1L, 48L))
}

.transaction_import_run_id <- function(artifact_fingerprint) {
  paste0("timp_", substr(artifact_fingerprint, 1L, 24L))
}

.transaction_import_origin_namespace <- function(artifact_fingerprint) {
  paste0("ltr_", substr(artifact_fingerprint, 1L, 24L), "_")
}

.transaction_import_transaction_id <- function(context, batch_command_id, source_row_ref) {
  paste0("txn_", substr(.catalog_hash_parts(c(
    "legacy-transaction-row-v1", context$tenant_id, context$user_id,
    context$data_space_id, batch_command_id, source_row_ref
  )), 1L, 24L))
}

.transaction_import_row_command_id <- function(context, batch_command_id, transaction_id) {
  paste0("cmd_txn_import_", substr(.catalog_hash_parts(c(
    "legacy-transaction-row-command-v1", context$tenant_id, context$user_id,
    context$data_space_id, batch_command_id, transaction_id
  )), 1L, 44L))
}

.transaction_validate_native_transaction <- function(bundle, audit, transaction_id, context) {
  if (!identical(bundle$record$origin_type, "native") || !is.null(bundle$record$origin_ref) ||
      nrow(audit) != 1L) {
    .transaction_abort("transaction_command_provenance_invalid")
  }
  action_shape_valid <- switch(
    audit$command_type[[1]],
    transaction_create_v1 = identical(bundle$record$record_action, "book") &&
      is.null(bundle$record$supersedes_transaction_id),
    transaction_create_explicit_settlement_v1 = identical(bundle$record$record_action, "book") &&
      is.null(bundle$record$supersedes_transaction_id) && bundle$record$transaction_type %in% c("buy", "sell"),
    transaction_correct_v1 = identical(bundle$record$record_action, "book") &&
      !is.null(bundle$record$supersedes_transaction_id),
    transaction_correct_explicit_settlement_v1 = identical(bundle$record$record_action, "book") &&
      !is.null(bundle$record$supersedes_transaction_id) && bundle$record$transaction_type %in% c("buy", "sell"),
    transaction_void_v1 = identical(bundle$record$record_action, "void") &&
      !is.null(bundle$record$supersedes_transaction_id),
    transaction_import_correct_v1 = identical(bundle$record$record_action, "book") &&
      !is.null(bundle$record$supersedes_transaction_id),
    transaction_import_void_v1 = identical(bundle$record$record_action, "void") &&
      !is.null(bundle$record$supersedes_transaction_id),
    FALSE
  )
  if (!isTRUE(action_shape_valid) || !identical(audit$entity_id[[1]], transaction_id) ||
      !identical(audit$actor_id[[1]], context$actor_id) ||
      !identical(audit$committed_at_utc[[1]], bundle$record$created_at_utc) ||
      !identical(audit$payload_fingerprint[[1]], bundle$fingerprint) ||
      !identical(audit$origin_type[[1]], "native") || !is.na(audit$origin_ref[[1]])) {
    .transaction_abort("transaction_command_integrity_invalid")
  }
  bundle$ledger_semantics <- if (startsWith(audit$command_type[[1]], "transaction_import_")) {
    "imported_event_v1"
  } else if (audit$command_type[[1]] %in% c(
    "transaction_create_explicit_settlement_v1", "transaction_correct_explicit_settlement_v1"
  )) {
    "native_explicit_settlement_v1"
  } else {
    "native_transaction_v1"
  }
  bundle
}

.transaction_validate_imported_transaction <- function(connection, bundle, audit, transaction_id, context) {
  record <- bundle$record
  if (!identical(record$origin_type, "legacy_import") || is.null(record$origin_ref) ||
      !grepl("^ltr_[a-f0-9]{24}_[a-f0-9]{24}$", record$origin_ref) ||
      !is.null(record$supersedes_transaction_id) || !identical(record$record_action, "book") ||
      nrow(audit) != 1L || !identical(audit$command_type[[1]], "legacy_transaction_import_row_v1") ||
      !identical(audit$origin_type[[1]], "legacy_import") || is.na(audit$origin_ref[[1]])) {
    .transaction_abort("transaction_command_provenance_invalid")
  }
  batch <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref FROM data_command_audit WHERE command_id=?"
    ),
    params = list(audit$origin_ref[[1]])
  )
  if (nrow(batch) != 1L || !identical(batch$area_id[[1]], "canonical_import_receipt") ||
      !identical(batch$command_type[[1]], "legacy_transaction_import_v1") ||
      !identical(batch$entity_id[[1]], record$portfolio_id) ||
      !identical(batch$actor_id[[1]], context$actor_id) ||
      !identical(batch$committed_at_utc[[1]], record$created_at_utc) ||
      !identical(batch$origin_type[[1]], "legacy_import") || is.na(batch$origin_ref[[1]]) ||
      !grepl("^timp_[a-f0-9]{24}$", batch$origin_ref[[1]])) {
    .transaction_abort("transaction_command_provenance_invalid")
  }
  artifact_fingerprint <- batch$payload_fingerprint[[1]]
  master_receipt <- .catalog_master_receipt_v1(connection, context)
  expected_batch <- .transaction_import_batch_command_id(
    context, master_receipt$candidate_fingerprint, artifact_fingerprint
  )
  expected_namespace <- .transaction_import_origin_namespace(artifact_fingerprint)
  expected_row_command <- .transaction_import_row_command_id(context, expected_batch, transaction_id)
  if (!identical(batch$command_id[[1]], expected_batch) ||
      !identical(batch$origin_ref[[1]], .transaction_import_run_id(artifact_fingerprint)) ||
      !startsWith(record$origin_ref, expected_namespace) ||
      !identical(audit$command_id[[1]], expected_row_command) ||
      !identical(audit$entity_id[[1]], transaction_id) ||
      !identical(audit$actor_id[[1]], context$actor_id) ||
      !identical(audit$committed_at_utc[[1]], record$created_at_utc) ||
      !identical(audit$payload_fingerprint[[1]], bundle$fingerprint)) {
    .transaction_abort("transaction_command_integrity_invalid")
  }
  bundle$import_batch <- .transaction_frame_row(
    batch,
    c(
      "command_id", "area_id", "command_type", "entity_id", "actor_id", "committed_at_utc",
      "payload_fingerprint", "origin_type", "origin_ref"
    )
  )
  bundle$ledger_semantics <- "imported_event_v1"
  bundle
}

.transaction_validate_managed_transaction <- function(connection, transaction_id, context) {
  bundle <- .transaction_fetch_bundle(connection, transaction_id)
  audit <- .transaction_audit_for_entity(connection, transaction_id)
  if (identical(bundle$record$origin_type, "native")) {
    bundle <- .transaction_validate_native_transaction(bundle, audit, transaction_id, context)
  } else if (identical(bundle$record$origin_type, "legacy_import")) {
    bundle <- .transaction_validate_imported_transaction(connection, bundle, audit, transaction_id, context)
  } else {
    .transaction_abort("transaction_command_provenance_invalid")
  }
  bundle$audit <- .transaction_frame_row(
    audit,
    c(
      "command_id", "area_id", "command_type", "entity_id", "actor_id", "committed_at_utc",
      "payload_fingerprint", "origin_type", "origin_ref"
    )
  )
  bundle
}

.transaction_catalog_entity <- function(connection, entity_type, entity_id, context) {
  tryCatch(
    .catalog_validate_reference_entity(connection, entity_type, entity_id, context),
    spot_catalog_data_command_error = function(error) {
      mapping <- c(
        catalog_command_entity_not_found = "transaction_command_entity_not_found",
        catalog_command_entity_state_invalid = "transaction_command_entity_state_invalid",
        catalog_command_provenance_invalid = "transaction_command_provenance_invalid",
        catalog_command_integrity_invalid = "transaction_command_integrity_invalid"
      )
      code <- unname(mapping[[error$code]])
      .transaction_abort(if (is.null(code)) "transaction_command_entity_reference_invalid" else code)
    }
  )
}

.transaction_cash_value <- function(posting, account, asset, currency) {
  if (!account$account_type %in% c("cash", "bank", "external")) {
    .transaction_abort("transaction_command_account_invalid")
  }
  if (!identical(asset$asset_type, "cash") || !identical(asset$valuation_method, "unit_value")) {
    .transaction_abort("transaction_command_asset_invalid")
  }
  if (!identical(asset$price_currency, currency)) .transaction_abort("transaction_command_currency_invalid")
  if (!is.null(posting$unit_price_decimal) || !is.null(posting$price_currency) ||
      !identical(posting$valuation_currency, currency)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  quantity <- .transaction_decimal_parse(posting$quantity_decimal, allow_zero = FALSE)
  valuation <- .transaction_decimal_parse(posting$valuation_amount_decimal, allow_zero = FALSE)
  if (!.transaction_decimal_equal(quantity, valuation)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  if (quantity$scale > asset$quantity_scale) .transaction_abort("transaction_command_decimal_invalid")
  quantity
}

.transaction_resolve_posting <- function(connection, posting, portfolio_id, context, require_active = FALSE) {
  account <- .transaction_catalog_entity(connection, "account", posting$account_id, context)
  asset <- .transaction_catalog_entity(connection, "asset", posting$asset_id, context)
  if (!identical(account$portfolio_id, portfolio_id)) {
    .transaction_abort("transaction_command_entity_reference_invalid")
  }
  if (require_active && (!identical(account$status, "active") || !identical(asset$status, "active"))) {
    .transaction_abort("transaction_command_entity_state_invalid")
  }
  if (require_active && identical(asset$asset_type, "derivative")) {
    .transaction_abort("transaction_command_asset_invalid")
  }
  list(posting = posting, account = account, asset = asset)
}

.transaction_validate_trade <- function(connection, bundle, portfolio, context, lots) {
  record <- bundle$record
  postings <- bundle$postings
  roles <- vapply(postings, function(posting) posting$posting_role, character(1))
  fee_present <- "fee" %in% roles
  tax_present <- "tax" %in% roles
  expected <- c("asset", "cash", if (fee_present) "fee", if (tax_present) "tax")
  if (!identical(roles, expected) || sum(roles == "asset") != 1L || sum(roles == "cash") != 1L ||
      sum(roles == "fee") > 1L || sum(roles == "tax") > 1L ||
      (record$transaction_type == "buy" && tax_present)) {
    .transaction_abort("transaction_command_posting_role_invalid")
  }
  resolved <- lapply(postings, function(posting) {
    .transaction_resolve_posting(connection, posting, record$portfolio_id, context)
  })
  asset_entry <- resolved[[1]]
  cash_entry <- resolved[[2]]
  if (!asset_entry$account$account_type %in% c("securities", "crypto_wallet")) {
    .transaction_abort("transaction_command_account_invalid")
  }
  if (identical(asset_entry$asset$asset_type, "cash")) .transaction_abort("transaction_command_asset_invalid")
  currency <- portfolio$base_currency
  if (!identical(asset_entry$asset$price_currency, currency) ||
      !identical(asset_entry$posting$price_currency, currency) ||
      !identical(asset_entry$posting$valuation_currency, currency)) {
    .transaction_abort("transaction_command_currency_invalid")
  }
  quantity <- .transaction_decimal_parse(asset_entry$posting$quantity_decimal, allow_zero = FALSE)
  if (quantity$scale > asset_entry$asset$quantity_scale) .transaction_abort("transaction_command_decimal_invalid")
  price <- .transaction_decimal_parse(asset_entry$posting$unit_price_decimal, allow_zero = FALSE, positive_only = TRUE)
  valuation <- .transaction_decimal_parse(asset_entry$posting$valuation_amount_decimal, allow_zero = FALSE)
  if (!.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), valuation)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  if ((record$transaction_type == "buy" && quantity$sign != 1L) ||
      (record$transaction_type == "sell" && quantity$sign != -1L)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  gross_cash <- .transaction_cash_value(cash_entry$posting, cash_entry$account, cash_entry$asset, currency)
  if (!cash_entry$account$account_type %in% c("cash", "bank") ||
      !bundle$ledger_semantics %in% c("native_transaction_v1", "native_explicit_settlement_v1") ||
      (identical(bundle$ledger_semantics, "native_transaction_v1") &&
       !.transaction_decimal_equal(gross_cash, .transaction_decimal_negate(valuation))) ||
      (identical(bundle$ledger_semantics, "native_explicit_settlement_v1") &&
       ((record$transaction_type == "buy" && gross_cash$sign != -1L) ||
        (record$transaction_type == "sell" && gross_cash$sign != 1L)))) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  if (length(resolved) > 2L) {
    for (index in 3:length(resolved)) {
      component <- resolved[[index]]
      if (!identical(component$posting$account_id, cash_entry$posting$account_id) ||
          !identical(component$posting$asset_id, cash_entry$posting$asset_id)) {
        .transaction_abort("transaction_command_account_invalid")
      }
      value <- .transaction_cash_value(component$posting, component$account, component$asset, currency)
      if (value$sign != -1L) .transaction_abort("transaction_command_valuation_invalid")
    }
  }
  key <- paste(record$portfolio_id, asset_entry$posting$account_id, asset_entry$posting$asset_id, sep = "|")
  existing <- if (exists(key, envir = lots, inherits = FALSE)) get(key, envir = lots) else list()
  if (record$transaction_type == "buy") {
    existing[[length(existing) + 1L]] <- quantity
    assign(key, existing, envir = lots)
    return(invisible(TRUE))
  }
  remaining <- .transaction_decimal_abs(quantity)
  while (remaining$sign != 0L) {
    if (!length(existing)) .transaction_abort("transaction_command_fifo_inventory_insufficient")
    lot <- existing[[1]]
    comparison <- .transaction_decimal_compare(lot, remaining)
    if (comparison <= 0L) {
      remaining <- .transaction_decimal_subtract(remaining, lot)
      existing <- existing[-1L]
    } else {
      existing[[1]] <- .transaction_decimal_subtract(lot, remaining)
      remaining <- .transaction_decimal_zero()
    }
  }
  assign(key, existing, envir = lots)
  invisible(TRUE)
}

.transaction_validate_cash_movement <- function(connection, bundle, portfolio, context) {
  record <- bundle$record
  postings <- bundle$postings
  roles <- vapply(postings, function(posting) posting$posting_role, character(1))
  base_roles <- if (record$transaction_type == "transfer") c("transfer", "transfer") else c("cash", "transfer")
  expected <- c(base_roles, if (length(postings) == 3L) "fee")
  if (!length(postings) %in% c(2L, 3L) || !identical(roles, expected)) {
    .transaction_abort("transaction_command_posting_role_invalid")
  }
  resolved <- lapply(postings, function(posting) {
    .transaction_resolve_posting(connection, posting, record$portfolio_id, context)
  })
  currency <- portfolio$base_currency
  values <- lapply(resolved, function(entry) {
    .transaction_cash_value(entry$posting, entry$account, entry$asset, currency)
  })
  if (!identical(resolved[[1]]$posting$asset_id, resolved[[2]]$posting$asset_id) ||
      !.transaction_decimal_equal(
        .transaction_decimal_add(values[[1]], values[[2]]), .transaction_decimal_zero()
      )) {
    .transaction_abort("transaction_command_principal_conservation_invalid")
  }
  internal <- c("cash", "bank")
  if (record$transaction_type == "deposit") {
    valid_accounts <- resolved[[1]]$account$account_type %in% internal && resolved[[2]]$account$account_type == "external"
    valid_signs <- values[[1]]$sign == 1L && values[[2]]$sign == -1L
  } else if (record$transaction_type == "withdrawal") {
    valid_accounts <- resolved[[1]]$account$account_type %in% internal && resolved[[2]]$account$account_type == "external"
    valid_signs <- values[[1]]$sign == -1L && values[[2]]$sign == 1L
  } else {
    valid_accounts <- resolved[[1]]$account$account_type %in% internal &&
      resolved[[2]]$account$account_type %in% internal &&
      !identical(resolved[[1]]$posting$account_id, resolved[[2]]$posting$account_id)
    valid_signs <- values[[1]]$sign == -1L && values[[2]]$sign == 1L
  }
  if (!valid_accounts) .transaction_abort("transaction_command_account_invalid")
  if (!valid_signs) .transaction_abort("transaction_command_principal_conservation_invalid")
  if (length(resolved) == 3L) {
    fee <- resolved[[3]]
    if (!identical(fee$posting$account_id, resolved[[1]]$posting$account_id) ||
        !identical(fee$posting$asset_id, resolved[[1]]$posting$asset_id) ||
        !fee$account$account_type %in% internal || values[[3]]$sign != -1L) {
      .transaction_abort("transaction_command_account_invalid")
    }
  }
  invisible(TRUE)
}

.transaction_validate_split_cash_trade <- function(connection, bundle, portfolio, context, lots) {
  record <- bundle$record
  postings <- bundle$postings
  if (!record$transaction_type %in% c("buy", "sell") || length(postings) != 1L ||
      !identical(postings[[1L]]$posting_role, "asset")) {
    .transaction_abort("transaction_command_posting_role_invalid")
  }
  entry <- .transaction_resolve_posting(connection, postings[[1L]], record$portfolio_id, context)
  if (!entry$account$account_type %in% c("securities", "crypto_wallet") ||
      identical(entry$asset$asset_type, "cash") || identical(entry$asset$asset_type, "derivative")) {
    .transaction_abort("transaction_command_asset_invalid")
  }
  currency <- portfolio$base_currency
  posting <- entry$posting
  if (!identical(entry$asset$price_currency, currency) ||
      !identical(posting$price_currency, currency) ||
      !identical(posting$valuation_currency, currency)) {
    .transaction_abort("transaction_command_currency_invalid")
  }
  quantity <- .transaction_decimal_parse(posting$quantity_decimal, allow_zero = FALSE)
  price <- .transaction_decimal_parse(posting$unit_price_decimal, allow_zero = FALSE, positive_only = TRUE)
  valuation <- .transaction_decimal_parse(posting$valuation_amount_decimal, allow_zero = FALSE)
  if (quantity$scale > entry$asset$quantity_scale ||
      !.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), valuation) ||
      (record$transaction_type == "buy" && quantity$sign != 1L) ||
      (record$transaction_type == "sell" && quantity$sign != -1L)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  key <- paste(record$portfolio_id, posting$account_id, posting$asset_id, sep = "|")
  existing <- if (exists(key, envir = lots, inherits = FALSE)) get(key, envir = lots) else list()
  if (record$transaction_type == "buy") {
    existing[[length(existing) + 1L]] <- quantity
    assign(key, existing, envir = lots)
    return(invisible(TRUE))
  }
  remaining <- .transaction_decimal_abs(quantity)
  while (remaining$sign != 0L) {
    if (!length(existing)) .transaction_abort("transaction_command_fifo_inventory_insufficient")
    lot <- existing[[1L]]
    comparison <- .transaction_decimal_compare(lot, remaining)
    if (comparison <= 0L) {
      remaining <- .transaction_decimal_subtract(remaining, lot)
      existing <- existing[-1L]
    } else {
      existing[[1L]] <- .transaction_decimal_subtract(lot, remaining)
      remaining <- .transaction_decimal_zero()
    }
  }
  assign(key, existing, envir = lots)
  invisible(TRUE)
}

.transaction_fifo_consume_quantities <- function(lots, key, quantity) {
  existing <- if (exists(key, envir = lots, inherits = FALSE)) get(key, envir = lots) else list()
  remaining <- quantity
  consumed <- list()
  while (remaining$sign != 0L) {
    if (!length(existing)) .transaction_abort("transaction_command_fifo_inventory_insufficient")
    lot <- existing[[1L]]
    comparison <- .transaction_decimal_compare(lot, remaining)
    if (comparison <= 0L) {
      consumed[[length(consumed) + 1L]] <- lot
      remaining <- .transaction_decimal_subtract(remaining, lot)
      existing <- existing[-1L]
    } else {
      consumed[[length(consumed) + 1L]] <- remaining
      existing[[1L]] <- .transaction_decimal_subtract(lot, remaining)
      remaining <- .transaction_decimal_zero()
    }
  }
  assign(key, existing, envir = lots)
  consumed
}

.transaction_validate_imported_reward <- function(connection, bundle, portfolio, context, lots) {
  record <- bundle$record
  postings <- bundle$postings
  roles <- vapply(postings, function(posting) posting$posting_role, character(1))
  expected <- c("income", if (length(postings) == 2L) "fee")
  if (!length(postings) %in% c(1L, 2L) || !identical(roles, expected)) {
    .transaction_abort("transaction_command_posting_role_invalid")
  }
  resolved <- lapply(postings, function(posting) {
    .transaction_resolve_posting(connection, posting, record$portfolio_id, context)
  })
  income <- resolved[[1L]]
  if (!income$account$account_type %in% c("crypto_wallet", "securities", "other") ||
      !identical(income$asset$asset_type, "crypto") ||
      !identical(income$asset$price_currency, portfolio$base_currency) ||
      !identical(income$posting$price_currency, portfolio$base_currency) ||
      !identical(income$posting$valuation_currency, portfolio$base_currency)) {
    .transaction_abort("transaction_command_asset_invalid")
  }
  quantity <- .transaction_decimal_parse(income$posting$quantity_decimal, allow_zero = FALSE)
  price <- .transaction_decimal_parse(
    income$posting$unit_price_decimal, allow_zero = FALSE, positive_only = TRUE
  )
  valuation <- .transaction_decimal_parse(income$posting$valuation_amount_decimal, allow_zero = FALSE)
  if (quantity$sign != 1L || quantity$scale > income$asset$quantity_scale ||
      !.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), valuation)) {
    .transaction_abort("transaction_command_valuation_invalid")
  }
  key <- paste(record$portfolio_id, income$posting$account_id, income$posting$asset_id, sep = "|")
  existing <- if (exists(key, envir = lots, inherits = FALSE)) get(key, envir = lots) else list()
  existing[[length(existing) + 1L]] <- quantity
  assign(key, existing, envir = lots)
  if (length(resolved) == 2L) {
    fee <- resolved[[2L]]
    if (!identical(fee$posting$account_id, income$posting$account_id) ||
        !identical(fee$posting$asset_id, income$posting$asset_id) ||
        !identical(fee$posting$unit_price_decimal, income$posting$unit_price_decimal) ||
        !identical(fee$posting$price_currency, income$posting$price_currency) ||
        !identical(fee$posting$valuation_currency, income$posting$valuation_currency)) {
      .transaction_abort("transaction_command_account_invalid")
    }
    fee_quantity <- .transaction_decimal_parse(fee$posting$quantity_decimal, allow_zero = FALSE)
    fee_valuation <- .transaction_decimal_parse(fee$posting$valuation_amount_decimal, allow_zero = FALSE)
    if (fee_quantity$sign != -1L || fee_quantity$scale > income$asset$quantity_scale ||
        !.transaction_decimal_equal(.transaction_decimal_multiply(fee_quantity, price), fee_valuation)) {
      .transaction_abort("transaction_command_valuation_invalid")
    }
    invisible(.transaction_fifo_consume_quantities(
      lots, key, .transaction_decimal_abs(fee_quantity)
    ))
  }
  invisible(TRUE)
}

.transaction_imported_movement_value <- function(entry, portfolio_currency) {
  posting <- entry$posting
  asset <- entry$asset
  quantity <- .transaction_decimal_parse(posting$quantity_decimal, allow_zero = FALSE)
  valuation <- .transaction_decimal_parse(posting$valuation_amount_decimal, allow_zero = FALSE)
  if (!identical(posting$valuation_currency, portfolio_currency) ||
      !identical(asset$price_currency, portfolio_currency) ||
      quantity$scale > asset$quantity_scale) {
    .transaction_abort("transaction_command_currency_invalid")
  }
  if (is.null(posting$unit_price_decimal)) {
    if (!is.null(posting$price_currency) || !identical(asset$asset_type, "cash") ||
        !.transaction_decimal_equal(quantity, valuation)) {
      .transaction_abort("transaction_command_valuation_invalid")
    }
  } else {
    if (!identical(posting$price_currency, portfolio_currency)) {
      .transaction_abort("transaction_command_currency_invalid")
    }
    price <- .transaction_decimal_parse(posting$unit_price_decimal, allow_zero = FALSE, positive_only = TRUE)
    if (!.transaction_decimal_equal(.transaction_decimal_multiply(quantity, price), valuation)) {
      .transaction_abort("transaction_command_valuation_invalid")
    }
  }
  quantity
}

.transaction_validate_imported_movement <- function(connection, bundle, portfolio, context, lots) {
  record <- bundle$record
  postings <- bundle$postings
  roles <- vapply(postings, function(posting) posting$posting_role, character(1))
  principal_count <- if (identical(record$transaction_type, "transfer")) 2L else 1L
  expected <- c(rep("transfer", principal_count), if (length(postings) == principal_count + 1L) "fee")
  if (!length(postings) %in% c(principal_count, principal_count + 1L) ||
      !identical(roles, expected)) {
    .transaction_abort("transaction_command_posting_role_invalid")
  }
  resolved <- lapply(postings, function(posting) {
    .transaction_resolve_posting(connection, posting, record$portfolio_id, context)
  })
  principal <- resolved[seq_len(principal_count)]
  first <- principal[[1L]]
  if (identical(first$asset$asset_type, "derivative")) {
    .transaction_abort("transaction_command_asset_invalid")
  }
  compatible <- if (identical(first$asset$asset_type, "cash")) {
    c("cash", "bank", "securities", "other")
  } else if (identical(first$asset$asset_type, "crypto")) {
    c("crypto_wallet", "securities", "other")
  } else {
    c("securities", "other")
  }
  if (any(vapply(principal, function(entry) {
    !identical(entry$posting$asset_id, first$posting$asset_id) ||
      !entry$account$account_type %in% compatible
  }, logical(1)))) {
    .transaction_abort("transaction_command_account_invalid")
  }
  values <- lapply(principal, .transaction_imported_movement_value, portfolio_currency = portfolio$base_currency)
  if (identical(record$transaction_type, "deposit")) {
    if (values[[1L]]$sign != 1L || !identical(first$asset$asset_type, "cash")) {
      .transaction_abort("transaction_command_principal_conservation_invalid")
    }
  } else if (identical(record$transaction_type, "withdrawal")) {
    if (values[[1L]]$sign != -1L) {
      .transaction_abort("transaction_command_principal_conservation_invalid")
    }
  } else if (values[[1L]]$sign != -1L || values[[2L]]$sign != 1L ||
             identical(principal[[1L]]$posting$account_id, principal[[2L]]$posting$account_id) ||
             !.transaction_decimal_equal(
               .transaction_decimal_add(values[[1L]], values[[2L]]), .transaction_decimal_zero()
             )) {
    .transaction_abort("transaction_command_principal_conservation_invalid")
  }
  if (!identical(first$asset$asset_type, "cash")) {
    source <- if (identical(record$transaction_type, "transfer")) principal[[1L]] else first
    source_key <- paste(record$portfolio_id, source$posting$account_id, source$posting$asset_id, sep = "|")
    if (identical(record$transaction_type, "withdrawal")) {
      invisible(.transaction_fifo_consume_quantities(lots, source_key, .transaction_decimal_abs(values[[1L]])))
    } else if (identical(record$transaction_type, "transfer")) {
      chunks <- .transaction_fifo_consume_quantities(lots, source_key, .transaction_decimal_abs(values[[1L]]))
      destination_key <- paste(
        record$portfolio_id, principal[[2L]]$posting$account_id,
        principal[[2L]]$posting$asset_id, sep = "|"
      )
      destination <- if (exists(destination_key, envir = lots, inherits = FALSE)) {
        get(destination_key, envir = lots)
      } else list()
      assign(destination_key, c(destination, chunks), envir = lots)
    }
  }
  if (length(resolved) == principal_count + 1L) {
    fee <- resolved[[principal_count + 1L]]
    owner <- principal[[1L]]
    if (!identical(fee$posting$account_id, owner$posting$account_id) ||
        !identical(fee$posting$asset_id, owner$posting$asset_id)) {
      .transaction_abort("transaction_command_account_invalid")
    }
    fee_value <- .transaction_imported_movement_value(fee, portfolio$base_currency)
    if (fee_value$sign != -1L) .transaction_abort("transaction_command_valuation_invalid")
    if (!identical(first$asset$asset_type, "cash")) {
      key <- paste(record$portfolio_id, fee$posting$account_id, fee$posting$asset_id, sep = "|")
      invisible(.transaction_fifo_consume_quantities(lots, key, .transaction_decimal_abs(fee_value)))
    }
  }
  invisible(TRUE)
}

.transaction_validate_current_ledger <- function(connection, portfolio_id, context) {
  portfolio <- .transaction_catalog_entity(connection, "portfolio", portfolio_id, context)
  records <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT transaction_id FROM current_transaction WHERE portfolio_id=?",
      "ORDER BY effective_at_utc, transaction_id"
    ),
    params = list(portfolio_id)
  )$transaction_id
  lots <- new.env(hash = TRUE, parent = emptyenv())
  for (transaction_id in records) {
    bundle <- .transaction_validate_managed_transaction(connection, transaction_id, context)
    record <- bundle$record
    if (!identical(record$record_action, "book")) .transaction_abort("transaction_command_integrity_invalid")
    sequences <- vapply(bundle$postings, function(posting) posting$sequence_no, integer(1))
    if (!identical(sequences, seq_along(bundle$postings))) {
      .transaction_abort("transaction_command_posting_sequence_invalid")
    }
    if (identical(bundle$ledger_semantics, "imported_event_v1")) {
      if (record$transaction_type %in% c("buy", "sell")) {
        .transaction_validate_split_cash_trade(connection, bundle, portfolio, context, lots)
      } else if (record$transaction_type %in% c("deposit", "withdrawal", "transfer")) {
        .transaction_validate_imported_movement(connection, bundle, portfolio, context, lots)
      } else if (identical(record$transaction_type, "reward")) {
        .transaction_validate_imported_reward(connection, bundle, portfolio, context, lots)
      } else {
        .transaction_abort("transaction_command_profile_unsupported")
      }
    } else if (record$transaction_type %in% c("buy", "sell")) {
      .transaction_validate_trade(connection, bundle, portfolio, context, lots)
    } else if (record$transaction_type %in% c("deposit", "withdrawal", "transfer")) {
      .transaction_validate_cash_movement(connection, bundle, portfolio, context)
    } else {
      .transaction_abort("transaction_command_profile_unsupported")
    }
  }
  invisible(TRUE)
}

.transaction_existing_command <- function(connection, command, context) {
  audit <- DBI::dbGetQuery(
    connection,
    paste(
      "SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,",
      "payload_fingerprint, origin_type, origin_ref FROM data_command_audit WHERE command_id=?"
    ),
    params = list(command$command_id)
  )
  if (!nrow(audit)) return(NULL)
  if (nrow(audit) != 1L) .transaction_abort("transaction_command_integrity_invalid")
  expected <- tryCatch(
    .transaction_expected_bundle(connection, command, context),
    spot_transaction_data_command_error = function(error) {
      .transaction_abort("transaction_command_idempotency_conflict")
    }
  )
  actual <- tryCatch(
    .transaction_fetch_bundle(connection, command$transaction_id),
    spot_transaction_data_command_error = function(error) {
      .transaction_abort("transaction_command_idempotency_conflict")
    }
  )
  valid <- identical(actual$record, expected$record) && identical(actual$postings, expected$postings) &&
    identical(actual$fingerprint, expected$fingerprint) &&
    identical(audit$area_id[[1]], "transaction_ledger") &&
    identical(audit$command_type[[1]], command$command_type) &&
    identical(audit$entity_id[[1]], command$transaction_id) &&
    identical(audit$actor_id[[1]], context$actor_id) &&
    identical(audit$committed_at_utc[[1]], command$committed_at_utc) &&
    identical(audit$payload_fingerprint[[1]], expected$fingerprint) &&
    identical(audit$origin_type[[1]], "native") && is.na(audit$origin_ref[[1]])
  if (!valid) .transaction_abort("transaction_command_idempotency_conflict")
  expected
}

.transaction_preconditions <- function(connection, command, context) {
  predecessor <- NULL
  portfolio_id <- command$portfolio_id
  if (command$action != "create") {
    predecessor <- .transaction_validate_managed_transaction(
      connection, command$supersedes_transaction_id, context
    )
    import_bridge_command <- command$command_type %in% c(
      "transaction_import_correct_v1", "transaction_import_void_v1"
    )
    imported_lineage <- identical(predecessor$ledger_semantics, "imported_event_v1")
    if (!identical(import_bridge_command, imported_lineage) ||
        (import_bridge_command && command$action == "correct" &&
         !command$transaction_profile %in% c(
           "buy", "sell", "deposit", "withdrawal", "internal_transfer", "reward"
         ))) {
      .transaction_abort("transaction_command_provenance_invalid")
    }
    if (!identical(predecessor$record$record_action, "book")) {
      .transaction_abort("transaction_command_entity_state_invalid")
    }
    successor_count <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT count(*) AS n FROM transaction_record successor",
        "JOIN transaction_seal seal ON seal.transaction_id=successor.transaction_id",
        "WHERE successor.supersedes_transaction_id=?"
      ),
      params = list(command$supersedes_transaction_id)
    )$n[[1]]
    if (successor_count != 0L) .transaction_abort("transaction_command_supersession_conflict")
    portfolio_id <- predecessor$record$portfolio_id
    if (command$action == "correct" && !identical(command$portfolio_id, portfolio_id)) {
      .transaction_abort("transaction_command_entity_reference_invalid")
    }
    if (!.catalog_time_later(command$committed_at_utc, predecessor$record$created_at_utc)) {
      .transaction_abort("transaction_command_input_invalid")
    }
  }
  portfolio <- .transaction_catalog_entity(connection, "portfolio", portfolio_id, context)
  if (!identical(portfolio$status, "active")) .transaction_abort("transaction_command_entity_state_invalid")
  if (!is.null(.transaction_fetch_record(connection, command$transaction_id, required = FALSE))) {
    .transaction_abort("transaction_command_duplicate_conflict")
  }
  if (command$action != "void") {
    for (posting in command$postings) {
      invisible(.transaction_resolve_posting(connection, posting, portfolio_id, context, require_active = TRUE))
    }
  }
  list(predecessor = predecessor, portfolio_id = portfolio_id)
}

.transaction_result <- function(command, status, bundle) {
  list(
    transaction_command_contract_version = 1L,
    status = status,
    action = command$action,
    command_type = command$command_type,
    command_id = command$command_id,
    transaction_profile = command$transaction_profile,
    transaction_id = command$transaction_id,
    supersedes_transaction_id = command$supersedes_transaction_id,
    record_action = bundle$record$record_action,
    posting_count = length(bundle$postings),
    content_fingerprint = bundle$fingerprint,
    committed_at_utc = command$committed_at_utc
  )
}

.transaction_connect_write <- function(context) {
  tryCatch(
    .catalog_connect_write(context),
    spot_catalog_data_command_error = function(error) .transaction_abort("transaction_command_repository_invalid")
  )
}

.transaction_execute_impl_v1 <- function(
  context,
  command,
  failpoint = "none",
  caller_connection = NULL
) {
  .transaction_context_check(context)
  if (!is.null(caller_connection)) .transaction_abort("transaction_command_caller_transaction_rejected")
  if (!inherits(command, "spot_transaction_command_v1") ||
      !identical(command$transaction_command_contract_version, 1L) ||
      !failpoint %in% c("none", "after_record", "after_postings", "after_audit", "before_commit")) {
    .transaction_abort("transaction_command_input_invalid")
  }

  read_connection <- .catalog_connect_read(context)
  replay <- tryCatch(.transaction_existing_command(read_connection, command, context), error = function(error) error)
  DBI::dbDisconnect(read_connection)
  if (inherits(replay, "error")) stop(replay)
  if (!is.null(replay)) return(.transaction_result(command, "already_committed", replay))

  lock <- tryCatch(
    .canonical_acquire_lock(runtime_data_space_path(context)),
    spot_canonical_repository_error = function(error) NULL
  )
  if (is.null(lock)) .transaction_abort("transaction_command_lock_unavailable")
  on.exit(unlink(lock, recursive = TRUE, force = TRUE), add = TRUE)
  connection <- .transaction_connect_write(context)
  on.exit(if (DBI::dbIsValid(connection)) DBI::dbDisconnect(connection), add = TRUE)
  began <- FALSE
  result <- tryCatch({
    begin_error <- tryCatch({
      DBI::dbExecute(connection, "BEGIN IMMEDIATE")
      NULL
    }, error = function(error) error)
    if (!is.null(begin_error)) .transaction_abort("transaction_command_lock_unavailable")
    began <- TRUE
    replay_locked <- .transaction_existing_command(connection, command, context)
    if (!is.null(replay_locked)) {
      DBI::dbExecute(connection, "ROLLBACK")
      began <- FALSE
      return(.transaction_result(command, "already_committed", replay_locked))
    }
    preconditions <- .transaction_preconditions(connection, command, context)
    bundle <- .transaction_expected_bundle(connection, command, context)
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO transaction_record",
        "(transaction_id, portfolio_id, transaction_type, record_action, effective_at_utc, local_date, memo,",
        "supersedes_transaction_id, origin_type, origin_ref, created_at_utc, created_by_actor)",
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'native', NULL, ?, ?)"
      ),
      params = list(
        bundle$record$transaction_id, bundle$record$portfolio_id, bundle$record$transaction_type,
        bundle$record$record_action, bundle$record$effective_at_utc, bundle$record$local_date,
        if (is.null(bundle$record$memo)) NA_character_ else bundle$record$memo,
        if (is.null(bundle$record$supersedes_transaction_id)) NA_character_ else bundle$record$supersedes_transaction_id,
        bundle$record$created_at_utc, bundle$record$created_by_actor
      )
    )
    if (failpoint == "after_record") stop("synthetic_transaction_failpoint", call. = FALSE)
    for (posting in bundle$postings) {
      DBI::dbExecute(
        connection,
        paste(
          "INSERT INTO transaction_posting",
          "(posting_id, transaction_id, sequence_no, account_id, asset_id, posting_role, quantity_decimal,",
          "unit_price_decimal, price_currency, valuation_amount_decimal, valuation_currency, memo)",
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        params = list(
          posting$posting_id, posting$transaction_id, posting$sequence_no, posting$account_id,
          posting$asset_id, posting$posting_role, posting$quantity_decimal,
          if (is.null(posting$unit_price_decimal)) NA_character_ else posting$unit_price_decimal,
          if (is.null(posting$price_currency)) NA_character_ else posting$price_currency,
          posting$valuation_amount_decimal, posting$valuation_currency,
          if (is.null(posting$memo)) NA_character_ else posting$memo
        )
      )
    }
    if (failpoint == "after_postings") stop("synthetic_transaction_failpoint", call. = FALSE)
    DBI::dbExecute(
      connection,
      "INSERT INTO transaction_seal VALUES (?, ?, ?, ?)",
      params = list(command$transaction_id, command$committed_at_utc, length(bundle$postings), bundle$fingerprint)
    )
    DBI::dbExecute(
      connection,
      paste(
        "INSERT INTO data_command_audit",
        "(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc, payload_fingerprint, origin_type, origin_ref)",
        "VALUES (?, 'transaction_ledger', ?, ?, ?, ?, ?, 'native', NULL)"
      ),
      params = list(
        command$command_id, command$command_type, command$transaction_id,
        context$actor_id, command$committed_at_utc, bundle$fingerprint
      )
    )
    if (failpoint == "after_audit") stop("synthetic_transaction_failpoint", call. = FALSE)
    validated <- .transaction_validate_managed_transaction(connection, command$transaction_id, context)
    if (!identical(validated$fingerprint, bundle$fingerprint)) {
      .transaction_abort("transaction_command_integrity_invalid")
    }
    .transaction_validate_current_ledger(connection, preconditions$portfolio_id, context)
    if (nrow(DBI::dbGetQuery(connection, "PRAGMA foreign_key_check")) != 0L ||
        !identical(DBI::dbGetQuery(connection, "PRAGMA integrity_check")[[1]], "ok")) {
      .transaction_abort("transaction_command_integrity_invalid")
    }
    if (failpoint == "before_commit") stop("synthetic_transaction_failpoint", call. = FALSE)
    DBI::dbExecute(connection, "COMMIT")
    began <- FALSE
    .transaction_result(command, "committed", bundle)
  }, error = function(error) {
    if (began && DBI::dbIsValid(connection)) try(DBI::dbExecute(connection, "ROLLBACK"), silent = TRUE)
    began <- FALSE
    if (inherits(error, "spot_transaction_data_command_error")) stop(error)
    .transaction_abort("transaction_command_transaction_failed")
  })
  result
}

.transaction_execute_public <- function(context, command) {
  .transaction_boundary_eval(
    .transaction_execute_impl_v1(context, command),
    fallback = "transaction_command_transaction_failed"
  )
}

transaction_create_v1 <- function(
  context,
  command_token,
  portfolio_id,
  transaction_profile,
  effective_at_utc,
  local_date,
  committed_at_utc,
  postings,
  memo = NULL,
  settlement_mode = NULL
) {
  .transaction_boundary_eval({
    if (!is.character(transaction_profile) || length(transaction_profile) != 1L ||
        is.na(transaction_profile) ||
        !transaction_profile %in% c("buy", "sell", "deposit", "withdrawal", "internal_transfer")) {
      .transaction_abort("transaction_command_profile_unsupported")
    }
    command <- .transaction_build_command(
      context, "create", command_token, portfolio_id, transaction_profile,
      effective_at_utc, local_date, committed_at_utc, postings, memo, settlement_mode = settlement_mode
    )
    .transaction_execute_public(context, command)
  })
}

transaction_correct_v1 <- function(
  context,
  command_token,
  supersedes_transaction_id,
  portfolio_id,
  transaction_profile,
  effective_at_utc,
  local_date,
  committed_at_utc,
  postings,
  memo = NULL,
  settlement_mode = NULL
) {
  .transaction_boundary_eval({
    if (!is.character(transaction_profile) || length(transaction_profile) != 1L ||
        is.na(transaction_profile) ||
        !transaction_profile %in% c("buy", "sell", "deposit", "withdrawal", "internal_transfer")) {
      .transaction_abort("transaction_command_profile_unsupported")
    }
    command <- .transaction_build_command(
      context, "correct", command_token, portfolio_id, transaction_profile,
      effective_at_utc, local_date, committed_at_utc, postings, memo,
      supersedes_transaction_id, settlement_mode
    )
    .transaction_execute_public(context, command)
  })
}

transaction_void_v1 <- function(
  context,
  command_token,
  supersedes_transaction_id,
  effective_at_utc,
  local_date,
  committed_at_utc,
  memo = NULL
) {
  .transaction_boundary_eval({
    command <- .transaction_build_command(
      context, "void", command_token, NULL, NULL,
      effective_at_utc, local_date, committed_at_utc, list(), memo,
      supersedes_transaction_id
    )
    .transaction_execute_public(context, command)
  })
}

transaction_import_correct_v1 <- function(
  context,
  command_token,
  supersedes_transaction_id,
  portfolio_id,
  transaction_profile,
  effective_at_utc,
  local_date,
  committed_at_utc,
  postings,
  memo = NULL
) {
  .transaction_boundary_eval({
    if (!is.character(transaction_profile) || length(transaction_profile) != 1L ||
        is.na(transaction_profile) || !transaction_profile %in% c(
          "buy", "sell", "deposit", "withdrawal", "internal_transfer", "reward"
        )) {
      .transaction_abort("transaction_command_profile_unsupported")
    }
    command <- .transaction_build_command(
      context, "correct", command_token, portfolio_id, transaction_profile,
      effective_at_utc, local_date, committed_at_utc, postings, memo,
      supersedes_transaction_id
    )
    command$command_type <- "transaction_import_correct_v1"
    .transaction_execute_public(context, command)
  })
}

transaction_import_void_v1 <- function(
  context,
  command_token,
  supersedes_transaction_id,
  effective_at_utc,
  local_date,
  committed_at_utc,
  memo = NULL
) {
  .transaction_boundary_eval({
    command <- .transaction_build_command(
      context, "void", command_token, NULL, NULL,
      effective_at_utc, local_date, committed_at_utc, list(), memo,
      supersedes_transaction_id
    )
    command$command_type <- "transaction_import_void_v1"
    .transaction_execute_public(context, command)
  })
}

transaction_read_history_v1 <- function(context, portfolio_id) {
  .transaction_boundary_eval({
    .transaction_context_check(context)
    if (!.transaction_id_valid(portfolio_id, "ptf_")) .transaction_abort("transaction_command_input_invalid")
    connection <- .catalog_connect_read(context)
    on.exit(DBI::dbDisconnect(connection), add = TRUE)
    invisible(.transaction_catalog_entity(connection, "portfolio", portfolio_id, context))
    transaction_ids <- DBI::dbGetQuery(
      connection,
      paste(
        "SELECT transaction_id FROM transaction_record WHERE portfolio_id=?",
        "ORDER BY created_at_utc, transaction_id"
      ),
      params = list(portfolio_id)
    )$transaction_id
    current_ids <- DBI::dbGetQuery(
      connection,
      "SELECT transaction_id FROM current_transaction WHERE portfolio_id=?",
      params = list(portfolio_id)
    )$transaction_id
    .transaction_validate_current_ledger(connection, portfolio_id, context)
    entries <- lapply(transaction_ids, function(transaction_id) {
      bundle <- .transaction_validate_managed_transaction(connection, transaction_id, context)
      list(
        record = bundle$record,
        postings = bundle$postings,
        seal = bundle$seal,
        audit = bundle$audit,
        is_current = transaction_id %in% current_ids
      )
    })
    payload <- list(
      transaction_history_contract_version = 1L,
      status = "ready",
      portfolio_id = portfolio_id,
      transaction_count = length(entries),
      current_transaction_count = sum(vapply(entries, function(entry) entry$is_current, logical(1))),
      entries = entries
    )
    result <- payload
    result$history_fingerprint <- .catalog_fingerprint(payload)
    result
  }, fallback = "transaction_command_repository_invalid")
}
