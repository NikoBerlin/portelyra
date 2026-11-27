# Wertpapier- und Krypto-Belege importieren (#446, #454): duenne R-Grenze ueber migrations/reference/securities_statement_import_v1.py.
# Der Browser sieht nur Bezeichnungen, Zaehler und Handles; Konto- und Asset-IDs bleiben serverseitig. Gebucht wird ueber
# den Aktivitaeten-CSV-Import (Vorschau, Bestaetigung, schrittweises Buchen, Wiederaufnahme).

new_data_securities_statement_import_v1 <- function(project_root, context) {
  payload_context <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id,
                          actor_id = context$actor_id, role = "desktop_owner")
  run <- function(command, payload) .per_asset_review_adapter_run(project_root, command, payload)
  empty_object <- structure(list(), names = character())
  list(
    adapters = function() run("securities-statement-adapters", list(data_space_path = runtime_data_space_path(context)))$adapters,
    # source_path und file_name: beliebig viele Belege eines Instituts. depot_accounts: Depot-Handle -> account_id.
    # window (#462): betrachteter Zeitraum; Vorgabe "ab dem letzten bestaetigten Import dieses Lesers".
    # scope_skip (#551): Vorgaenge einer im Portfolio nicht gewaehlten Klasse bewusst ueberspringen; Teil der bestaetigten Pruefung.
    review = function(adapter_id, source_path, file_name, depot_accounts = list(), window = data_securities_statement_window_v1(), scope_skip = FALSE) run("securities-statement-review", list(
      context = payload_context, canonical_path = runtime_canonical_path(context), data_space_path = runtime_data_space_path(context),
      adapter_id = adapter_id, source_path = as.list(source_path), file_name = as.list(file_name),
      depot_accounts = if (length(depot_accounts)) depot_accounts else empty_object, window = window, scope_skip = isTRUE(scope_skip))),
    # reader_check_acknowledged (rc.380): ausdrueckliche Bestaetigung fuer Leser, die in diesem Portfolio noch nicht an Ihren Belegen geprueft
    # sind; Python prueft den Stand selbst nach (vor dem Buchungsplan, vor Vorabpauschalen und Splits) und haelt ihn nach dem Buchen fest.
    csv = function(trusted_review_token, target_path, reader_check_acknowledged = FALSE) run("securities-statement-csv", list(
      context = payload_context, canonical_path = runtime_canonical_path(context), data_space_path = runtime_data_space_path(context),
      trusted_review_token = trusted_review_token, target_path = target_path, reader_check_acknowledged = isTRUE(reader_check_acknowledged))),
    # Nach dem Buchen: der Pruefstand des Lesers waechst mit (#450), wenn alle neuen Vorgaenge gebucht sind.
    confirm = function(trusted_review_token, created_event_count, confirmed_at_utc, reader_check_acknowledged = FALSE) run("securities-statement-confirm", list(
      context = payload_context, data_space_path = runtime_data_space_path(context), trusted_review_token = trusted_review_token,
      created_event_count = as.integer(created_event_count), confirmed_at_utc = confirmed_at_utc, reader_check_acknowledged = isTRUE(reader_check_acknowledged))),
    # Juengstes gebuchtes Datum je Institut (#462), etwa fuer den Reward-Zeitraum.
    latest = function(event_type) run("booked-latest-dates", list(context = payload_context, canonical_path = runtime_canonical_path(context),
      data_space_path = runtime_data_space_path(context), event_type = event_type))$latest,
    # Kontovorschlag je Coin fuer den Reward-Import (rc.343): asset_id -> account_id, nur wo eindeutig. Liest nur.
    reward_accounts = function(adapter_id, asset_ids) {
      if (!length(asset_ids)) return(list())
      value <- run("reward-account-suggest", list(context = payload_context, canonical_path = runtime_canonical_path(context),
        data_space_path = runtime_data_space_path(context), adapter_id = adapter_id, asset_ids = as.list(unname(asset_ids))))$accounts
      if (!is.list(value)) list() else value
    },
    # Vorabpauschalen der Belege (#460): fehlende uebernehmen, abweichende nur mit ausdruecklichem Haken.
    advance_lump_sums = function(trusted_review_token, replace_differing, recorded_at_utc, reader_check_acknowledged = FALSE) run("securities-statement-advance-lump-sums", list(
      context = payload_context, data_space_path = runtime_data_space_path(context), trusted_review_token = trusted_review_token,
      replace_differing = isTRUE(replace_differing), recorded_at_utc = recorded_at_utc, confirmed = TRUE, reader_check_acknowledged = isTRUE(reader_check_acknowledged))),
    # Splitmitteilungen (#451, rc.372): Split uebernehmen und split-bereinigt gebuchte Vorgaenge auf die Belegstuecke umstellen.
    # Je Vorgang eine Korrektur, das dauert einige Sekunden je Vorgang.
    stock_splits = function(trusted_review_token, recorded_at_utc, reader_check_acknowledged = FALSE) run("securities-statement-stock-splits", list(
      context = payload_context, canonical_path = runtime_canonical_path(context), data_space_path = runtime_data_space_path(context),
      trusted_review_token = trusted_review_token, recorded_at_utc = recorded_at_utc, confirmed = TRUE, reader_check_acknowledged = isTRUE(reader_check_acknowledged))),
    # Kennungen gebuchter Vorgaenge aus den Belegen nachtragen (#458 Teil 3, #439): nur leere Felder, nach Bestaetigung.
    references = function(trusted_review_token, recorded_at_utc) run("securities-statement-references", list(
      context = payload_context, data_space_path = runtime_data_space_path(context), trusted_review_token = trusted_review_token,
      recorded_at_utc = recorded_at_utc, confirmed = TRUE))
  )
}

# Betrachteter Zeitraum (#462) aus den Feldern der Karte: Modus und optionale Grenzen als ISO-Datum (leer = offen).
data_securities_statement_window_v1 <- function(mode = "since_confirmed", from = NULL, through = NULL) {
  # Offene Grenze als "" - ein NULL schriebe JSON als {} statt null.
  day <- function(value) if (is.null(value) || !length(value) || is.na(value[[1L]]) || !nzchar(as.character(value[[1L]]))) "" else format(as.Date(value[[1L]]), "%Y-%m-%d")
  mode <- if (is.character(mode) && length(mode) == 1L && mode %in% c("since_confirmed", "chosen", "all")) mode else "since_confirmed"
  list(mode = mode, from = if (identical(mode, "chosen")) day(from) else "", through = if (identical(mode, "all")) "" else day(through))
}

