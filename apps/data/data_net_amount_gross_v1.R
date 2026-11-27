# Rechnet einen Nettobetrag, von dem ein Steuersatz schon abgezogen ist, auf Brutto um.
#
# Manche Abrechnungen weisen eine Dividende nur netto aus. Gebucht wird trotzdem
# brutto, vor Steuern - die Steuer hat ihr eigenes Modul. Bisher musste man
# dafuer selbst rechnen. Brutto = Netto /
# (1 - Satz/100); bei 1,00 netto und 26,375 % sind das 1,358234...
#
# Zwei Dinge sind dabei festgelegt und stehen deshalb sichtbar im Formular:
# - Gerechnet wird exakt, auf ganzen Zahlen ueber die Ziffernarithmetik aus
#   data_exact_ratio_presentation_v1.R; keine Gleitkommazahl ist beteiligt.
# - Das Ergebnis geht in aller Regel nicht auf. Gebucht wird der Betrag
#   kaufmaennisch auf zwei Nachkommastellen gerundet - die Rundung ist keine
#   stille: Der gerundete und der rechnerische Wert werden vor der Vorschau
#   genannt, und wer es genauer braucht, traegt den Bruttobetrag selbst ein.
# Nettobetrag und Steuersatz werden nicht gespeichert; sie sind Rechenhilfe.

.data_net_amount_decimal_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) return(NULL)
  normalized <- sub(",", ".", trimws(value), fixed = TRUE)
  if (!nzchar(normalized) || nchar(normalized) > 40L || !grepl("^(0|[1-9][0-9]*)(\\.[0-9]+)?$", normalized)) return(NULL)
  parts <- strsplit(normalized, ".", fixed = TRUE)[[1L]]
  fraction <- if (length(parts) == 2L) parts[[2L]] else ""
  list(digits = .data_exact_ratio_digits_v1(paste0(parts[[1L]], fraction)), scale = nchar(fraction))
}

.data_net_amount_text_v1 <- function(digits) if (!length(digits)) "0" else paste0(digits, collapse = "")

# Produkt zweier Ziffernvektoren (hoechste Stelle zuerst), schriftlich.
.data_net_amount_multiply_v1 <- function(left, right) {
  if (!length(left) || !length(right)) return(integer())
  cells <- integer(length(left) + length(right))
  for (index in seq_along(left)) {
    target <- index + seq_along(right)
    cells[target] <- cells[target] + left[[index]] * right
  }
  carry <- 0L
  for (index in length(cells):1) {
    total <- cells[[index]] + carry
    cells[[index]] <- total %% 10L
    carry <- total %/% 10L
  }
  first <- which(cells != 0L)
  if (!length(first)) integer() else cells[first[[1L]]:length(cells)]
}

# status: "incomplete" (eine Angabe fehlt), "invalid" (keine Zahl, Satz >= 100,
# Betrag nicht positiv) oder "ready".
data_net_amount_gross_v1 <- function(net_decimal, tax_rate_percent_decimal, quantity_decimal = NULL) {
  blank <- function(value) is.null(value) || (is.character(value) && length(value) == 1L && !is.na(value) && !nzchar(trimws(value)))
  with_quantity <- !is.null(quantity_decimal)
  if (blank(net_decimal) || blank(tax_rate_percent_decimal) || (with_quantity && blank(quantity_decimal))) return(list(status = "incomplete"))
  net <- .data_net_amount_decimal_v1(net_decimal); rate <- .data_net_amount_decimal_v1(tax_rate_percent_decimal)
  quantity <- if (with_quantity) .data_net_amount_decimal_v1(quantity_decimal) else NULL
  if (is.null(net) || is.null(rate) || (with_quantity && is.null(quantity)) || !length(net$digits) || (with_quantity && !length(quantity$digits))) return(list(status = "invalid"))
  if (with_quantity) net <- list(digits = .data_net_amount_multiply_v1(quantity$digits, net$digits), scale = quantity$scale + net$scale)
  # Brutto = Netto * 100 / (100 - Satz), mit Netto = N / 10^a und Satz = R / 10^b:
  # Zaehler N * 10^(b+2), Nenner (10^(b+2) - R) * 10^a.
  hundred <- c(1L, integer(rate$scale + 2L))
  if (.data_exact_ratio_digits_compare_v1(rate$digits, hundred) >= 0L) return(list(status = "invalid"))
  numerator <- c(net$digits, integer(rate$scale + 2L))
  denominator <- c(.data_exact_ratio_digits_subtract_v1(hundred, rate$digits), integer(net$scale))
  # Kaufmaennisch auf Hundertstel: floor((200 * Zaehler + Nenner) / (2 * Nenner)).
  doubled <- .data_exact_ratio_digits_add_v1(numerator, numerator)
  dividend <- .data_exact_ratio_digits_add_v1(c(doubled, 0L, 0L), denominator)
  divisor <- .data_exact_ratio_digits_add_v1(denominator, denominator)
  hundredths <- sub("…$", "", .data_exact_ratio_truncated_decimal_v1(.data_net_amount_text_v1(dividend), .data_net_amount_text_v1(divisor), 0L))
  if (identical(hundredths, "0")) return(list(status = "invalid"))
  padded <- if (nchar(hundredths) < 3L) paste0(strrep("0", 3L - nchar(hundredths)), hundredths) else hundredths
  gross <- paste0(substr(padded, 1L, nchar(padded) - 2L), ".", substr(padded, nchar(padded) - 1L, nchar(padded)))
  gross <- sub("\\.$", "", sub("0+$", "", gross))
  numerator_text <- .data_net_amount_text_v1(numerator); denominator_text <- .data_net_amount_text_v1(denominator)
  list(
    status = "ready", gross_amount_decimal = gross,
    # Der rechnerische Wert, abgeschnitten und als solcher gekennzeichnet - zum Vergleich.
    exact_preview = .data_exact_ratio_truncated_decimal_v1(numerator_text, denominator_text, 6L),
    rounded = grepl("…$", .data_exact_ratio_truncated_decimal_v1(numerator_text, denominator_text, 2L))
  )
}

# Der Satz unter den Eingabefeldern. Punkt wird fuer die Anzeige zum Komma.
data_net_amount_gross_hint_v1 <- function(result) {
  if (!is.list(result) || !is.character(result$status) || length(result$status) != 1L) stop("data_net_amount_gross_invalid", call. = FALSE)
  comma <- function(value) sub(".", ",", value, fixed = TRUE)
  switch(result$status,
    incomplete = "Nettobetrag und Steuersatz eintragen; daraus wird der Bruttobetrag berechnet.",
    invalid = "Daraus lässt sich kein Bruttobetrag berechnen: Beträge als positive Zahl, der Steuersatz zwischen 0 und unter 100.",
    ready = paste0("Ergibt Brutto ", comma(result$gross_amount_decimal),
      if (isTRUE(result$rounded)) paste0(" – rechnerisch ", comma(result$exact_preview), ", kaufmännisch auf zwei Nachkommastellen gerundet") else " – ohne Rundung",
      ". Gebucht wird nur dieser Bruttobetrag; Nettobetrag und Steuersatz werden nicht gespeichert."),
    stop("data_net_amount_gross_invalid", call. = FALSE))
}
