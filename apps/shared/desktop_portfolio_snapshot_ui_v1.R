# Anzeige des veroeffentlichten Stichtags-Snapshots. Reine Darstellung: kein
# Abruf, keine Rechnung, keine Pfade und keine internen Kennungen im Browser.
#
# Die Frische steht je Ebene da, nicht als Sammelurteil. Ein Sammelurteil
# verdeckt, woran es liegt - und die Ebenen sagen es unterschiedlich: "noch
# nicht angefordert" ist etwas anderes als "Quelle hat keinen Wert" und wieder
# etwas anderes als "seither neu abgerufen" (#373, 26.09.2026).

.desktop_snapshot_text_v1 <- function(value, fallback = "—") {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value)))
    fallback else as.character(value)
}

# Exakt gerechnet, lesbar angezeigt: Betraege stehen ungerundet im Artefakt, und
# was nicht endlich dezimal darstellbar ist, steht als Bruch. Gerundet wird
# ausschliesslich hier.
.desktop_snapshot_amount_v1 <- function(value, digits = 2L) {
  text <- .desktop_snapshot_text_v1(value, "")
  if (!nzchar(text)) return("—")
  number <- if (grepl("^-?[0-9]+/[0-9]+$", text)) {
    parts <- as.numeric(strsplit(text, "/", fixed = TRUE)[[1L]])
    parts[[1L]] / parts[[2L]]
  } else suppressWarnings(as.numeric(text))
  if (is.na(number)) return(text)
  formatC(number, format = "f", digits = digits, big.mark = ".", decimal.mark = ",")
}

.desktop_snapshot_date_v1 <- function(value) {
  text <- .desktop_snapshot_text_v1(value, "")
  if (!nzchar(text)) return("—")
  parsed <- tryCatch(as.Date(text), error = function(error) NA)
  if (is.na(parsed)) return(text)
  format(parsed, "%d.%m.%Y")
}

desktop_snapshot_level_label_v1 <- function(code) {
  switch(.desktop_snapshot_text_v1(code, ""),
    activity = "Buchungen",
    fifo_basis = "FIFO-Basis",
    market_history = "Marktkurse",
    fx_history = "Wechselkurse",
    owner_excluded_assets = "Nach Eigentümerwahl nicht über den Markt bewertet",
    cash_coverage = "Cash",
    .desktop_snapshot_text_v1(code))
}

desktop_snapshot_status_label_v1 <- function(status) {
  switch(.desktop_snapshot_text_v1(status, ""),
    complete = "vollständig",
    source_gap = "Quelllücke",
    stale_market = "seither neu abgerufen",
    stale_fifo = "FIFO nicht fortgeschrieben",
    valuation_pending = "noch nicht bewertet",
    not_requested = "nicht angefordert",
    .desktop_snapshot_text_v1(status))
}

# Umfang je Portfolio (#542): `modules` sind die Bausteine eines veroeffentlichten Umfangs (benannte Liste, TRUE/FALSE) oder NULL.
# Ohne Marktdaten heisst ein Wert nicht „Marktwert“, sondern so, wie er entsteht: aus Transaktionen (eigene Kurse bzw. Trade-Kurse).
# Ohne Cash heisst die Summe ausdruecklich „ohne Cash“, und fehlendes Cash ist „nicht geführt, wie gewählt (Umfang)“ statt „nicht erklärt“ - aber
# nur, wenn der Stand kein Cash traegt: Abschalten loescht nichts, und gezaehltes Cash bleibt benannt. Ohne Umfang gilt alles wie bisher.
.desktop_snapshot_off_v1 <- function(modules, module) is.list(modules) && isFALSE(modules[[module]])
desktop_snapshot_value_word_v1 <- function(modules = NULL) if (.desktop_snapshot_off_v1(modules, "market_data")) "Wert (aus Transaktionen)" else "Marktwert"
.desktop_snapshot_has_cash_v1 <- function(value) is.list(value) && is.list(value$cash) && identical(value$cash$status, "available") && length(value$cash$accounts) > 0L
desktop_snapshot_total_word_v1 <- function(value, modules = NULL) {
  paste0(desktop_snapshot_value_word_v1(modules), if (.desktop_snapshot_off_v1(modules, "cash") && !.desktop_snapshot_has_cash_v1(value)) " ohne Cash" else "")
}
DESKTOP_SNAPSHOT_NOT_KEPT_V1 <- "nicht geführt, wie gewählt (Umfang)"

