# Kleinstbestaende ausbuchen (#534, Festlegung 04.11.2026): nur auf geschlossenen Konten, als Auszahlung „Restguthaben bei
# Aufloesung“. Auf einem ruhenden oder aktiven Konto liegt das Geld noch bei der Bank - ausgebucht passte der naechste Saldo nicht.
#
# Kein eigener Schreibweg: Die Karte nennt die Reste und fuellt das Formular „Cash-Buchung eintragen“ vor; geprueft, bestaetigt
# und gebucht wird dort wie jede Cash-Buchung. Saldo und Kontozustand stammen aus dem juengsten Stichtags-Snapshot (seit rc.360
# mit `account_state`), der Schliesstag aus der Ablage, der letzte Saldo-Abgleich aus der Cash-Sicht.
#
# Abgestimmte Konten (#538): Dort gilt der Saldo des letzten Abgleichs; eine spaetere Auszahlung
# zaehlt erst mit einem neuen Abgleich. Die Karte fuellt deshalb auch „Saldo prüfen · Abdeckung abstimmen“ vor (Konto, Tag der
# Ausbuchung, Saldo 0) und sagt, dass erst beides zusammen den Rest auf 0 setzt. Ist die Auszahlung schon gebucht, nur noch das.

# Der Tag der Ausbuchung: der Schliesstag - liegt der letzte Saldo-Abgleich an oder nach ihm, der Tag danach. Eine Auszahlung am
# Tag des Abgleichs braeche ihn.
data_small_holdings_write_off_day_v1 <- function(closed_on, reconciled_on = NULL) {
  closed <- as.Date(closed_on)
  reconciled <- if (length(reconciled_on)) suppressWarnings(max(as.Date(unlist(reconciled_on)), na.rm = TRUE)) else NA
  if (length(reconciled) == 1L && !is.na(reconciled) && is.finite(reconciled) && reconciled >= closed) reconciled + 1 else closed
}

# Die Reste: Cash-Zeilen des Snapshots auf geschlossenen Konten, in Euro, ueber 0 und unter der Grenze. `closed_on` je Kontoname
# (aus der Ablage), `periods` die Zeitraeume der Cash-Sicht (mit `account_label`, `as_of_date`, `balance_status`), `events` ihre
# Bewegungen (mit `account_label`, `local_date`, `event_type`, `amount_decimal`) - daran erkennt die Karte eine schon gebuchte
# Ausbuchung.
data_small_holdings_write_off_candidates_v1 <- function(snapshot, closed_on, periods = list(), threshold = "1", events = list()) {
  limit <- suppressWarnings(as.numeric(threshold))
  if (!is.list(snapshot) || !is.list(snapshot$cash) || length(limit) != 1L || is.na(limit) || limit <= 0) return(list())
  rows <- list()
  for (account in snapshot$cash$accounts) {
    label <- account$account_label; balance <- suppressWarnings(as.numeric(account$balance_decimal))
    day <- closed_on[[if (is.character(label)) label else ""]]
    if (!identical(account$account_state, "closed") || !identical(account$currency, "EUR") || length(balance) != 1L || is.na(balance) ||
        balance == 0 || abs(balance) >= limit || !is.character(day) || length(day) != 1L || is.na(day)) next
    reconciled <- unlist(lapply(periods, function(period) if (identical(period$account_label, label) && identical(period$balance_status, "complete_reconciled"))
      period$as_of_date else NULL))
    off_day <- data_small_holdings_write_off_day_v1(day, reconciled); kind <- if (balance > 0) "withdrawal" else "deposit"
    amount <- sub("^-", "", account$balance_decimal)
    booked <- any(vapply(events, function(event) identical(event$account_label, label) && identical(event$event_type, kind) &&
      identical(as.character(event$local_date), format(off_day)) && isTRUE(suppressWarnings(as.numeric(event$amount_decimal)) == as.numeric(amount)), logical(1L)))
    rows[[length(rows) + 1L]] <- list(account_label = label, balance_decimal = account$balance_decimal, closed_on = day,
      day = off_day, kind = kind, amount_decimal = amount, reconciled = length(reconciled) > 0L, booked = booked)
  }
  rows[order(vapply(rows, function(row) tolower(row$account_label), character(1L)))]
}

