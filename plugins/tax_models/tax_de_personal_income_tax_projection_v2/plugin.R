# Internal exact unsigned-big-integer and rational arithmetic for M2 projections.
#
# Canonical ledger Decimals are never converted to binary floating point. The
# implementation is intentionally dependency-free and operates on character
# digits. Public projection functions return canonical Decimal text only.

# Nur Ziffern, ohne fuehrende Nullen. Geprueft wird an den Zeichencodes: Die
# Funktion laeuft je Rechenschritt viele Male, und zwei regulaere Ausdruecke je
# Aufruf machten sie zur zweitgroessten Bremse des Moduls.
.ed_big_norm_v1 <- function(value) {
  if (!is.character(value) || length(value) != 1L || is.na(value)) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  codes <- utf8ToInt(value)
  if (!length(codes) || anyNA(codes) || any(codes < 48L | codes > 57L)) {
    stop("exact_decimal_internal_invalid", call. = FALSE)
  }
  if (codes[[1L]] != 48L) return(value)
  first <- which(codes != 48L)
  if (!length(first)) "0" else substr(value, first[[1L]], length(codes))
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

# Wie oft sich eine Zahl durch einen kleinen Teiler teilen laesst - hoechstens "limit"-mal gezaehlt.
.ed_big_factor_count_v1 <- function(value, divisor, limit) {
  count <- 0L
  while (count < limit) {
    divided <- .ed_big_div_small_v1(value, divisor)
    if (divided$remainder != 0L) break
    value <- divided$quotient
    count <- count + 1L
  }
  list(count = count, rest = value)
}

# Kuerzt Zaehler und Nenner. Dezimalzahlen haben Zehnerpotenzen im Nenner: Besteht
# er nur aus Zweien und Fuenfen, genuegt es, diese Faktoren am Zaehler abzuzaehlen -
# ohne die Divisionskette des euklidischen Verfahrens und ohne Langdivision. Die
# kostete je Bruch den Grossteil der Rechenzeit: Mit ihr konnte das Modul bei
# vielen Bruechen die Zeitgrenze des Abschlusses ueberschreiten. Jeder andere Nenner geht den bisherigen Weg.
.ed_big_reduce_v1 <- function(numerator, denominator) {
  limit <- nchar(denominator, type = "bytes") * 4L
  twos <- .ed_big_factor_count_v1(denominator, 2L, limit)
  fives <- .ed_big_factor_count_v1(twos$rest, 5L, limit)
  if (identical(fives$rest, "1")) {
    shared_twos <- .ed_big_factor_count_v1(numerator, 2L, twos$count)
    shared_fives <- .ed_big_factor_count_v1(shared_twos$rest, 5L, fives$count)
    reduced <- "1"
    for (ignored in seq_len(twos$count - shared_twos$count)) reduced <- .ed_big_mul_digit_v1(reduced, 2L)
    for (ignored in seq_len(fives$count - shared_fives$count)) reduced <- .ed_big_mul_digit_v1(reduced, 5L)
    return(list(numerator = shared_fives$rest, denominator = reduced))
  }
  common <- .ed_big_gcd_v1(numerator, denominator)
  if (!identical(common, "1")) {
    numerator <- .ed_big_divmod_v1(numerator, common)$quotient
    denominator <- .ed_big_divmod_v1(denominator, common)$quotient
  }
  list(numerator = numerator, denominator = denominator)
}

.ed_rat_new_v1 <- function(sign, numerator, denominator = "1") {
  numerator <- .ed_big_norm_v1(numerator)
  denominator <- .ed_big_norm_v1(denominator)
  if (identical(denominator, "0")) stop("exact_decimal_internal_invalid", call. = FALSE)
  if (identical(numerator, "0")) {
    return(structure(list(sign = 0L, numerator = "0", denominator = "1"), class = "spot_exact_rational_v1"))
  }
  sign <- if (as.integer(sign) < 0L) -1L else 1L
  reduced <- .ed_big_reduce_v1(numerator, denominator)
  structure(list(sign = sign, numerator = reduced$numerator, denominator = reduced$denominator), class = "spot_exact_rational_v1")
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


suppressPackageStartupMessages(library(jsonlite))
.realized_fifo_abort_v1 <- function(code) stop(code, call.=FALSE)
zero <- function() .ed_rat_zero_v1()
from <- function(x) .ed_rat_from_decimal_v1(x, code="reference_tax_decimal_invalid")
to <- function(x) .ed_rat_to_decimal_v1(x, code="reference_tax_rounding_policy_required")
hundred <- from("100")
nonneg <- function(x) if (x$sign < 0L) zero() else x
minimum <- function(a,b) if (.ed_rat_cmp_v1(a,b)<=0L) a else b
add <- .ed_rat_add_v1
minus <- .ed_rat_sub_v1
mul <- .ed_rat_mul_v1
div <- .ed_rat_div_v1
param <- function(parameters,year,code,field) {
 found <- Filter(function(x) identical(as.integer(x$tax_year),as.integer(year)) && identical(x$parameter_code,code) && is.null(x$institution_key),parameters)
 if (!length(found) || length(found) != 1L || is.null(found[[1]][[field]])) NULL else found[[1]][[field]]
}
# Der Rechtsstand je Steuerjahr. Das Modul bringt die Werte des Gesetzes selbst
# mit - Abgeltungsteuersatz, Solidaritaetszuschlag, die Freigrenzen der privaten
# Veraeusserungsgeschaefte und der sonstigen Einkuenfte -, statt sie je Jahr
# eintippen zu lassen. Ein eingetragener Parameter desselben Namens geht vor.
# Fuer ein Jahr ohne Zeilen hat das Modul keine Regeln: Dann rechnet es nichts
# und sagt es, statt mit den Werten eines anderen Jahres zu rechnen
# (Festlegung 12.10.2026). 2016 bis 2019 fuehrt es nur in Grundzuegen (#496, Festlegung 28.10.2026): dieselben
# Jahreswerte und Regeln wie ab 2020, aber ohne das alte Investmentsteuergesetz - siehe year-coverage.csv. Der Sandkasten liest nur diese Datei; die Tabelle
# steht deshalb hier und wortgleich in annual-legal-values.csv mit Fundstelle -
# der Vertragstest vergleicht beide.
legal_values_text <- "tax_year,value_code,value_decimal
2016,capital_income_tax_rate,25
2016,solidarity_surcharge_rate,5.5
2016,private_disposal_exemption_threshold,600
2016,other_income_exemption_threshold,256
2016,capital_income_allowance_single,801
2016,capital_income_allowance_joint,1602
2017,capital_income_tax_rate,25
2017,solidarity_surcharge_rate,5.5
2017,private_disposal_exemption_threshold,600
2017,other_income_exemption_threshold,256
2017,capital_income_allowance_single,801
2017,capital_income_allowance_joint,1602
2018,capital_income_tax_rate,25
2018,solidarity_surcharge_rate,5.5
2018,private_disposal_exemption_threshold,600
2018,other_income_exemption_threshold,256
2018,capital_income_allowance_single,801
2018,capital_income_allowance_joint,1602
2019,capital_income_tax_rate,25
2019,solidarity_surcharge_rate,5.5
2019,private_disposal_exemption_threshold,600
2019,other_income_exemption_threshold,256
2019,capital_income_allowance_single,801
2019,capital_income_allowance_joint,1602
2020,capital_income_tax_rate,25
2020,solidarity_surcharge_rate,5.5
2020,private_disposal_exemption_threshold,600
2020,other_income_exemption_threshold,256
2020,capital_income_allowance_single,801
2020,capital_income_allowance_joint,1602
2021,capital_income_tax_rate,25
2021,solidarity_surcharge_rate,5.5
2021,private_disposal_exemption_threshold,600
2021,other_income_exemption_threshold,256
2021,capital_income_allowance_single,801
2021,capital_income_allowance_joint,1602
2022,capital_income_tax_rate,25
2022,solidarity_surcharge_rate,5.5
2022,private_disposal_exemption_threshold,600
2022,other_income_exemption_threshold,256
2022,capital_income_allowance_single,801
2022,capital_income_allowance_joint,1602
2023,capital_income_tax_rate,25
2023,solidarity_surcharge_rate,5.5
2023,private_disposal_exemption_threshold,600
2023,other_income_exemption_threshold,256
2023,capital_income_allowance_single,1000
2023,capital_income_allowance_joint,2000
2024,capital_income_tax_rate,25
2024,solidarity_surcharge_rate,5.5
2024,private_disposal_exemption_threshold,1000
2024,other_income_exemption_threshold,256
2024,capital_income_allowance_single,1000
2024,capital_income_allowance_joint,2000
2025,capital_income_tax_rate,25
2025,solidarity_surcharge_rate,5.5
2025,private_disposal_exemption_threshold,1000
2025,other_income_exemption_threshold,256
2025,capital_income_allowance_single,1000
2025,capital_income_allowance_joint,2000
2026,capital_income_tax_rate,25
2026,solidarity_surcharge_rate,5.5
2026,private_disposal_exemption_threshold,1000
2026,other_income_exemption_threshold,256
2026,capital_income_allowance_single,1000
2026,capital_income_allowance_joint,2000"
legal_values <- lapply(strsplit(strsplit(legal_values_text,"\n",fixed=TRUE)[[1]][-1L],",",fixed=TRUE),function(parts) list(tax_year=as.integer(parts[[1]]),value_code=parts[[2]],value_decimal=parts[[3]]))
legal_years <- unique(vapply(legal_values,function(x)x$tax_year,integer(1)))
year_covered <- function(year) as.integer(year) %in% legal_years
legal <- function(year,code) {
 found <- Filter(function(x) identical(x$tax_year,as.integer(year)) && identical(x$value_code,code),legal_values)
 if (length(found) != 1L) NULL else found[[1]]$value_decimal
}
model_fingerprint <- Sys.getenv("PORTELYRA_TAX_PLUGIN_MODEL_FINGERPRINT")
plugin_fields <- function(row,parameter_fingerprint_value) {
 row$plugin_id <- Sys.getenv("PORTELYRA_TAX_PLUGIN_ID")
 row$plugin_version <- Sys.getenv("PORTELYRA_TAX_PLUGIN_VERSION")
 row$rules_fingerprint <- Sys.getenv("PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT")
 row$model_fingerprint <- model_fingerprint
 row$parameter_fingerprint <- parameter_fingerprint_value
 row$disclaimer_code <- "model_projection_not_legal_advice"
 row
}
# Fonds vor 2018 (#496, Festlegung 28.10.2026): Bis Ende 2017 galt das alte Investmentsteuergesetz, und fuer Anteile aus
# dieser Zeit (Altanteile) gilt die fiktive Veraeusserung zum 31.12.2017 (§ 56 InvStG). Beides bildet das Modul nicht ab;
# solche Vorgaenge bekommen keine Zahl, sondern tax_fund_old_investment_tax_act - nie eine falsche. Am Verkauf zaehlt jedes
# Lot, das vor 2018 angeschafft wurde, an der Ausschuettung nur ihr Datum.
OLD_FUND_ACT_UNTIL <- "2018-01-01"
old_fund_shares <- function(date, lots = NULL) {
 early <- is.character(date) && length(date) == 1L && date < OLD_FUND_ACT_UNTIL
 early || any(vapply(if (is.null(lots)) list() else lots, function(lot) is.character(lot$acquisition_local_date) && length(lot$acquisition_local_date) == 1L &&
   lot$acquisition_local_date < OLD_FUND_ACT_UNTIL, logical(1)))
}
anniversary <- function(date) {
 parts <- as.integer(strsplit(date,"-",fixed=TRUE)[[1]])
 year <- parts[[1]]+1L; month <- parts[[2]]; day <- parts[[3]]
 if (month==2L && day==29L) day <- 28L
 sprintf("%04d-%02d-%02d",year,month,day)
}
classification <- function(input,source,year) {
 selected <- Filter(function(x) identical(x$asset_ref,source$asset_ref) && as.integer(x$effective_from_year)<=year && (is.null(x$effective_to_year) || as.integer(x$effective_to_year)>=year),input$classifications)
 if (!length(selected)) NULL else selected[[length(selected)]]
}
class_matrix <- list(
 # Der Aktientopf (§ 20 Abs. 6 Satz 4 EStG) fasst nur Gewinne und Verluste aus der Veraeusserung von Aktien; die
 # Dividende ist allgemeiner Kapitalertrag (§ 20 Abs. 1 Nr. 1) und fliesst in den allgemeinen Topf. Bis hierhin lag sie
 # im Aktientopf, wo Aktienverluste sie mindern durften.
 de_equity_share=list(bucket="capital_equity",events=c("sell","dividend"),partial="zero",event_bucket=list(dividend="capital_general")),
 de_capital_instrument=list(bucket="capital_general",events=c("sell","dividend","interest"),partial="zero"),
 de_cash_interest=list(bucket="capital_general",events=c("interest"),partial="zero"),
 de_fund=list(bucket="capital_general",events=c("sell","dividend"),partial="asset"),
 # Ein Asset traegt eine Einordnung, loest aber zwei Arten von Vorgaengen aus: Der
 # Verkauf ist privates Veraeusserungsgeschaeft (§ 23 EStG), der Reward - Staking,
 # Lending - sonstige Einkunft (§ 22 Nr. 3 EStG) und fliesst in deren Topf. Bis
 # hierhin war am Krypto-Asset nur der Verkauf erlaubt: Jeder Reward blieb als
 # "Klassifikation ungueltig" ohne Steuerzahl stehen.
 de_private_disposal_asset=list(bucket="private_disposal",events=c("sell","reward"),partial="zero",event_bucket=list(reward="other_income")),
 # Zinsen sind Kapitalertrag nach § 20 I Nr. 7 EStG und gehoeren nach
 # de_cash_interest. Hier erlaubt, wurden sie als sonstige Einkunft mit dem
 # persoenlichen Satz besteuert - still und falsch (Festlegung 28.09.2026, #367).
 de_other_income_asset=list(bucket="other_income",events=c("reward"),partial="zero")
)
rule_for <- function(code,event) {
 paste(code,event,sep="_")
}
rate_for <- function(bucket) if (bucket %in% c("capital_equity","capital_general")) "capital_income_tax_rate" else "personal_income_tax_rate"
# Ein anteiliger Betrag ist oft periodisch: Werden zwei von drei Losen anteilig
# zugeordnet, endet die Dezimalzahl nie. Ohne Rundung brach das Modul mit
# reference_tax_rounding_policy_required ab und lieferte gar kein Ergebnis. Die
# Schaetzung wird deshalb auf zwoelf Nachkommastellen festgelegt - weit unter
# jeder steuerlichen Erheblichkeit (#367 Schritt 2, 28.09.2026).
scaled <- .ed_rat_from_decimal_v1("1000000000000")
round_dec <- function(value) {
 if (.ed_rat_is_zero_v1(value)) return(value)
 scaled_value <- .ed_rat_mul_v1(value, scaled)
 whole <- .ed_big_divmod_v1(scaled_value$numerator, scaled_value$denominator)
 .ed_rat_div_v1(.ed_rat_new_v1(value$sign, whole$quotient), scaled)
}
# Kapitalertraege je Ereignis auf Cent (#459, Festlegung 22.10.2026): Die Institute runden den steuerpflichtigen Betrag
# je Abrechnung kaufmaennisch auf Cent (etwa den Ertrag nach Teilfreistellung). Exakt gerechnet wiche der Betrag sonst
# um einige Cent von den Steuerbescheinigungen ab.
cent <- .ed_rat_from_decimal_v1("100")
half <- .ed_rat_new_v1(1L, "1", "2")
round_cent <- function(value) {
 if (.ed_rat_is_zero_v1(value)) return(value)
 scaled_value <- .ed_rat_mul_v1(.ed_rat_new_v1(1L, value$numerator, value$denominator), cent)
 bumped <- .ed_rat_add_v1(scaled_value, half)
 whole <- .ed_big_divmod_v1(bumped$numerator, bumped$denominator)
 .ed_rat_div_v1(.ed_rat_new_v1(value$sign, whole$quotient), cent)
}
# Endet eine Zahl als Dezimalzahl? Nur dann, wenn ihr gekuerzter Nenner aus Zweien und Fuenfen besteht.
terminates <- function(value) {
 if (value$sign == 0L) return(TRUE)
 limit <- nchar(value$denominator, type="bytes") * 4L
 twos <- .ed_big_factor_count_v1(value$denominator, 2L, limit)
 identical(.ed_big_factor_count_v1(twos$rest, 5L, limit)$rest, "1")
}
economic_gross <- function(source) add(from(source$realized_gross_gain_decimal),from(source$gross_income_decimal))
private_contribution <- function(source) {
 allocations <- source$fifo_allocations
 if (is.null(allocations) || !length(allocations)) return(NULL)
 total <- from(source$quantity_decimal); proceeds <- from(source$gross_proceeds_decimal); result <- zero()
 for (allocation in allocations) {
  if (source$local_date <= anniversary(allocation$acquisition_local_date)) {
   allocated_proceeds <- mul(proceeds,div(from(allocation$quantity_decimal),total))
   result <- add(result,minus(allocated_proceeds,from(allocation$fifo_cost_decimal)))
  }
 }
 # Liegt nur ein Teil der Lots in der Jahresfrist, ist ihr Anteil am Erloes oft
 # periodisch (ein Drittel, ein Siebtel). Ohne Rundung brach das Modul an dieser
 # einen Zeile ab - und mit ihm der ganze Lauf, also der Abschluss.
 # Es gilt dieselbe Festlegung wie bei der unrealisierten Rechnung:
 # zwoelf Nachkommastellen. Ein Wert, der als Dezimalzahl endet, bleibt exakt.
 if (terminates(result)) result else round_dec(result)
}
args <- commandArgs(trailingOnly=TRUE)
input <- fromJSON(args[[1]],simplifyVector=FALSE)
parameter_fingerprint_value <- Sys.getenv("PORTELYRA_TAX_PLUGIN_PARAMETER_FINGERPRINT")
# Der eingetragene Wert des Jahres, sonst der des Moduls. Den persoenlichen
# Steuersatz kennt kein Gesetz - er bleibt Angabe des Eigentuemers.
rate_value <- function(year,code) {
 own <- param(input$parameters,year,code,"rate_decimal")
 if (!is.null(own)) own else legal(year,code)
}
amount_value <- function(year,code) {
 own <- param(input$parameters,year,code,"amount_decimal")
 if (!is.null(own)) own else legal(year,code)
}
church_policy <- function(year) {
 applicable <- param(input$parameters,year,"church_tax_applicable","applicability_value")
 rate <- param(input$parameters,year,"church_tax_rate","rate_decimal")
 if (is.null(applicable) || !(applicable %in% c("applicable","not_applicable"))) return(list(blocked="church_tax_applicability_required",applicable=NULL,rate=NULL))
 if (identical(applicable,"not_applicable")) return(list(blocked=NULL,applicable="not_applicable",rate=NULL))
 if (is.null(rate)) return(list(blocked="church_tax_rate_required",applicable="applicable",rate=NULL))
 list(blocked=NULL,applicable="applicable",rate=rate)
}
# Ohne Bemessungsgrundlage gibt es keine Zuschlaege - und dann braucht es auch
# keinen Satz. Bis hierhin las die Funktion den Solidaritaetszuschlag
# unbedingt und brach mit reference_tax_decimal_invalid ab, wenn fuer das Jahr
# keiner gepflegt war. Aus "keine Steuer" wurde so ein harter Fehler, fuer
# jedes Jahr ohne gepflegten Wert (#368).
apply_tax_surcharges <- function(base_tax,soli_rate,church) {
 if (base_tax$sign <= 0L) return(list(solidarity=zero(),church_tax=zero(),total=base_tax))
 solidarity <- mul(base_tax,div(from(soli_rate),hundred))
 church_tax <- if (identical(church$applicable,"applicable")) mul(base_tax,div(from(church$rate),hundred)) else zero()
 list(solidarity=solidarity,church_tax=church_tax,total=add(add(base_tax,solidarity),church_tax))
}
annual_detail <- NULL
rows <- list()
if (identical(input$projection_mode,"realized_event")) {
 for (source in input$rows) {
  year <- as.integer(substr(source$local_date,1,4))
  gross <- economic_gross(source)
  relevant <- source$event_type %in% c("sell","dividend","interest","reward") && !.ed_rat_is_zero_v1(gross)
  cls <- if (relevant) classification(input,source,year) else NULL
  base <- list(event_ref=source$event_ref,effective_at_utc=source$effective_at_utc,local_date=source$local_date,event_type=source$event_type,account_ref=source$account_ref,asset_ref=source$asset_ref,currency=source$currency,gross_proceeds_decimal=source$gross_proceeds_decimal,realized_gross_gain_decimal=source$realized_gross_gain_decimal,gross_income_decimal=source$gross_income_decimal,fee_decimal=source$fee_decimal,tax_year=year)
  blocked <- NULL; taxable <- zero(); code <- "not_applicable"; bucket <- "not_applicable"; exemption_text <- "0"
  if (relevant && !year_covered(year)) blocked <- "tax_year_rules_missing"
  if (relevant && is.null(blocked) && is.null(cls)) blocked <- "tax_classification_required"
  if (relevant && is.null(blocked) && identical(cls$classification_code,"de_fund") &&
      old_fund_shares(source$local_date, if (identical(source$event_type,"sell")) source$fifo_allocations else NULL)) blocked <- "tax_fund_old_investment_tax_act"
  if (relevant && is.null(blocked)) {
   code <- cls$classification_code; bucket <- cls$tax_bucket; exemption_text <- cls$partial_exemption_rate_decimal
   model <- class_matrix[[code]]
   if (is.null(model) || !identical(model$bucket,bucket) || !(source$event_type %in% model$events) || (identical(model$partial,"zero") && !identical(exemption_text,"0"))) blocked <- "tax_classification_invalid"
   if (is.null(blocked)) {
    # Der Topf folgt dem Vorgang, wo die Einordnung es so vorsieht.
    if (!is.null(model$event_bucket[[source$event_type]])) bucket <- model$event_bucket[[source$event_type]]
    taxable <- if (identical(bucket,"private_disposal")) private_contribution(source) else gross
    if (is.null(taxable)) blocked <- "tax_holding_evidence_required"
    if (is.null(blocked) && identical(model$partial,"asset")) taxable <- mul(taxable,div(minus(hundred,from(exemption_text)),hundred))
    if (is.null(blocked) && bucket %in% c("capital_equity","capital_general")) {
     taxable <- round_cent(taxable)
     # Steuerpflichtig laut Beleg (#459, 04.11.2026): Nennt die Bank den Kapitalertrag dieses Vorgangs (nach Teilfreistellung,
     # vor Freistellungsauftrag und Verlustverrechnung), gilt ihr Betrag - auf den Cent wie in der Bescheinigung -, solange er
     # hoechstens 1 Euro von der eigenen Rechnung abweicht. Bei jeder Rechnung geprueft: Nach einer Korrektur der Buchung
     # ueberdeckt ein alter Belegwert die neue Rechnung nicht still. Die Steuer darauf rechnet das Modul wie sonst.
     document <- source$document_taxable_decimal
     if (is.character(document) && length(document)==1L && nzchar(document)) {
      candidate <- from(document); gap <- minus(candidate,taxable)
      if (gap$sign < 0L) gap <- minus(zero(),gap)
      if (minus(gap,from("1"))$sign <= 0L) taxable <- candidate
     }
    }
   }
  }
  tax <- NULL
  if (is.null(blocked)) {
   if (taxable$sign>0L) {
    base_rate <- rate_value(year,rate_for(bucket))
    soli_rate <- rate_value(year,"solidarity_surcharge_rate")
    church <- church_policy(year)
    if (is.null(base_rate) || is.null(soli_rate)) blocked <- "tax_rate_required" else if (!is.null(church$blocked)) blocked <- church$blocked else {
     base_tax <- mul(taxable,div(from(base_rate),hundred)); tax <- apply_tax_surcharges(base_tax,soli_rate,church)$total
    }
   } else tax <- zero()
  }
  if (!is.null(blocked)) {
   row <- c(base,list(classification_code=if(is.null(cls))NULL else cls$classification_code,tax_bucket=if(is.null(cls))NULL else cls$tax_bucket,partial_exemption_rate_decimal=if(is.null(cls))NULL else cls$partial_exemption_rate_decimal,taxable_contribution_decimal=NULL,projected_event_tax_decimal=NULL,projected_net_gain_decimal=NULL,projected_net_proceeds_decimal=NULL,projection_status="blocked",failure_code=blocked))
  } else {
   row <- c(base,list(classification_code=code,tax_bucket=bucket,partial_exemption_rate_decimal=exemption_text,taxable_contribution_decimal=to(taxable),projected_event_tax_decimal=to(tax),projected_net_gain_decimal=to(minus(gross,tax)),projected_net_proceeds_decimal=to(minus(add(from(source$gross_proceeds_decimal),from(source$gross_income_decimal)),tax)),projection_status="completed",failure_code=NULL))
  }
  rows[[length(rows)+1L]] <- plugin_fields(row,parameter_fingerprint_value)
 }
} else if (identical(input$projection_mode,"realized_annual")) {
 year <- as.integer(input$cutoff)
 currencies <- unique(vapply(input$rows,function(x)x$currency,character(1)))
 currency <- if (length(currencies)) currencies[[1]] else "EUR"
 buckets <- c("capital_equity","capital_general","private_disposal","other_income")
 optional <- c("capital_income_allowance","externally_used_capital_income_allowance","private_disposal_exemption_threshold","other_income_exemption_threshold","creditable_foreign_withholding_tax","opening_equity_loss_carryforward","opening_general_capital_loss_carryforward","opening_private_disposal_loss_carryforward","opening_other_income_loss_carryforward")
 defaults <- optional[vapply(optional,function(code)is.null(param(input$parameters,year,code,"amount_decimal")),logical(1))]
 amount <- function(code){value<-param(input$parameters,year,code,"amount_decimal");from(if(is.null(value))"0" else value)}
 opening_codes <- c(capital_equity="opening_equity_loss_carryforward",capital_general="opening_general_capital_loss_carryforward",private_disposal="opening_private_disposal_loss_carryforward",other_income="opening_other_income_loss_carryforward")
 states <- list(); grossgain <- zero()
 for (event in input$rows) grossgain <- add(grossgain,add(from(event$realized_gross_gain_decimal),from(event$gross_income_decimal)))
 sums <- function(selected,bucket) {
  positive<-zero();negative<-zero()
  for(event in Filter(function(x)identical(x$tax_bucket,bucket),selected)){v<-from(event$taxable_contribution_decimal);if(v$sign<0L)negative<-add(negative,v) else positive<-add(positive,v)}
  list(positive=positive,negative=negative,net=add(positive,negative))
 }
 for (bucket in c("private_disposal","other_income")) states[[bucket]]<-c(sums(input$rows,bucket),list(opening=amount(opening_codes[[bucket]]),used=zero(),closing=zero(),base=zero(),allowance=zero(),tax=zero(),credit=zero()))
 loss_of <- function(value) if (value$sign < 0L) .ed_rat_neg_v1(value) else zero()
 # Kapitalertraege (Festlegung 14.10.2026, #429). Erst gleicht sich das Jahr in sich aus, dann gelten die Vortraege
 # (Verlustausgleich vor Verlustabzug), zuletzt der Sparer-Pauschbetrag (§ 20 Abs. 9 Satz 4 EStG; BFH VIII R 11/18, Rn. 17).
 # Aktienverluste mindern nur Aktiengewinne (§ 20 Abs. 6 Satz 4); alle anderen Verluste mindern alle positiven
 # Kapitalertraege - auch Aktiengewinne (§ 20 Abs. 6, § 43a Abs. 3 Satz 2). Bis hierhin blieben allgemeine Verluste in
 # ihrem Topf und Aktiengewinne voll besteuert.
 capital_group <- function(selected,opening_equity,opening_general,allowance,withholding) {
  equity <- sums(selected,"capital_equity"); general <- sums(selected,"capital_general")
  share <- equity$net; share_loss <- loss_of(share); share <- nonneg(share)
  general_loss <- loss_of(general$net); general_income <- nonneg(general$net)
  cross <- minimum(share, general_loss); share <- minus(share, cross); general_loss <- minus(general_loss, cross)
  share_carry <- minimum(share, opening_equity); share <- minus(share, share_carry)
  general_carry_general <- minimum(general_income, opening_general); general_income <- minus(general_income, general_carry_general)
  general_carry_share <- minimum(share, minus(opening_general, general_carry_general)); share <- minus(share, general_carry_share)
  # Verbraucht ist, was die positiven Ertraege des Topfs gemindert hat - aus dem Jahr selbst und aus Vortraegen.
  e <- c(equity,list(opening=opening_equity,used=add(add(minimum(equity$positive, loss_of(equity$negative)), cross), add(share_carry, general_carry_share)),
   closing=add(minus(opening_equity, share_carry), share_loss),base=share,allowance=zero(),tax=zero(),credit=zero()))
  g <- c(general,list(opening=opening_general,used=add(minimum(general$positive, loss_of(general$negative)), general_carry_general),
   closing=add(minus(minus(opening_general, general_carry_general), general_carry_share), general_loss),base=general_income,allowance=zero(),tax=zero(),credit=zero()))
  # Der Pauschbetrag erst gegen die allgemeinen Ertraege, dann gegen Aktiengewinne.
  left <- allowance
  used <- minimum(g$base,left); g$allowance <- used; g$base <- minus(g$base,used); left <- minus(left,used)
  used <- minimum(e$base,left); e$allowance <- used; e$base <- minus(e$base,used)
  list(capital_equity=e,capital_general=g,allowance=allowance,withholding=withholding)
 }
 # Je Institut (Festlegung 14.10.2026): Freistellungsauftrag, Verlusttoepfe und anrechenbare Quellensteuer gelten je
 # auszahlender Stelle (§ 43a Abs. 3, § 44a Abs. 2 EStG); ein Verlust bei einem Institut mindert keinen Gewinn bei einem
 # anderen. Traegt eine Zeile `institution_key`, rechnet das Modul je Institut, mit den Werten der Parameter desselben
 # Schluessels - ohne Eintrag null. Zeilen ohne Schluessel rechnet es wie bisher in einem Ganzen mit den Werten ohne Schluessel.
 # Ein Jahr ohne Ertraege, aber mit Werten je Institut, rechnet ebenso je Institut - sonst gingen die Vortraege verloren.
 grouped <- any(vapply(input$rows,function(x)!is.null(x$institution_key),logical(1))) || any(vapply(input$parameters,function(x)!is.null(x$institution_key),logical(1)))
 group_of <- function(x) if (is.null(x$institution_key)) "" else as.character(x$institution_key)
 group_amount <- function(code,key) {
  found <- Filter(function(x) identical(as.integer(x$tax_year),year) && identical(x$parameter_code,code) && !is.null(x$institution_key) && identical(as.character(x$institution_key),key),input$parameters)
  if (length(found)!=1L || is.null(found[[1]]$amount_decimal)) zero() else from(found[[1]]$amount_decimal)
 }
 if (grouped) {
  capital_rows <- Filter(function(x)x$tax_bucket%in%c("capital_equity","capital_general"),input$rows)
  # Ein Institut mit Eintraegen, aber ohne Ertraege im Jahr, gehoert dazu: Sein Vortrag laeuft unveraendert weiter.
  keyed <- Filter(function(x) identical(as.integer(x$tax_year),year) && !is.null(x$institution_key),input$parameters)
  keys <- sort(unique(c(vapply(capital_rows,group_of,character(1)),vapply(keyed,function(x)as.character(x$institution_key),character(1)))))
  groups <- lapply(keys,function(key) capital_group(Filter(function(x)identical(group_of(x),key),capital_rows),
   group_amount("opening_equity_loss_carryforward",key),group_amount("opening_general_capital_loss_carryforward",key),
   group_amount("capital_income_allowance",key),group_amount("creditable_foreign_withholding_tax",key)))
 } else {
  keys <- ""
  groups <- list(capital_group(input$rows,amount("opening_equity_loss_carryforward"),amount("opening_general_capital_loss_carryforward"),
   nonneg(minus(amount("capital_income_allowance"),amount("externally_used_capital_income_allowance"))),amount("creditable_foreign_withholding_tax")))
 }
 allowance <- zero(); for (group in groups) allowance <- add(allowance,group$allowance)
 # Private Veraeusserungsgeschaefte und sonstige Einkuenfte: Das Jahr gleicht sich in sich aus; liegt der Gesamtgewinn unter
 # der Freigrenze, bleibt er steuerfrei und der Vortrag unberuehrt. Erst ein Gesamtgewinn ab der Freigrenze wird um den
 # Vortrag gemindert - und bleibt steuerpflichtig, auch wenn er danach unter der Grenze liegt (§ 23 Abs. 3 Satz 5 und 8,
 # § 22 Nr. 3 Satz 2 bis 4 EStG; BFH IX R 27/04 vom 11.01.2005, BStBl II 2005, 433). Bis hierhin minderte der Vortrag den
 # Gewinn vor der Pruefung der Freigrenze. Ein Verlustruecktrag in das Vorjahr ist nicht abgebildet.
 # Beide Freigrenzen kommen aus dem Rechtsstand des Jahres, wenn nichts eingetragen ist. Steuerfrei bleibt, was
 # "weniger als" die Grenze betraegt: Wer sie genau erreicht, zahlt.
 module_amount <- function(code){value<-amount_value(year,code);from(if(is.null(value))"0" else value)}
 limits <- list(private_disposal=module_amount("private_disposal_exemption_threshold"),other_income=module_amount("other_income_exemption_threshold"))
 for (bucket in c("private_disposal","other_income")) {
  s <- states[[bucket]]; same_year <- minimum(s$positive, loss_of(s$negative))
  if (s$net$sign <= 0L) {
   states[[bucket]]$used <- same_year; states[[bucket]]$closing <- add(s$opening, loss_of(s$net)); states[[bucket]]$base <- zero()
  } else if (limits[[bucket]]$sign > 0L && .ed_rat_cmp_v1(s$net, limits[[bucket]]) < 0L) {
   states[[bucket]]$used <- same_year; states[[bucket]]$closing <- s$opening; states[[bucket]]$base <- zero()
  } else {
   carry <- minimum(s$net, s$opening)
   states[[bucket]]$used <- add(same_year, carry); states[[bucket]]$closing <- minus(s$opening, carry); states[[bucket]]$base <- minus(s$net, carry)
  }
 }
 applicable_capital <- any(vapply(groups,function(g)g$capital_equity$base$sign>0L || g$capital_general$base$sign>0L,logical(1)))
 applicable_personal <- states$private_disposal$base$sign>0L || states$other_income$base$sign>0L
 applicable_tax <- applicable_capital || applicable_personal
 capital_rate<-rate_value(year,"capital_income_tax_rate");personal_rate<-rate_value(year,"personal_income_tax_rate");soli_rate<-rate_value(year,"solidarity_surcharge_rate");church<-church_policy(year)
 # Ohne Regeln fuer das Jahr gibt es auch keine Jahressteuer - auch keine von null.
 uncovered <- !year_covered(year)
 blocked <- uncovered || length(currencies)>1L || (applicable_capital && is.null(capital_rate)) || (applicable_personal && is.null(personal_rate)) || (applicable_tax&&is.null(soli_rate)) || (applicable_tax&&!is.null(church$blocked))
 failure <- if(uncovered)"tax_year_rules_missing" else if(length(currencies)>1L)"tax_currency_conflict" else if((applicable_capital && is.null(capital_rate)) || (applicable_personal && is.null(personal_rate)) || (applicable_tax&&is.null(soli_rate)))"tax_rate_required" else if(applicable_tax&&!is.null(church$blocked))church$blocked else NULL
 total_tax<-zero();total_positive<-zero();total_negative<-zero();total_net<-zero();total_opening<-zero();total_used<-zero();total_closing<-zero();total_allowance_used<-zero()
 # Anrechenbare auslaendische Quellensteuer mindert nur die Steuer auf Kapitalertraege, und zwar vor Solidaritaetszuschlag
 # und Kirchensteuer (§ 32d Abs. 5 EStG) - je Institut, erst im allgemeinen Topf, wo Dividenden und Zinsen liegen, dann im
 # Aktientopf, hoechstens bis null. Bis hierhin wurde sie von der Gesamtsteuer abgezogen, auch von der auf private
 # Veraeusserungen.
 if(!blocked){
  for (index in seq_along(groups)) {
   credit_left <- groups[[index]]$withholding
   for (bucket in c("capital_general","capital_equity")) {
    s <- groups[[index]][[bucket]]
    base_tax <- if(s$base$sign>0L) mul(s$base,div(from(capital_rate),hundred)) else zero()
    credit <- minimum(base_tax,credit_left); credit_left <- minus(credit_left,credit)
    groups[[index]][[bucket]]$credit <- credit
    groups[[index]][[bucket]]$tax <- apply_tax_surcharges(minus(base_tax,credit),soli_rate,church)$total
   }
  }
  for (bucket in c("private_disposal","other_income")) {
   base_tax <- if(states[[bucket]]$base$sign>0L) mul(states[[bucket]]$base,div(from(personal_rate),hundred)) else zero()
   states[[bucket]]$tax <- apply_tax_surcharges(base_tax,soli_rate,church)$total
  }
 }
 for (bucket in c("capital_equity","capital_general")) {
  total <- list(positive=zero(),negative=zero(),net=zero(),opening=zero(),used=zero(),closing=zero(),base=zero(),allowance=zero(),tax=zero(),credit=zero())
  for (group in groups) for (field in names(total)) total[[field]] <- add(total[[field]],group[[bucket]][[field]])
  states[[bucket]] <- total
 }
 for (bucket in buckets) total_tax <- add(total_tax,states[[bucket]]$tax)
 # Die Rechnung je Institut und die der persoenlichen Toepfe in Schritten - fuer die Jahresrechnung, die sie zeigt.
 part <- function(s) list(positive_contribution_decimal=to(s$positive),negative_contribution_decimal=to(s$negative),net_contribution_decimal=to(s$net),
  opening_loss_carryforward_decimal=to(s$opening),used_loss_decimal=to(s$used),closing_loss_carryforward_decimal=to(s$closing),
  allowance_used_decimal=to(s$allowance),taxable_base_decimal=to(s$base),withholding_credit_decimal=to(s$credit),projected_annual_tax_decimal=if(blocked)NULL else to(s$tax))
 annual_detail <- list(tax_year=year,institution_grouping=grouped,
  institutions=lapply(seq_along(groups),function(index){g<-groups[[index]];list(institution_key=if(grouped)keys[[index]] else NULL,
   allowance_available_decimal=to(g$allowance),withholding_available_decimal=to(g$withholding),capital_equity=part(g$capital_equity),capital_general=part(g$capital_general))}),
  private_disposal=c(part(states$private_disposal),list(exemption_threshold_decimal=to(limits$private_disposal))),
  other_income=c(part(states$other_income),list(exemption_threshold_decimal=to(limits$other_income))))
 for(bucket in buckets){s<-states[[bucket]];total_positive<-add(total_positive,s$positive);total_negative<-add(total_negative,s$negative);total_net<-add(total_net,s$net);total_opening<-add(total_opening,s$opening);total_used<-add(total_used,s$used);total_closing<-add(total_closing,s$closing);total_allowance_used<-add(total_allowance_used,s$allowance)
  row<-list(tax_year=year,row_type="bucket",tax_bucket=bucket,currency=currency,positive_contribution_decimal=to(s$positive),negative_contribution_decimal=to(s$negative),net_contribution_decimal=to(s$net),opening_loss_carryforward_decimal=to(s$opening),used_loss_decimal=to(s$used),closing_loss_carryforward_decimal=to(s$closing),allowance_available_decimal=if(bucket%in%c("capital_equity","capital_general"))to(allowance) else "0",allowance_used_decimal=to(s$allowance),withholding_credit_decimal=to(s$credit),projected_annual_tax_decimal=if(blocked)NULL else to(s$tax),projected_net_gain_decimal=if(blocked)NULL else to(minus(s$net,s$tax)),defaulted_parameter_codes=paste(defaults,collapse="|"),projection_status=if(blocked)"blocked" else "completed",failure_code=failure)
  rows[[length(rows)+1L]]<-plugin_fields(row,parameter_fingerprint_value)
 }
 summary<-list(tax_year=year,row_type="summary",tax_bucket="all",currency=currency,positive_contribution_decimal=to(total_positive),negative_contribution_decimal=to(total_negative),net_contribution_decimal=to(total_net),opening_loss_carryforward_decimal=to(total_opening),used_loss_decimal=to(total_used),closing_loss_carryforward_decimal=to(total_closing),allowance_available_decimal=to(allowance),allowance_used_decimal=to(total_allowance_used),withholding_credit_decimal=to(add(states$capital_general$credit,states$capital_equity$credit)),projected_annual_tax_decimal=if(blocked)NULL else to(total_tax),projected_net_gain_decimal=if(blocked)NULL else to(minus(grossgain,total_tax)),defaulted_parameter_codes=paste(defaults,collapse="|"),projection_status=if(blocked)"blocked" else "completed",failure_code=failure)
 rows[[length(rows)+1L]]<-plugin_fields(summary,parameter_fingerprint_value)
} else if (identical(input$projection_mode,"unrealized_snapshot")) {
 # Die hypothetische Liquidation: Was waere zu zahlen, wenn der Bestand am
 # Stichtag verkauft wuerde. Gerechnet wird je Position, nicht je Jahr - eine
 # Jahresaggregation mit Freibetraegen und Verlustverrechnung waere hier eine
 # Scheingenauigkeit, weil der Verkauf gar nicht stattgefunden hat. Deshalb
 # ausdruecklich ohne Sparerpauschbetrag, ohne Verlustverrechnung und ohne
 # Freigrenze; der Ausweis heisst darum Schaetzung (#367 Schritt 2, 28.09.2026).
 year <- as.integer(substr(input$cutoff,1,4))
 for (source in input$rows) {
  gain <- from(source$unrealized_gross_gain_decimal)
  fee <- if (is.null(source$liquidation_fee_decimal)) zero() else from(source$liquidation_fee_decimal)
  cls <- classification(input,source,year)
  base <- list(position_ref=source$position_ref,asset_ref=source$asset_ref,account_ref=source$account_ref,
    currency=source$currency,as_of_date=input$cutoff,
    market_value_decimal=source$market_value_decimal,fifo_cost_decimal=source$fifo_cost_decimal,
    unrealized_gross_gain_decimal=source$unrealized_gross_gain_decimal,
    liquidation_fee_decimal=source$liquidation_fee_decimal,tax_year=year)
  blocked <- NULL; taxable <- zero(); code <- "not_applicable"; bucket <- "not_applicable"; exemption_text <- "0"
  # Ohne Gewinn faellt keine Steuer an - und dann braucht es weder Einordnung
  # noch Haltedauer noch Satz. Das ist nicht Nachsicht, sondern die Rechnung:
  # Es gibt nichts zu besteuern. Eine Blockade hier haette den Abschluss
  # angehalten, obwohl das Ergebnis feststeht (#367 Schritt 2, 28.09.2026).
  # Privates Veraeusserungsgut rechnet je Kauflot (Festlegung 21.10.2026): Ein Gewinn der Lose in der Jahresfrist ist
  # steuerbar, auch wenn aeltere, steuerfreie Lose die Position insgesamt ins Minus ziehen. Dort entscheidet also nicht
  # der Gewinn der ganzen Position.
  private <- !is.null(cls) && identical(cls$classification_code,"de_private_disposal_asset")
  settled <- gain$sign <= 0L && !private
  if (!settled && !year_covered(year)) blocked <- "tax_year_rules_missing"
  if (!settled && is.null(blocked) && is.null(cls)) blocked <- "tax_classification_required"
  if (!settled && is.null(blocked) && identical(cls$classification_code,"de_fund") && old_fund_shares(input$cutoff, source$remaining_lots))
   blocked <- "tax_fund_old_investment_tax_act"
  if (!settled && is.null(blocked)) {
   code <- cls$classification_code; bucket <- cls$tax_bucket; exemption_text <- cls$partial_exemption_rate_decimal
   model <- class_matrix[[code]]
   # Eine hypothetische Liquidation ist ein Verkauf. Was nicht verkauft werden
   # kann - Zinsen, Rewards -, hat auch keinen Liquidationsgewinn.
   if (is.null(model) || !identical(model$bucket,bucket) || !("sell" %in% model$events) ||
       (identical(model$partial,"zero") && !identical(exemption_text,"0"))) blocked <- "tax_classification_invalid"
   if (is.null(blocked)) {
    # Die Veraeusserungskosten mindern den Gewinn; bei einem hypothetischen
    # Verkauf ist das die angenommene Liquidationsgebuehr.
    taxable <- minus(gain,fee)
    if (identical(code,"de_private_disposal_asset")) {
     lots <- source$remaining_lots
     if (is.null(lots) || !length(lots)) blocked <- "tax_holding_evidence_required" else {
      # Nur Lose innerhalb der Jahresfrist sind steuerbar (§ 23 EStG), je Kauflot
      # wie bei einem echten Verkauf: Der Erloes nach Gebuehr wird nach Menge auf
      # die Lose verteilt, steuerbar ist die Summe der Lotgewinne in der Frist
      # (Erloesanteil minus Anschaffungskosten des Loses). Bis 21.10.2026 wurde der
      # Gewinn der ganzen Position nach Menge zugeordnet; das traf Lose mit
      # verschiedenem Einstand nicht (Festlegung 21.10.2026).
      # Summe der Lotgewinne = Erloes * (Menge in der Frist / Gesamtmenge) - Kosten in der Frist; so zusammengefasst
      # rechnet das Modul einmal statt je Los mit grossen Bruechen.
      total <- zero(); inside <- zero(); inside_cost <- zero()
      for (lot in lots) {
       quantity <- from(lot$quantity_decimal); total <- add(total,quantity)
       if (input$cutoff <= anniversary(lot$acquisition_local_date)) {
        inside <- add(inside,quantity); inside_cost <- add(inside_cost,from(lot$fifo_cost_decimal))
       }
      }
      if (total$sign <= 0L) blocked <- "tax_holding_evidence_required" else {
       proceeds <- minus(from(source$market_value_decimal),fee)
       taxable <- round_dec(minus(mul(proceeds,div(inside,total)),inside_cost))
      }
     }
    }
    if (is.null(blocked) && identical(model$partial,"asset")) taxable <- round_dec(mul(taxable,div(minus(hundred,from(exemption_text)),hundred)))
   }
  }
  tax <- NULL
  if (settled) tax <- zero() else if (is.null(blocked)) {
   if (taxable$sign>0L) {
    base_rate <- rate_value(year,rate_for(bucket))
    soli_rate <- rate_value(year,"solidarity_surcharge_rate")
    church <- church_policy(year)
    if (is.null(base_rate) || is.null(soli_rate)) blocked <- "tax_rate_required" else if (!is.null(church$blocked)) blocked <- church$blocked else {
     base_tax <- mul(taxable,div(from(base_rate),hundred)); tax <- round_dec(apply_tax_surcharges(base_tax,soli_rate,church)$total)
    }
   } else tax <- zero()
  }
  if (!is.null(blocked)) {
   row <- c(base,list(classification_code=if(is.null(cls))NULL else cls$classification_code,tax_bucket=if(is.null(cls))NULL else cls$tax_bucket,partial_exemption_rate_decimal=if(is.null(cls))NULL else cls$partial_exemption_rate_decimal,taxable_contribution_decimal=NULL,projected_unrealized_tax_decimal=NULL,projected_net_liquidation_decimal=NULL,projection_status="blocked",failure_code=blocked))
  } else {
   net <- minus(minus(gain,fee),tax)
   row <- c(base,list(classification_code=code,tax_bucket=bucket,partial_exemption_rate_decimal=exemption_text,taxable_contribution_decimal=to(taxable),projected_unrealized_tax_decimal=to(tax),projected_net_liquidation_decimal=to(net),projection_status="completed",failure_code=NULL))
  }
  rows[[length(rows)+1L]] <- plugin_fields(row,parameter_fingerprint_value)
 }
} else quit(status=22L)
# Welche Werte des Jahres galten und woher sie stammen - damit eine Rechnung je
# Ereignis den Satz und seine Herkunft nennen kann, ohne ihn zu erraten.
years_seen <- if (identical(input$projection_mode,"realized_event")) sort(unique(vapply(input$rows,function(x)as.integer(substr(x$local_date,1,4)),integer(1)))) else as.integer(substr(input$cutoff,1,4))
year_rule_codes <- list(
 list(code="capital_income_tax_rate",field="rate_decimal"),
 list(code="personal_income_tax_rate",field="rate_decimal"),
 list(code="solidarity_surcharge_rate",field="rate_decimal"),
 list(code="church_tax_rate",field="rate_decimal"),
 list(code="private_disposal_exemption_threshold",field="amount_decimal"),
 list(code="other_income_exemption_threshold",field="amount_decimal"))
year_rules <- lapply(years_seen,function(year) {
 values <- lapply(year_rule_codes,function(entry) {
  own <- param(input$parameters,year,entry$code,entry$field); module <- legal(year,entry$code)
  list(value_code=entry$code,value_decimal=if(!is.null(own))own else module,
   value_origin=if(!is.null(own))"user_parameter" else if(!is.null(module))"module_year_value" else "missing")
 })
 list(tax_year=year,module_covers_year=year_covered(year),
  church_tax_applicability=param(input$parameters,year,"church_tax_applicable","applicability_value"),values=values)
})
result<-list(api_version="tax_model_plugin_v1",plugin_id=Sys.getenv("PORTELYRA_TAX_PLUGIN_ID"),plugin_version=Sys.getenv("PORTELYRA_TAX_PLUGIN_VERSION"),rules_fingerprint=Sys.getenv("PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT"),projection_mode=input$projection_mode,status="completed",rows=rows,reconciliation=list(row_count=length(rows),arithmetic="exact_rational",model_scope="non_binding_german_reference_v2",church_tax_basis="projected_income_tax",church_tax_identity_inference=FALSE,event_tax_is_annual_tax=FALSE,year_rules=year_rules),disclaimer_codes=list("model_projection_not_legal_advice","reference_model_no_automatic_legal_update","church_tax_user_confirmation_only"))
if (!is.null(annual_detail)) result$reconciliation$annual_detail <- annual_detail
write_json(result,file.path(args[[2]],"tax-plugin-output.json"),auto_unbox=TRUE,null="null",digits=NA,pretty=FALSE)
