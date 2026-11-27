# Reiter "Assets und Gruppen" der Analyse (#483, #485): ein Asset oder eine Assetklasse im Verlauf, Kennzahlen je Zeitraum
# mit Erfolgsbruecke, die Buchungen eines Assets und Uebersichten je Klasse und je Asset. Nur Anzeige: Alles ist in der
# veroeffentlichten Tageshistorie gerechnet.
#
# Festlegungen (20./21.10.2026): Einstand und Einstandskurs nach Vorzeichen gefaerbt - blau, wenn Wert bzw.
# Kurs darueber liegt (Gewinn), rot darunter (Verlust); Wert und Kurs dunkelgrau, damit sie sich abheben. Buchungssymbole
# deutlich groesser und ohne Ueberlappung (dicht liegende werden gebuendelt), Ertraege als Symbole, per Haekchen waehlbar.
# Einzelasset und Klasse getrennt: nur das Einzelasset zeigt Buchungen; ein Klick auf einen Verkauf zeigt die Rechnung je Lot.

ANALYSIS_ASSETS_LINE_V1 <- "#52514e"
# Kurs ohne Bestand (#526, Festlegung 06.11.2026): heller und gestrichelt - dort ist er kein Hebel des Vermoegens.
ANALYSIS_ASSETS_FREE_V1 <- "#a3a09a"
ANALYSIS_ASSETS_FREE_LABEL_V1 <- "Kurs ohne Bestand"
ANALYSIS_ASSETS_SIGN_V1 <- c(gain = "#2a78d6", loss = "#e34948")
# Symbole (geprueft gegeneinander, alle Paare): Kauf gruen, Verkauf violett, Ertraege gelb, Ein- und Auslieferungen rosa.
ANALYSIS_ASSETS_SYMBOLS_V1 <- list(
  buy = list(label = "Kauf", pch = 24, col = "#008300", group = "trades"),
  sell = list(label = "Verkauf", pch = 25, col = "#6250d6", group = "trades"),
  dividend = list(label = "Dividende", pch = 23, col = "#eda100", group = "income"),
  reward = list(label = "Reward, Stockdividende", pch = 21, col = "#eda100", group = "income"),
  stock_dividend = list(label = "Reward, Stockdividende", pch = 21, col = "#eda100", group = "income"),
  deposit = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  withdrawal = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  other_in = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  other_out = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  # In der Sicht je Konto (rc.294): Transfer zwischen eigenen Konten, gezeichnet wie eine Ein- oder Auslieferung.
  transfer_in = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  transfer_out = list(label = "Ein- und Auslieferung", pch = 22, col = "#e87ba4", group = "deliveries"),
  # Aktiensplit (#451): keine Buchung, eine Kapitalmassnahme - die Menge springt im Verhaeltnis, der Einstand bleibt.
  split = list(label = "Split", pch = 21, col = "#7a7670", group = "trades"))
ANALYSIS_ASSETS_GROUPS_V1 <- c("Käufe und Verkäufe" = "trades", "Erträge (Dividenden, Rewards)" = "income", "Ein- und Auslieferungen, Transfers" = "deliveries")
ANALYSIS_ASSETS_SYMBOL_CEX_V1 <- 2.1

# Auswahl: zuerst die Assets (groesster Wert am letzten Tag zuerst), dann die Klassen.
analysis_assets_choices_v1 <- function(history) {
  assets <- history$assets
  value_of <- function(asset) {
    # Kern mit Teildateien (#503): der Wert am letzten Tag steht im Kern; ohne Bestand an diesem Tag leer.
    if (!is.null(asset$part)) { value <- analysis_history_number_v1(list(asset$last_value)); return(if (is.na(value)) -Inf else value) }
    values <- analysis_history_number_v1(asset$days$market_value); days <- unlist(asset$days$day)
    if (!length(days) || !identical(days[[length(days)]], history$last_day)) return(-Inf)
    value <- values[[length(values)]]; if (is.na(value)) -Inf else value
  }
  last_value <- vapply(assets, value_of, numeric(1L))
  labels <- paste0(vapply(assets, function(asset) asset$label, character(1L)), ifelse(is.finite(last_value), "", " (nicht mehr gehalten)"))
  order <- order(-last_value, labels)
  asset_choices <- if (!length(assets)) character() else stats::setNames(paste0("asset:", vapply(assets[order], function(asset) as.character(asset$ordinal), character(1L))), labels[order])
  classes <- vapply(history$classes, function(row) row$class, character(1L))
  class_choices <- stats::setNames(paste0("class:", classes), vapply(classes, function(key) ANALYSIS_HISTORY_CLASSES_V1[[key]]$label, character(1L)))
  groups <- history$groups
  group_choices <- if (!length(groups)) character() else stats::setNames(paste0("group:", vapply(groups, function(row) as.character(row$ordinal), character(1L))),
    vapply(groups, function(row) paste0(row$label, if (length(row$new_labels)) " (neue Assets nicht enthalten)" else ""), character(1L)))
  watched <- history$watched
  watched_choices <- if (!length(watched)) character() else stats::setNames(paste0("watched:", vapply(watched, function(row) as.character(row$ordinal), character(1L))),
    paste0(vapply(watched, function(row) row$label, character(1L)), " (nie gehalten)"))
  if (!length(asset_choices) && !length(class_choices) && !length(watched_choices)) return(c("Keine Assets" = ""))
  choices <- list(Assets = asset_choices, Assetklassen = class_choices)
  if (length(group_choices)) choices$`Eigene Gruppen` <- group_choices
  # Beobachtet, nie gehalten (#526): nur der Kurs, gestrichelt.
  if (length(watched_choices)) choices$`Beobachtet (nie gehalten)` <- watched_choices
  choices
}

analysis_assets_selection_v1 <- function(history, choice) {
  if (is.null(history) || !is.character(choice) || !nzchar(choice)) return(NULL)
  parts <- strsplit(choice, ":", fixed = TRUE)[[1L]]
  if (length(parts) != 2L) return(NULL)
  if (identical(parts[[1L]], "watched")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), parts[[2L]]), history$watched)
    if (length(hit) != 1L) return(NULL)
    # Wie ein Asset ohne Buchungen: Bild und Abstand vom Hoch nehmen denselben Weg, nur ohne Bestand.
    row <- hit[[1L]]
    asset <- c(row, list(days = list(day = list(), quantity = list(), unit_value = list(), market_value = list()), basis = list(), trades = list(),
                         income = list(), performance = list(periods = list(), realized_steps = list()), held_accounts = list()))
    return(list(kind = "asset", watched = TRUE, label = row$label, asset = asset, periods = list()))
  }
  if (identical(parts[[1L]], "asset")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), parts[[2L]]), history$assets)
    if (length(hit) == 1L) return(list(kind = "asset", label = hit[[1L]]$label, asset = hit[[1L]], periods = hit[[1L]]$performance$periods))
  }
  if (identical(parts[[1L]], "class")) {
    hit <- Filter(function(row) identical(row$class, parts[[2L]]), history$classes)
    if (length(hit) == 1L) return(list(kind = "class", label = ANALYSIS_HISTORY_CLASSES_V1[[parts[[2L]]]]$label, key = parts[[2L]],
                                       group = hit[[1L]], periods = hit[[1L]]$periods))
  }
  # Eigene Gruppe (#483 Stufe 2): wie eine Klasse, ihr Wert je Tag kommt aus der Veroeffentlichung.
  if (identical(parts[[1L]], "group")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), parts[[2L]]), history$groups)
    if (length(hit) == 1L) return(list(kind = "group", label = hit[[1L]]$label, group = hit[[1L]], periods = hit[[1L]]$periods))
  }
  NULL
}

# Sicht je Konto (rc.294): Ein Asset auf mehreren Konten traegt je Konto einen Eintrag in Asset-Form. Die Wahl "Alle Konten" ist
# das Asset selbst. Der Wert nennt Asset und Konto ("<Asset>:<Konto>"), damit eine Wahl nie an einem anderen Asset haengt.
analysis_assets_account_choices_v1 <- function(selection) {
  is_asset <- !is.null(selection) && identical(selection$kind, "asset")
  accounts <- if (is_asset) selection$asset$accounts else list()
  held <- if (is_asset) unlist(selection$asset$held_accounts) else character()
  # Liegt das Asset nur auf einem Konto, steht dieses Konto in der Auswahl - man will wissen, wo es liegt (#499).
  if (!length(accounts)) return(if (length(held) == 1L) stats::setNames("", held) else c("Alle Konten" = ""))
  c(stats::setNames("", sprintf("Alle Konten (%d)", length(accounts))),
    stats::setNames(paste0(selection$asset$ordinal, ":", seq_along(accounts)), vapply(accounts, function(account) account$label, character(1L))))
}

# Die Zeile ueber der Grafik: was gezeigt wird - Asset mit Konto, alle Konten oder Klasse und Gruppe (#499).
analysis_assets_title_v1 <- function(selection) {
  if (is.null(selection)) return(NULL)
  if (identical(selection$kind, "class")) return(paste("Assetklasse", selection$label))
  if (identical(selection$kind, "group")) return(paste("Eigene Gruppe", selection$label))
  if (!is.null(selection$account)) return(selection$label)
  if (isTRUE(selection$watched)) return(paste(selection$label, "· beobachtet, nie gehalten"))
  held <- unlist(selection$asset$held_accounts)
  if (!length(held)) return(selection$label)
  if (length(held) == 1L) return(paste(selection$label, "·", held))
  shown <- utils::head(held, 4L)
  paste0(selection$label, " · alle Konten: ", paste(shown, collapse = ", "), if (length(held) > 4L) sprintf(" und %d weitere", length(held) - 4L) else "")
}

analysis_assets_account_selection_v1 <- function(selection, choice) {
  if (is.null(selection) || !identical(selection$kind, "asset") || !is.character(choice) || length(choice) != 1L) return(selection)
  parts <- strsplit(choice, ":", fixed = TRUE)[[1L]]
  if (length(parts) != 2L || !identical(parts[[1L]], as.character(selection$asset$ordinal))) return(selection)
  index <- suppressWarnings(as.integer(parts[[2L]]))
  if (is.na(index)) return(selection)
  accounts <- selection$asset$accounts
  if (index < 1L || index > length(accounts)) return(selection)
  account <- accounts[[index]]
  asset <- c(account[c("days", "basis", "trades", "income", "performance")],
             list(ordinal = selection$asset$ordinal, label = selection$asset$label, asset_type = selection$asset$asset_type,
                  valuation_method = selection$asset$valuation_method, net = account$net, fifo_wallet = account$fifo_wallet))
  list(kind = "asset", label = paste(selection$asset$label, "·", account$label), asset = asset, periods = account$performance$periods,
       account = account$label, fifo_wallet = account$fifo_wallet)
}

# FIFO-Wallet aus mehreren Konten (#508): Ein Einzelkonto der Wallet hat keinen eigenen Einstand - seine Lose gehoeren der Wallet.
ANALYSIS_ASSETS_IN_WALLET_V1 <- "rechnet in der FIFO-Wallet"
analysis_assets_wallet_member_v1 <- function(selection) identical(selection$fifo_wallet$role, "member")

.analysis_assets_realized_v1 <- function(days, steps) {
  if (!length(steps)) return(rep(0, length(days)))
  step_days <- as.Date(vapply(steps, function(step) step$day, character(1L)))
  values <- analysis_history_number_v1(lapply(steps, function(step) step$realized_cumulative))
  index <- findInterval(as.numeric(days), as.numeric(step_days))
  ifelse(index > 0L, values[pmax(index, 1L)], 0)
}

# Realisiert netto je Tag aus den veroeffentlichten Stufen; NA, sobald eine Steuer fehlt.
.analysis_assets_realized_net_v1 <- function(days, steps) {
  if (!length(steps)) return(rep(0, length(days)))
  step_days <- as.Date(vapply(steps, function(step) step$day, character(1L)))
  values <- analysis_history_number_v1(lapply(steps, function(step) step$realized_net_cumulative))
  index <- findInterval(as.numeric(days), as.numeric(step_days))
  ifelse(index > 0L, values[pmax(index, 1L)], 0)
}

# Rahmen eines Assets: Menge, Kurs, Wert, Einstand und Einstandskurs je Tag, dazu unrealisiert und realisiert (kumuliert).
# Mit der Netto-Sicht (#481): die Liquidationskosten je Tag (projizierte Verkaufsgebuehr und Steuer) und realisiert netto.
analysis_assets_asset_frame_v1 <- function(asset, period = "all", range = NULL, grid = NULL, held_only = FALSE) {
  frame <- analysis_history_asset_frame_v1(asset, "all")
  frame$unrealised <- ifelse(is.na(frame$market_value) | is.na(frame$cost_basis), NA_real_, frame$market_value - frame$cost_basis)
  frame$realized <- .analysis_assets_realized_v1(frame$day, asset$performance$realized_steps)
  # Je Konto gibt es Netto je Topf nicht (Kapitalertraege verrechnen sich je Institut und Jahr): Die Reihe fehlt dann, und die
  # Netto-Linie bleibt leer, statt das Bild abzubrechen (rc.305: "replacement has 0 rows").
  cost <- if (is.null(asset$net)) numeric() else analysis_history_number_v1(asset$net$cost)
  frame$cost <- if (length(cost) == nrow(frame)) cost else rep(NA_real_, nrow(frame))
  frame$realized_net <- if (is.null(asset$net)) rep(NA_real_, nrow(frame)) else .analysis_assets_realized_net_v1(frame$day, asset$net$realized_net_steps)
  frame <- .analysis_assets_with_gaps_v1(frame, asset, grid)
  frame <- .analysis_assets_with_exit_v1(frame, asset)
  frame <- .analysis_assets_with_prices_v1(frame, asset)
  if (isTRUE(held_only)) frame <- .analysis_assets_held_span_v1(frame)
  frame[analysis_history_window_v1(frame$day, period, range), , drop = FALSE]
}

