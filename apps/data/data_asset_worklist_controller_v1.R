# Sequential controller of the provider-mapping worklist. Inventory and identity resolution are trusted callbacks.
# Die Stammdaten-Variante (master) ist seit rc.309 entfernt: Sie stammte aus dem einmaligen Legacy-Import (Festlegung 23.10.2026).
data_asset_worklist_server_v1 <- function(input, output, session, prefix, service,
    inventory, choose, selected_id, get_draft, verify_inventory = inventory) {
  id <- function(suffix) paste0(prefix, "_", suffix)
  model <- shiny::reactiveVal(NULL)
  active <- shiny::reactiveVal(FALSE)
  notice <- shiny::reactiveVal("Noch keine Arbeitsliste geladen. Navigation speichert nichts.")
  safe <- function(operation) tryCatch(operation(), error = function(e) {
    active(FALSE)
    notice("Arbeitsliste blockiert. Gespeicherte Arbeitsliste erneut lesen; keinen Vorgang an Stammdaten oder Kurszuordnung auf Verdacht wiederholen.")
  })
  rows <- function() {
    value <- model(); if (is.null(value)) return(list())
    current <- inventory()
    lapply(seq_along(value$items), function(i) {
      item <- value$items[[i]]
      found <- Filter(function(row) identical(row$asset_id, item$asset_id), current)
      row <- if (length(found) == 1L) found[[1L]] else NULL
      list(ordinal = i, item = item, current = row)
    })
  }
  present <- function(value, navigate = TRUE) {
    force(value); model(value)
    if (is.null(value)) { notice("Keine gespeicherte Arbeitsliste vorhanden."); return(invisible(NULL)) }
    public_rows <- rows()
    choices <- stats::setNames(vapply(public_rows, function(r) as.character(r$ordinal), character(1L)),
      vapply(public_rows, function(r) paste(r$ordinal, if (is.null(r$current)) "Asset nicht mehr verfügbar" else r$current$label, "·", r$item$status), character(1L)))
    shiny::updateSelectInput(session, id("item"), choices = choices, selected = as.character(value$cursor + 1L))
    notice(paste("Eintrag", value$cursor + 1L, "von", length(value$items), "·",
      sum(vapply(value$items, function(r) r$status %in% c("reviewed", "mapping_saved"), logical(1L))), "bearbeitet · keine automatische Aktion beim Kursanbieter"))
    if (navigate) {
      row <- public_rows[[value$cursor + 1L]]
      if (is.null(row$current) || !isTRUE(row$current$eligible)) {
        active(FALSE); notice("Ausgewähltes Asset nicht mehr providerfähig/verfügbar. Eintrag bleibt erhalten; Stammdaten prüfen oder anderen Eintrag öffnen.")
      } else {
        active(TRUE)
        # Existing canonical mappings take precedence over unconfirmed drafts.
        restored <- if (row$item$status %in% c("reviewed", "mapping_saved") || !isTRUE(row$current$missing)) NULL else row$item$draft
        choose(row$current$asset_ref, restored, "provider")
      }
    }
    invisible(value)
  }
  selected <- function() {
    value <- model()
    if (!isTRUE(active()) || is.null(value)) stop("worklist_not_active")
    item <- value$items[[value$cursor + 1L]]
    if (!identical(item$asset_id, selected_id())) stop("worklist_selection_changed")
    item
  }
  update <- function(status, advance = TRUE) {
    item <- selected(); current <- Filter(function(r) identical(r$asset_id, item$asset_id), verify_inventory())
    if (length(current) != 1L) stop("worklist_asset_unavailable")
    if (status == "mapping_saved" && isTRUE(current[[1L]]$missing)) stop("worklist_mapping_unproven")
    # Completed entries retain their disposition, not stale form defaults.
    draft <- if (status %in% c("reviewed", "mapping_saved")) NULL else get_draft()
    present(service$update(item$asset_id, status, draft, advance), navigate = advance)
  }
  shiny::observe({
    current <- inventory()
    eligible <- Filter(function(r) isTRUE(r$eligible), current)
    choices <- stats::setNames(vapply(eligible, `[[`, character(1L), "asset_ref"),
      vapply(eligible, function(r) paste(r$label, "·", r$asset_ref), character(1L)))
    shiny::updateSelectizeInput(session, id("selection"), choices = choices, server = TRUE)
  })
  shiny::observeEvent(input[[id("start")]], safe(function() {
    current <- inventory(); refs <- input[[id("selection")]]
    chosen <- if (length(refs)) Filter(function(r) r$asset_ref %in% refs && isTRUE(r$eligible), current)
      else Filter(function(r) isTRUE(r$eligible) && isTRUE(r$missing), current)
    if (!length(chosen) || (length(refs) && length(chosen) != length(unique(refs)))) stop("worklist_selection_invalid")
    chosen <- chosen[order(vapply(chosen, `[[`, character(1L), "label"), vapply(chosen, `[[`, character(1L), "asset_id"))]
    present(service$start(vapply(chosen, `[[`, character(1L), "asset_id")))
  }))
  shiny::observeEvent(input[[id("load")]], safe(function() present(service$read())))
  shiny::observeEvent(input[[id("pause")]], safe(function() {
    status <- selected()$status
    if (status %in% c("reviewed", "mapping_saved")) status <- "pending"
    update(status, FALSE); active(FALSE); notice("Entwurf gespeichert · pausiert. Fortsetzen liest nur die Arbeitsliste; keine Bestätigung wurde gespeichert.")
  }))
  shiny::observeEvent(input[[id("skip")]], safe(function() update("skipped")))
  shiny::observeEvent(input[[id("defer")]], safe(function() update("deferred")))
  shiny::observeEvent(input[[id("reviewed")]], safe(function() {
    update("mapping_saved")
  }))
  shiny::observeEvent(input[[id("open")]], safe(function() {
    value <- model(); index <- suppressWarnings(as.integer(input[[id("item")]]))
    if (is.null(value) || length(index) != 1L || is.na(index) || index < 1L || index > length(value$items)) stop("worklist_selection_invalid")
    present(service$select(value$items[[index]]$asset_id))
  }))
  shiny::observeEvent(input[[id("back")]], safe(function() {
    value <- model(); if (is.null(value)) stop("worklist_not_loaded")
    present(service$select(value$items[[max(1L, value$cursor)]]$asset_id))
  }))
  output[[id("status")]] <- shiny::renderUI(shiny::p(notice()))
  output[[id("table")]] <- shiny::renderTable({
    value <- rows(); if (!length(value)) return(data.frame())
    labels <- c(pending = "Offen", deferred = "Später klären", skipped = "Übersprungen", reviewed = "Stammdaten geprüft", mapping_saved = "Zuordnung gespeichert · Verifizierung separat")
    do.call(rbind, lapply(value, function(r) data.frame(Eintrag = r$ordinal,
      Asset = if (is.null(r$current)) "Nicht mehr verfügbar" else r$current$label,
      Disposition = unname(labels[r$item$status]),
      Aktuell = if (is.null(r$current)) "nicht verfügbar" else if (!r$current$eligible) "nicht providerfähig" else r$current$mapping_label,
      check.names = FALSE)))
  })
  list(mapping_saved = function() { if (isTRUE(active())) safe(function() update("mapping_saved")) },
       active = active)
}
