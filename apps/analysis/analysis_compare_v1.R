# Reiter "Vergleich" der Analyse (#482, #502): Anlage, Klassen, eigene Gruppen, Assets und Vergleichsindizes als Linien ueber
# denselben Zeitraum, alle auf 100 zu ihrem ersten Wert im Zeitraum. Eigene Positionen laufen zeitgewichtet (TWR, vor Steuern,
# mit Dividenden und Rewards); ein Vergleichsindex ist eine gedachte Anlage ohne Gebuehren und Steuern, taeglich fest gewichtet
# und mit Ausschuettungen, wo die Kursquelle sie bereinigt. Darunter je Linie Rendite, p. a. und der Abstand zum gewaehlten
# Bezugsindex ueber dieselbe Spanne. Fair je Asset (gleiche Tage mit Bestand) ist die Rangliste im Reiter "Assets und Gruppen".
# Luecken bleiben leer, nie 0. Die Tagesreihen von Klassen, Gruppen und Assets kommen aus den Teildateien (#503). Nur Anzeige.

# Feste Folge der Farben (Leitfaden fuer Diagramme, Kategorien 1-7; Rot bleibt dem Verlust vorbehalten). Die Farbe folgt dem
# Eintrag, nicht seinem Platz: Wer eine Linie abwaehlt, faerbt die uebrigen nicht um.
ANALYSIS_COMPARE_PALETTE_V1 <- c("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")
ANALYSIS_COMPARE_LIMIT_V1 <- length(ANALYSIS_COMPARE_PALETTE_V1)

.analysis_compare_points_v1 <- function(value) analysis_history_points_v1(value)

# Die Linien zur Wahl, gegliedert: Anlage, Vergleichsindizes, Klassen, eigene Gruppen, Assets.
analysis_compare_choices_v1 <- function(history) {
  if (is.null(history)) return(list())
  # Ohne Eintraege kein Abschnitt (paste0 mit leerer Liste ergaebe sonst einen Schluessel ohne Nummer).
  named <- function(rows, prefix, key, label) if (!length(rows)) NULL else
    stats::setNames(paste0(prefix, vapply(rows, function(row) as.character(row[[key]]), character(1L))), vapply(rows, label, character(1L)))
  classes <- Filter(function(row) !is.null(ANALYSIS_HISTORY_CLASSES_V1[[row$class]]), history$classes)
  Filter(length, list(
    Anlage = c("Anlage (mit Cash)" = "investment", "Alle Assets ohne Cash" = "assets_only"),
    Vergleichsindizes = named(history$benchmarks, "index:", "ordinal", function(row) row$label),
    Klassen = named(classes, "class:", "class", function(row) ANALYSIS_HISTORY_CLASSES_V1[[row$class]]$label),
    `Eigene Gruppen` = named(history$groups, "group:", "ordinal", function(row) row$label),
    Assets = named(history$assets, "asset:", "ordinal", function(row) row$label)))
}

# Vorauswahl: die Anlage und der erste Vergleichsindex. Ohne Cash im Umfang (#542) statt der Anlage mit Cash alle Assets ohne Cash.
analysis_compare_default_lines_v1 <- function(history, cash = !analysis_scope_off_v1("cash")) {
  c(if (isFALSE(cash)) "assets_only" else "investment", if (length(history$benchmarks)) "index:1" else NULL)
}

# Farben je Eintrag: Bleibt ein Eintrag gewaehlt, behaelt er seine Farbe; ein neuer bekommt die erste freie.
analysis_compare_assign_colors_v1 <- function(previous, selected, palette = ANALYSIS_COMPARE_PALETTE_V1) {
  kept <- previous[intersect(names(previous), selected)]
  for (key in setdiff(selected, names(kept))) {
    free <- setdiff(palette, kept)
    kept[[key]] <- if (length(free)) free[[1L]] else palette[[(length(kept) %% length(palette)) + 1L]]
  }
  kept[selected]
}

# Ein Eintrag als Reihe auf dem Tagesraster: Niveau je Tag (NA ohne Wert) und ob er an dem Tag gehalten wurde. 'hydrate' holt
# die Teildatei einer Klasse, Gruppe oder eines Assets.
analysis_compare_series_v1 <- function(history, key, hydrate = function(entry) entry) {
  days <- unlist(history$portfolio$day); size <- length(days)
  window <- function(twr) {
    values <- rep(NA_real_, size)
    if (is.null(twr) || is.null(twr$first_day)) return(values)
    start <- match(twr$first_day, days); index <- analysis_history_number_v1(twr$index)
    if (is.na(start) || !length(index)) return(values)
    stop <- min(size, start + length(index) - 1L); values[start:stop] <- index[seq_len(stop - start + 1L)]
    values
  }
  kind <- sub(":.*$", "", key); id <- sub("^[a-z_]+:", "", key)
  if (identical(key, "investment"))
    return(list(key = key, label = "Anlage (mit Cash)", kind = "own", values = analysis_history_number_v1(history$investment$twr_index), held = rep(TRUE, size)))
  if (identical(key, "assets_only")) {
    values <- analysis_history_number_v1(history$investment$assets_only$twr_index)
    if (!length(values)) values <- rep(NA_real_, size)
    return(list(key = key, label = "Alle Assets ohne Cash", kind = "own", values = values, held = rep(TRUE, size)))
  }
  if (identical(kind, "index")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), id), history$benchmarks); if (length(hit) != 1L) return(NULL)
    return(list(key = key, label = hit[[1L]]$label, kind = "index", values = analysis_history_number_v1(hit[[1L]]$levels), held = rep(TRUE, size),
                index = hit[[1L]]))
  }
  if (identical(kind, "class")) {
    hit <- Filter(function(row) identical(row$class, id), history$classes); if (length(hit) != 1L) return(NULL)
    entry <- hydrate(hit[[1L]]); share <- history$portfolio$composition$values[[id]]
    held <- if (is.null(share)) rep(TRUE, size) else { value <- analysis_history_number_v1(share); !is.na(value) & value > 0 }
    return(list(key = key, label = ANALYSIS_HISTORY_CLASSES_V1[[id]]$label, kind = "own", values = window(entry$twr), held = held))
  }
  if (identical(kind, "group")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), id), history$groups); if (length(hit) != 1L) return(NULL)
    entry <- hydrate(hit[[1L]]); value <- analysis_history_number_v1(entry$value)
    held <- if (length(value) == size) !is.na(value) & value > 0 else rep(TRUE, size)
    return(list(key = key, label = entry$label, kind = "own", values = window(entry$twr), held = held))
  }
  if (identical(kind, "asset")) {
    hit <- Filter(function(row) identical(as.character(row$ordinal), id), history$assets); if (length(hit) != 1L) return(NULL)
    entry <- hydrate(hit[[1L]])
    held_days <- unlist(entry$days$day)[!is.na(analysis_history_number_v1(entry$days$market_value)) & analysis_history_number_v1(entry$days$market_value) > 0]
    held <- if (is.null(entry$days)) rep(TRUE, size) else days %in% held_days
    return(list(key = key, label = entry$label, kind = "own", values = window(entry$twr), held = held))
  }
  NULL
}