# Kurs ohne Bestand (#526, Festlegung 06.11.2026): Die Teildatei traegt den Kurs je Tag auch vor dem ersten Kauf, nach dem letzten
# Verkauf und in Luecken. Diese Tage kommen als Tage ohne Bestand in den Rahmen - Menge, Wert und Einstand 0, grau hinterlegt -, mit
# Kurs; das Bild zeichnet ihn dort gestrichelt. Ohne Kursreihe (eigene Bewertung, Handelswert) bleibt der Rahmen, wie er ist.
.analysis_assets_with_prices_v1 <- function(frame, asset) {
  prices <- asset$prices
  if (is.null(prices) || !length(prices$day)) return(frame)
  days <- as.Date(unlist(prices$day)); values <- analysis_history_number_v1(prices$unit_value)
  if (is.null(frame$gap)) frame$gap <- !is.na(frame$quantity) & frame$quantity == 0
  at <- match(frame$day, days)
  fill <- frame$gap & is.na(frame$unit_value) & !is.na(at)
  frame$unit_value[fill] <- values[at[fill]]
  missing <- !days %in% frame$day
  if (any(missing)) {
    extra <- data.frame(day = days[missing], quantity = 0, unit_value = values[missing], market_value = 0, cost_basis = 0, cost_average = NA_real_,
                        stringsAsFactors = FALSE)
    for (column in setdiff(names(frame), names(extra))) extra[[column]] <- if (column %in% c("unrealised", "cost")) 0 else if (column == "gap") TRUE else NA
    frame <- rbind(frame, extra[names(frame)])
    frame <- frame[order(frame$day), , drop = FALSE]; rownames(frame) <- NULL
    frame$realized <- .analysis_assets_realized_v1(frame$day, asset$performance$realized_steps)
    if (!is.null(asset$net)) frame$realized_net <- .analysis_assets_realized_net_v1(frame$day, asset$net$realized_net_steps)
  }
  frame
}

# "Nur Zeit mit Bestand" (#526): vom ersten Tag mit Bestand bis einschliesslich zum Abgangstag nach dem letzten. Ohne Bestand (nie
# gehalten) bleibt der Rahmen ganz.
.analysis_assets_held_span_v1 <- function(frame) {
  held <- which(!is.na(frame$quantity) & frame$quantity > 0)
  if (!length(held)) return(frame)
  last <- max(held); if (last < nrow(frame) && isTRUE(frame$quantity[[last + 1L]] == 0)) last <- last + 1L
  frame[seq(min(held), last), , drop = FALSE]
}

# Tage ohne Bestand im Rahmen, getrennt nach Art (#526): noch nicht gehalten (vor dem ersten Bestand), zwischenzeitlich (Luecke) und
# nicht mehr (nach dem letzten). Ohne jeden Bestand zaehlt alles als "noch nicht".
analysis_assets_free_days_v1 <- function(frame) {
  if (is.null(frame) || !nrow(frame)) return(c(before = 0L, between = 0L, after = 0L))
  held <- !is.na(frame$quantity) & frame$quantity > 0
  free <- !held & !is.na(frame$unit_value)
  if (!any(held)) return(c(before = sum(free), between = 0L, after = 0L))
  first <- min(which(held)); last <- max(which(held)); index <- seq_len(nrow(frame))
  c(before = sum(free & index < first), between = sum(free & index > first & index < last), after = sum(free & index > last))
}

analysis_assets_free_note_v1 <- function(frame, watched = FALSE) {
  counts <- analysis_assets_free_days_v1(frame)
  if (!sum(counts)) return(NULL)
  if (isTRUE(watched)) return("Nie gehalten: Der gestrichelte Kurs zeigt den Markt, nicht Ihre Rendite.")
  parts <- c(if (counts[["before"]]) sprintf("%d noch nicht", counts[["before"]]), if (counts[["between"]]) sprintf("%d zwischenzeitlich nicht", counts[["between"]]),
             if (counts[["after"]]) sprintf("%d nicht mehr", counts[["after"]]))
  paste0("Im Zeitraum Tage ohne Bestand: ", paste(parts, collapse = ", "), " gehalten. Dort zeigt der gestrichelte Kurs den Markt, nicht Ihre Rendite.")
}

# Abgangstag (#541): Der Verlauf fuehrt je Asset und je Konto nur Tage mit Bestand. Nach dem letzten Abgang endet die Reihe deshalb
# am Vortag, mit voller Menge. Die Anzeige ergaenzt den Tag der ersten Buchung mit Abgang
# danach als Tag ohne Bestand: Menge, Wert und Einstand 0, kein Kurs. So faellt das Bild auf 0 wie bei der Klasse, das Verkaufssymbol
# steht an seinem Tag, und "realisiert" enthaelt die letzte Stufe - wie beim Komplettverkauf mit spaeterem Wiederkauf.
.analysis_assets_with_exit_v1 <- function(frame, asset) {
  if (!nrow(frame) || !length(asset$trades) || isTRUE(frame$quantity[[nrow(frame)]] == 0)) return(frame)
  days <- as.Date(vapply(asset$trades, function(row) as.character(row$day), character(1L)))
  change <- analysis_history_number_v1(lapply(asset$trades, function(row) row$quantity_change))
  out <- !is.na(change) & change < 0 & days > max(frame$day)
  if (!any(out)) return(frame)
  row <- frame[nrow(frame), , drop = FALSE]
  row$day <- min(days[out]); row$quantity <- 0; row$market_value <- 0; row$unit_value <- NA_real_
  for (column in intersect(c("cost_basis", "unrealised", "cost"), names(row))) row[[column]] <- 0
  if ("cost_average" %in% names(row)) row$cost_average <- NA_real_
  if ("gap" %in% names(row)) row$gap <- TRUE
  frame <- rbind(frame, row); rownames(frame) <- NULL
  frame$realized <- .analysis_assets_realized_v1(frame$day, asset$performance$realized_steps)
  if (!is.null(asset$net)) frame$realized_net <- .analysis_assets_realized_net_v1(frame$day, asset$net$realized_net_steps)
  frame
}

# Tage ohne Bestand (#499): Zeilen mit Menge 0 und fehlende Tage des Rasters zwischen zwei Tagen mit Bestand; das Bild legt eine graue
# Flaeche darueber. Seit rc.367 (#541) sind Menge, Wert, Einstand und unrealisiert dort 0 - ein Komplettverkauf faellt an seinem Tag
# auf 0 wie jeder andere Verkauf, das Symbol steht dort. Kurs und Einstandskurs bleiben leer: Ohne Bestand fuehrt der Verlauf keinen
# Kurs (Kurse ohne Bestand kommen mit #526).
.analysis_assets_with_gaps_v1 <- function(frame, asset, grid = NULL) {
  frame$gap <- !is.na(frame$quantity) & frame$quantity == 0
  if (nrow(frame) >= 2L) {
    days <- if (is.null(grid)) NULL else sort(unique(as.Date(grid)))
    position <- if (is.null(days)) as.numeric(frame$day) else match(frame$day, days)
    if (!anyNA(position)) {
      jumps <- which(diff(position) > 1)
      if (length(jumps)) {
        extra <- do.call(rbind, lapply(jumps, function(index) {
          bounds <- if (is.null(days)) unique(c(frame$day[[index]] + 1, frame$day[[index + 1L]] - 1))
            else unique(days[c(position[[index]] + 1L, position[[index + 1L]] - 1L)])
          rows <- frame[rep(index, length(bounds)), , drop = FALSE]
          rows$day <- bounds; rows$quantity <- 0; rows$gap <- TRUE
          rows
        }))
        frame <- rbind(frame, extra)
        frame <- frame[order(frame$day), , drop = FALSE]
        rownames(frame) <- NULL
        frame$realized <- .analysis_assets_realized_v1(frame$day, asset$performance$realized_steps)
        if (!is.null(asset$net)) frame$realized_net <- .analysis_assets_realized_net_v1(frame$day, asset$net$realized_net_steps)
      }
    }
  }
  for (column in intersect(c("unit_value", "cost_average"), names(frame))) frame[[column]][frame$gap] <- NA_real_
  for (column in intersect(c("market_value", "cost_basis", "unrealised", "cost"), names(frame))) frame[[column]][frame$gap] <- 0
  frame
}

# Die Einstandslinie im Bild: Am Tag des Abgangs faellt sie auf 0, in der Luecke danach setzt sie aus, bis wieder Bestand da ist. Ihre
# Farbe in der Luecke folgt dem Tag davor, damit der Abfall nicht in einer anderen Farbe gezeichnet wird (#541).
.analysis_assets_cost_line_v1 <- function(frame) {
  values <- frame$cost_basis
  above <- !is.na(frame$market_value) & !is.na(values) & frame$market_value >= values
  gap <- if (is.null(frame$gap)) rep(FALSE, nrow(frame)) else frame$gap
  # Auf 0 faellt die Linie nur am Abgang - also nach einem Tag mit Bestand, nicht vor dem ersten Kauf (#526).
  first <- gap & c(FALSE, utils::head(!gap, -1L))
  values[gap & !first] <- NA_real_
  for (index in which(gap)) if (index > 1L) above[[index]] <- above[[index - 1L]]
  list(values = values, above = above)
}

# Graue Flaeche ueber den Tagen ohne Bestand - in jedem Teilbild, vor den Linien.
.analysis_assets_gap_bands_v1 <- function(frame) {
  gap <- if (is.null(frame$gap)) logical() else frame$gap
  if (!any(gap)) return(invisible(FALSE))
  runs <- rle(gap); ends <- cumsum(runs$lengths); starts <- ends - runs$lengths + 1L
  usr <- graphics::par("usr")
  for (index in which(runs$values)) {
    from <- as.numeric(frame$day[[starts[[index]]]]) - 0.5; to <- as.numeric(frame$day[[ends[[index]]]]) + 0.5
    graphics::rect(from, usr[[3L]], to, usr[[4L]], col = grDevices::adjustcolor(ANALYSIS_HISTORY_INK_V1[["grid"]], 0.65), border = NA)
  }
  invisible(TRUE)
}

# Rahmen einer Klasse: Wert (wie in der Zusammensetzung), Einstand, unrealisiert und realisiert je Tag.
analysis_assets_class_frame_v1 <- function(history, selection, period = "all", range = NULL) {
  days <- as.Date(unlist(history$portfolio$day))
  values <- if (identical(selection$kind, "group")) selection$group$value else history$portfolio$composition$values[[selection$key]]
  frame <- data.frame(day = days, market_value = if (is.null(values)) rep(0, length(days)) else analysis_history_number_v1(values),
                      cost_basis = analysis_history_number_v1(selection$group$basis), stringsAsFactors = FALSE)
  frame$unrealised <- frame$market_value - frame$cost_basis
  frame$realized <- .analysis_assets_realized_v1(days, selection$group$realized_steps)
  frame$cost <- if (is.null(selection$group$net_cost)) rep(NA_real_, nrow(frame)) else analysis_history_number_v1(selection$group$net_cost)
  frame$realized_net <- if (is.null(selection$group$net_realized_steps)) rep(NA_real_, nrow(frame)) else
    .analysis_assets_realized_net_v1(days, selection$group$net_realized_steps)
  held <- which(frame$market_value != 0 | frame$cost_basis != 0 | frame$realized != 0)
  if (length(held)) frame <- frame[seq(max(1L, held[[1L]] - 1L), nrow(frame)), , drop = FALSE]
  frame[analysis_history_window_v1(frame$day, period, range), , drop = FALSE]
}

