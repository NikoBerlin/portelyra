# Session-local presentation only: no command, persistence, or confirmation authority.
# Origin: existing Next state()/observeEvent boundaries, not legacy code.
new_data_action_feedback_v1 <- function(initial) {
  latest <- shiny::reactiveVal(initial)
  messages <- shiny::reactiveValues()
  scope <- NULL
  state <- function(value) {
    if (missing(value)) return(latest())
    stopifnot(is.list(value), is.character(value$title), is.character(value$copy))
    latest(value)
    if (!is.null(scope)) messages[[scope]] <- value
    invisible(value)
  }
  run <- function(area, expression) {
    previous <- scope
    scope <<- area
    on.exit(scope <<- previous, add = TRUE)
    force(expression)
  }
  observe <- function(area, eventExpr, handlerExpr, ...) {
    caller <- parent.frame()
    bound <- new.env(parent = caller)
    bound$.action_run <- run
    bound$.action_area <- area
    shiny::observeEvent(
      eventExpr = substitute(eventExpr), event.env = caller, event.quoted = TRUE,
      handlerExpr = bquote(.action_run(.action_area, .(substitute(handlerExpr)))),
      handler.env = bound, handler.quoted = TRUE, ...
    )
  }
  list(
    state = state, run = run, observe = observe,
    read = function(area) messages[[area]],
    clear = function(areas) { for (area in areas) messages[[area]] <- NULL; invisible(NULL) }
  )
}

data_action_feedback_panel_v1 <- function(value) {
  if (is.null(value)) return(NULL)
  shiny::div(role = "status", `aria-live` = "polite", `aria-atomic` = "true",
    portelyra_status_panel(value$title, value$copy, tone = value$tone))
}

data_provider_action_hint_v1 <- function(phase, mapped, verified, preview, probe, published) {
  stopifnot(phase %in% c('mapping', 'probe', 'promotion', 'verification'))
  copy <- switch(phase,
    mapping = if(preview) 'Vorschau prüfen, genau diese Zuordnung bestätigen und speichern. Ein Vorschlag allein ist weder gespeichert noch verifiziert.' else if(mapped) 'Eine Zuordnung ist gespeichert. Nur bei einer gewünschten Änderung erneut prüfen; weiter geht es mit „Jetzt einrichten“.' else 'Zuordnung im Formular prüfen. Ein Suchvorschlag füllt nur das Formular; Speicherung separat bestätigen.',
    probe = if(verified) 'Die Kursquelle ist aktiv. Kein weiterer Testabruf nötig; fehlende Historie separat planen.' else if(published) 'Die Testhistorie ist bereits gespeichert. Kein weiterer Testabruf nötig; Kursquelle separat verifizieren.' else if(probe) 'Gespeicherte Testdaten sind vorhanden. Keinen neuen Testabruf starten; ihre Übernahme unten prüfen.' else if(!mapped) 'Zuerst eine Zuordnung speichern. Noch kein Testabruf möglich.' else if(preview) 'Symbol, Währung und Zeitraum der Vorschau prüfen. Genau einen Testabruf bestätigen; er speichert einen Testnachweis, noch keine freigegebene Historie.' else 'Für die gespeicherte Zuordnung zuerst eine Testabruf-Vorschau erstellen. Noch kein Abruf.',
    promotion = if(published) 'Testhistorie gespeichert. Keine erneute Übernahme nötig; die Kursquelle separat verifizieren, falls noch offen.' else if(!probe) 'Zuerst einen gespeicherten Testnachweis laden oder einen ausdrücklich bestätigten Test durchführen. Noch keine Historienübernahme möglich.' else if(preview) 'Zeitraum, Tage und Lücken prüfen. Die separate Bestätigung veröffentlicht genau diese Testhistorie, ohne neuen Abruf.' else 'Gespeicherte Testdaten prüfen: Markt, Zeitzone und Kalender kontrollieren, danach die Übernahme der Historie prüfen. Noch keine Veröffentlichung.',
    verification = if(verified) 'Kursquelle bestätigt und aktiv. Diese Aufgabe ist abgeschlossen; weitere Historienabrufe bleiben separat bestätigt.' else if(!published) 'Zuerst die geprüfte Testhistorie separat übernehmen. Die Verifizierung benötigt diesen gespeicherten Nachweis; ein Suchvorschlag genügt nicht.' else if(preview) 'Gehören Asset, Symbol, Handelsplatz und Währung zusammen? Genau diese geprüfte Kursquelle bestätigen und aktivieren; kein neuer Abruf.' else 'Die Testdaten allein beweisen nicht die Assetidentität. Zuordnung mit dem Testnachweis prüfen, danach ausdrücklich aktivieren.'
  )
  list(title = 'Nächster Schritt', copy = copy, tone = 'neutral')
}
