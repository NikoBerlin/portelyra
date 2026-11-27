data_asset_center_legacy_reference_v1 <- function() list(
  source_role = "superseded_legacy_product_reference",
  relative_path = "server_functions/asset_onboarding.R",
  referenced_function = "asset_onboarding_prefill_from_symbol_hit",
  adopted_pattern = "search_select_probe_visible_prefill_preview",
  copied_runtime_or_write_logic = FALSE
)

data_asset_center_error_codes_v1 <- function() c(
  "data_asset_center_catalog_invalid", "data_asset_center_selection_invalid",
  "data_asset_center_state_invalid"
)

data_asset_center_abort_v1 <- function(code) {
  if (!code %in% data_asset_center_error_codes_v1()) stop("data_asset_center_error_unregistered", call. = FALSE)
  stop(code, call. = FALSE)
}

data_asset_center_value_v1 <- function(primary, fallback) {
  if (is.null(primary) || length(primary) == 0L) fallback else primary
}

data_asset_center_safe_text_v1 <- function(value, maximum = 160L) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value) ||
      nchar(value, type = "bytes") > maximum || grepl("[[:cntrl:]]", value)) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  value
}

data_asset_center_choices_v1 <- function(rows, selected = "") {
  if (!is.list(rows)) data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  if (!length(rows)) return(c("Noch keine Assets" = ""))
  refs <- vapply(rows, function(row) data_asset_center_safe_text_v1(row$ref, 40L), character(1L))
  labels <- vapply(rows, function(row) data_asset_center_safe_text_v1(data_asset_center_value_v1(row$display_name, row$label), 120L), character(1L))
  if (anyDuplicated(refs)) data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  stats::setNames(refs, labels)
}

data_asset_center_selected_v1 <- function(catalog, asset_ref) {
  if (!is.list(catalog) || !identical(catalog$status, "ready") || !is.list(catalog$assets)) {
    data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  }
  if (identical(asset_ref, "")) return(NULL)
  selected <- Filter(function(row) identical(row$ref, asset_ref), catalog$assets)
  if (length(selected) != 1L) data_asset_center_abort_v1("data_asset_center_selection_invalid")
  selected[[1L]]
}

data_asset_center_provider_rows_v1 <- function(provider_catalog, asset_ref) {
  if (is.null(provider_catalog)) return(list())
  if (!is.list(provider_catalog) || !identical(provider_catalog$status, "ready") ||
      !is.list(provider_catalog$mappings) || isTRUE(provider_catalog$provider_access) ||
      isTRUE(provider_catalog$network_access) || isTRUE(provider_catalog$canonical_write)) {
    data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  }
  Filter(function(row) identical(row$asset_ref, asset_ref), provider_catalog$mappings)
}

data_asset_center_progress_v1 <- function(
  catalog, provider_catalog = NULL, asset_ref = "", tax_state = "not_initialized",
  market_state = "not_requested", activity_state = "not_checked"
) {
  asset <- data_asset_center_selected_v1(catalog, asset_ref)
  provider_rows <- if (is.null(asset)) list() else data_asset_center_provider_rows_v1(provider_catalog, asset_ref)
  provider_verified <- any(vapply(provider_rows, function(row) identical(row$verification_status, "verified"), logical(1L)))
  states <- c(
    master_data = if (is.null(asset)) "required" else "complete",
    provider = if (provider_verified) "complete" else if (length(provider_rows)) "needs_test" else "optional",
    tax = tax_state,
    market_history = market_state,
    activities = activity_state
  )
  labels <- c(
    master_data = "Stammdaten", provider = "Kurszuordnung", tax = "Steuerklassifikation",
    market_history = "Markthistorie", activities = "Buchungen"
  )
  state_labels <- c(
    required = "Erforderlich", complete = "Vollständig", optional = "Optional",
    needs_test = "Testabruf offen", not_initialized = "Noch nicht eingerichtet",
    not_configured = "Optional offen", not_requested = "Noch nicht angefordert",
    partial = "Teilweise", source_gap = "Quelllücke", not_checked = "Noch nicht gelesen",
    available = "Vorhanden", unavailable = "Nicht verfügbar", blocked = "Blockiert"
  )
  tone <- function(state) if (identical(state, "complete") || identical(state, "available")) "positive" else if (state %in% c("optional", "not_configured", "not_requested", "not_checked")) "neutral" else "warning"
  data.frame(
    Bereich = unname(labels[names(states)]),
    Status = unname(state_labels[states]),
    Ton = vapply(states, tone, character(1L)),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

data_market_fx_batch_ui_v1 <- function() shiny::tagList(
  shiny::tags$h3("Gemeinsamer Sammelabruf für Kurse und FX · Abruf, Prüfung und Veröffentlichung"),
  shiny::p("Zuerst gespeicherte Ergebnisse prüfen und veröffentlichen. Nur noch wartende Bereiche brauchen eine separate Abruffreigabe. Kalenderpflege, EUR-Bewertung und Portfolioabschluss folgen getrennt."),
  shiny::uiOutput("batch_status"),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton("batch_list", "Gespeicherte Sammelabrufe lesen"),
    shiny::selectInput("batch_saved", "Gespeicherten Sammelabruf auswählen", choices = c("Zuerst lesen" = "")),
    shiny::actionButton("batch_load", "Gespeicherten Sammelabruf ohne Abruf laden")),
  shiny::div(class = "pl-table-wrap", shiny::tableOutput("batch_progress")),
  shiny::uiOutput("batch_actions"),
  shiny::tags$details(
    shiny::tags$summary("Ursprünglicher Plan des Sammelabrufs · kein aktueller Abrufbedarf"),
    shiny::p("Dieser unveränderliche Plan zeigt die damaligen Bereiche und geplanten Aufrufe. Maßgeblich sind der aktuelle Fortschritt und die ausdrücklich ausgewählte Aktion."),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("batch_bound_ranges")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("batch_binding_targets")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("batch_blockers")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("batch_calendar_dispositions"))),
  shiny::tags$fieldset(id="batch_review_panel",
    shiny::tags$legend("Gespeicherte Ergebnisse prüfen und veröffentlichen · kein Abruf"),
    shiny::uiOutput("batch_review_selection"),
    shiny::uiOutput("batch_review_action"),
    shiny::uiOutput("batch_review_details"),
    shiny::uiOutput("batch_publication_actions")),
  shiny::tags$fieldset(id="batch_fetch_panel",
    shiny::tags$legend("Wartende Bereiche abrufen · externer Zugriff"),
    shiny::p("Diese Freigabe gilt nur für neue Abrufe, niemals für die Veröffentlichung einer Prüfung. Eine Auswahländerung verwirft bestehende Freigaben."),
    shiny::uiOutput("batch_fetch_selection"),
    shiny::uiOutput("batch_fetch_actions"))
)

data_asset_center_market_inventory_v1 <- function(catalog, provider_catalog = NULL, timeline = NULL) {
  if (!is.list(catalog) || !identical(catalog$status, "ready") || !is.list(catalog$assets)) {
    data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  }
  if (!is.null(provider_catalog) && (!is.list(provider_catalog) ||
      !identical(provider_catalog$status, "ready") || !is.list(provider_catalog$mappings) ||
      isTRUE(provider_catalog$provider_access) || isTRUE(provider_catalog$network_access) ||
      isTRUE(provider_catalog$canonical_write))) {
    data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  }
  if (!is.null(timeline) && (!is.list(timeline) || !identical(timeline$status, "ready") || !is.list(timeline$assets))) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  # Bewertungs-Zeitleiste (rc.393, data_market_timeline_v1.R): Fuer ein Asset mit Zeitleiste steht je Marktreihe der Zeitleiste
  # eine Zeile da - auch wenn es heute eigene Kurse traegt. Ohne Zeitleiste (NULL) bleibt alles wie bisher.
  timeline_entry <- function(asset) if (is.null(timeline)) NULL else timeline$assets[[asset$ref]]
  assets <- Filter(function(row) identical(row$status, "active") &&
    (identical(row$valuation_method, "external_market") || !is.null(timeline_entry(row))), catalog$assets)
  rows <- lapply(assets, function(asset) {
    mappings <- if (is.null(provider_catalog)) list() else Filter(function(row) {
      identical(row$asset_ref, asset$ref) && identical(row$capability, "daily_history")
    }, provider_catalog$mappings)
    entry <- timeline_entry(asset)
    if (!is.null(entry)) return(data_asset_center_timeline_rows_v1(asset, mappings, entry))
    rank <- function(row) {
      exact_currency <- identical(row$provider_currency, asset$price_currency)
      if (isTRUE(row$enabled) && identical(row$verification_status, "verified") && exact_currency) 1L
      else if (isTRUE(row$enabled) && identical(row$verification_status, "verified")) 2L
      else if (identical(row$verification_status, "unverified")) 3L else 4L
    }
    chosen <- NULL
    if (length(mappings)) {
      # Ohne Zeitleiste hat bei Gleichstand Yahoo als Vorgabe Vorrang (rc.394): Eine zweite Zuordnung, etwa bei EODHD, uebernimmt
      # nicht still (alphabetisch gewaenne sonst "eodhd"); wirksam wird sie ueber "Bewertung ueber die Zeit".
      order_key <- order(
        vapply(mappings, rank, integer(1L)),
        vapply(mappings, function(row) !identical(row$provider_id, "yahoo"), logical(1L)),
        vapply(mappings, function(row) paste(row$provider_id, row$provider_symbol, row$ref), character(1L))
      )
      chosen <- mappings[[order_key[[1L]]]]
    }
    status <- if (is.null(chosen)) "mapping_missing" else if (
      isTRUE(chosen$enabled) && identical(chosen$verification_status, "verified")
    ) "history_ready_to_plan" else if (identical(chosen$verification_status, "unverified")) {
      "mapping_test_required"
    } else "mapping_disabled"
    provider_currency_differs <- !is.null(chosen) && !identical(chosen$provider_currency, asset$price_currency)
    labels <- c(
      mapping_missing = "Kurszuordnung fehlt", history_ready_to_plan = "Historie planbar",
      mapping_test_required = "Testabruf offen", mapping_disabled = "Kurszuordnung deaktiviert"
    )
    next_steps <- c(
      mapping_missing = "Yahoo-Zuordnung suchen", history_ready_to_plan = "Fehlenden Zeitraum planen",
      mapping_test_required = "Zuordnung testen und aktivieren",
      # Aus „deaktiviert“ führt kein Testabruf heraus: Der Testabruf verlangt
      # „ungeprüft“, und eine zweite Zuordnung zum selben Asset wird als Dublette
      # abgewiesen. Der Weg ist „überarbeiten“ (#283, 23.09.2026).
      mapping_disabled = "Zuordnung überarbeiten, dann testen und aktivieren"
    )
    list(list(
      asset_ref = asset$ref, mapping_ref = if (is.null(chosen)) NULL else chosen$ref,
      asset_name = asset$display_name, asset_type = asset$asset_type,
      price_currency = asset$price_currency,
      provider = if (is.null(chosen)) "—" else chosen$provider_id,
      symbol = if (is.null(chosen)) "—" else chosen$provider_symbol,
      provider_currency = if (is.null(chosen)) "—" else chosen$provider_currency,
      provider_currency_differs = provider_currency_differs,
      status = status,
      status_label = if (identical(status, "history_ready_to_plan") && provider_currency_differs) "Historie planbar · FX später erforderlich" else unname(labels[[status]]),
      next_step = unname(next_steps[[status]])
    ))
  })
  rows <- unlist(rows, recursive = FALSE)
  if (is.null(rows)) rows <- list()
  levels <- c("mapping_missing", "mapping_test_required", "mapping_disabled", "history_ready_to_plan")
  if (!is.null(timeline)) levels <- c(levels, "timeline_series_unmapped")
  value <- list(
    status = "ready", asset_count = length(unique(vapply(rows, `[[`, character(1L), "asset_ref"))), rows = rows,
    counts = as.list(table(factor(vapply(rows, `[[`, character(1L), "status"), levels = levels))),
    provider_access = FALSE, network_access = FALSE, canonical_write = FALSE,
    market_history_write = FALSE
  )
  if (!is.null(timeline)) value$timeline_series_count <- sum(vapply(rows, function(row) !is.null(row$series_role), logical(1L)))
  value
}

# Die Zeilen eines Assets mit Bewertungs-Zeitleiste: je Marktreihe eine, in der Reihenfolge der Abschnitte. Gefunden wird die
# Reihe ueber die heutige Zuordnung mit genau diesem Anbieter und Symbol - der Kern bewertet nur die aktuelle Revision einer
# Zuordnung. Wurde das Symbol einer Zuordnung spaeter ueberschrieben, gibt es fuer die alte Reihe keine Zuordnung mehr: Sie
# laesst sich weder abrufen noch bewerten, und das steht mit Grund in der Zeile (Status timeline_series_unmapped), statt still
# zu entfallen. Laufend ("current") ist die Reihe des letzten Abschnitts, sofern das Asset auch laut Stammdaten am Markt bewertet
# wird; jede andere ist "earlier" und wird nur in den Grenzen ihrer Abschnitte abgerufen.
data_asset_center_timeline_rows_v1 <- function(asset, mappings, entry) {
  market_today <- identical(asset$valuation_method, "external_market")
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  lapply(entry$series, function(series) {
    role <- if (identical(series$role, "current") && market_today) "current" else "earlier"
    matches <- Filter(function(row) identical(row$provider_id, series$provider_id) &&
      identical(row$provider_symbol, series$provider_symbol), mappings)
    chosen <- if (length(matches)) matches[[1L]] else NULL
    status <- if (is.null(chosen)) "timeline_series_unmapped" else if (
      isTRUE(chosen$enabled) && identical(chosen$verification_status, "verified")
    ) "history_ready_to_plan" else if (identical(chosen$verification_status, "unverified")) {
      "mapping_test_required"
    } else "mapping_disabled"
    provider_currency_differs <- !is.null(chosen) && !identical(chosen$provider_currency, asset$price_currency)
    labels <- c(
      timeline_series_unmapped = "Kursreihe der Zeitleiste ohne Zuordnung", history_ready_to_plan = "Historie planbar",
      mapping_test_required = "Testabruf offen", mapping_disabled = "Kurszuordnung deaktiviert"
    )
    next_steps <- c(
      timeline_series_unmapped = "Nicht abrufbar: Zeitleiste oder Zuordnung prüfen",
      history_ready_to_plan = if (identical(role, "earlier")) "Nur fehlende Tage im Abschnitt holen, dann bewerten" else "Fehlenden Zeitraum planen",
      mapping_test_required = "Zuordnung testen und aktivieren",
      mapping_disabled = "Zuordnung überarbeiten, dann testen und aktivieren"
    )
    label <- if (identical(status, "history_ready_to_plan") && provider_currency_differs) "Historie planbar · FX später erforderlich" else unname(labels[[status]])
    if (identical(role, "earlier")) label <- paste0(
      if (is.na(series$valid_until)) "Kursreihe der Zeitleiste" else paste0("Frühere Kursreihe bis ", day(series$valid_until)), " · ", label)
    same_provider <- Filter(function(row) identical(row$provider_id, series$provider_id), mappings)
    reason <- if (identical(status, "history_ready_to_plan")) "" else if (is.null(chosen) && length(same_provider)) {
      paste0("Die Zuordnung zu ", series$provider_id, " trägt heute das Symbol ", same_provider[[1L]]$provider_symbol, " statt ",
             series$provider_symbol, ". Die Reihe ", series$provider_symbol, " lässt sich deshalb weder abrufen noch bewerten; ",
             "ihre Tage stehen nur noch im Bewertungsstand, ein Neuaufbau des Stands kann sie nicht wiederherstellen.")
    } else if (is.null(chosen)) {
      paste0("Für ", series$provider_id, " gibt es keine Zuordnung mit dem Symbol ", series$provider_symbol, ". Die Reihe lässt sich ",
             "weder abrufen noch bewerten; ihre Tage stehen nur noch im Bewertungsstand, ein Neuaufbau des Stands kann sie nicht wiederherstellen.")
    } else if (identical(status, "mapping_test_required")) {
      paste0("Die Zuordnung ", series$provider_id, " · ", series$provider_symbol, " ist noch nicht geprüft; bis dahin wird die Reihe weder abgerufen noch bewertet.")
    } else {
      paste0("Die Zuordnung ", series$provider_id, " · ", series$provider_symbol, " ist deaktiviert; die Reihe wird weder abgerufen noch bewertet.")
    }
    list(
      asset_ref = asset$ref, mapping_ref = if (is.null(chosen)) NULL else chosen$ref,
      asset_name = asset$display_name, asset_type = asset$asset_type,
      price_currency = asset$price_currency,
      provider = series$provider_id, symbol = series$provider_symbol,
      provider_currency = if (is.null(chosen)) "—" else chosen$provider_currency,
      provider_currency_differs = provider_currency_differs,
      status = status, status_label = label, next_step = unname(next_steps[[status]]),
      series_role = role, valid_from = series$valid_from, valid_until = series$valid_until,
      provider_cost = if (is.character(series$cost) && length(series$cost) == 1L) series$cost else "unknown",
      series_reason = reason
    )
  })
}

