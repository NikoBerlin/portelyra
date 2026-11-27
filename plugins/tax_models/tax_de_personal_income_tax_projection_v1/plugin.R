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
 found <- Filter(function(x) identical(as.integer(x$tax_year),as.integer(year)) && identical(x$parameter_code,code),parameters)
 if (!length(found) || is.null(found[[1]][[field]])) NULL else found[[1]][[field]]
}
plugin_fields <- function(row) {
 row$plugin_id <- Sys.getenv("PORTELYRA_TAX_PLUGIN_ID")
 row$plugin_version <- Sys.getenv("PORTELYRA_TAX_PLUGIN_VERSION")
 row$rules_fingerprint <- Sys.getenv("PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT")
 row$disclaimer_code <- "model_projection_not_legal_advice"
 row
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
 de_equity_share=list(bucket="capital_equity",events=c("sell","dividend"),partial="zero"),
 de_capital_instrument=list(bucket="capital_general",events=c("sell","dividend","interest"),partial="zero"),
 de_cash_interest=list(bucket="capital_general",events=c("interest"),partial="zero"),
 de_fund=list(bucket="capital_general",events=c("sell","dividend"),partial="asset"),
 de_private_disposal_asset=list(bucket="private_disposal",events=c("sell"),partial="zero"),
 de_other_income_asset=list(bucket="other_income",events=c("reward","interest"),partial="zero")
)
rule_for <- function(code,event) {
 paste(code,event,sep="_")
}
rate_for <- function(bucket) if (bucket %in% c("capital_equity","capital_general")) "capital_income_tax_rate" else "personal_income_tax_rate"
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
 result
}
args <- commandArgs(trailingOnly=TRUE)
input <- fromJSON(args[[1]],simplifyVector=FALSE)
rows <- list()
if (identical(input$projection_mode,"realized_event")) {
 for (source in input$rows) {
  year <- as.integer(substr(source$local_date,1,4))
  gross <- economic_gross(source)
  relevant <- source$event_type %in% c("sell","dividend","interest","reward") && !.ed_rat_is_zero_v1(gross)
  cls <- if (relevant) classification(input,source,year) else NULL
  base <- list(event_ref=source$event_ref,effective_at_utc=source$effective_at_utc,local_date=source$local_date,event_type=source$event_type,account_ref=source$account_ref,asset_ref=source$asset_ref,currency=source$currency,gross_proceeds_decimal=source$gross_proceeds_decimal,realized_gross_gain_decimal=source$realized_gross_gain_decimal,gross_income_decimal=source$gross_income_decimal,fee_decimal=source$fee_decimal,tax_year=year)
  blocked <- NULL; taxable <- zero(); code <- "not_applicable"; bucket <- "not_applicable"; exemption_text <- "0"
  if (relevant && is.null(cls)) blocked <- "tax_classification_required"
  if (relevant && is.null(blocked)) {
   code <- cls$classification_code; bucket <- cls$tax_bucket; exemption_text <- cls$partial_exemption_rate_decimal
   model <- class_matrix[[code]]
   if (is.null(model) || !identical(model$bucket,bucket) || !(source$event_type %in% model$events) || (identical(model$partial,"zero") && !identical(exemption_text,"0"))) blocked <- "tax_classification_invalid"
   if (is.null(blocked)) {
    taxable <- if (identical(code,"de_private_disposal_asset")) private_contribution(source) else gross
    if (is.null(taxable)) blocked <- "tax_holding_evidence_required"
    if (is.null(blocked) && identical(model$partial,"asset")) taxable <- mul(taxable,div(minus(hundred,from(exemption_text)),hundred))
   }
  }
  tax <- NULL
  if (is.null(blocked)) {
   if (taxable$sign>0L) {
    base_rate <- param(input$parameters,year,rate_for(bucket),"rate_decimal")
    soli_rate <- param(input$parameters,year,"solidarity_surcharge_rate","rate_decimal")
    if (is.null(base_rate) || is.null(soli_rate)) blocked <- "tax_rate_required" else {
     base_tax <- mul(taxable,div(from(base_rate),hundred)); tax <- add(base_tax,mul(base_tax,div(from(soli_rate),hundred)))
    }
   } else tax <- zero()
  }
  if (!is.null(blocked)) {
   row <- c(base,list(classification_code=if(is.null(cls))NULL else cls$classification_code,tax_bucket=if(is.null(cls))NULL else cls$tax_bucket,partial_exemption_rate_decimal=if(is.null(cls))NULL else cls$partial_exemption_rate_decimal,taxable_contribution_decimal=NULL,projected_event_tax_decimal=NULL,projected_net_gain_decimal=NULL,projected_net_proceeds_decimal=NULL,projection_status="blocked",failure_code=blocked))
  } else {
   row <- c(base,list(classification_code=code,tax_bucket=bucket,partial_exemption_rate_decimal=exemption_text,taxable_contribution_decimal=to(taxable),projected_event_tax_decimal=to(tax),projected_net_gain_decimal=to(minus(gross,tax)),projected_net_proceeds_decimal=to(minus(add(from(source$gross_proceeds_decimal),from(source$gross_income_decimal)),tax)),projection_status="completed",failure_code=NULL))
  }
  rows[[length(rows)+1L]] <- plugin_fields(row)
 }
} else if (identical(input$projection_mode,"realized_annual")) {
 year <- as.integer(input$cutoff)
 currencies <- unique(vapply(input$rows,function(x)x$currency,character(1)))
 currency <- if (length(currencies)) currencies[[1]] else "EUR"
 buckets <- c("capital_equity","capital_general","private_disposal","other_income")
 optional <- c("capital_income_allowance","externally_used_capital_income_allowance","private_disposal_exemption_threshold","creditable_foreign_withholding_tax","opening_equity_loss_carryforward","opening_general_capital_loss_carryforward","opening_private_disposal_loss_carryforward","opening_other_income_loss_carryforward")
 defaults <- optional[vapply(optional,function(code)is.null(param(input$parameters,year,code,"amount_decimal")),logical(1))]
 amount <- function(code){value<-param(input$parameters,year,code,"amount_decimal");from(if(is.null(value))"0" else value)}
 opening_codes <- c(capital_equity="opening_equity_loss_carryforward",capital_general="opening_general_capital_loss_carryforward",private_disposal="opening_private_disposal_loss_carryforward",other_income="opening_other_income_loss_carryforward")
 states <- list(); grossgain <- zero()
 for (event in input$rows) grossgain <- add(grossgain,add(from(event$realized_gross_gain_decimal),from(event$gross_income_decimal)))
 for (bucket in buckets) {
  selected <- Filter(function(x) identical(x$tax_bucket,bucket),input$rows); positive<-zero();negative<-zero()
  for(event in selected){v<-from(event$taxable_contribution_decimal);if(v$sign<0L)negative<-add(negative,v) else positive<-add(positive,v)}
  opening<-amount(opening_codes[[bucket]]);net<-minus(add(positive,negative),opening);used<-minimum(positive,add(opening,if(negative$sign<0L).ed_rat_neg_v1(negative) else zero()));closing<-if(net$sign<0L).ed_rat_neg_v1(net) else zero();base<-nonneg(net)
  states[[bucket]]<-list(positive=positive,negative=negative,net=add(positive,negative),opening=opening,used=used,closing=closing,base=base,allowance=zero(),tax=zero())
 }
 allowance <- nonneg(minus(amount("capital_income_allowance"),amount("externally_used_capital_income_allowance")))
 remaining_allowance <- allowance
 for(bucket in c("capital_general","capital_equity")){used<-minimum(states[[bucket]]$base,remaining_allowance);states[[bucket]]$allowance<-used;states[[bucket]]$base<-minus(states[[bucket]]$base,used);remaining_allowance<-minus(remaining_allowance,used)}
 threshold<-amount("private_disposal_exemption_threshold")
 if(threshold$sign>0L && .ed_rat_cmp_v1(states$private_disposal$base,threshold)<=0L) states$private_disposal$base<-zero()
 applicable_capital <- states$capital_equity$base$sign>0L || states$capital_general$base$sign>0L
 applicable_personal <- states$private_disposal$base$sign>0L || states$other_income$base$sign>0L
 capital_rate<-param(input$parameters,year,"capital_income_tax_rate","rate_decimal");personal_rate<-param(input$parameters,year,"personal_income_tax_rate","rate_decimal");soli_rate<-param(input$parameters,year,"solidarity_surcharge_rate","rate_decimal")
 blocked <- length(currencies)>1L || (applicable_capital && is.null(capital_rate)) || (applicable_personal && is.null(personal_rate)) || ((applicable_capital||applicable_personal)&&is.null(soli_rate))
 failure <- if(length(currencies)>1L)"tax_currency_conflict" else if(blocked)"tax_rate_required" else NULL
 total_tax<-zero();total_positive<-zero();total_negative<-zero();total_net<-zero();total_opening<-zero();total_used<-zero();total_closing<-zero();total_allowance_used<-zero()
 if(!blocked){
  for(bucket in buckets){rate<-if(bucket%in%c("capital_equity","capital_general"))capital_rate else personal_rate;base_tax<-if(states[[bucket]]$base$sign>0L)mul(states[[bucket]]$base,div(from(rate),hundred)) else zero();states[[bucket]]$tax<-add(base_tax,mul(base_tax,div(from(soli_rate),hundred)));total_tax<-add(total_tax,states[[bucket]]$tax)}
  total_tax<-nonneg(minus(total_tax,amount("creditable_foreign_withholding_tax")))
 }
 for(bucket in buckets){s<-states[[bucket]];total_positive<-add(total_positive,s$positive);total_negative<-add(total_negative,s$negative);total_net<-add(total_net,s$net);total_opening<-add(total_opening,s$opening);total_used<-add(total_used,s$used);total_closing<-add(total_closing,s$closing);total_allowance_used<-add(total_allowance_used,s$allowance)
  row<-list(tax_year=year,row_type="bucket",tax_bucket=bucket,currency=currency,positive_contribution_decimal=to(s$positive),negative_contribution_decimal=to(s$negative),net_contribution_decimal=to(s$net),opening_loss_carryforward_decimal=to(s$opening),used_loss_decimal=to(s$used),closing_loss_carryforward_decimal=to(s$closing),allowance_available_decimal=if(bucket%in%c("capital_equity","capital_general"))to(allowance) else "0",allowance_used_decimal=to(s$allowance),withholding_credit_decimal="0",projected_annual_tax_decimal=if(blocked)NULL else to(s$tax),projected_net_gain_decimal=if(blocked)NULL else to(minus(s$net,s$tax)),defaulted_parameter_codes=paste(defaults,collapse="|"),projection_status=if(blocked)"blocked" else "completed",failure_code=failure)
  rows[[length(rows)+1L]]<-plugin_fields(row)
 }
 summary<-list(tax_year=year,row_type="summary",tax_bucket="all",currency=currency,positive_contribution_decimal=to(total_positive),negative_contribution_decimal=to(total_negative),net_contribution_decimal=to(total_net),opening_loss_carryforward_decimal=to(total_opening),used_loss_decimal=to(total_used),closing_loss_carryforward_decimal=to(total_closing),allowance_available_decimal=to(allowance),allowance_used_decimal=to(total_allowance_used),withholding_credit_decimal=to(amount("creditable_foreign_withholding_tax")),projected_annual_tax_decimal=if(blocked)NULL else to(total_tax),projected_net_gain_decimal=if(blocked)NULL else to(minus(grossgain,total_tax)),defaulted_parameter_codes=paste(defaults,collapse="|"),projection_status=if(blocked)"blocked" else "completed",failure_code=failure)
 rows[[length(rows)+1L]]<-plugin_fields(summary)
} else quit(status=22L)
result<-list(api_version="tax_model_plugin_v1",plugin_id=Sys.getenv("PORTELYRA_TAX_PLUGIN_ID"),plugin_version=Sys.getenv("PORTELYRA_TAX_PLUGIN_VERSION"),rules_fingerprint=Sys.getenv("PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT"),projection_mode=input$projection_mode,status="completed",rows=rows,reconciliation=list(row_count=length(rows),arithmetic="exact_rational",model_scope="non_binding_german_reference_v1",event_tax_is_annual_tax=FALSE),disclaimer_codes=list("model_projection_not_legal_advice","reference_model_no_automatic_legal_update"))
write_json(result,file.path(args[[2]],"tax-plugin-output.json"),auto_unbox=TRUE,null="null",digits=NA,pretty=FALSE)