# Die gewaehlten Linien im Zeitraum, je Linie auf 100 zu ihrem ersten Wert im Zeitraum. Eigene Positionen: an Tagen ohne
# Bestand bleibt die Linie leer (der Index des Eintrags steht dort still). Ergebnis: Tage und je Linie die Werte.
analysis_compare_frame_v1 <- function(history, keys, period = "all", range = NULL, hydrate = function(entry) entry) {
  days <- as.Date(unlist(history$portfolio$day))
  keep <- analysis_history_window_v1(days, period, range)
  lines <- Filter(Negate(is.null), lapply(keys, function(key) analysis_compare_series_v1(history, key, hydrate)))
  frame <- data.frame(day = days[keep], stringsAsFactors = FALSE)
  for (line in lines) {
    values <- line$values[keep]; held <- line$held[keep]
    first <- which(!is.na(values) & held)[1L]
    rebased <- if (is.na(first) || values[[first]] <= 0) rep(NA_real_, length(values)) else values / values[[first]] * 100
    if (!is.na(first) && first > 1L) rebased[seq_len(first - 1L)] <- NA_real_
    rebased[!held] <- NA_real_
    frame[[line$key]] <- rebased
  }
  attr(frame, "lines") <- lines
  frame
}

# Je Linie im Zeitraum: erster und letzter Tag mit Wert, Rendite, p. a. ab 365 Tagen und der Abstand zum Bezugsindex ueber die
# gemeinsame Spanne - vom spaeteren der beiden Anfaenge bis zum frueheren der beiden Enden. Beginnt der Bezugsindex spaeter als die
# Linie, steht am Abstand ein ¹: Er gilt dann erst ab dem ersten Tag des Index.
analysis_compare_lines_table_v1 <- function(frame, reference = NULL) {
  lines <- attr(frame, "lines")
  if (!length(lines) || !nrow(frame)) return(data.frame())
  ref <- if (!is.null(reference) && reference %in% names(frame)) frame[[reference]] else NULL
  ref_known <- if (is.null(ref)) integer() else which(!is.na(ref))
  carried <- function(position) { hit <- ref_known[ref_known <= position]; if (length(hit)) ref[[max(hit)]] else NA_real_ }
  rows <- lapply(lines, function(line) {
    values <- frame[[line$key]]; known <- which(!is.na(values))
    kind <- if (identical(line$kind, "index")) "Vergleichsindex" else "eigene Position"
    if (!length(known)) return(data.frame(Linie = line$label, Art = kind, Von = "–", Bis = "–", Rendite = "–", `p. a.` = "–",
      `Abstand zum Bezugsindex` = "–", check.names = FALSE, stringsAsFactors = FALSE))
    first <- known[[1L]]; last <- known[[length(known)]]
    result <- values[[last]] / values[[first]] - 1
    span <- as.numeric(frame$day[[last]] - frame$day[[first]])
    yearly <- if (span >= 365 && result > -1) (1 + result)^(365 / span) - 1 else NA_real_
    gap <- NA_real_; later <- FALSE
    if (length(ref_known) && !identical(line$key, reference)) {
      inside <- known[known >= ref_known[[1L]] & known <= max(ref_known)]
      if (length(inside) >= 2L) {
        start <- inside[[1L]]; end <- inside[[length(inside)]]; later <- start > first
        base <- carried(start); top <- carried(end)
        if (!is.na(base) && !is.na(top) && base > 0) gap <- (values[[end]] / values[[start]] - 1) - (top / base - 1)
      }
    }
    data.frame(Linie = line$label, Art = kind, Von = format(frame$day[[first]], "%d.%m.%Y"), Bis = format(frame$day[[last]], "%d.%m.%Y"),
               Rendite = analysis_history_pct_v1(result), `p. a.` = analysis_history_pct_v1(yearly),
               `Abstand zum Bezugsindex` = if (identical(line$key, reference)) "Bezug" else paste0(analysis_history_points_v1(gap), if (later && !is.na(gap)) " ¹" else ""),
               check.names = FALSE, stringsAsFactors = FALSE)
  })
  do.call(rbind, rows)
}

# Name am Linienende: kurz genug fuer den Rand; der volle Name steht in der Tabelle darunter.
.analysis_compare_short_v1 <- function(label, width = 26L) ifelse(nchar(label) > width, paste0(substr(label, 1L, width - 1L), "…"), label)