data_asset_center_fx_demand_v1 <- function(inventory, target_currency = "EUR") {
  if (!is.list(inventory) || !identical(inventory$status, "ready") ||
      !is.list(inventory$rows) || !is.character(target_currency) ||
      length(target_currency) != 1L || !grepl("^[A-Z]{3}$", target_currency) ||
      isTRUE(inventory$provider_access) || isTRUE(inventory$network_access) ||
      isTRUE(inventory$canonical_write) || isTRUE(inventory$market_history_write)) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  candidates <- Filter(function(row) {
    identical(row$status, "history_ready_to_plan") &&
      grepl("^[A-Z]{3}$", row$provider_currency) &&
      !identical(row$provider_currency, target_currency)
  }, inventory$rows)
  sources <- sort(unique(vapply(candidates, `[[`, character(1L), "provider_currency")))
  rows <- lapply(sources, function(source) {
    consumers <- Filter(function(row) identical(row$provider_currency, source), candidates)
    list(
      source_currency = source, target_currency = target_currency,
      consumer_count = length(consumers),
      consumer_names = sort(unique(vapply(consumers, `[[`, character(1L), "asset_name"))),
      status = "pair_missing", next_step = "FX-Paar einrichten"
    )
  })
  list(
    status = "ready", target_currency = target_currency,
    pair_count = length(rows), rows = rows,
    provider_access = FALSE, network_access = FALSE,
    canonical_write = FALSE, fx_history_write = FALSE
  )
}

data_asset_center_fx_demand_frame_v1 <- function(demand) {
  if (!is.list(demand) || !identical(demand$status, "ready") || !is.list(demand$rows) ||
      isTRUE(demand$provider_access) || isTRUE(demand$network_access) ||
      isTRUE(demand$canonical_write) || isTRUE(demand$fx_history_write)) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  if (!length(demand$rows)) return(data.frame())
  data.frame(
    Von = vapply(demand$rows, `[[`, character(1L), "source_currency"),
    Nach = vapply(demand$rows, `[[`, character(1L), "target_currency"),
    `Verwendet von` = vapply(demand$rows, `[[`, integer(1L), "consumer_count"),
    Verbraucher = vapply(demand$rows, function(row) paste(row$consumer_names, collapse = ", "), character(1L)),
    Status = pl_label_v1(c(pair_missing = "FX-Paar fehlt", ready = "bereit"), vapply(demand$rows, `[[`, character(1L), "status")),
    `Nächster Schritt` = vapply(demand$rows, `[[`, character(1L), "next_step"),
    stringsAsFactors = FALSE, check.names = FALSE
  )
}

data_asset_center_market_inventory_frame_v1 <- function(inventory) {
  if (!is.list(inventory) || !identical(inventory$status, "ready") || !is.list(inventory$rows) ||
      isTRUE(inventory$provider_access) || isTRUE(inventory$network_access) ||
      isTRUE(inventory$canonical_write) || isTRUE(inventory$market_history_write)) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  if (!length(inventory$rows)) return(data.frame())
  data.frame(
    Asset = vapply(inventory$rows, `[[`, character(1L), "asset_name"),
    Typ = pl_label_v1(PL_ASSET_TYPE_LABELS_V1, vapply(inventory$rows, `[[`, character(1L), "asset_type")),
    Preiswährung = vapply(inventory$rows, `[[`, character(1L), "price_currency"),
    Anbieter = pl_price_provider_label_v1(vapply(inventory$rows, `[[`, character(1L), "provider")),
    Symbol = vapply(inventory$rows, `[[`, character(1L), "symbol"),
    Providerwährung = vapply(inventory$rows, `[[`, character(1L), "provider_currency"),
    Status = vapply(inventory$rows, `[[`, character(1L), "status_label"),
    `Nächster Schritt` = vapply(inventory$rows, `[[`, character(1L), "next_step"),
    stringsAsFactors = FALSE, check.names = FALSE
  )
}

