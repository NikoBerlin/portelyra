# Punkt „jetzt“ in allen Diagrammen der Analyse (#512, Festlegung 25.10.2026: eine Sicht, die moeglichst aktuell zeigt, wie es
# gerade steht). Die juengste veroeffentlichte Momentaufnahme traegt je Asset den zuletzt abgerufenen Kurs. Jedes Bild bekommt
# daraus einen hohlen Punkt rechts vom letzten Tag: der Bestand des letzten Tages zu diesen Kursen. Menge, Einstand und Cash
# bleiben, wie sie am letzten Tag waren - so schliesst der Punkt an die Linien an. Eine Buchung seit dem letzten Tag zaehlt erst
# mit dem naechsten Tagesschluss und wird genannt; fehlt einem Asset ein frisch abgerufener Kurs, gilt sein letzter Tagesschluss,
# und auch das wird genannt. Nur Anzeige: Hier wird Menge mal Kurs gerechnet, sonst nichts.
#
# Den Punkt gibt es nur, wenn das Bild bis zum letzten Tag der Historie reicht und die Momentaufnahme juenger ist. Die
# Zuordnung je Asset braucht Schluessel und letzte Menge in der Tageshistorie (seit rc.317); die Tageshistorie traegt keine
# Kennungen, nur den daraus gebildeten Schluessel (asset_key_v1 in der Veroeffentlichung). Aeltere Staende zeigen bis zur
# naechsten Veroeffentlichung nur den Punkt im Portfolio-Verlauf, gerechnet aus den Summen der Momentaufnahme (wie rc.314).

# Zwei Zeilen (Festlegung 06.11.2026): In der waagerechten Legende des Verlaufs fiel "kein Tagesschluss" sonst rechts heraus.
ANALYSIS_MOMENT_LEGEND_V1 <- "jetzt (Momentaufnahme,\nkein Tagesschluss)"
# Klasse der Zusammensetzung je Assetart - dieselbe Tabelle wie COMPOSITION_CLASS_OF in der Veroeffentlichung.
ANALYSIS_MOMENT_CLASS_OF_V1 <- c(cash = "cash", fund = "fund", etf = "fund", equity = "equity", crypto = "crypto", fx = "fx", derivative = "derivative")

# Der Schluessel eines Assets wie in der Tageshistorie: aus der Kennung der Momentaufnahme gebildet, nicht umkehrbar.
analysis_moment_key_v1 <- function(asset_id) {
  paste0("akey_", substr(digest::digest(enc2utf8(paste0("portfolio_history_asset|", asset_id)), algo = "sha256", serialize = FALSE), 1L, 24L))
}

analysis_moment_class_of_v1 <- function(asset_type) {
  hit <- unname(ANALYSIS_MOMENT_CLASS_OF_V1[as.character(asset_type)])
  ifelse(is.na(hit), "other", hit)
}

