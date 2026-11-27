# Cash statement import (#184): thin R boundary over migrations/reference/cash_statement_import_v1.py.
# The browser only sees labels and counts; account and asset IDs stay server-side.

# Tag als ISO-Datum fuer die CLI; leer oder fehlend = offen ("").
data_cash_statement_day_v1 <- function(value) {
  if (is.null(value) || !length(value) || is.na(value[[1L]]) || !nzchar(as.character(value[[1L]]))) return("")
  format(as.Date(value[[1L]]), "%Y-%m-%d")
}

new_data_cash_statement_import_v1 <- function(project_root, context) {
  payload_context <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                          actor_id = context$actor_id, role = "desktop_owner")
  run <- function(command, payload) .per_asset_review_adapter_run(project_root, command, payload)
  list(
    # An empty R list serialises to [], which the bridge rejects: force an empty JSON object.
    # Mit dem Datenraum, damit installierte Leser-Plugins mit in der Liste stehen (rc.381).
    adapters = function() run("cash-statement-adapters", list(data_space_path = runtime_data_space_path(context)))$adapters,
    detect = function(source_path, file_name) run("cash-statement-detect", list(source_path = source_path, file_name = file_name))$matches,
    # source_path und file_name sind Listen: ein Auszug oder ein ganzer Ordner.
    # confirmed_balance: NULL oder list(as_of_date = "JJJJ-MM-TT", balance_decimal = "123.45").
    preview = function(adapter_id, source_path, file_name, account_id, confirmed_balance = NULL) run("cash-statement-preview", list(
      context = payload_context, data_space_path = runtime_data_space_path(context), adapter_id = adapter_id,
      source_path = source_path, file_name = file_name, account_id = account_id, confirmed_balance = confirmed_balance))$preview,
    # reader_check_acknowledged (rc.380): ausdrueckliche Bestaetigung fuer einen Leser, der in diesem Portfolio noch nicht an Ihren Belegen
    # geprueft ist; Python prueft den Stand selbst nach und haelt ihn nach dem letzten Schritt fest.
    apply = function(adapter_id, source_path, file_name, scope, include_text, max_commands, applied_at_utc, confirmed_balance = NULL,
                     reader_check_acknowledged = FALSE) run("cash-statement-apply", list(
      context = payload_context, canonical_path = runtime_canonical_path(context), data_space_path = runtime_data_space_path(context),
      adapter_id = adapter_id, source_path = source_path, file_name = file_name, scope = scope,
      applied_at_utc = applied_at_utc, include_text = isTRUE(include_text), max_commands = as.integer(max_commands),
      confirmed_balance = confirmed_balance, reader_check_acknowledged = isTRUE(reader_check_acknowledged)))$result,
    # Netto gebuchte Zinsertraege auf brutto heben (#465): eigene Vorschau, eigene
    # Bestaetigung, eigene Belege - der Geldfluss bleibt unberuehrt.
    # consider_from (#462): Brutto-Vorschlaege erst ab diesem Tag ("" = alle); Vorschau und Anwenden mit demselben Wert.
    gross_preview = function(adapter_id, source_path, file_name, account_id, confirmed_balance = NULL, consider_from = "") run("cash-statement-gross-preview", list(
      context = payload_context, data_space_path = runtime_data_space_path(context), adapter_id = adapter_id,
      source_path = source_path, file_name = file_name, account_id = account_id, confirmed_balance = confirmed_balance,
      consider_from = data_cash_statement_day_v1(consider_from)))$correction,
    gross_apply = function(adapter_id, source_path, file_name, scope, max_corrections, applied_at_utc, confirmed_balance = NULL, consider_from = "") run("cash-statement-gross-apply", list(
      context = payload_context, canonical_path = runtime_canonical_path(context), data_space_path = runtime_data_space_path(context),
      adapter_id = adapter_id, source_path = source_path, file_name = file_name, scope = scope,
      applied_at_utc = applied_at_utc, max_corrections = as.integer(max_corrections), confirmed_balance = confirmed_balance,
      consider_from = data_cash_statement_day_v1(consider_from)))$result,
    movements = function(account_id) run("cash-movements", list(
      context = payload_context, data_space_path = runtime_data_space_path(context),
      account_id = if (is.null(account_id)) NA else account_id))$movements
  )
}

