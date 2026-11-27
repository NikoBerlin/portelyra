#!/usr/bin/env Rscript
# Yahoo im Demo (#487, rc.414): schaltet im fertig aufgebauten Demo-Home Kurse von Yahoo Finance ein - ueber dieselben Wege wie ein
# Nutzer in der Data-App. Aufgerufen von `portelyra_desktop.R demo --prices yahoo` ueber apps/shared/desktop_demo_home_v1.R, erst nachdem
# der Nutzer die Hinweise und Bedingungen des Anbieters zur Kenntnis genommen hat (wie die Frage „Kurse“ der Einrichtung).
#
# Eine spaete Buchung ergaenzen und Yahoo einschalten. Ablauf:
#   1. Kursanbieter Yahoo aktivieren (Karte „Kursanbieter“: Vorschau, Uebernehmen).
#   2. Je Asset: Bewertungsart Marktdaten (Katalogbefehl wie „Bewertung ueber die Zeit“, ganze Historie), Kurszuordnung anlegen und
#      „Jetzt einrichten“ (Testabruf, Listing-Freigabe, Verifizierung). Scheitert das, geht das Asset zurueck auf „eigene Kurse“ - es
#      bewertet dann weiter mit den Kursen seiner Buchungen. Scheitert schon das erste Asset, gilt Yahoo als nicht erreichbar.
#   3. Wechselkurs-Paar fuer Kurse in Fremdwaehrung (Apple in USD); ohne Paar geht das Asset ebenfalls zurueck.
#   4. Umfang: Baustein „Marktdaten“ an.  5. „Alles aktualisieren“ mit Kursabruf.
# Das Demo bleibt in jedem Schritt vollstaendig. Ein zweiter Lauf setzt fort: Gepruefte Zuordnungen bleiben, zurueckgestellte Assets
# werden erneut versucht. Ausgabe: eine JSON-Zeile je Schritt, zuletzt {"step":"market","status":"active"|"partial"|"unreachable"}.
args <- commandArgs(trailingOnly = FALSE); file_arg <- sub("^--file=", "", args[grep("^--file=", args)][1L])
root <- normalizePath(file.path(dirname(file_arg), ".."), winslash = "/", mustWork = TRUE)
home <- normalizePath(Sys.getenv("PORTELYRA_DESKTOP_HOME"), winslash = "/", mustWork = TRUE)
Sys.setenv(PYTHONDONTWRITEBYTECODE = "1")
.libPaths(c(file.path(home, "library"), .libPaths()))
suppressPackageStartupMessages({ library(shiny); library(spotcore) })
# Wie die Data-App: interne Helfer des Kerns liegen im globalen Umfeld.
for (file in c("runtime_context.R", "canonical_repository.R", "catalog_data_command.R", "desktop_product_runtime_v1.R"))
  source(file.path(root, "packages", "spotcore", "R", file), local = .GlobalEnv)
`%||%` <- function(a, b) if (is.null(a)) b else a
say <- function(step, ...) {
  cat(as.character(jsonlite::toJSON(c(list(step = step), list(...)), auto_unbox = TRUE, null = "null")), "\n", sep = "")
  flush(stdout())
}
fail <- function(step, code) { say(step, status = "failed", code = code); quit(save = "no", status = 2L) }
stamp <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")

catalog_spec <- jsonlite::fromJSON(file.path(root, "apps", "demo", "content", "catalog.json"), simplifyVector = FALSE)
runtime <- desktop_product_runtime_load_v1(home)
space <- runtime_data_space_path(runtime$context)
current <- catalog_read_v1(runtime$context)
portfolio <- Filter(function(row) identical(row$display_name, catalog_spec$portfolio$display_name) && identical(row$status, "active"), current$portfolios)
if (length(portfolio) != 1L) fail("market", "desktop_demo_portfolio_missing")
portfolio_id <- portfolio[[1L]]$portfolio_id