# Das Modell der Momentaufnahme fuer die Bilder: je Asset der Tageshistorie Wert am letzten Tag ('before') und derselbe Bestand
# zum abgerufenen Kurs ('now'). NULL ohne Momentaufnahme oder wenn sie nicht juenger ist als der letzte Tag.
analysis_moment_model_v1 <- function(moment, history) {
  if (!is.list(moment) || !identical(moment$status, "available") || !is.list(history) || is.null(history$last_day)) return(NULL)
  day <- tryCatch(as.Date(moment$as_of_date), error = function(error) NA)
  last <- tryCatch(as.Date(history$last_day), error = function(error) NA)
  if (length(day) != 1L || is.na(day) || length(last) != 1L || is.na(last) || day <= last) return(NULL)
  number <- function(value) analysis_history_number_v1(list(value))
  totals <- if (is.list(moment$totals)) moment$totals else list()
  model <- list(day = day, last_day = last, at = .analysis_history_text_v1(moment$completed_at_utc, ""),
                totals = list(net_worth = number(totals$net_worth_decimal), market_value = number(totals$market_value_decimal),
                              unrealised = number(totals$unrealised_decimal), cash = number(totals$cash_balance_decimal)),
                per_asset = FALSE, assets = NULL, moved = character(), new_count = 0L)
  units <- numeric(); bases <- character(); held <- numeric()
  for (row in moment$positions) if (is.character(row$asset_id) && length(row$asset_id) == 1L) {
    key <- analysis_moment_key_v1(row$asset_id)
    units[[key]] <- number(row$unit_value_decimal)
    bases[[key]] <- if (is.character(row$price_basis) && length(row$price_basis) == 1L) row$price_basis else ""
  }
  for (row in c(moment$positions, moment$excluded_positions)) if (is.character(row$asset_id) && length(row$asset_id) == 1L)
    held[[analysis_moment_key_v1(row$asset_id)]] <- number(row$quantity_decimal)
  assets <- history$assets
  model$per_asset <- length(assets) > 0L && all(vapply(assets, function(asset)
    is.character(asset$asset_key) && length(asset$asset_key) == 1L && "last_quantity" %in% names(asset), logical(1L)))
  if (!model$per_asset) return(model)
  pick <- function(values, key, missing) { value <- unname(values[key]); if (length(value) != 1L || is.na(value)) missing else value }
  rows <- lapply(assets, function(asset) {
    quantity <- number(asset$last_quantity); before <- number(asset$last_value)
    unit <- pick(units, asset$asset_key, NA_real_); basis <- pick(bases, asset$asset_key, "")
    quoted <- !is.na(before) && !is.na(quantity) && !is.na(unit) && identical(basis, "intraday")
    # Ohne frisch abgerufenen Kurs gilt der letzte Tagesschluss: Der Wert bleibt der des letzten Tages.
    now <- if (!is.na(before) && !is.na(quantity) && !is.na(unit)) quantity * unit else before
    now_quantity <- pick(held, asset$asset_key, 0); last_quantity <- if (is.na(quantity)) 0 else quantity
    data.frame(ordinal = as.integer(asset$ordinal), label = asset$label, class = analysis_moment_class_of_v1(asset$asset_type),
               quantity = quantity, before = before, now = now, unit = if (!is.na(before) && is.na(unit) && !is.na(quantity) && quantity != 0) before / quantity else unit,
               quoted = quoted, fallback = !is.na(before) && before != 0 && !quoted,
               moved = abs(now_quantity - last_quantity) > 1e-9 * max(1, abs(last_quantity)), stringsAsFactors = FALSE)
  })
  model$assets <- do.call(rbind, rows)
  model$moved <- model$assets$label[model$assets$moved]
  ids <- vapply(assets, function(asset) asset$asset_key, character(1L))
  model$new_count <- length(setdiff(names(held)[!is.na(held) & held != 0], ids))
  model
}

# Ob ein Bild bis zum letzten Tag der Historie reicht - nur dann steht der Punkt daneben.
analysis_moment_reaches_v1 <- function(model, days) {
  !is.null(model) && length(days) > 0L && identical(as.character(max(days)), as.character(model$last_day))
}

# Die Zeilen der gewaehlten Assets (alle, wenn 'ordinals' NULL), soweit sie am letzten Tag einen Wert hatten.
.analysis_moment_rows_v1 <- function(model, ordinals = NULL) {
  rows <- model$assets
  if (is.null(rows)) return(NULL)
  if (!is.null(ordinals)) rows <- rows[rows$ordinal %in% ordinals, , drop = FALSE]
  rows[!is.na(rows$before), , drop = FALSE]
}

# Kursaenderung seit dem letzten Tag in Euro; NA ohne Zuordnung je Asset.
analysis_moment_delta_v1 <- function(model, ordinals = NULL) {
  rows <- .analysis_moment_rows_v1(model, ordinals)
  if (is.null(rows)) NA_real_ else sum(rows$now - rows$before)
}