# Accounts that hold Cash carry a visible domain marker; the stored name stays unchanged.
data_cash_account_label_v1 <- function(label, account_type) {
  if (is.character(account_type) && length(account_type) == 1L && account_type %in% c("cash", "bank")) paste(label, "· Cash") else label
}

# Eingang und Ausgang, nicht Ein- und Auszahlung (rc.325): Cash kennt nur Tagessalden, und ein Verkauf an der Boerse ist keine
# Einzahlung. Was es war, steht im Text der Zeile.
data_cash_statement_kind_label_v1 <- function(kind) {
  unname(c(interest = "Zinsen (Ertrag + Eingang)", deposit = "Eingang", withdrawal = "Ausgang")[kind])
}

# Welche Dateitypen die gewaehlte Quelle liest (#452, Festlegung 22.10.2026).
# Grenzen des Lesers aus dem Manifest (#550, aus #486), auf Deutsch; die Pruefangabe tested_formats mit den Spaltennamen des Exports
# steht nur im Reiter „Leser“. Ein Leser, der die Dateien eines Kontos zusammen liest (BSDEX: Export und Jahreshistorien), hat keine
# Monatsauszuege - der Satz zu Saldo-Ankern gilt dort nicht.
data_cash_statement_formats_ui_v1 <- function(adapters, chosen) {
  hit <- Filter(function(item) identical(item$adapter_id, chosen), if (is.list(adapters)) adapters else list())
  if (!length(hit)) return(NULL)
  item <- hit[[1L]]
  types <- toupper(sub("^\\.", "", unlist(item$extensions, use.names = FALSE)))
  how <- if (isTRUE(item$combine)) "Die Dateien des Kontos zusammen wählen; Portelyra liest sie gemeinsam."
         else "Mehrere Auszüge eines Kontos lassen sich zusammen wählen; Monate ohne Bewegung zählen als Saldo-Anker."
  limits <- as.character(unlist(item$known_limits))
  shiny::tagList(
    shiny::p(class = "pl-field-hint", paste(c(paste0("Liest: ", paste(types, collapse = ", "), "."), how,
                                              data_cash_statement_validation_text_v1(item$validated)), collapse = " ")),
    if (length(limits)) shiny::tags$ul(class = "pl-field-hint", lapply(limits, shiny::tags$li)))
}
# Pruefstand des Lesers (#492, wie bei den Wertpapierlesern #450): bis wann sein Format mit echten Auszuegen geprueft ist (Manifest, #486).
data_cash_statement_validation_text_v1 <- function(validated) {
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  if (!is.list(validated) || is.null(validated$through)) return("Format noch nicht mit echten Auszügen geprüft – die Vorschau bitte mit dem Auszug vergleichen.")
  sprintf("Format geprüft (Stand %s).", day(validated$checked_on))
}
# Hinweis in der Vorschau: neue Bewegungen nach dem Pruefstand oder bei einem noch nicht erprobten Leser.
data_cash_statement_reader_note_v1 <- function(reader) {
  beyond <- if (is.list(reader) && !is.null(reader$beyond_validation_count)) as.integer(reader$beyond_validation_count) else 0L
  if (beyond <= 0L) return("")
  if (!is.list(reader$validated) || is.null(reader$validated$through))
    return(sprintf("Das Format dieses Lesers ist noch nicht mit echten Auszügen geprüft: Die %d neuen Bewegungen bitte mit dem Auszug vergleichen.", beyond))
  sprintf("%d neue %s jünger als die letzte Prüfung des Leserformats (Stand %s) – bitte mit dem Auszug vergleichen.", beyond,
          if (identical(beyond, 1L)) "Bewegung ist" else "Bewegungen sind", format(as.Date(reader$validated$through), "%d.%m.%Y"))
}