data_securities_statement_window_note_v1 <- function(review) {
  hidden <- if (is.null(review$out_of_window_count)) 0L else as.integer(review$out_of_window_count)
  window <- review$window
  if (!hidden || is.null(window)) return("")
  counts <- if (is.null(review$out_of_window_counts)) list() else review$out_of_window_counts
  labels <- c(new = "neu", open = "offen", booked_differs = "abweichend", asset_missing = "ohne Katalogeintrag", depot_unassigned = "ohne Kontozuordnung")
  parts <- vapply(names(counts), function(key) paste(counts[[key]], if (is.na(labels[key])) key else labels[[key]]), character(1L))
  bounds <- paste0(if (!is.null(window$from)) paste0("vor dem ", format(as.Date(window$from), "%d.%m.%Y")) else "",
                   if (!is.null(window$from) && !is.null(window$through)) " oder " else "",
                   if (!is.null(window$through)) paste0("nach dem ", format(as.Date(window$through), "%d.%m.%Y")) else "")
  paste0(" · ", hidden, " Vorgang/Vorgänge ", bounds, " nicht betrachtet (", paste(parts, collapse = ", "), ")",
         if (identical(window$mode, "since_confirmed")) " – Zeitraum ab dem letzten bestätigten Import" else "")
}

# Blockierte Vorschau (rc.346): Der Hinweis auf fehlenden Bestand nur, wenn eine Zeile daran scheitert. Vorher stand er immer da -
# auch, wenn ein Verkauf an der Assetart scheiterte, und fuehrte auf die falsche Suche nach Kaeufen.
data_securities_import_blocked_copy_v1 <- function(preview) {
  codes <- vapply(if (is.null(preview)) list() else preview$rows, function(row) if (is.null(row$reason_code)) "" else as.character(row$reason_code), character(1L))
  paste0("Die Gründe stehen in der Tabelle; es wurde nichts gebucht. Eine blockierte Zeile hält alle Vorgänge dieser Auswahl an.",
         if ("simulation_failed" %in% codes) " Ein Verkauf ohne ausreichenden Bestand: die zugehörigen Käufe mit auswählen oder zuerst buchen." else "")
}

# Reward-Zeitraum (#462): Beginn ab dem juengsten gebuchten Reward der Boerse. latest: Institut -> ISO-Datum. Die Boerse eines Lesers
# ist das Institut seines Plugins (offered(), #486); ohne sie keine Vorbelegung.
data_reward_period_start_v1 <- function(latest, adapter, institution = NULL) {
  if (!is.character(institution) || length(institution) != 1L || is.na(institution) || !nzchar(institution) || !length(latest)) return(NULL)
  hits <- unlist(latest[startsWith(names(latest), institution)], use.names = FALSE)
  if (!length(hits)) NULL else max(as.character(hits))
}

# Was der Reward-Import je Boerse liest und was nicht (#492, Festlegung 23.10.2026: je Import-Moeglichkeit Geltungsbereich, Grenzen und
# Formate). Seit 0.3.4 (#550, aus #486) aus dem Manifest des Lesers (offered(): Dokument, known_limits, Pruefstand) - eine Quelle fuer
# mitgelieferte und installierte Leser; bis 0.3.3 standen die Texte fest hier und liefen dem Leser hinterher. Nicht gezeigt wird
# tested_formats: Das ist die Pruefangabe mit den Spaltennamen des Exports, oft englisch - sie steht im Reiter „Leser“ unter
# „Geprüfte Formate“. Bewertung und Grenzen stehen in known_limits, auf Deutsch.
data_reward_reader_info_v1 <- function(adapter_id, offered = NULL) {
  id <- if (is.character(adapter_id) && length(adapter_id) == 1L && !is.na(adapter_id)) adapter_id else ""
  if (!nzchar(id) || !is.list(offered) || !is.character(offered$label) || length(offered$label) != 1L) return(NULL)
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  text <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) value else NULL
  checked <- offered$format_checked
  state <- if (is.list(checked) && is.character(checked$through)) paste0("Format geprüft (Stand ", day(checked$checked_on),
    "). Jüngere Zeilen werden gelesen; die Vorschau zeigt sie vor dem Buchen.") else "Format noch nicht mit echten Belegen geprüft – die Vorschau bitte mit dem Export vergleichen."
  limits <- as.character(unlist(offered$known_limits))
  shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(offered$label), paste0(if (!is.null(text(offered$document_kind))) paste0(" · ", offered$document_kind) else "", " · ", state)),
    if (length(limits)) shiny::tags$ul(class = "pl-field-hint", lapply(limits, shiny::tags$li)),
    shiny::p(class = "pl-field-hint", "Die Datei darf die ganze Historie enthalten; übernommen werden die Rewards im gewählten Zeitraum."))
}

data_securities_statement_adapter_choices_v1 <- function(adapters) {
  c("Automatisch erkennen" = "auto", stats::setNames(vapply(adapters, `[[`, character(1L), "adapter_id"), vapply(adapters, `[[`, character(1L), "label")))
}