data_asset_center_market_inventory_coverage_frame_v1 <- function(inventory, market_coverage=NULL, fx_coverage=NULL) {
  base <- data_asset_center_market_inventory_frame_v1(inventory)
  if (!nrow(base)) return(base)
  valid_coverage <- function(value, write_key) is.list(value) && identical(value$status,"ready") &&
    is.list(value$rows) && !isTRUE(value$provider_access) && !isTRUE(value$network_access) &&
    !isTRUE(value$canonical_write) && !isTRUE(value[[write_key]])
  if (!is.null(market_coverage) && !valid_coverage(market_coverage,"market_history_write")) data_asset_center_abort_v1("data_asset_center_state_invalid")
  if (!is.null(fx_coverage) && !valid_coverage(fx_coverage,"fx_history_write")) data_asset_center_abort_v1("data_asset_center_state_invalid")
  one <- function(rows, predicate) {
    matches <- Filter(predicate, rows)
    if (length(matches)>1L) data_asset_center_abort_v1("data_asset_center_state_invalid")
    if (length(matches)) matches[[1L]] else NULL
  }
  market_rows <- if (is.null(market_coverage)) list() else market_coverage$rows
  fx_rows <- if (is.null(fx_coverage)) list() else fx_coverage$rows
  details <- lapply(inventory$rows,function(row){
    market <- one(market_rows,function(candidate)identical(candidate$asset_ref,row$asset_ref))
    market_from <- if(is.null(market)||is.null(market$first_covered_date)) "—" else pl_day_v1(market$first_covered_date)
    market_to <- if(is.null(market)||is.null(market$last_covered_date)) "—" else pl_day_v1(market$last_covered_date)
    market_status <- if(!identical(row$status,"history_ready_to_plan")) row$status_label else if(is.null(market)) {
      "Abdeckung noch nicht geprüft"
    } else if(identical(market$coverage_status,"complete")) {
      "vollständig im geprüften Zeitraum"
    } else paste0(if(identical(market$coverage_status,"partial"))"teilweise" else if(identical(market$coverage_status,"missing"))"keine Daten" else market$coverage_status," · ",market$missing_day_count," fehlend · ",market$source_gap_day_count," Quelllücken")
    next_step <- if(!identical(row$status,"history_ready_to_plan")) row$next_step else if(is.null(market)) {
      "Gespeicherte Abdeckung prüfen"
    } else if(market$missing_day_count>0L) {
      "Fehlenden Zeitraum planen"
    } else if(market$source_gap_day_count>0L) "Quelllücken prüfen" else "Keine Historienlücke"
    if(!isTRUE(row$provider_currency_differs)) {
      fx_status <- "nicht erforderlich"
      conversion <- "nicht erforderlich"
    } else {
      fx <- one(fx_rows,function(candidate)identical(candidate$source_currency,row$provider_currency)&&identical(candidate$target_currency,row$price_currency))
      route <- paste0(row$provider_currency,"→",row$price_currency)
      if(is.null(fx)) {
        fx_status <- paste(route,"· Abdeckung noch nicht geprüft")
      } else if(identical(fx$coverage_status,"pair_missing")||identical(fx$route_kind,"unbound")) {
        fx_status <- paste(route,"· FX-Paar fehlt")
      } else {
        checked <- if(is.null(fx_coverage$start_date)||is.null(fx_coverage$end_date)) "" else paste0(" · geprüft ",pl_day_v1(fx_coverage$start_date)," bis ",pl_day_v1(fx_coverage$end_date))
        fx_label <- if(identical(fx$coverage_status,"complete"))"vollständig" else if(identical(fx$coverage_status,"partial"))"teilweise" else fx$coverage_status
        fx_status <- paste0(route," · ",fx_label,checked," · ",fx$missing_day_count," fehlend · ",fx$source_gap_day_count," Quelllücken")
      }
      conversion <- "erforderlich · noch nicht erfolgt"
    }
    list(market_from=market_from,market_to=market_to,market_status=market_status,fx_status=fx_status,conversion=conversion,next_step=next_step)
  })
  data.frame(
    Asset=base$Asset, Typ=base$Typ, Preiswährung=base$Preiswährung,
    Anbieter=base$Anbieter, Symbol=base$Symbol, Providerwährung=base$Providerwährung,
    `Kursdaten von`=vapply(details,`[[`,character(1L),"market_from"),
    `Kursdaten bis`=vapply(details,`[[`,character(1L),"market_to"),
    Historienstatus=vapply(details,`[[`,character(1L),"market_status"),
    `FX-Historie`=vapply(details,`[[`,character(1L),"fx_status"),
    `FX-Umrechnung`=vapply(details,`[[`,character(1L),"conversion"),
    `Nächster Schritt`=vapply(details,`[[`,character(1L),"next_step"),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_asset_center_optional_calendar_gap_read_v1<-function(read_operation){
  if(!is.function(read_operation))data_asset_center_abort_v1("data_asset_center_state_invalid")
  tryCatch({
    value<-read_operation()
    if(!is.list(value)||!is.list(value$rows)||isTRUE(value$provider_access)||isTRUE(value$network_access)||isTRUE(value$history_write)||isTRUE(value$canonical_write))data_asset_center_abort_v1("data_asset_center_state_invalid")
    list(status="ready",value=value,error_code=NULL)
  },error=function(error){
    code<-if(is.character(error$code)&&length(error$code)==1L&&grepl("^(data|desktop)_market_calendar_gap_[a-z_]+$",error$code))error$code else "data_market_calendar_gap_boundary_failed"
    list(status="blocked",value=list(status="blocked",rows=list(),error_code=code,provider_access=FALSE,network_access=FALSE,history_write=FALSE,canonical_write=FALSE),error_code=code)
  })
}

data_asset_center_market_fx_completion_plan_v1 <- function(inventory, market_coverage=NULL, fx_coverage=NULL, required_start_date, as_of_date, target_currency="EUR") {
  data_asset_center_market_inventory_coverage_frame_v1(inventory,market_coverage,fx_coverage)
  valid_date<-function(value)is.character(value)&&length(value)==1L&&!is.na(value)&&grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",value)&&!is.na(as.Date(value,format="%Y-%m-%d"))
  if(!valid_date(required_start_date)||!valid_date(as_of_date)||as.Date(as_of_date)<as.Date(required_start_date)||!is.character(target_currency)||length(target_currency)!=1L||!grepl("^[A-Z]{3}$",target_currency))data_asset_center_abort_v1("data_asset_center_state_invalid")
  market_rows<-if(is.null(market_coverage))list()else market_coverage$rows
  fx_rows<-if(is.null(fx_coverage))list()else fx_coverage$rows
  one<-function(rows,predicate){matches<-Filter(predicate,rows);if(length(matches)>1L)data_asset_center_abort_v1("data_asset_center_state_invalid");if(length(matches))matches[[1L]]else NULL}
  priority<-c(mapping_required=1L,coverage_required=2L,market_history_required=3L,market_source_gap_review=4L,fx_pair_required=5L,fx_history_required=6L,fx_source_gap_review=7L,ready_for_snapshot=8L)
  labels<-c(mapping_required="Kurszuordnung vervollständigen",coverage_required="Gespeicherte Abdeckung der Kurse und FX prüfen",market_history_required="Fehlende Markthistorie planen",market_source_gap_review="Quelllücken der Kurse prüfen",fx_pair_required="FX-Paar einrichten",fx_history_required="Fehlende FX-Historie planen",fx_source_gap_review="FX-Quelllücken prüfen",ready_for_snapshot="Zum Snapshot-Abschluss weitergeben")
  rows<-lapply(inventory$rows,function(row){
    market<-one(market_rows,function(candidate)identical(candidate$asset_ref,row$asset_ref));fx<-NULL
    disposition<-if(!identical(row$status,"history_ready_to_plan"))"mapping_required" else if(is.null(market))"coverage_required" else if(market$missing_day_count>0L)"market_history_required" else if(market$source_gap_day_count>0L)"market_source_gap_review" else "ready_for_snapshot"
    fx_required<-identical(row$status,"history_ready_to_plan")&&!identical(row$provider_currency,target_currency)
    fx_disposition<-if(identical(row$status,"history_ready_to_plan"))"ready_for_snapshot"else "mapping_required"
    if(fx_required){
      fx<-one(fx_rows,function(candidate)identical(candidate$source_currency,row$provider_currency)&&identical(candidate$target_currency,target_currency))
      fx_disposition<-if(is.null(fx))"coverage_required" else if(identical(fx$coverage_status,"pair_missing")||identical(fx$route_kind,"unbound"))"fx_pair_required" else if(fx$missing_day_count>0L)"fx_history_required" else if(fx$source_gap_day_count>0L)"fx_source_gap_review" else "ready_for_snapshot"
    }
    if(identical(disposition,"ready_for_snapshot"))disposition<-fx_disposition
    list(asset_ref=row$asset_ref,asset_name=row$asset_name,provider_currency=row$provider_currency,target_currency=target_currency,disposition=disposition,fx_disposition=fx_disposition,next_action=unname(labels[[disposition]]),market_missing_day_count=if(is.null(market))NA_integer_ else market$missing_day_count,market_source_gap_day_count=if(is.null(market))NA_integer_ else market$source_gap_day_count,fx_missing_day_count=if(is.null(fx))if(fx_required)NA_integer_ else 0L else fx$missing_day_count,fx_source_gap_day_count=if(is.null(fx))if(fx_required)NA_integer_ else 0L else fx$source_gap_day_count)
  })
  dispositions<-vapply(rows,`[[`,character(1L),"disposition");selected<-if(length(rows))rows[[order(unname(priority[dispositions]),vapply(rows,`[[`,character(1L),"asset_name"))[[1L]]]]else NULL
  list(contract_version="data_asset_center_market_fx_completion_plan_v1",status=if(!length(rows)||all(dispositions=="ready_for_snapshot"))"ready_for_snapshot"else "action_required",required_start_date=required_start_date,as_of_date=as_of_date,target_currency=target_currency,asset_count=length(rows),rows=rows,counts=as.list(table(factor(dispositions,levels=names(priority)))),next_action=if(is.null(selected))list(code="ready_for_snapshot",label=unname(labels[["ready_for_snapshot"]]),asset_ref=NULL,asset_name=NULL)else list(code=selected$disposition,label=selected$next_action,asset_ref=selected$asset_ref,asset_name=selected$asset_name),silent_drop_count=0L,provider_access=FALSE,network_access=FALSE,market_history_write=FALSE,fx_history_write=FALSE,canonical_write=FALSE)
}

data_asset_center_market_fx_completion_plan_frame_v1<-function(plan){
  if(!is.list(plan)||!identical(plan$contract_version,"data_asset_center_market_fx_completion_plan_v1")||!is.list(plan$rows)||!identical(plan$silent_drop_count,0L)||isTRUE(plan$provider_access)||isTRUE(plan$network_access)||isTRUE(plan$market_history_write)||isTRUE(plan$fx_history_write)||isTRUE(plan$canonical_write))data_asset_center_abort_v1("data_asset_center_state_invalid")
  if(!length(plan$rows))return(data.frame())
  count<-function(row,key)if(is.na(row[[key]]))"noch nicht geprüft"else as.character(row[[key]])
  data.frame(Asset=vapply(plan$rows,`[[`,character(1L),"asset_name"),Disposition=vapply(plan$rows,`[[`,character(1L),"disposition"),FX_Disposition=vapply(plan$rows,`[[`,character(1L),"fx_disposition"),Market_fehlend=vapply(plan$rows,count,character(1L),"market_missing_day_count"),Market_Quelllücken=vapply(plan$rows,count,character(1L),"market_source_gap_day_count"),FX_fehlend=vapply(plan$rows,count,character(1L),"fx_missing_day_count"),FX_Quelllücken=vapply(plan$rows,count,character(1L),"fx_source_gap_day_count"),`Nächste Aktion`=vapply(plan$rows,`[[`,character(1L),"next_action"),check.names=FALSE)
}

data_asset_center_market_fx_fetch_batch_preview_v1<-function(plan,market_coverage,fx_coverage,created_at_utc){
  if(!is.list(plan)||!identical(plan$contract_version,"data_asset_center_market_fx_completion_plan_v1")||!is.list(plan$rows)||!identical(plan$silent_drop_count,0L)||!is.character(created_at_utc)||length(created_at_utc)!=1L||!grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",created_at_utc))data_asset_center_abort_v1("data_asset_center_state_invalid")
  market_rows<-if(is.null(market_coverage))list()else market_coverage$rows;fx_rows<-if(is.null(fx_coverage))list()else fx_coverage$rows
  items<-list();add<-function(value){items[[length(items)+1L]]<<-value}
  for(row in plan$rows){
    if(identical(row$disposition,"market_history_required")){
      matches<-Filter(function(value)identical(value$asset_ref,row$asset_ref),market_rows);if(length(matches)!=1L)data_asset_center_abort_v1("data_asset_center_state_invalid")
      for(range in matches[[1L]]$missing_ranges)add(list(kind="market",consumer=row$asset_name,consumer_ref=row$asset_ref,source_currency=row$provider_currency,target_currency=row$target_currency,route=paste0(row$provider_currency,"→",row$target_currency),start_date=range$start_date,end_date=range$end_date,calendar_day_count=as.integer(range$calendar_day_count),provider_call_count=1L,disposition="fetch_once"))
    }
  }
  fx_keys<-character()
  for(row in plan$rows){
    if(!identical(row$fx_disposition,"fx_history_required"))next
    key<-paste(row$provider_currency,row$target_currency,sep="→");if(key%in%fx_keys)next;fx_keys<-c(fx_keys,key)
    matches<-Filter(function(value)identical(value$source_currency,row$provider_currency)&&identical(value$target_currency,row$target_currency),fx_rows);if(length(matches)!=1L)data_asset_center_abort_v1("data_asset_center_state_invalid")
    for(range in matches[[1L]]$missing_ranges)add(list(kind="fx",consumer=key,consumer_ref=NULL,source_currency=row$provider_currency,target_currency=row$target_currency,route=key,start_date=range$start_date,end_date=range$end_date,calendar_day_count=as.integer(range$calendar_day_count),provider_call_count=1L,disposition="fetch_once"))
  }
  blockers<-lapply(Filter(function(row)!row$disposition%in%c("market_history_required","fx_history_required","ready_for_snapshot"),plan$rows),function(row)list(asset_name=row$asset_name,disposition=row$disposition,next_action=row$next_action))
  fx_blockers<-Filter(function(row)!row$fx_disposition%in%c("fx_history_required","ready_for_snapshot")&&!identical(row$fx_disposition,row$disposition),plan$rows)
  blockers<-c(blockers,lapply(fx_blockers,function(row)list(asset_name=row$asset_name,disposition=row$fx_disposition,next_action=paste("FX separat klären:",row$fx_disposition))))
  public<-list(contract_version="data_asset_center_market_fx_fetch_batch_preview_v1",status=if(length(items))"ready_for_confirmation"else if(length(blockers))"blocked_by_prerequisites"else"nothing_to_fetch",created_at_utc=created_at_utc,required_start_date=plan$required_start_date,as_of_date=plan$as_of_date,target_currency=plan$target_currency,item_count=length(items),provider_call_count=sum(vapply(items,`[[`,integer(1L),"provider_call_count")),market_range_count=sum(vapply(items,function(item)identical(item$kind,"market"),logical(1L))),fx_range_count=sum(vapply(items,function(item)identical(item$kind,"fx"),logical(1L))),items=items,blocker_count=length(blockers),blockers=blockers,explicit_asset_disposition_count=length(plan$rows),silent_drop_count=0L,confirmation_required=length(items)>0L,automatic_retry=FALSE,provider_fallback=FALSE,provider_access=FALSE,network_access=FALSE,market_history_write=FALSE,fx_history_write=FALSE,canonical_write=FALSE)
  public$batch_fingerprint<-digest::digest(charToRaw(enc2utf8(as.character(jsonlite::toJSON(public,auto_unbox=TRUE,null="null",digits=NA)))),algo="sha256",serialize=FALSE)
  public
}

data_asset_center_market_fx_fetch_batch_frame_v1<-function(preview){
  if(!is.list(preview)||!identical(preview$contract_version,"data_asset_center_market_fx_fetch_batch_preview_v1")||!is.list(preview$items)||!identical(preview$silent_drop_count,0L)||isTRUE(preview$provider_access)||isTRUE(preview$network_access)||isTRUE(preview$market_history_write)||isTRUE(preview$fx_history_write)||isTRUE(preview$canonical_write))data_asset_center_abort_v1("data_asset_center_state_invalid")
  if(!length(preview$items))return(data.frame())
  data.frame(Bereich=vapply(preview$items,function(item)if(identical(item$kind,"market"))"Markthistorie"else"FX-Historie",character(1L)),Verwendet_von=vapply(preview$items,`[[`,character(1L),"consumer"),Route=vapply(preview$items,`[[`,character(1L),"route"),Von=vapply(preview$items,`[[`,character(1L),"start_date"),Bis=vapply(preview$items,`[[`,character(1L),"end_date"),Kalendertage=vapply(preview$items,`[[`,integer(1L),"calendar_day_count"),Provideraufrufe=vapply(preview$items,`[[`,integer(1L),"provider_call_count"),Disposition="genau einmal abrufen",check.names=FALSE)
}

data_asset_center_history_ranges_v1 <- function(plan) {
  if (!is.list(plan) || !identical(plan$status, "ready") || !is.list(plan$ranges) ||
      !is.numeric(plan$range_count) || length(plan$range_count) != 1L ||
      is.na(plan$range_count) || !is.finite(plan$range_count) ||
      plan$range_count != trunc(plan$range_count) || plan$range_count < 0L ||
      plan$range_count > .Machine$integer.max ||
      as.integer(plan$range_count) != length(plan$ranges) ||
      !all(vapply(plan[c("provider_access", "network_access", "market_history_write")],
                  identical, logical(1L), FALSE))) {
    data_asset_center_abort_v1("data_asset_center_state_invalid")
  }
  if (!length(plan$ranges)) return(list())
  result <- lapply(seq_along(plan$ranges), function(index) {
    row <- plan$ranges[[index]]
    if (!is.list(row) || length(names(row)) != 3L ||
        !setequal(names(row), c("start_date", "end_date", "calendar_day_count")) ||
        !is.character(row$start_date) || length(row$start_date) != 1L || is.na(row$start_date) ||
        !is.character(row$end_date) || length(row$end_date) != 1L || is.na(row$end_date) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$start_date) ||
        !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", row$end_date) ||
        !is.numeric(row$calendar_day_count) || length(row$calendar_day_count) != 1L ||
        is.na(row$calendar_day_count) || !is.finite(row$calendar_day_count) ||
        row$calendar_day_count != trunc(row$calendar_day_count) ||
        row$calendar_day_count < 1L || row$calendar_day_count > .Machine$integer.max) {
      data_asset_center_abort_v1("data_asset_center_state_invalid")
    }
    start_date <- suppressWarnings(tryCatch(as.Date(row$start_date), error = function(error) as.Date(NA)))
    end_date <- suppressWarnings(tryCatch(as.Date(row$end_date), error = function(error) as.Date(NA)))
    if (is.na(start_date) || is.na(end_date) || end_date < start_date ||
        as.integer(end_date - start_date) + 1L != as.integer(row$calendar_day_count)) {
      data_asset_center_abort_v1("data_asset_center_state_invalid")
    }
    list(
      ref = sprintf("market_range_%03d", index),
      start_date = row$start_date, end_date = row$end_date,
      calendar_day_count = as.integer(row$calendar_day_count),
      label = paste0(row$start_date, " bis ", row$end_date, " · ", as.integer(row$calendar_day_count), " Tage")
    )
  })
  result
}

data_asset_center_history_range_choices_v1 <- function(plan) {
  ranges <- data_asset_center_history_ranges_v1(plan)
  if (!length(ranges)) return(c("Kein Abrufzeitraum geplant" = ""))
  stats::setNames(
    vapply(ranges, `[[`, character(1L), "ref"),
    vapply(ranges, `[[`, character(1L), "label")
  )
}

data_asset_center_selected_history_range_v1 <- function(plan, range_ref) {
  ranges <- data_asset_center_history_ranges_v1(plan)
  if (!is.character(range_ref) || length(range_ref) != 1L || is.na(range_ref) || !nzchar(range_ref)) {
    data_asset_center_abort_v1("data_asset_center_selection_invalid")
  }
  selected <- Filter(function(row) identical(row$ref, range_ref), ranges)
  if (length(selected) != 1L) data_asset_center_abort_v1("data_asset_center_selection_invalid")
  selected[[1L]]
}

data_asset_center_summary_v1 <- function(catalog, provider_catalog, asset_ref, tax_state, market_state, activity_state) {
  asset <- data_asset_center_selected_v1(catalog, asset_ref)
  progress <- data_asset_center_progress_v1(catalog, provider_catalog, asset_ref, tax_state, market_state, activity_state)
  list(
    state = if (is.null(asset)) "asset_required" else "asset_available",
    title = if (is.null(asset)) "Asset auswählen oder neu anlegen" else data_asset_center_value_v1(asset$display_name, asset$label),
    progress = progress[, c("Bereich", "Status"), drop = FALSE],
    calculation_boundary = list(
      realized_without_provider = !is.null(asset),
      provider_optional = TRUE,
      tax_optional = TRUE,
      missing_values_are_zero = FALSE
    ),
    provider_access = FALSE,
    network_access = FALSE,
    canonical_write = FALSE,
    internal_ids_exposed = FALSE,
    paths_exposed = FALSE
  )
}

data_asset_center_candidate_master_v1 <- function(candidate, manual_isin = "") {
  types <- c(equity="equity", etf="etf", fund="fund", cryptocurrency="crypto", currency="fx", index="index", future="derivative", option="derivative")
  currency <- candidate$quote_currency
  if (is.null(currency) || !grepl("^[A-Z]{3}$", currency) || currency %in% c("GBX", "ZAC", "ILA", "USX")) currency <- ""
  isin <- if (is.character(manual_isin) && length(manual_isin)==1L && nzchar(manual_isin)) manual_isin else candidate$isin
  if (is.null(isin)) isin <- ""
  list(display_name=candidate$display_name, price_currency=currency, isin=isin,
    asset_type=if (candidate$quote_type %in% names(types)) unname(types[[candidate$quote_type]]) else NULL)
}

# ISIN schon im Katalog (#448): das Asset, das sie traegt - gross geschrieben verglichen, nur bei vollstaendiger ISIN.
data_asset_center_isin_match_v1 <- function(catalog, isin) {
  if (!is.list(catalog) || !is.list(catalog$assets) || !is.character(isin) || length(isin) != 1L || is.na(isin)) return(NULL)
  wanted <- toupper(gsub("[[:space:]]", "", isin))
  if (!grepl("^[A-Z]{2}[A-Z0-9]{9}[0-9]$", wanted)) return(NULL)
  hits <- Filter(function(row) is.character(row$isin) && length(row$isin) == 1L && !is.na(row$isin) && identical(toupper(row$isin), wanted), catalog$assets)
  if (length(hits)) hits[[1L]] else NULL
}
# Naechster Schritt nach dem Anlegen (#455): Kurse zuordnen; bei Fonds und ETF auch Fondsart und Teilfreistellung pruefen.
data_asset_center_next_step_ui_v1 <- function(created) {
  fund <- isTRUE(created$type %in% c("fund", "etf"))
  shiny::div(class = "pl-section-copy",
    portelyra_status_panel(sprintf("„%s“ angelegt – weiter im selben Ablauf", created$name),
      paste("Als Nächstes die Kurse zuordnen: In „3. Marktdaten“ ist die Suche beim Kursanbieter mit ISIN bzw. Namen vorbelegt.",
        if (fund) "Danach in „4. Steuer“ Fondsart und Teilfreistellung prüfen." else ""), tone = "positive"),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("asset_center_next_market", "Weiter: Kurse zuordnen", class = "btn-primary"),
      # Der Steuer-Reiter folgt dem Baustein Steuerbericht (#542); der Knopf dorthin ebenso, sonst oeffnete er einen ausgeblendeten Reiter.
      if (fund) data_module_only_v1("tax_report", shiny::actionButton("asset_center_next_tax", "Weiter: Fondsart und Teilfreistellung", class = "btn-default"),
                                    inline = TRUE, also = "output.data_expert_tools == 'on'")))
}
# Vorbelegung der Neuanlage aus einem Import (#453): mit ISIN sucht der Kursanbieter nach ISIN, sonst nach Kuerzel oder Name.
data_asset_center_prefill_query_v1 <- function(item) {
  for (value in list(item$isin, item$symbol, item$name, item$missing_key))
    if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) return(value)
  ""
}
data_asset_center_prefill_mode_v1 <- function(item) {
  if (is.character(item$isin) && length(item$isin) == 1L && nzchar(item$isin)) "isin" else if (is.character(item$symbol) && length(item$symbol) == 1L && nzchar(item$symbol)) "auto" else "name"
}

# Suchanbieter (rc.392, #495): Yahoo und jeder weitere aktive Kursanbieter mit Suche, etwa EODHD, das die ISIN mitliefert. Ohne
# weiteren Anbieter bleibt es bei Yahoo; ein Plugin ist ein Zusatz.
data_asset_center_search_providers_v1 <- function(rows) {
  rows <- Filter(function(row) is.list(row) && isTRUE(row$active) && "search" %in% unlist(row$operations) && is.character(row$provider_id), rows)
  ids <- vapply(rows, function(row) row$provider_id, character(1L))
  labels <- vapply(rows, function(row) if (is.character(row$label) && nzchar(row$label)) row$label else row$provider_id, character(1L))
  choices <- stats::setNames(ids, labels)
  choices <- c(choices[ids == "yahoo"], choices[ids != "yahoo"])
  if (!length(choices) || !"yahoo" %in% choices) choices <- c(c("Yahoo" = "yahoo"), choices[choices != "yahoo"])
  choices
}

# Kursanbieter fuer die Kurszuordnung (rc.394, #495): Yahoo als Vorgabe zuerst, dann jeder weitere aktive Anbieter mit Tageskursen
# (etwa EODHD), dazu die beiden Entwurfsarten von frueher. `keep`: Der Anbieter einer gespeicherten Zuordnung bleibt waehlbar, auch
# wenn er inzwischen nicht aktiv ist - sonst zeigte das Formular einen falschen Anbieter.
data_asset_center_history_providers_v1 <- function(rows, keep = NULL) {
  rows <- Filter(function(row) is.list(row) && isTRUE(row$active) && "daily_history" %in% unlist(row$operations) && is.character(row$provider_id), rows)
  ids <- vapply(rows, function(row) row$provider_id, character(1L))
  labels <- vapply(rows, function(row) if (is.character(row$label) && nzchar(row$label)) row$label else row$provider_id, character(1L))
  choices <- c(c("Yahoo" = "yahoo"), stats::setNames(ids, labels)[ids != "yahoo"])
  extra <- c("Twelve Data · nur Expertenentwurf" = "twelve_data", "Anderer geprüfter Adapter" = "other_reviewed")
  if (is.character(keep) && length(keep) == 1L && !is.na(keep) && nzchar(keep) && !keep %in% c(choices, extra)) {
    label <- if (exists("pl_price_provider_label_v1", mode = "function")) pl_price_provider_label_v1(keep, keep) else keep
    choices <- c(choices, stats::setNames(keep, paste(label, "· nicht aktiv")))
  }
  c(choices, extra)
}

