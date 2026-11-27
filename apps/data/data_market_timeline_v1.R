# Die Bewertungs-Zeitleiste im Sammellauf (#495, rc.393).
#
# Bis rc.392 holte und bewertete der Sammellauf je Asset genau eine Kursreihe: die gewaehlte Zuordnung eines am Markt bewerteten
# Assets. Mit der Zeitleiste ("bis X Yahoo-Symbol A, ab X Anbieter B, ab Y eigene Kurse") traegt jede Marktreihe der Zeitleiste
# ihren Abschnitt. Wird der Bewertungsstand neu aufgebaut (der Kern verwirft ihn bei geaendertem Algorithmus-Abdruck), muss jede
# dieser Reihen wieder entstehen, sonst waeren vergangene Tage offen - ein Neuaufbau muss 1:1 gleich sein.
#
# Diese Datei liest die Zeitleiste ueber die CLI (scripts/desktop_asset_valuation_timeline.py, Befehl `overview`) und macht daraus
# je Asset die Marktreihen mit ihrem Abschnitt. Das Inventar (data_asset_center_market_inventory_v1) fuehrt daraus je Reihe eine
# Zeile; die Kurskette (data_market_chain_v1.R) holt fuer eine fruehere Reihe nur in den Grenzen ihres Abschnitts und nur, wenn dort
# Tage fehlen. Ohne Speicher der Zeitleiste startet kein Prozess, und alles bleibt wie bisher.

DATA_MARKET_TIMELINE_METHODS_V1 <- c("external_market", "manual", "transaction_only")

