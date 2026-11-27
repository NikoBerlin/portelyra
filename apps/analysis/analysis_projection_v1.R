# Reiter "Projektion" der Analyse (#494): Was ein Teilverkauf zu einem gewaehlten Kurs ergaebe und was ein Zukauf aus dem
# Einstandskurs macht. Die Veroeffentlichung traegt je Asset die offenen Lose in FIFO-Folge, den Gebuehrensatz und die
# Steuersaetze des Jahresmoduls; hier wird daraus nur gerechnet, was Menge mal Kurs ergibt (Festlegung 21.10.2026).
#
# Verkauf: FIFO vom aeltesten offenen Los an, Teil-Lose anteilig. Erloes nach Gebuehr wird nach Menge auf die Lose verteilt;
# steuerbar ist bei Aktien und Kapitalanlagen der Gewinn (Fonds nach Teilfreistellung), bei privatem Veraeusserungsgut die
# Summe der Lotgewinne in der Jahresfrist. Ein Verlust traegt die Steuer null (je Ereignis, ohne Freibetrag und Verrechnung).
# Gewinn blau, Verlust rot; Grenzen der Lose gepunktet. Der FIFO-Stand fuehrt die Lose je Konto (walletbezogen, seit rc.245):
# Ein Verkauf verbraucht nur die Lose der Wallet, von der er abgeht. Die Projektion rechnet deshalb je Konto (rc.294); bei der
# Durchschnittsmethode tragen alle Lose der Wallet denselben Stueckpreis, die Haltefrist folgt weiter der FIFO-Folge.

ANALYSIS_PROJECTION_MODES_V1 <- c("Verkauf" = "sell", "Zukauf" = "buy")

analysis_projection_choices_v1 <- function(history) {
  held <- Filter(function(asset) !is.null(asset$projection) && length(asset$projection$accounts), history$assets)
  if (!length(held)) return(c("Kein Asset im Bestand" = ""))
  value <- vapply(held, function(asset) analysis_history_number_v1(list(asset$projection$price)) * analysis_history_number_v1(list(asset$projection$quantity)),
                  numeric(1L))
  order <- order(-ifelse(is.na(value), -Inf, value))
  stats::setNames(vapply(held[order], function(asset) as.character(asset$ordinal), character(1L)), vapply(held[order], function(asset) asset$label, character(1L)))
}

analysis_projection_of_v1 <- function(history, choice) {
  if (is.null(history) || !is.character(choice) || !nzchar(choice)) return(NULL)
  hit <- Filter(function(asset) identical(as.character(asset$ordinal), choice) && !is.null(asset$projection), history$assets)
  if (length(hit) != 1L) NULL else hit[[1L]]
}

ANALYSIS_PROJECTION_METHODS_V1 <- c(fifo = "FIFO", average = "Durchschnitt")

# Die Konten eines Assets zur Wahl: groesster Bestand zuerst, mit Menge und Methode.
analysis_projection_account_choices_v1 <- function(asset) {
  accounts <- if (is.null(asset)) list() else asset$projection$accounts
  if (!length(accounts)) return(c("Kein Konto mit Bestand" = ""))
  stats::setNames(as.character(seq_along(accounts)), vapply(accounts, function(account) sprintf("%s · %s Stück · %s", account$account,
    .analysis_history_quantity_v1(signif(analysis_history_number_v1(list(account$quantity)), 10)), ANALYSIS_PROJECTION_METHODS_V1[[account$method]]), character(1L)))
}

# Die Projektion fuer ein Konto: Kurs, Gebuehr und Steuer des Assets, Lose und Methode der Wallet.
analysis_projection_for_account_v1 <- function(projection, choice) {
  accounts <- projection$accounts
  index <- if (is.character(choice) && length(choice) == 1L) suppressWarnings(as.integer(choice)) else NA_integer_
  if (!length(accounts)) return(NULL)
  if (is.na(index) || index < 1L || index > length(accounts)) index <- 1L
  account <- accounts[[index]]
  c(projection[setdiff(names(projection), "accounts")], list(lots = account$lots, account = account$account, method = account$method,
                                                             account_quantity = account$quantity, account_count = length(accounts)))
}

analysis_projection_lots_v1 <- function(projection) {
  lots <- projection$lots
  data.frame(acquired = as.Date(vapply(lots, function(lot) if (is.null(lot$acquired)) NA_character_ else lot$acquired, character(1L))),
             quantity = analysis_history_number_v1(lapply(lots, function(lot) lot$quantity)),
             basis = analysis_history_number_v1(lapply(lots, function(lot) lot$basis)),
             free_from = as.Date(vapply(lots, function(lot) if (is.null(lot$free_from)) NA_character_ else lot$free_from, character(1L))),
             stringsAsFactors = FALSE)
}

.analysis_projection_tax_v1 <- function(projection, taxable) {
  tax <- projection$tax
  if (!identical(tax$status, "ready") || is.na(taxable)) return(NA_real_)
  if (taxable <= 0) return(0)
  rate <- analysis_history_number_v1(list(tax$rate)); soli <- analysis_history_number_v1(list(tax$solidarity))
  church <- analysis_history_number_v1(list(tax$church)); if (is.na(church)) church <- 0
  taxable * rate / 100 * (1 + soli / 100 + church / 100)
}

# Ein Verkauf der Menge 'quantity' zum Kurs 'price': Erloes, Gebuehr, verbrauchter Einstand, GuV, projizierte Steuer, netto.
analysis_projection_sale_v1 <- function(projection, lots, price, quantity, with_fee = TRUE) {
  day <- as.Date(projection$day)
  fee_rate <- if (with_fee) analysis_history_number_v1(list(projection$fee_rate)) else 0
  if (is.na(fee_rate)) fee_rate <- 0
  gross <- quantity * price; fee <- gross * fee_rate / 100; proceeds <- gross - fee
  left <- quantity; basis <- 0; gain <- 0; inside_gain <- 0; used <- 0L; inside_used <- 0L; first <- NA; last <- NA
  # Die Jahresfrist zaehlt nur, wo das Modul sie kennt (privates Veraeusserungsgut).
  holding <- isTRUE(projection$tax$holding_period)
  for (index in seq_len(nrow(lots))) {
    if (left <= 0) break
    take <- min(left, lots$quantity[[index]])
    if (take <= 0) next
    part_basis <- lots$basis[[index]] * take / lots$quantity[[index]]
    part_gain <- (if (quantity > 0) proceeds * take / quantity else 0) - part_basis
    basis <- basis + part_basis; gain <- gain + part_gain; used <- used + 1L
    if (is.na(first)) first <- lots$acquired[[index]]
    last <- lots$acquired[[index]]
    inside <- holding && !is.na(lots$free_from[[index]]) && day < lots$free_from[[index]]
    if (inside) { inside_gain <- inside_gain + part_gain; inside_used <- inside_used + 1L }
    left <- left - take
  }
  tax_info <- projection$tax
  taxable <- if (!identical(tax_info$status, "ready")) NA_real_ else if (isTRUE(tax_info$holding_period)) inside_gain else
    gain * (100 - analysis_history_number_v1(list(tax_info$partial_exemption))) / 100
  tax <- .analysis_projection_tax_v1(projection, taxable)
  list(quantity = quantity, gross = gross, fee = fee, basis = basis, gain = gain, taxable = taxable, tax = tax, net = gain - tax,
       lots = used, inside = inside_used, first = as.Date(first, origin = "1970-01-01"), last = as.Date(last, origin = "1970-01-01"))
}

