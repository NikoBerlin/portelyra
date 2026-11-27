# Die Asset-Suche des Asset-Centers folgt dem generischen Asset-Filter
# (apps/shared/asset_filter_v1.R). Die Suche ist seit #424 die einzige Stelle, an
# der das Asset gewaehlt wird; Buchungstabelle und Formular folgen ihr. Der
# Filter grenzt deshalb genau diese eine Liste ein und sonst nichts: keine
# Berechnung, keine Tabelle, kein Schreibweg haengt an ihm.
#
# Zwei Dinge unterscheiden die Oberflaeche vom Filter selbst:
# - Das Asset-Center fuehrt Katalog-Refs, der Filter rechnet auf den Refs der
#   Buchungssicht. `bridge(kind, center_ref)` uebersetzt und liefert "" fuer
#   alles, was die Buchungssicht nicht kennt - Cash-Assets und Cash-Konten.
# - Das gerade gewaehlte Asset bleibt in der Liste, auch wenn es nicht passt. Ein
#   Filter, der die Auswahl umstellt, wechselte den Arbeitskontext unter einer
#   begonnenen Eingabe weg.

data_asset_center_filter_type_labels_v1 <- function() c(
  equity = "Aktie", etf = "ETF", fund = "Fonds", bond = "Anleihe", derivative = "Derivat",
  crypto = "Krypto", commodity = "Rohstoff", cash = "Cash", fx = "Devisen", index = "Index",
  other = "Sonstiges"
)

# Browserwerte in die Form des Filters: NULL und "" bedeuten "kein Kriterium".
data_asset_center_filter_input_v1 <- function(holding = NULL, account_refs = NULL, asset_types = NULL) {
  values <- function(value) {
    if (!is.character(value)) return(character())
    unique(value[!is.na(value) & nzchar(value)])
  }
  holding <- values(holding)
  list(
    holding = if (length(holding) == 1L && holding %in% asset_filter_holding_modes_v1()) holding else "any",
    account_refs = values(account_refs),
    asset_types = intersect(values(asset_types), names(data_asset_center_filter_type_labels_v1()))
  )
}

data_asset_center_filter_active_v1 <- function(input) {
  !identical(input$holding, "any") || length(input$account_refs) > 0L || length(input$asset_types) > 0L
}

# Was die Filterleiste anbietet: die Typen, die es im Katalog gibt, und die
# Konten, die Non-Cash-Bestaende fuehren koennen.
data_asset_center_filter_options_v1 <- function(assets, accounts, bridge) {
  labels <- data_asset_center_filter_type_labels_v1()
  present <- if (length(assets)) unique(vapply(assets, `[[`, character(1L), "asset_type")) else character()
  types <- names(labels)[names(labels) %in% present]
  usable <- Filter(function(row) nzchar(bridge("account", row$ref)), accounts)
  account_labels <- vapply(usable, `[[`, character(1L), "display_name")
  counts <- table(account_labels)
  list(
    asset_types = stats::setNames(types, unname(labels[types])),
    accounts = stats::setNames(
      vapply(usable, `[[`, character(1L), "ref"),
      vapply(seq_along(usable), function(index) {
        label <- account_labels[[index]]
        if (counts[[label]] == 1L) label else paste(label, "· Auswahl", sum(account_labels[seq_len(index)] == label), "von", counts[[label]])
      }, character(1L))
    )
  )
}

# rows: die sichtbaren Assets des Katalogs in ihrer Reihenfolge. Ergebnis: `keep`
# je Zeile, `pinned` fuer das gewaehlte Asset ausserhalb des Filters, und der
# Zustand fuer die Statuszeile.
data_asset_center_filter_apply_v1 <- function(rows, input, catalog, read_view, bridge, selected_ref = "") {
  if (!is.list(rows) || !is.list(input) || !is.function(bridge)) stop("data_asset_center_filter_invalid", call. = FALSE)
  total <- length(rows)
  refs <- if (total) vapply(rows, `[[`, character(1L), "ref") else character()
  off <- function(status, reason = NULL) list(
    keep = rep(TRUE, total), pinned = rep(FALSE, total),
    state = list(status = status, reason = reason, matched = total, total = total, pinned = FALSE,
      holding_status = "not_requested", account_status = "not_requested")
  )
  if (!data_asset_center_filter_active_v1(input)) return(off("off"))
  if (is.null(catalog) || is.null(read_view)) return(off("unavailable", "activity_view_missing"))
  account_refs <- vapply(input$account_refs, function(ref) bridge("account", ref), character(1L), USE.NAMES = FALSE)
  account_refs <- unique(account_refs[nzchar(account_refs)])
  result <- tryCatch(
    asset_filter_resolve_v1(catalog, read_view, input$holding, account_refs, input$asset_types),
    spot_asset_selection_context_error = function(error) NULL
  )
  if (is.null(result)) return(off("unavailable", "filter_rejected"))
  matched <- if (length(result$matched_assets)) vapply(result$matched_assets, `[[`, character(1L), "ref") else character()
  # Was die Buchungssicht nicht kennt, hat dort weder Bestand noch Konto; nur der
  # Typ laesst sich an der Katalogzeile selbst pruefen.
  outside <- identical(input$holding, "any") && !length(input$account_refs)
  keep <- vapply(rows, function(row) {
    activity_ref <- bridge("asset", row$ref)
    if (nzchar(activity_ref)) activity_ref %in% matched
    else outside && (!length(input$asset_types) || row$asset_type %in% input$asset_types)
  }, logical(1L))
  pinned <- !keep & refs == selected_ref & nzchar(selected_ref)
  list(
    keep = keep, pinned = pinned,
    state = list(status = "applied", reason = result$unavailable_reason, matched = as.integer(sum(keep)), total = total,
      pinned = any(pinned), holding_status = result$holding_status, account_status = result$account_status)
  )
}

# Die Statuszeile unter der Filterleiste. NULL heisst: nichts anzeigen.
data_asset_center_filter_text_v1 <- function(state) {
  if (!is.list(state) || !is.character(state$status) || length(state$status) != 1L) stop("data_asset_center_filter_invalid", call. = FALSE)
  if (identical(state$status, "off")) return(NULL)
  if (identical(state$status, "unavailable")) return(list(tone = "warning",
    copy = "Filter derzeit nicht anwendbar – die Buchungen sind noch nicht gelesen. Es werden alle Assets gezeigt."))
  parts <- if (state$matched == 0L) "Filter aktiv: Kein Asset passt." else
    sprintf("Filter aktiv: %d von %d Assets.", state$matched, state$total)
  if (isTRUE(state$pinned)) parts <- c(parts, "Das gewählte Asset liegt außerhalb des Filters und bleibt wählbar.")
  if (identical(state$holding_status, "unavailable")) parts <- c(parts,
    "Der Bestand lässt sich gerade nicht prüfen, weil der FIFO-Stand nicht frisch ist; dieses Kriterium ist ausgesetzt.")
  if (identical(state$account_status, "unavailable")) parts <- c(parts,
    "Die Konten lassen sich nicht prüfen, weil es noch keine Buchungen gibt; dieses Kriterium ist ausgesetzt.")
  suspended <- "unavailable" %in% c(state$holding_status, state$account_status)
  list(tone = if (suspended || state$matched == 0L) "warning" else "neutral", copy = paste(parts, collapse = " "))
}
