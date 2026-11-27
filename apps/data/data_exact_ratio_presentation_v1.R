# Schriftliche Division auf Ziffernvektoren. Bis rc.229 lief sie auf Zeichenketten:
# Je Quotientenziffer wurden bis zu zehn Vielfache des Nenners neu gebildet, als
# Text zusammengesetzt und per regulaerem Ausdruck normalisiert. Die Brueche der
# Positionstabelle kosteten so beim Sitzungsstart mehrere Sekunden. Jetzt entstehen die neun Vielfachen einmal je Division, und gerechnet
# wird auf ganzen Zahlen. Das Ergebnis ist Zeichen fuer Zeichen dasselbe; ein
# Vertragstest vergleicht beide Wege.
.data_exact_ratio_digits_v1 <- function(text) {
  digits <- utf8ToInt(text) - 48L
  first <- which(digits != 0L)
  if (!length(first)) integer() else digits[first[[1L]]:length(digits)]
}
# Vergleich zweier normalisierter Ziffernvektoren (ohne fuehrende Nullen; Null ist leer).
.data_exact_ratio_digits_compare_v1 <- function(left, right) {
  if (length(left) != length(right)) return(if (length(left) < length(right)) -1L else 1L)
  difference <- which(left != right)
  if (!length(difference)) return(0L)
  if (left[[difference[[1L]]]] < right[[difference[[1L]]]]) -1L else 1L
}
# left - right fuer left >= right; Ergebnis wieder normalisiert.
.data_exact_ratio_digits_subtract_v1 <- function(left, right) {
  size <- length(left)
  result <- left - c(integer(size - length(right)), right)
  borrow <- 0L
  for (index in size:1) {
    digit <- result[[index]] - borrow
    if (digit < 0L) { digit <- digit + 10L; borrow <- 1L } else borrow <- 0L
    result[[index]] <- digit
  }
  if (borrow != 0L) stop("data_exact_ratio_presentation_invalid", call.=FALSE)
  first <- which(result != 0L)
  if (!length(first)) integer() else result[first[[1L]]:size]
}
.data_exact_ratio_digits_add_v1 <- function(left, right) {
  size <- max(length(left), length(right))
  total <- c(integer(size - length(left)), left) + c(integer(size - length(right)), right)
  carry <- 0L
  for (index in size:1) {
    digit <- total[[index]] + carry
    if (digit > 9L) { digit <- digit - 10L; carry <- 1L } else carry <- 0L
    total[[index]] <- digit
  }
  if (carry != 0L) c(1L, total) else total
}
.data_exact_ratio_truncated_decimal_v1 <- function(numerator, denominator, decimal_places=8L) {
  if (
    !is.character(numerator) || length(numerator) != 1L || is.na(numerator) ||
    !grepl("^-?(0|[1-9][0-9]*)$", numerator) || nchar(numerator) > 4096L ||
    !is.character(denominator) || length(denominator) != 1L || is.na(denominator) ||
    !grepl("^[1-9][0-9]*$", denominator) || nchar(denominator) > 4096L ||
    !is.integer(decimal_places) || length(decimal_places) != 1L || is.na(decimal_places) ||
    decimal_places < 0L || decimal_places > 24L
  ) stop("data_exact_ratio_presentation_invalid", call.=FALSE)
  negative <- startsWith(numerator, "-")
  unsigned <- if (negative) substring(numerator, 2L) else numerator
  divisor <- .data_exact_ratio_digits_v1(denominator)
  # Die neun Vielfachen des Nenners einmal je Division, nicht je Quotientenziffer.
  multiples <- vector("list", 9L); multiples[[1L]] <- divisor
  for (factor in 2:9) multiples[[factor]] <- .data_exact_ratio_digits_add_v1(multiples[[factor - 1L]], divisor)
  step <- function(remainder, incoming) {
    if (length(remainder) || incoming != 0L) remainder <- c(remainder, incoming)
    digit <- 0L
    if (length(remainder) >= length(divisor)) {
      low <- 0L; high <- 9L
      while (low < high) {
        middle <- (low + high + 1L) %/% 2L
        if (.data_exact_ratio_digits_compare_v1(remainder, multiples[[middle]]) >= 0L) low <- middle else high <- middle - 1L
      }
      digit <- low
      if (digit > 0L) remainder <- .data_exact_ratio_digits_subtract_v1(remainder, multiples[[digit]])
    }
    list(digit = digit, remainder = remainder)
  }
  incoming <- utf8ToInt(unsigned) - 48L
  quotient <- integer(length(incoming)); remainder <- integer()
  for (index in seq_along(incoming)) {
    divided <- step(remainder, incoming[[index]])
    quotient[[index]] <- divided$digit; remainder <- divided$remainder
  }
  first <- which(quotient != 0L)
  integer_part <- if (!length(first)) "0" else paste0(quotient[first[[1L]]:length(quotient)], collapse="")
  fraction <- integer()
  if (length(remainder) && decimal_places > 0L) {
    for (index in seq_len(decimal_places)) {
      divided <- step(remainder, 0L)
      fraction <- c(fraction, divided$digit); remainder <- divided$remainder
      if (!length(remainder)) break
    }
  }
  decimal <- integer_part
  if (length(fraction)) decimal <- paste0(decimal, ".", paste0(fraction, collapse=""))
  if (negative && !identical(unsigned, "0")) decimal <- paste0("-", decimal)
  if (length(remainder)) decimal <- paste0(decimal, "…")
  decimal
}

# Exact canonical/state values remain unchanged. Only exact ratios receive a
# non-authoritative, non-rounded, truncation-marked browser presentation.
data_exact_ratio_presentation_v1 <- function(value, show_exact=FALSE, decimal_places=8L) {
  if (is.null(value)) return("—")
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value)) stop("data_exact_ratio_presentation_invalid", call.=FALSE)
  if (isTRUE(show_exact) || !grepl("/", value, fixed=TRUE)) return(value)
  parts <- strsplit(value, "/", fixed=TRUE)[[1L]]
  if (length(parts) != 2L) stop("data_exact_ratio_presentation_invalid", call.=FALSE)
  .data_exact_ratio_truncated_decimal_v1(parts[[1L]], parts[[2L]], decimal_places)
}