analysis_projection_curve_v1 <- function(projection, price, with_fee = TRUE, points = 240L) {
  lots <- analysis_projection_lots_v1(projection)
  total <- sum(lots$quantity)
  # Runde Schritte (etwa 'points' viele), dazu genau die Grenzen der Lose - so trifft der Zeiger glatte Mengen.
  marks <- pretty(c(0, total), n = points)
  step <- if (length(marks) > 1L) diff(marks)[[1L]] else total
  grid <- sort(unique(round(c(seq(0, total, by = step), total, cumsum(lots$quantity)), 12)))
  rows <- lapply(grid, function(quantity) analysis_projection_sale_v1(projection, lots, price, quantity, with_fee))
  frame <- data.frame(quantity = grid, gross = vapply(rows, function(row) row$gross, numeric(1L)), fee = vapply(rows, function(row) row$fee, numeric(1L)),
                      basis = vapply(rows, function(row) row$basis, numeric(1L)), gain = vapply(rows, function(row) row$gain, numeric(1L)),
                      tax = vapply(rows, function(row) row$tax, numeric(1L)), net = vapply(rows, function(row) row$net, numeric(1L)),
                      lots = vapply(rows, function(row) row$lots, integer(1L)), inside = vapply(rows, function(row) row$inside, integer(1L)))
  frame$first <- as.Date(vapply(rows, function(row) as.numeric(row$first), numeric(1L)), origin = "1970-01-01")
  frame$last <- as.Date(vapply(rows, function(row) as.numeric(row$last), numeric(1L)), origin = "1970-01-01")
  attr(frame, "boundaries") <- cumsum(lots$quantity)
  attr(frame, "inside_from") <- { inside <- isTRUE(projection$tax$holding_period) & !is.na(lots$free_from) & as.Date(projection$day) < lots$free_from
    if (any(inside)) sum(lots$quantity[seq_len(which(inside)[[1L]] - 1L)]) else NA_real_ }
  frame
}