desktop_snapshot_state_ui_v1 <- function(value, notice = NULL, modules = NULL) {
  panels <- list()
  if (is.list(notice)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      .desktop_snapshot_text_v1(notice$title, "Hinweis"),
      .desktop_snapshot_text_v1(notice$copy, ""),
      tone = .desktop_snapshot_text_v1(notice$tone, "neutral"))
  }
  if (!is.list(value)) {
    panels[[length(panels) + 1L]] <- portelyra_status_panel(
      "Noch kein veröffentlichter Snapshot",
      paste("Ein Snapshot hält den Stand eines Stichtags unveränderlich fest.",
            "Er entsteht aus dem Bewertungsstand und startet weder Abruf noch Berechnung."),
      tone = "neutral")
    return(do.call(shiny::tagList, panels))
  }
  complete <- identical(value$snapshot_status, "complete")
  panels[[length(panels) + 1L]] <- portelyra_status_panel(
    paste0(desktop_snapshot_total_word_v1(value, modules), " ", pl_amount_v1(value$totals$market_value_decimal, .desktop_snapshot_text_v1(value$base_currency, "EUR"), 2L, "—"),
           " · unrealisierte GuV ", pl_amount_v1(value$totals$unrealised_decimal, .desktop_snapshot_text_v1(value$base_currency, "EUR"), 2L, "—"),
           if (complete) "" else " · unvollständig"),
    paste0("Stichtag ", .desktop_snapshot_date_v1(value$as_of_date), " · ",
           .desktop_snapshot_text_v1(value$portfolio_label), " · veröffentlicht ",
           pl_moment_v1(value$completed_at_utc, "—"), ". ",
           if (complete)
             "Jede tragende Ebene ist vollständig, und jede gehaltene Position ist bewertet oder nach Eigentümerwahl ohne Wert geführt."
           else
             "Mindestens eine Ebene ist offen; die Summe umfasst deshalb nicht alles."),
    tone = if (complete) "neutral" else "warning")
  panels[[length(panels) + 1L]] <- shiny::p(class = "pl-field-hint", paste(
    "Die unrealisierte GuV ist brutto — vor Gebühren und Steuern.",
    "Positionen mit eigener Bewertung zählen in die Summe: zuerst die eigene Kursangabe, sonst der letzte bestätigte Trade-Stückpreis;",
    "die Spalten Kursherkunft und Kursstand sagen, woher der Preis stammt und von wann.",
    "Cash steht darunter je Konto mit dem Tag seines Saldos; das Gesamtvermögen ist Marktwert plus Cash.",
    "Führt ein Konto nur Bewegungen, ist sein Saldo deren Summe: abgeleitet, nicht durch einen Auszug bestätigt, und so benannt.",
    "Dahinter steht die Annahme, dass das Konto vor dem genannten Tag leer war; lag dort schon Geld, ist der Saldo um diesen Betrag zu niedrig.",
    "Assets, die nur mit ihren Transaktionen geführt werden, stehen ohne Wert unter „Nicht im Marktwert enthalten“."))
  do.call(shiny::tagList, panels)
}

# Die drei Zahlen, nach denen zuerst gefragt wird: was die Positionen wert sind,
# wie viel Cash belegt ist, und beides zusammen. Jede Zeile sagt, worauf sie
# beruht - ein Cash-Saldo von vor dem Stichtag steht mit seinem Datum da, und
# Konten ohne Saldo werden gezaehlt statt verschwiegen (Darstellung nach
# Festlegung 11.10.2026).
desktop_snapshot_cash_status_label_v1 <- function(code, derived_from_date = NULL) {
  # Der abgeleitete Saldo nennt, ab wann summiert ist: An diesem Tag haengt die
  # Annahme, dass das Konto davor leer war.
  since <- .desktop_snapshot_text_v1(derived_from_date, "")
  since <- if (nzchar(since)) paste0(" seit ", .desktop_snapshot_date_v1(since)) else ""
  switch(.desktop_snapshot_text_v1(code, ""),
    reconciled_at_as_of = "am Stichtag belegt",
    reconciled_before_as_of = "abgestimmt, Stand älter als der Stichtag",
    derived_at_as_of = paste0("abgeleitet aus Bewegungen", since, ", nicht durch Auszug bestätigt"),
    derived_before_as_of = paste0("abgeleitet aus Bewegungen", since, ", nicht durch Auszug bestätigt, Stand älter als der Stichtag"),
    movements_only = "nur Bewegungen, kein Saldo",
    movements_sum_negative = "nur Bewegungen, Summe zeitweise unter null: kein Saldo ableitbar",
    not_covered_yet = "am Stichtag noch nicht geführt",
    periods_ambiguous = "mehrere Zeiträume, Saldo nicht eindeutig",
    currency_without_rate = "Fremdwährung ohne Wechselkurs am Stichtag",
    .desktop_snapshot_text_v1(code, ""))
}