# BSDEX: Orders bzw. Euro-Bewegungen ohne Beleg in der Transaktionshistorie, je Grund (rc.376). %1$s: „N Order(s) ab dem TT.MM.JJJJ“.
DATA_CASH_BSDEX_GAPS_V1 <- c(
  bsdex_history_missing = "Die BSDEX-Transaktionshistorie %2$s fehlt: %1$s sind ohne genauen Betrag. Bitte die Historie %2$s laden und ablegen.",
  bsdex_history_outdated = "Die BSDEX-Transaktionshistorie reicht nur bis %3$s: %1$s stehen nur im Export. Bitte die aktuelle Historie laden und ablegen (das laufende Jahr neu).",
  bsdex_executions_missing = "%1$s: In ihrem Zeitraum nennt die Transaktionshistorie keine Ausführung, obwohl sie diese Tage abdeckt. Bitte Export und Historie vom selben Tag laden.",
  bsdex_execution_quantity_differs = "%1$s: Die Ausführungen in ihrem Zeitraum ergeben nicht die Menge aus dem Export. Bitte beide Dateien prüfen.",
  bsdex_execution_amount_differs = "%1$s: Die Ausführungen ergeben die Menge, aber nicht den Kurswert aus dem Export%4$s. Bitte beide Dateien prüfen.",
  bsdex_executions_ambiguous = "%1$s: Im Zeitraum liegen zu viele Ausführungen, um sie eindeutig zuzuordnen. Bitte melden.",
  bsdex_flows_missing = "%1$s: Sie stehen im Export „Transaktionen“, aber nicht in der Transaktionshistorie, obwohl diese die Tage abdeckt. Bitte beide Dateien vom selben Tag laden.")

data_cash_statement_bsdex_gap_text_v1 <- function(gap) {
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  number <- function(value) if (is.null(value)) 0L else as.integer(value)
  what <- paste(c(if (number(gap$order_count) > 0L) sprintf("%d Order(s)", number(gap$order_count)),
                  if (number(gap$flow_count) > 0L) sprintf("%d Ein- oder Auszahlung(en)", number(gap$flow_count))), collapse = " und ")
  amounts <- if (is.null(gap$executions_amount_decimal)) "" else
    sprintf(" (bei der ersten %s € statt %s €)", gap$executions_amount_decimal, gap$export_amount_decimal)
  body <- sprintf(DATA_CASH_BSDEX_GAPS_V1[[as.character(gap$reason)]], sprintf("%s ab dem %s", what, day(gap$period_from)),
    if (is.null(gap$year)) "" else as.character(gap$year), if (is.null(gap$history_until)) "" else day(gap$history_until), amounts)
  first <- if (is.null(gap$side)) "" else sprintf(" Die erste: %s %s %s am %s, laut Export %s € und %s € Entgelt.",
    c(buy = "Kauf", sell = "Verkauf")[[as.character(gap$side)]], gap$quantity_decimal, gap$asset, day(gap$period_from),
    gap$export_amount_decimal, gap$export_fee_decimal)
  paste0(body, first, " Es wurde nichts gebucht.")
}

# Weitere Luecken (rc.376): Die erste steht in der Abdeckung, jede weitere mit ihrem eigenen Grund.
data_cash_statement_further_gaps_text_v1 <- function(gaps) {
  gaps <- if (is.list(gaps)) gaps else list()
  if (length(gaps) < 2L) return("")
  paste(vapply(gaps[-1L], function(gap) data_cash_statement_coverage_text_v1(c(list(proposal = "gap"), gap)), character(1L)), collapse = " ")
}