# Version, Pruefstand und Formate eines Lesers (#450): wie weit er geprueft ist und was er liest.
data_securities_statement_adapter_info_v1 <- function(adapter, adapters = NULL) {
  if (is.null(adapter)) {
    # Vor dem Pruefen (#452): was "Automatisch erkennen" liest.
    listed <- Filter(function(item) identical(item$domain, "securities") && is.character(item$formats), if (is.list(adapters)) adapters else list())
    return(shiny::div(class = "pl-section-copy",
      shiny::p("Der Leser wird beim Prüfen erkannt; Version, Prüfstand und Formate stehen dann hier.",
        if (length(listed)) paste("Gelesen werden PDF-, Text- und CSV-Dateien; andere Dateitypen erscheinen mit Grund in der Liste.")),
      if (length(listed)) shiny::tags$details(class = "pl-disclosure", shiny::tags$summary("Welche Belege „Automatisch erkennen“ liest"),
        shiny::tags$ul(lapply(listed, function(item) shiny::tags$li(shiny::strong(item$label), ": ", item$formats))))))
  }
  day <- function(value) format(as.Date(value), "%d.%m.%Y")
  validated <- adapter$validated; confirmed <- adapter$confirmed
  # Experimentell, ohne Pruefstand (#514): ausdruecklich so benannt, mit der Trefferquote als Hinweis.
  if (is.null(validated)) return(shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(adapter$label), paste0(" · Version ", adapter$version, " · experimentell, ohne Gewähr und ohne Prüfstand.",
      if (!is.null(confirmed)) paste0(" Von Ihnen bestätigt bis ", day(confirmed$through), " (", confirmed$documents, " Vorgänge gebucht).") else "")),
    shiny::p(paste("Liest:", adapter$formats), shiny::br(), paste("Bucht nicht:", adapter$not_booked)),
    shiny::p(class = "pl-field-hint", paste("Für Institute mit eigenem Leser hat dieser Vorrang. Der generische Leser ist für Institute ohne geprüften Leser gedacht;",
      "vor dem ersten Buchen die Zuordnung unten prüfen und speichern."))))
  through <- if (is.null(adapter$effective_through)) validated$through else adapter$effective_through
  shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(adapter$label), paste0(" · Version ", adapter$version, " · Format geprüft (Stand ", day(validated$checked_on), ")",
      if (!is.null(confirmed)) paste0(" · von Ihnen bestätigt bis ", day(confirmed$through), " (", confirmed$documents, " Vorgänge in ", confirmed$imports, " geprüften Importen gebucht)") else "",
      ". Belege nach dem ", day(through), " werden gelesen und gekennzeichnet.")),
    shiny::p(paste("Liest:", adapter$formats), shiny::br(), paste("Bucht nicht:", adapter$not_booked)))
}

# "Fehlendes Asset anlegen" (#453): je fehlendem Asset eine Zeile mit Knopf; der Knopf meldet nur die Nummer der Zeile.
data_securities_statement_missing_label_v1 <- function(item) {
  text <- function(value) if (is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)) value else NULL
  parts <- c(text(item$name), if (!identical(text(item$isin), text(item$name))) text(item$isin))
  if (!length(parts)) parts <- text(item$missing_key)
  paste(parts, collapse = " · ")
}
data_securities_statement_missing_ui_v1 <- function(result) {
  missing <- if (is.null(result) || is.null(result$review$missing_assets)) list() else result$review$missing_assets
  if (!length(missing)) return(NULL)
  domain <- missing[[1L]]$domain
  shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(if (identical(domain, "crypto")) "Coins fehlen im Katalog" else if (identical(domain, "fx")) "Devisen fehlen im Katalog" else "Wertpapiere fehlen im Katalog"),
      " – je Eintrag einmal anlegen oder einem vorhandenen Asset zuordnen; danach geht es zurück hierher, und die Belege werden erneut geprüft.",
      # Woran der Import zuordnet (#537): ohne passenden Eintrag entstuende sonst ein zweites Asset.
      shiny::span(class = "pl-field-hint", if (identical(domain, "crypto")) " Zugeordnet wird über das Kürzel: erstes Wort des Namens oder in Klammern, etwa „BTC (Bitcoin)“ oder „Bitcoin (BTC)“."
        else if (identical(domain, "fx")) " Zugeordnet wird über die Währung im Namen des Devisen-Assets."
        else " Zugeordnet wird über die ISIN am Asset. Steht ein gleichnamiges Asset ohne ISIN im Katalog, lässt es sich zuordnen; die ISIN wird dann nachgetragen.")),
    shiny::tags$ul(lapply(seq_along(missing), function(index) {
      item <- missing[[index]]
      existing <- if (is.null(item$existing_labels)) character() else as.character(unlist(item$existing_labels))
      shiny::tags$li(paste0(data_securities_statement_missing_label_v1(item), " (", as.integer(item$count), " Vorgang/Vorgänge) "),
        lapply(seq_along(existing), function(which) shiny::tags$button(type = "button", class = "btn btn-default btn-sm",
          onclick = sprintf("Shiny.setInputValue('securities_import_missing_assign', '%d|%d', {priority: 'event'})", index, which),
          paste0("Vorhandenes „", existing[[which]], "“ zuordnen"))),
        shiny::tags$button(type = "button", class = "btn btn-default btn-sm",
          onclick = sprintf("Shiny.setInputValue('securities_import_missing_pick', %d, {priority: 'event'})", index),
          if (length(existing)) "Doch neu anlegen" else "Fehlendes Asset anlegen"))
    })))
}

# Kursquelle fuer neu angelegte Assets (#538): Jedes im Import angelegte Asset bleibt in der Liste, bis es eine gepruefte und aktive
# Kursquelle hat oder nicht ueber den Markt bewertet wird („nur Transaktionen“, eigene Kurse, Einheitswert). `pending`: je Eintrag
# `asset_id` (interne Kennung - die Refs des Katalogs sind Positionen und verschieben sich) und `name`; `ref_of(asset_id)` liefert
# den aktuellen Ref oder NULL; `assets` und `mappings` sind Asset- und Kursanbieter-Katalog. Zurueck kommen die offenen mit `ref`.
data_securities_statement_open_sources_v1 <- function(pending, assets, mappings, ref_of) {
  open <- list()
  for (item in pending) {
    ref <- tryCatch(ref_of(item$asset_id), error = function(error) NULL)
    if (!is.character(ref) || length(ref) != 1L || is.na(ref)) next
    asset <- Filter(function(row) identical(row$ref, ref), assets)
    if (length(asset) != 1L || identical(asset[[1L]]$status, "archived")) next
    method <- asset[[1L]]$valuation_method
    if (is.character(method) && length(method) == 1L && !identical(method, "external_market")) next
    verified <- any(vapply(mappings, function(row) identical(row$asset_ref, ref) && identical(row$capability, "daily_history") &&
      identical(row$verification_status, "verified") && isTRUE(row$enabled), logical(1L)))
    if (!verified) open[[length(open) + 1L]] <- c(item, list(ref = ref))
  }
  open
}