# Rendite seit dem letzten Tag: Kursaenderung durch 'base' (Vorgabe: der Wert der Assets am letzten Tag).
analysis_moment_return_v1 <- function(model, ordinals = NULL, base = NULL) {
  rows <- .analysis_moment_rows_v1(model, ordinals)
  if (is.null(rows) || !nrow(rows)) return(NA_real_)
  if (is.null(base)) base <- sum(rows$before)
  if (!is.finite(base) || base <= 0) NA_real_ else sum(rows$now - rows$before) / base
}

# Die Assets einer Klasse, einer eigenen Gruppe (ueber ihre Bezeichnungen) oder ein einzelnes Asset.
analysis_moment_members_v1 <- function(model, history, key) {
  rows <- model$assets
  if (is.null(rows) || !is.character(key) || length(key) != 1L) return(integer())
  kind <- sub(":.*$", "", key); id <- sub("^[a-z_]+:", "", key)
  if (identical(kind, "class")) return(rows$ordinal[rows$class == id])
  if (identical(kind, "asset")) return(rows$ordinal[as.character(rows$ordinal) == id])
  if (identical(kind, "group")) {
    hit <- Filter(function(group) identical(as.character(group$ordinal), id), history$groups)
    if (length(hit) != 1L) return(integer())
    return(rows$ordinal[rows$label %in% unlist(hit[[1L]]$member_labels)])
  }
  rows$ordinal
}

# Was am Punkt zu wissen ist: Kurse vom letzten Tagesschluss, Buchungen seit dem letzten Tag.
analysis_moment_caveats_v1 <- function(model, ordinals = NULL) {
  if (is.null(model)) return(character())
  if (!isTRUE(model$per_asset))
    return("Die Tageshistorie trägt noch keine Zuordnung je Asset: Bis zu ihrer nächsten Veröffentlichung („Alles aktualisieren“) steht der Punkt nur im Portfolio-Verlauf und zeigt die Summen der Momentaufnahme.")
  rows <- .analysis_moment_rows_v1(model, ordinals)
  parts <- character()
  fallback <- if (is.null(rows)) 0L else sum(rows$fallback)
  if (fallback) parts <- c(parts, sprintf("%d %s ohne frisch abgerufenen Kurs: dort gilt der letzte Tagesschluss.", fallback, if (fallback == 1L) "Asset" else "Assets"))
  moved <- if (is.null(ordinals)) model$moved else model$assets$label[model$assets$moved & model$assets$ordinal %in% ordinals]
  added <- if (is.null(ordinals)) model$new_count else 0L
  if (length(moved) || added) parts <- c(parts, paste0("Seit dem letzten Tag gebucht",
    if (length(moved)) paste0(": ", paste(utils::head(moved, 5L), collapse = ", "), if (length(moved) > 5L) sprintf(" und %d weitere", length(moved) - 5L)) else "",
    if (added) sprintf("%s%d %s", if (length(moved)) "; dazu " else ": ", added, if (added == 1L) "neues Asset" else "neue Assets") else "",
    " – der Punkt rechnet mit dem Bestand des letzten Tages; die Buchungen zählen ab dem nächsten Tagesschluss."))
  parts
}

# Hinweis unter einem Bild mit Punkt; 'values' ergaenzt, was der Punkt zeigt.
analysis_moment_note_v1 <- function(model, values = NULL, ordinals = NULL) {
  if (is.null(model)) return(NULL)
  shiny::p(class = "pl-field-hint", paste(c(
    paste0("Hohler Punkt rechts: jetzt, Momentaufnahme vom ", analysis_history_moment_time_v1(model), " – ",
           if (isTRUE(model$per_asset)) "der Bestand des letzten Tages zu den zuletzt abgerufenen Kursen; " else "",
           "tagesfrisch, aber kein Tagesschluss. Die Linien enden am letzten Tagesschluss."),
    values, analysis_moment_caveats_v1(model, ordinals)), collapse = " "))
}

# Liegt der Zeiger naeher am Punkt als am letzten Tag?
analysis_moment_hovered_v1 <- function(now, days, x) {
  !is.null(now) && !is.null(x) && length(days) > 0L && x > as.numeric(max(days)) + as.numeric(now$day - max(days)) / 2
}

