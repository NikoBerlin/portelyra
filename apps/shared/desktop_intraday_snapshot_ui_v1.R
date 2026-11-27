# Anzeige der Momentaufnahme - des fluiden Portfoliobilds. Reine Darstellung:
# kein Abruf, keine Rechnung, keine Pfade und keine internen Kennungen im Browser.
#
# Seit rc.242 ist das Bild dieselbe Rechnung wie der Stichtags-Snapshot, nur mit
# den zuletzt abgerufenen Kursen (Festlegung 12.10.2026). Positionen,
# Ueberblick und Cash zeigt die Karte deshalb mit den Bausteinen der
# Stichtags-Karte (desktop_portfolio_snapshot_ui_v1.R); hier steht nur, was die
# Momentaufnahme zusaetzlich sagen muss: von wann sie ist und wie aktuell ihre
# Kurse sind. Ein Kurs vom Freitag sieht am Montag sonst aus wie einer von jetzt
# (#283, 26.09.2026).

.desktop_intraday_text_v1 <- function(value, fallback = "—") {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value)))
    fallback else as.character(value)
}

.desktop_intraday_moment_v1 <- function(value) {
  text <- .desktop_intraday_text_v1(value, "")
  if (!nzchar(text)) return("—")
  parsed <- tryCatch(as.POSIXct(text, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                     error = function(error) NA)
  if (is.na(parsed)) return(text)
  format(parsed, "%d.%m.%Y %H:%M", tz = "", usetz = TRUE)
}

# Exakt gerechnet, lesbar angezeigt: Der Speicher haelt den Wert ungerundet - ein
# Bruch aus Kurs mal Wechselkurs mal Menge hat schnell vierzig Nachkommastellen.
# Gezeigt werden Cent; gerundet wird ausschliesslich hier (#283, 26.09.2026).
.desktop_intraday_amount_v1 <- function(value, digits = 2L) {
  text <- .desktop_intraday_text_v1(value, "")
  if (!nzchar(text)) return("—")
  # Nicht endlich dezimal darstellbare Betraege kommen als exakter Bruch an.
  number <- if (grepl("^-?[0-9]+/[0-9]+$", text)) {
    parts <- as.numeric(strsplit(text, "/", fixed = TRUE)[[1L]])
    parts[[1L]] / parts[[2L]]
  } else suppressWarnings(as.numeric(text))
  if (is.na(number)) return(text)
  formatC(number, format = "f", digits = digits, big.mark = ".", decimal.mark = ",")
}

# Wie aktuell die Kurse der gehaltenen Positionen sind - in Worten. Gezaehlt
# hat der Kern; hier wird nichts gefolgert.
desktop_intraday_summary_copy_v1 <- function(value) {
  if (!is.list(value) || !is.list(value$quotes)) return("Kein Stand.")
  quotes <- value$quotes
  count <- function(name) { number <- suppressWarnings(as.integer(quotes[[name]])); if (length(number) != 1L || is.na(number)) 0L else number }
  recent <- count("observed_within_hour_count"); carried <- count("last_close_count")
  older <- count("observed_earlier_count"); missing <- count("unavailable_count")
  # Gemessen am Zeitpunkt des Abrufs: Ein Kurs vom letzten Handelstag ist
  # gueltig, aber kein Bild von jetzt.
  parts <- c(paste0(recent, if (recent == 1L) " Kurs" else " Kurse", " höchstens eine Stunde alt"),
    if (older > 0L) paste0(older, " älter"),
    if (carried > 0L) paste0(carried, " Tagesschluss statt Momentkurs (Abruf misslungen oder Anbieter ohne Momentkurs)"),
    if (missing > 0L) paste0(missing, " ohne Wert"))
  paste(parts, collapse = " · ")
}

# Wie alt der gezeigte Stand ist. Ein Betrag ohne Alter sieht aus wie eine
# Tatsache; mit Alter sieht er aus, was er ist - eine Beobachtung von vorhin
# (Festlegung 27.09.2026, #373).
.desktop_intraday_age_v1 <- function(value) {
  text <- .desktop_intraday_text_v1(value, "")
  if (!nzchar(text)) return("")
  parsed <- tryCatch(as.POSIXct(text, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                     error = function(error) NA)
  if (is.na(parsed)) return("")
  minutes <- as.numeric(difftime(Sys.time(), parsed, units = "mins"))
  if (is.na(minutes) || minutes < 0) return("")
  if (minutes < 1) return("gerade eben")
  ago <- function(count, one, many) paste0("vor ", count, " ", if (count == 1) one else many)
  if (minutes < 60) return(ago(round(minutes), "Minute", "Minuten"))
  hours <- minutes / 60
  if (hours < 24) return(ago(round(hours), "Stunde", "Stunden"))
  ago(round(hours / 24), "Tag", "Tagen")
}

# `modules`: die Bausteine eines veroeffentlichten Umfangs (#542) oder NULL. Die Momentaufnahme holt aktuelle Kurse und gehoert zu den
# Marktdaten; ohne sie heisst ein fehlendes Bild „nicht geführt, wie gewählt (Umfang)“ statt „noch keine“, und ein Wert nicht „Marktwert“.
desktop_intraday_state_ui_v1 <- function(value, notice = NULL, modules = NULL) {
  panels <- list()
  if (is.list(notice)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      .desktop_intraday_text_v1(notice$title, "Hinweis"),
      .desktop_intraday_text_v1(notice$copy, ""),
      tone = .desktop_intraday_text_v1(notice$tone, "neutral"))
  }
  # Steht immer da, auch ohne Stand. Zwei Reiter zeigen Betraege aehnlicher Groesse aus derselben Rechnung; verbindlich fuer
  # einen Tag ist nur der Stichtags-Snapshot (27.09.2026, #373; neu gefasst 12.10.2026). Seit rc.313 veroeffentlicht „Alles
  # aktualisieren“ die Momentaufnahme zum Schluss; die Analyse zeigt sie (#478).
  panels[[length(panels) + 1L]] <- shiny::p(class = "pl-field-hint", paste(
    "Vorläufiges Bild von jetzt: dieselbe Rechnung wie der Stichtags-Snapshot, mit den zum Schluss von „Alles aktualisieren“ abgerufenen Kursen.",
    "Tagesfrisch, aber kein Tagesschluss — jeder Lauf ersetzt sie.",
    "Verbindlich für einen Tag ist der Stichtags-Snapshot."))
  if ((!is.list(value) || identical(value$status, "absent")) && is.list(modules) && isFALSE(modules[["market_data"]])) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      "Momentaufnahme nicht geführt, wie gewählt (Umfang)",
      paste("Die Momentaufnahme holt für jedes Asset den aktuellen Kurs und gehört zum Baustein Marktdaten, der im Umfang nicht eingeschaltet ist.",
            "Zuschalten unter Daten → „Einstellungen“ → „Portfolio“ → „Umfang dieses Portfolios“."),
      tone = "neutral")
    return(do.call(shiny::tagList, panels))
  }
  if (!is.list(value) || identical(value$status, "absent")) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      "Noch keine Momentaufnahme",
      paste("„Alles aktualisieren“ in der App „Daten“ holt zum Schluss für jedes Asset den aktuellen Kurs und veröffentlicht das Bild.",
            "Bestand, eigene Bewertung und Cash kommen aus derselben Rechnung wie beim Stichtags-Snapshot;",
            "Kurshistorie und Bewertung schreibt der Abruf nicht fort."),
      tone = "neutral")
    return(do.call(shiny::tagList, panels))
  }
  currency <- .desktop_intraday_text_v1(value$base_currency, "EUR")
  complete <- identical(value$snapshot_status, "complete")
  requested <- .desktop_intraday_text_v1(value$quotes$requested_at_utc, "")
  age <- .desktop_intraday_age_v1(requested)
  worth <- .desktop_intraday_text_v1(value$totals$net_worth_decimal, "")
  panels[[length(panels) + 1L]] <- portelyra_status_panel(
    paste0("Momentaufnahme · ",
           if (nzchar(worth)) paste0("Gesamtvermögen ", desktop_snapshot_provisional_amount_v1(worth, value$totals$net_worth_provisional_decimal, currency), " · ") else "",
           desktop_snapshot_total_word_v1(value, modules), " ", pl_amount_v1(value$totals$market_value_decimal, currency, 2L, "—"),
           if (nzchar(age)) paste0(" · ", age) else "",
           if (complete) "" else " · unvollständig"),
    paste0("Kurse abgerufen ", .desktop_intraday_moment_v1(requested), " · ", desktop_intraday_summary_copy_v1(value), ".",
           if (complete) "" else " Mindestens eine gehaltene Position hat keinen Wert; die Summe ist deshalb zu niedrig."),
    tone = if (complete) "neutral" else "warning")
  # Ein Abruf von gestern ist kein Bild von heute - auch wenn die Rechnung den
  # heutigen Bestand nimmt.
  # Verglichen wird der Ortstag des Abrufs: Ein Abruf kurz nach Mitternacht
  # traegt in UTC noch das Datum von gestern.
  requested_at <- tryCatch(as.POSIXct(requested, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), error = function(error) NA)
  requested_day <- if (is.na(requested_at)) "" else format(requested_at, "%Y-%m-%d", tz = "")
  # Seit rc.313 veroeffentlicht: Verglichen wird auch mit heute, denn ein Bild von gestern bleibt stehen, bis der naechste Lauf es ersetzt.
  as_of <- max(.desktop_intraday_text_v1(value$as_of_date, ""), format(Sys.Date(), "%Y-%m-%d"))
  if (nzchar(requested_day) && nzchar(as_of) && requested_day < as_of) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      "Die Kurse sind nicht von heute",
      paste0("Der letzte Abruf stammt vom ", format(as.Date(requested_day), "%d.%m.%Y"),
             ". Bestand und Cash sind die vom Tag des Abrufs; für ein Bild von jetzt in der Data-App „Alles aktualisieren“ ausführen."),
      tone = "warning")
  }
  panels[[length(panels) + 1L]] <- shiny::p(class = "pl-field-hint", paste(
    "Die unrealisierte GuV ist brutto — vor Gebühren und Steuern — und ein lebender Zwischenstand, kein Abschluss.",
    "Positionen mit eigener Bewertung zählen in die Summe wie im Stichtags-Snapshot;",
    "Assets, die nur mit ihren Transaktionen geführt werden, stehen ohne Wert unter „Nicht im Marktwert enthalten“."))
  do.call(shiny::tagList, panels)
}