data_securities_statement_sources_ui_v1 <- function(open) {
  if (!length(open)) return(NULL)
  names <- vapply(open, function(item) as.character(item$name), character(1L))
  copy <- paste0(if (length(open) == 1L) paste0("„", names[[1L]], "“ ist angelegt, aber noch ohne Kursquelle.")
                 else paste0(length(open), " neu angelegte Assets haben noch keine Kursquelle."),
                 " Ohne sie bleibt der Snapshot vor dem ersten Tag mit Bestand stehen. Wer ein Asset ohne Kurse führen will, wählt dort",
                 " „nur Transaktionen“. Nach dem Einrichten geht es von selbst hierher zurück; die Reihenfolge Buchen/Kursquelle ist egal.")
  shiny::div(class = "pl-editor-actions",
    portelyra_status_panel("Als Nächstes: Kursquelle", copy, tone = "warning"),
    shiny::tags$ul(lapply(seq_along(open), function(index) shiny::tags$li(names[[index]], " ",
      shiny::tags$button(type = "button", class = if (index == 1L) "btn btn-primary btn-sm" else "btn btn-default btn-sm",
        onclick = sprintf("Shiny.setInputValue('securities_import_source_pick', %d, {priority: 'event'})", index),
        "Kursquelle einrichten")))))
}

# Rueckmeldung nach der Rueckkehr aus den Marktdaten: was geprueft ist, ob noch Neues zu buchen ist, und was noch offen ist.
data_securities_statement_source_done_v1 <- function(name, result, open = list()) {
  counts <- if (is.null(result) || is.null(result$review)) list() else result$review$counts
  fresh <- if (is.null(counts[["new"]])) 0L else as.integer(counts[["new"]])
  rest <- vapply(open, function(item) as.character(item$name), character(1L))
  list(tone = "positive", title = "Kursquelle geprüft",
       copy = paste0("Kursquelle für „", name, "“ geprüft",
                     if (fresh > 0L) " – jetzt die neuen Vorgänge buchen." else ".",
                     if (length(rest)) paste0(" Noch ohne Kursquelle: ", paste(rest, collapse = ", "), ".") else ""))
}

# Kennungen nachtragen (#458 Teil 3, #439): Wie viele gebuchte Vorgaenge im Beleg-Speicher noch keine Kennung haben, die der Beleg nennt.
data_securities_statement_references_ui_v1 <- function(result) {
  count <- if (is.null(result) || is.null(result$review$reference_backfill_count)) 0L else as.integer(result$review$reference_backfill_count)
  if (!isTRUE(count > 0L)) return(NULL)
  shiny::div(class = "pl-section-copy",
    shiny::p(shiny::strong(sprintf("%d gebuchte(r) Vorgang/Vorgänge ohne Kennung", count)),
      " – der Beleg nennt Order-, Vorgangs- oder Transaktionsnummer (bei Krypto auch die Adresse). Übernommen wird nur in leere Felder; was schon eingetragen ist, bleibt."),
    shiny::checkboxInput("securities_import_references_confirm", "Kennungen aus diesen Belegen übernehmen", FALSE),
    shiny::actionButton("securities_import_references_run", "Kennungen nachtragen", class = "btn-default"))
}

# Umfang je Portfolio (#551, Festlegungen 11.11.2026): Hinweis und Wahl bei Vorgaengen einer im Portfolio nicht gewaehlten Klasse. Gebucht
# wird erst nach der Wahl; ueberspringen gilt fuer diese Auswahl von Belegen, ein neuer Import fragt neu. Ausserhalb des Zeitraums nur ein
# Hinweis. `open_settings` ist das Skript, das Einstellungen → Portfolio → Umfang dieses Portfolios oeffnet.
data_securities_statement_scope_ui_v1 <- function(review, prefix = "securities_import", open_settings = NULL) {
  if (!is.list(review)) return(NULL)
  number <- function(value) if (is.null(value)) 0L else as.integer(value)
  pending <- number(review$out_of_scope_count); skipped <- number(review$scope_skipped_count); outside <- number(review$out_of_scope_outside_window_count)
  if (!pending && !skipped && !outside) return(NULL)
  id <- function(name) paste0(prefix, "_", name)
  listing <- function(items) paste(vapply(items, function(item) sprintf("%s × „%s“", item$count, item$label), character(1L)), collapse = ", ")
  portfolio <- if (is.character(review$scope_portfolio_label) && nzchar(review$scope_portfolio_label)) review$scope_portfolio_label else "–"
  add <- shiny::actionButton(id("scope_add"), "Klasse dazunehmen", class = "btn-default", onclick = open_settings)
  shiny::div(class = "pl-field-group",
    if (pending) shiny::tagList(
      portelyra_status_panel(sprintf("%d Buchung(en) einer nicht gewählten Klasse", pending), paste0(listing(review$out_of_scope_classes),
        " – im Portfolio „", portfolio, "“ nicht gewählt. Gebucht wird erst, wenn Sie entscheiden: die Klasse dazunehmen (über die Vorschau unter",
        " Einstellungen → Portfolio → Umfang dieses Portfolios) oder diese Buchungen überspringen."), tone = "warning"),
      shiny::div(class = "pl-editor-actions", add, shiny::actionButton(id("scope_skip"), "Diese Buchungen überspringen", class = "btn-default"))),
    if (skipped) shiny::tagList(
      portelyra_status_panel(sprintf("%d Buchung(en) übersprungen", skipped), paste0(listing(review$out_of_scope_classes), " – Klasse im Portfolio „",
        portfolio, "“ nicht gewählt, nicht gebucht. Ein neuer Import fragt erneut."), tone = "neutral"),
      shiny::div(class = "pl-editor-actions", shiny::actionButton(id("scope_unskip"), "Doch nicht überspringen", class = "btn-default"))),
    if (outside) shiny::tagList(
      portelyra_status_panel(sprintf("%d weitere außerhalb des Zeitraums", outside), paste0(listing(review$out_of_scope_outside_window),
        " liegen außerhalb des betrachteten Zeitraums und gehören zu einer im Portfolio „", portfolio, "“ nicht gewählten Klasse; gebucht werden sie",
        " nicht. Zum Nachbuchen: Klasse dazunehmen und mit „Alle Zeiträume“ prüfen."), tone = "neutral"),
      if (!pending) shiny::div(class = "pl-editor-actions", add)))
}

