# Kursanbieter je Datenraum (rc.383, #495). Festlegungen vom 09.11.2026: aktiviert wird je Datenraum, nicht je
# Portfolio (alle Portfolios teilen die Kurshistorie). Yahoo wird mitgeliefert und bei der Einrichtung empfohlen. Beim Aktivieren stehen
# Adressen, Kosten und Bedingungen da: Der Dienst erfaehrt, welche Kurse abgerufen werden (#546). Ohne Abschottung laeuft nur ein
# mitgeliefertes Plugin, sichtbar gekennzeichnet. Gesperrt wird in den abrufenden Skripten (<modul>_provider_inactive).

DATA_PRICE_PROVIDER_INACTIVE_TEXT_V1 <- paste(
  "Der Kursanbieter ist in diesem Datenraum nicht aktiv, deshalb ruft Portelyra keine Kurse ab.",
  "Aktivieren unter Daten → „Transaktionen“ → „Kursanbieter“; die vorhandenen Kurse bleiben erhalten.")
DATA_PRICE_PROVIDER_STATE_TEXT_V1 <- paste(
  "Die Einstellung der Kursanbieter in diesem Datenraum ist nicht lesbar, deshalb ruft Portelyra keine Kurse ab.",
  "Den Reiter Daten → „Transaktionen“ → „Kursanbieter“ öffnen; bleibt die Meldung, das Backup prüfen.")

# Fuer jede Stelle, die einen Abrufcode anzeigt: der genaue Grund, wenn ein Kursanbieter gesperrt hat, sonst NULL.
data_price_provider_block_text_v1 <- function(code) {
  code <- as.character(code)
  if (length(code) != 1L || is.na(code)) return(NULL)
  if (grepl("_provider_inactive$", code)) return(DATA_PRICE_PROVIDER_INACTIVE_TEXT_V1)
  if (grepl("_provider_state_invalid$", code)) return(DATA_PRICE_PROVIDER_STATE_TEXT_V1)
  NULL
}

data_price_providers_abort_v1 <- function(code) {
  stop(structure(class = c("spot_price_providers_error_v1", "error", "condition"), list(message = code, call = NULL, code = code)))
}

data_price_providers_error_text_v1 <- function(code) switch(as.character(code),
  price_provider_admin_preview_stale = "Der Stand hat sich seit der Vorschau geändert. Bitte die Änderung erneut prüfen.",
  price_provider_admin_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.",
  price_provider_admin_store_invalid = "Die Einstellung der Kursanbieter ist nicht lesbar. Bitte das Backup prüfen.",
  price_provider_admin_input_invalid = "Die Anfrage war unvollständig. Bitte „Neu lesen“ und erneut versuchen.",
  price_provider_unavailable = "Für diesen Anbieter ist kein gültiges Plugin geladen.",
  price_provider_costs_preview_stale = "Die Kosten-Einstellung hat sich seit der Vorschau geändert. Bitte erneut prüfen.",
  price_provider_costs_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.",
  price_provider_costs_input_invalid = "Obergrenzen sind ganze Zahlen ab 1; leer heißt ohne Grenze.",
  price_provider_costs_store_invalid = "Die Kosten-Einstellung ist nicht lesbar. Bitte das Backup prüfen.",
  # Pakete und Updates (#486 Schritt 3, Festlegung 16.11.2026)
  price_provider_install_package_invalid = "Die Datei ist kein lesbares Kursanbieter-Paket (ZIP mit package.json und Plugin-Ordner).",
  price_provider_install_package_file_mismatch = "Eine Datei des Pakets weicht von ihrer Prüfsumme ab oder fehlt; das Paket wurde verändert.",
  price_provider_install_too_large = "Das Paket ist zu groß (höchstens 10 MB gepackt, 20 MB entpackt, 300 Dateien).",
  price_provider_install_unsafe = "Das Paket enthält eine Verknüpfung oder einen Pfad außerhalb des Plugin-Ordners.",
  price_provider_install_update_unsigned = "Ein Update eines mitgelieferten Anbieters wird nur mit Portelyra-Signatur installiert; eigene Anbieter brauchen eine eigene Kennung.",
  price_provider_install_update_not_newer = "Das Update ist nicht neuer als die mitgelieferte Fassung; es gilt die höhere.",
  price_provider_install_update_provider_changed = "Ein Update muss die Anbieter-Kennung des mitgelieferten Anbieters behalten.",
  price_provider_install_id_taken = "Ein anderer Kursanbieter trägt schon diese Anbieter-Kennung.",
  price_provider_install_selftest_failed = "Der Selbsttest des Pakets ist nicht bestanden; installiert wird nur, was ihn besteht.",
  price_provider_install_preview_stale = "Seit der Prüfung hat sich etwas geändert – bitte das Paket erneut prüfen.",
  price_provider_install_confirmation_required = "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.",
  price_provider_install_store_invalid = "Der Bereich der Kursanbieter im Datenraum ist nicht lesbar oder nicht schreibbar.",
  price_provider_revert_unavailable = "Es gibt keine vorige Fassung, zu der zurückgegangen werden kann.",
  price_provider_isolation_unavailable = "Fremde und aktualisierte Kursanbieter laufen nur abgeschottet (Linux ab Kernel 6.2); hier ist das nicht verfügbar.",
  price_provider_update_signature_invalid = "Die Signatur eines installierten Updates gilt nicht (mehr); Portelyra nimmt die mitgelieferte Fassung.",
  price_provider_plugin_signature_untrusted = "Das Paket ist signiert, aber nicht mit einem Schlüssel von Portelyra.",
  price_provider_plugin_signature_invalid = "Die Signatur passt nicht zum Inhalt des Pakets; es wurde nach dem Signieren verändert.",
  price_provider_plugin_signature_tool_missing = "Die Signatur lässt sich nicht prüfen, weil ssh-keygen fehlt.",
  "Die Kursanbieter sind gerade nicht lesbar.")

