# Die Kurskette und der Sammellauf des Asset-Centers ohne Shiny-Sitzung (rc.315, #510).
#
# Bis rc.314 lagen diese Funktionen im Server der Data-App. „Alles aktualisieren“ lief deshalb nur, solange die Seite offen war;
# ein Wechsel in eine andere App beendete den Lauf (Festlegung 24.10.2026). Jetzt rufen die App (Einzelablauf, Sammellauf im
# Reiter Marktdaten) und der Hintergrundlauf (scripts/desktop_refresh_all.R) denselben Code auf - ein Sammellauf, der
# stillschweigend etwas anderes taete als der Einzelschritt, waere nicht nachpruefbar (#283).
#
# Die Rumpfe sind aus der App uebernommen; geaendert sind nur die Vorgaben, die dort aus der Oberflaeche kamen (Auswahl,
# Zeitraum), und das Ziel: Es muss uebergeben werden. Dienste und Lesefunktionen kommen herein:
# - services: market_review, market_plan, market_coverage, fx_history, fx_coverage, calendar_gap, calendar_review, valuation,
#   promotion, catalog_editor, provider_editor (dieselben Konstruktoren wie in der App);
# - lookups: catalog() und providers() (Stammdaten und Zuordnungen, wie der Asset-Center sie zuletzt gelesen hat),
#   first_booking(asset_ref), now_utc(), invalidate_valuation();
#   wahlweise timeline() und timeline_coverage(asset_id) - die Bewertungs-Zeitleiste ueber new_data_market_timeline_reader_v1
#   (rc.393). Ohne sie oder ohne Speicher der Zeitleiste bleibt alles wie bisher: eine Kursreihe je Asset. Wahlweise valued_series():
#   alle Reihen im Bewertungsstand; eine fehlende bewertet der Sammellauf, auch wenn kein Kurstag fehlt (#493).
# Der Zustand eines Sammellaufs wird uebergeben (sweep_step, sweep_reset): in der App reactiveValues, im Hintergrundlauf eine
# Umgebung (new_data_market_sweep_state_v1). Beide kennen `$` und `$<-`.

new_data_market_sweep_state_v1 <- function() {
  state <- new.env(parent = emptyenv())
  state$queue <- list(); state$index <- 0L; state$results <- list(); state$running <- FALSE
  state$resume_at <- NULL; state$attempts <- 0L; state$prepared <- FALSE; state$period <- NULL; state$stepped_at <- NULL
  state
}