data_asset_center_search_ui_v1 <- function(query = "", mode = "name", providers = c("Yahoo" = "yahoo")) shiny::tags$details(
  id = "asset-center-search", open = "open", class = "pl-disclosure",
  shiny::tags$summary("Asset nach Namen, ISIN oder Symbol suchen · optional"),
  shiny::p("Auch vor der Asset-Anlage möglich. Ein Suchabruf erfordert eine ausdrückliche Bestätigung; Tippen allein startet keinen Abruf beim Kursanbieter. Treffer sind editierbare Vorschläge, keine verifizierten Stammdaten."),
  shiny::div(class = "pl-form-grid",
    shiny::textInput("asset_center_provider_query", "Firma, ISIN oder Symbol", query, placeholder = "z. B. Bitcoin"),
    shiny::selectInput("asset_center_search_provider", "Suchanbieter", providers, selected = "yahoo"),
    shiny::selectInput("asset_center_provider_search_mode", "Suchmodus", c("Name"="name", "Automatisch"="auto", "ISIN"="isin", "Symbol"="symbol"), selected=mode)),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton("asset_center_provider_search", "Suchvorschau erstellen"),
    shiny::checkboxInput("asset_center_provider_search_confirm", "Genau einen Suchabruf beim gewählten Anbieter bestätigen", FALSE),
    shiny::actionButton("asset_center_provider_search_execute", "Bestätigt Vorschläge abrufen", class="btn-primary")),
  shiny::uiOutput("asset_center_search_state"),
  shiny::div(class="pl-table-wrap", shiny::tableOutput("asset_center_provider_search_preview")),
  shiny::selectInput("asset_center_provider_candidate", "Vorschlag des Kursanbieters", c("Noch keine Vorschläge"="")),
  shiny::actionButton("asset_center_provider_candidate_apply", "Ausgewählten Vorschlag in Formular übernehmen"),
  shiny::uiOutput('candidate_action_feedback'),
  shiny::p("Eine ISIN wird nur vorgeschlagen, wenn sie in der Antwort des Kursanbieters enthalten und formal gültig ist. Vorhandene manuelle ISIN-Eingaben bleiben erhalten. Kein zusätzlicher ISIN-Abruf, keine automatische Kurszuordnung, kein Speichern."),
  shiny::tags$details(shiny::tags$summary("Alle gelieferten Vorschläge"),
    shiny::div(class="pl-table-wrap", shiny::tableOutput("asset_center_provider_candidates"))))

# Die Institute der Stammdaten als Auswahl: jede Angabe einmal, sortiert ohne Ruecksicht auf Gross- und Kleinschreibung.
# `keep` haelt eine Eingabe in der Liste, die es als Institut noch nicht gibt (gerade eingetippt).
data_asset_center_institution_choices_v1 <- function(accounts, keep = NULL) {
  labels <- unlist(lapply(accounts, function(account) {
    value <- if (is.list(account)) account$institution_label else NULL
    if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(trimws(value))) trimws(value) else NULL
  }))
  kept <- if (is.character(keep) && length(keep) == 1L && !is.na(keep) && nzchar(trimws(keep))) trimws(keep) else NULL
  labels <- unique(c(labels, kept))
  labels <- labels[order(tolower(labels))]
  c(`Kein Institut` = "", stats::setNames(labels, labels))
}
# Was gespeichert wird: Gleicht die Eingabe einem vorhandenen Institut bis auf Gross-/Kleinschreibung und Leerraum, gilt dessen
# Schreibweise. Sonst die Eingabe selbst, Leerraum zusammengezogen; leer heisst "kein Institut".
data_asset_center_institution_value_v1 <- function(value, accounts) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return("")
  text <- gsub("[[:space:]]+", " ", trimws(value))
  if (!nzchar(text)) return("")
  existing <- unname(data_asset_center_institution_choices_v1(accounts))
  key <- function(label) tolower(gsub("[[:space:]]+", "", label))
  hit <- existing[nzchar(existing) & vapply(existing, key, character(1L)) == key(text)]
  if (length(hit)) hit[[1L]] else text
}

# Die Konten mit ihrer Kontonummer, durchsuchbar, unter der Kontoauswahl. Die Kontonummer liegt neben den Stammdaten
# (apps/data/data_account_reference_service_v1.R); eingetragen wird sie im Kontoformular (#426, 14.10.2026) - der Bereich
# hier hatte ein eigenes Eingabefeld, das niemand fand. pl-lazy: Zugeklappt wird nichts gelesen und keine Tabelle gebaut.
data_account_reference_ui_v1 <- function() {
  shiny::tags$details(class = "pl-disclosure pl-lazy", id = "account_reference_details",
    shiny::tags$summary("Konten durchsuchen · mit Institut und Kontonummer"),
    shiny::p(class = "pl-section-copy",
      "Eintragen und ändern lässt sich die Kontonummer im Bereich darüber: „Konto / Wallet anlegen oder umbenennen“ → „Konto umbenennen“."),
    shiny::uiOutput("account_reference_state"),
    shiny::textInput("account_reference_search", "Konten durchsuchen (Name, Institut, Kontoart, Kontonummer)", value = "", width = "100%"),
    shiny::uiOutput("account_reference_list_hint"),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("account_reference_list")))
}

# Inline creation and renaming next to the portfolio and account selection.
# A rename changes the display name only; the ref and all bookings stay bound.
# Konten (Festlegung 14.10.2026, #425/#426): Beim Umbenennen waehlt man das Konto im Formular selbst, nicht oben in der
# Transaktionsmaske; ein Institut laesst sich in einem Schritt fuer alle seine Konten umbenennen; die Kontonummer steht
# im selben Formular - dort, wo man ein Konto anlegt oder aendert.
data_asset_center_catalog_inline_ui_v1 <- function(kind, open = FALSE) {
  stopifnot(kind %in% c("account", "portfolio"))
  account <- identical(kind, "account")
  prefix <- paste0("asset_center_", kind, "_")
  when <- function(condition, ...) shiny::conditionalPanel(sprintf(condition, prefix), ...)
  shiny::tags$details(
    id = paste0("asset-center-", kind, "-inline"), class = "pl-disclosure", open = if (isTRUE(open)) NA else NULL,
    shiny::tags$summary(if (account) "Konto / Wallet anlegen oder umbenennen · Kontonummer · Institut umbenennen" else "Portfolio anlegen oder umbenennen"),
    shiny::p(class = "pl-section-copy", if (account) {
      "Konto oder Wallet im oben gewählten Portfolio anlegen – auch ohne Bestand –, ein Konto umbenennen oder ein Institut für alle seine Konten umbenennen. Umbenennen ändert nur die Anzeige; Buchungen und Bestände bleiben demselben Konto zugeordnet."
    } else {
      "Ein Portfolio anlegen oder umbenennen. Eine Umbenennung ändert nur die Anzeige; Konten und Buchungen bleiben, wo sie sind."
    }),
    shiny::radioButtons(paste0(prefix, "action"), "Vorgang",
      if (account) c("Konto anlegen" = "create", "Konto umbenennen" = "update", "Institut umbenennen" = "rename_institution")
      else c("Portfolio umbenennen" = "update", "Neues Portfolio anlegen" = "create"),
      selected = if (account) "create" else "update", inline = TRUE),
    # #547 (Festlegung 09.11.2026): sichtbar in den Einstellungen statt im Expertenmodus. Je steuerliche Person ein Portfolio -
    # ein zweites ist kein Sonderfall. Welches umbenannt wird, waehlt das Formular selbst (die Auswahl der Kopfzeile ist von
    # den Einstellungen aus nicht im Blick).
    if (!account) when("input.%saction == 'update'",
      shiny::selectInput("asset_center_portfolio_target", "Portfolio", choices = c("wird geladen \u2026" = ""), width = "100%")) else NULL,
    if (!account) when("input.%saction == 'create'",
      shiny::p(class = "pl-field-hint",
        "Ein Portfolio ist ein eigener, getrennter Bestand mit eigenen Konten – etwa je steuerliche Person. Bearbeitet wird es danach über die Auswahl „Portfolio“ oben in „Assets pflegen“.")) else NULL,
    if (account) shiny::div(class = "pl-form-grid",
      when("input.%saction == 'update'",
        shiny::selectInput("asset_center_account_target", "Konto", choices = c("Bitte wählen" = ""), width = "100%")),
      when("input.%saction == 'rename_institution'",
        shiny::selectInput("asset_center_institution_target", "Institut", choices = c("Bitte wählen" = ""), width = "100%")),
      when("input.%saction == 'rename_institution'",
        shiny::textInput("asset_center_institution_name", "Neuer Name des Instituts", "", width = "100%"))
    ) else NULL,
    shiny::div(class = "pl-form-grid",
      if (account) when("input.%saction != 'rename_institution'", shiny::textInput(paste0(prefix, "name"), "Bezeichnung", ""))
      else shiny::textInput(paste0(prefix, "name"), "Bezeichnung", ""),
      if (account) shiny::tagList(
        when("input.%saction == 'create'",
          shiny::selectInput("asset_center_account_type", "Kontoart", c("Wertpapierdepot" = "securities", "Krypto-Wallet / -Depot" = "crypto_wallet",
            "Bankkonto" = "bank", "Cash" = "cash", "Extern" = "external", "Fremdwährungskonto (Devisen) / Sonstiges" = "other")),
          # Bankkonto und Cash rechnen gleich (#529 Punkt 2); die Wahl benennt nur, was das Konto ist.
          shiny::p(class = "pl-field-hint", paste("Bankkonto: Giro- oder Tagesgeldkonto bei einer Bank. Cash: Bargeld oder Verrechnungskonto beim Broker.",
            "Beide führen Euro-Salden und rechnen gleich. Ob ein Konto zum angelegten Vermögen zählt, legt „Cash-Konten · Anlage und Rendite“ fest."))),
        # Auswahl statt Freitext: Vorhandene Institute stehen zur Wahl, ein neues entsteht durch Eintippen. So bleibt die
        # Schreibweise eines Instituts ueber seine Konten gleich - an ihr haengt, welche Konten zusammengehoeren.
        # Der Eintrag, der beim Tippen eines neuen Namens erscheint, hiess englisch "Add ..." - so war nicht zu sehen, dass sich
        # hier ein Institut anlegen laesst (Festlegung 13.10.2026).
        when("input.%saction != 'rename_institution'",
          shiny::selectizeInput("asset_center_account_institution", "Institut / Börse (optional)", choices = c(`Kein Institut` = ""), selected = "",
            options = list(create = TRUE, createOnBlur = TRUE, placeholder = "Wählen oder neuen Namen eintippen",
              render = I("{option_create: function(data, escape) { return '<div class=\"create\">Neues Institut anlegen: <strong>' + escape(data.input) + '</strong></div>'; }}")))),
        # Die Kontonummer liegt neben den Stammdaten (apps/data/data_account_reference_service_v1.R); eingetragen wird sie hier.
        when("input.%saction != 'rename_institution'",
          shiny::textInput("asset_center_account_number", "Kontonummer / IBAN / Adresse (optional)", "", width = "100%"))
      ) else when("input.%saction == 'create'",
        # Fuer die Beta nur Euro (Endabnahme 19.11.2026, wie im Einrichtungsdialog): die anderen ausgegraut, „kommt später“.
        shiny::radioButtons("asset_center_portfolio_currency", "Portfolio-Währung", choices = c("Euro (EUR)" = "EUR"), selected = "EUR"),
        shiny::div(class = "pl-choice-later", lapply(c("Schweizer Franken (CHF)", "US-Dollar (USD)", "Britisches Pfund (GBP)"), function(label)
          shiny::div(class = "radio disabled", shiny::tags$label(shiny::tags$input(type = "radio", disabled = NA),
            shiny::span(class = "pl-muted", paste0(label, " – kommt später")))))))
    ),
    if (account) shiny::tagList(
      when("input.%saction != 'rename_institution'", shiny::p(class = "pl-field-hint",
        "Ein neues Institut entsteht mit dem Konto: seinen Namen ins Feld tippen. Danach „Prüfen“, dann „Geprüft speichern“.")),
      when("input.%saction == 'rename_institution'", shiny::p(class = "pl-field-hint",
        "Alle Konten des Instituts bekommen den neuen Namen. Heißt er wie ein anderes vorhandenes Institut, kommen die Konten dorthin."))) else NULL,
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton(paste0(prefix, "prepare"), "Prüfen", class = "btn-default"),
      shiny::actionButton(paste0(prefix, "execute"), "Geprüft speichern", class = "btn-primary")
    ),
    # Die Rueckmeldung steht am Formular. Die Statuszeile der Seitenleiste zeigt nach dem Speichern schon wieder
    # "Daten gelesen" - wer dort hinsah, erfuhr nicht, dass das Konto angelegt ist (Festlegung 13.10.2026).
    shiny::uiOutput(paste0(prefix, "notice")),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput(paste0(prefix, "preview")))
  )
}

# Auswahlen des Neuanlage-Formulars. Seit #542 filtert die Data-App sie nach dem Umfang des gewaehlten Portfolios
# (data_portfolio_configuration_v1.R); die Listen hier sind der volle Stand und die Vorgabe ohne Umfang.
data_asset_center_domain_choices_v1 <- function() c(
  "Wertpapier, Krypto, Fonds oder Sonstiges · FIFO, Marktbewertung, Kauf/Verkauf, Dividenden und Rewards" = "non_cash",
  "Cash · Konto- oder Börsenguthaben in einer Währung · nur Zinsen als Ertrag, kein FIFO, Wert 1:1" = "cash")
data_asset_center_type_choices_v1 <- function() c("Aktie"="equity", "ETF"="etf", "Fonds"="fund", "Anleihe"="bond", "Derivat"="derivative",
  "Krypto"="crypto", "Rohstoff"="commodity", "Devisen"="fx", "Index"="index", "Sonstiges"="other")
data_asset_center_valuation_choices_v1 <- function() c("Marktdaten"="external_market", "Manuell"="manual", "Nur Transaktionen"="transaction_only")

# Portfolios in den Einstellungen (#547, Festlegung 09.11.2026): sichtbar ohne Expertenmodus; die gefuehrte Einrichtung (#542)
# nutzt denselben Baustein.
data_portfolio_settings_ui_v1 <- function() shiny::tagList(
  shiny::tags$h3(class = "pl-section-title", "Portfolios"),
  shiny::p(class = "pl-section-copy", "Ein Portfolio ist ein eigener, getrennter Bestand – etwa je steuerliche Person. Hier legen Sie eines an oder benennen eines um."),
  data_asset_center_catalog_inline_ui_v1("portfolio", open = TRUE))

# Die Konten als Auswahl im Formular: Name, dahinter das Institut, wo es eines gibt. Archivierte stehen nicht zur Wahl.
data_asset_center_account_choices_v1 <- function(accounts) {
  shown <- Filter(function(row) is.list(row) && !identical(row$status, "archived"), accounts)
  if (!length(shown)) return(c("Keine Konten" = ""))
  labels <- vapply(shown, function(row) {
    institution <- row$institution_label
    if (is.character(institution) && length(institution) == 1L && !is.na(institution) && nzchar(trimws(institution)))
      paste0(row$display_name, " · ", trimws(institution)) else as.character(row$display_name)
  }, character(1L))
  order <- order(tolower(labels))
  c("Bitte wählen" = "", stats::setNames(vapply(shown, function(row) as.character(row$ref), character(1L))[order], labels[order]))
}
# Neuer Name eines Instituts: Leerraum zusammengezogen. Gleicht er bis auf Gross-/Kleinschreibung und Leerraum dem bisherigen,
# gilt die neue Schreibweise (eine Korrektur); gleicht er einem anderen vorhandenen Institut, gilt dessen Schreibweise - die
# Konten kommen dorthin. Leer heisst: kein gueltiger Name.
data_asset_center_institution_rename_v1 <- function(old, value, accounts) {
  if (is.null(value) || !is.character(value) || length(value) != 1L || is.na(value)) return(list(name = "", merge = FALSE))
  text <- gsub("[[:space:]]+", " ", trimws(value))
  if (!nzchar(text)) return(list(name = "", merge = FALSE))
  key <- function(label) tolower(gsub("[[:space:]]+", "", label))
  if (identical(key(text), key(old))) return(list(name = text, merge = FALSE))
  existing <- unname(data_asset_center_institution_choices_v1(accounts))
  hit <- existing[nzchar(existing) & vapply(existing, key, character(1L)) == key(text)]
  if (length(hit)) list(name = hit[[1L]], merge = TRUE) else list(name = text, merge = FALSE)
}