analysis_projection_plot_v1 <- function(curve, projection) {
  ink <- ANALYSIS_HISTORY_INK_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(3.4, 7, 2.6, 9.5), mgp = c(2.2, 0.6, 0), tcl = -0.2)
  net_ready <- any(!is.na(curve$net))
  shown <- if (net_ready) curve$net else curve$gain
  span <- range(c(0, curve$gain, shown), na.rm = TRUE); if (!all(is.finite(span)) || diff(span) == 0) span <- c(-1, 1)
  span <- span + c(-1, 1) * diff(span) * 0.05
  graphics::plot(range(curve$quantity), span, type = "n", axes = FALSE, xlab = "", ylab = "")
  inside_from <- attr(curve, "inside_from")
  if (!is.na(inside_from)) graphics::rect(inside_from, span[[1L]], max(curve$quantity), span[[2L]], col = grDevices::adjustcolor(ink[["grid"]], 0.55), border = NA)
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_history_axis_eur_v1(at), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  xs <- pretty(range(curve$quantity), n = 6L)
  graphics::axis(1, at = xs, labels = formatC(xs, format = "fg", big.mark = ".", decimal.mark = ","), col = NA, col.ticks = ink[["baseline"]],
                 col.axis = ink[["secondary"]], cex.axis = 0.85)
  graphics::mtext("verkaufte Menge (FIFO vom ältesten Los an)", side = 1, line = 2.2, cex = 0.8, col = ink[["secondary"]])
  graphics::abline(v = attr(curve, "boundaries"), col = ink[["muted"]], lty = 3, lwd = 1)
  positive <- pmax(ifelse(is.na(shown), 0, shown), 0); negative <- pmin(ifelse(is.na(shown), 0, shown), 0)
  graphics::polygon(c(curve$quantity, rev(curve$quantity)), c(positive, rep(0, nrow(curve))), col = grDevices::adjustcolor(ANALYSIS_ASSETS_SIGN_V1[["gain"]], 0.25), border = NA)
  graphics::polygon(c(curve$quantity, rev(curve$quantity)), c(negative, rep(0, nrow(curve))), col = grDevices::adjustcolor(ANALYSIS_ASSETS_SIGN_V1[["loss"]], 0.25), border = NA)
  graphics::abline(h = 0, col = ink[["primary"]], lwd = 1.4)
  graphics::lines(curve$quantity, curve$gain, col = ANALYSIS_ASSETS_LINE_V1, lwd = 2, lty = if (net_ready) 2 else 1)
  if (net_ready) graphics::lines(curve$quantity, curve$net, col = ink[["primary"]], lwd = 2.2)
  last <- nrow(curve)
  labels <- if (net_ready) c("GuV brutto", "GuV netto") else "GuV brutto"
  values <- if (net_ready) c(curve$gain[[last]], curve$net[[last]]) else curve$gain[[last]]
  .analysis_history_end_labels_v1(curve$quantity[[last]], values, labels, if (net_ready) c(ANALYSIS_ASSETS_LINE_V1, ink[["primary"]]) else ANALYSIS_ASSETS_LINE_V1)
  graphics::mtext(paste0("GuV eines Verkaufs bis zur gewählten Menge · Fläche ", if (net_ready) "netto" else "brutto",
                         ": Gewinn blau, Verlust rot · gepunktet: Grenzen der Lose", if (!is.na(inside_from)) " · grau: Lose in der Jahresfrist (steuerpflichtig)" else ""),
                  side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

analysis_projection_rows_v1 <- function(curve, x) {
  row <- curve[which.min(abs(curve$quantity - x)), , drop = FALSE]
  lots <- if (row$lots == 0L) "–" else if (row$lots == 1L) paste("1 Los vom", format(row$first, "%d.%m.%Y")) else
    sprintf("%d Lose, %s bis %s", row$lots, format(row$first, "%d.%m.%Y"), format(row$last, "%d.%m.%Y"))
  rows <- list(list(label = "Erlös brutto", value = analysis_history_eur_v1(row$gross, 2L)),
               list(label = "Verkaufsgebühr (Projektion)", value = analysis_history_eur_v1(row$fee, 2L)),
               list(label = "Einstand der verkauften Lose", value = analysis_history_eur_v1(row$basis, 2L)),
               list(label = "GuV brutto", value = analysis_history_eur_signed_v1(row$gain, 2L), color = ANALYSIS_ASSETS_LINE_V1),
               list(label = "Steuer (Projektion)", value = if (is.na(row$tax)) "nicht verfügbar" else analysis_history_eur_v1(row$tax, 2L)),
               list(label = "GuV netto", value = if (is.na(row$net)) "nicht verfügbar" else analysis_history_eur_signed_v1(row$net, 2L), color = ANALYSIS_HISTORY_INK_V1[["primary"]]),
               list(label = "betroffene Lose", value = lots))
  if (row$inside > 0L) rows <- c(rows, list(list(label = "davon in der Jahresfrist", value = as.character(row$inside))))
  list(title = paste("Verkauf von", .analysis_history_quantity_v1(signif(row$quantity, 10)), "Stück"), rows = rows)
}

# Zukauf: neuer Bestand und Einstandskurs; Umkehrung: Welche Menge braucht ein angestrebter Einstandskurs? Seit #531 Punkt 4 auch
# fuer einen Betrag: Er schliesst die Gebuehr ein, gekauft wird Betrag / (Kurs × (1 + Gebuehr)).
analysis_projection_buy_v1 <- function(projection, price, quantity, target = NA_real_, with_fee = TRUE, amount = NA_real_) {
  lots <- analysis_projection_lots_v1(projection)
  held <- sum(lots$quantity); basis <- sum(lots$basis)
  fee_rate <- if (with_fee) analysis_history_number_v1(list(projection$fee_rate)) else 0
  if (is.na(fee_rate)) fee_rate <- 0
  unit_cost <- price * (1 + fee_rate / 100)
  average <- basis / held
  rows <- list(c("Bestand heute", paste(.analysis_history_quantity_v1(signif(held, 10)), "Stück")),
               c("Einstand heute", analysis_history_eur_v1(basis, 2L)),
               c("Einstandskurs heute", analysis_history_eur_v1(average, 2L)),
               c("Kurs der Projektion", analysis_history_eur_v1(price, 2L)))
  if (is.numeric(amount) && length(amount) == 1L && !is.na(amount) && amount > 0 && unit_cost > 0) {
    quantity <- amount / unit_cost
    rows <- c(rows, list(c("Betrag", paste0(analysis_history_eur_v1(amount, 2L), " (Gebühr eingeschlossen)"))))
  }
  if (!is.na(quantity) && quantity > 0) {
    capital <- quantity * unit_cost; new_average <- (basis + capital) / (held + quantity)
    rows <- c(rows, list(c("Zukauf", paste(.analysis_history_quantity_v1(signif(quantity, 10)), "Stück")),
                         c("Kapitaleinsatz", paste0(analysis_history_eur_v1(capital, 2L), if (with_fee) sprintf(" (davon Gebühr %s)", analysis_history_eur_v1(quantity * price * fee_rate / 100, 2L)) else "")),
                         c("Bestand danach", paste(.analysis_history_quantity_v1(signif(held + quantity, 10)), "Stück")),
                         c("Einstandskurs danach", analysis_history_eur_v1(new_average, 2L)),
                         c("Abstand zum Kurs", analysis_history_pct_v1(price / new_average - 1))))
  }
  if (!is.na(target) && target > 0) {
    denominator <- unit_cost - target
    needed <- if (abs(denominator) < 1e-12) NA_real_ else (target * held - basis) / denominator
    rows <- c(rows, list(c("Angestrebter Einstandskurs", analysis_history_eur_v1(target, 2L)),
      c("Nötiger Zukauf", if (is.na(needed) || needed <= 0)
        "zu diesem Kurs nicht erreichbar – der Ziel-Einstandskurs muss zwischen dem heutigen Einstandskurs und dem Kaufkurs (samt Gebühr) liegen"
        else sprintf("%s Stück für %s", .analysis_history_quantity_v1(signif(needed, 8)), analysis_history_eur_v1(needed * unit_cost, 2L)))))
  }
  data.frame(Angabe = vapply(rows, `[[`, character(1L), 1L), Wert = vapply(rows, `[[`, character(1L), 2L), stringsAsFactors = FALSE)
}

# Der Einstandskurs ueber der Zukaufmenge (#531 Punkt 4): Er naehert sich dem Kaufkurs samt Gebuehr, erreicht ihn aber nie. Die
# Achse laeuft in Stueck oder in Euro (Betrag samt Gebuehr) - fuer ein Budget liest man so direkt ab (Festlegung 03.11.2026).
analysis_projection_buy_plot_v1 <- function(projection, price, with_fee = TRUE, chosen = NA_real_, target = NA_real_, axis = "quantity") {
  ink <- ANALYSIS_HISTORY_INK_V1
  lots <- analysis_projection_lots_v1(projection); held <- sum(lots$quantity); basis <- sum(lots$basis)
  fee <- .analysis_projection_fee_v1(projection, with_fee); unit_cost <- price * (1 + fee)
  needed <- if (is.finite(target) && abs(unit_cost - target) > 1e-12) (target * held - basis) / (unit_cost - target) else NA_real_
  upper <- max(c(held * 2, if (is.finite(chosen) && chosen > 0) chosen * 1.5, if (is.finite(needed) && needed > 0) needed * 1.3), na.rm = TRUE)
  if (!is.finite(upper) || upper <= 0) upper <- 1
  euro <- identical(axis, "amount")
  grid <- seq(0, upper, length.out = 240L); average <- (basis + grid * unit_cost) / (held + grid)
  scale <- if (euro) unit_cost else 1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(3.4, 7, 2.2, 11), mgp = c(2.2, 0.6, 0), tcl = -0.2)
  span <- range(c(average, unit_cost, basis / held, if (is.finite(target)) target), na.rm = TRUE); span <- span + c(-1, 1) * max(diff(span), abs(span[[2L]]) * 0.02) * 0.08
  graphics::plot(range(grid) * scale, span, type = "n", axes = FALSE, xlab = "", ylab = "")
  digits <- .analysis_projection_digits_v1(unit_cost)
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_history_axis_eur_v1(at, digits), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  xs <- pretty(range(grid) * scale, n = 6L)
  graphics::axis(1, at = xs, labels = if (euro) analysis_history_eur_v1(xs, 0L) else formatC(xs, format = "fg", big.mark = ".", decimal.mark = ","),
                 col = NA, col.ticks = ink[["baseline"]], col.axis = ink[["secondary"]], cex.axis = 0.85)
  graphics::mtext(if (euro) "Zukauf als Betrag in € (Gebühr eingeschlossen)" else "Zukauf in Stück", side = 1, line = 2.2, cex = 0.8, col = ink[["secondary"]])
  graphics::abline(h = basis / held, col = ink[["secondary"]], lty = 2, lwd = 1.4)
  graphics::abline(h = unit_cost, col = ink[["muted"]], lty = 3, lwd = 1.6)
  if (is.finite(target)) graphics::abline(h = target, col = ink[["secondary"]], lty = 4, lwd = 1.4)
  graphics::lines(grid * scale, average, col = ink[["primary"]], lwd = 2.2)
  if (is.finite(chosen) && chosen > 0 && chosen <= upper)
    graphics::points(chosen * scale, (basis + chosen * unit_cost) / (held + chosen), pch = 21, cex = 1.5, lwd = 2, col = ink[["primary"]], bg = ink[["surface"]])
  labels <- c(paste("Einstandskurs heute", analysis_history_eur_v1(basis / held, digits)), paste("Kaufkurs samt Gebühr", analysis_history_eur_v1(unit_cost, digits)),
              if (is.finite(target)) paste("Ziel", analysis_history_eur_v1(target, digits)))
  .analysis_history_end_labels_v1(upper * scale, c(basis / held, unit_cost, if (is.finite(target)) target), labels,
                                  c(ink[["secondary"]], ink[["muted"]], if (is.finite(target)) ink[["secondary"]]))
  graphics::mtext("Einstandskurs nach dem Zukauf · gestrichelt: heute · gepunktet: Kaufkurs samt Gebühr (wird nie erreicht) · Zeiger: Kosten und Einstand je Menge",
                  side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(c(.analysis_history_geometry_v1(), list(axis = if (euro) "amount" else "quantity", upper = upper * scale)))
}

# Der Zeiger im Zukauf-Bild: was die Menge (oder der Betrag) am Zeiger kostet und was sie aus dem Einstand macht.
analysis_projection_buy_rows_v1 <- function(projection, price, with_fee, x, axis = "quantity") {
  lots <- analysis_projection_lots_v1(projection); held <- sum(lots$quantity); basis <- sum(lots$basis)
  fee <- .analysis_projection_fee_v1(projection, with_fee); unit_cost <- price * (1 + fee); digits <- .analysis_projection_digits_v1(price)
  quantity <- max(0, if (identical(axis, "amount")) x / unit_cost else x); capital <- quantity * unit_cost
  average <- (basis + capital) / (held + quantity)
  list(title = paste("Zukauf von", .analysis_history_quantity_v1(signif(quantity, 6)), "Stück zu", analysis_history_eur_v1(price, digits)),
       rows = list(list(label = "Kapitaleinsatz", value = paste0(analysis_history_eur_v1(capital, 2L), if (fee > 0) sprintf(" (davon Gebühr %s)", analysis_history_eur_v1(quantity * price * fee, 2L)) else "")),
                   list(label = "Bestand danach", value = paste(.analysis_history_quantity_v1(signif(held + quantity, 10)), "Stück")),
                   list(label = "Einstand danach", value = analysis_history_eur_v1(basis + capital, 2L)),
                   list(label = "Einstandskurs danach", value = analysis_history_eur_v1(average, digits), color = ANALYSIS_HISTORY_INK_V1[["primary"]]),
                   list(label = "Einstandskurs heute", value = analysis_history_eur_v1(basis / held, digits)),
                   list(label = "Kurs gegenüber neuem Einstandskurs", value = analysis_history_pct_v1(price / average - 1))))
}

# --- Fragen an einen Verkauf (#531 Punkt 4) -----------------------------------------------------------------------------------
# Festlegung (03.11.2026): Zielkurs per Schalter so, dass a) das teuerste Los ±0 abgeht (kein Los im Minus), b) alle Lose
# zusammen ±0 (Einstand) oder c) eine angestrebte GuV in € oder als einfache Rendite entsteht - brutto oder netto, mit oder ohne
# Gebuehr. Dazu: Menge fuer einen Erloes, Haltefrist, derselbe Verkauf aus jedem Konto, Kursverlauf mit den Zielkursen.
ANALYSIS_PROJECTION_SELL_QUESTIONS_V1 <- c("Ergebnis bei Kurs und Menge" = "curve", "Zielkurs" = "target", "Menge für einen Erlös" = "proceeds",
                                           "Haltefrist" = "holding", "Konten vergleichen" = "accounts")
ANALYSIS_PROJECTION_BUY_QUESTIONS_V1 <- c("Stückzahl" = "quantity", "Betrag" = "amount", "Ziel-Einstandskurs" = "average")
ANALYSIS_PROJECTION_VIEWS_V1 <- c("netto (nach projizierter Steuer)" = "net", "brutto" = "gross")

.analysis_projection_fee_v1 <- function(projection, with_fee) {
  rate <- if (isTRUE(with_fee)) analysis_history_number_v1(list(projection$fee_rate)) else 0
  if (is.na(rate)) 0 else rate / 100
}
# Kurse unter 10 € mit vier, unter 1 € mit sechs Stellen - sonst sind Zielkurse kleiner Coins nicht zu unterscheiden.
.analysis_projection_digits_v1 <- function(value) if (!is.finite(value)) 2L else if (abs(value) < 1) 6L else if (abs(value) < 10) 4L else 2L

# Die Menge eines Verkaufs: leer, null oder mehr als der Bestand heisst alles.
analysis_projection_quantity_v1 <- function(lots, quantity) {
  total <- sum(lots$quantity)
  if (!is.numeric(quantity) || length(quantity) != 1L || is.na(quantity) || quantity <= 0 || quantity >= total) total else quantity
}

# Die verkauften Teile der Lose in FIFO-Folge, mit Einstand je Stueck.
analysis_projection_consumed_v1 <- function(lots, quantity) {
  left <- quantity; take <- numeric(nrow(lots))
  for (index in seq_len(nrow(lots))) { if (left <= 0) break; take[[index]] <- min(left, lots$quantity[[index]]); left <- left - take[[index]] }
  used <- take > 0
  data.frame(acquired = lots$acquired[used], take = take[used], unit = lots$basis[used] / lots$quantity[used], free_from = lots$free_from[used])
}

# Halbierung fuer eine steigende Funktion: das kleinste x zwischen lo und hi mit fn(x) >= goal; 'grow' verdoppelt hi bis dahin.
.analysis_projection_solve_v1 <- function(fn, goal, lo, hi, grow = TRUE) {
  if (!is.finite(goal)) return(NA_real_)
  if (fn(lo) >= goal) return(lo)
  if (grow) for (step in 1:80) { if (fn(hi) >= goal) break; hi <- hi * 2 }
  if (fn(hi) < goal) return(NA_real_)
  for (step in 1:200) { mid <- (lo + hi) / 2; if (fn(mid) >= goal) hi <- mid else lo <- mid; if (hi - lo <= 1e-12 * max(1, abs(hi))) break }
  hi
}

# Zielkurse fuer den Verkauf von 'quantity' Stueck (leer: alles). Netto rechnet mit der projizierten Steuer des Jahresmoduls; bei a)
# ist das derselbe Kurs, denn ein Los bei ±0 traegt keine Steuer. 'goal' ist die angestrebte GuV in € oder in % des Einstands.
analysis_projection_targets_v1 <- function(projection, quantity = NA_real_, with_fee = TRUE, view = "net", goal = NA_real_, goal_kind = "eur") {
  lots <- analysis_projection_lots_v1(projection); quantity <- analysis_projection_quantity_v1(lots, quantity)
  used <- analysis_projection_consumed_v1(lots, quantity); fee <- .analysis_projection_fee_v1(projection, with_fee)
  basis <- sum(used$take * used$unit); net <- identical(view, "net"); taxed <- identical(projection$tax$status, "ready")
  value <- function(price) { sale <- analysis_projection_sale_v1(projection, lots, price, quantity, with_fee); if (net) sale$net else sale$gain }
  solve <- function(target) {
    if (!is.finite(target) || target < -basis) return(NA_real_)
    if (!net) return((basis + target) / (quantity * (1 - fee)))
    if (!taxed) return(NA_real_)
    .analysis_projection_solve_v1(value, target, 0, max(basis / quantity / (1 - fee), 1e-9) * 2)
  }
  aim <- if (!is.numeric(goal) || length(goal) != 1L || is.na(goal)) NA_real_ else if (identical(goal_kind, "pct")) basis * goal / 100 else goal
  list(quantity = quantity, total = sum(lots$quantity), basis = basis, lots = nrow(used), fee = fee, net = net, taxed = taxed,
       worst = if (nrow(used)) max(used$unit) / (1 - fee) else NA_real_, even = solve(0), aim = aim, goal_kind = goal_kind, goal_input = goal,
       goal = solve(aim))
}

analysis_projection_targets_table_v1 <- function(targets, price) {
  digits <- .analysis_projection_digits_v1(price)
  missing <- if (targets$net && !targets$taxed) "nicht verfügbar – ohne Steuersätze nur brutto" else "–"
  show <- function(value) if (is.finite(value)) analysis_history_eur_v1(value, digits) else missing
  gap <- function(value) if (is.finite(value) && is.finite(price) && price > 0) analysis_history_pct_v1(value / price - 1) else "–"
  sight <- if (targets$net) "netto" else "brutto"
  goal_text <- if (!is.finite(targets$aim)) "c) Angestrebte GuV – Ziel eintragen" else
    paste0("c) GuV ", sight, " ", if (identical(targets$goal_kind, "pct")) paste0(formatC(targets$goal_input, format = "fg", decimal.mark = ","), " % (",
           analysis_history_eur_signed_v1(targets$aim, 2L), ")") else analysis_history_eur_signed_v1(targets$aim, 2L))
  rows <- list(
    list("a) Kein Los im Minus", targets$worst, "Ab diesem Kurs geht auch das teuerste verkaufte Los ohne Verlust ab: sein Einstand je Stück ÷ (1 − Gebühr). Brutto und netto gleich – ein Los bei ±0 trägt keine Steuer."),
    list(paste("b) Alle verkauften Lose zusammen ±0,", sight), targets$even, if (targets$net)
      "GuV nach projizierter Steuer null. Bei Krypto zählt nur, was in der Jahresfrist liegt – ein Gewinn dort kostet Steuer, auch wenn ältere Lose im Minus sind." else
      "Erlös nach Gebühr gleich dem Einstand der verkauften Lose."),
    list(goal_text, if (is.finite(targets$aim)) targets$goal else NA_real_, if (identical(targets$goal_kind, "pct")) "Einfache Rendite auf den Einstand der verkauften Lose." else "GuV des Verkaufs in Euro."))
  data.frame(Zielkurs = vapply(rows, function(row) row[[1L]], character(1L)),
             `Kurs je Einheit` = vapply(rows, function(row) if (grepl("Ziel eintragen", row[[1L]], fixed = TRUE)) "–" else show(row[[2L]]), character(1L)),
             `Abstand zum Kurs` = vapply(rows, function(row) gap(row[[2L]]), character(1L)),
             Erläuterung = vapply(rows, function(row) row[[3L]], character(1L)), check.names = FALSE, stringsAsFactors = FALSE)
}

analysis_projection_targets_text_v1 <- function(targets, price) {
  paste0("Verkauf von ", .analysis_history_quantity_v1(signif(targets$quantity, 10)), " Stück", if (targets$quantity < targets$total) "" else " (alles)",
         " aus ", targets$lots, if (targets$lots == 1L) " Los" else " Losen", ", Einstand ", analysis_history_eur_v1(targets$basis, 2L),
         ", Gebühr ", formatC(targets$fee * 100, format = "f", digits = 3, decimal.mark = ","), " % · Kurs der Projektion ",
         analysis_history_eur_v1(price, .analysis_projection_digits_v1(price)), ".")
}

# Der Kurs des letzten Jahres mit dem Kurs der Projektion und den Zielkursen als waagerechte Linien, rechts beschriftet mit dem Abstand.
analysis_projection_price_plot_v1 <- function(series, price, targets) {
  ink <- ANALYSIS_HISTORY_INK_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.6, 7, 2.2, 13), mgp = c(3, 0.6, 0), tcl = -0.2)
  marks <- c(Kurs = price, `a) kein Los im Minus` = targets$worst, `b) alle Lose ±0` = targets$even, `c) Ziel` = targets$goal)
  marks <- marks[is.finite(marks)]
  have <- !is.null(series) && nrow(series) > 1L && any(!is.na(series$price))
  days <- if (have) series$day else as.Date(c(Sys.Date() - 365, Sys.Date()))
  span <- range(c(if (have) series$price, marks), na.rm = TRUE); span <- span + c(-1, 1) * max(diff(span), abs(span[[2L]]) * 0.02) * 0.08
  graphics::plot(range(days), span, type = "n", axes = FALSE, xlab = "", ylab = "")
  digits <- .analysis_projection_digits_v1(price)
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_history_axis_eur_v1(at, digits), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  .analysis_history_axis_dates_v1(days)
  styles <- c(Kurs = 1L, `a) kein Los im Minus` = 2L, `b) alle Lose ±0` = 3L, `c) Ziel` = 4L)
  for (name in names(marks)) graphics::abline(h = marks[[name]], col = if (identical(name, "Kurs")) ink[["primary"]] else ink[["secondary"]], lty = styles[[name]], lwd = 1.5)
  if (have) .analysis_history_line_v1(series$day, series$price, ANALYSIS_ASSETS_LINE_V1)
  labels <- vapply(names(marks), function(name) paste0(name, " ", analysis_history_eur_v1(marks[[name]], digits),
    if (identical(name, "Kurs")) "" else paste0(" (", analysis_history_pct_v1(marks[[name]] / price - 1), ")")), character(1L))
  .analysis_history_end_labels_v1(max(days), unname(marks), labels, ifelse(names(marks) == "Kurs", ink[["primary"]], ink[["secondary"]]))
  graphics::mtext(if (have) "Kurs je Einheit im letzten Jahr, waagerecht: Kurs der Projektion und Zielkurse · Zeiger: Abstand des Tageskurses zu jedem Zielkurs" else "Ohne Kursverlauf: nur Kurs der Projektion und Zielkurse",
                  side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

# Der Zeiger im Kursbild: Kurs des Tages und wie weit jeder Zielkurs davon entfernt ist.
analysis_projection_price_rows_v1 <- function(series, price, targets, x) {
  if (is.null(series) || !nrow(series)) return(NULL)
  row <- series[which.min(abs(as.numeric(series$day) - x)), , drop = FALSE]
  if (is.na(row$price)) return(NULL)
  digits <- .analysis_projection_digits_v1(price)
  marks <- c(`Kurs der Projektion` = price, `a) kein Los im Minus` = targets$worst, `b) alle Lose ±0` = targets$even, `c) Ziel` = targets$goal)
  marks <- marks[is.finite(marks)]
  list(title = format(row$day, "%d.%m.%Y"),
       rows = c(list(list(label = "Kurs", value = analysis_history_eur_v1(row$price, digits), color = ANALYSIS_ASSETS_LINE_V1)),
                lapply(names(marks), function(name) list(label = name, value = paste0(analysis_history_eur_v1(marks[[name]], digits), " (",
                  analysis_history_pct_v1(marks[[name]] / row$price - 1), " zum Kurs des Tages)")))))
}

# Wie viel verkauft werden muss, damit ein Erloes ankommt: brutto nach Gebuehr, netto dazu nach projizierter Steuer. Der Erloes
# steigt mit der Menge (die Steuer waechst langsamer als der Erloes), deshalb reicht eine Halbierung.
analysis_projection_proceeds_v1 <- function(projection, price, wanted, with_fee = TRUE, view = "net") {
  lots <- analysis_projection_lots_v1(projection); total <- sum(lots$quantity); net <- identical(view, "net")
  if (!is.numeric(wanted) || length(wanted) != 1L || is.na(wanted) || wanted <= 0) return(list(status = "no_input"))
  if (net && !identical(projection$tax$status, "ready")) return(list(status = "tax_unavailable"))
  value <- function(quantity) { sale <- analysis_projection_sale_v1(projection, lots, price, quantity, with_fee); sale$gross - sale$fee - if (net) sale$tax else 0 }
  most <- value(total)
  if (most < wanted) return(list(status = "too_much", most = most, total = total, net = net))
  quantity <- .analysis_projection_solve_v1(value, wanted, 0, total, grow = FALSE)
  c(list(status = "ok", wanted = wanted, total = total, net = net), analysis_projection_sale_v1(projection, lots, price, quantity, with_fee))
}

analysis_projection_proceeds_table_v1 <- function(result) {
  if (!identical(result$status, "ok")) return(data.frame())
  lots <- if (result$lots == 1L) paste("1 Los vom", format(result$first, "%d.%m.%Y")) else sprintf("%d Lose, %s bis %s", result$lots, format(result$first, "%d.%m.%Y"), format(result$last, "%d.%m.%Y"))
  rows <- list(c("Verkaufsmenge", paste0(.analysis_history_quantity_v1(signif(result$quantity, 8)), " Stück (", formatC(result$quantity / result$total * 100, format = "f", digits = 1, decimal.mark = ","), " % des Bestands)")),
               c("Erlös brutto", analysis_history_eur_v1(result$gross, 2L)), c("Verkaufsgebühr (Projektion)", analysis_history_eur_v1(result$fee, 2L)),
               c("Steuer (Projektion)", if (is.na(result$tax)) "nicht verfügbar" else analysis_history_eur_v1(result$tax, 2L)),
               c(if (result$net) "Erlös nach Gebühr und Steuer" else "Erlös nach Gebühr", analysis_history_eur_v1(result$gross - result$fee - if (result$net) result$tax else 0, 2L)),
               c("Einstand der verkauften Lose", analysis_history_eur_v1(result$basis, 2L)), c("GuV brutto", analysis_history_eur_signed_v1(result$gain, 2L)),
               c("betroffene Lose", lots))
  if (result$inside > 0L) rows <- c(rows, list(c("davon in der Jahresfrist", as.character(result$inside))))
  data.frame(Angabe = vapply(rows, `[[`, character(1L), 1L), Wert = vapply(rows, `[[`, character(1L), 2L), stringsAsFactors = FALSE)
}

# Haltefrist (privates Veraeusserungsgut, etwa Krypto): was heute steuerfrei verkaufbar ist und wann die uebrigen Lose frei werden.
# Je noch gebundenem Los: der Tag, ab dem alles bis einschliesslich dieses Loses frei ist, und was ein Verkauf bis dahin heute
# an Steuer kostete - so viel spart, wer wartet. Ein Verlust in der Frist ist verrechenbar, danach nicht.
analysis_projection_holding_v1 <- function(projection, price, with_fee = TRUE) {
  if (!isTRUE(projection$tax$holding_period)) return(NULL)
  lots <- analysis_projection_lots_v1(projection); day <- as.Date(projection$day)
  bound <- !is.na(lots$free_from) & day < lots$free_from
  first <- which(bound)[1L]
  free_now <- if (is.na(first)) sum(lots$quantity) else sum(lots$quantity[seq_len(first - 1L)])
  free_until <- as.Date(cummax(ifelse(is.na(lots$free_from), -Inf, as.numeric(lots$free_from))), origin = "1970-01-01")
  rows <- lapply(which(bound), function(index) {
    quantity <- sum(lots$quantity[seq_len(index)])
    sale <- analysis_projection_sale_v1(projection, lots, price, quantity, with_fee)
    part <- lots$quantity[[index]] * price * (1 - .analysis_projection_fee_v1(projection, with_fee)) - lots$basis[[index]]
    data.frame(`Los vom` = format(lots$acquired[[index]], "%d.%m.%Y"), Menge = .analysis_history_quantity_v1(signif(lots$quantity[[index]], 10)),
               `frei ab` = format(free_until[[index]], "%d.%m.%Y"), `Tage bis dahin` = as.character(as.integer(free_until[[index]] - day)),
               `ab dann steuerfrei verkaufbar` = paste(.analysis_history_quantity_v1(signif(quantity, 10)), "Stück"),
               `GuV dieses Loses heute` = analysis_history_eur_signed_v1(part, 2L),
               `Steuer bei Verkauf bis hierhin heute` = if (is.na(sale$tax)) "nicht verfügbar" else analysis_history_eur_v1(sale$tax, 2L),
               check.names = FALSE, stringsAsFactors = FALSE)
  })
  list(free_now = free_now, total = sum(lots$quantity), next_day = if (is.na(first)) NA else free_until[[first]],
       next_quantity = if (is.na(first)) NA_real_ else lots$quantity[[first]], table = if (length(rows)) do.call(rbind, rows) else data.frame())
}

analysis_projection_holding_text_v1 <- function(holding) {
  if (is.null(holding)) return("Für dieses Asset gibt es keine Haltefrist: Jeder Gewinn ist steuerpflichtig, gleich wie lange es gehalten wird.")
  paste0("Heute steuerfrei verkaufbar: ", .analysis_history_quantity_v1(signif(holding$free_now, 10)), " von ", .analysis_history_quantity_v1(signif(holding$total, 10)), " Stück",
         if (!is.na(holding$next_day)) paste0(" · nächstes Los frei ab ", format(holding$next_day, "%d.%m.%Y"), " (", .analysis_history_quantity_v1(signif(holding$next_quantity, 10)), " Stück)")
         else " · alle Lose sind frei", ". Ein Verlust in der Jahresfrist ist verrechenbar, danach nicht.")
}

# Derselbe Verkauf aus jedem Konto des Assets (FIFO je Wallet): wo er am wenigsten Steuer kostet. Ohne Menge jeweils alles.
analysis_projection_accounts_v1 <- function(projection, price, quantity = NA_real_, with_fee = TRUE) {
  accounts <- projection$accounts
  if (!length(accounts)) return(data.frame())
  rows <- lapply(seq_along(accounts), function(index) {
    own <- analysis_projection_for_account_v1(projection, as.character(index)); lots <- analysis_projection_lots_v1(own)
    held <- sum(lots$quantity); sold <- analysis_projection_quantity_v1(lots, quantity)
    sale <- analysis_projection_sale_v1(own, lots, price, sold, with_fee)
    list(net = if (is.na(sale$net)) sale$gain else sale$net, row = data.frame(Konto = own$account, Methode = ANALYSIS_PROJECTION_METHODS_V1[[own$method]],
      Bestand = .analysis_history_quantity_v1(signif(held, 10)),
      verkauft = paste0(.analysis_history_quantity_v1(signif(sold, 10)), if (is.finite(quantity) && quantity > held + 1e-12) " (mehr liegt nicht da)" else ""),
      `Erlös brutto` = analysis_history_eur_v1(sale$gross, 2L), `Einstand der verkauften Lose` = analysis_history_eur_v1(sale$basis, 2L),
      `GuV brutto` = analysis_history_eur_signed_v1(sale$gain, 2L), `Steuer (Projektion)` = if (is.na(sale$tax)) "nicht verfügbar" else analysis_history_eur_v1(sale$tax, 2L),
      `GuV netto` = if (is.na(sale$net)) "nicht verfügbar" else analysis_history_eur_signed_v1(sale$net, 2L),
      `Lose in der Jahresfrist` = as.character(sale$inside), check.names = FALSE, stringsAsFactors = FALSE))
  })
  table <- do.call(rbind, lapply(rows, `[[`, "row"))
  table[order(-vapply(rows, `[[`, numeric(1L), "net")), , drop = FALSE]
}

analysis_projection_note_v1 <- function(projection) {
  tax <- projection$tax
  fee <- analysis_history_number_v1(list(projection$fee_rate))
  fee_text <- if (is.na(fee)) "ohne Gebühr (keine Käufe oder Verkäufe mit Gebühr)" else
    sprintf("Gebühr %s %% vom Erlös (%s)", formatC(fee, format = "f", digits = 3, decimal.mark = ","),
            if (identical(projection$fee_source, "asset")) "aus den eigenen Käufen und Verkäufen" else "Durchschnitt des Portfolios")
  tax_text <- if (!identical(tax$status, "ready")) paste("Steuer nicht verfügbar:", {
      text <- ANALYSIS_HISTORY_NET_REASONS_V1[tax$status]; if (is.na(text)) tax$status else unname(text) }) else
    sprintf("Steuer nach Jahresmodul %s: %s %%%s, Solidaritätszuschlag %s %%, Kirchensteuer %s %%%s; je Verkauf konservativ ohne Freibetrag und Verrechnung",
            tax$tax_year, formatC(analysis_history_number_v1(list(tax$rate)), format = "fg", decimal.mark = ","),
            if (!identical(tax$partial_exemption, "0")) paste0(" auf den Gewinn nach ", tax$partial_exemption, " % Teilfreistellung") else "",
            formatC(analysis_history_number_v1(list(tax$solidarity)), format = "fg", decimal.mark = ","),
            formatC(analysis_history_number_v1(list(tax$church)), format = "fg", decimal.mark = ","),
            if (isTRUE(tax$holding_period)) "; nur Lose in der Jahresfrist" else "")
  method_text <- if (identical(projection$method, "average"))
    "Durchschnittsmethode: Jedes verkaufte Stück kostet den Durchschnitt der Wallet, die Haltefrist folgt der FIFO-Folge" else
    "FIFO je Wallet: Ein Verkauf verbraucht die ältesten Lose dieses Kontos"
  paste0("Stand ", format(as.Date(projection$day), "%d.%m.%Y"), " · ", projection$account, ": ", length(projection$lots), " offene Lose",
         if (isTRUE(projection$account_count > 1L)) sprintf(" (das Asset liegt auf %d Konten)", projection$account_count) else "",
         " · ", method_text, " · ", fee_text, " · ", tax_text, ". Projektion, keine Steuerberechnung.")
}

analysis_projection_ui_v1 <- function() shiny::tagList(
  portelyra_card(
    "Projektion",
    copy = "Was ein Verkauf aus einem Konto zu einem gewählten Kurs ergäbe, welcher Kurs ein Ziel erreicht und was ein Zukauf aus dem Einstandskurs macht.",
    note = portelyra_note_v1(title = "So rechnet die Projektion", id = "analysis-projection",
      "Verkauft wird vom ältesten offenen Los dieses Kontos an, Teil-Lose anteilig, brutto und nach projizierter Gebühr und Steuer.",
      "Der Kurs ist frei wählbar. Voreingestellt ist der zuletzt abgerufene Kurs der Momentaufnahme, ohne ihn der des letzten Tages; beide lassen sich mit einem Klick übernehmen. Gerechnet wird mit den Losen, dem Gebührensatz und den Steuersätzen, die die Tageshistorie veröffentlicht.",
      "Erst die Frage wählen, dann ihre Angaben: Beim Zielkurs zählt die Verkaufsmenge (leer heißt alles), beim Erlös der Betrag, der ankommen soll. „Netto“ heißt nach projizierter Steuer, je Verkauf ohne Freibetrag und Verrechnung."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("projection_asset", "Asset", c("Bitte warten" = ""), width = "360px"),
      shiny::selectInput("projection_account", "Konto / Wallet", c("Bitte warten" = ""), width = "360px"),
      shiny::radioButtons("projection_mode", "Vorgang", ANALYSIS_PROJECTION_MODES_V1, selected = "sell", inline = TRUE),
      shiny::numericInput("projection_price", "Kurs je Einheit (€)", value = NA, min = 0, step = 0.01),
      shiny::checkboxInput("projection_fee", "Gebühr einrechnen", value = TRUE)),
    # Zwei Kurse zur Wahl (#512, Festlegung 25.10.2026): der zuletzt abgerufene der Momentaufnahme und der des letzten Tages.
    shiny::div(class = "pl-inline-actions", style = "display:flex;gap:18px;flex-wrap:wrap",
      shiny::actionLink("projection_price_moment", "Letzten abgerufenen Momentaufnahmen-Kurs übernehmen"),
      shiny::actionLink("projection_price_reset", "Kurs des letzten Tages übernehmen")),
    shiny::uiOutput("projection_price_state"),
    shiny::uiOutput("projection_state"),
    shiny::conditionalPanel("input.projection_mode == 'sell'",
      # Fragen statt eines Formulars (#531 Punkt 4): Je Frage nur ihre Angaben.
      shiny::div(class = "pl-form-grid",
        shiny::radioButtons("projection_question", "Frage", ANALYSIS_PROJECTION_SELL_QUESTIONS_V1, selected = "curve"),
        shiny::conditionalPanel("input.projection_question == 'target' || input.projection_question == 'proceeds'",
          shiny::radioButtons("projection_view", "Sicht", ANALYSIS_PROJECTION_VIEWS_V1, selected = "net"))),
      shiny::conditionalPanel("input.projection_question == 'curve'",
        shiny::div(class = "pl-zoomable", style = "position:relative",
          shiny::plotOutput("projection_plot", height = "420px", hover = shiny::hoverOpts("projection_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
          shiny::uiOutput("projection_overlay", style = "position:absolute;inset:0;pointer-events:none")),
        shiny::tags$details(shiny::tags$summary("Offene Lose des Kontos in FIFO-Folge"),
          shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("projection_lots")))),
      shiny::conditionalPanel("input.projection_question == 'target'",
        shiny::div(class = "pl-form-grid",
          shiny::numericInput("projection_sell_quantity", "Verkaufsmenge (leer = alles)", value = NA, min = 0),
          shiny::numericInput("projection_goal", "c) angestrebte GuV", value = NA),
          shiny::radioButtons("projection_goal_kind", "c) in", c("Euro" = "eur", "Prozent (einfache Rendite)" = "pct"), selected = "eur", inline = TRUE)),
        shiny::uiOutput("projection_target_state"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("projection_targets")),
        shiny::div(style = "position:relative",
          shiny::plotOutput("projection_price_plot", height = "360px", hover = shiny::hoverOpts("projection_price_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
          shiny::uiOutput("projection_price_overlay", style = "position:absolute;inset:0;pointer-events:none"))),
      shiny::conditionalPanel("input.projection_question == 'proceeds'",
        shiny::div(class = "pl-form-grid", shiny::numericInput("projection_wanted", "Erlös, der ankommen soll (€)", value = NA, min = 0)),
        shiny::uiOutput("projection_proceeds_state"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("projection_proceeds"))),
      shiny::conditionalPanel("input.projection_question == 'holding'",
        shiny::uiOutput("projection_holding_state"),
        shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("projection_holding"))),
      shiny::conditionalPanel("input.projection_question == 'accounts'",
        shiny::div(class = "pl-form-grid", shiny::numericInput("projection_compare_quantity", "Verkaufsmenge je Konto (leer = jeweils alles)", value = NA, min = 0)),
        shiny::uiOutput("projection_accounts_state"),
        shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("projection_accounts")))),
    shiny::conditionalPanel("input.projection_mode == 'buy'",
      shiny::radioButtons("projection_buy_question", "Frage", ANALYSIS_PROJECTION_BUY_QUESTIONS_V1, selected = "quantity", inline = TRUE),
      shiny::div(class = "pl-form-grid",
        shiny::conditionalPanel("input.projection_buy_question == 'quantity'", shiny::numericInput("projection_buy_quantity", "Zukauf (Stück)", value = NA, min = 0)),
        shiny::conditionalPanel("input.projection_buy_question == 'amount'", shiny::numericInput("projection_buy_amount", "Betrag (€, Gebühr eingeschlossen)", value = NA, min = 0)),
        shiny::conditionalPanel("input.projection_buy_question == 'average'", shiny::numericInput("projection_target_average", "angestrebter Einstandskurs (€)", value = NA, min = 0))),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("projection_buy")),
      shiny::radioButtons("projection_buy_axis", "Achse des Bilds", c("Stück" = "quantity", "Betrag in €" = "amount"), selected = "quantity", inline = TRUE),
      shiny::div(style = "position:relative",
        shiny::plotOutput("projection_buy_plot", height = "320px", hover = shiny::hoverOpts("projection_buy_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
        shiny::uiOutput("projection_buy_overlay", style = "position:absolute;inset:0;pointer-events:none")))))

# Woher der Kurs der Projektion stammt - als Satz unter den beiden Links.
analysis_projection_price_text_v1 <- function(source, quote, day, typed = FALSE) {
  if (isTRUE(typed)) return("Kurs: eigene Eingabe.")
  if (identical(source, "moment") && !is.null(quote))
    return(paste0("Kurs: zuletzt abgerufen, Momentaufnahme vom ", quote$time, if (isTRUE(quote$quoted)) "" else " – für dieses Asset ohne frischen Abruf, also der letzte Schlusskurs", "."))
  paste0("Kurs: Tagesschluss vom ", format(as.Date(day), "%d.%m.%Y"),
         if (identical(source, "moment")) " – die Momentaufnahme hat für dieses Asset keinen Kurs (oder ist nicht jünger als der letzte Tag)." else ".")
}

analysis_projection_server_v1 <- function(input, output, session, ready, geometry, moment = function() NULL, hydrate = function(entry) entry) {
  shiny::observeEvent(ready(), shiny::updateSelectInput(session, "projection_asset", choices = analysis_projection_choices_v1(ready())), ignoreNULL = TRUE)
  chosen <- shiny::reactive(analysis_projection_of_v1(ready(), input$projection_asset))
  shiny::observeEvent(chosen(), shiny::updateSelectInput(session, "projection_account", choices = analysis_projection_account_choices_v1(chosen())),
                      ignoreNULL = FALSE)
  # Das gewaehlte Asset mit der Projektion des gewaehlten Kontos.
  asset <- shiny::reactive({
    current <- chosen(); if (is.null(current)) return(NULL)
    projection <- analysis_projection_for_account_v1(current$projection, input$projection_account)
    if (is.null(projection)) return(NULL)
    current$projection <- projection
    current
  })
  # Welcher Kurs zuletzt uebernommen wurde: Quelle und Wert. Weicht die Eingabe davon ab, ist es ein eigener Kurs.
  taken <- shiny::reactiveVal(NULL)
  quote <- shiny::reactive({ model <- moment(); if (is.null(model)) NULL else analysis_moment_price_v1(model, chosen()) })
  set_price <- function(source = "moment") {
    current <- chosen(); if (is.null(current)) return(invisible(NULL))
    hit <- if (identical(source, "moment")) quote() else NULL
    value <- signif(if (!is.null(hit)) hit$price else analysis_history_number_v1(list(current$projection$price)), 10)
    taken(list(source = source, value = value, used = if (is.null(hit)) "day" else "moment"))
    shiny::updateNumericInput(session, "projection_price", value = value)
  }
  # Beim Wechsel des Assets gilt der juengste Kurs: der der Momentaufnahme, ohne ihn der des letzten Tages.
  shiny::observeEvent(input$projection_asset, set_price("moment"), ignoreInit = TRUE)
  shiny::observeEvent(input$projection_price_moment, set_price("moment"), ignoreInit = TRUE)
  shiny::observeEvent(input$projection_price_reset, set_price("day"), ignoreInit = TRUE)
  output$projection_price_state <- shiny::renderUI({
    current <- chosen(); state <- taken(); if (is.null(current) || is.null(state)) return(NULL)
    typed <- input$projection_price
    own <- is.numeric(typed) && length(typed) == 1L && !is.na(typed) && abs(typed - state$value) > 1e-9 * max(1, abs(state$value))
    shiny::p(class = "pl-field-hint", analysis_projection_price_text_v1(state$source, if (identical(state$used, "moment")) quote() else NULL, current$projection$day, own))
  })
  price <- shiny::reactive({
    current <- asset(); typed <- input$projection_price
    if (is.null(current)) return(NA_real_)
    if (is.numeric(typed) && length(typed) == 1L && !is.na(typed) && typed >= 0) typed else analysis_history_number_v1(list(current$projection$price))
  })
  curve <- shiny::reactive({
    current <- asset(); value <- price()
    if (is.null(current) || is.na(value)) return(NULL)
    analysis_projection_curve_v1(current$projection, value, !identical(input$projection_fee, FALSE))
  })
  output$projection_state <- shiny::renderUI({
    current <- asset(); if (is.null(current)) return(NULL)
    shiny::p(class = "pl-field-hint", analysis_projection_note_v1(current$projection))
  })
  output$projection_plot <- shiny::renderPlot({
    current <- curve(); shiny::req(current, nrow(current) > 1L)
    geometry$projection <- analysis_projection_plot_v1(current, asset()$projection)
  })
  output$projection_overlay <- shiny::renderUI({
    current <- curve(); hover <- input$projection_hover
    x <- analysis_history_pixel_day_v1(geometry$projection, hover)
    if (is.null(current) || is.null(x)) return(NULL)
    content <- analysis_projection_rows_v1(current, x)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$projection)
  })
  output$projection_lots <- shiny::renderTable({
    current <- asset(); shiny::req(current)
    lots <- analysis_projection_lots_v1(current$projection)
    data.frame(Anschaffung = format(lots$acquired, "%d.%m.%Y"), Menge = vapply(lots$quantity, function(value) .analysis_history_quantity_v1(signif(value, 10)), character(1L)),
               Einstand = analysis_history_eur_v1(lots$basis, 2L), `Einstand je Einheit` = analysis_history_eur_v1(lots$basis / lots$quantity, 2L),
               `steuerfrei ab` = ifelse(is.na(lots$free_from) | !isTRUE(current$projection$tax$holding_period), "–", format(lots$free_from, "%d.%m.%Y")),
               check.names = FALSE, stringsAsFactors = FALSE)
  }, striped = TRUE, spacing = "xs")
  number <- function(value) if (is.numeric(value) && length(value) == 1L && !is.na(value)) value else NA_real_
  with_fee <- shiny::reactive(!identical(input$projection_fee, FALSE))
  view <- shiny::reactive(if (identical(input$projection_view, "gross")) "gross" else "net")
  # Zukauf je Frage (#531 Punkt 4): Stueckzahl, Betrag oder angestrebter Einstandskurs.
  buy_inputs <- shiny::reactive({
    question <- if (is.null(input$projection_buy_question)) "quantity" else input$projection_buy_question
    list(quantity = if (identical(question, "quantity")) number(input$projection_buy_quantity) else NA_real_,
         amount = if (identical(question, "amount")) number(input$projection_buy_amount) else NA_real_,
         target = if (identical(question, "average")) number(input$projection_target_average) else NA_real_)
  })
  output$projection_buy <- shiny::renderTable({
    current <- asset(); shiny::req(current, !is.na(price())); chosen_buy <- buy_inputs()
    analysis_projection_buy_v1(current$projection, price(), chosen_buy$quantity, chosen_buy$target, with_fee(), chosen_buy$amount)
  }, striped = TRUE, spacing = "xs")
  output$projection_buy_plot <- shiny::renderPlot({
    current <- asset(); shiny::req(current, !is.na(price()), price() > 0); chosen_buy <- buy_inputs()
    unit_cost <- price() * (1 + .analysis_projection_fee_v1(current$projection, with_fee()))
    quantity <- if (is.finite(chosen_buy$amount)) chosen_buy$amount / unit_cost else chosen_buy$quantity
    geometry$projection_buy <- analysis_projection_buy_plot_v1(current$projection, price(), with_fee(), quantity, chosen_buy$target, buy_axis())
  })
  buy_axis <- shiny::reactive(if (identical(input$projection_buy_axis, "amount")) "amount" else "quantity")
  output$projection_buy_overlay <- shiny::renderUI({
    current <- asset(); hover <- input$projection_buy_hover; x <- analysis_history_pixel_day_v1(geometry$projection_buy, hover)
    if (is.null(current) || is.null(x) || is.na(price()) || x < 0 || x > geometry$projection_buy$upper) return(NULL)
    content <- analysis_projection_buy_rows_v1(current$projection, price(), with_fee(), x, geometry$projection_buy$axis)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$projection_buy)
  })
  # Verkauf: Zielkurs, Erloes, Haltefrist, Konten (#531 Punkt 4).
  targets <- shiny::reactive({
    current <- asset(); value <- price(); if (is.null(current) || is.na(value)) return(NULL)
    analysis_projection_targets_v1(current$projection, number(input$projection_sell_quantity), with_fee(), view(), number(input$projection_goal),
                                   if (identical(input$projection_goal_kind, "pct")) "pct" else "eur")
  })
  output$projection_target_state <- shiny::renderUI({ found <- targets(); if (is.null(found)) return(NULL)
    shiny::p(class = "pl-field-hint", analysis_projection_targets_text_v1(found, price())) })
  output$projection_targets <- shiny::renderTable(analysis_projection_targets_table_v1(shiny::req(targets()), price()), striped = TRUE, spacing = "xs")
  # Der Kursverlauf aus der Teildatei des Assets (#503), das letzte Jahr.
  series <- shiny::reactive({
    current <- chosen(); if (is.null(current)) return(NULL)
    full <- tryCatch(hydrate(current), error = function(error) NULL); if (is.null(full) || is.null(full$days)) return(NULL)
    frame <- tryCatch(analysis_history_asset_frame_v1(full, "1y"), error = function(error) NULL)
    if (is.null(frame) || !nrow(frame)) NULL else data.frame(day = frame$day, price = frame$unit_value)
  })
  output$projection_price_plot <- shiny::renderPlot({ found <- shiny::req(targets()); geometry$projection_price <- analysis_projection_price_plot_v1(series(), price(), found) })
  output$projection_price_overlay <- shiny::renderUI({
    found <- targets(); hover <- input$projection_price_hover; x <- analysis_history_pixel_day_v1(geometry$projection_price, hover)
    if (is.null(found) || is.null(x)) return(NULL)
    content <- analysis_projection_price_rows_v1(series(), price(), found, x); if (is.null(content)) return(NULL)
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$projection_price)
  })
  proceeds <- shiny::reactive({
    current <- asset(); value <- price(); if (is.null(current) || is.na(value)) return(NULL)
    analysis_projection_proceeds_v1(current$projection, value, number(input$projection_wanted), with_fee(), view())
  })
  output$projection_proceeds_state <- shiny::renderUI({
    result <- proceeds(); if (is.null(result)) return(NULL)
    text <- switch(result$status, no_input = "Den Erlös eintragen, der nach Gebühr (netto auch nach Steuer) ankommen soll.",
      tax_unavailable = "Netto ist ohne Steuersätze des Jahresmoduls nicht verfügbar; brutto rechnet nur mit der Gebühr.",
      too_much = sprintf("So viel bringt dieses Konto nicht: Alles verkauft ergäbe %s.", analysis_history_eur_v1(result$most, 2L)), NULL)
    if (!is.null(text)) shiny::p(class = "pl-field-hint", text)
  })
  output$projection_proceeds <- shiny::renderTable(analysis_projection_proceeds_table_v1(shiny::req(proceeds())), striped = TRUE, spacing = "xs")
  holding <- shiny::reactive({ current <- asset(); value <- price(); if (is.null(current) || is.na(value)) NULL else
    list(value = analysis_projection_holding_v1(current$projection, value, with_fee())) })
  output$projection_holding_state <- shiny::renderUI({ found <- shiny::req(holding()); shiny::p(class = "pl-field-hint", analysis_projection_holding_text_v1(found$value)) })
  output$projection_holding <- shiny::renderTable({ found <- shiny::req(holding()); if (is.null(found$value)) data.frame() else found$value$table }, striped = TRUE, spacing = "xs")
  output$projection_accounts_state <- shiny::renderUI({
    current <- chosen(); if (is.null(current)) return(NULL)
    count <- length(current$projection$accounts)
    shiny::p(class = "pl-field-hint", if (count < 2L) "Das Asset liegt nur auf einem Konto; der Vergleich zeigt dieses eine." else
      sprintf("Derselbe Verkauf aus jedem der %d Konten, FIFO je Wallet; oben das Konto mit dem besten Ergebnis nach Steuer.", count))
  })
  output$projection_accounts <- shiny::renderTable({
    current <- chosen(); value <- price(); shiny::req(current, !is.na(value))
    analysis_projection_accounts_v1(current$projection, value, number(input$projection_compare_quantity), with_fee())
  }, striped = TRUE, spacing = "xs")
  invisible(list(asset = asset, curve = curve, price = price, quote = quote, taken = taken, targets = targets, proceeds = proceeds, holding = holding, series = series))
}
