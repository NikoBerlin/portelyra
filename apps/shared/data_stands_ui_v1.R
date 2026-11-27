# Staende je Datenart (#463): bis wann Buchungen, Rewards, Cash, Kurse, Tageshistorie und Snapshot reichen. Gemeinsam fuer die
# Karte „Alles aktualisieren“ der Data-App und die Datenbasis-App (rc.314, #478); die Werte liefert data_stands_v1.

.data_stands_day_v1 <- function(value) {
  if (is.null(value) || length(value) != 1L || is.na(value) || !nzchar(as.character(value))) return("–")
  parsed <- tryCatch(as.Date(as.character(value)), error = function(error) NA)
  if (is.na(parsed)) "–" else format(parsed, "%d.%m.%Y")
}

# Je Datenart, bis wann sie reicht. Ein Bild mit Stichtag heute wirkt sonst vollstaendiger, als es ist: Cash kommt hoechstens
# monatlich mit dem Auszug, Rewards mit dem Import (Festlegung 17.10.2026).
#
# `modules`: die Bausteine eines veroeffentlichten Umfangs (#542) oder NULL. Was ein abgeschalteter Baustein liefern wuerde, fehlt
# nicht, sondern ist „nicht geführt, wie gewählt (Umfang)“; liegt aus frueherer Zeit noch etwas vor, bleibt es stehen und sagt, dass es nicht
# fortgefuehrt wird. Ohne Umfang ist die Tabelle dieselbe wie bisher.
DATA_STANDS_NOT_KEPT_V1 <- "nicht geführt, wie gewählt (Umfang)"
data_stands_frame_v1 <- function(stands, modules = NULL) {
  if (!is.list(stands)) return(data.frame())
  day <- .data_stands_day_v1
  absent <- function(part) !is.list(part) || !identical(part$status, "available") && !identical(part$status, "ready")
  count <- function(value) if (is.null(value)) 0L else as.integer(value)
  base_row <- function(kind, through, hint) data.frame(Datenart = kind, `Stand bis` = through, Hinweis = hint,
                                                       stringsAsFactors = FALSE, check.names = FALSE)
  off_kinds <- c(Cash = "cash", Kurse = "market_data", Tageshistorie = "history_analysis")
  tx <- stands$transactions; rw <- stands$rewards; cash <- stands$cash; px <- stands$prices
  hist <- stands$history; snap <- stands$snapshot
  parts <- list(Cash = cash, Kurse = px, Tageshistorie = hist)
  row <- function(kind, through, hint) {
    module <- if (kind %in% names(off_kinds)) off_kinds[[kind]] else NA_character_
    if (is.na(module) || !is.list(modules) || !isFALSE(modules[[module]])) return(base_row(kind, through, hint))
    if (absent(parts[[kind]])) base_row(kind, "–", DATA_STANDS_NOT_KEPT_V1) else base_row(kind, through, paste0(hint, " · nicht im Umfang, wird nicht fortgeführt"))
  }
  rbind(
    row("Buchungen", if (absent(tx)) "–" else day(tx$through),
        if (absent(tx)) "noch keine Buchung" else paste0("jüngste Buchung · ", count(tx$event_count), " Buchungen auf ", count(tx$account_count), " Konten")),
    row("Rewards", if (absent(rw)) "–" else day(rw$through),
        if (absent(rw)) "noch kein Reward gebucht" else paste0("jüngster Reward · kommt mit dem Import, nicht mit diesem Lauf")),
    row("Cash", if (absent(cash)) "–" else day(cash$through),
        if (absent(cash)) "keine Auszüge eingelesen" else paste0("Auszüge je Konto, ", count(cash$account_count), " Konten",
          if (!identical(cash$earliest, cash$through)) paste0(" · ältestes bis ", day(cash$earliest)) else "",
          " · danach gilt der letzte belegte Saldo")),
    row("Kurse", if (absent(px)) "–" else day(px$through),
        if (absent(px)) "noch nichts bewertet" else paste0(count(px$asset_count), " gehaltene Assets am Markt bewertet",
          if (count(px$behind_count) > 0L) paste0(" · ", count(px$behind_count), " davon nur bis ", day(px$earliest)) else "",
          if (count(px$without_valuation_count) > 0L) paste0(" · ", count(px$without_valuation_count), " ohne Bewertung") else "")),
    row("Tageshistorie", if (absent(hist)) "–" else day(hist$through),
        if (absent(hist)) "noch nicht aufgebaut" else paste0("ab ", day(hist$first),
          if (identical(hist$complete_through, hist$through)) " · durchgehend vollständig bewertet bis zum letzten Tag"
          else paste0(" · vollständig bewertet bis ", day(hist$complete_through)))),
    row("Snapshot", if (absent(snap)) "–" else day(snap$as_of_date),
        if (absent(snap)) "noch keiner veröffentlicht" else paste0("jüngster veröffentlichter Stichtag · ",
          if (identical(snap$snapshot_status, "complete")) "vollständig" else "unvollständig")))
}
