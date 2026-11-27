# Tageshistorie (#473) in der Data-App: Stand lesen und fortschreiben. Die Rechnung liegt in
# workers/reference/portfolio_history_v1.py; diese Karte zeigt nur Tagessummen und den letzten Lauf.

data_portfolio_history_card_ui_v1 <- function() portelyra_card(
  "Tageshistorie",
  copy = "Je Tag, Konto und Asset: Menge, Kurs und Wert, dazu Cash je Konto und die Tagessummen – gerechnet wie der Stichtags-Snapshot.",
  note = portelyra_note_v1(title = "Hinweise zur Bedienung", id = "data-daily-history", paste(
    "Fortgeschrieben wird nur, was sich geändert hat: neue Tage kommen dazu, ein Nachtrag für einen vergangenen Tag rechnet ab diesem Tag nach.",
    "Danach wird die Reihe für die Analyse veröffentlicht, wenn sie sich geändert hat.",
    "Vorher den FIFO-Stand aktualisieren (oben); mit veraltetem Stand hält der Lauf an. Kein Kursabruf, keine Buchung.")),
  class = "pl-write-boundary",
  shiny::uiOutput("portfolio_history_state"),
  shiny::div(class = "pl-editor-actions",
    shiny::actionButton("portfolio_history_update", "Tageshistorie fortschreiben", class = "btn-primary"),
    shiny::checkboxInput("portfolio_history_rebuild", "Von vorn rechnen (Prüfung; geschrieben wird nur, was sich unterscheidet)", FALSE)))

# Die Veroeffentlichung fuer die Analyse (#473) als Satz. NULL heisst: Sie schlug fehl; der naechste Lauf versucht es erneut.
data_portfolio_history_publication_copy_v1 <- function(published) {
  if (is.null(published)) return(" Die Veröffentlichung für die Analyse schlug fehl; der nächste Lauf versucht es erneut.")
  switch(as.character(published$status), published = " Für die Analyse veröffentlicht.",
         already_published = " Die Analyse zeigt bereits diesen Stand.", "")
}

# Der Zustand als Satz: wie weit die Reihe reicht und was der letzte Lauf getan hat.
data_portfolio_history_state_v1 <- function(read = NULL, result = NULL, error = NULL, published = list(status = "absent")) {
  day <- function(value) if (is.null(value) || !nzchar(value)) "–" else format(as.Date(value), "%d.%m.%Y")
  if (!is.null(error)) {
    copy <- if (grepl("portfolio_history_fifo_stale", error, fixed = TRUE))
      "Der Rechenstand der Bestände liegt zurück. Bitte unter „Transaktionen → Bestand prüfen“ nachrechnen, dann erneut fortschreiben."
      else paste("Die Tageshistorie konnte nicht fortgeschrieben werden:", error)
    return(list(tone = "error", title = "Nicht fortgeschrieben", copy = copy))
  }
  if (!is.null(result)) {
    copy <- if (is.null(result$recomputed_from)) paste0("Nichts geändert – die Reihe reicht vom ", day(result$first_day), " bis ", day(result$last_day), ".")
      else paste0(result$computed_day_count, " Tag(e) ab dem ", day(result$recomputed_from), " gerechnet, ", result$written_day_count,
                  " geändert gespeichert. Die Reihe reicht vom ", day(result$first_day), " bis ", day(result$last_day), ".")
    return(list(tone = "positive", title = "Tageshistorie fortgeschrieben",
                copy = paste0(copy, " Dauer ", format(round(as.numeric(result$duration_ms) / 1000, 1), nsmall = 1, decimal.mark = ","), " s.",
                              data_portfolio_history_publication_copy_v1(published))))
  }
  if (is.null(read) || identical(read$status, "absent") || !length(read$days)) {
    return(list(tone = "neutral", title = "Noch keine Tageshistorie", copy = "Mit „Tageshistorie fortschreiben“ entsteht sie einmal vollständig; danach kommen nur neue oder geänderte Tage dazu."))
  }
  days <- read$days; last <- days[[length(days)]]; run <- read$last_run
  list(tone = "neutral", title = paste0("Tageshistorie bis ", day(last$day)),
       copy = paste0(length(days), " Tage ab dem ", day(days[[1L]]$day), ". Gesamtvermögen am letzten Tag ",
                     if (is.null(last$net_worth_decimal)) "nicht verfügbar" else paste(format(round(as.numeric(last$net_worth_decimal), 2), big.mark = ".", decimal.mark = ",", nsmall = 2), "€"),
                     if (!is.null(run)) paste0(" · zuletzt fortgeschrieben ", format(as.POSIXct(run$requested_at_utc, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), "%d.%m.%Y %H:%M", tz = "Europe/Berlin")) else "", "."))
}

data_portfolio_history_server_v1 <- function(input, output, session, service, now_utc) {
  state <- shiny::reactiveVal(NULL)
  read <- function() {
    if (is.null(service)) return(invisible(NULL))
    state(tryCatch(data_portfolio_history_state_v1(read = service$history_read()),
                   error = function(error) data_portfolio_history_state_v1(error = conditionMessage(error))))
  }
  # Gelesen wird erst, wenn "Alles aktualisieren" in der Kopfzeile aufgeklappt wird (#368), nicht beim Sitzungsstart.
  shiny::observeEvent(input$refresh_all_panel_open, if (isTRUE(input$refresh_all_panel_open) && is.null(state())) read(), ignoreInit = TRUE)
  shiny::observeEvent(input$portfolio_history_update, {
    if (is.null(service)) { state(list(tone = "error", title = "Nicht verfügbar", copy = "Der Dienst der Tageshistorie ist nicht erreichbar.")); return() }
    state(tryCatch({
      result <- shiny::withProgress(message = "Tageshistorie wird fortgeschrieben", value = 0.3,
        service$history_update(now_utc(), isTRUE(input$portfolio_history_rebuild)))
      shiny::updateCheckboxInput(session, "portfolio_history_rebuild", value = FALSE)
      published <- tryCatch(service$history_publish(now_utc()), error = function(error) NULL)
      data_portfolio_history_state_v1(result = result, published = published)
    }, error = function(error) data_portfolio_history_state_v1(error = conditionMessage(error))))
  })
  output$portfolio_history_state <- shiny::renderUI({
    message <- state()
    if (is.null(message)) return(portelyra_status_panel("Tageshistorie", "Der Stand wird mit dem Reiter gelesen.", tone = "neutral"))
    portelyra_status_panel(message$title, message$copy, tone = message$tone)
  })
  invisible(list(read = read))
}