# Ob der Datenbestand an diesem Ort gebunden ist (#556): Liegt er an einem anderen Ort als beim Anlegen und ist dort nicht gebunden
# (Restore mit "unverified", oder eine von Hand kopierte Kopie), lehnen Bewertung, Kurszuordnung, Wechselkurse und Kalender ihre
# Eintraege ab - bisher mit Fehlercodes der einzelnen Speicher. Nur lesend; gebunden wird nie von selbst. NULL heisst: nicht
# feststellbar, dann haelt nichts an.
data_relocation_status_v1 <- function(project_root, data_space) {
  python <- Sys.which("python3"); cli <- file.path(project_root, "scripts", "desktop_relocation.py")
  if (!nzchar(python) || !file.exists(cli) || !is.character(data_space) || length(data_space) != 1L) return(NULL)
  output <- tryCatch(suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), "status"), stdout = TRUE, stderr = FALSE,
    input = as.character(jsonlite::toJSON(list(data_space_path = data_space), auto_unbox = TRUE)))), error = function(error) character())
  parsed <- tryCatch(jsonlite::fromJSON(utils::tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (!is.list(parsed) || !identical(parsed$status, "completed") || !is.list(parsed$result)) return(NULL)
  parsed$result
}

# Der Grund in Worten, mit den betroffenen Speichern und dem naechsten Schritt; NULL, wenn gebunden oder unbekannt.
data_relocation_blocked_copy_v1 <- function(status) {
  if (!is.list(status) || !identical(status$status, "unbound")) return(NULL)
  stores <- vapply(status$unbound_stores, as.character, character(1L))
  paste0("Der Datenbestand liegt an einem anderen Ort als beim Anlegen und ist dort nicht gebunden",
         if (length(stores)) paste0(": ", paste(stores, collapse = ", "), if (length(stores) == 1L) " lehnt" else " lehnen",
                                    " die eigenen Einträge hier ab") else "",
         ". Nach einem Restore an diesen Ort einmal „portelyra_desktop.R relocate --confirm BIND_RESTORED_DATA_SPACE“ ausführen",
         " (Handbuch „Backup zurückspielen“). Bei einer von Hand kopierten Kopie ist die Sperre Absicht.")
}

new_data_market_chain_v1 <- function(services, lookups, context) {
  required <- c("market_review", "market_plan", "market_coverage", "fx_history", "fx_coverage", "calendar_gap", "calendar_review",
                "valuation", "promotion", "catalog_editor", "provider_editor")
  if (!is.list(services) || !all(required %in% names(services)) || !is.list(lookups) ||
      !all(c("catalog", "providers", "first_booking", "now_utc", "invalidate_valuation") %in% names(lookups)))
    stop("data_market_chain_invalid", call. = FALSE)
  # Dieselben Namen wie in der App, damit die uebernommenen Rumpfe unveraendert bleiben.
  asset_center_market_review_service <- services$market_review
  asset_center_market_plan_service <- services$market_plan
  asset_center_market_coverage_service <- services$market_coverage
  asset_center_fx_history_service <- services$fx_history
  asset_center_fx_coverage_service <- services$fx_coverage
  asset_center_calendar_gap_service <- services$calendar_gap
  asset_center_calendar_review_service <- services$calendar_review
  asset_center_valuation_service <- services$valuation
  asset_center_provider_promotion_service <- services$promotion
  asset_center_catalog_editor <- services$catalog_editor
  asset_center_provider_editor <- services$provider_editor
  asset_center_catalog <- lookups$catalog
  asset_center_provider_catalog <- lookups$providers
  asset_center_first_booking <- lookups$first_booking
  now_utc <- lookups$now_utc
  asset_center_valuation_workflow <- list(invalidate = lookups$invalidate_valuation)
  runtime <- list(context = context)
  ASSET_CENTER_SWEEP_BACKOFF <- c(300L, 600L, 1200L, 1800L)
  # Die Bewertungs-Zeitleiste je asset_ref (data_market_timeline_series_v1) oder NULL, wenn es keine gibt. Die Zeitleiste kennt
  # interne Kennungen; die Zeilen der Oberflaeche tragen Browser-Refs, uebersetzt ueber den Katalog wie in valuation_resolve.
  asset_center_timeline <- function() {
    if (!is.function(lookups$timeline)) return(NULL)
    overview <- lookups$timeline()
    if (is.null(overview) || !length(overview$assets)) return(NULL)
    refs <- character()
    for (a in asset_center_catalog()$assets) {
      id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", a$ref),
                     error = function(error) NA_character_)
      if (is.character(id) && length(id) == 1L && !is.na(id)) refs[[id]] <- a$ref
    }
    data_market_timeline_series_v1(overview, refs)
  }
  # series = TRUE: mit den frueheren Kursreihen der Zeitleiste (Sammellauf). Ohne bleibt es bei einer Zeile je Asset - die
  # Bewertung in der Oberflaeche, der Einzelablauf und die Uebertragung verlangen genau eine. Dort sperrt eine unlesbare
  # Zeitleiste nicht die ganze Oberflaeche; der Sammellauf dagegen haelt an (kein stiller Rueckfall).
  asset_center_valuation_inventory <- function(series = FALSE) {
      if (is.null(asset_center_catalog()) || is.null(asset_center_provider_catalog())) return(list(rows=list()))
      timeline <- if (isTRUE(series)) asset_center_timeline() else tryCatch(asset_center_timeline(), error = function(error) NULL)
      value <- data_asset_center_market_inventory_v1(asset_center_catalog(), asset_center_provider_catalog(), timeline)
      for(a in asset_center_catalog()$assets) if(identical(a$status,'active') && !identical(a$asset_type,'cash') && a$valuation_method%in%c('manual','unit_value'))
        value$rows <- c(value$rows,list(list(asset_ref=a$ref,asset_name=a$display_name,status=a$valuation_method)))
      if (!isTRUE(series) && !is.null(timeline))
        value$rows <- Filter(function(row) !identical(row$series_role, "earlier"), value$rows)
      value
  }
  # Die eine Zeile eines Laufs: Fuehrt ein Asset mehrere (Zeitleiste), entscheidet bei Marktdaten die Reihe des Ziels (Anbieter
  # und Symbol der aufgeloesten Zuordnung), sonst die providerfreie Zeile. Ein Asset mit einer Zeile bleibt wie bisher.
  asset_center_inventory_rows <- function(asset_ref, target = NULL, provider_free = FALSE) {
    rows <- Filter(function(row) identical(row$asset_ref, asset_ref), asset_center_valuation_inventory(series = TRUE)$rows)
    if (length(rows) <= 1L) return(rows)
    if (isTRUE(provider_free)) return(Filter(function(row) as.character(row$status) %in% c("manual", "unit_value"), rows))
    Filter(function(row) identical(row$provider, target$mapping$provider_id) && identical(row$symbol, target$mapping$provider_symbol), rows)
  }
  # Die Grenzen, in denen eine Reihe der Zeitleiste abgerufen und bewertet wird: eine fruehere nur in ihren Abschnitten (NA =
  # seit Beginn bzw. offen, dann gilt die heutige Regel); die laufende wie bisher, bei einem nicht kostenlosen Anbieter aber erst
  # ab Beginn ihres Abschnitts - davor traegt eine andere Reihe die Tage. Zeilen ohne Zeitleiste: keine Grenze.
  asset_center_series_window <- function(row) {
    if (identical(row$series_role, "earlier")) return(list(from = row$valid_from, until = row$valid_until))
    if (identical(row$series_role, "current") && !identical(row$provider_cost, "free") && data_market_timeline_day_v1(row$valid_from))
      return(list(from = row$valid_from, until = NA_character_))
    NULL
  }
  # Ob eine fruehere Reihe im Bewertungsstand fehlt oder ihren Abschnitt nicht bis zum Ende traegt - etwa nach einem Neuaufbau des
  # Stands. Dann wird sie bewertet, auch wenn kein Kurstag fehlt; sonst bliebe die Zeit vor dem Wechsel offen. Ein unklarer
  # Befund haelt die Reihe im Lauf.
  asset_center_series_unvalued <- function(row, held) {
    if (!identical(row$series_role, "earlier")) return(FALSE)
    if (!is.function(lookups$timeline_coverage)) return(TRUE)
    asset_id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", row$asset_ref),
                         error = function(error) NA_character_)
    if (!is.character(asset_id) || length(asset_id) != 1L || is.na(asset_id)) return(TRUE)
    if (!exists(asset_id, envir = held, inherits = FALSE))
      assign(asset_id, tryCatch(lookups$timeline_coverage(asset_id), error = function(error) NULL), envir = held)
    coverage <- get(asset_id, envir = held, inherits = FALSE)
    entry <- if (is.list(coverage)) coverage[[row$symbol]] else NULL
    days <- if (is.list(entry)) suppressWarnings(as.integer(entry$days)) else NA_integer_
    if (length(days) != 1L || is.na(days) || days < 1L) return(TRUE)
    last <- entry$last
    data_market_timeline_day_v1(row$valid_until) && !(data_market_timeline_day_v1(last) && last >= row$valid_until)
  }
  # Ob der Bewertungsstand eine Kursreihe gar nicht fuehrt - etwa nach einem Restore, bei dem er neu aufgebaut wird, oder wenn er
  # verloren ging (#493). Dann wird sie aus den gespeicherten Kursen bewertet, auch wenn kein Kurstag fehlt; sonst meldete der
  # Sammellauf "keinem Asset fehlt ein Kurstag", und Tageshistorie und Snapshot blieben leer. Ohne die Abfrage (lookups$valued_series)
  # bleibt alles wie bisher; ein unklarer Befund haelt die Reihe im Lauf.
  asset_center_series_absent <- function(row, held) {
    if (!is.function(lookups$valued_series)) return(FALSE)
    if (!exists(".valued_series", envir = held, inherits = FALSE))
      assign(".valued_series", tryCatch(lookups$valued_series(), error = function(error) NULL), envir = held)
    valued <- get(".valued_series", envir = held, inherits = FALSE)
    if (!is.character(valued) || !is.character(row$symbol) || length(row$symbol) != 1L) return(TRUE)
    asset_id <- tryCatch(desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", row$asset_ref),
                         error = function(error) NA_character_)
    if (!is.character(asset_id) || length(asset_id) != 1L || is.na(asset_id)) return(TRUE)
    !paste(asset_id, row$symbol, sep = "\t") %in% valued
  }
  asset_center_valuation_resolve <- function(rows) lapply(rows, function(row) {
      asset_id <- desktop_catalog_editor_internal_identity_v1(asset_center_catalog_editor, runtime$context, "asset", row$asset_ref)
      target <- list(asset_id=asset_id, asset_ref=row$asset_ref, asset_name=row$asset_name,
                     listing_ref=NULL, mapping=NULL, promotion_binding=NULL, disposition=row$status)
      if (!identical(row$status, "history_ready_to_plan")) return(target)
      # Eine widersprüchliche Zuordnung (etwa eine Listing-Promotion aus einer
      # früheren Mapping-Revision) betrifft nur dieses Asset. Sie erscheint als
      # „Testabruf offen“ in der Zusammenfassung, statt den ganzen Lauf mit
      # desktop_market_valuation_mapping_invalid abzubrechen (#189-Nachlauf).
      resolved <- tryCatch({
        mapping <- data_provider_mapping_editor_resolve_history_scope_v1(asset_center_provider_editor, runtime$context, row$mapping_ref)
        if (!identical(mapping$asset_id, asset_id)) stop("mapping_scope_mismatch", call. = FALSE)
        recovered <- asset_center_provider_promotion_service$recover(mapping$mapping_id)
        if (is.null(recovered)) list(mapping = mapping, promotion = NULL) else {
          promotion <- asset_center_provider_promotion_service$resolve_promotion(recovered$promotion_handle)
          if (!identical(promotion$mapping_id, mapping$mapping_id)) stop("mapping_scope_mismatch", call. = FALSE)
          list(mapping = mapping, promotion = promotion)
        }
      }, error = function(error) NULL)
      if (is.null(resolved)) { target$disposition <- "mapping_test_required"; return(target) }
      if (is.null(resolved$promotion)) return(target)
      mapping <- resolved$mapping; promotion <- resolved$promotion
      target$mapping<-mapping;target$listing_ref<-promotion$listing_ref
      target$promotion_binding<-list(listing_ref=promotion$listing_ref,listing_fingerprint=promotion$listing_fingerprint,
        mapping_id=promotion$mapping_id,mapping_revision=as.integer(promotion$mapping_revision),mapping_fingerprint=promotion$mapping_fingerprint)
      target
  })
  asset_center_resolve_open_fx <- function() {
    resolved <- 0L
    for (attempt in seq_len(20L)) {
      inspection <- tryCatch(asset_center_fx_history_service$inspect(), error = function(error) NULL)
      if (is.null(inspection)) break
      open <- Filter(function(row) !identical(row$state, "published") && !isTRUE(row$reviewed_no_result), inspection$rows)
      if (!length(open)) break
      row <- open[[1L]]
      if (identical(row$state, "staged") && is.character(row$source_currency) && length(row$source_currency) == 1L) {
        recovered <- asset_center_fx_history_service$recover(row$attempt_ref, row$source_currency, row$target_currency, row$start_date, row$end_date)
        invisible(asset_center_fx_history_service$publish(recovered, TRUE, now_utc()))
      } else {
        invisible(asset_center_fx_history_service$acknowledge(row$attempt_ref, TRUE))
      }
      resolved <- resolved + 1L
    }
    resolved
  }
  asset_center_coverage_row <- function(target, from, until, asset_ref, mapping_ref) tryCatch({
    rows <- asset_center_market_coverage_service$read(
      list(list(asset_ref = asset_ref, mapping_ref = mapping_ref,
                listing_ref = target$private$listing_ref)), from, until)$rows
    if (length(rows)) rows[[1L]] else NULL
  }, error = function(error) NULL)
  # Erster gespeicherter Kurstag der Reihe, auch vor dem Abrufzeitraum (#557): Ab dort wird bewertet, nicht erst ab der ersten
  # Buchung - die Kurshistorie gehoert der Notierung (Festlegung 27.09.2026). Sonst begann ein Neuaufbau des Bewertungsstands
  # spaeter als der fortgeschriebene Stand. Nie vor dem Abschnitt der Bewertungs-Zeitleiste und nie nach dem Ende.
  asset_center_stored_from <- function(row, window, until) {
    value <- if (is.list(row)) row$first_stored_observed_date else NULL
    if (!is.character(value) || length(value) != 1L || !data_market_timeline_day_v1(value) || value > until) return(NA_character_)
    if (is.list(window) && data_market_timeline_day_v1(window$from) && value < window$from) return(NA_character_)
    value
  }
  asset_center_first_observed <- function(target, from, until, asset_ref, mapping_ref, row = NULL) {
    tryCatch({
      if (is.null(row)) row <- asset_center_coverage_row(target, from, until, asset_ref, mapping_ref)
      if (is.null(row)) return(NA_character_)
      covered <- row$first_covered_date
      # Der erste Kurstag beweist nur dann eine spaete Listung, wenn die Tage davor
      # ueberhaupt gespeichert sind. Reicht der Bestand selbst erst spaeter zurueck
      # - etwa nach einem kurzen Testabruf -, sagt er nichts ueber die Listung und
      # darf den Bewertungsbeginn nicht abschneiden (#283, 21.09.2026).
      if (!is.character(covered) || length(covered) != 1L || !nzchar(covered) || covered > from) return(NA_character_)
      value <- row$first_observed_date
      if (is.character(value) && length(value) == 1L && nzchar(value)) value else NA_character_
    }, error = function(error) NA_character_)
  }
  asset_center_completed_until <- function(until, reported) {
    if (is.character(reported) && length(reported) == 1L && !is.na(reported) && nzchar(reported) && reported < until) reported else until
  }
  asset_center_not_completed_plan <- function(target, from, until, listed_since) list(
    plan = list(range_count = 0L, target_day_count = 0L, ranges = list()), fx_plan = NULL, fx_missing = FALSE, open_fx = 0L,
    currency = target$mapping$provider_currency, from = from, until = until, fx_as_of = NA_character_,
    listed_since = listed_since, not_completed_yet = TRUE)
  asset_center_chain_plan <- function(asset_ref, period_start, period_end,
                                      period_mode = "from_first_trade",
                                      valuation_method = "external_market",
                                      manual_source = "own_entries",
                                      target = NULL, mapping_ref = NULL, window = NULL) {
        method <- valuation_method
        if (!identical(method, "external_market")) {
          until <- as.character(min(as.Date(period_end), Sys.Date() - 1L))
          from <- as.character(period_start)
          booked <- asset_center_first_booking(asset_ref)
          mode <- if (is.character(period_mode) && length(period_mode) == 1L)
            period_mode else "from_first_trade"
          if (identical(mode, "from_first_trade") && !is.null(booked) && !is.na(booked)) from <- as.character(booked)
          return(list(provider_free = TRUE, method = method, currency = "EUR", from = from, until = until,
            fx_as_of = NA_character_, open_fx = 0L, fx_missing = FALSE, fx_plan = NULL,
            plan = list(range_count = 0L, target_day_count = 0L, ranges = list())))
        }
        # Das Ziel loest der Aufrufer auf: die App aus ihrer Auswahl, der Sammellauf je Zeile.
        if (is.null(target)) stop("asset_center_chain_target_required", call. = FALSE)
        until <- as.character(min(as.Date(period_end), Sys.Date() - 1L))
        from <- as.character(period_start)
        # Erst die erste Buchung des Assets, dann die Erstnotiz. Den unberuehrten
        # Vorgabewert ersetzt die erste Buchung ganz, auch nach hinten; einen selbst
        # gesetzten Beginn ruecken wir nur vor.
        # Der gewaehlte Modus entscheidet ueber den Beginn.
        mode <- if (is.character(period_mode) && length(period_mode) == 1L)
          period_mode else "from_first_trade"
        booked_from <- asset_center_first_booking(asset_ref)
        booked <- if (!is.null(booked_from) && !is.na(booked_from)) as.character(booked_from) else NA_character_
        period_invalid <- FALSE
        if (identical(mode, "from_first_trade")) {
          if (!is.na(booked)) from <- booked
        } else if (identical(mode, "before_first_trade")) {
          if (!is.na(booked) && from > booked) period_invalid <- TRUE
        } else if (identical(mode, "recent_gaps")) {
          # Nachabruf der Quellluecken (#477): nur das Fenster, nicht vor der ersten Buchung.
          if (!is.na(booked) && booked > from) from <- booked
        }
        # Der Nachabruf plant nur Tage mit Quellluecke; alles andere bleibt "nur fehlende Tage".
        history_mode <- if (identical(mode, "recent_gaps")) "retry_source_gaps" else "incremental"
        if (period_invalid) return(list(period_invalid = TRUE, booked = booked, from = from, until = until))
        # Bewertungs-Zeitleiste (rc.393): Eine Reihe mit Grenzen (asset_center_series_window) wird nur darin abgerufen und
        # bewertet. Liegt ihr Abschnitt ganz ausserhalb des Zeitraums, gibt es nichts zu tun - eine Auskunft, kein Abbruch.
        if (is.list(window)) {
          if (data_market_timeline_day_v1(window$from) && window$from > from) from <- window$from
          if (data_market_timeline_day_v1(window$until) && window$until < until) until <- window$until
          if (from > until) return(list(plan = list(range_count = 0L, target_day_count = 0L, ranges = list()),
            fx_plan = NULL, fx_missing = FALSE, open_fx = 0L, currency = target$mapping$provider_currency,
            from = from, until = until, fx_as_of = NA_character_, listed_since = NA_character_, outside_window = TRUE))
        }
        # Vor der Erstnotiz gibt es keinen Kurs - dort zu planen erzeugt nur
        # Abbrueche und falsche offene Tage. Die Quelle nennt die Erstnotiz in
        # jeder gelungenen Antwort; sie liegt am Anbietersymbol und wird hier
        # gelesen, ohne Abruf (#283, 25.09.2026).
        notation <- tryCatch(asset_center_market_review_service$notation(
          target$mapping$provider_symbol), error = function(error) NULL)
        listed_since <- if (is.list(notation) && is.character(notation$first_trade_date) &&
            length(notation$first_trade_date) == 1L) notation$first_trade_date else NA_character_
        if (!is.na(listed_since) && listed_since > from) from <- listed_since
        # Endet der gewuenschte Zeitraum vor der Erstnotiz, gibt es nichts zu
        # planen. Das ist eine Auskunft, kein Abbruch.
        if (from > until) return(list(plan = list(range_count = 0L, target_day_count = 0L, ranges = list()),
          fx_plan = NULL, fx_missing = FALSE, open_fx = 0L, currency = target$mapping$provider_currency,
          from = from, until = until, fx_as_of = NA_character_, listed_since = listed_since,
          not_listed_yet = TRUE))
        coverage <- asset_center_coverage_row(target, from, until, asset_ref, mapping_ref)
        listed_from <- asset_center_first_observed(target, from, until, asset_ref, mapping_ref, row = coverage)
        if (!is.na(listed_from) && listed_from > from) from <- listed_from
        stored_from <- asset_center_stored_from(coverage, window, until)
        plan <- asset_center_market_plan_service$plan(target$private$listing_ref, from, until, history_mode)
        # Das Ende ist der juengste Tag, der in der Zeitzone der Notierung abgeschlossen ist - nicht einfach gestern nach
        # Ortszeit. Kurz nach Mitternacht laeuft der UTC-Tag noch; ein laufender Kurs kaeme sonst als Tageswert in den
        # Speicher und gaelte danach als vorhanden (#475). Die Planung kennt die Zeitzone und meldet ihr Ende.
        until <- asset_center_completed_until(until, plan$as_of_date)
        if (from > until) return(asset_center_not_completed_plan(target, from, until, listed_since))
        # Fremdwaehrung heisst: ohne Kurse des Paares bleibt die Bewertung offen.
        currency <- target$mapping$provider_currency
        # Fehlt das Waehrungspaar, ist das keine Stoerung mitten im Lauf, sondern eine
        # eigene Entscheidung: Symbol und Richtung kann niemand raten.
        open_fx <- if (identical(currency, "EUR")) 0L else tryCatch({
          rows <- asset_center_fx_history_service$inspect()$rows
          length(Filter(function(row) !identical(row$state, "published") && !isTRUE(row$reviewed_no_result), rows))
        }, error = function(error) 0L)
        fx <- if (identical(currency, "EUR")) list(plan = NULL, missing = FALSE) else tryCatch(
          list(plan = asset_center_fx_history_service$plan(currency, "EUR", from, until), missing = FALSE),
          error = function(error) if (grepl("pair_missing", conditionMessage(error), fixed = TRUE)) list(plan = NULL, missing = TRUE) else stop(error))
        # Endet der Tag des Waehrungspaares spaeter als der der Notierung, gilt das fruehere Ende fuer beide (#475).
        if (!is.null(fx$plan)) {
          fx_until <- asset_center_completed_until(until, fx$plan$end_date)
          if (fx_until < until) {
            until <- fx_until
            if (from > until) return(asset_center_not_completed_plan(target, from, until, listed_since))
            plan <- asset_center_market_plan_service$plan(target$private$listing_ref, from, until, history_mode)
          }
        }
        # Die Aktualitaet der Umrechnungsbasis gehoert in den Plan: Der Wechselkurs
        # traegt jede Fremdwaehrungsbewertung (Entscheidung 22.09.2026).
        fx_as_of <- if (identical(currency, "EUR")) NA_character_ else tryCatch({
          rows <- asset_center_fx_coverage_service$read(
            list(list(source_currency = currency, target_currency = "EUR", consumer_count = 1L)), from, until)$rows
          value <- if (length(rows)) rows[[1L]]$last_observed_date else NULL
          if (is.character(value) && length(value) == 1L && nzchar(value)) value else NA_character_
        }, error = function(error) NA_character_)
        list(plan = plan, fx_plan = fx$plan, fx_missing = fx$missing, open_fx = open_fx, currency = currency,
             from = from, until = until, fx_as_of = fx_as_of, listed_since = listed_since,
             valued_from = if (!is.na(stored_from) && stored_from < from && stored_from <= until) stored_from else from)
  }
  asset_center_chain_run <- function(asset_ref, planned, target = NULL,
                                     manual_source = "own_entries",
                                     require_selection = FALSE) {
    step <- "Kursabruf"
    fetched <- 0L
    fetched_fx <- 0L
    resolved_fx <- 0L
    provider_free <- isTRUE(planned$provider_free)
    outcome <- tryCatch({
      if (provider_free) {
        step <- "Bewertung"
        asset_center_valuation_workflow$invalidate()
        rows <- asset_center_inventory_rows(asset_ref, provider_free = TRUE)
        if (length(rows) != 1L) stop("desktop_market_valuation_selection_invalid", call. = FALSE)
        request <- list(targets = asset_center_valuation_resolve(rows), execution_ref = NULL,
          start_date = planned$from, end_date = planned$until,
          valuation_policy = list(mode = "last_valid", max_age_days = NULL, age_unit = "calendar_days"),
          target_currency = "EUR", use_rules = FALSE, use_saved_calendars = FALSE, max_age_days = 366L,
          market_exceptions = structure(list(), names = character()), fx_exceptions = structure(list(), names = character()),
          simple_absence_policy = FALSE,
          use_trade_prices = identical(planned$method, "manual") && identical(manual_source, "trade_prices"),
          use_manual_prices = identical(planned$method, "manual") && identical(manual_source, "own_entries"))
        review <- asset_center_valuation_service$prepare(request)
        detail <- tryCatch(asset_center_valuation_service$detail(1L)$rows, error = function(error) list())
        return(list(status = "prepared", fetched = 0L, fetched_fx = 0L, resolved_fx = 0L, bound_closures = 0L,
          review = review, detail = detail, valued_from = request$start_date,
          requested_from = planned$from, until = planned$until,
          summary = if (length(review$rows)) review$rows[[1L]] else NULL))
      }
      # Auswahl und Ziel der Oberflaeche prueft die App vor dem Aufruf (require_selection); hier gilt nur das Ziel.
      if (is.null(target)) stop("asset_center_chain_target_required", call. = FALSE)
      # Der gewuenschte Zeitraum endet vor der Erstnotiz: Es gibt nichts
      # abzurufen und nichts zu bewerten. Das ist eine Auskunft, kein Fehler.
      if (isTRUE(planned$not_listed_yet)) {
        return(list(status = "not_listed", fetched = 0L, fetched_fx = 0L, resolved_fx = 0L,
          bound_closures = 0L, review = NULL, detail = list(), not_listed = 0L,
          listed_since = planned$listed_since, valued_from = planned$from,
          requested_from = planned$from, until = planned$until, summary = NULL))
      }
      # Ein gestagter oder unquittierter Versuch sperrt nicht nur weitere Abrufe des
      # Paares: Solange sein Ausgang unbekannt ist, sperrt die Bewertung saemtliche
      # Wechselkurse, und jeder Tag jedes Fremdwaehrungsassets gilt als offen. Das
      # wird deshalb immer zuerst aufgeloest, nicht nur wenn FX-Tage fehlen
      # (#283).
      step <- "Offene Wechselkurs-Versuche"
      resolved_fx <- asset_center_resolve_open_fx()
      # Der Wechselkurs ist die Basis jeder Fremdwaehrungsbewertung und wird deshalb
      # zuerst geholt. Sonst steht bei einem Abbruch am Ende ein frischer Kurs neben
      # einem alten Wechselkurs (Entscheidung 22.09.2026, #283).
      if (!is.null(planned$fx_plan) && length(planned$fx_plan$ranges)) {
        step <- "Wechselkursabruf"
        for (range in planned$fx_plan$ranges) {
          fx_preview <- asset_center_fx_history_service$preview(planned$currency, "EUR", range$start_date, range$end_date, now_utc())
          fx_review <- asset_center_fx_history_service$stage(fx_preview, TRUE)
          step <- "Wechselkurs-Veröffentlichung"
          invisible(asset_center_fx_history_service$publish(fx_review, TRUE, now_utc()))
          step <- "Wechselkursabruf"
          fetched_fx <- fetched_fx + 1L
        }
      }
      # Ein misslungener Abruf laesst den Pruefdienst im Zustand "Abrufversuch
      # verbraucht" zurueck. Ohne Aufloesung weist er danach jede weitere
      # Anfrage ab - sonst bricht nach einem einzigen
      # unbrauchbaren Anbieterergebnis der Rest ab: alle weiteren Assets enden mit
      # desktop_market_history_review_recovery_required, obwohl mit ihnen
      # nichts ist (#283).
      resolve_review_state <- function(listing_ref) {
        # Erst der begonnene, nie angekommene Schreibvorgang: Ohne Aufloesung
        # bleibt das Asset dauerhaft gesperrt - erneut veroeffentlichen geht
        # nicht, der Versuch ist verbraucht. Das Verwerfen sucht den offenen
        # Stand selbst und prueft selbst, dass der Anhang ausblieb; es haengt
        # damit nicht an der Wiederherstellung, deren strenge Nachpruefung
        # ihrerseits scheitern kann (25.09.2026, #283).
        tryCatch(invisible(asset_center_market_review_service$discard(listing_ref, now_utc())),
                 error = function(error) NULL)
        recovered <- tryCatch(asset_center_market_review_service$recover(listing_ref),
                              error = function(error) NULL)
        if (is.null(recovered) || !identical(recovered$state, "staged_review")) return(invisible(NULL))
        # Abgerufen ist abgerufen: Die Tage liegen vor, nur das Schreiben fehlte.
        # Verwerfen hiesse, die Quelle ein zweites Mal zu belasten - und genau
        # die bremst.
        tryCatch(invisible(asset_center_market_review_service$publish(
          recovered$public_review, TRUE, now_utc())), error = function(error)
            tryCatch(invisible(asset_center_market_review_service$reject(
              recovered$public_review, TRUE, now_utc())), error = function(inner) NULL))
        invisible(NULL)
      }
      step <- "Kursabruf"
      # Liegt ein Fenster vollstaendig vor der Erstnotiz, weist die Quelle es ab.
      # Das ist eine Auskunft und kein Grund, das Asset abzubrechen: Die
      # spaeteren Fenster liefern die Kurse und die Erstnotiz gleich mit, und ab
      # dem naechsten Lauf beginnt die Planung dort (#283, 25.09.2026).
      not_listed <- 0L
      for (range in planned$plan$ranges) {
        outcome_range <- tryCatch({
          preview <- asset_center_market_review_service$preview(
            target$private$listing_ref, target$mapping, target$binding,
            range$start_date, range$end_date, planned$plan$mode, now_utc())
          review <- asset_center_market_review_service$stage(preview, TRUE)
          step <- "Veröffentlichung"
          invisible(asset_center_market_review_service$publish(review, TRUE, now_utc()))
          step <- "Kursabruf"
          "fetched"
        }, error = function(error) {
          resolve_review_state(target$private$listing_ref)
          if (identical(conditionMessage(error), "desktop_market_history_review_source_not_listed"))
            return("not_listed")
          stop(error)
        })
        step <- "Kursabruf"
        if (identical(outcome_range, "not_listed")) not_listed <- not_listed + 1L else fetched <- fetched + 1L
      }
      # Ein Boersenfeiertag liefert keinen Kurs. Ohne gebundenen Schliesstag gilt er
      # als Quellluecke und der fortgeschriebene Wert als Ersatzwert - bei einer
      # US-Aktie ein Dutzend roter Tage pro Jahr, obwohl nichts fehlt. Die
      # Schliesstage kommen ausschliesslich aus dem beobachteten Kursverlauf
      # (rule_closure_candidate), nicht aus einer erfundenen Feiertagsliste
      # (Festlegung 22.09.2026, #283).
      step <- "Handelskalender"
      bound_closures <- 0L
      gap_rows <- tryCatch(asset_center_calendar_gap_service$read(
        list(list(asset_ref = asset_ref, listing_ref = target$private$listing_ref)),
        if (identical(planned$currency, "EUR")) list() else list(list(source_currency = planned$currency, target_currency = "EUR", consumer_count = 1L)),
        planned$from, planned$until)$rows, error = function(error) list())
      if (length(gap_rows)) {
        listing_dates <- data_calendar_binding_choices_v1(gap_rows, list(kind = "listing", consumer = asset_ref))
        if (length(listing_dates)) {
          public <- asset_center_calendar_review_service$preview_listing_binding(
            target$private$listing_ref, listing_dates, planned$from, planned$until, now_utc())
          invisible(asset_center_calendar_review_service$apply_binding(public, TRUE, now_utc()))
          bound_closures <- bound_closures + length(listing_dates)
        }
        if (!identical(planned$currency, "EUR")) {
          route <- paste0(planned$currency, "→EUR")
          fx_dates <- data_calendar_binding_choices_v1(gap_rows, list(kind = "fx_pair", consumer = route))
          if (length(fx_dates)) {
            public <- asset_center_calendar_review_service$preview_binding(
              planned$currency, "EUR", fx_dates, planned$from, planned$until, now_utc())
            invisible(asset_center_calendar_review_service$apply_binding(public, TRUE, now_utc()))
            bound_closures <- bound_closures + length(fx_dates)
          }
        }
      }
      step <- "Bewertung"
      asset_center_valuation_workflow$invalidate()
      # Mit Zeitleiste fuehrt ein Asset mehrere Reihen; bewertet wird die, deren Kurse eben geholt wurden.
      rows <- asset_center_inventory_rows(asset_ref, target)
      if (length(rows) != 1L) stop("desktop_market_valuation_selection_invalid", call. = FALSE)
      # Bewertet wird ab dem ersten gespeicherten Kurstag, auch wenn der Abruf spaeter beginnt (#557).
      valued_from <- if (is.character(planned$valued_from) && length(planned$valued_from) == 1L) planned$valued_from else planned$from
      request <- list(targets = asset_center_valuation_resolve(rows), execution_ref = NULL,
        start_date = valued_from, end_date = planned$until,
        valuation_policy = list(mode = "last_valid", max_age_days = NULL, age_unit = "calendar_days"),
        # Mit abgeleiteten Kalenderregeln kennt die Bewertung die Boersenfeiertage:
        # Sie zaehlen als geschlossene Handelstage, nicht als Quellluecken. Das
        # senkt die Zahl der Ersatzwerte deutlich, und die
        # verbliebenen sind echte Wechselkurslueecken (#283).
        target_currency = "EUR", use_rules = TRUE, use_saved_calendars = FALSE, max_age_days = 366L,
        market_exceptions = structure(list(), names = character()), fx_exceptions = structure(list(), names = character()),
        simple_absence_policy = FALSE)
      review <- asset_center_valuation_service$prepare(request)
      # Vor der Erstnotiz eines Assets gibt es keine Kurse und auch keinen Vorgaenger
      # zum Uebertragen. Solche Tage sind keine Luecke, sondern liegen vor der
      # Listung: die Bewertung beginnt beim ersten echten Kurs (#283, 21.09.2026).
      detail <- tryCatch(asset_center_valuation_service$detail(1L)$rows, error = function(error) list())
      native_start <- tryCatch({
        observed <- vapply(Filter(function(row) identical(row$price_native_status, "observed"), detail),
                           function(row) as.character(row$date), character(1L))
        if (length(observed)) min(observed) else NA_character_
      }, error = function(error) NA_character_)
      # Die Tagesliste wurde bisher zweimal geholt: einmal fuer die Erstnotiz,
      # einmal fuer die Anzeige. Bei voller Historie sind das grosse Mengen ueber die Prozessgrenze, und der Abruf selbst dauert nur eine Sekunde -
      # die Zeit steckt in diesen Aufrufen. Der zweite erfolgt jetzt nur noch,
      # wenn der Beginn tatsaechlich vorgerueckt ist und die Liste sich dadurch
      # aendert (#283).
      if (!is.na(native_start) && native_start > request$start_date) {
        request$start_date <- native_start
        review <- asset_center_valuation_service$prepare(request)
        detail <- tryCatch(asset_center_valuation_service$detail(1L)$rows, error = function(error) list())
      }
      list(status = "prepared", fetched = fetched, fetched_fx = fetched_fx, resolved_fx = resolved_fx,
           bound_closures = bound_closures, review = review, detail = detail,
           not_listed = not_listed, listed_since = planned$listed_since,
           valued_from = request$start_date, requested_from = planned$from, until = planned$until,
           summary = if (length(review$rows)) review$rows[[1L]] else NULL)
    }, error = function(error) list(status = "failed", code = asset_center_safe_code(error)))
    outcome$step <- step
    if (is.null(outcome$fetched)) outcome$fetched <- fetched
    if (is.null(outcome$fetched_fx)) outcome$fetched_fx <- fetched_fx
    if (is.null(outcome$resolved_fx)) outcome$resolved_fx <- resolved_fx
    outcome
  }
  asset_center_safe_code <- function(error) {
    code <- spotcore::desktop_product_safe_error_code_v1(error)
    if (!identical(code, "desktop_product_boundary_failed")) return(code)
    message <- tryCatch(conditionMessage(error), error = function(inner) "")
    if (is.character(message) && length(message) == 1L &&
        grepl("^[a-z][a-z0-9_]{5,80}$", message)) {
      recovered <- spotcore::desktop_product_safe_error_code_v1(
        structure(list(message = message, call = NULL, code = message),
                  class = c("spot_asset_center_error_v1", "error", "condition")))
      if (!identical(recovered, "desktop_product_boundary_failed")) return(recovered)
    }
    code
  }
  asset_center_fetch_reason <- function(code) {
    code <- as.character(code)
    provider_block <- if (exists("data_price_provider_block_text_v1", mode = "function")) data_price_provider_block_text_v1(code) else NULL
    if (!is.null(provider_block)) provider_block
    else if (grepl("source_not_listed", code, fixed = TRUE))
      "Der Titel war in diesem Zeitraum noch nicht notiert. Die Quelle führt ihn erst ab einem späteren Tag; die Planung beginnt ab dem nächsten Lauf dort."
    else if (grepl("_credential_unavailable", code, fixed = TRUE))
      "Für den Kursanbieter dieser Zuordnung ist kein bereiter Zugang eingetragen. Den Schlüssel unter Einstellungen → Plugins und Zugänge → Zugänge eintragen oder dort den Zustand prüfen."
    else if (grepl("_scheduled_disabled", code, fixed = TRUE))
      "Im täglichen Zeitlauf ist dieser Kursanbieter nicht freigegeben. Von Hand holt „Alles aktualisieren“ die Kurse; für den Zeitlauf unter Kursanbieter → Kosten „Im täglichen Zeitlauf abrufen“ einschalten."
    else if (grepl("_cost_limit", code, fixed = TRUE))
      "Die Obergrenze an Abrufen dieses Kursanbieters ist erreicht, oder er hat wegen zu vieler Abrufe abgewiesen. Morgen erneut versuchen oder die Grenze unter Kursanbieter → Kosten anheben."
    else if (grepl("source_rejected", code, fixed = TRUE))
      "Die Quelle hat den Abruf abgewiesen — typischerweise nach vielen Abrufen kurz hintereinander. Nichts ist beschädigt; später erneut versuchen."
    else if (grepl("review_input_invalid", code, fixed = TRUE))
      "Die Einrichtung dieses Assets stammt aus einer älteren Version und passt nicht mehr zum heutigen Stammdatenstand. Einmal „Tagesfrischen Kurs prüfen“ und „Jetzt einrichten“ ausführen; die vorhandenen Kurse bleiben erhalten."
    else if (grepl("review_fetch_interrupted", code, fixed = TRUE))
      "Ein früherer Abruf dieses Assets wurde durch einen Neustart des Rechners unterbrochen. Er ist jetzt als unterbrochen festgehalten; ein erneuter Lauf holt das Fehlende."
    # Seit rc.405 loest die Wiederherstellung einen Versuch ohne Ergebnis selbst auf, wenn er vor dem letzten Systemstart begann.
    # Uebrig bleibt nur ein Versuch, dessen Prozess danach mitten im Abruf endete: Ob er noch laeuft, ist nicht sicher zu sagen.
    # Bis rc.404 hiess es hier "wurde jetzt aufgeloest" - auch dann, wenn nichts aufgeloest war.
    else if (grepl("review_recovery_required", code, fixed = TRUE))
      "Ein früherer Abruf dieses Assets ist ohne Ergebnis geblieben: Sein Prozess endete mitten im Abruf. Solange nicht sicher ist, dass er nicht mehr läuft, bleibt das Asset gesperrt; nach einem Neustart des Rechners löst der nächste Lauf ihn auf."
    else if (grepl("review_response_invalid", code, fixed = TRUE))
      "Die Quelle hat eine unbrauchbare Antwort geliefert — kein Kurs, falsche Währung oder falsche Zeitzone. Das Symbol prüfen."
    else if (grepl("review_stage_invalid", code, fixed = TRUE))
      "Ein früherer Abruf dieses Assets ist halb geschrieben liegen geblieben. Im Expertenbereich „Kurshistorie einzeln abrufen“ wiederherstellen."
    else ""
  }
  asset_center_chain_target <- function(row) {
    resolved <- asset_center_valuation_resolve(list(row))[[1L]]
    if (is.null(resolved$mapping) || is.null(resolved$promotion_binding))
      stop("asset_center_sweep_mapping_incomplete", call. = FALSE)
    list(private = list(listing_ref = resolved$listing_ref,
                        listing_fingerprint = resolved$promotion_binding$listing_fingerprint,
                        mapping_id = resolved$promotion_binding$mapping_id,
                        mapping_revision = resolved$promotion_binding$mapping_revision,
                        mapping_fingerprint = resolved$promotion_binding$mapping_fingerprint),
         mapping = resolved$mapping, binding = resolved$promotion_binding)
  }
  asset_center_sweep_missing <- function(row, until, notations = NULL, period) {
    tryCatch({
      target <- asset_center_chain_target(row)
      from <- as.character(period$start)
      if (identical(period$mode, "from_first_trade")) {
        booked <- asset_center_first_booking(row$asset_ref)
        if (!is.null(booked) && !is.na(booked)) from <- as.character(booked)
      }
      # Bewertungs-Zeitleiste (rc.393): dieselben Grenzen wie in der Kette - eine fruehere Reihe zaehlt nur in ihrem Abschnitt.
      window <- asset_center_series_window(row)
      if (data_market_timeline_day_v1(window$from) && window$from > from) from <- window$from
      if (data_market_timeline_day_v1(window$until) && window$until < until) until <- window$until
      # Derselbe Beginn wie in der Kette, sonst gilt ein Asset dauerhaft als
      # unvollstaendig: Die Tage vor seiner Erstnotiz kann niemand nachliefern,
      # und der Lauf holte es jedes Mal erneut (#283, 25.09.2026).
      listed_since <- if (is.environment(notations)) {
        value <- get0(target$mapping$provider_symbol, envir = notations, inherits = FALSE)
        if (is.character(value) && length(value) == 1L) value else NA_character_
      } else {
        notation <- tryCatch(asset_center_market_review_service$notation(
          target$mapping$provider_symbol), error = function(error) NULL)
        if (is.list(notation) && is.character(notation$first_trade_date) &&
            length(notation$first_trade_date) == 1L) notation$first_trade_date else NA_character_
      }
      if (!is.na(listed_since) && listed_since > from) from <- listed_since
      if (from > until) return(0L)
      plan <- asset_center_market_plan_service$plan(target$private$listing_ref, from, until, "incremental")
      missing <- as.integer(plan$target_day_count)
      # Der Lauf plant Kurse und Wechselkurse getrennt; der Filter muss es
      # ebenso tun. Sonst gilt ein Asset mit vollstaendigen Kursen und
      # fehlenden FX-Tagen als vollstaendig und wird uebersprungen, waehrend die
      # Oberflaeche behauptet, seine Bewertung sei geschrieben
      # (Prüfung 25.09.2026).
      currency <- target$mapping$provider_currency
      if (!identical(currency, "EUR")) {
        fx <- tryCatch(as.integer(asset_center_fx_history_service$plan(currency, "EUR", from, until)$target_day_count),
          error = function(error) NA_integer_)
        if (is.na(fx)) return(NA_integer_)
        missing <- missing + fx
      }
      missing
    }, error = function(error) NA_integer_)
  }
  asset_center_sweep_queue <- function(only_missing, period) {
    # Mit den frueheren Kursreihen der Bewertungs-Zeitleiste: Jede wird bewertet, damit ihr Bereich besteht und ein Neuaufbau
    # des Bewertungsstands 1:1 gleich bleibt (rc.393). Ohne Zeitleiste dieselben Zeilen wie bisher.
    inventory <- asset_center_valuation_inventory(series = TRUE)
    ready <- Filter(function(row) identical(row$status, "history_ready_to_plan"), inventory$rows)
    # Wer nicht mitlaeuft, gehoert benannt. Sonst sieht der Eigentuemer am Ende
    # eine runde Zahl und weiss nicht, welche Assets sie nicht enthaelt.
    others <- Filter(function(row) !identical(row$status, "history_ready_to_plan"), inventory$rows)
    complete <- 0L
    if (isTRUE(only_missing) && length(ready)) {
      until <- as.character(min(as.Date(period$end), Sys.Date() - 1L))
      # Die Erstnotizen in einem Aufruf statt einem je Asset: das spart je Asset
      # einen Prozessstart (#283).
      notations <- tryCatch(asset_center_market_review_service$notations(), error = function(error) NULL)
      held <- new.env(parent = emptyenv())
      # Ein unklarer Befund haelt das Asset im Lauf: lieber einmal zuviel
      # bewerten als eine fehlende Kursreihe stillschweigend auslassen.
      keep <- vapply(ready, function(row) {
        missing <- asset_center_sweep_missing(row, until, notations, period)
        is.na(missing) || missing > 0L || asset_center_series_unvalued(row, held) || asset_center_series_absent(row, held)
      }, logical(1L))
      complete <- sum(!keep)
      ready <- ready[keep]
    }
    list(ready = ready, complete = as.integer(complete),
         excluded = table(vapply(others, function(row) as.character(row$status), character(1L))),
         # Reihen der Zeitleiste, die nicht laufen koennen, mit Grund (etwa ein spaeter ueberschriebenes Symbol).
         timeline_blocked = data_market_timeline_blocked_v1(others))
  }
  asset_center_sweep_reset <- function(asset_center_sweep) {
    asset_center_sweep$queue <- list(); asset_center_sweep$index <- 0L
    asset_center_sweep$results <- list(); asset_center_sweep$running <- FALSE
    asset_center_sweep$resume_at <- NULL; asset_center_sweep$attempts <- 0L
    asset_center_sweep$prepared <- FALSE; asset_center_sweep$period <- NULL
  }
  asset_center_sweep_step <- function(asset_center_sweep, period_inputs = function() NULL) {
    index <- asset_center_sweep$index + 1L
    queue <- asset_center_sweep$queue
    if (index > length(queue)) { asset_center_sweep$running <- FALSE; return(invisible(NULL)) }
    entry <- queue[[index]]
    attempt_once <- function() tryCatch({
      target <- asset_center_chain_target(entry)
      # Der Lauf nimmt den Modus aus dem Reiter, statt ihn festzunageln. Vorher
      # galt immer "ab erster Transaktion": Ein eingetragener Beginn stand
      # daneben und sah aus, als gaelte er - er wirkte nicht
      # (Festlegung 24.09.2026, #283).
      period <- asset_center_sweep$period
      if (is.null(period)) period <- period_inputs()
      if (is.null(period)) stop("asset_center_sweep_period_missing", call. = FALSE)
      window <- asset_center_series_window(entry)
      planned <- asset_center_chain_plan(entry$asset_ref, period$start, period$end, period$mode, "external_market",
        target = target, mapping_ref = entry$mapping_ref, window = window)
      if (isTRUE(planned$outside_window))
        list(status = "skipped", reason = paste0("Die Kursreihe ", entry$symbol, " gilt laut Bewertungs-Zeitleiste ",
          if (data_market_timeline_day_v1(window$from)) paste0("ab ", format(as.Date(window$from), "%d.%m.%Y"), " ") else "",
          if (data_market_timeline_day_v1(window$until)) paste0("bis ", format(as.Date(window$until), "%d.%m.%Y"), " ") else "",
          "und damit nicht im gewählten Zeitraum; es gibt nichts abzurufen oder zu bewerten."))
      else if (isTRUE(planned$period_invalid))
        list(status = "skipped", reason = paste0("Der Modus „vor erster Transaktion“ verlangt einen Beginn bis spätestens ",
          format(as.Date(planned$booked), "%d.%m.%Y"), "; eingetragen ist ", format(as.Date(planned$from), "%d.%m.%Y"), "."))
      else if (isTRUE(planned$not_completed_yet))
        list(status = "skipped", reason = paste0("Der erste Handelstag (", format(as.Date(planned$from), "%d.%m.%Y"),
          ") ist in der Zeitzone der Notierung noch nicht abgeschlossen; ein späterer Lauf holt ihn."))
      else if (isTRUE(planned$fx_missing))
        list(status = "skipped", reason = paste0("Wechselkurs-Paar ", planned$currency, "/EUR fehlt"))
      else {
        run <- asset_center_chain_run(entry$asset_ref, planned, target, require_selection = FALSE)
        if (identical(run$status, "failed")) run
        else if (identical(run$status, "not_listed"))
          list(status = "skipped", reason = paste0("Erstnotiz laut Quelle ",
            format(as.Date(run$listed_since), "%d.%m.%Y"), "; der gewählte Zeitraum endet davor."))
        else {
          written <- asset_center_valuation_service$complete(run$review, TRUE)
          list(status = "completed", numbers = asset_center_valuation_numbers(run$summary, run$detail),
               quality = written$valuation_status, from = run$valued_from, until = run$until,
               listed_since = run$listed_since, not_listed = run$not_listed,
               fetched = run$fetched, fetched_fx = run$fetched_fx)
        }
      }
    }, error = function(error) list(status = "failed", step = "Lauf",
      code = spotcore::desktop_product_safe_error_code_v1(error)))
    outcome <- attempt_once()
    # Ein unaufgelöster Abruf eines *anderen* Assets hat diesen Versuch
    # abgewiesen, nicht dieses Asset. Der Versuch selbst loest ihn auf, also
    # ist der zweite Anlauf der aussagekraeftige (#283, 23.09.2026).
    if (identical(outcome$status, "failed") &&
        grepl("review_recovery_required", as.character(outcome$code), fixed = TRUE)) {
      outcome <- attempt_once()
    }
    # Eine Abweisung der Quelle ist kein Fehler des Assets. Der Lauf wartet und
    # versucht dasselbe Asset erneut; bereits veroeffentlichte Kurse bleiben.
    throttled <- identical(outcome$status, "failed") &&
      grepl("source_rejected", as.character(outcome$code), fixed = TRUE)
    if (throttled && asset_center_sweep$attempts < length(ASSET_CENTER_SWEEP_BACKOFF)) {
      attempts <- asset_center_sweep$attempts + 1L
      asset_center_sweep$attempts <- attempts
      asset_center_sweep$resume_at <- Sys.time() + ASSET_CENTER_SWEEP_BACKOFF[[attempts]]
      return(invisible(NULL))
    }
    if (throttled) outcome <- list(status = "deferred",
      reason = "Die Quelle hat den Abruf mehrfach abgewiesen; bereits geholte Kurse bleiben erhalten.")
    outcome$asset_name <- data_market_timeline_row_name_v1(entry)
    asset_center_sweep$results <- c(asset_center_sweep$results, list(outcome))
    asset_center_sweep$index <- index
    asset_center_sweep$attempts <- 0L
    asset_center_sweep$resume_at <- NULL
    if (index >= length(queue)) asset_center_sweep$running <- FALSE
    invisible(NULL)
  }
  asset_center_valuation_numbers <- function(row, detail = NULL) {
    count <- function(key) if (is.null(row) || is.null(row[[key]])) 0L else as.integer(row[[key]])
    if (!is.null(detail) && length(detail)) {
      native <- 0L; calendar <- 0L; substituted <- 0L; open <- 0L
      # Bei einem rund um die Uhr gehandelten Wert in Fremdwaehrung fallen Kurs-
      # und Wechselkurskalender auseinander: Am Samstag gibt es den Kurs, aber
      # keinen Devisenkurs. Beides in eine Zahl zu werfen liest sich, als fehlten
      # die Kurse - dabei wurde oft nur die Umrechnungsbasis fortgeschrieben (#283).
      calendar_price <- 0L; calendar_rate <- 0L
      for (day in detail) {
        price <- if (is.null(day$price_basis)) "" else as.character(day$price_basis)
        rate <- if (is.null(day$fx_basis)) "identity" else as.character(day$fx_basis)
        price_carried <- !identical(price, "observed")
        rate_carried <- !rate %in% c("identity", "observed")
        if (is.null(day$target_decimal) || identical(day$valuation_status, "incomplete")) open <- open + 1L
        else if (isTRUE(day$substitution_used)) substituted <- substituted + 1L
        else if (price_carried || rate_carried) {
          calendar <- calendar + 1L
          if (price_carried) calendar_price <- calendar_price + 1L
          if (rate_carried && !price_carried) calendar_rate <- calendar_rate + 1L
        }
        else native <- native + 1L
      }
      adjusted <- sum(vapply(detail, function(day) identical(as.character(day$price_source_kind), "split_adjusted_close"), logical(1L)))
      return(list(native = native, calendar = calendar, calendar_price = calendar_price,
                  calendar_rate = calendar_rate, substituted = substituted, open = open,
                  adjusted = adjusted, valued = native + calendar + substituted))
    }
    list(native = max(0L, count("valued_day_count") - count("substituted_day_count")), calendar = 0L,
         calendar_price = 0L, calendar_rate = 0L,
         substituted = count("substituted_day_count"), open = count("unavailable_day_count"),
         adjusted = count("split_adjusted_day_count"), valued = count("valued_day_count"))
  }
  # Ein Schritt des Sammellaufs im eigenen Takt (Hintergrundlauf): drei Sekunden Abstand zwischen zwei Assets, wie im Reiter
  # Marktdaten - die Quelle weist Abrufe ab, die dicht aufeinander folgen (#283). Wartet der Lauf auf eine Abweisung, ruht er.
  asset_center_sweep_tick <- function(asset_center_sweep, now = Sys.time()) {
    if (!isTRUE(asset_center_sweep$running)) return(invisible(FALSE))
    resume_at <- asset_center_sweep$resume_at
    if (!is.null(resume_at) && now < resume_at) return(invisible(FALSE))
    last <- asset_center_sweep$stepped_at
    if (!is.null(last) && as.numeric(difftime(now, last, units = "secs")) < 3) return(invisible(FALSE))
    asset_center_sweep$stepped_at <- now
    asset_center_sweep_step(asset_center_sweep)
    invisible(TRUE)
  }
  list(valuation_inventory = asset_center_valuation_inventory, valuation_resolve = asset_center_valuation_resolve,
       resolve_open_fx = asset_center_resolve_open_fx, first_observed = asset_center_first_observed,
       completed_until = asset_center_completed_until, not_completed_plan = asset_center_not_completed_plan,
       chain_plan = asset_center_chain_plan, chain_run = asset_center_chain_run, safe_code = asset_center_safe_code,
       fetch_reason = asset_center_fetch_reason, chain_target = asset_center_chain_target, sweep_missing = asset_center_sweep_missing,
       sweep_queue = asset_center_sweep_queue, sweep_reset = asset_center_sweep_reset, sweep_step = asset_center_sweep_step,
       sweep_tick = asset_center_sweep_tick, valuation_numbers = asset_center_valuation_numbers, backoff = ASSET_CENTER_SWEEP_BACKOFF,
       timeline = asset_center_timeline, inventory_rows = asset_center_inventory_rows, series_window = asset_center_series_window,
       series_unvalued = asset_center_series_unvalued, series_absent = asset_center_series_absent)
}