# Vorlaeufiger Cash-Stand (#539, Festlegung 04.11.2026): der amtliche Betrag bleibt Hauptwert, der vorlaeufige steht in
# Klammern dahinter - nur, wo er abweicht. Gebucht ist er nicht; der naechste Auszug ersetzt ihn.
desktop_snapshot_provisional_amount_v1 <- function(official, provisional, currency) {
  shown <- pl_amount_v1(official, currency, 2L, "\u2014")
  later <- .desktop_snapshot_text_v1(provisional, "")
  if (!nzchar(later) || identical(later, .desktop_snapshot_text_v1(official, ""))) return(shown)
  paste0(shown, " (vorl. ", pl_amount_v1(later, currency, 2L, "\u2014"), ")")
}

.desktop_snapshot_count_v1 <- function(value) {
  number <- suppressWarnings(as.integer(value)); if (length(number) != 1L || is.na(number)) 0L else number
}

# Was im vorlaeufigen Stand steckt und was nicht - fuer die Grundlage der Summen.
desktop_snapshot_provisional_note_v1 <- function(cash) {
  if (!is.list(cash)) return(character())
  settled <- .desktop_snapshot_count_v1(cash$provisional_settlement_count); moved <- .desktop_snapshot_count_v1(cash$provisional_movement_count)
  stale <- .desktop_snapshot_count_v1(cash$provisional_unestimated_account_count)
  parts <- character()
  if (identical(cash$provisional_status, "available")) {
    what <- c(if (settled) paste0(settled, if (settled == 1L) " Abrechnung" else " Abrechnungen", " ohne Auszugszeile"),
              if (moved) paste0(moved, if (moved == 1L) " Buchung" else " Buchungen", " nach dem letzten Auszug"))
    parts <- c(parts, paste0("vorläufig: ", paste(what, collapse = " und "), " eingerechnet – nicht gebucht, der nächste Auszug ersetzt es;",
                             " Umbuchungen und einbehaltene Steuer erst mit dem Auszug"))
  } else if (identical(cash$provisional_status, "unavailable")) {
    parts <- c(parts, "vorläufiger Stand nicht verfügbar")
  }
  if (stale) parts <- c(parts, paste0(stale, if (stale == 1L) " Konto" else " Konten", " mit Auszug älter als zwei Monate: offene Abrechnungen nicht geschätzt"))
  parts
}

