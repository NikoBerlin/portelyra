# Die Bausteine von „Alles aktualisieren“ ohne Shiny-Sitzung (rc.315, #510), fuer den Hintergrundlauf
# (scripts/desktop_refresh_all.R). Dieselben Dienste und dieselbe Kurskette wie in der Data-App (data_market_chain_v1.R);
# statt der Oberflaeche halten hier einfache Variablen den zuletzt gelesenen Stand von Stammdaten, Zuordnungen und Buchungen.
# Was in der App nur die Seite auffrischte (Listen, Auswahlfelder, Abschlussanzeige), entfaellt. Die Vorgaben der App gelten:
# Zeitraum ab erster Buchung bis gestern, Beginn sonst 01.01.2019 wie im Reiter Marktdaten.

# Die Dateien, die der Hintergrundlauf laedt: genau die, die die Data-App laedt - gelesen aus deren Kopf. Eine feste Liste lief
# beim ersten Versuch auseinander: Es fehlten interne Teile von spotcore (Abdruecke der Kurszuordnung) und die Bindung
# an den Buchungsbestand; der Kern rechnete dann ohne Buchungen (24.10.2026).
data_refresh_all_sources_v1 <- function(project_root) {
  app <- readLines(file.path(project_root, "apps", "data", "desktop_product_app_v1.R"), warn = FALSE, encoding = "UTF-8")
  lines <- grep('^source\\(file.path\\(project_root, "[^)]*\\), local = TRUE\\)$', app, value = TRUE)
  files <- vapply(lines, function(line) paste(gsub('"', "", regmatches(line, gregexpr('"[^"]+"', line))[[1L]]), collapse = "/"),
                  character(1L), USE.NAMES = FALSE)
  if (length(files) < 20L || !all(file.exists(file.path(project_root, files)))) stop("refresh_all_sources_invalid", call. = FALSE)
  files
}
DATA_REFRESH_ALL_DEFAULT_START_V1 <- "2019-01-01"

# data_refresh_all_modules_v1 steht seit rc.406 in data_refresh_all_v1.R: Auch die Data-App liest den Umfang (Statuszeile des Abschlusses).