data_price_providers_error_copy_v1 <- function(code) sprintf("%s (%s)", data_price_providers_error_text_v1(code), as.character(code))

new_data_price_providers_service_v1 <- function(project_root, context, cli_runner = NULL) {
  root <- normalizePath(project_root, winslash = "/", mustWork = TRUE)
  python <- Sys.which("python3"); cli <- file.path(root, "scripts", "desktop_price_providers.py")
  space <- if (is.null(cli_runner)) runtime_data_space_path(context) else ""
  if (is.null(cli_runner) && (!nzchar(python) || !file.exists(cli) || nzchar(Sys.readlink(cli)) || !dir.exists(space)))
    data_price_providers_abort_v1("price_provider_admin_store_invalid")
  payload <- list(tenant_id = context$tenant_id, user_id = context$user_id, data_space_id = context$data_space_id, actor_id = context$actor_id, role = "desktop_owner")
  request <- function(extra) as.character(jsonlite::toJSON(c(list(context = payload, data_space_path = space), extra), auto_unbox = TRUE, null = "null", digits = NA))
  parse <- function(output, status = 0L) {
    parsed <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    if (is.null(parsed) || !identical(parsed$status, "completed") || !identical(as.integer(status), 0L))
      data_price_providers_abort_v1(if (is.list(parsed) && is.character(parsed$code)) parsed$code else "price_provider_admin_store_invalid")
    parsed$result
  }
  run <- if (is.function(cli_runner)) cli_runner else function(command, extra) {
    output <- suppressWarnings(system2(python, c("-B", "-E", "-s", shQuote(cli), command), stdout = TRUE, stderr = FALSE, input = request(extra)))
    status <- attr(output, "status"); parse(output, if (is.null(status)) 0L else status)
  }
  list(
    overview = function() run("overview", list()),
    preview = function(provider_id, active) run("activation-preview", list(provider_id = provider_id, active = isTRUE(active))),
    apply = function(preview, confirmed) run("activation-apply", list(preview = preview, confirmed = isTRUE(confirmed))),
    selftest = function(provider_id) run("selftest", list(provider_id = provider_id)),
    costs = function() run("costs-overview", list()),
    costs_preview = function(provider_id, scheduled_enabled, daily_cap, monthly_cap) run("costs-preview", list(provider_id = provider_id,
      scheduled_enabled = isTRUE(scheduled_enabled), daily_cap = daily_cap, monthly_cap = monthly_cap)),
    costs_apply = function(preview, confirmed) run("costs-apply", list(preview = preview, confirmed = isTRUE(confirmed))),
    # Pakete (#486 Schritt 3): Installieren nach Vorschau und Bestaetigung, "Zur vorigen Fassung".
    install_preview = function(zip_path) run("install-preview", list(zip_path = zip_path)),
    install_apply = function(zip_path, preview_fingerprint, recorded_at_utc, confirmed) run("install-apply", list(zip_path = zip_path,
      preview_fingerprint = preview_fingerprint, recorded_at_utc = recorded_at_utc, confirmed = isTRUE(confirmed))),
    revert_preview = function(plugin_id) run("revert-preview", list(plugin_id = plugin_id)),
    revert_apply = function(plugin_id, preview_fingerprint, recorded_at_utc, confirmed) run("revert-apply", list(plugin_id = plugin_id,
      preview_fingerprint = preview_fingerprint, recorded_at_utc = recorded_at_utc, confirmed = isTRUE(confirmed))))
}