desktop_snapshot_summary_frame_v1 <- function(value, modules = NULL) {
  if (!is.list(value) || !is.list(value$totals)) return(data.frame())
  currency <- .desktop_snapshot_text_v1(value$base_currency, "EUR")
  positions <- if (is.list(value$counts) && !is.null(value$counts$valued_position_count)) value$counts$valued_position_count else length(value$positions)
  rows <- list(list(
    paste0(desktop_snapshot_total_word_v1(value, modules), " (", positions, " Positionen)"), pl_amount_v1(value$totals$market_value_decimal, currency, 2L, "\u2014"),
    if (identical(value$snapshot_status, "complete")) "jede gehaltene Position bewertet oder nach Eigentümerwahl ohne Wert"
    else "unvollständig \u2014 siehe „Nicht im Marktwert enthalten\u201c und Frische je Ebene"))
  cash <- value$cash
  if (!.desktop_snapshot_has_cash_v1(value) && .desktop_snapshot_off_v1(modules, "cash")) {
    rows[[2L]] <- list("Cash", "\u2014", DESKTOP_SNAPSHOT_NOT_KEPT_V1)
  } else if (!is.list(cash)) {
    rows[[2L]] <- list("Cash", "\u2014", "in diesem veröffentlichten Stand nicht ausgewiesen; neu planen und veröffentlichen")
  } else if (!identical(cash$status, "available") || !length(cash$accounts)) {
    rows[[2L]] <- list("Cash", "\u2014", "keine Cash-Zeiträume erklärt")
  } else {
    counted <- as.integer(cash$counted_account_count); uncounted <- as.integer(cash$uncounted_account_count)
    # Fassung 4 kennt keine abgeleiteten Salden; ihr fehlt der Zaehler.
    derived <- if (is.null(cash$derived_account_count)) 0L else as.integer(cash$derived_account_count)
    # "Belegt" ist ein Kontostand nur durch einen Auszug. Sind abgeleitete
    # darunter, heisst die Spanne schlicht "letzter Kontostand".
    stand <- if (derived > 0L) "letzter Kontostand" else "letzter belegter Kontostand"
    # Die Spanne nennt, von wann der letzte belegte Kontostand je Konto stammt -
    # nicht, seit wann es Cash-Daten gibt. "Salden vom ... bis ..." las sich
    # wie der Beginn der Historie.
    span <- if (is.null(cash$oldest_balance_date)) "" else if (!isTRUE(cash$dated_before_as_of))
        (if (derived > 0L) "Kontostand vom Stichtag" else "Kontostand am Stichtag belegt")
      else if (identical(cash$oldest_balance_date, cash$newest_balance_date))
        paste0(stand, " vom ", .desktop_snapshot_date_v1(cash$newest_balance_date))
      else paste0(stand, " je Konto zwischen ", .desktop_snapshot_date_v1(cash$oldest_balance_date),
                  " und ", .desktop_snapshot_date_v1(cash$newest_balance_date))
    # Der abgeleitete Anteil steht mit seinem Betrag da: Wer nur dem Auszug
    # traut, zieht ihn ab (Festlegung 11.10.2026).
    derived_note <- if (derived > 0L) paste0("davon ", derived, if (derived == 1L) " Konto" else " Konten",
      " aus Bewegungen abgeleitet (", pl_amount_v1(value$totals$cash_derived_balance_decimal, currency, 2L, "\u2014"),
      "), nicht durch einen Auszug bestätigt")
    provisional <- desktop_snapshot_provisional_note_v1(cash)
    note <- c(span, if (isTRUE(cash$dated_before_as_of)) "älter als der Stichtag", derived_note,
      if (uncounted > 0L) paste0(uncounted, if (uncounted == 1L) " Konto" else " Konten", " ohne Saldo nicht enthalten"), provisional)
    rows[[2L]] <- list(paste0("Cash (", counted, if (counted == 1L) " Konto" else " Konten", " mit Saldo)"),
      desktop_snapshot_provisional_amount_v1(value$totals$cash_balance_decimal, value$totals$cash_provisional_balance_decimal, currency),
      paste(note[nzchar(note)], collapse = " · "))
    worth_note <- c(paste(desktop_snapshot_value_word_v1(modules), "plus Cash"), if (isTRUE(cash$dated_before_as_of)) "Cash-Stand älter als der Stichtag",
      if (derived > 0L) "enthält abgeleitetes Cash", if (uncounted > 0L) "ohne die Konten ohne Saldo", if (!identical(value$snapshot_status, "complete")) "Marktwert unvollständig",
      if (!is.null(value$totals$net_worth_provisional_decimal)) "in Klammern mit dem vorläufigen Cash-Stand")
    rows[[3L]] <- list("Gesamtvermögen", desktop_snapshot_provisional_amount_v1(value$totals$net_worth_decimal, value$totals$net_worth_provisional_decimal, currency),
      paste(worth_note, collapse = " · "))
  }
  # Der Betrag traegt seine Einheit selbst (#529 Punkt 8); bis rc.348 stand sie nur im Spaltenkopf.
  data.frame(
    Posten = vapply(rows, `[[`, character(1L), 1L), Betrag = vapply(rows, `[[`, character(1L), 2L),
    Grundlage = vapply(rows, `[[`, character(1L), 3L), stringsAsFactors = FALSE, check.names = FALSE)
}

# Je Konto: was vorlaeufig eingerechnet ist, oder dass bei altem Auszug nicht geschaetzt wird.
desktop_snapshot_provisional_row_note_v1 <- function(row) {
  settled <- .desktop_snapshot_count_v1(row$provisional_settlement_count); moved <- .desktop_snapshot_count_v1(row$provisional_movement_count)
  stale <- .desktop_snapshot_count_v1(row$provisional_unestimated_count)
  since <- .desktop_snapshot_date_v1(row$balance_date)
  as.character(c(if (!is.null(row$provisional_balance_decimal) && (settled || moved))
      paste0("vorläufig: ", paste(c(if (settled) paste0(settled, if (settled == 1L) " Abrechnung" else " Abrechnungen"),
        if (moved) paste0(moved, if (moved == 1L) " Buchung" else " Buchungen")), collapse = " und "), " seit ", since, " eingerechnet"),
    if (stale) paste0(stale, if (stale == 1L) " Abrechnung" else " Abrechnungen", " seit ", since,
      " ohne Auszugszeile – Auszug älter als zwei Monate, nicht geschätzt")))
}