options(portelyra.desktop.project_root = root, portelyra.desktop.runtime = runtime)
app_env <- new.env(parent = globalenv())
invisible(source(file.path(root, "apps", "data", "desktop_product_app_v1.R"), local = app_env, chdir = TRUE))
# Innerhalb von testServer sieht der Code die Variablen des App-Servers zuerst: eigene Namen deshalb eindeutig (die Data-App kennt etwa
# `state`, `stamp` und `portfolio_id`).
demo_market <- new.env(parent = emptyenv()); demo_market$verified <- character(); demo_market$reverted <- character(); demo_market$code <- NULL
safe_code <- function(error) tryCatch(spotcore::desktop_product_safe_error_code_v1(error), error = function(e) "desktop_demo_market_failed")

shiny::testServer(app_env$server, {
  # Als Funktion, damit ein Abbruch mit return() moeglich ist; sie sieht die Dienste des App-Servers.
  demo_market_run <- function() {
  session$setInputs(asset_center_mode = "existing"); session$flushReact()
  # 1) Kursanbieter Yahoo, wie in der Karte „Kursanbieter“ - die Kenntnisnahme kam vom Aufrufer.
  activated <- tryCatch({
    overview <- price_providers_service$overview()
    yahoo <- Filter(function(row) identical(row$provider_id, "yahoo"), overview$providers)
    if (!length(yahoo) || !isTRUE(yahoo[[1L]]$active)) invisible(price_providers_service$apply(price_providers_service$preview("yahoo", TRUE), TRUE))
    TRUE
  }, error = function(error) { demo_market$code <- safe_code(error); FALSE })
  say("price_provider", status = if (activated) "active" else "failed", code = if (activated) NULL else demo_market$code)
  if (!activated) return(invisible(NULL))

  refresh_core <- function() app_env$desktop_catalog_editor_refresh_v1(asset_center_catalog_editor, runtime$context)
  revise <- function(ref, method) {
    refresh_core()
    form <- list(action = "revise_valuation_method", entity_type = "asset", entity_ref = ref, portfolio_ref = "", display_name = "",
                 base_currency = "EUR", account_type = "securities", institution_label = "", asset_type = "other", price_currency = "EUR",
                 quantity_scale = "0", valuation_method = method, isin = "")
    prepared <- app_env$desktop_catalog_editor_prepare_v1(asset_center_catalog_editor, runtime$context, form, now_utc())
    invisible(app_env$desktop_catalog_editor_execute_v1(asset_center_catalog_editor, runtime$context, prepared, TRUE))
    refresh_core()
  }
  core <- refresh_core()
  refs <- stats::setNames(vapply(core$assets, `[[`, character(1L), "ref"), vapply(core$assets, `[[`, character(1L), "display_name"))
  method_of <- function(ref) asset_center_catalog_editor$catalog$maps$asset[[ref]]$valuation_method
  back <- function(ref, name) {
    if (!identical(method_of(ref), "manual")) tryCatch(revise(ref, "manual"), error = function(error) NULL)
    demo_market$reverted <- unique(c(demo_market$reverted, name))
  }

  # 2) Je Asset: Marktdaten, Kurszuordnung, „Jetzt einrichten“. Rueckweg bei jedem Fehlschlag.
  for (asset in catalog_spec$assets) {
    ref <- refs[[asset$display_name]]
    if (is.null(ref)) next
    outcome <- tryCatch({
      if (!identical(method_of(ref), "external_market")) revise(ref, "external_market")
      session$setInputs(asset_center_asset = ref); session$flushReact()
      invisible(asset_center_refresh(ref))
      same <- function(a, b) length(a) == 1L && length(b) == 1L && isTRUE(as.character(unname(a)) == as.character(unname(b)))
      mapping_of <- function() {
        id <- asset_center_selected_id()
        names(Filter(function(row) same(row$asset_id, id) && same(row$capability, "daily_history") && same(row$provider_id, "yahoo"),
                     asset_center_provider_editor$state$mapping_map))
      }
      mapping_ref <- mapping_of()
      if (!length(mapping_ref)) {
        session$setInputs(asset_center_provider_action = "create", asset_center_mapping = "", asset_center_provider_capability = "daily_history",
                          asset_center_provider_id = "yahoo", asset_center_provider_symbol = asset$provider_symbol, asset_center_provider_exchange = "",
                          asset_center_provider_mic = "", asset_center_provider_currency = asset$provider_currency, asset_center_provider_expert = FALSE)
        session$flushReact()
        preview <- app_env$data_provider_mapping_editor_prepare_v1(asset_center_provider_editor, runtime$context, asset_center_provider_form(), now_utc())
        invisible(app_env$data_provider_mapping_editor_execute_v1(asset_center_provider_editor, runtime$context, preview, TRUE))
        invisible(asset_center_refresh(ref))
        mapping_ref <- mapping_of()
      }
      row <- asset_center_provider_editor$state$mapping_map[[mapping_ref[[1L]]]]
      if (identical(row$verification_status, "verified")) list(status = "completed", already = TRUE) else {
        session$setInputs(asset_center_mapping = mapping_ref[[1L]], asset_center_probe_start = format(Sys.Date() - 14L),
                          asset_center_probe_end = format(Sys.Date() - 1L), asset_center_listing_market = "")
        session$flushReact()
        asset_center_setup_run()
      }
    }, error = function(error) list(status = "failed", code = safe_code(error), step = "Einrichten", detail = conditionMessage(error)))
    if (identical(outcome$status, "completed")) {
      demo_market$verified <- c(demo_market$verified, asset$display_name)
      say("market_setup", asset = asset$display_name, status = if (isTRUE(outcome$already)) "already_verified" else "completed")
      next
    }
    back(ref, asset$display_name)
    demo_market$code <- outcome$code %||% "desktop_demo_market_failed"
    say("market_setup", asset = asset$display_name, status = "reverted", at = outcome$step %||% NULL, code = demo_market$code,
        detail = if (is.character(outcome$detail) && grepl("^[a-z][a-z0-9_]{2,80}$", outcome$detail)) outcome$detail else NULL)
    # Scheitert schon das erste Asset, ist die Quelle nicht erreichbar: keine weiteren Versuche, alles bleibt bei den Buchungskursen.
    if (!length(demo_market$verified)) {
      for (other in catalog_spec$assets) if (!is.null(refs[[other$display_name]]) && !identical(other$display_name, asset$display_name) &&
                                             identical(method_of(refs[[other$display_name]]), "external_market")) back(refs[[other$display_name]], other$display_name)
      return(invisible(NULL))
    }
  }

  # 3) Wechselkurs-Paare fuer Kurse in Fremdwaehrung (wie unter Marktdaten → Wechselkurse). Ohne Paar keine Bewertung in EUR: zurueck.
  verified_specs <- Filter(function(asset) asset$display_name %in% demo_market$verified, catalog_spec$assets)
  for (currency in setdiff(unique(vapply(verified_specs, `[[`, character(1L), "provider_currency")), "EUR")) {
    paired <- tryCatch({
      present <- tryCatch({ invisible(asset_center_fx_history_service$plan(currency, "EUR", format(Sys.Date() - 7L), format(Sys.Date() - 1L))); TRUE },
                          error = function(error) if (grepl("pair_missing", conditionMessage(error), fixed = TRUE)) FALSE else stop(error))
      if (!present) {
        candidate <- list(symbol = paste0(currency, "EUR=X"), display_name = paste0(currency, "/EUR"), exchange = "CCY", quote_type = "currency",
                          quote_currency = "EUR")
        probe_preview <- asset_center_fx_probe_service$preview(candidate, currency, "EUR", "direct", format(Sys.Date() - 14L), format(Sys.Date() - 1L), now_utc())
        probe <- asset_center_fx_probe_service$execute(probe_preview, TRUE)
        promotion_preview <- asset_center_fx_promotion_service$preview(asset_center_fx_probe_service$resolve_result(probe$result_ref), now_utc())
        invisible(asset_center_fx_promotion_service$publish(promotion_preview, TRUE, now_utc()))
        asset_center_fx_history_service$invalidate()
      }
      TRUE
    }, error = function(error) { demo_market$code <- safe_code(error); FALSE })
    say("fx_pair", pair = paste0(currency, "/EUR"), status = if (paired) "ready" else "failed", code = if (paired) NULL else demo_market$code)
    if (!paired) for (asset in Filter(function(item) identical(item$provider_currency, currency), verified_specs)) {
      back(refs[[asset$display_name]], asset$display_name)
      demo_market$verified <- setdiff(demo_market$verified, asset$display_name)
      say("market_setup", asset = asset$display_name, status = "reverted", at = "Wechselkurs", code = demo_market$code)
    }
  }
  }
  demo_market_run()
})