data_securities_statement_state_v1 <- function(result) {
  if (is.null(result) || is.null(result$review)) {
    # Erkannt, aber in diesem Portfolio nicht aktiv (rc.440, Endabnahme 19.11.2026): den Leser und den Weg zur Aktivierung nennen.
    inactive <- if (is.list(result)) Filter(function(item) is.list(item) && is.character(item$label), result$inactive_matches) else list()
    if (length(inactive)) return(list(tone = "warning", title = "Leser nicht aktiv", copy = paste0(
      "Erkannt: ", paste(vapply(inactive, function(item) item$label, character(1L)), collapse = ", "), ". ",
      if (length(inactive) == 1L) "Dieser Leser ist" else "Diese Leser sind", " in keinem Portfolio aktiv. Aktivieren unter Daten → „1. Transaktionen“ → ",
      "„Leser“ → „Aktivierung je Portfolio“, danach die Belege erneut prüfen.")))
    return(list(tone = "warning", title = "Keine passenden Belege", copy = "Die gewählte Quelle erkennt keine der Dateien. Bitte Institut wählen oder andere Dateien nehmen."))
  }
  counts <- result$review$counts; count <- function(key) if (is.null(counts[[key]])) 0L else as.integer(counts[[key]])
  documents <- length(result$review$documents)
  other <- sum(vapply(result$review$documents, function(item) !identical(item$status, "candidate"), logical(1L)))
  # Devisen (#449): Befunde der Kontoauszuege (Zeile ohne Beleg, Saldo geht nicht auf, Kette unterbrochen) zaehlen eigens.
  fx <- identical(result$review$adapter$domain, "fx")
  # Krypto (#454): Wallets statt Depots; was der Export nicht vollstaendig hergibt, bleibt offen und wird nicht gebucht.
  crypto <- identical(result$review$adapter$domain, "crypto")
  reasons <- if (is.null(result$review$row_reasons)) list() else result$review$row_reasons
  anchor <- vapply(reasons, function(item) item$reason_code %in% c("fx_line_without_document", "fx_balance_mismatch", "fx_balance_gap"), logical(1L))
  rows <- sum(vapply(reasons[!anchor], function(item) as.integer(item$rows), integer(1L)))
  anchors <- sum(vapply(reasons[anchor], function(item) as.integer(item$rows), integer(1L)))
  booked <- count("booked") + count("booked_combined") + count("split_adjusted")
  advance <- data_securities_statement_advance_summary_v1(result$review)
  split <- if (is.null(result$review$split_recommended_count)) 0L else as.integer(result$review$split_recommended_count)
  copy <- paste0(documents, " Datei(en) gelesen · ", count("new"), " neu · ", booked, " schon gebucht",
                 if (count("booked_differs")) paste0(" · ", count("booked_differs"), " gebucht, weichen ab") else "",
                 if (count("open")) paste0(" · ", count("open"), " offen, nicht automatisch buchbar (Grund in der Tabelle)") else "",
                 if (count("out_of_scope")) paste0(" · ", count("out_of_scope"), " einer nicht gewählten Klasse – bitte unten entscheiden") else "",
                 if (count("skipped_scope")) paste0(" · ", count("skipped_scope"), " übersprungen (Klasse nicht gewählt)") else "",
                 if (count("asset_missing")) paste0(" · ", count("asset_missing"), if (fx) " ohne Devisen-Asset im Katalog" else if (crypto) " ohne Coin im Katalog" else " ohne Wertpapier im Katalog") else "",
                 if (count("depot_unassigned")) paste0(" · ", count("depot_unassigned"), if (fx) " ohne Kontozuordnung" else if (crypto) " ohne Wallet-Zuordnung" else " ohne Depotzuordnung") else "",
                 if (anchors) paste0(" · ", anchors, " Befund(e) der Kontoauszüge (Gründe in der Liste)") else "",
                 if (other) paste0(" · ", other, " Datei(en) ohne Buchung (Gründe in der Liste)") else "",
                 if (rows) paste0(" · ", rows, " Exportzeile(n) ohne Buchung (Gründe in der Liste)") else "",
                 if (split) paste0(" · ", split, " Teilausführung(en) gemeinsam gebucht – die Bank verbraucht sie getrennt") else "",
                 data_securities_statement_window_note_v1(result$review),
                 advance$copy)
  # Fehlende Wertpapiere werden nie mitgebucht; das muss auch dann sichtbar sein, wenn sonst alles gebucht ist.
  missing <- if (!count("asset_missing")) "" else if (crypto) paste0(" ", count("asset_missing"), " Vorgang/Vorgänge bleiben ungebucht, weil ihr Coin im Katalog fehlt – „Fehlendes Asset anlegen“ trägt das Kürzel als erstes Wort des Namens ein (z. B. „BTC (Bitcoin)“) und führt danach zurück.")
    else if (fx) paste0(" ", count("asset_missing"), " Vorgang/Vorgänge bleiben ungebucht, weil ihre Währung im Katalog fehlt – „Fehlendes Asset anlegen“ legt ein Asset der Klasse „Devisen“ mit der Währung im Namen an (z. B. „US-Dollar“) und führt danach zurück.")
    else paste0(" ", count("asset_missing"), " Vorgang/Vorgänge bleiben ungebucht, weil ihr Wertpapier im Katalog fehlt – „Fehlendes Asset anlegen“ führt in die Stammdaten und danach zurück.")
  if (count("depot_unassigned")) return(list(tone = "warning", title = if (fx || crypto) "Konto zuordnen" else "Depot zuordnen", copy = paste0(copy, if (crypto)
    " – bitte unten jedem Wallet sein Konto (Kontoart Wallet) zuweisen und erneut prüfen." else if (fx)
    " – bitte unten jeder Währung ihr Fremdwährungskonto (Kontoart „Fremdwährungskonto (Devisen) / Sonstiges“) zuweisen und erneut prüfen." else " – bitte unten jedem Depot ein Konto zuweisen und erneut prüfen.", missing)))
  beyond <- if (is.null(result$review$beyond_validation_count)) 0L else as.integer(result$review$beyond_validation_count)
  beyond_through <- if (is.null(result$review$adapter$effective_through)) result$review$adapter$validated$through else result$review$adapter$effective_through
  # Ein experimenteller Leser (#514) hat keinen Pruefstand: Dann gilt der Hinweis fuer jeden neuen Vorgang.
  unproven <- !is.character(beyond_through) || length(beyond_through) != 1L || !nzchar(beyond_through)
  beyond_note <- if (beyond && unproven) paste0(" Der Leser ist experimentell und ohne Gewähr: Alle ", beyond, " neuen Vorgänge bitte in der Vorschau Zeile für Zeile mit dem Export vergleichen.")
    else if (beyond) paste0(" ", beyond, " davon sind jünger als die letzte Prüfung des Leserformats (Stand ", format(as.Date(beyond_through), "%d.%m.%Y"),
                                    ") – die Vorschau bitte mit den Belegen vergleichen.") else ""
  # Aeltere neue Vorgaenge ausserhalb des Zeitraums (#462): nie unter "Alles gebucht" verschwinden lassen.
  hidden_new <- if (is.null(result$review$out_of_window_counts$new)) 0L else as.integer(result$review$out_of_window_counts$new)
  if (hidden_new && !count("new")) return(list(tone = "warning", title = "Neue Vorgänge vor dem Zeitraum", copy = paste0(copy,
    " – sie werden nicht gebucht. Zum Buchen „Alle Zeiträume“ oder ein früheres Datum wählen und erneut prüfen.", missing)))
  if (count("new")) return(list(tone = "warning", title = "Neue Vorgänge gefunden", copy = paste0(copy, " – mit „Neue Vorgänge vorbereiten“ entsteht die Vorschau; gebucht wird erst danach.", beyond_note, missing)))
  if (count("asset_missing")) return(list(tone = "warning", title = if (fx) "Devisen fehlen im Katalog" else if (crypto) "Coins fehlen im Katalog" else "Wertpapiere fehlen im Katalog", copy = paste0(copy, ".", missing)))
  if (count("booked_differs")) return(list(tone = "warning", title = "Gebucht, aber abweichend", copy = paste(copy, "– die Abweichungen stehen in der Tabelle; der Import ändert keine vorhandene Buchung.")))
  if (anchors) return(list(tone = "warning", title = "Kontoauszüge nicht vollständig belegt", copy = paste(copy, "– fehlende Belege ergänzen oder den Auszug prüfen; gebucht wird nur, was belegt ist.")))
  editable <- length(data_securities_statement_open_choices_v1(result))
  if (count("open")) return(list(tone = "warning", title = "Gebucht bis auf offene Vorgänge", copy = paste(copy, "– offene Vorgänge bucht der Import nicht; bitte von Hand buchen oder fehlende Exporte mitwählen.",
    if (editable) paste0(editable, " davon lassen sich unten mit „Im Editor öffnen“ in der Maske vorbelegen.") else "")))
  if (advance$open) return(list(tone = "warning", title = advance$title, copy = paste0(copy, ".", advance$hint)))
  list(tone = "positive", title = "Alles gebucht", copy = copy)
}