# Die Symbole eines Assets: Buchungen mit Mengenaenderung und Dividenden, nach den gewaehlten Gruppen.
analysis_assets_marks_v1 <- function(asset, frame, groups = unname(ANALYSIS_ASSETS_GROUPS_V1)) {
  empty <- data.frame(day = as.Date(character()), kind = character(), value = numeric(), stringsAsFactors = FALSE); empty$events <- list()
  if (is.null(frame) || !nrow(frame)) return(empty)
  rows <- lapply(asset$trades, function(row) list(day = row$day, kind = row$kind, events = row$events))
  rows <- c(rows, lapply(asset$income, function(row) list(day = row$day, kind = "dividend", events = list(list(
    kind = "dividend", quantity = NULL, unit_price = NULL, amount = row$amount, fee = NULL, currency = row$currency, account = row$account, lots = list(),
    tax = row$tax)))))
  if (!length(rows)) return(empty)
  marks <- data.frame(day = as.Date(vapply(rows, function(row) row$day, character(1L))), kind = vapply(rows, function(row) row$kind, character(1L)),
                      stringsAsFactors = FALSE)
  marks$events <- lapply(rows, function(row) row$events)
  group_of <- vapply(marks$kind, function(kind) if (is.null(ANALYSIS_ASSETS_SYMBOLS_V1[[kind]])) "" else ANALYSIS_ASSETS_SYMBOLS_V1[[kind]]$group, character(1L))
  marks <- marks[group_of %in% groups & marks$day >= min(frame$day) & marks$day <= max(frame$day), , drop = FALSE]
  marks$value <- frame$market_value[match(marks$day, frame$day)]
  # Nach einem Verkauf ohne Restbestand ist der Tag ohne Bestand und sein Wert leer (#499): Das Symbol steht dann auf dem letzten
  # Wert davor - dort endet die Linie -, ohne einen solchen auf 0. Bis rc.360 fiel es weg (Festlegung 04.11.2026). Den letzten
  # Abgang traegt seit rc.367 der Abgangstag des Rahmens mit Wert 0 (#541); ohne ihn lag der Verkauf ausserhalb und fehlte weiter.
  for (index in which(is.na(marks$value))) {
    before <- which(frame$day <= marks$day[[index]] & !is.na(frame$market_value))
    marks$value[[index]] <- if (length(before)) frame$market_value[[max(before)]] else 0
  }
  # Komplettverkauf (#541): der Abgang am Tag, an dem der Bestand auf 0 faellt. Er wird nicht gebuendelt (analysis_assets_cluster_v1).
  quantity <- if (is.null(frame$quantity)) rep(NA_real_, nrow(frame)) else frame$quantity
  emptied <- frame$day[!is.na(quantity) & quantity == 0 & c(FALSE, utils::head(!is.na(quantity) & quantity > 0, -1L))]
  marks$exit <- marks$day %in% emptied & marks$kind %in% c("sell", "withdrawal", "other_out", "transfer_out")
  marks[order(marks$day), , drop = FALSE]
}

# Buendeln: Liegen Symbole derselben Art dichter, als ein Symbol breit ist, werden sie eines; die Zahl daneben nennt, wie viele.
analysis_assets_cluster_v1 <- function(marks, pixels_per_day, width_px) {
  empty <- data.frame(day = numeric(), kind = character(), value = numeric(), count = integer(), stringsAsFactors = FALSE); empty$members <- list()
  if (!nrow(marks)) return(empty)
  out <- list()
  for (kind in unique(marks$kind)) {
    rows <- marks[marks$kind == kind & !is.na(marks$value), , drop = FALSE]
    if (!nrow(rows)) next
    # Der Komplettverkauf bleibt einzeln an seinem Tag bei 0, wo die Linie auf 0 faellt (#541). Im Buendel stuende er auf dem
    # Median der Werte - bei zwei Verkaeufen auf halber Hoehe, bei dreien auf dem mittleren.
    exit <- if (is.null(rows$exit)) rep(FALSE, nrow(rows)) else rows$exit
    start <- 1L
    for (index in seq_len(nrow(rows))) {
      last <- index == nrow(rows)
      gap <- if (last || exit[[index]] || exit[[index + 1L]]) Inf else (as.numeric(rows$day[[index + 1L]]) - as.numeric(rows$day[[start]])) * pixels_per_day
      if (gap > width_px || last) {
        members <- rows[start:index, , drop = FALSE]
        out[[length(out) + 1L]] <- list(day = mean(as.numeric(members$day)), kind = kind, value = stats::median(members$value),
                                        count = nrow(members), members = list(members))
        start <- index + 1L
      }
    }
  }
  if (!length(out)) return(empty)
  clusters <- data.frame(day = vapply(out, function(row) row$day, numeric(1L)), kind = vapply(out, function(row) row$kind, character(1L)),
                         value = vapply(out, function(row) row$value, numeric(1L)), count = vapply(out, function(row) row$count, integer(1L)),
                         stringsAsFactors = FALSE)
  clusters$members <- lapply(out, function(row) row$members[[1L]])
  clusters
}

# Eine Stufenlinie, nach Vorzeichen gefaerbt: blau, wo 'above' gilt, sonst rot. Gleichfarbige Strecken werden in einem Zug
# gezeichnet - Einzelstuecke je Tag erschienen gestrichelt.
.analysis_assets_sign_steps_v1 <- function(days, values, above) {
  count <- length(values)
  if (count < 2L) return(invisible(NULL))
  x <- as.numeric(days); color <- ifelse(!is.na(above) & above, "gain", "loss")
  start <- 1L
  while (start < count) {
    if (is.na(values[[start]])) { start <- start + 1L; next }
    stop <- start
    while (stop + 1L < count && !is.na(values[[stop + 1L]]) && identical(color[[stop + 1L]], color[[start]])) stop <- stop + 1L
    last <- if (is.na(values[[stop + 1L]])) stop else stop + 1L
    graphics::lines(x[start:last], values[start:last], type = "s", col = ANALYSIS_ASSETS_SIGN_V1[[color[[start]]]], lwd = 2.4)
    if (last == stop) graphics::segments(x[[stop]], values[[stop]], x[[stop + 1L]], values[[stop]], col = ANALYSIS_ASSETS_SIGN_V1[[color[[start]]]], lwd = 2.4)
    start <- stop + 1L
  }
}

.analysis_assets_legend_v1 <- function(entries) {
  ink <- ANALYSIS_HISTORY_INK_V1
  graphics::legend(graphics::par("usr")[[1]], graphics::par("usr")[[4]] + diff(graphics::par("usr")[3:4]) * 0.12, horiz = TRUE, bty = "n",
                   cex = 0.8, text.col = ink[["secondary"]], xpd = NA, legend = vapply(entries, function(entry) entry$label, character(1L)),
                   col = vapply(entries, function(entry) entry$col, character(1L)),
                   pt.bg = vapply(entries, function(entry) if (is.null(entry$bg)) NA_character_ else entry$bg, character(1L)),
                   lty = vapply(entries, function(entry) if (is.null(entry$lty)) NA_real_ else entry$lty, numeric(1L)),
                   lwd = vapply(entries, function(entry) if (is.null(entry$lwd)) 1 else entry$lwd, numeric(1L)),
                   pch = vapply(entries, function(entry) if (is.null(entry$pch)) NA_real_ else entry$pch, numeric(1L)), pt.cex = 1.6, seg.len = 1.8,
                   text.width = graphics::strwidth(vapply(entries, function(entry) entry$label, character(1L)), cex = 0.8) + graphics::strwidth("MM", cex = 0.8))
}