# Die Kopfzeile des Zeigers am Punkt.
analysis_moment_title_v1 <- function(model) paste0("jetzt · Momentaufnahme ", analysis_history_moment_time_v1(model), " (kein Tagesschluss)")

# Der hohle Punkt, mit gepunkteter Verbindung zum letzten Tag.
.analysis_moment_mark_v1 <- function(from_day, from_value, day, value, color, cex = 1.5) {
  if (is.null(value) || is.na(value)) return(invisible(FALSE))
  if (!is.na(from_value)) graphics::segments(from_day, from_value, day, value, col = color, lwd = 1.5, lty = 3)
  graphics::points(day, value, pch = 21, cex = cex, lwd = 2, col = color, bg = ANALYSIS_HISTORY_INK_V1[["surface"]])
  invisible(TRUE)
}

# Der Legendeneintrag des Punkts unter einem Bild ohne eigene Legende: am oberen Rand rechts.
.analysis_moment_legend_v1 <- function() {
  usr <- graphics::par("usr")
  graphics::legend(usr[[2L]], usr[[4L]] + diff(usr[3:4]) * 0.02, legend = ANALYSIS_MOMENT_LEGEND_V1, pch = 21, pt.bg = ANALYSIS_HISTORY_INK_V1[["surface"]],
                   col = ANALYSIS_HISTORY_INK_V1[["secondary"]], pt.cex = 1.2, pt.lwd = 2, bty = "n", cex = 0.75, xjust = 1, yjust = 0,
                   text.col = ANALYSIS_HISTORY_INK_V1[["secondary"]], xpd = NA)
}

# --- je Bild -------------------------------------------------------------------------------------------------------------------

# Portfolio-Verlauf: Gesamtvermoegen, Marktwert und unrealisierte GuV des letzten Tages plus der Kursaenderung seither.
analysis_history_moment_point_v1 <- function(model, frame) {
  if (is.null(frame) || !nrow(frame) || !analysis_moment_reaches_v1(model, frame$day)) return(NULL)
  base <- list(day = model$day, at = model$at)
  if (!isTRUE(model$per_asset)) {
    totals <- model$totals
    point <- c(base, list(net_worth = totals$net_worth, market_value = totals$market_value, unrealised = totals$unrealised,
                          cash = totals$cash, delta = NA_real_, from_totals = TRUE))
    return(if (is.na(point$net_worth) && is.na(point$market_value)) NULL else point)
  }
  last <- nrow(frame); delta <- analysis_moment_delta_v1(model)
  c(base, list(net_worth = frame$net_worth[[last]] + delta, market_value = frame$market_value[[last]] + delta,
               unrealised = frame$unrealised[[last]] + delta, cash = frame$cash[[last]], delta = delta, from_totals = FALSE))
}

# Zusammensetzung: je Schicht der Wert des letzten Tages plus die Kursaenderung ihrer Assets. 'members' ordnet bei einer eigenen
# Aufteilung jeder Schicht ihre Assets zu; ohne sie gilt die Klasse.
analysis_moment_composition_v1 <- function(model, frame, members = NULL) {
  if (!isTRUE(model$per_asset) || is.null(frame) || !nrow(frame) || !analysis_moment_reaches_v1(model, frame$day)) return(NULL)
  layers <- attr(frame, "classes")
  before <- analysis_history_composition_matrix_v1(frame)[nrow(frame), layers]
  now <- vapply(seq_along(layers), function(index) {
    key <- layers[[index]]
    ordinals <- if (is.null(members)) model$assets$ordinal[model$assets$class == key] else members[[key]]
    if (!length(ordinals)) before[[index]] else before[[index]] + analysis_moment_delta_v1(model, ordinals)
  }, numeric(1L))
  list(day = model$day, at = model$at, values = stats::setNames(pmax(now, 0), layers), before = stats::setNames(before, layers))
}

