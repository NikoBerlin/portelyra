# Internal exact unsigned-big-integer and rational arithmetic for M2 projections.
#
# Canonical ledger Decimals are never converted to binary floating point. The
# implementation is intentionally dependency-free and operates on character
# digits. Public projection functions return canonical Decimal text only.

.ed_big_norm_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^[0-9]+$", value, perl = TRUE)) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  normalized <- sub("^0+", "", value, perl = TRUE)
  if (!nzchar(normalized)) "0" else normalized
}

.ed_big_cmp_v1 <- function(left, right) {
  left <- .ed_big_norm_v1(left)
  right <- .ed_big_norm_v1(right)
  left_length <- nchar(left, type = "bytes")
  right_length <- nchar(right, type = "bytes")
  if (left_length < right_length) return(-1L)
  if (left_length > right_length) return(1L)
  if (identical(left, right)) return(0L)
  left_digits <- as.integer(strsplit(left, "", fixed = TRUE)[[1L]])
  right_digits <- as.integer(strsplit(right, "", fixed = TRUE)[[1L]])
  first_difference <- which(left_digits != right_digits)[[1L]]
  if (left_digits[[first_difference]] < right_digits[[first_difference]]) -1L else 1L
}

.ed_big_add_v1 <- function(left, right) {
  left <- rev(as.integer(strsplit(.ed_big_norm_v1(left), "", fixed = TRUE)[[1L]]))
  right <- rev(as.integer(strsplit(.ed_big_norm_v1(right), "", fixed = TRUE)[[1L]]))
  size <- max(length(left), length(right))
  length(left) <- size
  length(right) <- size
  left[is.na(left)] <- 0L
  right[is.na(right)] <- 0L
  output <- integer(size + 1L)
  carry <- 0L
  for (index in seq_len(size)) {
    value <- left[[index]] + right[[index]] + carry
    output[[index]] <- value %% 10L
    carry <- value %/% 10L
  }
  output[[size + 1L]] <- carry
  .ed_big_norm_v1(paste0(rev(output), collapse = ""))
}

.ed_big_sub_v1 <- function(left, right) {
  left_text <- .ed_big_norm_v1(left)
  right_text <- .ed_big_norm_v1(right)
  if (.ed_big_cmp_v1(left_text, right_text) < 0L) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  left_digits <- rev(as.integer(strsplit(left_text, "", fixed = TRUE)[[1L]]))
  right_digits <- rev(as.integer(strsplit(right_text, "", fixed = TRUE)[[1L]]))
  length(right_digits) <- length(left_digits)
  right_digits[is.na(right_digits)] <- 0L
  output <- integer(length(left_digits))
  borrow <- 0L
  for (index in seq_along(left_digits)) {
    value <- left_digits[[index]] - borrow - right_digits[[index]]
    if (value < 0L) {
      value <- value + 10L
      borrow <- 1L
    } else {
      borrow <- 0L
    }
    output[[index]] <- value
  }
  if (borrow != 0L) stop("exact_decimal_internal_invalid", call. = FALSE)
  .ed_big_norm_v1(paste0(rev(output), collapse = ""))
}

.ed_big_mul_digit_v1 <- function(value, digit) {
  value <- .ed_big_norm_v1(value)
  digit <- as.integer(digit)
  if (is.na(digit) || digit < 0L || digit > 9L) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  if (identical(value, "0") || digit == 0L) return("0")
  digits <- rev(as.integer(strsplit(value, "", fixed = TRUE)[[1L]]))
  output <- integer(length(digits) + 1L)
  carry <- 0L
  for (index in seq_along(digits)) {
    product <- digits[[index]] * digit + carry
    output[[index]] <- product %% 10L
    carry <- product %/% 10L
  }
  output[[length(digits) + 1L]] <- carry
  .ed_big_norm_v1(paste0(rev(output), collapse = ""))
}

.ed_big_mul_v1 <- function(left, right) {
  left <- .ed_big_norm_v1(left)
  right <- .ed_big_norm_v1(right)
  if (identical(left, "0") || identical(right, "0")) return("0")
  right_digits <- rev(as.integer(strsplit(right, "", fixed = TRUE)[[1L]]))
  result <- "0"
  for (index in seq_along(right_digits)) {
    partial <- .ed_big_mul_digit_v1(left, right_digits[[index]])
    if (!identical(partial, "0") && index > 1L) {
      partial <- paste0(partial, strrep("0", index - 1L))
    }
    result <- .ed_big_add_v1(result, partial)
  }
  .ed_big_norm_v1(result)
}