# Welche anderen Assets dieselbe Notierung beschreiben wie das gewaehlte: gleicher
# Anbieter, gleiches Symbol, gleiche Kurswaehrung.
#
# `resolve` loest die Freigabe der Notierung auf und kostet je Asset einen
# Unterprozess. Bis rc.229 lief es fuer jedes providerfaehige Asset: bei vielen Assets also viele Unterprozesse und Sekunden bei jedem Assetwechsel im
# Marktdaten-Reiter. Anbieter, Symbol und Waehrung stehen
# aber schon in der gelesenen Zuordnungsliste. Aufgeloest wird deshalb nur noch,
# was dort uebereinstimmt - und das Ziel selbst. Das Ergebnis ist dasselbe; fehlt
# eine Zuordnung in der Liste, wird wie bisher aufgeloest statt uebersprungen.
data_asset_center_carry_candidates_v1 <- function(rows, mappings, target_ref, resolve) {
  if (!is.function(resolve) || !is.list(rows) || !is.list(mappings)) data_asset_center_abort_v1("data_asset_center_catalog_invalid")
  target <- resolve(target_ref)
  if (is.null(target)) return(character())
  listed <- list()
  for (mapping in mappings) if (is.character(mapping$ref) && length(mapping$ref) == 1L && !is.na(mapping$ref)) listed[[mapping$ref]] <- mapping
  same <- function(mapping) identical(mapping$provider_id, target$mapping$provider_id) &&
    identical(mapping$provider_symbol, target$mapping$provider_symbol) &&
    identical(mapping$provider_currency, target$mapping$provider_currency)
  hits <- list()
  for (row in rows) {
    if (identical(row$asset_ref, target_ref)) next
    if (!identical(row$status, "history_ready_to_plan")) next
    public <- if (is.character(row$mapping_ref) && length(row$mapping_ref) == 1L && !is.na(row$mapping_ref)) listed[[row$mapping_ref]] else NULL
    if (!is.null(public) && !same(public)) next
    candidate <- resolve(row$asset_ref)
    if (is.null(candidate) || !same(candidate$mapping)) next
    hits[[candidate$name]] <- row$asset_ref
  }
  unlist(hits)
}

# Shinys mitgelieferte Bootstrap-Barrierefreiheit gibt jedem Reiter ohne eigene
# Kennung "ui-tab-" plus eine Zufallszahl von 1 bis 1000 und prueft nicht, ob sie
# schon vergeben ist. Bei fuenf Reitern traegt damit rund jeder hundertste
# Seitenaufbau zwei gleiche Kennungen im Dokument (etwa
# "ui-tab-853" doppelt). Einen Reiter, der schon eine Kennung hat, laesst die
# Bibliothek unberuehrt - also bekommen die Reiter feste.
data_asset_center_tab_link_ids_v1 <- function(tag, prefix) {
  count <- 0L
  walk <- function(node) {
    if (inherits(node, "shiny.tag")) {
      if (identical(node$name, "a") && identical(node$attribs[["data-toggle"]], "tab") && is.null(node$attribs$id)) {
        count <<- count + 1L
        node$attribs$id <- paste0(prefix, "_", count)
      }
      node$children <- lapply(node$children, walk)
    } else if (is.list(node) && !inherits(node, "html_dependency") && !is.function(node)) {
      node[] <- lapply(node, walk)
    }
    node
  }
  result <- walk(tag)
  if (count < 1L) stop("data_asset_center_tab_links_missing", call. = FALSE)
  result
}

# Fondsart und Satz (#466). Der Satz bleibt der ausdrueckliche Wert des Eigentuemers;
# die Auswahl setzt ihn nur, damit nicht jeder Fonds still die Vorgabe seines Typs
# erbt - Anleihe- und Geldmarkt-ETFs sind sonstige Investmentfonds mit 0 %.
data_asset_center_fund_kind_choices_v1 <- function() c(
  "Bitte wählen" = "", "Aktienfonds – 30 %" = "30", "Mischfonds – 15 %" = "15",
  "Immobilienfonds – 60 %" = "60", "Immobilienfonds mit Auslandsschwerpunkt – 80 %" = "80",
  "sonstiger Fonds, etwa Anleihen oder Geldmarkt – 0 %" = "0")

# Nur Fonds tragen eine Teilfreistellung; jede andere Einordnung verlangt 0, sonst
# weist der Kern sie ab (tax_classification_invalid).
data_asset_center_tax_partial_for_v1 <- function(classification_code) {
  if (identical(classification_code, "de_fund")) "" else "0"
}

# Reiter der Data-App. Seit rc.298 (#368) gibt es keinen Reiter "5. Abschluss" mehr: "Alles aktualisieren" steht in der Kopfzeile,
# das Run Center zugeklappt in "4. Steuer" ('run_center'), die Zusammenfassung des gewaehlten Assets in "2. Stammdaten". Der
# Reiter "Einstellungen" (#500) traegt 'settings'.
# Wegweiser der Ersteinrichtung (#492, Festlegung 23.10.2026): die Schritte in der Reihenfolge des Reiters und der
# Hinweis, was die Rechnung ist und was sie nicht ist.
data_tax_setup_guide_v1 <- function() shiny::tagList(
  shiny::tags$ol(class = "pl-steps",
    shiny::tags$li("Hier einrichten: Der Steuerbereich wird auf diesem Rechner angelegt."),
    shiny::tags$li("„Regelmodul wählen“ (Karte „Regelmodul“): je Projektionsart das empfohlene Modul übernehmen. Die Auswahl klappt von selbst auf, solange eines fehlt oder neu zu übernehmen ist."),
    shiny::tags$li("„Steuerangaben je Jahr“: persönlichen Steuersatz und Kirchensteuer eintragen."),
    shiny::tags$li("„Freistellung, Verlusttöpfe und Quellensteuer je Institut“: Freistellungsaufträge und Verlusttöpfe nachtragen."),
    shiny::tags$li("„Vorgabe je Asset-Typ“ prüfen; bei Fonds die Vorabpauschalen je Fonds und Konto nachtragen."),
    shiny::tags$li("„Alles aktualisieren“ rechnet danach die Steuer je Ereignis und je Jahr.")),
  shiny::p(class = "pl-field-hint", "Verlustvorträge aus Jahren vor der ersten Buchung stehen bei den Expertenwerkzeugen unter „Weitere Steuerparameter je Jahr“."),
  portelyra_status_panel("Modellrechnung ohne Gewähr", paste(
    "Portelyra rechnet nach einem Regelmodul je Steuerjahr. Das ist keine Rechtsberatung und keine Zusicherung,",
    "dass die Regeln aktuell, vollständig oder richtig umgesetzt sind. Maßgeblich bleiben die Steuerbescheinigungen",
    "der Institute und der Steuerbescheid."), tone = "warning"))

# Stammdaten in Unterreitern (#422, Festlegung 27.10.2026). Bis rc.329 standen die Asset-Pflege und neun weitere Bereiche
# untereinander, jeder als Aufklapper. master_tools ist eine benannte Liste: "top" steht ueber den Unterreitern (Ersteinrichtung
# und erstes Portfolio, beides nur bei Bedarf), die uebrigen Namen sind Unterreiter nach DATA_MASTER_SECTIONS_V1. Ein Bereich
# mit data-pl-autoopen klappt beim ersten Zeigen seines Unterreiters selbst auf; gelesen wird wie bisher erst dann, denn
# pl-lazy meldet das Aufklappen ("<id>_open"). Ohne Liste (aeltere Aufrufer, Tests) bleibt alles im Unterreiter "Assets".
DATA_MASTER_SECTIONS_V1 <- c(accounts = "Konten und Institute", archive = "Ablage", wallet = "FIFO-Wallet",
  corporate = "Kapitalmaßnahmen", settings = "Anlage- und Analyse-Einstellungen")
data_master_autoopen_v1 <- function(section) htmltools::tagAppendAttributes(section, `data-pl-autoopen` = "1")
# Kontoformular und Kontoliste (#422, rc.331): standen bis rc.330 im Unterreiter "Assets" unter der Kontowahl fuer die naechste
# Transaktion; sie gehoeren zu "Konten und Institute". Die Liste klappt dort selbst auf, das Formular bleibt zu.
data_master_account_tools_v1 <- function() shiny::tagList(
  data_asset_center_catalog_inline_ui_v1("account"),
  data_master_autoopen_v1(data_account_reference_ui_v1()))
data_master_sections_ui_v1 <- function(assets, master_tools = NULL) {
  named <- is.list(master_tools) && !inherits(master_tools, c("shiny.tag", "shiny.tag.list")) && length(names(master_tools))
  if (named) master_tools$accounts <- shiny::tagList(data_master_account_tools_v1(), master_tools$accounts)
  tabs <- list(shiny::tabPanel("Assets", value = "assets", assets, if (!named) shiny::tagList(data_master_account_tools_v1(), master_tools)))
  if (named) for (name in names(DATA_MASTER_SECTIONS_V1)) if (!is.null(master_tools[[name]]))
    tabs[[length(tabs) + 1L]] <- shiny::tabPanel(DATA_MASTER_SECTIONS_V1[[name]], value = name, master_tools[[name]])
  shiny::tagList(if (named) master_tools$top,
    # "Ablage" (#542) nur mit dem Baustein Belege (seit #583 "Import aus Belegen und Auszuegen"); ohne Unterreiter (aeltere Aufrufer)
    # gibt es sie nicht.
    shiny::div(class = "pl-workspace-tabs pl-subtabs", if (named && !is.null(master_tools$archive))
      data_module_tabs_v1(do.call(shiny::tabsetPanel, c(list(id = "master_section"), tabs)), list(archive = data_module_condition_v1("documents")))
      else do.call(shiny::tabsetPanel, c(list(id = "master_section"), tabs))),
    shiny::tags$script(shiny::HTML(paste0(
      "$(document).on('shown.bs.tab','#master_section a',function(e){",
      "var sel=e.target.getAttribute('data-bs-target')||e.target.getAttribute('href');if(!sel||sel.charAt(0)!=='#'){return;}",
      "var pane=document.getElementById(sel.slice(1));if(!pane){return;}",
      "pane.querySelectorAll('details[data-pl-autoopen]').forEach(function(d){",
      "if(!d.hasAttribute('data-pl-opened')){d.setAttribute('data-pl-opened','1');d.open=true;}});});"))))
}

# Die Asset-Suche mit Filter (#422, rc.332): ein einziges Bedienelement, das in den gerade offenen Reiter wandert. Dieselbe
# Auswahl fuehrt "Manuell" (Formular und Buchungsliste), "Stammdaten -> Assets" und "Marktdaten"; ein unsichtbarer Filter
# waere wieder das Auseinanderlaufen von #424. Wo sie nicht wirkt, liegt sie verborgen in der Kopfzeile.
data_asset_context_bar_v1 <- function() shiny::div(id = "asset-context-bar", class = "pl-asset-context",
  shiny::conditionalPanel(
    "input.asset_center_mode == 'existing'",
    # Der Asset-Filter grenzt nur die Suche darunter ein (Stufe 1, 09.10.2026).
    shiny::tags$details(class = "pl-disclosure", id = "asset-context-filter",
      shiny::tags$summary("Asset-Auswahl eingrenzen · Bestand, Konten, Asset-Typ"),
      shiny::div(class = "pl-form-grid",
        shiny::selectInput("asset_center_filter_holding", "Bestand", c("Alle" = "any", "Mit Bestand" = "held", "Ohne Bestand" = "not_held")),
        shiny::selectizeInput("asset_center_filter_accounts", "Konten", choices = character(), multiple = TRUE,
          options = list(placeholder = "alle Konten", plugins = list("remove_button"))),
        shiny::selectizeInput("asset_center_filter_types", "Asset-Typ", choices = character(), multiple = TRUE,
          options = list(placeholder = "alle Typen", plugins = list("remove_button"))))),
    shiny::conditionalPanel(
      "input.asset_center_filter_holding != 'any' || (input.asset_center_filter_accounts || []).length > 0 || (input.asset_center_filter_types || []).length > 0",
      shiny::div(class = "pl-editor-actions",
        shiny::actionButton("asset_center_filter_reset", "Filter zurücksetzen", class = "btn-default"))),
    shiny::uiOutput("asset_center_filter_state"),
    shiny::div(class = "pl-editor-actions",
      shiny::selectizeInput("asset_center_asset", "Asset", choices = c("wird geladen \u2026" = ""), options = list(placeholder = "Name, Typ oder ISIN eingeben")),
      shiny::conditionalPanel("input.asset_center_asset != ''",
        shiny::actionButton("asset_center_asset_clear", "Auswahl aufheben", class = "btn-default")))),
  shiny::uiOutput("asset_center_state"),
  # Ein Asset einer Klasse, die das Portfolio nicht waehlt (#542): bleibt bearbeitbar, mit Hinweis.
  shiny::uiOutput("asset_center_scope_note"))
data_asset_context_slot_v1 <- function() shiny::div(class = "pl-asset-context-slot")
# "Weiter" zum naechsten Unterreiter der Marktdaten (#422, rc.333): ein Klick auf den Reiter, kein Serverweg.
data_market_next_v1 <- function(value, label) shiny::div(class = "pl-editor-actions pl-market-next",
  shiny::tags$button(type = "button", class = "btn btn-default", `data-market-next` = value,
    onclick = paste0("var a=document.querySelector('#market_section a[data-value=\"", value, "\"]');if(a){a.click();",
                     "var t=document.getElementById('market_section');if(t){t.scrollIntoView({behavior:'smooth',block:'start'});}}"),
    paste0("Weiter: ", label, " \u2192")))
data_asset_context_script_v1 <- function() shiny::tags$script(shiny::HTML(paste0(
  "(function(){function shown(el){for(var p=el.parentElement;p;p=p.parentElement){",
  "if(p.classList&&p.classList.contains('tab-pane')&&!p.classList.contains('active'))return false;}return true;}",
  "function place(){var bar=document.getElementById('asset-context-bar');var home=document.getElementById('asset-context-home');",
  "if(!bar||!home)return;var target=home;var slots=document.querySelectorAll('.pl-asset-context-slot');",
  "for(var i=0;i<slots.length;i++){if(shown(slots[i])){target=slots[i];break;}}",
  "if(bar.parentElement!==target)target.appendChild(bar);}",
  "$(document).on('shown.bs.tab',place);$(document).on('shiny:connected',place);$(place);})();")))