# 'log': logarithmische Skala - gleiche Abstaende sind gleiche prozentuale Aenderungen; noetig, sobald eine Linie (etwa Krypto) die
# anderen flach drueckt.
analysis_compare_plot_v1 <- function(frame, colors, log = FALSE, now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1; lines <- attr(frame, "lines")
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.6, 12), mgp = c(3, 0.6, 0), tcl = -0.2)
  values <- unlist(lapply(lines, function(line) frame[[line$key]]))
  points <- if (is.null(now)) numeric() else now$values[intersect(names(now$values), vapply(lines, function(line) line$key, character(1L)))]
  span <- range(c(100, values, points), na.rm = TRUE)
  xlim <- range(c(frame$day, if (length(points)) now$day))
  if (isTRUE(log)) {
    span <- span * c(0.95, 1.05)
    graphics::plot(frame$day, rep(100, nrow(frame)), type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "", log = "y")
    at <- grDevices::axisTicks(log10(span), log = TRUE, nint = 6L)
  } else {
    span <- span + c(-1, 1) * max(diff(span), 1) * 0.05
    graphics::plot(frame$day, rep(100, nrow(frame)), type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
    at <- pretty(span, n = 5L)
  }
  graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = formatC(at, format = "fg", decimal.mark = ","), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::abline(h = 100, col = ink[["baseline"]], lwd = 1)
  # Vergleichsindizes gestrichelt, eigene Positionen durchgezogen - so traegt nicht allein die Farbe die Art.
  for (line in lines) .analysis_history_line_v1(frame$day, frame[[line$key]], colors[[line$key]], rep(identical(line$kind, "index"), nrow(frame)))
  for (key in names(points)) .analysis_moment_mark_v1(frame$day[[nrow(frame)]], frame[[key]][[nrow(frame)]], now$day, points[[key]], colors[[key]])
  ends <- vapply(lines, function(line) {
    if (line$key %in% names(points)) return(points[[line$key]])
    known <- which(!is.na(frame[[line$key]])); if (length(known)) frame[[line$key]][[max(known)]] else NA_real_ }, numeric(1L))
  labels <- vapply(seq_along(lines), function(position) paste(.analysis_compare_short_v1(lines[[position]]$label), analysis_history_pct_v1(ends[[position]] / 100 - 1)), character(1L))
  .analysis_history_end_labels_v1(xlim[[2L]], ends, labels, vapply(lines, function(line) colors[[line$key]], character(1L)))
  .analysis_history_axis_dates_v1(frame$day)
  graphics::mtext(paste0("Erster Wert im Zeitraum = 100", if (isTRUE(log)) " (logarithmisch)" else "",
                         " · eigene Positionen zeitgewichtet, vor Steuern; leer: Tage ohne Bestand · gestrichelt: Vergleichsindizes",
                         if (length(points)) " · hohl: jetzt (Momentaufnahme, nur eigene Linien)" else ""),
                  side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

# Zeiger am Punkt „jetzt“: je eigene Linie der Stand jetzt und seit dem letzten Tagesschluss; Indizes ohne Momentaufnahme.
analysis_compare_moment_rows_v1 <- function(frame, now, colors, model = NULL) {
  rows <- lapply(attr(frame, "lines"), function(line) {
    value <- now$values[line$key]
    list(label = line$label, color = colors[[line$key]],
         value = if (identical(line$kind, "index")) "Index: keine Momentaufnahme" else if (length(value) != 1L || is.na(value)) "–"
           else paste0(analysis_history_pct_v1(value / 100 - 1), " · seit dem letzten Tagesschluss ", analysis_history_pct_v1(now$rates[[line$key]], 2L)))
  })
  notes <- analysis_moment_caveats_v1(model)
  if (length(notes)) rows <- c(rows, lapply(notes, function(note) list(label = "Hinweis", value = note)))
  list(title = analysis_moment_title_v1(now), rows = rows)
}

analysis_compare_rows_v1 <- function(frame, x, colors, reference = NULL) {
  position <- which.min(abs(as.numeric(frame$day) - x)); lines <- attr(frame, "lines")
  ref <- if (!is.null(reference) && reference %in% names(frame)) frame[[reference]][[position]] else NA_real_
  rows <- lapply(lines, function(line) {
    value <- frame[[line$key]][[position]]
    list(label = line$label, color = colors[[line$key]],
         value = if (is.na(value)) (if (identical(line$kind, "index")) "kein Kurs" else "kein Bestand") else analysis_history_pct_v1(value / 100 - 1))
  })
  list(title = format(frame$day[[position]], "%d.%m.%Y"), rows = rows)
}

# Je Zeitraum: TWR der Anlage und ohne Cash, Rendite des Bezugsindex, Mehr- oder Minderrendite in Prozentpunkten; p. a. ab einem Jahr.
analysis_compare_table_v1 <- function(periods, index = 1L, assets_only = NULL) {
  periods <- Filter(function(row) !is.null(analysis_assets_benchmark_of_v1(row, index)), periods)
  if (!length(periods)) return(data.frame())
  number <- function(field) analysis_history_number_v1(lapply(periods, function(row) row[[field]]))
  bench <- function(field) analysis_history_number_v1(lapply(periods, function(row) analysis_assets_benchmark_of_v1(row, index)[[field]]))
  long <- vapply(periods, function(row) row$period %in% c("all", "3y", "5y"), logical(1L))
  missing <- vapply(periods, function(row) { value <- analysis_assets_benchmark_of_v1(row, index)$missing_days; as.integer(if (is.null(value)) 0L else value) }, integer(1L))
  only <- analysis_history_number_v1(lapply(periods, function(row) {
    hit <- Filter(function(other) identical(other$period, row$period), assets_only); if (length(hit) == 1L) hit[[1L]]$twr else NULL }))
  data.frame(Zeitraum = vapply(periods, function(row) row$label, character(1L)),
             Von = format(as.Date(vapply(periods, function(row) row$start_day, character(1L))), "%d.%m.%Y"),
             Bis = format(as.Date(vapply(periods, function(row) row$end_day, character(1L))), "%d.%m.%Y"),
             `Anlage (TWR)` = analysis_history_pct_v1(number("twr")), `TWR ohne Cash` = analysis_history_pct_v1(only),
             Vergleichsindex = analysis_history_pct_v1(bench("return")),
             `Mehr-/Minderrendite` = analysis_history_points_v1(number("twr") - bench("return")),
             `Mehr-/Minderrendite ohne Cash` = analysis_history_points_v1(only - bench("return")),
             `Anlage p. a.` = analysis_history_pct_v1(ifelse(long, number("twr_annualised"), NA_real_)),
             `Index p. a.` = analysis_history_pct_v1(ifelse(long, bench("annualised"), NA_real_)),
             `Tage ohne Kurs` = ifelse(missing > 0L, as.character(missing), "–"), check.names = FALSE, stringsAsFactors = FALSE)
}

# --- Abstand vom Hoch (#506) -------------------------------------------------------------------------------------------------
# Festlegung (22.10.2026): fuer volatile Assets sehen, wie weit der Kurs unter seinem Hoch liegt. Eigene Positionen und die
# Anlage auf dem TWR-Index, nicht auf dem Wert - sonst saehe eine Einzahlung wie eine Erholung aus. Das Hoch gilt seit Beginn der
# vorliegenden Reihe, nicht als echtes Allzeithoch. Nur Anzeige.

# Je Tag Niveau / bisheriges Hoch - 1 (0 am Hoch, negativ darunter). Tage ohne Bestand bleiben leer; das Hoch laeuft weiter, denn
# der Index steht an solchen Tagen still.
analysis_drawdown_v1 <- function(values, held = rep(TRUE, length(values))) {
  out <- rep(NA_real_, length(values)); high <- NA_real_
  for (index in seq_along(values)) {
    value <- values[[index]]
    if (is.na(value) || value <= 0) next
    high <- if (is.na(high)) value else max(high, value)
    if (isTRUE(held[[index]])) out[[index]] <- value / high - 1
  }
  out
}

# Die gewaehlten Linien als Abstand vom Hoch im Zeitraum: gerechnet ueber die ganze Reihe, gezeigt im Zeitraum. Dazu je Linie die
# Niveaus im Zeitraum (fuer die Kennzahlen).
analysis_compare_drawdown_frame_v1 <- function(history, keys, period = "all", range = NULL, hydrate = function(entry) entry) {
  days <- as.Date(unlist(history$portfolio$day))
  keep <- analysis_history_window_v1(days, period, range)
  lines <- Filter(Negate(is.null), lapply(keys, function(key) analysis_compare_series_v1(history, key, hydrate)))
  frame <- data.frame(day = days[keep], stringsAsFactors = FALSE); levels <- list()
  for (line in lines) {
    frame[[line$key]] <- analysis_drawdown_v1(line$values, line$held)[keep]
    level <- line$values[keep]; level[!line$held[keep]] <- NA_real_
    levels[[line$key]] <- level
  }
  attr(frame, "lines") <- lines; attr(frame, "levels") <- levels
  frame
}

# Kennzahlen einer Linie im Zeitraum: groesster Rueckgang mit Hoch und Tief, Erholung bis zum neuen Hoch, Schwankung p. a.
# Der groesste Rueckgang zaehlt ab dem Anfang des Zeitraums. Die Schwankung ist die Standardabweichung der Tagesrenditen ueber
# Kalendertage mal Wurzel aus 365 (Tage ohne Kursaenderung zaehlen mit, so bleibt die Jahresvarianz gleich).
analysis_drawdown_stats_v1 <- function(days, levels) {
  known <- which(!is.na(levels) & levels > 0)
  empty <- list(depth = NA_real_, peak = NA, trough = NA, recovered = NA, recovery_days = NA_integer_, volatility = NA_real_, current = NA_real_)
  if (length(known) < 2L) return(empty)
  peak_value <- levels[[known[[1L]]]]; peak <- known[[1L]]; depth <- 0; best_peak <- NA_integer_; trough <- NA_integer_
  for (index in known) {
    if (levels[[index]] > peak_value) { peak_value <- levels[[index]]; peak <- index }
    drop <- levels[[index]] / peak_value - 1
    if (drop < depth) { depth <- drop; best_peak <- peak; trough <- index }
  }
  recovered <- NA_integer_
  if (!is.na(trough)) {
    later <- known[known > trough & levels[known] >= levels[[best_peak]]]
    if (length(later)) recovered <- later[[1L]]
  }
  pairs <- known[-1L][diff(known) == 1L]
  returns <- levels[pairs] / levels[pairs - 1L] - 1
  list(depth = depth, peak = if (is.na(best_peak)) NA else days[[best_peak]], trough = if (is.na(trough)) NA else days[[trough]],
       recovered = if (is.na(recovered)) NA else days[[recovered]],
       recovery_days = if (is.na(recovered)) NA_integer_ else as.integer(days[[recovered]] - days[[trough]]),
       volatility = if (length(returns) >= 20L) stats::sd(returns) * sqrt(365) else NA_real_,
       current = levels[[known[[length(known)]]]] / max(levels[known]) - 1)
}

analysis_compare_drawdown_table_v1 <- function(frame) {
  lines <- attr(frame, "lines"); levels <- attr(frame, "levels")
  if (!length(lines) || !nrow(frame)) return(data.frame())
  date <- function(value) if (length(value) != 1L || is.na(value)) "–" else format(as.Date(value), "%d.%m.%Y")
  rows <- lapply(lines, function(line) {
    stats <- analysis_drawdown_stats_v1(frame$day, levels[[line$key]])
    current <- frame[[line$key]]; current <- current[!is.na(current)]
    erholt <- if (is.na(stats$trough) || isTRUE(stats$depth == 0)) "–" else if (is.na(stats$recovered)) "noch nicht" else
      sprintf("%s (%d Tage nach dem Tief)", date(stats$recovered), stats$recovery_days)
    data.frame(Linie = line$label, `Abstand vom Hoch am Ende` = analysis_history_pct_v1(if (length(current)) current[[length(current)]] else NA_real_),
               `Größter Rückgang im Zeitraum` = analysis_history_pct_v1(if (isTRUE(stats$depth == 0)) NA_real_ else stats$depth),
               Hoch = date(stats$peak), Tief = date(stats$trough), `Wieder auf dem Hoch` = erholt,
               `Schwankung p. a.` = analysis_history_pct_v1(stats$volatility), check.names = FALSE, stringsAsFactors = FALSE)
  })
  do.call(rbind, rows)
}

# Zonen als Baender: von der ersten Schwelle abwaerts heller, ab der zweiten kraeftiger. Die Farbe ist die des Verlusts, sehr blass.
.analysis_drawdown_zones_v1 <- function(zones, bottom) {
  zones <- sort(unique(zones)); if (!length(zones)) return(invisible(NULL))
  edges <- c(-zones / 100, bottom)
  for (index in seq_along(zones)) {
    upper <- edges[[index]]; lower <- if (index < length(zones)) edges[[index + 1L]] else min(bottom, upper)
    graphics::rect(graphics::par("usr")[[1L]], lower, graphics::par("usr")[[2L]], upper, border = NA,
                   col = grDevices::adjustcolor(ANALYSIS_HISTORY_INK_V1[["negative"]], 0.05 + 0.05 * index))
    graphics::abline(h = upper, col = grDevices::adjustcolor(ANALYSIS_HISTORY_INK_V1[["negative"]], 0.55), lty = 3, lwd = 1)
    graphics::text(graphics::par("usr")[[1L]], upper, paste0("Zone ", "\u2212", zones[[index]], " %"), adj = c(0, -0.4), cex = 0.72,
                   col = ANALYSIS_HISTORY_INK_V1[["secondary"]])
  }
}

analysis_drawdown_axis_labels_v1 <- function(at) ifelse(abs(at) < 1e-12, "0 %", analysis_history_pct_v1(at, 0L))

analysis_compare_drawdown_plot_v1 <- function(frame, colors, zones = ANALYSIS_DISPLAY_V1$zones, now = NULL) {
  ink <- ANALYSIS_HISTORY_INK_V1; lines <- attr(frame, "lines")
  old <- graphics::par(no.readonly = TRUE); on.exit(graphics::par(old))
  graphics::par(bg = ink[["surface"]], family = "sans", mar = c(2.2, 7, 2.2, 12), mgp = c(3, 0.6, 0), tcl = -0.2)
  values <- unlist(lapply(lines, function(line) frame[[line$key]]))
  points <- if (is.null(now)) numeric() else now$values[intersect(names(now$values), vapply(lines, function(line) line$key, character(1L)))]
  bottom <- min(c(values, points, if (length(zones)) -max(zones) / 100 * 1.1 else NULL, -0.05), na.rm = TRUE)
  span <- c(bottom * 1.04, 0.02)
  xlim <- range(c(frame$day, if (length(points)) now$day))
  graphics::plot(frame$day, rep(0, nrow(frame)), type = "n", xlim = xlim, ylim = span, axes = FALSE, xlab = "", ylab = "")
  .analysis_drawdown_zones_v1(zones, span[[1L]])
  at <- pretty(span, n = 5L); at <- at[at <= 0]
  graphics::abline(h = at, col = ink[["grid"]], lwd = 1)
  graphics::axis(2, at = at, labels = analysis_drawdown_axis_labels_v1(at), las = 1, col = NA, col.axis = ink[["secondary"]], cex.axis = 0.8)
  graphics::abline(h = 0, col = ink[["baseline"]], lwd = 1)
  for (line in lines) .analysis_history_line_v1(frame$day, frame[[line$key]], colors[[line$key]], rep(identical(line$kind, "index"), nrow(frame)))
  for (key in names(points)) .analysis_moment_mark_v1(frame$day[[nrow(frame)]], frame[[key]][[nrow(frame)]], now$day, points[[key]], colors[[key]])
  ends <- vapply(lines, function(line) {
    if (line$key %in% names(points)) return(points[[line$key]])
    known <- which(!is.na(frame[[line$key]])); if (length(known)) frame[[line$key]][[max(known)]] else NA_real_ }, numeric(1L))
  labels <- vapply(seq_along(lines), function(position) paste(.analysis_compare_short_v1(lines[[position]]$label), analysis_history_pct_v1(ends[[position]])), character(1L))
  .analysis_history_end_labels_v1(xlim[[2L]], ends, labels, vapply(lines, function(line) colors[[line$key]], character(1L)))
  .analysis_history_axis_dates_v1(frame$day)
  graphics::mtext("Abstand vom bisherigen Hoch · 0 % = am Hoch · eigene Positionen auf dem zeitgewichteten Index, gestrichelt: Vergleichsindizes",
                  side = 3, line = 0.6, adj = 0, cex = 0.8, col = ink[["secondary"]])
  invisible(.analysis_history_geometry_v1())
}

analysis_compare_drawdown_rows_v1 <- function(frame, x, colors) {
  position <- which.min(abs(as.numeric(frame$day) - x)); lines <- attr(frame, "lines")
  rows <- lapply(lines, function(line) {
    value <- frame[[line$key]][[position]]
    list(label = line$label, color = colors[[line$key]],
         value = if (is.na(value)) (if (identical(line$kind, "index")) "kein Kurs" else "kein Bestand") else analysis_history_pct_v1(value))
  })
  list(title = format(frame$day[[position]], "%d.%m.%Y"), rows = rows)
}

ANALYSIS_DRAWDOWN_NOTES_V1 <- paste(
  "Das Hoch gilt seit Beginn der vorliegenden Reihe, nicht als echtes Allzeithoch. Der größte Rückgang zählt ab dem Anfang des Zeitraums;",
  "„Wieder auf dem Hoch“ ist der erste Tag, an dem die Linie das Hoch vor dem Tief wieder erreicht.",
  "Die Schwankung ist die Standardabweichung der Tagesrenditen, aufs Jahr gerechnet (mal Wurzel aus 365, ab 20 Tagen).",
  "Eigene Zonen lassen sich in der App „Daten“ unter „Einstellungen“ festlegen.")

# Erklaerung der taeglich festen Gewichte (#502, Text vom 22.10.2026); derselbe Text steht in der Data-App bei den
# Gewichten (DATA_ANALYSIS_INDEX_WEIGHTS_TEXT_V1) - ein Vertragstest haelt beide gleich.
ANALYSIS_COMPARE_WEIGHTS_TEXT_V1 <- paste(
  "Ein Index aus mehreren Assets wird jeden Tag auf seine festen Gewichte zurückgesetzt. Er verhält sich, als würde man täglich verkaufen, was gestiegen ist,",
  "und nachkaufen, was gefallen ist, ohne Gebühren und ohne Steuern. Nur so ergibt jeder Zeitraum und jede Haltedauer dieselbe Indexreihe.",
  "Läuft ein Bestandteil lange in eine Richtung (etwa BTC stark aufwärts), liegt dieser Index unter einem einmal gekauften und gehaltenen Mix;",
  "schwanken die Kurse hin und her, liegt er darüber.")

ANALYSIS_COMPARE_NOTES_V1 <- paste(
  "Ein Vergleichsindex ist eine gedachte Anlage ohne Gebühren und Steuern; die eigenen Positionen rechnen vor Steuern, aber nach Gebühren.",
  "Ausschüttungen zählen beim Index am Ex-Tag, beim eigenen Asset am Zahltag – liegt eine Ausschüttung zwischen Dezember und Januar, landet sie so in verschiedenen Kalenderjahren;",
  "über längere Zeiträume gleicht sich das aus. Bei Krypto ist der Index reiner Kurs; Staking-Rewards zählen nur beim eigenen Asset.",
  "Im Bild laufen eigene Positionen über ihre ganze Spanne; je Asset fair über dieselben Tage mit Bestand vergleicht die Rangliste darunter.")

# Rangliste gegen den Bezugsindex (#502), seit rc.309 hier statt in "Assets und Gruppen": Index-Vergleiche sucht man im
# Vergleich; die eigenen Kennzahlen bleiben dort (Festlegung 23.10.2026).
ANALYSIS_RANKING_SORTS_V1 <- c("Mehr-/Minderrendite ggü. Index" = "excess", "Mehr-/Minderrendite p. a. ggü. Index" = "excess_annualised",
                               "zeitgewichtete Rendite" = "twr", "Anlageerfolg" = "gain")
ANALYSIS_RANKING_COLUMNS_V1 <- c("Name", "Klasse", "Von", "Bis", "Tage mit Bestand", "TWR", "TWR p. a.", "Index (gleiche Tage)",
                                 "Mehr-/Minderrendite", "Mehr-/Minderrendite p. a.")
analysis_ranking_table_v1 <- function(history, level, period, sort, index) {
  if (is.null(history) || !length(history$benchmarks)) return(data.frame())
  table <- analysis_assets_overview_table_v1(history, level, period, sort, "gross", NULL, index)
  if (!nrow(table)) return(table)
  table[, intersect(ANALYSIS_RANKING_COLUMNS_V1, names(table)), drop = FALSE]
}
analysis_ranking_asset_choices_v1 <- function(history) {
  assets <- if (is.null(history)) list() else history$assets
  if (!length(assets)) return(c("Keine Assets" = ""))
  labels <- vapply(assets, function(row) row$label, character(1L))
  c("Bitte wählen" = "", stats::setNames(as.character(seq_along(assets))[order(labels)], sort(labels)))
}
analysis_ranking_asset_periods_v1 <- function(history, choice, index, bounds = NULL) {
  number <- suppressWarnings(as.integer(choice))
  if (is.null(history) || !length(history$benchmarks) || length(number) != 1L || is.na(number) || number < 1L || number > length(history$assets))
    return(data.frame())
  table <- analysis_assets_periods_table_v1(analysis_history_rows_in_v1(history$assets[[number]]$performance$periods, bounds), "gross", index)
  if (!nrow(table)) return(table)
  table[, intersect(c("Zeitraum", "Von", "Bis", "Tage mit Bestand", "zeitgewichtet (TWR)", "TWR p. a.", "Vergleichsindex (gleiche Tage)", "Mehr-/Minderrendite"),
    names(table)), drop = FALSE]
}

analysis_compare_ui_v1 <- function() shiny::tagList(
  portelyra_card(
    "Vergleich",
    copy = paste("Anlage, Klassen, eigene Gruppen und Assets neben einem oder mehreren Vergleichsindizes über denselben Zeitraum, jede Linie auf 100 zu ihrem ersten Wert.",
                 "Erst dieser Vergleich zeigt, was besser oder schlechter lief als „der Markt“. Höchstens sieben Linien zugleich."),
    # Lesart gesammelt in einem Kaestchen (#507, Variante A) statt als Absaetze unter Bildern und Tabellen.
    note = portelyra_note_v1(title = "So lesen Sie den Vergleich", id = "analysis-compare",
      "„Abstand zum Bezugsindex“ ist der Unterschied der Renditen über die gemeinsame Spanne, in Prozentpunkten; ¹ der Index beginnt später als die Linie, der Abstand gilt ab seinem ersten Tag.",
      ANALYSIS_COMPARE_NOTES_V1,
      paste(ANALYSIS_COMPARE_WEIGHTS_TEXT_V1, "Behalten Sie das beim Lesen der Mehr- oder Minderrendite im Kopf."),
      paste("Abstand vom Hoch:", ANALYSIS_DRAWDOWN_NOTES_V1)),
    shiny::uiOutput("compare_state"),
    shiny::div(class = "pl-form-grid",
      shiny::selectizeInput("compare_lines", "Linien", choices = NULL, multiple = TRUE, width = "100%",
                            options = list(plugins = list("remove_button"), maxItems = ANALYSIS_COMPARE_LIMIT_V1, placeholder = "Linien wählen")),
      shiny::selectInput("compare_reference", "Bezugsindex", c("Kein Vergleichsindex" = ""), selectize = FALSE),
      shiny::radioButtons("compare_scale", "Skala", c("linear" = "linear", "logarithmisch" = "log"), selected = "linear", inline = TRUE)),
    shiny::uiOutput("compare_part_state"),
    analysis_history_zoomable_v1("zeitraum", "compare",
      shiny::plotOutput("compare_plot", height = "400px", hover = shiny::hoverOpts("compare_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      shiny::uiOutput("compare_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::uiOutput("compare_moment_note"),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Abstand vom Hoch"),
    shiny::div(style = "position:relative",
      shiny::plotOutput("compare_drawdown_plot", height = "240px", hover = shiny::hoverOpts("compare_drawdown_hover", delay = 60, delayType = "throttle", clip = FALSE, nullOutside = FALSE)),
      shiny::uiOutput("compare_drawdown_overlay", style = "position:absolute;inset:0;pointer-events:none")),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("compare_drawdown_table")),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Je Linie im Zeitraum des Bilds"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("compare_lines_table")),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Anlage gegen den Bezugsindex je Zeitraum"),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("compare_table")),
    shiny::tags$details(shiny::tags$summary("Kalenderjahre von – bis"),
      shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("compare_spans")))),
  portelyra_card("Rangliste gegen den Bezugsindex", help = "app-analyse#vergleich",
    copy = "Je Asset, Klasse oder eigener Gruppe die zeitgewichtete Rendite neben dem oben gewählten Bezugsindex, über dieselben Tage mit Bestand.",
    note = portelyra_note_v1(title = "So lesen Sie die Rangliste", id = "analysis-ranking",
      "Je Zeile läuft der Index über dieselben Tage mit Bestand wie die Zeile. So lassen sich auch kurz und lang gehaltene Assets vergleichen.",
      "„Mehr-/Minderrendite“ ist der Abstand der TWR zum Index in Prozentpunkten, „p. a.“ gilt für mehrjährige Zeiträume.",
      "Der Index ist eine gedachte Anlage ohne Gebühren und Steuern; die TWR der eigenen Positionen ist vor Steuern, aber nach Gebühren."),
    shiny::uiOutput("ranking_index_state"),
    shiny::div(class = "pl-form-grid",
      shiny::selectInput("ranking_level", "Ebene", c("Je Asset" = "assets", "Je Assetklasse" = "classes", "Je eigener Gruppe" = "groups"), selectize = FALSE),
      shiny::uiOutput("ranking_period_ui"),
      shiny::selectInput("ranking_sort", "Sortiert nach", ANALYSIS_RANKING_SORTS_V1, selectize = FALSE)),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("ranking_table")),
    shiny::h4(class = "pl-section-title", style = "margin-top:14px", "Ein Asset gegen den Bezugsindex je Zeitraum"),
    shiny::selectInput("ranking_asset", "Asset", c("Bitte wählen" = ""), width = "360px", selectize = FALSE),
    shiny::div(class = "pl-table-wrap", style = "white-space:nowrap", shiny::tableOutput("ranking_asset_periods"))))