data_cash_statement_coverage_text_v1 <- function(coverage) {
  if (!is.list(coverage)) return("")
  switch(as.character(coverage$proposal),
    complete_reconciled = if (isTRUE(coverage$owner_confirmed))
      sprintf("Vollständig abgeglichen ab %s bis zum Stichtag: Saldo %s am %s von Ihnen bestätigt, daraus Anfangssaldo %s.",
        format(as.Date(coverage$effective_from) + 1L, "%d.%m.%Y"), coverage$reconcile_to$observed_balance_decimal,
        format(as.Date(coverage$reconcile_to$as_of_date), "%d.%m.%Y"), coverage$opening_balance_decimal)
    else sprintf("Vollständig abgeglichen ab %s: Anfangssaldo %s, Endsaldo %s am %s aus dem Auszug belegt. Die Rechnung geht auf.",
      format(as.Date(coverage$effective_from) + 1L, "%d.%m.%Y"), coverage$opening_balance_decimal,
      coverage$reconcile_to$observed_balance_decimal, format(as.Date(coverage$reconcile_to$as_of_date), "%d.%m.%Y")),
    existing = if (identical(coverage$reason, "balance_anchor")) sprintf("Keine Bewegungen im Zeitraum. Der Auszug belegt den Saldo %s am %s; er passt zum gebuchten Stand und wird als Abgleich festgehalten.",
      coverage$reconcile_to$observed_balance_decimal, format(as.Date(coverage$reconcile_to$as_of_date), "%d.%m.%Y")) else
      if (is.list(coverage$reconcile_to)) sprintf("Zeitraum ist bereits erfasst. Zusätzlich wird der Endsaldo %s am %s als Abgleich festgehalten.",
      coverage$reconcile_to$observed_balance_decimal, format(as.Date(coverage$reconcile_to$as_of_date), "%d.%m.%Y")) else
      "Zeitraum ist bereits erfasst; nur neue Bewegungen werden ergänzt.",
    partial = "Teilweise erfasst: Der Auszug belegt keinen Saldo. Mit „Saldo bestätigen“ (Stichtag und Betrag, z. B. aus der Banking-App) wird das Konto bis zum Stichtag vollständig abgeglichen.",
    blocked = if (identical(coverage$reason, "partial_coverage_needs_correction"))
      "Dieses Konto ist bereits ohne Saldobestätigung als „teilweise erfasst“ gebucht. Eine nachträgliche Bestätigung ist hier noch nicht möglich; es wurde nichts gebucht."
    else "Für dieses Konto gibt es bereits eine Abdeckung, die nur einen Teil dieses Zeitraums umfasst. Bitte zuerst den passenden Zeitraum importieren.",
    gap = if (identical(coverage$reason, "owner_balance_mismatch"))
      sprintf("Der bestätigte Saldo passt nicht: Aus den gebuchten und neuen Bewegungen ergibt sich am %s ein Saldo von %s, bestätigt wurden %s. Bitte Stichtag und Betrag prüfen; es wurde nichts gebucht.",
        format(as.Date(coverage$as_of_date), "%d.%m.%Y"), coverage$expected_balance_decimal, coverage$opening_balance_decimal)
    else if (identical(coverage$reason, "statement_missing_before"))
      sprintf("Die Auszüge ergeben keine lückenlose Kette: „%s“ beginnt mit %s, der Auszug davor endet mit %s. Bitte den fehlenden Auszug ergänzen; es wurde nichts gebucht.",
        coverage$file_name, coverage$opening_balance_decimal, coverage$expected_balance_decimal)
    # BSDEX (rc.325): Gebucht wird je Order mit dem Betrag ihrer Ausfuehrungen; dafuer braucht es beide Dateien.
    # Seit rc.376 je Fall ein eigener Grund (Festlegung 08.11.2026: den Grund immer so genau wie moeglich).
    else if (as.character(coverage$reason) %in% names(DATA_CASH_BSDEX_GAPS_V1))
      data_cash_statement_bsdex_gap_text_v1(coverage)
    else if (identical(coverage$reason, "bsdex_orders_missing"))
      sprintf("%d Ausführung(en) ab dem %s gehören zu keiner Order im Export „Transaktionen“. Bitte den Export neu laden und ablegen – am selben Tag wie die Transaktionshistorie. Es wurde nichts gebucht.",
        as.integer(coverage$execution_count), format(as.Date(coverage$period_from), "%d.%m.%Y"))
    # Saldoprobe und neu verteilte Tage (#524)
    else if (identical(coverage$reason, "statement_balance_mismatch"))
      sprintf("Gebuchtes und Auszug passen nicht zusammen: Mit den neuen Bewegungen ergäbe sich am %s ein Saldo von %s, der Auszug nennt %s.%s Bitte prüfen; es wurde nichts gebucht.",
        format(as.Date(coverage$as_of_date), "%d.%m.%Y"), coverage$expected_balance_decimal, coverage$observed_balance_decimal,
        if (!is.null(coverage$period_from)) sprintf(" %d gebuchte Bewegung(en) nennt der Auszug gar nicht, die erste am %s.", as.integer(coverage$unmatched_count), format(as.Date(coverage$period_from), "%d.%m.%Y")) else "")
    else if (identical(coverage$reason, "restated_reconciliation_mismatch"))
      sprintf("Der Auszug verteilt gebuchte Tage neu, aber der Abgleich am %s passt danach nicht zu seinem Stand (%s statt %s).%s Bitte prüfen; es wurde nichts gebucht.",
        format(as.Date(coverage$as_of_date), "%d.%m.%Y"), coverage$expected_balance_decimal, coverage$opening_balance_decimal,
        if (!is.null(coverage$period_from)) sprintf(" Gebuchte Bewegungen fehlen im Auszug, die erste am %s.", format(as.Date(coverage$period_from), "%d.%m.%Y")) else "")
    else if (identical(coverage$reason, "restated_reconciliation_locked"))
      sprintf("Der Auszug verschiebt den Abgleich am %s, der zur Eröffnung des Kontos gehört. Das lässt sich nur über die Cash-Korrektur ändern; es wurde nichts gebucht.",
        format(as.Date(coverage$as_of_date), "%d.%m.%Y"))
    else if (identical(coverage$reason, "restated_group_too_large"))
      sprintf("Ab dem %s verteilt der Auszug so viele gebuchte Tage neu, dass sie nicht in einem Schritt korrigiert werden können (%d). Bitte melden; es wurde nichts gebucht.",
        format(as.Date(coverage$period_from), "%d.%m.%Y"), as.integer(coverage$correction_count))
    else if (identical(coverage$reason, "two_statements_for_one_period"))
      sprintf("Für den Zeitraum ab %s liegen zwei unterschiedliche Auszüge vor („%s“). Bitte den überholten entfernen; es wurde nichts gebucht.",
        format(as.Date(coverage$period_from), "%d.%m.%Y"), coverage$file_name)
    else sprintf("Es fehlt ein Auszug davor: Der Auszug beginnt mit %s, gebucht ist zum %s aber %s. Bitte zuerst die Auszüge des Zeitraums dazwischen importieren; es wurde nichts gebucht.",
      coverage$opening_balance_decimal, format(as.Date(coverage$as_of_date), "%d.%m.%Y"), coverage$expected_balance_decimal),
    none = "Keine Bewegungen im Auszug. Für dieses Konto gibt es noch keinen abgeglichenen Zeitraum, an den der Saldo anschließen könnte; es wird nichts gebucht.",
    "")
}

