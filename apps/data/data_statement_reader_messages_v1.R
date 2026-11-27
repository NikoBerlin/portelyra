# Meldungen der Leser-Plugins (#486), gemeinsam fuer Cash-, Reward- und Steuerbeleg-Import (rc.377).
#
# Festlegung (08.11.2026): den Grund immer so genau wie moeglich zeigen - Transparenz ist ein Qualitaetsmerkmal. Deshalb ein Satz je
# Grund: fehlende Abschottung (mit der gefundenen Kernel-Version), ungueltiges Ergebnis, Absturz, Zeitgrenze, nicht installiert. Ein
# Code steht frei im Text oder ist der ganze Text (etwa "desktop_per_asset_legacy_review_failed:statement_reader_timeout").
# NULL heisst: kein Code eines Lesers; dann gelten die Meldungen des jeweiligen Imports.
data_statement_reader_message_v1 <- function(message, reader_label, outcome = "Es wurde nichts gebucht.",
                                             kernel = tryCatch(as.character(Sys.info()[["release"]]), error = function(error) "unbekannt")) {
  message <- if (is.character(message) && length(message) == 1L && !is.na(message)) message else ""
  code <- regmatches(message, regexpr("statement_reader_[a-z_]+", message))
  if (!length(code)) return(NULL)
  label <- if (is.character(reader_label) && length(reader_label) == 1L && !is.na(reader_label) && nzchar(reader_label)) reader_label else "unbekannt"
  text <- switch(code,
    statement_reader_isolation_unavailable = c("Import auf diesem Rechner nicht verfügbar", sprintf(paste(
      "Leser laufen nur abgeschottet, damit ein fehlerhafter Leser nichts außer dem Beleg lesen und nichts senden kann.",
      "Das braucht Linux ab Kernel 6.2 (Landlock). Dieser Rechner meldet Kernel %s. %s"), kernel, outcome)),
    statement_reader_output_invalid = c("Leser lieferte ein ungültiges Ergebnis", sprintf(paste(
      "Der Leser „%s“ hat Werte geliefert, die Portelyra nicht annimmt (Form oder Plausibilität, etwa ein Tag nach heute).",
      "%s Bitte den Leser melden."), label, outcome)),
    statement_reader_failed = c("Leser ist abgebrochen", sprintf("Der Leser „%s“ ist beim Lesen der Datei abgebrochen. %s Bitte den Leser melden.", label, outcome)),
    statement_reader_timeout = c("Leser hat die Zeitgrenze überschritten", sprintf(paste(
      "Der Leser „%s“ hat länger gebraucht als erlaubt und wurde beendet (Grenze je Datei 120 Sekunden).",
      "%s Bei sehr großen Exporten hilft es, den Zeitraum zu teilen."), label, outcome)),
    statement_reader_unavailable = c("Leser nicht verfügbar", sprintf(paste(
      "Der Leser „%s“ ist nicht installiert, oder seine Prüfsumme stimmt nicht mit dem Manifest überein (Datei verändert).",
      "%s"), label, outcome)),
    statement_reader_pdf_text_missing = c("PDF-Text fehlt", sprintf("Für den Leser „%s“ fehlt der Text des PDF. %s", label, outcome)),
    # Pruefstand je Portfolio (rc.380): ein noch nicht an Ihren Belegen gepruefter Leser bucht nur mit ausdruecklicher Bestaetigung.
    statement_reader_unchecked = c("Bitte erst die Vorschau prüfen", sprintf(paste(
      "Der Leser „%s“ ist in diesem Portfolio noch nicht an Ihren Belegen geprüft (oder liegt in einer neuen Version vor).",
      "Vergleichen Sie die Vorschau mit den Belegen und setzen Sie das Häkchen. %s"), label, outcome)),
    statement_reader_check_portfolio_unknown = c("Portfolio nicht eindeutig", sprintf(paste(
      "Für den Leser „%s“ ließ sich nicht feststellen, in welchem Portfolio gebucht wird (Konten aus mehreren Portfolios oder keines). %s"), label, outcome)),
    statement_reader_inactive = c("Leser in diesem Portfolio nicht aktiv", sprintf(paste(
      "Der Leser „%s“ ist in diesem Portfolio nicht aktiv. Aktivieren lässt er sich im Reiter „Leser“ unter „Aktivierung je Portfolio“. %s"), label, outcome)),
    statement_reader_incompatible = c("Leser nach dem Update nicht kompatibel", sprintf(paste(
      "Der installierte Leser „%s“ hat den Selbsttest mit dieser Fassung von Portelyra nicht bestanden und ist gesperrt, bis eine neue Fassung",
      "des Herausgebers installiert ist und besteht (Befunde im Reiter „Leser“). %s"), label, outcome)),
    statement_reader_check_store_invalid = c("Prüfstand der Leser nicht lesbar", sprintf(paste(
      "Ob der Leser „%s“ an Ihren Belegen geprüft ist, ließ sich nicht lesen (Speicher activity-reader-checks). %s"), label, outcome)),
    c("Leser meldet einen Fehler", sprintf("Der Leser „%s“ meldet „%s“. %s", label, code, outcome)))
  list(tone = "error", title = text[[1L]], copy = text[[2L]], code = code)
}

# Herkunft je Buchung (rc.378): Welcher Leser eine Buchung erzeugt hat, haelt Portelyra nach dem Buchen fest. Gelingt das nicht, bleibt
# die Buchung stehen; die Meldung sagt es, statt es zu verschweigen. Sonst kein Text.
data_statement_provenance_note_v1 <- function(status) {
  status <- if (is.character(status) && length(status) == 1L && !is.na(status)) status else ""
  if (!startsWith(status, "failed")) return("")
  sprintf(paste("Gebucht ist alles; nur die Herkunft (welcher Leser die Buchungen erzeugt hat, mit Version und Prüfsumme) konnte nicht",
                "festgehalten werden (%s). Sie gilt für diese Buchungen als „nicht verfügbar“."), sub("^failed:", "", status))
}