.ed_big_divmod_v1 <- function(numerator, denominator) {
  numerator <- .ed_big_norm_v1(numerator)
  denominator <- .ed_big_norm_v1(denominator)
  if (identical(denominator, "0")) stop("exact_decimal_internal_invalid", call. = FALSE)
  if (.ed_big_cmp_v1(numerator, denominator) < 0L) {
    return(list(quotient = "0", remainder = numerator))
  }
  remainder <- "0"
  quotient <- character()
  digits <- strsplit(numerator, "", fixed = TRUE)[[1L]]
  for (digit in digits) {
    remainder <- .ed_big_norm_v1(paste0(if (identical(remainder, "0")) "" else remainder, digit))
    quotient_digit <- 0L
    if (.ed_big_cmp_v1(remainder, denominator) >= 0L) {
      for (candidate in 9L:1L) {
        product <- .ed_big_mul_digit_v1(denominator, candidate)
        if (.ed_big_cmp_v1(product, remainder) <= 0L) {
          quotient_digit <- candidate
          remainder <- .ed_big_sub_v1(remainder, product)
          break
        }
      }
    }
    quotient <- c(quotient, as.character(quotient_digit))
  }
  list(
    quotient = .ed_big_norm_v1(paste0(quotient, collapse = "")),
    remainder = .ed_big_norm_v1(remainder)
  )
}

.ed_big_div_small_v1 <- function(value, divisor) {
  divisor <- as.integer(divisor)
  if (is.na(divisor) || divisor < 1L || divisor > 9L) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  carry <- 0L
  quotient <- integer()
  for (digit in as.integer(strsplit(.ed_big_norm_v1(value), "", fixed = TRUE)[[1L]])) {
    current <- carry * 10L + digit
    quotient <- c(quotient, current %/% divisor)
    carry <- current %% divisor
  }
  list(
    quotient = .ed_big_norm_v1(paste0(quotient, collapse = "")),
    remainder = carry
  )
}

.ed_big_gcd_v1 <- function(left, right) {
  left <- .ed_big_norm_v1(left)
  right <- .ed_big_norm_v1(right)
  while (!identical(right, "0")) {
    remainder <- .ed_big_divmod_v1(left, right)$remainder
    left <- right
    right <- remainder
  }
  left
}

.ed_rat_new_v1 <- function(sign, numerator, denominator = "1") {
  numerator <- .ed_big_norm_v1(numerator)
  denominator <- .ed_big_norm_v1(denominator)
  if (identical(denominator, "0")) stop("exact_decimal_internal_invalid", call. = FALSE)
  if (identical(numerator, "0")) {
    return(structure(list(sign = 0L, numerator = "0", denominator = "1"), class = "spot_exact_rational_v1"))
  }
  sign <- if (as.integer(sign) < 0L) -1L else 1L
  common <- .ed_big_gcd_v1(numerator, denominator)
  if (!identical(common, "1")) {
    numerator <- .ed_big_divmod_v1(numerator, common)$quotient
    denominator <- .ed_big_divmod_v1(denominator, common)$quotient
  }
  structure(list(sign = sign, numerator = numerator, denominator = denominator), class = "spot_exact_rational_v1")
}

.ed_rat_zero_v1 <- function() .ed_rat_new_v1(0L, "0")

.ed_rat_from_decimal_v1 <- function(value, positive = FALSE, nonnegative = FALSE, code = "realized_fifo_decimal_invalid") {
  if (!is.character(value) || length(value) != 1L || is.na(value) ||
      !grepl("^-?(0|[1-9][0-9]*)(\\.[0-9]*[1-9])?$", value, perl = TRUE) || identical(value, "-0")) {
    .realized_fifo_abort_v1(code)
  }
  sign <- if (startsWith(value, "-")) -1L else 1L
  unsigned <- sub("^-", "", value)
  parts <- strsplit(unsigned, ".", fixed = TRUE)[[1L]]
  scale <- if (length(parts) == 2L) nchar(parts[[2L]], type = "bytes") else 0L
  numerator <- paste0(parts, collapse = "")
  rational <- .ed_rat_new_v1(sign, numerator, paste0("1", strrep("0", scale)))
  if (positive && rational$sign <= 0L) .realized_fifo_abort_v1(code)
  if (nonnegative && rational$sign < 0L) .realized_fifo_abort_v1(code)
  rational
}

