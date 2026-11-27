# Generischer Asset-Filter, Stufe 1: grenzt eine Asset-Auswahl ein.
#
# Wer viele Transaktionen nachtraegt, sucht in der vollen Assetliste immer wieder
# dieselben wenigen Assets (Festlegung vom 09.10.2026: nur Assets mit
# Bestand, nur bestimmte Konten, nur Aktien). Der Filter beantwortet genau eine
# Frage - welche Assets gehoeren dazu - und ist bewusst kein Teil einer Oberflaeche:
# Data grenzt damit die Suche ein, spaeter rechnet die Analyse auf derselben Menge.
#
# Er liest nur das bereits gepruefte Lesemodell des Auswahlkontexts v3 und startet
# nichts. Drei Kriterien, alle mit UND verknuepft:
# - holding: "any", "held" (Bestand > 0) oder "not_held";
# - account_refs: irgendeines dieser Konten. Zusammen mit "held" zaehlt der
#   heutige Bestand auf diesen Konten, sonst jede Buchung, die sie beruehrt hat;
# - asset_types: einer dieser Typen.
#
# Ein Kriterium, das sich nicht pruefen laesst, wird ausgesetzt und gemeldet, nie
# still als "trifft nicht zu" gewertet: Bestaende gibt es nur bei frischem
# FIFO-Stand. Ein ausgesetztes Kriterium zeigt zu viel, kein Asset verschwindet
# deshalb - bei einer Auswahlliste ist das die sichere Richtung.

asset_filter_holding_modes_v1 <- function() c("any", "held", "not_held")

asset_filter_resolve_v1 <- function(
  catalog, read_view, holding = "any", account_refs = character(), asset_types = character()
) {
  if (!is.character(holding) || length(holding) != 1L || is.na(holding) ||
      !holding %in% asset_filter_holding_modes_v1() ||
      !is.character(asset_types) || anyNA(asset_types) || anyDuplicated(asset_types)) {
    .asset_selection_context_abort_v1("asset_selection_context_input_invalid")
  }
  for (type in asset_types) invisible(asset_selection_context_asset_domain_v2(type))
  account_refs <- .asset_selection_context_refs_v2(account_refs, "^activity_account_[0-9]{4,10}$")
  validated <- .asset_selection_context_read_model_v3(catalog, read_view)
  assets <- validated$assets
  refs <- if (length(assets)) vapply(assets, `[[`, character(1L), "ref") else character()
  types <- if (length(assets)) vapply(assets, `[[`, character(1L), "asset_type") else character()
  known_accounts <- if (length(validated$accounts)) vapply(validated$accounts, `[[`, character(1L), "ref") else character()
  if (length(setdiff(account_refs, known_accounts))) {
    .asset_selection_context_abort_v1("asset_selection_context_selection_invalid")
  }
  absent <- identical(validated$read_view$status, "absent")
  fresh <- !absent && identical(validated$read_view$fifo_state, "fresh")

  keep <- rep(TRUE, length(refs))
  type_status <- if (length(asset_types)) "applied" else "not_requested"
  if (length(asset_types)) keep <- keep & types %in% asset_types
  holding_status <- if (identical(holding, "any")) "not_requested" else if (fresh) "applied" else "unavailable"
  account_status <- if (!length(account_refs)) "not_requested" else if (absent) "unavailable" else "applied"
  related <- function(usage) .asset_selection_context_filter_refs_v2(
    validated, "noncash", account_refs, "any", usage
  )$refs
  account_relation <- "none"
  if (identical(account_status, "applied")) {
    booked <- related("historical")
    if (identical(holding_status, "applied")) {
      held_there <- related("current")
      keep <- keep & refs %in% (if (identical(holding, "held")) held_there else setdiff(booked, held_there))
      account_relation <- "current"
    } else {
      keep <- keep & refs %in% booked
      account_relation <- "historical"
    }
  } else if (identical(holding_status, "applied")) {
    held <- unique(unlist(lapply(validated$portfolios, function(portfolio) {
      vapply(Filter(function(row) {
        .asset_selection_context_positive_decimal_v2(row$remaining_quantity_decimal)
      }, portfolio$positions), `[[`, character(1L), "asset_ref")
    }), use.names = FALSE))
    keep <- keep & (refs %in% held) == identical(holding, "held")
  }
  unavailable <- c(holding_status, account_status) == "unavailable"
  list(
    asset_filter_version = 1L,
    status = if (any(keep)) "ready" else "empty",
    active = !identical(holding, "any") || length(account_refs) > 0L || length(asset_types) > 0L,
    holding = holding, holding_status = holding_status,
    account_status = account_status, account_relation = account_relation,
    type_status = type_status,
    unavailable_reason = if (!any(unavailable)) NULL else if (absent) "read_model_absent" else "fifo_not_fresh",
    fifo_state = validated$read_view$fifo_state,
    account_refs = account_refs, asset_types = asset_types,
    available_asset_count = as.integer(length(refs)),
    matched_asset_count = as.integer(sum(keep)),
    matched_assets = unname(assets[keep]),
    browser_local = TRUE, calculation_started = FALSE, provider_access = FALSE,
    network_access = FALSE, canonical_write = FALSE, path_exposed = FALSE,
    internal_id_exposed = FALSE
  )
}