desktop_snapshot_cash_frame_v1 <- function(value) {
  if (!is.list(value) || !is.list(value$cash) || !length(value$cash$accounts)) return(data.frame())
  rows <- value$cash$accounts
  # Erst die Konten in der Summe - die durch einen Auszug belegten vor den
  # abgeleiteten -, juengster Saldo zuerst; dann die uebrigen.
  order_key <- order(!vapply(rows, function(row) isTRUE(row$in_total), logical(1L)),
    vapply(rows, function(row) .desktop_snapshot_text_v1(row$balance_status, "") %in% c("derived_at_as_of", "derived_before_as_of"), logical(1L)),
    -xtfrm(vapply(rows, function(row) .desktop_snapshot_text_v1(row$balance_date, ""), character(1L))),
    vapply(rows, function(row) .desktop_snapshot_text_v1(row$account_label, ""), character(1L)))
  rows <- rows[order_key]
  data.frame(
    Konto = vapply(rows, function(row) .desktop_snapshot_text_v1(row$account_label), character(1L)),
    Saldo = vapply(rows, function(row) desktop_snapshot_provisional_amount_v1(row$balance_decimal, row$provisional_balance_decimal,
      .desktop_snapshot_text_v1(row$currency, "")), character(1L)),
    `Saldo vom` = vapply(rows, function(row) .desktop_snapshot_date_v1(row$balance_date), character(1L)),
    Status = vapply(rows, function(row) paste(c(desktop_snapshot_cash_status_label_v1(row$balance_status, row$derived_from_date),
      desktop_snapshot_provisional_row_note_v1(row)), collapse = " · "), character(1L)),
    `In der Summe` = vapply(rows, function(row) if (isTRUE(row$in_total)) "ja" else "nein", character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

# Die veroeffentlichten Staende zur Auswahl. Im Browser steht ein Kurzzeichen je
# Stand, nicht dessen Kennung; welches Kurzzeichen welcher Stand ist, weiss nur
# der Server. Das Kurzzeichen haengt am Stand und nicht an seiner Position in der
# Liste - sonst zeigte dieselbe Auswahl nach dem naechsten Veroeffentlichen einen
# anderen Stand.
desktop_snapshot_library_ref_v1 <- function(snapshot_id) {
  paste0("stand_", substr(digest::digest(snapshot_id, algo = "sha256", serialize = FALSE), 1L, 16L))
}

desktop_snapshot_library_refs_v1 <- function(library) {
  rows <- if (is.list(library)) library$snapshots else NULL
  if (!length(rows)) return(character())
  ids <- vapply(rows, function(row) .desktop_snapshot_text_v1(row$snapshot_id, ""), character(1L))
  stats::setNames(ids, vapply(ids, desktop_snapshot_library_ref_v1, character(1L)))
}

.desktop_snapshot_local_moment_v1 <- function(value) {
  text <- .desktop_snapshot_text_v1(value, "")
  parsed <- if (nzchar(text)) tryCatch(as.POSIXct(text, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), error = function(error) NA) else NA
  if (is.na(parsed)) return(text)
  format(parsed, "%d.%m.%Y %H:%M", tz = "")
}

desktop_snapshot_library_choices_v1 <- function(library) {
  rows <- if (is.list(library)) library$snapshots else NULL
  first <- c("Zuletzt veröffentlicht" = "")
  if (!length(rows)) return(first)
  dates <- vapply(rows, function(row) .desktop_snapshot_text_v1(row$as_of_date, ""), character(1L))
  labels <- vapply(seq_along(rows), function(index) {
    row <- rows[[index]]
    paste0(.desktop_snapshot_date_v1(row$as_of_date), " · ",
      if (identical(row$snapshot_status, "complete")) "vollständig" else "unvollständig",
      # Mehrere Staende zum selben Stichtag: Die Liste fuehrt den juengsten
      # zuerst; die aelteren sagen, dass sie es sind.
      if (index > 1L && identical(dates[[index - 1L]], dates[[index]])) " · ältere Fassung" else "",
      if (!isTRUE(row$cash_included)) " · ohne Cash" else "",
      " · veröffentlicht ", .desktop_snapshot_local_moment_v1(row$completed_at_utc),
      if (isTRUE(row$latest)) " · zuletzt veröffentlicht" else "")
  }, character(1L))
  c(first, stats::setNames(names(desktop_snapshot_library_refs_v1(library)), labels))
}

desktop_snapshot_freshness_frame_v1 <- function(value) {
  if (!is.list(value) || !is.list(value$freshness) || !length(value$freshness$levels))
    return(data.frame())
  levels <- value$freshness$levels
  data.frame(
    Ebene = vapply(levels, function(row) desktop_snapshot_level_label_v1(row$level_code), character(1L)),
    Stand = vapply(levels, function(row) desktop_snapshot_status_label_v1(row$status), character(1L)),
    Tragend = vapply(levels, function(row) if (isTRUE(row$blocking)) "ja" else "nachrichtlich", character(1L)),
    Grund = vapply(levels, function(row) desktop_snapshot_reason_text_v1(row$reason_code, row$detail), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}

# Der Grund einer Ebene in Worten (rc.314, #478; bis dahin stand das Kuerzel da). Unbekannte Kuerzel bleiben stehen, damit nichts
# verschwindet; die Zahl Betroffener haengt an, wo der Rechenkern sie nennt.
DESKTOP_SNAPSHOT_REASON_LABELS_V1 <- c(
  valuation_state_absent = "noch kein Bewertungsstand", nothing_to_value = "nichts am Markt zu bewerten",
  listing_requests_changed = "Notierungen seither neu abgerufen", day_unavailable = "Quelle lieferte für den Tag keinen Kurs",
  window_or_day_missing = "Tag noch nicht bewertet", all_valued = "alle bewertet", held_without_scope = "gehaltene Assets ohne Kurszuordnung",
  active_generation = "Buchungsbestand gelesen", no_active_generation = "noch keine Buchung",
  fifo_v2_fresh = "FIFO-Stand aktuell", fifo_v2_stale = "Buchungen seit dem letzten FIFO-Lauf geändert",
  fifo_v2_stale_pending = "FIFO-Lauf steht aus", fifo_v2_stale_failed = "letzter FIFO-Lauf fehlgeschlagen",
  valuation_method_owner_choice = "eigene Bewertung oder nur Transaktionen (Eigentümerwahl)", no_owner_choice_assets = "keine",
  declared_periods = "Auszüge eingelesen", cash_not_declared = "keine Auszüge eingelesen",
  as_of_outside_valued_window = "Stichtag außerhalb des bewerteten Zeitraums", no_valued_day = "kein bewerteter Tag",
  valued_substituted = "bewertet, mit Ersatzkurs", rate_unavailable = "kein Wechselkurs", rate_effective = "Wechselkurs wirksam",
  rate_effective_in_valuation = "Wechselkurs in der Bewertung wirksam", no_effective_day = "kein wirksamer Wechselkurstag")
desktop_snapshot_reason_text_v1 <- function(code, detail = NULL) {
  text <- .desktop_snapshot_text_v1(code, "")
  if (!nzchar(text)) return("")
  label <- if (text %in% names(DESKTOP_SNAPSHOT_REASON_LABELS_V1)) unname(DESKTOP_SNAPSHOT_REASON_LABELS_V1[[text]])
           else if (startsWith(text, "valued_")) "bewertet"
           else if (startsWith(text, "day_")) "Quelllücke am Tag"
           else if (startsWith(text, "fifo_v2_")) "FIFO-Stand nicht lesbar"
           else text
  count <- function(field) { value <- if (is.list(detail)) detail[[field]] else NULL
    if (is.numeric(value) && length(value) == 1L && !is.na(value) && value > 0) as.integer(value) else NA_integer_ }
  affected <- count("affected_count"); missing <- count("held_without_scope_count"); owner <- count("asset_count")
  if (!is.na(affected)) paste0(label, " · ", affected, " betroffen")
  else if (!is.na(missing)) paste0(label, " · ", missing, if (missing == 1L) " Asset" else " Assets")
  else if (!is.na(owner) && identical(text, "valuation_method_owner_choice")) paste0(label, " · ", owner, if (owner == 1L) " Asset" else " Assets")
  else label
}

# Woher der Preis einer Position stammt. Der Code allein ("observed",
# "trade_price_reference") sagt dem Eigentuemer nichts; und seit eigene
# Bewertungen in die Summe zaehlen, muss an der Zeile stehen, dass ihr Preis
# keine Marktnotiz ist (11.10.2026).
desktop_snapshot_price_basis_label_v1 <- function(code, provider_id = NULL) {
  # Ein Anbieter ohne Momentkurs (rc.394, etwa EODHD) liefert im fluiden Bild immer den letzten Tagesschluss - kein misslungener Abruf.
  if (identical(.desktop_snapshot_text_v1(code, ""), "last_close") && exists("PL_PRICE_PROVIDERS_WITHOUT_QUOTE_V1") &&
      isTRUE(.desktop_snapshot_text_v1(provider_id, "") %in% PL_PRICE_PROVIDERS_WITHOUT_QUOTE_V1))
    return("letzter Tagesschluss, Anbieter ohne Momentkurs")
  switch(.desktop_snapshot_text_v1(code, ""),
    observed = "Marktkurs",
    imputed_closed_day = "Marktkurs, letzter Handelstag",
    imputed_non_trading_day = "Marktkurs, letzter Handelstag",
    imputed_source_gap = "Marktkurs, fortgeschrieben",
    imputed_after_source_gap = "Marktkurs, fortgeschrieben",
    owner_recorded_manual_price = "eigene Kursangabe",
    trade_price_reference = "eigene Bewertung · Trade-Stückpreis",
    # Nur im fluiden Bild: der zuletzt abgerufene Kurs - oder, wenn der Abruf
    # misslang, der letzte Tagesschluss aus dem Bewertungsstand.
    intraday = "abgerufener Kurs",
    last_close = "letzter Tagesschluss, Abruf misslungen",
    .desktop_snapshot_text_v1(code, ""))
}

# Der Kursstand einer Zeile. Das fluide Bild kennt den Zeitpunkt, zu dem die
# Quelle den Kurs beobachtet hat; ein Tag allein liesse einen Kurs vom
# Vormittag wie einen von jetzt aussehen.
.desktop_snapshot_price_moment_v1 <- function(row) {
  observed <- .desktop_snapshot_text_v1(row$price_observed_at_utc, "")
  parsed <- if (nzchar(observed)) tryCatch(as.POSIXct(observed, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
                                           error = function(error) NA) else NA
  if (is.na(parsed)) return(.desktop_snapshot_date_v1(row$price_source_date))
  format(parsed, "%d.%m.%Y %H:%M", tz = "")
}

# Kleinstbestaende (#534, Festlegung 04.11.2026): Cash-Salden ueber 0 und unter der Grenze (Euro) auf geschlossenen und ruhenden
# Konten fallen aus der Anzeige, gezaehlt und summiert - "nur geschlossene / ruhende Konten". Ein Rest auf einem aktiven Konto liegt
# noch bei der Bank und bleibt stehen, ebenso jede Position (im Snapshot je Asset, keinem Konto zuzuordnen). Den Zustand traegt die
# Cash-Zeile seit rc.360 (`account_state`); fehlt er (aeltere Snapshots), bleibt die Zeile stehen. Gerechnet wird nichts neu.
DESKTOP_SNAPSHOT_SMALL_STATES_V1 <- c("closed", "resting")
desktop_snapshot_small_holdings_v1 <- function(value, threshold) {
  limit <- suppressWarnings(as.numeric(threshold))
  none <- list(model = value, count = 0L, total = 0, threshold = if (length(limit) != 1L || is.na(limit)) 0 else limit)
  if (!is.list(value) || length(limit) != 1L || is.na(limit) || limit <= 0) return(none)
  small <- function(text) { number <- suppressWarnings(as.numeric(text)); length(number) == 1L && !is.na(number) && number != 0 && abs(number) < limit }
  accounts <- if (is.list(value$cash) && is.list(value$cash$accounts)) value$cash$accounts else list()
  # Fremdwaehrungskonten zaehlen mit ihrem Euro-Gegenwert; ohne ihn bleiben sie stehen.
  euro <- function(row) if (identical(row$currency, "EUR")) row$balance_decimal else row$balance_target_decimal
  hidden <- vapply(accounts, function(row) isTRUE(row$account_state %in% DESKTOP_SNAPSHOT_SMALL_STATES_V1) && small(euro(row)), logical(1L))
  model <- value
  if (is.list(model$cash)) model$cash$accounts <- accounts[!hidden]
  list(model = model, count = sum(hidden), total = sum(vapply(accounts[hidden], function(row) as.numeric(euro(row)), numeric(1L))), threshold = limit)
}
desktop_snapshot_small_holdings_note_v1 <- function(small, shown) {
  if (!is.list(small) || !isTRUE(small$count > 0L)) return(NULL)
  limit <- pl_amount_v1(format(small$threshold, scientific = FALSE), "EUR", if (small$threshold == round(small$threshold)) 0L else 2L, "")
  sprintf(if (isTRUE(shown)) "%d Kleinstbestände unter %s auf geschlossenen oder ruhenden Konten eingeblendet (zusammen %s)." else
            "%d Kleinstbestände unter %s auf geschlossenen oder ruhenden Konten ausgeblendet (zusammen %s); „Kleinstbestände zeigen“ blendet sie ein. Summen enthalten sie.",
          as.integer(small$count), limit, pl_amount_v1(format(small$total, scientific = FALSE, nsmall = 2L), "EUR", 2L, "0,00 €"))
}
desktop_snapshot_positions_frame_v1 <- function(value, modules = NULL) {
  if (!is.list(value) || !length(value$positions)) return(data.frame())
  rows <- value$positions
  currency <- .desktop_snapshot_text_v1(value$base_currency, "EUR")
  amount <- function(field) vapply(rows, function(row) pl_amount_v1(row[[field]], currency, 2L, "\u2014"), character(1L))
  # Stueck ohne Nullen am Ende, Betraege mit Einheit (#529 Punkt 8), GuV beim Namen (#531 Punkt 5).
  frame <- data.frame(
    Asset = vapply(rows, function(row) .desktop_snapshot_text_v1(row$asset_name,
      .desktop_snapshot_text_v1(row$provider_symbol)), character(1L)),
    Symbol = vapply(rows, function(row) .desktop_snapshot_text_v1(row$provider_symbol), character(1L)),
    # Kursanbieter je Position (rc.384, #495); aeltere Snapshots ohne Angabe zeigen einen Strich.
    # Terminkontrakte als "Future-Naeherung" (rc.388); die Fussnote liefert desktop_snapshot_series_note_v1.
    Anbieter = vapply(rows, function(row) pl_price_provider_series_label_v1(row$provider_id, row$provider_symbol, "\u2014"), character(1L)),
    Bestand = vapply(rows, function(row) pl_quantity_v1(row$quantity_decimal, "\u2014"), character(1L)),
    `Wert je Stück` = vapply(rows, function(row) pl_price_v1(row$unit_value_decimal, currency, "\u2014", 4L), character(1L)),
    `Marktwert` = amount("market_value_decimal"),
    `Anschaffung` = amount("cost_basis_decimal"),
    `Unrealisierte GuV` = amount("unrealised_decimal"),
    Kursherkunft = vapply(rows, function(row) desktop_snapshot_price_basis_label_v1(row$price_basis, row$provider_id), character(1L)),
    Kursstand = vapply(rows, .desktop_snapshot_price_moment_v1, character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
  # Ohne Marktdaten heisst die Spalte, wie der Wert entsteht (#542); die Kursherkunft je Zeile steht daneben.
  names(frame)[names(frame) == "Marktwert"] <- desktop_snapshot_value_word_v1(modules)
  frame
}

desktop_snapshot_series_note_v1 <- function(value) {
  if (!is.list(value) || !length(value$positions)) return(NULL)
  pl_price_series_future_note_v1(vapply(value$positions, function(row) pl_price_series_is_future_v1(row$provider_id, row$provider_symbol), logical(1L)))
}

desktop_snapshot_excluded_frame_v1 <- function(value) {
  if (!is.list(value) || !length(value$excluded_positions)) return(data.frame())
  rows <- value$excluded_positions
  data.frame(
    Asset = vapply(rows, function(row) .desktop_snapshot_text_v1(row$asset_name,
      substr(.desktop_snapshot_text_v1(row$asset_id), 1L, 16L)), character(1L)),
    Art = vapply(rows, function(row) if (isTRUE(row$owner_excluded)) "Eigentümerwahl" else "Lücke", character(1L)),
    Grund = vapply(rows, function(row) .desktop_snapshot_text_v1(row$reason, ""), character(1L)),
    Bestand = vapply(rows, function(row) pl_quantity_v1(row$quantity_decimal, "\u2014"), character(1L)),
    `Hergeleiteter Wert` = vapply(rows, function(row) pl_amount_v1(row$derived_value_decimal, .desktop_snapshot_text_v1(value$base_currency, "EUR"), 2L, "\u2014"), character(1L)),
    `Anschaffung` = vapply(rows, function(row) pl_amount_v1(row$cost_basis_decimal, .desktop_snapshot_text_v1(value$base_currency, "EUR"), 2L, "\u2014"), character(1L)),
    stringsAsFactors = FALSE, check.names = FALSE)
}