data_refresh_all_deps_v1 <- function(project_root, runtime) {
  ctx <- runtime$context
  now_utc <- function() format(as.POSIXct(Sys.time(), tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  add_seconds <- function(value, seconds) {
    parsed <- as.POSIXct(value, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
    format(parsed + seconds, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
  }
  catalog_editor <- new_desktop_catalog_editor_v1()
  price_provider_operations <- data_price_provider_operations_v1(project_root)
  provider_editor <- new_data_provider_mapping_editor_v1(
    history_providers = data_price_providers_with_v1(price_provider_operations, "daily_history"),
    quote_providers = data_price_providers_with_v1(price_provider_operations, "quote"))
  activity_editor <- new_data_asset_activity_editor_v1(new_data_asset_activity_product_adapter_v1(project_root, ctx))
  realized_adapter <- new_data_realized_state_product_adapter_v2(project_root, ctx)
  snapshot <- new_data_portfolio_snapshot_service_v1(project_root, ctx)
  intraday <- tryCatch(new_data_intraday_snapshot_service_v1(project_root, ctx), error = function(error) NULL)
  user_settings <- tryCatch(new_data_user_settings_service_v1(project_root, ctx), error = function(error) NULL)
  run_center <- spotcore::new_desktop_run_center_v1()
  per_asset_product_adapter <- tryCatch(new_data_per_asset_legacy_review_product_adapter_v1(project_root, ctx,
    new_data_per_asset_legacy_review_fixture_adapter_if_available_v1(project_root, ctx)), error = function(error) NULL)
  republication_adapter <- tryCatch(new_data_asset_activity_republication_adapter_v1(project_root, ctx), error = function(error) NULL)
  services <- list(
    market_review = new_data_market_history_review_service_v1(project_root, ctx), market_plan = new_data_market_history_plan_service_v1(project_root, ctx),
    market_coverage = new_data_market_history_coverage_service_v1(project_root, ctx), fx_history = new_data_fx_history_review_service_v1(project_root, ctx),
    fx_coverage = new_data_fx_demand_coverage_service_v1(project_root, ctx), calendar_gap = new_data_market_calendar_gap_service_v1(project_root, ctx),
    calendar_review = new_data_calendar_gap_review_service_v1(project_root, ctx), valuation = new_data_market_valuation_service_v1(project_root, ctx),
    promotion = new_data_provider_promotion_service_v1(project_root, ctx), catalog_editor = catalog_editor, provider_editor = provider_editor)
  held <- new.env(parent = emptyenv())
  held$core <- NULL; held$providers <- NULL; held$activity_view <- NULL; held$activity_catalog <- NULL; held$run_catalog <- NULL
  # Wie asset_center_refresh in der App, ohne Auswahlfelder: Stammdaten und Zuordnungen muessen zueinander passen.
  refresh_catalog <- function() {
    held$core <- desktop_catalog_editor_refresh_v1(catalog_editor, ctx)
    held$providers <- data_provider_mapping_editor_refresh_v1(provider_editor, ctx)
    if (!identical(catalog_editor$catalog$catalog_fingerprint, provider_editor$state$catalog_fingerprint)) stop("asset_center_catalog_changed", call. = FALSE)
    invisible(NULL)
  }
  # Wie refresh_activity_catalog in der App, ohne Formularfelder.
  refresh_activity <- function() {
    held$activity_view <- data_asset_activity_editor_read_view_v1(activity_editor, ctx)
    held$activity_catalog <- data_asset_activity_editor_refresh_v1(activity_editor, ctx)
    invisible(NULL)
  }
  # Wie asset_center_first_booking und activity_ref_for_center in der App.
  first_booking <- function(asset_ref) {
    if (is.null(asset_ref) || !length(asset_ref) || !nzchar(asset_ref)) return(NULL)
    activity_ref <- tryCatch(data_asset_activity_editor_ref_for_internal_v1(activity_editor, ctx, "asset",
      desktop_catalog_editor_internal_identity_v1(catalog_editor, ctx, "asset", asset_ref)), error = function(error) "")
    if (!is.character(activity_ref) || length(activity_ref) != 1L || !nzchar(activity_ref)) return(NULL)
    projection <- tryCatch(if (is.null(held$activity_view) || is.null(held$activity_catalog)) NULL else
      asset_selection_context_project_activity_v3(held$activity_catalog, held$activity_view, scope_mode = "all"), error = function(error) NULL)
    if (is.null(projection)) return(NULL)
    dates <- character(0)
    for (portfolio in projection$portfolios) for (row in portfolio$events_newest_first)
      if (identical(row$asset_ref, activity_ref) && is.character(row$local_date) && length(row$local_date) == 1L) dates <- c(dates, row$local_date)
    if (!length(dates)) NULL else min(dates)
  }
  # Bewertungs-Zeitleiste (rc.393): wie in der App jede Kursreihe der Zeitleiste, eine fruehere nur in ihrem Abschnitt.
  timeline_reader <- new_data_market_timeline_reader_v1(project_root, ctx)
  chain <- new_data_market_chain_v1(services, lookups = list(catalog = function() held$core, providers = function() held$providers,
    first_booking = first_booking, now_utc = now_utc, invalidate_valuation = function() services$valuation$invalidate(),
    timeline = timeline_reader$overview, timeline_coverage = timeline_reader$coverage,
    valued_series = timeline_reader$valued_series), context = ctx)
  sweep <- new_data_market_sweep_state_v1()
  start_sweep <- function(queue, period) {
    chain$sweep_reset(sweep)
    sweep$queue <- queue; sweep$period <- period; sweep$prepared <- TRUE
    if (length(queue)) { sweep$running <- TRUE; sweep$resume_at <- NULL }
    invisible(NULL)
  }
  # Wie run_semantic_binding in der App: Hat sich der Stammdatenstand seit der letzten Buchung geaendert, wird der Buchungsbestand
  # angeglichen (ohne Buchung) und der FIFO-Stand fortgeschrieben; abgewiesen wird nur, wenn das nicht gelingt.
  semantic_binding <- function() {
    read_binding <- function() if (is.null(per_asset_product_adapter)) NULL else tryCatch(per_asset_product_adapter$product_binding(ctx), error = function(error) NULL)
    binding <- read_binding(); aligned <- FALSE
    if (is.list(binding) && identical(binding$status, "available") && !identical(binding$canonical_fingerprint,
        digest::digest(file = spotcore::runtime_canonical_path(ctx), algo = "sha256", serialize = FALSE))) {
      outcome <- if (is.null(republication_adapter)) simpleError("per_asset_review_adapter_failed") else
        tryCatch(republication_adapter$republish(ctx, now_utc()), error = function(error) error)
      if (inherits(outcome, "error")) return(list(status = "failed", copy = data_run_plan_alignment_failure_text_v1(
        tryCatch(spotcore::desktop_product_safe_error_code_v1(outcome), error = function(error) "desktop_product_boundary_failed"))))
      aligned <- identical(outcome$status, "republished")
      binding <- read_binding()
      tryCatch(refresh_activity(), error = function(error) NULL)
      tryCatch(invisible(realized_adapter$materialize(ctx, "incremental", now_utc(), "incomplete_quarantined_or_derivative_blocked")), error = function(error) NULL)
    }
    list(status = "ready", aligned = aligned, binding = if (!is.list(binding) || !identical(binding$status, "available")) NULL else
      binding[c("status", "ledger_path", "ledger_fingerprint", "canonical_fingerprint", "semantic_contracts")])
  }
  list(
    today = function() format(Sys.Date(), "%Y-%m-%d"),
    # Umfang je Portfolio (#542, rc.395): die wirksamen Bausteine; nicht lesbar -> NULL, dann laeuft alles wie bisher.
    modules = function() data_refresh_all_modules_v1(project_root, ctx),
    stands = function(as_of) snapshot$stands(as_of),
    # Noch kein Buchungsbestand (#565): Die Bindung ist "absent". Nicht lesbar -> FALSE, dann laeuft alles wie bisher.
    bookings_absent = function() {
      binding <- if (is.null(per_asset_product_adapter)) NULL else tryCatch(per_asset_product_adapter$product_binding(ctx), error = function(error) NULL)
      is.list(binding) && identical(binding$status, "absent")
    },
    fifo_check = function() realized_adapter$read(ctx),
    fifo_update = function() {
      value <- realized_adapter$materialize(ctx, "incremental", now_utc(), "incomplete_quarantined_or_derivative_blocked")
      tryCatch(refresh_activity(), error = function(error) NULL)
      value
    },
    # Sammellauf im Reiter Marktdaten und offener Bewertungsentwurf: Beide prueft die Data-App vor dem Start; ein Sammellauf dort
    # haelt dieselbe Sperre (data_refresh_all_store_v1).
    # Ein Datenbestand an fremdem Ort ohne Bindung (#556): mit genauem Grund anhalten statt an den Sperren der Speicher zu scheitern.
    prices_blocked = function() data_relocation_blocked_copy_v1(data_relocation_status_v1(project_root, runtime_data_space_path(ctx))),
    prices_prepare = function() {
      refresh_catalog(); refresh_activity()
      period <- list(mode = "from_first_trade", end = as.character(Sys.Date() - 1L), start = DATA_REFRESH_ALL_DEFAULT_START_V1)
      prepared <- chain$sweep_queue(TRUE, period)
      start_sweep(prepared$ready, period)
      list(count = length(prepared$ready), complete = prepared$complete, excluded = prepared$excluded,
           timeline_blocked = prepared$timeline_blocked)
    },
    prices_progress = function() {
      chain$sweep_tick(sweep)
      list(running = isTRUE(sweep$running), total = length(sweep$queue), results = sweep$results, resume_at = sweep$resume_at)
    },
    prices_stop = function() { sweep$running <- FALSE; sweep$resume_at <- NULL },
    prices_reason = function(row) {
      why <- if (!is.null(row$reason)) as.character(row$reason) else chain$fetch_reason(row$code)
      if (length(why) == 1L && nzchar(why)) why else paste("Fehlercode", as.character(row$code))
    },
    history_update = function() snapshot$history_update(now_utc(), FALSE, format(Sys.Date() - 1L, "%Y-%m-%d")),
    history_publish = function() snapshot$history_publish(now_utc()),
    history_read = function() snapshot$history_read("", ""),
    after_history = function() invisible(NULL),
    snapshot_plan = function(day) snapshot$plan(day, now_utc()),
    snapshot_publish = function(plan) snapshot$publish(plan$as_of_date, plan$plan_fingerprint, TRUE, now_utc()),
    moment_fetch = function() {
      if (is.null(intraday)) stop("data_intraday_snapshot_service_invalid", call. = FALSE)
      intraday$snapshot(TRUE, now_utc())
    },
    moment_publish = function() snapshot$intraday_publish(format(Sys.Date(), "%Y-%m-%d"), now_utc()),
    basis_publish = function(run_center_inputs) snapshot$basis_publish(format(Sys.Date(), "%Y-%m-%d"), now_utc(), run_center_inputs),
    now_utc = now_utc,
    durations_read = function() if (is.null(user_settings)) list() else user_settings$durations_read(),
    durations_record = function(values) if (!is.null(user_settings)) user_settings$durations_record(values, now_utc()),
    gaps_prepare = function(window) {
      found <- snapshot$recent_gaps(window$start, window$end)
      ids <- vapply(found$listings, function(row) as.character(row$asset_id), character(1L))
      if (is.null(held$core)) refresh_catalog()
      ready <- Filter(function(row) identical(row$status, "history_ready_to_plan"), chain$valuation_inventory()$rows)
      queue <- Filter(function(row) isTRUE(tryCatch(desktop_catalog_editor_internal_identity_v1(catalog_editor, ctx, "asset", row$asset_ref) %in% ids,
                                                    error = function(error) FALSE)), ready)
      start_sweep(queue, list(mode = "recent_gaps", start = window$start, end = window$end))
      list(count = length(queue), gap_day_count = as.integer(found$gap_day_count))
    },
    gaps_remaining = function(window) as.integer(snapshot$recent_gaps(window$start, window$end)$gap_day_count),
    closing_inputs = function(day, cutoff) {
      held$run_catalog <- spotcore::desktop_run_center_catalog_v1(run_center, ctx)
      spotcore::desktop_run_center_last_form_v1(run_center, ctx, day, cutoff)
    },
    # Der Umfang des Portfolios, dessen Abschluss gerechnet wird (rc.410), und der Vermerk der Steuervorgaben, die „Alles aktualisieren“
    # wegen eines Umfangs ohne Steuerbericht selbst abgeschaltet hat - nur diese holt es zurueck (#564).
    portfolio_modules = function(portfolio_id) data_refresh_all_portfolio_modules_v1(project_root, ctx, portfolio_id),
    tax_override_read = function() {
      path <- file.path(runtime_data_space_path(ctx), DATA_REFRESH_ALL_AREA_V1, "closing-tax-override.json")
      if (!file.exists(path) || nzchar(Sys.readlink(path))) NULL else tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE), error = function(error) NULL)
    },
    tax_override_write = function(value) {
      area <- file.path(runtime_data_space_path(ctx), DATA_REFRESH_ALL_AREA_V1)
      old <- Sys.umask("0077"); on.exit(Sys.umask(old), add = TRUE)
      if (!dir.exists(area)) dir.create(area, mode = "0700")
      path <- file.path(area, "closing-tax-override.json"); staged <- paste0(path, ".", Sys.getpid())
      writeLines(as.character(jsonlite::toJSON(c(value, list(saved_at_utc = now_utc())), auto_unbox = TRUE, null = "null")), staged, useBytes = TRUE)
      Sys.chmod(staged, "0600")
      if (!file.rename(staged, path)) { unlink(staged); stop("data_refresh_all_store_invalid", call. = FALSE) }
      invisible(TRUE)
    },
    tax_override_clear = function() invisible(unlink(file.path(runtime_data_space_path(ctx), DATA_REFRESH_ALL_AREA_V1, "closing-tax-override.json"))),
    closing_run = function(inputs, day) {
      form <- inputs$form
      complaint <- desktop_product_run_form_complaint_v1(form, Filter(function(asset) asset$asset_type != "cash" && asset$status == "active",
                                                                      held$run_catalog$assets))
      if (!is.null(complaint)) return(list(status = "invalid", copy = complaint))
      bound <- semantic_binding()
      if (identical(bound$status, "failed")) return(list(status = "invalid", copy = bound$copy))
      preview <- spotcore::desktop_run_center_prepare_v1(run_center, ctx, form, now_utc(), runtime$data_space_label, bound$binding, NULL)
      if (isTRUE(spotcore::desktop_run_center_preview_repeats_last_v1(run_center, ctx, preview, project_root)))
        return(list(status = "current", aligned = bound$aligned))
      issued <- now_utc()
      confirmation <- spotcore::desktop_run_center_build_confirmation_v1(run_center, ctx, preview, issued, add_seconds(issued, 300L), project_root)
      result <- spotcore::desktop_run_center_execute_v1(run_center, ctx, preview, confirmation, issued, project_root)
      list(status = result$status, failure_code = result$failure_code, aligned = bound$aligned)
    })
}
