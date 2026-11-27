#!/usr/bin/env Rscript
# Demo-Portfolio (#487, rc.412): baut in ein frisch installiertes, eigenes Demo-Home den Demo-Bestand auf - offline, aus Textdateien
# (apps/demo/content: Katalog und Buchungen), ueber dieselben Kernwege wie Einrichtung und Data-App. Aufgerufen von
# `portelyra_desktop.R demo` ueber apps/shared/desktop_demo_home_v1.R (PORTELYRA_DESKTOP_HOME zeigt auf das Demo-Home, XDG_STATE_HOME auf
# dessen eigenen Zustandsordner). Ein zweiter Aufruf setzt einen unterbrochenen Aufbau fort und aendert sonst nichts.
#
# Festlegung (13.11.2026): echte Assets mit erfundenen Mengen; ohne Netz bewertet das Demo mit den Kursen der Buchungen
# (Umfang ohne Kursabruf, #567). Kursreihen werden nicht mitgeliefert (Yahoo-Weitergabe voraussichtlich unzulaessig); Yahoo laesst sich
# im Demo zuschalten. Der Steuersatz (30 %) ist erfunden. Ausgabe: eine JSON-Zeile je Schritt; Abbruch mit Status 2 und Fehlercode.
args <- commandArgs(trailingOnly = FALSE); file_arg <- sub("^--file=", "", args[grep("^--file=", args)][1L])
root <- normalizePath(file.path(dirname(file_arg), ".."), winslash = "/", mustWork = TRUE)
home <- normalizePath(Sys.getenv("PORTELYRA_DESKTOP_HOME"), winslash = "/", mustWork = TRUE)
Sys.setenv(PYTHONDONTWRITEBYTECODE = "1")
.libPaths(c(file.path(home, "library"), .libPaths()))
suppressPackageStartupMessages(library(spotcore))
# Jede Zeile sofort hinausschreiben: Der Aufrufer liest sie laufend und zeigt den Fortschritt (rc.413).
say <- function(step, ...) {
  cat(as.character(jsonlite::toJSON(c(list(step = step), list(...)), auto_unbox = TRUE, null = "null")), "\n", sep = "")
  flush(stdout())
}
fail <- function(step, code) { say(step, status = "failed", code = code); quit(save = "no", status = 2L) }
stamp <- function(offset = 0L) format(as.POSIXct(Sys.time() + offset, tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
source(file.path(root, "apps", "shared", "desktop_setup_v1.R"), local = .GlobalEnv)
desktop_setup_load_v1(root)
source(file.path(root, "apps", "data", "data_per_asset_legacy_review_adapter_v1.R"), local = .GlobalEnv)
source(file.path(root, "apps", "data", "data_asset_activity_csv_v1.R"), local = .GlobalEnv)
source(file.path(root, "apps", "data", "data_cash_coverage_editor_v1.R"), local = .GlobalEnv)
source(file.path(root, "apps", "data", "data_manual_price_service_v1.R"), local = .GlobalEnv)
source(file.path(root, "apps", "data", "data_statement_readers_v1.R"), local = .GlobalEnv)
content <- file.path(root, "apps", "demo", "content")
catalog_spec <- jsonlite::fromJSON(file.path(content, "catalog.json"), simplifyVector = FALSE)

# 1) Einrichtung wie im Dialog, mit festen Antworten: Datenraum, Portfolio, Umfang, Steuer, erster Lauf. Marktdaten aus: Bewertung mit den
#    Kursen der Buchungen (Umfang ohne Kursabruf); der Dialog setzte sie bei „Wert und Entwicklung“ an.
status <- desktop_setup_status_v1(root, home)
# Fortsetzbar: Ist die Einrichtung schon uebernommen (etwa ein unterbrochener Aufbau), geht es mit Katalog und Buchungen weiter.
if (identical(status$result$state, "applied")) say("setup", status = "kept") else {
  if (!isTRUE(status$result$needed)) fail("setup", "desktop_demo_home_not_fresh")
  # Mit Belegen (#583): „Erste Schritte“ importiert im Demo einen Beispielbeleg, dafuer braucht es den Reiter „Import“.
  answers <- list(portfolio_name = catalog_spec$portfolio$display_name, base_currency = catalog_spec$portfolio$base_currency,
                  holdings = list("equity_etf", "crypto", "cash"), bookings = list("manual", "documents"), purposes = list("performance", "tax"),
                  prices = "none", tax_rate = "30", church = "no", protection = "no")
  planned <- desktop_setup_cli_v1(root, "plan", list(answers = answers, current = desktop_setup_current_v1(home)))
  if (!identical(planned$status, "completed")) fail("setup", planned$code)
  plan <- planned$result
  plan$steps <- lapply(plan$steps, function(step) {
    if (identical(step$key, "scope")) step$configuration$modules$market_data <- FALSE
    step
  })
  results <- desktop_setup_apply_v1(root, home, plan)
  failed <- Filter(function(item) identical(item$status, "failed"), results)
  if (length(failed)) fail("setup", failed[[1L]]$code)
  marked <- desktop_setup_cli_v1(root, "mark", list(home = home, status = "applied", plan_fingerprint = plan$plan_fingerprint,
    results = lapply(results, function(item) item[intersect(names(item), c("key", "status", "code"))])))
  if (!identical(marked$status, "completed")) fail("setup", marked$code)
  say("setup", status = "applied", steps = paste(vapply(results, function(item) paste0(item$key, "=", item$status), character(1L)), collapse = " "))
}

# 2) Konten und Assets in das Portfolio der Einrichtung, wie der Katalog-Editor. Bewertung "manual" (Kurse aus den Buchungen), wie der Umfang
#    ohne Marktdaten es fuer neue Assets vorgibt; mit „Marktdaten“ im Umfang stellt Portelyra sie auf den Kursabruf um (#542).
runtime <- desktop_product_runtime_load_v1(home); ctx <- runtime$context
current <- catalog_read_v1(ctx)
portfolio <- Filter(function(row) identical(row$display_name, catalog_spec$portfolio$display_name) && identical(row$status, "active"), current$portfolios)
if (length(portfolio) != 1L) fail("catalog", "desktop_demo_portfolio_missing")
portfolio_id <- portfolio[[1L]]$portfolio_id
# Fortsetzbar: angelegt wird nur, was es unter diesem Namen noch nicht gibt. Dazu das Cash-Konto und das Cash-Asset (rc.415).
known <- function(rows) vapply(rows, function(row) as.character(row$display_name), character(1L))
for (account in c(catalog_spec$accounts, list(catalog_spec$cash$account))) if (!account$display_name %in% known(current$accounts))
  invisible(catalog_create_account_v1(ctx, account$token, portfolio_id, account$display_name, account$account_type, account$institution_label, stamp()))
for (asset in catalog_spec$assets) if (!asset$display_name %in% known(current$assets))
  invisible(catalog_create_asset_v1(ctx, asset$token, asset$display_name, asset$asset_type, asset$price_currency,
                                    as.integer(asset$quantity_scale), "manual", asset$isin, stamp()))
cash_asset <- catalog_spec$cash$asset
if (!cash_asset$display_name %in% known(current$assets))
  invisible(catalog_create_asset_v1(ctx, cash_asset$token, cash_asset$display_name, cash_asset$asset_type, cash_asset$price_currency,
                                    as.integer(cash_asset$quantity_scale), cash_asset$valuation_method, NULL, stamp()))
current <- catalog_read_v1(ctx)
say("catalog", accounts = length(current$accounts), assets = length(current$assets))

# 3) Buchungen ueber den Aktivitaeten-CSV-Import: pruefen, Zuordnung ueber die Namen, Vorschau, bestaetigt ausfuehren.
center <- new_data_asset_activity_csv_center_v1(new_data_asset_activity_csv_product_adapter_v1(root, ctx))
source_csv <- tempfile(fileext = ".csv"); on.exit(unlink(source_csv), add = TRUE)
file.copy(file.path(content, "activities.csv"), source_csv); Sys.chmod(source_csv, "0400")
inspection <- data_asset_activity_csv_inspect_v1(center, ctx, source_csv, portfolio_id)
csv_plan <- data_asset_activity_csv_prepare_v1(center, ctx, data_asset_activity_csv_default_mapping_v1(inspection), stamp())
if (identical(csv_plan$status, "ready_for_confirmation")) {
  issued <- stamp()
  imported <- data_asset_activity_csv_execute_v1(center, ctx, TRUE, issued, stamp(600L))
  say("activities", status = imported$status, created = imported$created_event_count)
} else if (identical(csv_plan$status, "nothing_to_import")) {
  say("activities", status = "unchanged")
} else fail("activities", if (is.character(csv_plan$code)) csv_plan$code else "desktop_demo_activities_blocked")

# 3a) Eigene Kursangaben (rc.439): Ohne Kursanbieter bewertet das Demo mit dem Kurs
#     der juengsten Buchung; Einzelwerte ohne regelmaessige Kaeufe sprangen am naechsten Kauftag um Jahre an Kursbewegung. prices.csv traegt
#     fuer sie erfundene Werte (Kaufkurs am Kauftag, dazwischen je Quartalsende eingeschoben, dev/demo_home/make_demo_prices.py), keine
#     Kursreihe eines Anbieters (deren Weitergabe erlauben die Bedingungen in der Regel nicht). Sie koennen von echten Kursen abweichen;
#     Handbuch und Einrichtungsdialog sagen das. Vorrang: Gibt es eine eigene Kursangabe, gilt sie vor dem Buchungskurs - eine
#     Uebungsbuchung bewegt den Kurs dieser vier Assets nicht. Ueber den Dienst der Karte in Data, bestaetigt. Fortsetzbar: Eingetragenes
#     wird uebersprungen.
price_rows <- utils::read.csv(file.path(content, "prices.csv"), colClasses = "character", stringsAsFactors = FALSE)
if (nrow(price_rows)) {
  price_service <- new_data_manual_price_service_v1(root, ctx)
  asset_of <- function(name) {
    hit <- Filter(function(row) identical(as.character(row$display_name), name), current$assets)
    spec <- Filter(function(asset) identical(asset$display_name, name), catalog_spec$assets)
    if (length(hit) != 1L || length(spec) != 1L) fail("prices", "desktop_demo_prices_asset_missing")
    list(id = as.character(hit[[1L]]$asset_id), currency = spec[[1L]]$price_currency)
  }
  price_count <- 0L
  for (name in unique(price_rows$asset_key)) {
    asset <- asset_of(name)
    have <- vapply(price_service$read(asset$id)$entries, function(row) as.character(row$price_date), character(1L))
    for (index in which(price_rows$asset_key == name)) if (!price_rows$price_date[[index]] %in% have) {
      invisible(price_service$append(asset$id, price_rows$price_date[[index]], price_rows$value_decimal[[index]], asset$currency, stamp(), TRUE))
      price_count <- price_count + 1L
    }
  }
  say("prices", status = if (price_count) "completed" else "unchanged", entries = price_count)
}

# 3a') Leser fuer den Beispielbeleg (rc.440, Endabnahme 19.11.2026): Neue Portfolios beginnen ohne aktive Plugins; „Erste Schritte“ liest den
#     erfundenen Export im Format von Trade Republic ein. Das Demo aktiviert dieses Plugin deshalb fuer sein Portfolio - ueber denselben Dienst
#     wie die Karte „Aktivierung je Portfolio“, mit Vorschau und Bestaetigung. Ist es schon aktiv, aendert sich nichts.
reader_service <- new_data_statement_readers_service_v1(root, ctx)
reader_state <- reader_service$activation()
reader_plugin <- Filter(function(plugin) identical(plugin$plugin_id, "trade_republic"), reader_state$plugins)
if (length(reader_plugin) != 1L) fail("readers", "desktop_demo_readers_plugin_missing")
already <- Filter(function(state) identical(state$portfolio_id, portfolio_id) && isTRUE(state$active), reader_plugin[[1L]]$states)
if (length(already)) say("readers", status = "unchanged") else {
  changes <- list(list(portfolio_id = portfolio_id, plugin_id = "trade_republic", active = TRUE))
  preview <- reader_service$activation_preview(changes)
  applied <- reader_service$activation_apply(changes, preview$preview_fingerprint, stamp(), TRUE)
  say("readers", status = "completed", activated = "trade_republic", written = applied$written_count)
}

# 3b) Cash (rc.415, Festlegung 14.11.2026): das Demo-Tagesgeld ueber „Cash von Hand“, wie die Karte in Data - Vorschau, Bestaetigung,
#     Schreiben. Der Zeit nach: Ein Pruef-Saldo hebt den Zeitraum auf „abgestimmt“, danach gehen nur Buchungen nach dem gepruefften Tag.
#     Fortsetzbar: Gebuchtes (Tag, Art, Betrag) und Abgestimmtes (bis zum juengsten Pruef-Tag) wird uebersprungen.
cash_rows <- utils::read.csv(file.path(content, "cash.csv"), colClasses = "character", stringsAsFactors = FALSE)
cash_editor <- new_data_cash_coverage_editor_v1(new_data_cash_coverage_product_adapter_v1(root, ctx))
cash_catalog <- data_cash_coverage_editor_refresh_v1(cash_editor, ctx)
pick <- function(rows, label) { hit <- Filter(function(row) identical(row$label, label), rows); if (length(hit) != 1L) fail("cash", "desktop_demo_cash_catalog_missing"); hit[[1L]]$ref }
cash_account_ref <- pick(cash_catalog$accounts, catalog_spec$cash$account$display_name)
cash_asset_ref <- pick(cash_catalog$cash_assets, cash_asset$display_name)
cash_view <- data_cash_coverage_editor_read_view_v1(cash_editor, ctx)
amount_key <- function(value) formatC(as.numeric(value), format = "f", digits = 2)
mine <- Filter(function(row) identical(row$account_label, catalog_spec$cash$account$display_name), cash_view$cash_history)
booked <- vapply(mine, function(row) paste(row$local_date, row$event_type, amount_key(row$amount_decimal)), character(1L))
checked_through <- suppressWarnings(max(c("", vapply(cash_view$periods, function(row) if (is.character(row$as_of_date)) row$as_of_date else "", character(1L)))))
cash_counts <- c(bookings = 0L, check_balances = 0L)
for (index in seq_len(nrow(cash_rows))) {
  row <- cash_rows[index, ]
  if (identical(row$kind, "check_balance")) {
    if (nzchar(checked_through) && row$local_date <= checked_through) next
    prepared <- data_cash_coverage_editor_prepare_check_balance_v1(cash_editor, ctx, list(account_ref = cash_account_ref, cash_asset_ref = cash_asset_ref,
      as_of_date = row$local_date, observed_balance_decimal = row$amount_decimal, evidence_kind = "owner_sighted", evidence_fingerprint = ""), stamp())
    if (!identical(prepared$status, "pending_confirmation")) fail("cash", paste0("desktop_demo_cash_", prepared$status))
    invisible(data_cash_coverage_editor_confirm_v1(cash_editor, ctx, prepared$preview_ref, stamp()))
    invisible(data_cash_coverage_editor_execute_v1(cash_editor, ctx, prepared$preview_ref, stamp()))
    cash_counts[["check_balances"]] <- cash_counts[["check_balances"]] + 1L
  } else {
    if (paste(row$local_date, if (identical(row$kind, "withdrawal")) "withdrawal" else "deposit", amount_key(row$amount_decimal)) %in% booked) next
    prepared <- data_cash_coverage_editor_prepare_booking_v1(cash_editor, ctx, list(account_ref = cash_account_ref, cash_asset_ref = cash_asset_ref,
      local_date = row$local_date, kind = row$kind, amount_decimal = row$amount_decimal), stamp())
    if (!identical(prepared$status, "pending_confirmation")) fail("cash", paste0("desktop_demo_cash_", prepared$status))
    invisible(data_cash_coverage_editor_confirm_booking_v1(cash_editor, ctx, prepared$preview_ref, stamp()))
    invisible(data_cash_coverage_editor_execute_booking_v1(cash_editor, ctx, prepared$preview_ref, stamp()))
    cash_counts[["bookings"]] <- cash_counts[["bookings"]] + 1L
  }
}
say("cash", status = if (sum(cash_counts)) "completed" else "unchanged", bookings = cash_counts[["bookings"]], check_balances = cash_counts[["check_balances"]])

# 4) Einmal „Alles aktualisieren“, offline (ohne Marktdaten): FIFO, Tageshistorie, Snapshot, Abschluss.
runner <- file.path(root, "scripts", "desktop_refresh_all.R")
out <- suppressWarnings(system2(file.path(R.home("bin"), "Rscript"), c(shQuote(runner), "--home", shQuote(home), "--run-id", "auto", "--origin", "app",
  "--retry-gaps", "no", "--confirm", "RUN_REFRESH_ALL"), stdout = TRUE, stderr = FALSE, env = "PYTHONDONTWRITEBYTECODE=1"))
finished <- tryCatch(jsonlite::fromJSON(utils::tail(out, 1L), simplifyVector = FALSE), error = function(error) NULL)
if (!is.list(finished) || !identical(finished$status, "finished")) fail("refresh", "desktop_demo_refresh_failed")
# Ein Lauf, der an einem Schritt anhielt, ist fuer das Demo kein fertiger Stand: Der Aufbau gilt dann als nicht durchgelaufen.
if (identical(finished$tone, "error")) fail("refresh", "desktop_demo_refresh_halted")
say("refresh", status = "finished", tone = finished$tone)
say("demo", status = "ready")