.ed_rat_neg_v1 <- function(value) .ed_rat_new_v1(-value$sign, value$numerator, value$denominator)

.ed_rat_add_v1 <- function(left, right) {
  if (left$sign == 0L) return(right)
  if (right$sign == 0L) return(left)
  left_scaled <- .ed_big_mul_v1(left$numerator, right$denominator)
  right_scaled <- .ed_big_mul_v1(right$numerator, left$denominator)
  denominator <- .ed_big_mul_v1(left$denominator, right$denominator)
  if (left$sign == right$sign) {
    return(.ed_rat_new_v1(left$sign, .ed_big_add_v1(left_scaled, right_scaled), denominator))
  }
  comparison <- .ed_big_cmp_v1(left_scaled, right_scaled)
  if (comparison == 0L) return(.ed_rat_zero_v1())
  if (comparison > 0L) {
    .ed_rat_new_v1(left$sign, .ed_big_sub_v1(left_scaled, right_scaled), denominator)
  } else {
    .ed_rat_new_v1(right$sign, .ed_big_sub_v1(right_scaled, left_scaled), denominator)
  }
}

.ed_rat_sub_v1 <- function(left, right) .ed_rat_add_v1(left, .ed_rat_neg_v1(right))

.ed_rat_mul_v1 <- function(left, right) {
  .ed_rat_new_v1(
    left$sign * right$sign,
    .ed_big_mul_v1(left$numerator, right$numerator),
    .ed_big_mul_v1(left$denominator, right$denominator)
  )
}

.ed_rat_div_v1 <- function(left, right) {
  if (right$sign == 0L) stop("exact_decimal_internal_invalid", call. = FALSE)
  .ed_rat_new_v1(
    left$sign * right$sign,
    .ed_big_mul_v1(left$numerator, right$denominator),
    .ed_big_mul_v1(left$denominator, right$numerator)
  )
}

.ed_rat_cmp_v1 <- function(left, right) {
  difference <- .ed_rat_sub_v1(left, right)
  difference$sign
}

.ed_rat_min_v1 <- function(left, right) if (.ed_rat_cmp_v1(left, right) <= 0L) left else right
.ed_rat_equal_v1 <- function(left, right) identical(.ed_rat_cmp_v1(left, right), 0L)
.ed_rat_is_zero_v1 <- function(value) identical(value$sign, 0L)

.ed_rat_to_decimal_v1 <- function(value, code = "realized_fifo_rounding_policy_required") {
  if (value$sign == 0L) return("0")
  denominator <- value$denominator
  factor_two <- 0L
  factor_five <- 0L
  repeat {
    divided <- .ed_big_div_small_v1(denominator, 2L)
    if (divided$remainder != 0L) break
    denominator <- divided$quotient
    factor_two <- factor_two + 1L
  }
  repeat {
    divided <- .ed_big_div_small_v1(denominator, 5L)
    if (divided$remainder != 0L) break
    denominator <- divided$quotient
    factor_five <- factor_five + 1L
  }
  if (!identical(denominator, "1")) .realized_fifo_abort_v1(code)
  scale <- max(factor_two, factor_five)
  numerator <- value$numerator
  if (factor_two < scale) {
    for (ignored in seq_len(scale - factor_two)) numerator <- .ed_big_mul_digit_v1(numerator, 2L)
  }
  if (factor_five < scale) {
    for (ignored in seq_len(scale - factor_five)) numerator <- .ed_big_mul_digit_v1(numerator, 5L)
  }
  if (scale == 0L) {
    rendered <- numerator
  } else {
    digits <- nchar(numerator, type = "bytes")
    if (digits <= scale) numerator <- paste0(strrep("0", scale - digits + 1L), numerator)
    split_at <- nchar(numerator, type = "bytes") - scale
    rendered <- paste0(substr(numerator, 1L, split_at), ".", substr(numerator, split_at + 1L, nchar(numerator)))
    rendered <- sub("0+$", "", rendered, perl = TRUE)
    rendered <- sub("\\.$", "", rendered, perl = TRUE)
  }
  if (value$sign < 0L) rendered <- paste0("-", rendered)
  if (nchar(rendered, type = "bytes") > 80L) .realized_fifo_abort_v1(code)
  rendered
}