data_market_timeline_abort_v1 <- function(code) {
  if (!is.character(code) || length(code) != 1L || !grepl("^data_market_timeline_[a-z_]+$", code)) code <- "data_market_timeline_unreadable"
  stop(structure(class = c("spot_data_market_timeline_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
}

# Ein UTC-Tag oder nichts.
data_market_timeline_day_v1 <- function(value) {
  is.character(value) && length(value) == 1L && !is.na(value) && grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value)
}

# Kosten je Anbieter aus den Manifesten der Kursanbieter-Plugins (`cost`: free, free_quota, paid). Ein Anbieter ohne lesbares
# Manifest gilt nicht als kostenlos - lieber ein Abruf zu wenig als einer, der Geld kostet.
data_market_timeline_provider_costs_v1 <- function(project_root) {
  folder <- file.path(project_root, "plugins", "price_providers")
  costs <- character()
  for (directory in sort(list.dirs(folder, full.names = TRUE, recursive = FALSE))) {
    if (startsWith(basename(directory), "_")) next
    manifest <- tryCatch(jsonlite::fromJSON(file.path(directory, "manifest.json"), simplifyVector = FALSE), error = function(error) NULL)
    id <- if (is.list(manifest)) manifest$provider_id else NULL
    cost <- if (is.list(manifest)) manifest$cost else NULL
    if (is.character(id) && length(id) == 1L && grepl("^[a-z][a-z0-9_]{1,40}$", id) &&
        is.character(cost) && length(cost) == 1L && cost %in% c("free", "free_quota", "paid")) costs[[id]] <- cost
  }
  costs
}

# Operationen je Anbieter aus den Manifesten der Kursanbieter-Plugins (rc.394): Welche Anbieter Tageskurse (daily_history) oder einen
# Momentkurs (quote) liefern. Ob ein Anbieter im Datenraum aktiv ist, prueft der Kern beim Abruf und nennt dann den Grund.
data_price_provider_operations_v1 <- function(project_root) {
  folder <- file.path(project_root, "plugins", "price_providers")
  result <- list()
  for (directory in sort(list.dirs(folder, full.names = TRUE, recursive = FALSE))) {
    if (startsWith(basename(directory), "_")) next
    manifest <- tryCatch(jsonlite::fromJSON(file.path(directory, "manifest.json"), simplifyVector = FALSE), error = function(error) NULL)
    id <- if (is.list(manifest)) manifest$provider_id else NULL
    operations <- if (is.list(manifest)) unlist(manifest$operations) else NULL
    if (is.character(id) && length(id) == 1L && grepl("^[a-z][a-z0-9_]{1,40}$", id) && is.character(operations)) result[[id]] <- operations
  }
  result
}
data_price_providers_with_v1 <- function(operations, operation) {
  ids <- names(Filter(function(items) operation %in% items, operations))
  unique(c(if ("yahoo" %in% ids) "yahoo", sort(ids)))
}

# Die Zeitleiste als Marktreihen je Asset (Schluessel: asset_ref der Oberflaeche). `overview` ist das Ergebnis des CLI-Befehls,
# `asset_refs` ein benannter Vektor asset_id -> asset_ref. Je Reihe: Anbieter, Symbol, Rolle (laufender Abschnitt = "current",
# sonst "earlier"), erster und letzter Tag ihrer Abschnitte (NA = seit Beginn bzw. offen), die Abschnitte selbst und die Kosten.
# Taucht eine Reihe in mehreren Abschnitten auf, gilt die Huelle der Abschnitte.
data_market_timeline_series_v1 <- function(overview, asset_refs, costs = NULL) {
  if (is.null(overview)) return(NULL)
  if (!is.list(overview) || !identical(overview$contract_version, "asset_valuation_timeline_overview_v1") || !is.list(overview$assets))
    data_market_timeline_abort_v1("data_market_timeline_invalid")
  if (is.null(costs)) costs <- if (is.character(overview$provider_costs)) overview$provider_costs else
    unlist(overview$provider_costs, use.names = TRUE)
  if (is.null(costs)) costs <- character()
  day_or_na <- function(value) {
    if (is.null(value)) return(NA_character_)
    if (!data_market_timeline_day_v1(value)) data_market_timeline_abort_v1("data_market_timeline_invalid")
    value
  }
  result <- list()
  for (item in overview$assets) {
    if (!is.list(item) || !is.character(item$asset_id) || length(item$asset_id) != 1L || !is.list(item$segments) || !length(item$segments))
      data_market_timeline_abort_v1("data_market_timeline_invalid")
    ref <- if (item$asset_id %in% names(asset_refs)) unname(asset_refs[[item$asset_id]]) else NULL
    # Ein Asset, das die Oberflaeche nicht fuehrt (archiviert, fremd), hat keine Zeile im Inventar.
    if (!is.character(ref) || length(ref) != 1L || !nzchar(ref)) next
    segments <- lapply(item$segments, function(segment) {
      if (!is.list(segment) || !is.character(segment$method) || length(segment$method) != 1L ||
          !segment$method %in% DATA_MARKET_TIMELINE_METHODS_V1) data_market_timeline_abort_v1("data_market_timeline_invalid")
      market <- identical(segment$method, "external_market")
      if (market && !(is.character(segment$provider_id) && length(segment$provider_id) == 1L && nzchar(segment$provider_id) &&
          is.character(segment$provider_symbol) && length(segment$provider_symbol) == 1L && nzchar(segment$provider_symbol)))
        data_market_timeline_abort_v1("data_market_timeline_invalid")
      list(valid_from = day_or_na(segment$valid_from), valid_until = day_or_na(segment$valid_until), method = segment$method,
           provider_id = if (market) segment$provider_id else NA_character_,
           provider_symbol = if (market) segment$provider_symbol else NA_character_)
    })
    last <- segments[[length(segments)]]
    series <- list()
    for (segment in segments) {
      if (!identical(segment$method, "external_market")) next
      found <- which(vapply(series, function(row) identical(row$provider_id, segment$provider_id) &&
        identical(row$provider_symbol, segment$provider_symbol), logical(1L)))
      window <- list(valid_from = segment$valid_from, valid_until = segment$valid_until)
      if (length(found)) series[[found[[1L]]]]$windows <- c(series[[found[[1L]]]]$windows, list(window))
      else series[[length(series) + 1L]] <- list(provider_id = segment$provider_id, provider_symbol = segment$provider_symbol,
                                                 windows = list(window))
    }
    series <- lapply(series, function(row) {
      froms <- vapply(row$windows, `[[`, character(1L), "valid_from")
      untils <- vapply(row$windows, `[[`, character(1L), "valid_until")
      current <- identical(last$method, "external_market") && identical(last$provider_id, row$provider_id) &&
        identical(last$provider_symbol, row$provider_symbol)
      cost <- if (row$provider_id %in% names(costs)) unname(costs[[row$provider_id]]) else "unknown"
      c(row, list(role = if (current) "current" else "earlier",
                  valid_from = if (anyNA(froms)) NA_character_ else min(froms),
                  valid_until = if (anyNA(untils)) NA_character_ else max(untils),
                  cost = cost))
    })
    result[[ref]] <- list(asset_id = item$asset_id, segments = segments, series = series, current_method = last$method)
  }
  list(status = "ready", assets = result)
}

# Liest die Zeitleiste ueber die CLI. `overview()` liefert NULL, solange es keinen Speicher gibt (dann startet kein Prozess); das
# Ergebnis wird bis zur naechsten Aenderung des Speichers gehalten. Ein vorhandener, aber unlesbarer Speicher sperrt
# (data_market_timeline_unreadable) - kein stiller Rueckfall auf eine Reihe je Asset. `coverage(asset_id)` nennt je Symbol die
# bewerteten Tage im Bewertungsstand (Befehl `read`), damit der Sammellauf erkennt, dass eine fruehere Reihe nach einem Neuaufbau
# des Stands wieder bewertet werden muss. `valued_series()` nennt alle Reihen, die der Bewertungsstand fuehrt (Befehl `series`): Fehlt
# eine laufende Reihe dort ganz, bewertet der Sammellauf sie aus den gespeicherten Kursen (#493).
new_data_market_timeline_reader_v1 <- function(project_root, context, cli_runner = NULL, data_space = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  space <- if (is.null(data_space)) runtime_data_space_path(context) else data_space
  cli <- file.path(root, "scripts", "desktop_asset_valuation_timeline.py")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                  actor_id = context$actor_id, role = "desktop_owner")
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    python <- Sys.which("python3")
    if (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli))) data_market_timeline_abort_v1("data_market_timeline_unreadable")
    body <- c(list(context = payload, data_space_path = space), extra)
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE,
      input = as.character(jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA))))
    status <- attr(output, "status"); if (is.null(status)) status <- 0L
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(as.integer(status), 0L) || !identical(parsed$status, "completed"))
      data_market_timeline_abort_v1("data_market_timeline_unreadable")
    parsed$result
  }
  store <- file.path(space, "asset-valuation-timeline-v1", "timeline.sqlite")
  held <- new.env(parent = emptyenv()); held$stamp <- NULL; held$value <- NULL; held$costs <- NULL
  stamp <- function() {
    info <- suppressWarnings(file.info(store, extra_cols = FALSE))
    if (is.na(info$size)) NULL else paste(format(as.numeric(info$mtime), digits = 22), info$size)
  }
  list(
    overview = function() {
      current <- stamp()
      if (is.null(current)) return(NULL)
      if (identical(held$stamp, current)) return(held$value)
      value <- tryCatch(run("overview", list()), error = function(error) data_market_timeline_abort_v1("data_market_timeline_unreadable"))
      if (!is.list(value) || !identical(value$contract_version, "asset_valuation_timeline_overview_v1") || !is.list(value$assets))
        data_market_timeline_abort_v1("data_market_timeline_unreadable")
      if (is.null(held$costs)) held$costs <- data_market_timeline_provider_costs_v1(root)
      value$provider_costs <- held$costs
      held$stamp <- current; held$value <- value
      value
    },
    coverage = function(asset_id) {
      if (is.null(stamp())) return(list())
      value <- run("read", list(asset_id = asset_id))
      if (is.list(value) && is.list(value$coverage)) value$coverage else list()
    },
    # Alle Kursreihen im Bewertungsstand als "asset_id<Tab>Symbol" - auch ohne Zeitleiste, ein Aufruf fuer alle Assets (#493).
    valued_series = function() {
      value <- run("series", list())
      if (!is.list(value) || !identical(value$contract_version, "asset_valuation_series_v1") || !is.list(value$series))
        data_market_timeline_abort_v1("data_market_timeline_unreadable")
      vapply(value$series, function(item) paste(as.character(item[[1L]]), as.character(item[[2L]]), sep = "\t"), character(1L))
    })
}