# Die Assets je Schicht einer eigenen Aufteilung: je Gruppe ihre Mitglieder, „keiner Gruppe zugeordnet“ der Rest.
analysis_moment_partition_members_v1 <- function(model, history, frame) {
  if (is.null(model$assets)) return(NULL)
  layers <- attr(frame, "classes"); meta <- attr(frame, "meta")
  members <- list(); grouped <- integer()
  for (key in layers[startsWith(layers, "g")]) {
    hit <- Filter(function(group) identical(paste0("g", group$ordinal), key), history$groups)
    ordinals <- if (length(hit) == 1L) model$assets$ordinal[model$assets$label %in% unlist(hit[[1L]]$member_labels)] else integer()
    members[[key]] <- ordinals; grouped <- c(grouped, ordinals)
  }
  for (key in intersect(c("cash", "transit"), layers)) members[[key]] <- integer()
  if ("unassigned" %in% layers) members$unassigned <- setdiff(model$assets$ordinal, grouped)
  members
}

# Rendite der Anlage: die TWR des letzten Tages, fortgeschrieben um die Kursaenderung seither (ohne Fluesse seit dem letzten Tag).
analysis_moment_returns_v1 <- function(model, frame) {
  if (!isTRUE(model$per_asset) || is.null(frame) || !nrow(frame) || !analysis_moment_reaches_v1(model, frame$day)) return(NULL)
  last <- nrow(frame)
  rate <- analysis_moment_return_v1(model, NULL, frame$value[[last]])
  if (is.na(rate) || is.na(frame$twr[[last]])) return(NULL)
  list(day = model$day, at = model$at, rate = rate, delta = analysis_moment_delta_v1(model), value = frame$value[[last]] * (1 + rate),
       twr = (1 + frame$twr[[last]]) * (1 + rate) - 1)
}

# Kennzahlen je Intervall: ein schmaler Balken „seit dem letzten Tagesschluss“.
analysis_moment_interval_v1 <- function(model, history, frame) {
  if (!isTRUE(model$per_asset) || is.null(frame) || !nrow(frame) || max(frame$end) != model$last_day) return(NULL)
  value <- analysis_history_number_v1(history$investment$value); value <- value[[length(value)]]
  rate <- analysis_moment_return_v1(model, NULL, value)
  if (is.na(rate)) return(NULL)
  list(day = model$day, at = model$at, gain = analysis_moment_delta_v1(model), twr = rate, mwr = rate)
}

# Vergleich: je eigener Linie ihr letzter Wert, fortgeschrieben um die Rendite ihrer Assets seit dem letzten Tag. Indizes haben
# keine Momentaufnahme und bleiben ohne Punkt.
analysis_moment_compare_v1 <- function(model, history, frame) {
  lines <- attr(frame, "lines")
  if (!isTRUE(model$per_asset) || is.null(frame) || !nrow(frame) || !analysis_moment_reaches_v1(model, frame$day)) return(NULL)
  last <- nrow(frame); values <- numeric(); rates <- numeric()
  investment <- analysis_history_number_v1(history$investment$value)
  for (line in lines) {
    if (identical(line$kind, "index")) next
    level <- frame[[line$key]][[last]]
    if (is.null(level) || is.na(level)) next
    rate <- if (identical(line$key, "investment")) analysis_moment_return_v1(model, NULL, investment[[length(investment)]])
      else if (identical(line$key, "assets_only")) analysis_moment_return_v1(model)
      else analysis_moment_return_v1(model, analysis_moment_members_v1(model, history, line$key))
    if (is.na(rate)) next
    values[[line$key]] <- level * (1 + rate); rates[[line$key]] <- rate
  }
  if (!length(values)) return(NULL)
  list(day = model$day, at = model$at, values = values, rates = rates)
}

# Abstand vom Hoch: der letzte Abstand, fortgeschrieben um dieselbe Rendite; ueber dem Hoch ist er null.
analysis_moment_drawdown_v1 <- function(drawdown_last, rate) {
  if (is.na(drawdown_last) || is.na(rate)) return(NA_real_)
  min(0, (1 + drawdown_last) * (1 + rate) - 1)
}