# Vorabpauschalen der Belege (#460, #471): Zaehler fuer den Statustext. open = es gibt etwas zu uebernehmen oder zu pruefen.
data_securities_statement_advance_summary_v1 <- function(review) {
  counts <- if (is.null(review$advance_lump_sum_counts)) list() else review$advance_lump_sum_counts
  count <- function(key) if (is.null(counts[[key]])) 0L else as.integer(counts[[key]])
  total <- sum(vapply(counts, as.integer, integer(1L)))
  if (!total) return(list(copy = "", open = FALSE, title = "", hint = ""))
  warn <- count("amount_missing") + count("tax_mismatch") + count("conflict") + count("asset_missing") + count("not_a_fund") + count("depot_unassigned")
  copy <- paste0(" · Vorabpauschalen: ", total, " Beleg(e)", if (count("new")) paste0(", ", count("new"), " neu") else "",
                 if (count("booked")) paste0(", ", count("booked"), " schon eingetragen") else "",
                 if (count("differs")) paste0(", ", count("differs"), " weichen ab") else "", if (warn) paste0(", ", warn, " mit Warnung") else "")
  hint <- paste0(if (count("new") || count("differs")) " Mit „Vorabpauschalen übernehmen“ werden die neuen eingetragen; abweichende ersetzt der Import nur, wenn Sie das Häkchen setzen." else "",
                 if (warn) " Warnungen stehen in der Tabelle der Vorabpauschalen; dort fehlt ein Betrag oder er passt nicht zur Steuer – bitte in Daten → „4. Steuer“ prüfen." else "")
  list(copy = copy, open = (count("new") + count("differs") + warn) > 0L, hint = hint,
       title = if (count("new")) "Vorabpauschalen gefunden" else if (count("differs")) "Vorabpauschalen weichen ab" else "Vorabpauschalen prüfen")
}