# Was fuer einen Rest noch zu tun ist: buchen, abstimmen oder beides.
data_small_holdings_step_v1 <- function(row) {
  booking <- if (identical(row$kind, "withdrawal")) "Abgang (Restguthaben bei Auflösung)" else "Zugang (Restschuld ausgleichen)"
  if (isTRUE(row$booked) && isTRUE(row$reconciled)) return("gebucht – noch „Saldo prüfen“ mit 0,00 €")
  if (isTRUE(row$booked)) return("gebucht – fällt mit dem nächsten „Alles aktualisieren“ weg")
  if (isTRUE(row$reconciled)) return(paste(booking, "und „Saldo prüfen“ mit 0,00 €"))
  booking
}

data_small_holdings_frame_v1 <- function(rows) {
  if (!length(rows)) return(data.frame())
  data.frame(Konto = vapply(rows, function(row) row$account_label, character(1L)),
             Saldo = vapply(rows, function(row) pl_amount_v1(row$balance_decimal, "EUR", 2L, "—"), character(1L)),
             `geschlossen seit` = vapply(rows, function(row) pl_day_v1(row$closed_on), character(1L)),
             `ausbuchen am` = vapply(rows, function(row) pl_day_v1(format(row$day)), character(1L)),
             Buchung = vapply(rows, function(row) data_small_holdings_step_v1(row), character(1L)),
             check.names = FALSE, stringsAsFactors = FALSE)
}

data_small_holdings_card_ui_v1 <- function() shiny::tags$details(class = "pl-disclosure pl-lazy", id = "data_small_holdings",
  shiny::tags$summary("Kleinstbestände auf geschlossenen Konten ausbuchen"),
  shiny::p(class = "pl-field-hint", paste(
    "Ein Rest unter der Grenze aus den Einstellungen auf einem geschlossenen Konto lässt sich als Auszahlung „Restguthaben bei Auflösung“ ausbuchen.",
    "Die Karte füllt „Cash-Buchung eintragen“ vor; geprüft, bestätigt und gebucht wird dort. Ausgebucht wird am Schließtag – liegt der letzte",
    "Saldo-Abgleich an oder nach ihm, am Tag danach. Ruhende und aktive Konten bleiben: Dort liegt das Geld noch bei der Bank.",
    "Bei einem abgestimmten Konto füllt sie auch „Saldo prüfen“ mit 0,00 € vor: Erst Buchung und Abgleich zusammen setzen den Rest auf 0.",
    "Grundlage ist der jüngste Stichtags-Snapshot; nach dem Buchen verschwindet der Rest mit dem nächsten „Alles aktualisieren“.")),
  shiny::div(class = "pl-table-wrap", shiny::tableOutput("data_small_holdings_rows")),
  shiny::div(class = "pl-form-grid", shiny::selectInput("data_small_holdings_pick", "Rest", choices = c("wird gelesen …" = ""))),
  shiny::div(class = "pl-editor-actions", shiny::actionButton("data_small_holdings_prefill", "In „Cash-Buchung eintragen“ übernehmen", class = "btn-default")),
  shiny::uiOutput("data_small_holdings_notice"))