# BSDEX (rc.326): Ausfuehrungen einer noch offenen Order warten auf ihren Abschluss; gebucht wird je Order, nie ein Teil.
data_cash_statement_held_back_text_v1 <- function(held) {
  held <- if (is.list(held)) held else list()
  if (!length(held)) return("")
  side <- c(buy = "Kauf", sell = "Verkauf")
  parts <- vapply(held, function(row) sprintf("%s %s seit %s (%s)", side[[as.character(row$side)]], as.character(row$asset),
    format(as.Date(row$since), "%d.%m.%Y"), if (as.integer(row$execution_count) > 0L)
      sprintf("%d Ausführung(en), %s €", as.integer(row$execution_count), as.character(row$amount_decimal)) else "Ausführungen noch nicht in der Historie"),
    character(1L))
  sprintf("%d offene Order(s) schon teilweise ausgeführt: %s. Gebucht wird jede, sobald sie abgeschlossen ist (ausgeführt oder storniert); bis dahin weicht das Guthaben um diesen Betrag von BSDEX ab.",
    length(held), paste(parts, collapse = "; "))
}

# Dateien, die die gewaehlte Quelle nicht liest (#518), und solche im richtigen Format, die kein Auszug von ihr sind (rc.321): mit
# Namen in der Meldung, damit niemand eine fehlende Pruefung uebersieht.
data_cash_statement_skipped_text_v1 <- function(files) {
  files <- if (is.list(files)) files else list()
  named <- function(status) vapply(Filter(function(row) identical(row$status, status), files), function(row) as.character(row$file_name), character(1L))
  format_names <- named("skipped_format"); other_names <- named("skipped_unreadable")
  # Nur die Zahl (#522); jede Datei steht mit Grund in der Dateitabelle.
  paste(c(
    if (length(format_names)) sprintf("%d Datei(en) übergangen, weil die gewählte Quelle dieses Format nicht liest (siehe Dateiliste).", length(format_names)),
    if (length(other_names)) sprintf("%d Datei(en) übergangen, weil sie kein Auszug der gewählten Quelle sind (siehe Dateiliste).", length(other_names))),
    collapse = " ")
}