data_asset_center_ui_v1 <- function(transactions = NULL, master_tools = NULL, tax = NULL, settings = NULL, run_center = NULL, snapshot_tools = NULL,
                                    market_tools = NULL) {
  header <- shiny::tagList(
    shiny::tags$style(shiny::HTML("\n      .pl-lab-details { margin-top: 18px; border: 1px solid var(--pl-border, #d8dee8); border-radius: 10px; padding: 12px; }\n      .pl-lab-details > summary { cursor: pointer; font-weight: 700; font-size: 1.05rem; }\n      .pl-lab-content { margin-top: 14px; }\n      #asset_center_step { margin-top: 12px; }\n      #asset-activity-editor-anchor, #asset-activity-command-form-anchor { scroll-margin-top: 18px; }\n      #asset-activity-editor-anchor:focus-visible, #asset-activity-command-form-anchor:focus-visible { outline: 3px solid rgba(217,164,65,.65); outline-offset: 4px; border-radius: 18px; }\n    ")),
    # Kopfzeile (#422, rc.332, Festlegung 27.10.2026): global nur noch das Portfolio. Die Stammdaten laden beim Start und bei
    # jedem Reiterwechsel von selbst; "Stammdaten neu lesen" erscheint nur nach einem Fehler. Asset-Suche und Filter stehen in
    # den Reitern, in denen sie wirken ("Manuell", "Stammdaten -> Assets", "Marktdaten"), "Vorgang" nur unter "Assets".
    shiny::div(class = "pl-editor-actions",
      shiny::selectInput("asset_center_portfolio", "Portfolio", choices = c("wird geladen \u2026" = "")),
      data_when_needed_v1("action_failed", shiny::actionButton("asset_center_refresh", "Stammdaten neu lesen", class = "btn-default"), inline = TRUE)),
    shiny::div(id = "asset-context-home", hidden = NA, data_asset_context_bar_v1()),
    data_asset_context_script_v1()
  )
  # Abdeckung, FX-Bedarf, Kalender- und Quellluecken sind Pruefwerkzeuge fuer Fachleute (#492); "Alles aktualisieren" holt
  # fehlende Kurse und FX selbst. Die Bewertung des gewaehlten Assets und sein Stand je Bereich bleiben sichtbar.
  # Die Abdeckung ueber alle Assets ist eine Nebenpruefung; sie steht eingeklappt.
  # Die Bewertung selbst bleibt sichtbar, sie gehoert zum Normalweg
  # (Festlegung 21.09.2026, #283).
  coverage <- shiny::tagList(
    data_expert_only_v1(shiny::tags$details(shiny::tags$summary("Prüfen · Abdeckung der Markthistorie aller Assets mit Kursanbieter"),
    shiny::p(class = "pl-section-copy", "Diese Übersicht liest alle aktiven Assets mit Marktdatenbewertung. Sie ruft keinen Kursanbieter ab, legt keine Kurszuordnung an und schreibt keine Historie."),
    shiny::uiOutput("asset_center_market_inventory_state"),
    shiny::div(class = "pl-form-grid",
      shiny::dateInput("asset_center_coverage_start", "Abdeckung benötigt ab", value = as.Date('2019-01-01'), format = "dd.mm.yyyy", language = "de", weekstart = 1),
      shiny::dateInput("asset_center_coverage_end", "Abdeckung bis einschließlich", value = Sys.Date() - 1L, format = "dd.mm.yyyy", language = "de", weekstart = 1)
    ),
    shiny::actionButton("asset_center_coverage_read", "Gespeicherte Abdeckung nur lesend prüfen", class = "btn-default"),
    shiny::tags$details(shiny::tags$summary('Experten · Gesamtbedarf und bisherige Sammelverfahren'),
    shiny::div(class="pl-editor-actions",
      shiny::selectInput("asset_center_completion_currency","Zielwährung",c("Euro (EUR)"="EUR"),selected="EUR"),
      shiny::actionButton("asset_center_completion_plan","Historienabschluss providerfrei planen",class="btn-primary")
    ),
    shiny::uiOutput("asset_center_completion_next_action"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_center_completion_plan_table")),
    shiny::uiOutput("asset_center_completion_batch_action"),
    shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_center_completion_batch")),
    shiny::tags$details(shiny::tags$summary("Optionale Sammelabrufe · gespeicherte Abrufe für Kurse und FX"),data_market_fx_batch_ui_v1())))),
    # Die Bewertung des gewaehlten Assets steht seit rc.333 unter "3. Bewerten", nicht mehr zwischen den Pruefwerkzeugen.
    data_expert_only_v1(shiny::tags$details(shiny::tags$summary('Gespeicherte Abdeckung · alle Assets'),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_market_inventory")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_market_persisted_coverage")))),
    data_expert_only_v1(shiny::tags$details(
      shiny::tags$summary("FX-Bedarf · ", shiny::uiOutput("asset_center_fx_demand_state", inline = TRUE)),
      shiny::p(class = "pl-section-copy", "Nur tatsächlich benötigte Währungspaare. Die Übersicht ruft keinen Kursanbieter ab und schreibt keine FX-Historie."),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_demand_table")),
      shiny::tags$h4("FX-Zeitraum · unabhängig vom Abdeckungs- und Bewertungszeitraum"),
      shiny::div(class="pl-form-grid",
        shiny::dateInput("asset_center_fx_history_start","FX benötigt ab",Sys.Date()-1L,format = "dd.mm.yyyy", language = "de", weekstart = 1),
        shiny::dateInput("asset_center_fx_history_end","FX bis einschließlich",Sys.Date()-1L,format = "dd.mm.yyyy", language = "de", weekstart = 1)),
      shiny::p("Die Datumsfelder der Abdeckung oben bleiben unverändert. Fehlende Kalenderzeilen sind nicht automatisch fehlende Bewertungswerte."),
      shiny::uiOutput("asset_center_fx_search_controls"),
      shiny::tags$details(shiny::tags$summary("FX-Abrufnachweise und Wiederaufnahme · ohne Providerabruf"),
        shiny::actionButton("asset_center_fx_attempts_read","Gespeicherte FX-Versuche lesen"),
        shiny::tableOutput("asset_center_fx_attempts_table"),
        shiny::uiOutput("asset_center_fx_attempts_controls")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_search_preview")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_search_results")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_probe_preview")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_probe_result")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_promotion_preview")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_promotion_result")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_history_plan")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_history_fetch_preview")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_history_review")),
      shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_fx_history_publication"))
    )),
    data_when_needed_v1(NULL, shiny::tags$details(
      shiny::tags$summary("Kalender- und Quelllücken"),
      shiny::p(class="pl-section-copy","Gemeinsamer Katalog für Notierungen und FX-Paare, unabhängig vom Kursanbieter. Vorschläge schreiben und interpolieren nichts."),
      shiny::selectInput('asset_center_calendar_scope','Kalenderbereich · Kurs oder FX',c('Zuerst Abdeckung lesen'='')),
      shiny::uiOutput('asset_center_calendar_local_feedback'),
      shiny::uiOutput("asset_center_calendar_gap_controls"),
      shiny::div(class='pl-table-wrap',shiny::tableOutput('asset_center_calendar_batch_preview')),
      shiny::tags$details(shiny::tags$summary('Technische Kalender-/Quelllückentabelle'),
        shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_center_calendar_gaps"))),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_center_calendar_binding_preview")),
      shiny::tags$details(shiny::tags$summary('Vollständige Kalenderentscheidung · beibehaltene und neue Tage'),
        shiny::div(class='pl-table-wrap',shiny::tableOutput('asset_center_calendar_binding_days'))),
      shiny::div(class="pl-table-wrap",shiny::tableOutput("asset_center_calendar_correction_preview"))
    )),
    shiny::div(class = "pl-editor-actions",
      shiny::selectInput("asset_center_market_asset", "Asset aus der Abdeckung", c("wird geladen \u2026" = "")),
      shiny::actionButton("asset_center_market_continue", "Nächsten Schritt für dieses Asset öffnen", class = "btn-default")
    ),
    shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_progress"))
  )
  panels <- list(
      shiny::tabPanel(
        "2. Stammdaten", value = "1 · Stammdaten",
        # "Vorgang" gehoert nur hierher (rc.332): Neuanlage oder Pflege eines bestehenden Assets.
        shiny::radioButtons(
          "asset_center_mode", "Vorgang",
          choices = c("Bestehendes Asset vervollständigen" = "existing", "Neues Asset anlegen" = "new"),
          selected = "existing", inline = TRUE
        ),
        data_asset_context_slot_v1(),
        shiny::uiOutput("asset_center_search_master"),
        shiny::uiOutput("asset_center_next_step"),
        shiny::conditionalPanel(
          "input.asset_center_mode == 'new'",
          shiny::p(class = "pl-section-copy", "Nur fachliche Asset-Stammdaten. Kursanbieter, Steuer und erste Buchung folgen als getrennt bestätigte Schritte im selben Ablauf."),
          # #364: the domain is an explicit, required decision before any other field.
          shiny::radioButtons("asset_center_domain", "Art des Assets (Pflicht)", data_asset_center_domain_choices_v1(), selected = character(0)),
          shiny::conditionalPanel("input.asset_center_domain == 'cash'",
            shiny::div(class = "pl-section-copy", shiny::strong("Cash-Asset: "),
              "Der Wert entspricht 1:1 dem Betrag in der gewählten Währung. Als Ertrag gibt es nur Zinsen. Es entstehen keine FIFO-Positionen und keine Marktbewertung; Asset-Typ und Bewertung sind deshalb fest.")),
          shiny::conditionalPanel("input.asset_center_domain == 'cash' || input.asset_center_domain == 'non_cash'",
            shiny::div(class = "pl-form-grid",
              shiny::textInput("asset_center_name", "Bezeichnung", ""),
              shiny::conditionalPanel("input.asset_center_domain == 'non_cash'",
                shiny::selectInput("asset_center_type", "Asset-Typ", data_asset_center_type_choices_v1()),
                shiny::textInput("asset_center_isin", "ISIN optional", "")),
              shiny::textInput("asset_center_currency", "Währung (Preis- bzw. Cash-Währung)", "EUR"),
              shiny::selectInput("asset_center_scale", "Mengengenauigkeit (Nachkommastellen)", stats::setNames(as.character(0:24), as.character(0:24)), selected = "8"),
              shiny::conditionalPanel("input.asset_center_domain == 'non_cash'",
                shiny::selectInput("asset_center_valuation", "Bewertung", data_asset_center_valuation_choices_v1(), selected = "external_market"))
            )),
          shiny::uiOutput("asset_center_isin_duplicate"),
          # Angeboten wird, was das Portfolio waehlt; ohne Marktdaten ist die Bewertung ohne Kursabruf vorbelegt (#542).
          shiny::uiOutput("asset_center_new_scope_note"),
          shiny::div(class = "pl-editor-actions",
            shiny::actionButton("asset_center_core_prepare", "Stammdaten prüfen", class = "btn-default"),
            shiny::checkboxInput("asset_center_core_confirm", "Genau diese Stammdaten bestätigen", FALSE),
            shiny::actionButton("asset_center_core_execute", "Asset anlegen und fortfahren", class = "btn-primary")
          ),
          shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_core_preview"))
        ),
        shiny::conditionalPanel(
          "input.asset_center_mode == 'existing'",
          shiny::uiOutput("asset_center_core_detail"),
          shiny::tags$h4("Bestehende Stammdaten bearbeiten"),
          shiny::textInput("asset_center_edit_name", "Bezeichnung ändern", ""),
          shiny::textInput("asset_center_edit_isin", "ISIN ändern (optional)", ""),
          shiny::p("Asset-Typ, Bewertungsmethode und Mengengenauigkeit werden hier nicht still umgeschrieben. Fachliche Preiswährungsänderungen sind separat bestätigt; bestehende Buchungen bleiben unverändert. Nur zwischen ETF und Fonds lässt sich der Typ unten wechseln."),
          shiny::actionButton("asset_center_edit_prepare", "Stammdaten-Korrektur prüfen"),
          shiny::checkboxInput("asset_center_edit_confirm", "Genau diese Stammdaten-Korrektur bestätigen", FALSE),
          shiny::actionButton("asset_center_edit_execute", "Bestätigt Stammdaten korrigieren"),
          shiny::tableOutput("asset_center_edit_preview"),
          shiny::tags$h4("Fachliche Preiswährung korrigieren"),
          shiny::p(
            class = "pl-section-copy",
            "Diese Währung gilt für fachliche Preise und Bewertungen. Die Währungen von Kursanbieter und Notierung bleiben getrennte Zuordnungsdaten; es erfolgt keine FX-Umrechnung."
          ),
          shiny::div(
            class = "pl-form-grid",
            shiny::textInput("asset_center_price_currency_target", "Neue fachliche Preiswährung", "EUR")
          ),
          shiny::div(
            class = "pl-editor-actions",
            shiny::actionButton("asset_center_price_currency_prepare", "Preiswährungs-Korrektur prüfen", class = "btn-default"),
            shiny::checkboxInput("asset_center_price_currency_confirm", "Genau diese Preiswährungs-Korrektur bestätigen", FALSE),
            shiny::actionButton("asset_center_price_currency_execute", "Bestätigt Preiswährung korrigieren", class = "btn-primary")
          ),
          shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_price_currency_preview")),
          shiny::uiOutput("asset_center_fund_type_ui")
        ),
        shiny::tags$hr(),
        shiny::selectInput("asset_center_custody_account", "Konto / Wallet für die nächste Transaktion (optional)", c("wird geladen \u2026"="")),
        shiny::p(class = "pl-section-copy", "Die Auswahl erzeugt keine statische Asset-Konto-Kopplung. Sie wird nur sicher an genau eine neue Transaktion übergeben."),
        shiny::div(class="pl-editor-actions",
          shiny::actionButton(
            "asset_center_activity_handoff", "Dieses Asset in neuer Transaktion verwenden", class="btn-primary",
            `aria-controls`="asset-activity-command-form-anchor",
            onclick=paste0(
              "$('#asset_center_step a[data-value=\"transactions\"]').tab('show');",
              "var target=document.getElementById('asset-activity-command-form-anchor');",
              "if(target){window.setTimeout(function(){target.scrollIntoView({behavior:'smooth',block:'start'});target.focus({preventScroll:true});},0);}"
            )
          )
        )
      ),
      shiny::tabPanel(
        "2 · Kursanbieter",
        # Seit rc.333 (#422) zwei Teile fuer die Unterreiter der Marktdaten: "1. Kursquelle" (Zuordnung speichern) und
        # "2. Einrichten". Der Schritt-Hinweis steht ueber den Unterreitern (asset_center_provider_next_step).
        shiny::div(class = "pl-market-source",
          shiny::uiOutput('asset_center_search_market'),
          shiny::div(class='pl-form-grid',
            shiny::selectInput('asset_center_provider_id','Kursanbieter',c('Yahoo'='yahoo','Twelve Data · nur Expertenentwurf'='twelve_data','Anderer geprüfter Adapter'='other_reviewed')),
            shiny::textInput('asset_center_provider_symbol','Symbol beim Kursanbieter',''),
            shiny::textInput('asset_center_provider_currency','Kurswährung beim Kursanbieter · Vorschlag manuell korrigierbar','')),
          shiny::uiOutput('asset_center_provider_note'),
          if (exists("PL_PRICE_PROVIDER_DEFAULT_NOTE_V1")) shiny::p(class = "pl-field-hint", PL_PRICE_PROVIDER_DEFAULT_NOTE_V1),
          shiny::div(class='pl-editor-actions',
            shiny::actionButton('asset_center_currency_suggest','Währungsvorschlag übernehmen · nur Formular'),
            shiny::uiOutput('asset_center_defaults_notice')),
          # Fuer die erste Zuordnung reichen Anbieter, Symbol und Kurswaehrung; der Rest ist Korrektur und Sonderfall.
          shiny::tags$details(class = "pl-disclosure", id = "market-source-more",
            shiny::tags$summary("Weitere Angaben · gespeicherte Zuordnung, Aktion, Verwendung, Börse, MIC"),
            shiny::div(class='pl-form-grid',
              shiny::selectInput('asset_center_mapping','Gespeicherte Zuordnung · Symbol und Währung',c('Neue Zuordnung'='')),
              shiny::selectInput('asset_center_provider_action','Aktion',c('Neue Zuordnung'='create','Zuordnung korrigieren'='revise','Zuordnung deaktivieren'='disable')),
              shiny::selectInput('asset_center_provider_capability','Verwendung',c('Tageshistorie'='daily_history','Aktueller Kurs'='quote','Intraday'='intraday','Fundamentals'='fundamentals')),
              shiny::textInput('asset_center_provider_exchange','Börse optional',''),
              shiny::textInput('asset_center_provider_mic','MIC optional',''),
              shiny::checkboxInput('asset_center_provider_expert','Expertenmapping; standardmäßig deaktiviert',FALSE)),
            shiny::actionButton('asset_center_provider_refresh','Zuordnungen lesen',class='btn-default'),
            shiny::div(class='pl-table-wrap',shiny::tableOutput('asset_center_provider_table'))),
          shiny::uiOutput('mapping_action_hint'),
          shiny::div(class='pl-editor-actions',
            shiny::actionButton('asset_center_provider_prepare','Zuordnung prüfen',class='btn-default'),
            shiny::checkboxInput('asset_center_provider_confirm','Genau diese Zuordnung bestätigen',FALSE),
            shiny::actionButton('asset_center_provider_execute','Zuordnung speichern',class='btn-primary')),
          # Rueckmeldung und Vorschau der Zuordnung stehen bei ihren Knoepfen.
          shiny::uiOutput("asset_center_provider_online_state"),
          shiny::div(class='pl-table-wrap',shiny::tableOutput('asset_center_provider_preview'))),
        shiny::div(class = "pl-market-setup",
        # Ein Weg statt drei: der Knopf benennt die Folge und ist zugleich die Bestaetigung (#283, 21.09.2026).
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_setup_execute", "Jetzt einrichten · ein Testabruf, dann Freigabe und Verifizierung", class = "btn-primary")),
        shiny::uiOutput("setup_action_feedback"),
        # Snapshot-Test: zeigt, welche Quelle einen tagesfrischen Kurs liefert und
        # wie aktuell er ist. Schreibt nichts in die Kurshistorie (#373).
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_snapshot_quote", "Tagesfrischen Kurs prüfen · ein Abruf je Quelle, ohne Schreiben", class = "btn-default")
        ),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_snapshot_quote_table")),
        # Fuer bereits eingerichtete Assets, deren Freigabe aus einer aelteren Produktversion stammt: Der Kursabruf weist sie ab,
        # und ohne diesen Knopf muesste man erst eine Zuordnung korrigieren, an der nichts zu korrigieren ist (#283, 23.09.2026).
        # Seit rc.333 zugeklappt: Er wird selten gebraucht, die Rueckmeldung steht wie bisher darueber.
        shiny::tags$details(class = "pl-disclosure", id = "market-setup-renew",
          shiny::tags$summary("Kursabruf abgewiesen? · Einrichtung erneuern"),
          shiny::div(class = "pl-editor-actions",
            shiny::actionButton("asset_center_setup_renew", "Einrichtung erneuern · bei abgewiesenem Kursabruf", class = "btn-default")),
          # Die erste Fassung versprach „vorhandene Kurse bleiben erhalten“. Das war falsch: Die Kurshistorie haengt an der
          # Listing-Freigabe, und die Erneuerung legt eine neue an (#283).
          shiny::p(class = "pl-field-hint", "„Einrichtung erneuern“ setzt eine bereits verifizierte Zuordnung auf „ungeprüft“ zurück und durchläuft dieselbe Einrichtung noch einmal — ohne Anbieter, Symbol oder Kurswährung zu ändern. Gedacht für Assets, deren Kursabruf mit „Die Einrichtung stammt aus einer älteren Version“ abgewiesen wird."),
          shiny::p(class = "pl-field-hint", "Die Erneuerung legt eine neue Freigabe der Notierung an, und die Kurshistorie hängt an der Freigabe. Die bisher abgerufenen Kurse werden dabei aus der alten Freigabe übernommen — ohne erneuten Abruf bei der Quelle. Es kostet einen Testabruf; fehlende Tage holt danach „Prüfen, was fehlt“ oder der Sammellauf.")),
        # Testabruf, Historien-Uebernahme und Verifizierung stecken vollstaendig in
        # "Jetzt einrichten". Einzeln erreichbar bleiben sie, aber eingeklappt:
        # gleichberechtigt nebeneinander war nicht erkennbar, was wann dran ist
        # (Festlegung 21.09.2026, #283).
        data_when_needed_v1("market_setup_failed", shiny::tags$details(shiny::tags$summary('Einzelschritte · nur nötig, wenn die Kette stehenbleibt'),
        shiny::tags$h4("Gespeicherte Zuordnung testweise abrufen"),
        shiny::p(class = "pl-section-copy", "Der Test verwendet genau die unten ausgewählte, noch ungeprüfte Zuordnung für Tageskurse. Normalisierte Testdaten werden lokal beim Eigentümer gespeichert, aber noch nicht für die Bewertung freigegeben."),
        shiny::div(class = "pl-form-grid",
          shiny::dateInput("asset_center_probe_start", "Testzeitraum von", value = Sys.Date() - 14L, format = "dd.mm.yyyy", language = "de", weekstart = 1),
          shiny::dateInput("asset_center_probe_end", "Testzeitraum bis", value = Sys.Date() - 1L, format = "dd.mm.yyyy", language = "de", weekstart = 1)
        ),
        shiny::uiOutput('probe_action_hint'),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_provider_probe", "Testabruf-Vorschau", class = "btn-default"),
          shiny::checkboxInput("asset_center_provider_probe_confirm", "Genau einen Testabruf der Tageskurse bestätigen", FALSE),
          shiny::actionButton("asset_center_provider_probe_execute", "Bestätigt testen und Nachweis speichern", class = "btn-primary")
        ),
        shiny::uiOutput('probe_action_feedback'),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_provider_probe_preview")),
        shiny::uiOutput("asset_center_provider_probe_result"),
        shiny::tags$h4("Testdaten als Kurshistorie der Notierung übernehmen"),
        shiny::div(class = "pl-form-grid",
          shiny::textInput("asset_center_listing_market", "Marktcode", "", placeholder = "z. B. XETR oder XNAS"),
          shiny::textInput("asset_center_listing_timezone", "Markt-Zeitzone", "", placeholder = "wird aus dem Test vorgeschlagen"),
          shiny::selectInput("asset_center_listing_calendar", "Handelskalender", c("Börsenwerktage"="weekday_exchange", "24/7"="continuous_24_7", "Bankarbeitstage"="bank_business_day", "Explizit geprüft"="custom_reviewed"), selected = "weekday_exchange")
        ),
        shiny::uiOutput('promotion_action_hint'),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_promotion_prepare", "Übernahme in die Historie prüfen", class = "btn-default"),
          shiny::checkboxInput("asset_center_promotion_confirm", "Genau diese Testhistorie übernehmen", FALSE),
          shiny::actionButton("asset_center_promotion_execute", "Bestätigt in Markthistorie speichern", class = "btn-primary")
        ),
        shiny::uiOutput('promotion_action_feedback'),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_promotion_preview")),
        shiny::uiOutput("asset_center_promotion_result"),
        shiny::uiOutput('verification_action_hint'),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_mapping_verify_prepare", "Verifizierung der Kurszuordnung prüfen", class = "btn-default"),
          shiny::checkboxInput("asset_center_mapping_verify_confirm", "Kurszuordnung mit genau diesem Testnachweis verifizieren", FALSE),
          shiny::actionButton("asset_center_mapping_verify_execute", "Kurszuordnung verifizieren und aktivieren", class = "btn-primary")
        ),
        shiny::uiOutput('verification_action_feedback'),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_mapping_verify_preview"))
        )))
      ),
      shiny::tabPanel(
        "4. Steuer", value = "3 · Steuer",
        # Reihenfolge nach Haeufigkeit (Festlegung 14.10.2026, #427): die Regel je Asset-Typ und die Angaben je Jahr oben,
        # die Abweichung fuer ein einzelnes Asset ganz unten - sie wird am seltensten gebraucht. Die Ersteinrichtung braucht
        # man einmal; sie steht zugeklappt am Anfang.
        shiny::p(class = "pl-section-copy", "Die steuerliche Einordnung bestätigst Du selbst; was ein Kursanbieter über ein Wertpapier meldet, gilt nicht als steuerliche Einordnung."),
        # Mit Wegweiser (#492, Festlegung 23.10.2026); erscheint nur, solange der Steuerbereich fehlt.
        data_when_needed_v1("tax_setup", shiny::tags$details(class = "pl-disclosure", open = NA,
          shiny::tags$summary("Ersteinrichtung des Steuerbereichs (einmalig)"),
          data_tax_setup_guide_v1(),
          shiny::div(class = "pl-editor-actions",
            shiny::checkboxInput("asset_center_tax_initialize_confirm", "Steuerbereich auf diesem Rechner einrichten", FALSE),
            shiny::actionButton("asset_center_tax_initialize", "Steuerbereich einrichten", class = "btn-primary")))),
        # Regelmodul, Vorgabe je Asset-Typ, Parameter und Bereitschaft (#367).
        tax,
        data_expert_only_v1(shiny::tags$details(class = "pl-disclosure", id = "asset-center-tax-asset-deviation",
          shiny::tags$summary("Abweichung für ein einzelnes Asset (selten nötig)"),
          shiny::p(class = "pl-section-copy",
            paste("Normalerweise gilt die Vorgabe je Asset-Typ. Nur wenn ein einzelnes Asset anders zu behandeln ist als sein Typ, hier eine eigene Klassifikation setzen.",
                  "Anleihe- und Geldmarkt-ETFs sind sonstige Investmentfonds mit 0 %; ETCs sind keine Investmentfonds und gehören zum allgemeinen Kapitalinstrument.",
                  "Ein früheres „Gültig ab“ als bei der bestehenden Abweichung korrigiert rückwirkend: Die neue Fassung gilt ab diesem Jahr.")),
          shiny::div(class = "pl-editor-actions",
            shiny::actionButton("asset_center_tax_refresh", "Assets lesen", class = "btn-default")),
          shiny::div(class = "pl-form-grid",
            shiny::selectInput("asset_center_tax_portfolio", "Portfolio", c("Bitte lesen"="")),
            shiny::selectInput("asset_center_tax_asset", "Asset", c("Bitte lesen"="")),
            shiny::numericInput("asset_center_tax_year", "Gültig ab Jahr", value = as.integer(format(Sys.Date(), "%Y")), min = 1900L, max = 9999L),
            # Dieselben Namen wie bei der Vorgabe je Asset-Typ (data_tax_classification_labels_v1) - eine Klassifikation, ein Name.
            shiny::selectInput("asset_center_tax_classification", "Klassifikation", c(
              "Bitte ausdrücklich wählen"="", "Aktie"="de_equity_share", "Allgemeines Kapitalinstrument"="de_capital_instrument",
              "Cash / Zinsen"="de_cash_interest", "Fonds"="de_fund", "Privates Veräußerungsgut (Jahresfrist)"="de_private_disposal_asset",
              "Sonstige Einkünfte"="de_other_income_asset"
            )),
            # Die Fondsart ist eine Eingabehilfe fuer den Satz, keine eigene Autoritaet:
            # gespeichert wird weiter der ausdrueckliche Prozentwert. Ohne sie trug jeder
            # Fonds den Satz der Typ-Vorgabe - auch Anleihe-ETFs, die 0 % haben (#466).
            shiny::selectInput("asset_center_tax_fund_kind", "Fondsart (setzt den Satz)", data_asset_center_fund_kind_choices_v1()),
            shiny::textInput("asset_center_tax_partial", "Teilfreistellung in Prozent", "", placeholder = "bei Fonds ausdrücklich angeben; sonst 0")
          ),
          shiny::div(class = "pl-editor-actions",
            shiny::actionButton("asset_center_tax_prepare", "Abweichung prüfen", class = "btn-default"),
            shiny::checkboxInput("asset_center_tax_confirm", "Genau diese Abweichung bestätigen", FALSE),
            shiny::actionButton("asset_center_tax_execute", "Abweichung speichern", class = "btn-primary")
          ),
          shiny::uiOutput("asset_center_tax_notice"),
          shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_tax_preview")))),
        # Der Abschluss laeuft mit "Alles aktualisieren" (Kopfzeile). Das Formular des Run Center braucht nur, wer bewusst etwas
        # anderes will, etwa einen anderen Stichtag oder eine abgeschlossene EUR-Bewertung (#368).
        data_expert_only_v1(shiny::tags$details(class = "pl-disclosure", id = "data-run-details",
          shiny::tags$summary("Abschluss mit anderem Stichtag (für Fachleute)"),
          shiny::p(class = "pl-section-copy", paste(
            "Der Abschluss rechnet die Steuer je Ereignis und je Jahr, die Bewertung mit projizierter Steuer sowie Handels- und Marktanalyse und veröffentlicht für Cockpit, Steuer und Analyse.",
            "„Alles aktualisieren“ oben rechnet ihn zum jüngsten vollständig bewerteten Tag mit den Eingaben des letzten Laufs hier.",
            "Dieses Formular braucht nur, wer einen anderen Stichtag, andere Eingaben oder eine abgeschlossene EUR-Bewertung einbinden will.")),
          run_center)),
        # Snapshot zu anderem Stichtag und Einstellung der Momentaufnahme (rc.313, #478): kamen aus dem Cockpit.
        if (!is.null(snapshot_tools)) data_expert_only_v1(snapshot_tools)
      ),
      shiny::tabPanel(
        "4 · Historie",
        shiny::p(
          class = "pl-section-copy",
          "Kursdaten folgen immer dem sichtbaren Ablauf: planen → einen Zeitraum auswählen → externen Abruf bestätigen → lokal beim Eigentümer vormerken → Tabelle und Grafik prüfen → separat veröffentlichen oder verwerfen. Ein Abruf veröffentlicht nichts; Veröffentlichen ruft den Kursanbieter nicht erneut ab."
        ),
        shiny::uiOutput("asset_center_history_state"),
        shiny::div(class = "pl-form-grid",
          shiny::selectInput("asset_center_history_mode", "Planmodus", c("Nur fehlende Tage"="incremental", "Quelllücken ausdrücklich erneut"="retry_source_gaps", "Vollständiger Neuvergleich"="full_refresh"), selected = "incremental"),
          shiny::dateInput("asset_center_history_start", "Benötigt ab", value = as.Date('2019-01-01'), format = "dd.mm.yyyy", language = "de", weekstart = 1),
          shiny::dateInput("asset_center_history_end", "Bis einschließlich", value = Sys.Date() - 1L, format = "dd.mm.yyyy", language = "de", weekstart = 1)
        ),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_history_plan", "Zeiträume nur lesend planen", class = "btn-default"),
          shiny::actionButton("asset_center_history_recover", "Letzten Prüfvorgang abgleichen", class = "btn-default")
        ),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_history_plan_table")),
        shiny::uiOutput('asset_center_history_plan_guidance'),
        shiny::conditionalPanel("output.asset_center_history_has_ranges == 'yes'",
        shiny::selectInput("asset_center_history_range", "Genau einen geplanten Abrufzeitraum auswählen", c("Zuerst planen"="")),
        shiny::div(class = "pl-editor-actions",
          shiny::actionButton("asset_center_history_fetch_prepare", "Ausgewählten Abruf prüfen", class = "btn-default"),
          shiny::checkboxInput("asset_center_history_fetch_confirm", "Genau einen externen Abruf für diesen Zeitraum bestätigen", FALSE),
          shiny::actionButton("asset_center_history_fetch_execute", "Bestätigt abrufen und nur lokal beim Eigentümer vormerken", class = "btn-primary")
        )),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_history_fetch_preview")),
        shiny::uiOutput("asset_center_history_fetch_result"),
        shiny::tags$h4("Vorgemerkten Kandidaten exakt prüfen"),
        shiny::p(class = "pl-section-copy", "Bisherige, abgerufene und effektive Schlusskurse bleiben getrennt. Gestrichelte effektive Punkte sind ausschließlich kalenderbestätigte Ableitungen; Quelllücken bleiben sichtbar und werden nicht erfunden."),
        shiny::uiOutput("asset_center_history_review_state"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_history_review_summary")),
        shiny::tags$details(shiny::tags$summary('Tagesdaten und Kursverlauf prüfen · Details'),
          shiny::plotOutput("asset_center_history_review_plot", height = "420px"),
          shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_history_review_table"))),
        shiny::div(class = "pl-editor-actions",
          shiny::checkboxInput("asset_center_history_publish_confirm", "Genau den angezeigten Kandidaten veröffentlichen · nur fortgeschrieben", FALSE),
          shiny::actionButton("asset_center_history_publish", "Bestätigt veröffentlichen · ohne neuen Abruf", class = "btn-primary")
        ),
        shiny::div(class = "pl-editor-actions",
          shiny::checkboxInput("asset_center_history_reject_confirm", "Genau den angezeigten Kandidaten endgültig verwerfen", FALSE),
          shiny::actionButton("asset_center_history_reject", "Bestätigt verwerfen · ohne Schreiben der Marktdaten", class = "btn-default")
        ),
        shiny::uiOutput("asset_center_history_publish_result")
      ),
      shiny::tabPanel(
        "Einstellungen", value = "settings",
        settings
      )
    )
  # "4. Steuer" (#542) nur mit dem Baustein Steuerbericht; mit den Expertenwerkzeugen bleibt der Reiter erreichbar, denn dort stehen
  # auch Run Center und Snapshot zu anderem Stichtag.
  data_module_tabs_v1(shiny::tagList(shiny::tags$script(shiny::HTML("$(document).on('shiny:connected',function(){Shiny.addCustomMessageHandler('asset_center_currency_proposal',function(m){var el=document.getElementById('asset_center_provider_currency');function value(id){return document.getElementById(id)?.value;}if(!el||el.value!==m.expected_currency||value('asset_center_provider_symbol')!==m.symbol||value('asset_center_provider_id')!==m.provider||value('asset_center_asset')!==m.asset||value('asset_center_mapping')!==''||value('asset_center_provider_action')!=='create')return;$(el).val(m.currency).trigger('change');});Shiny.addCustomMessageHandler('pl_set_if_unchanged',function(m){if(m.kind==='tab'){var on=document.querySelector('#'+m.id+' li.active > a');if(!on||on.getAttribute('data-value')!==m.expected)return;var to=Array.prototype.find.call(document.querySelectorAll('#'+m.id+' a[data-value]'),function(a){return a.getAttribute('data-value')===m.value;});if(to)$(to).tab('show');return;}var el=document.getElementById(m.id);if(!el||el.value!==m.expected)return;$(el).val(m.value).trigger('change');});});")),header, data_asset_center_tab_link_ids_v1(shiny::tabsetPanel(id = "asset_center_step",
    shiny::tabPanel("1. Transaktionen", value = "transactions", transactions),
    shiny::tabPanel("2. Stammdaten", value = "1 · Stammdaten", data_master_sections_ui_v1(shiny::tagList(panels[[1L]]$children,
      shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Zusammenfassung des gewählten Assets · Stammdaten, Kurse, Steuer, Buchungen"),
        shiny::uiOutput("asset_center_summary"),
        shiny::div(class = "pl-table-wrap", shiny::tableOutput("asset_center_summary_table")))), master_tools)),
    # Marktdaten in Unterreitern (#422, rc.333, Festlegung 27.10.2026): Bis rc.332 standen Bewerten, Bewertungsart und
    # Zuordnung untereinander - die Bewertung vor der Zuordnung, die sie braucht. Jetzt der Ablauf als Reiter mit "Weiter";
    # beim Oeffnen und beim Assetwechsel zeigt der Reiter, was fuer dieses Asset dran ist. Selten Gebrauchtes unter
    # "Bei Problemen", das meiste davon wie bisher nur mit dem Schalter "Expertenwerkzeuge".
    shiny::tabPanel("3. Marktdaten", value = "Marktdaten",
      data_asset_context_slot_v1(),
      shiny::uiOutput("asset_center_market_selection_notice"),
      shiny::uiOutput("asset_center_provider_next_step"),
      # "2. Einrichten" (#542) nur mit dem Baustein Marktdaten - oder fuer ein gewaehltes Asset, das schon Marktdaten nutzt.
      shiny::div(class = "pl-workspace-tabs pl-subtabs", data_module_tabs_v1(shiny::tabsetPanel(id = "market_section",
        shiny::tabPanel("1. Kursquelle", value = "source",
          shiny::uiOutput("asset_center_market_method"),
          # Bewertung ueber die Zeit (rc.393, #495): neben der Bewertungsart, nur fuer ein bestehendes Asset.
          if (!is.null(market_tools)) shiny::conditionalPanel("input.asset_center_mode == 'existing'", market_tools),
          # Eigene Kursangaben: nur fuer die Methode "Manuell". Beliebig grosse Luecken
          # sind erlaubt; die Bewertung schreibt den letzten Wert fort (#283 Punkt 2).
          shiny::conditionalPanel("output.asset_center_manual_method == 'yes'",
            shiny::tags$h4("Bewertung ohne Kursanbieter"),
            shiny::radioButtons("asset_center_manual_source", "Woraus soll bewertet werden?",
              choices = c("eigene Kursangaben" = "own_entries", "bestätigte Trade-Stückpreise" = "trade_prices"),
              selected = "own_entries", inline = TRUE),
            shiny::tags$h4("Eigene Kursangaben"),
            portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-manual-prices", shiny::p("Eine Angabe je Tag; ein zweiter Eintrag zum selben Tag ersetzt den ersten. Lücken sind erlaubt — die Bewertung schreibt den zuletzt eingetragenen Wert fort und kennzeichnet diese Tage als Ersatzwerte. Es ist eine Eigentümerangabe, kein Marktkurs.")),
            shiny::div(class = "pl-form-grid",
              shiny::dateInput("asset_center_manual_price_date", "Tag", value = Sys.Date() - 1L, format = "dd.mm.yyyy", language = "de", weekstart = 1),
              shiny::textInput("asset_center_manual_price_value", "Kurs je Einheit", "", placeholder = "z. B. 128.40")
            ),
            shiny::div(class = "pl-editor-actions",
              shiny::actionButton("asset_center_manual_price_read", "Angaben lesen", class = "btn-default"),
              shiny::checkboxInput("asset_center_manual_price_confirm", "Genau diese Kursangabe bestätigen", FALSE),
              shiny::actionButton("asset_center_manual_price_save", "Kursangabe speichern", class = "btn-primary")
            ),
            shiny::div(class = "pl-table-wrap", style = "max-height:240px;overflow:auto",
              shiny::tableOutput("asset_center_manual_price_table"))),
          shiny::conditionalPanel("output.asset_center_external_market == 'yes'", panels[[2L]]$children[[1L]],
            data_market_next_v1("setup", "2. Einrichten")),
          shiny::conditionalPanel("output.asset_center_external_market != 'yes'", data_market_next_v1("valuation", "3. Bewerten")),
          data_module_only_v1("market_data", shiny::tags$details(class = "pl-disclosure", id = "market-unmapped",
            shiny::tags$summary("Weitere Assets ohne Kurszuordnung"),
            shiny::uiOutput("asset_center_unmapped"))),
          # Die Arbeitsliste fuehrt das Zuordnungsformular darueber von Asset zu Asset - sie gehoert zu ihm, nicht unter "Bei Problemen".
          data_expert_only_v1(shiny::tags$details(shiny::tags$summary("Optional · mehrere Assets als Arbeitsliste bearbeiten"),data_market_worklist_ui_v1()))),
        shiny::tabPanel("2. Einrichten", value = "setup",
          shiny::conditionalPanel("output.asset_center_external_market == 'yes'", panels[[2L]]$children[[2L]],
            data_market_next_v1("valuation", "3. Bewerten")),
          shiny::conditionalPanel("output.asset_center_external_market != 'yes'",
            shiny::p(class = "pl-section-copy", "Einrichten braucht nur ein Asset mit Kursen eines Anbieters. Für dieses Asset geht es unter „3. Bewerten“ weiter."),
            data_market_next_v1("valuation", "3. Bewerten"))),
        shiny::tabPanel("3. Bewerten", value = "valuation",
          shiny::radioButtons("asset_center_period_mode", "Kursabruf",
            choices = c("ab erster Transaktion" = "from_first_trade",
                        "vor erster Transaktion" = "before_first_trade",
                        "freie Datumswahl" = "free"),
            selected = "from_first_trade", inline = TRUE),
          shiny::div(class = "pl-form-grid",
            shiny::dateInput("asset_center_period_start", "Bewertungszeitraum von", value = as.Date("2019-01-01"), format = "dd.mm.yyyy", language = "de", weekstart = 1),
            shiny::dateInput("asset_center_period_end", "Bewertungszeitraum bis", value = Sys.Date() - 1L, format = "dd.mm.yyyy", language = "de", weekstart = 1)
          ),
          portelyra_note_v1(title = "So wählen Sie den Zeitraum", id = "data-valuation-period", shiny::p("Ein Zeitraum für alles: Kurshistorie, Wechselkurse und Bewertung. ‚Ab erster Transaktion‘ setzt den Beginn selbst; ‚vor erster Transaktion‘ nimmt Ihr Datum und verlangt, dass es nicht nach der ersten Buchung liegt; ‚freie Datumswahl‘ nimmt Ihr Datum ohne Prüfung. Ende ist gestern – je Notierung aber erst, wenn ihr Handelstag in ihrer Zeitzone vorbei ist, plus eine Stunde: Krypto nach UTC, Wechselkurse nach London, US-Börsen nach New York. Kurz nach Mitternacht endet der Abruf für diese deshalb noch am Vortag.")),
          # Die Wahl steht nach jedem Neustart auf dem Vorgabewert. Ein Lauf darf
          # deshalb nicht verwerfen, was ein frueherer mit weiterem Beginn gerechnet
          # hat (Entscheidung 12.10.2026).
          shiny::p(class = "pl-field-hint", "Ein schon bewerteter Zeitraum wird nie kürzer: Reicht die Bewertung eines Assets weiter zurück als der hier gewählte Beginn, rechnet der Lauf ab dort weiter. Der Beginn bestimmt, was mindestens bewertet und was abgerufen wird."),
          shiny::div(class = "pl-editor-actions",
            shiny::actionButton("asset_center_refresh_plan", "Prüfen, was fehlt · ohne Abruf", class = "btn-default"),
            shiny::uiOutput("asset_center_refresh_action", inline = TRUE),
            shiny::actionButton("asset_center_valuation_view", "Bewertung ansehen · ohne Abruf, ohne Schreiben", class = "btn-default")
          ),
          shiny::uiOutput("refresh_action_feedback"),
          shiny::uiOutput("asset_center_refresh_preview"),
          shiny::uiOutput("asset_center_valuation_workspace")),
        shiny::tabPanel("Bei Problemen", value = "problems",
          shiny::p(class = "pl-section-copy", "Werkzeuge für den Fall, dass ein Schritt stehenbleibt, und für mehrere Assets auf einmal. Die meisten erscheinen mit dem Schalter „Expertenwerkzeuge“ in den Einstellungen."),
          shiny::conditionalPanel("output.asset_center_external_market == 'yes'",
            # Dasselbe Papier als zwei Assets ist kein Fehler - aber
            # jedes holt seine Kurse einzeln. Die Uebernahme haengt dieselbe Reihe
            # an das zweite Asset, ohne die Quelle ein zweites Mal zu belasten
            # (#283, 24.09.2026).
            data_expert_only_v1(shiny::tags$details(shiny::tags$summary("Experten · Kursreihe eines anderen Assets übernehmen"),
              shiny::p(class = "pl-section-copy", "Wird dasselbe Papier als zwei Assets geführt — etwa aus zwei Depots —, muss die Kursreihe nicht zweimal abgerufen werden. Zur Auswahl stehen nur Assets, deren Zuordnung in Anbieter, Symbol und Kurswährung mit der des oben gewählten Assets übereinstimmt; alles andere wäre eine andere Notierung."),
              shiny::p(class = "pl-field-hint", "Übernommen wird nur, was die Quelle trägt und das gewählte Asset noch nicht hat — die Übernahme ergänzt, sie überschreibt nicht. Übernommene Tage bleiben als übernommen erkennbar. Es findet kein Abruf bei der Quelle statt."),
              shiny::selectInput("asset_center_carry_source", "Kursreihe von welchem Asset übernehmen?", choices = c("Bitte wählen" = "")),
              shiny::div(class = "pl-editor-actions",
                shiny::actionButton("asset_center_carry_preview", "Prüfen, was übernommen würde · ohne Schreiben", class = "btn-default"),
                shiny::checkboxInput("asset_center_carry_confirm", "Genau diese Übernahme bestätigen", FALSE),
                shiny::actionButton("asset_center_carry_execute", "Übernehmen", class = "btn-primary")),
              shiny::uiOutput("asset_center_carry_state"))),
            # Der Einzelabruf der Kurshistorie ist der Expertenweg; die Kette oben
            # erledigt ihn. Sichtbar nebeneinander war nicht erkennbar, was gilt.
            data_expert_only_v1(shiny::tags$details(shiny::tags$summary('Experten · Kurshistorie einzeln abrufen, prüfen und veröffentlichen'),
              panels[[4L]]$children))),
          # Der Einzelablauf kostet je Asset sechs Klicks. Der Sammellauf geht dieselbe
          # Kette der Reihe nach durch (#283, 23.09.2026).
          data_expert_only_v1(shiny::tags$details(shiny::tags$summary("Sammellauf · alle zugeordneten Assets nacheinander bewerten"),
            shiny::p(class = "pl-section-copy", "Der Lauf nimmt jedes aktive Asset mit Marktbewertung über einen Kursanbieter und geprüfter Zuordnung, bestimmt dessen Zeitraum ab der ersten Buchung, ruft die fehlenden Kurse und Wechselkurse ab, veröffentlicht sie, bindet die Schließtage und schreibt die Bewertung. Er hält nicht vor jedem Entwurf an — dafür ist er gedacht. Assets mit eigenen Kursangaben oder bestätigten Trade-Stückpreisen bleiben außen vor: welche der beiden Quellen gilt, entscheiden Sie je Asset."),
            shiny::p(class = "pl-section-copy", "Während ein Asset abgearbeitet wird, reagiert die Oberfläche nicht; „Anhalten“ greift nach dem laufenden Asset. Zwischen zwei Assets liegen drei Sekunden Abstand, damit die Quelle den Lauf durchlässt."),
            shiny::p(class = "pl-section-copy", "Weist die Quelle einen Abruf ab, wartet der Lauf 5, 10, 20 und 30 Minuten und versucht dasselbe Asset erneut; danach stellt er es zurück und geht weiter. Bereits veröffentlichte Kurse bleiben in jedem Fall erhalten, ein erneuter Lauf holt nur noch das Fehlende."),
            # Fehlt einem Asset kein Kurstag, ist seine Bewertung geschrieben; sie
            # erneut zu rechnen kostet Zeit und aendert nichts. Ohne Haekchen laeuft
            # jedes Asset erneut durch - das ist der ausdrueckliche Weg, eine
            # Bewertung neu zu schreiben (#283, 25.09.2026).
            shiny::checkboxInput("asset_center_sweep_only_missing",
              "Nur Assets mit fehlenden Kurstagen (Häkchen entfernen, um alle Bewertungen neu zu schreiben)", TRUE),
            shiny::div(class = "pl-editor-actions",
              shiny::actionButton("asset_center_sweep_prepare", "Sammellauf vorbereiten · ohne Abruf", class = "btn-default"),
              shiny::checkboxInput("asset_center_sweep_confirm", "Bestätigen: abrufen, veröffentlichen und Bewertungen schreiben", FALSE),
              shiny::actionButton("asset_center_sweep_start", "Sammellauf starten", class = "btn-primary"),
              shiny::actionButton("asset_center_sweep_stop", "Anhalten", class = "btn-default")),
            shiny::uiOutput("asset_center_sweep_state"))),
          # Eine Sperre sagt nur, dass ueber diesen einen Tag nichts feststeht. Ohne
          # diesen Schalter loeschte sie auch den Vorgaenger, und alle Tage danach
          # blieben ohne Wert (#368).
          data_when_needed_v1(NULL, shiny::tags$details(shiny::tags$summary("Gesperrte Tage · ob eine Sperre die Folgetage ansteckt"),
            shiny::uiOutput("asset_center_gap_carry"))),
          coverage)), list(setup = data_module_condition_v1("market_data", "output.asset_center_external_market == 'yes'"))))),
    # Ohne `settings` kein Reiter "Einstellungen": Seit rc.332 (#519) stehen sie in der Kopfzeile der Data-App.
    panels[[3L]], if (!is.null(settings)) panels[[5L]]), "asset_center_step_tab")),
    list(`3 · Steuer` = data_module_condition_v1("tax_report", "output.data_expert_tools == 'on'")))
}