analysis_compare_server_v1 <- function(input, output, session, ready, spec, geometry, hydrate = function(entry) entry, moment = function() NULL) {
  colors <- shiny::reactiveVal(character())
  bounds <- shiny::reactive(analysis_history_bounds_v1(ready(), spec()))
  shiny::observeEvent(ready(), {
    history <- ready(); choices <- analysis_compare_choices_v1(history)
    keys <- unlist(choices, use.names = FALSE)
    kept <- intersect(shiny::isolate(input$compare_lines), keys)
    shiny::updateSelectizeInput(session, "compare_lines", choices = choices, selected = if (length(kept)) kept else analysis_compare_default_lines_v1(history), server = FALSE)
    references <- analysis_assets_index_choices_v1(history)
    keep <- shiny::isolate(input$compare_reference)
    shiny::updateSelectInput(session, "compare_reference", choices = references, selected = if (!is.null(keep) && keep %in% references) keep else references[[1L]])
  }, ignoreNULL = TRUE)
  chosen <- shiny::reactive({
    history <- ready(); if (is.null(history)) return(character())
    keys <- input$compare_lines
    if (is.null(keys)) keys <- analysis_compare_default_lines_v1(history)
    utils::head(intersect(keys, unlist(analysis_compare_choices_v1(history), use.names = FALSE)), ANALYSIS_COMPARE_LIMIT_V1)
  })
  shiny::observeEvent(chosen(), colors(analysis_compare_assign_colors_v1(shiny::isolate(colors()), chosen())), ignoreNULL = FALSE)
  reference <- shiny::reactive({ value <- input$compare_reference; if (is.character(value) && nzchar(value)) paste0("index:", value) else NULL })
  part_error <- shiny::reactiveVal(NULL)
  frame <- shiny::reactive({
    history <- ready(); window <- spec(); if (is.null(history)) return(NULL)
    keys <- unique(c(chosen(), reference()))
    result <- tryCatch(analysis_compare_frame_v1(history, keys, window$period, window$range, hydrate),
                       error = function(error) structure(list(code = if (is.character(error$code)) error$code else "display_boundary_failed"), class = "part_failure"))
    if (inherits(result, "part_failure")) { part_error(result$code); return(NULL) }
    part_error(NULL); result
  })
  # Nur die gewaehlten Linien zeichnen; der Bezugsindex rechnet auch mit, wenn er nicht gezeichnet wird.
  drawn <- shiny::reactive({
    current <- frame(); if (is.null(current)) return(NULL)
    attr(current, "lines") <- Filter(function(line) line$key %in% chosen(), attr(current, "lines"))
    current
  })
  output$compare_part_state <- shiny::renderUI({
    code <- part_error(); if (is.null(code)) return(NULL)
    portelyra_status_panel("Die Tagesreihen einer Linie ließen sich nicht lesen",
      if (identical(code, "display_no_latest")) "Inzwischen ist ein neuer Stand veröffentlicht. „Neu lesen“ oben lädt ihn." else pl_error_text_v1(code), tone = "warning")
  })
  output$compare_state <- shiny::renderUI({
    history <- ready(); if (is.null(history)) return(NULL)
    if (!length(history$benchmarks)) return(portelyra_status_panel("Kein Vergleichsindex angelegt",
      "In der App „Daten“ unter „2. Stammdaten · Analyse · Vergleichsindizes und Asset-Gruppen“ einen Index aus einem oder mehreren Assets mit Kurshistorie anlegen, etwa einen MSCI-World-ETF oder 50 % Gold und 50 % BTC. Bis dahin lassen sich Anlage, Klassen, Gruppen und Assets untereinander vergleichen.", tone = "neutral"))
    index <- history$benchmarks[[min(analysis_assets_index_number_v1(input$compare_reference), length(history$benchmarks))]]
    shiny::p(class = "pl-field-hint", paste0("Bezugsindex: ", analysis_assets_index_basis_text_v1(index), " · Kurse in EUR aus dem Bewertungsstand",
      if (isTRUE(index$missing_days > 0)) sprintf(" · %s Tage ohne Kurs", index$missing_days) else "", "."))
  })
  # Punkt „jetzt“ (#512) fuer die eigenen Linien; Indizes haben keine Momentaufnahme.
  now <- shiny::reactive({ model <- moment(); current <- drawn(); if (is.null(model) || is.null(current)) NULL else analysis_moment_compare_v1(model, ready(), current) })
  output$compare_plot <- shiny::renderPlot({
    current <- drawn(); shiny::req(current, nrow(current) > 1L, length(attr(current, "lines")) > 0L)
    geometry$compare <- analysis_compare_plot_v1(current, colors(), identical(input$compare_scale, "log"), now())
  })
  output$compare_moment_note <- shiny::renderUI({ if (is.null(now())) NULL else analysis_moment_note_v1(moment(), "Punkte nur an den eigenen Linien: Vergleichsindizes haben keine Momentaufnahme.") })
  output$compare_overlay <- shiny::renderUI({
    current <- drawn(); hover <- input$compare_hover
    day <- analysis_history_pixel_day_v1(geometry$compare, hover)
    if (is.null(current) || !nrow(current) || is.null(day) || !length(attr(current, "lines"))) return(NULL)
    if (analysis_moment_hovered_v1(now(), current$day, day)) {
      content <- analysis_compare_moment_rows_v1(current, now(), colors(), moment())
      return(.analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$compare))
    }
    content <- analysis_compare_rows_v1(current, day, colors(), reference())
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$compare)
  })
  # Abstand vom Hoch (#506): dieselben Linien und derselbe Zeitraum wie das Bild darueber.
  drawdown <- shiny::reactive({
    history <- ready(); window <- spec(); if (is.null(history) || !length(chosen())) return(NULL)
    tryCatch(analysis_compare_drawdown_frame_v1(history, chosen(), window$period, window$range, hydrate), error = function(error) NULL)
  })
  drawdown_now <- shiny::reactive({
    point <- now(); current <- drawdown(); if (is.null(point) || is.null(current) || !nrow(current)) return(NULL)
    values <- vapply(names(point$rates), function(key) if (key %in% names(current)) analysis_moment_drawdown_v1(current[[key]][[nrow(current)]], point$rates[[key]]) else NA_real_, numeric(1L))
    values <- values[!is.na(values)]
    if (length(values)) list(day = point$day, at = point$at, values = values) else NULL
  })
  output$compare_drawdown_plot <- shiny::renderPlot({
    current <- drawdown(); shiny::req(current, nrow(current) > 1L, length(attr(current, "lines")) > 0L)
    geometry$compare_drawdown <- analysis_compare_drawdown_plot_v1(current, colors(), now = drawdown_now())
  })
  output$compare_drawdown_overlay <- shiny::renderUI({
    current <- drawdown(); hover <- input$compare_drawdown_hover
    day <- analysis_history_pixel_day_v1(geometry$compare_drawdown, hover)
    if (is.null(current) || !nrow(current) || is.null(day) || !length(attr(current, "lines"))) return(NULL)
    content <- analysis_compare_drawdown_rows_v1(current, day, colors())
    .analysis_history_box_v1(hover, content$title, content$rows, geometry = geometry$compare_drawdown)
  })
  output$compare_drawdown_table <- shiny::renderTable({
    current <- drawdown(); shiny::req(current)
    analysis_history_tint_v1(analysis_compare_drawdown_table_v1(current))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$compare_lines_table <- shiny::renderTable({
    current <- frame(); shiny::req(current)
    attr(current, "lines") <- Filter(function(line) line$key %in% chosen(), attr(current, "lines"))
    analysis_history_tint_v1(analysis_compare_lines_table_v1(current, reference()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  index_number <- shiny::reactive(analysis_assets_index_number_v1(input$compare_reference))
  output$compare_table <- shiny::renderTable({
    history <- shiny::req(ready())
    analysis_history_tint_v1(analysis_compare_table_v1(analysis_history_rows_in_v1(history$investment$periods, bounds()), index_number(), history$investment$assets_only$periods))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$compare_spans <- shiny::renderTable({
    history <- shiny::req(ready())
    spans <- analysis_history_rows_in_v1(history$investment$year_spans, bounds())
    analysis_history_tint_v1(analysis_compare_table_v1(if (isTRUE(attr(spans, "cover"))) list() else spans, index_number(), history$investment$assets_only$year_spans))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  # Rangliste gegen den Bezugsindex (seit rc.309 hier): derselbe Index wie das Bild darueber.
  shiny::observeEvent(ready(), {
    history <- ready()
    shiny::updateSelectInput(session, "ranking_asset", choices = analysis_ranking_asset_choices_v1(history), selected = "")
  }, ignoreNULL = TRUE)
  # Der Zeitraum oben (#531 Punkt 1): je Asset gibt es keine Kalenderjahre von–bis, dort waehlt man unter den Zeitraeumen darin.
  ranking_offer <- shiny::reactive({ history <- ready(); if (is.null(history)) NULL else analysis_history_offer_v1(history$investment$periods, bounds()) })
  output$ranking_period_ui <- shiny::renderUI({
    offer <- ranking_offer(); if (is.null(offer)) return(NULL)
    analysis_history_offer_ui_v1("ranking_period", offer, shiny::isolate(input$ranking_period), analysis_history_window_label_v1(spec(), bounds()))
  })
  ranking_key <- shiny::reactive({ offer <- ranking_offer(); key <- if (is.null(offer)) NULL else analysis_history_offer_key_v1(offer, input$ranking_period)
    if (is.null(key)) "" else key })
  output$ranking_index_state <- shiny::renderUI({
    history <- ready(); if (is.null(history)) return(NULL)
    if (!length(history$benchmarks)) return(shiny::p(class = "pl-field-hint",
      "Mit einem Vergleichsindex (Daten → „2. Stammdaten · Analyse“) zeigt jede Zeile, ob sie besser oder schlechter lief als der Index."))
    index <- history$benchmarks[[min(index_number(), length(history$benchmarks))]]
    shiny::p(class = "pl-field-hint", paste0("Bezugsindex: ", analysis_assets_index_basis_text_v1(index), "."))
  })
  output$ranking_table <- shiny::renderTable({
    history <- shiny::req(ready())
    analysis_history_tint_v1(analysis_ranking_table_v1(history, if (is.null(input$ranking_level)) "assets" else input$ranking_level,
      ranking_key(), if (is.null(input$ranking_sort)) "excess" else input$ranking_sort, index_number()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  output$ranking_asset_periods <- shiny::renderTable({
    history <- shiny::req(ready())
    analysis_history_tint_v1(analysis_ranking_asset_periods_v1(history, input$ranking_asset, index_number(), bounds()))
  }, striped = TRUE, spacing = "xs", sanitize.text.function = .analysis_history_html_v1)
  invisible(list(frame = frame, colors = colors, chosen = chosen, drawdown = drawdown, now = now, drawdown_now = drawdown_now))
}