# Je Datei eine Zeile: welcher Zeitraum, wie viele Bewegungen, welcher Saldoverlauf.
data_cash_statement_files_frame_v1 <- function(preview) {
  if (!is.list(preview) || !length(preview$files)) return(data.frame())
  rows <- preview$files
  day <- function(value) if (is.null(value)) "" else format(as.Date(value), "%d.%m.%Y")
  status <- c(used = "verwendet", duplicate = "Duplikat, übersprungen", conflicting_duplicate = "zweiter Auszug für denselben Zeitraum", gap_before = "Auszug davor fehlt",
    skipped_format = "übergangen: Format liest diese Quelle nicht", skipped_unreadable = "übergangen: kein Auszug dieser Quelle",
    orders_for_grouping = "verwendet: ordnet die Ausführungen ihren Orders zu", superseded = "ersetzt durch einen neueren Auszug")
  data.frame(check.names = FALSE,
    Datei = vapply(rows, function(row) as.character(row$file_name), character(1L)),
    Zeitraum = vapply(rows, function(row) if (is.null(row$period_from) && is.null(row$period_to)) "" else paste(day(row$period_from), "–", day(row$period_to)), character(1L)),
    Bewegungen = vapply(rows, function(row) as.character(as.integer(row$row_count)), character(1L)),
    Saldo = vapply(rows, function(row) paste(if (is.null(row$opening_balance_decimal)) "?" else row$opening_balance_decimal, "→",
      if (is.null(row$closing_balance_decimal)) "?" else row$closing_balance_decimal), character(1L)),
    Status = vapply(rows, function(row) if (identical(row$status, "superseded") && !is.null(row$superseded_by)) sprintf("ersetzt durch „%s“", row$superseded_by)
      else if (!is.null(row$continued_by)) sprintf("verwendet bis %s, danach „%s“", day(row$period_to), row$continued_by)
      else unname(ifelse(is.na(status[[row$status]]), row$status, status[[row$status]])), character(1L)))
}

# Neu verteilte Tage (#524): Der neueste Auszug gilt; gebuchte Tage, die er anders nennt, werden korrigiert, nicht doppelt gebucht.
data_cash_statement_corrections_text_v1 <- function(corrections) {
  if (!is.list(corrections) || is.null(corrections$count) || as.integer(corrections$count) == 0L) return("")
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  shifts <- if (length(corrections$reconciliations)) sprintf(" Mitkorrigiert %s: %s.", if (length(corrections$reconciliations) == 1L) "wird der Abgleich" else "werden die Abgleiche",
    paste(vapply(corrections$reconciliations, function(item) sprintf("%s %s → %s", day(item$as_of_date), item$observed_balance_decimal, item$new_observed_balance_decimal), character(1L)), collapse = "; ")) else ""
  sprintf("%d gebuchte Tag(e) zwischen %s und %s nennt der Auszug anders (zusammen %s €): Sie werden korrigiert, die alten Buchungen bleiben als Vorgänger erhalten.%s",
    as.integer(corrections$count), day(corrections$first_date), day(corrections$last_date), corrections$delta_decimal, shifts)
}

# Lange Historien bremsen den Browser; die Tabelle zeigt
# deshalb die neuen Bewegungen zuerst und hoechstens DATA_CASH_TABLE_LIMIT Zeilen.
DATA_CASH_TABLE_LIMIT <- 500L