# One Cash asset per currency (#184): Cash balances are separated by accounts, not assets.
data_asset_center_cash_duplicate_v1 <- function(catalog, currency) {
  if (!is.list(catalog) || !is.character(currency) || length(currency) != 1L || is.na(currency)) return(NULL)
  # Archived assets no longer hold Cash and must not block a new one.
  hits <- Filter(function(row) identical(row$asset_type, "cash") && !identical(row$status, "archived") && identical(toupper(row$price_currency), toupper(trimws(currency))), catalog$assets)
  if (length(hits)) hits[[1L]] else NULL
}

# Fondsart im Katalog (#447, rc.274): ein Investmentfonds steht als "ETF" oder "Fonds"; nur zwischen beiden laesst sich wechseln.
# NULL fuer jedes andere Asset - dann erscheint der Bereich nicht.
data_asset_center_fund_type_ui_v1 <- function(selected) {
  if (is.null(selected) || !isTRUE(selected$asset_type %in% c("etf", "fund"))) return(NULL)
  now <- if (identical(selected$asset_type, "etf")) "ETF" else "Fonds"; target <- if (identical(selected$asset_type, "etf")) "Fonds" else "ETF"
  shiny::tagList(
    shiny::tags$h4("Fondsart: ETF oder Fonds"),
    shiny::p(class = "pl-section-copy", sprintf(paste(
      "Heute: %s. Beides ist steuerlich ein Investmentfonds (Vorabpauschale, Teilfreistellung); die Steuervorgabe je Asset-Typ",
      "unterscheidet aber zwischen ETF und Fonds. Konten, Mengenskala, Kurse und Kursfreigabe bleiben, Buchungen auch."), now)),
    shiny::div(class = "pl-editor-actions",
      shiny::actionButton("asset_center_fund_type_prepare", sprintf("Wechsel zu „%s“ prüfen", target), class = "btn-default"),
      shiny::checkboxInput("asset_center_fund_type_confirm", sprintf("Genau diesen Wechsel zu „%s“ bestätigen", target), FALSE),
      shiny::actionButton("asset_center_fund_type_execute", sprintf("Bestätigt zu „%s“ wechseln", target), class = "btn-primary")),
    # Rueckmeldung hier, wo geklickt wird (die allgemeine Statuszeile ersetzt nach dem Neulesen die Auswahlmeldung des
    # Assets) - als eigene Ausgabe: baute die Meldung den ganzen Bereich neu, sprang das Bestaetigungshaekchen zurueck.
    shiny::uiOutput("asset_center_fund_type_notice"))
}