# Ein Asset oder eine Klasse/Gruppe im Reiter "Assets und Gruppen": Wert, Einstand, GuV, Kurs und Menge des Punkts.
analysis_moment_selection_v1 <- function(model, history, selection, frame) {
  if (!isTRUE(model$per_asset) || is.null(selection) || is.null(frame) || !nrow(frame) || !analysis_moment_reaches_v1(model, frame$day)) return(NULL)
  last <- nrow(frame)
  if (identical(selection$kind, "asset")) {
    row <- model$assets[model$assets$ordinal == as.integer(selection$asset$ordinal), , drop = FALSE]
    if (nrow(row) != 1L || is.na(row$unit) || isTRUE(frame$gap[[last]])) return(NULL)
    quantity <- frame$quantity[[last]]; value <- quantity * row$unit
    before_unit <- frame$unit_value[[last]]
    return(list(day = model$day, at = model$at, kind = "asset", unit = row$unit, value = value, quantity = quantity,
                cost_basis = frame$cost_basis[[last]], unrealised = value - frame$cost_basis[[last]], cost_average = frame$cost_average[[last]],
                rate = if (is.na(before_unit) || before_unit <= 0) NA_real_ else row$unit / before_unit - 1,
                fallback = isTRUE(row$fallback), moved = isTRUE(row$moved), ordinals = row$ordinal))
  }
  key <- if (identical(selection$kind, "class")) paste0("class:", selection$key) else paste0("group:", selection$group$ordinal)
  ordinals <- analysis_moment_members_v1(model, history, key)
  delta <- analysis_moment_delta_v1(model, ordinals)
  if (is.na(delta) || is.na(frame$market_value[[last]])) return(NULL)
  list(day = model$day, at = model$at, kind = selection$kind, value = frame$market_value[[last]] + delta, cost_basis = frame$cost_basis[[last]],
       unrealised = frame$unrealised[[last]] + delta, rate = analysis_moment_return_v1(model, ordinals), ordinals = ordinals)
}

# Zeilen des Zeigers am Punkt im Reiter "Assets und Gruppen".
analysis_moment_selection_rows_v1 <- function(now, model) {
  rows <- list(list(label = "Wert", value = analysis_history_eur_v1(now$value, 2L), color = ANALYSIS_ASSETS_LINE_V1),
               list(label = "Einstand (letzter Tag)", value = analysis_history_eur_v1(now$cost_basis, 2L)),
               list(label = "unrealisiert", value = analysis_history_eur_signed_v1(now$unrealised, 2L)),
               list(label = "seit dem letzten Tagesschluss", value = analysis_history_pct_v1(now$rate, 2L)))
  if (identical(now$kind, "asset")) rows <- c(rows, list(
    list(label = "Kurs (zuletzt abgerufen)", value = paste0(analysis_history_eur_v1(now$unit, 2L), if (isTRUE(now$fallback)) " – letzter Tagesschluss" else "")),
    list(label = "Menge (letzter Tag)", value = .analysis_history_quantity_v1(now$quantity))))
  notes <- analysis_moment_caveats_v1(model, now$ordinals)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = analysis_moment_title_v1(model), rows = rows)
}

# Projektion: der zuletzt abgerufene Kurs eines Assets - NULL ohne Momentaufnahme oder ohne Kurs fuer dieses Asset.
analysis_moment_price_v1 <- function(model, asset) {
  if (!isTRUE(model$per_asset) || is.null(asset)) return(NULL)
  row <- model$assets[model$assets$ordinal == as.integer(asset$ordinal), , drop = FALSE]
  if (nrow(row) != 1L || is.na(row$unit)) return(NULL)
  list(price = row$unit, quoted = isTRUE(row$quoted), at = model$at, day = model$day, time = analysis_history_moment_time_v1(model))
}