data_cash_statement_rows_frame_v1 <- function(preview) {
  if (!is.list(preview) || !length(preview$rows)) return(data.frame())
  rows <- preview$rows
  fresh <- vapply(rows, function(row) !identical(row$status, "booked"), logical(1L))
  rows <- c(rows[fresh], rows[!fresh])
  if (length(rows) > DATA_CASH_TABLE_LIMIT) rows <- rows[seq_len(DATA_CASH_TABLE_LIMIT)]
  data.frame(check.names = FALSE,
    Datum = vapply(rows, function(row) format(as.Date(row$local_date), "%d.%m.%Y"), character(1L)),
    Art = vapply(rows, function(row) data_cash_statement_kind_label_v1(row$kind), character(1L)),
    Text = vapply(rows, function(row) { text <- if (is.null(row$text)) "" else as.character(row$text); if (nchar(text) > 60L) paste0(substr(text, 1L, 59L), "…") else text }, character(1L)),
    Betrag = vapply(rows, function(row) as.character(row$amount_decimal), character(1L)),
    `Saldo laut Auszug` = vapply(rows, function(row) if (is.null(row$balance_after_decimal)) "" else as.character(row$balance_after_decimal), character(1L)),
    Status = vapply(rows, function(row) if (identical(row$status, "booked")) "Bereits gebucht" else if (identical(row$status, "corrected"))
      sprintf("Korrektur (gebucht %s)", row$booked_amount_decimal) else "Neu", character(1L)))
}

# Netto gebuchte Zinsertraege dieses Auszugs (#465): was gebucht ist, was der Auszug
# brutto nennt, und die Differenz - die einbehaltene Steuer, die im Topf fehlte.
data_cash_statement_gross_frame_v1 <- function(correction) {
  if (!is.list(correction) || !length(correction$rows)) return(data.frame())
  rows <- correction$rows
  if (length(rows) > DATA_CASH_TABLE_LIMIT) rows <- rows[seq_len(DATA_CASH_TABLE_LIMIT)]
  data.frame(check.names = FALSE,
    Datum = vapply(rows, function(row) format(as.Date(row$local_date), "%d.%m.%Y"), character(1L)),
    `Gebucht als Ertrag` = vapply(rows, function(row) as.character(row$booked_gross_income_decimal), character(1L)),
    `Brutto laut Auszug` = vapply(rows, function(row) as.character(row$gross_income_decimal), character(1L)),
    `Einbehaltene Steuer` = vapply(rows, function(row) as.character(row$withheld_tax_decimal), character(1L)),
    `Auf dem Konto` = vapply(rows, function(row) as.character(row$cash_amount_decimal), character(1L)))
}

data_cash_movements_frame_v1 <- function(movements, account_label) {
  if (!is.list(movements) || !length(movements$movements)) return(data.frame())
  rows <- movements$movements
  # Die juengsten Bewegungen zuerst; Summen und Saldo oben beruecksichtigen weiterhin alle.
  rows <- rev(rows)
  if (length(rows) > DATA_CASH_TABLE_LIMIT) rows <- rows[seq_len(DATA_CASH_TABLE_LIMIT)]
  kind <- function(row) if (identical(row$event_type, "opening_balance")) "Anfangssaldo" else if (identical(row$flow_classification, "income_receipt")) "Zinseingang" else if (identical(row$event_type, "withdrawal")) "Ausgang" else if (identical(row$event_type, "transfer")) "Übertrag" else "Eingang"
  data.frame(check.names = FALSE,
    Datum = vapply(rows, function(row) format(as.Date(row$local_date), "%d.%m.%Y"), character(1L)),
    Konto = vapply(rows, function(row) account_label(row$account_id), character(1L)),
    Art = vapply(rows, kind, character(1L)),
    Betrag = vapply(rows, function(row) as.character(row$signed_decimal), character(1L)))
}


# Meldungen der Leser-Plugins (#486, rc.373; seit rc.377 je Grund ein eigener Satz in data_statement_reader_messages_v1.R).
data_cash_statement_reader_message_v1 <- function(message, reader_label, kernel = tryCatch(as.character(Sys.info()[["release"]]), error = function(error) "unbekannt")) {
  found <- data_statement_reader_message_v1(message, reader_label, "Es wurde nichts gebucht.", kernel)
  if (is.null(found)) NULL else found[c("tone", "title", "copy")]
}
