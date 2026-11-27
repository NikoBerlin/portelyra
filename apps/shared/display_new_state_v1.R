# Neuer Stand veroeffentlicht (#457): Analyse, Cockpit und Steuer lesen beim Laden und auf Knopfdruck. Laeuft danach in der
# Data-App "Alles aktualisieren", zeigt die Seite weiter den alten Stand, ohne es zu sagen (Festlegung 21.10.2026). Jede dieser
# Apps fragt deshalb alle 15 Sekunden die Zeiger ihrer Bereiche ab (nur latest.json, kein Artefakt) und bietet "Neu lesen" an,
# sobald sich einer seit dem Laden geaendert hat. Gelesen wird nur, was die Rolle ohnehin lesen darf; ein unlesbarer Zeiger zeigt
# keinen Hinweis.
display_new_state_marker_v1 <- function(context, areas) {
  markers <- vapply(areas, function(area) {
    value <- tryCatch(spotdisplay::display_latest_marker_v1(context, area), error = function(error) NA_character_)
    if (is.character(value) && length(value) == 1L) value else NA_character_
  }, character(1L))
  paste(areas, ifelse(is.na(markers), "-", markers), sep = "=", collapse = ";")
}

display_new_state_server_v1 <- function(output, session, id, marker, interval_ms = 15000L, button = "„Neu lesen“ oben rechts") {
  loaded <- shiny::reactiveVal(NULL)
  read <- function() tryCatch(marker(), error = function(error) NA_character_)
  current <- shiny::reactivePoll(interval_ms, session, checkFunc = read, valueFunc = read)
  output[[id]] <- shiny::renderUI({
    now <- current(); was <- loaded()
    if (is.null(was) || is.na(was) || is.na(now) || identical(now, was)) return(NULL)
    portelyra_status_panel("Neuer Stand veröffentlicht",
      paste0("Seit dem Laden dieser Seite ist ein neuer Stand erschienen, etwa nach „Alles aktualisieren“. ", button,
             " lädt ihn; bis dahin zeigt die Seite den vorigen Stand."), tone = "warning")
  })
  # Nach jedem Laden aufrufen: Der jetzige Zeiger gilt dann als gelesen.
  list(mark = function() loaded(read()), loaded = loaded)
}