# Die Zeile einer frueheren Reihe traegt im Ergebnis des Sammellaufs ihr Symbol; sonst staenden zwei Zeilen mit demselben
# Assetnamen da.
data_market_timeline_row_name_v1 <- function(row) {
  if (!identical(row$series_role, "earlier")) return(row$asset_name)
  paste0(row$asset_name, " (frühere Kursreihe ", row$symbol, ")")
}

# Kurzfassung fuer die Anzeige "Historie planbar": wie viele fruehere Reihen die Zeitleiste fuehrt und welche nicht laufen koennen,
# mit Grund. Leer ohne Zeitleiste.
data_market_timeline_inventory_note_v1 <- function(rows) {
  earlier <- Filter(function(row) identical(row$series_role, "earlier"), rows)
  blocked <- Filter(function(row) !is.null(row$series_role) && !identical(row$status, "history_ready_to_plan"), rows)
  if (!length(earlier) && !length(blocked)) return("")
  ready <- sum(vapply(earlier, function(row) identical(row$status, "history_ready_to_plan"), logical(1L)))
  names <- vapply(utils::head(blocked, 5L), function(row) paste0(row$asset_name, " · ", row$symbol), character(1L))
  paste0(" · ", length(earlier), if (length(earlier) == 1L) " frühere Kursreihe" else " frühere Kursreihen",
         " der Bewertungs-Zeitleiste (", ready, " bewertbar)",
         if (length(blocked)) paste0(" · nicht bewertbar: ", paste(names, collapse = "; "),
           if (length(blocked) > 5L) paste0(" und ", length(blocked) - 5L, " weitere") else "") else "")
}

# Die Reihen der Zeitleiste, die nicht in den Sammellauf koennen, mit Grund - fuer die Meldung nach dem Vorbereiten.
data_market_timeline_blocked_v1 <- function(rows) {
  blocked <- Filter(function(row) !is.null(row$series_role) && !identical(row$status, "history_ready_to_plan"), rows)
  lapply(blocked, function(row) list(asset_name = row$asset_name, provider = row$provider, symbol = row$symbol,
                                     series_role = row$series_role, status = row$status, reason = row$series_reason))
}

data_market_timeline_blocked_copy_v1 <- function(blocked) {
  if (!length(blocked)) return("")
  items <- vapply(utils::head(blocked, 5L), function(row) paste0(row$asset_name, " · ", row$symbol,
    if (is.character(row$reason) && length(row$reason) == 1L && nzchar(row$reason)) paste0(" (", row$reason, ")") else ""), character(1L))
  paste0(" Kursreihen der Bewertungs-Zeitleiste nicht im Lauf: ", paste(items, collapse = "; "),
         if (length(blocked) > 5L) paste0(" und ", length(blocked) - 5L, " weitere") else "", ".")
}