data_securities_statement_advance_frame_v1 <- function(result) {
  rows <- if (is.null(result) || is.null(result$review) || is.null(result$review$advance_lump_sum_rows)) list() else result$review$advance_lump_sum_rows
  if (!length(rows)) return(NULL)
  order <- c(new = 1L, differs = 2L, tax_mismatch = 3L, amount_missing = 4L, conflict = 5L, asset_missing = 6L, not_a_fund = 7L, depot_unassigned = 8L, booked = 9L, out_of_window = 10L)
  rows <- rows[order(vapply(rows, function(row) order[[row$status]], integer(1L)), -vapply(rows, function(row) as.integer(row$calculation_year), integer(1L)))]
  text <- function(value) if (is.null(value) || identical(value, "")) "" else as.character(value)
  data.frame(
    Status = vapply(rows, function(row) row$status_label, character(1L)),
    Jahr = vapply(rows, function(row) as.character(row$calculation_year), character(1L)),
    Fonds = vapply(rows, function(row) if (nzchar(text(row$asset_label))) row$asset_label else paste(text(row$security_name), "·", text(row$isin)), character(1L)),
    Konto = vapply(rows, function(row) text(row$account_label), character(1L)),
    `Beleg EUR` = vapply(rows, function(row) text(row$amount), character(1L)),
    `Eingetragen EUR` = vapply(rows, function(row) text(row$booked_amount), character(1L)),
    `Steuer EUR` = vapply(rows, function(row) text(row$taxes_amount), character(1L)),
    Hinweis = vapply(rows, function(row) paste(unlist(row$notes), collapse = " · "), character(1L)),
    Beleg = vapply(rows, function(row) row$file_name, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_securities_statement_rows_frame_v1 <- function(result, limit = 500L) {
  rows <- if (is.null(result) || is.null(result$review)) list() else result$review$rows
  if (!length(rows)) return(data.frame(Hinweis = "Noch keine Belege geprüft", check.names = FALSE))
  order <- c(new = 1L, booked_differs = 2L, open = 3L, asset_missing = 4L, depot_unassigned = 5L, split_adjusted = 6L, booked_combined = 7L, booked = 8L, out_of_window = 9L)
  rows <- rows[order(vapply(rows, function(row) order[[row$status]], integer(1L)), vapply(rows, function(row) row$local_date, character(1L)), decreasing = FALSE)]
  rows <- utils::head(rows, limit)
  text <- function(value) if (is.null(value) || identical(value, "")) "" else as.character(value)
  kind <- c(buy = "Kauf", sell = "Verkauf", dividend = "Dividende", deposit = "Zugang", transfer = "Transfer")
  fx_kind <- c(buy = "Devisenkauf", sell = "Devisenverkauf", deposit = "Zufluss aus Ertrag")
  open_kind <- c(transfer_out = "Abgang", transfer_in = "Eingang", direction_unknown = "Ein- oder Auszahlung", swap = "Tausch", order_time = "Auftrag",
    history_missing = "Historie des Jahres fehlt", history_outdated = "Historie zu alt", executions_missing = "Keine Ausführung im Zeitraum",
    executions_quantity_differs = "Menge der Ausführungen passt nicht", executions_ambiguous = "Ausführungen nicht eindeutig",
    export_amount_differs = "Betrag weicht vom Export ab",
                 fee_only = "Gebühr", amount_mismatch = "Transfer", same_wallet = "Transfer", dust = "Kleinstbetrag", ledger_solana = "Ledger-Solana")
  art <- function(row) if (identical(row$kind, "open")) open_kind[[row$open_kind]] else if (nzchar(text(row$currency))) fx_kind[[row$kind]] else kind[[row$kind]]
  account <- function(row) if (nzchar(text(row$related_account_label))) paste(text(row$account_label), "→", row$related_account_label) else text(row$account_label)
  fee <- function(row) if (row$kind %in% c("dividend", "deposit")) "" else if (nzchar(text(row$asset_fee))) paste(row$asset_fee, text(row$security_name)) else text(row$fee_amount)
  data.frame(
    Status = vapply(rows, function(row) row$status_label, character(1L)),
    Art = vapply(rows, art, character(1L)),
    Datum = vapply(rows, function(row) format(as.Date(row$local_date), "%d.%m.%Y"), character(1L)),
    `Wertpapier / Coin / Devise` = vapply(rows, function(row) if (nzchar(text(row$asset_label))) row$asset_label
      else if (nzchar(text(row$isin)) && !nzchar(text(row$currency))) paste(text(row$security_name), "·", row$isin) else text(row$security_name), character(1L)),
    Konto = vapply(rows, account, character(1L)),
    Stück = vapply(rows, function(row) text(if (identical(row$kind, "dividend")) row$eligible_quantity else row$quantity), character(1L)),
    Kurs = vapply(rows, function(row) text(row$unit_price), character(1L)),
    `Kurswert / Brutto EUR` = vapply(rows, function(row) text(row$gross_amount), character(1L)),
    Gebühr = vapply(rows, fee, character(1L)),
    Abweichung = vapply(rows, function(row) paste(c(unlist(row$differences), unlist(row$notes)), collapse = " · "), character(1L)),
    Beleg = vapply(rows, function(row) row$file_name, character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

data_securities_statement_documents_frame_v1 <- function(result) {
  documents <- if (is.null(result) || is.null(result$review)) list() else Filter(function(item) !identical(item$status, "candidate"), result$review$documents)
  # Exporte (CSV): uebrige Zeilen je Grund gezaehlt, z. B. stornierte oder vorlaeufige Orders
  rows <- if (is.null(result) || is.null(result$review) || is.null(result$review$row_reasons)) list() else result$review$row_reasons
  if (!length(documents) && !length(rows)) return(data.frame(Hinweis = "Jede Datei ergab einen Vorgang", check.names = FALSE))
  data.frame(Datei = c(vapply(documents, function(item) item$file_name, character(1L)),
                       vapply(rows, function(item) paste0(item$file_name, " · ", item$rows, " Zeile(n)"), character(1L))),
             Grund = c(vapply(documents, function(item) if (is.null(item$reason)) item$status else item$reason, character(1L)),
                       vapply(rows, function(item) item$reason, character(1L))),
             check.names = FALSE, stringsAsFactors = FALSE)
}

# "Im Editor öffnen" (#454, rc.273): offene Ein- und Ausgaenge und BSDEX-Auftraege ohne Ausfuehrung als Auswahl - Wert ist die
# Vorgangsnummer der Pruefung; Konto und Coin liest der Server aus dem Pruefergebnis, der Browser sieht nur die Bezeichnung.
data_securities_statement_open_choices_v1 <- function(result) {
  rows <- if (is.null(result) || is.null(result$review)) list() else Filter(function(row) isTRUE(row$editable), result$review$rows)
  if (!length(rows)) return(stats::setNames(character(), character()))
  art <- c(transfer_out = "Abgang", transfer_in = "Eingang", direction_unknown = "Ein- oder Auszahlung", ledger_solana = "Ledger-Solana",
           order_time = "Auftrag", amount_mismatch = "Handel ohne Betrag", export_amount_differs = "Betrag weicht vom Export ab",
           executions_quantity_differs = "Menge der Ausführungen passt nicht", executions_ambiguous = "Ausführungen nicht eindeutig")
  labels <- vapply(rows, function(row) paste(format(as.Date(row$local_date), "%d.%m.%Y"), art[[row$open_kind]], row$security_name, row$quantity,
                                               if (is.null(row$account_label)) "" else row$account_label, sep = " · "), character(1L))
  stats::setNames(vapply(rows, function(row) as.character(row$candidate_ordinal), character(1L)), labels)
}

# Die Werte fuer die Maske aus einem offenen Vorgang. refs: Editor-Refs von Coin und Konto. Ein Abgang traegt das Konto als Quelle,
# ein Eingang als Ziel; die Gegenseite waehlt der Eigentuemer. Ein Auftrag wird Kauf oder Verkauf (Stueckpreis = Kurswert / Menge, aus Python).
data_securities_statement_editor_form_v1 <- function(row, asset_ref, account_ref) {
  text <- function(value) if (is.null(value) || identical(value, "")) "" else as.character(value)
  trade <- row$open_kind %in% c("order_time", "amount_mismatch")
  direction <- if (trade) "" else if (is.null(row$direction)) "unknown" else row$direction
  list(event_type = if (trade) text(row$side) else "transfer", asset_ref = asset_ref,
       account_ref = if (identical(direction, "in")) "" else account_ref, related_account_ref = if (identical(direction, "in")) account_ref else "",
       local_date = row$local_date, local_time = text(row$local_time), time_zone = text(row$time_zone), quantity = text(row$quantity),
       asset_fee = if (identical(direction, "out")) text(row$asset_fee) else "", amount_mode = if (trade) "quantity_unit_price" else "",
       unit_price = if (trade) text(row$unit_price) else "", monetary_fee = if (trade) text(row$fee_amount) else "",
       hint = if (trade) "Kauf oder Verkauf aus dem Auftrag – Uhrzeit der Ausführung und Beträge mit der Börse vergleichen."
         else if (identical(direction, "in")) "Eingang ohne Gegenstück – Herkunftskonto wählen; kam er von außen, als Non-Cash-Zugang mit Anschaffung buchen."
         else if (identical(direction, "out")) "Abgang ohne Gegenstück – Zielkonto wählen; ging er nach außen, als Non-Cash-Abgang buchen."
         else "Richtung nennt der Export nicht – Quell- und Zielkonto prüfen.")
}

# Splitmitteilungen aus den Belegen (#451, rc.372): je Mitteilung eine Zeile mit Stichtag, Verhaeltnis und Stand.
data_securities_statement_split_frame_v1 <- function(result) {
  rows <- if (is.null(result) || is.null(result$review) || is.null(result$review$stock_split_rows)) list() else result$review$stock_split_rows
  if (!length(rows)) return(NULL)
  text <- function(value) if (is.null(value) || !nzchar(as.character(value))) "–" else as.character(value)
  data.frame(
    Wertpapier = vapply(rows, function(row) text(if (is.null(row$asset_label)) row$security_name else row$asset_label), character(1L)),
    Konto = vapply(rows, function(row) text(row$account_label), character(1L)),
    Stichtag = vapply(rows, function(row) pl_day_v1(row$local_date), character(1L)),
    `Verhältnis neu : alt` = vapply(rows, function(row) paste(row$ratio_numerator, ":", row$ratio_denominator), character(1L)),
    `Bestand vom` = vapply(rows, function(row) pl_day_v1(row$record_date), character(1L)),
    `Zusatzstücke laut Beleg` = vapply(rows, function(row) pl_quantity_v1(row$credited_quantity), character(1L)),
    Stand = vapply(rows, function(row) text(row$status_label), character(1L)),
    Hinweis = vapply(rows, function(row) if (length(row$notes)) paste(unlist(row$notes), collapse = "; ") else "–", character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

# Die split-bereinigt gebuchten Vorgaenge, die mit dem Split Stueckzahl und Kurs ihres Belegs bekommen.
data_securities_statement_conversion_frame_v1 <- function(result) {
  rows <- if (is.null(result) || is.null(result$review) || is.null(result$review$stock_split_conversion_rows)) list() else result$review$stock_split_conversion_rows
  if (!length(rows)) return(NULL)
  kinds <- c(buy = "Kauf", sell = "Verkauf", dividend = "Dividende")
  quantity <- function(value) if (is.null(value)) "–" else pl_quantity_v1(value)
  price <- function(value) if (is.null(value)) "–" else pl_price_v1(value)
  data.frame(
    Datum = vapply(rows, function(row) pl_day_v1(row$local_date), character(1L)),
    Art = vapply(rows, function(row) if (row$kind %in% names(kinds)) unname(kinds[[row$kind]]) else row$kind, character(1L)),
    Wertpapier = vapply(rows, function(row) as.character(row$asset_label), character(1L)),
    `Stück gebucht` = vapply(rows, function(row) quantity(row$booked_quantity), character(1L)),
    `Stück laut Beleg` = vapply(rows, function(row) quantity(row$document_quantity), character(1L)),
    `Kurs gebucht` = vapply(rows, function(row) price(row$booked_unit_price), character(1L)),
    `Kurs laut Beleg` = vapply(rows, function(row) price(row$document_unit_price), character(1L)),
    check.names = FALSE, stringsAsFactors = FALSE)
}

# Beschriftung der Aktion: was der Klick tut.
data_securities_statement_split_action_v1 <- function(review) {
  splits <- if (is.null(review$stock_split_new_count)) 0L else as.integer(review$stock_split_new_count)
  conversions <- if (is.null(review$stock_split_conversion_count)) 0L else as.integer(review$stock_split_conversion_count)
  if (splits + conversions < 1L) return(NULL)
  noun <- function(count) if (count == 1L) "Vorgang" else "Vorgänge"
  if (splits && conversions) sprintf("%s übernehmen und %d %s umstellen", if (splits == 1L) "Split" else paste(splits, "Splits"), conversions, noun(conversions))
  else if (splits) (if (splits == 1L) "Split übernehmen" else paste(splits, "Splits übernehmen"))
  else sprintf("%d %s auf Belegstücke umstellen", conversions, noun(conversions))
}

# Rueckmeldung nach dem Uebernehmen; die Gruende einer Ablehnung in Worten.
data_securities_statement_split_message_v1 <- function(recorded = NULL, code = NULL, published = NULL) {
  if (!is.null(code)) return(list(tone = "error", title = "Nicht vollständig übernommen", copy = switch(code,
    securities_statement_stock_split_blocked = "Ein Schritt wurde abgewiesen. Was bis dahin übernommen oder umgestellt ist, bleibt gebucht; „Belege prüfen“ zeigt den Rest.",
    securities_statement_review_invalid = "Die Prüfung ist nicht mehr aktuell – bitte erneut „Belege prüfen“.",
    securities_statement_scope_choice_required = "Buchungen einer nicht gewählten Klasse: bitte zuerst „Klasse dazunehmen“ oder „Diese Buchungen überspringen“ wählen.",
    pl_error_text_v1(code))))
  parts <- c(if (as.integer(recorded$recorded_split_count) > 0L) paste(recorded$recorded_split_count, if (recorded$recorded_split_count == 1L) "Split gespeichert" else "Splits gespeichert"),
    if (as.integer(recorded$converted_count) > 0L) paste(recorded$converted_count, if (recorded$converted_count == 1L) "Vorgang auf Belegstücke umgestellt" else "Vorgänge auf Belegstücke umgestellt"))
  list(tone = "success", title = "Kapitalmaßnahme übernommen", copy = paste0(paste(parts, collapse = ", "), ". FIFO-Stand fortgeschrieben",
    if (identical(published, "published")) ", Tageshistorie neu veröffentlicht" else "", ". Erneut geprüft:"))
}