# GuV-Feld: unrealisiert als Flaeche (ueber null blau, darunter rot), realisiert kumuliert als gestrichelte Stufe.
.analysis_assets_gain_panel_v1 <- function(frame, last, net = FALSE, now = NULL, xlim = range(frame$day)) {
  ink <- ANALYSIS_HISTORY_INK_V1
  gain <- if (net) frame$unrealised - frame$cost else frame$unrealised
  realized <- if (net) frame$realized_net else frame$realized
  # Netto kennt die Momentaufnahme keine Liquidationskosten: dort ohne Punkt.
  point <- if (is.null(now) || net) NA_real_ else now$unrealised
  span <- range(c(0, gain, realized, point), na.rm = TRUE); if (!all(is.finite(span))) span <- c(-1, 1)
  graphics::plot(frame$day, gain, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  .analysis_assets_gap_bands_v1(frame)
  .analysis_history_axis_values_v1(span)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  ok <- !is.na(gain)
  if (any(ok)) {
    positive <- ifelse(ok, pmax(gain, 0), 0); negative <- ifelse(ok, pmin(gain, 0), 0)
    graphics::polygon(c(frame$day, rev(frame$day)), c(positive, rep(0, nrow(frame))), col = grDevices::adjustcolor(ANALYSIS_ASSETS_SIGN_V1[["gain"]], 0.18), border = NA)
    graphics::polygon(c(frame$day, rev(frame$day)), c(negative, rep(0, nrow(frame))), col = grDevices::adjustcolor(ANALYSIS_ASSETS_SIGN_V1[["loss"]], 0.18), border = NA)
    .analysis_history_line_v1(frame$day, gain, ANALYSIS_ASSETS_LINE_V1)
  }
  if (any(realized != 0, na.rm = TRUE)) graphics::lines(frame$day, realized, type = "s", col = ink[["primary"]], lwd = 2, lty = 2)
  if (!is.na(point)) .analysis_moment_mark_v1(frame$day[[last]], gain[[last]], now$day, point, ANALYSIS_ASSETS_LINE_V1)
  graphics::mtext(if (net) "GuV netto (Projektion: Verkaufsgebühr und Steuer) · unrealisiert (Fläche) · realisiert nach Steuer, kumuliert (gestrichelt)"
                  else "GuV vor Steuern · unrealisiert (Fläche: Gewinn blau, Verlust rot) · realisiert, kumuliert (gestrichelt)", side = 3, line = 0.1,
                  adj = 0, cex = 0.8, col = ink[["secondary"]])
  .analysis_history_end_labels_v1(xlim[[2L]], c(if (is.na(point)) gain[[last]] else point, realized[[last]]), if (net) c("unrealisiert netto", "realisiert netto") else c("unrealisiert", "realisiert"),
                                  c(ANALYSIS_ASSETS_LINE_V1, ink[["primary"]]))
}

# Asset oder Klasse: Wert und Einstand, GuV; beim Asset dazu Kurs mit Einstandskurs, Menge und die Buchungssymbole.
analysis_assets_plot_v1 <- function(selection, frame, marks = NULL, net = FALSE, now = NULL) {
  if (isTRUE(selection$watched)) return(analysis_assets_watched_plot_v1(frame))
  ink <- ANALYSIS_HISTORY_INK_V1; asset <- identical(selection$kind, "asset")
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::layout(matrix(seq_len(if (asset) 4L else 2L)), heights = if (asset) c(2.4, 1.25, 1.2, 0.85) else c(2.4, 1.4))
  # Ab drei Teilbildern verkleinert R die Schrift von selbst; hier gilt dieselbe Groesse wie in den anderen Grafiken.
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(1.2, 7, 3.6, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2, cex = 1)
  span <- range(c(frame$market_value, frame$cost_basis, if (!is.null(now)) now$value), na.rm = TRUE); if (!all(is.finite(span))) span <- c(0, 1)
  span <- span + c(-1, 1) * diff(span) * 0.04
  # Alle Teilbilder teilen dieselbe Zeitachse - mit dem Punkt „jetzt“ reicht sie bis zu seinem Tag (#512).
  xlim <- range(c(frame$day, if (!is.null(now)) now$day))
  graphics::plot(frame$day, frame$market_value, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  gaps <- .analysis_assets_gap_bands_v1(frame)
  .analysis_history_axis_values_v1(span)
  cost_line <- .analysis_assets_cost_line_v1(frame)
  .analysis_assets_sign_steps_v1(frame$day, cost_line$values, cost_line$above)
  .analysis_history_line_v1(frame$day, frame$market_value, ANALYSIS_ASSETS_LINE_V1)
  clusters <- NULL
  if (asset && !is.null(marks)) {
    px <- graphics::grconvertX(graphics::par("usr")[1:2], "user", "device")
    pixels_per_day <- abs(diff(px)) / diff(graphics::par("usr")[1:2])
    width <- abs(graphics::grconvertY(0, "user", "device") - graphics::grconvertY(graphics::strheight("M", cex = ANALYSIS_ASSETS_SYMBOL_CEX_V1), "user", "device")) * 1.15
    clusters <- analysis_assets_cluster_v1(marks, pixels_per_day, width)
    for (index in seq_len(nrow(clusters))) {
      symbol <- ANALYSIS_ASSETS_SYMBOLS_V1[[clusters$kind[[index]]]]
      graphics::points(clusters$day[[index]], clusters$value[[index]], pch = symbol$pch, bg = symbol$col, col = ink[["surface"]],
                       cex = ANALYSIS_ASSETS_SYMBOL_CEX_V1, lwd = 1.6)
      if (clusters$count[[index]] > 1L) graphics::text(clusters$day[[index]], clusters$value[[index]], clusters$count[[index]], pos = 3,
                                                        offset = 1.1, cex = 0.75, col = ink[["primary"]], xpd = NA)
    }
  }
  last <- nrow(frame)
  if (!is.null(now)) .analysis_moment_mark_v1(frame$day[[last]], frame$market_value[[last]], now$day, now$value, ANALYSIS_ASSETS_LINE_V1)
  # Am Abgangstag (#541) sind Wert und Einstand 0: Die Farbe des Einstands folgt dann dem letzten Tag mit Bestand.
  signed <- if (!is.null(frame$quantity) && isTRUE(frame$quantity[[last]] == 0) && any(frame$quantity > 0, na.rm = TRUE)) max(which(frame$quantity > 0)) else last
  .analysis_history_end_labels_v1(xlim[[2L]], c(if (!is.null(now)) now$value else frame$market_value[[last]], frame$cost_basis[[last]]), c("Wert", "Einstand"),
                                  c(ANALYSIS_ASSETS_LINE_V1, if (isTRUE(frame$market_value[[signed]] >= frame$cost_basis[[signed]])) ANALYSIS_ASSETS_SIGN_V1[["gain"]] else ANALYSIS_ASSETS_SIGN_V1[["loss"]]))
  entries <- list(list(label = "Wert", col = ANALYSIS_ASSETS_LINE_V1, lty = 1, lwd = 2),
                  list(label = "Einstand, Wert darüber", col = ANALYSIS_ASSETS_SIGN_V1[["gain"]], lty = 1, lwd = 2.4),
                  list(label = "Einstand, Wert darunter", col = ANALYSIS_ASSETS_SIGN_V1[["loss"]], lty = 1, lwd = 2.4))
  if (!is.null(now)) entries[[length(entries) + 1L]] <- list(label = ANALYSIS_MOMENT_LEGEND_V1, col = ANALYSIS_HISTORY_INK_V1[["secondary"]], bg = ANALYSIS_HISTORY_INK_V1[["surface"]], pch = 21, lwd = 2)
  if (isTRUE(gaps)) entries[[length(entries) + 1L]] <- list(label = "kein Bestand", col = grDevices::adjustcolor(ANALYSIS_HISTORY_INK_V1[["grid"]], 0.65),
                                                            bg = grDevices::adjustcolor(ANALYSIS_HISTORY_INK_V1[["grid"]], 0.65), pch = 22)
  if (asset && any(frame$gap & !is.na(frame$unit_value), na.rm = TRUE))
    entries[[length(entries) + 1L]] <- list(label = ANALYSIS_ASSETS_FREE_LABEL_V1, col = ANALYSIS_ASSETS_FREE_V1, lty = 2, lwd = 2)
  if (!is.null(clusters) && nrow(clusters)) {
    # Feste Folge wie in der Tabelle der Symbole, nicht die Folge im Bild.
    present <- unique(vapply(clusters$kind, function(kind) ANALYSIS_ASSETS_SYMBOLS_V1[[kind]]$label, character(1L)))
    for (label in intersect(unique(vapply(ANALYSIS_ASSETS_SYMBOLS_V1, function(item) item$label, character(1L))), present)) {
      symbol <- Filter(function(item) identical(item$label, label), ANALYSIS_ASSETS_SYMBOLS_V1)[[1L]]
      entries[[length(entries) + 1L]] <- list(label = label, col = ink[["surface"]], bg = symbol$col, pch = symbol$pch)
    }
  }
  .analysis_assets_legend_v1(entries)
  graphics::par(mar = c(if (asset) 1.2 else 2.4, 7, 1.4, 9.5))
  .analysis_assets_gain_panel_v1(frame, last, net, now, xlim)
  if (asset) {
    graphics::par(mar = c(1.2, 7, 1.4, 9.5))
    prices <- frame$unit_value
    span <- range(c(prices, frame$cost_average, if (!is.null(now)) now$unit), na.rm = TRUE); if (!all(is.finite(span))) span <- c(0, 1)
    graphics::plot(frame$day, prices, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
    .analysis_assets_gap_bands_v1(frame)
    at <- pretty(span, n = 4L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
    graphics::axis(2, at = at, labels = analysis_history_axis_eur_v1(at, if (max(abs(span)) < 10) 2L else 0L), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
    .analysis_assets_sign_steps_v1(frame$day, frame$cost_average, !is.na(prices) & prices >= frame$cost_average)
    .analysis_assets_price_lines_v1(frame$day, prices, if (is.null(frame$gap)) rep(TRUE, nrow(frame)) else !frame$gap)
    if (!is.null(now)) .analysis_moment_mark_v1(frame$day[[last]], prices[[last]], now$day, now$unit, ANALYSIS_ASSETS_LINE_V1)
    graphics::mtext("Kurs je Einheit (gestrichelt: ohne Bestand) · Einstandskurs (Durchschnitt, Gewinnschwelle; blau, wenn der Kurs darüber liegt)", side = 3, line = 0.1,
                    adj = 0, cex = 0.8, col = ink[["secondary"]])
    # Am Abgangstag (#541) gibt es keinen Kurs: Die Beschriftung nennt dann den letzten Tag mit Kurs.
    priced <- if (is.na(prices[[last]]) && any(!is.na(prices))) max(which(!is.na(prices))) else last
    .analysis_history_end_labels_v1(xlim[[2L]], c(if (!is.null(now)) now$unit else prices[[priced]], frame$cost_average[[priced]]), c("Kurs", "Einstandskurs"),
                                    c(ANALYSIS_ASSETS_LINE_V1, if (isTRUE(prices[[priced]] >= frame$cost_average[[priced]])) ANALYSIS_ASSETS_SIGN_V1[["gain"]] else ANALYSIS_ASSETS_SIGN_V1[["loss"]]))
    graphics::par(mar = c(2.2, 7, 1.4, 9.5))
    quantity <- frame$quantity
    span <- range(c(0, quantity), na.rm = TRUE)
    graphics::plot(frame$day, quantity, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
    .analysis_assets_gap_bands_v1(frame)
    at <- pretty(span, n = 3L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
    graphics::axis(2, at = at, labels = formatC(at, format = "fg", big.mark = ".", decimal.mark = ","), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
    graphics::lines(frame$day, quantity, type = "s", col = ANALYSIS_ASSETS_LINE_V1, lwd = 2)
    graphics::mtext("Menge", side = 3, line = 0.1, adj = 0, cex = 0.8, col = ink[["secondary"]])
  }
  .analysis_history_axis_dates_v1(frame$day)
  geometry <- .analysis_history_geometry_v1()
  geometry$clusters <- clusters
  invisible(geometry)
}

# Kurs mit und ohne Bestand (#526): mit Bestand durchgezogen, ohne heller und gestrichelt - dort ist er kein Hebel des Vermoegens.
# Die gestrichelte Strecke reicht bis an den Nachbartag mit Bestand, damit beide Linien aneinander anschliessen.
.analysis_assets_price_lines_v1 <- function(days, prices, held) {
  held[is.na(held)] <- TRUE
  free <- !held
  if (any(free)) {
    joined <- free | c(free[-1L], FALSE) | c(FALSE, free[-length(free)])
    .analysis_history_line_v1(days, ifelse(joined, prices, NA_real_), ANALYSIS_ASSETS_FREE_V1, dashed = rep(TRUE, length(prices)))
  }
  .analysis_history_line_v1(days, ifelse(held, prices, NA_real_), ANALYSIS_ASSETS_LINE_V1)
}

# Beobachtet, nie gehalten (#526): nur der Kurs, gestrichelt - es gibt weder Wert noch Einstand noch Menge.
analysis_assets_watched_plot_v1 <- function(frame) {
  ink <- ANALYSIS_HISTORY_INK_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.4, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2, cex = 1)
  prices <- frame$unit_value
  span <- range(prices, na.rm = TRUE); if (!all(is.finite(span))) span <- c(0, 1)
  xlim <- range(frame$day)
  graphics::plot(frame$day, prices, type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  at <- pretty(span, n = 5L); graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_history_axis_eur_v1(at, if (max(abs(span)) < 10) 2L else 0L), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  .analysis_history_line_v1(frame$day, prices, ANALYSIS_ASSETS_FREE_V1, dashed = rep(TRUE, length(prices)))
  graphics::mtext("Kurs je Einheit in Euro · nie gehalten (gestrichelt: kein Hebel des Vermögens)", side = 3, line = 0.4, adj = 0, cex = 0.8, col = ink[["secondary"]])
  priced <- which(!is.na(prices))
  if (length(priced)) .analysis_history_end_labels_v1(xlim[[2L]], prices[[max(priced)]], "Kurs", ANALYSIS_ASSETS_FREE_V1)
  .analysis_history_axis_dates_v1(frame$day)
  geometry <- .analysis_history_geometry_v1()
  geometry$clusters <- NULL
  invisible(geometry)
}

# Abstand vom Hoch des Kurses (#506), nur beim einzelnen Asset: ueber die ganze Reihe gerechnet, im Zeitraum gezeigt; Kaeufe und
# Verkaeufe als Punkte darauf. So laesst sich pruefen, ob Kaeufe in den Rueckgangszonen lagen.
analysis_assets_drawdown_frame_v1 <- function(asset, period = "all", range = NULL, grid = NULL, held_only = FALSE) {
  full <- analysis_assets_asset_frame_v1(asset, "all", NULL, grid)
  if (is.null(full) || !nrow(full)) return(NULL)
  drawdown <- analysis_drawdown_v1(full$unit_value, !is.na(full$unit_value))
  keep <- analysis_history_window_v1(full$day, period, range)
  if (isTRUE(held_only)) keep <- keep & full$day %in% .analysis_assets_held_span_v1(full)$day
  data.frame(day = full$day[keep], drawdown = drawdown[keep], stringsAsFactors = FALSE)
}

# Kaeufe und Verkaeufe im Zeitraum mit dem Abstand vom Hoch an ihrem Tag; dazu je Zone, wie viele Kaeufe darin lagen.
analysis_assets_drawdown_trades_v1 <- function(frame, marks) {
  if (is.null(frame) || is.null(marks) || !nrow(marks)) return(data.frame(day = as.Date(character()), kind = character(), drawdown = numeric()))
  trades <- marks[marks$kind %in% c("buy", "sell"), c("day", "kind"), drop = FALSE]
  trades$drawdown <- frame$drawdown[match(trades$day, frame$day)]
  trades[!is.na(trades$drawdown), , drop = FALSE]
}

analysis_assets_drawdown_text_v1 <- function(frame, trades, zones = ANALYSIS_DISPLAY_V1$zones) {
  if (is.null(frame) || !any(!is.na(frame$drawdown))) return("Für diesen Zeitraum liegt kein Kurs vor.")
  values <- frame$drawdown[!is.na(frame$drawdown)]
  below <- function(value) paste0(formatC(abs(value) * 100, format = "f", digits = 1, decimal.mark = ","), " %")
  parts <- c(sprintf("Am Ende des Zeitraums %s unter dem bisherigen Hoch, am tiefsten %s.", below(values[[length(values)]]), below(min(values))))
  buys <- trades$drawdown[trades$kind == "buy"]
  if (length(buys)) {
    parts <- c(parts, sprintf("%d Käufe im Zeitraum, im Mittel %s unter dem Hoch.", length(buys), below(mean(buys))))
    for (zone in zones) parts <- c(parts, sprintf("Unter \u2212%d %%: %d von %d Käufen.", zone, sum(buys <= -zone / 100), length(buys)))
  }
  if (!length(zones)) parts <- c(parts, "Eigene Rückgangszonen lassen sich in der App „Daten“ unter „Einstellungen“ festlegen.")
  paste(parts, collapse = " ")
}

analysis_assets_drawdown_plot_v1 <- function(frame, trades, zones = ANALYSIS_DISPLAY_V1$zones, now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.2, 9.5), mgp = c(3, 0.6, 0), tcl = -0.2)
  bottom <- min(c(frame$drawdown, if (length(zones)) -max(zones) / 100 * 1.1 else NULL, -0.05), na.rm = TRUE)
  span <- c(bottom * 1.04, 0.02)
  graphics::plot(frame$day, rep(0, nrow(frame)), type = "n", xlim = range(c(frame$day, if (!is.null(now)) now$day)), ylim = span, axes = FALSE, xlab = "", ylab = "")
  .analysis_drawdown_zones_v1(zones, span[[1L]])
  at <- pretty(span, n = 4L); at <- at[at <= 0]
  graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_drawdown_axis_labels_v1(at), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  .analysis_history_line_v1(frame$day, frame$drawdown, ANALYSIS_ASSETS_LINE_V1)
  for (kind in c("buy", "sell")) {
    hit <- trades[trades$kind == kind, , drop = FALSE]; if (!nrow(hit)) next
    symbol <- ANALYSIS_ASSETS_SYMBOLS_V1[[kind]]
    graphics::points(hit$day, hit$drawdown, pch = symbol$pch, bg = symbol$col, col = ink[["surface"]], cex = 1.5, lwd = 1.2)
  }
  if (!is.null(now)) .analysis_moment_mark_v1(frame$day[[nrow(frame)]], frame$drawdown[[nrow(frame)]], now$day, now$drawdown, ANALYSIS_ASSETS_LINE_V1)
  .analysis_history_axis_dates_v1(frame$day)
  graphics::mtext("Kurs: Abstand vom bisherigen Hoch · Kauf grün, Verkauf violett", side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

# --- Kaufzeitpunkte gegen einen gedachten Sparplan (#504) ---------------------------------------------------------------------
# Festlegung (22.10.2026): messen, ob Kaeufe und Verkaeufe im Kurs guenstig lagen, unabhaengig von Renditeformeln. Massstab ist
# ein gedachter Sparplan ueber dasselbe Fenster: gleicher Euro-Betrag je Handelstag vom ersten bis zum letzten Kauf. Sein Ø Kurs ist
# das harmonische Mittel der Tageskurse. Verkaeufe spiegelbildlich: gleicher Erloes je Handelstag vom ersten bis zum letzten Verkauf
# (Festlegung 23.10.2026). Handelstage: bei Krypto jeder Tag, sonst Montag bis Freitag. Kurse in Euro wie in der Bewertung.
# Rewards, Ein- und Auslieferungen und Umbuchungen zaehlen nicht. Nur Anzeige.

ANALYSIS_ASSETS_PLAN_TEXT_V1 <- paste(
  "Eigener Ø Kurs gegen den Ø Kurs eines gleichmäßigen Plans über dasselbe Fenster: Bei Käufen ein Sparplan mit gleichem Euro-Betrag je Handelstag",
  "vom ersten bis zum letzten Kauf, bei Verkäufen derselbe Erlös je Handelstag vom ersten bis zum letzten Verkauf. Der Ø Kurs eines solchen Plans ist",
  "das harmonische Mittel der Tageskurse; der Vorteil des Sparplans ist damit schon eingerechnet. Der eigene Kurs enthält die Gebühren.",
  "Handelstage: bei Krypto jeder Tag, sonst Montag bis Freitag; Tage ohne Bestand haben keinen Kurs und zählen nicht. Rewards, Ein- und Auslieferungen und Umbuchungen zählen nicht. Negativer Abstand bei Käufen",
  "und positiver bei Verkäufen heißt: günstiger als der Plan.")

analysis_assets_plan_trades_v1 <- function(asset) {
  rows <- list()
  for (trade in asset$trades) {
    if (!trade$kind %in% c("buy", "sell")) next
    for (event in trade$events) {
      if (!identical(event$kind, trade$kind)) next
      quantity <- analysis_history_number_v1(list(event$quantity)); amount <- analysis_history_number_v1(list(event$amount))
      fee <- analysis_history_number_v1(list(event$fee)); if (is.na(fee)) fee <- 0
      rows[[length(rows) + 1L]] <- data.frame(day = as.Date(trade$day), kind = trade$kind, quantity = quantity, amount = amount, fee = fee,
        euro = identical(event$currency, "EUR"), stringsAsFactors = FALSE)
    }
  }
  if (!length(rows)) return(data.frame(day = as.Date(character()), kind = character(), quantity = numeric(), amount = numeric(), fee = numeric(), euro = logical()))
  do.call(rbind, rows)
}

.analysis_assets_trading_days_v1 <- function(days, crypto) if (isTRUE(crypto)) rep(TRUE, length(days)) else !format(days, "%u") %in% c("6", "7")

# Eine Art (Kaeufe oder Verkaeufe) in einem Zeitraum: eigener Ø Kurs, Ø Kurs des gleichmaessigen Plans, Abstand in Prozent und Euro.
analysis_assets_plan_row_v1 <- function(trades, prices, kind, crypto = FALSE) {
  own <- trades[trades$kind == kind & trades$euro & !is.na(trades$quantity) & trades$quantity > 0 & !is.na(trades$amount), , drop = FALSE]
  skipped <- sum(trades$kind == kind) - nrow(own)
  empty <- list(count = nrow(own), skipped = skipped, first = NA, last = NA, window_days = NA_integer_, own_price = NA_real_, plan_price = NA_real_,
                gap = NA_real_, euro = NA_real_, price_days = 0L)
  if (!nrow(own)) return(empty)
  first <- min(own$day); last <- max(own$day)
  quantity <- sum(own$quantity)
  total <- if (identical(kind, "buy")) sum(own$amount + own$fee) else sum(own$amount - own$fee)
  window <- prices[prices$day >= first & prices$day <= last & !is.na(prices$price) & prices$price > 0, , drop = FALSE]
  window <- window[.analysis_assets_trading_days_v1(window$day, crypto), , drop = FALSE]
  own_price <- total / quantity
  plan_price <- if (nrow(window)) nrow(window) / sum(1 / window$price) else NA_real_
  gap <- if (is.na(plan_price)) NA_real_ else own_price / plan_price - 1
  euro <- if (is.na(plan_price)) NA_real_ else if (identical(kind, "buy")) quantity * plan_price - total else total - quantity * plan_price
  list(count = nrow(own), skipped = skipped, first = first, last = last, window_days = as.integer(last - first) + 1L, own_price = own_price,
       plan_price = plan_price, gap = gap, euro = euro, price_days = nrow(window))
}

# Je Zeitraum (seit Beginn, dann jedes Kalenderjahr mit Kauf oder Verkauf) und Art eine Zeile.
analysis_assets_plan_table_v1 <- function(asset, grid = NULL) {
  trades <- analysis_assets_plan_trades_v1(asset)
  if (!nrow(trades)) return(data.frame())
  frame <- analysis_assets_asset_frame_v1(asset, "all", NULL, grid)
  prices <- data.frame(day = frame$day, price = frame$unit_value)
  crypto <- identical(asset$asset_type, "crypto")
  years <- sort(unique(format(trades$day, "%Y")))
  periods <- c(list(list(label = "Seit Beginn", keep = rep(TRUE, nrow(trades)))),
               lapply(years, function(year) list(label = year, keep = format(trades$day, "%Y") == year)))
  rows <- list()
  for (period in periods) for (kind in c("buy", "sell")) {
    part <- trades[period$keep, , drop = FALSE]
    if (!any(part$kind == kind)) next
    row <- analysis_assets_plan_row_v1(part, prices, kind, crypto)
    price <- function(value) if (is.na(value)) "–" else analysis_history_eur_v1(value, if (abs(value) < 10) 4L else 2L)
    rows[[length(rows) + 1L]] <- data.frame(
      Zeitraum = period$label, Art = if (identical(kind, "buy")) "Käufe" else "Verkäufe", Anzahl = as.character(row$count),
      Fenster = if (is.na(row$first)) "–" else sprintf("%s – %s (%d %s)", format(row$first, "%d.%m.%Y"), format(row$last, "%d.%m.%Y"), row$window_days,
                                                     if (identical(row$window_days, 1L)) "Tag" else "Tage"),
      `Eigener Ø Kurs` = price(row$own_price),
      `Ø Kurs gleichmäßig` = price(row$plan_price),
      Abstand = analysis_history_pct_v1(row$gap),
      `In Euro` = if (is.na(row$euro)) "–" else paste0(analysis_history_eur_signed_v1(row$euro),
        if (identical(kind, "buy")) (if (row$euro >= 0) " weniger bezahlt" else " mehr bezahlt") else (if (row$euro >= 0) " mehr erlöst" else " weniger erlöst")),
      Hinweis = paste(c(if (row$count < 3L) "weniger als drei – sagt wenig" else NULL,
                        if (row$skipped > 0L) sprintf("%d ohne Betrag in Euro nicht gezählt", row$skipped) else NULL,
                        if (!is.na(row$first) && row$price_days == 0L) "kein Kurs im Fenster" else NULL), collapse = "; "),
      check.names = FALSE, stringsAsFactors = FALSE)
  }
  if (!length(rows)) return(data.frame())
  do.call(rbind, rows)
}

analysis_assets_rows_v1 <- function(selection, frame, x, net = FALSE) {
  row <- frame[which.min(abs(as.numeric(frame$day) - x)), , drop = FALSE]
  # Beobachtet, nie gehalten (#526): nur der Kurs.
  if (isTRUE(selection$watched)) return(list(title = format(row$day, "%d.%m.%Y"), rows = list(
    list(label = "Kurs", value = analysis_history_eur_v1(row$unit_value, 2L), color = ANALYSIS_ASSETS_FREE_V1),
    list(label = "Bestand", value = "nie gehalten"))))
  sign <- if (isTRUE(row$market_value >= row$cost_basis)) ANALYSIS_ASSETS_SIGN_V1[["gain"]] else ANALYSIS_ASSETS_SIGN_V1[["loss"]]
  member <- analysis_assets_wallet_member_v1(selection)
  in_wallet <- function(value) if (member) ANALYSIS_ASSETS_IN_WALLET_V1 else value
  rows <- list(list(label = "Wert", value = analysis_history_eur_v1(row$market_value, 2L), color = ANALYSIS_ASSETS_LINE_V1),
               list(label = "Einstand", value = in_wallet(analysis_history_eur_v1(row$cost_basis, 2L)), color = sign),
               list(label = "unrealisiert", value = in_wallet(analysis_history_eur_signed_v1(row$unrealised, 2L))),
               list(label = "realisiert, kumuliert", value = analysis_history_eur_signed_v1(row$realized, 2L)))
  if (net) rows <- c(rows, list(
    list(label = "Liquidationskosten (Gebühr und Steuer, Projektion)", value = in_wallet(analysis_history_eur_v1(row$cost, 2L))),
    list(label = "unrealisiert netto", value = in_wallet(analysis_history_eur_signed_v1(row$unrealised - row$cost, 2L))),
    list(label = "realisiert netto, kumuliert", value = in_wallet(analysis_history_eur_signed_v1(row$realized_net, 2L)))))
  if (identical(selection$kind, "asset") && isTRUE(row$gap) && !is.na(row$unit_value)) rows <- c(rows, list(
    list(label = "Kurs ohne Bestand", value = analysis_history_eur_v1(row$unit_value, 2L), color = ANALYSIS_ASSETS_FREE_V1)))
  else if (identical(selection$kind, "asset")) rows <- c(rows, list(
    list(label = "Kurs", value = analysis_history_eur_v1(row$unit_value, 2L)),
    list(label = "Einstandskurs", value = in_wallet(analysis_history_eur_v1(row$cost_average, 2L))),
    list(label = "Menge", value = .analysis_history_quantity_v1(row$quantity))))
  list(title = format(row$day, "%d.%m.%Y"), rows = rows)
}

# Der angeklickte Punkt: das naechste Buendel innerhalb von 1,5 % der Zeitachse.
analysis_assets_cluster_at_v1 <- function(clusters, day, span) {
  if (is.null(day) || is.null(clusters) || !nrow(clusters)) return(NULL)
  distance <- abs(clusters$day - day)
  index <- which.min(distance)
  if (distance[[index]] > abs(span) * 0.015) return(NULL)
  clusters[index, , drop = FALSE]
}

.analysis_assets_money_v1 <- function(value, currency = "EUR") {
  if (is.null(value)) return("–")
  paste0(formatC(analysis_history_number_v1(list(value)), format = "f", digits = 2, big.mark = ".", decimal.mark = ","), if (is.null(currency)) "" else paste0(" ", currency))
}

# Die Buchungen eines Buendels; bei einem Verkauf die Rechnung je Lot (Anschaffung, Menge, Einstand, Erloes, GuV vor Steuern).
analysis_assets_cluster_rows_v1 <- function(cluster) {
  members <- cluster$members[[1L]]
  rows <- list()
  for (index in seq_len(nrow(members))) {
    # Ein Split (#451) ist keine Buchung: Er teilt die Lose, der Einstand bleibt.
    if (identical(members$kind[[index]], "split") && !length(members$events[[index]]))
      rows[[length(rows) + 1L]] <- list(label = paste(format(members$day[[index]], "%d.%m.%Y"), "Split"),
                                        value = "Lose im Verhältnis geteilt · Einstand bleibt", color = ANALYSIS_ASSETS_SYMBOLS_V1$split$col)
    for (event in members$events[[index]]) {
      kind <- ANALYSIS_HISTORY_EVENT_LABELS_V1[[if (event$kind %in% names(ANALYSIS_HISTORY_EVENT_LABELS_V1)) event$kind else "other"]]
      money <- function(value) .analysis_assets_money_v1(value, event$currency)
      parts <- c(if (!is.null(event$quantity)) paste(.analysis_history_quantity_v1(analysis_history_number_v1(list(event$quantity))), "Stück"),
                 if (!is.null(event$unit_price)) paste("zu", money(event$unit_price)),
                 if (!is.null(event$amount)) paste("· Betrag", money(event$amount)),
                 if (!is.null(event$fee) && analysis_history_number_v1(list(event$fee)) != 0) paste("· Gebühr", money(event$fee)),
                 if (!is.null(event$account)) paste("·", event$account))
      symbol <- ANALYSIS_ASSETS_SYMBOLS_V1[[event$kind]]
      rows[[length(rows) + 1L]] <- list(label = paste(format(members$day[[index]], "%d.%m.%Y"), kind), value = paste(parts, collapse = " "),
                                        color = if (is.null(symbol)) NULL else symbol$col)
      for (lot in event$lots) rows[[length(rows) + 1L]] <- list(
        label = paste0(" Lot vom ", if (is.null(lot$acquired)) "–" else format(as.Date(lot$acquired), "%d.%m.%Y")),
        value = sprintf("%s Stück · Einstand %s · Erlös %s · GuV %s", .analysis_history_quantity_v1(analysis_history_number_v1(list(lot$quantity))),
                        analysis_history_eur_v1(analysis_history_number_v1(list(lot$basis)), 2L), analysis_history_eur_v1(analysis_history_number_v1(list(lot$proceeds)), 2L),
                        analysis_history_eur_signed_v1(analysis_history_number_v1(list(lot$gain)), 2L)))
      # Netto-Sicht (#481): die projizierte Steuer des Ereignisses und was danach bleibt.
      if (!is.null(event$tax)) {
        tax <- analysis_history_number_v1(list(event$tax))
        gross <- if (length(event$lots)) sum(analysis_history_number_v1(lapply(event$lots, function(lot) lot$gain))) else
          if (identical(event$kind, "dividend")) analysis_history_number_v1(list(event$amount)) else NA_real_
        rows[[length(rows) + 1L]] <- list(label = "\u2003Steuer (Projektion)", value = paste0(analysis_history_eur_v1(tax, 2L),
          if (is.na(gross)) "" else paste0(" · netto ", analysis_history_eur_signed_v1(gross - tax, 2L))))
      }
    }
  }
  title <- if (nrow(members) == 1L) paste(format(members$day[[1L]], "%d.%m.%Y"), "· Buchungen dieses Tages")
    else sprintf("%d Buchungstage · %s bis %s", nrow(members), format(min(members$day), "%d.%m.%Y"), format(max(members$day), "%d.%m.%Y"))
  list(title = title, rows = rows)
}

# Kennzahlen je Zeitraum fuer die Auswahl, mit der Erfolgsbruecke (vor Steuern).
# Netto-Teile eines Zeitraums (#481): Steuer auf Realisiertes und auf Ertraege, Aenderung der Liquidationskosten, Erfolg netto.
.analysis_assets_net_columns_v1 <- function(periods) {
  net <- function(field) analysis_history_number_v1(lapply(periods, function(row) row$bridge$net[[field]]))
  warning <- vapply(periods, function(row) !is.null(row$bridge$net$warning), logical(1L))
  data.frame(`Steuer auf Realisiertes` = analysis_history_eur_signed_v1(-net("tax_realized")), `Steuer auf Erträge` = analysis_history_eur_signed_v1(-net("tax_income")),
             `Änderung Liquidationskosten` = analysis_history_eur_signed_v1(-net("cost_change")),
             `Anlageerfolg netto` = paste0(analysis_history_eur_signed_v1(net("gain")), ifelse(warning, " ¹", "")), check.names = FALSE, stringsAsFactors = FALSE)
}

# Der gewaehlte Vergleichsindex (#502) einer Zeitraumzeile: Eintrag in der Reihenfolge der Indizes; NULL ohne Index.
analysis_assets_benchmark_of_v1 <- function(row, index = 1L) {
  entries <- row$benchmarks
  if (!is.numeric(index) || length(index) != 1L || is.na(index) || index < 1L || index > length(entries)) NULL else entries[[index]]
}

# Auswahl des Vergleichsindex fuer Rangliste und Zeitraumtabellen; der erste ist vorgewaehlt.
analysis_assets_index_choices_v1 <- function(history) {
  indices <- if (is.null(history)) list() else history$benchmarks
  if (!length(indices)) return(c("Kein Vergleichsindex" = ""))
  stats::setNames(vapply(indices, function(row) as.character(row$ordinal), character(1L)), vapply(indices, function(row) row$label, character(1L)))
}

analysis_assets_index_number_v1 <- function(choice) {
  value <- suppressWarnings(as.integer(choice)); if (length(value) != 1L || is.na(value)) 1L else value
}

# Was ein Index enthaelt und ob Ausschuettungen mitzaehlen (#502).
analysis_assets_index_basis_text_v1 <- function(index) {
  if (is.null(index)) return("")
  parts <- vapply(index$components, function(part) sprintf("%s %s %%", part$label, sub(".", ",", part$weight_percent, fixed = TRUE)), character(1L))
  basis <- switch(as.character(index$basis),
    total_return = "mit Ausschüttungen",
    mixed = paste0("teils nur Kurs (", paste(vapply(Filter(function(part) !identical(part$basis, "total_return"), index$components), function(part) part$label, character(1L)), collapse = ", "), ")"),
    price_only = "nur Kurs – die Kursquelle liefert keine durchgehend bereinigten Kurse",
    "ohne Kurse")
  sprintf("%s (%s; %s)", index$label, paste(parts, collapse = ", "), basis)
}

analysis_assets_periods_table_v1 <- function(periods, view = "gross", index = 1L) {
  periods <- analysis_history_net_view_v1(periods, view)
  if (!length(periods)) return(data.frame())
  number <- function(field) analysis_history_number_v1(lapply(periods, function(row) row[[field]]))
  bridge <- function(field) analysis_history_number_v1(lapply(periods, function(row) row$bridge[[field]]))
  # "p. a." nur fuer mehrjaehrige Zeitraeume; ob die Haltedauer reicht, entscheidet die Veroeffentlichung (TWR: Tage mit
  # Bestand, IZF: Spanne).
  long <- vapply(periods, function(row) row$period %in% c("all", "3y", "5y"), logical(1L))
  held <- vapply(periods, function(row) if (is.null(row$held_days)) NA_integer_ else as.integer(row$held_days), integer(1L))
  data.frame(Zeitraum = vapply(periods, function(row) row$label, character(1L)),
             Von = format(as.Date(vapply(periods, function(row) row$start_day, character(1L))), "%d.%m.%Y"),
             Bis = format(as.Date(vapply(periods, function(row) row$end_day, character(1L))), "%d.%m.%Y"),
             `Tage mit Bestand` = ifelse(is.na(held), "–", formatC(held, format = "d", big.mark = ".", decimal.mark = ",")),
             Anfangswert = analysis_history_eur_v1(number("start_value")), Endwert = analysis_history_eur_v1(number("end_value")),
             Anlageerfolg = analysis_history_eur_signed_v1(number("gain")), realisiert = analysis_history_eur_signed_v1(bridge("realized")),
             `Änderung unrealisiert` = analysis_history_eur_signed_v1(bridge("unrealised_change")), Erträge = analysis_history_eur_signed_v1(bridge("income")),
             `zeitgewichtet (TWR)` = analysis_history_pct_v1(number("twr")), `geldgewichtet (IZF)` = analysis_history_pct_v1(number("mwr")),
             `TWR p. a.` = analysis_history_pct_v1(ifelse(long, number("twr_annualised"), NA_real_)),
             `IZF p. a.` = analysis_history_pct_v1(ifelse(long, number("mwr_annualised"), NA_real_)), check.names = FALSE, stringsAsFactors = FALSE) -> table
  table[["Timing-Effekt (IZF − TWR)"]] <- analysis_history_points_v1(number("mwr") - number("twr"))
  # Vergleichsindex (#482, #502) ueber dieselben Tage mit Bestand.
  if (any(vapply(periods, function(row) !is.null(analysis_assets_benchmark_of_v1(row, index)), logical(1L)))) {
    bench <- analysis_history_number_v1(lapply(periods, function(row) analysis_assets_benchmark_of_v1(row, index)$return))
    table[["Vergleichsindex (gleiche Tage)"]] <- analysis_history_pct_v1(bench)
    table[["Mehr-/Minderrendite"]] <- ifelse(is.na(bench) | is.na(number("twr")), "–",
      paste0(ifelse(number("twr") - bench < 0, "\u2212", "+"), formatC(abs(number("twr") - bench) * 100, format = "f", digits = 1, decimal.mark = ","), " Pp."))
  }
  if (!analysis_history_net_kind_v1(view)) return(table)
  # Netto: der Erfolg und seine Abzuege. Die Renditen bleiben vor Steuern und stehen dabei, gekennzeichnet (#499) - bis rc.295
  # fielen sie in dieser Sicht weg, ohne dass es erklaert war.
  rates <- table[, c("zeitgewichtet (TWR)", "geldgewichtet (IZF)", "TWR p. a.", "IZF p. a.", "Timing-Effekt (IZF − TWR)"), drop = FALSE]
  names(rates) <- paste(names(rates), "vor Steuern")
  cbind(table[, c("Zeitraum", "Von", "Bis", "Tage mit Bestand", "Anlageerfolg"), drop = FALSE], .analysis_assets_net_columns_v1(periods), rates)
}

# Die Buchungen eines Assets als Tabelle, neueste zuerst.
analysis_assets_bookings_table_v1 <- function(asset) {
  marks <- analysis_assets_marks_v1(asset, data.frame(day = as.Date(c("1900-01-01", "2999-12-31")), market_value = c(NA, NA)))
  rows <- list()
  for (index in rev(seq_len(nrow(marks)))) for (event in marks$events[[index]]) {
    rows[[length(rows) + 1L]] <- data.frame(Tag = format(marks$day[[index]], "%d.%m.%Y"),
      Art = ANALYSIS_HISTORY_EVENT_LABELS_V1[[if (event$kind %in% names(ANALYSIS_HISTORY_EVENT_LABELS_V1)) event$kind else "other"]],
      Menge = if (is.null(event$quantity)) "–" else .analysis_history_quantity_v1(analysis_history_number_v1(list(event$quantity))),
      Kurs = .analysis_assets_money_v1(event$unit_price, event$currency), Betrag = .analysis_assets_money_v1(event$amount, event$currency),
      Gebühr = .analysis_assets_money_v1(event$fee, event$currency), Konto = if (is.null(event$account)) "–" else event$account,
      `GuV (realisiert)` = if (length(event$lots)) analysis_history_eur_signed_v1(sum(analysis_history_number_v1(lapply(event$lots, function(lot) lot$gain))), 2L) else "",
      `Steuer (Projektion)` = if (is.null(event$tax)) "" else analysis_history_eur_v1(analysis_history_number_v1(list(event$tax)), 2L),
      check.names = FALSE, stringsAsFactors = FALSE)
  }
  if (!length(rows)) return(data.frame())
  table <- do.call(rbind, rows)
  if (all(table[["Steuer (Projektion)"]] == "")) table[["Steuer (Projektion)"]] <- NULL
  table
}

# Uebersicht je Klasse oder je Asset fuer einen Zeitraum; sortiert nach Anlageerfolg, TWR oder Wert am Ende.
# Rangliste gegen den Vergleichsindex (#502, Festlegung 22.10.2026): je Zeile der Index ueber dieselben Tage mit Bestand und der
# Abstand dazu; danach laesst sich sortieren. 'members' grenzt die Assets auf die Mitglieder einer eigenen Gruppe ein.
# Ohne Index-Sortierung: Die Rangliste gegen einen Index steht seit rc.309 im Reiter "Vergleich" (analysis_ranking_table_v1).
ANALYSIS_ASSETS_SORTS_V1 <- c("Anlageerfolg" = "gain", "zeitgewichtete Rendite" = "twr", "Timing-Effekt" = "timing", "Wert am Ende" = "value")

analysis_assets_overview_table_v1 <- function(history, kind, period, sort = "gain", view = "gross", members = NULL, index = 1L) {
  entries <- if (identical(kind, "groups")) lapply(history$groups, function(row) list(name = row$label, class = "", periods = row$periods))
    else if (identical(kind, "classes")) lapply(history$classes, function(row) list(name = ANALYSIS_HISTORY_CLASSES_V1[[row$class]]$label, class = "", periods = row$periods))
    else lapply(Filter(function(row) is.null(members) || row$label %in% members, history$assets), function(row) list(name = row$label, class = {
      key <- if (row$asset_type %in% c("fund", "etf")) "fund" else if (row$asset_type %in% names(ANALYSIS_HISTORY_CLASSES_V1)) row$asset_type else "other"
      ANALYSIS_HISTORY_CLASSES_V1[[key]]$label }, periods = row$performance$periods))
  # Netto je Topf (#501): die Bruecke je Topf in die Netto-Felder.
  if (identical(view, "net")) entries <- lapply(entries, function(entry) { entry$periods <- analysis_history_pooled_v1(entry$periods); entry })
  indexed <- length(history$benchmarks) >= index && index >= 1L
  rows <- list()
  for (entry in entries) {
    hit <- Filter(function(row) identical(row$period, period), entry$periods)
    if (length(hit) != 1L) next
    row <- hit[[1L]]; number <- function(field) analysis_history_number_v1(list(row[[field]])); bridge <- function(field) analysis_history_number_v1(list(row$bridge[[field]]))
    long <- row$period %in% c("all", "3y", "5y")
    net_gain <- analysis_history_number_v1(list(row$bridge$net$gain))
    chosen <- analysis_assets_benchmark_of_v1(row, index)
    bench <- analysis_history_number_v1(list(chosen$return)); bench_pa <- analysis_history_number_v1(list(chosen$annualised))
    excess <- number("twr") - bench; excess_pa <- if (long) number("twr_annualised") - bench_pa else NA_real_
    timing <- number("mwr") - number("twr")
    key <- if (analysis_history_net_kind_v1(view) && identical(sort, "gain")) net_gain
      else c(gain = number("gain"), twr = number("twr"), excess = excess, excess_annualised = excess_pa, timing = timing, value = number("end_value"))[[sort]]
    rows[[length(rows) + 1L]] <- list(sort = key, net = .analysis_assets_net_columns_v1(list(row)),
                                      index = data.frame(`Index (gleiche Tage)` = analysis_history_pct_v1(bench), `Mehr-/Minderrendite` = .analysis_compare_points_v1(excess),
                                                         `Mehr-/Minderrendite p. a.` = .analysis_compare_points_v1(excess_pa), check.names = FALSE, stringsAsFactors = FALSE),
                                      frame = data.frame(
      Name = entry$name, Klasse = entry$class, Von = format(as.Date(row$start_day), "%d.%m.%Y"), Bis = format(as.Date(row$end_day), "%d.%m.%Y"),
      # Neben jeder Rate die Haltedauer: Ein kurz gehaltener Treffer soll nicht wie eine lange Leistung aussehen.
      `Tage mit Bestand` = if (is.null(row$held_days)) "–" else formatC(as.integer(row$held_days), format = "d", big.mark = ".", decimal.mark = ","),
      `Wert am Anfang` = analysis_history_eur_v1(number("start_value")), `Wert am Ende` = analysis_history_eur_v1(number("end_value")),
      Anlageerfolg = analysis_history_eur_signed_v1(number("gain")),
      realisiert = analysis_history_eur_signed_v1(bridge("realized")), `Änderung unrealisiert` = analysis_history_eur_signed_v1(bridge("unrealised_change")),
      Erträge = analysis_history_eur_signed_v1(bridge("income")), `TWR` = analysis_history_pct_v1(number("twr")), `IZF` = analysis_history_pct_v1(number("mwr")),
      `TWR p. a.` = if (long) analysis_history_pct_v1(number("twr_annualised")) else "–", `IZF p. a.` = if (long) analysis_history_pct_v1(number("mwr_annualised")) else "–",
      `Timing-Effekt` = analysis_history_points_v1(timing), check.names = FALSE, stringsAsFactors = FALSE))
  }
  if (!length(rows)) return(data.frame())
  order <- order(-vapply(rows, function(row) if (is.na(row$sort)) -Inf else row$sort, numeric(1L)))
  table <- do.call(rbind, lapply(rows[order], function(row) row$frame))
  if (analysis_history_net_kind_v1(view)) {
    net <- do.call(rbind, lapply(rows[order], function(row) row$net))
    rates <- table[, c("TWR", "IZF", "TWR p. a.", "IZF p. a.", "Timing-Effekt"), drop = FALSE]
    names(rates) <- paste(names(rates), "vor Steuern")
    table <- cbind(table[, c("Name", "Klasse", "Von", "Bis", "Tage mit Bestand", "Wert am Anfang", "Wert am Ende", "Anlageerfolg"), drop = FALSE], net, rates)
  }
  if (indexed) {
    index <- do.call(rbind, lapply(rows[order], function(row) row$index))
    if (!any(period %in% c("all", "3y", "5y"))) index[["Mehr-/Minderrendite p. a."]] <- NULL
    table <- cbind(table, index)
  }
  if (kind %in% c("classes", "groups")) table$Klasse <- NULL
  table
}

# Auswahl, welche Assets die Tabelle "Je Asset" zeigt: alle oder die Mitglieder einer eigenen Gruppe.
analysis_assets_member_choices_v1 <- function(history) {
  groups <- if (is.null(history)) list() else history$groups
  # Ohne Gruppen nur "Alle Assets": paste0("group:", character(0)) ergaebe "group:" mit dem Namen NA (#490).
  if (!length(groups)) return(c("Alle Assets" = ""))
  c("Alle Assets" = "", stats::setNames(paste0("group:", vapply(groups, function(row) as.character(row$ordinal), character(1L))),
                                        vapply(groups, function(row) paste("Gruppe", row$label), character(1L))))
}

analysis_assets_members_v1 <- function(history, choice) {
  if (is.null(history) || !is.character(choice) || !startsWith(choice, "group:")) return(NULL)
  hit <- Filter(function(row) identical(paste0("group:", row$ordinal), choice), history$groups)
  if (length(hit) == 1L) unlist(hit[[1L]]$member_labels) else NULL
}

analysis_assets_period_choices_v1 <- function(history) {
  periods <- history$investment$periods
  stats::setNames(vapply(periods, function(row) row$period, character(1L)), vapply(periods, function(row) row$label, character(1L)))
}

analysis_assets_ui_v1 <- function() shiny::tagList(
  portelyra_card(
    "Asset oder Assetklasse",
    copy = "Wert und Einstand über die Zeit, darunter die GuV vor Steuern; beim einzelnen Asset dazu Kurs, Menge und Buchungen. Ohne Bestand ist der Kurs gestrichelt.",
    note = portelyra_note_v1(title = "So lesen Sie das Bild", id = "analysis-asset",
      "Der Einstand ist blau, solange der Wert darüber liegt, und rot, wenn er darunter liegt. Unrealisiert steht als Fläche, realisiert kumuliert gestrichelt.",
      "Beim einzelnen Asset dazu Kurs mit Einstandskurs, Menge und die Buchungen als Symbole; dicht liegende Buchungen derselben Art sind zu einem Symbol gebündelt (die Zahl nennt, wie viele). Ein Klick auf ein Symbol zeigt die Buchungen, bei einem Verkauf die Rechnung je Lot.",
      "Ohne Bestand – noch nicht, zwischenzeitlich oder nicht mehr gehalten – ist die Fläche grau und der Kurs gestrichelt: Er zeigt den Markt, keinen Hebel Ihres Vermögens. Ein Komplettverkauf fällt an seinem Tag auf 0.",
      "„nur Zeit mit Bestand“ zeigt die Zeit vom ersten Kauf bis zum letzten Verkauf. Beobachtete, nie gehaltene Assets stehen unten in der Auswahl; sie haben nur den Kurs."),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("history_asset", "Asset oder Klasse", c("Bitte warten" = ""), width = "420px"),
      shiny::selectInput("history_asset_account", "Konto", c("Alle Konten" = ""), width = "300px", selectize = FALSE),
      shiny::checkboxGroupInput("history_asset_symbols", "Symbole", ANALYSIS_ASSETS_GROUPS_V1, selected = unname(ANALYSIS_ASSETS_GROUPS_V1)),
      shiny::radioButtons("history_asset_view", "GuV und Kennzahlen", ANALYSIS_HISTORY_VIEWS_V1, selected = "gross"),
      # Nur Zeit mit Bestand (#526): vom ersten Kauf bis einschliesslich zum Abgangstag; sonst auch der Kurs davor, danach und dazwischen.
      shiny::checkboxInput("history_asset_held", "nur Zeit mit Bestand", value = FALSE)),
    shiny::uiOutput("history_asset_part_state"),
    shiny::uiOutput("history_asset_net_state"),
    shiny::uiOutput("history_asset_account_state"),
    shiny::uiOutput("history_asset_group_state"),
    shiny::uiOutput("history_asset_title"),
    analysis_history_zoomable_v1("zeitraum", "asset",
      shiny::plotOutput("history_asset_plot", height = "700px", hover = shiny::hoverOpts("history_asset_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE),
                        click = shiny::clickOpts("history_asset_click", clip = FALSE)),
      shiny::uiOutput("history_asset_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("history_asset_free_note"),
    shiny::uiOutput("history_asset_moment_note"),
    shiny::conditionalPanel("input.history_asset && (input.history_asset.indexOf('asset:') === 0 || input.history_asset.indexOf('watched:') === 0)",
      shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Abstand vom Hoch"),
      shiny::plotOutput("history_asset_drawdown", height = "220px"),
      shiny::p(class = "pl-field-hint", shiny::textOutput("history_asset_drawdown_text", inline = TRUE))),
    shiny::conditionalPanel("input.history_asset && input.history_asset.indexOf('asset:') === 0",
      shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Kaufzeitpunkte gegen einen gedachten Sparplan"),
      portelyra_note_v1(ANALYSIS_ASSETS_PLAN_TEXT_V1, title = "So lesen Sie den Vergleich mit dem Sparplan", id = "analysis-plan"),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_asset_plan"))),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Kennzahlen je Zeitraum"),
    portelyra_note_v1(title = "So lesen Sie die Kennzahlen", id = "analysis-asset-periods",
      "Je Zeitraum ab dem ersten Bestand: Anlageerfolg vor Steuern mit realisiertem Ergebnis, Änderung des unrealisierten und Erträgen; zeit- und geldgewichtete Rendite.",
      "„TWR p. a.“ rechnet über die Tage mit Bestand: Wer zwischendurch ganz ausgestiegen ist, verdünnt die Jahresrate nicht. Der IZF gewichtet das Kapital ohnehin nach der Zeit, in der es angelegt war.",
      paste(ANALYSIS_HISTORY_RETURNS_INCLUDE_V1, "Den Vergleich mit einem Index zeigt der Reiter „Vergleich“.")),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_asset_periods")),
    shiny::conditionalPanel("input.history_asset && input.history_asset.indexOf('asset:') === 0",
      shiny::tags$details(shiny::tags$summary("Buchungen dieses Assets"),
        shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_asset_bookings"))))),
  portelyra_card(
    "Rendite je Klasse und je Asset",
    copy = "Für einen Zeitraum je Assetklasse und je Asset: Anlageerfolg und seine Teile, zeit- und geldgewichtete Rendite.",
    note = portelyra_note_v1(title = "So lesen Sie die Tabellen", id = "analysis-overview",
      "Jedes Asset zählt ab seinem ersten Bestand; „TWR p. a.“ rechnet über die Tage mit Bestand und steht ab einem Jahr mit Bestand. Die Tage mit Bestand stehen daneben: Ein kurz gehaltener Treffer ist keine lange Leistung.",
      "Beginnt der Zeitraum, während ein Asset schon gehalten wird (Wert am Anfang nicht 0), zählt nur, was im Zeitraum entstand: Wird dann ein früher aufgelaufener Verlust realisiert, steht er voll unter „realisiert“ und zugleich als positive „Änderung unrealisiert“ – der Verlust war am Anfang schon da und ist danach weg.",
      paste("Sicht brutto: Anlageerfolg vor Steuern = realisiert + Änderung unrealisiert + Erträge (dazu Wertänderungen von Ein- und Auslieferungen),",
            "daneben zeit- und geldgewichtete Rendite. Sicht netto: derselbe Erfolg abzüglich projizierter Steuer auf Realisiertes und Erträge",
            "und der Änderung der Liquidationskosten (Verkaufsgebühr und Steuer eines gedachten Verkaufs). Die Renditen bleiben in beiden Sichten vor Steuern."),
      paste(ANALYSIS_HISTORY_RETURNS_INCLUDE_V1, ANALYSIS_HISTORY_TIMING_TEXT_V1)),
    shiny::div(class = "pl-form-grid",
      shiny::uiOutput("history_overview_period_ui"),
      shiny::selectInput("history_overview_sort", "Sortiert nach", ANALYSIS_ASSETS_SORTS_V1, selectize = FALSE),
      shiny::radioButtons("history_overview_view", "Sicht", ANALYSIS_HISTORY_VIEWS_V1, selected = "gross")),
    shiny::uiOutput("history_overview_net_state"),

    shiny::h4(class = "pl-section-title", "Je Assetklasse"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_overview_classes")),
    shiny::uiOutput("history_overview_groups_block"),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Je Asset"),
    shiny::selectInput("history_overview_members", "Eingrenzen auf", c("Alle Assets" = ""), width = "360px", selectize = FALSE),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_overview_assets"))))

# Server des Reiters; 'spec' ist der Zeitraum der Seite (#531), 'geometry' die gemerkte Zeitachse der Bilder.
analysis_assets_server_v1 <- function(input, output, session, ready, spec, geometry, hydrate = function(entry) entry, moment = function() NULL) {
  shiny::observeEvent(ready(), {
    history <- ready()
    shiny::updateSelectInput(session, "history_asset", choices = analysis_assets_choices_v1(history))
  }, ignoreNULL = TRUE)
  # Der Zeitraum oben (#531 Punkt 1): seine Grenzen und, fuer die Tabellen je Klasse und Asset, der passende Zeitraum.
  bounds <- shiny::reactive(analysis_history_bounds_v1(ready(), spec()))
  overview_offer <- shiny::reactive({ history <- ready(); if (is.null(history)) NULL else analysis_history_offer_v1(history$investment$periods, bounds()) })
  output$history_overview_period_ui <- shiny::renderUI({
    offer <- overview_offer(); if (is.null(offer)) return(NULL)
    analysis_history_offer_ui_v1("history_overview_period", offer, shiny::isolate(input$history_overview_period), analysis_history_window_label_v1(spec(), bounds()))
  })
  overview_key <- shiny::reactive({ offer <- overview_offer(); key <- if (is.null(offer)) NULL else analysis_history_offer_key_v1(offer, input$history_overview_period)
    if (is.null(key)) "" else key })
  # Eigene Kennzahlen ohne Index (seit rc.309); Index 0 heisst: keine Index-Spalten.
  index_choice <- function() 0L
  # Die Tagesreihen der Auswahl aus ihrer Teildatei (#503); laesst sie sich nicht lesen, sagt die Karte das statt leer zu bleiben.
  part_error <- shiny::reactiveVal(NULL)
  chosen <- shiny::reactive({
    picked <- analysis_assets_selection_v1(ready(), input$history_asset)
    if (is.null(picked)) { part_error(NULL); return(NULL) }
    loaded <- tryCatch({
      if (identical(picked$kind, "asset")) picked$asset <- hydrate(picked$asset) else picked$group <- hydrate(picked$group)
      picked
    }, error = function(error) structure(list(code = if (is.character(error$code)) error$code else "display_boundary_failed"), class = "part_failure"))
    if (inherits(loaded, "part_failure")) { part_error(loaded$code); return(NULL) }
    part_error(NULL); loaded
  })
  output$history_asset_part_state <- shiny::renderUI({
    code <- part_error(); if (is.null(code)) return(NULL)
    portelyra_status_panel("Die Tagesreihen dieser Auswahl ließen sich nicht lesen",
      if (identical(code, "display_no_latest")) "Inzwischen ist ein neuer Stand veröffentlicht. „Neu lesen“ oben lädt ihn."
      else paste("„Neu lesen“ oben lädt den Stand neu.", pl_error_text_v1(code)), tone = "warning")
  })
  # Ein Asset auf mehreren Konten: die Konten zur Wahl; ein anderes Asset setzt die Wahl auf "Alle Konten" zurueck.
  shiny::observeEvent(input$history_asset, shiny::updateSelectInput(session, "history_asset_account", choices = analysis_assets_account_choices_v1(chosen()),
                                                                    selected = ""), ignoreNULL = FALSE)
  selection <- shiny::reactive(analysis_assets_account_selection_v1(chosen(), input$history_asset_account))
  # Netto (#481): Verkaufsgebuehr und Steuer als Projektion; die Renditen bleiben vor Steuern. Zwei Netto-Sichten (#501):
  # je Topf im Jahr (Vorgabe) und je Asset ohne Verrechnung - die Auswahl tauscht nur, welche Felder gelesen werden.
  net_view <- shiny::reactive(analysis_history_net_kind_v1(input$history_asset_view))
  view_choice <- shiny::reactive(if (is.null(input$history_asset_view)) "gross" else input$history_asset_view)
  viewed <- shiny::reactive({ picked <- selection(); if (is.null(picked)) NULL else analysis_history_net_view_v1(picked, view_choice()) })
  frame <- shiny::reactive({
    picked <- viewed(); window <- spec()
    if (is.null(picked)) return(NULL)
    if (identical(picked$kind, "asset")) analysis_assets_asset_frame_v1(picked$asset, window$period, window$range, grid = unlist(ready()$portfolio$day),
                                                                        held_only = isTRUE(input$history_asset_held))
    else analysis_assets_class_frame_v1(ready(), picked, window$period, window$range)
  })
  # Tage ohne Bestand im Zeitraum (#526): gezaehlt und benannt, damit der gestrichelte Kurs nicht als Rendite gelesen wird.
  output$history_asset_free_note <- shiny::renderUI({
    picked <- viewed(); current <- frame()
    if (is.null(picked) || !identical(picked$kind, "asset")) return(NULL)
    text <- analysis_assets_free_note_v1(current, isTRUE(picked$watched)); if (is.null(text)) return(NULL)
    shiny::p(class = "pl-field-hint", text)
  })
  marks <- shiny::reactive({
    picked <- viewed(); current <- frame()
    if (is.null(picked) || !identical(picked$kind, "asset") || is.null(current)) return(NULL)
    analysis_assets_marks_v1(picked$asset, current, if (is.null(input$history_asset_symbols)) character() else input$history_asset_symbols)
  })
  # Punkt „jetzt“ (#512): der Bestand des letzten Tages zum zuletzt abgerufenen Kurs.
  now <- shiny::reactive({ model <- moment(); if (is.null(model)) NULL else analysis_moment_selection_v1(model, ready(), viewed(), frame()) })
  output$history_asset_plot <- shiny::renderPlot({
    current <- frame(); shiny::req(current, nrow(current) > 1L)
    geometry$asset <- analysis_assets_plot_v1(viewed(), current, marks(), net_view(), now())
  })
  output$history_asset_moment_note <- shiny::renderUI({
    point <- now(); if (is.null(point)) return(NULL)
    analysis_moment_note_v1(moment(), paste0("Wert jetzt ", analysis_history_eur_v1(point$value, 2L), " · seit dem letzten Tagesschluss ", analysis_history_pct_v1(point$rate, 2L),
      if (net_view()) " · netto ohne Punkt: Die Momentaufnahme rechnet keine Liquidationskosten" else "", "."), point$ordinals)
  })
  # Abstand vom Hoch des Kurses (#506), nur beim einzelnen Asset.
  drawdown <- shiny::reactive({
    picked <- viewed(); window <- spec()
    if (is.null(picked) || !identical(picked$kind, "asset")) return(NULL)
    frame <- analysis_assets_drawdown_frame_v1(picked$asset, window$period, window$range, grid = unlist(ready()$portfolio$day),
                                               held_only = isTRUE(input$history_asset_held))
    all_marks <- analysis_assets_marks_v1(picked$asset, frame(), "trades")
    point <- now()
    point <- if (is.null(point) || is.null(frame) || !nrow(frame)) NULL else list(day = point$day, drawdown = analysis_moment_drawdown_v1(frame$drawdown[[nrow(frame)]], point$rate))
    list(frame = frame, trades = analysis_assets_drawdown_trades_v1(frame, all_marks), now = if (is.null(point) || is.na(point$drawdown)) NULL else point)
  })
  output$history_asset_drawdown <- shiny::renderPlot({
    current <- drawdown(); shiny::req(current, !is.null(current$frame), nrow(current$frame) > 1L, any(!is.na(current$frame$drawdown)))
    analysis_assets_drawdown_plot_v1(current$frame, current$trades, now = current$now)
  })
  output$history_asset_drawdown_text <- shiny::renderText({
    current <- drawdown(); shiny::req(current); analysis_assets_drawdown_text_v1(current$frame, current$trades)
  })
  clicked <- shiny::reactiveVal(NULL)
  shiny::observeEvent(list(input$history_asset, input$history_asset_account, spec(), input$history_asset_symbols), clicked(NULL), ignoreInit = TRUE)
  shiny::observeEvent(input$history_asset_click, {
    day <- analysis_history_pixel_day_v1(geometry$asset, input$history_asset_click)
    cluster <- if (is.null(day) || is.null(geometry$asset)) NULL else analysis_assets_cluster_at_v1(geometry$asset$clusters, day, diff(geometry$asset$usr))
    clicked(if (is.null(cluster)) NULL else list(cluster = cluster, event = input$history_asset_click))
  })
  output$history_asset_overlay <- shiny::renderUI({
    current <- frame(); hover <- input$history_asset_hover; pick <- clicked(); picked <- viewed()
    if (is.null(current) || !nrow(current) || is.null(picked)) return(NULL)
    parts <- list()
    near <- !is.null(pick) && !is.null(hover) && !is.null(hover$coords_css) && abs(as.numeric(hover$coords_css$x) - as.numeric(pick$event$coords_css$x)) < 60
    day <- analysis_history_pixel_day_v1(geometry$asset, hover)
    point <- now()
    if (!is.null(day)) {
      content <- if (analysis_moment_hovered_v1(point, current$day, day)) analysis_moment_selection_rows_v1(point, moment()) else analysis_assets_rows_v1(picked, current, day, net_view())
      parts <- c(parts, list(.analysis_history_box_v1(hover, content$title, content$rows, box = !near, geometry = geometry$asset)))
    }
    if (!is.null(pick)) { content <- analysis_assets_cluster_rows_v1(pick$cluster); parts <- c(parts, list(.analysis_history_box_v1(pick$event, content$title, content$rows, line = FALSE, geometry = geometry$asset))) }
    shiny::tagList(parts)
  })
  # Kaufzeitpunkte gegen einen gedachten Sparplan (#504): ueber alle Konten des Assets, seit Beginn und je Kalenderjahr.
  output$history_asset_plan <- shiny::renderTable({
    picked <- viewed(); shiny::req(picked, identical(picked$kind, "asset"))
    table <- analysis_assets_plan_table_v1(picked$asset, grid = unlist(ready()$portfolio$day))
    shiny::validate(shiny::need(nrow(table) > 0L, "Für dieses Asset gibt es keine Käufe oder Verkäufe."))
    analysis_history_tint_v1(table)
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$history_asset_periods <- shiny::renderTable({
    picked <- selection(); shiny::req(picked, !isTRUE(picked$watched))
    analysis_history_tint_v1(analysis_assets_periods_table_v1(analysis_history_rows_in_v1(picked$periods, bounds()), view_choice(), index_choice()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$history_asset_net_state <- shiny::renderUI({
    history <- ready(); picked <- selection()
    if (is.null(history) || !net_view()) return(NULL)
    if (!is.null(picked) && !is.null(picked$account) && identical(view_choice(), "net"))
      return(shiny::p(class = "pl-field-hint", "Je Konto gibt es Netto nur ohne Verrechnung: Kapitalerträge verrechnen sich je Institut und Jahr, nicht je Konto. Bitte „netto, je Asset ohne Verrechnung“ wählen oder „Alle Konten“."))
    shiny::p(class = "pl-field-hint", analysis_history_net_note_v1(history, if (!is.null(picked) && identical(picked$kind, "asset")) picked$asset else NULL, view_choice()))
  })
  output$history_overview_net_state <- shiny::renderUI({
    history <- ready(); if (is.null(history) || !analysis_history_net_kind_v1(input$history_overview_view)) return(NULL)
    shiny::p(class = "pl-field-hint", analysis_history_net_note_v1(history, view = input$history_overview_view))
  })
  output$history_asset_bookings <- shiny::renderTable({
    picked <- viewed(); shiny::req(picked, identical(picked$kind, "asset")); analysis_assets_bookings_table_v1(picked$asset)
  }, striped = TRUE, spacing = "xs")
  overview <- function(kind) shiny::renderTable({
    history <- shiny::req(ready())
    analysis_history_tint_v1(analysis_assets_overview_table_v1(history, kind, overview_key(),
                                      if (is.null(input$history_overview_sort)) "gain" else input$history_overview_sort,
                                      if (is.null(input$history_overview_view)) "gross" else input$history_overview_view,
                                      if (identical(kind, "assets")) analysis_assets_members_v1(history, input$history_overview_members) else NULL, index_choice()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  shiny::observeEvent(ready(), shiny::updateSelectInput(session, "history_overview_members", choices = analysis_assets_member_choices_v1(ready()), selected = ""),
                      ignoreNULL = TRUE)
  output$history_overview_classes <- overview("classes")
  output$history_overview_assets <- overview("assets")
  output$history_overview_groups <- overview("groups")
  output$history_overview_groups_block <- shiny::renderUI({
    history <- ready(); if (is.null(history) || !length(history$groups)) return(NULL)
    shiny::tagList(shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Je eigener Gruppe"),
                   shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("history_overview_groups")))
  })
  output$history_asset_title <- shiny::renderUI({
    title <- analysis_assets_title_v1(selection())
    if (is.null(title)) NULL else shiny::h4(class = "pl-section-title", style = "margin:10px 0 0", title)
  })
  output$history_asset_account_state <- shiny::renderUI({
    picked <- selection(); if (is.null(picked) || is.null(picked$account)) return(NULL)
    wallet <- picked$fifo_wallet
    if (identical(wallet$role, "wallet")) return(shiny::p(class = "pl-field-hint", paste0("Sicht je FIFO-Wallet: ",
      paste(unlist(wallet$accounts), collapse = ", "), " rechnen als eine Wallet. Einstand, GuV und Netto gelten für alle Lose der Wallet; ",
      "eine Umbuchung zwischen ihren Konten ist hier weder Zu- noch Abgang.")))
    if (identical(wallet$role, "member")) return(shiny::p(class = "pl-field-hint", paste0("Sicht je Konto: ", picked$account,
      ". Das Konto gehört zur ", wallet$wallet_label, ": Menge, Wert, Buchungen und realisierte GuV stehen je Konto; Einstand, ",
      "unrealisierte GuV und Netto ", ANALYSIS_ASSETS_IN_WALLET_V1, ", weil die Lose der Wallet gehören. Die Wallet steht in der Kontoauswahl.")))
    shiny::p(class = "pl-field-hint", paste0("Sicht je Konto: ", picked$account, ". Ein Transfer zwischen eigenen Konten verlässt das eine Konto und kommt im anderen ",
      "zum Tageswert an; die Anschaffungskosten der übertragenen Lose wandern mit. Netto rechnet mit den Losen dieses Kontos;",
      "die Steuer eines gedachten Verkaufs gilt hier für dieses Konto allein."))
  })
  output$history_asset_group_state <- shiny::renderUI({
    picked <- selection(); if (is.null(picked) || !identical(picked$kind, "group")) return(NULL)
    group <- picked$group
    members <- unlist(group$member_labels)
    shiny::p(class = "pl-field-hint", paste0(length(members), " Assets: ", paste(utils::head(members, 12L), collapse = ", "),
      if (length(members) > 12L) sprintf(" und %d weitere", length(members) - 12L) else "", ".",
      if (length(group$new_labels)) paste0(" Seit dem Speichern neu und nicht enthalten: ", paste(unlist(group$new_labels), collapse = ", "),
                                           " – die Gruppe lässt sich in der App „Daten“ aktualisieren.") else "",
      if (!is.null(group$partition)) paste0(" Teil der Aufteilung „", group$partition, "“.") else ""))
  })
  invisible(list(selection = selection, frame = frame, clicked = clicked, now = now, drawdown = drawdown))
}