# Pruefstand je Portfolio (rc.380, Festlegungen vom 09.11.2026): Ein Leser gilt erst als "an Ihren Belegen geprueft", wenn
# Sie eine Buchung mit genau diesem Plugin-Code ausdruecklich bestaetigt haben. ``check`` ist das Feld reader_check einer Vorschau.
data_statement_reader_check_required_v1 <- function(check) is.list(check) && isTRUE(check$acknowledgment_required)

# Hinweis in der Vorschau: je ungeprueftem Leser ein Satz, dazu Hinweise (Hilfsbibliothek geaendert). NULL ohne Anlass.
data_statement_reader_check_panel_v1 <- function(check) {
  if (!is.list(check)) return(NULL)
  notes <- unlist(check$notes, use.names = FALSE); hints <- unlist(check$hints, use.names = FALSE)
  if (identical(check$status, "unavailable")) notes <- c(notes, paste0(
    "Ob die Leser an Ihren Belegen geprüft sind, ließ sich nicht feststellen (", as.character(check$code), "). Buchen geht nur mit dem Häkchen."))
  blocked <- unlist(check$blocked_notes, use.names = FALSE)
  if (!length(notes) && !length(hints) && !length(blocked)) return(NULL)
  # Beleg ohne Saldo (Festlegung vom 07.11.2026): deutlich, dass bis zur Bestaetigung nur der eigene Vergleich prueft.
  balance <- if (is.character(check$balance_warning) && length(check$balance_warning) == 1L && nzchar(check$balance_warning)) check$balance_warning else NULL
  shiny::div(class = "pl-reader-check",
    # Gesperrt (rc.381): nicht aktiv im Portfolio oder nach einem Update nicht mehr kompatibel - bucht nie, auch nicht mit Haekchen.
    if (length(blocked)) portelyra_status_panel("Leser gesperrt", shiny::tags$ul(lapply(blocked, shiny::tags$li)), tone = "error"),
    if (length(notes)) portelyra_status_panel("Leser noch nicht an Ihren Belegen geprüft",
      shiny::tagList(if (!is.null(balance)) shiny::p(shiny::tags$strong(balance)), shiny::tags$ul(lapply(notes, shiny::tags$li))), tone = "warning"),
    if (length(hints)) shiny::p(class = "pl-section-copy", paste(hints, collapse = " ")))
}

# Haekchen vor dem Buchen, nur wenn die Vorschau es verlangt; die Vorschau rendert es neu, damit es an genau diese Vorschau gebunden ist.
data_statement_reader_check_ack_v1 <- function(input_id, check, document = "den Belegen") {
  if (!data_statement_reader_check_required_v1(check) || isTRUE(check$blocked)) return(NULL)
  shiny::checkboxInput(input_id, sprintf(paste("Ich habe die Vorschau mit %s verglichen. Die genannten Leser dürfen in diesem Portfolio buchen",
                                              "(gilt für genau diese Version)."), document), value = FALSE)
}

# Nach dem Buchen: Konnte der Pruefstand nicht festgehalten werden, bleibt die Buchung stehen; die Meldung sagt es. Sonst kein Text.
data_statement_reader_check_note_v1 <- function(recorded) {
  recorded <- if (is.character(recorded) && length(recorded) == 1L && !is.na(recorded)) recorded else ""
  if (!startsWith(recorded, "failed")) return("")
  sprintf(paste("Gebucht ist alles; nur die Bestätigung des Lesers konnte nicht festgehalten werden (%s). Beim nächsten Import fragt die",
                "Vorschau deshalb erneut."), sub("^failed:", "", recorded))
}

# Pruefstand fuer Ablaeufe ohne eigenen Vorschau-Befehl (Rewards, rc.380): Stand lesen, vor dem Buchen pruefen, danach festhalten.
# readers: list(list(reader_id = ..., domain = ...)); account_ids: Zeichenvektor (leer = einziges Portfolio des Datenraums).
new_data_statement_reader_check_service_v1 <- function(project_root, context) {
  payload_context <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                          actor_id = context$actor_id, role = "desktop_owner")
  run <- function(command, payload) .per_asset_review_adapter_run(project_root, command, payload)
  base <- function(readers, account_ids) list(context = payload_context, data_space_path = runtime_data_space_path(context),
    readers = readers, account_ids = as.list(as.character(account_ids)))
  list(
    status = function(readers, account_ids = character(), balance_checked = NULL) run("statement-reader-check",
      c(base(readers, account_ids), list(balance_checked = balance_checked)))$reader_check,
    require = function(readers, acknowledged, account_ids = character()) run("statement-reader-check-confirm",
      c(base(readers, account_ids), list(acknowledged = isTRUE(acknowledged), phase = "require", recorded_at_utc = NULL, document_count = NULL, booking_count = NULL))),
    # Was die Import-Karten anbieten (rc.381): Leser der Plugins, die in mindestens einem Portfolio aktiv sind.
    offered = function() run("statement-reader-offered", list(context = payload_context, data_space_path = runtime_data_space_path(context))),
    record = function(readers, acknowledged, recorded_at_utc, account_ids = character(), document_count = NULL, booking_count = NULL) run("statement-reader-check-confirm",
      c(base(readers, account_ids), list(acknowledged = isTRUE(acknowledged), phase = "record", recorded_at_utc = recorded_at_utc,
        document_count = if (is.null(document_count)) NULL else as.integer(document_count), booking_count = if (is.null(booking_count)) NULL else as.integer(booking_count))))$reader_check_recorded
  )
}