# `read`: liefert list(snapshot, closed_on, periods, threshold, events) oder wirft. `prefill(row)`: fuellt „Cash-Buchung eintragen“
# (ausser bei `row$booked`) und bei `row$reconciled` auch „Saldo prüfen“; gibt TRUE zurueck, wenn das Konto dort waehlbar ist.
data_small_holdings_server_v1 <- function(input, output, session, read, prefill) {
  rows <- shiny::reactiveVal(list()); notice <- shiny::reactiveVal(NULL)
  load <- function() {
    value <- tryCatch(read(), error = function(error) NULL)
    if (is.null(value)) { rows(list()); notice(list(tone = "warning", title = "Nicht lesbar", copy = "Snapshot, Ablage oder Cash-Sicht ließen sich nicht lesen.")); return(invisible(NULL)) }
    found <- data_small_holdings_write_off_candidates_v1(value$snapshot, value$closed_on, value$periods, value$threshold,
      if (is.list(value$events)) value$events else list())
    rows(found); notice(if (!length(found)) list(tone = "neutral", title = "Nichts auszubuchen", copy = "Kein Rest unter der Grenze auf einem geschlossenen Konto.") else NULL)
    choices <- if (length(found)) stats::setNames(as.character(seq_along(found)), vapply(found, function(row) sprintf("%s · %s", row$account_label,
      pl_amount_v1(row$balance_decimal, "EUR", 2L, "")), character(1L))) else c("Kein Rest" = "")
    shiny::updateSelectInput(session, "data_small_holdings_pick", choices = choices)
  }
  shiny::observeEvent(input$data_small_holdings_open, if (isTRUE(input$data_small_holdings_open)) load(), ignoreInit = TRUE)
  output$data_small_holdings_rows <- shiny::renderTable(data_small_holdings_frame_v1(rows()), striped = TRUE, spacing = "xs")
  shiny::observeEvent(input$data_small_holdings_prefill, {
    index <- suppressWarnings(as.integer(input$data_small_holdings_pick)); found <- rows()
    if (length(index) != 1L || is.na(index) || index < 1L || index > length(found)) {
      notice(list(tone = "warning", title = "Kein Rest gewählt", copy = "Bitte zuerst einen Rest wählen.")); return()
    }
    row <- found[[index]]
    if (isTRUE(row$booked) && !isTRUE(row$reconciled)) {
      notice(list(tone = "neutral", title = "Schon gebucht", copy = sprintf("Die Ausbuchung auf „%s“ ist gebucht; der Rest fällt mit dem nächsten „Alles aktualisieren“ weg.",
        row$account_label))); return()
    }
    if (!isTRUE(prefill(row))) {
      notice(list(tone = "warning", title = "Konto nicht wählbar", copy = sprintf("„%s“ steht im Formular nicht zur Wahl. Bitte unter „Cash“ die Konten neu laden.", row$account_label))); return()
    }
    day <- pl_day_v1(format(row$day)); check <- sprintf("„Saldo prüfen“ steht auf %s, Stand am %s, Saldo 0,00 €", row$account_label, day)
    booking <- sprintf("„Cash-Buchung eintragen“ steht auf %s, %s, %s %s", row$account_label, day,
      if (identical(row$kind, "withdrawal")) "Abgang" else "Zugang", pl_amount_v1(row$amount_decimal, "EUR", 2L, ""))
    copy <- if (isTRUE(row$booked)) paste0("Die Ausbuchung ist gebucht. ", check, ": „Saldo prüfen“, die Vorschau bestätigen und „Abstimmung festhalten“.")
      else if (isTRUE(row$reconciled)) paste0(booking, "; ", check, ". Das Konto ist abgestimmt: Erst beides zusammen setzt den Rest auf 0 –",
        " zuerst „Buchung prüfen“, bestätigen und „Buchen“, danach „Saldo prüfen“, bestätigen und „Abstimmung festhalten“.")
      else paste0(booking, ". Jetzt „Buchung prüfen“, die Vorschau bestätigen und „Buchen“.")
    notice(list(tone = "neutral", title = "Vorbelegt", copy = copy))
  }, ignoreInit = TRUE)
  output$data_small_holdings_notice <- shiny::renderUI({ value <- notice(); if (is.list(value)) portelyra_status_panel(value$title, value$copy, tone = value$tone) })
  invisible(list(load = load, rows = rows, notice = notice))
}