total <- length(catalog_spec$assets)
if (!length(demo_market$verified)) {
  say("market", status = "unreachable", verified = 0L, total = total, code = demo_market$code)
  quit(save = "no", status = 0L)
}

# 4) Umfang: Baustein „Marktdaten“ an - ueber Vorschau und Bestaetigung wie in den Einstellungen.
python <- function(command, payload) {
  input <- tempfile(); on.exit(unlink(input), add = TRUE)
  writeLines(as.character(jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null")), input, useBytes = TRUE)
  out <- suppressWarnings(system2("python3", c("-B", "-E", "-s", file.path(root, "scripts", "desktop_portfolio_configuration.py"), command),
                                  stdin = input, stdout = TRUE, stderr = FALSE))
  tryCatch(jsonlite::fromJSON(paste(out, collapse = ""), simplifyVector = FALSE), error = function(error) list(status = "blocked", code = "desktop_demo_market_failed"))
}
ctx <- list(tenant_id = runtime$context$tenant_id, user_id = runtime$context$user_id, data_space_id = runtime$context$data_space_id,
            actor_id = "desktop_owner", role = "desktop_owner")
read <- python("read", list(context = ctx, data_space_path = space))
entries <- if (identical(read$status, "completed")) Filter(function(row) identical(row$portfolio_id, portfolio_id), read$result$portfolios) else list()
if (length(entries) != 1L) fail("configuration", read$code %||% "desktop_demo_market_failed")
configuration <- entries[[1L]]$configuration
if (!isTRUE(configuration$modules$market_data)) {
  configuration$modules$market_data <- TRUE
  preview <- python("preview", list(context = ctx, data_space_path = space, portfolio_id = portfolio_id, configuration = configuration, origin = "owner"))
  if (!identical(preview$status, "completed")) fail("configuration", preview$code %||% "desktop_demo_market_failed")
  applied <- python("apply", list(context = ctx, data_space_path = space, preview = preview$result, confirmed = TRUE))
  if (!identical(applied$status, "completed")) fail("configuration", applied$code %||% "desktop_demo_market_failed")
}
say("configuration", status = "market_data_on")

# 5) „Alles aktualisieren“ mit Kursabruf: die ganze Kurshistorie ab der ersten Buchung, dann Verlauf, Snapshot und Abschluss neu.
out <- suppressWarnings(system2(file.path(R.home("bin"), "Rscript"), c(shQuote(file.path(root, "scripts", "desktop_refresh_all.R")), "--home", shQuote(home),
  "--run-id", "auto", "--origin", "app", "--retry-gaps", "yes", "--confirm", "RUN_REFRESH_ALL"), stdout = TRUE, stderr = FALSE,
  env = "PYTHONDONTWRITEBYTECODE=1"))
finished <- tryCatch(jsonlite::fromJSON(utils::tail(out, 1L), simplifyVector = FALSE), error = function(error) NULL)
say("refresh_market", status = if (is.list(finished)) finished$status %||% "unknown" else "failed", tone = if (is.list(finished)) finished$tone %||% NULL else NULL)
say("market", status = if (length(demo_market$verified) == total) "active" else "partial", verified = length(demo_market$verified), total = total,
    reverted = if (length(setdiff(demo_market$reverted, demo_market$verified))) as.list(setdiff(demo_market$reverted, demo_market$verified)) else NULL)