.data_price_providers_text_v1 <- function(value) if (is.character(value) && length(value) == 1L && nzchar(value)) value else "–"

data_price_providers_active_input_id_v1 <- function(index) sprintf("data_price_providers_active_%d", as.integer(index))

data_price_providers_state_text_v1 <- function(row) {
  if (identical(row$state, "new")) return("neu – noch nicht eingestellt")
  if (identical(row$origin_of_state, "existing_data_space")) return("aktiv – Bestand bis rc.382")
  word <- if (isTRUE(row$active)) "aktiv" else "nicht aktiv"
  if (is.character(row$since)) sprintf("%s seit %s", word, pl_day_v1(row$since)) else word
}

data_price_providers_ui_v1 <- function() shiny::tagList(
  portelyra_card("Kursanbieter", help = "app-data#kursanbieter",
    copy = "Kursanbieter liefern Tageskurse, Wechselkurse und Kurse der laufenden Sitzung. Hier schalten Sie einen Anbieter für diesen Datenraum ein oder aus; alle Portfolios teilen dieselbe Kurshistorie.",
    note = portelyra_note_v1(title = "So lesen Sie die Tabelle", id = "data-price-providers",
      "Ein Anbieter-Plugin baut nur die Anfrage und liest die Antwort. Abgerufen wird von Portelyra selbst, ausschließlich an die genannten Adressen.",
      "Der Dienst erfährt dabei, welche Kurse abgerufen werden – also ungefähr, was Sie halten. Abruf, Kosten und die Bedingungen des Anbieters verantworten Sie; Portelyra ist kostenlos und ohne Gewähr.",
      "„Bestand bis rc.382“: In Datenräumen aus der Zeit vor rc.383 bleibt ein Anbieter, mit dem dort schon Kurse entstanden sind, aktiv, bis Sie ihn ausschalten.",
      "Ausschalten löscht nichts: Die vorhandene Kurshistorie bleibt, nur neue Kurse werden nicht mehr abgerufen."),
    if (exists("PL_PRICE_PROVIDER_DEFAULT_NOTE_V1")) shiny::p(class = "pl-field-hint", PL_PRICE_PROVIDER_DEFAULT_NOTE_V1),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_refresh", "Neu lesen", class = "btn-default")),
    shiny::uiOutput("data_price_providers_state"),
    shiny::uiOutput("data_price_providers_table"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_preview", "Änderung prüfen", class = "btn-default")),
    shiny::uiOutput("data_price_providers_preview_panel"),
    shiny::uiOutput("data_price_providers_revert_preview"),
    shiny::uiOutput("data_price_providers_costs"),
    shiny::uiOutput("data_price_providers_costs_preview"),
    shiny::h4(class = "pl-section-title", "Selbsttest"),
    shiny::p(class = "pl-field-hint", "Prüft das Plugin mit seinen erfundenen Testantworten, veränderten und erfundenen Antworten – ohne Netz, ohne Ihre Daten."),
    shiny::uiOutput("data_price_providers_selftest_choice"),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_selftest", "Selbsttest starten", class = "btn-default")),
    shiny::uiOutput("data_price_providers_selftest_result")))

data_price_providers_table_ui_v1 <- function(overview) {
  if (is.null(overview)) return(NULL)
  if (!is.null(attr(overview, "code"))) return(portelyra_status_panel("Kursanbieter nicht lesbar", data_price_providers_error_copy_v1(attr(overview, "code")), tone = "warning"))
  rows <- overview$providers; text <- .data_price_providers_text_v1
  if (!length(rows)) return(portelyra_status_panel("Kein Kursanbieter geladen", "Es ist kein gültiges Kursanbieter-Plugin vorhanden.", tone = "warning"))
  cells <- lapply(seq_along(rows), function(index) {
    row <- rows[[index]]
    list(
      shiny::tagList(shiny::checkboxInput(data_price_providers_active_input_id_v1(index), shiny::tagList("aktiv", shiny::span(class = "sr-only", sprintf(" – %s", text(row$label)))),
        value = isTRUE(row$active)), shiny::div(class = "pl-field-hint", data_price_providers_state_text_v1(row))),
      text(row$label),
      shiny::tagList(if (is.character(row$replaces_shipped)) sprintf("%s (Update der mitgelieferten %s)", text(row$plugin_version), text(row$replaces_shipped)) else
        text(row$plugin_version),
        # Installierte Fassung zuruecknehmen (#486 Schritt 3): zur frueheren, zur mitgelieferten oder - eigener Anbieter - nicht mehr laden.
        if (identical(row$origin, "installed")) shiny::div(shiny::actionButton(data_price_providers_revert_input_id_v1(index), "Zur vorigen Fassung …",
          class = "btn-default btn-sm", `aria-label` = sprintf("„%s“ zur vorigen Fassung …", text(row$label))))),
      text(row$cost_text), paste(unlist(row$hosts), collapse = ", "),
      if (isTRUE(row$isolated)) "abgeschottet" else "läuft ohne Abschottung",
      shiny::tags$a(href = row$terms_url, target = "_blank", rel = "noopener noreferrer", "Bedingungen"))
  })
  shiny::div(class = "pl-table-wrap", pl_table_v1(c("Stand", "Anbieter", "Version", "Kosten", "Abruf bei", "Abschottung", "Bedingungen"), cells))
}

data_price_providers_revert_input_id_v1 <- function(index) sprintf("data_price_providers_revert_%d", as.integer(index))

# Vorschau eines Kursanbieter-Pakets (#486 Schritt 3): Anbieter, Signatur, Adressen, Kosten, Bedingungen, Selbsttest, was es abloest.
data_price_providers_install_preview_ui_v1 <- function(preview) {
  if (is.null(preview)) return(NULL)
  if (!is.null(attr(preview, "code"))) return(portelyra_status_panel("Prüfung nicht möglich", data_price_providers_error_copy_v1(attr(preview, "code")), tone = "error"))
  text <- .data_price_providers_text_v1; signed <- isTRUE(preview$publisher_verified)
  previous <- if (is.list(preview$replaces)) sprintf("ersetzt die installierte Version %s", text(preview$replaces$plugin_version)) else
    if (is.list(preview$replaces_shipped)) sprintf("mitgelieferte Version %s – dieses Update löst sie ab", text(preview$replaces_shipped$plugin_version)) else
    "nicht installiert – wird neu installiert und ist danach nicht aktiv"
  selftest <- preview$selftest
  facts <- list(
    c("Anbieter", sprintf("%s (Kennung %s)", text(preview$label), text(preview$provider_id))),
    c("Version", text(preview$plugin_version)),
    c("Herausgeber", paste0(text(preview$publisher), " (laut Manifest) – ", if (signed) "von Portelyra signiert" else "ungeprüft: nicht von Portelyra signiert")),
    c("Abruf bei", paste(unlist(preview$hosts), collapse = ", ")),
    c("Kosten", text(preview$cost)),
    c("Selbsttest", if (!is.list(selftest)) "nicht gerechnet" else if (isTRUE(selftest$passed)) "bestanden (ohne Netz)" else "nicht bestanden"),
    c("Bisher", previous))
  problems <- unlist(preview$problems, use.names = FALSE)
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: Kursanbieter „%s“ Version %s", text(preview$label), text(preview$plugin_version))),
    shiny::tags$ul(class = "pl-plain-list", lapply(facts, function(fact) shiny::tags$li(shiny::tags$strong(paste0(fact[[1L]], ": ")), fact[[2L]]))),
    if (is.character(preview$terms_url)) shiny::p(shiny::tags$a(href = preview$terms_url, target = "_blank", rel = "noopener noreferrer", "Bedingungen des Anbieters")),
    if (length(problems)) portelyra_status_panel("Nicht installierbar", shiny::tags$ul(lapply(problems, function(code) shiny::tags$li(data_price_providers_error_copy_v1(code)))), tone = "error"),
    if (isTRUE(preview$installable)) shiny::tagList(
      shiny::p(class = "pl-field-hint", if (is.list(preview$replaces_shipped) || is.list(preview$replaces)) paste("Aktivierung, Kosten-Einstellung und Zugang",
        "bleiben, wie sie sind; „Zur vorigen Fassung“ nimmt das Update zurück.") else "Aktiviert wird der Anbieter danach im Reiter „Kursanbieter“ – mit Adressen, Kosten und Bedingungen."),
      if (!signed) shiny::checkboxInput("data_price_providers_install_unchecked", paste("Ich weiß, dass Portelyra diesen Kursanbieter nicht geprüft hat: Er baut",
        "Anfragen und liest Antworten mit Code eines anderen Herausgebers. Ich installiere ihn trotzdem."), FALSE),
      shiny::checkboxInput("data_price_providers_install_confirm", sprintf("Ich habe die Vorschau geprüft: „%s“ Version %s installieren.", text(preview$label),
        text(preview$plugin_version)), FALSE),
      shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_install_apply", "Installieren", class = "btn-primary"))))
}

data_price_providers_revert_preview_ui_v1 <- function(preview) {
  if (is.null(preview)) return(NULL)
  if (!is.null(attr(preview, "code"))) return(portelyra_status_panel("Zurücknehmen nicht möglich", data_price_providers_error_copy_v1(attr(preview, "code")), tone = "warning"))
  text <- .data_price_providers_text_v1
  target <- switch(text(preview$to_origin), shipped = sprintf("die mitgelieferte Version %s", text(preview$to_version)),
    installed = sprintf("die früher installierte Version %s", text(preview$to_version)), none = "keine – der Anbieter wird nicht mehr geladen (seine Dateien bleiben)", "–")
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: zur vorigen Fassung (Version %s)", text(preview$from_version))),
    shiny::p(sprintf("Danach gilt %s. Vorhandene Kurse bleiben unverändert.", target)),
    shiny::checkboxInput("data_price_providers_revert_confirm", "Ich habe die Vorschau geprüft.", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_revert_apply", "Zur vorigen Fassung", class = "btn-primary")))
}

data_price_providers_state_ui_v1 <- function(overview) {
  if (is.null(overview) || !is.null(attr(overview, "code"))) return(NULL)
  panels <- list()
  if (!isTRUE(overview$isolation_available))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Ohne Abschottung",
      "Auf diesem System steht die Abschottung nicht zur Verfügung (Linux ab Kernel 6.2). Mitgelieferte, mit jedem Release geprüfte Plugins laufen trotzdem, in einem eigenen Prozess ohne Datei- und Netzsperre; fremde Plugins nie.", tone = "warning")
  if (!any(vapply(overview$providers, function(row) isTRUE(row$active), logical(1L))))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Kein Kursanbieter aktiv",
      "Ohne aktiven Anbieter ruft Portelyra keine Kurse ab. Empfohlen für den Anfang: Yahoo Finance – kostenlos und ohne Schlüssel.", tone = "neutral")
  if (length(overview$problems))
    panels[[length(panels) + 1L]] <- portelyra_status_panel("Plugin verworfen", paste(vapply(overview$problems, function(item)
      sprintf("%s (%s)", .data_price_providers_text_v1(item$plugin_id), .data_price_providers_text_v1(item$code)), character(1L)), collapse = "; "), tone = "warning")
  if (length(panels)) shiny::tagList(panels) else NULL
}

# Erste abweichende Auswahl (ein Anbieter je Vorschau).
data_price_providers_change_v1 <- function(overview, value_of) {
  if (is.null(overview) || !is.null(attr(overview, "code"))) return(NULL)
  for (index in seq_along(overview$providers)) {
    chosen <- value_of(data_price_providers_active_input_id_v1(index))
    row <- overview$providers[[index]]
    if (!is.null(chosen) && !identical(isTRUE(chosen), isTRUE(row$active))) return(list(provider_id = row$provider_id, active = isTRUE(chosen)))
  }
  NULL
}

data_price_providers_preview_ui_v1 <- function(preview) {
  if (is.null(preview)) return(NULL)
  if (!is.null(attr(preview, "code"))) return(portelyra_status_panel("Vorschau nicht möglich", data_price_providers_error_copy_v1(attr(preview, "code")), tone = "warning"))
  if (identical(preview, "unchanged")) return(portelyra_status_panel("Nichts zu ändern", "Die Häkchen entsprechen dem gespeicherten Stand.", tone = "neutral"))
  text <- .data_price_providers_text_v1
  title <- sprintf("Vorschau: %s %s", text(preview$label), if (isTRUE(preview$active_after)) "aktivieren" else "ausschalten")
  shiny::tagList(
    shiny::h4(class = "pl-section-title", title),
    shiny::tags$ul(class = "pl-plain-list", lapply(unlist(preview$notes), function(note) shiny::tags$li(note))),
    shiny::checkboxInput("data_price_providers_confirm", if (isTRUE(preview$active_after))
      "Ich habe die Vorschau geprüft und nehme die Bedingungen des Anbieters zur Kenntnis." else "Ich habe die Vorschau geprüft.", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_apply", "Übernehmen", class = "btn-primary")))
}

data_price_providers_selftest_ui_v1 <- function(report, label = NULL) {
  if (is.null(report)) return(NULL)
  if (!is.null(attr(report, "code"))) return(portelyra_status_panel("Selbsttest nicht möglich", data_price_providers_error_copy_v1(attr(report, "code")), tone = "warning"))
  counts <- report$counts
  # Deutsche Schreibweise wie beim Selbsttest der Leser ("1,4 Sek."), der Name des Anbieters statt der Kennung.
  seconds <- suppressWarnings(as.numeric(report$duration_seconds))
  duration <- if (length(seconds) == 1L && !is.na(seconds)) paste0(formatC(seconds, format = "f", digits = 1L, decimal.mark = ","), " Sek.") else "–"
  number <- function(value) formatC(as.numeric(value), format = "d", big.mark = ".")
  summary <- sprintf("%s Testantworten, %s veränderte und %s erfundene Antworten geprüft, %s%s.", number(counts$fixtures), number(counts$mutations),
    number(counts$generated), duration, if (isTRUE(report$isolated)) ", abgeschottet" else ", ohne Abschottung")
  name <- if (is.character(label) && length(label) == 1L && nzchar(label)) label else .data_price_providers_text_v1(report$plugin_id)
  if (isTRUE(report$passed)) return(portelyra_status_panel(sprintf("Selbsttest bestanden: %s %s", name, .data_price_providers_text_v1(report$plugin_version)), summary, tone = "positive"))
  findings <- vapply(report$failures, function(item) sprintf("%s · %s · %s", item$stage, item$case, item$problem), character(1L))
  shiny::tagList(portelyra_status_panel("Selbsttest mit Befunden", summary, tone = "error"), shiny::tags$ul(class = "pl-plain-list", lapply(findings, shiny::tags$li)))
}

# Kosten (rc.390, #546): nur bei kostenpflichtigen Anbietern. Zeitlauf ja/nein, Obergrenze je Tag und Monat (leer = ohne Grenze), dazu die
# Abrufe heute und im Monat und die letzte Abweisung wegen zu vieler Abrufe (HTTP 429).
data_price_providers_costs_input_id_v1 <- function(kind, index) sprintf("data_price_providers_costs_%s_%d", kind, as.integer(index))

data_price_providers_costs_ui_v1 <- function(costs) {
  if (is.null(costs) || !is.null(attr(costs, "code")) || !length(costs$providers)) return(NULL)
  text <- .data_price_providers_text_v1
  cap <- function(value) if (is.numeric(value) && length(value) == 1L) value else NA
  shiny::tagList(
    shiny::h4(class = "pl-section-title", "Kosten"),
    shiny::p(class = "pl-field-hint", "Kostenpflichtige Anbieter laufen im täglichen Zeitlauf nur, wenn Sie es hier einschalten. Mit einer Obergrenze hält Portelyra mit Grund an; weist der Anbieter wegen zu vieler Abrufe ab (HTTP 429), endet der Lauf. Gezählt wird in UTC."),
    lapply(seq_along(costs$providers), function(index) {
      row <- costs$providers[[index]]; setting <- row$setting
      shiny::div(class = "pl-field-group",
        shiny::strong(sprintf("%s · %s", text(row$label), text(row$cost_text))),
        shiny::div(class = "pl-field-hint", sprintf("Abrufe heute %s, im Monat %s%s.", as.character(row$used_today), as.character(row$used_month),
          if (is.character(row$rate_limited_at_utc)) sprintf(" · zuletzt abgewiesen (429) am %s", pl_day_v1(row$rate_limited_at_utc)) else "")),
        shiny::checkboxInput(data_price_providers_costs_input_id_v1("scheduled", index), "Im täglichen Zeitlauf abrufen", isTRUE(setting$scheduled_enabled)),
        shiny::numericInput(data_price_providers_costs_input_id_v1("daily", index), "Obergrenze je Tag (leer = ohne)", cap(setting$daily_cap), min = 1, step = 1),
        shiny::numericInput(data_price_providers_costs_input_id_v1("monthly", index), "Obergrenze je Monat (leer = ohne)", cap(setting$monthly_cap), min = 1, step = 1),
        shiny::div(class = "pl-editor-actions", shiny::actionButton(data_price_providers_costs_input_id_v1("preview", index), "Kosten-Einstellung prüfen", class = "btn-default")))
    }))
}

data_price_providers_costs_preview_ui_v1 <- function(preview) {
  if (is.null(preview)) return(NULL)
  if (!is.null(attr(preview, "code"))) return(portelyra_status_panel("Kosten-Einstellung nicht möglich", data_price_providers_error_copy_v1(attr(preview, "code")), tone = "warning"))
  if (!isTRUE(preview$changed)) return(portelyra_status_panel("Nichts zu ändern", "Die Angaben entsprechen der gespeicherten Kosten-Einstellung.", tone = "neutral"))
  shiny::tagList(
    shiny::h4(class = "pl-section-title", sprintf("Vorschau: Kosten bei %s", .data_price_providers_text_v1(preview$label))),
    shiny::tags$ul(class = "pl-plain-list", lapply(unlist(preview$notes), function(note) shiny::tags$li(note))),
    shiny::checkboxInput("data_price_providers_costs_confirm", "Ich habe die Vorschau geprüft.", FALSE),
    shiny::div(class = "pl-editor-actions", shiny::actionButton("data_price_providers_costs_apply", "Übernehmen", class = "btn-primary")))
}

data_price_providers_server_v1 <- function(input, output, session, service, active = shiny::reactive(TRUE)) {
  overview <- shiny::reactiveVal(NULL); preview <- shiny::reactiveVal(NULL); selftest <- shiny::reactiveVal(NULL); selftest_label <- shiny::reactiveVal(NULL)
  failed <- function(error) structure(list(), code = if (is.character(error$code)) error$code else "price_provider_admin_store_invalid")
  read <- function() {
    if (is.null(service)) return(overview(structure(list(), code = "price_provider_admin_store_invalid")))
    overview(tryCatch(service$overview(), error = failed))
  }
  shiny::observeEvent(active(), if (isTRUE(active()) && is.null(overview())) read(), ignoreInit = FALSE)
  shiny::observeEvent(input$data_price_providers_refresh, { preview(NULL); read() })
  output$data_price_providers_state <- shiny::renderUI(data_price_providers_state_ui_v1(overview()))
  output$data_price_providers_table <- shiny::renderUI(data_price_providers_table_ui_v1(overview()))
  shiny::observeEvent(input$data_price_providers_preview, {
    change <- data_price_providers_change_v1(overview(), function(id) input[[id]])
    if (is.null(change)) return(preview("unchanged"))
    preview(tryCatch(service$preview(change$provider_id, change$active), error = failed))
  })
  output$data_price_providers_preview_panel <- shiny::renderUI(data_price_providers_preview_ui_v1(preview()))
  shiny::observeEvent(input$data_price_providers_apply, {
    current <- preview()
    if (!is.list(current) || !is.null(attr(current, "code"))) return(NULL)
    result <- tryCatch(service$apply(current, isTRUE(input$data_price_providers_confirm)), error = failed)
    if (!is.null(attr(result, "code"))) return(preview(result))
    preview(NULL); read()
    shiny::showNotification(sprintf("%s ist jetzt %s.", .data_price_providers_text_v1(current$label), if (isTRUE(current$active_after)) "aktiv" else "nicht aktiv"), type = "message")
  })
  # Mehrere Plugins (seit rc.392 auch EODHD): der Selbsttest gilt dem gewaehlten, ohne Wahl dem ersten.
  output$data_price_providers_selftest_choice <- shiny::renderUI({
    current <- overview(); rows <- if (is.list(current) && is.null(attr(current, "code"))) current$providers else list()
    if (length(rows) < 2L) return(NULL)
    shiny::selectInput("data_price_providers_selftest_provider", "Plugin", stats::setNames(vapply(rows, function(row) row$provider_id, character(1L)),
      vapply(rows, function(row) .data_price_providers_text_v1(row$label), character(1L))))
  })
  shiny::observeEvent(input$data_price_providers_selftest, {
    current <- overview(); rows <- if (is.list(current) && is.null(attr(current, "code"))) current$providers else list()
    if (!length(rows)) return(NULL)
    chosen <- Filter(function(row) identical(row$provider_id, input$data_price_providers_selftest_provider), rows)
    row <- if (length(chosen)) chosen[[1L]] else rows[[1L]]
    selftest_label(row$label)
    selftest(tryCatch(service$selftest(row$provider_id), error = failed))
  })
  output$data_price_providers_selftest_result <- shiny::renderUI(data_price_providers_selftest_ui_v1(selftest(), selftest_label()))
  costs <- shiny::reactiveVal(NULL); costs_preview <- shiny::reactiveVal(NULL)
  read_costs <- function() if (!is.null(service) && is.function(service$costs)) costs(tryCatch(service$costs(), error = failed))
  shiny::observeEvent(active(), if (isTRUE(active()) && is.null(costs())) read_costs(), ignoreInit = FALSE)
  shiny::observeEvent(input$data_price_providers_refresh, { costs_preview(NULL); read_costs() })
  output$data_price_providers_costs <- shiny::renderUI(data_price_providers_costs_ui_v1(costs()))
  number <- function(value) { value <- suppressWarnings(as.numeric(value)); if (length(value) != 1L || is.na(value)) NULL else if (value == round(value)) as.integer(value) else value }
  observed <- new.env(parent = emptyenv())
  shiny::observe({
    current <- costs()
    if (is.null(current) || !is.null(attr(current, "code"))) return(NULL)
    lapply(seq_along(current$providers), function(index) {
      id <- data_price_providers_costs_input_id_v1("preview", index)
      if (!is.null(observed[[id]])) return(NULL)
      observed[[id]] <- shiny::observeEvent(input[[id]], {
        rows <- shiny::isolate(costs())$providers
        if (index > length(rows)) return(NULL)
        costs_preview(tryCatch(service$costs_preview(rows[[index]]$provider_id, input[[data_price_providers_costs_input_id_v1("scheduled", index)]],
          number(input[[data_price_providers_costs_input_id_v1("daily", index)]]), number(input[[data_price_providers_costs_input_id_v1("monthly", index)]])), error = failed))
      }, ignoreInit = TRUE)
    })
  })
  output$data_price_providers_costs_preview <- shiny::renderUI(data_price_providers_costs_preview_ui_v1(costs_preview()))
  shiny::observeEvent(input$data_price_providers_costs_apply, {
    current <- costs_preview()
    if (!is.list(current) || !is.null(attr(current, "code"))) return(NULL)
    result <- tryCatch(service$costs_apply(current, isTRUE(input$data_price_providers_costs_confirm)), error = failed)
    if (!is.null(attr(result, "code"))) return(costs_preview(result))
    costs_preview(NULL); read_costs()
    shiny::showNotification(sprintf("Kosten-Einstellung für %s gespeichert.", .data_price_providers_text_v1(current$label)), type = "message")
  })
  # Pakete (#486 Schritt 3): Pruefen aus dem gemeinsamen "Paket installieren" (Einstellungen -> "Plugins"), Installieren nach Bestaetigung.
  install_preview <- shiny::reactiveVal(NULL); install_path <- shiny::reactiveVal(NULL)
  check_install <- function(request) {
    install_path(request$zip_path)
    install_preview(if (is.null(service)) structure(list(), code = "price_provider_admin_store_invalid") else
      shiny::withProgress(message = "Kursanbieter wird geprüft", detail = "samt Selbsttest ohne Netz", value = 0.3, tryCatch(service$install_preview(request$zip_path), error = failed)))
  }
  shiny::observeEvent(input$data_plugin_package_file, { install_preview(NULL); install_path(NULL) }, ignoreInit = TRUE)
  output$data_price_providers_install_preview <- shiny::renderUI(data_price_providers_install_preview_ui_v1(install_preview()))
  shiny::observeEvent(input$data_price_providers_install_apply, {
    current <- install_preview(); path <- install_path()
    if (!is.list(current) || !isTRUE(current$installable) || is.null(path)) return(NULL)
    if (!isTRUE(input$data_price_providers_install_confirm) || (!isTRUE(current$publisher_verified) && !isTRUE(input$data_price_providers_install_unchecked))) {
      shiny::showNotification(if (isTRUE(current$publisher_verified)) "Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben." else
        "Dieser Kursanbieter ist nicht von Portelyra signiert; bitte zusätzlich bestätigen, dass Sie ihn trotzdem installieren.", type = "warning")
      return(NULL)
    }
    result <- tryCatch(service$install_apply(path, current$preview_fingerprint, format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), TRUE), error = failed)
    if (!is.null(attr(result, "code"))) return(install_preview(result))
    install_preview(NULL); install_path(NULL); read()
    shiny::showNotification(sprintf("Kursanbieter „%s“ Version %s ist installiert.", .data_price_providers_text_v1(current$label), .data_price_providers_text_v1(result$plugin_version)),
                            type = "message")
  })
  revert_preview <- shiny::reactiveVal(NULL); revert_plugin <- shiny::reactiveVal(NULL)
  revert_buttons <- new.env(parent = emptyenv())
  shiny::observe({
    current <- overview(); rows <- if (is.list(current) && is.null(attr(current, "code"))) current$providers else list()
    for (index in seq_along(rows)) {
      id <- data_price_providers_revert_input_id_v1(index)
      if (exists(id, envir = revert_buttons, inherits = FALSE)) next
      local({ position <- index; button <- id
        assign(button, shiny::observeEvent(input[[button]], {
          now <- shiny::isolate(overview()); listed <- if (is.list(now) && is.null(attr(now, "code"))) now$providers else list()
          if (position > length(listed)) return(NULL)
          revert_plugin(listed[[position]]$plugin_id)
          revert_preview(tryCatch(service$revert_preview(listed[[position]]$plugin_id), error = failed))
        }, ignoreInit = TRUE), envir = revert_buttons) })
    }
  })
  output$data_price_providers_revert_preview <- shiny::renderUI(data_price_providers_revert_preview_ui_v1(revert_preview()))
  shiny::observeEvent(input$data_price_providers_revert_apply, {
    current <- revert_preview()
    if (!is.list(current) || !is.null(attr(current, "code"))) return(NULL)
    if (!isTRUE(input$data_price_providers_revert_confirm)) { shiny::showNotification("Bitte zuerst bestätigen, dass Sie die Vorschau geprüft haben.", type = "warning"); return(NULL) }
    result <- tryCatch(service$revert_apply(revert_plugin(), current$preview_fingerprint, format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"), TRUE), error = failed)
    if (!is.null(attr(result, "code"))) return(revert_preview(result))
    revert_preview(NULL); read()
    shiny::showNotification("Zur vorigen Fassung zurückgenommen.", type = "message")
  })
  invisible(list(overview = overview, read = read, costs = costs, check_install = check_install))
}
